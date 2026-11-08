"""Class content rebuild: generator.

Reads the game's own 2DAs (feat, spells, classes, featgain, classpowergain, cls_spgn_jedi, skills, cls_st_*, cls_atk_*)
and the 12 recruitable companion templates, and writes into this folder:

  class_rebuild_tables.json   every class x level 1..50: auto-granted feats, general feat slots, power gain, power tier cap,
                              attack, saves, hit die, Force die, skill points; plus the feat and power plans and the
                              per-companion protected sets (the machine-readable source for everything below)
  class_rebuild_levels.csv    the same per-level table, one row per class and level, for reading
  k2se_classrb_data.nss       the generated NSS include (pure lookup functions, no arrays: NWScript has none)
  class_rebuild_checks.json   the generator's own consistency checks and the predictions compared with the live logs
  class_rebuild_vectors.json  expected totals per class and level, for the live tests to compare against

TSL has no Get2DAString (it is not among the 877 routines of nwscript.nss), so a script cannot read the game tables
at run time; this include is the data channel. Re-run after any change to the game data:

    python build_class_rebuild.py
"""
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# --game-dir D reads the tables of that install (default: K2_GAME_DIR, else the Steam folder); --out D writes there (default: this folder);
# --include-only writes just k2se_classrb_data.nss.
GAME_ARG = sys.argv[sys.argv.index("--game-dir") + 1] if "--game-dir" in sys.argv else None
if GAME_ARG:
    os.environ["K2_GAME_DIR"] = GAME_ARG
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else HERE
INCLUDE_ONLY = "--include-only" in sys.argv
os.makedirs(OUT, exist_ok=True)
import classrb_data as R  # noqa: E402

T = R.T
d = R.load()
F, S = d["feats"], d["spells"]
CL = d["classes"]
NL = R.N_LEVELS

SOURCE_2DAS = ["classes", "feat", "spells", "featgain", "classpowergain", "cls_spgn_jedi", "skills", "baseitems", "exptable"] +     sorted({d["classes"][c]["savingthrowtable"].lower() for c in d["classes"]} | {d["classes"][c]["attackbonustable"].lower() for c in d["classes"]})


def source_hashes():
    """sha1 of every 2DA the tables come from, as the game resolves it (Override first). A player's install that differs
    (TSLRCM and other content mods edit these) must be regenerated or refused."""
    import hashlib
    return {n: hashlib.sha1(T.find(n, T.RT.TwoDA)).hexdigest() for n in SOURCE_2DAS}


# --------------------------------------------------------------------------------------------- class tables
CODE = {cid: CL[cid]["featstable"].lower() for cid in CL}            # feat.2da column code
SKCODE = {cid: CL[cid]["skillstable"].lower() for cid in CL}         # skills.2da column code
PGCODE = {cid: CL[cid]["spellgaintable"].lower() for cid in CL}      # classpowergain.2da column ('' = no Force)
FGCODE = {cid: CL[cid]["featgain"].lower() for cid in CL}            # featgain.2da column prefix
ALIAS = {8: 0, 10: 0}                                                # rows that reuse Soldier's tables
FORCE = set(R.FORCE_CLASSES)
LIGHT, DARK = 0, 1
PLAN_DROPS = []   # (class, feat, missing prerequisite) entries removed from a feat plan because the prerequisite cannot be taken


def dead_feat(i):
    lab = F[i]["label"]
    return lab == "" or lab.startswith("XXX")


def granted_level(cid, i):
    v = R.toint(F[i][CODE[cid] + "_granted"], -1)
    return v if v and v > 0 else 0


def pc_granted(cid, i):
    col = CODE[cid] + "_pc_granted"
    return R.toint(F[i].get(col, ""), -1) > 0


def listed(cid, i):
    """feat is on the class's general (level-up) list: list column 0 or 1 [inferred: 3 = auto-granted, 4 = not offered]."""
    return F[i][CODE[cid] + "_list"] in ("0", "1") and not dead_feat(i)


def granted_feats(cid):
    out = [(granted_level(cid, i), i) for i in F if granted_level(cid, i) and not dead_feat(i)]
    return sorted(out)


def slots_at(cid, lvl):
    g = d["featgain"][lvl]
    return g[FGCODE[cid] + "_reg"] + g[FGCODE[cid] + "_bon"]


def power_gain_at(cid, lvl):
    return d["powergain"][lvl][PGCODE[cid]] if PGCODE[cid] else 0


