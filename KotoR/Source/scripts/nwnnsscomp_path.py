r"""
Shared nwnnsscomp.exe path resolution -- used by every script in this
folder that shells out to the NWScript compiler (generate_poll_shared.py,
generate_makejedi_suppressor.py, generate_trampoline_batch.py,
patch_item_suppression.py, generate_companion_suppressors.py,
generate_store_suppressors.py). Extracted 2026-09-08 when the exact same
NWNNSSCOMP = r"C:\...\KotOR Scripting Tool\nwnnsscomp.exe" hardcoded
literal was found duplicated identically across all 6 files.

Why this changed: the new tester installer now bundles nwnnsscomp.exe
directly into the game folder (redistribution permission confirmed
directly with the tool's dev, 2026-09-08 -- see FutureDesign.md's Q1,
previously blocked on unclear rights). So resolution now has to check
there FIRST, falling back to the old standalone KotOR Scripting Tool
install for a dev machine (or any tester who installed that separately
before this existed). Pulled into one shared module rather than fixed in
each of the 6 files individually so a future change to where the
installer places it only needs one edit, not six.

Does its own lightweight --game-dir sys.argv scan rather than accepting
game_dir as a parameter, since where each of those 6 files' own
"current game dir" is available (and how/when) differs: some resolve
it via real argparse, one via a lightweight sys.argv pre-parse, others
don't expose a reusable game-dir variable at module scope at all. This
lets every caller just do `NWNNSSCOMP = resolve_nwnnsscomp()` at module
level with zero ordering dependency on that file's own argument parsing.
"""
import os
import sys

_STANDALONE_TOOL_DEFAULT = r"C:\Program Files (x86)\KotOR Scripting Tool\nwnnsscomp.exe"
_STEAM_DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def resolve_nwnnsscomp() -> str:
    game_dir = _STEAM_DEFAULT_GAME_DIR
    for i, a in enumerate(sys.argv):
        if a == "--game-dir" and i + 1 < len(sys.argv):
            game_dir = sys.argv[i + 1]
            break
        if a.startswith("--game-dir="):
            game_dir = a.split("=", 1)[1]
            break
    bundled = os.path.join(game_dir, "nwnnsscomp.exe")
    return bundled if os.path.exists(bundled) else _STANDALONE_TOOL_DEFAULT
