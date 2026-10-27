# Where every file comes from

This project randomizes a commercial game, so the rule is simple: **nothing in this repository or in a release download is a copy or an edit of the game's own files.**
Models, textures, icons, audio, conversations, scripts and data tables that belong to the game are made on the player's machine, from the player's own copy of KOTOR.

`Source/scripts/provenance.json` is the machine-readable version of this page, and `Source/scripts/check_provenance.py` enforces it on every push and on every release
(see `RELEASE_CHECKLIST.md`). If this page and that file ever disagree, the file is what is checked.

## What is in the repository

| What | Where | Origin |
|---|---|---|
| Python (world, client, installer, generators, tests) | `Source/kotor_ap`, `Source/scripts` | Written for this project with heavy AI assistance (see the README's "AI usage"), reviewed by the maintainer. Contains no game data. |
| NWScript source (`.nss`) and its compiled form (`.ncs`) | `Source/extender/scripts_src`, `Source/extender/raw_override_files` | Our scripts, many of them generated. The game's own scripts are never stored here; the few of them our scripts depend on are copied from the player's install (below). |
| Item, creature, placeable and conversation templates | `*.uti`, `*.utc`, `*.utp`, `*.dlg` in the two folders above | Created by our generators. Every one is named `ap_*`; the game's own files never are, and the check fails any template that is not. They refer to game models and base item types by name but contain none of them. |
| The extender (a game-side DLL) | `Source/extender/src_k1se` | Ours, built on K1SE's hook code (MIT, Brandon Guffey; licence in `K1SE_LICENSE.txt`), linked with MinHook and the Hacker Disassembler Engine (BSD-2). |
| MinHook | `Source/extender/third_party/minhook` | Third party, BSD-2 (Tsuda Kageyu); its licence is in the folder. |
| The script compiler | `Source/tools/nwnsc` | nwnsc 1.1.5, MIT (Ken Johnson), with a compiler library under BSD-3 (Edward T. Smith, The Open Knights Consortium). Downloaded unchanged; licence and credits in the folder. |
| Data tables | the `*.json` files under `Source`, `Source/kotor_ap` and `Source/extender/area_trampolines` | Facts read out of the game's data: identifiers, tags, coordinates, challenge ratings, door-to-module links, short item and power names. The check refuses a `description`, `text` or `dialogue` field in them, so no prose of the game's is stored. The short names are the game's own words; they are needed to refer to the game's things at all. |
| Recipes for building game-derived files | `Source/scripts/preserved_originals.json` and the builder scripts | Names of the game's resources and byte offsets to change. They contain no game bytes. |
| Documentation | `Docs` | Ours. |

## What is built on the player's machine and never published

`build_game_assets.py` (run by the installer, again on every connect, and undone by the uninstaller) and `model_builders.py` make these from the player's install:

- the copies of the game's scripts that our wrappers call (`apo_*`);
- the cutscene conversations with one extra link, and the companions' feat-training conversations;
- the six extra lightsaber crystal colours (models, blade glows, icons, item templates, `upcrystals.2da`);
- three edited creature and trigger templates;
- the Malak, HK-47 variant and droid models (with MDLOps);
- `nwscript.nss` and the game's include scripts, which the compiler needs.

`scripts/list_game_derived.py` is the single rule for "is this derived from the game"; the packagers, the repository sync and the tests all use it.

## Programs in a release

| Program | Licence | Source |
|---|---|---|
| `binkw32.dll` (the extender) | ours + MIT (K1SE) + BSD-2 (MinHook, HDE) | built from `Source/extender/src_k1se` |
| `tools/nwnsc/nwnsc.exe` | MIT + BSD-3 | https://github.com/nwneetools/nwnsc |
| `tools/mdlops/mdlops.exe` (release zip only) | GPL | https://deadlystream.com/files/file/779-mdlops/ ; shipped with its Perl source, licence, readme and tutorials |

Each program is listed in `provenance.json` with its SHA-256, so replacing or adding one is a visible change that the check rejects until it is recorded. Python packages
(Kivy, pykotor, numpy, pillow and others) are downloaded by the installer and not shipped.

## How this is checked

1. **On every push and pull request** (GitHub Actions, no game installed): no game-format file anywhere; no file without a rule; templates named `ap_*`; every program registered
   with its hash; no prose in the data tables; and the whole world test suite.
2. **On every release:** the published zips are downloaded and checked again, including the `.apworld` inside the world zip.
3. **Before every release, on the maintainer's machine** (with the game): `release_gate.py`, which also checks that no file in the repository has the same name as one
   that the derived-file rule identifies as the game's (that check needs the game, so GitHub cannot run it), and the clean-room install described in `RELEASE_CHECKLIST.md`.
