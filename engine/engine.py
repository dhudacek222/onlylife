"""Engine facade: submit / advance / view / replay. One BEGIN IMMEDIATE transaction per input;
per-observer text is rendered only from that observer's perception rows."""
import json
from contextlib import contextmanager

from engine import db, fixtures, parser, rules
from engine import world as W
from engine.actions import Action, Result
from engine.config import Config

YOU = {
    "move": "You go to {target}.", "flee": "You flee to {target}.", "flee:failure": "You try to flee.",
    "look": "You look around.", "take": "You take {item}.", "drop": "You drop {item}.",
    "give": "You give {item} to {target}.", "buy": "You buy {item} from {target} for {price} coins.",
    "offer": "You offer {target} {deal} (trade #{trade}).", "accept": "You accept trade #{trade} from {target}.",
    "accept:failure": "Trade #{trade} with {target} falls through.", "decline": "You decline trade #{trade}.",
    "attack": "You hit {target}{with} for {damage} damage.", "attack:failure": "You attack {target}{with}.",
    "steal": "You steal {loot} from {target}.", "steal:failure": "You try to steal from {target}.",
    "sneak": "You slip out of sight.", "unhide": "You step out of hiding.",
    "open": "You open {target}.", "close": "You close {target}.", "lock": "You lock {target}.",
    "unlock": "You unlock {target}.", "unlock:failure": "You try to pick {target}.",
    "force": "You force {target} open.", "force:failure": "You throw yourself against {target}.",
    "talk": 'You say to {target}: "{text}"', "say": 'You say: "{text}"', "use": "You use {item}.",
    "wait": "You wait.",
}
THEM = {
    "move": "{actor} goes to {target}.", "flee": "{actor} flees to {target}.",
    "flee:failure": "{actor} tries to flee but can't get away.", "look": "{actor} looks around.",
    "take": "{actor} takes {item}.", "drop": "{actor} drops {item}.", "give": "{actor} gives {item} to {target}.",
    "buy": "{actor} buys {item} from {target}.", "offer": "{actor} offers {target} {deal} (trade #{trade}).",
    "accept": "{actor} accepts a trade from {target}.",
    "accept:failure": "A trade between {actor} and {target} falls through.",
    "decline": "{actor} declines a trade with {target}.",
    "attack": "{actor} hits {target}{with} for {damage} damage.", "attack:failure": "{actor} attacks {target}{with} and misses.",
    "steal": "{actor} steals {loot} from {target}.", "steal:failure": "{actor} tries to steal from {target}!",
    "sneak": "{actor} tries to slip out of sight, but you keep track of them.",
    "unhide": "{actor} steps out of hiding.", "open": "{actor} opens {target}.", "close": "{actor} closes {target}.",
    "lock": "{actor} locks {target}.", "unlock": "{actor} unlocks {target}.",
    "unlock:failure": "{actor} fiddles with the lock of {target}.",
    "force": "CRASH! {actor} forces {target} open.", "force:failure": "BANG! {actor} throws themselves against {target}.",
    "talk": '{actor} says to {target}: "{text}"', "say": '{actor} says: "{text}"', "use": "{actor} uses {item}.",
    "wait": "{actor} waits.",
}


class _Blank(dict):
    def __missing__(self, key):
        return ""


