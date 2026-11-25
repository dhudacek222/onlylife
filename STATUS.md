# Status

_Last updated: 2026-11-25_

## Milestones (BRIEF.md §18)
| # | Milestone | State |
|---|---|---|
| 1 | Core state + rules (schema, seeded dice, action schema, rules engine, event log, evidence; hardcoded parser) | **done pending owner sign-off**: every DESIGN.md §6 rule tested; independent adversarial review + 300-seed multi-actor fuzz (no dupes, coins conserved, replay identical) after fixes |
| 2 | Harness: decision model + LLM escalation, reference resolution, alternatives, confirmations, per-observer narration | **in progress**: slice 1 done (DESIGN.md §9): Protocols, rule→Claude escalation, structured-action replay, confirmations, per-observer narration, 132-case eval. Live Claude eval not yet run. Slice 1b: **MCP connector** so players use their own Claude/ChatGPT subscription (DESIGN.md §10), tested end-to-end over HTTP with a real MCP client |
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
0. **Owner action (main path):** try the connector from a real app: run `python -m engine.mcp_server --db world.db --http`, expose it over HTTPS (e.g. a tunnel), add it as a custom connector in Claude (Settings → Connectors) and/or ChatGPT (developer mode). Unverified: whether ChatGPT Plus allows write-capable tools. Note how the assistant narrates and whether it respects confirmations.
1. **Owner action (fallback path, optional):** `pip install anthropic`, set credentials, run `python -m engine.evals --model both --show-failures` (costs a little: ~70 small requests reach the API). Record scores here; tune `DECIDE_SYSTEM` on failures.
2. M2 slice 2: risk estimate on confirm (roll-free DC preview in rules → `risk_display`), feasible alternatives when an action is impossible (BRIEF §5 step 4).
3. Rule tier mis-parses some junk into valid-looking actions ("give me the king's crown" → give item "me the king's crown"); harmless (engine says impossible) but it never escalates. Consider escalating when references don't resolve.
4. Characters can't be targeted by description ("the hooded stranger") through the rule tier, only by name; the LLM tier handles it via scene refs.

- 2026-11-25 independent adversarial review of M1 found 3 more defects, all fixed with regression tests:
  - **Leak:** witnesses read a hidden target's name ("... says to Wren"). Targets an observer can't see now render as "someone".
  - **Leak:** bare `accept` completed a trade with a hidden offerer (presence test + name). Recipients only know offers they perceived; offerer must be present and visible.
  - `decline` worked remotely and broadcast names; now needs both parties here. Asking about others' trades = "There is no such offer."
  - Also: rule reasons named strangers ("Vex is dead"); now "the stranger" until introduced.
- 2026-11-25 MCP connector (DESIGN.md §10): players' own AI subscriptions play the game through `look`/`act` tools.
- 2026-11-25 M2 slice 1 (see DESIGN.md §9). Fixed during it: confirmation prompt named strangers by their internal id.

## Known gaps / deferred on purpose
- M1 leaves out: confirmations, alternatives as buttons, encounters/turn order, NPC routines, bounty/contract board, containers (chests), setting packs (fixture world is hardcoded).
- Review design notes, not defects against DESIGN.md (decide later): "steal X from bob" / "offer ... for X" reveal another's inventory for free (prerequisite check before any roll); lockpick repeat pressure also counts earlier key unlocks of that door; a hidden mover failing destination stealth stays hidden from those who didn't notice (BRIEF §8 says failed movement stealth "ends" hiding).
- Open questions noticed in the audit (not bugs against DESIGN.md, decide later): stealing coins from a target with 0 coins "succeeds" for 0; attack has no repeat pressure; looting a body is not a crime; parser splits item names on "and" ("bread and butter").
