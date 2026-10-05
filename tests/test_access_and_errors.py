import sqlite3

import pytest

from tests.conftest import AUTH, make_client_db

USERS = "/api/v1/clients/{}/reports/users"


def test_authentication_is_required(client, env):
    make_client_db(env[1] / "acme.db")
    url = USERS.format("acme")
    assert client.get(url, params={"letra": "Todos"}).status_code == 401
    assert client.get(url, params={"letra": "Todos"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get(url, params={"letra": "Todos"}, headers={"Authorization": "Basic abc"}).status_code == 401
    # el token en el query string NO es un mecanismo válido
    assert client.get(url, params={"letra": "Todos", "token": "test-token"}).status_code == 401


def test_unknown_and_malformed_clients_look_the_same(client, env):
    make_client_db(env[1] / "acme.db")
    unknown = client.get(USERS.format("fantasma"), params={"letra": "Todos"}, headers=AUTH)
    malformed = client.get(USERS.format("a%0d%0aX-Evil:1"), params={"letra": "Todos"}, headers=AUTH)
    assert unknown.status_code == malformed.status_code == 404
    assert unknown.json() == malformed.json()
    assert "x-evil" not in malformed.headers  # sin inyección de cabeceras


def test_registered_client_without_database_file_is_404(client):
    assert client.get(USERS.format("beta"), params={"letra": "Todos"}, headers=AUTH).status_code == 404


@pytest.mark.parametrize("missing", ["table", "column"])
def test_unexpected_schema_is_422_with_detail(client, env, missing):
    path = env[1] / "acme.db"
    make_client_db(path)
    with sqlite3.connect(path) as conn:
        if missing == "table":
            conn.execute("DROP TABLE users")
        else:
            conn.execute("ALTER TABLE users DROP COLUMN phone")
    r = client.get(USERS.format("acme"), params={"letra": "Todos"}, headers=AUTH)
    assert r.status_code == 422
    assert "esquema inesperado" in r.json()["detail"]
    assert ("users" in r.json()["detail"]) and (missing == "table" or "phone" in r.json()["detail"])


def test_database_failure_is_503_without_leaking_details(client, env):
    path = env[1] / "acme.db"
    path.write_bytes(b"esto no es una base de datos sqlite")
    r = client.get(USERS.format("acme"), params={"letra": "Todos"}, headers=AUTH)
    assert r.status_code == 503
    assert "sqlite" not in r.text.lower()


def test_health_and_version_are_public(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "version" in client.get("/version").json()