class Engine:
    def __init__(self, conn, config=None):
        self.conn, self.config = conn, config or Config()

    @classmethod
    def create(cls, path=":memory:", seed=42, config=None, world=None):
        conn = db.connect(path)
        db.init(conn)
        eng = cls(conn, config)
        with eng._tx():
            W.load_fixture(conn, world or fixtures.MILL_STREET, seed)
        return eng

    @classmethod
    def open(cls, path, config=None):
        """Continue an existing world file (the persistent world; create() starts a new one)."""
        return cls(db.connect(path), config)

    @classmethod
    def replay(cls, fixture, seed, config, inputs):
        eng = cls.create(seed=seed, config=config, world=fixture)
        for kind, actor_id, payload in inputs:
            if kind == "cmd":
                eng.submit(actor_id, payload)
            elif kind == "actions":  # decided by an AI model: replay the decision, never re-ask the model
                eng.submit_actions(actor_id, [Action.from_dict(d) for d in json.loads(payload)])
            else:
                eng.advance(int(payload))
        return eng

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def inputs(self):
        return [tuple(r) for r in self.conn.execute("SELECT kind, actor_id, payload FROM inputs ORDER BY id")]

    def submit(self, actor_id, text):
        """Text through the M1 hardcoded parser (tests, REPL). Logged as text: the parser is deterministic."""
        actions = parser.parse(text)
        if not actions:  # costs nothing: no input row, no event, no clock
            msg = f"I don't understand '{text}'."
            return [Result(Action("?", raw=text), "unparsed", msg, messages={actor_id: msg})]
        return self._run(actor_id, actions, "cmd", text)

    def submit_actions(self, actor_id, actions):
        """Already-structured actions (from the M2 harness). Logged as the actions themselves, so replay
        never depends on a model answering the same way twice."""
        if not actions:
            raise ValueError("no actions")
        return self._run(actor_id, actions, "actions", json.dumps([a.to_dict() for a in actions]))

    def is_player(self, cid):
        ch = W.char(self.conn, cid)
        return ch is not None and not ch["is_npc"]

    def _run(self, actor_id, actions, kind, payload):
        separate = self.config.chain_actions_cost_separate_turns
        results = []
        with self._tx():
            W.log_input(self.conn, kind, actor_id, payload)
            for a in actions:
                if results and results[-1].outcome != "success":
                    results.append(Result(a, "skipped", "An earlier action in this command didn't succeed."))
                    continue
                r = rules.resolve(self.conn, self.config, actor_id, a)
                if r.event_id:
                    r.messages = self._render(r, actor_id)
                    if separate:
                        W.advance_clock(self.conn, 1)
                else:
                    r.messages = {actor_id: r.reason}
                results.append(r)
            if not separate and any(r.event_id for r in results):
                W.advance_clock(self.conn, 1)
        return results

    def advance(self, ticks):
        with self._tx():
            W.log_input(self.conn, "advance", None, str(ticks))
            W.advance_clock(self.conn, ticks)

    # ------------------------------------------------------------ per-observer output

    def _label(self, observer_id, subject_id):
        if subject_id == observer_id:
            return "you"
        ch = W.char(self.conn, subject_id)
        if ch is None:
            d = W.door(self.conn, subject_id)
            return f"the {d['name']}" if d else W.location(self.conn, subject_id)["name"]
        if not W.can_see(self.conn, observer_id, ch):  # e.g. the hidden target of a witnessed act
            return "someone"
        if W.knows(self.conn, observer_id, subject_id, "knows_identity"):
            return ch["name"]
        return "a stranger in " + ch["appearance"].get("clothes", "plain clothes")

    def _render(self, res, actor_id):
        ev = W.event(self.conn, res.event_id)
        d, verb = ev["data"], ev["verb"]
        key = f"{verb}:failure" if ev["outcome"] == "failure" else verb
        msgs = {}
        for o in W.detectors(self.conn, res.event_id):
            you = o == actor_id
            table = YOU if you else THEM
            f = _Blank(d)
            f["actor"] = self._label(o, ev["actor_id"])
            f["target"] = self._label(o, ev["target_id"]) if ev["target_id"] else ""
            f["item"] = f"the {d['item_name']}" if d.get("item_name") else ""
            f["loot"] = f"{d['coins']} coins" if "coins" in d else f["item"]
            f["with"] = f" with the {d['weapon']}" if d.get("weapon") else " barehanded" if verb == "attack" else ""
            text = table.get(key, table[verb]).format_map(f)
            if d.get("killed"):
                text += " You die." if o == ev["target_id"] else f" {f['target'][0].upper()}{f['target'][1:]} dies."
            if you:
                text += f" {res.reason}" if res.reason else "".join(f" ({r})" for r in res.rolls)
                if d.get("found"):
                    text += " You spot " + ", ".join(self._label(o, s) for s in d["found"]) + "!"
                if d.get("healed") is not None:
                    text += f" You recover {d['healed']} hp."
                if verb in ("look", "move", "flee") and ev["outcome"] == "success":
                    text += " " + self.describe(o)
            msgs[o] = text[0].upper() + text[1:]
        return msgs

    def view(self, observer_id):
        """What this observer can perceive right now. Hidden characters they aren't aware of don't exist here."""
        conn = self.conn
        me = W.char(conn, observer_id)
        here = me["location_id"]
        exits = []
        for e in W.exits(conn, here):
            d = e["door_id"] and W.door(conn, e["door_id"])
            exits.append({"id": e["id"], "name": e["name"],
                          "door": d and {"name": d["name"], "locked": bool(d["locked"]), "open": bool(d["is_open"])}})
        return {
            "time": W.now(conn),
            "you": {**{k: me[k] for k in ("id", "name", "hp", "max_hp", "coins", "status", "wanted_level")},
                    "hidden": bool(me["hidden"])},
            "location": {"id": here, "name": W.location(conn, here)["name"]},
            "exits": exits,
            # ponytail: ids are readable slugs, so they name strangers; switch to opaque ids when disguises land
            "characters": [{"id": c["id"], "name": self._label(observer_id, c["id"]), "status": c["status"]}
                           for c in W.chars_at(conn, here)
                           if c["id"] != observer_id and W.can_see(conn, observer_id, c)],
            "items": [{"id": i["id"], "name": i["name"]} for i in W.items_at(conn, here)],
            "inventory": [{"id": i["id"], "name": i["name"]} for i in W.items_held(conn, observer_id)],
        }

    def describe(self, observer_id):
        v = self.view(observer_id)
        out = [f"You are at {v['location']['name']}."]
        if v["characters"]:
            out.append("You see " + ", ".join(
                c["name"] + (" (dead)" if c["status"] == "dead" else "") for c in v["characters"]) + ".")
        if v["items"]:
            out.append("On the ground: " + ", ".join(i["name"] for i in v["items"]) + ".")
        out.append("Exits: " + ", ".join(e["name"] for e in v["exits"]) + ".")
        return " ".join(out)
