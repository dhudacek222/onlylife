"""Tiny REPL: python -m engine [--ai]   (:wait N advances the clock, :view prints the view, :q quits).
--ai: free text the rule parser can't handle escalates to Claude, and Claude narrates (needs `anthropic`
and credentials). Irreversible actions ask for confirmation in both modes."""
import pprint
import sys

from engine import fixtures
from engine.engine import Engine
from engine.harness import Escalating, Harness, RuleDecision


def main():
    eng = Engine.create(seed=42, world=fixtures.MILL_STREET)
    if "--ai" in sys.argv:
        from engine.claude import ClaudeDecision, ClaudeNarrator
        h = Harness(eng, Escalating(RuleDecision(), ClaudeDecision()), ClaudeNarrator())
    else:
        h = Harness(eng)
    print(eng.describe("player"))
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
        if not line:
            continue
        if "player" in h.pending:
            t = h.confirm("player") if line.lower() in ("y", "yes") else h.cancel("player")
        else:
            t = h.handle("player", line)
        print(t.prompt if t.status != "done" else t.messages.get("player", ""))


if __name__ == "__main__":
    main()
