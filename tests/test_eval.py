"""Parser eval set (BRIEF §19) against the free rules model. The bar that matters most is calibration:
whatever the rules model is confident about must be right, so every error lands where the harness escalates
to an LLM or asks the player."""
from harness.eval import load, report, score
from harness.rules_model import RulesDecisionModel


def test_eval_set_size_and_coverage():
    cases = load()
    assert 100 <= len(cases) <= 200
    assert {c["cat"] for c in cases} == {"clean", "speech", "typo", "slang", "nonnative", "unparsed", "injection"}


def test_rules_model_accuracy_and_calibration():
    r = report(score(RulesDecisionModel()))
    assert r["high_conf_accuracy"] == 1.0, r  # confident => right
    assert r["low_conf_accuracy"] < r["high_conf_accuracy"]  # errors live below the escalation threshold
    assert r["by_category"]["clean"] == 1.0 and r["by_category"]["speech"] == 1.0
    assert r["by_category"]["injection"] == 1.0 and r["false_injections"] == 0
    assert r["accuracy"] >= 0.9, r
