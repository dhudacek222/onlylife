"""NPC turns inside encounters: a fixed, deterministic code routine (BRIEF §12 — no LLM). It only picks an
Action; the rules engine resolves it like anyone else's, so an NPC can't do what a player couldn't."""
from engine import world as W
from engine.actions import Action


def choose(conn, cfg, cid, enc):
    me = W.char(conn, cid)
    foes = [m["character_id"] for m in W.members(conn, enc["id"]) if m["character_id"] != cid]
    hurt_by = [r[0] for r in conn.execute(
        "SELECT actor_id FROM events WHERE target_id=? AND verb IN ('attack','steal') AND time>=? ORDER BY id DESC",
        (cid, enc["started"]))]
    attacker = next((a for a in hurt_by if a in foes), None)
    if me["role"] != "guard" and me["hp"] <= cfg.npc_flee_below * me["max_hp"]:
        exits = [e for e in W.exits(conn, me["location_id"])
                 if not (e["door_id"] and W.door(conn, e["door_id"])["locked"])]
        if exits:
            return Action("flee", target=exits[0]["id"])
    if me["role"] == "guard":  # guards go for the most wanted foe, attacker first on ties
        target = max(foes, key=lambda f: (W.char(conn, f)["wanted_level"], f == attacker, f), default=None)
    else:
        target = attacker
    return Action("attack", target=target) if target else Action("wait")
