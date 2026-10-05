from conftest import counts, one
from engine.parser import parse


def verbs(text):
    return [(a.verb, a.target, a.item) for a in parse(text)]


def test_multi_action():
    assert verbs("take knife and attack bob") == [("take", None, "knife"), ("attack", "bob", None)]
    assert verbs("go to street, then unlock green door; go home") == [
        ("move", "street", None), ("unlock", "green door", None), ("move", "home", None)]


def test_outcome_words_become_intents():
    assert verbs("kill bob") == [("attack", "bob", None)]
    assert verbs("murder bob with the knife") == [("attack", "bob", "the knife")]


def test_synonyms():
    assert verbs("grab the knife") == [("take", None, "the knife")]
    assert verbs("pick up knife") == [("take", None, "knife")]
    assert verbs("walk to the tavern") == [("move", "the tavern", None)]
    assert verbs("hide") == [("sneak", None, None)]
    assert verbs("pickpocket bob") == [("steal", "bob", None)]
    assert verbs("steal the watch from bob") == [("steal", "bob", "the watch")]
    assert verbs("drink potion") == [("use", None, "potion")]
    assert verbs("shut the door") == [("close", "the door", None)]
    assert verbs("kick in oak door") == [("force", "oak door", None)]
    assert verbs("please look around") == [("look", None, None)]


def test_speech_keeps_its_text():
    [a] = parse('say "Hello, I am Ash and I mean no harm"')
    assert a.verb == "say" and a.text == "Hello, I am Ash and I mean no harm"
    [a] = parse("tell bob: nice apron")
    assert (a.verb, a.target, a.text) == ("talk", "bob", "nice apron")
    take, say = parse("take knife and say hi and bye")
    assert take.verb == "take" and say.text == "hi and bye"


def test_offer_and_accept():
    [a] = parse("offer knife to bob for 5 coins")
    assert (a.item, a.coins, a.target, a.want_item, a.want_coins) == ("knife", 0, "bob", None, 5)
    [a] = parse("offer 10 coins to bob for pocket watch")
    assert (a.item, a.coins, a.target, a.want_item) == (None, 10, "bob", "pocket watch")
    assert parse("accept")[0].target is None
    assert parse("accept trade #3")[0].target == "3"
    assert parse("accept bob's offer")[0].target == "bob"


def test_unparsed():
    assert parse("dance wildly") == []
    assert parse("take knife and dance") == []  # any unknown clause -> whole input unparsed
    assert parse("") == []


def test_unparsed_costs_nothing(eng):
    before = counts(eng)
    r = one(eng, "player", "dance wildly on the table")
    assert r.outcome == "unparsed" and "understand" in r.messages["player"]
    assert counts(eng) == before  # no event, no clock, no roll, not even an input row
