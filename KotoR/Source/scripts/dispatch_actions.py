"""
The dispatcher's parameterized actions, as NWScript for the poll (generate_poll_shared.py --dispatch-test).

The area-entry path bakes every value into a freshly generated script (generate_trampoline_batch.py's build_*_block functions). The
dispatcher gets its values at run time, in the job's args, so the poll carries ready-made functions that read them. The bodies are not
rewritten here: they are the same builders' output, with the baked value replaced by a variable (set_xp, delevel, force_power) or
generated once per allowed value (the traps), so the code that runs is the code that was already proven. Only the companion class
conversion is assembled for run time, from the same pieces (build_class_feat_delta_lines and companion_unequip_lines).

Every function returns what DtRun expects: 1 applied, 2 ran but could not do its job (the client logs it as failed), 0 unknown.

  set_xp:<value>                       exact XP (and the party's catch-up)
  delevel:<level>:<xp>[:<force>]       exact level and XP, Force points when given and not negative
  force_power:<spells.2da row>         one Force power
  companion_class:<name>:<class>       a companion's class (needs the companion in the party; otherwise FAILED, nothing written)
  trap:<type>:<params>                 the trap items; params as build_trap_block takes them ("-" when it takes none)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

JEDI_CLASSES = ("guardian", "consular", "sentinel")
SKILL_KEYS = ("computeruse", "demolitions", "stealth", "awareness", "persuade", "repair", "security", "treatinjury")
ABILITY_TRAPS = ("reduce_str", "reduce_dex", "reduce_int", "reduce_wis", "reduce_cha")
COMPANION_TRAPS = ("remove_companion", "purge_companion", "trap_companion", "unparty_companion", "select_companion",
                   "set_recruit_marker")


def _indent(lines, n=4):
    pad = " " * n
    return [pad + line if line else line for line in lines]


def _function(signature, body):
    return [signature, "{", *_indent(body), "}", ""]


def build_source(gtb):
    """The NWScript text (functions only) for every parameterized action. `gtb` is the imported generate_trampoline_batch module."""
    out = []

    # ---- helpers ------------------------------------------------------------------------------------------------------
    out += _function("int DtNthInt(string sList, int nIndex, int nDefault)", [
        "// the nIndex-th number of a list separated by commas or colons",
        "int i = 0;",
        "while (i < nIndex)",
        "{",
        '    int nA = FindSubString(sList, ",");',
        '    int nB = FindSubString(sList, ":");',
        "    if (nA < 0 || (nB >= 0 && nB < nA)) nA = nB;",
        "    if (nA < 0) return nDefault;",
        "    sList = GetSubString(sList, nA + 1, GetStringLength(sList));",
        "    i = i + 1;",
        "}",
        'int nEndA = FindSubString(sList, ",");',
        'int nEndB = FindSubString(sList, ":");',
        "if (nEndA < 0 || (nEndB >= 0 && nEndB < nEndA)) nEndA = nEndB;",
        "if (nEndA >= 0) sList = GetSubString(sList, 0, nEndA);",
        'if (sList == "" || sList == "-") return nDefault;',
        "return StringToInt(sList);",
    ])
    out += _function("int DtListCount(string sList)", [
        "int n = 0;",
        "while (DtNthInt(sList, n, -9999) != -9999) n = n + 1;",
        "return n;",
    ])

    # ---- set_xp / delevel / force_power: the builders' own lines with the value as a variable ---------------------------
    # 2 = ran but the player's XP is still below what was asked: nothing was written
    out += _function("int DtSetXp(string sArgs)", ["int nValue = StringToInt(sArgs);", *gtb.build_set_xp_block("nValue"),
                                                     "if (GetXP(GetFirstPC()) < nValue) return 2;", "return 1;"])

    delevel = gtb.build_delevel_block("nLevel", "nXp", 0)
    delevel = [("if (nForce >= 0) " + line.replace("KSE_FIELD_FORCE(), 0)", "KSE_FIELD_FORCE(), nForce)")) if "KSE_FIELD_FORCE()" in line else line
               for line in delevel]
    out += _function("int DtDelevel(string sArgs)", [
        "int nLevel = DtNthInt(sArgs, 0, -1);", "int nXp = DtNthInt(sArgs, 1, -1);", "int nForce = DtNthInt(sArgs, 2, -1);",
        "if (nLevel < 1 || nXp < 0) return 2;", *delevel, "return 1;"])

    power = [line.replace("|id=nSpell|", '|id=" + IntToString(nSpell) + "|') for line in gtb.build_force_power_block("nSpell")]
    out += _function("int DtForcePower(string sArgs)", ["int nSpell = StringToInt(sArgs);", "if (nSpell < 1) return 2;", *power, "return 1;"])

    # ---- companion_class: one run-time function over the same pieces build_companion_class_block uses ------------------
    names = list(gtb._COMPANION_TAGS)
    names = [n for n in names if n in gtb._COMPANION_NPC_CONST]
    classes = list(gtb._CLASS_NAME_TO_CONST)
    body = ["int nSep = FindSubString(sArgs, \":\");", "if (nSep < 1) return 0;",
            "string sName = GetSubString(sArgs, 0, nSep);", "string sClass = GetSubString(sArgs, nSep + 1, GetStringLength(sArgs));",
            'string sTag = "";', "int nNpc = -1;"]
    for name in names:
        body.append(f'if (sName == "{name}") {{ sTag = "{gtb._COMPANION_TAGS[name]}"; nNpc = {gtb._COMPANION_NPC_CONST[name]}; }}')
    body += ["if (nNpc < 0) return 0;", "int nNew = -1;", "int bJedi = FALSE;"]
    for cls in classes:
        jedi = " bJedi = TRUE;" if cls in JEDI_CLASSES else ""
        body.append(f'if (sClass == "{cls}") {{ nNew = {gtb._CLASS_NAME_TO_CONST[cls]};{jedi} }}')
    body += ["if (nNew < 0) return 0;",
             "// the companion has to be in the party: a Carth-tagged object can exist well before he really joins, and a class written to it is lost",
             "object oCompanion = GetObjectByTag(sTag);",
             "if (!IsNPCPartyMember(nNpc) || !GetIsObjectValid(oCompanion)) return 2;",
             "int nOldClass = GetClassByPosition(1, oCompanion);",
             "int nClass1 = GetClassByPosition(2, oCompanion);",
             "// already this class: a repeat of an applied assignment, which would reset the level; counts as done",
             "if (nOldClass != nNew)",
             "{",
             "    KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_TYPE(), nNew);",
             "    KSE_SetCreatureField(oCompanion, KSE_FIELD_CLASS0_LEVEL(), 1);",
             "    KSE_SetCreatureField(oCompanion, KSE_FIELD_FORCE(), 10);"]
    for cls in classes:
        const = gtb._CLASS_NAME_TO_CONST[cls]
        delta = gtb.build_class_feat_delta_lines(const, "oCompanion", old_class_var="nOldClass", delay_grants=cls in JEDI_CLASSES,
                                                  indent="        ")
        if delta:
            body += [f"    if (nNew == {const})", "    {", *delta, "    }"]
    body += ["}", "if (!bJedi)", "{", *gtb.companion_unequip_lines(), "}",
             'KSE_Diag(109, "AP|APPLIED|companion_class|name=" + sName + "|class=" + sClass + "|class1=" + IntToString(nClass1));',
             "return 1;"]
    out += _function("int DtCompanionClass(string sArgs)", body)

    # ---- trap: each type and value as its own scope, using the builder's lines unchanged -------------------------------
    t = ["int nSep = FindSubString(sArgs, \":\");", "if (nSep < 1) return 0;",
         "string sType = GetSubString(sArgs, 0, nSep);", "string sParams = GetSubString(sArgs, nSep + 1, GetStringLength(sArgs));"]

    def case(cond, lines):
        t.extend([f"if ({cond})", "{", *_indent(lines), "    return 1;", "}"])

    for skill in SKILL_KEYS:
        case(f'sType == "reduce_skill" && sParams == "{skill}"', gtb.build_trap_block("reduce_skill", skill))
    for kind in ABILITY_TRAPS:
        case(f'sType == "{kind}"', gtb.build_trap_block(kind, "-"))
    case('sType == "cut_max_hp"', gtb.build_trap_block("cut_max_hp", "-"))
    case('sType == "remove_half_inventory"', gtb.build_trap_block("remove_half_inventory", "-"))
    for kind in COMPANION_TRAPS:
        for name in gtb._COMPANION_NPC_CONST_ALL:
            if kind == "set_recruit_marker" and name not in gtb._COMPANION_NPC_CONST_ALL:
                continue
            case(f'sType == "{kind}" && sParams == "{name}"', gtb.build_trap_block(kind, name))
    # the two list traps read their ids at run time
    case('sType == "remove_half_feats"', [
        "object oPC = GetFirstPC();", "int i = 0;", "int nId = DtNthInt(sParams, 0, -9999);",
        "while (nId != -9999)", "{", "    if (GetHasFeat(nId, oPC)) KSE_RemoveFeatArrayA(nId, oPC);", "    i = i + 1;",
        "    nId = DtNthInt(sParams, i, -9999);", "}",
        'KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_feats|ids=" + sParams);'])
    case('sType == "remove_half_powers"', [
        "object oPC = GetFirstPC();", "int i = 0;", "int nId = DtNthInt(sParams, 0, -9999);",
        "while (nId != -9999)", "{", "    if (GetHasSpell(nId, oPC)) KSE_SetCreatureField(oPC, KSE_FIELD_REMOVE_FORCE_POWER(), nId);",
        "    i = i + 1;", "    nId = DtNthInt(sParams, i, -9999);", "}",
        'KSE_Diag(134, "AP|APPLIED|trap|type=remove_half_powers|ids=" + sParams);'])
    t.append("return 0;")
    out += _function("int DtTrap(string sArgs)", t)
    return "\n".join(out)


# ---- fixed-arm result checks ---------------------------------------------------------------------------------------------
# Every fixed arm used to be reported as applied whenever it ran. Where the result can be read straight after the write, the arm is now
# judged by it: a skill, ability, XP or credit arm must have raised its number; a class arm, the droid conversion and a companion arm must
# leave the player in that state (so a repeat of one already applied still counts). The other arms (a death, the journal markers, the
# diagnostic ones) are not judged.
_CLASS_ARM_TYPES = {
    "class_guardian": "CLASS_TYPE_JEDIGUARDIAN", "class_consular": "CLASS_TYPE_JEDICONSULAR", "class_sentinel": "CLASS_TYPE_JEDISENTINEL",
    "pc_class_soldier": "CLASS_TYPE_SOLDIER", "pc_class_scout": "CLASS_TYPE_SCOUT", "pc_class_scoundrel": "CLASS_TYPE_SCOUNDREL",
}
UNJUDGED = -999


def arm_checks(by_label, labels):
    """({label: NWScript expression of the measure for delta arms}, {label: expression for state arms}) from the arm bodies."""
    import re
    delta, state = {}, {}
    for label in labels:
        text = "\n".join(by_label[label])
        skill = re.search(r"GetSkillRank\((SKILL_\w+), oPC\)", text)
        ability = re.search(r"GetAbilityScore\(oPC, (ABILITY_\w+)\)", text)
        npc = re.search(r"int nNPC = (NPC_\w+);", text)
        if skill:
            delta[label] = f"GetSkillRank({skill.group(1)}, oPC)"
        elif ability:
            delta[label] = f"GetAbilityScore(oPC, {ability.group(1)})"
        elif label == "xp":
            delta[label] = "GetXP(oPC)"
        elif label == "credits":
            delta[label] = "GetGold(oPC)"
        elif label in _CLASS_ARM_TYPES:
            assert _CLASS_ARM_TYPES[label] in text, label
            state[label] = f"(GetClassByPosition(1, oPC) == {_CLASS_ARM_TYPES[label]})"
        elif label == "pc_droid":
            assert "KSE_FIELD_CLASS0_TYPE(), 9" in text
            state[label] = "(GetClassByPosition(1, oPC) == 9)"
        elif label.startswith("companion_") and npc:
            state[label] = f"IsAvailableCreature({npc.group(1)})"
    return delta, state


def build_arm_checks(by_label, labels):
    """NWScript for DtArmValue (the measure before and after an arm) and DtArmCheck (1 = it did its job, 2 = it did not)."""
    delta, state = arm_checks(by_label, labels)
    value = ["int DtArmValue(object oPC, string sName)", "{"]
    for label, expr in list(delta.items()) + list(state.items()):
        value.append(f'    if (sName == "{label}") return {expr};')
    value += [f"    return {UNJUDGED};", "}", ""]
    check = ["int DtArmCheck(string sName, int nBefore, int nAfter)", "{", f"    if (nBefore == {UNJUDGED}) return 1;"]
    if state:
        cond = " || ".join(f'sName == "{label}"' for label in state)
        check += [f"    if ({cond})", "    {", "        if (nAfter == 1) return 1;", "        return 2;", "    }"]
    check += ["    if (nAfter > nBefore) return 1;", "    return 2;", "}", ""]
    return "\n".join(value + check)
