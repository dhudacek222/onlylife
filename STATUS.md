# Status

_Last updated: 2026-11-26_

Two sessions built in parallel from the first M1 commit (`ccr-dc99b96c-k0zz4a`: M1 audit + MCP connector;
`ccr-dfe4ce3f-0j3lis`: full M2 harness, encounters, Part 2 brief, research). **They are merged on
`ccr-dfe4ce3f-0j3lis`** (owner's choice: this branch's harness is the base). One branch from here on.

Build order follows `BRIEF_PART2.md` §11. Owner's call: core engine and harness first, assets/visuals later.

## Milestones (BRIEF_PART2.md §11)
| # | Step | State |
|---|---|---|
| 1 | Core state + rules | **done, pending owner sign-off**: every DESIGN.md §6 rule tested; adversarial review + 300-seed multi-actor fuzz on the connector branch; 4 leaks found and fixed (see below) |
| 2 | Harness: decision model + escalation, references, alternatives, confirmations, per-observer narration | **done, offline**: rules model + Claude adapter + escalation; refuse / clarify / confirm with risk estimate / alternatives; facts-only narration; 139-case eval. Plus the **MCP connector** (players' own Claude/ChatGPT runs the AI), now using the same confirm + risk flow. The Claude API path and the connector from a real app have **never been run for real** |
| 3 | Asset pipeline spike | deferred by owner. Quaternius packs must be downloaded manually (automated itch.io download was refused) |
| 4 | Building generator v1 | not started |
| 5 | First street playable single-player | **in progress**: encounters done (DESIGN.md §11). Next: free-form attempts with effect-based crimes (RESEARCH.md), NPC routines, guards reacting to witnessed crimes, bounty board, minimal server |
| 6–9 | Web client, multiplayer, travel, storyteller | not started |

## Done
- M1 (85 tests) → audit fixes: hidden-target names leaked to witnesses ("someone" now); bare `accept` worked
  with a hidden offerer; `decline` worked remotely; same-tick re-hide kept stale awareness (`hidden_event`);
  "say I need cash" introduced Ash (whole-word match); rule reasons named strangers ("the stranger").
- M2 harness (DESIGN.md §9), Part 2 conflicts (§10), encounters (§11), MCP connector (§12).
- Merge fix: confirmation prompts named the target by internal id; now by the label the actor knows.
- `RESEARCH.md`: why AI RPGs feel soft; build rule "code decides, LLM voices"; effect-based crimes.
- 188 tests green.

## Next steps
1. **Owner sign-off on M1**, and on DESIGN.md §10 (Part 2 conflict resolutions) and §11 ("join a fight by
   involvement, not proximity").
2. **Owner try-outs (real, not faked):** the connector from the Claude/ChatGPT app (`SETUP.md`); and/or
   `pip install anthropic` + API key → `python -m harness.eval --claude` (cost, accuracy, latency; decides
   OPEN DECISION 16).
3. Free-form attempt verb with effect-based crimes (RESEARCH.md §"Custom crimes").
4. NPCs decide in code, LLM voices; NPC routines; delayed consequences (witness report → investigation → bounty).

## Known gaps / deferred on purpose
- Preview estimates only the first irreversible action of a chain.
- Connector: one player per process, no auth (M5: MCP OAuth); refs/inboxes in memory.
- Rule tier can't target characters by description ("the hooded stranger"); the LLM tier and connector can.
- Review notes to decide later: "steal X from bob" reveals inventory before any roll; stealing coins from someone
  with 0 coins "succeeds" for 0; attack has no repeat pressure; looting a body is not a crime; the parser splits
  item names on "and" ("bread and butter"); a hidden mover failing destination stealth stays hidden from those
  who didn't notice.
