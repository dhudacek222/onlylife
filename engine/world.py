"""The ONLY module that writes to the database. Read queries + the consequence whitelist.
Callers own the transaction; nothing here commits."""
import json

from engine import dice
from engine.actions import Roll

JSON_COLS = {"tags", "stats", "skills", "appearance", "aliases", "properties", "flags", "data", "detail",
             "raw", "give_items", "want_items", "appearance_seen"}


def _d(row):
    if row is None:
        return None
    return {k: json.loads(row[k]) if k in JSON_COLS and row[k] is not None else row[k] for k in row.keys()}


def q1(conn, sql, *args):
    return _d(conn.execute(sql, args).fetchone())


def q(conn, sql, *args):
    return [_d(r) for r in conn.execute(sql, args)]


def _w(conn, sql, *args):
    return conn.execute(sql, [json.dumps(a) if isinstance(a, (dict, list)) else a for a in args])


# ---------------------------------------------------------------- reads

def meta(conn, key):
    return conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0]


def now(conn):
    return int(meta(conn, "clock"))


def char(conn, cid):
    return q1(conn, "SELECT * FROM characters WHERE id=?", cid)


def chars_at(conn, loc):
    return q(conn, "SELECT * FROM characters WHERE location_id=? ORDER BY id", loc)


def present(conn, loc, exclude=None):
    """Characters who can perceive things here (awake and alive)."""
    return [c for c in chars_at(conn, loc) if c["status"] in ("online", "afk") and c["id"] != exclude]


def location(conn, lid):
    return q1(conn, "SELECT * FROM locations WHERE id=?", lid)


def door(conn, did):
    return q1(conn, "SELECT * FROM doors WHERE id=?", did)


def item(conn, iid):
    return q1(conn, "SELECT * FROM items WHERE id=?", iid)


def items_at(conn, loc):
    return q(conn, "SELECT * FROM items WHERE location_id=? ORDER BY id", loc)


def items_held(conn, cid):
    return q(conn, "SELECT * FROM items WHERE holder_id=? ORDER BY id", cid)


def exits(conn, loc):
    return q(conn, "SELECT l.*, c.door_id FROM connections c JOIN locations l ON l.id = c.to_id "
                   "WHERE c.from_id=? ORDER BY l.id", loc)


def door_sides(conn, did):
    return [r[0] for r in conn.execute("SELECT from_id FROM connections WHERE door_id=? ORDER BY from_id", (did,))]


def knows(conn, observer_id, subject_id, fact, since=None):
    return conn.execute(
        "SELECT 1 FROM knowledge WHERE observer_id=? AND subject_id=? AND fact=? AND (? IS NULL OR time>=?) LIMIT 1",
        (observer_id, subject_id, fact, since, since)).fetchone() is not None


def can_see(conn, observer_id, subject):
    """The visibility rule: subject not hidden, or observer became aware of them since they hid."""
    if observer_id == subject["id"] or not subject["hidden"]:
        return True
    return knows(conn, observer_id, subject["id"], "aware_of", since=subject["hidden_since"])


def attempts(conn, actor_id, verb, target_id, since):
    return conn.execute("SELECT COUNT(*) FROM events WHERE actor_id=? AND verb=? AND target_id IS ? AND time>?",
                        (actor_id, verb, target_id, since)).fetchone()[0]


def broke_in(conn, actor_id, door_id):
    """Did the actor pick or force this door since their last move (i.e. on this visit)?"""
    last_move = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events WHERE actor_id=? AND verb IN ('move','flee') "
                             "AND outcome='success'", (actor_id,)).fetchone()[0]
    return conn.execute("SELECT 1 FROM events WHERE actor_id=? AND target_id=? AND outcome='success' AND id>? "
                        "AND json_extract(data, '$.method') IN ('lockpick','force')",
                        (actor_id, door_id, last_move)).fetchone() is not None


def trade(conn, tid):
    return q1(conn, "SELECT * FROM trades WHERE id=?", tid)


def latest_trade(conn, to_id, from_id=None):
    return q1(conn, "SELECT * FROM trades WHERE to_id=? AND status='pending' AND (? IS NULL OR from_id=?) "
                    "ORDER BY id DESC LIMIT 1", to_id, from_id, from_id)


def next_event_id(conn):
    """Single writer + BEGIN IMMEDIATE makes this safe; rolls are logged against it before the event row exists."""
    return conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM events").fetchone()[0]


def event(conn, eid):
    return q1(conn, "SELECT * FROM events WHERE id=?", eid)


def detectors(conn, eid):
    return [r[0] for r in conn.execute(
        "SELECT observer_id FROM perceptions WHERE event_id=? AND detected=1 ORDER BY observer_id", (eid,))]


