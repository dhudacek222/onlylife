# ReadyOne — Architecture & Milestone 1 Contract

## 1. Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11 | per brief; stdlib covers M1 entirely |
| Storage | SQLite (stdlib `sqlite3`, WAL) now → Postgres at M5 | single file, transactional, zero deps. Schema avoids SQLite-only features except triggers (Postgres has equivalents) |
| Concurrency model | **One authoritative writer per world.** Every action runs in one `BEGIN IMMEDIATE` transaction | 150 entities/world is tiny; serialising actions removes whole classes of dupe/race bugs |
| Server (M5) | FastAPI + websockets, one world process | not in M1 |
| AI (M2+) | `typing.Protocol` interfaces: `DecisionModel`, `Narrator`, `Storyteller`, `ImageGen` | swappable, never touch DB |
| LLM adapter (M2) | official `anthropic` SDK, **optional**, imported lazily inside `harness/claude.py` only | stdlib core stays dependency-free; SDK gives retries/typed errors |
| Tests | pytest | installed |
| Dependencies | **none** beyond stdlib + pytest for engine, rules model and tests; `anthropic` only to run with `--claude` | |

## 2. Module boundaries

```
engine/
  config.py    Config dataclass: all tunables + OPEN DECISIONS (section 4)
  db.py        SCHEMA (DDL + integrity triggers), connect()
  dice.py      Dice: seeded, counter-based, every roll logged; probability helpers
  actions.py   Verb metadata (irreversible? hostile? crime?), Action, Roll, Result dataclasses
  parser.py    hardcoded parser: text -> list[Action]  (wrapped by harness.rules_model in M2)
  world.py     ONLY module that writes world tables. Read queries + the consequence WHITELIST
  rules.py     Deterministic resolution per verb: prerequisites, DCs, modifiers, dice -> whitelist calls
  encounters.py  Encounter lifecycle (start, join, turn order, leave, end) via world.* writes
  npc.py       Deterministic NPC fight routine: picks an Action, rules resolve it
  engine.py    Engine facade: the harness loop (submit), preview/confirm, alternatives, per-observer facts, replay
  fixtures.py  Demo world ("Mill Street") used by tests and the REPL
  __main__.py  Tiny REPL: python -m engine [--claude]
harness/       AI seams (M2). May import engine.actions / engine.parser / engine.config only
  protocols.py   DecisionModel, Narrator Protocols; Decision record
  rules_model.py RulesDecisionModel: parser + fillers/slang/typos, view-based ref check, injection screen, confidence
  claude.py      ClaudeDecisionModel, ClaudeNarrator, EscalatingModel; validate() for untrusted model output
  narration.py   TemplateNarrator (the M1 templates, now fed per-observer facts)
  eval.py        parser eval: accuracy per category + calibration; evalset.jsonl (139 cases)
  scene.py       scene_for() (view with opaque character refs c1, c2…), unref(), VERB_GUIDE — for outside AIs
engine/connector.py  the game as tools for a player's own AI assistant (look / act), stdlib only
engine/mcp_server.py thin MCP 2.x wrapper around connector.Game (the only module importing `mcp`)
tests/
```

Dependency direction (no cycles): `engine → rules → world → db`; `rules → dice, actions, config`; `parser → actions`;
`engine.engine → harness → engine.actions/parser`. **No AI module may import `world`, `db` or `rules`** (test-enforced).
The harness hands structured `Action`s to the engine; the engine never trusts them beyond the verb whitelist.

## 3. Pipeline (M1 subset of the Action Harness)

```
text ─parser─► [Action…] ─► for each, in order, inside one transaction:
   resolve refs (inventory → location items → visible characters; hidden = unresolvable)
   check prerequisites   ── missing → Result(outcome="impossible", reason, missing=[…])  (no roll)
   compute DC + modifiers ── roll (logged) ── outcome
   apply consequences via world.* whitelist only
   write event + perceptions (witness records) + traces + knowledge
   render per-observer template lines (actor / target / each detecting witness)
```
If an action in a chain is impossible or fails, the remaining actions of that input are **not** executed (they get `outcome="skipped"`). Unparseable input → `Result(outcome="unparsed")`, no event, no clock change.

Confirmations, alternatives-as-buttons, LLM escalation, encounters/turn order, NPC routines, contracts/bounty board, images: **not M1** (M2/M3/M4).

