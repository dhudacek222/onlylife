# Status

_Last updated: 2026-11-25_

## Milestones (BRIEF.md §18)
| # | Milestone | State |
|---|---|---|
| 1 | Core state + rules (schema, seeded dice, action schema, rules engine, event log, evidence; hardcoded parser) | **done pending owner sign-off**: 93 tests green; every DESIGN.md §6 verb row + repeat/perception/wanted/arrival rule has a test |
| 2 | Harness: decision model + LLM escalation, reference resolution, alternatives, confirmations, per-observer narration | not started |
| 3 | First street: tavern, herbalist, well, guard post, houses; 5–10 NPC routines; encounters, stealth, law/evidence/bounty loop | not started |
| 4 | Images: cached locations, overlays, hotspots, vision verification | not started |
| 5 | Multiplayer (3–5 friends): concurrency, global clock, AFK/logout, atomic trades over network | not started |
| 6 | Storyteller + news + gossip propagation, monsters/contracts | not started |

## Done
- Architecture proposal + OPEN DECISIONS → `DESIGN.md`
- M1 first pass (85 tests).
- 2026-11-25 M1 audit of DESIGN.md §6 against code + tests:
  - **Fixed leak:** visibility compared `aware_of.time >= hidden_since`; awareness from an earlier hide in the same tick survived a re-hide. Now `hidden_event` (event id) + `knowledge.event_id`. Latent under default config, real at M5 (many events per tick).
  - **Fixed:** "say I need cash" introduced Ash (substring match). Now whole-word.
  - Added tests for previously untested rules: night stealth bonus, guard penalty, arrival passive-perception notice + `seen_at`, force heard on both sides of the door, repeat pressure on lockpick/force, steal advantage vs AFK, offline characters perceive nothing.

## In progress / next steps
1. M2. First task: define `DecisionModel` / `Narrator` Protocols and a parser eval set (100–200 commands: clean, typos, slang, injection) per BRIEF.md §19.

## Known gaps / deferred on purpose
- M1 leaves out: confirmations, alternatives as buttons, encounters/turn order, NPC routines, bounty/contract board, containers (chests), setting packs (fixture world is hardcoded).
- Open questions noticed in the audit (not bugs against DESIGN.md, decide later): stealing coins from a target with 0 coins "succeeds" for 0; attack has no repeat pressure; looting a body is not a crime; parser splits item names on "and" ("bread and butter").
