"""Compiles the Archipelago Vendor's conversation scripts (ap_vd_*) from data/vendor.json into a folder.

Five generic scripts that read their category and item from the script parameters of the dialogue node or link that runs them (so no script per skill or per
bundle). They contain no game content, only routine numbers; the dialogue, the creature and the items are made on the player's machine by client/k2_vendor.py.
Categories: 0 skill training, 1 ability training, 2 alignment change (item 0 toward the dark side, 1 toward the light), 3 Components, 4 Chemicals.

  python tools/build_vendor.py --game-dir <K2 folder> --out DIR
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)


def script_sources(cfg: dict) -> dict:
    head = '#include "k2ap_vendor"\n\n'
    bundles = cfg["bundles"]
    price_cases = "".join("    if (nCat >= 3 && nItem == %d) return %d;\n" % (i, p) for i, (_, p) in enumerate(bundles))
    amount_cases = "".join("    if (nItem == %d) return %d;\n" % (i, n) for i, (n, _) in enumerate(bundles))
    helpers = '''int VdPrice(int nCat, int nItem)
{
    if (nCat == 0) return %(skill_price)d;
    if (nCat == 1) return %(ability_price)d;
    if (nCat == 2 && nItem == 0) return 0;
    if (nCat == 2) return %(light_costs)d;
%(price_cases)s    return 0;
}

int VdAmount(int nItem)
{
%(amount_cases)s    return 0;
}

// TRUE when the category's offer may be taken now: under its limit, affordable, and not refused by the alignment.
int VdAllowed(object oPC, int nCat, int nItem)
{
    int nPrice = VdPrice(nCat, nItem);
    if (nCat == 0 && K2AP_Held(oPC, "ap_vd_skill") >= %(skill_limit)d) return FALSE;
    if (nCat == 1 && K2AP_Held(oPC, "ap_vd_abil") >= %(ability_limit)d) return FALSE;
    if (nCat == 2 && nItem == 0 && GetGoodEvilValue(oPC) <= %(dark_refused_at_or_below)d) return FALSE;
    if (nCat == 2 && nItem == 1 && GetGoodEvilValue(oPC) >= %(light_refused_at_or_above)d) return FALSE;
    return GetGold(oPC) >= nPrice;
}
''' % dict(cfg, price_cases=price_cases, amount_cases=amount_cases)
    out = {}
    out["ap_vd_greet"] = head + '''int StartingConditional()
{
    object oPC = GetPCSpeaker();
    SetCustomToken(9031, "Skill training: " + IntToString(K2AP_Held(oPC, "ap_vd_skill")) + " of %(skill_limit)d. Ability training: " + IntToString(K2AP_Held(oPC, "ap_vd_abil")) + " of %(ability_limit)d.");
    return TRUE;
}
''' % cfg
    out["ap_vd_menu"] = head + '''int StartingConditional()
{
    object oPC = GetPCSpeaker();
    int nMenu = GetScriptParameter(1);
    if (nMenu == 0) return K2AP_Held(oPC, "ap_vp_skill") > 0 && K2AP_Held(oPC, "ap_vd_skill") < %(skill_limit)d;
    if (nMenu == 1) return K2AP_Held(oPC, "ap_vp_abil") > 0 && K2AP_Held(oPC, "ap_vd_abil") < %(ability_limit)d;
    if (nMenu == 2) return K2AP_Held(oPC, "ap_vp_align") > 0;
    return K2AP_Held(oPC, "ap_vp_supply") > 0 && K2SE_ConfigInt("ap_crafting_mode", 0) > 0;
}
''' % cfg
    out["ap_vd_ok"] = head + helpers + '''
int StartingConditional()
{
    return VdAllowed(GetPCSpeaker(), GetScriptParameter(1), GetScriptParameter(2));
}
'''
    out["ap_vd_no"] = head + helpers + '''
int StartingConditional()
{
    return !VdAllowed(GetPCSpeaker(), GetScriptParameter(1), GetScriptParameter(2));
}
'''
    out["ap_vd_do"] = head + helpers + '''
void main()
{
    object oPC = GetPCSpeaker();
    int nCat = GetScriptParameter(1);
    int nItem = GetScriptParameter(2);
    if (!VdAllowed(oPC, nCat, nItem)) return;
    int nPrice = VdPrice(nCat, nItem);
    if (nCat == 0)
    {
        int nRank = K2SE_GetSkillRankBase(oPC, nItem);
        if (nRank < 0 || K2SE_SetSkillRank(oPC, nItem, nRank + 1) != 1) return;
        CreateItemOnObject("ap_vd_skill", oPC, 1);
    }
    else if (nCat == 1)
    {
        int nScore = K2SE_GetAbilityScoreBase(oPC, nItem);
        if (nScore < 0 || K2SE_SetAbilityScoreBase(oPC, nItem, nScore + 1) != 1) return;
        CreateItemOnObject("ap_vd_abil", oPC, 1);
    }
    else if (nCat == 2)
    {
        if (nItem == 0)
        {
            AdjustAlignment(oPC, ALIGNMENT_DARK_SIDE, %(alignment_step)d);
            K2SE_SetPartyCredits(GetGold(oPC) + %(dark_pays)d);
            K2AP_Trace("vendor", "alignment toward the dark side");
            return;
        }
        AdjustAlignment(oPC, ALIGNMENT_LIGHT_SIDE, %(alignment_step)d);
    }
    else if (nCat == 3) CreateItemOnObject("compont_00001", oPC, VdAmount(nItem));
    else CreateItemOnObject("chem_00001", oPC, VdAmount(nItem));
    K2SE_SetPartyCredits(GetGold(oPC) - nPrice);
    K2AP_Trace("vendor", "category " + IntToString(nCat) + " item " + IntToString(nItem) + " for " + IntToString(nPrice));
}
''' % cfg
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import k2compile
    with open(os.path.join(ROOT, "data", "vendor.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, "_work")
    k2compile.prepare_include_dir(work, a.game_dir)
    problems = 0
    sources = script_sources(cfg)
    for name, source in sources.items():
        with open(os.path.join(work, name + ".nss"), "w", newline="\n") as f:
            f.write(source)
        ok, message = k2compile.compile_script(work, name)
        if ok:
            with open(os.path.join(work, name + ".ncs"), "rb") as r, open(os.path.join(a.out, name + ".ncs"), "wb") as w:
                w.write(r.read())
        else:
            print("PROBLEM: %s did not compile: %s" % (name, message[-500:]))
            problems += 1
    print("%d scripts compiled into %s, %d problem(s)" % (len(sources) - problems, a.out, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
