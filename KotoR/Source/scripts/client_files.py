"""
Records the files the client writes into the game's Override folder when it connects, and takes them out again.

Several things the client does on every connect (the Jedi-trial suppressor, the shop price fixes, the New Companion templates and scripts, the tracker journal) write loose
files into Override. Each of those scripts calls start() before it writes and finish() after; this module keeps a list of the files that appeared (and the SHA-256 of each),
so that Uninstall and /ap_restore_all can remove exactly those files, and only while they are still the files that were written (a file someone has since replaced is left alone).

  client_files.py --restore [--game-dir PATH]     remove every recorded file, then the Override tables that have become identical to the game's own again

The tables (appearance.2da, baseitems.2da and the others) are edited cell by cell by more than one script, so they are not listed per file. Once the scripts that own those
edits have undone them, a table that is identical to the game's own, or that differs only in the Body/Head/Hands rows' denysubrace cells that New Companion sets, is removed.
"""
import contextlib
import hashlib
import json
import os
import sys

STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
STATE_PATH = os.path.join(STATE_DIR, "client_files.json")
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
TABLES = ("appearance", "baseitems", "portraits", "heads", "classes", "feat", "featgain", "skills", "spells")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _snapshot(override_dir):
    out = {}
    if os.path.isdir(override_dir):
        for name in os.listdir(override_dir):
            path = os.path.join(override_dir, name)
            if os.path.isfile(path):
                out[name.lower()] = _sha(path)
    return out


def _load():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE_PATH)


class Tracker:
    def __init__(self, group, game_dir):
        self.group = group
        self.override_dir = os.path.join(game_dir, "Override")
        self.before = _snapshot(self.override_dir)

    def finish(self):
        """Records the files that appeared since start(), and keeps the digest of the files already recorded current (a rerun may rewrite them)."""
        after = _snapshot(self.override_dir)
        state = _load()
        mine = state.setdefault(self.override_dir.lower(), {}).setdefault(self.group, {})
        for name, digest in after.items():
            if name not in self.before:
                mine[name] = digest                       # appeared during this run: ours
            elif name in mine and self.before[name] != digest:
                mine[name] = digest                       # we rewrote a file we already own; a file another script changed is left as it was recorded
        _save(state)
        return len(mine)


def start(group, game_dir):
    return Tracker(group, game_dir)


@contextlib.contextmanager
def tracked(group, game_dir):
    tracker = start(group, game_dir)
    try:
        yield tracker
    finally:
        tracker.finish()


def restore_group(game_dir, group):
    """Removes the files recorded for `group` that are still byte-for-byte what was written. Returns how many were removed."""
    override_dir = os.path.join(game_dir, "Override")
    state = _load()
    per_dir = state.get(override_dir.lower(), {})
    mine = per_dir.get(group, {})
    removed = 0
    kept = {}
    for name, digest in mine.items():
        path = os.path.join(override_dir, name)
        if not os.path.isfile(path):
            continue
        if _sha(path) == digest:
            os.remove(path)
            removed += 1
        else:
            kept[name] = digest
            print(f"  left {name}: it has been changed since it was written")
    if kept:
        per_dir[group] = kept
    else:
        per_dir.pop(group, None)
    if per_dir:
        state[override_dir.lower()] = per_dir
    else:
        state.pop(override_dir.lower(), None)
    _save(state)
    return removed


def restore_all(game_dir):
    state = _load()
    groups = sorted(state.get(os.path.join(game_dir, "Override").lower(), {}))
    return sum(restore_group(game_dir, g) for g in groups)


def _tolerated_baseitems_rows():
    """The baseitems.2da rows whose denysubrace cell New Companion edits (its labels are listed in generate_new_companion_assets.py)."""
    try:
        import generate_new_companion_assets as nc
        return set(nc.MALAK_RESTRICTED_GEAR_LABELS) | set(nc.OPEN_GEAR_LABELS)
    except Exception:
        return set()


def table_matches_game(over, vanilla, tolerated_rows=(), tolerated_column="denysubrace"):
    """True when the two 2DA tables hold the same cells, apart from `tolerated_column` in the rows whose label is in `tolerated_rows`."""
    if list(over.get_headers()) != list(vanilla.get_headers()) or over.get_height() != vanilla.get_height():
        return False
    for i in range(vanilla.get_height()):
        label = vanilla.get_label(i)
        for header in vanilla.get_headers():
            if over.get_cell(i, header) != vanilla.get_cell(i, header):
                if header == tolerated_column and label in tolerated_rows:
                    continue
                return False
    return True


def remove_vanilla_identical_tables(game_dir):
    """Removes the Override copies of the shared 2DA tables that no longer differ from the game's own. Returns the number removed."""
    try:
        from pykotor.extract.installation import Installation, SearchLocation
        from pykotor.resource.formats.twoda import read_2da
        from pykotor.resource.type import ResourceType
    except Exception:
        print("  pykotor is not available, so the Override tables were not checked")
        return 0
    override_dir = os.path.join(game_dir, "Override")
    installation = None
    removed = 0
    for name in TABLES:
        path = os.path.join(override_dir, f"{name}.2da")
        if not os.path.isfile(path):
            continue
        if installation is None:
            installation = Installation(game_dir)
        res = installation.resource(name, ResourceType.TwoDA, [SearchLocation.CHITIN])
        if res is None:
            continue
        with open(path, "rb") as f:
            over = read_2da(f.read())
        tolerated = _tolerated_baseitems_rows() if name == "baseitems" else ()
        if table_matches_game(over, read_2da(bytes(res.data)), tolerated):
            os.remove(path)
            removed += 1
        else:
            print(f"  left {name}.2da: it differs from the game's own in cells this mod does not set")
    return removed


def main():
    game_dir = DEFAULT_GAME_DIR
    for arg in sys.argv[1:]:
        if arg.startswith("--game-dir="):
            game_dir = arg.split("=", 1)[1].strip('"')
        elif arg == "--game-dir" and sys.argv.index(arg) + 1 < len(sys.argv):
            game_dir = sys.argv[sys.argv.index(arg) + 1].strip('"')
    if "--restore" not in sys.argv:
        sys.exit(__doc__)
    files = restore_all(game_dir)
    tables = remove_vanilla_identical_tables(game_dir)
    print(f"Removed {files + tables} file(s) the client wrote while connected ({files} recorded files, {tables} tables back to the game's own).")


if __name__ == "__main__":
    main()