def encounter_of(conn, cid):
    """The active encounter this character is a member of (and hasn't left), or None."""
    return q1(conn, "SELECT e.* FROM encounters e JOIN encounter_members m ON m.encounter_id = e.id "
                    "WHERE m.character_id=? AND m.left_round IS NULL AND e.ended IS NULL ORDER BY e.id LIMIT 1", cid)


def encounter(conn, eid):
    return q1(conn, "SELECT * FROM encounters WHERE id=?", eid)


def members(conn, eid):
    """Active members in turn order: earlier joiners first, then initiative (high first), then id."""
    return q(conn, "SELECT * FROM encounter_members WHERE encounter_id=? AND left_round IS NULL "
                   "ORDER BY joined_round, initiative DESC, character_id", eid)


def active_encounters(conn):
    return q(conn, "SELECT * FROM encounters WHERE ended IS NULL ORDER BY id")


# ---------------------------------------------------------------- whitelist (the only writes in the engine)

def _insert(conn, table, row):
    _w(conn, f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", *row.values())


def load_fixture(conn, fx, seed):
    clock = fx.get("clock", 0)
    for k, v in (("world_seed", seed), ("roll_counter", 0), ("clock", clock)):
        _w(conn, "INSERT INTO meta VALUES (?, ?)", k, str(v))
    for table in ("housing_tiers", "locations", "doors"):
        for row in fx.get(table, []):
            _insert(conn, table, row)
    for a, b, door_id in fx.get("connections", []):
        _insert(conn, "connections", dict(from_id=a, to_id=b, door_id=door_id))
        _insert(conn, "connections", dict(from_id=b, to_id=a, door_id=door_id))
    for table in ("buildings", "characters"):
        for row in fx.get(table, []):
            _insert(conn, table, row)
    for it in fx.get("items", []):
        _insert(conn, "items", it)
        where = it.get("location_id") or char(conn, it["holder_id"])["location_id"]
        _w(conn, "INSERT INTO provenance (item_id, kind, to_id, location_id, time) VALUES (?, 'created', ?, ?, ?)",
           it["id"], it.get("holder_id"), where, clock)
    for observer, subject, fact in fx.get("knowledge", []):
        add_knowledge(conn, observer, subject, fact, None, clock, None)


def log_input(conn, kind, actor_id, payload):
    _w(conn, "INSERT INTO inputs (kind, actor_id, payload) VALUES (?, ?, ?)", kind, actor_id, payload)


def log_model_call(conn, actor_id, purpose, usage, verbs):
    _w(conn, "INSERT INTO model_calls (time, actor_id, purpose, model, input_tokens, output_tokens, "
             "cache_read_input_tokens, latency_ms, verbs) VALUES (?,?,?,?,?,?,?,?,?)",
       now(conn), actor_id, purpose, usage.get("model", "?"), usage.get("input_tokens"), usage.get("output_tokens"),
       usage.get("cache_read_input_tokens"), usage.get("latency_ms"), verbs)


def advance_clock(conn, ticks):
    _w(conn, "UPDATE meta SET value = CAST(value AS INT) + ? WHERE key='clock'", ticks)


def roll(conn, actor_id, purpose, modifier=0, dc=None, mode="normal", sides=20, event_id=None, time=None):
    """Roll n = counter+1, persist the counter and log it. Rolled back with the action's transaction."""
    n = int(meta(conn, "roll_counter")) + 1
    raw = dice.raw_roll(meta(conn, "world_seed"), n, sides, mode)
    total = dice.kept(raw, mode) + modifier
    success = None if dc is None else total >= dc
    _w(conn, "UPDATE meta SET value=? WHERE key='roll_counter'", str(n))
    _w(conn, "INSERT INTO dice_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", n, time, event_id, actor_id, purpose, sides,
       raw, mode, modifier, total, dc, None if success is None else int(success))
    return Roll(n, purpose, sides, raw, mode, modifier, total, dc, success)


def move_item(conn, item_id, kind, *, holder_id=None, location_id=None, event_id=None):
    """Every item move goes through here: exactly one new place + a provenance row, same transaction."""
    old = item(conn, item_id)
    where = location_id or char(conn, holder_id)["location_id"]
    _w(conn, "UPDATE items SET holder_id=?, location_id=? WHERE id=?", holder_id, location_id, item_id)
    _w(conn, "INSERT INTO provenance (item_id, kind, from_id, to_id, location_id, time, event_id) "
             "VALUES (?,?,?,?,?,?,?)", item_id, kind, old["holder_id"], holder_id, where, now(conn), event_id)


def transform_item(conn, item_id, becomes, event_id):
    """Items change, never vanish: same id, new type/name/properties, provenance 'transformed'."""
    old = item(conn, item_id)
    _w(conn, "UPDATE items SET type=?, name=?, aliases=?, properties=?, price=NULL WHERE id=?",
       becomes.get("type", old["type"]), becomes.get("name", old["name"]), becomes.get("aliases", []),
       becomes.get("properties", {}), item_id)
    where = old["location_id"] or char(conn, old["holder_id"])["location_id"]
    _w(conn, "INSERT INTO provenance (item_id, kind, from_id, to_id, location_id, time, event_id) "
             "VALUES (?, 'transformed', ?, ?, ?, ?, ?)", item_id, old["holder_id"], old["holder_id"], where,
       now(conn), event_id)


def flag_item(conn, item_id, flag):
    flags = item(conn, item_id)["flags"]
    if flag not in flags:
        _w(conn, "UPDATE items SET flags=? WHERE id=?", flags + [flag], item_id)


def move_char(conn, cid, loc):
    _w(conn, "UPDATE characters SET location_id=? WHERE id=?", loc, cid)


def set_hidden(conn, cid, hidden, since=None, total=None):
    _w(conn, "UPDATE characters SET hidden=?, hidden_since=?, stealth_total=? WHERE id=?",
       int(hidden), since if hidden else None, total if hidden else None, cid)


def set_hp(conn, cid, hp):
    _w(conn, "UPDATE characters SET hp=? WHERE id=?", hp, cid)


def set_status(conn, cid, status):
    _w(conn, "UPDATE characters SET status=? WHERE id=?", status, cid)


def add_coins(conn, cid, delta):
    _w(conn, "UPDATE characters SET coins = coins + ? WHERE id=?", delta, cid)  # CHECK (coins >= 0) guards


def add_wanted(conn, cid, n):
    _w(conn, "UPDATE characters SET wanted_level = wanted_level + ? WHERE id=?", n, cid)


def set_door(conn, did, *, locked=None, is_open=None):
    d = door(conn, did)
    _w(conn, "UPDATE doors SET locked=?, is_open=? WHERE id=?",
       d["locked"] if locked is None else int(locked), d["is_open"] if is_open is None else int(is_open), did)


def add_event(conn, eid, time, actor_id, verb, target_id, item_id, location_id, outcome, crime, data):
    _w(conn, "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)",
       eid, time, actor_id, verb, target_id, item_id, location_id, outcome, crime, data)


def add_perception(conn, eid, observer_id, detected, recognized, appearance_seen, roll_id):
    _w(conn, "INSERT INTO perceptions VALUES (?,?,?,?,?,?)",
       eid, observer_id, int(detected), int(recognized), appearance_seen, roll_id)


def add_trace(conn, eid, kind, item_id, location_id, detail):
    _w(conn, "INSERT INTO traces (event_id, kind, item_id, location_id, detail) VALUES (?,?,?,?,?)",
       eid, kind, item_id, location_id, detail)


def add_knowledge(conn, observer_id, subject_id, fact, location_id, time, eid):
    _w(conn, "INSERT INTO knowledge (observer_id, subject_id, fact, location_id, time, event_id) "
             "VALUES (?,?,?,?,?,?)", observer_id, subject_id, fact, location_id, time, eid)


def add_encounter(conn, location_id, time):
    return _w(conn, "INSERT INTO encounters (location_id, started) VALUES (?, ?)", location_id, time).lastrowid


def add_member(conn, eid, cid, initiative, roll_id, joined_round):
    _w(conn, "INSERT OR REPLACE INTO encounter_members (encounter_id, character_id, initiative, roll_id, joined_round) "
             "VALUES (?,?,?,?,?)", eid, cid, initiative, roll_id, joined_round)


def leave_encounter(conn, eid, cid, round_):
    _w(conn, "UPDATE encounter_members SET left_round=? WHERE encounter_id=? AND character_id=?", round_, eid, cid)


def set_turn(conn, eid, round_, turn_id):
    _w(conn, "UPDATE encounters SET round=?, turn_id=? WHERE id=?", round_, turn_id, eid)


def end_encounter(conn, eid, time):
    _w(conn, "UPDATE encounters SET ended=?, turn_id=NULL WHERE id=?", time, eid)


def add_trade(conn, from_id, to_id, give_items, give_coins, want_items, want_coins, time):
    return _w(conn, "INSERT INTO trades (from_id, to_id, give_items, give_coins, want_items, want_coins, status, "
                    "created) VALUES (?,?,?,?,?,?,'pending',?)",
              from_id, to_id, give_items, give_coins, want_items, want_coins, time).lastrowid


def set_trade(conn, tid, status, time):
    _w(conn, "UPDATE trades SET status=?, resolved=? WHERE id=?", status, time, tid)
