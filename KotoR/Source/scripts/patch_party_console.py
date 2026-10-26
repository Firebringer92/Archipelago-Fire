"""
Gives a player's game the spells.2da row the Party Console item needs.

The Party Console (ap_partycon_a, the item "Party Console") is a usable item whose CastSpell property names row 132 of spells.2da; that row's impact script is
ap_party_console, which opens the party selection dialog. Vanilla spells.2da has rows 0 to 131, so row 132 does not exist on a clean install and has to be
appended: a copy of the vanilla usable plot spell in row 109 (it targets the user and runs a script when its item is used) with the label and script changed.
generate_party_console.py makes the same row on the developer's machine; this script is the player-side version, run on every Connect (it is safe to repeat).

  apply (default)   adds row 132 if spells.2da has none. Writes Override\\spells.2da (a new file, so the game has to be started after this runs).
  --restore         takes the file out again if this script created it and nothing else has changed it (Uninstall.bat runs this).

An Override\\spells.2da that already has a row 132 is left alone when that row is ours (label starts with "AP_") and refused otherwise: another mod's row is not ours to
change, and the Party Console then does nothing.
"""
import argparse
import json
import os
import sys

SPELL_ROW = 132
PLOT_SPELL_ROW = 109
LABEL = "AP_PARTY_CONSOLE"
IMPACT_SCRIPT = "ap_party_console"
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
STATE_PATH = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP", "partycon_spells.json")


def ensure_row(table) -> str:
    """Makes row SPELL_ROW the Party Console's. Returns "added", "updated" (our row, changed), "present" (already right) or "foreign" (not ours, untouched).
    Raises ValueError if the table is not the shape this expects."""
    height = table.get_height()
    if height < SPELL_ROW:
        raise ValueError(f"spells.2da has {height} rows; the Party Console row {SPELL_ROW} would not follow the last one")
    if height == SPELL_ROW:
        row = table.add_row(str(SPELL_ROW))
        status = "added"
    else:
        label = table.get_cell(SPELL_ROW, "label")
        if not label.upper().startswith("AP_"):
            return "foreign"
        row = SPELL_ROW
        status = "present" if (label == LABEL and table.get_cell(SPELL_ROW, "impactscript") == IMPACT_SCRIPT) else "updated"
    if status != "present":
        for header in table.get_headers():
            if header in ("label", "impactscript"):
                continue
            table.set_cell(row, header, table.get_cell(PLOT_SPELL_ROW, header))
        table.set_cell(row, "label", LABEL)
        table.set_cell(row, "impactscript", IMPACT_SCRIPT)
    return status


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


def apply(game_dir: str) -> str:
    from pykotor.extract.installation import Installation, SearchLocation
    from pykotor.resource.formats.twoda import read_2da, write_2da
    from pykotor.resource.type import ResourceType

    override = os.path.join(game_dir, "Override")
    path = os.path.join(override, "spells.2da")
    existed = os.path.isfile(path)
    if existed:
        with open(path, "rb") as f:
            table = read_2da(f.read())
    else:
        table = read_2da(Installation(game_dir).resource("spells", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)
    status = ensure_row(table)
    if status == "foreign":
        return f"spells.2da row {SPELL_ROW} belongs to something else: the Party Console item will do nothing (left alone)."
    if status == "present":
        return f"spells.2da row {SPELL_ROW} is already the Party Console's."
    os.makedirs(override, exist_ok=True)
    out = bytearray()
    write_2da(table, out)
    with open(path, "wb") as f:
        f.write(bytes(out))
    state = _load_state()
    if status == "added" and not existed:
        state[game_dir.lower()] = {"created": True}
        _save_state(state)
    return f"spells.2da row {SPELL_ROW} {status} for the Party Console ({path})" + ("; the game must be started after this" if not existed else "")


def restore(game_dir: str) -> str:
    state = _load_state()
    entry = state.get(game_dir.lower())
    path = os.path.join(game_dir, "Override", "spells.2da")
    if not (entry and entry.get("created")):
        return "Party Console spells.2da row: not created by this installer, nothing to undo."
    if os.path.isfile(path):
        from pykotor.resource.formats.twoda import read_2da
        with open(path, "rb") as f:
            table = read_2da(f.read())
        if table.get_height() == SPELL_ROW + 1 and table.get_cell(SPELL_ROW, "label") == LABEL:
            os.remove(path)
            msg = "Party Console spells.2da removed."
        else:
            msg = "Override\\spells.2da has been changed by something else since; left in place."
    else:
        msg = "Party Console spells.2da was already gone."
    state.pop(game_dir.lower(), None)
    _save_state(state)
    return msg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()
    game_dir = args.game_dir.strip().strip('"').rstrip("\\/ ") or args.game_dir
    try:
        print(restore(game_dir) if args.restore else apply(game_dir))
    except Exception as e:
        print(f"patch_party_console.py failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
