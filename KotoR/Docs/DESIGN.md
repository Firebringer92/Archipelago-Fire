# KOTOR Archipelago Randomizer — Design Doc

**Status: Alpha.** Core pipeline (delivery, detection, options, item
distribution, goal detection) is built, wired, and generation-tested
end-to-end. Live in-game testing has proven that it is working.

This document explains how the whole system fits together and what each
Python file is for.

## 1. What this is

A mod for KOTOR 1 (Steam) that connects a real, running game process to a
real Archipelago multiworld server. Real in-game progress (quest
completions, companion recruitment, area exploration, light/dark alignment
shifts, levels) becomes real Archipelago location checks. Items
received from the multiworld (skills, companions, abilities, gear, XP,
credits, class changes) get applied live, in-game, without needing a save
edit or a second launch.

## 2. The moving pieces, top to bottom

```
 Archipelago server (MultiServer.py, unmodified upstream)
        |  network protocol (items, location checks, DeathLink, goal status)
        v
 KotorClient.py  (this project's AP client)
   ├─ kotor_extender_bridge.py   -- TCP socket to the injected extender
   ├─ kotor_reconciliation.py    -- "what should I have" vs "what do I have"
   └─ kotor_location_tracker.py  -- raw game state -> real location checks
        |  TCP, 127.0.0.1:25586
        v
 extender/src_k1se/ap_extender.c + kse_hook.cpp  (merged proxy DLL, injected into swkotor.exe)
   ├─ K1SE's dispatcher-hook mechanism, merged directly into this build (not a
   │  separate third-party mod any more -- see README.md's install steps)
   ├─ tails kse.log for AP|... marker lines -> EVENT: over the socket
   ├─ receives APPLY:/APPLYVALUE: commands from the client
   └─ shells out to scripts/arm_orchestrator.py to arm the right areas
        |  regenerates + recompiles + deploys NWScript to Override
        v
 In-game NWScript (auto-generated, deployed to Override)
   ├─ ap_poll_shared.nss    -- the shared "brain," polls everything, reports via KSE_Diag
   ├─ area trampolines      -- preserve original OnEnter, call the brain, carry pending grants
   ├─ ap_heartbeat.nss      -- keeps polling alive independent of area transitions
   └─ suppression wrappers  -- companion/store/item-suppression preserve-and-chain scripts
        ^
        |  built from real game data (RIMs, 2DAs, journal, dialogue)
 scripts/*.py  (dev-side generators, patchers, and one-off research tools)
```

**K1SE (KOTOR Script Extender)'s real, MIT-licensed source is merged
directly into this project's own compiled extender** (`extender/src_k1se/`)
rather than installed as a separate third-party mod. This project's own native additions 
(like`KSE_SetCreatureField`, used by the `companion_class` companion feature)
sit alongside K1SE's original dispatcher-hook code in the same build,
using the same hijacked-opcode mechanism K1SE itself pioneered.

## 3. Design principles that explain a lot of otherwise-odd code

- **The game never remembers "have I already reported this."** Custom
  (non-`globalcat.2da`) global variables don't persist in this engine
  build — confirmed the hard way. So every poll reports *current truth*
  unconditionally, and the Python client (real, persistent storage) is
  the only place "is this new" gets decided. This is why so much of
  `ap_poll_shared.nss` looks stateless and so much of the client-side code
  is about dedup.
- **Delivery only ever rides a native engine event**, never
  `ExecuteScript` to a resref whose content changes mid-session
  (`ExecuteScript` caches bytecode per-process forever). That's why
  delivery works by regenerating area *trampolines* themselves (native
  `OnEnter`), not by writing into some fixed "mailbox" script.
- **Arming is proximity-based, not global.** Only the player's current
  area and its direct neighbors carry the pending batch — see
  `arm_orchestrator.py`. This keeps each individual trampoline small and
  avoids constantly touching all ~78 covered areas.
- **Reconciliation is deficit-only**, except XP and Credits under specific restrictions
  which is a bidirectional clamp (it has to suppress vanilla combat/quest XP, not
  just top up).
- **Only ~10 items are ever unconditionally guaranteed** in the pool (the
  9 companions, when `companion_mode` is `ap_gated`) — everything else
  (gear, Skills, Abilities, EXP, Credits) is drawn through a weighted
  7-category distribution (`item_distribution_type`), not a fixed
  guaranteed list. See `Options.py`'s `ItemDistributionType` docstring.
