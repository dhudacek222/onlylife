"""M2 Action Harness: text -> DecisionModel -> confirm -> Engine -> Narrator, per observer.

Boundaries (BRIEF §2): nothing here imports `world`. Models only ever see `Engine.view()` of the acting
player (what that character perceives), may only answer with `Action`s from the fixed schema, and
narration is generated per observer from that observer's own engine message + view."""
from dataclasses import dataclass, field
from typing import Protocol

from engine import parser
from engine.actions import VERBS, Action


@dataclass
class Decision:
    actions: list
    source: str  # which model produced it ("rules", "claude", ...)
    clarify: str = ""  # shown to the player when actions is empty


class DecisionModel(Protocol):
    def decide(self, text: str, scene: dict) -> Decision: ...


class Narrator(Protocol):
    def narrate(self, line: str, scene: dict) -> str: ...


# ---------------------------------------------------------------- scene: what a model may know

def scene_for(view):
    """The acting player's view with character ids replaced by opaque refs (c1, c2, ...).
    Slug ids would name strangers the player has never been introduced to."""
    refs, chars = {}, []
    for i, c in enumerate(view["characters"], 1):
        refs[f"c{i}"] = c["id"]
        chars.append({"ref": f"c{i}", "name": c["name"], "status": c["status"]})
    scene = {
        "location": view["location"]["name"],
        "exits": [e["name"] + (f" (through the {e['door']['name']})" if e["door"] else "") for e in view["exits"]],
        "characters": chars,
        "items_here": [i["name"] for i in view["items"]],
        "inventory": [i["name"] for i in view["inventory"]],
        "coins": view["you"]["coins"],
        "hidden": view["you"]["hidden"],
    }
    return scene, refs


def unref(actions, refs):
    for a in actions:
        if a.target in refs:
            a.target = refs[a.target]
    return actions


# ---------------------------------------------------------------- decision models

class RuleDecision:
    """The free, deterministic first tier: the M1 parser."""

    def decide(self, text, scene):
        actions = parser.parse(text)
        return Decision(actions, "rules", "" if actions else f"I don't understand '{text}'.")


class Escalating:
    """Try each model in order; the first one that produces actions wins (BRIEF §5: cheap first, LLM on failure)."""

    def __init__(self, *models):
        self.models = models

    def decide(self, text, scene):
        d = Decision([], "none", f"I don't understand '{text}'.")
        for m in self.models:
            try:
                d = m.decide(text, scene)
            except Exception as e:  # a model outage must never take the game down; the next tier answers
                d = Decision([], type(m).__name__, f"I couldn't work out what you mean ({type(e).__name__}).")
            if d.actions:
                return d
        return d


class TemplateNarrator:
    def narrate(self, line, scene):
        return line


# ---------------------------------------------------------------- the harness

@dataclass
class Turn:
    status: str  # "done" | "confirm" | "unclear" | "cancelled"
    prompt: str = ""  # confirm question or clarification, for the actor
    results: list = field(default_factory=list)
    messages: dict = field(default_factory=dict)  # observer_id -> narrated text
    source: str = ""


class Harness:
    def __init__(self, engine, decision=None, narrator=None, confirm_irreversible=True):
        self.engine = engine
        self.decision = decision or RuleDecision()
        self.narrator = narrator or TemplateNarrator()
        self.confirm_irreversible = confirm_irreversible
        self.pending = {}  # actor_id -> list[Action] awaiting confirmation

    def handle(self, actor_id, text):
        """One player input. Unclear input costs nothing (no input row, no clock)."""
        scene, refs = scene_for(self.engine.view(actor_id))
        d = self.decision.decide(text, scene)
        if not d.actions:
            return Turn("unclear", d.clarify or f"I don't understand '{text}'.", source=d.source)
        for a in d.actions:
            a.raw = a.raw or text
        labels = {c["ref"]: c["name"] for c in scene["characters"]}
        what = "; ".join(_describe(a, labels) for a in d.actions)  # labels, before refs become real ids
        actions = unref(d.actions, refs)
        risky = [a for a in actions if VERBS[a.verb].irreversible]
        if self.confirm_irreversible and risky and self.engine.is_player(actor_id):
            self.pending[actor_id] = actions
            # ponytail: no risk estimate yet (OPEN DECISION 1, risk_display); needs a roll-free DC preview in rules
            return Turn("confirm", f"You are about to: {what}. This can't be undone. Go ahead? (yes/no)",
                        source=d.source)
        return self._execute(actor_id, actions, d.source)

    def confirm(self, actor_id):
        actions = self.pending.pop(actor_id, None)
        if not actions:
            return Turn("unclear", "There is nothing to confirm.")
        return self._execute(actor_id, actions, "confirmed")

    def cancel(self, actor_id):
        self.pending.pop(actor_id, None)
        return Turn("cancelled", "You think better of it.")

    def _execute(self, actor_id, actions, source):
        results = self.engine.submit_actions(actor_id, actions)
        lines = {}
        for r in results:
            for o, m in r.messages.items():
                lines.setdefault(o, []).append(m)
        messages = {}
        for o, ls in lines.items():
            line = " ".join(ls)
            # narration sees only this observer's own engine lines and view; NPCs get the plain lines
            messages[o] = self._narrate(line, o) if self.engine.is_player(o) else line
        return Turn("done", results=results, messages=messages, source=source)

    def _narrate(self, line, observer_id):
        try:
            return self.narrator.narrate(line, scene_for(self.engine.view(observer_id))[0]) or line
        except Exception:  # narration is flavour; the engine's line is always a correct fallback
            return line


def _describe(a, labels):
    target = labels.get(a.target, a.target)
    return " ".join(p for p in (a.verb, a.item, target and f"-> {target}") if p)
