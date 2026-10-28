import json, sqlite3
from config import DB_PATH


def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY, run_id TEXT, t TEXT, at TEXT, data TEXT,
        receipt TEXT UNIQUE)""")
    return c


def add_event(run_id, t, at, data):
    """Raises sqlite3.IntegrityError if a fuel receipt number repeats."""
    receipt = (data or {}).get("receipt_no") if t == "fuel" else None
    with conn() as c:
        c.execute("INSERT INTO events(run_id,t,at,data,receipt) VALUES(?,?,?,?,?)",
                  (str(run_id), t, at, json.dumps(data), receipt))


def all_events():
    rows = conn().execute("SELECT run_id,t,at,data FROM events ORDER BY id").fetchall()
    return [{"run": r[0], "t": r[1], "at": r[2], "d": json.loads(r[3])} for r in rows]
