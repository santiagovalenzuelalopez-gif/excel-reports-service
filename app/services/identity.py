"""Identidad de quien consulta los reportes. Síncrono: los endpoints corren en el threadpool."""

import hmac
from typing import Protocol


class InvalidIdentity(Exception):
    """Token ausente, con firma inválida o expirado."""


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> dict: ...


class StaticIdentityVerifier:
    """Tokens fijos: demo y tests. No usar en producción."""

    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    def verify(self, token: str) -> dict:
        if any(hmac.compare_digest(token.encode(), valid.encode()) for valid in self._tokens):
            return {"sub": "static-demo"}
        raise InvalidIdentity("token inválido")


class GoogleIdentityVerifier:
    """ID token de Google: firma RS256, emisor, expiración y audiencia propia (configurable)."""

    def __init__(self, audience: str):
        if not audience:
            raise ValueError("GOOGLE_AUDIENCE es obligatorio con IDENTITY_BACKEND=google")
        from google.auth.transport import requests as google_requests

        self._audience = audience
        self._request = google_requests.Request()

    def verify(self, token: str) -> dict:
        from google.oauth2 import id_token

        try:
            return id_token.verify_oauth2_token(token, self._request, self._audience)
        except ValueError as exc:
            raise InvalidIdentity(str(exc)) from exc
