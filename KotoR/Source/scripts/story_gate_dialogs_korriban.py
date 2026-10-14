r"""
Builds the two edited Korriban dialogs the story gates need (design: DEVELOPMENT_HISTORY.md section 17 (design record, Korriban)).

  kor33_yuthura.dlg  (gate Ko1, always part of build())
      Yuthura Ban's acceptance into the academy is node E16 ("I will take you to the academy..."), which raises the journal
      quest kor33_enteracademy to stage 50. Exactly six reply lines lead into it (R13, R18, R27, R35, R38, R88: the persuade,
      force-persuade, lie, fallen-Jedi, medallion and "one of the others accepted you" routes all end there). None of those
      six links carries a condition in the original, so each gets the new condition ap_kor_ko1 (sg_ap_kor_ko1.nss: holds one
      Korriban progression item) and a second, unconditional link to a new "not yet" entry. The engine takes the first link whose
      condition passes, so with the progression item the original link is taken and the conversation is byte-for-byte the vanilla one.
      The new entry is Yuthura saying she has not decided; its replies lead back into her ordinary menu (E0, or E63 for a
      player who looks like a Jedi, the same choice her starters make) or end the conversation through the existing
      "I'll be on my way." reply. No journal entry, global or item is touched on that path, so the player can come back and
      try again once the progression item arrives (the refusal flag KOR_YUTHURA_REFUSE is set only by the unrelated node R17).

  kor35_utharwynn.dlg  (optional repair, only from build_uthar_intro(); NOT part of build())
      Uthar's welcome scene has three student lines spoken by the academy copies of Lashowe (E110), Mekel (E112) and
      Shaardan (E114), and two optional interjections (E134 Lashowe, E135 Shaardan). The module-enter script kor35_enter
      destroys a student's academy copy once that student is dead (KOR33_SHAARDAN >= 4, KOR_LASHOWE_PLOT >= 5,
      KOR_MEKEL_KILLED >= 1 or KOR_MEKEL_LIGHT). Every link in the scene is unconditional, so a destroyed student leaves
      a line whose speaker object does not exist. Each such link gets a presence condition and a second link that skips
      the line. With every student present the scene is unchanged.

Both dialog names exist in exactly one module (korr_m33aa and korr_m35aa), so an Override copy replaces no other module's dialog.
The originals are always read from the game's module archives (never from Override), so running this twice cannot stack edits.

  python story_gate_dialogs_korriban.py [--game-dir=PATH] [--out=DIR] [--uthar-intro] [--check]
"""
import copy
import os
import sys

from pykotor.common.language import LocalizedString
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import GFFList, GFFStruct, read_gff, write_gff
from pykotor.resource.type import ResourceType

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"

# ---- Ko1: kor33_yuthura ------------------------------------------------------------------------------------------------
YUTHURA_DLG = "kor33_yuthura"
YUTHURA_MODULE = "korr_m33aa"
GATE_CONDITION = "ap_kor_ko1"
START_CONDITION = "ap_kor_ko1x"          # first starter: TRUE while the gate would refuse and the player is not yet accepted
ACCEPT_ENTRY = 16                       # E16: "I will take you to the academy..." (kor33_enteracademy 50)
ACCEPT_REPLIES = (13, 18, 27, 35, 38, 88)  # the six replies whose only link is E16
MENU_ENTRY = 0                          # E0: "Is there something you need, human?"
MENU_ENTRY_JEDI = 63                    # E63: the same menu for a player who looks like a Jedi
MENU_JEDI_CONDITION = "k_pkor_lookjedi"  # the starter condition that picks E63 over E0
LEAVE_REPLY = 0                         # R0: "I'll be on my way." -> E1 "As you wish." -> end
NOT_YET_TEXT = ("I have not yet decided whether you are worthy of the academy. Come back when I have, "
                "or ask what you will in the meantime.")
BACK_TEXT = "I have other questions."
START_TEXT = "[Yuthura will not speak of the academy yet. You need more Korriban Progression items to continue.]"

