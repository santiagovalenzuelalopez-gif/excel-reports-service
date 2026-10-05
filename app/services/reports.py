"""Definición declarativa de reportes.

Un reporte es: tabla + columnas permitidas (columna en BD -> encabezado en Excel) + cómo filtrar.
Los identificadores (tabla y columnas) salen SIEMPRE de estas definiciones, nunca de la petición,
y se arman con ``sqlalchemy.table/column`` (con entrecomillado), no con f-strings de SQL.
Agregar un reporte nuevo es agregar una ``ReportSpec``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, TableClause, func, select


@dataclass(frozen=True)
class ReportContext:
    tz: ZoneInfo


@dataclass(frozen=True)
class ReportSpec:
    key: str
    sheet: str
    table: str
    columns: dict[str, str]  # columna en BD -> encabezado
    build_query: Callable[[TableClause, dict], Select]
    converters: dict[str, Callable[[Any, ReportContext], Any]] = field(default_factory=dict)


def _users_query(t: TableClause, params: dict) -> Select:
    query = select(*t.c).select_from(t).order_by(t.c.id)
    letter = params["letter"]
    if letter != "Todos":
        # lower() + LIKE: sensible a mayúsculas igual en cualquier motor (no depende del collation)
        query = query.where(func.lower(t.c.login).like(f"{letter.lower()}%"))
    return query


def _audit_query(t: TableClause, params: dict) -> Select:
    return (
        select(*t.c)
        .select_from(t)
        .where(t.c.created_at >= params["start"], t.c.created_at < params["end_exclusive"])
        .order_by(t.c.created_at.desc(), t.c.id.desc())
    )


def _epoch_to_local(value: Any, ctx: ReportContext) -> datetime | None:
    """Epoch (segundos) -> fecha y hora en la zona del reporte, sin tz (Excel no soporta datetimes con tz)."""
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), ctx.tz).replace(tzinfo=None)


USERS = ReportSpec(
    key="users",
    sheet="Usuarios",
    table="users",
    columns={
        "id": "ID Registro",
        "name": "Nombre",
        "login": "Login",
        "doc_type": "Tipo de identificación",
        "doc_number": "Número de identificación",
        "email": "E-mail",
        "address": "Dirección",
        "phone": "Teléfono",
        "country": "País",
        "department": "Departamento",
        "city": "Municipio",
        "kind": "Tipo",
        "status": "Estado",
    },
    build_query=_users_query,
)

AUDIT = ReportSpec(
    key="audit",
    sheet="Auditoría",
    table="audit_log",
    columns={
        "id": "ID Registro",
        "created_at": "Fecha",
        "ip": "IP",
        "user_id": "ID Usuario",
        "login": "Login",
        "entity": "Tabla",
        "entity_2": "Tabla secundaria",
        "entity_id": "ID Registro afectado",
        "action": "Acción",
        "detail": "Detalle",
    },
    build_query=_audit_query,
    converters={"created_at": _epoch_to_local},
)

REPORTS = {spec.key: spec for spec in (USERS, AUDIT)}
