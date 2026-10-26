r"""
Builds the Unknown World story-gate dialogs (design: DEVELOPMENT_HISTORY.md section 17 (design record, gates U1 to U3)) as raw Override .dlg files.

Each gated dialog gets one new starter placed FIRST in its StartingList. The starter's condition script (ap_unk_u1 / u2 / u3,
sources extender/scripts_src/sg_ap_unk_u*.nss) returns TRUE only while the player holds too few Unknown World progression items; it then
plays one short embedded "not yet" line (no dialog.tlk change) and the conversation ends. With enough progression items the condition is
FALSE, the engine moves on to the original starters in their original order, and the original entries and replies are
byte-for-byte the vanilla ones: nothing is removed, reordered or renumbered, the new nodes are appended at the end.

  unk41_guide_dlg  (unk_m41ad)  U1, 1 progression item   the temple guide's ritual, where both the Elders' and The One's route end
  unk44_evilbast   (unk_m44ac)  U2, 2 progression items  the Bastila scene at the temple summit
  unk44_evilbast2  (unk_m44ac)  U2, 2 progression items  same scene, alternate copy (no caller was found in the game data; edited anyway)
  unk44_comp       (unk_m44ac)  U3, 3 progression items  the temple computer (shield and disruptor shutdown)
  dan14_juhani     (danm14ac)   Dantooine D2, 2 progression items  the Juhani confrontation (not an Unknown World gate; same technique)
  kas22_chorraw_02 (kas_m22ab)  Kashyyyk K3, 3 progression items  Chorrawl's walk to the throne room (same technique)

All five names exist in exactly one module, so an Override copy replaces only the intended dialog. The originals are read from
the game's module resources only (never from Override), so a previously patched copy can never be re-patched.

  python story_gate_dialogs_unknown.py [--game-dir=PATH] [--out=DIR]   -- build, verify, write <name>.dlg files into DIR
"""
import copy
import os
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import GFFList, read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")

U1_TEXT = "[The Rakatan guide will not begin the ritual yet. You need more Unknown World Progression items to continue.]"
U2_TEXT = "[This confrontation cannot begin yet. You need more Unknown World Progression items to continue.]"
D2_TEXT = "[This confrontation cannot begin yet. You need more Dantooine Progression items to continue.]"
D1_TEXT = "[Master Dorak will not guide you on the Jedi path yet. You need more Dantooine Progression items to continue.]"
M1_TEXT = "[Roland Wann will not discuss the mission yet. You need more Manaan Progression items to continue.]"
K3_TEXT = "[Chorrawl will not lead you to the throne room yet.]"   # the player then says the number needed (sg_ap_kas_k3x)
U3_TEXT = ("ACCESS DENIED\nAUTHORIZATION INCOMPLETE\n[You need more Unknown World Progression items to continue.]\n"
           "SYSTEM LOGGING OFF...")

# dialog name -> (module holding it, condition script, "not yet" text, source file of the condition script)
DIALOGS = {
    "unk41_guide_dlg": ("unk_m41ad", "ap_unk_u1", U1_TEXT, "sg_ap_unk_u1"),
    "unk44_evilbast": ("unk_m44ac", "ap_unk_u2", U2_TEXT, "sg_ap_unk_u2"),
    "unk44_evilbast2": ("unk_m44ac", "ap_unk_u2", U2_TEXT, "sg_ap_unk_u2"),
    "unk44_comp": ("unk_m44ac", "ap_unk_u3", U3_TEXT, "sg_ap_unk_u3"),
    # Dantooine D2, the Juhani confrontation (danm14ac only); same technique, kept here so one builder serves every starter-insert gate.
    "dan14_juhani": ("danm14ac", "ap_dan_d2", D2_TEXT, "sg_ap_dan_d2"),
    # Dantooine D1, Dorak's class and crystal conversation (danm13 only); without this he fell through to his ordinary greeting in silence.
    "dan13_dorak": ("danm13", "ap_dan_d1", D1_TEXT, "sg_ap_dan_d1"),
    # Manaan M1, Roland Wann's dialog (manm26ae only): the whole conversation waits, so none of his branches can start early.
    "man26_repdip": ("manm26ae", "ap_man_m1x", M1_TEXT, "sg_ap_man_m1x"),
    # Kashyyyk K3, Chorrawl on the Great Walkway (kas_m22ab only): his whole conversation, which ends with the walk into the throne room, waits.
    "kas22_chorraw_02": ("kas_m22ab", "ap_kas_k3x", K3_TEXT, "sg_ap_kas_k3x"),
}

def _plain_reply(r):
    return not str(r.get_resref("Script")) and not r.get_string("Quest") and len(r.get_list("AnimList")) == 0


