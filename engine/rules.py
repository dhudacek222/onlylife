"""Deterministic resolution per verb: references, prerequisites, DCs, dice -> world.* whitelist calls.
Each handler checks every prerequisite (raising Impossible) before its first roll or write."""
import re

from engine import world
from engine.actions import VERBS, Result

ARTICLES = {"the", "a", "an", "my", "your", "his", "her", "their", "some"}
COINS = {"coins", "coin", "money", "gold", "purse"}


class Probe(Exception):
    """Raised by Ctx.roll in preview mode: the first check an action would make, before it is rolled."""

    def __init__(self, purpose, modifier, dc, mode):
        super().__init__(purpose)
        self.purpose, self.modifier, self.dc, self.mode = purpose, modifier, dc, mode


class Impossible(Exception):
    def __init__(self, reason, missing=(), outcome="impossible", candidates=()):
        super().__init__(reason)
        self.reason, self.missing, self.outcome, self.candidates = reason, list(missing), outcome, list(candidates)


def mod(score):
    return (score - 10) // 2


def skill(ch, name):
    return ch["skills"].get(name, 0)


def passive(ch):
    return 10 + mod(ch["stats"]["wis"]) + skill(ch, "perception")


def ac(conn, ch):
    armor = [i["properties"].get("armor", 0) for i in world.items_held(conn, ch["id"]) if i["type"] == "armor"]
    return 10 + mod(ch["stats"]["dex"]) + max(armor, default=0)


def is_night(cfg, t):
    hour = (t % cfg.ticks_per_day) * 24 // cfg.ticks_per_day
    return hour < 6 or hour >= 20


class Ctx:
    """One action in flight: actor snapshot, the reserved event id, and the rolls made so far."""

    def __init__(self, conn, cfg, actor_id, action, probe=False):
        self.conn, self.cfg, self.a, self.probe = conn, cfg, action, probe
        self.me = world.char(conn, actor_id)
        self.now = world.now(conn)
        self.eid = world.next_event_id(conn)
        self.rolls, self.detected = [], []

    @property
    def here(self):
        return self.me["location_id"]

    def roll(self, purpose, modifier, dc=None, mode="normal", sides=20):
        if self.probe:
            raise Probe(purpose, modifier, dc, mode)
        r = world.roll(self.conn, self.me["id"], purpose, modifier, dc, mode, sides, self.eid, self.now)
        self.rolls.append(r)
        return r

    def know(self, observer_id, subject_id, fact):
        world.add_knowledge(self.conn, observer_id, subject_id, fact, self.here, self.now, self.eid)

    def repeat(self, target_id):
        """Diegetic repeat pressure: +step per prior attempt on the same target within the window."""
        since = self.now - self.cfg.repeat_window_ticks
        return self.cfg.repeat_dc_step * world.attempts(self.conn, self.me["id"], self.a.verb, target_id, since)


# ---------------------------------------------------------------- reference resolution

def _norm(ref):
    return " ".join(w for w in (ref or "").lower().split() if w not in ARTICLES)


def names(thing, *extra):
    n = thing["name"].lower()
    return {thing["id"], n, *n.split(), *extra}


def item_names(it):
    return names(it, *it["aliases"])


def place_names(loc):
    return names(loc, *loc["tags"])


def pick(ref, things, names_of):
    ref = _norm(ref)
    found = [t for t in things if t["id"] == ref] or [t for t in things if ref in names_of(t)]
    if len(found) > 1:
        ids = [t["id"] for t in found]
        raise Impossible(f"Which {ref}? ({', '.join(ids)})", outcome="ambiguous", candidates=ids)
    return found[0] if found else None


def inv(c):
    return world.items_held(c.conn, c.me["id"])


def floor(c):
    return world.items_at(c.conn, c.here)


def find_item(c, ref, *scopes):
    """Resolution order is the order of `scopes` (inventory first, then the location)."""
    if not ref:
        raise Impossible(f"{c.a.verb.capitalize()} what?", missing=["item"])
    for things in scopes:
        it = pick(ref, things, item_names)
        if it:
            return it
    raise Impossible(f"You don't see '{ref}' here.", missing=[ref])


