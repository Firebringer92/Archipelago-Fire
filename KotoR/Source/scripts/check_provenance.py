"""
Provenance check: every file we publish has to be something we wrote, something we build from the player's own install, or a third-party file we ship with its licence.
It needs no KOTOR install, so it runs on GitHub's servers as well as on a development machine.

  check_provenance.py --root KotoR                 check a repository folder (CI runs this on every push)
  check_provenance.py --zip dist/KOTOR-AP-PlayerBundle-vX.zip     check a release zip
  check_provenance.py --root KotoR --zip a.zip b.zip              both
  check_provenance.py --compare OLD.zip NEW.zip   list the non-code files a release adds, changes or drops, for a human to look at
  check_provenance.py --paths-file paths.txt      check every path git ever recorded (one per line, from the command in RELEASE_CHECKLIST.md)

The rules live in provenance.json next to this script (read that file to see what is allowed and why):
  - a file with a game-data extension (models, textures, 2DA tables, archives, audio ...) fails, wherever it is;
  - a file that no rule in provenance.json describes fails: adding a new kind of file means adding its rule, with its origin, in the same commit;
  - a conversation, item, creature or placeable template must be named ap_* (the game's own are never named like that);
  - every .exe and .dll must be listed with its SHA-256, its source and its licence file, so a changed or added program is a visible edit;
  - the data tables that come from facts about the game must not carry prose (descriptions, dialogue text).
The check that a name does not exist in the game needs the game itself, so that part (list_game_derived.py and test_game_assets.py) stays in the release checklist.
Exit status 0 when everything passes, 1 otherwise.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "provenance.json")


def _glob_to_regex(pattern):
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$", re.IGNORECASE)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class Rules:
    def __init__(self, path=MANIFEST):
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        self.manifest = m
        self.banned = {e.lower() for e in m["banned_extensions"]}
        self.gff_ext = {e.lower() for e in m["gff_extensions"]}
        self.gff_prefix = m["gff_name_prefix"].lower()
        self.allowed = [(_glob_to_regex(r["glob"]), r) for r in m["allowed"]]
        self.binaries = {b["path"].lower(): b for b in m["binaries"] if "path" in b}
        self.zip_binaries = {b["zip_path"].lower(): b for b in m["binaries"] if "zip_path" in b}
        self.prose_keys = {k.lower() for k in m["prose_keys_forbidden_in_data"]}
        self.prose_files = [_glob_to_regex(g) for g in m["data_tables_checked_for_prose"]]
        self.zip_exempt = [_glob_to_regex(g) for g in m["zip_exempt_from_banned_extensions"]]
        self.zip_forbidden_names = {n.lower() for n in m["zip_forbidden_names"]}
        self.zip_own_apo = {n.lower() for n in m["zip_own_apo_files"]}


def _prose_problems(rel, data, rules):
    problems = []
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except Exception as e:
        return [f"{rel}: not valid JSON ({e})"]

    def walk(x, trail):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in rules.prose_keys:
                    problems.append(f"{rel}: has a '{k}' field at {trail or '/'}; data tables may hold identifiers, tags, coordinates and short names, never the game's prose")
                walk(v, trail + "/" + str(k)[:30])
        elif isinstance(x, list):
            for i, v in enumerate(x[:2000]):
                walk(v, trail + f"[{i}]")
    walk(doc, "")
    return problems[:5]


def check_tree(root, rules):
    problems = []
    seen_binaries = set()
    count = 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            ext = os.path.splitext(name)[1].lower()
            count += 1
            if ext in rules.banned:
                problems.append(f"{rel}: a game-data file ({ext}). Models, textures, tables, archives and audio from the game must never be published; build them from the player's install instead.")
                continue
            if ext in (".exe", ".dll", ".so", ".dylib", ".sys", ".com", ".msi"):
                entry = rules.binaries.get(rel.lower())
                if entry is None:
                    problems.append(f"{rel}: a program that is not listed under 'binaries' in provenance.json. Add it with its SHA-256, source and licence file, or remove it.")
                    continue
                seen_binaries.add(rel.lower())
                with open(full, "rb") as f:
                    digest = _sha256(f.read())
                if digest != entry["sha256"].lower():
                    problems.append(f"{rel}: its SHA-256 ({digest[:16]}...) is not the one recorded in provenance.json. If you rebuilt or replaced it on purpose, update the entry (and its source and licence) in the same commit.")
                lic = entry.get("licence_file")
                if lic and not os.path.isfile(os.path.join(root, lic)):
                    problems.append(f"{rel}: its licence file {lic} is missing.")
                continue
            matched = next((r for rx, r in rules.allowed if rx.match(rel)), None)
            if matched is None:
                problems.append(f"{rel}: no rule in provenance.json describes this file. Decide where it came from (we wrote it, we build it, or it is third-party with a licence), then add a rule.")
                continue
            if ext in rules.gff_ext and not name.lower().startswith(rules.gff_prefix):
                problems.append(f"{rel}: a conversation, item, creature or placeable template must be named {rules.gff_prefix}*; the game's own are not, so this may be a copy of one.")
            if any(rx.match(rel) for rx in rules.prose_files):
                with open(full, "rb") as f:
                    problems += _prose_problems(rel, f.read(), rules)
    return problems, count


def check_zip(zpath, rules):
    problems = []
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        for n in names:
            if n.endswith("/"):
                continue
            low = n.lower()
            base = os.path.basename(low)
            ext = os.path.splitext(base)[1]
            exempt = any(rx.match(n) for rx in rules.zip_exempt)
            if ext in rules.banned and not exempt:
                problems.append(f"{n}: a game-data file ({ext}) in the release.")
            if base.startswith("apo_") and base not in rules.zip_own_apo:
                problems.append(f"{n}: a preserved game script; these are built on the player's machine.")
            if base in rules.zip_forbidden_names:
                problems.append(f"{n}: a file written from the player's install; it must not ship.")
            if ext in (".exe", ".dll", ".so", ".dylib", ".sys", ".com", ".msi"):
                entry = rules.zip_binaries.get(low)
                if entry is None:
                    problems.append(f"{n}: a program in the release that is not listed under 'binaries' (with a zip_path) in provenance.json.")
                elif _sha256(z.read(n)) != entry["sha256"].lower():
                    problems.append(f"{n}: its SHA-256 is not the one recorded in provenance.json.")
            if ext in rules.gff_ext and not base.startswith(rules.gff_prefix) and not low.startswith(("data/", "worlds/")):
                problems.append(f"{n}: a template not named {rules.gff_prefix}*; the game's own are never named like that.")
        for n in names:
            if n.lower().endswith(".apworld"):          # the world zip holds kotor.apworld, which is a zip itself
                with tempfile.TemporaryDirectory() as tmp:
                    inner = os.path.join(tmp, os.path.basename(n))
                    with open(inner, "wb") as f:
                        f.write(z.read(n))
                    inner_problems, _ = check_zip(inner, rules)
                    problems += [f"{n} -> {p}" for p in inner_problems]
        notices = z.read("THIRD_PARTY_NOTICES.txt").decode("utf-8", "replace") if "THIRD_PARTY_NOTICES.txt" in names else ""
        for b in rules.manifest["binaries"]:
            if "zip_path" in b and b["zip_path"] in names:
                for needle in b.get("notice_must_mention", []):
                    if needle not in notices:
                        problems.append(f"THIRD_PARTY_NOTICES.txt does not mention '{needle}', but the release ships {b['zip_path']}.")
                if b.get("licence_zip_path") and b["licence_zip_path"] not in names:
                    problems.append(f"{b['licence_zip_path']} (the licence for {b['zip_path']}) is missing from the release.")
    return problems, len([n for n in names if not n.endswith('/')])


CODE_EXTENSIONS = {".py", ".nss", ".ncs", ".c", ".cpp", ".h", ".md", ".txt", ".bat", ".ps1", ".yaml", ".yml", ".kv", ".json", ".apignore", ".sln", ".vcxproj", ".filters", ".vcproj", ".cmake", ".rc", ".def", ".in", ""}


def compare_zips(old_path, new_path):
    """Prints the files whose kind is not plain code or text that were added, changed or dropped between two releases."""
    def table(path):
        with zipfile.ZipFile(path) as z:
            return {n: _sha256(z.read(n)) for n in z.namelist() if not n.endswith("/")}
    old, new = table(old_path), table(new_path)
    added = sorted(n for n in new if n not in old)
    changed = sorted(n for n in new if n in old and new[n] != old[n])
    dropped = sorted(n for n in old if n not in new)
    review = lambda names: [n for n in names if os.path.splitext(n)[1].lower() not in CODE_EXTENSIONS]
    print(f"{os.path.basename(old_path)} -> {os.path.basename(new_path)}: {len(added)} added, {len(changed)} changed, {len(dropped)} dropped")
    for label, names in (("ADDED", added), ("CHANGED", changed), ("DROPPED", dropped)):
        odd = review(names)
        print(f"  {label} files that are not plain code or text ({len(odd)}) - look at each one and say where it came from:")
        for n in odd:
            print("     " + n)
    return len(review(added)) + len(review(changed))


def check_paths(path, rules):
    """Every path git ever recorded (a list, one per line): none may have been a game-data file."""
    problems, n = [], 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            rel = line.strip().strip('"')
            if not rel:
                continue
            n += 1
            ext = os.path.splitext(rel)[1].lower()
            if ext in rules.banned and not any(rx.match(rel) for rx in rules.zip_exempt):
                problems.append(f"{rel}: a game-data file ({ext}) was recorded in the history")
            base = os.path.basename(rel).lower()
            if base in rules.zip_forbidden_names or (base.startswith("apo_") and base not in rules.zip_own_apo):
                problems.append(f"{rel}: a file written from, or a copy of, the game's scripts was recorded in the history")
            if ext in (".ncs", ".exe", ".dll", ".obj"):
                problems.append(f"{rel}: build output ({ext}) was recorded in the history; the repository holds source only")
            if ext in rules.gff_ext and not base.startswith(rules.gff_prefix):
                problems.append(f"{rel}: a template not named {rules.gff_prefix}* was recorded in the history; the game's own are never named like that, so this may be a copy of one")
    return problems, n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", help="repository folder to check (e.g. KotoR)")
    ap.add_argument("--zip", nargs="*", default=[], help="release zip(s) to check")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--compare", nargs=2, metavar=("OLD_ZIP", "NEW_ZIP"), help="list the non-code files that differ between two releases")
    ap.add_argument("--paths-file", help="a list of every path git ever recorded, one per line")
    args = ap.parse_args()
    if args.compare:
        compare_zips(*args.compare)
        if not args.root and not args.zip and not args.paths_file:
            return
    if not args.root and not args.zip and not args.paths_file:
        ap.error("give --root, --zip, --compare or --paths-file")
    rules = Rules(args.manifest)
    failed = False
    if args.paths_file:
        problems, count = check_paths(args.paths_file, rules)
        print(f"provenance: {count} paths in the history: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems[:200]:
            print("  FAIL " + p)
        failed = failed or bool(problems)
    if args.root:
        problems, count = check_tree(args.root, rules)
        print(f"provenance: {count} files under {args.root}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems:
            print("  FAIL " + p)
        failed = failed or bool(problems)
    for zpath in args.zip:
        problems, count = check_zip(zpath, rules)
        print(f"provenance: {count} files in {os.path.basename(zpath)}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems:
            print("  FAIL " + p)
        failed = failed or bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
