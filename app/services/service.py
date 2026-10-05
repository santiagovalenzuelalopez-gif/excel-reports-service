import logging
from tempfile import SpooledTemporaryFile
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.services.clients import CLIENT_ID_RE, ClientLookupError, ClientResolver, ephemeral_engine
from app.services.export import ReportTooLarge, SchemaMismatch, generate_workbook
from app.services.reports import REPORTS, ReportContext

logger = logging.getLogger(__name__)


class ReportError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ReportService:
    def __init__(self, resolver: ClientResolver, settings: Settings):
        self._resolver = resolver
        self._settings = settings
        self._ctx = ReportContext(tz=ZoneInfo(settings.report_timezone))

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def tz(self) -> ZoneInfo:
        return self._ctx.tz

    def export(self, client_id: str, report_key: str, params: dict) -> tuple[SpooledTemporaryFile, int]:
        spec = REPORTS[report_key]

        # Misma respuesta para un id malformado y para uno inexistente: no es un oráculo de clientes.
        if not CLIENT_ID_RE.match(client_id):
            raise ReportError(404, "Cliente no encontrado.")
        try:
            url = self._resolver.resolve(client_id)
        except ClientLookupError as exc:
            logger.error("client_lookup_failed", extra={"client_id": client_id, "error": str(exc)})
            raise ReportError(503, "Servicio temporalmente no disponible: no se pudo acceder a la configuración.") from exc
        if url is None:
            raise ReportError(404, "Cliente no encontrado.")

        engine = ephemeral_engine(url)
        try:
            handle, rows = generate_workbook(engine, spec, params, self._ctx, self._settings)
        except SchemaMismatch as exc:
            logger.error("report_schema_mismatch", extra={"client_id": client_id, "error": str(exc)})
            raise ReportError(422, f"La base de datos del cliente tiene un esquema inesperado: {exc}") from exc
        except ReportTooLarge as exc:
            raise ReportError(413, f"{exc} Acota el filtro e inténtalo de nuevo.") from exc
        except SQLAlchemyError as exc:
            logger.error("report_db_error", exc_info=True, extra={"client_id": client_id})
            raise ReportError(503, "No se pudo generar el reporte: error al conectar con la base de datos del cliente.") from exc
        finally:
            engine.dispose()

        logger.info("report_exported", extra={"client_id": client_id, "report": report_key, "rows": rows, **{
            f"param_{k}": v for k, v in params.items()}})
        return handle, rows
