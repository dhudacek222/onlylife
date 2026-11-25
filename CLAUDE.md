# ReadyOne / onlylife — AI-driven persistent world engine

Read these before working:
- `BRIEF.md` — the product brief and its non-negotiable principles (engine = source of truth, AI never mutates state, whitelist consequences, nothing vanishes, every action leaves evidence, per-observer information, legible fairness).
- `DESIGN.md` — binding contract: stack, module boundaries, DB schema, rules table, OPEN DECISIONS (all live in `engine/config.py`), Engine API.
- `STATUS.md` — what is done, what is in progress, what is next. **Update it at the end of every session.**

## Commands
- Tests: `python -m pytest -q`
- Play in the terminal: `python -m engine` (REPL as "player"; `:wait N` advances the clock, `:view` shows what you see)
- Play from a Claude/ChatGPT app (player's own subscription runs the AI): `python -m engine.mcp_server --db world.db --http` → connector URL `http://host:8000/mcp` (needs `mcp>=2,<3`; no auth yet, keep it local)
- Parser eval: `python -m engine.evals [--model rules|claude|both] [--show-failures]`

## Rules of the codebase
- Python 3.11, stdlib only (+ pytest). No new dependencies without a strong reason. Exceptions, each confined to one module and imported nowhere else: `mcp` (engine/mcp_server.py), `anthropic` (engine/claude.py, lazy).
- `engine/world.py` is the ONLY module that writes world tables. AI modules (M2+) must never import it; they produce `Action`s for `engine.py`.
- DB triggers enforce no-delete, append-only logs, one-place items, coins ≥ 0, immutable face_shape. Never weaken them.
- Determinism: all randomness goes through `engine/dice.py`; every SELECT that affects outcomes has ORDER BY; replay must stay identical.
- Hidden entities must never leak into another observer's messages, view(), reference resolution or knowledge.
- Keep it lean: no speculative abstractions, no code for future milestones. Mark deliberate shortcuts with a `# ponytail:` comment naming the limit.
- Deviating from DESIGN.md? Update DESIGN.md in the same change.

## Working style (owner preferences)
- In Workflow scripts: `model: 'sonnet'` for research/scouting agents, `model: 'opus'` for implementation, review, adversarial verification and judging.
- Build milestone by milestone (DESIGN.md / BRIEF.md §18). Do not start AI integration (M2) before M1 tests are green.
- Commit and push working states, so sessions can continue on another machine (home PC ↔ claude.ai/code cloud).
