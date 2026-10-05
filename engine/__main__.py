"""Tiny REPL: python -m engine [--claude]
   :wait N advances the clock, :view prints the view, :q quits. Numbered buttons: type the number."""
import pprint
import sys

from engine import fixtures
from engine.config import Config
from engine.engine import Engine


def main(argv):
    cfg, model, narrator = Config(), None, None
    if "--claude" in argv:  # needs `pip install anthropic` and credentials; low-confidence inputs and narration
        from harness.claude import ClaudeDecisionModel, ClaudeNarrator, EscalatingModel
        from harness.narration import TemplateNarrator
        from harness.rules_model import RulesDecisionModel
        model = EscalatingModel(RulesDecisionModel(), ClaudeDecisionModel(cfg.llm_model, cfg.llm_effort),
                                cfg.escalate_below)
        narrator = ClaudeNarrator(TemplateNarrator(), cfg.llm_model, cfg.llm_effort)
    eng = Engine.create(seed=42, config=cfg, world=fixtures.MILL_STREET, model=model, narrator=narrator)
    print(eng.describe("player"))
    buttons = []
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in (":q", ":quit"):
            break
        if line.startswith(":wait"):
            eng.advance(int(line.split()[1]) if len(line.split()) > 1 else 1)
            print(f"time is now {eng.view('player')['time']}")
            continue
        if line == ":view":
            pprint.pprint(eng.view("player"), sort_dicts=False)
            continue
        if line.isdigit() and 0 < int(line) <= len(buttons):
            b = buttons[int(line) - 1]
            if b["command"] is None:
                buttons = []
                continue
            results = eng.submit("player", b["command"], confirm=b.get("confirm", False), via="button")
        elif line:
            results = eng.submit("player", line)
        else:
            continue
        buttons = []
        for r in results:
            if r.messages.get("player"):
                print(r.messages["player"])
            buttons = r.alternatives or buttons
        for i, b in enumerate(buttons, 1):
            print(f"  [{i}] {b['label']}")


if __name__ == "__main__":
    main(sys.argv[1:])
