# KOTOR Archipelago Randomizer — Design Doc

**Status: Alpha.** The core pipeline (delivery, detection, options, item distribution, goal detection) is built, wired, and generation-tested
end-to-end, and most of it has been played. As of 0.1.9 every story gate of the Progression System (Taris, Dantooine, Tatooine, Kashyyyk,
Manaan, Korriban) has been played closed and then open

This document explains how the whole system fits together and what each file is for. It does not re-derive the engine-constraint
discoveries that shaped the design; the ones that matter for reading the code are summarised in section 3 and in each file's entry.

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
   ├─ kotor_dispatcher.py        -- the delivery queue: one numbered job at a time
   ├─ kotor_reconciliation.py    -- "what should I have" vs "what do I have"
   └─ kotor_location_tracker.py  -- raw game state -> real location checks
        |  TCP, 127.0.0.1:25586
        v
 extender/src_k1se/ap_extender.c + kse_hook.cpp  (merged proxy DLL, injected into swkotor.exe)
   ├─ K1SE's dispatcher-hook mechanism, merged directly into this build (not a
   │  separate third-party mod any more -- see README.md's install steps)
   ├─ tails kse.log for AP|... marker lines -> EVENT: over the socket
   ├─ receives DISPATCH: jobs from the client and leaves each in an in-DLL inbox the poll reads
   └─ shells out to scripts/arm_orchestrator.py to rebuild area-entry scripts (shop catalog, Hawk spawns)
        |  regenerates + recompiles + deploys NWScript to Override
        v
 In-game NWScript (auto-generated, deployed to Override)
   ├─ ap_poll_shared.nss    -- the shared "brain," polls everything, reports via KSE_Diag, applies the client's delivery jobs
   ├─ area trampolines      -- preserve original OnEnter, call the brain, carry the shop catalog and the Hawk's spawns
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
- **A delivery is data, never a rewritten script.** `ExecuteScript` to a
  resref whose content changes mid-session cannot carry it
  (`ExecuteScript` caches bytecode per-process forever). So the client
  leaves a job (an action and its arguments) in an inbox held inside the
  DLL, and the poll script, which is not rewritten per delivery, reads it
  there on its next beat and applies it (the job dispatcher, see
  `kotor_dispatcher.py` in 4.2). The earlier design, regenerating area
  *trampolines* with a pending batch for the player's current area and its
  neighbors (`arm_orchestrator.py`), is no longer how anything arrives.
- **A delivery is one numbered job, applied at a calm moment.** One job is
  in flight at a time; the game applies it only when no conversation,
  cutscene or fight is running, at most once, and keeps the count in the
  save, so a repeat is dropped and a reloaded older save gets back what it
  lacks. Deaths from DeathLink are never replayed.
- **Reconciliation is deficit-only**, except XP under
  `experience_mode` (when not `off`), which is the one deliberately
  bidirectional clamp (it has to suppress vanilla combat/quest XP, not
  just top up).
- **Only a short list of items is ever unconditionally guaranteed** in the
  pool (the 9 companions when `companion_mode` is `ap_gated`, the 24
  Progression items (`progression_system` on), the 5 Vendor Passes, the 12 fixed-amount traps,
  the Party Console (whenever companions exist), and the Jedi class / Jedi
  Training / Additional Feats / New Companion Selection items when those
  options are on) — everything else (gear, Skills, Abilities, EXP, Credits,
  filler traps) is drawn through a weighted 8-category distribution
  (`item_distribution_type`), not a fixed guaranteed list. See `Options.py`'s `ItemDistributionType` docstring.
- **Real game data drives content generation, not hand-transcription.**
  Journal completion values, companion recruit scripts, door/trigger
  destinations, area OnEnter hooks — all discovered by scanning actual
  compiled scripts/RIMs/2DAs via `pykotor`, not guessed or hand-typed.
  Several early research scripts exist specifically because a
  hand-transcribed version turned out to be wrong.
- **Every resref this project invents must be 16 characters or fewer.**
  KOTOR's engine hard-caps resref length at 16 -- a longer name (e.g. a
  first attempt at a test dialogue resref, `ap_testvendor_dlg`, 18 chars)
  silently truncates on write with no error anywhere, so every later
  reference to it (script string literals, a `.utc`'s `Conversation`
  field) points at a name that never matches the real deployed file.
  Confirmed live: this was the actual root cause of an entire dialogue
  mechanism appearing completely broken, while the real bug had nothing
  to do with the scripting logic being debugged at the time. Always
  check new resref lengths before debugging anything else about
  content that "does nothing" with no error.
- **A freshly-authored `.dlg` node defaults to being a plot/XP node.**
  `pykotor`'s `DLGEntry`/`DLGReply` default `plot_index` to `0` (a real
  quest-progression node, grants `plot_xp_percentage` worth of XP just
  for being reached) rather than `-1` (not a plot node, the value every
  real non-quest vanilla conversation node actually uses). Confirmed
  live: an otherwise-correct test dialogue was silently handing out free
  XP on every node, including a plain "Never mind" exit option, until
  `plot_index` was explicitly set to `-1` on every node. Any dialogue
  built from scratch via `pykotor` needs this set explicitly -- never
  rely on the library default.

**Code comment conventions** (standard set 2026-09-16, applies going
forward — most of the codebase predates this and is being brought in line
gradually, not all at once):
- A comment explains what the code does, why (when non-obvious), and any
  real dependency the reader needs to know about — nothing else.
- No dates, no "(YYYY-MM-DD)" stamps, no "found live," no session
  narrative. Git history already has the timeline; a comment isn't the
  place to re-derive it.
- Never write "at the user's request," "per the user's explicit ask," or
  any equivalent attribution. It tells a reader nothing about the code
  and rots the moment anyone other than this project's own maintainer
  reads it.
- If a decision needs real justification (an engine limitation, a design
  tradeoff, a rejected alternative), that justification belongs in this
  document — the comment should be a short pointer to it (e.g. "see
  DESIGN.md §5.2, `OnOpen` never fires in this engine build"), not a
  restatement of the investigation inline.
- Don't reference internal-only files a GitHub reader won't have
  (working notes, a specific past chat, a date) — point at `DESIGN.md`
  or state the fact in the comment itself.
- **Engine findings that shape the scripts.** `ActionStartConversation` reached through `ExecuteScript` silently does not start, so a gate whose original
  starts a conversation is written out natively or moved into the dialog. An Override file replaces every module's file of the same name (a dialog,
  trigger or template that exists in more than one module with different content must be renamed, not overridden). On-screen messages do not show, so
  the player speaks a one-line dialog (`ap_gate_msg`) instead. The Override folder is read once at game startup. Triggers can fire while a module is
  still loading, before the player exists. Item variables do not survive an area change but an item's presence does, and a journal quest only moves
  forward, which is why the mod's records in the save are marker items and journal entries. The game also groups its modules by planet in `modulesave.2da`
  (Endar Spire, Taris, Dantooine, the four open worlds, the Leviathan, the Unknown World) and deletes a group's saved areas when the player enters the next
  planet's first area (Taris on entering the Jedi Enclave, Dantooine on entering the Leviathan's Hawk, and so on). Nothing is lost in the base game because
  those planets cannot be revisited; with the area randomizer a shuffled door can lead back, and the planet comes back in its fresh state (enemies, containers,
  fog and first-entry scenes reset, while quests and globals are kept). The mod does not change this table.