def _plain_entry(e):
    return (len(e.get_list("RepliesList")) == 1 and not str(e.get_resref("Script")) and not e.get_string("Quest")
            and len(e.get_list("AnimList")) == 0 and not e.get_string("Speaker"))


def _pick_templates(entries, replies):
    """First plain entry (one reply link) and first plain ending reply of the dialog; copied for the new nodes so every
    field has the shape the engine expects for that dialog (computer dialogs differ from cinematic ones)."""
    entry = next(i for i, e in enumerate(entries) if _plain_entry(e))
    plain = [i for i, r in enumerate(replies) if _plain_reply(r)]
    ending = [i for i in plain if len(replies[i].get_list("EntriesList")) == 0]
    return entry, (ending or plain)[0]


def _read_original(inst, name):
    module, _cond, _text, _src = DIALOGS[name]
    res = inst.resource(name, ResourceType.DLG, [SearchLocation.MODULES], module_root=module)
    if res is None:
        raise RuntimeError(f"{name}.dlg not found in {module}_s.rim")
    path = str(res.filepath).lower().replace("\\", "/")
    if "/modules/" not in path:
        raise RuntimeError(f"{name}.dlg did not come from the game's modules: {res.filepath}")
    return read_gff(res.data)


def _clean_plain(struct):
    """Turns a copied node into a bare line: no sound, animation, script or journal entry."""
    struct.set_string("Speaker", "") if struct.exists("Speaker") else None
    struct.set_list("AnimList", GFFList())
    struct.set_resref("VO_ResRef", ResRef.from_blank())
    struct.set_resref("Sound", ResRef.from_blank())
    struct.set_resref("Script", ResRef.from_blank())
    struct.set_string("Quest", "")
    struct.set_int32("PlotIndex", -1)
    if struct.exists("QuestEntry"):
        struct.remove("QuestEntry")
    if struct.exists("SoundExists"):
        struct.set_uint8("SoundExists", 0)


def build_one(inst, name):
    module, cond, text, _src = DIALOGS[name]
    gff = _read_original(inst, name)
    root = gff.root
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")
    starters = root.get_list("StartingList")
    if any(str(s.get_resref("Active")).lower() == cond for s in starters):
        raise RuntimeError(f"{name} already carries {cond}")
    tpl_entry, tpl_reply = _pick_templates(entries, replies)

    new_reply = copy.deepcopy(replies[tpl_reply])
    new_reply.set_list("EntriesList", GFFList())  # the new reply ends the conversation
    _clean_plain(new_reply)
    new_reply.set_locstring("Text", LocalizedString.from_english(""))
    new_reply.struct_id = len(replies)
    replies.append(new_reply)

    new_entry = copy.deepcopy(entries[tpl_entry])
    links = new_entry.get_list("RepliesList")
    assert len(links) == 1, "template entry must have exactly one reply link"
    _clean_plain(new_entry)
    new_entry.set_locstring("Text", LocalizedString.from_english(text))
    links[0].set_uint32("Index", len(replies) - 1)
    links[0].set_resref("Active", ResRef.from_blank())
    new_entry.set_list("RepliesList", links)
    new_entry.struct_id = len(entries)
    entries.append(new_entry)

    starter = copy.deepcopy(starters[0])
    starter.set_uint32("Index", len(entries) - 1)
    starter.set_resref("Active", ResRef(cond))
    starters.insert(0, starter)
    for position, s in enumerate(starters):  # starter struct ids are their positions
        s.struct_id = position

    root.set_list("EntryList", entries)
    root.set_list("ReplyList", replies)
    root.set_list("StartingList", starters)
    return gff


def _to_bytes(gff):
    data = bytearray()
    write_gff(gff, data, ResourceType.DLG)
    return bytes(data)


def build(game_dir):
    """{"unk41_guide_dlg.dlg": bytes, ...} computed from the original dialogs in the game's module resources."""
    inst = Installation(game_dir)
    return {f"{name}.dlg": _to_bytes(build_one(inst, name)) for name in DIALOGS}


# ---------------------------------------------------------------------------------------------------------------------
# Verification: re-read the output and walk each graph.
# ---------------------------------------------------------------------------------------------------------------------

def _dump(value):
    """Nested plain-Python form of a GFF value, for exact node comparison."""
    if hasattr(value, "_fields"):
        return {k: _dump(f.value()) for k, f in sorted(value._fields.items())}
    if isinstance(value, GFFList):
        return [_dump(s) for s in value]
    if isinstance(value, LocalizedString):
        return (value.stringref, tuple(sorted((int(k), v) for k, v in value)))
    return repr(value)


