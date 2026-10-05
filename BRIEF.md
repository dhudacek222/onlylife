# MASTER PROMPT — AI-Driven Persistent World Engine (verbatim brief, condensed only in whitespace)

## 1. Vision
Players are dropped into a world (medieval, sci-fi, any setting) with no scripted story. They can attempt anything. The world remembers what they did and reacts: witnesses talk, NPCs gossip, guards investigate, bounties are posted, news spreads. Stories emerge from player actions, not from authored quests. The "magic" is consequence and memory, not AI prose.

## 2. Non-negotiable principles
1. **The engine is the single source of truth.** World state lives in the database. No AI model ever mutates state directly.
2. **AI layers are swappable modules.** Decision model, narrator, storyteller and image generator sit behind interfaces. Swapping a model must not change game rules.
3. **AI decides, code executes, AI narrates.** Pipeline: text → structured action → deterministic rules + dice → state change → narration.
4. **Consequences come from a fixed whitelist** of state mutations the engine supports. An AI may describe anything but may only change the world through these.
5. **Nothing vanishes.** Objects change owner or location; they are never silently deleted.
6. **Every action leaves evidence.** Investigations read evidence records; they never invent facts.
7. **Information is per-observer.** Each player/NPC only receives what their character actually perceives. Narration for a player must be generated only from that player's visible facts.
8. **Setting is configuration.** Medieval vs sci-fi changes names, assets and flavor text, not engine code.
9. **Fairness is legible.** When a player fails or gets caught, the engine must be able to show why (which roll, which witness, which evidence).

## 4. World model (core entities)
- Location / Zone: id, type, setting tags, connections, owner (optional), safety level, lighting/crowd modifiers by time of day.
- Building: template tier, mechanical attributes (windows, doors, lock quality, cellar), owner, cosmetic description, wealth_display score (1–5), image refs, object hotspots.
- Object/Item: unique id, type, properties, current location or holder, full provenance history (created/bought/sold/gifted/dropped/stolen, by whom, when, where), flags (bloodied, poisoned…).
- Character: stats, skills, skill points, inventory, appearance record (face shape immutable; clothes/hair changeable), reputation per faction/area, wanted status, location, online/AFK/offline state.
- Knowledge table: who knows what about whom. Drives stealth, gossip, investigations and per-player narration.
- Evidence record: action, actor, location, time, witnesses (with detection results), physical traces.
- Event log: append-only record of every resolved action.

## 5. Action Harness (core loop)
1. Decompose free text into an ordered list of structured actions from a fixed schema (move, look, take, drop, give, trade, attack, steal, sneak, open, lock, talk, use, flee, …). Outcome words → intents: "kill X" → attack(X). The player never decides results; the dice do.
2. Resolve references: inventory first, then reachable objects in location, then visible entities. Ambiguity → offer choices.
3. Check prerequisites. 4. If impossible, offer feasible alternatives. 5. Confirm irreversible actions. 6. Roll and resolve. 7. Apply consequences from the whitelist only. 8. Write evidence + event log + knowledge updates. 9. Narrate per observer.
Parser failure: do not consume the player's turn or timer.

## 6. Rules engine & dice
- d20 + stat + skill + gear/situational vs DC. Tiers: trivial (no roll) / normal / hard / impossible-without-prerequisites.
- Prefer prerequisites over micro-probabilities (a 1.25% chance × 100 players/day = the king gets robbed daily).
- Gear matters heavily (no gear ≈ needs 18+ on d20). Advantage/disadvantage (AFK target, surprise, darkness, heavy armor for stealth).
- All dice seeded and logged for replay, debugging and dispute resolution.
- Repeat-attempt pressure is diegetic: raises difficulty, recognition, wanted level. No out-of-game "you are blocked".

## 8. Stealth & perception
Stealth roll vs EACH observer's passive perception separately. Modifiers: night, crowds, noise (+); light, heavy armor, dogs, guards (–). Undetected arrival grants surprise. Hidden ends on aggression, an active look-around perception roll, or failed movement stealth. Stealth state lives in the knowledge table; narration must never leak hidden entities.

## 9. Law, evidence & investigation
Crimes generate evidence (purchases of poison, being seen near the scene, objects left behind, bloodied items). Wanted system with bounty, wanted level, "last seen" circle. Face shape immutable; clothing/hair disguise.

## 14. Items & economy
Unique ids + provenance for every item. Player-to-player trades are atomic (item and payment move together or not at all). Guard against duplication exploits explicitly. Dropped items persist.

## 18. Milestone 1 — Core state + rules
DB schema (sections 4, 14), seeded dice, action schema, rules engine, event log, evidence records. Text-only, no AI (hardcoded parser for tests). Single-player first on the MMO architecture (same schema, same per-observer knowledge model).

## 19. Testing requirements
- Deterministic replay of any session from seeds + event log.
- Exploit tests: item duplication during trades, information leaks of hidden entities, (later: combat logging, freezing via non-hostile interactions, impact caps).
- Probability sanity: server-level success rates of rare actions (per-player chance × attempts per day).
