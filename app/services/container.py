"""Composición de dependencias (única parte que conoce las implementaciones concretas)."""

from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from app.core.config import get_settings
from app.services.clients import MasterDbClientResolver, SqliteClientResolver
from app.services.identity import (
    GoogleIdentityVerifier,
    IdentityVerifier,
    InvalidIdentity,
    StaticIdentityVerifier,
)
from app.services.service import ReportService


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_service() -> ReportService:
    settings = get_settings()
    if settings.client_db_backend == "master":
        resolver = MasterDbClientResolver(settings.master_db_url)
    else:
        resolver = SqliteClientResolver(settings.sqlite_dir, _split(settings.demo_clients))
    return ReportService(resolver, settings)


@lru_cache
def get_verifier() -> IdentityVerifier:
    settings = get_settings()
    if settings.identity_backend == "google":
        return GoogleIdentityVerifier(settings.google_audience)
    return StaticIdentityVerifier(_split(settings.static_tokens))


def require_identity(
    authorization: str | None = Header(default=None),
    verifier: IdentityVerifier = Depends(get_verifier),
) -> dict:
    """``Authorization: Bearer <token>``. El token va en la cabecera, no en el query string: las URL
    terminan en logs de proxies, balanceadores e historiales de navegador."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Falta el token de autorización.")
    try:
        return verifier.verify(token)
    except InvalidIdentity:
        raise HTTPException(status_code=401, detail="Token de autorización inválido o expirado.") from None