def _walk(root, start_indices):
    """Entry and reply indexes reachable from the given starter entries, treating every condition as possibly true."""
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")
    seen_e, seen_r = set(), set()
    todo = [("E", i) for i in start_indices]
    while todo:
        kind, i = todo.pop()
        if kind == "E":
            if i in seen_e:
                continue
            seen_e.add(i)
            todo += [("R", l.get_uint32("Index")) for l in entries[i].get_list("RepliesList")]
        else:
            if i in seen_r:
                continue
            seen_r.add(i)
            todo += [("E", l.get_uint32("Index")) for l in replies[i].get_list("EntriesList")]
    return seen_e, seen_r


def verify(game_dir, built=None):
    """Raises AssertionError on the first discrepancy; returns a list of human-readable proof lines."""
    inst = Installation(game_dir)
    built = built or build(game_dir)
    lines = []
    for name, (module, cond, text, src) in DIALOGS.items():
        assert os.path.isfile(os.path.join(SRC_DIR, src + ".nss")), f"missing condition source {src}.nss"
        assert len(cond) <= 16, cond
        orig = _read_original(inst, name).root
        new = read_gff(built[f"{name}.dlg"]).root
        oe, orr, os_ = orig.get_list("EntryList"), orig.get_list("ReplyList"), orig.get_list("StartingList")
        ne, nr, ns = new.get_list("EntryList"), new.get_list("ReplyList"), new.get_list("StartingList")

        # 1. Nothing vanilla moved or changed: node lists are the originals plus exactly one appended node each.
        assert len(ne) == len(oe) + 1 and len(nr) == len(orr) + 1 and len(ns) == len(os_) + 1
        assert [_dump(x) for x in ne[:len(oe)]] == [_dump(x) for x in oe], f"{name}: an original entry changed"
        assert [_dump(x) for x in nr[:len(orr)]] == [_dump(x) for x in orr], f"{name}: an original reply changed"
        orig_fields = {k: _dump(f.value()) for k, f in orig._fields.items() if k not in ("EntryList", "ReplyList", "StartingList")}
        new_fields = {k: _dump(f.value()) for k, f in new._fields.items() if k not in ("EntryList", "ReplyList", "StartingList")}
        assert orig_fields == new_fields, f"{name}: a dialog-level field changed"

        # 2. Starters: the new one first, then the original ones with identical targets and conditions, in order.
        first = ns[0]
        assert str(first.get_resref("Active")) == cond and first.get_uint32("Index") == len(ne) - 1
        assert [(s.get_uint32("Index"), str(s.get_resref("Active"))) for s in list(ns)[1:]] == \
               [(s.get_uint32("Index"), str(s.get_resref("Active"))) for s in os_], f"{name}: original starters differ"
        assert [s.struct_id for s in ns] == list(range(len(ns)))

        # 3. Gate OPEN (new starter never taken): reachable graph == the vanilla graph, node for node.
        open_e, open_r = _walk(new, [s.get_uint32("Index") for s in list(ns)[1:]])
        van_e, van_r = _walk(orig, [s.get_uint32("Index") for s in os_])
        assert (open_e, open_r) == (van_e, van_r), f"{name}: open-gate graph differs from vanilla"
        assert len(ne) - 1 not in open_e and len(nr) - 1 not in open_r

        # 4. Gate CLOSED (new starter taken): exactly the new entry and the new reply, then the conversation ends.
        closed_e, closed_r = _walk(new, [first.get_uint32("Index")])
        assert closed_e == {len(ne) - 1} and closed_r == {len(nr) - 1}, f"{name}: closed-gate walk escapes the new nodes"
        entry, reply = ne[len(ne) - 1], nr[len(nr) - 1]
        assert len(reply.get_list("EntriesList")) == 0
        for node in (entry, reply):
            assert str(node.get_resref("Script")) == "" and node.get_string("Quest") == ""
            assert not node.exists("QuestEntry") and len(node.get_list("AnimList")) == 0
        assert entry.get_locstring("Text").stringref == -1
        lines.append(f"{name}: open == vanilla ({len(van_e)} entries, {len(van_r)} replies reachable); closed -> E{len(ne) - 1} -> R{len(nr) - 1} -> end")
    return lines


def main():
    game_dir, out_dir = DEFAULT_GAME_DIR, DEFAULT_OUT_DIR
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            game_dir = a.split("=", 1)[1]
        elif a.startswith("--out="):
            out_dir = a.split("=", 1)[1]
    built = build(game_dir)
    for line in verify(game_dir, built):
        print("OK  " + line)
    os.makedirs(out_dir, exist_ok=True)
    for fname, data in built.items():
        with open(os.path.join(out_dir, fname), "wb") as f:
            f.write(data)
        print(f"wrote {os.path.join(out_dir, fname)} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
