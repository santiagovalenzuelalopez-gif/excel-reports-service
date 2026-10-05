from datetime import datetime

from tests.conftest import AUTH, epoch, make_client_db, read_sheet

URL = "/api/v1/clients/acme/reports/audit"


def audit_rows():
    return [
        {"id": 1, "created_at": epoch(2026, 3, 1, 0, 0, 0), "action": "PRIMER_INSTANTE"},
        {"id": 2, "created_at": epoch(2026, 3, 1, 23, 59, 59), "action": "FIN_DEL_DIA_1"},
        {"id": 3, "created_at": epoch(2026, 3, 2, 0, 0, 0), "action": "FUERA_DE_RANGO"},
        {"id": 4, "created_at": epoch(2026, 2, 28, 23, 59, 59), "action": "ANTES_DEL_RANGO"},
    ]


def test_range_covers_whole_local_days_and_orders_newest_first(client, env):
    make_client_db(env[1] / "acme.db", audit=audit_rows())
    r = client.get(URL, params={"desde": "2026-03-01", "hasta": "2026-03-01"}, headers=AUTH)

    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="auditoria_acme_2026-03-01_a_2026-03-01.xlsx"'
    rows = list(read_sheet(r.content).values)[1:]
    # límites inclusivos en el día LOCAL (Bogotá): 00:00:00 y 23:59:59 entran; el segundo siguiente no
    assert [row[8] for row in rows] == ["FIN_DEL_DIA_1", "PRIMER_INSTANTE"]


def test_dates_are_shown_in_report_timezone_as_native_datetimes(client, env):
    make_client_db(env[1] / "acme.db", audit=[{"id": 1, "created_at": epoch(2026, 3, 1, 15, 30, 0), "action": "X"}])
    sheet = read_sheet(client.get(URL, params={"desde": "2026-03-01", "hasta": "2026-03-01"}, headers=AUTH).content)
    cell = sheet["B2"]
    assert cell.value == datetime(2026, 3, 1, 15, 30, 0)  # hora local, no UTC
    assert "yy" in cell.number_format.lower()  # formato de fecha de Excel, no un texto


def test_invalid_ranges(client, env):
    make_client_db(env[1] / "acme.db", audit=audit_rows())
    assert client.get(URL, params={"desde": "2026-03-05", "hasta": "2026-03-01"}, headers=AUTH).status_code == 422
    too_long = client.get(URL, params={"desde": "2026-01-01", "hasta": "2026-03-01"}, headers=AUTH)  # > 31 días
    assert too_long.status_code == 422 and "31" in too_long.json()["detail"]
    assert client.get(URL, params={"desde": "ayer", "hasta": "hoy"}, headers=AUTH).status_code == 422


def test_report_too_large_is_413_and_does_not_read_the_whole_table(client, env):
    settings, db_dir = env
    make_client_db(db_dir / "acme.db", audit=[{"id": i, "created_at": epoch(2026, 3, 1, 10), "action": "A"} for i in range(1, 1500)])
    r = client.get(URL, params={"desde": "2026-03-01", "hasta": "2026-03-01"}, headers=AUTH)  # max_rows = 1000
    assert r.status_code == 413
    assert "1000" in r.json()["detail"]
