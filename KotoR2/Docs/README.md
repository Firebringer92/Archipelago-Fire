# KOTOR 2 (TSL) Archipelago

An [Archipelago](https://archipelago.gg) multiworld randomizer for **Star Wars: Knights of the Old Republic II – The Sith Lords** (Steam/Aspyr, 1.0.2.0).

> **Status: first test release (0.1.0).** It plays, but much of it has only been tried in part, and the story gates, which hold the story back until you have found the right items, have not had a full playthrough yet.
> Back up your saves and your game's `Modules` and `Override` folders before you play a randomized seed. Please report what breaks.
> Sister project: the KotoR folder of this repository (KOTOR 1).

## What it is

- **The world** (`Source/worlds/kotor2`): locations (quests, area visits, levels, alignment, recruits, influence, quest items, the Bazaar), items (story progression, companions, gear,
  skills, experience, credits, traps) and options. Needs Archipelago 0.6.7 or later to generate.
- **The client** (`Source/client`): connects to the Archipelago server, writes the seed's files into the game when it connects, and delivers items to the running game. Started with
  `Start_KOTOR2_Client.bat` or from the Archipelago Launcher ("KOTOR 2 Client").
- **The extension** (`Source/extender`): a `version.dll` proxy that adds script routines to the game (forked from [K2SE](https://github.com/renanaugustomacena-ux/K2SE) by renanaugustomacena-ux).
- **The scripts** (`Source/nss`): the NWScript that runs inside the game.
- **The installer** (`Source/installer`): `Install.bat`, `Uninstall.bat` and the Python script they run.

Story progression is kept in journal quests, one per planet, so a loaded older save brings back the stage it had. Optional randomizers change shops, loot, enemies and doors. Other options
add extra companions (the KOTOR 1 and KOTOR 2 characters, and generated ones named after the players), change companion classes (including droids), start you as another class, and
shorten the Peragus opening.

## What you need

- **Star Wars: Knights of the Old Republic II, the Steam version.** Other copies are not supported.
- **Windows.**
- **Python 3.12 or 3.13**, from [python.org](https://www.python.org/). 3.11.9 or a newer 3.11 also works; **Python 3.14 does not** (the Archipelago client refuses to run on it), and the
  Microsoft Store version of Python does not work with the game. If Install.bat asks for **Git for Windows**, it offers to install it (one of Archipelago's libraries comes from GitHub).
- **The Archipelago Launcher, 0.6.7 or newer**, only to **generate or host** a seed yourself. To play a seed someone else hosts you do not need it: the download carries the Archipelago
  files the client runs on.
- **An internet connection for the first install.** Nothing from the game is distributed: the files that are edits of the game's own are built on your machine from your own install (see `PROVENANCE.md`).

## Install

1. Download both zips from the **[Releases page](https://github.com/Firebringer92/Archipelago-Fire/releases)** (the same release, do not mix versions): `KotorTwoAP-World-v0.1.0.zip`
   (only `kotor2.apworld`) and `KotorTwoAP-PlayerBundle-v0.1.0.zip` (everything else).
2. Right-click the PlayerBundle zip, choose **Extract All**, and pick a new folder (for example `C:\KOTOR2-AP`; not inside Program Files and not inside the zip). Keep this folder: the client runs from it.
3. Double-click **`Install.bat`**. Press Enter to let it look for the game in the usual Steam and GOG places, or paste your KOTOR 2 folder (the one with `swkotor2.exe`). Close the game first.
   The install takes a few minutes: it puts `version.dll` next to the game, installs the Python libraries, builds the files made from your own copy of the game, and sets up the Launcher button.
4. Only if you generate or host seeds: put `kotor2.apworld` in the `custom_worlds` folder of your Archipelago Launcher install (not in the folder from step 2).

To remove everything, close the game and double-click **`Uninstall.bat`**: it takes the seed's files out of `Override`, puts back the module files and `dialog.tlk` the client changed, and removes `version.dll`.

## Play

1. Get a player YAML: download **[`KotOR2_TEMPLATE.yaml`](https://github.com/Firebringer92/Archipelago-Fire/blob/main/KotoR2/Docs/KotOR2_TEMPLATE.yaml)**, save it in the Launcher's `Players` folder under a new name, and edit `name:` and the options.
   If someone else hosts, send them your YAML.
2. Start the client: double-click **`Start_KOTOR2_Client.bat`** (or click "KOTOR 2 Client" in the Archipelago Launcher) and connect to the server with your slot name.
3. On connecting, the client writes the seed's files into the game. **If the game is already running, close it and start it again** so it sees the new files. Then start a new game.
4. `/k2_status` shows what the client is doing, `/k2_unpatch` takes the seed's files out of the game again, and `/release <gate>` lets you past a story gate that holds you up (it is logged, so the gate can be fixed).

## Known problems in this release

- Story gates are on and have not had a full playthrough. If one holds you up with nothing left to find, use `/release <gate>` and tell us which one.
- Many options are marked "Built, but not yet tried in the game" in the template. Expect problems there.
- On Peragus the hangar has no delivery loop until you touch one of its doors, so items and messages wait until then. Mira and T3-M4 cannot be added to the party while you are on Peragus; they can be added afterwards.
- Darth Nihilus has no blaster stances (he is a Force user); the generated companions use the player-head portraits, so non-human ones show human faces.
- The KOTOR 1 characters as extra companions use a generic look. Building their real models from your KOTOR 1 install (`/k2_prepare <your KOTOR 1 folder>`) is untested.
- Mods that change the game's class tables or scripts (for example TSLRCM) are not supported.
- If the client is started while an older save is loaded, it sends the items that save is missing again; this is by design.

## What the download contains, and under which licence

Everything we wrote is published in this repository. The player bundle also carries the third-party files below, unchanged, each with its licence text (all of them are repeated in
`THIRD_PARTY_NOTICES.txt` inside the bundle). Licences and conditions were read on 2026-11-20. The SHA-256 of each program is recorded in `Source/tools/provenance.json`, and a release is
refused if one changes without a new record.

| Part | Where in the bundle | Licence | Who | What we do with it |
|---|---|---|---|---|
| Archipelago core (0.6.8 source files) | `core/` | MIT | the Archipelago contributors ([github.com/ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago)) | Copied unchanged so the client runs without an Archipelago install; only `requirements.txt` is cut down to the libraries the client needs. Licence: `core/LICENSE`. |
| nwnsc 1.1.5 | `tools/nwnsc/` | MIT (Ken Johnson, Skywing); its compiler library `_NscLib` is BSD-3 (Edward T. Smith, The Open Knights Consortium) | [github.com/nwneetools/nwnsc](https://github.com/nwneetools/nwnsc) | The unchanged release, run as a separate program to compile the game scripts. Licence and credits: `tools/nwnsc/LICENSE.txt` and `CREDITS.txt`. |
| MDLOps 1.0.0 | `tools/mdlops/` | GNU General Public License (`GPL.txt`) | Chuck Chargin Jr., with JdNoa, ndix UR and other contributors; [Deadly Stream](https://deadlystream.com/files/file/779-mdlops/) | The unchanged program, shipped with its Perl source (`mdlops.pl`, `MDLOpsM.pm`), licence, readme and tutorials. It is run only as a separate program (our code never links to it) to build the droid models from your own game files. |
| The extension (`version.dll`) | `extender/` | Ours, built from `Source/extender` and forked from K2SE, which states MIT in its README (its repository has no LICENSE file and names no copyright holder; we publish ours with this credit) | [K2SE](https://github.com/renanaugustomacena-ux/K2SE) by renanaugustomacena-ux; address data from [Kotor-Patch-Manager](https://github.com/LaneDibello/Kotor-Patch-Manager) (MIT, LaneDibello) | The source is in `Source/extender`; the built program is recorded with its SHA-256 in each release's notes. |

Libraries that `Install.bat` downloads with pip are not part of the download and keep their own licences: pykotor (LGPL-3.0-or-later), numpy (BSD-3-Clause and others), pillow (MIT-CMU), Kivy
and KivyMD (MIT), websockets (BSD-3-Clause), PyYAML (MIT) and the rest of Archipelago's requirements. Python itself is not included.

The mod contains **nothing from the game**: no scripts, models, textures, text, tables or icons. Everything derived from KOTOR 2 is built on your machine from your own copy. KOTOR 2 and its
characters belong to their owners; this is an unofficial fan project, not affiliated with or endorsed by them.

## Checking the code

- `SECURITY.md` says what the software does on your computer and which checks limit it.
- `PROVENANCE.md` says where every file comes from.
- `RELEASE_CHECKLIST.md` is what has to be done before any release.
- GitHub runs four checks on every change (provenance, capabilities, world tests, client tests). Release builds are listed with their SHA-256 in the release notes.

## AI usage

Much of the code was written with an AI model, directed and reviewed by the maintainer. `SECURITY.md` and the capability check exist because of that.

## Credits

- Archipelago (MIT) – the multiworld framework.
- [K2SE](https://github.com/renanaugustomacena-ux/K2SE) by [renanaugustomacena-ux](https://github.com/renanaugustomacena-ux) (MIT, as stated in its README) – the script extender the in-game extension is forked from. Much of the extension's core (the script-engine hooks, the routine table, the offsets and the offset-checking tools) is theirs, with our changes and additions on top.
- [Kotor-Patch-Manager](https://github.com/LaneDibello/Kotor-Patch-Manager) by LaneDibello (MIT) – part of the address table comes from its Steam/Aspyr database, and the 32-slot companion roster follows the design of its PartyRosterLimit32K2 mod by Vriff (our own implementation).
- K1SE (MIT) – the KOTOR 1 extender whose design this project follows.
- nwnsc 1.1.5 (MIT, Ken Johnson; BSD-3 compiler library) – the script compiler. Licence and credits in `Source/tools/nwnsc`.
- **[MDLOps](https://deadlystream.com/files/file/779-mdlops/)** v1.0.0, written by Chuck Chargin Jr., with animation support by JdNoa, version 1.0 by ndix UR and many other contributors (GPL; submitted to Deadly Stream by Fair Strides) It ships unchanged in `tools\mdlops`, with its licence, readme, tutorials and Perl source, and builds the droid models from your own copy of the game on your machine.
- pykotor – reading and writing the game's file formats.
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra) (NSA, Apache 2.0) – used to study the game's program when working out the extension's addresses. Nothing of it is shipped.
- [xoreos-tools](https://github.com/xoreos/xoreos-tools) (xoreos team) – used as a reference when cross-checking the game's script-engine behaviour. Nothing of it is shipped.
