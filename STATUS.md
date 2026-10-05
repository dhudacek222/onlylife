# Status

_Last updated: 2026-10-05_

## Milestones (BRIEF.md §18)
| # | Milestone | State |
|---|---|---|
| 1 | Core state + rules (schema, seeded dice, action schema, rules engine, event log, evidence; hardcoded parser) | **in progress**: first implementation done (85 tests green); multi-lens review, adversarial verify and fixes in progress |
| 2 | Harness: decision model + LLM escalation, reference resolution, alternatives, confirmations, per-observer narration | not started |
| 3 | First street: tavern, herbalist, well, guard post, houses; 5–10 NPC routines; encounters, stealth, law/evidence/bounty loop | not started |
| 4 | Images: cached locations, overlays, hotspots, vision verification | not started |
| 5 | Multiplayer (3–5 friends): concurrency, global clock, AFK/logout, atomic trades over network | not started |
| 6 | Storyteller + news + gossip propagation, monsters/contracts | not started |

## Done
- Architecture proposal + OPEN DECISIONS → `DESIGN.md`

## In progress / next steps
1. Finish M1: `python -m pytest -q` fully green, every DESIGN.md §5–8 row covered by a test.
2. Then M2. First task: define `DecisionModel` / `Narrator` Protocols and a parser eval set (100–200 commands: clean, typos, slang, injection) per BRIEF.md §19.

## Known gaps / deferred on purpose
- M1 leaves out: confirmations, alternatives as buttons, encounters/turn order, NPC routines, bounty/contract board, containers (chests), setting packs (fixture world is hardcoded).