def build_class_tables():
    out = {}
    for cid in sorted(CL):
        c = CL[cid]
        t = {
            "id": cid, "label": c["label"], "name": R.tlk(c["name"]) or c["label"], "feat_code": CODE[cid],
            "skill_code": SKCODE[cid], "alias_of": ALIAS.get(cid),
            "hit_die": R.toint(c["hitdie"]), "force_die": R.toint(c["forcedie"]), "skill_points_base": R.toint(c["skillpointbase"]),
            "spellcaster": R.toint(c["spellcaster"]), "primary": c["primaryabil"], "is_force": cid in FORCE,
            "unnamed_cut_row": cid == 10,
            "class_skills": [i for i in d["skills"] if d["skills"][i][SKCODE[cid] + "_class"] == "1"],
            "skill_reco_order": [i for _, i in sorted((R.toint(d["skills"][i][SKCODE[cid] + "_reco"]), i) for i in d["skills"]
                                                      if d["skills"][i][SKCODE[cid] + "_reco"] != "")],
            "levels": {},
        }
        for lvl in range(1, NL + 1):
            fs, sv, bab = d["featgain"][lvl], d["saves"][cid][lvl], d["bab"][cid][lvl]
            t["levels"][lvl] = {
                "granted_feats": [i for (l, i) in granted_feats(cid) if l == lvl],
                "general_slots": slots_at(cid, lvl),
                "power_gain": power_gain_at(cid, lvl),
                "power_tier_cap": d["power_cap"][lvl] if cid in FORCE else None,
                "bab": bab, "fort": sv[0], "ref": sv[1], "will": sv[2],
            }
        out[cid] = t
    return out


# --------------------------------------------------------------------------------------------- feat plan
def feat_plan(cid):
    """Ordered list of general-pick feats for the class: the game's own recommended order (<code>_recom ascending, ties by
    feat id), then the remaining eligible list feats by (min character level, id). Feats the class auto-grants are skipped."""
    code = CODE[cid]
    rec = sorted((R.toint(F[i][code + "_recom"]), i) for i in F if F[i][code + "_recom"] != "")
    plan, seen = [], set()
    for _, i in rec:
        if listed(cid, i) and not granted_level(cid, i) and i not in seen:
            plan.append(i)
            seen.add(i)
    n_recom = len(plan)
    rest = sorted((R.toint(F[i]["mincharlevel"], 0), i) for i in F if listed(cid, i) and not granted_level(cid, i) and i not in seen)
    for _, i in rest:
        plan.append(i)
    # closure: every prerequisite must be granted by the class (any level) or sit earlier in the plan; a missing but listed
    # prerequisite is pulled forward to just before its dependent, an unlistable one drops the dependent
    ok_granted = {i for (_, i) in granted_feats(cid)}
    changed, guard = True, 0
    while changed and guard < 500:
        changed, guard = False, guard + 1
        for pos, i in enumerate(plan):
            for p in feat_prereqs(i):
                if p in ok_granted:
                    continue
                if p not in plan:
                    if listed(cid, p) and not dead_feat(p):
                        plan.insert(pos, p)
                    else:
                        PLAN_DROPS.append((cid, i, p))
                        plan.remove(i)
                    changed = True
                    break
                if plan.index(p) > pos:
                    plan.remove(p)
                    plan.insert(pos, p)
                    changed = True
                    break
            if changed:
                break
    return plan, n_recom


def feat_prereqs(i):
    return [x for x in (R.toint(F[i]["prereqfeat1"]), R.toint(F[i]["prereqfeat2"])) if x]


def feat_meta_pack(i):
    p = feat_prereqs(i)
    p1 = p[0] if len(p) > 0 else 999
    p2 = p[1] if len(p) > 1 else 999
    return R.toint(F[i]["mincharlevel"], 0) * 1000000 + p2 * 1000 + p1


# --------------------------------------------------------------------------------------------- power plans
PGROUP = {3: "A", 4: "A", 5: "A", 11: "B", 12: "B", 13: "B", 14: "B", 16: "B", 15: "C"}   # identical learn tables inside a group
GROUP_REP = {"A": 3, "B": 11, "C": 15}


def learnable_powers(cid):
    col = R.FORCE_COLS[cid]
    return {i: R.toint(S[i][col], -1) for i in S if S[i]["usertype"] == "1" and R.toint(S[i][col], -1) >= 0}


def power_prereqs(i):
    return [int(x) for x in S[i]["prerequisites"].split("_") if x.isdigit()]


def power_plan(cid, side):
    learn = learnable_powers(cid)
    rc = "light_recom" if side == LIGHT else "dark_recom"
    rec = sorted((R.toint(S[i][rc]), i) for i in learn if S[i][rc] != "")
    plan = [i for _, i in rec]
    tail = sorted((learn[i], i) for i in learn if i not in plan)
    plan += [i for _, i in tail]
    warnings = []
    # closure: a power's prerequisites (spell ids) must be learnable by the class and come earlier in the plan
    changed = True
    guard = 0
    while changed and guard < 200:
        changed, guard = False, guard + 1
        for pos, i in enumerate(plan):
            for pre in power_prereqs(i):
                if pre not in learn:
                    warnings.append(f"power {i} {S[i]['label']} needs {pre} which class {cid} cannot learn: dropped")
                    plan.remove(i)
                    changed = True
                    break
                if plan.index(pre) > pos:
                    plan.remove(pre)
                    plan.insert(pos, pre)
                    changed = True
                    break
            if changed:
                break
    return plan, learn, sorted(set(warnings))


