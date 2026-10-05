from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Observabilidad
    service_name: str = "excel-reports-service"
    service_version: str = "1.0.0"
    environment: str = "dev"
    log_level: str = "INFO"

    # Identidad de quien consulta. static: tokens de demo. google: ID token de Google.
    identity_backend: Literal["static", "google"] = "static"
    static_tokens: str = "demo-token"
    google_audience: str = ""

    # Dónde viven las credenciales de cada cliente.
    # sqlite: un archivo por cliente (demo/tests). master: tabla en una BD maestra (MySQL).
    client_db_backend: Literal["sqlite", "master"] = "sqlite"
    sqlite_dir: str = "data/db"
    demo_clients: str = "demo"
    master_db_url: str = ""

    # Zona horaria en la que se muestran las fechas del reporte de auditoría.
    report_timezone: str = "UTC"

    # Protección del servicio. Excel admite 1.048.576 filas por hoja (1 es el encabezado).
    max_rows: int = Field(default=500_000, ge=1, le=1_048_575)
    max_range_days: int = 366
    fetch_chunk_size: int = 5_000
    # Por encima de este tamaño el .xlsx en construcción se vuelca a disco en vez de RAM.
    spool_max_bytes: int = 16 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
