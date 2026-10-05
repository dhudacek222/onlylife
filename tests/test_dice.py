import json
import random
from fractions import Fraction

import pytest

from engine import dice
from engine.dice import server_daily_rate, success_probability
from conftest import new, one, rows, setchar, val


def test_roll_n_uses_seed_colon_n():
    for n in range(1, 50):
        assert dice.raw_roll(42, n) == [random.Random(f"42:{n}").randint(1, 20)]
    assert dice.raw_roll(42, 7, mode="advantage") != dice.raw_roll(43, 7, mode="advantage")


def test_every_roll_is_logged_and_matches_seed():
    eng = new(seed=1234)
    for _ in range(5):
        eng.submit("player", "look")
    log = rows(eng, "SELECT id, raw, total, modifier, purpose, event_id, actor_id FROM dice_log ORDER BY id")
    assert [r[0] for r in log] == [1, 2, 3, 4, 5]
    assert val(eng, "SELECT value FROM meta WHERE key='roll_counter'") == "5"
    for n, raw, total, modifier, purpose, event_id, actor in log:
        assert raw == f"[{random.Random(f'1234:{n}').randint(1, 20)}]"
        assert purpose == "perception" and actor == "player"
        assert val(eng, "SELECT verb FROM events WHERE id=?", event_id) == "look"


def test_same_seed_same_rolls_different_seed_different_rolls():
    a, b, c = new(seed=7), new(seed=7), new(seed=8)
    for e in (a, b, c):
        for _ in range(10):
            e.submit("player", "look")
    raws = [rows(e, "SELECT raw FROM dice_log ORDER BY id") for e in (a, b, c)]
    assert raws[0] == raws[1] != raws[2]


def test_advantage_logs_both_dice_and_keeps_best():
    eng = new()
    setchar(eng, "bob", status="afk", hp=100, max_hp=100)  # afk target -> advantage
    eng.submit("player", "attack bob")
    raw, mode, total, modifier = eng.conn.execute(
        "SELECT raw, mode, total, modifier FROM dice_log WHERE purpose='attack'").fetchone()
    raw = json.loads(raw)
    assert mode == "advantage" and len(raw) == 2 and total == max(raw) + modifier


def brute(modifier, dc, mode):
    faces = range(1, 21)
    if mode == "normal":
        outcomes = [d for d in faces]
    else:
        pick = max if mode == "advantage" else min
        outcomes = [pick(a, b) for a in faces for b in faces]
    return Fraction(sum(o + modifier >= dc for o in outcomes), len(outcomes))


@pytest.mark.parametrize("mode", ["normal", "advantage", "disadvantage"])
def test_success_probability_is_exact(mode):
    for modifier in range(-8, 12):
        for dc in range(-2, 35):
            assert success_probability(modifier, dc, mode) == brute(modifier, dc, mode)


def test_probability_examples():
    assert success_probability(0, 11) == Fraction(1, 2)
    assert success_probability(0, 18) == Fraction(3, 20)  # unarmed vs AC 12 needs 18+
    assert success_probability(0, 11, "advantage") == Fraction(3, 4)
    assert success_probability(0, 11, "disadvantage") == Fraction(1, 4)
    assert success_probability(0, 30) == 0 and success_probability(30, 5) == 1


def test_server_level_rate_of_a_rare_action():
    # brief: 1.25% x 100 players/day = the king gets robbed (almost) daily
    assert server_daily_rate(0.0125, 100) == pytest.approx(0.7156, abs=0.001)
    assert server_daily_rate(0.0125, 1) == pytest.approx(0.0125)
    assert server_daily_rate(Fraction(1, 20), 100) > 0.99
    assert server_daily_rate(0, 10_000) == 0