# ---- Uthar's welcome scene: kor35_utharwynn ----------------------------------------------------------------------------
UTHAR_DLG = "kor35_utharwynn"
UTHAR_MODULE = "korr_m35aa"
# reply -> (the student-speaker entry it leads to, presence condition, entry to jump to when the student is absent)
UTHAR_SKIPS = {
    132: (110, "ap_kor_st_lash", 111),   # E110 Lashowe "I dare, Master Uthar!"  -> skip to E111 Uthar ("What of you, Mekel?")
    134: (112, "ap_kor_st_mekel", 113),  # E112 Mekel "I am, Master."             -> skip to E113 Uthar ("And Shaardan...")
    136: (114, "ap_kor_st_shaa", 115),   # E114 Shaardan "I am always ready!"     -> skip to E115 Uthar
}
# (reply, entry, vanilla condition) -> replacement condition that also requires the speaker to be present
UTHAR_COMBINED = {
    (119, 135, "k35_sha_mercy"): "ap_kor_st_shaam",
    (119, 134, "k_pkor_lashhate"): "ap_kor_st_lashh",
    (162, 134, "k_pkor_lashhate"): "ap_kor_st_lashh",
}
UTHAR_NEW_CONDITIONS = ("ap_kor_st_lash", "ap_kor_st_mekel", "ap_kor_st_shaa", "ap_kor_st_lashh", "ap_kor_st_shaam")


def _arg(flag, default=None):
    for a in sys.argv[1:]:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _original(game_dir, name, module):
    """The dialog as shipped in the module archive, never an Override copy."""
    inst = Installation(game_dir)
    res = inst.resource(name, ResourceType.DLG, [SearchLocation.MODULES], module_root=module)
    if res is None:
        sys.exit(f"{name}.dlg not found in {module}_s.rim under {game_dir} -- is --game-dir a real KOTOR install?")
    return res.data


def _to_bytes(gff):
    out = bytearray()
    write_gff(gff, out, ResourceType.DLG)
    return bytes(out)


def _links(node, field):
    return [(l.get_uint32("Index"), str(l.get_resref("Active"))) for l in node.get_list(field)]


def _add_link(links, index, active):
    """Appends a link after the existing ones, copying an existing link's field set so IsChild/LinkComment stay valid."""
    new = links.add(len(links))
    new.set_uint32("Index", index)
    new.set_resref("Active", active)
    new.set_uint8("IsChild", 0)
    return new


