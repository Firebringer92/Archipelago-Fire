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
it and edit your own, see `README.md` Step 4) and writes a zip into
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

## 3. Launch the game and connect the client

Launch KOTOR normally (with the merged extender DLL installed per
`README.md`) and get into a save. Then, in a **real terminal** (not a
piped/non-interactive shell — the client's stdin reader doesn't behave
the same over a non-TTY pipe), from `Archipelago\`:

```bash
python KotorClient.py --connect localhost:38281 --nogui
```

Enter your slot name when prompted (must match the `name:` field in your
player yaml). Once connected, the extender bridge should pick up the
already-running game automatically — `/ap_status` should show
`Extender: CONNECTED`. If it says not connected, confirm `swkotor.exe` is
actually running and the DLL loaded (check `kse.log` for `KSE DIAG` lines
arriving) before troubleshooting further.

On every successful connect, the client also automatically regenerates,
compiles, and deploys `ap_poll_shared.ncs` to your game's live Override,
matching this specific seed's real `loot_mode`/`area_randomizer` — this
replaces a script (`generate_poll_shared.py`) that used to be a manual,
easy-to-forget dev-only step. Look for a `[poll_shared] regenerated for
loot_mode=... area_randomizer=...` line in the client log right after
connecting; a `[poll_shared] regeneration FAILED` line instead means
something (usually a stale `nwnnsscomp.exe` path or `--game-dir`
mismatch) needs fixing — use `/ap_regen_poll` below to retry once fixed.

## 4. Useful client commands

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
  block first — see [docs/history/PHASE13.md](docs/history/PHASE13.md)'s
  "Silent orchestrator-crash bug" section for the story behind why that
  check exists.
- See [PHASE14.md](docs/history/PHASE14.md) for the current list of
  what's been live-tested vs. still open, and any in-progress bugs.
