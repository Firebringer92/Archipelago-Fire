# Release checklist — required for every release and every patch

No release or patch is published until every item below is done and the sign-off line (last section) is in its patch notes. A hotfix is not an exception:
the smallest patch is where an unreviewed file is most likely to slip in.

The point of the checklist is that **a person looks at what is new**. The scripts do the counting and catch the mistakes that are easy to make; they cannot
decide where a new file came from. That decision is always made by a person.

## 1. Before packaging

- [ ] **Every new kind of file has a rule.** If the release adds a file type, folder or program that `Source/scripts/provenance.json` does not describe, add its rule there
  (what it is, where it came from) in the same change. Not knowing where a file came from is a reason to stop, not to guess.
- [ ] **Every new third-party file has its licence read by a person.** Record the download page, the licence name, the conditions on redistributing it and the date in the
  patch notes. Ship its licence text, add it to `THIRD_PARTY_NOTICES.txt` (in `package_playerbundle.py`), and credit it in `README.md`. A program also gets an entry (with its SHA-256)
  under `binaries` in `provenance.json`.
- [ ] **Nothing was copied out of the game.** Anything that is a copy or an edit of a game file is built on the player's machine by `build_game_assets.py`, never stored in the
  repository or in a zip (see `PROVENANCE.md`).
- [ ] **The poll script in `extender/scripts_src` is the release baseline.** The client rewrites it for whichever seed was connected last. The gate (step 3) checks this.
- [ ] Version numbers decided: `WORLD_VERSION` only changes for a change that needs a new world; client-only fixes change only the PlayerBundle version.
- [ ] When packaging the world, `--min-ap-version` is the oldest Archipelago version a real player's install has (ask; do not let it default to the development machine's).

## 2. Build

- [ ] `python scripts/package_apworld.py` and `python scripts/package_playerbundle.py`. Both run the provenance check on the zip they just wrote and refuse (exit 1) if it fails.
- [ ] **Programs and compiled scripts are not committed.** The zips carry `binkw32.dll`, `nwnsc.exe`, `mdlops.exe` and the compiled `.ncs` files; the repository does not (`.gitignore`, and the check
  fails them). If the extender was rebuilt, record the new DLL's SHA-256 in `provenance.json` (the gate fails until you do) and in the patch notes.

## 3. The gate (automatic)

- [ ] `python scripts/release_gate.py --previous <the last release's PlayerBundle zip>` ends with **RESULT: PASS**. It checks the poll baseline, runs the whole test suite with the game
  installed, checks that the repository copy holds nothing derived from the game, runs the provenance check on the repository copy and on both release zips, and lists the
  non-code files the release adds or changes. Its report is saved in `docs/release_reports/`; keep the file name for the sign-off.
- [ ] The repository copy is synced, pushed, and the **"KotoR checks" run on GitHub is green** (both jobs: *Provenance* and *World tests*). Link the run in the patch notes.

## 4. By a person

- [ ] **Read the gate's list of added and changed non-code files and account for each one**: ours, built on the player's machine, or third-party with a licence. Any file nobody
  can account for stops the release.
- [ ] **Clean-room install.** Extract the PlayerBundle zip into a new folder. Use a throwaway copy of the game folder (copy `modules\`; link or copy the rest, never link `modules\`).
  Run `Install.bat` against it, connect a generated seed, confirm the client log has no `APPLY FAILED`, `COMPILE FAILED` or `[game assets] FAILED`, then run `Uninstall.bat`
  and confirm the files the install made are gone.
- [ ] **In-game test of what changed**, listed in the patch notes (what was tried, and the result).
- [ ] **If the git history was rewritten, or a file was ever removed for copyright:** produce the list of every path git ever recorded and check it:
  `git log --all --name-only --pretty=format: | sort -u > paths.txt`, then `python scripts/check_provenance.py --paths-file paths.txt`. It must pass.
- [ ] `README.md`, `TESTING.md` and `DESIGN.md` describe what changed, including credits for anything new.

## 5. After publishing

- [ ] The **"KotoR release check"** run on GitHub (it downloads the published zips and checks them again, including the `.apworld` inside the world zip) is green. If it is red,
  take the release down and fix it before anyone downloads it.

## Sign-off line (paste into the patch notes)

> Provenance: gate report `gate_YYYYMMDD_HHMM.txt` (PASS); GitHub checks `<link to the run>`; new non-code files accounted for: `<list or "none">`;
> third-party files added: `<name, licence, link, date read, or "none">`. Reviewed by `<name>` on `<date>`.