def held(c, ref):
    it = find_item(c, ref, inv(c), floor(c))
    if it["holder_id"] != c.me["id"]:
        raise Impossible(f"You aren't holding the {it['name']}.", missing=[it["name"]])
    return it


def visible_chars(c):
    """Hidden characters the actor isn't aware of are simply not here, as far as resolution goes."""
    return [x for x in world.chars_at(c.conn, c.here)
            if x["id"] != c.me["id"] and world.can_see(c.conn, c.me["id"], x)]


def find_char(c, ref, alive=True):
    if not ref:
        raise Impossible(f"{c.a.verb.capitalize()} whom?", missing=["target"])
    ch = pick(ref, visible_chars(c), names)
    if not ch:  # same words whether absent or hidden: no leak
        raise Impossible(f"You don't see '{ref}' here.", missing=[ref])
    if alive and ch["status"] == "dead":
        raise Impossible(f"{ch['name']} is dead.")
    return ch


def find_exit(c, ref):
    if not ref:
        raise Impossible("Go where?", missing=["destination"])
    dest = pick(ref, world.exits(c.conn, c.here), place_names)
    if not dest:
        raise Impossible(f"You can't get to '{ref}' from here.", missing=[ref])
    return dest, dest["door_id"] and world.door(c.conn, dest["door_id"])


def find_door(c, ref):
    doors = []
    for e in world.exits(c.conn, c.here):
        if e["door_id"]:
            doors.append(dict(world.door(c.conn, e["door_id"]), dest=e))
    ref = _norm(ref)
    place = re.sub(r"\s*\b(door|lock)$", "", ref)
    found = [d for d in doors if not ref or ref in names(d) or place in place_names(d["dest"])]
    if not found:
        raise Impossible(f"There is no door '{ref}' here." if ref else "There is no door here.", missing=["door"])
    if len(found) > 1:
        ids = [d["id"] for d in found]
        raise Impossible(f"Which door? ({', '.join(ids)})", outcome="ambiguous", candidates=ids)
    return found[0]


def has_key(c, d):
    return d["key_item_id"] is not None and any(i["id"] == d["key_item_id"] for i in inv(c))


def key_name(c, d):
    return world.item(c.conn, d["key_item_id"])["name"] if d["key_item_id"] else "key"


# ---------------------------------------------------------------- evidence: event + perceptions + knowledge

def record(c, outcome, target=None, item=None, crime=None, data=None, reason="", missing=(),
           always=(), never=(), everyone=False, locs=None):
    """Write the event and one perception row per present character. Undetecting characters get a
    detected=0 row (evidence of who was there) and nothing else: no knowledge, no text."""
    conn = c.conn
    me = world.char(conn, c.me["id"])
    if VERBS[c.a.verb].hostile and me["hidden"]:
        world.set_hidden(conn, me["id"], 0)
        me = world.char(conn, me["id"])
    loc = me["location_id"]
    data = dict(data or {})
    if item and "item_name" not in data:
        data["item_name"] = world.item(conn, item)["name"]
    world.add_event(conn, c.eid, c.now, me["id"], c.a.verb, target, item, loc, outcome, crime, data)
    roll_id = c.rolls[0].id if c.rolls else None
    world.add_perception(conn, c.eid, me["id"], 1, 1, None, roll_id)
    witnesses = 0
    for l in locs or [loc]:
        for o in world.chars_at(conn, l):
            if o["id"] == me["id"] or (o["status"] not in ("online", "afk") and o["id"] not in always):
                continue
            seen = o["id"] not in never and (everyone or o["id"] in always or world.can_see(conn, o["id"], me))
            if not seen:
                world.add_perception(conn, c.eid, o["id"], 0, 0, None, roll_id)
                continue
            known = world.knows(conn, o["id"], me["id"], "knows_identity")
            looks = None if known else {"face_shape": me["face_shape"], **me["appearance"]}
            world.add_perception(conn, c.eid, o["id"], 1, known, looks, roll_id)
            world.add_knowledge(conn, o["id"], me["id"], "seen_at", loc, c.now, c.eid)
            if crime:
                world.add_knowledge(conn, o["id"], me["id"], "knows_crime", loc, c.now, c.eid)
            c.detected.append(o["id"])
            witnesses += o["status"] != "dead"
    if crime and witnesses:
        world.add_wanted(conn, me["id"], c.cfg.wanted_severity[crime])
    return Result(c.a, outcome, reason, list(missing), rolls=c.rolls, event_id=c.eid)


