import re
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.services.container import get_service, require_identity
from app.services.export import iter_file
from app.services.service import ReportService

router = APIRouter(prefix="/api/v1/clients/{client_id}/reports", tags=["reports"], dependencies=[Depends(require_identity)])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_LETTER_RE = re.compile(r"^[A-Za-z]$")


def _xlsx_response(handle, filename: str) -> StreamingResponse:
    # filename solo contiene [A-Za-z0-9_.-]: client_id está validado y el resto lo arma el servicio
    return StreamingResponse(
        iter_file(handle),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/users")
def users_report(
    client_id: str,
    letra: str = Query(..., description="Letra A-Z (por el inicio del login) o 'Todos'"),
    service: ReportService = Depends(get_service),
):
    letra = letra.strip()
    if letra.lower() == "todos":
        letra = "Todos"
    elif not _LETTER_RE.match(letra):
        raise HTTPException(422, "Parámetro 'letra' inválido: debe ser una letra A-Z o 'Todos'.")
    handle, _ = service.export(client_id, "users", {"letter": letra})
    return _xlsx_response(handle, f"reporte_usuarios_{client_id}_{letra.lower()}.xlsx")


@router.get("/audit")
def audit_report(
    client_id: str,
    desde: date = Query(..., description="Fecha inicial (inclusive), YYYY-MM-DD, en la zona del reporte"),
    hasta: date = Query(..., description="Fecha final (inclusive), YYYY-MM-DD"),
    service: ReportService = Depends(get_service),
):
    settings = service.settings
    if desde > hasta:
        raise HTTPException(422, "'desde' no puede ser posterior a 'hasta'.")
    if (hasta - desde).days + 1 > settings.max_range_days:
        raise HTTPException(422, f"El rango no puede superar {settings.max_range_days} días.")

    tz = service.tz
    start = int(datetime.combine(desde, time.min, tzinfo=tz).timestamp())
    end_exclusive = int(datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=tz).timestamp())
    handle, _ = service.export(client_id, "audit", {"start": start, "end_exclusive": end_exclusive})
    return _xlsx_response(handle, f"auditoria_{client_id}_{desde}_a_{hasta}.xlsx")
