"""Engine facade: submit / advance / view / replay. The M2 harness loop lives in submit():
text -> DecisionModel -> (refuse | unparsed | clarify | confirm) -> execute: one BEGIN IMMEDIATE transaction
per input. Narration is built per observer from that observer's perception row only."""
import json
from contextlib import contextmanager

from engine import db, encounters, fixtures, npc, rules
from engine import world as W
from engine.actions import VERBS, Action, Result, to_command
from engine.config import Config
from engine.dice import success_probability
from harness.narration import TemplateNarrator
from harness.rules_model import RulesDecisionModel

REFUSED = "The world doesn't bend to words like that. Say what your character does."
CANCEL = {"label": "Cancel", "command": None}


class Engine:
    def __init__(self, conn, config=None, model=None, narrator=None):
        self.conn, self.config = conn, config or Config()
        self.model = model or RulesDecisionModel()
        self.template = TemplateNarrator()
        self.narrator = narrator or self.template  # used for free text; buttons always get templates

    @classmethod
    def create(cls, path=":memory:", seed=42, config=None, world=None, model=None, narrator=None):
        conn = db.connect(path)
        db.init(conn)
        eng = cls(conn, config, model, narrator)
        with eng._tx():
            W.load_fixture(conn, world or fixtures.MILL_STREET, seed)
        return eng

    @classmethod
    def replay(cls, fixture, seed, config, inputs):
        """Re-executes the logged DECIDED actions: no model is consulted, so replay is exact."""
        eng = cls.create(seed=seed, config=config, world=fixture)
        for kind, actor_id, payload in inputs:
            if kind == "cmd":
                p = json.loads(payload)
                eng._execute(actor_id, p["text"], [Action.from_dict(a) for a in p["actions"]])
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

    # ------------------------------------------------------------ the harness loop

    def submit(self, actor_id, text, confirm=False, via="text"):
        """via="button": the text is a canonical command from our own buttons (template narration)."""
        if W.char(self.conn, actor_id) is None:
            return [Result(Action("?", raw=text), "impossible", f"There is no character '{actor_id}'.")]
        d = self.model.decide(text, self.view(actor_id))
        if d.usage:
            with self._tx():
                W.log_model_call(self.conn, actor_id, "decide", d.usage, [a.verb for a in d.actions])
        if d.injection:  # costs nothing, like unparsed input
            return [Result(Action("?", raw=text), "refused", REFUSED, messages={actor_id: REFUSED})]
        if not d.actions:
            msg = f"I don't understand '{text}'."
            return [Result(Action("?", raw=text), "unparsed", msg, messages={actor_id: msg},
                           alternatives=[{"label": s, "command": s} for s in d.suggestions])]
        command = " and ".join(to_command(a) for a in d.actions)
        risky = any(VERBS[a.verb].irreversible for a in d.actions)
        unsure = d.confidence < (self.config.escalate_below if risky else self.config.clarify_below)
        if unsure:  # never guess silently on irreversible actions; don't burn turns on wild guesses either
            msg = f"Did you mean: {command}?"
            return [Result(d.actions[0], "clarify", msg, messages={actor_id: msg},
                           alternatives=[{"label": command, "command": command}, CANCEL])]
        if risky and self.config.confirm_irreversible and not confirm:
            stop = self._preview(actor_id, d.actions)
            if stop.outcome != "confirm":
                return [stop]
            stop.alternatives = [{"label": f"Yes: {command}", "command": command, "confirm": True}, CANCEL]
            return [stop]
        return self._execute(actor_id, text, d.actions, template=via == "button") + self._npc_turns()

    def timeout(self, encounter_id):
        """The server calls this when the turn timer (Config.turn_timer_seconds) runs out: the member whose turn it
        is takes the default action. Logged like any command, so replay needs no clock."""
        enc = W.encounter(self.conn, encounter_id)
        if enc is None or enc["ended"] is not None or enc["turn_id"] is None:
            return []
        return self._execute(enc["turn_id"], "(timeout)", [Action("wait")]) + self._npc_turns()

    def _npc_turns(self):
        """Play every NPC whose turn it is, until a human is up (or nobody is fighting)."""
        results = []
        for _ in range(200):  # ponytail: hard stop against NPC-only fights that never end; M3 routines replace it
            enc = next((e for e in W.active_encounters(self.conn)
                        if e["turn_id"] and W.char(self.conn, e["turn_id"])["is_npc"]), None)
            if enc is None:
                break
            nid = enc["turn_id"]
            rs = self._execute(nid, "(npc)", [npc.choose(self.conn, self.config, nid, enc)])
            if not rs[0].event_id:  # e.g. its attacker is hidden from it: it holds its ground
                rs = self._execute(nid, "(npc)", [Action("wait")])
            results += rs
        return results

    def _preview(self, actor_id, actions):
        """Dry-run the chain up to its first irreversible action, then roll everything back. Returns that action's
        'confirm' Result with a risk estimate, or the impossible/ambiguous Result that would stop the chain."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for a in actions:
                if VERBS[a.verb].irreversible:
                    p = rules.resolve(self.conn, self.config, actor_id, a, probe=True)
                    if isinstance(p, Result) and p.outcome in ("impossible", "ambiguous"):
                        return self._stopped(actor_id, a, p)
                    msg = self._risk(actor_id, a, p)
                    return Result(a, "confirm", msg, messages={actor_id: msg})
                r = rules.resolve(self.conn, self.config, actor_id, a)
                if r.outcome in ("impossible", "ambiguous"):
                    return self._stopped(actor_id, a, r)
                if r.outcome != "success":  # a dice-dependent step: we can't promise what comes after it
                    msg = f"First you'd {to_command(a)}; what follows depends on how that goes. Go ahead?"
                    return Result(a, "confirm", msg, messages={actor_id: msg})
        finally:
            self.conn.execute("ROLLBACK")
        raise AssertionError("no irreversible action in a risky chain")

    def _stopped(self, actor_id, action, res):
        res.messages = {actor_id: res.reason}
        res.alternatives = self._alternatives(actor_id, action, res)
        return res

    def _risk(self, actor_id, action, probe):
        """Verbal risk estimate (OPEN DECISION 1): precision grows with the character's experience."""
        crime = VERBS[action.verb].crime
        tail = f" It is a crime ({crime}) if anyone sees it." if crime else " This can't be undone."
        mode = self.config.risk_display
        if not isinstance(probe, rules.Probe) or mode == "none":
            return f"Are you sure you want to {to_command(action)}?{tail}"
        p = float(success_probability(probe.modifier, probe.dc, probe.mode))
        xp = W.char(self.conn, actor_id)["xp"]
        coarse, fine = self.config.risk_xp_steps
        if mode == "exact" or xp >= fine:
            est = f"about {round(p * 100)}% to succeed" if mode == "exact" else f"roughly {round(p * 10)} in 10"
        elif xp >= coarse:
            est = next(w for t, w in ((0.15, "almost hopeless"), (0.4, "unlikely"), (0.6, "a coin toss"),
                                      (0.85, "likely"), (1.01, "almost certain")) if p < t)
        else:
            est = "poor" if p < 0.35 else "even" if p < 0.7 else "good"
        return f"{to_command(action).capitalize()}? Your odds look {est}.{tail}"

    def _alternatives(self, actor_id, action, res):
        """Feasible next steps instead of a bare 'no' (BRIEF §5.4). Built from the actor's view only."""
        v = self.view(actor_id)
        held = {i["name"] for i in v["inventory"]}
        types = {i["type"] for i in v["inventory"]}
        out = []
        for m in res.missing:
            if m.startswith("unlocked "):  # a locked door in the way
                door = m[len("unlocked "):]
                if "key" in types or "lockpick" in types:
                    out.append(f"unlock {door}")
                out.append(f"force {door}")
            elif m == "flee":  # in a fight, walking away isn't an option
                out += [f"flee to {e['name']}" for e in v["exits"]]
            elif m == "lockpick":
                out += [f"take {i['name']}" for i in v["items"] if i["type"] == "lockpick"]
                if action.target:
                    out.append(f"force {action.target}")
            elif action.verb == "attack" and action.item and m not in held:  # named weapon not in hand
                if any(action.item in (i["name"], *i["aliases"]) for i in v["items"]):
                    out.append(f"take {action.item} and attack {action.target}")
                out.append(f"attack {action.target}")
        if res.outcome == "ambiguous":
            out += [to_command(Action(**{**action.__dict__, "target" if action.target else "item": c}))
                    for c in res.candidates]
        out.append("look around")
        return [{"label": c, "command": c} for c in dict.fromkeys(out)] + [CANCEL]

    def _execute(self, actor_id, text, actions, template=True):
        separate = self.config.chain_actions_cost_separate_turns
        narrator = self.template if template else self.narrator
        results = []
        with self._tx():
            W.log_input(self.conn, "cmd", actor_id, {"text": text, "actions": [a.to_dict() for a in actions]})
            for a in actions:
                if results and results[-1].outcome != "success":
                    results.append(Result(a, "skipped", "An earlier action in this command didn't succeed."))
                    continue
                r = rules.resolve(self.conn, self.config, actor_id, a)
                if r.event_id and self.config.encounters:
                    encounters.after_action(self.conn, actor_id, a.verb, r.event_id)
                if r.event_id:
                    r.messages = {}
                    for o in W.detectors(self.conn, r.event_id):
                        r.messages[o] = narrator.narrate(self.facts(o, r))
                        if getattr(narrator, "last_usage", None):
                            W.log_model_call(self.conn, o, "narrate", narrator.last_usage, [a.verb])
                            narrator.last_usage = None
                    if separate:
                        W.advance_clock(self.conn, 1)
                else:
                    self._stopped(actor_id, a, r)
                results.append(r)
            if not separate and any(r.event_id for r in results):
                W.advance_clock(self.conn, 1)
        return results

    def advance(self, ticks):
        with self._tx():
            W.log_input(self.conn, "advance", None, str(ticks))
            W.advance_clock(self.conn, ticks)

    # ------------------------------------------------------------ per-observer facts

    def _label(self, observer_id, subject_id):
        if subject_id == observer_id:
            return "you"
        ch = W.char(self.conn, subject_id)
        if ch is None:
            d = W.door(self.conn, subject_id)
            return f"the {d['name']}" if d else W.location(self.conn, subject_id)["name"]
        if W.knows(self.conn, observer_id, subject_id, "knows_identity"):
            return ch["name"]
        return "a stranger in " + ch["appearance"].get("clothes", "plain clothes")

    def facts(self, observer_id, res):
        """Everything a narrator may use for this observer: labels as THEY know them, no ids, no hidden
        entities they haven't noticed, rolls only for the actor. Called only for detecting observers."""
        ev = W.event(self.conn, res.event_id)
        d, you = ev["data"], observer_id == ev["actor_id"]
        f = {"verb": ev["verb"], "outcome": ev["outcome"], "you_acted": you,
             "actor": self._label(observer_id, ev["actor_id"]),
             "target": self._label(observer_id, ev["target_id"]) if ev["target_id"] else "",
             "target_is_you": ev["target_id"] == observer_id}
        for k in ("item_name", "weapon", "damage", "killed", "coins", "deal", "trade", "text", "price"):
            if d.get(k) is not None:
                f["item" if k == "item_name" else k] = d[k]
        if you:
            f["reason"], f["rolls"] = res.reason, [str(r) for r in res.rolls]
            if d.get("found"):
                f["found"] = [self._label(observer_id, s) for s in d["found"]]
            if d.get("healed") is not None:
                f["healed"] = d["healed"]
            if ev["verb"] in ("look", "move", "flee") and ev["outcome"] == "success":
                f["scene"] = self.describe(observer_id)
        return f

    def view(self, observer_id):
        """What this observer can perceive right now. Hidden characters they aren't aware of don't exist here."""
        conn = self.conn
        me = W.char(conn, observer_id)
        here = me["location_id"]
        exits = []
        for e in W.exits(conn, here):
            d = e["door_id"] and W.door(conn, e["door_id"])
            exits.append({"id": e["id"], "name": e["name"], "tags": e["tags"],
                          "door": d and {"name": d["name"], "locked": bool(d["locked"]), "open": bool(d["is_open"])}})

        def thing(i):
            return {"id": i["id"], "name": i["name"], "type": i["type"], "aliases": i["aliases"]}

        return {
            "time": W.now(conn),
            "you": {**{k: me[k] for k in ("id", "name", "hp", "max_hp", "coins", "status", "wanted_level")},
                    "hidden": bool(me["hidden"])},
            "location": {"id": here, "name": W.location(conn, here)["name"]},
            "exits": exits,
            # ponytail: ids are readable slugs, so they name strangers; switch to opaque ids when disguises land
            "characters": [{"id": c["id"], "name": self._label(observer_id, c["id"]), "status": c["status"],
                            **({"wares": [dict(thing(i), price=i["price"]) for i in W.items_held(conn, c["id"])
                                          if i["price"] is not None]} if c["role"] == "merchant" else {})}
                           for c in W.chars_at(conn, here)
                           if c["id"] != observer_id and W.can_see(conn, observer_id, c)],
            "items": [thing(i) for i in W.items_at(conn, here)],
            "inventory": [thing(i) for i in W.items_held(conn, observer_id)],
            "encounter": self._encounter_view(observer_id),
        }

    def _encounter_view(self, observer_id):
        enc = W.encounter_of(self.conn, observer_id)
        if enc is None:
            return None
        seen = [m["character_id"] for m in W.members(self.conn, enc["id"])
                if W.can_see(self.conn, observer_id, W.char(self.conn, m["character_id"]))]
        turn = enc["turn_id"]
        return {"id": enc["id"], "round": enc["round"], "your_turn": turn == observer_id,
                "turn": self._label(observer_id, turn) if turn in seen else "someone",
                "order": [self._label(observer_id, c) for c in seen]}

    def describe(self, observer_id):
        v = self.view(observer_id)
        out = [f"You are at {v['location']['name']}."]
        if v["characters"]:
            out.append("You see " + ", ".join(
                c["name"] + (" (dead)" if c["status"] == "dead" else "") for c in v["characters"]) + ".")
        if v["items"]:
            out.append("On the ground: " + ", ".join(i["name"] for i in v["items"]) + ".")
        out.append("Exits: " + ", ".join(e["name"] for e in v["exits"]) + ".")
        if v["encounter"]:
            out.append("You are in a fight; " + ("it's your turn." if v["encounter"]["your_turn"]
                                                 else f"{v['encounter']['turn']} acts next."))
        return " ".join(out)
