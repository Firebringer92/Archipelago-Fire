"""The Master gates' dialogue patch: the three Masters' conversations are pointed at the seed's own script for the "+1 on the Jedi count" nodes.

Each Master's conversation (zezkaiel in 303NAR, kavar in 506OND, vrook in 602DAN) adds 1 to the global 000_Jedi_Found at a few nodes through the game's shared script
a_global_inc. Those nodes are rewritten in the module's conversation archive (<module>_dlg.erf, edited in place after a backup like the other module files,
client/k2_modules.py) to run ap_jedi_inc instead (nss/ap_jedi_inc.nss), which does the same unless the Master's gate is still closed, in which case the +1 is held
and remembered until the tokens arrive (nss/k2ap_master.nss). The conversation itself is never stopped: a Master is spent after it, and the Onderon palace does not
let the player leave. Nothing but these nodes is touched, and the game's shared script is left as it is.
"""
import typing

SHARED_SCRIPT = "a_global_inc"
OUR_SCRIPT = "ap_jedi_inc"
COUNT_GLOBAL = "000_Jedi_Found"
# module -> (conversation, gate)
MASTERS = {"303NAR": ("zezkaiel", "NAR3"), "506OND": ("kavar", "DXN3"), "602DAN": ("vrook", "DAN2")}


def point_nodes_at_ours(root) -> int:
    """Rewrites the Jedi-count nodes of one conversation (a GFF root). Returns how many were changed."""
    from pykotor.common.misc import ResRef
    changed = 0
    for lst in ("EntryList", "ReplyList"):
        if not root.exists(lst):
            continue
        for node in root.get_list(lst):
            for field in ("Script", "Script2"):
                if (node.exists(field) and str(node.get_resref(field)).lower() == SHARED_SCRIPT
                        and node.exists("ActionParamStrA") and node.get_string("ActionParamStrA") == COUNT_GLOBAL):
                    node.set_resref(field, ResRef(OUR_SCRIPT))
                    changed += 1
    return changed


def master_dialogue_files(store, active_gates: typing.Collection[str]) -> typing.Tuple[int, typing.List[str]]:
    """Patches the conversations of the Masters whose gate is active. Returns (nodes changed, problems)."""
    total = 0
    problems: typing.List[str] = []
    for module, (conversation, gate) in sorted(MASTERS.items()):
        if gate not in active_gates:
            continue
        if not store.exists(module, "_dlg"):
            problems.append("the Master gates: %s_dlg.erf was not found, the %s gate cannot hold the Jedi count" % (module, gate))
            continue
        count = [0]

        def change(root, count=count):
            count[0] = point_nodes_at_ours(root)
            return count[0] > 0
        try:
            if not store.edit_gff(module, conversation, "dlg", change, "_dlg"):
                problems.append("the Master gates: %s has no Jedi-count node in %s_dlg.erf, the %s gate cannot hold the Jedi count" % (conversation, module, gate))
        except Exception as e:
            problems.append("the Master gates: %s_dlg.erf could not be changed (%s)" % (module, e))
            continue
        total += count[0]
    return total, problems