# ---------------------------------------------------------------- verbs

def stealth_mod(c, loc):
    me = c.me
    m = mod(me["stats"]["dex"]) + skill(me, "stealth") + loc["cover"] + loc["crowd"]
    if is_night(c.cfg, c.now) and not loc["lit"]:
        m += 2
    m -= 2 * sum(1 for g in world.present(c.conn, loc["id"], exclude=me["id"])
                 if g["role"] == "guard" and world.can_see(c.conn, me["id"], g))
    heavy = any(i["type"] == "armor" and i["properties"].get("heavy") for i in inv(c))
    return m, "disadvantage" if heavy else "normal"


def do_move(c, a):
    dest, door = find_exit(c, a.target)
    if door and door["locked"]:
        raise Impossible(f"The {door['name']} is locked.", missing=[f"unlocked {door['name']}"])
    origin, me = c.here, c.me
    if a.verb == "flee":
        r = c.roll("flee", mod(me["stats"]["dex"]), c.cfg.dc_normal)
        if not r.success:
            return record(c, "failure", target=dest["id"], reason=f"You can't get away: {r}.")
    if door and not door["is_open"]:
        world.set_door(c.conn, door["id"], is_open=1)
    world.move_char(c.conn, me["id"], dest["id"])
    crime = None
    if not dest["is_public"] and dest["owner_id"] not in (None, me["id"]):
        crime = "burglary" if door and world.broke_in(c.conn, me["id"], door["id"]) else "trespass"
    others = world.present(c.conn, dest["id"], exclude=me["id"])
    c.me = world.char(c.conn, me["id"])
    if me["hidden"]:  # sneaking in: one fresh stealth roll vs every observer at the destination
        m, mode = stealth_mod(c, dest)
        r = c.roll("stealth", m, mode=mode)
        world.set_hidden(c.conn, me["id"], 1, me["hidden_since"], r.total)
        for o in others:
            if passive(o) >= r.total:
                c.know(o["id"], me["id"], "aware_of")
    for o in others:  # arrival: notice hidden people with passive perception, note everyone visible
        if o["hidden"] and not world.can_see(c.conn, me["id"], o) and passive(me) >= o["stealth_total"]:
            c.know(me["id"], o["id"], "aware_of")
        if world.can_see(c.conn, me["id"], o):
            c.know(me["id"], o["id"], "seen_at")
    return record(c, "success", target=dest["id"], crime=crime, locs=[origin, dest["id"]])


def do_look(c, a):
    me = c.me
    r = c.roll("perception", mod(me["stats"]["wis"]) + skill(me, "perception"))  # always rolled: no leak
    found = []
    for o in world.present(c.conn, c.here, exclude=me["id"]):
        if o["hidden"] and not world.can_see(c.conn, me["id"], o) and r.total >= o["stealth_total"]:
            c.know(me["id"], o["id"], "aware_of")
            found.append(o["id"])
    return record(c, "success", data={"found": found})


def do_take(c, a):
    if not a.item:
        raise Impossible("Take what?", missing=["item"])
    bodies = [x for x in world.chars_at(c.conn, c.here) if x["status"] == "dead"]
    loot = [i for b in bodies for i in world.items_held(c.conn, b["id"])]
    it = pick(a.item, floor(c), item_names) or pick(a.item, loot, item_names)
    if not it:
        if pick(a.item, inv(c), item_names):
            raise Impossible(f"You already have the {_norm(a.item)}.")
        raise Impossible(f"You don't see '{a.item}' here.", missing=[a.item])
    loc = world.location(c.conn, c.here)
    looted = it["holder_id"] is not None
    crime = "theft" if not looted and not loc["is_public"] and loc["owner_id"] not in (None, c.me["id"]) else None
    world.move_item(c.conn, it["id"], "looted" if looted else "taken", holder_id=c.me["id"], event_id=c.eid)
    return record(c, "success", target=it["holder_id"], item=it["id"], crime=crime)


