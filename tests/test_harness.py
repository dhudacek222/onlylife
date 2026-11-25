"""M2 harness: escalation, confirmations, replay of AI decisions, per-observer scene + narration. Offline."""
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from conftest import counts, holder, new, rows, setskill
from engine.actions import Action
from engine.claude import ClaudeDecision, ClaudeNarrator
from engine.engine import Engine
from engine import fixtures
from engine.harness import Decision, Escalating, Harness, RuleDecision, scene_for


class Fixed:
    """A fake DecisionModel that records what it was shown."""

    def __init__(self, *actions, source="fake"):
        self.actions, self.source, self.seen = list(actions), source, []

    def decide(self, text, scene):
        self.seen.append((text, scene))
        return Decision([Action(**vars(a)) for a in self.actions], self.source, "" if self.actions else "Hm?")


class Boom:
    def decide(self, text, scene):
        raise TimeoutError("api down")


def fake_client(payload, stop_reason="end_turn"):
    calls = []

    def create(**kw):
        calls.append(kw)
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))), calls


def act(verb, **kw):
    base = dict(target=None, item=None, text=None, want_item=None, coins=0, want_coins=0)
    base.update(kw)
    return {"verb": verb, **base}


# ---------------------------------------------------------------- pipeline

def test_rule_tier_executes_and_logs_structured_actions(eng):
    h = Harness(eng)
    t = h.handle("player", "take knife")
    assert t.status == "done" and t.source == "rules" and holder(eng, "knife") == ("player", None)
    kind, actor, payload = eng.inputs()[-1]
    assert (kind, actor) == ("actions", "player") and json.loads(payload)[0]["verb"] == "take"


def test_unclear_input_costs_nothing(eng):
    before = counts(eng)
    t = Harness(eng).handle("player", "dance wildly")
    assert t.status == "unclear" and "understand" in t.prompt
    assert counts(eng) == before


def test_escalates_only_when_the_cheap_tier_fails(eng):
    llm = Fixed(Action("take", item="knife"))
    h = Harness(eng, Escalating(RuleDecision(), llm))
    assert h.handle("player", "look").source == "rules" and llm.seen == []
    t = h.handle("player", "yoink that pointy thing on the table")
    assert t.status == "done" and t.source == "fake" and holder(eng, "knife") == ("player", None)


def test_a_failing_model_never_breaks_the_turn(eng):
    t = Harness(eng, Escalating(RuleDecision(), Boom())).handle("player", "yoink it")
    assert t.status == "unclear" and "TimeoutError" in t.prompt


def test_replay_does_not_ask_the_model_again():
    eng = Engine.create(seed=5)
    h = Harness(eng, Escalating(RuleDecision(), Fixed(Action("take", item="knife"), Action("attack", target="c1"))),
                confirm_irreversible=False)
    h.handle("player", "grab the blade and go for the bald guy")
    h.handle("player", "look")
    again = Engine.replay(fixtures.MILL_STREET, 5, eng.config, eng.inputs())  # no model anywhere
    for table in ("events", "dice_log", "perceptions", "knowledge", "items", "characters"):
        assert rows(again, f"SELECT * FROM {table} ORDER BY rowid") == rows(eng, f"SELECT * FROM {table} ORDER BY rowid")


# ---------------------------------------------------------------- confirmations

def test_irreversible_actions_wait_for_confirmation(eng):
    h = Harness(eng)
    before = counts(eng)
    t = h.handle("player", "give key to bob")
    assert t.status == "confirm" and "can't be undone" in t.prompt
    assert counts(eng) == before  # nothing happened yet
    assert h.confirm("player").status == "done" and holder(eng, "player_key") == ("bob", None)
    assert h.confirm("player").status == "unclear"  # one confirmation, one execution


def test_cancel_and_npcs(eng):
    h = Harness(eng)
    h.handle("player", "give key to bob")
    assert h.cancel("player").status == "cancelled" and h.confirm("player").status == "unclear"
    assert holder(eng, "player_key") == ("player", None)
    assert h.handle("bob", "give watch to wren").status == "done"  # NPC brains don't get asked


# ---------------------------------------------------------------- what models may see

def test_scene_hides_slug_ids_and_hidden_characters(eng):
    setskill(eng, "wren", stealth=40)
    eng.submit("wren", "hide")
    model = Fixed()
    Harness(eng, model).handle("player", "whatever")
    scene = model.seen[0][1]
    assert [c["ref"] for c in scene["characters"]] == ["c1"]  # bob only; wren is hidden
    assert "wren" not in json.dumps(scene).lower()
    assert "player" not in json.dumps(scene) and "bob\"" not in json.dumps(scene)  # no slug ids


