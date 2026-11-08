# Release checklist — required for every release and every patch

No release or patch is published until every item below is done and the sign-off line (last section) is in its patch notes. A hotfix is not an exception:
the smallest patch is where an unreviewed file is most likely to slip in.

The point of the checklist is that **a person looks at what is new**. The scripts do the counting and catch the mistakes that are easy to make; they cannot
decide where a new file came from. That decision is always made by a person.

## 0. Not built yet (the first release waits for these)

- A release gate script that runs everything in section 3 in one go and saves its report. Until it exists, run the commands of section 3 by hand and paste their output into the patch notes.
- The installer and the release zips. Section 2 and the clean-room install describe what they must satisfy.
- A check that no file in the repository has the same name as one of the game's own (needs the game, so GitHub cannot run it).
- A person's review of the K2SE licence. Decision (maintainer, 2026-11-08): the repository's README states MIT, so the extension is published with a link and credit in `README.md`. Note for the review: GitHub shows no `LICENSE` file or named copyright holder there; if the author adds one, copy its text into `Source/extender/`.
- MDLOps is credited in `README.md` as planned for model editing but is not used yet. The day it is first used or shipped: add its `binaries` entry (SHA-256) to `provenance.json`, ship it unchanged with its licence, readme and tutorials (it is GPL), add it to the capability list if our code runs it, and change the README line from "planned" to a plain credit.

## 1. Before packaging

- [ ] **Every new kind of file has a rule.** If the release adds a file type, folder or program that `Source/tools/provenance.json` does not describe, add its rule there
  (what it is, where it came from) in the same change. Not knowing where a file came from is a reason to stop, not to guess.
- [ ] **Every new third-party file has its licence read by a person.** Record the download page, the licence name, the conditions on redistributing it and the date in the
  patch notes. Ship its licence text, credit it in `README.md`. A program also gets an entry (with its SHA-256) under `binaries` in `provenance.json`.
- [ ] **Every new power has a reason.** If the code now runs a program, opens a connection, deletes files or imports by name where it did not before, a person reads that code and adds the file
  and the reason to `Source/tools/capabilities.json`. The GitHub checks fail until it is there, and nothing in `SECURITY.md` should say something the manifest contradicts.
  `eval`, `exec`, `pickle`, `ctypes`, the registry and `shell=True` are never allowed.
- [ ] **Nothing was copied out of the game.** Anything that is a copy or an edit of a game file is built on the player's machine (`tools/build_payload.py`, the client's builders), never stored in the
  repository or in a zip (see `PROVENANCE.md`). `client/payload` and `_build` folders are build output of the maintainer's machine and must not be packaged.
- [ ] Version numbers decided: `WORLD_VERSION` only changes for a change that needs a new world; client-only fixes change only the bundle's version.
- [ ] When packaging the world, `--min-ap-version` is the oldest Archipelago version a real player's install has (ask; do not let it default to the development machine's).

## 2. Build

- [ ] `python tools/package_world.py` (the world) and the bundle's packager. Each runs the provenance check on what it wrote and refuses if it fails.
- [ ] **Programs and compiled scripts are not committed.** The zips carry `version.dll`, `nwnsc.exe` and the compiled `.ncs` files; the repository does not (`.gitignore`, and the check
  fails them). If the extender was rebuilt, record the new DLL's SHA-256 in `provenance.json` and in the patch notes.

## 3. The checks

- [ ] `python tools/stage_publish.py` stages the repository copy and runs the provenance check on it; it must end with `OK`.
- [ ] `python tools/check_capabilities.py --root <the staged folder> --manifest <staged>/Source/tools/capabilities.json` must end with `OK`.
- [ ] `python tools/run_world_tests.py` and `python tools/run_client_tests.py` pass **with the game installed** (so the game-reading tests run, not skip).
- [ ] The repository copy is synced, pushed, and the **"KotoR2 checks" run on GitHub is green** (all four jobs: *Provenance*, *Capabilities*, *World tests*, *Client tests*). Link the run in the patch notes.
- [ ] Compiled scripts are free of the instruction that stops the game's script engine (`tools/k2compile.py` strips it; check a fresh build).

## 4. By a person

- [ ] **Read the list of added and changed non-code files and account for each one**: ours, built on the player's machine, or third-party with a licence. Any file nobody
  can account for stops the release.
- [ ] **Clean-room install.** Extract the release zip into a new folder. Use a throwaway copy of the game folder. Connect a generated seed, confirm the client log has no failed step,
  then run `/k2_unpatch` and confirm the game folder is back to what it was (`dialog.tlk`, `global.jrl`, the module files and `Override`).
- [ ] **In-game test of what changed**, listed in the patch notes (what was tried, and the result). The deferred live tests are in the maintainer's `docs/TEST_QUEUE.md`.
- [ ] **If the git history was rewritten, or a file was ever removed for copyright:** produce the list of every path git ever recorded and check it:
  `git log --all --name-only --pretty=format: | sort -u > paths.txt`, then `python tools/check_provenance.py --paths-file paths.txt`. It must pass.
- [ ] `README.md` describes what changed, including credits for anything new.

## Sign-off line (paste into the patch notes)

> Provenance: checks run `<link to the GitHub run>`; new non-code files accounted for: `<list or "none">`;
> third-party files added: `<name, licence, link, date read, or "none">`. Reviewed by `<name>` on `<date>`.
