# KotOR Archipelago — client commands, what to check, and bug reports

Setup (installing, generating a seed, hosting, connecting the client and launching the game) is in `README.md`. This page covers what
the client does on connect, its commands, what to look at in this build, and what to send when something goes wrong.

## 1. What the client does on connect

Connect before launching KOTOR: the client writes your seed's real options to a local file the moment it connects, and the patches and the
regenerated poll script need that file before the game starts reading its Override and modules.

On every connect the client first builds the files that are made from your own copy of the game (`[game assets] built N, already in place M`; a `FAILED` line says
what was missing; the Malak and droid model builds log as `[new companion]` and `[droid assets]`). It then regenerates and deploys `ap_poll_shared.ncs` for the seed
(look for `[poll_shared] regenerated for ...`; a `regeneration FAILED` line carries the compiler's own message: a missing `nwscript.nss` means the game-assets step did
not finish, and a `--game-dir` mismatch also causes it; retry with `/ap_regen_poll`). It then applies the per-seed game-file patches:
Loot Mode, item suppression, the story gates (Progression System), door randomization, Additional Enemies and the Bazaar tokens, then Galactic Shop, New Companion, the droid
assets, the area poll hooks and the boss datapads. It prints `[patching] ...` when it starts and a `Finished` line when you can start the game (a warning if
a patch failed); relaunch the game if it was already running, since the droid options replace tables it reads once at startup.

Look for `[loot_disturb] ...`, `[item_suppression] ...`, `[story_gates] ...`, `[door_randomizer] ...`, `[additional_enemies] ...` and `[bazaar_tokens] ...` in the client log:
`applied: ...` the first time, `already applied for this option set -- skipping re-run.` when you reconnect with the same options, and `APPLY FAILED: ...`
when something needs fixing (usually a `--game-dir` mismatch). These six do a real per-module sweep, so they only re-run when the seed's options change; use
`/ap_patch_all` to force a re-apply after fixing a failure. If the install was last patched for a different seed or option set, the client prints a reminder:
quit and restart the client when you switch seeds, then run `/ap_restore_all` and reconnect.

If the client cannot find the project's `scripts\` folder (an unusual folder layout), start it with `--repo-root "C:\...\your-playerbundle-folder"`.

## 2. Useful client commands

- `/ap_status` — extender connection state and the delivery window: "Deliveries waiting", the job in flight, failed jobs with the reason, and the last results.
  The Status tab shows the same block.
- `/ap_apply <arm_name>` — admin/testing safety valve: directly queue an
  arm with the extender, bypassing the AP server entirely (exactly the
  same call the real item-received path makes). Use `/ap_apply` with no
  argument to see the full list of known arm names. Special forms:
  `give_item:<resref>[:<count>]` for gear, `companion_class:<name>:<class>`
  for the companion class-randomization feature (see `Options.py`'s
  `CompanionClass`), `force_power:<row>` and `trap:<type>[:<params>]` (for
  example `trap:remove_companion`). It goes through the same dispatcher as a
  real item, so it lands when the game is calm, not instantly. To unlock a
  companion's feat training use `give_item:ap_ft_<key>:1` (`bastila`,
  `canderous`, `carth`, `jolee`, `juhani`, `mission`, `zaalbar`).
- `/ap_check <location name>` — manually report a location check by name
  (bypasses the normal auto-detection).
- `/ap_locations` — list every location and whether it's checked.
- `/ap_clear_queue` — admin, rarely needed now: deliveries go through the dispatcher and are not in the older staged queue this command empties. It only matters when an entry
  an earlier version left staged keeps firing on every load. What it drops that cannot be re-derived is journaled (`extender/area_trampolines/_dropped_queue.json`);
  `/ap_restore_queue` stages it again.
- `/ap_restore_queue` — admin: re-stages what the last `/ap_clear_queue` dropped. Corrections the reconciler recomputes and queued DeathLink deaths are never restored.
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
  item suppression, story gates, door randomization, Additional Enemies, Bazaar
  tokens, boss datapads, the droid assets, Jedi suppression), ignoring the already-applied marker. Use it after an
  `APPLY FAILED` line, or after manually restoring or editing the game install and
  wanting a clean re-apply.
