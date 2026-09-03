# KOTOR Archipelago Randomizer — Installation (Alpha)

> **Status: alpha.** This rewrites live game files (see "Before you start,
> back up" below) and has caused real crashes and softlocks during
> development testing. Expect bugs. While no game crashes has occured in this version, that doesn't mean a unique interaction with a scripted event can't cause interference and cause a crash. A live end-end playthrough with each scenario is unfeasable with current design. I ask testers to focus on efforts on random_areas, no_companion/ap_companion gating as while these options have been tested to work, I firmly believe they may have bugs and/or soft locks present in them. If you find an issue please report to me  with a brief description and if crash please also include kise logs, and recent delivery list at time of crash. Refer to `TESTING.md` for more information.

This mod needs two pieces working together: **this project's own extender**
(a single compiled DLL — it merges K1SE's dispatcher-hook source directly in,
so there's no separate third-party script extender to install any more —
plus generated NWScript that talks to Archipelago) and **Python** (to
generate your seed and run a couple of small setup scripts). Neither is
optional — skipping either means the mod won't work.

## What you'll need

- **Knights of the Old Republic (Steam version specifically).** The merged
  extender fingerprints the game build on launch (inherited from K1SE's own
  fingerprinting discipline, preserved as-is in the merge) and is only
  confirmed safe against that one exact build — GOG, disc, patched, or
  localized copies are not supported yet.
- **Windows.** Everything here (the proxy DLL, the install script) is
  Windows-only.
- **Python 3.12+** — used to generate your seed and run the setup scripts
  that patch a couple of game files (item suppression, door randomization).
  Get it from [python.org](https://www.python.org/) or via
  `winget install Python.Python.3.12`.
- **[KotOR Scripting Tool](https://deadlystream.com/files/file/1163-kotor-tool/)**
  (specifically its `nwnnsscomp.exe`, expected at
  `C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe`) — a separate,
  already-compiled NWScript compiler, not something you build. Needed on
  the machine actually running the game/client: `KotorClient.py`
  automatically recompiles and redeploys two scripts (`ap_poll_shared.ncs`
  and, if `jedi_start` isn't `off`, the Dantooine trial-completion
  suppressor) to match your seed's real options every time it connects
  (see `TESTING.md`). Not needed on a machine that's only generating seeds
  or hosting a server — see the hosting-only section below.


## Just hosting a multiworld / generating a seed? You can skip almost all of this

If you're only generating seeds and/or running the Archipelago server for
other people to connect to — you're not installing the mod or launching
KOTOR on this machine yourself — **almost none of the game-side setup
applies to you.** Skip the DLL entirely: no compiler, no VS2022 Build
Tools, no `nwnnsscomp.exe`/KotOR Scripting Tool, not even a KOTOR install.
The one thing you still need from Step 1 is `kotor.apworld` — `Generate.py`
can't produce a KOTOR seed without it. Everything else is plain Python.

What you actually need:

- **Python 3.12+** (see above) and this repo checked out.
- `kotor.apworld` from Step 1 above, placed at
  `Archipelago\custom_worlds\kotor.apworld`.
- Install dependencies and generate, from `Archipelago\`:
  ```bash
  pip install -r requirements.txt
  pip install "setuptools<81" pykotor
  python Generate.py --player_files_path Players --outputpath output
  ```
  Reads every `.yaml` under `Players\` — see Step 4 below for how to set
  up player files (each player sends you their own filled-out `.yaml`
  copied from `Archipelago\Players\kotor_test.yaml`; you don't need to
  understand what any individual option does to generate for them). This
  produces one `AP_<seed>.zip` in `Archipelago\output\` covering every
  player file present.
- Host it:
  ```bash
  python MultiServer.py output/AP_<seed>.zip
  ```
  Prints `server listening on 0.0.0.0:<port>` and sits there — give
  players your address and port to connect with. If you want players
  outside your own network to connect, that's a router/firewall
  port-forwarding question, not something this project's setup touches.
- State (checked locations, received items) lives in the server's memory
  only for the session — there's no separate save step; leave it running
  to persist across a play session, restart it for a clean slate.

**Important: generation happens exactly once, here, covering every
player's yaml together — a player joining your server does NOT run
`Generate.py` themselves.** There's only ever one seed, one zip, one
`Generate.py` run for the whole multiworld; it doesn't matter who runs it
as long as everyone's yaml went into that single run. If two people each
ran `Generate.py` separately (even with the exact same yaml files), the
random item/location placement would come out different each time and
the two resulting seeds would NOT match each other — that's the mistake
to avoid.

What a player joining your server DOES still need, on their own machine:
the full game-side Steps 1-3 (extender installed, base scripts deployed)
— that's what lets their copy of KOTOR actually talk to your server —
followed by `python KotorClient.py --connect <your-address>:<port>` (see
`TESTING.md`) instead of running their own server. Skip Step 4's
`Generate.py`/`MultiServer.py` commands entirely on a joining player's
machine; those are only for whoever is doing the one, shared generation
and hosting.

## Step 1 — Get the release files

Every release ships three zips together, version-pinned as a set — always
get all three from the same release, never mix versions:

- **`KOTOR-AP-Extender-vX.Y.Z.zip`** → `extender\build_new\binkw32.dll`,
  the compiled extender. Only needed if you're actually launching KOTOR on
  this machine — skip it entirely if you're only generating seeds/hosting
  (see "Just hosting..." above). No compiler needed — this is a
  ready-to-use build of `extender\src_k1se\*` (this project's own extender
  code plus K1SE's merged dispatcher-hook source) and MinHook.
- **`KOTOR-AP-World-vX.Y.Z.zip`** → `kotor.apworld`, the Archipelago world
  implementation (item placement, location mapping, every player-facing
  option). Needed by anyone generating a seed AND anyone connecting with
  `KotorClient.py`, since it imports directly from this. Whoever generates
  your seed and everyone connecting to play it must be using the exact
  same version, or items/locations can come out mismatched — the release
  version number is your guarantee of that, don't substitute a different
  copy.
- **`KOTOR-AP-PlayerBundle-vX.Y.Z.zip`** → everything else needed to
  install and play: `extender\install.ps1`, the setup/delivery scripts
  under `scripts\`, the precompiled `dist\Override\` content, and a
  `KotorClient\` folder with the client script and its 3 helper modules.
  Skip it too if you're only generating seeds/hosting.

Download from **[the project's Releases page — link TBD, not published
yet]** and extract **PlayerBundle and Extender into the same destination
folder** — pick any folder, this becomes "your checkout" for the rest of
these steps; the two zips are laid out to merge cleanly (both put
`build_new\` and `install.ps1` under the same `extender\` folder). You
should end up with:

```
<your folder>\
  extender\install.ps1
  extender\build_new\binkw32.dll
  extender\area_trampolines\...
  scripts\...
  dist\Override\...
  KotorClient\...
```

`kotor.apworld` (from the World zip) and the `KotorClient\` folder's 4
files go somewhere different — your own Archipelago checkout, not this
folder — see Step 4.

## Step 2 — Install it

`install.ps1` captures whatever `binkw32.dll` is already in your game
folder as `binkw32_real.dll` (the true original Bink codec, forwarded
through to for every real Bink function), then drops the freshly-built
merged DLL in as the new `binkw32.dll`. Run it from inside `<your
folder>\extender\`:

```powershell
powershell -ExecutionPolicy Bypass -File "extender\install.ps1" -GameDir "C:\Program Files (x86)\Steam\steamapps\common\swkotor" -Install
```

Adjust `-GameDir` if your Steam library isn't in the default location.
This also writes `ap_repo_root.txt` into your game folder — a one-line
pointer back to `<your folder>` that the DLL reads at runtime to find
`scripts\arm_orchestrator.py`, so don't move or delete `<your folder>`
after installing without re-running this step.

To remove it later (restores the original `binkw32.dll`):

```powershell
powershell -ExecutionPolicy Bypass -File "extender\install.ps1" -GameDir "C:\Program Files (x86)\Steam\steamapps\common\swkotor" -Uninstall
```

## Step 3 — Deploy the mod's base scripts

This deploys the always-on part of the mod (area reporting, companion
suppression, shop markers) into your `Override` folder. It's pure Python
standard library — no compiler, no `pykotor`, nothing else to install for
this step:

```bash
python scripts\setup_game.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\swkotor"
```

This copies everything from `dist\Override\` — a folder of already-compiled
scripts, so nothing needs to be rebuilt on your machine.

## Step 4 — Generate a seed and connect

Before running `KotorClient.py`, it needs to live inside your own
Archipelago checkout (it imports `CommonClient`/`NetUtils` from there,
same as every other Archipelago world's client script) — copy all 4 files
from the `KotorClient\` folder (from Step 1's PlayerBundle zip) into the
root of your Archipelago checkout, alongside its `CommonClient.py`. Also
place `kotor.apworld` (from Step 1's World zip) at
`Archipelago\custom_worlds\kotor.apworld` in that same checkout (create
that folder if it doesn't exist yet).

**If someone ELSE is hosting the multiworld you're joining, skip this
step's `Generate.py`/`MultiServer.py` commands entirely** — send them your
filled-out `.yaml` instead and let their one generation run cover you too
(see "Just hosting..." above for why running it yourself would produce a
mismatched seed). Jump straight to connecting with `KotorClient.py` below
once they've told you their server address.

The rest of this step is for a solo game, or for whoever is doing the
generating/hosting for a group. `Generate.py` reads every `.yaml` file in
`Archipelago\Players\` and builds one multiworld seed covering all of them
(one file per player, even for a solo game). Start from **`kotor_test.yaml`
on the Releases page** (a standalone file, not inside any of the three
zips) rather than writing one from scratch — it documents every available
option inline, with its default and what it does. Download it into your
Archipelago checkout's `Players\` folder, then copy it to your own name:

```bash
copy Archipelago\Players\kotor_test.yaml Archipelago\Players\my_game.yaml
```

Edit `my_game.yaml`: set `name:` to whatever slot name you want to connect
with (must be unique among the files in `Players\` if you're generating for
more than one player at once), then adjust any options under the `KotOR:`
block — leave `game:` itself alone, that's the fixed internal name
Archipelago uses to find this world, not a display name. Delete or move
`kotor_test.yaml` out of `Players\` first if you don't want its own
(non-default) options generated as a second, separate slot alongside yours.

```bash
pip install -r Archipelago\requirements.txt
pip install "setuptools<81" pykotor
cd Archipelago
python Generate.py --player_files_path Players --outputpath output
```

Then, only if you enabled these options in your player YAML, apply them to
your own install (both accept `--game-dir` the same way `setup_game.py`
does, and default to the same standard Steam path if you omit it):

```bash
python scripts\patch_item_suppression.py --game-dir "C:\...\swkotor"
python scripts\patch_door_randomizer.py --game-dir "C:\...\swkotor"
```

Neither needs the NWScript compiler — `patch_door_randomizer.py` only edits
existing data fields, and `patch_item_suppression.py` uses a precompiled
script already checked into `extender\scripts_src\` for the same reason
`setup_game.py` doesn't need a compiler in Step 3.

Then connect with `KotorClient.py`. See `TESTING.md` for the full
walkthrough.

## Building from source (optional — only if you're modifying the extender)

Everyone else should use Step 1's prebuilt DLL instead. This needs
**Visual Studio Build Tools (2022, with the C++ workload)**:

```powershell
powershell -ExecutionPolicy Bypass -File "extender\build.ps1"
```

Compiles `extender\src_k1se\*` (this project's own extender code plus
K1SE's merged dispatcher-hook source) together with MinHook into
`extender\build_new\binkw32.dll` — the exact file Step 1 has you download
instead. Needs the VS2022 Build Tools' C++ toolchain on `PATH` (or run
from a "Developer PowerShell for VS 2022" prompt) — see the top of
`build.ps1` if it can't find `vcvars32.bat`. Once built, Step 2's
`install.ps1` works identically regardless of whether the DLL came from
here or from the downloaded zip.

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

## Known alpha limitations

- Door randomization and item suppression both directly rewrite game
  files — see the backup section above before enabling either.
- A handful of doors are structurally impossible to randomize and are left on their
  vanilla exit automatically. This is expected. Not a bug
- Companion class randomization (`randomize_class` option) writes a
  companion's class/level/Force directly and lets KOTOR's own normal
  in-game leveling catch them up to the party over subsequent play. It
  also grants/removes the Jedi-only feats and force-unequips Jedi-exclusive
  gear (lightsabers, Jedi robes) a real class switch implies. A current known gap: newly-granted Force Powers show up
  correctly on the character sheet but not in the combat hotbar/quickbar this means they cannot be used by characters who were not already force users.
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
  **[Bioware] For making an amazing game, I loved it as a kid growing up and its been interesting learning about the
  inner working of the engine that made this game  (the good and bad)

## AI usage

This project is largely vibecoded.
What do you mean by vibe coded?
A bulk portion of the code in this project is drafted by AI. The AI responsibilities
for this project included building the extender, apworld and python client. AI was also used both with asisting in research and diagnostics during testing. 
So what were you responsibities?
I built out testing ncs scripts to validate functionality.
I performed a review over all code line by line.
Validated my understanding of the code by questioning any functions/tracing code paths when documentation was unclear or not specific. As well as clarified my understanding for areas of the code I wasn't sure what it was used for and ensured was inline with design of the features and or project goal. 
I performed live in game testing of both my own scripts and AI drafted code and fixes.
I was responsible for all game design decisions. 

If you're evaluating this project's code quality, treat it accordingly:
this is a human-directed, AI-assisted alpha project, not a fully
human-hand-written one, and it's tested and reviewed as such.
