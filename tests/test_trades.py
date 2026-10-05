"""Player-to-player trades: atomic, re-validated on accept, dupe-proof."""
import pytest

from conftest import holder, one, place, rows, val


def coins(eng, who):
    return val(eng, "SELECT coins FROM characters WHERE id=?", who)


@pytest.fixture
def offered(eng):
    eng.submit("player", "take knife")
    r = one(eng, "player", "offer knife to bob for 5 coins")
    assert r.outcome == "success" and "trade #1" in r.messages["bob"]
    return eng


def test_accept_swaps_atomically(offered):
    eng = offered
    r = one(eng, "bob", "accept")
    assert r.outcome == "success"
    assert holder(eng, "knife") == ("bob", None)
    assert (coins(eng, "player"), coins(eng, "bob")) == (35, 15)
    assert val(eng, "SELECT status FROM trades WHERE id=1") == "accepted"
    assert val(eng, "SELECT kind FROM provenance WHERE item_id='knife' ORDER BY id DESC") == "traded"


def test_item_for_item(eng):
    eng.submit("player", "take knife")
    one(eng, "player", "offer knife to bob for pocket watch")
    assert one(eng, "bob", "accept offer from ash").outcome == "success"
    assert holder(eng, "knife") == ("bob", None) and holder(eng, "watch") == ("player", None)


@pytest.mark.parametrize("move_it", ["drop knife", "give knife to wren"])
def test_dupe_exploit_offer_then_move_item(offered, move_it):
    eng = offered
    assert one(eng, "player", move_it).outcome == "success"
    where = holder(eng, "knife")
    r = one(eng, "bob", "accept 1")
    assert r.outcome == "failure" and "no longer has the knife" in r.reason and r.missing
    assert holder(eng, "knife") == where  # nothing moved
    assert (coins(eng, "player"), coins(eng, "bob")) == (30, 20)
    assert val(eng, "SELECT status FROM trades WHERE id=1") == "failed"
    assert one(eng, "bob", "accept 1").outcome == "impossible"  # failed is final


def test_double_accept(offered):
    eng = offered
    assert one(eng, "bob", "accept").outcome == "success"
    r = one(eng, "bob", "accept 1")
    assert r.outcome == "impossible" and "already accepted" in r.reason
    assert (coins(eng, "player"), coins(eng, "bob")) == (35, 15)
    assert val(eng, "SELECT COUNT(*) FROM provenance WHERE kind='traded'") == 1


def test_accept_by_wrong_party(offered):
    eng = offered
    r = one(eng, "wren", "accept 1")
    assert r.outcome == "impossible" and "isn't addressed to you" in r.reason
    assert one(eng, "player", "accept 1").outcome == "impossible"  # can't accept your own offer
    assert one(eng, "wren", "accept").outcome == "impossible"  # nothing addressed to wren
    assert holder(eng, "knife") == ("player", None) and val(eng, "SELECT status FROM trades") == "pending"


def test_coins_never_go_negative(eng):
    r = one(eng, "player", "offer 40 coins to bob for pocket watch")
    assert r.outcome == "impossible" and r.missing == ["10 more coins"]
    one(eng, "player", "offer 30 coins to bob for pocket watch")
    place(eng, "player", "shop")
    eng.submit("player", "buy potion")  # spend coins after offering
    place(eng, "player", "tavern")
    r = one(eng, "bob", "accept")
    assert r.outcome == "failure" and "doesn't have 30 coins" in r.reason
    assert (coins(eng, "player"), coins(eng, "bob")) == (20, 20) and holder(eng, "watch") == ("bob", None)
    assert rows(eng, "SELECT COUNT(*) FROM characters WHERE coins < 0") == [(0,)]


def test_accept_fails_if_offerer_left(offered):
    eng = offered
    eng.submit("player", "go to street")
    r = one(eng, "bob", "accept")
    assert r.outcome == "failure" and "not here" in r.reason and holder(eng, "knife") == ("player", None)


def test_decline(offered):
    eng = offered
    r = one(eng, "bob", "decline")
    assert r.outcome == "success" and val(eng, "SELECT status FROM trades") == "declined"
    assert one(eng, "bob", "accept 1").outcome == "impossible"
    assert one(eng, "bob", "decline").reason == "There is no such offer."
