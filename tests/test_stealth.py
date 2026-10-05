"""Reference resolution and per-observer information: hidden characters never leak."""
from conftest import holder, new, one, place, rows, setchar, setskill, val


# ---------------------------------------------------------------- resolution

def test_inventory_resolves_before_location(eng):
    eng.conn.execute("INSERT INTO items (id, type, name, holder_id) VALUES ('knife_2', 'weapon', 'knife', 'player')")
    r = one(eng, "player", "drop knife")
    assert r.outcome == "success" and r.event_id
    assert holder(eng, "knife_2") == (None, "tavern")  # the held one, not the one on the table


def test_ambiguity_offers_candidates(eng):
    eng.conn.execute("INSERT INTO items (id, type, name, aliases, location_id) "
                     "VALUES ('knife_2', 'weapon', 'rusty knife', '[\"blade\"]', 'tavern')")
    r = one(eng, "player", "take blade")
    assert r.outcome == "ambiguous" and r.candidates == ["knife", "knife_2"] and r.event_id is None
    assert one(eng, "player", "take knife_2").outcome == "success"  # an exact id always wins
    place(eng, "player", "street")
    r = one(eng, "player", "go to house")
    assert r.outcome == "ambiguous" and r.candidates == ["player_house", "tom_house"]


def test_hidden_character_is_unresolvable(eng):
    setskill(eng, "wren", stealth=40)
    eng.submit("wren", "hide")
    hidden = one(eng, "player", "attack wren")
    absent = one(eng, "player", "attack zed")
    assert hidden.outcome == absent.outcome == "impossible"
    assert hidden.reason.replace("wren", "X") == absent.reason.replace("zed", "X")  # indistinguishable
    assert one(eng, "player", "give key to wren").reason == "You don't see 'wren' here."
    assert one(eng, "player", "talk to wren: hi").reason == "You don't see 'wren' here."


# ---------------------------------------------------------------- stealth vs each observer

def stealthy_player_with_guard_in_tavern(eng):
    place(eng, "guard", "tavern")
    setskill(eng, "guard", perception=18)  # passive 30
    setskill(eng, "player", stealth=7, sleight=30)  # stealth mod 7+2+1+2-2(guard) = 10 -> totals 11..30
    r = one(eng, "player", "sneak")
    assert 11 <= r.rolls[0].total <= 30  # > bob's passive 10, <= guard's 30
    return r


def test_guard_detects_bob_does_not(eng):
    r = stealthy_player_with_guard_in_tavern(eng)
    aware = rows(eng, "SELECT observer_id FROM knowledge WHERE subject_id='player' AND fact='aware_of'")
    assert aware == [("guard",)]
    assert set(r.messages) == {"player", "guard"}
    assert "player" in [c["id"] for c in eng.view("guard")["characters"]]
    assert "player" not in [c["id"] for c in eng.view("bob")["characters"]]

    r = one(eng, "player", "steal watch from bob")
    assert r.outcome == "success" and set(r.messages) == {"player", "guard"}
    assert "steals the pocket watch from Bob" in r.messages["guard"]
    det = dict(rows(eng, "SELECT observer_id, detected FROM perceptions WHERE event_id=?", r.event_id))
    assert det == {"player": 1, "guard": 1, "bob": 0, "wren": 0}
    assert val(eng, "SELECT wanted_level FROM characters WHERE id='player'") == 1  # the guard saw it


def test_hidden_thief_leaks_nothing_to_unaware_witnesses(eng):
    setskill(eng, "player", stealth=40, sleight=40)
    before = val(eng, "SELECT COALESCE(MAX(id), 0) FROM knowledge")
    sneak = one(eng, "player", "sneak")
    steal = one(eng, "player", "steal watch from bob")
    assert steal.outcome == "success" and holder(eng, "watch") == ("player", None)

    for r in (sneak, steal):
        assert set(r.messages) == {"player"}  # no text for bob or wren
        assert rows(eng, "SELECT observer_id FROM perceptions WHERE event_id=? AND detected=1", r.event_id) == [
            ("player",)]
    assert rows(eng, "SELECT * FROM knowledge WHERE id>? AND observer_id IN ('bob','wren')", before) == []
    for observer in ("bob", "wren"):
        v = eng.view(observer)
        assert "player" not in [c["id"] for c in v["characters"]]
        assert "Ash" not in str(v) and "green cloak" not in str(v)
    assert val(eng, "SELECT wanted_level FROM characters WHERE id='player'") == 0  # unwitnessed


def test_noticing_requires_awareness_newer_than_hiding(eng):
    setskill(eng, "player", stealth=40)
    setskill(eng, "bob", perception=60)
    eng.submit("player", "sneak")  # bob (passive 70) notices
    assert "player" in [c["id"] for c in eng.view("bob")["characters"]]
    eng.submit("player", "unhide")
    setskill(eng, "bob", perception=0)
    eng.submit("player", "sneak")  # old awareness is stale now
    assert "player" not in [c["id"] for c in eng.view("bob")["characters"]]


def test_look_finds_hidden_people(eng):
    setskill(eng, "wren", stealth=-30)  # stealth_total will be very low
    setskill(eng, "player", perception=-60)  # but our passive is lower still
    eng.submit("wren", "hide")
    assert "wren" not in [c["id"] for c in eng.view("player")["characters"]]
    setskill(eng, "player", perception=40)
    r = one(eng, "player", "look")
    assert "You spot Wren!" in r.messages["player"]
    assert "wren" in [c["id"] for c in eng.view("player")["characters"]]


def test_look_always_rolls_even_with_nobody_hidden(eng):
    assert len(one(eng, "player", "look").rolls) == 1  # roll count must not reveal hidden presence


def test_hidden_attacker_gets_advantage_and_is_revealed(eng):
    setskill(eng, "player", stealth=40)
    setchar(eng, "bob", hp=100, max_hp=100)
    eng.submit("player", "sneak")
    r = one(eng, "player", "attack bob")
    assert r.rolls[0].mode == "advantage"
    assert val(eng, "SELECT hidden FROM characters WHERE id='player'") == 0
    assert set(r.messages) == {"player", "bob", "wren"}  # aggression ends hiding


def test_sneaking_into_a_room_rolls_against_the_people_there(eng):
    place(eng, "player", "street")
    setskill(eng, "player", stealth=40)
    eng.submit("player", "hide")
    r = one(eng, "player", "go to tavern")
    assert r.rolls[0].purpose == "stealth" and set(r.messages) == {"player"}
    assert "player" not in [c["id"] for c in eng.view("bob")["characters"]]


def test_heavy_armor_gives_stealth_disadvantage(eng):
    eng.conn.execute("UPDATE items SET location_id=NULL, holder_id='player' WHERE id='plate'")
    assert one(eng, "player", "sneak").rolls[0].mode == "disadvantage"
