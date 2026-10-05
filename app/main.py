from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import CorrelationMiddleware
from app.routers import health, reports
from app.services.service import ReportError

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="Excel Reports Service",
    description="Exporta reportes a Excel desde la base de datos de cada cliente, en streaming y con memoria acotada.",
    version=settings.service_version,
)

app.add_middleware(CorrelationMiddleware)


@app.exception_handler(ReportError)
async def report_error_handler(_: Request, exc: ReportError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health.router)
app.include_router(reports.router)
