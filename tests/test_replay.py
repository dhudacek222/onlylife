from engine import fixtures
from engine.config import Config
from engine.engine import Engine
from conftest import rows

SESSION = [
    ("player", "look"),
    ("player", "take knife and attack bob"),
    ("player", "dance"),  # unparsed: not even logged
    ("wren", "hide"),
    ("player", "steal from bob"),
    ("player", "go to street"),
    ("player", "sneak"),
    ("player", "unlock door"),  # ambiguous
    ("player", "unlock green door and go home and take plate"),
    ("bob", "say Has anyone seen my knife?"),
]


def test_replay_reproduces_events_and_dice():
    cfg = Config()
    eng = Engine.create(seed=99, config=cfg, world=fixtures.MILL_STREET)
    for i, (actor, text) in enumerate(SESSION):
        eng.submit(actor, text)
        if i == 4:
            eng.advance(600)  # into the night
    again = Engine.replay(fixtures.MILL_STREET, 99, cfg, eng.inputs())
    for table in ("events", "dice_log", "perceptions", "knowledge", "provenance", "traces", "characters", "items"):
        assert rows(again, f"SELECT * FROM {table} ORDER BY rowid") == rows(eng, f"SELECT * FROM {table} ORDER BY rowid")
    assert len(rows(eng, "SELECT * FROM dice_log")) >= 5
    assert ("advance", None, "600") in eng.inputs()


def test_different_seed_diverges():
    a = Engine.create(seed=1)
    b = Engine.create(seed=2)
    for e in (a, b):
        for _ in range(5):
            e.submit("player", "look")
    assert rows(a, "SELECT raw FROM dice_log") != rows(b, "SELECT raw FROM dice_log")
