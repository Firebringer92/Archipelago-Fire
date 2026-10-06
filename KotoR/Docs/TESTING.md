# KotOR Archipelago — running and testing a seed

This describes the REAL, current pipeline: a real generated seed, a real
local Archipelago server, the actual KOTOR game running with this
project's merged extender DLL loaded, and `KotorClient.py` bridging
between them over a local socket. If you haven't installed the extender
DLL yet, do that first — see `README.md`'s Steps 1-2.

Every command below assumes `SKIP_REQUIREMENTS_UPDATE=1` is set in your
environment — without it, `Generate.py`/`MultiServer.py`/the clients try
to interactively confirm installing per-world extra dependencies (for
*other* games bundled in the Archipelago clone, not KotOR) and hang
waiting on a prompt that never comes. On Windows PowerShell:
`$env:SKIP_REQUIREMENTS_UPDATE=1`. You'll also see a wall of `Could not
load world ...ModuleNotFoundError` tracebacks on every run — those are
unrelated bundled games missing optional third-party deps this project
never installed. Harmless noise, ignore them.

## 1. Generate a seed

From `Archipelago\`:

```bash
python Generate.py --player_files_path Players
```

Reads every `.yaml` in `Players\` (start from the `KotoR_TEMPLATE.yaml` in the
project's `Docs` folder — copy it and edit your own, see `README.md` Step 3) and writes a zip into
`Archipelago\output\`, e.g. `AP_<seed>.zip`. That's the real multiworld
data the server hosts.

## 2. Start a local server

```bash
python MultiServer.py output/AP_<seed>.zip
```

(swap in the real filename). Prints `server listening on 0.0.0.0:38281`
and sits there. State (checked locations, received items) lives in memory
only — restart the server for a clean slate, or leave it running to pick
up where a previous session left off.

## 3. Connect the client, THEN launch the game

**Connect before launching KOTOR, not after.** `KotorClient.py` writes
your seed's real options to a local file the moment it connects to the
AP server — whether or not KOTOR is even running yet — and both
`patch_item_suppression.py`/`patch_door_randomizer.py` (step 3b below)
and the automatic `ap_poll_shared.ncs`/Dantooine-suppressor regeneration
need that file to exist before the game starts reading its own Override/
modules. Connecting first means everything's correctly in place from the
game's very first load, instead of needing a mid-session restart.

In a **real terminal** (not a piped/non-interactive shell — the client's
stdin reader doesn't behave the same over a non-TTY pipe), from
`Archipelago\`:

```bash
python KotorClient.py --connect localhost:38281 --nogui
```

`KotorClient.py` auto-detects where `scripts\generate_poll_shared.py`/
`scripts\generate_makejedi_suppressor.py` live (checking both the merged
single-folder layout README.md Step 1 sets up and a nested `Archipelago\`
subfolder, matching this repo's own dev layout). If it still can't find
them — a genuinely unusual folder layout neither guess matches — pass
`--repo-root` pointing at the folder that actually has `scripts\` in it:

```bash
python KotorClient.py --connect localhost:38281 --nogui --repo-root "C:\...\your-playerbundle-folder"
```

Enter your slot name when prompted (must match the `name:` field in your
player yaml). `/ap_status` will say the extender isn't connected yet —
that's expected, since KOTOR isn't running. Leave this window open.

On every successful connect, the client also automatically regenerates,
compiles, and deploys `ap_poll_shared.ncs` to your game's live Override,
matching this specific seed's real `area_randomizer` and Additional Enemies
setting — this replaces a script (`generate_poll_shared.py`) that used to be
a manual, easy-to-forget dev-only step. Look for a `[poll_shared] regenerated
for area_randomizer=..., additional_enemies_mode=...` line in the client log right after
connecting; a `[poll_shared] regeneration FAILED` line instead means
something (usually a stale `nwnnsscomp.exe` path or `--game-dir`
mismatch) needs fixing — use `/ap_regen_poll` below to retry once fixed.

**The per-seed game-file patches also run automatically on connect**, right after
the poll_shared/makejedi regeneration above: Loot Mode, Progression System
checkpoints (item suppression), door randomization and Additional Enemies, then
Galactic Shop, New Companion, the area poll hooks and the boss datapads. Look for
`[loot_disturb] ...`, `[item_suppression] ...`, `[door_randomizer] ...` and
`[additional_enemies] ...` lines in the client log: `applied: ...` the first time,
`already applied for this option set -- skipping re-run.` when you reconnect with the
same options, and `APPLY FAILED: ...` when something needs fixing (check the message
— usually a `--game-dir` mismatch). Unlike poll_shared/makejedi (a cheap
single-file recompile, always re-run), these four do a real per-module sweep, so
they are gated on a fingerprint of the seed's options changing. Use `/ap_patch_all`
below to force a re-apply after fixing a failure.

## 3b. (Historical — now automatic, see above) Apply item suppression / door randomization by hand

Before 2026-09-08, this required a second terminal, after connecting once
in step 3:

```bash
python scripts\patch_item_suppression.py --game-dir "C:\...\swkotor"
python scripts\patch_door_randomizer.py --game-dir "C:\...\swkotor"
python scripts\patch_additional_enemies.py --game-dir "C:\...\swkotor"
```

Kept here only as a manual escape hatch (e.g. running against a game
install `KotorClient.py` isn't pointed at, or debugging one script in
isolation) — normal play never needs this any more. All 3 read
`extender\area_trampolines\_slot_data.json` — written by `KotorClient.py`
on every successful connect — instead of hunting for a locally generated
seed zip, which is also why this works identically whether you
generated/hosted the seed yourself or are joining someone ELSE's
multiworld.

## 4. Launch the game

Launch KOTOR normally and load into a save. The client from step 3
(still running) picks up the extender automatically once the game is
up — `/ap_status` should switch to showing `Extender: CONNECTED`. If it
doesn't, confirm `swkotor.exe` is actually running and the DLL loaded
(check `kse.log` for `K1SE DIAG` lines arriving) before troubleshooting
further.

**Set the frame rate first (known base-game bug, not the randomizer).** KOTOR 1 can leave the character unable to move during or
just after a fight, for 15 to 55 seconds, and it is much more likely with an unlimited frame rate or a high-refresh display
(V-Sync off, a 120/144 Hz panel). Before playing: turn V-Sync on in Options, Graphics, Advanced Options, and cap the game at 60 FPS
(NVIDIA Control Panel, Manage 3D settings, Program Settings, `swkotor.exe`, Max Frame Rate 60 and Vertical sync On; or choose a
60 Hz mode in the in-game resolution list). If you still get stuck: hold forward while panning the camera (map a key to Pan Camera
Left or Right in Options, Controls) for a second or two, or click an object or another party member, or quicksave and quickload.
Nothing the randomizer sends to the game releases it; only real mouse or keyboard input does.

## 5. Useful client commands

- `/ap_status` — extender connection state, pending/recent deliveries.
- `/ap_apply <arm_name>` — admin/testing safety valve: directly queue an
  arm with the extender, bypassing the AP server entirely (exactly the
  same call the real item-received path makes). Use `/ap_apply` with no
  argument to see the full list of known arm names. Special forms:
  `give_item:<resref>[:<count>]` for gear, `companion_class:<name>:<class>`
  for the companion class-randomization feature (see `Options.py`'s
  `CompanionClass`), `additional_feats:<key>` (`pc`, `bastila`, `canderous`,
  `carth`, `jolee`, `juhani`, `mission`, `zaalbar`), `force_power:<row>` and
  `trap:<type>[:<params>]` (for example `trap:remove_companion`).
- `/ap_check <location name>` — manually report a location check by name
  (bypasses the normal auto-detection).
- `/ap_locations` — list every location and whether it's checked.
- `/ap_clear_queue` — admin: drops EVERY entry staged for the game but not yet applied. The client already drops the entries it
  re-derives from fresh polls (XP/credit/level corrections, companion classes, the tracker stages) every time it connects to the game;
  use this when anything else staged keeps firing on every load. The gear, traps and other grants it drops that cannot be re-derived are
  journaled (`extender/area_trampolines/_dropped_queue.json`); `/ap_restore_queue` stages them again.
- `/ap_restore_queue` — admin: re-stages what the last `/ap_clear_queue` dropped (item grants, traps, force powers, feats, plain arms).
  Corrections the reconciler recomputes and queued DeathLink deaths are never restored; an entry already staged is not added twice.
- `/ap_regen_poll` — manual fallback: re-run the automatic `ap_poll_shared.ncs`
  regeneration described above, using this session's already-connected
  `area_randomizer` and Additional Enemies setting. Use this if the automatic regeneration
  failed on connect, or after manually touching the game install's Override.
- `/ap_confirm_character` — see "New-character safeguard" below. Only
  needed if you see a `[SAFEGUARD]` warning after connecting.
- `/ap_regen_makejedi` — manual fallback for the Dantooine make-jedi
  suppression wrapper (prevents the vanilla trial from granting a free
  Jedi class outside `starting_class`'s gating), same idea as `/ap_regen_poll`.
- `/ap_patch_all` — re-applies the per-seed game-file patches (Loot Mode,
  Progression System checkpoints, door randomization, Additional Enemies, boss
  datapads, Jedi suppression), ignoring the already-applied marker. Use it after an
  `APPLY FAILED` line, or after manually restoring or editing the game install and
  wanting a clean re-apply.
- `/ap_apply_galactic_shop`, `/ap_apply_new_companion`,
  `/ap_apply_area_poll_hooks`, `/ap_apply_shop_item_costs`,
  `/ap_apply_tracker_quest` — the same kind of manual fallback for the
  patches that run on every connect (Galactic Shop crate, the New
  Companion assets, the poll hook for areas with no OnEnter script, shop
  prices, the in-game Archipelago Tracker journal quest). The boss
  datapad patch and the vendor refresh also run on every connect and have
  no manual command; reconnecting re-runs them.
- `/ap_restore_all` — reverts the per-seed patches (the same set `/ap_patch_all`
  re-applies). The always-on patches (Galactic Shop crate, area poll hook, New
  Companion, shop prices) are not touched by either command; `Uninstall.bat` removes
  them. Connect with the game CLOSED: the patches rewrite module files.
- `/ap_autorelease [on|off]` — when your goal completes the client tells
  the server and sends `!release` for you (only if the room's release
  permission is `goal` or `enabled`; `auto` rooms release by themselves,
  `disabled` rooms are left alone). On by default.
- `/ap_roster_cleanup [on|off|log]` — the reconciler removes a companion
  from your roster/party when you aren't entitled to them (a scene's
  temporary staging, a vanilla story leak, a companion removed by the
  Remove a Companion trap). `log` only reports what it would do.
- `/ap_shop` — Galactic Shop (Void Trade) status for this slot.
- `/received` — item receipt history (standard Archipelago client command).

**Use `/`, not `!`, for the commands above** — despite older guidance in
this doc, `/` is the ONLY real command marker: `CommandProcessor`'s base
class (`Archipelago/MultiServer.py`'s `CommandProcessor.marker = "/"`)
hardcodes it, and every command (built-ins like `/connect` AND this
client's own custom `ap_*` commands, registered into the exact same
`commands` dict) is only ever recognized through it. There is no separate
`!`-prefix mechanism anywhere in the code. Typing `!ap_status` doesn't
error locally -- it silently falls through to `default()`, which for a
connected client means it gets sent to the AP **server** as a raw message,
which then correctly reports "Could not find command ap_status" (a real
`MultiServer.py` command list, nothing to do with this client at all).
Confirmed live (2026-09-03): `!ap_apply`/`!ap_status` reliably produced
exactly this silent-wrong-target failure, while `/ap_apply`/`/ap_status`
worked correctly every time. If you're running the client from a
bash-family shell, `!` also triggers bash's own history expansion
(`event not found` errors) as a second, unrelated reason to avoid it --
use `cmd.exe`/PowerShell, or `set +H` in bash to disable it if you must.

## 5b. What to look at in this build

Quick checks for the newest features (details and known gaps are in
`docs/MODE_DEPENDENCIES.md`):

- **Archipelago Vendor** (`archipelago_vendor: true`): connect, relaunch the
  game once, board the Ebon Hawk. The vendor stands by the repair bench in
  the main hold. Only Character Respec is offered until a Vendor Pass arrives;
  each pass (Skill, Ability, Feat, Force Power Training, Alignment Change)
  opens its own menu. A lost pass is re-granted by the client.
- **Boss datapads**: always on. Calo Nord, Darth Bandon and Saul Karath each
  drop a datapad on death; picking it up completes the matching "Boss: ..."
  check. These checks never hold a required item.
- **Remove a Companion trap**: the companion is removed for good (party,
  roster and standing object). The client remembers it across restarts.
- **Companion listed but greyed out on the party screen**: should now fix
  itself within a few polls (`[reconcile] ... not selectable` in the log).
- **Goal and release**: on completing the goal the client log shows
  `[goal] Goal status sent` and `[goal] Sent !release`.
- **Connect-time DeathLink purge**: a DeathLink that arrived while the game
  was closed is dropped on the next connect (`[deathlink purge]`).
- **Star Forge ending**: after Malak, the Deck 1 conversation starts about
  nine seconds after you arrive; wait for it before walking to the Hawk.
- **Area state**: each `AP|CHECK|AREA|<n>|seen=0/1` line in kse.log says
  whether the game restored the area's saved state on entry. `seen=0` on
  an area you have already visited, with no save load in between, is
  worth reporting.

## New-character safeguard

On every connect, the client checks the current character's name against
every character name it's ever logged a delivery for. If the name is
**unrecognized AND the character is above level 1**, every delivery and
correction is paused — nothing gets sent to the game — and you'll see a
`[SAFEGUARD]` warning block in the log explaining why, along with any
previously-known character name(s).

This exists to catch an easy accident: connecting to the wrong save (or
the right save with the wrong character) would otherwise silently dump
the *entire* backlog of items you should have received by now onto
whoever's currently loaded. A genuinely new, level-1 character can't
have any prior history by definition, so that case always proceeds
automatically — you'll only ever see this warning for an unrecognized
name that already has some progress on it.

If you see the warning and this really is the character/save you meant
to connect with, run `/ap_confirm_character` to proceed — everything
paused resumes immediately. Otherwise, close the client, load the
correct save, and reconnect.

**This also shows on the Status tab** (2026-09-14), not just as a log
line — a real incident found this the hard way: a forgotten mid-session
"New Game" left deliveries silently paused for 20+ minutes, with the only
sign being a `[SAFEGUARD]` line buried in the Heartbeat log. The Status
tab now shows an impossible-to-miss warning with the unrecognized
character's name whenever this is active, right next to the extender
connection status.

## Reporting a bug — what to send

A short description alone is rarely enough to root-cause a delivery or
crash bug — send these along with it:

- **`%LOCALAPPDATA%\KSE\kse.log`** (and `kse.log.1` if present — the
  single kept backup from the previous run). Every `KSE_Diag(...,
  "AP|...")` line from every script lands here — suppression firing,
  arms applying, companion class changes, etc. Usually the single most
  useful file for "something didn't apply" or "the wrong thing applied."
- **`%LOCALAPPDATA%\KotorApExtender\extender.log`** — the extender DLL's
  own log: socket connect/disconnect, orchestrator shell-outs and their
  exit codes, `ap_run_orchestrator: FAILED` blocks. This is where a
  silently-broken delivery chain shows up (see "Known rough edges" below)
  — check this first for anything that looks like "staged but never
  arrived."
- **`kotor_delivery_log.jsonl`** — next to `KotorClient.py`
  (your Client folder). The full history of
  what's been delivered and confirmed this playthrough, plus every
  character name the client has ever seen — relevant for both delivery
  bugs and anything involving the new-character safeguard below.
- **Your player `.yaml`** — which options were actually active matters a
  lot for reproducing anything, especially `starting_class`/`companion_class`/
  `loot_mode`/`area_randomizer`.
- **The client's log** around the time it happened — the newest
  `logs\KotorClient_<date>.txt` in your Client folder (it holds the same lines
  as the client's Heartbeat tab, including the game events it relayed).
- If it's specifically a delivery that's stuck (staged but never lands):
  also grab `extender\area_trampolines\_pending_queue.json` and
  `_armed_state.json` from wherever you installed this project — shows
  exactly what's still queued and which areas currently have it baked in.

## Known rough edges

- Companion recruit arms and some other deliveries are serialized
  (`HEAVY_ARMS` in `entitlement.py`) and apply on the player's *next* area
  transition, not instantly — a documented "one-transition delivery lag,"
  not a bug.
- If an armed delivery shows "STAGED" in the log but never actually lands
  in-game, check `extender.log` for an `ap_run_orchestrator: FAILED`
  block first — see [docs/history/PHASE13.md](docs/history/PHASE13.md)'s
  "Silent orchestrator-crash bug" section for the story behind why that
  check exists.
- See [docs/MODE_DEPENDENCIES.md](docs/MODE_DEPENDENCIES.md) for the
  current list of what's been live-tested vs. still open (the checklist
  items near the end), and any in-progress bugs.
- **Taris Undercity (`tar_m04aa`) crashes -- confirmed graphics driver
  issue, not the mod.** Two crashes here landed on the identical fault
  offset inside `igxelpicd32.dll` (Intel's graphics driver), one with the
  gear store UI open and one without -- same driver instruction both
  times, unrelated to any store/UI action, and structurally unrelated to
  this mod's memory writes (those touch creature stat fields only, never
  anything render-related). If you crash in the Undercity, try lowering
  or disabling dynamic lighting/particle effects, disabling anti-
  aliasing, or running in windowed mode before assuming it's a mod bug --
  this looks like a real compatibility gap between this area's rendering
  and Intel integrated graphics on this era of driver, not something a
  code fix here can address.
- **Crash during a dialogue, faulting module `mss32.dll` -- confirmed
  vanilla audio-engine issue, not the mod.** `mss32.dll` is the Miles
  Sound System audio middleware bundled with the original 2003 release; a
  crash there (exception `0xc0000095`, array bounds exceeded) happens
  inside the game's own audio engine while it's streaming VO, nothing in
  this project's NWScript/Python/extender stack touches it. A well-known
  category of crash for Miles Sound System-era games on modern multi-core
  CPUs. Community workarounds (untested/unverified against this specific
  install -- try in this order): restrict `swkotor.exe` to a single CPU
  core (Steam launch option `-affinity 0`, or Task Manager -> Details ->
  Set affinity), run in Windows XP SP2/3 compatibility mode, or update/
  roll back audio drivers and disable hardware audio acceleration/EAX if
  your sound card control panel exposes it.
- **Stuck at a "CutStart" object mid-dialogue -- already fixed in this
  build if you're on a current install.** This is a real, independently-
  documented KOTOR 1 engine bug: several vanilla cutscenes hang if the
  PC's base class was never one of the 3 original classes (Soldier/Scout/
  Scoundrel) -- historically only reachable via a save editor, but this
  project's `jedi_start=granted` option triggers the identical condition
  by writing a Jedi class directly as the PC's starting class. Confirmed
  live via a stalled character's own `AP|CLASSREPORT` diagnostic showing
  `baseclass=5` (Jedi Sentinel) with no base class ever recorded. Fixed by
  4 replacement `.dlg` files (community "KotOR 1 Fixed Cutscene Files for
  KSE," tk102) that ship automatically as part of the always-on Override
  package -- see `docs/MODE_DEPENDENCIES.md` for the full investigation.
  **If you hit this on an install predating the fix, or after manually
  editing Override, a full game restart (not just reloading the save) is
  required** -- the `.dlg` files are only read once at process start.
