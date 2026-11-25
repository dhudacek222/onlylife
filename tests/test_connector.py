"""The game as a tool server for a player's own AI (MCP). Offline: the MCP wrapper itself is skipped without `mcp`."""
import json
import pathlib
import re
import threading

import pytest

from conftest import counts, holder, place, setchar, setskill, val
from engine.connector import Game
from engine.engine import Engine


def two_players(eng):
    setchar(eng, "wren", is_npc=0)
    return Game(eng)


def act(verb, **kw):
    return {"verb": verb, **kw}


def test_look_shows_only_this_players_world(eng):
    setskill(eng, "wren", stealth=40)
    eng.submit("wren", "hide")
    g = Game(eng)
    out = g.look("player")
    text = json.dumps(out)
    assert [c["name"] for c in out["scene"]["characters"]] == ["Bob"]  # hidden wren is absent
    assert '"bob"' not in text and "wren" not in text.lower()  # no slug ids, no hidden names


def test_act_and_deliver_to_other_players_only(eng):
    g = two_players(eng)
    g.look("player")
    out = g.act("player", [act("take", item="knife")])
    assert out["status"] == "done" and out["you_perceive"] == ["You take the knife."]
    assert holder(eng, "knife") == ("player", None)
    assert g.look("wren")["perceived"] == ["A stranger in a green cloak takes the knife."]
    assert g.look("wren")["perceived"] == []  # delivered once
    assert "bob" not in g.inbox  # NPCs have no inbox


def test_refs_stay_stable_when_someone_arrives(eng):
    g = Game(eng)
    refs = {c["name"]: c["ref"] for c in g.look("player")["scene"]["characters"]}
    place(eng, "tom", "tavern")  # sorts between bob and wren: per-call numbering would shift wren
    refs2 = {c["name"]: c["ref"] for c in g.look("player")["scene"]["characters"]}
    assert refs2["Wren"] == refs["Wren"] and refs2["Bob"] == refs["Bob"]
    out = g.act("player", [act("talk", target=refs["Wren"], text="hi")])
    assert out["status"] == "done" and "to Wren" in out["you_perceive"][0]


def test_irreversible_needs_confirmation(eng):
    g = Game(eng)
    before = counts(eng)
    out = g.act("player", [act("give", item="key", target="bob")])
    assert out["status"] == "needs_confirmation" and out["irreversible"] == ["give"]
    assert counts(eng) == before
    assert g.act("player", [act("give", item="key", target="bob")], confirm=True)["status"] == "done"
    assert holder(eng, "player_key") == ("bob", None)


@pytest.mark.parametrize("bad", [
    [act("teleport", target="castle")],
    [act("offer", target="bob", coins=-100)],
    [act("take", item="knife", grant_coins=1000)],
    ["take knife"],
    [],
])
def test_invalid_ai_input_changes_nothing(eng, bad):
    before = counts(eng)
    assert Game(eng).act("player", bad, confirm=True)["status"] == "invalid"
    assert counts(eng) == before


def test_nulls_mean_defaults(eng):
    out = Game(eng).act("player", [act("take", item="knife", target=None, coins=None, text=None)])
    assert out["status"] == "done"


def test_only_player_characters_can_be_driven(eng):
    with pytest.raises(PermissionError):
        Game(eng).look("bob")
    with pytest.raises(PermissionError):
        Game(eng).act("guard", [act("attack", target="player")], confirm=True)


def test_world_persists_across_server_restarts(tmp_path):
    path = str(tmp_path / "world.db")
    Game(Engine.create(path, seed=3)).act("player", [act("take", item="knife")])
    again = Game(Engine.open(path))
    assert "knife" in again.look("player")["scene"]["inventory"]


def test_concurrent_calls_are_serialized(tmp_path):
    eng = Engine.create(str(tmp_path / "w.db"), seed=1)
    g = Game(eng)
    errors = []

    def worker():
        try:
            for _ in range(10):
                g.act("player", [act("wait")])
        except Exception as e:  # pragma: no cover - the assertion below reports it
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and val(eng, "SELECT COUNT(*) FROM events") == 80


def test_connector_modules_never_touch_world():
    root = pathlib.Path(__file__).parent.parent / "engine"
    for name in ("connector.py", "mcp_server.py"):
        src = (root / name).read_text()
        assert not re.search(r"import\s+world|from\s+engine\s+import\s+[^\n]*\bworld\b|engine\.world", src), name


def test_mcp_server_exposes_two_tools(eng):
    pytest.importorskip("mcp")
    import asyncio

    from engine.mcp_server import build
    server = build(Game(eng), "player")
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == ["act", "look"]
    res = asyncio.run(server.call_tool("act", {"actions": [{"verb": "take", "item": "knife"}]}))
    assert "You take the knife." in json.dumps(res.model_dump(), ensure_ascii=False)
    assert holder(eng, "knife") == ("player", None)
