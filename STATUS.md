# Status

_Last updated: 2026-10-05_

Build order now follows `BRIEF_PART2.md` §11 (replaces BRIEF.md §18). Owner's call (2026-10-05): **core engine and
harness first, assets/visuals later.**

## Milestones (BRIEF_PART2.md §11)
| # | Step | State |
|---|---|---|
| 1 | Core state + rules | **done** (M1 test suite green). The adversarial review planned last session was not run; a read-through found no defects |
| 2 | Harness: decision model + LLM escalation, references, alternatives, confirmations, per-observer narration | **done, offline**: rules model + Claude adapter + escalation + confirm/clarify/alternatives + facts-only narration; 147 tests green. The Claude path is tested with a fake client only; it has **never run against the real API** |
| 3 | Asset pipeline spike (Three.js, Quaternius, mobile perf) | deferred by owner. Blocker noted: the Quaternius packs must be downloaded manually (automated itch.io download was refused) |
| 4 | Building generator v1 | not started |
| 5 | First street playable single-player | not started |
| 6 | Web client shell | not started |
| 7 | Multiplayer + offline agents | not started |
| 8 | Travel | not started |
| 9 | Storyteller, news, gossip, contracts, portraits | not started |

## Done this session
- M2 harness (DESIGN.md §9): `harness/` package; `submit()` decides → refuse / unparsed / clarify / confirm (dry-run
  preview with risk estimate, nothing written) → execute; buttons carry canonical commands; replay logs decided
  actions; `model_calls` cost table; narrators only ever receive per-observer facts.
- Parser eval set `harness/evalset.jsonl` (139 cases: clean, speech, typo, slang, non-native, unparsed, injection).
  Rules model: 95.7% overall, **100% when confident (84/84)**, 100% injection recall, 0 false injections.
- Part 2 brief saved (`BRIEF_PART2.md`); its conflicts with Part 1 and proposed resolutions: DESIGN.md §10.

## Next steps
1. Run `python -m harness.eval --claude` once with real credentials (`pip install anthropic`). Record accuracy, cost and
   latency per call; decide OPEN DECISION 16 (decision/narration model vs ≈$0.10/player-hour).
2. Owner to confirm the DESIGN.md §10 resolutions (map tracking, offline-agent status, caravan logout, server timing).
3. Step 5 core (engine-side, no visuals): NPC routines in code, encounters/turn order/initiative, AFK handling,
   bounty/contract board. Then the minimal server (FastAPI + WebSocket pushing per-observer views).

## Known gaps / deferred on purpose
- Preview estimates only the first irreversible action of a chain.
- `to_command` of a `say` mid-chain would swallow later clauses (speech is always last in practice).
- Fixture world is hardcoded (no setting packs); no containers; no NPC routines yet.