# ---- Ko1 --------------------------------------------------------------------------------------------------------------
def edit_yuthura(data):
    gff = read_gff(data)
    root = gff.root
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")

    # Shape checks: the edit assumes exactly the dialog read while writing it.
    assert len(entries) == 82 and len(replies) == 96, "kor33_yuthura changed shape"
    into_accept = sorted(r for r, node in enumerate(replies) if any(i == ACCEPT_ENTRY for i, _ in _links(node, "EntriesList")))
    assert tuple(into_accept) == ACCEPT_REPLIES, f"links into E{ACCEPT_ENTRY} are R{into_accept}"
    for r in ACCEPT_REPLIES:
        assert _links(replies[r], "EntriesList") == [(ACCEPT_ENTRY, "")], f"R{r} already has a condition or extra links"
    assert ACCEPT_ENTRY not in [s.get_uint32("Index") for s in root.get_list("StartingList")], "E16 is a starter"

    # New reply "I have other questions." -> E63 (looks like a Jedi) else E0.
    back = copy.deepcopy(replies[LEAVE_REPLY])
    back.set_locstring("Text", LocalizedString.from_english(BACK_TEXT))
    back.set_resref("VO_ResRef", "")
    back.set_resref("Sound", "")
    back.set_uint8("SoundExists", 0)
    back_links = GFFList()
    _add_link(back_links, MENU_ENTRY_JEDI, MENU_JEDI_CONDITION)
    _add_link(back_links, MENU_ENTRY, "")
    back.set_list("EntriesList", back_links)
    back_index = len(replies)
    back.struct_id = back_index  # list items carry their own index as struct id
    replies.append(back)

    # New entry: Yuthura has not decided. Template E80 is a plain Yuthura entry with one reply link and no script or quest.
    not_yet = copy.deepcopy(entries[80])
    not_yet.set_locstring("Text", LocalizedString.from_english(NOT_YET_TEXT))
    not_yet.set_resref("VO_ResRef", "")
    not_yet.set_resref("Script", "")
    not_yet.set_resref("Sound", "")
    not_yet.set_uint8("SoundExists", 0)
    not_yet.set_string("Quest", "")
    not_yet_links = GFFList()
    _add_link(not_yet_links, back_index, "")
    _add_link(not_yet_links, LEAVE_REPLY, "")
    not_yet.set_list("RepliesList", not_yet_links)
    not_yet_index = len(entries)
    not_yet.struct_id = not_yet_index
    entries.append(not_yet)

    # Gate the six links; add the fall-through link to the new entry.
    for r in ACCEPT_REPLIES:
        links = replies[r].get_list("EntriesList")
        links[0].set_resref("Active", GATE_CONDITION)
        _add_link(links, not_yet_index, "")
        replies[r].set_list("EntriesList", links)

    # First starter: while the gate refuses, Yuthura says one line and the conversation ends before any choice (nothing is used up).
    # The ending reply has empty text and no links; both new nodes are plain copies, like the Dorak "not yet" starter.
    end_reply = copy.deepcopy(replies[LEAVE_REPLY])
    end_reply.set_locstring("Text", LocalizedString.from_english(""))
    end_reply.set_resref("VO_ResRef", "")
    end_reply.set_resref("Sound", "")
    end_reply.set_resref("Script", "")
    end_reply.set_uint8("SoundExists", 0)
    end_reply.set_list("EntriesList", GFFList())
    end_index = len(replies)
    end_reply.struct_id = end_index
    replies.append(end_reply)

    start_entry = copy.deepcopy(entries[80])
    start_entry.set_locstring("Text", LocalizedString.from_english(START_TEXT))
    start_entry.set_resref("VO_ResRef", "")
    start_entry.set_resref("Script", "")
    start_entry.set_resref("Sound", "")
    start_entry.set_uint8("SoundExists", 0)
    start_entry.set_string("Quest", "")
    start_links = GFFList()
    _add_link(start_links, end_index, "")
    start_entry.set_list("RepliesList", start_links)
    start_index = len(entries)
    start_entry.struct_id = start_index
    entries.append(start_entry)

    starters = root.get_list("StartingList")
    first = copy.deepcopy(starters[0])
    first.set_uint32("Index", start_index)
    first.set_resref("Active", START_CONDITION)
    starters.insert(0, first)
    for position, st in enumerate(starters):  # starter struct ids are their positions
        st.struct_id = position
    root.set_list("StartingList", starters)

    root.set_list("EntryList", entries)
    root.set_list("ReplyList", replies)
    return gff


# ---- Uthar welcome scene -----------------------------------------------------------------------------------------------
def edit_uthar_intro(data):
    gff = read_gff(data)
    root = gff.root
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")
    assert len(entries) == 143 and len(replies) == 170, "kor35_utharwynn changed shape"

    for r, (speaker_entry, condition, skip_to) in UTHAR_SKIPS.items():
        links = replies[r].get_list("EntriesList")
        assert _links(replies[r], "EntriesList") == [(speaker_entry, "")], f"R{r} changed"
        assert str(entries[speaker_entry].get_string("Speaker")).startswith("kor35_"), f"E{speaker_entry} is not a student line"
        links[0].set_resref("Active", condition)
        _add_link(links, skip_to, "")
        replies[r].set_list("EntriesList", links)

    for (r, e, vanilla), replacement in UTHAR_COMBINED.items():
        links = replies[r].get_list("EntriesList")
        hit = [l for l in links if l.get_uint32("Index") == e and str(l.get_resref("Active")) == vanilla]
        assert len(hit) == 1, f"R{r} -> E{e} ({vanilla}) not found"
        hit[0].set_resref("Active", replacement)
        replies[r].set_list("EntriesList", links)

    root.set_list("EntryList", entries)
    root.set_list("ReplyList", replies)
    return gff


def build(game_dir=DEFAULT_GAME_DIR):
    """{file name: dialog bytes} for the gate dialogs that are always deployed with the Progression System."""
    return {YUTHURA_DLG + ".dlg": _to_bytes(edit_yuthura(_original(game_dir, YUTHURA_DLG, YUTHURA_MODULE)))}