def do_drop(c, a):
    it = held(c, a.item)
    world.move_item(c.conn, it["id"], "dropped", location_id=c.here, event_id=c.eid)
    world.add_trace(c.conn, c.eid, "item_left", it["id"], c.here, {"by": c.me["id"]})
    return record(c, "success", item=it["id"])


def do_give(c, a):
    it = held(c, a.item)
    to = find_char(c, a.target)
    world.move_item(c.conn, it["id"], "given", holder_id=to["id"], event_id=c.eid)
    return record(c, "success", target=to["id"], item=it["id"])


def do_buy(c, a):
    if a.target:
        m = find_char(c, a.target)
    else:
        ms = [x for x in visible_chars(c) if x["role"] == "merchant" and x["status"] != "dead"]
        if len(ms) != 1:
            raise Impossible("Buy from whom?", missing=["merchant"] if not ms else [],
                             outcome="ambiguous" if ms else "impossible", candidates=[x["id"] for x in ms])
        m = ms[0]
    if m["role"] != "merchant":
        raise Impossible(f"{m['name']} isn't selling anything.", missing=["merchant"])
    if not a.item:
        raise Impossible("Buy what?", missing=["item"])
    it = pick(a.item, [i for i in world.items_held(c.conn, m["id"]) if i["price"] is not None], item_names)
    if not it:
        raise Impossible(f"{m['name']} doesn't sell '{a.item}'.", missing=[a.item])
    price, coins = it["price"], c.me["coins"]
    if coins < price:
        raise Impossible(f"The {it['name']} costs {price} coins; you have {coins}.",
                         missing=[f"{price - coins} more coins"])
    world.add_coins(c.conn, c.me["id"], -price)
    world.add_coins(c.conn, m["id"], price)
    world.move_item(c.conn, it["id"], "bought", holder_id=c.me["id"], event_id=c.eid)
    world.add_trace(c.conn, c.eid, "purchase", it["id"], c.here, {"buyer": c.me["id"], "seller": m["id"], "price": price})
    return record(c, "success", target=m["id"], item=it["id"], data={"price": price})


def _goods(it, coins):
    return " and ".join(([f"the {it['name']}"] if it else []) + ([f"{coins} coins"] if coins else [])) or "nothing"


def do_offer(c, a):
    to = find_char(c, a.target)
    give = held(c, a.item) if a.item else None
    want = None
    if a.want_item:
        want = pick(a.want_item, world.items_held(c.conn, to["id"]), item_names)
        if not want:
            raise Impossible(f"{to['name']} doesn't have '{a.want_item}'.", missing=[a.want_item])
    if not (give or a.coins or want or a.want_coins):
        raise Impossible("Offer what?", missing=["item or coins"])
    if a.coins > c.me["coins"]:
        raise Impossible(f"You only have {c.me['coins']} coins.", missing=[f"{a.coins - c.me['coins']} more coins"])
    tid = world.add_trade(c.conn, c.me["id"], to["id"], [give["id"]] if give else [], a.coins,
                          [want["id"]] if want else [], a.want_coins, c.now)
    deal = f"{_goods(give, a.coins)} for {_goods(want, a.want_coins)}"
    return record(c, "success", target=to["id"], item=give and give["id"], data={"trade": tid, "deal": deal})


def _pending_trade(c, a):
    if a.target and a.target.isdigit():
        t = world.trade(c.conn, int(a.target))
    elif a.target:
        t = world.latest_trade(c.conn, c.me["id"], find_char(c, a.target, alive=False)["id"])
    else:
        t = world.latest_trade(c.conn, c.me["id"])
    if not t:
        raise Impossible("There is no such offer.", missing=["pending offer"])
    if t["status"] != "pending":
        raise Impossible(f"Trade #{t['id']} is already {t['status']}.")
    return t


