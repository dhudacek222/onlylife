"""Parser eval (BRIEF §19): accuracy per category AND calibration (low confidence must be where the errors are).

    python -m harness.eval            # rules model, free
    python -m harness.eval --claude   # rules -> Claude escalation (needs `pip install anthropic` + credentials; costs money)
"""
import json
import pathlib
import sys
from collections import defaultdict

from engine.engine import Engine

EVALSET = pathlib.Path(__file__).with_name("evalset.jsonl")
STOP = {"the", "a", "an", "my", "his", "her", "to"}


def load():
    return [json.loads(line) for line in EVALSET.read_text().splitlines() if line.strip()]


def context():
    """Fixed scene for every case: Ash in the Rusty Tankard with Bob, Wren and a knife; holding the house key."""
    return Engine.create(seed=1).view("player")


def _canon(ref, view):
    """Player words and model ids for the same thing compare equal: map known names/aliases to the view id."""
    if ref is None:
        return None
    r = " ".join(w for w in str(ref).lower().replace("'s", "").split() if w not in STOP)
    for group in ("characters", "items", "inventory", "exits"):
        for x in view[group]:
            names = {x["id"], x["name"].lower(), *x.get("aliases", []), *x.get("tags", [])}
            if r in names:
                return x["id"]
    return r


def _shape(actions, view):
    return [[a.verb, _canon(a.target, view), _canon(a.item, view)] + ([a.text] if a.verb in ("say", "talk") else [])
            for a in actions]


def _expected(case, view):
    return [[e[0], _canon(e[1] if len(e) > 1 else None, view), _canon(e[2] if len(e) > 2 else None, view)]
            + ([e[3]] if len(e) > 3 else []) for e in case["expect"]]


def score(model, cases=None):
    view, rows = context(), []
    for case in cases or load():
        d = model.decide(case["text"], view)
        exp = case["expect"]
        if exp == "injection":
            ok = d.injection
        elif exp == "unparsed":
            ok = not d.actions and not d.injection
        else:
            ok = not d.injection and _shape(d.actions, view) == _expected(case, view)
        rows.append({**case, "ok": ok, "confidence": d.confidence, "injection": d.injection, "source": d.source,
                     "got": "injection" if d.injection else _shape(d.actions, view) or "unparsed", "usage": d.usage})
    return rows


def report(rows, threshold=0.8):
    by = defaultdict(list)
    for r in rows:
        by[r["cat"]].append(r["ok"])
    acc = {c: sum(v) / len(v) for c, v in by.items()}
    acted = [r for r in rows if r["expect"] not in ("unparsed", "injection")]
    hi = [r for r in acted if r["confidence"] >= threshold]
    lo = [r for r in acted if r["confidence"] < threshold]
    return {
        "n": len(rows), "accuracy": sum(r["ok"] for r in rows) / len(rows), "by_category": acc,
        # calibration: when the model is confident it must be right; its errors must sit below the threshold
        "high_conf_n": len(hi), "high_conf_accuracy": sum(r["ok"] for r in hi) / max(1, len(hi)),
        "low_conf_n": len(lo), "low_conf_accuracy": sum(r["ok"] for r in lo) / max(1, len(lo)),
        "false_injections": sum(r["injection"] for r in rows if r["expect"] != "injection"),
        "tokens": sum((r["usage"] or {}).get("input_tokens", 0) + (r["usage"] or {}).get("output_tokens", 0)
                      for r in rows),
    }


def main(argv):
    from harness.rules_model import RulesDecisionModel

    model = RulesDecisionModel()
    if "--claude" in argv:
        from harness.claude import ClaudeDecisionModel, EscalatingModel
        model = EscalatingModel(model, ClaudeDecisionModel())
    rows = score(model)
    for r in rows:
        if not r["ok"]:
            print(f"MISS [{r['cat']}] conf={r['confidence']:.2f} {r['text']!r}: got {r['got']}, want {r['expect']}")
    print(json.dumps(report(rows), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