## 4. File-by-file breakdown

### 4.1 The Archipelago world (`Archipelago/worlds/kotor/`)

- **`__init__.py`** — the `KotorWorld` class AP's generator actually
  calls: builds regions (`create_regions`), builds the item pool
  (`create_items`, `_distribute_items`, `_gear_category_pools`,
  `_skill_ability_pools`), builds `slot_data` (`fill_slot_data`) for the
  client to read on connect, and wires in `EntranceRando`/`Rules` when
  their options are on. This is where the weighted item-distribution
  system actually lives. Guaranteed-placement pool: the 9 companions
  (`companion_mode=ap_gated`), the 24 Progression items
  (`progression_system` on), the 5 Vendor Passes (`archipelago_vendor` on),
  the 12 fixed-amount Traps items, the Party Console (whenever
  `companion_mode` is not `none`; it is not an option), and the Jedi class /
  Jedi Training / Additional Feats (seven, one per non-droid companion) /
  "Ebon Hawk: New Companion Selection" items when those options are on are
  the only items ever unconditionally placed — the same `mandatory_names`
  pattern for all of them, everything else drawn through the weighted
  distribution. `Traps = item_filler` is capped at `MAX_FILLER_TRAPS` (36)
  trap items per seed: once that many are drawn the trap category leaves
  the weighted draw. `PLANET_MODULE_PREFIXES` maps each of the 6
  planets to its module-name prefix for `_shop_stock()`'s per-planet
  catalogs — Tatooine (`"tat_m"`) was once missing entirely
  (since fixed); a dev-tooling duplicate of this same
  dict, `_PLANET_PREFIXES` in `scripts/generate_trampoline_batch.py`, has
  to be kept in sync by hand (the two live in separate processes — see
  4.3's note — so they can't just share one Python object).
