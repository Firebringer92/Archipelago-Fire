# KOTOR Archipelago Randomizer — Installation (Alpha)

> **Status: alpha.** This rewrites live game files (see "Before you start,
> back up" below) and has caused real crashes and softlocks during
> development testing. Expect bugs. While no game crashes has occured in this version, that doesn't mean a unique interaction with a scripted event can't cause interference and cause a crash. A live end-end playthrough with each scenario is unfeasable with current design. I ask testers to focus on efforts on random_areas, no_companion/ap_companion gating as while these options have been tested to work, I firmly believe they may have bugs and/or soft locks present in them. If you find an issue please report to me  with a brief description and if crash please also include kise logs, and recent delivery list at time of crash. Refer to `TESTING.md` for more information.

**ALPHA TESTERS: PLEASE DO NOT USE THIS MOD IN A MULTIWORLD!!!!** 

This mod needs two pieces working together: **this project's own extender**
(a single compiled DLL -plus generated NWScript that talks to Archipelago) and **Python** (to
generate your seed and run a couple of small setup scripts). Neither is
optional — skipping either means the mod won't work.

## What you'll need

- **Knights of the Old Republic (Steam version specifically).** The merged
  extender fingerprints the game build on launch (inherited from K1SE's own dependencies) and is only
  confirmed safe against that one exact build — GOG, disc, patched, or
  localized copies are not supported yet.
- **Windows.** Everything here (the proxy DLL, the install script) is
  Windows-only.
- **Python 3.12 or 3.13** — used to generate your seed, run the setup
  scripts that patch a couple of game files (item suppression, door
  randomization), and run `KotorClient.py` itself. Get it from
  [python.org](https://www.python.org/). Note latest version will not work with Kivy (GUI) so be mindful of this
- **[KotOR Scripting Tool](https://github.com/KobaltBlu/KotOR-Scripting-Tool/releases/tag/v0.1.5)**
  (specifically its `nwnnsscomp.exe`) — a separate, already-compiled
  NWScript compiler, not something you build. `nwnnsscomp.exe` must end up
  **directly inside** `C:\Program Files (x86)\KotOR Scripting Tool\` — the
  exact path this project's scripts hardcode, not configurable — with
  nothing else in between. When you download and extract there could be a subfolder it is sitting in you will have to move it out of. 
- **Archipelago 0.6.7** or newer — as a full source checkout, not just the
  official installer app.** If you have archipelago already installed as an app you will still need source
  ([see here for latest releases](https://github.com/ArchipelagoMW/Archipelago/releases)).
  Download the "Source code" zip for your version from that same
  releases page, extract it, and run `pip install -r requirements.txt`
  once inside it — see Step 1 below for exactly where the client files go.
  `kotor.apworld` is also version-gated and will be rejected with a
  generic "no functional world found" error on an Archipelago core older
  than 0.6.7 — if you hit that error, check your version first.


## Step 1 — Set up your KotoRClient folder (the bridge between AP and your actual game)

One folder holds everything you'll run commands from for the rest of this
guide — this doc calls it your **Client folder**.

1. Download Archipelago's own source code (not the Windows installer app
   — see "What you'll need" above for why it must be the source) from
   [Archipelago's GitHub releases](https://github.com/ArchipelagoMW/Archipelago/releases),
   matching version 0.6.7 or newer. Grab the "Source code (zip)" asset,
   and extract it anywhere — that extracted folder **is** your Client
   folder from here on.
2. Download both zips from **[this project's Releases page](https://github.com/Firebringer92/Archipelago-Fire/releases)**
   (always the same release, never mix versions):
   - `KOTOR-AP-World-vX.Y.Z.zip` → `kotor.apworld` — placed later, in Step 5.
   - `KOTOR-AP-PlayerBundle-vX.Y.Z.zip` → everything else: the compiled
     extender DLL, setup/delivery scripts, precompiled game-script content,
     and `KotorClient.py` + its 3 helper modules.
3. Extract the PlayerBundle zip, then merge it into your Client folder:
   - Copy its `extender\`, `scripts\`, and `dist\` folders straight into
     the Client folder root, as siblings of `CommonClient.py`.
   - The PlayerBundle also contains a subfolder literally named
     **`KotorClient\`** — don't confuse this with your **Client folder**
     from step 1 above (unrelated names that happen to look similar).
     Open it and move the 4 `.py` files inside it (`KotorClient.py`,
     `kotor_extender_bridge.py`, `kotor_location_tracker.py`,
     `kotor_reconciliation.py`) **directly into the Client folder root**
     — do not leave them inside the `KotorClient\` subfolder itself, and
     delete that now-empty subfolder once you've moved them out so it's
     not sitting around looking like somewhere else these files might
     belong. This one's easy to get wrong: `KotorClient.py` specifically
     needs to sit right next to `CommonClient.py` at the same folder
     level, since it does `from CommonClient import (...)` and Python
     only looks in the launched script's own folder for that — one level
     of nesting difference and the import fails immediately on connect.

You should end up with a single folder that looks like:

```
<Client folder>\
  CommonClient.py, Utils.py, ModuleUpdate.py, ... (Archipelago's own files)
  KotorClient.py
  kotor_extender_bridge.py
  kotor_location_tracker.py
  kotor_reconciliation.py
  extender\install.ps1
  extender\build_new\binkw32.dll
  extender\area_trampolines\...
  extender\scripts_src\...
  scripts\...
  dist\Override\...
```

If you're re-installing over an older setup rather than starting fresh,
replace the whole `extender\` and `scripts\` folders rather than copying
over just the files you already recognize — `extender\scripts_src\` in
particular is easy to leave out that way, and both `patch_item_suppression.py`
and the automatic `ap_poll_shared.ncs`/Dantooine suppressor regeneration
(Step 6) need it.

## Step 2 — Install the extender DLL

`install.ps1` captures whatever `binkw32.dll` is already in your game
folder as `binkw32_real.dll` (the true original Bink codec, forwarded
through to for every real Bink function), then drops the freshly-built
merged DLL in as the new `binkw32.dll`. Run it from inside your **Client
folder**:

```powershell
powershell -ExecutionPolicy Bypass -File "extender\install.ps1" -GameDir "C:\Program Files (x86)\Steam\steamapps\common\swkotor" -Install
```

Adjust `-GameDir` if your Steam library isn't in the default location.
This also writes `ap_repo_root.txt` into your game folder — a one-line
pointer back to your Client folder that the DLL reads at runtime to find
`scripts\arm_orchestrator.py`, so don't move or delete your Client folder
after installing without re-running this step.

To remove it later (restores the original `binkw32.dll`):

```powershell
powershell -ExecutionPolicy Bypass -File "extender\install.ps1" -GameDir "C:\Program Files (x86)\Steam\steamapps\common\swkotor" -Uninstall
```

## Step 3 — Deploy the mod's base scripts

This deploys the always-on part of the mod (area reporting, companion
suppression, shop markers) into your `Override` folder. It's pure Python
standard library — no compiler, no `pykotor`, nothing else to install for
this step. From your Client folder:

```bash
python scripts\setup_game.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\swkotor"
```

This copies everything from `dist\Override\` — a folder of already-compiled
scripts, so nothing needs to be rebuilt on your machine.

## Step 4 — Install dependencies and the NWScript compiler

From your Client folder (make sure Python 3.12 or 3.13 is installed
first — see "What you'll need" above):

```bash
pip install -r requirements.txt
pip install "setuptools<81" pykotor
```

Then install the [KotOR Scripting Tool](https://github.com/KobaltBlu/KotOR-Scripting-Tool/releases/tag/v0.1.5)
so that `nwnnsscomp.exe` ends up **directly inside**
`C:\Program Files (x86)\KotOR Scripting Tool\` — see "What you'll need"
above for the exact-path requirement and the zip-extraction to ensure it is sitting in correct spot
and not a super folder.

Your Client folder is now fully set up.

## Step 5 — Generate a seed and host it

This step uses the separate, official **Archipelago Launcher app** (the
one from Archipelago's own Windows installer) for its Generate/Host GUI —
a different installation from your Client folder, so a couple of things
need a copy in both places:

1. Place `kotor.apworld` (from Step 1's World zip) in **two** locations:
   - `<Client folder>\custom_worlds\kotor.apworld` — needed because
     `KotorClient.py` imports directly from it in Step 6.
   - `custom_worlds\kotor.apworld` inside the official Launcher app's own
     install folder (create `custom_worlds\` there if it doesn't exist).
     Not sure where that install folder is? Find the Launcher's shortcut
     (Start Menu → right-click "Archipelago Launcher" → Open file
     location), then right-click that shortcut → Properties → **Target**
     gives you the real folder.
2. Download **[`KotoR_TEMPLATE.yaml`](https://github.com/Firebringer92/Archipelago-Fire/blob/main/KotoR/Docs/KotoR_TEMPLATE.yaml)**
   (in this repo's `Docs\` folder, not inside either zip) — it documents
   every available option inline, with its default and what it does.
   Save it into the Launcher app's own `Players\` folder (same install
   folder as step 1 above), renamed to whatever you like, e.g. `my_game.yaml`.
3. Edit `my_game.yaml`: set `name:` to whatever slot name you want to
   connect with, then adjust any options under the `KotOR:` block — leave
   `game:` itself alone, that's the fixed internal name Archipelago uses
   to find this world, not a display name.
4. Open the Archipelago Launcher, click **Generate**, and select your
   yaml. This writes a seed zip (`AP_<seed>.zip`) into that Launcher
   install's own `output\` folder.
5. Click **Host** in the Launcher and select that seed zip. This starts
   the server and shows you the address/port to connect with.

## Step 6 — Connect, then patch, then play

**Important order — connect with `KotorClient.py` before you launch
KOTOR**, not after. This is different from how you might expect it to
work, so here's why: `patch_item_suppression.py`/`patch_door_randomizer.py`
(the optional door-randomization/item-suppression patches below) need
your seed's real options, which only exist locally once `KotorClient.py`
receives them from the AP server and writes them to a small file — it
does this the moment it connects, whether or not KOTOR is even running
yet. Connecting first means those files are already correctly in place
*before* the game process starts, instead of needing a restart partway
through.

1. Set `SKIP_REQUIREMENTS_UPDATE=1` in your terminal first (PowerShell:
   `$env:SKIP_REQUIREMENTS_UPDATE=1`) — `KotorClient.py` triggers the
   same interactive per-world dependency check `Generate.py`/`MultiServer.py`
   do, and this skips it.
2. From your Client folder, **with KOTOR not running yet**:
   ```bash
   python KotorClient.py --connect localhost:<port> --nogui
   ```
   (drop `--nogui` for GUI mode, if your Python version's Kivy supports
   it — see "What you'll need" above). Enter your slot name when
   prompted. `/ap_status` will say the extender isn't connected yet —
   that's expected, since KOTOR isn't running. Leave this window open.
3. **Only if you enabled these options in your player YAML**, open a
   second terminal and apply them (both accept `--game-dir` the same way
   `setup_game.py` does):
   ```bash
   python scripts\patch_item_suppression.py --game-dir "C:\...\swkotor"
   python scripts\patch_door_randomizer.py --game-dir "C:\...\swkotor"
   ```
   Both read the seed data `KotorClient.py` just wrote in step 2 — this
   works whether you're hosting or joining someone else's multiworld,
   with no separate flag needed either way. Neither needs the NWScript
   compiler — `patch_door_randomizer.py` only edits existing data fields,
   and `patch_item_suppression.py` uses a precompiled script already
   shipped in `extender\scripts_src\` for the same reason `setup_game.py`
   doesn't need a compiler in Step 3.
4. Now launch KOTOR and load into a save. The client from step 2 (still
   running) picks up the extender automatically once the game is up —
   `/ap_status` should switch to showing `Extender: CONNECTED`. If it
   doesn't, confirm `swkotor.exe` is actually running and the DLL loaded
   (check `kse.log` for `KSE DIAG` lines arriving) before troubleshooting
   further.

See `TESTING.md` for the full walkthrough, client commands, and what to
send if you hit a bug.


## Before you start: back up

This mod repacks real game files in place — `modules\*.rim` and
`Override\` are both modified directly, not just added to.

- Back up your **saves** (`%LOCALAPPDATA%\KotOR\saves` or similar) before
  playing a randomized seed.
- Back up your **`modules\` folder and `Override\` folder** (or your whole
  game install) before running any of the setup scripts, in case something
  goes wrong beyond what the built-in restore covers.
- `python scripts\patch_item_suppression.py --restore` reverts every
  module RIM touched by either item suppression or door randomization back
  to its backed-up original (they share one backup store).
- If all else fails, Steam's **Verify integrity of game files** will
  restore any modified `modules\`/`Override\` content from scratch (this
  won't undo save-file changes, which is why saves need their own backup).

## How do checks/locations work in this mod?
Due to nature of game, this mod has a specialized delivery/receipt pipeline to read and write to the game.
When you first launch KotorClient.py and connect to server you will see an "extender" along with status. 
This extender is what is used to get information from the game to report on current status and the client will 
then use this information to determine "Did you achieve requirements for a known check". If you did, it will then send back to AP Server to mark it as completed and the attached item is then sent by client to be delivered to your game.
You in game might not see the result check immediately. The delivery pipeline is designed to provide you items when you load into a new module (loading zone). Additionally because of how taxing some of the items are to the game client, there is a queuing system in place so you might not get all the items your supposed to get on your first transition. This is designed purposefully to prevent a game crash. A known issue where if more than 30 or so items being sent at once overwhelms the game. So if you see you should have gotten an item, it wsn't delivered ensure you check if its queued in the KotorClient status page or if it is marked as Completed/Received and you didn't get it that would be a bug. You will notice during playing that your KotorClient.py will get lots of messages, these are in game events that is being reported to client from game on current status and used to detect a check, this happens every 5 seconds. 
For more technical details on how it all works refer to DESIGN.md

## Known alpha limitations

- Door randomization and item suppression both directly rewrite game
  files — see the backup section above before enabling either.
- A handful of doors are structurally impossible to randomize and are left on their
  vanilla exit automatically. This is expected. Not a bug
= Door-randomization also doesn't begin until after tutorial (Endar Spire) until you leave Apartments on Taris.
  So you will go from Endar Spire > Hideout > Apartments and then next door is randomed. 
  additionally while game is set to try to couple doors, some may not be directly linked back ot previous. This is done to ensure you always are allowed to go to all areas and are never soft locked from reaching an area. If you have suggestions on a mapping system that is less random and more sane let me know of how  we can better map this. 
  Ebon hawk travel to all planets is enabled automatically in this mode to ensure you can still use it as a hub
  and travel to and from planets. Ebon-Hawk entrance/exit always leads to it.
  End game areas (leviathan/unknown world/star forge) are taken out of randomization on doors
- Death link will not kill the player if he has party members due to having a companion still up. Known issue.
- Companion class randomization (`companion_class` option): switching to a
  base class writes the companion's class/level/Force directly and lets
  KOTOR's own normal in-game leveling catch them up to the party over
  subsequent play. Granting a companion a Jedi class they didn't already
  have uses the real `AddMultiClass()` native instead (fixed 2026-09-03 --
  the direct-write approach left newly-granted Force Powers sheet-visible
  but never usable from the combat hotbar/quickbar, since it skipped the
  engine's own class-change housekeeping). Either way, Jedi-only feats are
  granted/removed and Jedi-exclusive gear (lightsabers, Jedi robes) is
  force-unequipped when switching away from Jedi.
- **Crash Confirmed In Game: opening a companion's Force Powers
  screen right after they've been granted a Jedi class, before they've
  reached level 2 in it.** A freshly-granted level-1 Jedi companion has
  zero known Force Powers yet (our grant mechanism doesn't run the normal
  "learn initial powers" step a real level-up would), and the Force
  Powers screen isn't built to render a completely empty list for a
  character it considers Jedi. **Workaround: don't open that screen for a
  companion who was just converted until they've leveled up at least
  once** (companion leveling happens only through real combat XP —
  confirmed no scriptable way to grant a companion levels or XP directly
  in this engine build). No code fix yet; this is still very real. Note will only happen when
  `companion_class`'s `jedi_companion`/`randomize_all` modes are selected. DO NOT OPEN FORCE POWERS MENU ON COMPANION
- Only tested against the Steam release of KOTOR 1.

## Credits

This project leans heavily on work by other people in the KOTOR modding
and Archipelago communities. It would not exist without:

- **[K1SE (KOTOR Script Extender)](https://www.nexusmods.com/kotor/mods/1852)**
  by Brandon Guffey ([source, MIT-licensed](https://github.com/Brotaku-Vengeant/Kotor-Script-Extender-Public-))
  — this mod's whole delivery/reporting pipeline is built on top of K1SE's
  dispatcher-hook mechanism, and (as of this project's alpha) K1SE's own
  source is merged directly into this project's compiled extender rather
  than installed as a separate third-party mod, per its MIT license. Its
  persistent heartbeat, diagnostic channel, and skill/feat-grant natives
  are what let this project actually see and change what's happening
  inside a running game.
- **[Holocron Toolset](https://github.com/Bagelboi/HolocronToolset)** and
  the underlying PyKotor library — used constantly during research and
  development to inspect and understand KOTOR's own file formats
  (GFF/RIM/2DA/journal data) well enough to build on top of them.
- **[Kotor Randomizer](https://github.com/LaneDibello/Kotor-Randomizer)**
  by LaneDibello — an existing KOTOR randomizer whose approach to entrance/
  location randomization was referenced while designing this project's own
  door-randomization and location-detection systems.
- **[Archipelago](https://archipelago.gg/)** itself, obviously — this
  project is built as an Archipelago world/client 
**[Bioware]** For making an amazing game, I loved it as a kid growing up and its been interesting learning about the
  inner working of the engine that made this game  (the good and bad)

## AI usage

This project is largely vibecoded.
What do you mean by vibe coded?
A bulk portion of the code in this project is drafted by AI. The AI responsibilities
for this project included building the extender, apworld and python client. AI was also used both with asisting in research and diagnostics during testing. 
So what were you responsibities?
I built out testing ncs scripts to validate functionality.
I performed a review over all code line by line, I also leave soome comments in code to make them more clear.
Validated my understanding of the code by questioning any functions/tracing code paths when documentation was unclear or not specific. As well as clarified my understanding for areas of the code I wasn't sure what it was used for and ensured was inline with design of the features and or project goal. 
I performed live in game testing of both my own scripts and AI drafted code and fixes.
I was responsible for all game design decisions. 

If you're evaluating this project's code quality, treat it accordingly:
this is a human-directed, AI-assisted alpha project, not a fully
human-hand-written one, and it's tested and reviewed as such.
