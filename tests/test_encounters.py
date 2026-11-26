"""Encounters (BRIEF §7): hostile acts start turn mode; initiative order; join by involvement only; free speech;
flee is the only way out; timeout = default action; NPCs take their turns in code; replay stays exact."""
from conftest import counts, new, one, rows, setchar, setstat, val
from engine import fixtures
from engine.config import Config
from engine.engine import Engine


def duel():
    """Ash (fast) vs Wren, both human-controlled, Bob a bystander. Ash attacks: encounter, Ash's initiative wins."""
    eng = new(encounters=True)
    setchar(eng, "wren", is_npc=0)
    setchar(eng, "bob", is_npc=0)
    setstat(eng, "player", dex=40)
    setstat(eng, "wren", dex=1)
    eng.submit("player", "attack wren")
    return eng


def turn(eng):
    return val(eng, "SELECT turn_id FROM encounters WHERE ended IS NULL")


def test_attack_starts_an_encounter_with_logged_initiative():
    eng = duel()
    assert rows(eng, "SELECT character_id, joined_round FROM encounter_members ORDER BY initiative DESC") == [
        ("player", 1), ("wren", 1)]
    assert val(eng, "SELECT COUNT(*) FROM dice_log WHERE purpose='initiative'") == 2
    assert turn(eng) == "player"  # the opening attack came before turn order; initiative decides who's next


def test_out_of_turn_actions_are_refused_and_cost_nothing():
    eng = duel()
    before = counts(eng)
    r = one(eng, "wren", "look")
    assert r.outcome == "impossible" and "not your turn" in r.reason
    assert counts(eng)["events"] == before["events"] and turn(eng) == "player"


def test_turns_rotate_and_rounds_count():
    eng = duel()
    one(eng, "player", "wait")
    assert turn(eng) == "wren"
    one(eng, "wren", "wait")
    assert turn(eng) == "player" and val(eng, "SELECT round FROM encounters") == 2


def test_speaking_is_free():
    eng = duel()
    r = one(eng, "wren", "say stop this!")
    assert r.outcome == "success" and turn(eng) == "player"


def test_bystanders_are_never_locked_in():
    eng = duel()
    assert one(eng, "bob", "go to street").outcome == "success"


def test_fighters_leave_only_by_fleeing():
    eng = duel()
    r = one(eng, "player", "go to street")
    assert r.outcome == "impossible" and "flee" in r.reason
    assert r.alternatives[0]["command"] == "flee to Mill Street"
    setstat(eng, "player", dex=40)
    assert one(eng, "player", "flee to street").outcome == "success"
    assert val(eng, "SELECT ended IS NOT NULL FROM encounters") == 1  # one fighter left: it's over


def test_attacking_a_fighter_joins_next_round_behind_existing_members():
    eng = duel()
    setstat(eng, "bob", dex=40)  # best initiative, but newcomers still act after the original members
    one(eng, "bob", "attack wren")
    assert rows(eng, "SELECT character_id, joined_round FROM encounter_members WHERE character_id='bob'") == [
        ("bob", 2)]
    one(eng, "player", "wait")
    one(eng, "wren", "wait")
    assert turn(eng) == "player"  # round 2: player, wren, then the newcomer
    one(eng, "player", "wait")
    one(eng, "wren", "wait")
    assert turn(eng) == "bob"


def test_death_ends_the_encounter():
    eng = duel()
    setchar(eng, "wren", hp=1)
    setstat(eng, "player", str=40)
    one(eng, "player", "attack wren")
    assert val(eng, "SELECT status FROM characters WHERE id='wren'") == "dead"
    assert val(eng, "SELECT ended IS NOT NULL FROM encounters") == 1
    assert eng.view("player")["encounter"] is None


def test_timeout_takes_the_default_action_and_is_replayable():
    eng = duel()
    eid = val(eng, "SELECT id FROM encounters")
    [r] = eng.timeout(eid)
    assert (r.action.verb, r.outcome) == ("wait", "success") and turn(eng) == "wren"
    assert eng.inputs()[-1][1:] == ("player", '{"text": "(timeout)", "actions": [{"verb": "wait"}]}')


def test_npcs_fight_back_on_their_turn():
    eng = new(encounters=True)
    setstat(eng, "bob", dex=40)  # Bob wins initiative
    results = eng.submit("player", "attack bob")
    assert [(r.action.verb, r.action.target) for r in results][1] == ("attack", "player")
    assert eng.view("player")["encounter"]["your_turn"]


def test_hurt_npcs_flee():
    eng = new(encounters=True)
    setchar(eng, "bob", hp=4)
    setstat(eng, "player", str=12)
    setstat(eng, "bob", dex=40)
    eng.submit("player", "take knife")
    results = eng.submit("player", "attack bob with knife")
    flee = [r for r in results if r.action.verb == "flee"]
    assert flee and flee[0].action.target == "street"


def test_hidden_fighters_stay_hidden_in_the_encounter_view():
    eng = duel()
    one(eng, "player", "wait")
    setstat(eng, "wren", dex=40)
    one(eng, "wren", "sneak")
    enc = eng.view("player")["encounter"]
    assert enc["order"] == ["you"] and "Wren" not in str(enc)


def test_replay_with_npc_turns_is_exact():
    cfg = Config(confirm_irreversible=False)
    eng = Engine.create(seed=5, config=cfg)
    for text in ("take knife", "attack bob with knife", "attack bob with knife", "attack bob with knife"):
        eng.submit("player", text)
    assert val(eng, "SELECT COUNT(*) FROM events WHERE actor_id='bob'") >= 1
    again = Engine.replay(fixtures.MILL_STREET, 5, cfg, eng.inputs())
    for t in ("events", "dice_log", "encounters", "encounter_members", "characters", "items"):
        assert rows(again, f"SELECT * FROM {t} ORDER BY rowid") == rows(eng, f"SELECT * FROM {t} ORDER BY rowid")
