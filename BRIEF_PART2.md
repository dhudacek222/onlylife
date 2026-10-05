# MASTER PROMPT — PART 2: World, Client & Visuals (owner's brief, condensed)

Extends `BRIEF.md` (Part 1). Where they conflict, **Part 2 wins**. All Part 1 principles stay non-negotiable.
Known conflicts and proposed resolutions: `DESIGN.md` §10.

## 0. Overrides of Part 1
- §15 Images: locations are rendered live from data with modular 3D assets; AI images only for portraits, news
  illustrations, bounty posters. No vision verification for buildings (geometry comes from data).
- §15 Hotspots: from the scene graph (every object knows its entity id).
- §11 Online/offline: extended with offline agents and travel rules. §16 Input: extended with the web client.
- §18 Build order: replaced by §11 below.

## 1. Travel & movement
Shared global clock, never accelerated per player; geography is compressed. Inside a town near-instant; town to
town on foot ~15–30 real minutes; horseback 2–3× faster (a horse is an Item: id, provenance, stealable, must be fed);
paid carriage/ship fastest, costs money, can be ambushed. Travel is content: route events weighted by dynamic route
danger (bandits, monsters, merchants, pilgrims with rumors), fed by Storyteller/news. Caravan escort is a job.
Logout mid-route: solo only at a roadside inn; inside a caravan the journey may continue offline (guards resolve
ambushes, conservative). Travellers appear on the world map along the route; "last seen" circles still apply.

## 2. Activities, work timers & offline agents
- Activity = data `{id, duration, location_requirement, tool_requirement, skill, output_table, risk_profile,
  interruptible: true}`; dice for quality/quantity; interruptible with partial results; the world keeps running and
  the Zone Agent may inject events. Never "wait or pay to skip".
- Offline agent: free-text standing orders, compiled once by an LLM into if-then rules the player confirms, executed
  in code as an NPC routine. Engine-enforced limits: safe zones only; reversible routine actions from the activity
  whitelist only (uncompilable orders rejected with an explanation); earnings full rate for N hours then diminishing
  plus a daily cap (online must out-earn offline). Login report. Offline players act as extra NPCs.

## 3. Combat & feedback
Turn-based with dice. "Shake & fidget" juice: work strokes, lunges, hit shakes, floating damage numbers, idle
breathing. The dice roll is the main animation (slow-down, sound, natural 20/1 emphasis). Tweens (GSAP or similar).

## 4. World bible
Factions (crown, guilds, church, underworld, outsiders) with goals/rivalries/resources; scarce resources; open
mysteries seeded into dialogue/rumors. Settings are configuration packs. Story surfaces: news board, chronicle,
wanted/bounty posters.

## 5. Web client (mobile-first PWA)
Mobile: scene on top, narration feed, contextual buttons + text input, slide-up panels (map, inventory, character,
news). Desktop: map | scene + narration | character/inventory/news. Irreversible-action confirmation with verbal
risk scaled by experience. WebSocket; client never authoritative. Suggested React + Three.js (orthographic
isometric camera), renderer behind an interface. Map levels: world (regions, routes, danger), town, location (live 3D,
clickable). Fog of war tied to the knowledge table; map knowledge tradeable. Overlays: own position, fading "last
seen" circles, bounties, caravans.

## 6. Visual direction
Baldur's Gate / RuneScape seriousness, not cute. Quality from lighting (time-of-day grading, window glow, fireplaces,
soft shadows), density & composition, material variety & wear, ambience. Muted palette. Instancing, KTX2, glTF
optimisation, merged static geometry; must run on mid-range phones. OPEN DECISION: live 3D (default) vs pre-rendered
isometric sprites; keep the pipeline compatible with both.

## 7. Assets & licensing
Base: Quaternius CC0 (Medieval Village MegaKit, Fantasy Props MegaKit, Universal Base Characters, Modular Character
Outfits – Fantasy, Universal Animation Library 1+2; one shared skeleton). Prefer CC0. **No Synty.** Any non-CC0 asset
needs an `ASSETS.md` note (source, license, allowed uses, derivation/AI permitted?). Never feed non-CC0 assets to
generators/AI/training. `ASSETS.md` is the single registry. Gap: serious monsters.

## 8. Procedural asset generator ("style DNA")
`style_dna.json` (grid, wall heights, palette/atlas, materials, proportions, bevel/wear, roof types, window/door
modules). Building generator first: DB building record (tier, footprint, windows per side, door, lock, cellar,
cosmetic tags, wealth_display) → modular building exterior + interior + entity ids per clickable part; counts always
from data; wear/colour/upgrades/damage as parameters. Then interior generator, then bpy scripts for new modules,
AI image-to-3D only as an approved last resort, a few hand-made landmarks per town. Every generated asset registered
with its parameters for deterministic regeneration.

## 9. AI imagery (limited)
Portraits (once at creation from a canonical reference, regenerated on major changes), news illustrations, bounty
posters from the portrait. One fixed style guide.

## 10. Lessons from `crooked-tankard.html`
Interior footprint = building footprint; windows from one record; peeking reports real counts; state changes are
visible immediately; crime → confirmation → dice → witness → dialogue reflects it; a tiny parser was enough.

## 11. Build order (replaces Part 1 §18)
1. Core state + rules. 2. Harness. 3. Asset pipeline spike (Quaternius glTF in Three.js, orthographic camera, dusk
lighting, one tavern exterior + interior, mobile performance; decide live 3D vs sprites). 4. Building generator v1.
5. First street, playable single-player (NPC routines, encounters, stealth, law, activities with timers, juice + dice
animation). 6. Web client shell (layouts, map levels with fog of war, news board). 7. Multiplayer (3–5 friends,
offline agents). 8. Travel. 9. Storyteller + news + gossip, monsters/contracts, portraits and posters.

## 12. Open decisions
Live 3D vs sprites (default live 3D); travel durations/time compression; offline earnings curve and caps; death rule
details; risk display (default verbal, scaled); monster asset source.