- `/ap_apply_galactic_shop`, `/ap_apply_new_companion`, `/ap_apply_droid_assets`,
  `/ap_apply_area_poll_hooks`, `/ap_apply_shop_item_costs`,
  `/ap_apply_tracker_quest` — the same kind of manual fallback for the
  patches that run on every connect (Galactic Shop crate, the New
  Companion assets, the droid assets, the poll hook for areas with no OnEnter script, shop
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
- `/ap_leak_purge [auto|on|log|off]` — the companion leak purge. A companion on your roster without an entitlement marker in your save
  is removed after two area changes, never during a scripted scene. `auto` (the default) only logs who it would remove until the Leviathan
  has been escaped, then removes them; `on` always removes, `log` never does, `off` disables it.
- `/ap_shop` — Galactic Shop (Void Trade) status for this slot.
- `/received` — item receipt history (standard Archipelago client command).

A few more commands (`/ap_raw` and the `/ap_dispatch*` family) are developer tools. They are refused unless the environment variable `KOTOR_AP_DEV=1` is set when the
client starts, and they are not needed for playing or for reporting a bug.

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
Confirmed: `!ap_apply`/`!ap_status` reliably produced
exactly this silent-wrong-target failure, while `/ap_apply`/`/ap_status`
worked correctly every time. If you're running the client from a
bash-family shell, `!` also triggers bash's own history expansion
(`event not found` errors) as a second, unrelated reason to avoid it --
use `cmd.exe`/PowerShell, or `set +H` in bash to disable it if you must.

## 3. If a companion shows up that shouldn't

The mod keeps a marker in your save for every companion it has granted, and removes a companion who is on your roster without one (after two area
changes, never during a scripted scene). Until the Leviathan has been escaped it only logs who it would remove; after that it removes them (`/ap_leak_purge` changes this).
If you ever see a companion in your party or roster that you did not receive, please report it with:

- the client log lines containing `is on the roster with` (they name the companion and say whether it has no marker or a trapped-off marker);
- the `AP|CREWREPORT|...` and `AP|ROSTERREPORT|...` lines from `kse.log` around that time;
- your `companion_mode`, and where and when the companion appeared (which area or scene, before or after the Leviathan).

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

**This also shows on the Status tab**, not just as a log
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
- **The `[game assets]`, `[new companion]` and `[droid assets]` lines** in the client log, and whether `%LOCALAPPDATA%\KotorAP\models` exists: it holds the finished Malak,
  HK-47 and droid models (delete it to force a rebuild).
- **`kotor_delivery_log.jsonl`** — next to `KotorClient.py`
  (your Client folder). The full history of
  what's been delivered and confirmed this playthrough, plus every
  character name the client has ever seen — relevant for both delivery
  bugs and anything involving the new-character safeguard below.
- **Your player `.yaml`** — which options were actually active matters a
  lot for reproducing anything, especially `starting_class`/`companion_class`/
  `loot_mode`/`area_randomizer`.
- **`%LOCALAPPDATA%\KotorAP\launcher.log`** — only if the "KOTOR Client" button in the Archipelago Launcher does nothing; it records each step of the start.
- **The client's log** around the time it happened — the newest
  `logs\KotorClient_<date>.txt` in your Client folder (it holds the same lines
  as the client's Heartbeat tab, including the game events it relayed).
- If it's specifically a delivery that's stuck or failed: a screenshot of the Status tab's delivery block (or the `/ap_status` output) and the `[dispatch]`
  lines in the client log around that time. They show whether the job was waiting for a calm moment, was sent again, or failed, and why.

## Troubleshooting

- Deliveries wait for a calm moment: not during a conversation, a cutscene or a fight (the client log says `job N is waiting for a calm moment: <why>`). A long fight
  or scene delays them until it ends; that is not a bug. Companion recruits and class changes are sent one at a time on purpose.
- If the log shows `[dispatch] no answer for job N yet; sending it again`, the game is not answering: KOTOR pauses all script activity while its window is not focused, so click
  into it. If it is focused and the client keeps resending, check `extender.log` for the extender losing its connection.
- A `[dispatch] ... the game does not know the action` or `could not apply job` line means that one job failed and was not retried; it is in the delivery log with the reason. Report it.
- Close an old KotorClient before starting a new one: a leftover client process can hold the game's connection, and the new client then connects to nothing
  without showing an error.
- A `COMPILE FAILED` line in the client log comes from `tools\nwnsc\nwnsc.exe`, the script compiler, and carries its own message. If `nwnsc.exe` or `tools\mdlops\mdlops.exe`
  will not start, check whether your antivirus quarantined it; restore or allow it, then connect again.
- Crashes in the Taris Undercity or during a dialogue are known vanilla issues (graphics driver, audio engine); README's "Other Notes" has the workarounds.
- **Stuck at a "CutStart" object mid-dialogue.** A vanilla KOTOR 1 engine bug: several cutscenes hang if the PC's base class was never Soldier, Scout or
  Scoundrel, which `starting_class: jedi_start` / `jedi_granted` would otherwise cause. Replacement conversation files that prevent it are built from your own game files by the installer (and on every connect) into Override.
  **If it still happens, or after editing Override by hand, restart the game completely (not just reload the save):** those files are read once at process start.