- **`Options.py`** — every player-facing setting (`KotorOptions`
  dataclass) with full docstrings. `STARTING_ABILITY_ARMS`/
  `STARTING_SKILL_ARMS` map arm names to their matching starting-boost
  option, shared with `__init__.py`. `ProgressionSystem` (the story gates,
  see `StoryGates.py` below),
  `Traps` (field name `enable_traps`: a Choice of off / item_filler /
  fixed_amount covering 12 one-time punishment items, see
  `Items.py`/`KotorClient.py` below; with `trap_weight` and `trap_link`;
  `item_filler` is capped at 36 traps per seed),
  `ArchipelagoVendor` (its own option, five Vendor Pass items), `GalacticShop`, and `NewCompanion` (the console
  that swaps HK-47's or T3-M4's party slot, see 4.3's
  `generate_new_companion_console.py` entry) are the newest option classes;
  all default off. `NewCompanion` is a 3-way `Choice`: `off`, `on` and
  `random_class` (old `false`/`true` values still work as aliases). The six
  characters the console offers (Meetra Surik, Darth Malak, Calo Nord,
  Yuthura Ban, Darth Bandon, Trask Ulgo) are chosen at the console on the
  Ebon Hawk, never at HK-47's recruitment, so the option adds one item
  ("Ebon Hawk: New Companion Selection") and no locations of its own;
  HK-47's and T3-M4's items and checks are exactly the vanilla ones. With
  `on` each character has its own class; with `random_class` each is dealt
  one of the six base and Jedi classes when the seed is made
  (`new_companion_classes` in `slot_data`, rolled in `generate_early()`
  after the companion-class rolls so the other options draw as before).
  The option is ignored (treated as off) with `companion_class: droid` or
  `companion_mode: none`. `_companion_class_keys()` (in `__init__.py`, not
  this file) now simply returns the seven non-droid companions: a console
  replacement is never rolled a class by `companion_class` and has no
  Additional Feats item. 0.2.0 also added `quest_item_checks` (13 checks
  that fire when a quest item is received; default on) and `bazaar` (the
  Archipelago Bazaar's 5 purchase and 20 token-exchange checks; default
  off), and `additional_feats` now unlocks a "train a feat" dialog option
  instead of granting feats (see 4.3's `generate_feat_training.py`).
  0.1.9 added `companion_mode: ap_limited`, the `droid` values of
  `starting_class` and `companion_class` (see 4.3's `generate_droid_assets.py`) and new EXP defaults (EXP Item 8000, EXP Limiter 1000, both with a minimum of 500).
- **`Items.py`** — `item_table`: every AP item (skills, companions,
  abilities, class switches, XP/credits filler, the 24 story-gate Progression
  items (`ap_tk_<family><n>`, ids from `base_id + 200000`), the five Archipelago Vendor passes `VENDOR_UNLOCK_ITEMS`, the seven
  "Additional Feats Character: <companion>" unlocks (`give_item:ap_ft_<key>`), "Ebon Hawk: New Companion Selection" and "Party Console" —
  all three kinds are plot items delivered by a plain `give_item:`; the ids of the removed
  "Progression Item:" entries and of the New Companion and player-character feat items are not reused) plus gear items loaded at
  runtime from `gear_items.json` (only rows flagged `included_as_item`
  get a real AP code). Exports `arm_name_to_item`, `item_name_to_id`,
  `lookup_id_to_name` as the single source of truth other files import
  rather than rebuild. `TRAP_ITEMS` (12 entries, `arm_name`s like
  `trap:cut_max_hp`) all route through one consolidated `trap:<type>:
  <params>` wire action rather than each getting its own native/plumbing
  — see `KotorClient.py` and 4.3's `generate_trampoline_batch.py` entry.
- **`Locations.py`** — `location_table`: all 304 locations (100 journal,
  9 companion, 78 area, 14 alignment + 2
  alignment-bonus, 19 level, 1 Malak defeated, 40 bounty card, 3 boss datapad
  (`Boss: Calo Nord / Darth Bandon / Saul Karath`, ids +261..263), 13 quest
  item (`Quest Item: <item> - <place>`, ids +268..280), 5 `Archipelago
  Bazaar: Purchase 1-5` (ids +281..285) and 20 `Bazaar Token Exchange 1-20`
  (ids +286..305)). The quest item, Bazaar and bounty checks exist only in
  slots with the matching option on (`_active_locations()`). Mostly
  generated by `scripts/generate_kotor_locations.py`, but not completely:
  everything after id +267 is hand-added, and the generator is out of date
  with the table (it still knows the removed New Companion row at +260, which
  is now unused), so do not re-run it without checking the result against the
  table. Ids must stay unique. `LocationData` also carries `quest_item_tags`
  (the item tags a quest item check fires on, from any source),
  `alt_journal_tag`/`alt_journal_target` (a second journal value that also
  completes a check, for quests that can be made impossible to finish the
  usual way) and `count_value` (which Bazaar purchase or exchange this is).
- **`Rules.py`** — `set_rules` and `set_completion_rules` (which sets the
  generation-time completion condition from the locked goal-marker items:
  "Malak Defeated", "Reached Level 20", "Reached Dark Side 0"/"Reached Light
  Side 100", "Reached Leviathan"). The real Goal signal in the playthrough is
  still client-driven via `KotorClient.py`'s `_check_goal`/`finished_game`.
  **`Goal`'s `reach_leviathan` option**: a shorter alternative to
  `defeat_malak`, detected from the first Leviathan area visit
  (`Visited: Leviathan - Prison Block`). `progression_system` works with every goal and with both area randomizer modes. `set_rules` stays flat
  and calls `StoryGates.py` when that option is on (next entry). It also
  holds the item-placement bans that apply to every seed: no progression
  item (of any game) on the alignment, level, bounty, boss datapad (Calo
  Nord's excepted when the area randomizer is off), Genoharadan, Ebon Hawk
  quest, Sunry chain, Bazaar purchase and Loot Exchange checks, nor on the
  late-game planets the player cannot return to (Leviathan, Unknown World,
  Star Forge, the final checks).
- **`StoryGates.py`** — access rules and placement restrictions for the story-gate Progression System (called from `Rules.py` when `progression_system` is on).
  The pool holds 24 plot items in eight families (Taris, Dantooine, Tatooine, Kashyyyk, Manaan, Korriban, Unknown World, Star Forge; three each,
  named "<Planet> Progression 1" to "3"). A gate in the game waits until the player holds enough items of one family, so the rules are plain
  item-count requirements: a planet baseline that accumulates down the story (leaving Taris needs 3 Taris items; the open-world planets also need
  Dantooine 3; the Leviathan and the Unknown World also need the four open-world planets' items; the Star Forge also needs the Unknown World; the
  Malak fight needs the Star Forge items), per-check extras for named checks (the 13 quest item checks have theirs too), and placement restrictions
  (the Leviathan, Unknown World, Star Forge and epilogue checks, which cannot be returned to, take no token, and `Rules.py` bars any progression item
  there; Taris and the Endar Spire take any token, because the tracker completes every check there that was not reached when the Ebon Hawk takes
  off, see `kotor_location_tracker.py` in 4.2, except that the Taris Shield Codes check takes Taris tokens only; an open-world family's
  items stay off its own planet). A check whose exact beat is uncertain is listed at the higher step: over-requiring only makes a seed more
  conservative, under-requiring could strand an item behind itself. `scripts/check_story_gate_spoilers.py` rebuilds reachability from a spoiler's own
  location list to confirm no item sits where it could not be reached without itself.
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
  Archipelago's own `entrance_rando.py` engine. Options.py's
  `AreaRandomizer` picks `off`/`coupled`/`decoupled`; both non-off modes
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
  deliberate scope choice to keep the coupled/decoupled split a small,
  low-risk change rather than a new design. Coupled mode's own placement
  can still leave a rare residual orphan (a module with exactly one
  coupled entrance whose placement failed to get a replacement) --
  `_repair_orphaned_modules` patches those after placement by stealing and
  repointing a well-connected edge, the same technique the old
  uncoupled-mode `_ensure_full_reachability` used, just scoped to the
  handful of leftover entries rather than the whole graph; the same repair
  pass runs for decoupled mode too, unchanged. In coupled mode AP's engine cannot place the last two doors on its own; `_repair_keeping_pairs` pairs those leftovers with each other and, if an area would still be
  cut off, swaps partners between two pairs, so every door leads back the way you came (30 test seeds had no one-way door and no unreachable area);
  `_repair_orphaned_modules` stays only as a last resort. See the module's own docstring for the full reverse-door analysis and reachability findings.

### 4.2 The Python AP client (`Archipelago/` root)

- **`KotorClient.py`** — the actual client entry point (`KotorContext`,
  `launch()`). Receives items from the server and forwards them to the
  game as dispatcher jobs (`_deliver_item`/`_do_deliver`, then the bridge's
  `send_*` methods and `kotor_dispatcher.py`, below), with `HEAVY_ARMS`/
  `companion_class:` still serialized one-at-a-time through a single choke
  point, `_queue_heavy()`, which waits for the game's answer to each before
  the next goes out, to avoid a confirmed crash class -- every real
  entry point that can trigger a heavy send, including the `/ap_apply`
  admin bypass and the `companion_mode=normal` auto-grant, funnels through
  it, not just the real-item path). An incoming DeathLink is a dispatcher
  job too (the `force_death` arm). It only sends location ids that belong
  to the slot, since the optional checks are missing from a slot that
  turned them off. It watches extender events and turns
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
  a fingerprint of the options each was last applied for) so a reconnect with
  the SAME options skips the redundant sweep rather than re-paying its cost on
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
  `patch_story_gates.py` and, since 0.2.0, `patch_bazaar_tokens.py` (which
  rebuilds container templates and so must run after `loot_disturb`) run in
  the same ordered task.
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
  back up; a known, low-risk gap left unfixed, since New Companion already re-syncs correctly on
  every real Connect regardless of either admin command.
  `apply_new_companion_assets()`/`_apply_new_companion_assets_and_log()`
  run `generate_new_companion_assets.py` the same
  not-seed-gated way as Galactic Shop, every `Connected` — see 4.3. With
  `new_companion = random_class` the `Connected` handler also writes the
  seed's rolled classes into `_slot_data.json` for that script.
  New Companion has no location of its own any more, so the tracker needs
  no per-seed correction for it.
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
  `_resolve_trap()` implements all 12 Traps items' one-time-only computation (each gated by the existing delivery log,
  no new dedup mechanism needed): the client works out the specifics from the character's live state (which half of the
  feats, powers or inventory goes, which skill, which companion, how far an ability is cut) and sends them over the `trap:`
  dispatcher action. The NWScript side (`build_trap_block` in `generate_trampoline_batch.py`, reached through
  `dispatch_actions.py`) applies them with native setters on the true base values (`KSE_FIELD_HALVE_*_BASE` for the five
  ability traps, `KSE_FIELD_HALVE_MAX_HP_VIA_CON` for Max HP, `KSE_FIELD_HALVE_SKILL_RANK` for the skill), not with a relative
  effect. Cut Max HP lowers Constitution, and the reconciler's ability baseline follows that drop so it is not read as a loss
  and granted back.
