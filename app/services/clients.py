"""Conexión a la base de datos de cada cliente.

Los reportes son infrecuentes y los clientes muchos: mantener un pool abierto por cliente agotaría
las conexiones de las bases de datos. Se usa un engine **desechable** (``NullPool``) por exportación:
abre una conexión, la usa y la cierra.
"""

import logging
import re
from pathlib import Path
from typing import Protocol

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# client_id llega por la URL y termina en un nombre de archivo y en una cabecera HTTP.
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ClientLookupError(Exception):
    """Fallo de infraestructura al resolver las credenciales (distinto de 'cliente no existe')."""


class ClientResolver(Protocol):
    def resolve(self, client_id: str) -> URL | None:
        """URL de conexión del cliente, o None si no existe / no está activo."""


class SqliteClientResolver:
    def __init__(self, directory: str, clients: list[str]):
        self._dir = Path(directory)
        self._clients = set(clients)

    def resolve(self, client_id: str) -> URL | None:
        path = self._dir / f"{client_id}.db"
        if client_id not in self._clients or not path.is_file():
            return None
        return URL.create("sqlite", database=str(path))


class MasterDbClientResolver:
    """Lee las credenciales desde ``client_connections`` en la BD maestra (pool pequeño y compartido)."""

    _QUERY = text(
        "SELECT db_user, db_password, host, port, db_name "
        "FROM client_connections WHERE client_id = :client_id AND active = 1 LIMIT 1"
    )

    def __init__(self, master_url: str):
        self._engine = create_engine(
            master_url, pool_size=2, max_overflow=3, pool_timeout=10, pool_recycle=1800, pool_pre_ping=True
        )

    def resolve(self, client_id: str) -> URL | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(self._QUERY, {"client_id": client_id}).mappings().first()
        except Exception as exc:
            raise ClientLookupError(str(exc)) from exc
        if not row:
            return None
        return mysql_url(row)


def mysql_url(row) -> URL:
    """``URL.create`` escapa usuario y contraseña (pueden traer '@', ':' o '/'); concatenar
    cadenas produciría una URL inválida o con el host equivocado."""
    return URL.create(
        "mysql+pymysql",
        username=row["db_user"],
        password=row["db_password"],
        host=row["host"],
        port=int(row["port"] or 3306),
        database=row["db_name"],
    )


def ephemeral_engine(url: URL) -> Engine:
    return create_engine(url, poolclass=NullPool)
