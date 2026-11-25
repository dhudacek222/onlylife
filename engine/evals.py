"""Parser eval: score a DecisionModel on evals/commands.jsonl (BRIEF §19).
    python -m engine.evals                 # the free rule tier
    python -m engine.evals --model claude  # live API: costs money, needs credentials
    python -m engine.evals --model both    # rules, escalating to claude
Each case: text, starting place, expected [verb, target, item] list ("a|b" alternatives, "*" any, null none).
allow_empty: returning no actions also passes (injection, vague input). Extra/other actions never pass."""
import argparse
import json
import pathlib
from collections import defaultdict

from engine.engine import Engine
from engine.harness import Escalating, RuleDecision, scene_for, unref

CASES = pathlib.Path(__file__).parent.parent / "evals" / "commands.jsonl"
GOTO = {"tavern": "", "street": "go to street", "shop": "go to street and go to shop"}
ARTICLES = {"the", "a", "an", "my", "his", "her", "their", "some"}


def norm(s):
    return " ".join(w for w in str(s).lower().strip(" .!?\"'").split() if w not in ARTICLES) if s is not None else None


def slot_ok(got, want):
    if want == "*":
        return True
    if want is None:
        return got is None
    return got is not None and norm(got) in {norm(w) for w in want.split("|")}


def passes(case, actions):
    if not actions:
        return case.get("allow_empty", False) or not case["expect"]
    if len(actions) != len(case["expect"]):
        return False
    return all(a.verb in e[0].split("|") and slot_ok(a.target, e[1]) and slot_ok(a.item, e[2])
               for a, e in zip(actions, case["expect"]))


def load():
    return [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]


def scenes():
    out = {}
    for at, cmd in GOTO.items():
        eng = Engine.create(seed=1)
        if cmd:
            eng.submit("player", cmd)
        out[at] = scene_for(eng.view("player"))
    return out


def run(model, cases=None):
    """Returns (per-category [passed, total], failures)."""
    cases, sc = cases or load(), scenes()
    score, failures = defaultdict(lambda: [0, 0]), []
    for c in cases:
        scene, refs = sc[c["at"]]
        try:
            actions = unref(model.decide(c["text"], scene).actions, refs)
        except Exception as e:  # count model errors as failures, keep going
            actions, c = [], {**c, "error": repr(e)}
        ok = passes(c, actions)
        score[c["cat"]][0] += ok
        score[c["cat"]][1] += 1
        if not ok:
            failures.append((c, [(a.verb, a.target, a.item) for a in actions]))
    return dict(score), failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["rules", "claude", "both"], default="rules")
    ap.add_argument("--show-failures", action="store_true")
    args = ap.parse_args()
    if args.model == "rules":
        model = RuleDecision()
    else:
        from engine.claude import ClaudeDecision
        model = ClaudeDecision() if args.model == "claude" else Escalating(RuleDecision(), ClaudeDecision())
    score, failures = run(model)
    total = [sum(v[i] for v in score.values()) for i in (0, 1)]
    for cat, (p, n) in sorted(score.items()):
        print(f"{cat:10s} {p:4d}/{n:<4d} {100 * p / n:5.1f}%")
    print(f"{'TOTAL':10s} {total[0]:4d}/{total[1]:<4d} {100 * total[0] / total[1]:5.1f}%")
    if args.show_failures:
        for c, got in failures:
            print(f"  [{c['cat']}] {c['text']!r}: got {got} want {c['expect']}{' ' + c['error'] if 'error' in c else ''}")


if __name__ == "__main__":
    main()
