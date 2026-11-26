"""Encounters (BRIEF §7): a hostile act (an attack, or a theft attempt the victim notices) puts actor and target
into turn mode. Joining is by involvement, never by proximity: whoever acts hostile toward a member, or is targeted
by one, joins at the start of the next round; bystanders and new arrivals stay free (anti-freeze, BRIEF §7).
Turn order: earlier joiners first, then initiative (d20 + dex mod, logged), then id. Members leave by dying,
fleeing, or being elsewhere; fewer than two members ends the encounter. All writes go through world.*."""
from engine import world as W
from engine.rules import FREE_VERBS, mod


def _hostile(ev):
    return ev["target_id"] and (ev["verb"] == "attack" or (ev["verb"] == "steal" and ev["outcome"] == "failure"))


def after_action(conn, actor_id, verb, event_id):
    """The engine calls this after every executed action that wrote an event."""
    ev = W.event(conn, event_id)
    enc = W.encounter_of(conn, actor_id)
    had_turn = enc is not None and enc["turn_id"] == actor_id and verb not in FREE_VERBS
    if _hostile(ev) and W.char(conn, ev["target_id"]):
        enc = enc or W.encounter_of(conn, ev["target_id"])
        if enc is None:
            eid = W.add_encounter(conn, ev["location_id"], ev["time"])
            for cid in sorted({actor_id, ev["target_id"]}):
                _join(conn, eid, cid, 1, event_id)
            W.set_turn(conn, eid, 1, W.members(conn, eid)[0]["character_id"])
            return
        for cid in (actor_id, ev["target_id"]):
            if cid not in [m["character_id"] for m in W.members(conn, enc["id"])]:
                _join(conn, enc["id"], cid, enc["round"] + 1, event_id)
    if had_turn:
        _advance(conn, enc["id"])
    for e in {x["id"] for x in (W.encounter_of(conn, actor_id), enc) if x}:
        cleanup(conn, e)


def _join(conn, eid, cid, round_, event_id):
    ch = W.char(conn, cid)
    r = W.roll(conn, cid, "initiative", mod(ch["stats"]["dex"]), event_id=event_id, time=W.now(conn))
    W.add_member(conn, eid, cid, r.total, r.id, round_)


def _order(conn, eid, round_):
    return [m["character_id"] for m in W.members(conn, eid) if m["joined_round"] <= round_]


def _advance(conn, eid, snapshot=None):
    """Pass the turn to the next active member after the current one (in `snapshot`, the order as it was when
    the turn holder acted), or start the next round, where new joiners take their place."""
    enc = W.encounter(conn, eid)
    order = snapshot or _order(conn, eid, enc["round"])
    active = set(_order(conn, eid, enc["round"]))
    later = order[order.index(enc["turn_id"]) + 1:] if enc["turn_id"] in order else []
    later = [c for c in later if c in active]
    if later:
        W.set_turn(conn, eid, enc["round"], later[0])
        return
    nxt = _order(conn, eid, enc["round"] + 1)
    W.set_turn(conn, eid, enc["round"] + 1, nxt[0] if nxt else None)


def cleanup(conn, eid):
    enc = W.encounter(conn, eid)
    if enc["ended"] is not None:
        return
    snapshot = _order(conn, eid, enc["round"])
    for m in W.members(conn, eid):
        ch = W.char(conn, m["character_id"])
        if ch["status"] in ("dead", "offline") or ch["location_id"] != enc["location_id"]:
            W.leave_encounter(conn, eid, ch["id"], enc["round"])
    if len(W.members(conn, eid)) < 2:
        W.end_encounter(conn, eid, W.now(conn))
    elif enc["turn_id"] not in _order(conn, eid, enc["round"]):
        _advance(conn, eid, snapshot)