def do_accept(c, a):
    t = _pending_trade(c, a)
    me = c.me
    if t["to_id"] != me["id"]:
        raise Impossible(f"Trade #{t['id']} isn't addressed to you.")
    frm = world.char(c.conn, t["from_id"])
    # re-validate everything: offering never locks anything, so it may all have moved since
    problems = []
    if frm["location_id"] != me["location_id"] or frm["status"] == "dead":
        problems.append(f"{frm['name']} is not here")
    for iid in t["give_items"]:
        it = world.item(c.conn, iid)
        if it["holder_id"] != frm["id"]:
            problems.append(f"{frm['name']} no longer has the {it['name']}")
    for iid in t["want_items"]:
        it = world.item(c.conn, iid)
        if it["holder_id"] != me["id"]:
            problems.append(f"you no longer have the {it['name']}")
    if frm["coins"] < t["give_coins"]:
        problems.append(f"{frm['name']} doesn't have {t['give_coins']} coins")
    if me["coins"] < t["want_coins"]:
        problems.append(f"you don't have {t['want_coins']} coins")
    if problems:
        world.set_trade(c.conn, t["id"], "failed", c.now)
        return record(c, "failure", target=frm["id"], data={"trade": t["id"]},
                      reason="The trade fails: " + "; ".join(problems) + ".", missing=problems)
    for iid in t["give_items"]:
        world.move_item(c.conn, iid, "traded", holder_id=me["id"], event_id=c.eid)
    for iid in t["want_items"]:
        world.move_item(c.conn, iid, "traded", holder_id=frm["id"], event_id=c.eid)
    net = t["give_coins"] - t["want_coins"]
    world.add_coins(c.conn, frm["id"], -net)
    world.add_coins(c.conn, me["id"], net)
    world.set_trade(c.conn, t["id"], "accepted", c.now)
    return record(c, "success", target=frm["id"], data={"trade": t["id"]})


def do_decline(c, a):
    t = _pending_trade(c, a)
    if c.me["id"] not in (t["to_id"], t["from_id"]):
        raise Impossible(f"Trade #{t['id']} isn't addressed to you.")
    world.set_trade(c.conn, t["id"], "declined", c.now)
    other = t["from_id"] if t["to_id"] == c.me["id"] else t["to_id"]
    return record(c, "success", target=other, data={"trade": t["id"]})


def kill(c, victim):
    world.set_status(c.conn, victim["id"], "dead")
    if victim["hidden"]:
        world.set_hidden(c.conn, victim["id"], 0)
    world.add_trace(c.conn, c.eid, "body", None, victim["location_id"], {"victim": victim["id"]})
    # ponytail: penalty-mode revival after death_lockout needs a real-time clock (M5); until then the
    # modes differ only in what happens to carried items (dropped here vs left on the lootable body).
    if c.cfg.death_mode == "penalty":
        for it in world.items_held(c.conn, victim["id"]):
            world.move_item(c.conn, it["id"], "dropped", location_id=victim["location_id"], event_id=c.eid)


def do_attack(c, a):
    me = c.me
    t = find_char(c, a.target)
    if a.item:
        w = held(c, a.item)
        if not w["properties"].get("damage"):
            raise Impossible(f"The {w['name']} is not a weapon.", missing=["weapon"])
    else:
        ws = [i for i in inv(c) if i["properties"].get("damage")]
        w = max(ws, key=lambda i: i["properties"]["damage"]) if ws else None
    surprise = me["hidden"] and not world.can_see(c.conn, t["id"], me)
    mode = "advantage" if surprise or t["status"] == "afk" else "normal"
    m = mod(me["stats"]["str"]) + skill(me, "athletics") - (0 if w else c.cfg.unarmed_attack_penalty)
    r = c.roll("attack", m, ac(c.conn, t), mode)
    data = {"weapon": w and w["name"]}
    if not r.success:
        return record(c, "failure", target=t["id"], item=w and w["id"], crime="assault", data=data,
                      reason=f"You miss: {r}.", always=[t["id"]])
    str_mod = mod(me["stats"]["str"])
    dmg = max(1, c.roll("damage", str_mod, sides=w["properties"]["damage"]).total if w
              else c.cfg.unarmed_damage + str_mod)
    hp = max(0, t["hp"] - dmg)
    world.set_hp(c.conn, t["id"], hp)
    if w:
        world.flag_item(c.conn, w["id"], "bloodied")
        world.add_trace(c.conn, c.eid, "bloodied_item", w["id"], c.here, {"victim": t["id"]})
    if hp == 0:
        kill(c, t)
    data.update(damage=dmg, killed=hp == 0, death_mode=c.cfg.death_mode if hp == 0 else None)
    return record(c, "success", target=t["id"], item=w and w["id"], crime="murder" if hp == 0 else "assault",
                  data=data, always=[t["id"]])


