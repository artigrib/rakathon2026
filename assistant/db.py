"""SQLite store: assistants, their calls and what they did. One connection per operation."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS assistants(
  id TEXT PRIMARY KEY, tool_token TEXT NOT NULL, owner_name TEXT NOT NULL, owner_phone TEXT NOT NULL,
  name TEXT NOT NULL, greeting TEXT NOT NULL, instructions TEXT NOT NULL, language TEXT NOT NULL,
  notify_email TEXT NOT NULL DEFAULT '', number TEXT NOT NULL, agent_id TEXT NOT NULL DEFAULT '',
  perms TEXT NOT NULL DEFAULT '{}', google_token TEXT NOT NULL DEFAULT '', google_email TEXT NOT NULL DEFAULT '',
  google_scopes TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS assistants_number ON assistants(number, created_at);
CREATE TABLE IF NOT EXISTS calls(
  sid TEXT PRIMARY KEY, assistant_id TEXT, to_number TEXT NOT NULL, from_number TEXT NOT NULL DEFAULT '',
  forwarded_from TEXT NOT NULL DEFAULT '', called_via TEXT NOT NULL DEFAULT '', route TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'in-progress', duration INTEGER, conversation_id TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '{}', transcript TEXT NOT NULL DEFAULT '[]',
  fetched INTEGER NOT NULL DEFAULT 0, notified INTEGER NOT NULL DEFAULT 0, started_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS calls_assistant ON calls(assistant_id, started_at);
CREATE INDEX IF NOT EXISTS calls_number ON calls(to_number, started_at);
CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, assistant_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS actions_assistant ON actions(assistant_id, at);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
CALL_COLUMNS = {"direction": "TEXT NOT NULL DEFAULT 'inbound'", "task": "TEXT NOT NULL DEFAULT ''", "agent_id": "TEXT NOT NULL DEFAULT ''",
                "notes": "TEXT NOT NULL DEFAULT ''", "report_id": "TEXT NOT NULL DEFAULT ''", "call_ref": "TEXT NOT NULL DEFAULT ''",
                "tools": "TEXT NOT NULL DEFAULT '[]'", "live_at": "REAL NOT NULL DEFAULT 0",
                "mode": "TEXT NOT NULL DEFAULT 'errand'", "owner": "TEXT NOT NULL DEFAULT ''", "batch_id": "TEXT NOT NULL DEFAULT ''",
                "label": "TEXT NOT NULL DEFAULT ''", "report_lang": "TEXT NOT NULL DEFAULT 'cs'"}


def _path() -> str:
    return os.getenv("ASSISTANT_DB", "/data/assistant.db")


@contextmanager
def conn():
    c = sqlite3.connect(_path(), timeout=10)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init():
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        have = {r[1] for r in c.execute("PRAGMA table_info(calls)")}
        for col, decl in CALL_COLUMNS.items():   # added after the first deploy
            if col not in have:
                c.execute(f"ALTER TABLE calls ADD COLUMN {col} {decl}")
        if "call_sid" not in {r[1] for r in c.execute("PRAGMA table_info(actions)")}:
            c.execute("ALTER TABLE actions ADD COLUMN call_sid TEXT NOT NULL DEFAULT ''")


class _KV:
    def get(self, key: str) -> str:
        with conn() as c:
            r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return r[0] if r else ""

    def set(self, key: str, value: str):
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, value))


kv = _KV()


def _assistant(row):
    if not row:
        return None
    a = dict(row)
    a["perms"] = json.loads(a["perms"] or "{}")
    return a


def add_assistant(**f):
    f.setdefault("created_at", time.time())
    f["perms"] = json.dumps(f.get("perms") or {})
    cols = ",".join(f)
    with conn() as c:
        c.execute(f"INSERT INTO assistants({cols}) VALUES({','.join('?' * len(f))})", tuple(f.values()))


def get_assistant(aid: str):
    with conn() as c:
        return _assistant(c.execute("SELECT * FROM assistants WHERE id=?", (aid,)).fetchone())


UPDATABLE = {"owner_name", "name", "greeting", "instructions", "language", "notify_email", "agent_id", "perms",
             "google_token", "google_email", "google_scopes"}


def update_assistant(aid: str, **f):
    if not f:
        return
    assert set(f) <= UPDATABLE, set(f) - UPDATABLE  # column names are interpolated, keep them fixed
    if "perms" in f:
        f["perms"] = json.dumps(f["perms"])
    with conn() as c:
        c.execute(f"UPDATE assistants SET {','.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), aid))


def delete_assistant(aid: str):
    with conn() as c:
        c.execute("DELETE FROM actions WHERE assistant_id=?", (aid,))
        c.execute("DELETE FROM calls WHERE assistant_id=?", (aid,))
        c.execute("DELETE FROM assistants WHERE id=?", (aid,))


def count_assistants() -> int:
    with conn() as c:
        return c.execute("SELECT count(*) FROM assistants").fetchone()[0]


def assistants_on(number: str) -> list:
    """Newest first."""
    with conn() as c:
        return [_assistant(r) for r in c.execute("SELECT * FROM assistants WHERE number=? ORDER BY created_at DESC, rowid DESC", (number,))]


def load_by_number() -> dict:
    with conn() as c:
        return {r["number"]: r["n"] for r in c.execute("SELECT number, count(*) n FROM assistants GROUP BY number")}


def add_call(sid: str, assistant_id, to_number: str, from_number: str, forwarded_from: str, called_via: str, route: str):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO calls(sid,assistant_id,to_number,from_number,forwarded_from,called_via,route,started_at) "
                  "VALUES(?,?,?,?,?,?,?,?)", (sid, assistant_id, to_number, from_number, forwarded_from, called_via, route, time.time()))


def add_outbound(sid: str, assistant_id: str, to_number: str, from_number: str, task: str, agent_id: str,
                 notes: str = "", report_id: str = "", call_ref: str = "", mode: str = "errand", owner: str = "", batch_id: str = "",
                 label: str = "", report_lang: str = "cs"):
    """Stored before Twilio is asked to call (sid = 'pending-…'), so the call webhook always finds it."""
    with conn() as c:
        c.execute("INSERT INTO calls(sid,assistant_id,to_number,from_number,route,direction,task,agent_id,notes,report_id,call_ref,status,"
                  "mode,owner,batch_id,label,report_lang,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sid, assistant_id, to_number, from_number, "outbound", "outbound", task, agent_id, notes, report_id, call_ref, "queued",
                   mode, owner, batch_id, label, report_lang, time.time()))


def batch(batch_id: str) -> list:
    if not batch_id:
        return []
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM calls WHERE batch_id=? ORDER BY rowid", (batch_id,))]


def rename_call(old: str, new: str):
    with conn() as c:
        c.execute("UPDATE calls SET sid=? WHERE sid=?", (new, old))
        c.execute("UPDATE actions SET call_sid=? WHERE call_sid=?", (new, old))


def call_by(column: str, value: str):
    assert column in ("report_id", "call_ref", "sid")
    if not value:
        return None
    with conn() as c:
        r = c.execute(f"SELECT * FROM calls WHERE {column}=?", (value,)).fetchone()
        return dict(r) if r else None


def outbound_since(aid: str, since: float) -> int:
    with conn() as c:
        return c.execute("SELECT count(*) FROM calls WHERE assistant_id=? AND direction='outbound' AND started_at>=?", (aid, since)).fetchone()[0]


def get_call(sid: str):
    with conn() as c:
        r = c.execute("SELECT * FROM calls WHERE sid=?", (sid,)).fetchone()
        return dict(r) if r else None


def update_call(sid: str, **f):
    if f:
        with conn() as c:
            c.execute(f"UPDATE calls SET {','.join(k + '=?' for k in f)} WHERE sid=?", (*f.values(), sid))


def claim_notification(sid: str) -> bool:
    """True exactly once per call: the summary e-mail must not go out twice."""
    with conn() as c:
        return c.execute("UPDATE calls SET notified=1 WHERE sid=? AND notified=0", (sid,)).rowcount == 1


def calls_of(aid: str, limit: int = 30) -> list:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM calls WHERE assistant_id=? ORDER BY started_at DESC LIMIT ?", (aid, limit))]


def calls_since(number: str, since: float) -> int:
    with conn() as c:
        return c.execute("SELECT count(*) FROM calls WHERE to_number=? AND started_at>=?", (number, since)).fetchone()[0]


def add_action(aid: str, kind: str, detail: str, call_sid: str = ""):
    with conn() as c:
        c.execute("INSERT INTO actions(assistant_id,kind,detail,at,call_sid) VALUES(?,?,?,?,?)", (aid, kind, detail, time.time(), call_sid))


def actions_of_call(sid: str) -> list:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM actions WHERE call_sid=? ORDER BY at, id", (sid,))]


def actions_of(aid: str, limit: int = 30) -> list:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM actions WHERE assistant_id=? ORDER BY at DESC, id DESC LIMIT ?", (aid, limit))]


def actions_since(aid: str, kind: str, since: float) -> int:
    with conn() as c:
        return c.execute("SELECT count(*) FROM actions WHERE assistant_id=? AND kind=? AND at>=?", (aid, kind, since)).fetchone()[0]


def purge(days: int):
    cut = time.time() - days * 86400
    with conn() as c:
        c.execute("DELETE FROM calls WHERE started_at<?", (cut,))
        c.execute("DELETE FROM actions WHERE at<?", (cut,))
