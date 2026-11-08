# What this software does on your computer

This is the KOTOR 2 (TSL) Archipelago randomizer: an Archipelago world (`kotor2.apworld`), a client, and a small extension (`version.dll`) that runs inside Star Wars Knights of the Old Republic II.
Much of the code was written with the help of an AI model and directed and reviewed by the maintainer. Because of that, this page says plainly what the software can do, which checks limit it,
and where a person should read the code first. It is meant to be checked against the code, not taken on trust. **It is not released yet.**

## What it can do

| Power | What it does here |
|---|---|
| **Network** | The client talks to the Archipelago server you give it, through Archipelago's own client code. **Our own code opens no other connection**: no telemetry, no update check, no accounts. The extension in the game opens no socket either; client and game exchange text files in `%LOCALAPPDATA%\K2SE\ap` (an inbox and an outbox). |
| **Programs it starts** | Python running our own scripts, `tools/nwnsc/nwnsc.exe` (the script compiler), and `tasklist` (to see whether the game is running). The Archipelago Launcher button starts the client in a new console window. Always as a list of arguments, never through a shell. |
| **Files it writes** | The game folder: `Override\` (files we add), `modules\*.rim` (rewritten in place for the seed's options; the originals are copied to the client's state folder first), `dialog.tlk` (strings appended; the original is backed up), `global.jrl` (rebuilt), and `version.dll` (the extension). Your user folders: `%LOCALAPPDATA%\K2SE` (config, the inbox and outbox, logs) and the client's state folder. |
| **Files it deletes** | Only files it wrote itself, plus its own temporary files. The full list of code that deletes anything is in `Source/tools/capabilities.json`, with the reason for each. `/k2_unpatch` puts the game folder back. |
| **Registry, admin tricks** | None. The code does not touch the registry, and `ctypes`, `eval`, `exec`, `pickle` and `shell=True` are forbidden by a check (below). |
| **Inside the game** | `version.dll` is a proxy that the game loads at start. It hooks the game's script engine, adds script routines, and reads and writes that process's memory. Native code like this is the part that most deserves a careful read. |

Antivirus programs sometimes flag a proxy DLL that hooks a game. The SHA-256 of each shipped DLL is recorded in the release notes.

## What limits it

These run on every push to GitHub and again before every release. A failure blocks the release.

- **Provenance** (`Source/tools/check_provenance.py`, rules in `provenance.json`): nothing derived from the game's own files is in the repository or a download, every file is accounted for, and every
  program is listed with its SHA-256.
- **Capabilities** (`Source/tools/check_capabilities.py`, list in `capabilities.json`): every file that starts a program, opens a connection, deletes files or imports code by name is listed with a
  reason a person wrote after reading it. A new use fails the check until someone adds it. Things that are never allowed fail outright: `eval`, `exec`, `pickle`, `marshal`, `ctypes`, the registry and `shell=True`.
- **Tests**: the world's and the client's test suites run on GitHub with no game installed.
- **A release checklist** (`RELEASE_CHECKLIST.md`) makes a person look at what is new, including every new third-party file and its licence, before each release, hotfixes included.

## Where to read the code first

| File | What it can do |
|---|---|
| `extender/src/dllmain.cpp`, `hookkit.cpp`, `routines.cpp`, `gameobj.cpp`, `cwrite.cpp` | The extension inside the game: the hooks, the routines scripts can call, the game memory it reads and writes. The most powerful code here. |
| `extender/src/apfiles.cpp` | How the game reads the inbox and writes the outbox. |
| `client/KotorTwoClient.py`, `client/k2_dispatcher.py`, `client/k2_files.py` | The client: what it sends to the game and what it writes into the game folder when it connects. |
| `client/k2_patch.py`, `client/k2_modules.py`, `client/k2_journal.py` | What is written into `Override`, `modules`, `dialog.tlk` and `global.jrl`, and how it is undone. |
| `worlds/kotor2/ClientLauncher.py` | The Launcher button: what it starts. |
| `tools/k2compile.py` | How scripts are compiled. |
| `tools/capabilities.json` | Every other place the code starts a program or deletes a file. |

## What this does not promise

- A check can show that code stays inside the powers listed for it. It cannot show that the logic inside those powers is right or harmless. Reading the files above is still the real review.
- The extension is native code that runs inside the game. It is built from the source in `extender/src`, but a third party cannot yet rebuild the shipped DLL from that source and compare it.
- The extension is forked from [K2SE](https://github.com/renanaugustomacena-ux/K2SE) (MIT, stated in its README); much of its core is that project's code with our changes (see `README.md`, Credits).

## Reporting a problem

Open an issue on the repository. If you think something is a security problem, say so in the title and leave out the details; use GitHub's private "Report a vulnerability" option if it is enabled
on the repository, or ask in the issue for a private way to send them.