def do_steal(c, a):
    me = c.me
    t = find_char(c, a.target)
    it = None
    if a.item and _norm(a.item) not in COINS:
        it = pick(a.item, world.items_held(c.conn, t["id"]), item_names)
        if not it:
            raise Impossible(f"{t['name']} doesn't have '{a.item}'.", missing=[a.item])
    dc = passive(t) + c.repeat(t["id"])
    r = c.roll("sleight", mod(me["stats"]["dex"]) + skill(me, "sleight"), dc,
               "advantage" if t["status"] == "afk" else "normal")
    if not r.success:  # the mark notices, and keeps noticing
        if me["hidden"]:
            c.know(t["id"], me["id"], "aware_of")
        return record(c, "failure", target=t["id"], item=it and it["id"], crime="theft",
                      reason=f"{t['name']} notices: {r}.", always=[t["id"]])
    data = {}
    if it:
        world.move_item(c.conn, it["id"], "stolen", holder_id=me["id"], event_id=c.eid)
    else:
        data["coins"] = n = t["coins"] // 2
        world.add_coins(c.conn, t["id"], -n)
        world.add_coins(c.conn, me["id"], n)
    return record(c, "success", target=t["id"], item=it and it["id"], crime="theft", data=data, never=[t["id"]])


def do_sneak(c, a):
    me = c.me
    if me["hidden"]:
        raise Impossible("You are already hidden.")
    m, mode = stealth_mod(c, world.location(c.conn, c.here))
    r = c.roll("stealth", m, mode=mode)
    world.set_hidden(c.conn, me["id"], 1, c.now, r.total)
    for o in world.present(c.conn, c.here, exclude=me["id"]):  # vs EACH observer's passive perception
        if passive(o) >= r.total:
            c.know(o["id"], me["id"], "aware_of")
    return record(c, "success")


def do_unhide(c, a):
    if not c.me["hidden"]:
        raise Impossible("You aren't hiding.")
    world.set_hidden(c.conn, c.me["id"], 0)
    return record(c, "success")


def do_open(c, a):
    d = find_door(c, a.target)
    if d["is_open"]:
        raise Impossible(f"The {d['name']} is already open.")
    if d["locked"]:
        raise Impossible(f"The {d['name']} is locked.", missing=[f"unlocked {d['name']}"])
    world.set_door(c.conn, d["id"], is_open=1)
    return record(c, "success", target=d["id"])


def do_close(c, a):
    d = find_door(c, a.target)
    if not d["is_open"]:
        raise Impossible(f"The {d['name']} is already closed.")
    world.set_door(c.conn, d["id"], is_open=0)
    return record(c, "success", target=d["id"])


def do_unlock(c, a):
    d = find_door(c, a.target)
    if not d["locked"]:
        raise Impossible(f"The {d['name']} isn't locked.")
    if has_key(c, d):
        world.set_door(c.conn, d["id"], locked=0)
        return record(c, "success", target=d["id"], data={"method": "key"})
    lockpick = any(i["type"] == "lockpick" for i in inv(c))
    if not lockpick or d["lock_dc"] is None:
        raise Impossible(f"The {d['name']} is locked and you have no way to open it.",
                         missing=[key_name(c, d)] + (["lockpick"] if d["lock_dc"] is not None else []))
    me = c.me
    r = c.roll("lockpicking", mod(me["stats"]["dex"]) + skill(me, "lockpicking"), d["lock_dc"] + c.repeat(d["id"]))
    if not r.success:
        return record(c, "failure", target=d["id"], data={"method": "lockpick"}, reason=f"The lock holds: {r}.")
    world.set_door(c.conn, d["id"], locked=0)
    return record(c, "success", target=d["id"], data={"method": "lockpick"})