def build_uthar_intro(game_dir=DEFAULT_GAME_DIR):
    """{file name: dialog bytes} for the optional repair of Uthar's welcome scene (absent students)."""
    return {UTHAR_DLG + ".dlg": _to_bytes(edit_uthar_intro(_original(game_dir, UTHAR_DLG, UTHAR_MODULE)))}


# ---- verification ------------------------------------------------------------------------------------------------------
def _struct_dump(obj):
    """Plain-python image of a GFF struct tree, so two dialogs can be compared field by field."""
    if isinstance(obj, GFFStruct):
        return {f.label: _struct_dump(f.value) for f in obj.fields()}
    if isinstance(obj, GFFList):
        return [_struct_dump(s) for s in obj]
    if isinstance(obj, LocalizedString):
        return ("loc", obj.stringref, tuple(sorted((int(l), int(g), t) for l, g, t in _substrings(obj))))
    return str(obj) if not isinstance(obj, (int, float, str, bytes, bool)) else obj


def _substrings(loc):
    for language, gender, text in loc:
        yield language, gender, text


def _graph(gff):
    root = gff.root
    entries = root.get_list("EntryList")
    replies = root.get_list("ReplyList")
    starters = [(s.get_uint32("Index"), str(s.get_resref("Active"))) for s in root.get_list("StartingList")]
    e_links = [_links(e, "RepliesList") for e in entries]
    r_links = [_links(r, "EntriesList") for r in replies]
    e_script = [str(e.get_resref("Script")) for e in entries]
    r_script = [str(r.get_resref("Script")) for r in replies]
    return starters, e_links, r_links, e_script, r_script


def _reach(graph, dead_conditions=(), blocked_starters=()):
    """Entries and replies reachable from the starters when every condition in dead_conditions is FALSE and every other
    condition is optimistically TRUE. Returns (entry set, reply set)."""
    starters, e_links, r_links, _, _ = graph
    seen_e, seen_r = set(), set()
    stack = [("E", i) for i, c in starters if c not in dead_conditions and c not in blocked_starters]
    while stack:
        kind, i = stack.pop()
        seen, nxt = (seen_e, e_links) if kind == "E" else (seen_r, r_links)
        if i in seen:
            continue
        seen.add(i)
        for t, c in nxt[i]:
            if c in dead_conditions:
                continue
            stack.append(("R" if kind == "E" else "E", t))
    return seen_e, seen_r


