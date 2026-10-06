"""
One-off migration for an existing install whose _mapping.json predates
per-variant OnEnter originals (see generate_area_trampolines.py).

Several areas share one OnEnter resref while each module's copy is a
DIFFERENT script (korr_m34aa/korr_m39aa, sta_m45aa/ac/ad). The old mapping
held one preserved original per resref and matched the area by module name
instead of the ARE tag, so the wrong script ran in all but the first area and
those areas never reported their area check. This preserves each distinct
original under apo_NNNN / apo_NNNNb / apo_NNNNc, records every area's real ARE
tag and its own preserved original in _mapping.json, and leaves every other
mapping entry alone. Run generate_trampoline_batch.py --areas=<those areas>
afterwards to rebuild their trampolines.

Usage: python migrate_shared_onenters.py [--game-dir=<path>]
"""
import json
import os
import sys
from collections import defaultdict

from pykotor.resource.formats.gff import read_gff
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
for a in sys.argv[1:]:
    if a.startswith("--game-dir="):
        GAME = a.split("=", 1)[1]
MOD_DIR = os.path.join(GAME, "Modules")
OVERRIDE = os.path.join(GAME, "Override")
MAPPING = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_mapping.json")


def module_script(module, resref):
    for suffix in ("_s", ""):
        path = os.path.join(MOD_DIR, f"{module}{suffix}.rim")
        if os.path.exists(path):
            for res in read_rim(path):
                if res.restype == ResourceType.NCS and res.resref.get().lower() == resref.lower():
                    return bytes(res.data)
    raise RuntimeError(f"{resref}.ncs not found in {module}")


def area_tag(module):
    for res in read_rim(os.path.join(MOD_DIR, f"{module}.rim")):
        if res.restype == ResourceType.ARE:
            root = read_gff(res.data).root
            return root.get_string("Tag") if root.exists("Tag") else module
    raise RuntimeError(f"no ARE in {module}")


def main():
    with open(MAPPING, encoding="utf-8") as f:
        mapping = json.load(f)
    by_onenter = defaultdict(list)
    for base, info in mapping.items():
        by_onenter[info["onenter"]].append(base)

    changed = []
    for onenter, bases in by_onenter.items():
        if len(bases) < 2:
            continue
        base_name = mapping[bases[0]]["renamed"].rstrip("abcdefgh")
        variants = {}
        for base in bases:
            data = module_script(base, onenter)
            if data not in variants:
                suffix = "" if not variants else chr(ord("a") + len(variants))
                name = f"{base_name}{suffix}"
                variants[data] = name
                with open(os.path.join(OVERRIDE, f"{name}.ncs"), "wb") as f:
                    f.write(data)
            mapping[base]["renamed"] = variants[data]
            mapping[base]["tag"] = area_tag(base)
        if len(variants) > 1:
            changed.append(onenter)
            print(f"{onenter}: {len(variants)} distinct scripts -> "
                  + ", ".join(f"{b}={mapping[b]['renamed']} (tag {mapping[b]['tag']!r})" for b in bases))
        else:
            print(f"{onenter}: all areas share one script, tags recorded only")

    with open(MAPPING, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    print("updated", MAPPING)
    print("rebuild trampolines for:", ",".join(b for o in changed for b in by_onenter[o]))


if __name__ == "__main__":
    main()
