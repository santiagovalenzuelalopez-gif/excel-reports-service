"""Crea la base de demo ``data/db/demo.db`` con usuarios y registros de auditoría sintéticos.

    python scripts/seed_demo.py
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

DDL = [
    """CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, login TEXT, doc_type TEXT,
       doc_number TEXT, email TEXT, address TEXT, phone TEXT, country TEXT, department TEXT, city TEXT,
       kind TEXT, status TEXT)""",
    """CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, created_at INTEGER, ip TEXT, user_id INTEGER,
       login TEXT, entity TEXT, entity_2 TEXT, entity_id INTEGER, action TEXT, detail TEXT)""",
]
NAMES = ["Ana", "Luis", "María", "Carlos", "Beatriz", "Andrés", "Camila", "Diego", "Elena", "Felipe"]
SURNAMES = ["Pérez", "Gómez", "Rojas", "Ruiz", "Torres", "Díaz", "Vargas", "Mora", "Castro", "Silva"]
ACTIONS = ["LOGIN", "LOGOUT", "CREATE", "UPDATE", "DELETE", "EXPORT"]
ENTITIES = ["users", "orders", "documents", "settings"]


def main(directory: str = "data/db", users: int = 2_000, events: int = 5_000) -> None:
    random.seed(7)  # datos reproducibles
    path = Path(directory) / "demo.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    engine = create_engine(f"sqlite:///{path}")
    now = datetime.now(ZoneInfo("America/Bogota"))
    with engine.begin() as conn:
        for statement in DDL:
            conn.execute(text(statement))
        people = []
        for i in range(1, users + 1):
            first, last = random.choice(NAMES), random.choice(SURNAMES)
            people.append(
                {
                    "id": i, "name": f"{first} {last}", "login": f"{first.lower()}.{last.lower()}{i}",
                    "doc_type": "CC", "doc_number": str(10_000_000 + i), "email": f"user{i}@example.com",
                    "address": f"Calle {random.randint(1, 120)} # {random.randint(1, 99)}-{random.randint(1, 99)}",
                    "phone": f"+5730{random.randint(10_000_000, 99_999_999)}", "country": "Colombia",
                    "department": "Antioquia", "city": "Medellín", "kind": "Persona natural",
                    "status": random.choice(["activo", "activo", "inactivo"]),
                }
            )
        conn.execute(text("INSERT INTO users VALUES (:id,:name,:login,:doc_type,:doc_number,:email,:address,"
                          ":phone,:country,:department,:city,:kind,:status)"), people)
        log = []
        for i in range(1, events + 1):
            person = random.choice(people)
            when = now - timedelta(seconds=random.randint(0, 30 * 24 * 3600))
            log.append(
                {"id": i, "created_at": int(when.timestamp()), "ip": f"10.0.{random.randint(0, 9)}.{random.randint(1, 250)}",
                 "user_id": person["id"], "login": person["login"], "entity": random.choice(ENTITIES),
                 "entity_2": None, "entity_id": random.randint(1, 500), "action": random.choice(ACTIONS), "detail": ""}
            )
        conn.execute(text("INSERT INTO audit_log VALUES (:id,:created_at,:ip,:user_id,:login,:entity,:entity_2,"
                          ":entity_id,:action,:detail)"), log)
    print(f"Base de demo creada en {path} ({users} usuarios, {events} eventos)")


if __name__ == "__main__":
    main(*sys.argv[1:2])
