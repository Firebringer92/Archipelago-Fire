# What this software does on your computer

This is the KOTOR Archipelago randomizer: an Archipelago world (`kotor.apworld`), a client, and a small extension that runs inside Knights of the Old Republic. Much of the code was
written with the help of an AI model and directed and reviewed by the maintainer. Because of that, this page says plainly what the software can do, which checks limit it, and where a
person should read the code first. It is meant to be checked against the code, not taken on trust.

## What it can do

| Power | What it does here |
|---|---|
| **Network** | The client talks to the Archipelago server you give it, through Archipelago's own client code. `Install.bat` downloads `pykotor`, `numpy`, `pillow` and `setuptools` from PyPI (the latest versions at install time). Archipelago's own launcher code may install Archipelago's own Python requirements, which is standard Archipelago behaviour. **Our own code makes no other network connection**: the only network use in our files is one connection from the client to the game, on `127.0.0.1` (this computer). No telemetry, no update check, no accounts. |
| **Programs it starts** | Python running our own scripts; `tools/nwnsc/nwnsc.exe` (the script compiler); `tools/mdlops/mdlops.exe` (a model tool, GPL); `pip` (at install); `tasklist` (to see whether the game is running). Always as a list of arguments, never through a shell. |
| **Files it writes** | The game folder: `Override\` (files we add), `modules\*.rim` (rewritten in place for the seed's options; the originals are copied to `extender\backup` first), `dialog.tlk` (strings appended; the original is backed up), and `binkw32.dll` (replaced by our proxy; the original is kept as `binkw32_real.dll`). Your user folders: `%LOCALAPPDATA%\KotorAP` (state, a model cache, manifests), `%LOCALAPPDATA%\KSE\kse.log` (the extension's log), and the install folder (client logs, the delivery log). |
| **Files it deletes** | Only files it wrote itself, recorded with a hash so a file you changed or replaced is left alone, plus its own temporary files. The full list of code that deletes anything is in `Source/scripts/capabilities.json`, with the reason for each. Uninstall (`Uninstall.bat`) and `/ap_restore_all` put the game folder back. |
| **Registry, admin tricks** | None. The code does not touch the registry, and `ctypes`, `eval`, `exec`, `pickle` and `shell=True` are forbidden by a check (below). |
| **Inside the game** | `binkw32.dll` is a proxy for the game's video library. It forwards the game's calls and loads the extension, which is built on K1SE (MIT). The extension runs in the game's own process: it hooks the game's script engine, reads and writes that process's memory, and listens on `127.0.0.1:25586`. Native code like this is the part that most deserves a careful read. |

Antivirus programs sometimes flag a proxy DLL that hooks a game. The SHA-256 of the shipped DLL is recorded in `Source/scripts/provenance.json`, and GitHub shows the SHA-256 of each release zip
next to its download.

## What limits it

These run on every push to GitHub and again before every release. A failure blocks the release.

- **Provenance** (`Source/scripts/check_provenance.py`, rules in `provenance.json`): nothing derived from the game's own files is in the repository or a download, every file is accounted for, and every
  program is listed with its SHA-256. The game's models, textures, templates and dialogs are built on your machine from your own install.
- **Capabilities** (`Source/scripts/check_capabilities.py`, list in `capabilities.json`): every file that starts a program, opens a connection, deletes files or imports code by name is listed with a
  reason a person wrote after reading it. A new use fails the check until someone adds it. Things that are never allowed fail outright: `eval`, `exec`, `pickle`, `marshal`, `ctypes`, the
  registry and `shell=True`.
- **Tests**: the world's test suite runs on GitHub with no game installed.
- **Compiled scripts** are checked for the instruction that stops the game's script engine (see `ncs_nops.py`).
- **A release checklist** (`RELEASE_CHECKLIST.md`) makes a person look at what is new, including every new third-party file and its licence, before each release, hotfixes included.

## Where to read the code first

| File | What it can do |
|---|---|
| `extender/src_k1se/ap_extender.c`, `kse_hook.cpp`, `dllmain.cpp` | The extension inside the game: the local connection and the commands it accepts, the hooks, the game memory it reads and writes. The most powerful code here. |
| `kotor_extender_bridge.py`, `kotor_dispatcher.py` | How the client talks to the extension, and what it sends. |
| `KotorClient.py` | The client: what it starts, and what it writes into the game folder when it connects. |
| `scripts/install_playerbundle.py` | Install and uninstall: the `pip` step, the `binkw32.dll` swap and backup, and what Uninstall removes. |
| `scripts/client_files.py`, `scripts/build_game_assets.py` | What the client and the asset builder write into `Override`, and how they undo it. |
| `scripts/nwnnsscomp_path.py`, `scripts/ncs_nops.py` | How scripts are compiled and cleaned before the game runs them. |
| `scripts/capabilities.json` | Every other place the code starts a program or deletes a file. |

## What this does not promise

- A check can show that code stays inside the powers listed for it. It cannot show that the logic inside those powers is right or harmless. Reading the files above is still the real review.
- The extension is native code that runs inside the game. It is built from the source in `extender/src_k1se`, but a third party cannot yet rebuild the shipped DLL from that source and compare it.
- `Install.bat` installs the latest `pykotor`, `numpy` and `pillow` from PyPI, so those come from their own maintainers and are not pinned to a tested version.

## Reporting a problem

Open an issue on the repository. If you think something is a security problem, say so in the title and leave out the details; use GitHub's private "Report a vulnerability" option if it is enabled
on the repository, or ask in the issue for a private way to send them.
