"""Generación del .xlsx en streaming, con memoria acotada.

Cargar todo en un DataFrame y luego escribirlo multiplica la memoria por el tamaño de la tabla.
Aquí las filas se leen de la BD por bloques y se escriben una a una con el modo ``write_only`` de
openpyxl; el archivo en construcción vive en un ``SpooledTemporaryFile`` que se vuelca a disco
al superar ``spool_max_bytes``. La memoria depende del tamaño del bloque, no de la tabla.
"""

import logging
import re
from decimal import Decimal
from tempfile import SpooledTemporaryFile
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from sqlalchemy import column, inspect, table
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.services.reports import ReportContext, ReportSpec

logger = logging.getLogger(__name__)

# Límite de una celda en la especificación OOXML
EXCEL_CELL_CHAR_LIMIT = 32_767
# Caracteres de control que openpyxl rechaza (IllegalCharacterError) y rompen el XML
_ILLEGAL_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BOLD = Font(bold=True)


class SchemaMismatch(ValueError):
    """La base del cliente no tiene la tabla o las columnas esperadas."""


class ReportTooLarge(Exception):
    def __init__(self, max_rows: int):
        super().__init__(f"El reporte supera el máximo de {max_rows} filas.")
        self.max_rows = max_rows


def check_schema(engine: Engine, spec: ReportSpec) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(spec.table):
        raise SchemaMismatch(f"Falta la tabla '{spec.table}'")
    present = {c["name"] for c in inspector.get_columns(spec.table)}
    missing = [c for c in spec.columns if c not in present]
    if missing:
        raise SchemaMismatch(f"Columnas faltantes en '{spec.table}': {missing}")


def _clean_value(value: Any) -> Any:
    """Valor apto para escribir en una celda."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        value = _ILLEGAL_XML_CHARS.sub("", value)
        if len(value) > EXCEL_CELL_CHAR_LIMIT:
            value = value[: EXCEL_CELL_CHAR_LIMIT - 3] + "..."
        return value
    if isinstance(value, Decimal):
        return float(value)
    return value


def _cell(ws, value: Any):
    """Celda lista para escribir.

    openpyxl interpreta como FÓRMULA cualquier texto que empiece con '=': un nombre de usuario como
    ``=HYPERLINK("http://...")`` se ejecutaría al abrir el archivo (inyección de fórmulas). Esos
    valores se fuerzan a tipo texto: se ven tal cual y nunca se evalúan, sin alterar el dato
    (a diferencia de anteponer un apóstrofo, que quedaría visible en la celda).
    """
    value = _clean_value(value)
    if isinstance(value, str) and value.startswith("="):
        cell = WriteOnlyCell(ws, value=value)
        cell.data_type = "s"
        return cell
    return value


def generate_workbook(
    engine: Engine, spec: ReportSpec, params: dict, ctx: ReportContext, settings: Settings
) -> tuple[SpooledTemporaryFile, int]:
    """Devuelve (archivo posicionado al inicio, cantidad de filas)."""
    check_schema(engine, spec)

    source = table(spec.table, *[column(c) for c in spec.columns])
    # max_rows + 1: si llega esa fila extra se sabe que hay más sin leer toda la tabla
    query = spec.build_query(source, params).limit(settings.max_rows + 1)

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(spec.sheet)
    try:
        rows = _fill(sheet, engine, spec, query, ctx, settings)
        output = SpooledTemporaryFile(max_size=settings.spool_max_bytes)  # noqa: SIM115 - lo cierra el stream
        try:
            workbook.save(output)
        except BaseException:
            output.close()
            raise
        output.seek(0)
        return output, rows
    finally:
        # En modo write_only cada hoja mantiene un generador y archivos temporales abiertos hasta
        # que se guarda. Si la exportación aborta a mitad (p. ej. ReportTooLarge) hay que cerrarla
        # explícitamente; si no, el generador se finaliza tarde, con el archivo ya cerrado.
        if not sheet.closed:
            sheet.close()
        workbook.close()


def _fill(sheet, engine: Engine, spec: ReportSpec, query, ctx: ReportContext, settings: Settings) -> int:
    sheet.freeze_panes = "A2"
    for index, header in enumerate(spec.columns.values(), start=1):
        sheet.column_dimensions[_col_letter(index)].width = min(max(len(header) + 4, 12), 40)

    header_cells = []
    for header in spec.columns.values():
        cell = WriteOnlyCell(sheet, value=header)
        cell.font = _BOLD
        header_cells.append(cell)
    sheet.append(header_cells)

    names = list(spec.columns)
    rows = 0
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(query)
        for chunk in result.partitions(settings.fetch_chunk_size):
            for record in chunk:
                rows += 1
                if rows > settings.max_rows:
                    raise ReportTooLarge(settings.max_rows)
                sheet.append(
                    [
                        _cell(sheet, spec.converters[name](value, ctx) if name in spec.converters else value)
                        for name, value in zip(names, record, strict=True)
                    ]
                )
    return rows


def _col_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def iter_file(handle: SpooledTemporaryFile, chunk_size: int = 64 * 1024):
    """Entrega el archivo por bloques y lo cierra (y por tanto lo borra) al terminar o abortar."""
    try:
        while chunk := handle.read(chunk_size):
            yield chunk
    finally:
        handle.close()