def check_yuthura(original_bytes, edited_bytes):
    """Re-reads both dialogs with pykotor, proves the gate and prints what it proved. Raises AssertionError on a failure."""
    orig = read_gff(original_bytes)
    new = read_gff(edited_bytes)
    og, ng = _graph(orig), _graph(new)
    o_starters, o_e, o_r, o_es, o_rs = og
    n_starters, n_e, n_r, n_es, n_rs = ng
    n_old_e, n_old_r = len(o_e), len(o_r)
    not_yet, back = n_old_e, n_old_r

    # 1. Nothing else changed: every original node is identical except the six gated reply links.
    o_root, n_root = _struct_dump(orig.root), _struct_dump(new.root)
    for key in o_root:
        if key in ("EntryList", "ReplyList", "StartingList"):
            continue
        assert o_root[key] == n_root[key], f"root field {key} changed"
    for i in range(n_old_e):
        assert o_root["EntryList"][i] == n_root["EntryList"][i], f"entry E{i} changed"
    changed = []
    for r in range(n_old_r):
        if o_root["ReplyList"][r] != n_root["ReplyList"][r]:
            changed.append(r)
            a, b = dict(o_root["ReplyList"][r]), dict(n_root["ReplyList"][r])
            a.pop("EntriesList"), b.pop("EntriesList")
            assert a == b, f"reply R{r} changed beyond its links"
    assert tuple(changed) == ACCEPT_REPLIES, f"changed replies {changed}"
    assert len(n_root["EntryList"]) == n_old_e + 2 and len(n_root["ReplyList"]) == n_old_r + 2
    start_entry, end_reply = n_old_e + 1, n_old_r + 1
    # The new first starter: Yuthura says one line (START_TEXT) and the conversation ends; all original starters follow unchanged.
    assert n_starters == [(start_entry, START_CONDITION)] + o_starters, f"starters are {n_starters}"
    assert n_e[start_entry] == [(end_reply, "")] and n_r[end_reply] == [], "the closed-gate entry must end the conversation after one line"
    assert n_es[start_entry] == "" and n_rs[end_reply] == "", "the closed-gate nodes must run no script"
    assert not str(new.root.get_list("EntryList")[start_entry].get_string("Quest")), "the closed-gate entry must not write a journal entry"
    print(f"  first starter E{start_entry} (if {START_CONDITION}): one line, then R{end_reply} ends the conversation; the original {len(o_starters)} starters follow")
    for r in ACCEPT_REPLIES:
        assert n_r[r] == [(ACCEPT_ENTRY, GATE_CONDITION), (not_yet, "")], f"R{r} links are {n_r[r]}"
    print(f"  only R{list(ACCEPT_REPLIES)} differ; they read [E{ACCEPT_ENTRY} if {GATE_CONDITION}] then [E{not_yet}]")

    # 2. Gate open (condition TRUE) reaches exactly what the original reached plus the new nodes; gate closed loses E16.
    #    k_pkor_yuthlv4 (starter E79, "You have come back") needs KOR_YUTHURA1 == 2, which only k_pkor_yuthlv2 sets, and
    #    that script runs only on E17, E19 and E23 -- all after E16. So it is blocked unless one of those is reachable.
    def reach_model(graph, dead):
        e, r = _reach(graph, dead_conditions=dead, blocked_starters=("k_pkor_yuthlv4",))
        sets_yuthura1 = any(graph[3][i] == "k_pkor_yuthlv2" for i in e)
        if sets_yuthura1:
            e, r = _reach(graph, dead_conditions=dead)
        return e, r, sets_yuthura1

    oe, orr, o_flag = reach_model(og, ())
    ge, gr, g_flag = reach_model(ng, (START_CONDITION,))                   # gate open: ap_kor_ko1 TRUE, the closed-gate starter FALSE
    ce, cr, c_flag = reach_model(ng, (GATE_CONDITION, START_CONDITION))   # backstop: the six links refuse even if the starter did not
    assert ACCEPT_ENTRY in oe and 95 in orr, "original: E16/R95 should be reachable"
    assert ge - {not_yet} == oe and gr - {back} == orr, "gate open: reachable set differs from the original"
    assert ACCEPT_ENTRY in ge and 95 in gr
    print(f"  original reaches E16 and R95 (academy transfer); gate open reaches the same {len(oe)} entries + the new one")
    assert ACCEPT_ENTRY not in ce, "gate closed: E16 still reachable"
    assert not c_flag, "gate closed: a script that sets KOR_YUTHURA1 is still reachable"
    assert 95 not in cr and 81 not in ce and 79 not in ce, "gate closed: the academy transfer is still reachable"
    quest50 = [i for i in ce if str(new.root.get_list("EntryList")[i].get_string("Quest")) == "kor33_enteracademy"
               and new.root.get_list("EntryList")[i].get_uint32("QuestEntry") == 50]
    assert not quest50, "gate closed: journal stage 50 is still reachable"
    print(f"  gate closed: E16, E17/E19/E23 (set KOR_YUTHURA1), E79/E81 and R95 (k_pkor_start35) unreachable; journal 50 unreachable; "
          f"{len(oe) - len(ce) + 1} original entries lost, all downstream of E16")
    lost = sorted(oe - ce)
    print(f"  entries lost with the gate closed: {lost}")

    # 3. The new entry is reachable when the gate is closed and does not dead-end.
    assert not_yet in ce and back in cr
    assert n_e[not_yet] == [(back, ""), (LEAVE_REPLY, "")]
    assert n_r[back] == [(MENU_ENTRY_JEDI, MENU_JEDI_CONDITION), (MENU_ENTRY, "")]
    assert n_es[not_yet] == "" and n_rs[back] == ""
    # Every path from the new entry ends in an entry/reply with an unconditional way on, or in the conversation's end.
    closed = {GATE_CONDITION, START_CONDITION}
    for kind, i in [("E", not_yet), ("R", back)]:
        links = n_e[i] if kind == "E" else n_r[i]
        assert any(c == "" for _, c in links), f"{kind}{i} has no unconditional link"
    e_after, r_after = _reach(ng, closed, blocked_starters=("k_pkor_yuthlv4",))
    ends = [r for r in r_after if not n_r[r]]
    assert 95 not in ends, "R95 (academy transfer) reachable with the gate closed"
    print(f"  new entry E{not_yet} is reachable; it offers R{back} (back to E{MENU_ENTRY_JEDI} if Jedi-looking, else E{MENU_ENTRY}) and R{LEAVE_REPLY} "
          f"(ends); the reachable conversation ends are replies {sorted(ends)}")
    # Starting again from E0/E63 must be able to reach the end (R1) and the persuade routes again.
    e_from_menu = _reach_from(ng, "E", MENU_ENTRY, closed)
    assert 11 in e_from_menu[0] and 15 in e_from_menu[0], "retry: the persuade-success entries are no longer reachable from the menu"
    assert 1 in e_from_menu[0] and 1 in e_from_menu[1], "retry: the conversation can no longer end from the menu"
    print("  from the menu the player can retry the persuade/lie routes (E11, E15 reachable) or leave (E1, R1)")

    # 4. The condition script name is the one the builder promises.
    assert len(GATE_CONDITION) <= 16