- **Real game data drives content generation, not hand-transcription.**
  Journal completion values, companion recruit scripts, door/trigger
  destinations, area OnEnter hooks — all discovered by scanning actual
  compiled scripts/RIMs/2DAs via `pykotor`, not guessed or hand-typed.
  Several early research scripts exist specifically because a
  hand-transcribed version turned out to be wrong.

## 4. File-by-file breakdown

### 4.1 The Archipelago world (`Archipelago/worlds/kotor/`)

- **`__init__.py`** — the `KotorWorld` class AP's generator actually
  calls: builds regions (`create_regions`), builds the item pool
  (`create_items`, `_distribute_items`, `_gear_category_pools`,
  `_skill_ability_pools`), builds `slot_data` (`fill_slot_data`) for the
  client to read on connect, and wires in `EntranceRando`/`Rules` when
  their options are on. This is where the weighted item-distribution
  system actually lives.
- **`Options.py`** — every player-facing setting (`KotorOptions`
  dataclass) with full docstrings. `STARTING_ABILITY_ARMS`/
  `STARTING_SKILL_ARMS` map arm names to their matching starting-boost
  option, shared with `__init__.py`.
- **`Items.py`** — `item_table`: every AP item (skills, companions,
  abilities, class switches, XP/credits filler) plus gear items loaded at
  runtime from `gear_items.json` (only rows flagged `included_as_item`
  get a real AP code). Exports `arm_name_to_item`, `item_name_to_id`,
  `lookup_id_to_name` as the single source of truth other files import
  rather than rebuild.
- **`Locations.py`** — `location_table`: all 200 real locations (100
  journal, 9 companion, 78 area, 13 alignment). **Auto-generated by
  `scripts/generate_kotor_locations.py`** — never hand-edit this file.
- **`Rules.py`** — `set_rules` (access rules; currently flat/ungated,
  real story-order gating is future work) and `set_completion_rules` (a
  deliberate no-op — the real Goal signal is entirely client-driven via
  `KotorClient.py`'s `_check_goal`/`finished_game`, independent of AP's
  own completion-condition machinery).
