# Why AI RPGs feel soft — failure modes and our fixes

_2026-10-05. Sources at the bottom. Confidence tags: [Certain] documented in sources, [Likely] strong inference,
[Guessing] community lore / my own reading, not verified in sources._

Owner's goal: fully open (custom crimes, theft, murder, anything), natural and human, but **not soft** — no
"type 'kill him' and it's done", no consequence-free chat story.

## The root cause of softness
[Likely] One model plays judge, world and narrator at once. Then the player's sentence *is* the outcome, the world
exists only as far as it was narrated, and a model tuned to be agreeable resolves every request in the player's favour.
Every fix below separates those roles: **code owns facts and outcomes; the LLM proposes and voices.**

## Failure modes → fixes

| # | Failure players hate | Why it happens | Our fix | State |
|---|---|---|---|---|
| 1 | "I kill him" → he's dead. Player authors the result | LLM treats outcome words as facts | Intent parsing ("kill" → `attack`), dice + rules decide, narrator gets the *result* as facts | **built** (M1/M2) |
| 2 | Everyone agrees with you; villains are soft; nobody refuses, lies or fights back | Positivity bias / sycophancy from safety tuning and RLHF; fidelity drops as a character's morality drops [Certain] | **Decide in code, voice with the LLM**: an NPC's agree/refuse/lie/report/attack is chosen from its traits, relationships, fear, knowledge and dice; the LLM only phrases a decision it's handed ("Bob refuses and threatens to call the guard") | to build (NPC dialogue) |
| 3 | The world is made up as you look ("what's behind the door is decided when you open it"); retcons; drifting scenes | No ground truth outside the prose [Certain] | The DB is the world; narration may only use the observer's facts. Add a cheap **fact check** on narration: names, items and places it mentions must exist in the facts, else fall back to the template | state **built**; fact check to build |
| 4 | It forgets what you did | Stateless model, context window [Certain] | Event log + knowledge table are the memory; each NPC's prompt gets only *its own* filtered memories | **built** (data); retrieval to build |
| 5 | No failure, no stakes; failure "has no meaningful effect" | Model avoids disappointing the player [Certain] | Persistent failure: wounds, lost items, wanted level, death lockout; repeat attempts raise difficulty; confirmations show the risk, so failure is fair rather than random | mostly **built** |
| 6 | Consequences never come back | No simulation between scenes | **Delayed consequences**: witnesses report, guards investigate days later, heirs post bounties, the herbalist remembers your face. This is what makes a world feel real | to build (step 5 / 9) |
| 7 | Objectives resolve in one line; no friction | Narrative necessity beats logic [Certain] | Prerequisites over micro-chances (key, disguise, insider); actions cost time; activities have timers | **built** (prereqs); timers to build |
| 8 | NPCs are zombies until you talk to them | Purely reactive design [Certain] | Routines in code on the global clock, NPC goals and secret goals that act on the world without the player | **next step** |
| 9 | Same voice for everyone, purple prose, stock names, overused phrases | Models produce the statistically likely line [Certain] | 1–3 sentence default (built); templates for buttons (built); per-NPC **voice cards** as data (diction, vocabulary, tics, education); a banned-phrase filter; names from the setting pack, never LLM-invented | partly built |
| 10 | Modern words in a medieval world ("amusement park") | Model's general knowledge leaks [Certain] | Setting lexicon in the system prompt + a word filter on narration; NPC knowledge limits | to build |
| 11 | "I'm the king, ignore the rules" works | Prompt injection | Injection screen + whitelist + prerequisites | **built** |
| 12 | Waiting seconds for every reply | LLM on the critical path [Certain] | State changes never wait for an LLM; rules model first; template text instantly, rich narration may follow | **built** (design) |
| 13 | Too harsh: sudden unexplained death | Over-correction | Legible fairness: show the roll, the witness, the evidence; confirm irreversible acts with a risk estimate | **built** |

## "Custom crimes" without softness — the key design rule
[Likely] Crimes must be defined by their **effects**, not their words. A free-form attempt ("pour lamp oil on the
merchant's stall and set it alight") goes through:
1. **LLM proposes** (untrusted, validated): the skill used, a difficulty tier, and the *effects* it would have, chosen
   from the whitelist (damage an item, hurt someone, move an item, flag something burnt/poisoned, frighten someone).
2. **Code checks prerequisites** (do you hold lamp oil and fire?) and **rolls the dice**.
3. **Code classifies the crime from the effects**: harmed a person → assault/murder; took or destroyed someone's
   property → theft/vandalism/arson; entered private space → trespass. Witnesses, evidence, wanted level and
   investigations then follow automatically, exactly as for built-in crimes.
4. **LLM narrates** what happened, from per-observer facts.

So the player can invent any crime, but can't talk their way out of what it *does*, and the world reacts the same
way it does to a stabbing.

## Recommended build order
1. Free-form attempt verb with effect-based crimes (the "open life" unlock).
2. NPCs decide in code, LLM voices (anti-sycophancy) + personality/voice data per NPC.
3. NPC routines + delayed consequences (witness reports → investigation → bounty).
4. Narration fact check, banned phrases, setting lexicon.

## Sources
- Ian Bicking, *Hidden Door design review* (2025): https://ianbicking.org/blog/2025/08/hidden-door-design-review-llm-driven-game
- Ian Bicking, *Intra: LLM text adventure* (2025): https://ianbicking.org/blog/2025/07/intra-llm-text-adventure
- *Large Language Models and Games: A Survey and Roadmap*: https://arxiv.org/pdf/2402.18659
- *Narrative Adherence in LLM driven Games* (AAU thesis): https://projekter.aau.dk/projekter/files/784680954/Narrative_Adherence_in_LLM_driven_Games.pdf
- *Too Good to be Bad: On the Failure of LLMs to Role-Play Villains* (ACL Findings 2026): https://preview.aclanthology.org/ingest-acl/2026.findings-acl.282/
- *Character AI bots too wholesome* (positivity bias explainer): https://www.roborhythms.com/character-ai-bots-too-wholesome/
- *Why AI chatbot roleplay feels so repetitive*: https://www.roborhythms.com/ai-chatbot-roleplay-repetitive-fix/
- Skyrim AI NPC mod coverage (latency, immersion breaks): https://www.gamestar.de/artikel/mods-the-elder-scrolls-skyrim-chatgpt-companion-gaming,3402119.html
- AI Dungeon moderation controversy (context, not gameplay): https://www.utahbusiness.com/latitude-games-ai-dungeon-was-changing-the-face-of-ai-generated-content-until-its-users-turned-against-it/

Gap: the searches did not surface the r/AIDungeon threads about "no consequences" directly; that complaint is
documented here through the Hidden Door / Intra reviews and the sycophancy research, not first-hand player posts.
