"""
Scans every compiled script across every module (RIM) AND every core/chitin
resource for real ACTION calls to a set of candidate NWScript routine IDs --
the same verification methodology already used for the companion-XP research
(exhaustive byte-pattern scan) and for scan_journal_values.py. Purpose: find
a routine ID with the smallest possible real-caller footprint, safe to
hijack for a new custom KSE_-style native (KSE_SetClassType /
KSE_SetCreatureField), without colliding with anything a real player script
might actually invoke.

ACTION instruction format (confirmed against scan_journal_values.py):
  05 00 <routine_id: u16 BE> <argcount: u8>

Candidates: every SWMG_ (swoop minigame) routine ID, since that whole
category is real-but-narrow (K1SE itself hijacked SWMG_SetSoundFrequency=684
for KSE_AdjustCreatureSkills) -- excluding 684 itself, already taken.

Output: prints a sorted table, fewest real callers first, plus which
scripts/modules call each one (so a "0 callers" result can be double
checked it isn't just a scan gap).
"""
import os
from collections import defaultdict
from pykotor.extract.installation import Installation
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
MOD_DIR = os.path.join(GAME_DIR, "modules")

# Every SWMG_ routine ID from nwscript.nss, excluding 684 (SWMG_SetSoundFrequency,
# already hijacked by K1SE for KSE_AdjustCreatureSkills).
CANDIDATE_IDS = [
    584, 588, 589, 594, 596, 600, 601, 602, 603, 604, 605, 606, 607, 608, 609,
    610, 611, 612, 613, 614, 615, 616, 617, 618, 619, 620, 621, 622, 623, 624,
    625, 626, 627, 628, 629, 630, 631, 632, 633, 634, 635, 636, 637, 638, 639,
    640, 641, 642, 643, 644, 645, 646, 647, 648, 649, 650, 651, 652, 653, 654,
    655, 656, 657, 658, 659, 660, 661, 662, 663, 664,
    683, 685, 686, 687, 688,
    717, 718,
]

PATTERNS = {rid: bytes([0x05, 0x00, (rid >> 8) & 0xFF, rid & 0xFF]) for rid in CANDIDATE_IDS}


def scan_ncs(data, source_name, counts, callers):
    for rid, pattern in PATTERNS.items():
        n = data.count(pattern)
        if n:
            counts[rid] += n
            callers[rid].append((source_name, n))


def main():
    counts = defaultdict(int)
    callers = defaultdict(list)
    scanned = 0

    for fname in sorted(os.listdir(MOD_DIR)):
        if not fname.lower().endswith(".rim"):
            continue
        try:
            r = read_rim(os.path.join(MOD_DIR, fname))
        except Exception:
            continue
        for res in r:
            if res.restype != ResourceType.NCS:
                continue
            scanned += 1
            scan_ncs(res.data, f"{fname}:{res.resref}", counts, callers)

    installation = Installation(GAME_DIR)
    core_scanned = 0
    for cres in installation.core_resources():
        if cres.restype() != ResourceType.NCS:
            continue
        try:
            data = cres.data()
        except Exception:
            continue
        core_scanned += 1
        scan_ncs(data, f"core:{cres.resname()}", counts, callers)

    print(f"scanned {scanned} module-RIM scripts + {core_scanned} core/chitin scripts")
    print(f"checked {len(CANDIDATE_IDS)} candidate SWMG_ routine IDs\n")

    for rid in CANDIDATE_IDS:
        n = counts.get(rid, 0)
        print(f"routine {rid}: {n} real call site(s)" + (f" -> {callers[rid]}" if n else ""))


if __name__ == "__main__":
    main()
