import json, sqlite3
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY, run_id TEXT, t TEXT, at TEXT, data TEXT,
            receipt TEXT UNIQUE)""")
        with c:
            yield c
    finally:
        c.close()


def add_event(run_id, t, at, data):
    """Raises sqlite3.IntegrityError if a fuel receipt number repeats."""
    receipt = (data or {}).get("receipt_no") if t == "fuel" else None
    with conn() as c:
        c.execute("INSERT INTO events(run_id,t,at,data,receipt) VALUES(?,?,?,?,?)",
                  (str(run_id), t, at, json.dumps(data), receipt))


def all_events():
    with conn() as c:
        rows = c.execute("SELECT run_id,t,at,data FROM events ORDER BY id").fetchall()
    return [{"run": r[0], "t": r[1], "at": r[2], "d": json.loads(r[3])} for r in rows]


def admin_events():
    with conn() as c:
        rows = c.execute("SELECT id,run_id,t,at,data FROM events ORDER BY id DESC").fetchall()
    return [{"id": r[0], "run": r[1], "t": r[2], "at": r[3], "d": json.loads(r[4])} for r in rows]


def delete_event(event_id):
    with conn() as c:
        cursor = c.execute("DELETE FROM events WHERE id = ?", (event_id,))
        return cursor.rowcount > 0
