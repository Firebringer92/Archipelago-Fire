"""Rename four TSL prestige classes in dialog.tlk (display text only).

    Jedi Weapon Master -> Jedi Vanguard      Jedi Watchman -> Jedi Shadow
    Jedi Master        -> Jedi Sage          Sith Lord     -> Sith Sorcerer

Usage:
    python -I patch_prestige_names.py --check    round-trip the file, build the change table, write the
                                                 change log; touches nothing in the game folder
    python -I patch_prestige_names.py --apply    back up dialog.tlk once (dialog.tlk.orig), then write a
                                                 patched dialog.tlk built from the pristine copy
    python -I patch_prestige_names.py --restore  copy dialog.tlk.orig back over dialog.tlk

Only the strings listed in SCOPE change. Every other phrase in the file (NPC speech, item names, journal
text, lore) keeps the old wording. See docs/PRESTIGE_RENAME_PLAN.md.
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsl_data as T  # noqa: E402  (also silences pykotor logging)
from pykotor.resource.formats.tlk import read_tlk, write_tlk  # noqa: E402

TLK = os.path.join(T.GAME, "dialog.tlk")
ORIG = TLK + ".orig"
LOG = r"C:\Users\User\KOTOR2 AP\research\prestige_rename_changes.txt"

# Whole-string replacements for the four class names themselves.
NAME_STRINGS = {47998: "Jedi Vanguard", 47999: "Jedi Sage", 48000: "Jedi Shadow", 48002: "Sith Sorcerer"}

# Strings whose class references are swapped by the phrase rules below. Every entry was read by hand: it
# is a class tip, a prerequisite line, a class-trait description or one of Kreia's prestige-menu lines.
SCOPE = set()
SCOPE.update(range(38062, 38066))      # class tips
SCOPE.update(range(38070, 38073))
SCOPE.update([32279, 38671, 38672, 48097, 48098])
SCOPE.update(range(42319, 42325))      # Sneak Attack II-VII
SCOPE.update(range(48106, 48113))      # Crush Opposition I-IV, Sith Lord trait
SCOPE.update(range(48128, 48131))      # Weapon Master prerequisites
SCOPE.update(range(48134, 48137))
SCOPE.update(range(48142, 48149))      # Inspire Followers, Jedi Master trait
SCOPE.update([48150])                  # Deflect (with its typo)
SCOPE.update(range(48154, 48157))      # Inner Strength
SCOPE.update(range(48160, 48163))      # Increase Melee Damage
SCOPE.update([48415])                  # Crush Opposition V
SCOPE.update(range(48479, 48482))      # Force Camouflage
SCOPE.update(range(48506, 48512))      # Inspire Followers (Force power form)
SCOPE.update([118781, 118786, 118788, 118789, 118841, 118845, 118846, 118847])  # Kreia, prestige menu

# One source line is fixed outright (the original has a typo).
FULL_REPLACE = {
    48150: None,  # filled in below from the pristine text
}

# Ordered phrase rules: longest and most specific first.
RULES = [
    (r"Jedi Weapon Masters", "Jedi Vanguards"),
    (r"Jedi Weapon Master", "Jedi Vanguard"),
    (r"Jedi Weaponmaster", "Jedi Vanguard"),
    (r"Weapon Masters", "Vanguards"),
    (r"Weapon Master", "Vanguard"),
    (r"weapon masters", "Vanguards"),
    (r"Jedi Watchmen", "Jedi Shadows"),
    (r"Jedi Watchman", "Jedi Shadow"),
    (r"Jedi Masters", "Jedi Sages"),
    (r"Jedi Master", "Jedi Sage"),
    (r"Sith Lords", "Sith Sorcerers"),
    (r"Sith Lord", "Sith Sorcerer"),
]


def patched_text(strref, old):
    if strref in NAME_STRINGS:
        return NAME_STRINGS[strref]
    if strref not in SCOPE:
        return old
    new = old
    if strref == 48150:
        new = new.replace("A Weapon Master with has the incredible skill to deflecting blaster bolts.",
                          "A Vanguard has the incredible skill of deflecting blaster bolts.")
    for pat, rep in RULES:
        new = re.sub(pat, rep, new)
    return new


def entries_equal(a, b):
    return (a.text == b.text and str(a.voiceover) == str(b.voiceover))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode == "--restore":
        if not os.path.exists(ORIG):
            sys.exit("no dialog.tlk.orig to restore from")
        shutil.copy2(ORIG, TLK)
        print("restored dialog.tlk from dialog.tlk.orig")
        return

    # Always build from the pristine copy.
    src = ORIG if os.path.exists(ORIG) else TLK
    print("source:", src)
    tlk = read_tlk(src)
    n = len(tlk)
    print("entries:", n)

    # Round trip: write the untouched file to a scratch path and compare every entry.
    scratch = os.path.join(os.environ.get("TEMP", "."), "dialog_roundtrip.tlk")
    write_tlk(tlk, scratch)
    again = read_tlk(scratch)
    bad = [i for i in range(n) if not entries_equal(tlk[i], again[i])]
    print("round trip:", "OK, %d entries identical" % n if len(again) == n and not bad
          else "FAILED (len %d vs %d, %d differ)" % (n, len(again), len(bad)))
    if len(again) != n or bad:
        sys.exit(1)

    changes = []
    for i in sorted(SCOPE | set(NAME_STRINGS)):
        old = tlk[i].text
        new = patched_text(i, old)
        if new != old:
            changes.append((i, old, new))
    missing = [i for i in sorted(SCOPE | set(NAME_STRINGS)) if patched_text(i, tlk[i].text) == tlk[i].text]
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("Prestige class rename: %d strings changed in dialog.tlk\n\n" % len(changes))
        for i, old, new in changes:
            f.write("[%d]\n  old: %r\n  new: %r\n\n" % (i, old, new))
        if missing:
            f.write("In scope but unchanged: %s\n" % missing)
    print("changes:", len(changes), "| in scope but unchanged:", missing, "| log:", LOG)

    # No old class name may survive in scope.
    left = [i for i in SCOPE | set(NAME_STRINGS)
            if re.search(r"Weapon ?[Mm]aster|Watchm[ae]n|Jedi Master|Sith Lord", patched_text(i, tlk[i].text))]
    print("old names left in scope:", left)
    if mode != "--apply":
        print("check only: nothing written to the game folder")
        return

    if not os.path.exists(ORIG):
        shutil.copy2(TLK, ORIG)
        print("backup created:", ORIG)
    for i, old, new in changes:
        tlk[i].text = new
    write_tlk(tlk, TLK)

    check = read_tlk(TLK)
    pristine = read_tlk(ORIG)
    changed = [i for i in range(len(pristine)) if not entries_equal(pristine[i], check[i])]
    expected = [c[0] for c in changes]
    print("patched file entries:", len(check), "| entries that differ from the pristine copy:", len(changed),
          "| exactly the intended set:", changed == expected)


if __name__ == "__main__":
    main()
