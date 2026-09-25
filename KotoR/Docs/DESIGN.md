# KOTOR Archipelago Randomizer — Design Doc

**Status: Alpha.** Core pipeline (delivery, detection, options, item
distribution, goal detection) is built, wired, and generation-tested
end-to-end. Live in-game testing has proven most of it, including a
2026-09-08 live-test pass that confirmed Traps (all 12), Additional
Feats (PC and companion), and the Tatooine shop-catalog fix — see
`DEVELOPMENT_HISTORY.md`'s "Live-test pass" subsection for the real bugs
that pass found and fixed. **One feature remains code-complete but NOT
yet live-tested at all**: the redesigned Progression System's artificial
travel-gate (§4.1's `Rules.py` entry) — by the user's own 2026-09-08
call, gate verification is left to natural playthrough/testers rather
than forced via console warp, since warping bypasses the unlock sequence
the feature is built around. Additional Enemies is feature-complete and
*partially* live-tested (both extreme modes confirmed across 3 modules;
`random_sane` specifically not yet exercised, and per the user's own
2026-09-08 call, 3/3 correct modules is treated as working-as-intended
rather than grounds for exhaustive per-module testing). See
[DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) for the consolidated
technical history (feature decisions, confirmed capabilities, and every
engine limitation found) that this doc summarizes, or the individual
phase-by-phase logs archived at

This document explains how the whole system fits together and what each
Python file is for. It does not re-derive the engine-constraint discoveries
that shaped this design — see
[DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md)'s engine-limitations
section

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
- **Reconciliation is deficit-only**, except XP under
  `experience_mode` (when not `off`), which is the one deliberately
  bidirectional clamp (it has to suppress vanilla combat/quest XP, not
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

**Code comment conventions** (standard set 2026-09-16, applies going
forward — most of the codebase predates this and is being brought in line
gradually, not all at once):
- A comment explains what the code does, why (when non-obvious), and any
  real dependency the reader needs to know about — nothing else.
- No dates, no "(YYYY-MM-DD)" stamps, no "found live," no session
  narrative. Git history already has the timeline; a comment isn't the
  place to re-derive it.
- If a decision needs real justification (an engine limitation, a design
  tradeoff, a rejected alternative), that justification belongs in this
  document or `DEVELOPMENT_HISTORY.md` — the comment should be a short
  pointer to it (e.g. "see DESIGN.md §5.2, `OnOpen` never fires in this
  engine build"), not a restatement of the investigation inline.
- Don't reference internal-only files a GitHub reader won't have
  (`FutureDesign.md`, the memory-file notes, a specific past chat) —
  point at `DESIGN.md`/`DEVELOPMENT_HISTORY.md`/`docs/history/PHASE*.md`
  instead, since those actually ship with the repo.

## 4. File-by-file breakdown

### 4.1 The Archipelago world (`Archipelago/worlds/kotor/`)

- **`__init__.py`** — the `KotorWorld` class AP's generator actually
  calls: builds regions (`create_regions`), builds the item pool
  (`create_items`, `_distribute_items`, `_gear_category_pools`,
  `_skill_ability_pools`), builds `slot_data` (`fill_slot_data`) for the
  client to read on connect, and wires in `EntranceRando`/`Rules` when
  their options are on. This is where the weighted item-distribution
  system actually lives. Guaranteed-placement pool: the 9 companions
  (`companion_mode=ap_gated`), the 8 Progression System quest items
  (`progression_system` on), and the 12 Traps items (`enable_traps` on)
  are the only items ever unconditionally placed — same
  `mandatory_names` pattern for all three, everything else drawn through
  the weighted distribution. `PLANET_MODULE_PREFIXES` maps each of the 6
  planets to its module-name prefix for `_shop_stock()`'s per-planet
  catalogs — Tatooine (`"tat_m"`) was missing entirely until 2026-09-08
  (see `DEVELOPMENT_HISTORY.md`); a dev-tooling duplicate of this same
  dict, `_PLANET_PREFIXES` in `scripts/generate_trampoline_batch.py`, has
  to be kept in sync by hand (the two live in separate processes — see
  4.3's note — so they can't just share one Python object).
- **`Options.py`** — every player-facing setting (`KotorOptions`
  dataclass) with full docstrings. `STARTING_ABILITY_ARMS`/
  `STARTING_SKILL_ARMS` map arm names to their matching starting-boost
  option, shared with `__init__.py`. `ProgressionSystem` (redesigned
  2026-09-08 after real per-item disassembly, see `Rules.py` below),
  `EnableTraps` (new 2026-09-08 — 12 one-time punishment items, see
  `Items.py`/`KotorClient.py` below), and `NewCompanion` (new 2026-09-14
  — the HK-47/Meetra Surik swap, see 4.3's `generate_new_companion_
  assets.py` entry) are the newest option classes; all default off.
  `_companion_class_keys()` (in `__init__.py`, not this file) is a
  runtime-conditional list, not a static edit to `COMPANION_CLASS_KEYS` —
  `new_companion` only makes her eligible for `companion_class`/
  `additional_feats` when it's actually on, so a vanilla-HK47 seed never
  picks up class-randomization/feat items meant for a droid.
- **`Items.py`** — `item_table`: every AP item (skills, companions,
  abilities, class switches, XP/credits filler) plus gear items loaded at
  runtime from `gear_items.json` (only rows flagged `included_as_item`
  get a real AP code). Exports `arm_name_to_item`, `item_name_to_id`,
  `lookup_id_to_name` as the single source of truth other files import
  rather than rebuild. `TRAP_ITEMS` (12 entries, `arm_name`s like
  `trap:cut_max_hp`) all route through one consolidated `trap:<type>:
  <params>` wire action rather than each getting its own native/plumbing
  — see `KotorClient.py` and 4.3's `generate_trampoline_batch.py` entry.
- **`Locations.py`** — `location_table`: all 200 real locations (100
  journal, 9 companion, 78 area, 13 alignment). **Auto-generated by
  `scripts/generate_kotor_locations.py`** — never hand-edit this file.
- **`Rules.py`** — `set_rules` and `set_completion_rules` (the latter a
  deliberate no-op — the real Goal signal is entirely client-driven via
  `KotorClient.py`'s `_check_goal`/`finished_game`, independent of AP's
  own completion-condition machinery). **`Goal`'s `reach_leviathan` option
  (2026-09-17)**: a shorter alternative to `defeat_malak`, detected off the
  same already-tracked "Leviathan: Captured by the Leviathan" journal check
  (no new NWScript/native signal needed). `progression_system` now REQUIRES
  `goal` to be `defeat_malak` or `reach_leviathan` (enforced as an
  `OptionError` at generation time, same mechanism as its existing
  `area_randomizer` incompatibility) — confirmed live that a seed combining
  `progression_system` with `goal=max_level` left 2 of the 4 Star Maps
  permanently unfound, since neither `true_balance` nor `max_level` ever
  requires reaching the Leviathan or later. `set_rules` was largely
  flat/ungated until the Progression System redesign (2026-09-08): real
  per-item disassembly found the 4 star-map quest items are gated by a
  *global flag* (`k_pla_actmap`), not inventory possession, so
  suppressing the item alone wouldn't stop a player from completing the
  vanilla flag first. The fix is an **artificial travel-gate**: `Rules.py`
  now maps every location on each of the 4 star-map planets (via
  `PLANET_AREA_IDX`, cross-referenced against
  `extender/area_trampolines/_mapping.json`) plus companion-recruitment
  and Genoharadan-bounty locations known to occur on those planets
  (`COMPANION_PLANET_OVERRIDE`, `GENOHARADAN_PLANET_OVERRIDE` — the
  latter's Lorgal→Korriban entry is an inference by elimination, lower
  confidence than the other three) back to that planet's own AP star-map
  item, and `add_rule`-gates (AND-combines) every one of those locations
  behind actually holding it. Dantooine and its Desert Map were dropped
  from the item list entirely once disassembly showed neither is a real
  mechanical gate (see `DEVELOPMENT_HISTORY.md`). The other 4 Progression
  items (Sith Armor/Papers, Shield Codes, Enviro Suit) genuinely are
  inventory-gated, so those stay suppressed at the source instead (see
  `gear_items.json`'s `progression_suppression` flag and 4.3's
  `apply_progression_checkpoint_wrappers`) — `Rules.py`'s new gating
  logic only covers the 4 star maps.
- **`launch_kotor_client()` + its `Component(...)` registration**
  (2026-09-08, top of `__init__.py`) — registers a "KOTOR Client" button
  in the Archipelago Launcher (the `x2wotc`/`tits_the_3rd`-style pattern).
  Doesn't run `KotorClient.py` in-process the way those two do -- its
  `_detect_repo_root()` needs a real folder to walk, which breaks inside
  a zip -- so this reads the install-path marker `install_playerbundle.py`
  writes (`%LOCALAPPDATA%\KotorAP\install_path.txt`) and launches it as a
  subprocess instead. No `KotorClient.py`/helper-module bundling needed
  inside the apworld for this to work, despite an earlier research note
  assuming it would be.
- **`EntranceRando.py`** — door/trigger randomization, built on
  Archipelago's own `entrance_rando.py` engine. `AreaRandomizer`
  (Options.py) picks `off`/`coupled`/`decoupled`; both non-off modes
  share the exact same pool/pairing/repair logic, differing only in the
  entrance type (`TWO_WAY` vs `ONE_WAY`) and the `coupled` flag passed to
  `randomize_entrances` (AP's own reciprocal-placement logic is gated on
  `if self.coupled and ...`, so it's simply inert in decoupled mode).
  Builds a separate physical-module region graph purely for this purpose
  (doesn't touch the thematic regions that govern location access). 110 of
  the 118 randomization-eligible transitions have a genuine,
  individually-identifiable reverse door (matched 1:1, or via a shared
  destination-waypoint-tag suffix for the 4 Dantooine module-pairs with two
  doors each way) and are wired as real Entrance pairs in both modes; the
  remaining 8 (no reverse door anywhere in vanilla data) are left fully
  fixed to their vanilla destination in either mode -- decoupled mode
  reuses the same 110-entry pool rather than also covering those 8, a
  deliberate scope choice to keep the split a small, low-risk change.
  Coupled placement can still leave a rare residual orphan (a module with
  exactly one coupled entrance whose placement failed to get a
  replacement) -- `_repair_orphaned_modules` patches those after
  placement by stealing and repointing a well-connected edge, the same
  technique the old uncoupled-mode `_ensure_full_reachability` used, just
  scoped to the handful of leftover entries rather than the whole graph;
  the same repair pass runs for decoupled mode too, unchanged. See its own
  module docstring for the full reverse-door analysis and reachability
  findings.

### 4.2 The Python AP client (`Archipelago/` root)

- **`KotorClient.py`** — the actual client entry point (`KotorContext`,
  `launch()`). Receives items from the server and forwards them to the
  extender (`_deliver_item`/`_do_deliver`, with `HEAVY_ARMS`/
  `companion_class:` serialized one-at-a-time through a single choke
  point, `_queue_heavy()`, to avoid a confirmed crash class -- every real
  entry point that can trigger a heavy send, including the `/ap_apply`
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
  (see 4.3's packaging note). `/ap_regen_poll` is the manual fallback.
  Same pattern, same call site, for the Dantooine make-jedi suppression
  wrapper (`regenerate_makejedi_suppressor()`, with the connected seed's
  `starting_class`; `/ap_regen_makejedi` is its manual fallback) -- see 4.3's
  `generate_makejedi_suppressor.py` entry.
  **2026-09-08 (the "3-step install" plan, Option B)**: the 3 heavier
  per-seed patch scripts (`patch_item_suppression.py`/
  `patch_door_randomizer.py`/`patch_additional_enemies.py`, plus
  `patch_loot_disturb.py`) are now ALSO auto-invoked on every `Connected`
  -- this is what used to be a separate manual README/TESTING.md step.
  Unlike poll_shared/makejedi (a cheap single-file recompile, safe to
  always re-run), these 4 do a real per-module RIM sweep with no internal
  "already applied" short-circuit of their own, so `_apply_seed_patch_if_new()`
  gates each on `PATCHED_SEEDS_MARKER_PATH` (a small JSON marker recording
  the last seed_name each was actually applied for) so a reconnect to the
  SAME seed skips the redundant sweep rather than re-paying its cost on
  every launch.
  **SEQUENCED, not independent (2026-09-15 fix, real data-loss bug
  closed)**: all 4 share the exact same backup directory
  (`extender/backup/modules/`). `patch_additional_enemies.py`/
  `patch_door_randomizer.py`/`patch_item_suppression.py` always read/write
  the live `.rim` directly (their backup is purely a `--restore`
  snapshot), but `patch_loot_disturb.py`'s module-RIM path is the one
  outlier: it reads FROM the backup instead of live whenever one already
  exists, specifically so a second loot_disturb run doesn't compound its
  own prior edits. Dispatching all 4 as independent, unordered
  `run_in_executor` calls (the original shape) meant they could genuinely
  race as separate OS subprocesses -- if `additional_enemies` happened to
  run first (creating that shared backup as a side effect of placing new
  enemies into a module's live GIT), `loot_disturb` running concurrently
  or after would read that backup -- the PRISTINE, pre-additional-enemies
  state -- and overwrite live with a version that silently erases every
  enemy additional_enemies had just placed. `KotorClient.py` now runs all
  4 sequentially in a single executor task
  (`_apply_module_rim_patches_in_order()`), `loot_disturb` always first,
  closing this off structurally rather than by luck of subprocess timing.
  `/ap_patch_all` (renamed from `!ap_apply_all` 2026-09-15; originally
  2026-09-13, replacing the earlier separate `!ap_apply_item_suppression`/
  `!ap_apply_door_randomizer`/`!ap_apply_additional_enemies` fallbacks
  with one combined command) is the manual fallback, bypassing the marker
  to force a clean re-apply. **Also fixed 2026-09-15**: the command
  handler used to call `apply_all_patches()` directly on the event loop
  thread with no executor dispatch at all, blocking the entire client
  (network heartbeat included) for the full combined runtime of 4
  subprocess-based RIM sweeps -- now dispatched via `run_in_executor` like
  everything else, result logged via `game_events_logger` instead of
  blocking. Pairs with `/ap_restore_all` (renamed from
  `!ap_revert_game_files`, same 2026-09-15 pass -- it had the identical
  blocking flaw, fixed the same way), which reverts everything back to
  vanilla in one call -- the real use case being two different player
  YAMLs' seeds tested on the same local KOTOR install, where switching
  which slot's patches are active needs a clean revert in between.
  **Output simplified the same night** (user's explicit ask): each
  command now returns short, player-facing status lines instead of raw
  per-script stdout -- `/ap_restore_all` a single restored-file count,
  `/ap_patch_all` one `Patching <name> - Status: DONE/FAILED` line per
  distinct file operation (Loot Mode is deliberately two lines, the main
  static-edit pass and the Endar Spire starting locker fix, since
  `patch_loot_disturb.py` genuinely performs both as separate operations
  in one subprocess call) plus a final "ready to launch" summary line.
  `/ap_patch_all` also gained a **Jedi Suppression** line
  (`regenerate_makejedi_suppressor()`) that it never covered before at
  all -- a real gap, since the seed's `starting_class` can differ between
  test slots the same way `loot_mode` does. Deliberately still does NOT
  cover New Companion's asset deploy (`apply_new_companion_assets()`) --
  it has no `--restore` counterpart, so adding it to `/ap_patch_all` alone
  would let that command deploy something `/ap_restore_all` can't clean
  back up; tracked as a known, low-risk gap in `MODE_DEPENDENCIES.md`
  rather than fixed, since New Companion already re-syncs correctly on
  every real Connect regardless of either admin command. Same deliberate
  exclusion applies to `apply_shop_item_costs()`
  (`patch_shop_item_costs.py`, wired to run on every Connect the same
  not-seed-gated way as Galactic Shop) -- purely additive, no meaningful
  restore, always re-syncs correctly on Connect regardless of either admin
  command.
  `apply_new_companion_assets()`/`_apply_new_companion_assets_and_log()`
  (2026-09-14) run `generate_new_companion_assets.py` the same
  not-seed-gated way as Galactic Shop, every `Connected` — see 4.3.
  `self.location_tracker.set_new_companion(...)` fires in the same
  `Connected` handler, right after `write_slot_data_for_patch_scripts()`,
  correcting the companion-index collision noted in 4.3's entry.
  A separate, small diagnostic (not a safeguard) added the same day:
  `arm_orchestrator.py`'s pending-queue-bloat warning (40+ entries) used
  to only reach that script's own stdout, which the C extender discards
  on a successful exit — traced end to end and fixed by appending an
  `AP|WARNING|QUEUE_BLOAT|<n>` line directly to `kse.log` (the file the
  extender's log-tail thread already watches for any `AP|` marker
  regardless of writer), so it reaches the client through the
  already-working relay; `_on_extender_event` now surfaces it on the main
  visible tab, not the buried Heartbeat one.
  New-character safeguard (`_evaluate_character_safety`, 2026-09-02):
  pauses every delivery/reconciliation action if the connected
  character's name has never appeared in the delivery log AND they're
  above level 1 (a real level-1 character is always waved through
  automatically) -- protects against silently dumping the full delivery
  backlog onto an unexpected character (wrong save loaded, etc.).
  `/ap_confirm_character` overrides it once a human confirms. See
  `TESTING.md`'s "New-character safeguard" section.
  `_resolve_trap()` (2026-09-08) implements all 12 Traps items'
  one-time-only computation (each gated by the existing delivery log, no
  new dedup mechanism needed) — notably `_compute_max_hp()`/
  `_con_decrease_for_half_max_hp()`, since KOTOR has no direct Max HP
  memory field (it's `sum(class_level*hitdie) + floor((CON-10)/2)*
  total_level`); halving HP means searching for the CON decrease that
  gets closest to half, then sending that amount over the `trap:` wire
  action for the NWScript side to apply as an `EffectAbilityDecrease`
  (same mechanism as the other 5 ability-score trap items — this project
  has no absolute base-ability-score setter, only the relative Effect,
  same as K1SE).
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
  **XP-clamp staleness fix (2026-09-17)**: the clamp used to run on every
  `AREA` event whenever `experience_mode != 0`, including before any real
  `XPREPORT` had ever been seen this connection — comparing a stale/
  default `current_scalar` against the real in-game XP and clamping it
  down incorrectly. Gated on a new `_xp_seen_since_reset` flag (set only
  when an actual `XPREPORT` event has been parsed, reset alongside
  `reset_live_state()`) so the clamp can't fire on data it never actually
  received.
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
  `build_trap_block()` (2026-09-08) generates all 12 Traps items' NWScript
  bodies from one `trap:<type>:<params>` action, following the same
  consolidated-wire-action pattern as `companion_class:`/`give_item:` —
  adding a Traps-shaped feature needed zero new native/opcode work, only
  a new case in this function plus matching cases in `arm_orchestrator.py`
  and `ap_extender.c`. Also owns `_PLANET_PREFIXES` (see 4.1's
  `PLANET_MODULE_PREFIXES` note for why this is a separate dict, not a
  shared import, and why Tatooine's absence from both was a real bug).
- `generate_companion_suppressors.py` / `generate_store_suppressors.py`
  — preserve-and-chain wrapper pairs for companion recruitment and store
  markers.
- `generate_council_gate_trampolines.py` (2026-09-17) — compiles
  `ap_companion_gate.nss` (a shared, `#include`-only "secondary brain,"
  deliberately separate from `ap_poll_shared.nss`) into the trampolines
  for a small family of vanilla scenes that expect Bastila and/or Carth
  to already be present as active party members (the Dantooine Jedi
  Council wrap-up, the Taris Hideout escape-plan scene) — under
  `companion_mode=ap_gated`/`none`, before either companion's real item
  has arrived, the scene's own `IsAvailableCreature` gate can never pass
  otherwise, a real story stall. Temporarily grants+benches+reverts
  around calling the real original script, guarded by a busy flag
  (`GetLocalBoolean`/`SetLocalBoolean` on the module — K1's local storage
  is index-based, not string-keyed) against the same physical trigger
  firing multiple times in a burst, which is confirmed to otherwise race
  the grant/revert against itself and leave a companion permanently
  seated without ever having received their real item. Handles a genuine
  cross-module resref collision (`k_pdan_cut01`-`cut06` are different
  real compiled scripts in `danm13` vs `danm14ab`, resolved at runtime via
  `GetModuleFileName()`). See `docs/MODE_DEPENDENCIES.md` for the full
  investigation, including the separate, unrelated "CutStart" engine bug
  this family was initially (incorrectly) suspected of causing.
- `generate_makejedi_suppressor.py` (2026-09-02) — same preserve-and-chain
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
  the real connected seed's `starting_class` (`/ap_regen_makejedi` is the
  manual fallback), same pattern as `ap_poll_shared.ncs`.
- `build_area_graph.py` / `build_door_graph.py` — static connectivity
  data: which covered areas are directly reachable from which (used for
  arming neighbors), and the full 156-transition door/trigger graph (used
  by `EntranceRando.py`).
- `generate_kotor_locations.py` — generates `Locations.py` from
  `questtagmapping.json`/`areatodisplaymap.json` (renamed by the user
  2026-09-02 from `scratch_locations.json`/`scratch_areas.json`, built
  from the now-removed journal-scan scripts), a hardcoded companion list,
  AND (2026-09-02) all 33 alignment/level/goal locations (10 alignment
  thresholds, 3 alignment-bonus checks, 19 character levels, 1 Malak-
  defeated) via fixed constants at the top of the file -- these used to
  live in `Locations.py` some other way outside this generator's
  knowledge, and a re-run silently wiped all 33 once, breaking every
  seed's generation project-wide until caught and fixed same session (see
  `FutureDesign.md`). Covers all 220 real locations now; re-running this
  can't silently drop any of them again.

**Live pipeline — runtime orchestration:**
- `arm_orchestrator.py` — invoked by the extender's C code on every
  relevant event; computes the armed set (current area + graph
  neighbors), regenerates newly-in-scope areas, clears out-of-scope ones.

**Live pipeline — per-seed, game-file-level patchers** (not part of
NWScript generation; directly rewrite RIM files for one specific
generated seed, gated on that seed's options):
- `patch_loot_disturb.py` — Loot Mode (destroy/bonus/replace), on its
  **3rd design** as of 2026-09-13 (updated 2026-09-14 for the Endar Spire
  starting-locker fix below): pure STATIC template-data edits applied
  before the game ever loads, no runtime script or script-hook field of
  any kind. Replaces two earlier designs in order: (1) `Mod_OnAcquirItem`
  (`patch_item_suppression.py`'s original mechanism — re-fires for
  already-held items, ruled out for reuse anywhere); (2) `OnInvDisturbed`/
  `ScriptDisturbed` (this file's own first design — structurally sound for
  placeables, but a real dead end for creature corpse loot: confirmed live
  that `ScriptDisturbed` never fires at all when looting a dead creature's
  body, only while the creature is alive, which is fatal since most of
  this game's real loot comes from killing enemies). The static-edit
  design works because a creature/placeable template's `ItemList` is just
  GFF data, no different in kind from any other field this project already
  edits directly — editing it once at patch time and depositing the result
  as a global Override file means the modified loot is just *there* the
  moment that module next loads, same as any other vanilla placement: no
  event, no process-level cache, **no relaunch requirement at all** (a
  real usability win over both earlier designs — takes effect on a plain
  reload, including of an already-running game).
  - **destroy**: delete every non-whitelisted `ItemList` entry from every
    loot-bearing template (chitin first, then every module `.rim`
    including each module's own `_s.rim` companion — some real loot, e.g.
    `end_m01aa`'s `rsldcrps002` corpse, lives only in the `_s.rim`).
  - **replace**: same scan, swap each non-whitelisted entry for a
    seed-deterministic random pick from the loot pool instead of deleting
    it (own `GetRandomLootItem()`-equivalent static pick over the real
    `shop_randomize` pool).
  - **bonus**: leave all original items untouched, add ONE extra
    seed-deterministic item to every template that already has at least
    one (fires far more often than the old per-5-real-pickups milestone
    design — user's own explicit simplification, cadence over exact
    matching).
  **Equipped-gear suppression** (`_process_equipment()`, 2026-09-15): a
  creature's equipped weapon/armor (`utc.equipment`/`Equip_ItemList`) is a
  completely separate GFF field from carried inventory (`ItemList`) —
  found live as a real gap (a Sith trooper's carried vibrosword survives
  destroy mode untouched since it was never carried inventory to begin
  with). destroy and replace both flip the equipped item's `Dropable` flag
  to `False` rather than removing/swapping it, since actually changing
  equipment would visibly alter the creature's appearance/combat animation
  (fighting bare-handed); replace additionally can't safely reuse the
  random loot pool here since it mixes weapons/armor/medpacs with no
  slot-type filtering. bonus mode leaves equipment untouched entirely,
  consistent with never removing existing loot. Narrow in practice — only
  one creature in the entire base game (`n_calonord`, Calo Nord) has a
  genuinely droppable equipped item at all.
  Also carries forward Progression System's Sith Armor/Shield Codes
  always-suppress-at-source check (the 2 of its 8 items whose real
  vanilla acquisition is a genuine container/corpse pickup) as the same
  unconditional static removal, independent of `loot_mode`, gated only on
  `progression_system`. `granted_exempt_` bookkeeping (needed by both
  earlier runtime designs to protect an AP-granted item from immediate
  re-suppression) is gone — this file never touches anything delivered
  through the AP item pipeline any more, so there's no overlap to guard.
  Idempotent by construction: every run re-derives each template's final
  state from the PRISTINE source, never from a previously-deployed
  Override copy of its own (`discover_chitin_templates()` reads via the
  chitin `FileResource`'s own `.data()`, not `Installation.resource()`,
  specifically to avoid reading back its own prior output as if it were
  pristine). `_loot_static_manifest.json` tracks exactly which Override
  files this script has deployed, so `--restore` and a mode/seed switch
  both know precisely what to remove without guessing at another
  feature's legitimate Override content by name collision.
  **Endar Spire starting locker** (`ensure_starting_locker_gear()`,
  2026-09-14): `footlker001` in `end_m01aa_s.rim` is set to exactly
  `STARTING_LOCKER_KIT` (clothing, a blaster pistol, a short sword, 10
  Computer Spikes) whenever a loot mode is active, replacing real vanilla
  contents that included an extra medpac and no pistol at all — a full
  replace, not additive. Edits the module RIM directly (never Override —
  `footlker001` is one of 58 real BioWare name collisions reused with
  different contents across other modules), idempotent, and restores true
  vanilla contents when `loot_mode` is off. Replaces the retired "Loot
  Safety Net" AP-item precollection with a permanent, seed-independent
  world-content fix instead.
  `patch_item_suppression.py` itself is NOT fully retired: its
  `apply_progression_checkpoint_wrappers()` mechanism, below, is a
  completely separate thing that never went through `Mod_OnAcquirItem` at
  all, and still lives there.
  `apply_progression_checkpoint_wrappers()` (2026-09-08) is a separate
  mechanism for the Progression System's other 6 suppress-at-source items
  (Sith Papers, Enviro Suit, the 4 Star Maps): extracts each
  real checkpoint script's TRUE original directly from chitin via
  `Installation(game_dir).resource(name, ResourceType.NCS)`, writes it as
  `apo_<name>_orig.ncs`, and deploys a small gate-and-delegate wrapper
  (`k_sup_galaxymap_progression.nss` etc. in `extender/scripts_src/`) that
  checks a `KSE_HasData("granted_exempt_<tag>")` exemption flag before
  calling through via `ExecuteScript`. One of the 4
  (`k_ptar_sithpaper`, a `StartingConditional`) needed full
  reimplementation instead of gate-and-delegate, since `ExecuteScript`
  can't relay a called script's return value back to its caller.
- `patch_door_randomizer.py` — rewrites each shuffled transition's
  `LinkedToModule`/`LinkedTo` GFF fields to match the seed's computed
  mapping. No compiler dependency at all (pure GFF field edits).
- `patch_additional_enemies.py` (2026-09-08) — the fourth per-seed
  patcher, same pattern as the two above. Reads `additional_enemies_mode`
  from slot_data and, for each of 195 precomputed safe spawn points
  across 40 modules (Tables A/B/C — see `DEVELOPMENT_HISTORY.md`), places
  a creature chosen by mode (`area_appropriate`: CR-filtered, drawn from
  that module's own dominant category; `random_sane`: CR-filtered, full
  safe pool; `fully_random`: unfiltered). Seeded by the real AP
  `seed_name` so a reconnect reproduces identical placements.
  Live-tested at both extremes; `random_sane` itself not yet separately
  exercised (mechanically identical minus the category filter).
- `generate_new_companion_assets.py` (2026-09-14, live-tested) — the
  `new_companion` option: replaces HK-47 with a new
  human companion, Meetra Surik (Jedi Sentinel), in his exact party slot
  (his Tag stays `"HK47"` — load-bearing for a game-wide, generic
  9-companion tag-exclusion check every companion is subject to, and for
  the codegen below that resolves her by that same tag). Deploys 3 pieces
  every `Connected` (not seed-gated — has to restore vanilla just as
  reliably as it installs the swap):
  - `p_meetra.utc` — her level-1 stat block, ability scores/skills/combat-
    tuning fields taken from Bastila's own real template (same class,
    Jedi Sentinel) wherever a field doesn't scale with level; HP/FP/
    feats/starting Force powers independently re-derived for level 1
    specifically (`classes.2da`'s hit die/force die + CON/WIS modifiers;
    the "4 mandatory Jedi feats + Sentinel signature" recipe already used
    by `companion_class` conversions, matching real cross-class feat data
    from `feat.2da`; the 5 "base tier" starting Force powers `spells.2da`
    shows are outside the normal level-6+ learn list, i.e. the standard
    from-creation Jedi kit).
  - The vanilla Tatooine recruit trigger's dual variant
    (`extender/scripts_src/apo_hk47_vanilla.ncs` vs. `apo_hk47_new.ncs`,
    precompiled and checked in, no compiler needed at runtime — same
    convention `patch_item_suppression.py`'s own mode variants use).
    Reconstructed the real vanilla script's NWScript source from a fresh
    disassembly, confirmed byte-identical to the true original via a
    compile+disassemble+diff pass (0 of 38 opcodes differ) before forking
    it — the new variant differs from vanilla by exactly that one
    template-resref string, nothing else.
  - Her placeholder Ebon Hawk greeting (`k_hmee_dialog.dlg`, one line, no
    replies) — replaces her entire personal subplot, which is cut
    entirely for this option.
  Wired into `KotorClient.py` (`apply_new_companion_assets()`/
  `_apply_new_companion_assets_and_log()`, `/ap_apply_new_companion` manual
  fallback), same not-seed-gated shape as `patch_galactic_shop.py`.
  Because AP's item/location name-to-id mapping is a static, class-level
  table shared by every seed of this world (not per-player), "renaming"
  HK-47's item/location to say "New Companion" couldn't be a live string
  swap on the existing entries — `Items.py`/`Locations.py` instead carry a
  second, permanently-named item/location pair (`"Companion: New
  Companion"`/`"Companion Recruited: New Companion"`), with `__init__.py`
  choosing which of the two is actually active per seed (same shape
  `_active_locations()` already uses for `companion_mode=none`). Two real
  bugs this surfaced and fixed before any live testing: (1) `Rules.py`'s
  ap_gated subplot self-guard iterated locations directly rather than
  through `_active_locations()`, which would have crashed generation
  outright the moment `companion_mode=ap_gated` + `new_companion=on` were
  combined together; (2) `kotor_location_tracker.py`'s `LocationTracker`
  built its companion-index from the raw, unfiltered `location_table` at
  import time, before any seed's `new_companion` value was known, so it
  needed a `set_new_companion()` correction fired on `Connected` (see
  4.2) or it would report the wrong location name for whichever setting
  didn't win dict-iteration-order by default.

**Distribution/packaging** (for getting a fresh install running without
the full dev toolchain — see `README.md`):
- `package_dist.py` — collects the always-on generated Override content
  into `dist/Override/`, deriving the exact file list from the generator
  scripts' own data so it can't silently drift. **`EXTRA_RAW_FILES`
  (2026-09-17)** ships a small set of non-`.ncs` files verbatim (never
  compiled) from `extender/raw_override_files/` — currently the 4
  replacement `.dlg` files that fix the "CutStart" engine bug (see
  `docs/MODE_DEPENDENCIES.md`), sourced from the repo itself rather than
  a dev machine's live game install, since they're static and
  seed-independent.
- `setup_game.py` — tester-facing: copies `dist/Override/` into a real
  install. Pure standard library, no `pykotor`/compiler needed.
- `install_playerbundle.py` (2026-09-08, the "3-step install" plan's
  Step 2) — the real installer: calls `setup_game.py`, copies the now-
  bundled `nwnnsscomp.exe` into the game folder root, installs the merged
  `binkw32.dll` proxy (a native Python port of `install.ps1 -Install` --
  see that file's own entry in 4.4 for why both exist rather than one
  shelling out to the other), `pip install`s `pykotor`, and writes an
  install-path marker (`%LOCALAPPDATA%\KotorAP\install_path.txt`, for the
  not-yet-built apworld Launcher-button registration to read) plus a
  manifest (`install_manifest.json`) recording exactly what it touched.
  `--uninstall` reverses all of it -- the 3 patch scripts' own
  `--restore`, the DLL swap, and only the Override files THIS run
  actually added (anything that already existed with the same name is
  left alone, since Override is shared space). Verified live against a
  synthetic fake game directory, install then uninstall, byte-for-byte
  correct on both sides -- not yet run against a real Steam install.
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
`generate_trampoline_batch.py`'s `APPLIES`.

`extender/install.ps1` captures the game folder's real `binkw32.dll` as
`binkw32_real.dll` (once) and swaps in this compiled proxy, plus writes
`ap_repo_root.txt` (read by `ap_extender.c` at runtime to find
`scripts\arm_orchestrator.py`). Still maintained as a standalone dev
tool, but 4.3's `install_playerbundle.py` (2026-09-08) is now the
tester-facing path -- it ports this same logic natively into Python
rather than shelling out to PowerShell, a small deliberate duplication
(this script is short and rarely touched) rather than adding a
PowerShell subprocess dependency to the one true installer path.