def test_refs_map_back_to_characters(eng):
    eng.submit("player", "say hi")  # nothing special; bob is c1 in the tavern
    _, refs = scene_for(eng.view("player"))
    assert refs == {"c1": "bob", "c2": "wren"}
    t = Harness(eng, Fixed(Action("talk", target="c2", text="hello"))).handle("player", "greet the hooded one")
    assert t.status == "done" and 'says to you: "hello"' in t.messages["wren"]


def test_narration_is_per_player_and_falls_back(eng):
    shown = []

    class Spy:
        def narrate(self, line, scene):
            shown.append((line, scene["location"]))
            return "PROSE: " + line

    eng.conn.execute("UPDATE characters SET is_npc=0 WHERE id='wren'")  # a second player
    t = Harness(eng, narrator=Spy()).handle("player", "take knife")
    assert t.messages["player"].startswith("PROSE") and t.messages["wren"].startswith("PROSE")
    assert not t.messages["bob"].startswith("PROSE")  # NPCs get engine lines
    assert {line for line, _ in shown} == {"You take the knife.", "A stranger in a green cloak takes the knife."}

    class Broken:
        def narrate(self, line, scene):
            raise RuntimeError

    t = Harness(eng, narrator=Broken()).handle("player", "drop knife")
    assert t.messages["player"] == "You drop the knife."


# ---------------------------------------------------------------- Claude adapter (fake client)

def test_claude_decision_request_and_validation(eng):
    client, calls = fake_client({"actions": [act("steal", target="c1")], "clarify": ""})
    d = ClaudeDecision(client=client).decide("rob the bald guy", {"characters": []})
    assert [(a.verb, a.target) for a in d.actions] == [("steal", "c1")] and d.source == "claude"
    kw = calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_config"]["format"]["type"] == "json_schema"
    sent = json.loads(kw["messages"][0]["content"])
    assert sent == {"scene": {"characters": []}, "player_text": "rob the bald guy"}


@pytest.mark.parametrize("payload, stop", [
    ({"actions": [act("teleport")], "clarify": ""}, "end_turn"),  # verb outside the whitelist
    ({"actions": [act("offer", target="c1", coins=-50)], "clarify": ""}, "end_turn"),  # negative coins
    ({"actions": [{**act("take", item="knife"), "grant_coins": 999}], "clarify": ""}, "end_turn"),  # extra field
    ("not json", "end_turn"),
    ({"actions": [], "clarify": ""}, "refusal"),
])
def test_bad_model_output_is_rejected_not_executed(eng, payload, stop):
    client, _ = fake_client(payload, stop)
    before = counts(eng)
    t = Harness(eng, Escalating(RuleDecision(), ClaudeDecision(client=client))).handle("player", "do the thing")
    assert t.status == "unclear" and counts(eng) == before


def test_claude_clarify_and_narrator(eng):
    client, _ = fake_client({"actions": [], "clarify": "Which way, the street?"})
    assert Harness(eng, ClaudeDecision(client=client)).handle("player", "go").prompt == "Which way, the street?"
    client, calls = fake_client("You snatch the knife from the table.")
    assert ClaudeNarrator(client=client).narrate("You take the knife.", {}) == "You snatch the knife from the table."
    assert "format" not in calls[0]["output_config"]


def test_ai_modules_never_touch_world():
    root = pathlib.Path(__file__).parent.parent / "engine"
    for name in ("harness.py", "claude.py"):
        src = (root / name).read_text()
        assert not re.search(r"import\s+world|from\s+engine\s+import\s+[^\n]*\bworld\b|engine\.world", src), name


def test_action_from_dict_is_strict():
    assert Action.from_dict(act("look")).verb == "look"
    for bad in ({"verb": "fly"}, {**act("look"), "hp": 1}, act("say", text=5), act("offer", coins=True)):
        with pytest.raises(ValueError):
            Action.from_dict(bad)


def test_confirmation_prompt_never_names_a_stranger(eng):
    eng.conn.execute("INSERT INTO characters (id, name, is_npc, location_id, status, hp, max_hp, stats, face_shape, "
                     "appearance) VALUES ('vex', 'Vex', 1, 'tavern', 'online', 10, 10, '{}', 'sharp', "
                     "'{\"clothes\": \"a red mask\"}')")  # nobody has been introduced to Vex
    _, refs = scene_for(eng.view("player"))
    ref = next(r for r, cid in refs.items() if cid == "vex")
    h = Harness(eng, Fixed(Action("give", item="key", target=ref)))
    t = h.handle("player", "hand the key to the masked one")
    assert t.status == "confirm" and "vex" not in t.prompt.lower()
    assert "stranger in a red mask" in t.prompt
    assert h.confirm("player").status == "done" and holder(eng, "player_key") == ("vex", None)
