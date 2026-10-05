"""Seeded, counter-based dice and probability helpers. Pure: world.roll() persists the counter and the log."""
import random
from fractions import Fraction


def raw_roll(seed, n, sides=20, mode="normal"):
    """Roll number n of a world. String seeding is sha512-based, so this is stable across processes."""
    rng = random.Random(f"{seed}:{n}")
    return [rng.randint(1, sides) for _ in range(1 if mode == "normal" else 2)]


def kept(raw, mode):
    return max(raw) if mode == "advantage" else min(raw) if mode == "disadvantage" else raw[0]


def success_probability(modifier, dc, mode="normal", sides=20):
    """Exact P(d{sides} (+adv/dis) + modifier >= dc), as a Fraction."""
    need = dc - modifier
    p = Fraction(min(sides, max(0, sides - need + 1)), sides)
    if mode == "advantage":
        return 1 - (1 - p) ** 2
    if mode == "disadvantage":
        return p ** 2
    return p


def server_daily_rate(p, attempts_per_day):
    """Chance that at least one of `attempts_per_day` independent tries succeeds."""
    return 1 - (1 - p) ** attempts_per_day