# --------------------------------------------------------------------------------------------- bit masks (24 bit words)
WORD = 24
NWORDS = (len(F) + WORD - 1) // WORD


def mask_words(ids, n=None):
    n = n or NWORDS
    w = [0] * n
    for i in ids:
        w[i // WORD] |= 1 << (i % WORD)
    return w


# --------------------------------------------------------------------------------------------- companions
COMP = {  # slot: (template resref, feat.2da companion column or None)
    0: ("p_atton", "atton"), 1: ("p_baodur", "baodur"), 2: ("p_mand", None), 3: ("p_g0t0", "g0t0"), 4: ("p_handmaiden", "handmaiden"),
    5: ("p_hk47", "hk47"), 6: ("p_kreia", "kreia"), 7: ("p_mira", None), 8: ("p_t3m4", None), 9: ("p_visas", None),
    10: ("p_hanharr", "hanharr"), 11: ("p_disciple", None)}


def comp_columns():
    """per companion column: {feat: level} for 1..50 (the level at which the engine's NPC level-up gives it) and the 255 'forbidden' set."""
    out = {}
    for col in R.COMPANION_FEAT_COLS:
        grant, forbid = {}, []
        for i in F:
            v = R.toint(F[i].get(col, ""), 0)
            if v in (None, 0):
                continue
            if v == 255:
                forbid.append(i)
            else:
                grant[i] = v
        out[col] = {"grant": grant, "forbid": forbid}
    return out


def read_template(resref):
    g = T.gff(resref, T.RT.UTC)
    cls = []
    for c in g.get_list("ClassList"):
        kl = [int(k.get_uint16("Spell")) for k in c.get_list("KnownList0")] if c.exists("KnownList0") else []
        cls.append({"class": int(c.get_int32("Class")), "level": int(c.get_int16("ClassLevel")), "powers": kl})
    feats = [int(f.get_uint16("Feat")) for f in g.get_list("FeatList")] if g.exists("FeatList") else []
    skills = [int(s.get_uint8("Rank")) for s in g.get_list("SkillList")] if g.exists("SkillList") else []
    ab = {k: int(g.get_uint8(k)) for k in ("Str", "Dex", "Con", "Int", "Wis", "Cha")}
    return {"classes": cls, "feats": feats, "skills": skills, "abilities": ab, "race": int(g.get_uint8("Race")),
            "max_hp": int(g.get_int16("MaxHitPoints")), "good_evil": int(g.get_uint8("GoodEvil"))}


def build_companions(cols):
    out = {}
    for slot, (resref, col) in COMP.items():
        tpl = read_template(resref)
        cls = tpl["classes"][0]
        cid, lvl = cls["class"], cls["level"]
        gset = {i for (l, i) in granted_feats(cid) if l <= lvl}
        have = set(tpl["feats"])
        colgrant = set(cols[col]["grant"]) if col else set()
        extras = sorted(have - gset)                       # on the template, not explained by the class table
        out[slot] = {
            "name": T.NPC_SLOTS[slot], "template": resref, "column": col, "class": cid, "class_label": CL[cid]["label"], "level": lvl,
            "race": tpl["race"], "abilities": tpl["abilities"], "max_hp": tpl["max_hp"], "good_evil": tpl["good_evil"],
            "template_feats": sorted(have), "granted_by_class_present": sorted(have & gset), "granted_by_class_missing": sorted(gset - have),
            "template_extras": extras, "column_feats_on_template": sorted(have & colgrant),
            "template_powers": cls["powers"], "skills": tpl["skills"],
            "general_slots_at_template_level": sum(slots_at(cid, l) for l in range(1, lvl + 1)),
            # protected = everything on the template that the class table does not explain, plus every feat the companion's own
            # column ever grants; never removed by a class swap
            # Complex Unarmed Animations (207, a Jedi-granted animation feat) belongs with the Unarmed Specialist line: a companion whose
            # column grants Unarmed Specialist I keeps it even in STRIP mode
            "column_extra": [207] if 212 in colgrant else [],
            "protected": sorted(set(extras) | colgrant),
            "forbidden": sorted(cols[col]["forbid"]) if col else [],
            "column_grant_levels": {str(k): v for k, v in sorted(cols[col]["grant"].items())} if col else {},
        }
    return out


# --------------------------------------------------------------------------------------------- checks
def run_checks(tables, comps, plans):
    chk = {"asserts": [], "warnings": [], "predictions": {}}

    def need(cond, msg):
        chk["asserts"].append({"ok": bool(cond), "what": msg})

    # 1. featgain and power gains are 0/1 and {1,2}: needed by the bit-mask encoding in the include
    need(all(v in (0, 1) for lvl in d["featgain"].values() for v in lvl.values()), "featgain values are all 0 or 1 (bonus column is all 0)")
    need(all(0 <= v <= 2 for lvl in d["powergain"].values() for v in lvl.values()), "classpowergain values are all 0..2")
    need(all(d["powergain"][l][k] >= 1 for l in d["powergain"] for k in d["powergain"][l]), "classpowergain is at least 1 every level")
    # 2. every class: list==3 set versus granted>0 set
    diff = {}
    for cid in sorted(CL):
        c = CODE[cid]
        l3 = {i for i in F if F[i][c + "_list"] == "3"}
        gr = {i for i in F if granted_level(cid, i)}
        if l3 != gr:
            diff[cid] = {"granted_but_list_not_3": sorted(gr - l3), "list3_but_not_granted": sorted(l3 - gr)}
    chk["list3_vs_granted_mismatch"] = diff
    need(not any(v["list3_but_not_granted"] for v in diff.values()), "every list==3 feat has a granted level")
    # 3. cap table is class level + 1
    need(all(d["power_cap"][l] == l + 1 for l in range(1, NL + 1)), "cls_spgn_jedi spelllevel0 == class level + 1 for 1..50")
    # 4. xp table closed form
    xp = T.twoda("exptable")
    ok = all(int(xp.get_row(i).get_string("xp")) == 500 * (i + 1) * i for i in range(NL))
    need(ok, "exptable xp(L) == 500*L*(L-1) for L in 1..50")
    # 5. HP formula against the templates
    hp = {}
    for slot, c in comps.items():
        cid, lvl, ab = c["class"], c["level"], c["abilities"]
        formula = (R.toint(CL[cid]["hitdie"]) + (ab["Con"] - 10) // 2) * lvl
        hp[T.NPC_SLOTS[slot]] = {"template_max_hp": c["max_hp"], "formula_sum_hd_plus_conmod": formula, "diff": c["max_hp"] - formula}
    chk["template_hp_vs_formula"] = hp
    # 6. plans: prerequisites closure
    for cid, (plan, n_recom) in plans["feat"].items():
        have = {i for (l, i) in granted_feats(cid)}
        pos = {i: k for k, i in enumerate(plan)}
        for k, i in enumerate(plan):
            for p in feat_prereqs(i):
                if p not in have and (p not in pos or pos[p] > k):
                    chk["warnings"].append(f"feat plan class {cid}: {F[i]['label']}({i}) needs feat {p} ({F[p]['label']}) not granted and not earlier in the plan")
    # 7. predictions against the live logs (COMPANION_SLOT_TEST.md)
    def feats_new(cid, lo, hi):
        return [i for (l, i) in granted_feats(cid) if lo <= l <= hi]

    def picks(cid, lo, hi):
        return sum(slots_at(cid, l) for l in range(lo, hi + 1))

    def pw(cid, lo, hi):
        return sum(power_gain_at(cid, l) for l in range(lo, hi + 1))

    carth = read_template("p_carth")
    s16 = feats_new(3, 1, 1)
    dup = [i for i in s16 if i in carth["feats"]]
    chk["predictions"]["stage16_carth_guardian_L1"] = {
        "granted_at_L1": len(s16), "already_on_template": len(dup), "general_picks": picks(3, 1, 1), "power_gain": pw(3, 1, 1),
        "predicted_feat_delta": len(s16) - len(dup) + picks(3, 1, 1), "observed_feat_delta": 6, "observed_powers": 2}
    s25 = feats_new(3, 5, 11)
    chk["predictions"]["stage25_carth_guardian_L4_to_L11"] = {
        "granted_L5_11": len(s25), "general_picks": picks(3, 5, 11), "power_gain": pw(3, 5, 11),
        "predicted_feat_delta": len(s25) + picks(3, 5, 11), "observed_feat_delta": 7, "observed_powers": 8,
        "note": "feat delta matches exactly; the power count is 1 higher than classpowergain predicts"}
    s24 = feats_new(13, 1, 8)
    chk["predictions"]["stage24_player_watchman_L1_to_L8"] = {
        "granted_L1_8": len(s24), "general_picks": picks(13, 1, 8), "power_gain": pw(13, 1, 8),
        "predicted_feat_delta_max": len(s24) + picks(13, 1, 8), "observed_feat_delta": 18, "observed_powers": 10,
        "note": "feat delta 1 below the maximum (one granted feat was probably already held); powers 2 above classpowergain"}
    return chk


# --------------------------------------------------------------------------------------------- NSS include
# Data channel: fixed-width digit strings read with StringToInt(GetSubString(...)). NWScript has no arrays, TSL has no
# Get2DAString, and a switch-per-entry encoding of the same data compiled to 145 KB; strings give O(1) indexed access
# and a few tens of KB. Every literal is kept under 2000 characters (the compiler accepted 32000; stay well below).
MAXLIT = 2000


def lit(s):
    assert len(s) <= MAXLIT, (len(s), s[:40])
    assert '"' not in s and "\\" not in s
    return '"' + s + '"'


def str_switch(fname, mapping, default='""', comment=""):
    """mapping: {key: string} -> string fname(int n) with a switch returning literals."""
    L = []
    if comment:
        L.append("// " + comment)
    L.append(f"string {fname}(int n)")
    L.append("{")
    L.append("    switch (n)")
    L.append("    {")
    for k, v in mapping.items():
        L.append(f"        case {k}: return {lit(v)};")
    L.append("    }")
    L.append(f"    return {default};")
    L.append("}")
    L.append("")
    return L


def int_switch(fname, pairs, default, comment=""):
    L = []
    if comment:
        L.append("// " + comment)
    L.append(f"int {fname}(int n)")
    L.append("{")
    L.append("    switch (n)")
    L.append("    {")
    for k, v in pairs:
        L.append(f"        case {k}: return {v};")
    L.append("    }")
    L.append(f"    return {default};")
    L.append("}")
    L.append("")
    return L


NFEAT = len(F)
NSPELL = len(S)
HALF_F = NFEAT // 2
HALF_S = NSPELL // 2


def split_fn(name, text, width, comment):
    """a string function with an int selector that returns the first or second half of a long table (keeps every literal short)."""
    half = (len(text) // width // 2) * width
    return [comment, f"string {name}(int nPart)", "{", f"    if (nPart == 0) return {lit(text[:half])};", f"    return {lit(text[half:])};", "}", ""]


def gen_include(tables, comps, plans, cols):
    out = []
    A = out.append
    A("// k2se_classrb_data.nss -- GENERATED by research/classrebuild/build_class_rebuild.py from the game's own 2DAs. Do not edit.")
    A("// Source tables (sha1 of the file the game resolves, Override first); a different install must regenerate this file:")
    for n, h in source_hashes().items():
        A("//   %-16s %s" % (n + ".2da", h))
    A("// Data is held in fixed-width digit strings (NWScript has no arrays and TSL has no Get2DAString). Read element k of width w with")
    A("//   RB_Num(sTable, k, w) = StringToInt(GetSubString(sTable, k*w, w)).")
    A("// Class ids are CLASS_TYPE_*; rows 8 (Minion) and 10 (cut Bounty Hunter) share Soldier's tables. Feat and spell numbers are")
    A("// feat.2da / spells.2da row numbers (%d feats, %d spells). Tables longer than %d characters come in two parts (RB_xxx(0), RB_xxx(1))." % (NFEAT, NSPELL, MAXLIT))
    A("")
    A("int RB_Num(string sTable, int nIdx, int nWidth)")
    A("{")
    A("    return StringToInt(GetSubString(sTable, nIdx * nWidth, nWidth));")
    A("}")
    A("")
    grant_s, list_s, slot_s, pow_s, plan_s = {}, {}, {}, {}, {}
    for cid in sorted(CL):
        base = ALIAS.get(cid, cid)
        grant_s[cid] = "".join("%02d" % granted_level(base, i) for i in range(NFEAT))
        list_s[cid] = "".join("1" if listed(base, i) else "0" for i in range(NFEAT))
        slot_s[cid] = "".join(str(slots_at(base, l)) for l in range(1, NL + 1))
        pow_s[cid] = "".join(str(power_gain_at(base, l)) for l in range(1, NL + 1)) if base in FORCE else ""
        plan_s[cid] = "".join("%03d" % i for i in plans["feat"][base][0])
    A("// ---- RB_GrantStr(nClass): %d x 2 digits, the class level at which feat i is auto-granted (00 = never)" % NFEAT)
    out += str_switch("RB_GrantStr", grant_s)
    A("// ---- RB_ListStr(nClass): %d x 1 digit, 1 when feat i is on the class's general level-up list (list column 0 or 1)" % NFEAT)
    out += str_switch("RB_ListStr", list_s)
    A("// ---- RB_SlotStr(nClass): 50 x 1 digit, general feat picks gained at class level 1..50 (featgain reg + bon)")
    out += str_switch("RB_SlotStr", slot_s)
    A("// ---- RB_PowStr(nClass): 50 x 1 digit, Force powers gained at class level 1..50 (classpowergain); empty for non-Force classes")
    out += str_switch("RB_PowStr", pow_s)
    A("// ---- RB_FeatPlanStr(nClass): 3 digits per entry, the general-pick feats in the order to take them (recommended order first)")
    plan_lens = {cid: len(v) for cid, v in plan_s.items()}
    assert max(plan_lens.values()) <= MAXLIT, plan_lens
    out += str_switch("RB_FeatPlanStr", plan_s)
    # feat meta: min character level (2), prereq1 (3), prereq2 (3), 8 digits per feat
    meta = "".join("%02d%03d%03d" % (R.toint(F[i]["mincharlevel"], 0), (feat_prereqs(i) + [999, 999])[0], (feat_prereqs(i) + [999, 999])[1])
                   for i in range(NFEAT))
    out += split_fn("RB_FeatMetaStr", meta, 8,
                    "// ---- RB_FeatMetaStr(nPart): %d x 8 digits: min character level (2), prerequisite feat 1 (3), prerequisite feat 2 (3); 999 = none. "
                    "Part 0 holds feats 0..%d, part 1 the rest." % (NFEAT, (len(meta) // 8 // 2) - 1))
    fo = set(force_only_feats())
    A("// ---- RB_ForceOnlyStr(): %d x 1 digit, 1 = feat granted by a Force class and by no non-Force class (stripped by No_Jedi / Droid)" % NFEAT)
    A("string RB_ForceOnlyStr()")
    A("{")
    A("    return %s;" % lit("".join("1" if i in fo else "0" for i in range(NFEAT))))
    A("}")
    A("")
    # powers
    tier_all = {}
    for cid in sorted(FORCE):
        for i, t in learnable_powers(cid).items():
            tier_all.setdefault(i, t)
    tier_s = "".join("%02d" % (tier_all[i] + 1 if i in tier_all else 0) for i in range(NSPELL))
    out += split_fn("RB_PowTierStr", tier_s, 2,
                    "// ---- RB_PowTierStr(nPart): %d x 2 digits, learn tier + 1 of each class-learnable Force power (00 = not learnable by level-up). "
                    "Tier 0 = base tier; tier n needs class level n-1 (cls_spgn_jedi caps the learnable tier at class level + 1). "
                    "Part 0 holds spells 0..%d, part 1 the rest." % (NSPELL, (len(tier_s) // 2 // 2) - 1))
    A("// RB_PowTier(nSpell): learn tier of a class-learnable Force power, -1 if it is not learnable by level-up")
    A("int RB_PowTier(int nSpell)")
    A("{")
    A("    int nHalf = %d;" % (len(tier_s) // 2 // 2))
    A("    int v;")
    A("    if (nSpell < 0 || nSpell >= %d) return -1;" % NSPELL)
    A("    if (nSpell < nHalf) v = RB_Num(RB_PowTierStr(0), nSpell, 2);")
    A("    else v = RB_Num(RB_PowTierStr(1), nSpell - nHalf, 2);")
    A("    return v - 1;")
    A("}")
    A("")
    A("int RB_IsForce(int nClass)")
    A("{")
    A("    return (nClass >= 3 && nClass <= 5) || (nClass >= 11 && nClass <= 16);")
    A("}")
    A("")
    A("// RB_PowerOk(nClass, nSpell): 1 if that class may learn the power (Confusion 200: prestige only; Crush Opposition I 144: Sith Lord only)")
    A("int RB_PowerOk(int nClass, int nSpell)")
    A("{")
    A("    if (!RB_IsForce(nClass)) return 0;")
    A("    if (RB_PowTier(nSpell) < 0) return 0;")
    A("    if (nSpell == 200) return (nClass >= 11);")
    A("    if (nSpell == 144) return (nClass == 15);")
    A("    return 1;")
    A("}")
    A("")
    ppl = {}
    for gname, gi in (("A", 0), ("B", 1), ("C", 2)):
        for side in (LIGHT, DARK):
            ppl[gi * 2 + side] = "".join("%03d" % i for i in plans["power"][(gname, side)][0])
    A("// ---- RB_PowPlanStr(nGroupSide): 3 digits per entry, spell ids in the order to learn them. nGroupSide = group*2 + side")
    A("//      group 0 = Guardian/Consular/Sentinel, 1 = Weapon Master/Master/Watchman/Marauder/Assassin, 2 = Sith Lord; side 0 = light, 1 = dark")
    out += str_switch("RB_PowPlanStr", ppl)
    A("int RB_PowerGroup(int nClass)")
    A("{")
    A("    if (nClass >= 3 && nClass <= 5) return 0;")
    A("    if (nClass == 15) return 2;")
    A("    if (nClass >= 11 && nClass <= 16) return 1;")
    A("    return -1;")
    A("}")
    A("")
    comp_s = {}
    for slot, c in comps.items():
        prot, forb = set(c["protected"]), set(c["forbidden"])
        gl = c["column_grant_levels"]
        def flag(i):
            if i in forb:
                return 2
            if str(i) in gl or i in c["column_extra"]:
                return 3
            return 1 if i in prot else 0
        comp_s[slot] = "".join("%d%02d" % (flag(i), int(gl.get(str(i), 0))) for i in range(NFEAT))
    A("// ---- RB_CompStr(nSlot): %d x 3 digits for companion slot 0..11: flag + the level (2 digits) at which the companion's own" % NFEAT)
    A("//      feat.2da column grants the feat (00 = none). Flags: 0 none, 1 template extra (kept by a class swap), 2 forbidden to grant")
    A("//      (the column's 255 entries), 3 companion column feat (never removed, granted at its level)")
    out += str_switch("RB_CompStr", comp_s)
    sk_s = {}
    for cid in sorted(CL):
        base = ALIAS.get(cid, cid)
        t = tables[base]
        reco = {sk: k + 1 for k, sk in enumerate(t["skill_reco_order"])}
        sk_s[cid] = "".join("%d%d%02d" % (1 if sk in t["class_skills"] else 0, 1 if d["skills"][sk]["droidcanuse"] == "1" else 0, reco.get(sk, 0))
                            for sk in range(8))
    A("// ---- RB_SkillStr(nClass): 8 skills x 4 digits: class skill (1/0), droid can use it (1/0), recommended rank order (2 digits, 00 = none)")
    A("//      skills in skills.2da order: 0 ComputerUse 1 Demolitions 2 Stealth 3 Awareness 4 Persuade 5 Repair 6 Security 7 TreatInjury")
    out += str_switch("RB_SkillStr", sk_s)
    bi = T.twoda("baseitems")
    req = {}
    for r in range(bi.get_height()):
        row = bi.get_row(r)
        fs = [R.toint(R.cell(row, "reqfeat%d" % k), 0) for k in range(5)]
        fs = [f for f in fs if f]
        if fs:
            assert len(fs) <= 3
            req[r] = "".join("%03d" % f for f in (fs + [0, 0, 0])[:3])
    A("// ---- RB_ReqFeatStr(nBaseItem): 3 x 3 digits, the feats baseitems.2da requires to equip that base item type (000 = none)")
    A("//      used to unequip a weapon/robe/armor the creature no longer qualifies for after a class change")
    out += str_switch("RB_ReqFeatStr", req, '"000000000"')
    pck = "".join("1" if any(pc_granted(c, i) for c in (3, 4, 5)) and not dead_feat(i) else "0" for i in range(NFEAT))
    A("// ---- RB_PcKeepStr(): %d x 1 digit, 1 = granted only to the PLAYER at character creation by a base Jedi class (<code>_pc_granted:" % NFEAT)
    A("//      light and medium armor, Critical Strike, Flurry, Power Attack/Blast, Rapid Shot, Sniper Shot, Blaster Rifle, Force Chain). A class")
    A("//      swap on the player keeps all of them. Used as the companion table of 'slot' 12 (the player).")
    A("string RB_PcKeepStr()")
    A("{")
    A("    return %s;" % lit(pck))
    A("}")
    A("")
    out += int_switch("RB_HitDie", [(cid, R.toint(CL[cid]["hitdie"])) for cid in sorted(CL)], 0, "RB_HitDie(nClass): classes.2da hitdie")
    out += int_switch("RB_ForceDie", [(cid, R.toint(CL[cid]["forcedie"])) for cid in sorted(CL)], 0, "RB_ForceDie(nClass): classes.2da forcedie")
    out += int_switch("RB_SkillPts", [(cid, R.toint(CL[cid]["skillpointbase"])) for cid in sorted(CL)], 0, "RB_SkillPts(nClass): classes.2da skillpointbase")
    A("// RB_XpForLevel(nLevel): exptable.2da, checked equal to 500*L*(L-1) for L 1..50")
    A("int RB_XpForLevel(int nLevel)")
    A("{")
    A("    return 500 * nLevel * (nLevel - 1);")
    A("}")
    A("")
    return "\n".join(out)


def force_only_feats():
    """feats granted by a Force class that no non-Force class grants OR lists as a general pick (so Weapon Focus: Blaster, which a
    Sith Lord is granted but a Soldier may simply choose, is not a Force-only feat)."""
    force, nonforce = set(), set()
    for cid in CL:
        for (l, i) in granted_feats(cid):
            (force if cid in FORCE else nonforce).add(i)
        if cid not in FORCE:
            nonforce |= {i for i in F if listed(cid, i)}
    return sorted(force - nonforce)


# --------------------------------------------------------------------------------------------- main
def main():
    tables = build_class_tables()
    cols = comp_columns()
    comps = build_companions(cols)
    plans = {"feat": {}, "power": {}}
    for cid in sorted(CL):
        if cid not in ALIAS:
            plans["feat"][cid] = feat_plan(cid)
        else:
            plans["feat"][cid] = plans["feat"][ALIAS[cid]]
    pw_warn = []
    for g, rep in GROUP_REP.items():
        for side in (LIGHT, DARK):
            plan, learn, w = power_plan(rep, side)
            plans["power"][(g, side)] = (plan, learn)
            pw_warn += w
    chk = run_checks(tables, comps, plans)
    chk["power_plan_warnings"] = sorted(set(pw_warn))
    chk["feat_plan_drops"] = [f"class {c}: {F[i]['label']}({i}) dropped, prerequisite {F[p]['label']}({p}) is neither granted nor on the class list"
                              for (c, i, p) in PLAN_DROPS]
    chk["force_only_feats"] = [{"id": i, "label": F[i]["label"]} for i in force_only_feats()]
    bad = [a for a in chk["asserts"] if not a["ok"]]
    chk["all_asserts_ok"] = not bad

    # ---- JSON tables
    js = {
        "meta": {"source_sha1": source_hashes(), "generated_from": "tsl_data (Override > chitin) feat/spells/classes/featgain/classpowergain/cls_spgn_jedi/skills/cls_st_*/cls_atk_*",
                 "levels": NL, "feat_count": len(F), "spell_count": len(S)},
        "classes": {str(cid): t for cid, t in tables.items()},
        "feat_plan": {str(cid): {"order": plan, "n_recommended": n} for cid, (plan, n) in plans["feat"].items()},
        "power_plan": {f"{g}_{'light' if side == LIGHT else 'dark'}": {"order": plan, "tiers": {str(i): learn[i] for i in plan}}
                       for (g, side), (plan, learn) in plans["power"].items()},
        "companions": {str(s): c for s, c in comps.items()},
        "force_only_feats": force_only_feats(),
        "feat_names": {str(i): F[i]["label"] for i in F},
        "spell_names": {str(i): S[i]["label"] for i in S if S[i]["usertype"] in ("1", "6")},
    }
    if not INCLUDE_ONLY:
        json.dump(js, open(os.path.join(OUT, "class_rebuild_tables.json"), "w"), indent=1)

    # ---- CSV
    with open(os.path.join(OUT, "class_rebuild_levels.csv") if not INCLUDE_ONLY else os.devnull, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["class_id", "class", "level", "new_granted_feat_ids", "new_granted_feats", "general_feat_slots", "power_gain",
                    "power_tier_cap", "bab", "fort", "ref", "will", "hit_die", "force_die", "skill_points_base"])
        for cid, t in tables.items():
            for lvl in range(1, NL + 1):
                r = t["levels"][lvl]
                w.writerow([cid, t["label"], lvl, " ".join(str(i) for i in r["granted_feats"]),
                            "; ".join(F[i]["label"] for i in r["granted_feats"]), r["general_slots"], r["power_gain"],
                            r["power_tier_cap"] if r["power_tier_cap"] is not None else "", r["bab"], r["fort"], r["ref"], r["will"],
                            t["hit_die"], t["force_die"], t["skill_points_base"]])

    # ---- test vectors: cumulative totals at fixed levels
    vec = {}
    for cid, t in tables.items():
        v = {}
        for lvl in (1, 3, 6, 10, 15, 20, 30, 50):
            gs = [i for (l, i) in granted_feats(cid) if l <= lvl]
            v[str(lvl)] = {
                "granted_feat_count": len(gs), "granted_feats": gs,
                "general_slots": sum(slots_at(cid, l) for l in range(1, lvl + 1)),
                "powers": sum(power_gain_at(cid, l) for l in range(1, lvl + 1)),
                "power_tier_cap": d["power_cap"][lvl] if cid in FORCE else None,
                "bab": d["bab"][cid][lvl], "fort": d["saves"][cid][lvl][0], "ref": d["saves"][cid][lvl][1], "will": d["saves"][cid][lvl][2],
                "hp_per_level_without_con": R.toint(CL[cid]["hitdie"]),
            }
        vec[str(cid)] = {"label": t["label"], "levels": v}
    if not INCLUDE_ONLY:
        json.dump(vec, open(os.path.join(OUT, "class_rebuild_vectors.json"), "w"), indent=1)

    # ---- include
    inc = gen_include(tables, comps, plans, cols)
    open(os.path.join(OUT, "k2se_classrb_data.nss"), "w", newline="\n").write(inc)
    chk["include"] = {"bytes": len(inc.encode()), "lines": inc.count("\n") + 1, "functions": inc.count("\nint RB_") + 1,
                      "case_labels": inc.count("        case ")}
    if not INCLUDE_ONLY:
        json.dump(chk, open(os.path.join(OUT, "class_rebuild_checks.json"), "w"), indent=1)

    print("asserts:", "ALL OK" if not bad else bad)
    print("include:", chk["include"])
    print("warnings:", len(chk["warnings"]), "power warnings:", len(chk["power_plan_warnings"]))
    for w in chk["warnings"][:20]:
        print("  ", w)
    for w in chk["power_plan_warnings"][:20]:
        print("  ", w)
    print("predictions:", json.dumps(chk["predictions"], indent=1))
    print("hp:", json.dumps(chk["template_hp_vs_formula"]))


if __name__ == "__main__":
    main()
