"""Shared helpers. Tests set stats/positions with plain SQL so outcomes are forced, not seed-lucky."""
import pytest

from engine.config import Config
from engine.engine import Engine


def new(seed=42, **cfg):
    """M1 rule tests drive single actions directly: confirmations and encounters are off unless a test turns them on."""
    cfg.setdefault("confirm_irreversible", False)
    cfg.setdefault("encounters", False)
    return Engine.create(seed=seed, config=Config(**cfg))


@pytest.fixture
def eng():
    return new()


def rows(eng, sql, *args):
    return [tuple(r) for r in eng.conn.execute(sql, args)]


def val(eng, sql, *args):
    return eng.conn.execute(sql, args).fetchone()[0]


def setstat(eng, who, **stats):
    for k, v in stats.items():
        eng.conn.execute("UPDATE characters SET stats = json_set(stats, ?, ?) WHERE id=?", (f"$.{k}", v, who))


def setskill(eng, who, **skills):
    for k, v in skills.items():
        eng.conn.execute("UPDATE characters SET skills = json_set(skills, ?, ?) WHERE id=?", (f"$.{k}", v, who))


def setchar(eng, who, **cols):
    for k, v in cols.items():
        eng.conn.execute(f"UPDATE characters SET {k}=? WHERE id=?", (v, who))


def place(eng, who, where):
    setchar(eng, who, location_id=where)


def holder(eng, item):
    return eng.conn.execute("SELECT holder_id, location_id FROM items WHERE id=?", (item,)).fetchone()[:]


def counts(eng):
    """Fingerprint of everything an action could write."""
    return {t: val(eng, f"SELECT COUNT(*) FROM {t}") for t in
            ("events", "perceptions", "knowledge", "traces", "provenance", "dice_log", "inputs", "trades")} | {
        "clock": val(eng, "SELECT value FROM meta WHERE key='clock'"),
        "rolls": val(eng, "SELECT value FROM meta WHERE key='roll_counter'"),
        "items": rows(eng, "SELECT * FROM items ORDER BY id"),
        "chars": rows(eng, "SELECT * FROM characters ORDER BY id"),
        "doors": rows(eng, "SELECT * FROM doors ORDER BY id")}


def one(eng, actor, text):
    """Submit a single-action command and return its Result."""
    results = eng.submit(actor, text)
    assert len(results) == 1, results
    return results[0]
