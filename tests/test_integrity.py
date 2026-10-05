"""DB-level guarantees: each forbidden operation raises, whoever attempts it."""
import pathlib
import re
import sqlite3

import pytest

from conftest import counts, new, one, val
from engine import world


@pytest.fixture
def played():
    eng = new()
    eng.submit("player", "take knife and attack bob")  # fills events, perceptions, knowledge, dice_log, provenance
    eng.submit("player", "drop knife")  # traces
    return eng


@pytest.mark.parametrize("table", ["items", "characters", "locations"])
def test_nothing_vanishes(played, table):
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        played.conn.execute(f"DELETE FROM {table}")


@pytest.mark.parametrize("table", ["events", "provenance", "perceptions", "traces", "knowledge", "dice_log"])
def test_history_is_append_only(played, table):
    assert val(played, f"SELECT COUNT(*) FROM {table}") > 0
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        played.conn.execute(f"UPDATE {table} SET rowid = rowid")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        played.conn.execute(f"DELETE FROM {table}")


def test_item_must_be_in_exactly_one_place(eng):
    with pytest.raises(sqlite3.IntegrityError):
        eng.conn.execute("UPDATE items SET holder_id='player' WHERE id='knife'")  # held AND on the table
    with pytest.raises(sqlite3.IntegrityError):
        eng.conn.execute("UPDATE items SET location_id=NULL WHERE id='knife'")  # nowhere
    with pytest.raises(sqlite3.IntegrityError):
        eng.conn.execute("INSERT INTO items (id, type, name) VALUES ('ghost', 'thing', 'ghost')")


def test_coins_never_negative(eng):
    with pytest.raises(sqlite3.IntegrityError):
        eng.conn.execute("UPDATE characters SET coins = -1 WHERE id='bob'")


def test_face_shape_immutable(eng):
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        eng.conn.execute("UPDATE characters SET face_shape='round' WHERE id='player'")
    eng.conn.execute("UPDATE characters SET appearance='{\"clothes\": \"a red cloak\"}' WHERE id='player'")  # disguise ok


def test_every_item_move_writes_provenance(played):
    kinds = [r[0] for r in played.conn.execute("SELECT kind FROM provenance WHERE item_id='knife' ORDER BY id")]
    assert kinds == ["created", "taken", "dropped"]
    assert val(played, "SELECT COUNT(*) FROM provenance WHERE kind='created'") == val(played, "SELECT COUNT(*) FROM items")


def test_only_world_py_writes():
    for path in pathlib.Path(world.__file__).parent.glob("*.py"):
        if path.name != "world.py":
            src = path.read_text()
            assert not re.search(r"INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM", src, re.I), path.name


def test_exception_mid_action_rolls_back_everything(eng, monkeypatch):
    before = counts(eng)

    def boom(*a, **k):
        raise RuntimeError("crash after the roll and the item move")

    monkeypatch.setattr(world, "add_event", boom)  # steal has already rolled and moved coins by then
    with pytest.raises(RuntimeError):
        eng.submit("player", "steal from bob")
    with pytest.raises(RuntimeError):
        eng.submit("player", "take knife and attack bob")
    assert counts(eng) == before  # incl. dice counter, dice_log, inputs, clock
    monkeypatch.undo()
    r = one(eng, "player", "look")
    assert r.rolls[0].id == 1  # the counter really did not move


def test_impossible_action_writes_nothing_but_the_input(eng):
    before = counts(eng)
    r = one(eng, "player", "go to tom's house")
    assert r.outcome == "impossible"
    after = counts(eng)
    assert after.pop("inputs") == before.pop("inputs") + 1
    assert after == before