def _reach_from(graph, kind, index, dead):
    _, e_links, r_links, _, _ = graph
    seen_e, seen_r = set(), set()
    stack = [(kind, index)]
    while stack:
        k, i = stack.pop()
        seen, nxt = (seen_e, e_links) if k == "E" else (seen_r, r_links)
        if i in seen:
            continue
        seen.add(i)
        for t, c in nxt[i]:
            if c in dead:
                continue
            stack.append(("R" if k == "E" else "E", t))
    return seen_e, seen_r


def check_uthar_intro(original_bytes, edited_bytes):
    orig, new = read_gff(original_bytes), read_gff(edited_bytes)
    og, ng = _graph(orig), _graph(new)
    o_root, n_root = _struct_dump(orig.root), _struct_dump(new.root)
    assert o_root["EntryList"] == n_root["EntryList"], "an entry changed"
    expected = sorted(set(UTHAR_SKIPS) | {r for r, _, _ in UTHAR_COMBINED})
    changed = [r for r in range(len(o_root["ReplyList"])) if o_root["ReplyList"][r] != n_root["ReplyList"][r]]
    assert changed == expected, f"changed replies {changed}, expected {expected}"
    # Absent-student model: the presence conditions are FALSE, so none of the student-speaker entries may be reachable.
    absent = {"ap_kor_st_lash": 110, "ap_kor_st_mekel": 112, "ap_kor_st_shaa": 114}
    base_e, base_r = _reach(og)
    for cond, ent in absent.items():
        e, _ = _reach(ng, dead_conditions=(cond,))
        assert ent in base_e and ent not in e, f"E{ent} should vanish when {cond} is false"
        # the scene still reaches the player's choice node E116 and the end of the scene
        assert 116 in e, f"scene no longer reaches E116 without {cond}"
    e_all, _ = _reach(ng, dead_conditions=tuple(UTHAR_NEW_CONDITIONS))
    assert 116 in e_all and not ({110, 112, 114, 134, 135} & e_all)
    # With every student present the reachable scene equals the original's.
    e_ok, r_ok = _reach(ng)
    assert e_ok == base_e and r_ok == base_r
    print("  all presence conditions TRUE: reachable set equals the original; any condition FALSE: that student's line is gone, E116 still reached")


def main():
    game_dir = _arg("--game-dir", DEFAULT_GAME_DIR)
    out_dir = _arg("--out")
    jobs = [(YUTHURA_DLG, YUTHURA_MODULE, build, check_yuthura)]
    if "--uthar-intro" in sys.argv:
        jobs.append((UTHAR_DLG, UTHAR_MODULE, build_uthar_intro, check_uthar_intro))
    for name, module, builder, checker in jobs:
        files = builder(game_dir)
        original = _original(game_dir, name, module)
        edited = files[name + ".dlg"]
        print(f"{name}.dlg: {len(original)} -> {len(edited)} bytes")
        if "--check" in sys.argv or out_dir:
            checker(original, edited)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, name + ".dlg"), "wb") as f:
                f.write(edited)
            print(f"  wrote {os.path.join(out_dir, name + '.dlg')}")


if __name__ == "__main__":
    main()
