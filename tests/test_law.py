"""Crime, wanted level, evidence, repeat pressure and death."""
import json

from conftest import holder, new, one, place, rows, setchar, setskill, setstat, val


def wanted(eng, who="player"):
    return val(eng, "SELECT wanted_level FROM characters WHERE id=?", who)


def test_repeat_attempts_raise_the_dc(eng):
    setskill(eng, "player", sleight=-30)  # keep failing; the DC still climbs
    dcs = [one(eng, "player", "steal from bob").rolls[0].dc for _ in range(3)]
    assert dcs == [10, 12, 14]
    eng.advance(1440)  # pressure fades after repeat_window_ticks
    assert one(eng, "player", "steal from bob").rolls[0].dc == 10
    assert one(eng, "player", "steal from wren").rolls[0].dc == 9  # per target


def test_wanted_only_when_witnessed(eng):
    setskill(eng, "player", stealth=40, sleight=40)
    eng.submit("player", "hide")
    eng.submit("player", "steal from bob")
    assert wanted(eng) == 0
    eng.submit("player", "unhide")
    eng.submit("player", "steal from bob")  # in plain sight: wren sees it
    assert wanted(eng) == 1


def test_trespass_seen_from_the_street(eng):
    place(eng, "player", "street")
    eng.conn.execute("UPDATE doors SET locked=0 WHERE id='tom_door'")
    r = one(eng, "player", "go to tom's house")
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) == "trespass"
    assert wanted(eng) == 1  # gareth and tom watched from the street
    assert "goes to Tom's House" in r.messages["guard"]


def test_own_house_is_not_trespass(eng):
    place(eng, "player", "street")
    r = eng.submit("player", "unlock green door and go home")[1]
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) is None and wanted(eng) == 0


def test_burglary_after_picking_the_lock(eng):
    place(eng, "player", "street")
    eng.submit("player", "take lockpick")
    setskill(eng, "player", lockpicking=30)
    eng.submit("player", "unlock oak door")
    r = one(eng, "player", "go to tom's house")
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) == "burglary"
    assert wanted(eng) == 2
    r = one(eng, "player", "take candlestick")
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) == "theft"
    assert wanted(eng) == 2  # nobody inside saw that


def test_evidence_shows_witnesses_traces_and_the_roll(eng):
    eng.submit("player", "take knife")
    setstat(eng, "player", str=30)
    setchar(eng, "bob", hp=100, max_hp=100)
    r = one(eng, "player", "attack bob")
    ev = rows(eng, "SELECT kind, subject_id, detected, roll_id FROM evidence WHERE event_id=? ORDER BY kind, subject_id",
              r.event_id)
    assert ev == [("bloodied_item", "knife", None, None),
                  ("witness", "bob", 1, r.rolls[0].id),
                  ("witness", "player", 1, r.rolls[0].id),
                  ("witness", "wren", 1, r.rolls[0].id)]
    roll = rows(eng, "SELECT purpose, total, dc, success FROM dice_log WHERE id=?", r.rolls[0].id)
    assert roll == [("attack", r.rolls[0].total, 10, 1)]
    seen = json.loads(val(eng, "SELECT appearance_seen FROM perceptions WHERE event_id=? AND observer_id='wren'",
                          r.event_id))
    assert seen == {"face_shape": "angular", "hair": "short black hair", "clothes": "a green cloak"}
    assert wanted(eng) == 2


def test_failure_is_legible(eng):
    setskill(eng, "player", sleight=-30)
    r = one(eng, "player", "steal watch from bob")
    assert r.outcome == "failure"
    assert r.rolls[0].success is False and str(r.rolls[0]) in r.reason and "vs DC 10" in r.reason
    assert r.reason in r.messages["player"]


def kill_bob(eng):
    eng.submit("player", "take knife")
    setstat(eng, "player", str=30)  # can't miss, d4+10 >= bob's 10 hp
    r = one(eng, "player", "kill bob")
    assert r.outcome == "success" and "Bob dies." in r.messages["player"] and "You die." in r.messages["bob"]
    assert val(eng, "SELECT status FROM characters WHERE id='bob'") == "dead"
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) == "murder"
    assert ("body",) in rows(eng, "SELECT kind FROM traces WHERE event_id=?", r.event_id)
    assert wanted(eng) == 4  # wren saw it; the dead victim doesn't count
    assert one(eng, "bob", "look").reason == "You are dead."
    return r


def test_death_penalty_mode_drops_items_at_the_spot():
    eng = new()
    kill_bob(eng)
    assert val(eng, "SELECT COUNT(*) FROM characters WHERE id='bob'") == 1  # the character persists
    assert holder(eng, "watch") == (None, "tavern")
    r = one(eng, "player", "take watch")
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='watch' ORDER BY id DESC") == "taken"


def test_permadeath_leaves_items_on_the_body():
    eng = new(death_mode="permadeath")
    kill_bob(eng)
    assert holder(eng, "watch") == ("bob", None)
    assert one(eng, "player", "take watch from bob").outcome == "success"
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='watch' ORDER BY id DESC") == "looted"
    assert one(eng, "player", "attack bob").reason == "Bob is dead."
