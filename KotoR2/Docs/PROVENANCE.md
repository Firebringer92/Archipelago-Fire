# Where every file comes from

This project randomizes a commercial game, so the rule is simple: **nothing in this repository or in a release download is a copy or an edit of the game's own files.**
Models, textures, icons, audio, conversations, scripts and data tables that belong to the game are made on the player's machine, from the player's own copy of KOTOR 2.

`Source/tools/provenance.json` is the machine-readable version of this page, and `Source/tools/check_provenance.py` enforces it on every push and on every release
(see `RELEASE_CHECKLIST.md`). If this page and that file ever disagree, the file is what is checked.

## What is in the repository

| What | Where | Origin |
|---|---|---|
| Python (world, client, tools, tests) | `Source/worlds/kotor2`, `Source/client`, `Source/tools` | Written for this project with heavy AI assistance, reviewed by the maintainer. Contains no game data. |
| NWScript source (`.nss`) | `Source/nss` | Our scripts, some of them generated. The game's own scripts, and the game's `nwscript.nss` that the compiler needs, are never stored here. |
| Compiled scripts (`.ncs`) | not in the repository | Build output. `Source/tools/build_payload.py` compiles them on the player's machine, together with wrappers that embed copies of the game's own scripts. The check fails any `.ncs` committed. |
| Item, creature, placeable and conversation templates | not in the repository | The client writes the few it needs (the Crafting Console, the message box, the Bazaar's Jawa and tokens, the extra companions) field by field on the player's machine. The check fails any template file that is not named `ap_*`. |
| The extender (a game-side DLL, `version.dll`) | `Source/extender/src` | Ours, forked from K2SE (see `README.md`, Credits). Built with CMake; the program itself is not in the repository. |
| The script compiler | `Source/tools/nwnsc` | nwnsc 1.1.5, MIT (Ken Johnson), with a compiler library under BSD-3. Downloaded unchanged; only its licence and credits are in the repository. |
| Data tables | `Source/data`, `Source/worlds/kotor2/data` | Facts read out of the game's data: identifiers, tags, coordinates, challenge ratings, module links, short item names. The check refuses a `description`, `text` or `dialogue` field in them, so no prose of the game's is stored. |
| Documentation | `Docs` | Ours. A document that quotes the game's text is reviewed by a person before it is added. |

Research notes, extracted game data and the maintainer's working files stay on the maintainer's machine and are not published.

## What is built on the player's machine and never published

The client builds these into the game's `Override` folder (and edits the module files in place, with a backup) when it connects, and puts everything back on `/k2_unpatch`:

- compiled scripts, including the wrappers that call copies of the game's own scripts (`tools/build_payload.py`, `tools/prepare_game_scripts.py`);
- the Crafting Console, the dispatcher's message box, the Bazaar's Jawa and tokens, and the extra companions' creature files (`client/k2_assets.py`, `k2_bazaar.py`, `k2_extras.py`);
- module changes for the enemy, loot, shop, door and Bazaar-token randomizers (`client/k2_modules.py` and the files that use it);
- the journal quests (`dialog.tlk` strings are appended, `global.jrl` is rebuilt; the originals are backed up) (`client/k2_journal.py`).

## Programs in a release

| Program | Licence | Source |
|---|---|---|
| `version.dll` (the extender) | ours, derived from K2SE | built from `Source/extender/src`; its SHA-256 goes in each release's notes |
| `tools/nwnsc/nwnsc.exe` | MIT + BSD-3 | https://github.com/nwneetools/nwnsc |

The repository holds none of these programs (`.gitignore` keeps `.exe`, `.dll` and `.ncs` files out). Each program is listed in `provenance.json` with its SHA-256, so replacing or adding
one is a visible change that the check rejects until it is recorded.

## How this is checked

1. **On every push and pull request** (GitHub Actions, no game installed): no game-format file anywhere; no file without a rule; templates named `ap_*`; no prose in the data tables;
   no code gaining a power it is not listed for; the world's and the client's test suites.
2. **Before every release, on the maintainer's machine** (with the game): the checklist in `RELEASE_CHECKLIST.md`, including a check that nothing in the repository is a copy of a game file.
