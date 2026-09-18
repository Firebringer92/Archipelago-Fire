# KotOR Archipelago — running and testing a seed

This describes the REAL, current pipeline: a real generated seed, a real
local Archipelago server, the actual KOTOR game running with this
project's merged extender DLL loaded, and `KotorClient.py` bridging
between them over a local socket. If you haven't installed the extender
DLL yet, do that first — see `README.md`'s Steps 1-2.


## 1. Generate a seed and Hosting

If you already have Archipelago already installed on your computer just unzip apworld. Click on it and it will be added to the custom folder or manually move it to the programdata/custom world folder. 

Fill out a yaml template (refer to `KotoR_TEMPLATE.yaml`) and then save your copy with your options filled out in the players folder of archipelago.

Then on launcher hit generate, this will create a zip file in your programdata/archipelago/output folder. Use this to either localhost using the launcher or can upload zip here  https://archipelago.gg/uploads and archipelago will host a server for you.


## 2. Connect the client, THEN launch the game

**Connect before launching KOTOR, not after.** `KotorClient.py` writes
your seed's real options to a local file the moment it connects to the
AP server — whether or not KOTOR is even running yet — and both
`patch_item_suppression.py`/`patch_door_randomizer.py`
and the automatic `ap_poll_shared.ncs`/Dantooine-suppressor regeneration
need that file to exist before the game starts reading its own Override/
modules. Connecting first means everything's correctly in place from the
game's very first load, instead of needing a mid-session restart.


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
matching this specific seed's real game mode selections `loot_mode`/`area_randomizer`, additional_enemies — this
replaces a script (`generate_poll_shared.py`). Look for a `[poll_shared] regenerated for
loot_mode=... area_randomizer=...` line in the client log right after
connecting; a `[poll_shared] regeneration FAILED` line instead means
something (usually a stale `nwnnsscomp.exe` path or `--game-dir`
mismatch) needs fixing — use `/ap_regen_poll` below to retry once fixed.

`[<name>] already applied for seed '...' -- skipping re-run.` instead of
redoing the sweep every launch. A `[<name>] APPLY FAILED for seed '...':
...` line means something needs fixing (check the message — usually a
`--game-dir` mismatch); use the matching `/ap_apply_*` admin command
below to retry once fixed, which always re-applies regardless of what's
already recorded.



## 3. Launch the game

Launch KOTOR normally and load into a save. The client from step 3
(still running) picks up the extender automatically once the game is
up — `/ap_status` should switch to showing `Extender: CONNECTED`. If it
doesn't, confirm `swkotor.exe` is actually running and the DLL loaded
(check `kse.log` for `KSE DIAG` lines arriving) before troubleshooting
further.

## 4. Useful client commands

-'/ap_patch_all' - This will patch your game based on your seed slot. Useful need to repatch after your first reconnect
-'/ap_restore_all' - Restores back up files to base game. Good for if want to switch to another slot playing kotor.
- `/ap_status` — extender connection state, pending/recent deliveries.
- `/ap_apply <arm_name>` — admin/testing safety valve: directly queue an
  arm with the extender, bypassing the AP server entirely (exactly the
  same call the real item-received path makes). Use `/ap_apply` with no
  argument to see the full list of known arm names. Special forms:
  `give_item:<resref>[:<count>]` for gear, `companion_class:<name>:<class>`
  for the companion class-randomization feature (see `Options.py`'s
  `CompanionClass`).
- `/ap_check <location name>` — manually report a location check by name
  (bypasses the normal auto-detection).
- `/ap_locations` — list every location and whether it's checked.
- `/ap_regen_poll` — manual fallback: re-run the automatic `ap_poll_shared.ncs`
  regeneration described above, using this session's already-connected
  `loot_mode`/`area_randomizer`. Use this if the automatic regeneration
  failed on connect, or after manually touching the game install's Override.
- `/ap_confirm_character` — see "New-character safeguard" below. Only
  needed if you see a `[SAFEGUARD]` warning after connecting.
- `/ap_regen_makejedi` — manual fallback for the Dantooine make-jedi
  suppression wrapper (prevents the vanilla trial from granting a free
  Jedi class outside `starting_class`'s gating), same idea as `/ap_regen_poll`.
- `/ap_apply_item_suppression`, `/ap_apply_door_randomizer`,
  `/ap_apply_additional_enemies` — manual fallbacks for the 3 automatic
  per-seed patches above. Unlike the automatic on-connect run, these
  always re-apply (full RIM sweep) regardless of the once-per-seed
  marker — use after an `APPLY FAILED` log line, or after manually
  restoring/editing the game install and wanting a clean re-apply.
- `/received` — item receipt history (standard Archipelago client command).

**Use `/`, not `!`, for the commands above** 


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
- **`kotor_delivery_log.jsonl`** — in whatever folder you ran
  `KotorClient.py` from (normally `Archipelago\`). The full history of
  what's been delivered and confirmed this playthrough, plus every
  character name the client has ever seen — relevant for both delivery
  bugs and anything involving the new-character safeguard below.
- **Your player `.yaml`** — which options were actually active matters a
  lot for reproducing anything, especially `starting_class`/`companion_class`/
  `loot_mode`/`area_randomizer`.
- **The client's terminal output** around the time it happened — this
  isn't saved to a file anywhere (neither `KotorClient.py` nor the
  Archipelago `CommonClient` base it's built on writes its own log file),
  so either keep the window's scrollback, screenshot it, or — better, if
  you can reproduce on demand — redirect it to a file next time:
  `python KotorClient.py --connect ... --nogui > client_log.txt 2>&1`.
- If it's specifically a delivery that's stuck (staged but never lands):
  also grab `extender\area_trampolines\_pending_queue.json` and
  `_armed_state.json` from wherever you installed this project — shows
  exactly what's still queued and which areas currently have it baked in.

## Known rough edges

- Companion recruit arms and some other deliveries are serialized
  (`HEAVY_ARMS` in `KotorClient.py`) and apply on the player's *next* area
  transition, not instantly — a documented "one-transition delivery lag,"
  not a bug.
- If an armed delivery shows "STAGED" in the log but never actually lands
  in-game, check `extender.log` for an `ap_run_orchestrator: FAILED`
  block first
- Ive had in game crashes that seem completely as normal kotor graphics/sound crashes rather than anything
  my mod does, if you experience crashes and nothing was staged to be delivered to you,
  it is unlikely related to the mod - unless it was a specific cutscene/script requiring a companion there that I missed
  I still advise reporting any and all crashes during playthrough so i can verify if mod is causing the issue or not.
