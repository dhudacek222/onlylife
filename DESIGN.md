# ReadyOne — Architecture & Milestone 1 Contract

## 1. Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11 | per brief; stdlib covers M1 entirely |
| Storage | SQLite (stdlib `sqlite3`, WAL) now → Postgres at M5 | single file, transactional, zero deps. Schema avoids SQLite-only features except triggers (Postgres has equivalents) |
| Concurrency model | **One authoritative writer per world.** Every action runs in one `BEGIN IMMEDIATE` transaction | 150 entities/world is tiny; serialising actions removes whole classes of dupe/race bugs |
| Server (M5) | FastAPI + websockets, one world process | not in M1 |
| AI (M2+) | `typing.Protocol` interfaces: `DecisionModel`, `Narrator`, `Storyteller`, `ImageGen` | swappable, never touch DB |
| Tests | pytest | installed |
| Dependencies in M1 | **none** beyond stdlib + pytest | |

## 2. Module boundaries

```
engine/
  config.py    Config dataclass: all tunables + OPEN DECISIONS (section 4)
  db.py        SCHEMA (DDL + integrity triggers), connect()
  dice.py      Dice: seeded, counter-based, every roll logged; probability helpers
  actions.py   Verb metadata (irreversible? hostile? crime?), Action, Roll, Result dataclasses
  parser.py    M1 hardcoded parser: text -> list[Action]  (replaced by DecisionModel in M2)
  world.py     ONLY module that writes world tables. Read queries + the consequence WHITELIST
  rules.py     Deterministic resolution per verb: prerequisites, DCs, modifiers, dice -> whitelist calls
  engine.py    Engine facade: submit/advance/view/replay, transaction per action, template text per observer
  fixtures.py  Demo world ("Mill Street") used by tests and the REPL
  __main__.py  Tiny REPL: python -m engine
tests/
```

Dependency direction (no cycles): `engine → rules → world → db`; `rules → dice, actions, config`; `parser → actions`.
**No AI module may import `world`.** M2's harness hands structured `Action`s to `engine`, exactly like the hardcoded parser does.

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
- `characters(id PK, name, is_npc, role TEXT NULL ['guard','merchant',…], location_id, status ['online','afk','offline','dead'], hp, max_hp, xp, coins INT CHECK ≥0, stats JSON {str,dex,con,int,wis,cha} as scores, skills JSON {stealth,perception,sleight,athletics,lockpicking,…} ints, skill_points, face_shape TEXT (immutable trigger), appearance JSON {hair,clothes,…}, wanted_level INT, hidden INT, hidden_since INT NULL, stealth_total INT NULL)`
- `reputation(character_id, scope, value, PK(character_id,scope))`
- `items(id PK, type, name, aliases JSON, properties JSON, price INT NULL, location_id NULL, holder_id NULL, flags JSON)` — CHECK exactly one of `location_id`,`holder_id` non-null. **DELETE forbidden by trigger.**
- `provenance(id PK AUTOINC, item_id, kind ['created','bought','sold','gifted','given','dropped','taken','stolen','looted','traded','transformed'], from_id NULL, to_id NULL, location_id, time, event_id NULL)` — append-only (UPDATE/DELETE forbidden).
- `events(id PK AUTOINC, time, actor_id, verb, target_id NULL, item_id NULL, location_id, outcome, crime NULL, data JSON)` — append-only.
- `perceptions(event_id, observer_id, detected INT, recognized INT, appearance_seen JSON NULL, roll_id NULL, PK(event_id,observer_id))` — witness records for every event; append-only.
- `traces(id PK AUTOINC, event_id, kind ['bloodied_item','item_left','forced_lock','purchase','body'], item_id NULL, location_id, detail JSON)` — physical evidence; append-only.
- `VIEW evidence` = events with `crime IS NOT NULL` joined to perceptions + traces.
- `knowledge(id PK AUTOINC, observer_id, subject_id, fact ['aware_of','seen_at','knows_identity','knows_crime'], location_id NULL, time, event_id NULL)` — append-only. Visibility rule: observer sees subject iff `subject.hidden=0` OR an `aware_of` row exists with `time >= subject.hidden_since`.
- `dice_log(id PK = roll counter, time, event_id NULL, actor_id, purpose, sides, raw JSON (both dice if adv/dis), mode ['normal','advantage','disadvantage'], modifier, total, dc NULL, success NULL)` — append-only.
- `trades(id PK AUTOINC, from_id, to_id, give_items JSON, give_coins, want_items JSON, want_coins, status ['pending','accepted','declined','failed'], created, resolved NULL)`
- `inputs(id PK AUTOINC, kind ['cmd','advance'], actor_id NULL, payload TEXT)` — everything needed for replay.

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
| sneak | not already hidden | stealth = d20+dex+stealth+cover+crowd+(2 if night and not lit) −2 per visible guard; disadvantage with heavy armor | `hidden=1`, `hidden_since=now`, `stealth_total`; each observer whose passive perception ≥ total gets `aware_of` |
| unhide | hidden | — | `hidden=0` |
| open/close(door) | door here; open requires unlocked | trivial | door state |
| unlock/lock(door) | key item held → trivial; unlock w/o key needs a held `lockpick` item → dex+lockpicking vs lock_dc; no key and no lockpick → **impossible** (missing prerequisite listed) | | door state |
| force(door) | door here, locked | str+athletics vs lock_dc+4 | unlocked+open; trace `forced_lock`; **noisy: everyone in both connected locations detects** |
| talk(target, text) / say(text) | target visible+here | none | event; listeners get `knows_identity` if actor introduces (`text` contains their own name) |
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
eng = Engine.create(path=":memory:", seed=42, config=Config(), world=fixtures.MILL_STREET)
results = eng.submit("player", "take knife and attack bob")   # list[Result]
eng.advance(60)                     # moves global clock, logged in inputs
eng.view("player")                  # dict: what this observer can see right now
eng2 = Engine.replay(fixture, seed, config, eng.inputs())   # identical events + dice_log
```
`Result(action, outcome ['success','failure','impossible','ambiguous','unparsed','skipped'], reason, missing, candidates, rolls: list[Roll], event_id, messages: dict[observer_id, str])` — `rolls` + `reason` make every failure legible (brief §2.9).
