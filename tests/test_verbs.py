"""Every verb: a happy path, and an impossible path with a legible reason / missing list."""
from conftest import holder, new, one, place, rows, setchar, setskill, setstat, val


def impossible(eng, actor, text, reason_part, missing=None):
    r = one(eng, actor, text)
    assert r.outcome == "impossible", (r.outcome, r.reason)
    assert reason_part in r.reason and r.messages == {actor: r.reason}
    assert r.event_id is None and r.rolls == []
    if missing is not None:
        assert r.missing == missing
    return r


def test_move(eng):
    r = one(eng, "player", "go to street")
    assert r.outcome == "success" and val(eng, "SELECT location_id FROM characters WHERE id='player'") == "street"
    assert "Mill Street" in r.messages["player"]
    impossible(eng, "player", "go to tom's house", "oak door is locked", ["unlocked oak door"])
    impossible(eng, "player", "go to narnia", "can't get to 'narnia'", ["narnia"])


def test_move_through_closed_unlocked_door_opens_it(eng):
    place(eng, "player", "street")
    eng.conn.execute("UPDATE doors SET locked=0 WHERE id='player_door'")
    assert one(eng, "player", "go home").outcome == "success"
    assert val(eng, "SELECT is_open FROM doors WHERE id='player_door'") == 1


def test_look(eng):
    r = one(eng, "player", "look around")
    assert r.outcome == "success" and len(r.rolls) == 1 and "Bob" in r.messages["player"]


def test_take(eng):
    r = one(eng, "player", "take knife")
    assert r.outcome == "success" and holder(eng, "knife") == ("player", None)
    assert set(r.messages) == {"player", "bob", "wren"}
    assert r.messages["bob"] == "A stranger in a green cloak takes the knife."
    impossible(eng, "player", "take knife", "already have")
    impossible(eng, "player", "take sword", "don't see 'sword'", ["sword"])


def test_drop(eng):
    eng.submit("player", "take knife")
    r = one(eng, "player", "drop knife")
    assert r.outcome == "success" and holder(eng, "knife") == (None, "tavern")
    assert rows(eng, "SELECT kind, item_id FROM traces") == [("item_left", "knife")]
    impossible(eng, "player", "drop knife", "aren't holding the knife", ["knife"])


def test_give(eng):
    r = one(eng, "player", "give key to bob")
    assert r.outcome == "success" and holder(eng, "player_key") == ("bob", None)
    assert "gives the house key to you" in r.messages["bob"]
    impossible(eng, "player", "give knife to bob", "aren't holding the knife")  # resolved on the table, not held
    impossible(eng, "bob", "give watch to gareth", "don't see 'gareth'", ["gareth"])


def test_buy(eng):
    place(eng, "player", "shop")
    r = one(eng, "player", "buy potion")
    assert r.outcome == "success" and holder(eng, "potion") == ("player", None)
    assert rows(eng, "SELECT coins FROM characters WHERE id IN ('player','herbalist') ORDER BY id") == [(60,), (20,)]
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='potion' ORDER BY id DESC") == "bought"
    assert rows(eng, "SELECT kind, item_id FROM traces") == [("purchase", "potion")]  # purchases are evidence
    setchar(eng, "player", coins=3)
    impossible(eng, "player", "buy poison from mira", "costs 15 coins; you have 3", ["12 more coins"])
    impossible(eng, "player", "buy sword", "doesn't sell 'sword'")
    place(eng, "bob", "shop")
    impossible(eng, "player", "buy watch from bob", "isn't selling", ["merchant"])


def test_attack_hit_and_impossible(eng):
    eng.submit("player", "take knife")
    setstat(eng, "player", str=30)  # +10: can't miss AC 10
    setchar(eng, "bob", hp=100, max_hp=100)
    r = one(eng, "player", "attack bob with knife")
    assert r.outcome == "success" and [x.purpose for x in r.rolls] == ["attack", "damage"]
    dmg = 100 - val(eng, "SELECT hp FROM characters WHERE id='bob'")
    assert dmg == r.rolls[1].total and f"for {dmg} damage" in r.messages["bob"]
    assert "bloodied" in val(eng, "SELECT flags FROM items WHERE id='knife'")
    assert val(eng, "SELECT crime FROM events WHERE id=?", r.event_id) == "assault"
    impossible(eng, "player", "attack tom", "don't see 'tom'", ["tom"])
    impossible(eng, "player", "attack bob with sword", "don't see 'sword'")


def test_unarmed_attack_needs_a_high_roll(eng):
    setchar(eng, "bob", hp=100, max_hp=100)
    r = one(eng, "player", "punch bob")
    attack = r.rolls[0]
    assert attack.modifier == 1 + 1 - 6 and attack.dc == 10  # str +1, athletics 1, unarmed -6 vs AC 10
    assert r.outcome == ("success" if attack.total >= 10 else "failure")


def test_steal(eng):
    setskill(eng, "player", sleight=30)
    r = one(eng, "player", "steal watch from bob")
    assert r.outcome == "success" and holder(eng, "watch") == ("player", None)
    assert "bob" not in r.messages  # the mark only notices a failed attempt
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='watch' ORDER BY id DESC") == "stolen"
    r = one(eng, "player", "steal from bob")
    assert r.outcome == "success" and val(eng, "SELECT coins FROM characters WHERE id='bob'") == 10
    impossible(eng, "player", "steal sword from bob", "doesn't have 'sword'", ["sword"])


def test_failed_steal_is_noticed(eng):
    setskill(eng, "player", sleight=-30)
    r = one(eng, "player", "steal from bob")
    assert r.outcome == "failure" and "notices" in r.reason and str(r.rolls[0]) in r.reason
    assert "tries to steal from you" in r.messages["bob"]


