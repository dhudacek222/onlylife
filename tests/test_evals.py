"""The parser eval set itself (BRIEF §19) and the rule tier's floor on it."""
from engine.actions import Action
from engine.evals import load, passes, run
from engine.harness import RuleDecision


def test_eval_set_shape():
    cases = load()
    assert 100 <= len(cases) <= 200
    assert {c["cat"] for c in cases} == {"clean", "multi", "typo", "slang", "injection", "nonsense"}


def test_rule_tier_handles_clean_input_and_rejects_nonsense():
    score, failures = run(RuleDecision())
    for cat in ("clean", "multi", "nonsense"):
        assert score[cat][0] == score[cat][1], [f for f in failures if f[0]["cat"] == cat]


def test_scoring():
    case = {"expect": [["attack", "bob", None]], "allow_empty": True}
    assert passes(case, [Action("attack", target="Bob")])
    assert passes(case, [])
    assert not passes(case, [Action("attack", target="bob"), Action("look")])  # extra actions never pass
    assert not passes({"expect": [["attack", "bob", None]]}, [])