- **`entitlement.py`** — pure data and small helpers shared by the client and
  the reconciler, so neither has to import the other: `HEAVY_ARMS` (the arms
  that are serialized through the client's heavy queue), `PROGRESSION_ITEM_RESREFS`
  (the 38 tracked items), and `compute_entitlement`.
- **The old staged queue** (`KotorClient.py` with `arm_orchestrator.py`): nothing in
  the client stages an arm there any more, since every delivery is a dispatcher
  job. So that a queue an earlier version left on disk cannot fire at an area entry
  on top of the dispatcher (one authority per arm), on every extender (re)connect
  and every Connect the client runs `--clear-all`, which drops every staged entry.
  The admin `/ap_clear_queue` (the same `--clear-all`) journals what can't be
  re-derived to `_dropped_queue.json`; `/ap_restore_queue` (`--restore-dropped`)
  stages it again, and a slot change deletes the journal. After a client restart
  the expected companions, class and progression items are re-seeded from the
  delivery log.
- **`kotor_extender_bridge.py`** — owns the raw TCP connection to the
  injected extender (127.0.0.1:25586) and the wire protocol
  (`DISPATCH:`/`SHOPSTOCK:` out; `EVENT:`/`STAGED:`/`ERROR:` back). Every
  `send_*` method (`send_apply`, `send_apply_value`, `send_apply_item`,
  `send_companion_class`, `send_trap`, `send_force_power`, `send_delevel`,
  `send_notify`) turns its arguments into one dispatcher job instead of
  writing a command, and the delivery-tracking table the rest of the client
  reads (`wait_staged`, `rejection()`, the heavy queue's confirmation) follows
  that job: staged at once, settled when the game answers `APPLIED` or
  `DUP`, rejected when the job fails, removed when it is replaced. The older
  `APPLY:`/`APPLYVALUE:`/`NOTIFY:` commands are no longer sent.
- **`kotor_dispatcher.py`** — `DispatchClient`, the client half of the job
  dispatcher that is the only way anything is delivered to the game (the
  game half is `DtTick` in `ap_poll_shared`, 4.3). A job is one action
  (`arm:<name>`, `give_item:<resref>:<count>`, `set_xp`, `set_credits`,
  `delevel`, `force_power`, `companion_class`, `trap`, `notify`) with an
  optional message shown to the player once it has run. The client sends
  `DISPATCH:<seq>:<action>[:<args>]`, the extender leaves it in the DLL's
  inbox, and the poll takes it on its next beat. Rules: one job in flight at
  a time (the next goes out after the game answers the one before); the game
  applies a job only at a calm moment, so a job waits while a scripted scene,
  a conversation, a cutscene module, a locked player, combat, an area that
  has just loaded, an empty party or a dead player holds it (`GATE_NAMES`;
  the status window says which); `seq` is a number 0-255 that counts jobs,
  kept by the game in the save (the player's local booleans), so a job whose
  number the save already holds is dropped as a repeat (`DUP`, counted as
  done), a wrong number is answered `SYNC` and the job renumbered, and the
  number is advanced before the action runs, so a job can be lost but never
  run twice. A job that gets no answer is sent again, and given up on after a
  number of tries. Answers are `AP|DISPATCH|APPLIED/DUP/SYNC/FAILED/UNKNOWN/
  WAIT/STATE` lines; `FAILED` (the action ran but could not do its job, which
  for the fixed arms means the result is not there afterwards: a skill,
  ability, XP or credit arm that did not raise its number, a class,
  droid-conversion or companion arm that left the player in a different
  state) and `UNKNOWN` are written to the delivery log and not retried.
  A loaded older save brings back its own, lower number: the client keeps a
  ledger of every job the game counted and sends the jobs that save never
  had again, in their original order. A death (an incoming DeathLink, the
  `force_death` arm; the game does not hold it for combat) is counted in the
  ledger so the numbers stay in step but is never replayable, and a reload
  also drops a death still waiting or being sent, so a death that belonged to
  the life just left cannot kill the reloaded one; the client also does not
  send a DeathLink for a death seen within `LINK_DEATH_ECHO_SECONDS` of one
  the game applied for an incoming link, which would otherwise bounce between
  two linked players for ever. `set_xp`, `set_credits`, `delevel`,
  `companion_class` (per companion) and `force_power` (per id) replace a job
  of the same kind that is still waiting (the reconciler sends a correction
  again on every poll until the game agrees); items, traps, deaths and plain
  arms never replace each other. Messages of a run of jobs are batched into
  one message box. `has_unfinished()` lets the reconciler's self-heal skip an
  item whose real delivery is still waiting for a calm moment (otherwise the
  player got two). `window_text()` builds the delivery block of the Status
  tab and `/ap_status` (what is waiting and why, what failed, what was
  delivered recently). The `/ap_dispatch*` commands are developer tests.
- **`kotor_reconciliation.py`** — `ReconciliationTracker`: the
  "client-authoritative" half. Tracks what the player *should* have
  (from received items, or for `ap_limited` XP, live from
  `checked_location_count`) against what the game *currently reports*,
  and sends corrective dispatcher jobs to close any deficit.
  Scope (2026-09-29/30): skills, credits, all 9 companion recruit adds
  (idempotent -- Zaalbar/HK-47 were previously excluded over an
  unverified concern, re-added once their trampoline arms were confirmed
  identical to every already-reconciled companion's own), PC+companion
  class (there is no feats branch any more: feats are trained in the
  companions' dialogs, and nothing re-grants them), the 38 tracked progression
  items (the 24 story-gate Progression
  items, the 5 Vendor Pass tokens, the 7 companion feat-training unlock items,
  the New Companion console unlock and the Party Console; a lost one is
  re-granted -- a narrow possession
  check, not full reconciliation), the "Archipelago Tracker" journal
  quest's check-percentage stage, and ability scores (str/dex/con/int/
  wis/cha -- a bootstrap-then-track-deltas design, deliberately different
  from skills' pure AP-grant-count floor, since ability scores start at a
  real natural value instead of near 0; Charisma has its own `ability_charisma`
  arm and is reconciled like the other five). Plus the special XP clamp.
  Trap-awareness: `reduce_skill`/`reduce_str`/`reduce_dex`/`reduce_int`/
  `reduce_wis`/`reduce_cha`/`remove_credits` are recognized as
  legitimate decreases and lower the relevant expected/baseline value to
  match, instead of being silently healed back; so is `cut_max_hp`, which
  halves max HP by lowering base Constitution (the trap prints the Constitution
  before and after, and the reconciler lowers its Constitution baseline by that
  drop). The AP Vendor's
  Character Reset (respec) and "Steal from the Republic" alignment
  option are also recognized directly (via their own diag lines) so a
  respec actually clears AP-tracked skills/abilities instead of
  them regrowing, and a credit gain isn't clamped back down as an
  unauthorized vanilla gain.
  **XP-clamp staleness fix (2026-09-17)**: the clamp used to run on every
  `AREA` event whenever `experience_mode != 0`, including before any real
  `XPREPORT` had ever been seen this connection — comparing a stale/
  default `current_scalar` against the real in-game XP and clamping it
  down incorrectly. Gated on a new `_xp_seen_since_reset` flag (set only
  when an actual `XPREPORT` event has been parsed, reset alongside
  `reset_live_state()`) so the clamp can't fire on data it never actually
  received.
  **Roster reconciliation (2026-10-03/04):** from the `ROSTERREPORT` poll the
  reconciler also keeps the companion roster honest: a companion who is on the
  roster but not entitled (a scene's temporary staging, a vanilla story leak, a
  companion removed by the Remove a Companion trap) is purged once the Leviathan
  has been escaped and no scene is staging anyone (`busy=0`, three stable
  reports, warm-up); a Star Forge pass handles the endgame cast (Bastila by
  path, the rest purged on arrival, nothing after Malak dies); an entitled
  companion who is listed but unselectable gets the `select_companion` trap
  (`sel=` bits). Entitlement = companion items the server has sent this slot,
  plus the delivery log, minus companions a Remove a Companion trap has taken
  for good (`trap_removed:<key>` in the delivery log, `trapped_off_companions`).
  `/ap_roster_cleanup off|log|on` controls it. The client also reports goal
  completion to the server and sends `!release` (`/ap_autorelease`). An
  incoming DeathLink is a dispatcher job that is never replayed (see
  `kotor_dispatcher.py` above), so nothing needs purging on connect; the old
  `--purge-arm=32` call is gone.
- **Companion entitlement markers and the leak purge** (`kotor_reconciliation.py`, with `build_ap_tracker_quest.py` and `generate_poll_shared.py`). Who may be
  on the roster is decided by a journal marker in the save, not by the client's records: nine quests `ap_ent_<key>`, 10 = entitled (written by the companion
  grant arm in the same script that adds the companion, so an AP item, the normal-mode auto-grant, the `ap_limited` counter and an admin grant all write it) and
  20 = trapped off for good (the Remove a Companion trap; a quest only moves forward, so it cannot be undone). The poll reports them as `AP|CREWREPORT|...`. A
  companion on the roster whose marker is not 10 is purged after settled reports across two area entries, never while a scene is busy (the roster report's `bz=`
  mask) or in the Star Forge (its own pass). `/ap_leak_purge auto|on|log|off` (default `auto`: log only until the Leviathan has been escaped). A received
  companion on the roster without a marker is repaired by re-sending her grant, not purged.
- **`kotor_location_tracker.py`** — `LocationTracker`: turns raw
  `CHECK|JOURNAL`/`CHECK|COMPANION`/`CHECK|AREA`/`ALIGNMENT` events into
  real AP location IDs, reading `ctx.checked_locations` as the single
  source of truth for "already checked" rather than keeping a second
  set. Also owns alignment-crossing detection and `true_balance_reached()`
  for the Goal system. Since 0.2.0 it also credits the quest item checks by
  item tag (poll line `AP|QUESTITEM|<tag>`; the item counts from any
  source) and the Bazaar checks by count (`AP|BAZAAR|<purchase
  receipts>|<exchange receipts>`, a high-water mark like the bounty cards);
  any journal check can carry an alternate completion value
  (`alt_journal_tag`/`alt_journal_target`, e.g. Dead Settler also on
  `dan_romance` >= 60, Tach Poaching also on `kas24_removepoachers` >= 40,
  Bacca's blade also on `kas23_mainwookplot` >= 100); and when the journal
  quest `tar_escape` reaches 99 (the Ebon Hawk takes off, so Taris and the
  Endar Spire can never be returned to) it completes every check of those two
  planets the player did not reach (the client logs them as
  released and tells the player). It is read from the journal, which lives in
  the save, so a client that was not connected at takeoff still releases them
  when it next sees the quest. A companion check released that way does not
  auto-grant the companion in `companion_mode=normal`.

### 4.3 Dev/build tooling (`scripts/`)

**Live pipeline — NWScript generators** (produce content deployed to
Override; re-run after changing their inputs):
- `generate_poll_shared.py` — the shared polling "brain" (quest flags,
  plot trackers, journal, XP/credits/skills/abilities/classes, alignment,
  Malak-defeat goal check, character level, death, self-healing heartbeat
  restart, the quest item and Bazaar receipt reports `CheckQuestItems`/
  `CheckBazaar`). It also carries the game half of the job dispatcher
  (`DtTick`, called from every poll): it reads the pending job from the DLL's
  inbox (KSE data key `dt_job`), compares its number with the one kept in the
  save, holds it while the game is not calm (`DtGateBits`), runs it, and logs
  `AP|DISPATCH|...` lines. The fixed arms it can run (the 8 skills, the 6
  abilities, XP, credits, the class and companion arms, `pc_droid`, the
  journal tracker markers, `force_death`) are generated from the `APPLIES`
  table of `generate_trampoline_batch.py`, each followed by a check that the
  result is really there; the parameterized actions `set_xp`, `delevel`,
  `force_power`, `companion_class` and `trap` come
  from `dispatch_actions.py`, which builds them from the same batch-builder
  functions with the value as a variable (or one copy per allowed value for
  the traps), so the code that runs is the code that was already proven;
  `give_item`, `set_credits` and `notify` are written in the poll itself. The
  dispatcher is part of the standard poll (`--no-dispatcher` leaves it out,
  for comparison only). `companion_class` answers `FAILED`, writing nothing,
  when the companion is not in the party.
- `generate_area_trampolines.py` — one trampoline per covered
  area/`OnEnter` resref, preserving the real original script.
- `generate_heartbeat.py` — the persistent 5s self-rescheduling tick.
- `generate_trampoline_batch.py` — regenerates a specific area's
  trampoline (the area-entry script). It used to inline the pending arm
  batch there, which is how items were delivered; nothing is staged that way
  any more, so the batch block is empty. What it still writes into the
  entry scripts: the stores' catalog (`SHOPSTOCK`), the Hawk's spawns (the
  Archipelago Vendor, the Bazaar's Jawa, the New Companion console), the
  port-gate unlocks of area randomizer seeds (`ENTRY_UNLOCKS`) and a few
  area-specific calls. Its `APPLIES` table is now the single source of the
  arm bodies the dispatcher runs (`generate_poll_shared.py` imports it), and
  the DLL's `AP_ARM_NAMES` is no longer needed for delivery (4.4).
  `build_trap_block()` (2026-09-08) generates all 12 Traps items' NWScript
  bodies from one `trap:<type>:<params>` action, following the same
  consolidated-wire-action pattern as `companion_class:`/`give_item:` —
  adding a Traps-shaped feature needed zero new native/opcode work, only
  a new case in this function plus a matching case in `dispatch_actions.py`
  (the cases in `arm_orchestrator.py` and `ap_extender.c` serve only the
  retired staged path). Also owns `_PLANET_PREFIXES` (see 4.1's
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
  `GetModuleFileName()`). The "CutStart" engine bug this family was first suspected of causing is a
  separate, unrelated problem, fixed by replacement dialog files.
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
  seed's generation project-wide until caught and fixed same session (since fixed). It is now out of date with `Locations.py`: the rows after
  id +267 (quest items, Bazaar) are hand-added and it still knows the removed New Companion row, so do not re-run it (see the
  `Locations.py` entry above).

**Live pipeline — runtime orchestration:**
- `arm_orchestrator.py` — no longer how anything is delivered (that is the
  job dispatcher, 4.2). Invoked by the extender's C code on an area change
  and when the store catalog arrives (`SHOPSTOCK`), and by the client on
  Connect, it still rebuilds the area-entry scripts (current area + graph
  neighbors) through `generate_trampoline_batch.py`, which is where the
  stores' catalog and the Hawk's vendor, Jawa and console spawns live.
  `--ensure-vendor` rebuilds just the Hawk's script (and the two port-gate
  areas of area randomizer seeds) so those spawns match the connected seed's
  options; `--reset-if-owner-changed` cleans a previous slot's state; `--clear-all`
  empties the old staged queue (see 4.2). Its queue code (`--queue-*`,
  `--delivered`, `--purge-arm`) is kept but unused: nothing stages an arm.

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
  `patch_item_suppression.py` now only takes back out a leftover deployment of the first-design Progression System wrappers; the story gates replaced them
  (`patch_story_gates.py`, below).
- `patch_door_randomizer.py` — rewrites each shuffled transition's
  `LinkedToModule`/`LinkedTo` GFF fields to match the seed's computed
  mapping. No compiler dependency at all (pure GFF field edits). Besides the
  door unlocks it already did, it opens the barriers a shuffled arrival
  would hit: the Manaan West Central port gate, the Dreshdae port gate, the
  Manaan Sith embassy door and both Hidden Bek doors (the Dreshdae denial
  conversation and the Hidden Bek control-room conversation are cleared
  too), removes the Sand People kill trigger and its 8 turrets, and clears the
  Dantooine west trigger's script. The two port gates are locked again by
  their areas' own entry scripts, so `generate_trampoline_batch.py` adds an
  unlock to those entry scripts for these seeds (`ENTRY_UNLOCKS`).
- `patch_additional_enemies.py` (2026-09-08) — the fourth per-seed
  patcher, same pattern as the two above. Reads `additional_enemies_mode`
  from slot_data and, for each of 195 precomputed safe spawn points
  across 40 modules (Tables A/B/C), places
  a creature chosen by mode (`area_appropriate`: CR-filtered, drawn from
  that module's own dominant category; `random_sane`: CR-filtered, full
  safe pool; `fully_random`: unfiltered). Seeded by the real AP
  `seed_name` so a reconnect reproduces identical placements.
  Live-tested at both extremes; `random_sane` itself not yet separately
  exercised (mechanically identical minus the category filter).
- `patch_boss_datapads.py` — always
  on, run on every connect after the other module-file writers. Writes the three
  boss datapad item templates (`ap_dp_calo/bandon/karath`) and appends the datapad
  to 10 fighting templates in 5 modules (Calo Nord, Darth Bandon and Saul Karath; the
  Taris Calo Nord and the Endar Spire Bandon are excluded); a boss killed before the
  patch runs cannot be looted retroactively. Picking one up completes the matching
  `Boss: ...` check (poll `CheckBossDatapads`,
  tracker `datapad` location type, never able to hold a progression item).
- `generate_location_items.py` — the 78
  visited-area marker items `ap_loc_<idx>` ("Location: <area>", plot items), static
  and seed-independent, listed in `extender/scripts_src/_location_manifest.json`
  for `package_dist.py`. Every area's entry script (the shared `area_entry_diag_lines`
  in both area generators) gives the player its marker once; the poll's
  `CheckVisitedMarkers` reports the set (`AP|AREASVISITED|<idx,idx,...>`, on change
  plus about once a minute) and the tracker credits each `Visited:` location, so an
  area entered while the client was closed is still credited. Presence is the whole
  record (item variables do not survive an area change); a strip (Endar Spire,
  Leviathan) only costs a backfill and the marker is recreated on re-entry.
- `patch_player_id.py` (passive: nothing is enforced on it) — writes
  `Override/ap_pid.uti`, the Player ID item, on every Connect (a placeholder ships in the
  bundle). Its name is "Player ID: <slot> <hash>", the hash being `save_id_for(seed_name, slot)`
  (first 9 hex of sha1 of `seed|slot`, in `KotorClient.py`). The `end_m01aa` entry script
  (`area_entry_diag_lines`, idx 0) gives it to a brand-new level-1 character once; the item
  data, name included, is baked into the save. The poll's `CheckPlayerId` prints
  `AP|PLAYERID|<name>` (or `NONE`) on change plus about once a minute; the client records the
  hash as `save_id` on each new delivery-log line and logs a warning on a mismatch or when the
  save has none. Nothing is paused on it: the character-name safeguard is still the only guard.
- `patch_story_gates.py` — deploys the in-game side of the Progression System on every Connect when the option is on (and removes it when it is off): the 24 item
  templates `ap_tk_<family><n>` (plot items, so they cannot be sold or dropped), 51 gate scripts (`extender/scripts_src/sg_*.nss`; 50 on seeds without the area randomizer) and 10 edited dialogs. A gate is
  `ApGateOpen(family, step)` in `extender/scripts_src/ap_gate.nss`, which counts the family's items in the player's inventory (so it needs no variable and
  survives saves) and also requires the family before it to be complete (the story chain). Script kinds: wrap (the vanilla script is kept under an `apo_sg_*`
  alias and run only when the gate is open), reimpl (a replacement for a vanilla condition or node script), dispatch (one name used by two modules, which
  picks that module's original at runtime) and new (no vanilla counterpart). Gates that guard a dialog starter insert a first "not yet" starter through
  `story_gate_dialogs_unknown.py` and `story_gate_dialogs_korriban.py`. A closed gate makes the player say a one-line dialog (`ap_gate_msg`), because on-screen
  messages do not show; a gate decided in the middle of a conversation uses `ApGateSayLater`, which speaks it once the conversation has ended. Gates hold story
  beats only, never doors or travel: the Manaan submarine door is no longer opened by a gate (`k_pman_door08` is listed in `RETIRED_GATES` and taken out of
  Override, so the game's own script runs and the door needs the card Roland hands over at the debrief, which the second Manaan gate holds); Kashyyyk's third
  gate holds only the conversations (Chuundar's, Gorwook's fallback to his ordinary lines, a "not yet" starter on Chorrawl's), leaving every movement script
  alone; and the Hrakert Rift's two exit doors, computer panel and two triggers are wrapped (`k_pman_at01`/`at02`) so that the game's own seal, which waits for a
  star map the third Manaan item holds back, never shuts the player in. In area randomizer seeds the Taris elevator guard needs no Sith armor. The star-map counter is handled by
  `k_pdan_starmap02` (the Dantooine ruins map adds 10 instead of setting 10, so planet maps found earlier are kept), and `k_pebn_galaxy` on the Hawk's galaxy map
  console raises the Unknown World flag when all five star maps are counted and the Leviathan is done.
- `generate_droid_assets.py` — installs (or removes, when neither option is on; it runs on every Connect) everything the droid options need in Override: the Battle
  Droid class (a tenth `classes.2da` row, class 9, with its own feat, skill and level-gain columns), the melee weapon types opened to droids (`baseitems.2da`), the
  human-rig droid models (war droid, assassin droid and an HK-47 PC variant) so melee weapons swing, the Mark Two droid's ranged animations, wrappers that let a droid
  PC past the Taris elevator guard and roll Persuade on Charisma, and, for `companion_class: droid`, droid-race templates for the seven organic companions. The plan
  (a look and a class per companion) is rolled at generation time by `roll_droid_companions` in `__init__.py`: seven looks from twelve (at most two companions
  share a model type, with different paint jobs) and a 3/2/2 hand of Combat, Expert and Battle Droid classes; the human-rig looks are swapped onto Battle Droids
  when one is available. A manifest records everything written so it can be taken out again.
- `generate_ap_vendor.py` — the Archipelago Vendor's dialogue, gating scripts,
  NPC and the five Vendor Pass items, written once on the dev machine and shipped
  from `extender/scripts_src/_vendor_manifest.json` plus the raw files. The
  vendor is its own option (`archipelago_vendor`) and always stands on the Hawk;
  each menu except Character Respec needs its pass.
- `generate_new_companion_assets.py` (the original Meetra and Malak builds live-tested; the console characters since less so) — the
  `new_companion` option (off / on / random_class). It builds the six characters
  the New Companion console (next entry) can put in HK-47's or T3-M4's party
  slot: Meetra Surik (Jedi Sentinel), Darth Malak (Jedi Guardian), Calo Nord
  (Soldier), Yuthura Ban (Jedi Consular), Darth Bandon (Jedi Guardian) and
  Trask Ulgo (Soldier). HK-47 is always recruited the vanilla way: the
  Tatooine recruit trigger it deploys is the true vanilla one whatever the
  option says (the earlier `apo_hk47_new` variant that put Meetra in HK-47's
  place at recruitment is no longer used). With the option on it deploys, on
  every `Connected` (not seed-gated):
  - A level-1 template per character (`p_meetra.utc`, `p_malak.utc`,
    `p_calo.utc`, `p_yuthura.utc`, `p_bandon.utc`, `p_trask.utc`) whose Tag is
    `"HK47"` — load-bearing for a game-wide, generic companion tag-exclusion
    check every companion is subject to, and for the console's swap scripts,
    which resolve the slot by that tag — plus a second copy for T3-M4's slot
    (`p_<name>_t3`, Tag `t3m4`; an object's tag is fixed in its template and
    cannot be set when it is created, so each slot needs its own). Meetra's
    stat block takes its ability scores/skills/combat-tuning fields from
    Bastila's own real template (same class, Jedi Sentinel) wherever a field
    doesn't scale with level; HP/FP/feats/starting Force powers are
    independently re-derived for level 1 (`classes.2da`'s hit die/force die +
    CON/WIS modifiers; the "4 mandatory Jedi feats + class signature" recipe
    already used by `companion_class` conversions; the 5 "base tier" starting
    Force powers `spells.2da` shows are outside the normal level-6+ learn
    list, i.e. the standard from-creation Jedi kit). Everything except Meetra
    is an ordinary party body (Juhani's, Carth's for Calo) whose `OnSpawn`
    script (`k_hmal_spawn01`, `k_hcal_spawn01`, `k_hyut_spawn01`,
    `k_hban_spawn01`, `k_htra_spawn01`) applies a permanent `EffectDisguise` of
    the character's own appearance row, so no custom model is needed.
  - A spawn script, a one-line greeting dialog (`k_h<name>_dialog.dlg`; a
    replacement has only that greeting, no personal subplot) and a
    `portraits.2da` row per character.
  - `random_class` (`new_companion` = 2): the class the seed rolled for each
    character (`new_companion_classes` in the slot data, which `KotorClient.py`
    writes to `_slot_data.json` at Connect) is written into each template —
    class, that class's starting feats, starting Force powers for a Jedi class,
    hit points, Force points — before the T3-M4 copies are made, so both slots
    agree. The class is fixed for the seed.
  - **No body armor for Bandon.** Equipping robes on Bandon crashed the game (a
    disguised character's body model is rebuilt from the disguise's appearance
    row, and his row has a single body model). `GEAR_RESTRICTED` (currently only
    Bandon; live tests found Malak, Calo and Yuthura wearing body armor without a
    crash, Trask not tried) gives a character a subrace that `baseitems.2da`
    denies the body-armor rows to (reusing the mechanism that keeps Wookiees
    out of Jedi robes), and in its place natural armor class and a bonus to
    each save (`GEAR_SLOT_NATURAL_AC`/`GEAR_SLOT_SAVE_BONUS`, about the value
    of end-game body armor). Head and Hands items stay allowed for everyone.
  - **Malak's appearance** uses the same disguise mechanism: `k_hmal_spawn01`
    self-applies `EffectDisguise(DISGUISE_TYPE_N_DARTHMALAK)`, rendering his
    real, unmodified vanilla appearance.2da row (21) straight from
    `models.bif`; this superseded three earlier, all-failed custom-model/
    head-splice attempts (visually broken or crash-associated). His attacks
    didn't animate at all once he was a companion — the real `N_DarthMalak`
    model has `supermodel=NULL` (zero animation fallback of any kind), and
    `baseitems.2da`'s Lightsaber row is `weaponwield=2`, so his own partial
    set was never the right group. Fixed by splicing animations from
    `S_Male02` into his model via MDLOps
    (`scripts/fix_malak_basic_attack_animations.py`): the melee swings
    (`g2a1`/`g2a2`) and, since he now also holds firearms as a party member,
    the ready/wound/guard/dodge/attack animations of the blaster pistol,
    rifle, repeating blaster and double blade groups and the rifle and
    double-blade walk/run styles. `pykotor`'s own `write_mdl` reliably crashed
    the game on every attempt at this edit (confirmed via decoding the actual
    Windows crash dumps); MDLOps' independent, ~20-year-old writer did not.
    Known, accepted limitation: he doesn't show the standard party-member
    knockdown pose at 0 HP (`appearance.2da`'s `disableinjuredanim` is set on
    his row, a deliberate vanilla "boss never shows weakness" flag) —
    confirmed this doesn't affect the vanilla endgame Malak fight itself.
  Wired into `KotorClient.py` (`apply_new_companion_assets()`/
  `_apply_new_companion_assets_and_log()`, `/ap_apply_new_companion` manual
  fallback), same not-seed-gated shape as `patch_galactic_shop.py`. Because
  the replacement is a console choice rather than a different item or
  location, there is no second "New Companion" item/location pair any more
  (HK-47's and T3-M4's own are never removed).
- `generate_new_companion_console.py` — the New Companion console on the Ebon
  Hawk. The AP item "Ebon Hawk: New Companion Selection" is the plot item
  `ap_nc_console` (`give_item:ap_nc_console`); while the player holds it the
  Hawk's entry script (an `AREA_PERMANENT_SPAWNS` entry in
  `generate_trampoline_batch.py`) places the terminal `ap_nc_term`, a clone of
  the Endar Spire's security computer, between HK-47's spot and the swoop pod,
  so it appears on the next entry to the Hawk after the item arrives. The
  terminal's conversation `ap_nc_dlg` first asks whose place a new companion
  should take, HK-47's or T3-M4's (a slot is offered once its companion has
  joined, `IsAvailableCreature`); each slot's menu offers the six
  characters plus the slot's own original, and a character already in one slot
  is not offered for the other, so nobody stands in both. A swap removes the
  current character of the slot and creates the chosen one there from a fresh
  template (the slot's Tag and NPC slot stay HK-47's or T3-M4's): if the old
  one was in the party the new one joins it, otherwise the new one stands at
  the slot's spot on the ship. Level, gear and feats are not carried over. The
  current occupant is recognised by name (`GetName`), so the console stores
  nothing. Other slots are deliberately not offered: story scripts address
  companions by tag and slot number, and class assignment, feat training and the
  personal-subplot checks are per slot; on the other hand scripts that name
  `HK47` or `t3m4` by tag also treat a replacement as the droid (on Kashyyyk
  the landing scenes play HK-47's lines at its spot), which is a known,
  accepted side effect. Generated files: `ap_nc_c_<key>`/`ap_nc_s_<key>`
  (HK-47 slot) and `ap_nc_ct_<key>`/`ap_nc_st_<key>` (T3-M4 slot) condition
  and swap scripts, `ap_nc_hk_ok`/`ap_nc_t3_ok`, the greeting conditions
  `ap_nc_greet`/`ap_nc_greett`; `/ap_dispatch nc_here` (developer, needs
  `KOTOR_AP_DEV=1`) places the terminal in front of the player to test a spot.
- `generate_party_console.py` — the Party Console item (AP item "Party
  Console", `give_item:ap_partycon_a`, always in the pool while companions
  exist). A plot item with one CastSpell property on a reused `spells.2da` row
  (132) whose impact script `ap_party_console` opens the one-question dialog
  `ap_party_con`, whose answer opens the party selection screen. It refuses
  (with a message) in the Taris cantina and its Duel Ring arena, the Korriban
  star map tomb, the Star Forge Malak fight (`BLOCKED_MODULES`) and on the
  Ebon Hawk (`BLOCKED_PREFIXES`, modules starting `ebo_`). The script's own
  docstring still calls it a developer test, and its files are not yet in
  `package_dist.py`'s lists.
- `generate_feat_training.py` — Additional Feats as a training dialog. Each of
  the seven non-droid companions' conversation files gets one new first
  starter whose condition (`ap_ftr_front`) holds while the companion's unlock
  item `ap_ft_<key>` (the AP item "Additional Feats Character: <name>") is
  held, the player is not in combat and the module is not the Ebon Hawk (module
  names starting `ebo_`). It shows a short menu: train in a new feat / "Let's
  talk." / never mind. "Let's talk." links to exactly the starters the file had
  before (same entries, same conditions), so the story conversation is
  unchanged, and a companion without the item behaves exactly as before; edits
  are made on the raw GFF (new nodes appended, one starter inserted). The
  picker lists, from the 18 feats of the old Additional Feats pool (the 11
  passive ones the Archipelago Vendor also offers and 7 active/toggle ones), the
  ones the companion does not know; Force Jump, Force Focus and Force
  Immunity: Fear show only for a companion with Force levels. The price is
  1,000 credits for a companion's first feat and 2,000 more for each feat that
  companion has already been trained in, counted by a plot receipt
  `ap_fn_<key>` (one per training) that lives in the save, so a reload restores
  credits and count together; credits are taken only after `KSE_GetFeatAcquired`
  confirms the feat, and a full feat array charges nothing. Nothing is queued,
  drawn at random or retried: the feat is granted by the dialog's own script.
  The generated dialogs and the 14 items (`ap_ft_<key>`, `ap_fn_<key>`) are in
  `extender/raw_override_files`; Juhani's base is the project's own changed
  file (`extender/dialog_bases`), the other six are built from the game's.
- `generate_bazaar_jawa.py` and `patch_bazaar_tokens.py` — the Archipelago
  Bazaar (`bazaar` option). A Jawa trader (`ap_jawa_npc`, spawned by the Hawk's
  entry script next to the Archipelago Vendor) gives the player a check, never
  an item: five purchases for credits (1,000 for the first, 2,000 more for each
  later one) and twenty token exchanges at five Bazaar tokens each. Each
  completed deal hands over a plot receipt (`ap_bz_buy`/`ap_bz_swap`); the
  number of receipts held is the number of deals done, so price and count
  both live in the save, and the poll's `CheckBazaar` reports them for the
  tracker. The 100 tokens (`ap_bz_token`, a copy of the Sith Medallion
  template) are placed by `patch_bazaar_tokens.py`: one per container, never
  an enemy's drop, at most 10 in a module, none in the end game, the Ebon Hawk
  or the Endar Spire; a container gets its own copy of its template
  (`apbz<NNN>.utp` in Override) with the token added, chosen by the seed name
  so a re-run gives the same placement. It edits module RIMs in place like the
  other module patchers, so it must run after `patch_loot_disturb.py` (see
  4.2); `--restore` puts the backups back. The Jawa's and the token's
  generated files are not yet in `package_dist.py`'s lists.

**Distribution/packaging** (for getting a fresh install running without
the full dev toolchain — see `README.md`):
- `package_dist.py` — collects the always-on generated Override content
  into `dist/Override/`, deriving the exact file list from the generator
  scripts' own data so it can't silently drift. **`EXTRA_RAW_FILES`**
  ships the non-`.ncs` files verbatim (never compiled) from
  `extender/raw_override_files/`: the replacement `.dlg` files that fix the
  "CutStart" engine bug (see TESTING.md's troubleshooting notes), the Player ID
  placeholder `ap_pid.uti`, the 78 `ap_loc_*.uti` location markers, the vendor
  token templates and dialogs, the Leviathan console and dialogs, and the extra
  lightsaber crystal icons, sourced from the repo itself rather than a dev
  machine's live game install, since they're static and seed-independent. The 87
  vendor scripts and the other hand-written scripts ride in
  `HAND_WRITTEN_EXTRA`.
- `setup_game.py` — tester-facing: copies `dist/Override/` into a real
  install. Pure standard library, no `pykotor`/compiler needed.
- `install_playerbundle.py` (2026-09-08, the "3-step install" plan's
  Step 2) — the real, only tester-facing installer: calls `setup_game.py`,
  copies the now-bundled `nwnnsscomp.exe` into the game folder root,
  installs the merged `binkw32.dll` proxy and writes
  `%LOCALAPPDATA%\KotorAP\python_path.txt` (the real interpreter that ran
  this installer, so `ap_extender.c`'s orchestrator shell-out never has to
  guess at a working Python from the game process's own inherited PATH --
  see 4.4's `ap_run_orchestrator()` entry), `pip install`s `pykotor`, and
  writes an
  install-path marker (`%LOCALAPPDATA%\KotorAP\install_path.txt`, which the
  apworld's "KOTOR Client" Launcher button reads) plus a
  manifest (`install_manifest.json`) recording exactly what it touched.
  `--uninstall` reverses all of it -- the patch scripts' own `--restore`
  (loot_disturb, item_suppression, door_randomizer, additional_enemies,
  boss_datapads, galactic_shop, area_poll_hooks), the DLL swap, and only the
  Override files THIS run actually added (anything that already existed
  with the same name is left alone, since Override is shared space).
  Verified against a synthetic fake game directory, install then uninstall,
  byte-for-byte correct on both sides, and installed by real testers.
- `package_playerbundle.py` — builds the PlayerBundle zip (the Client
  folder's extra files: `KotorClient.py` and its helper modules including
  `entitlement.py` and `kotor_dispatcher.py`, the scripts (including
  `dispatch_actions.py`, which the poll generator imports), the extender folder, `Install.bat` and
  `Uninstall.bat`). Its `FILES`/`DIRS` lists do not update themselves: a new
  file a tester needs must be added there, and `BUNDLE_VERSION` is bumped by
  hand together with `WORLD_VERSION`.
- `package_apworld.py` — packages `Archipelago/worlds/kotor/`
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
them as `EVENT:` lines, and handles incoming `DISPATCH:<seq>:<action>[:<args>]`
commands by leaving the job in a one-slot mailbox (`kse_inbox_put`, in
`kse_hook.cpp`): the socket thread must not write into the script data store,
so the script VM's thread moves the job into the store key `dt_job` at the
start of its next store operation, where the poll reads it (a newer job replaces
one not yet moved; the reply `STAGED:dispatch:<seq>` only means "in the
mailbox", the game's `AP|DISPATCH|APPLIED` line is the real confirmation).
`SHOPSTOCK:` and the area-change events still shell out to `arm_orchestrator.py`
(4.3). The older `APPLY:`/`APPLYVALUE:`/`NOTIFY:` handlers and the
orchestrator queue they feed are still in the DLL, but the client no longer
sends them; `AP_ARM_NAMES[]`, the arm-ID table those handlers look names up in,
is therefore used only by that retired queue (the dispatcher names arms by the
labels of `generate_trampoline_batch.py`'s `APPLIES`). The native `KSE_SetCreatureField` also writes a character's race (field 33, droid or human only) for the droid options.

4.3's `install_playerbundle.py` captures the game folder's real
`binkw32.dll` as `binkw32_real.dll` (once) and swaps in this compiled
proxy, plus writes `ap_repo_root.txt` (read by `ap_extender.c` at runtime
to find `scripts\arm_orchestrator.py`) and `python_path.txt` (read by
`ap_run_orchestrator()` to resolve a real Python interpreter instead of
trusting a bare `"python"` command against the game process's own
inherited PATH -- see that function's own comment in `ap_extender.c` for
the real tester failure this closes: a wrong/stale PATH resolving
`"python"` to the Microsoft Store's placeholder stub, failing every
orchestrator call silently until the next full game restart). A separate
PowerShell equivalent (`extender/install.ps1`) existed previously; it's
retired now rather than kept in parity by hand, since it never wrote
`python_path.txt` and silently reintroduced exactly that failure for
anyone who used it instead of `Install.bat`.