def test_sneak_and_unhide(eng):
    r = one(eng, "player", "sneak")
    assert r.outcome == "success" and val(eng, "SELECT hidden FROM characters WHERE id='player'") == 1
    assert val(eng, "SELECT stealth_total FROM characters WHERE id='player'") == r.rolls[0].total
    impossible(eng, "player", "hide", "already hidden")
    assert one(eng, "player", "unhide").outcome == "success"
    impossible(eng, "player", "unhide", "aren't hiding")


def test_doors_with_key(eng):
    place(eng, "player", "street")
    impossible(eng, "player", "open green door", "is locked", ["unlocked green door"])
    r = one(eng, "player", "unlock door")
    assert r.outcome == "ambiguous" and r.candidates == ["player_door", "tom_door"]
    assert one(eng, "player", "unlock green door").outcome == "success"
    impossible(eng, "player", "unlock green door", "isn't locked")
    assert one(eng, "player", "open green door").outcome == "success"
    impossible(eng, "player", "open green door", "already open")
    assert one(eng, "player", "close green door").outcome == "success"
    impossible(eng, "player", "close green door", "already closed")
    assert one(eng, "player", "lock green door").outcome == "success"
    assert val(eng, "SELECT locked FROM doors WHERE id='player_door'") == 1
    impossible(eng, "player", "lock green door", "already locked")


def test_unlock_without_key_needs_lockpick(eng):
    place(eng, "player", "street")
    impossible(eng, "player", "unlock tom's door", "no way to open it", ["iron key", "lockpick"])
    eng.conn.execute("UPDATE doors SET locked=0 WHERE id='tom_door'")
    impossible(eng, "player", "lock oak door", "need the iron key", ["iron key"])
    eng.conn.execute("UPDATE doors SET locked=1 WHERE id='tom_door'")
    eng.submit("player", "take lockpick")
    setskill(eng, "player", lockpicking=30)
    r = one(eng, "player", "unlock oak door with lockpick")
    assert r.outcome == "success" and r.rolls[0].purpose == "lockpicking" and r.rolls[0].dc == 12


def test_force(eng):
    place(eng, "player", "street")
    setstat(eng, "player", str=40)
    r = one(eng, "player", "force oak door")
    assert r.outcome == "success" and r.rolls[0].dc == 12 + 4
    assert rows(eng, "SELECT locked, is_open FROM doors WHERE id='tom_door'") == [(0, 1)]
    assert rows(eng, "SELECT kind FROM traces") == [("forced_lock",)]
    assert "CRASH" in r.messages["guard"]  # noisy
    impossible(eng, "player", "force oak door", "isn't locked")


def test_talk_and_say(eng):
    r = one(eng, "player", "talk to bob: nice apron")
    assert r.outcome == "success" and r.messages["bob"] == 'A stranger in a green cloak says to you: "nice apron"'
    r = one(eng, "player", "say Hello, I am Ash")
    assert r.messages["wren"] == 'Ash says: "Hello, I am Ash"'  # the introduction itself names them
    assert val(eng, "SELECT recognized FROM perceptions WHERE event_id=? AND observer_id='wren'", r.event_id) == 0
    assert val(eng, "SELECT COUNT(*) FROM knowledge WHERE subject_id='player' AND fact='knows_identity'") == 2
    r = one(eng, "player", "say bye")
    assert r.messages["bob"] == 'Ash says: "bye"'  # recognised from now on
    impossible(eng, "player", "talk to gareth: hi", "don't see 'gareth'")


def test_use(eng):
    place(eng, "player", "shop")
    eng.submit("player", "buy potion")
    setchar(eng, "player", hp=3)
    r = one(eng, "player", "drink potion")
    assert r.outcome == "success" and "recover 5 hp" in r.messages["player"]
    assert val(eng, "SELECT hp FROM characters WHERE id='player'") == 8
    assert rows(eng, "SELECT name, holder_id FROM items WHERE id='potion'") == [("empty vial", "player")]  # never deleted
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='potion' ORDER BY id DESC") == "transformed"
    impossible(eng, "player", "use vial", "can't use the empty vial")
    impossible(eng, "player", "drink healing potion", "don't see 'healing potion'")


def test_flee():
    eng = new()
    setstat(eng, "player", dex=40)
    r = one(eng, "player", "flee to street")
    assert r.outcome == "success" and val(eng, "SELECT location_id FROM characters WHERE id='player'") == "street"
    eng = new(dc_normal=99)
    r = one(eng, "player", "run to street")
    assert r.outcome == "failure" and "can't get away" in r.reason
    assert val(eng, "SELECT location_id FROM characters WHERE id='player'") == "tavern"
    impossible(eng, "player", "flee to narnia", "can't get to")


def test_wait(eng):
    r = one(eng, "player", "wait")
    assert r.outcome == "success" and r.event_id and r.messages["player"] == "You wait."


def test_chain_stops_after_failure(eng):
    results = eng.submit("player", "take sword and attack bob")
    assert [r.outcome for r in results] == ["impossible", "skipped"]
    results = eng.submit("player", "take knife and attack bob")
    assert results[0].outcome == "success" and results[1].outcome in ("success", "failure")
    assert results[1].rolls[0].purpose == "attack"


def test_each_chained_action_costs_a_tick():
    eng = new()
    eng.submit("player", "take knife and drop knife")
    assert eng.view("player")["time"] == 722
    eng = new(chain_actions_cost_separate_turns=False)
    eng.submit("player", "take knife and drop knife")
    assert eng.view("player")["time"] == 721


def test_dead_cannot_act(eng):
    setchar(eng, "player", status="dead")
    impossible(eng, "player", "look", "You are dead")