## 4. OPEN DECISIONS (all live in `Config`, defaults shown)

| # | Decision | Default | Source |
|---|---|---|---|
| 1 | Risk estimate on confirm | `risk_display="verbal_scaled"` (precision grows with character XP); alts `"exact"`, `"none"` | brief §5 |
| 2 | take + attack = one or two turns | `chain_actions_cost_separate_turns=True` (two) | brief §5 |
| 3 | Death rule | `death_mode="penalty"` (character persists, carried items dropped at death spot), `death_lockout="next_real_day"`; alt `death_mode="permadeath"` | brief §11 |
| 4 | Turn timer | `turn_timer_seconds=90` | brief §7 (60–120) |
| 5 | AFK threshold | `afk_after_ticks=10` | brief §11 |
| 6 | Unsafe-logout linger | `logout_linger_ticks=30` | brief §11 |
| 7 | Fresh "look around" image cost | `look_image_turn_cost=0.5` | brief §15 |
| 8 | Gossip distortion per hop | `gossip_distortion_chance=0.15` | brief §12 (mine) |
| 9 | DC tiers | `dc_normal=12`, `dc_hard=16`; trivial = no roll; impossible = prerequisite gate | brief §6 |
| 10 | Unarmed attack | `unarmed_attack_penalty=6` (vs AC 12 → needs 18+, matching the brief's example), `unarmed_damage=1` | brief §6 |
| 11 | Repeat-attempt pressure | `repeat_dc_step=2` per prior attempt on same target+verb within `repeat_window_ticks=1440` | brief §6 (mine) |
| 12 | Wanted increments | `wanted_severity={"theft":1,"trespass":1,"burglary":2,"assault":2,"murder":4}`; applied only if ≥1 witness detected the crime | brief §9 (mine) |
| 13 | World clock | `ticks_per_day=1440` (1 tick = 1 in-game minute); night = hour <6 or ≥20 | brief §3 (mine) |
| 14 | Armor | any held armor item counts (best one); equip slots later | M1 simplification (mine) |
| 15 | Storage | SQLite until M5, then Postgres | mine |

## 5. Data model (SQLite DDL lives in `db.py`)

JSON columns are `TEXT` holding JSON. All ids are TEXT slugs (`"bob"`, `"knife_1"`) for readable tests; generated ids use `<type>_<n>`.

- `meta(key PK, value)` — `world_seed`, `roll_counter`, `clock`.
- `locations(id PK, name, kind ['street','building','wild'], tags JSON, owner_id NULL, is_public INT, safety INT 0-3, lit INT, crowd INT 0-2, cover INT)`
- `doors(id PK, name, lock_dc INT NULL, locked INT, is_open INT, key_item_id NULL)` 
- `connections(from_id, to_id, door_id NULL, PK(from_id,to_id))` — store both directions; both rows share the door.
- `housing_tiers(tier PK, windows INT, doors INT, lock_dc INT, cellar INT)`
- `buildings(location_id PK, tier → housing_tiers, owner_id, cosmetic TEXT, wealth_display INT 1-5, image_ref NULL)` — mechanics come from the tier, cosmetics are text only.
- `characters(id PK, name, is_npc, role TEXT NULL ['guard','merchant',…], location_id, status ['online','afk','offline','dead'], hp, max_hp, xp, coins INT CHECK ≥0, stats JSON {str,dex,con,int,wis,cha} as scores, skills JSON {stealth,perception,sleight,athletics,lockpicking,…} ints, skill_points, face_shape TEXT (immutable trigger), appearance JSON {hair,clothes,…}, wanted_level INT, hidden INT, hidden_event INT NULL, stealth_total INT NULL)`
- `reputation(character_id, scope, value, PK(character_id,scope))`
- `items(id PK, type, name, aliases JSON, properties JSON, price INT NULL, location_id NULL, holder_id NULL, flags JSON)` — CHECK exactly one of `location_id`,`holder_id` non-null. **DELETE forbidden by trigger.**
- `provenance(id PK AUTOINC, item_id, kind ['created','bought','sold','gifted','given','dropped','taken','stolen','looted','traded','transformed'], from_id NULL, to_id NULL, location_id, time, event_id NULL)` — append-only (UPDATE/DELETE forbidden).
- `events(id PK AUTOINC, time, actor_id, verb, target_id NULL, item_id NULL, location_id, outcome, crime NULL, data JSON)` — append-only.
- `perceptions(event_id, observer_id, detected INT, recognized INT, appearance_seen JSON NULL, roll_id NULL, PK(event_id,observer_id))` — witness records for every event; append-only.
- `traces(id PK AUTOINC, event_id, kind ['bloodied_item','item_left','forced_lock','purchase','body'], item_id NULL, location_id, detail JSON)` — physical evidence; append-only.
- `VIEW evidence` = events with `crime IS NOT NULL` joined to perceptions + traces.
- `knowledge(id PK AUTOINC, observer_id, subject_id, fact ['aware_of','seen_at','knows_identity','knows_crime'], location_id NULL, time, event_id NULL)` — append-only. Visibility rule: observer sees subject iff `subject.hidden=0` OR an `aware_of` row exists with `event_id >= subject.hidden_event` (the sneak event). Compared by event id, not clock time, because many events can share a tick (chained actions with `chain_actions_cost_separate_turns=False`; concurrent players at M5).
- `dice_log(id PK = roll counter, time, event_id NULL, actor_id, purpose, sides, raw JSON (both dice if adv/dis), mode ['normal','advantage','disadvantage'], modifier, total, dc NULL, success NULL)` — append-only.
- `trades(id PK AUTOINC, from_id, to_id, give_items JSON, give_coins, want_items JSON, want_coins, status ['pending','accepted','declined','failed'], created, resolved NULL)`
- `inputs(id PK AUTOINC, kind ['cmd','advance'], actor_id NULL, payload TEXT)` — everything needed for replay. Since M2 a `cmd` payload is JSON `{"text", "actions"}` (the decided actions).
- `model_calls(id, time, actor_id, purpose ['decide','narrate'], model, input_tokens, output_tokens, cache_read_input_tokens, latency_ms, verbs JSON)` — cost telemetry; never read by rules.

## 6. Rules (M1)

- `mod(score) = (score-10)//2`. Check = d20 (+adv/dis) + stat mod + skill + gear + situational ≥ DC.
- Passive perception = 10 + wis mod + perception. AC = 10 + dex mod + best held armor `properties.armor`.
- HP = 10 + con mod at creation (fixture sets it).
- **Dice determinism:** roll *n* uses `random.Random(f"{world_seed}:{n}")` (string seeding is sha512-based, stable across processes). Counter persisted in `meta`. Every roll writes `dice_log`.
- `success_probability(modifier, dc, mode)` exact; `server_daily_rate(p, attempts_per_day) = 1-(1-p)**attempts`.

Verbs (all resolve against the actor's current location):

| Verb | Prereqs | Check | Consequences |
|---|---|---|---|
| move(dest) | connected; door open or unlocked (moving through a closed unlocked door opens it) | none | location change; private building w/o owner permission → crime `trespass` (`burglary` if door was forced/picked this visit). If hidden: re-roll stealth vs observers at destination |
| look | — | active perception vs each hidden entity's `stealth_total` here | `aware_of` knowledge for found ones; returns visible snapshot |
| take(item) | item at location, or held by a **dead** character here | trivial | holder=actor; provenance `taken`/`looted`; taking an item lying in someone else's private building = `theft` |
| drop(item) | held | trivial | location=here; provenance `dropped`; trace `item_left` |
| give(item, target) | held; target visible, here, alive | trivial | holder=target; provenance `given` |
| buy(item, merchant) | merchant role, holds item with price, actor coins ≥ price | trivial | atomic coins+item; provenance `bought`; trace `purchase` (purchases are evidence) |
| offer / accept / decline | items held / coins available, both here | trivial | `trades` row; **accept re-validates everything and swaps atomically** or marks `failed` |
| attack(target, weapon?) | target visible, here, alive; weapon held if named (else best held weapon; none → unarmed) | d20+str mod (+athletics) − unarmed penalty vs AC; advantage if actor hidden and target not aware, or target afk; hp damage = weapon die + str mod (min 1) | ends actor hidden; weapon flag `bloodied` + trace; hp→0: status dead, `murder`, trace `body`, death_mode applied; else `assault` |
| steal(item or coins, target) | target here, visible, alive; item held by target | d20+dex+sleight vs target passive perception + repeat penalty; advantage if target afk | success: transfer (provenance `stolen`) or half target's coins; target detects only if roll fails; crime `theft` |
| sneak | not already hidden | stealth = d20+dex+stealth+cover+crowd+(2 if night and not lit) −2 per visible guard; disadvantage with heavy armor | `hidden=1`, `hidden_event=<this event>`, `stealth_total`; each observer whose passive perception ≥ total gets `aware_of` |
| unhide | hidden | — | `hidden=0` |
| open/close(door) | door here; open requires unlocked | trivial | door state |
| unlock/lock(door) | key item held → trivial; unlock w/o key needs a held `lockpick` item → dex+lockpicking vs lock_dc; no key and no lockpick → **impossible** (missing prerequisite listed) | | door state |
| force(door) | door here, locked | str+athletics vs lock_dc+4 | unlocked+open; trace `forced_lock`; **noisy: everyone in both connected locations detects** |
| talk(target, text) / say(text) | target visible+here | none | event; listeners get `knows_identity` if actor introduces (`text` contains their own name as a whole word) |
| use(item) | held, has `properties.on_use` | trivial | apply effect (`heal`), item transforms per `on_use.becomes` (provenance `transformed`) — never deleted |
| flee(dest) | connected | dex check vs dc_normal | success = move; failure = stay |
| wait | — | — | event only |

**Repeat pressure:** DC += `repeat_dc_step` × (prior events with same actor, verb, target within `repeat_window_ticks`).
**Perception of an event:** actor and (for attack, or failed steal) target always detect; each other present character (status online/afk, alive) detects iff the actor is visible to them (visibility rule), except `force` (everyone detects). Detecting witnesses get `seen_at` + (`knows_crime` if crime) knowledge; `recognized` = witness already has `knows_identity` of actor; else `appearance_seen` snapshot of the actor's face_shape + appearance is stored (so disguises matter later). Undetecting characters get **nothing**: no perception row with detected=1, no knowledge, no text.
**Wanted:** crime with ≥1 detecting witness other than the actor → `wanted_level += severity`.
**Arrival:** moving into a location writes `seen_at` for everyone who can see the arriver, and for the arriver about everyone visible to them.

## 7. Integrity guarantees (enforced in DB, tested)

- items/characters/locations cannot be deleted; events/provenance/perceptions/traces/knowledge/dice_log are append-only.
- items CHECK exactly-one-place; coins CHECK ≥0; face_shape immutable.
- Every item move goes through `world.move_item(...)` which writes provenance in the same transaction.
- Every action = one transaction; any exception rolls back everything (including dice counter).

## 8. Engine API

```python
eng = Engine.create(path=":memory:", seed=42, config=Config(), world=fixtures.MILL_STREET,
                    model=None, narrator=None)       # defaults: RulesDecisionModel, TemplateNarrator
results = eng.submit("player", "take knife and attack bob")   # -> [Result(outcome="confirm", alternatives=[Yes, Cancel])]
results = eng.submit("player", "take knife and attack bob", confirm=True)   # executes
eng.advance(60)                     # moves global clock, logged in inputs
eng.view("player")                  # dict: what this observer can see right now
eng.submit_actions("player", [Action("take", item="knife")])   # structured input (connector / harness): confirm flow, then execute
eng2 = Engine.replay(fixture, seed, config, eng.inputs())   # identical events + dice_log
```
`Result(action, outcome ['success','failure','impossible','ambiguous','unparsed','skipped','refused','confirm','clarify'], reason, missing, candidates, rolls: list[Roll], event_id, messages: dict[observer_id, str], alternatives: list[{label, command, confirm?}])` — `rolls` + `reason` make every failure legible (brief §2.9).

## 9. Milestone 2 — the Action Harness (BRIEF §5)

```
submit(actor, text, confirm=False, via="text"|"button")
  d = model.decide(text, view(actor))            # view = per-observer, so models never see hidden entities
  d.usage            → model_calls row (cost per action type, BRIEF §17)
  d.injection        → "refused"   (nothing written, no turn used)
  no actions         → "unparsed"  + suggestion buttons (nothing written)
  confidence < escalate_below (irreversible) or < clarify_below (any) → "clarify": "Did you mean: <canonical>?"
  irreversible and not confirm → preview: run the chain inside a transaction up to the first irreversible action,
       probe its first roll (rules.Probe), ROLLBACK everything → "confirm" + risk estimate + [Yes, Cancel] buttons,
       or the impossible/ambiguous Result + alternatives (still nothing written)
  else → execute (one transaction, M1 semantics) and narrate each detecting observer from facts(observer, event)
```
- **Buttons carry canonical commands** (`actions.to_command`), which the hardcoded parser maps back exactly (test-enforced
  round trip). Confirming never re-asks an LLM and needs no server-side pending state.
- **Preview burns nothing:** dice counter, clock, events all roll back; the confirmed roll is identical to an unconfirmed one.
- **Replay stores decisions, not text:** `inputs.payload` for `cmd` = `{"text", "actions"}`. `Engine.replay` executes the
  logged actions without any model, so an LLM in the loop cannot break determinism.
- **Model output is untrusted:** `claude.validate` enforces verb whitelist, field types, string/coin/length caps;
  anything off → treated as not understood. Safety against injection comes from the whitelist + rules prerequisites;
  detection only saves tokens and gives a clear message. Speech text (`say`/`talk`) is exempt from detection.
- **Escalation:** rules model first (free, deterministic); LLM only below `escalate_below`; rule-detected injection is
  final; an LLM failure or a less confident LLM answer keeps the rules' decision.
- **Narration:** `Engine.facts(observer, result)` is the only narrator input: labels as that observer knows them
  ("a stranger in a green cloak"), no ids, rolls/reason/scene only for the actor, nothing for non-detecting observers.
  Buttons always get templates; free text uses the configured narrator (ClaudeNarrator falls back to templates).
- **Alternatives** (`Engine._alternatives`) come from the actor's view: locked door → unlock/force; no lockpick →
  take the one lying here/force; named weapon missing → take it/attack unarmed; ambiguity → one button per candidate;
  always "look around" + Cancel.
- **Rules-model confidence levels:** exact parse 1.0; known rewrite (filler words, slang table, trailing "please") 0.9;
  unknown-but-suspicious reference (mistyped connector "wiht", transposed name "bbo") 0.7; fuzzy verb or reference
  correction 0.6; not understood 0.0. Calibrated on `harness/evalset.jsonl`: every case at ≥0.8 is correct (test-enforced).

### New tunables (Config)
| Name | Default | Note |
|---|---|---|
| `confirm_irreversible` | True | M1 rule tests turn it off; NPC routines (M3) will too |
| `escalate_below` | 0.8 | LLM escalation + clarify threshold for irreversible actions |
| `clarify_below` | 0.65 | below this even reversible guesses are offered, not run |
| `risk_xp_steps` | (100, 1000) | verbal_scaled: xp < 100 → poor/even/good; < 1000 → 5 words; else "roughly N in 10" |
| `llm_model` / `llm_effort` | `claude-opus-5-5` / `low` | **OPEN DECISION 16**: Opus is the quality default; the brief's ≈$0.10/player-hour target likely needs a cheaper model for decide/narrate — measure with `python -m harness.eval --claude` and the `model_calls` table before switching |

Requests to Claude use structured outputs (`output_config.format` json_schema; forced `tool_choice` is rejected by
current models), a cached system prompt, and server-side refusal fallback (`fallbacks: "default"`). A refused or
truncated response is treated as not understood.

## 10. Part 2 brief (`BRIEF_PART2.md`): contradictions and proposed resolutions

| # | Conflict | Proposed resolution (not yet built) |
|---|---|---|
| 1 | P2 §1 "traveller appears on the world map along the route" vs P1 §9 "never live tracking" | map shows your own position and caravans you know of; everyone else only via fading "last seen" circles |
| 2 | P2 §2.2 offline agent keeps your character trading vs P1 §10/§11 offline = out of the world | new status `agent` (perceives + trades inside a safe zone, protected from crimes like offline chars); decide if shops can be robbed while owner is an agent |
| 3 | P2 §1 caravan journeys continue offline vs P1 §11 logout only in safe places | explicit exception: an escorted caravan counts as a safe location |
| 4 | P2 §11 step 5 (playable first street with juice/dice animation) precedes step 6 (web client shell) and the server was planned for M5 | a minimal server + client must exist at step 5; move FastAPI/WebSocket from M5 to step 5 |
| 5 | P1 OPEN DECISION 7 (fresh "look around" image costs half a turn) assumes generated images; live 3D always shows the scene | drop it; the renderer may only draw `view()` (per-observer) and the half-turn cost stays on the perception roll |
| 6 | P2 §8 generator input needs footprint, windows per side, cosmetic tags; schema has a tier with a window count only, and the tavern has no building record | extend `buildings`/`housing_tiers` (footprint, per-side windows, tags) and give every building a record; windows become entities (peeking, P2 §10) |
| 7 | P2 §5 "client only renders state pushed by server" — a full scene graph would leak hidden entities over the WebSocket | server pushes per-observer view diffs only; never the location's full state |
| 8 | P2 §2.1 "never wait-or-pay timers" vs 15–30 real-minute walks | travel must roll route events (content), and travel time is a config value |

## 11. Encounters (BRIEF §7) — first slice of build step 5

- **Start:** an `attack`, or a `steal` the victim notices (failure), on a character outside any encounter creates
  `encounters` + two `encounter_members` rows. Each member rolls initiative = d20 + dex mod (logged, purpose
  `initiative`). The opening act happened before turn order; the turn then goes to the top of the order.
- **Join by involvement, not proximity (interpretation, owner may overrule):** whoever acts hostile toward a member,
  or is targeted by one, joins with `joined_round = round + 1`. Bystanders and arrivals stay free, so nobody can
  freeze a room by starting a fight. BRIEF §7's "anyone entering the radius joins" is read as "may join by acting".
- **Order:** `joined_round`, then initiative (high first), then id. Earlier members always act before newcomers.
- **Turn gate (rules.turn_gate, applies to previews too):** a member acts only on their turn; `say`/`talk` are free and
  don't pass the turn; `move` is refused ("flee" alternatives offered); `flee` is the way out (dex check).
- **Leave / end:** dead, offline or no longer at the location → `left_round` set. Fewer than two active members →
  `ended`. If the turn holder leaves, the turn passes on in the order as it stood.
- **Timeout:** `Engine.timeout(encounter_id)`, called by the server when `turn_timer_seconds` runs out: the turn
  holder `wait`s. Logged as an ordinary `cmd` input, so replay needs no wall clock.
- **NPC turns:** after every submit/timeout the engine plays each NPC whose turn it is (`engine/npc.py`): non-guards
  flee at ≤ `npc_flee_below` × max hp, otherwise hit back at their latest attacker; guards attack the most wanted
  member. A choice the rules reject (e.g. the attacker is hidden from it) becomes `wait`. NPC actions are logged
  inputs; replay executes them and never re-runs the policy.
- **Per-observer:** `view()["encounter"]` lists only members the observer can see; a hidden turn holder is "someone".
- `Config.encounters` (default True) is switched off only by the M1 single-action rule tests.
- Not yet: free attack on a failed flee (BRIEF says "may"), guards joining fights they witness (needs NPC routines),
  per-turn real-time timer (server, step 5).

## 12. Player-subscription play: the game as an MCP connector (`connector.py`, `mcp_server.py`)

Players bring their own Claude / ChatGPT subscription; we pay for no model calls. Subscription credentials cannot
legally be used by our code (Anthropic forbids third-party use of Free/Pro/Max OAuth), so the direction is inverted:
the player's app calls **our** tools. The player's assistant is both DecisionModel and Narrator.

- Tools: `look()` → `{scene, perceived}`; `act(actions, confirm=false)` → `{status: done|needs_confirmation|invalid,
  outcomes, you_perceive, earlier, scene}`. Server `instructions` = engine-is-truth rules + `VERB_GUIDE`.
- Same guarantees as §9: the assistant only ever receives its player's scene and its player's engine lines; actions
  are re-validated by `Action.from_dict` and go through `Engine.submit_actions`, so irreversible verbs return
  `needs_confirmation` with the engine's own risk estimate (worded with labels the player knows, never ids); the
  assistant must ask the human before resending with `confirm=true`. Encounters' turn gate applies as for anyone.
  It can mis-narrate to its own player, never change the world beyond the whitelist.
- Refs are **stable per player** (`c1`, `c2`… assigned on first sight), because someone may arrive between look and act.
- Lines other players perceive go to an in-memory per-player inbox, delivered on their next look/act.
- `Game` serializes all engine access with a lock (single authoritative writer); the SQLite connection allows
  cross-thread use for that reason. `Engine.open(path)` continues a persistent world.
- ponytail: one player per process, no auth. M5: MCP OAuth → token → character id, one server for all players.
