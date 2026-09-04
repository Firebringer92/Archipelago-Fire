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

Reads every `.yaml` in `Players\` (start from `KotoR_TEMPLATE.yaml` — copy
it and edit your own, see `README.md` Step 5) and writes a zip into
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
matching this specific seed's real `loot_mode`/`area_randomizer` — this
replaces a script (`generate_poll_shared.py`) that used to be a manual,
easy-to-forget dev-only step. Look for a `[poll_shared] regenerated for
loot_mode=... area_randomizer=...` line in the client log right after
connecting; a `[poll_shared] regeneration FAILED` line instead means
something (usually a stale `nwnnsscomp.exe` path or `--game-dir`
mismatch) needs fixing — use `/ap_regen_poll` below to retry once fixed.

## 3b. Apply item suppression / door randomization (if enabled)

Only if you enabled these options in your player YAML, in a second
terminal (leave the client from step 3 running):

```bash
python scripts\patch_item_suppression.py --game-dir "C:\...\swkotor"
python scripts\patch_door_randomizer.py --game-dir "C:\...\swkotor"
```

Both read `extender\area_trampolines\_slot_data.json` — written by
`KotorClient.py` on the connect you just did in step 3 — instead of
hunting for a locally generated seed zip. This is what makes step 3's
"connect before launching" order load-bearing rather than just a
suggestion: skip straight to running these without connecting first and
you'll get a clear "connect first" message instead of a patch. It also
means this now works identically whether you generated/hosted the seed
yourself or are joining someone ELSE's multiworld — neither case needs
local access to their `AP_<seed>.zip` at all.

## 4. Launch the game

Launch KOTOR normally and load into a save. The client from step 3
(still running) picks up the extender automatically once the game is
up — `/ap_status` should switch to showing `Extender: CONNECTED`. If it
doesn't, confirm `swkotor.exe` is actually running and the DLL loaded
(check `kse.log` for `KSE DIAG` lines arriving) before troubleshooting
further.

## 5. Useful client commands

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
- `/received` — item receipt history (standard Archipelago client command).

**Use `/`, not `!`, for the commands above** — exclamation will not work in the client
for commands. I don't need to go into why.

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
- 