- **`EntranceRando.py`** — door/trigger randomization, built on
  Archipelago's own `entrance_rando.py` engine, run in uncoupled mode.
  Builds a separate physical-module region graph purely for this purpose
  (doesn't touch the thematic regions that govern location access). A
  custom `_ensure_reciprocal_pairing` post-pass forces at least one B->A
  edge for every placed A->B pair (not real AP `coupled` mode -- that
  needs matched-by-name reverse entrance/exit pairs this flat
  156-transition data model doesn't have), so a shuffled door reliably
  has some way back without needing that bigger data-modeling effort. See
  its own module docstring

### 4.2 The Python AP client (`Archipelago/` root)

- **`KotorClient.py`** — the actual client entry point (`KotorContext`,
  `launch()`). Receives items from the server and forwards them to the
  extender (`_deliver_item`/`_do_deliver`, with `HEAVY_ARMS`/
  `companion_class:` serialized one-at-a-time through a single choke
  point, `_queue_heavy()`, to avoid a confirmed crash class -- every real
  entry point that can trigger a heavy send, including the `!ap_apply`
  admin bypass and the `companion_mode=normal` auto-grant, funnels through
  it, not just the real-item path); watches extender events and turns
  them into real `LocationChecks` sends (`_on_extender_event`, via
  `kotor_location_tracker`); detects the configured Goal condition live
  and sets `finished_game` (`_check_goal`); runs the GUI status tab. Also,
  on every `Connected`, calls `scripts/generate_poll_shared.py` directly
  (`regenerate_poll_shared()`, a blocking subprocess in a
  `run_in_executor`) with the ACTUAL connected seed's `area_randomizer`,
  recompiling and redeploying `ap_poll_shared.ncs` straight to the live
  Override so it always matches the seed being played rather than
  whatever was baked into a prebuilt `dist/Override` at packaging time
  (see 4.3's packaging note). `!ap_regen_poll` is the manual fallback.
  Same pattern, same call site, for the Dantooine make-jedi suppression
  wrapper (`regenerate_makejedi_suppressor()`, with the connected seed's
  `starting_class`; `!ap_regen_makejedi` is its manual fallback) -- see 4.3's
  `generate_makejedi_suppressor.py` entry.
  New-character safeguard (`_evaluate_character_safety`, 2026-09-02):
  pauses every delivery/reconciliation action if the connected
  character's name has never appeared in the delivery log AND they're
  above level 1 (a real level-1 character is always waved through
  automatically) -- protects against silently dumping the full delivery
  backlog onto an unexpected character (wrong save loaded, etc.).
  `!ap_confirm_character` overrides it once a human confirms. See
  `TESTING.md`'s "New-character safeguard" section.
- **`kotor_extender_bridge.py`** — owns the raw TCP connection to the
  injected extender (127.0.0.1:25586) and the wire protocol
  (`APPLY:`/`APPLYVALUE:`/`EVENT:`/`STAGED:`/`ERROR:`), plus a
  delivery-tracking table so the GUI can show queued-vs-confirmed status.
- **`kotor_reconciliation.py`** — `ReconciliationTracker`: the
  "client-authoritative" half. Tracks what the player *should* have
  (from received items, or for `ap_limited` XP, live from
  `checked_location_count`) against what the game *currently reports*,
  and sends corrective `APPLY`/`APPLYVALUE` calls to close any deficit.
  Deliberately scoped to safely-repeatable additive grants only (skills,
  credits, the two idempotent companion adds) plus the special XP clamp.
- **`kotor_location_tracker.py`** — `LocationTracker`: turns raw
  `CHECK|JOURNAL`/`CHECK|COMPANION`/`CHECK|AREA`/`ALIGNMENT` events into
  real AP location IDs, reading `ctx.checked_locations` as the single
  source of truth for "already checked" rather than keeping a second
  set. Also owns alignment-crossing detection and `true_balance_reached()`
  for the Goal system.

### 4.3 Dev/build tooling (`scripts/`)

**Live pipeline — NWScript generators** (produce content deployed to
Override; re-run after changing their inputs):
- `generate_poll_shared.py` — the shared polling "brain" (quest flags,
  plot trackers, journal, XP/credits/skills/abilities/classes, alignment,
  Malak-defeat goal check, character level, death, self-healing heartbeat
  restart).
- `generate_area_trampolines.py` — one trampoline per covered
  area/`OnEnter` resref, preserving the real original script.
- `generate_heartbeat.py` — the persistent 5s self-rescheduling tick.
- `generate_trampoline_batch.py` — regenerates a specific area's
  trampoline with the current pending arm batch inlined (`APPLIES`
  table, kept in sync with `dllmain.c`'s `AP_ARM_NAMES` by hand).
- `generate_companion_suppressors.py` / `generate_store_suppressors.py`
  — preserve-and-chain wrapper pairs for companion recruitment and store
  markers.
- `generate_makejedi_suppressor.py`  — same preserve-and-chain
  pattern, for Dantooine's real "become a Jedi" trial-completion script
  (`k_pdan_makejedi`). Confirmed via `read_ncs()` that the vanilla script
  calls `AddMultiClass()` unconditionally on trial completion, completely
  bypassing `StartingClass`'s item-gating (`jedi_granted` mode) if left
  unsuppressed -- a player who simply plays Dantooine normally would get
  the Jedi class for free. Skips the vanilla script entirely whenever
  `starting_class != off` (the real grant comes from `class_guardian`/
  `class_consular`/`class_sentinel` instead); confirmed safe to skip
  wholesale by tracing every global it touches (`DAN_EXTRA`/
  `DAN_EXTRA_XP`/`DAN_EXTRA_XP2` are used nowhere else in the game;
  `DAN_PATH_STATE` is only ever READ here, never written, so nothing
  downstream can be corrupted) and confirming its Bastila/Carth/
  lightsaber-resref/`dan_wanderhound` block is cosmetic cutscene setup,
  not an item grant (no `CreateItemOnObject` anywhere near it).
  `KotorClient.py` regenerates/redeploys this on every `Connected` with
  the real connected seed's `starting_class` (`!ap_regen_makejedi` is the
  manual fallback), same pattern as `ap_poll_shared.ncs`.
- `build_area_graph.py` / `build_door_graph.py` — static connectivity
  data: which covered areas are directly reachable from which (used for
  arming neighbors), and the full 156-transition door/trigger graph (used
  by `EntranceRando.py`).
- `generate_kotor_locations.py` — generates `Locations.py` from
  `questtagmapping.json`/`areatodisplaymap.json`  built
  from the now-removed journal-scan scripts), a hardcoded companion list,
  AND all 33 alignment/level/goal locations (10 alignment
  thresholds, 3 alignment-bonus checks, 19 character levels, 1 Malak-
  defeated) via fixed constants at the top of the file. Covers all 220 real locations

**Live pipeline — runtime orchestration:**
- `arm_orchestrator.py` — invoked by the extender's C code on every
  relevant event; computes the armed set (current area + graph
  neighbors), regenerates newly-in-scope areas, clears out-of-scope ones.

**Live pipeline — per-seed, game-file-level patchers** (not part of
NWScript generation; directly rewrite RIM files for one specific
generated seed, gated on that seed's options):
- `patch_item_suppression.py` — wires `Mod_OnAcquirItem` (RIM edit for
  ~106 modules with an empty slot; Override-wrapper for 11 with an
  existing vanilla script) to handle non-whitelisted pickups per the
  seed's single `loot_mode` option (`Options.py`'s `LootMode`), one of 4
  modes (normal/destroy/bonus/replace). Both `replace` AND `bonus`
  (redesigned 2026-08-31, superseding an intermediate heartbeat-scan
  version) guard on the same shape of fix: a per-tag HELD-QUANTITY delta
  against `KSE_SetData`, checked once per real `Mod_OnAcquirItem` EVENT
  rather than on any kind of timer -- immune to the engine's own item-
  reacquisition re-firing by construction, since a spurious re-fire
  produces zero quantity delta for that one tag. `replace` destroys +
  immediately grants a 1:1 swap; `bonus` feeds the genuine delta into a
  persistent `pickup_running_count` and grants one item every time that
  crosses a multiple of 5, aggregate across all suppress-eligible tags
  combined. `replace`/`bonus` each
  generate their own `GetRandomLootItem()` NWScript function (a flat
  `Random(N)`-indexed if/else chain over the real 577-item
  `shop_randomize` pool) in their respective files, kept in sync by hand
  since they're separate generated `.nss` files. The RIM edit for
  empty-slot modules only ever needs to happen once regardless of mode
  (it just points at a fixed shared resref); only that resref's Override
  *content* changes per mode. Falls back to precompiled copies (one per
  non-skip mode) when `nwnnsscomp.exe` isn't present, so a tester's
  machine doesn't need the compiler.
- `patch_door_randomizer.py` — rewrites each shuffled transition's
  `LinkedToModule`/`LinkedTo` GFF fields to match the seed's computed
  mapping. No compiler dependency at all (pure GFF field edits).

**Distribution/packaging** (for getting a fresh install running without
the full dev toolchain — see `README.md`):
- `package_dist.py` — collects the always-on generated Override content
  into `dist/Override/`, deriving the exact file list from the generator
  scripts' own data so it can't silently drift.
- `setup_game.py` — tester-facing: copies `dist/Override/` into a real
  install. Pure standard library, no `pykotor`/compiler needed.
- `package_apworld.py` (2026-08-31) — packages `Archipelago/worlds/kotor/`
  into a single, version-stamped `dist/kotor.apworld` (Archipelago's
  standard world-distribution format, via `worlds.Files.APWorldContainer`)
  for testers to drop into `Archipelago/custom_worlds/`. Exists because
  `Generate.py` itself is stock, unmodified Archipelago (verified via
  `git diff` against the tracked upstream commit) -- the ONLY thing that
  determines a KOTOR seed's actual content is `worlds/kotor/` itself, and
  `KotorClient.py` also imports directly from it at connect time (e.g.
  `Items.py`'s `item_table`). Whoever generates a seed and whoever
  connects to play it must be running the exact same `kotor.apworld`
  version -- this is the file a GitHub Release pins to guarantee that,
  instead of everyone's loose `worlds/kotor/` folder hopefully matching.


### 4.4 The extender (C/C++, not Python — `extender/src_k1se/`)

Compiles to a single merged `binkw32.dll` (`ap_extender.c` + K1SE's own
merged `kse_hook.cpp`/`dllmain.cpp`/`log.cpp`, plus MinHook, built by
`extender/build.ps1`) that forwards every real Bink export straight
through to `binkw32_real.dll` (see `README.md`'s install steps — there is
no separate K1SE mod to chain under any more). Runs a local TCP server
(127.0.0.1:25586), tails `kse.log` for `AP|...` marker lines and relays
them as `EVENT:` lines, and handles incoming `APPLY:`/`APPLYVALUE:`
commands by shelling out to `arm_orchestrator.py`. `AP_ARM_NAMES[]` is the
authoritative arm-ID table, kept in sync by hand with
`generate_trampoline_batch.py`'s `APPLIES`