def do_lock(c, a):
    d = find_door(c, a.target)
    if d["locked"]:
        raise Impossible(f"The {d['name']} is already locked.")
    if not has_key(c, d):
        raise Impossible(f"You need the {key_name(c, d)} to lock the {d['name']}.", missing=[key_name(c, d)])
    world.set_door(c.conn, d["id"], locked=1, is_open=0)
    return record(c, "success", target=d["id"])


def do_force(c, a):
    d = find_door(c, a.target)
    if not d["locked"]:
        raise Impossible(f"The {d['name']} isn't locked.")
    me = c.me
    dc = (d["lock_dc"] or c.cfg.dc_normal) + 4 + c.repeat(d["id"])
    r = c.roll("athletics", mod(me["stats"]["str"]) + skill(me, "athletics"), dc)
    if r.success:
        world.set_door(c.conn, d["id"], locked=0, is_open=1)
        world.add_trace(c.conn, c.eid, "forced_lock", None, c.here, {"door": d["id"]})
    # noisy: everyone on both sides of the door detects it
    return record(c, "success" if r.success else "failure", target=d["id"], data={"method": "force"},
                  reason="" if r.success else f"The door holds: {r}.", everyone=True,
                  locs=world.door_sides(c.conn, d["id"]))


def do_talk(c, a):
    t = find_char(c, a.target) if a.verb == "talk" else None
    if not a.text:
        raise Impossible("Say what?", missing=["text"])
    res = record(c, "success", target=t and t["id"], data={"text": a.text})
    if c.me["name"].lower() in a.text.lower():  # introducing yourself
        for o in c.detected:
            c.know(o, c.me["id"], "knows_identity")
    return res


def do_use(c, a):
    it = held(c, a.item)
    effect = it["properties"].get("on_use")
    if not effect:
        raise Impossible(f"You can't use the {it['name']}.", missing=["usable item"])
    data = {"item_name": it["name"]}
    if effect.get("effect") == "heal":
        hp = min(c.me["max_hp"], c.me["hp"] + effect.get("amount", 0))
        world.set_hp(c.conn, c.me["id"], hp)
        data["healed"] = hp - c.me["hp"]
    if effect.get("becomes"):
        world.transform_item(c.conn, it["id"], effect["becomes"], c.eid)
    return record(c, "success", item=it["id"], data=data)


def do_wait(c, a):
    return record(c, "success")


HANDLERS = {
    "move": do_move, "flee": do_move, "look": do_look, "take": do_take, "drop": do_drop, "give": do_give,
    "buy": do_buy, "offer": do_offer, "accept": do_accept, "decline": do_decline, "attack": do_attack,
    "steal": do_steal, "sneak": do_sneak, "unhide": do_unhide, "open": do_open, "close": do_close,
    "unlock": do_unlock, "lock": do_lock, "force": do_force, "talk": do_talk, "say": do_talk,
    "use": do_use, "wait": do_wait,
}


def resolve(conn, cfg, actor_id, action, probe=False):
    """Resolve one action inside the caller's transaction. Impossible/ambiguous roll back to a savepoint,
    so they can never leave a write behind; any other exception propagates to the caller's rollback.
    probe=True: check prerequisites, then stop at the first roll and return the Probe (or the Result if the
    action needs no roll); nothing is kept either way."""
    conn.execute("SAVEPOINT action")
    try:
        c = Ctx(conn, cfg, actor_id, action, probe)
        if c.me is None:
            raise Impossible(f"There is no character '{actor_id}'.")
        if c.me["status"] == "dead":
            raise Impossible("You are dead.")
        res = HANDLERS[action.verb](c, action)
    except Probe as p:
        conn.execute("ROLLBACK TO action")
        conn.execute("RELEASE action")
        return p
    except Impossible as e:
        conn.execute("ROLLBACK TO action")
        conn.execute("RELEASE action")
        return Result(action, e.outcome, e.reason, e.missing, e.candidates)
    if probe:
        conn.execute("ROLLBACK TO action")
    conn.execute("RELEASE action")
    return res
