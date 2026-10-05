"""Tiny REPL: python -m engine   (:wait N advances the clock, :view prints the view, :q quits)."""
import pprint

from engine import fixtures
from engine.engine import Engine


def main():
    eng = Engine.create(seed=42, world=fixtures.MILL_STREET)
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
        elif line == ":view":
            pprint.pprint(eng.view("player"), sort_dicts=False)
        elif line:
            for r in eng.submit("player", line):
                if r.messages.get("player"):
                    print(r.messages["player"])


if __name__ == "__main__":
    main()
