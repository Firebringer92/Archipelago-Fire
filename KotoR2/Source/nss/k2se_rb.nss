// k2se_rb.nss -- the class content rebuild (docs/CLASS_REBUILD.md): what a creature has after a class swap or a class add, brought to "a character of
// that class at level N". Promoted from research/classrebuild/class_rebuild_reference.nss (compiles with the project's compiler; it has not run in the game).
// Python twin: research/classrebuild/rb_sim.py (same algorithm on the same generated data; it is the oracle for the live tests).
//
// The data include k2se_classrb_data.nss is generated from the game's own tables (research/classrebuild/build_class_rebuild.py) and must be made on the
// player's machine: nothing derived from the game is published.
//
// Decisions of 2026-11-07: Tech Specialist counts as a base class; an added class gets one level at delivery; feats come in the game's recommended order
// (the autolevel order); the skill step is off; No_Jedi strips the Jedi feats including the lightsaber focus (mode STRIP).
//
// Entry points
//   RB_ConvertClass(oC, nPos, nNewClass, nLevel, nNpc, nMode)   swap the class in class position nPos (0..2), set its level, rebuild
//   RB_AddClass(oC, nClass, nLevel, nNpc, nSide)                 add a second/third class directly (AddMultiClass + level write + rebuild)
//   RB_RebuildClass(oC, nClass, nLevel, nOld, nOldLevel, ...)    the content step on its own (idempotent top-up)
//   RB_Resume(oC, nNpc)                                          finish a conversion that a crash or reload interrupted
//   main()                                                       script entry: ExecuteScript("k2se_rb", oC, RB_Pack(...)) -- the router's way in
// Natives used: K2SE_SetClassId, K2SE_SetClassLevel, K2SE_RemoveFeat, K2SE_RemovePower, K2SE_GetAbilityScoreBase, K2SE_Diag.
// Vanilla used: GrantFeat, GrantSpell, GetFeatAcquired, GetSpellAcquired, AddMultiClass, SetMaxHitPoints, SetXP, GetClassByPosition.
#include "k2se"
#include "k2se_classrb_data"

int RB_KEEP = 0;
int RB_STRIP = 1;
int RB_LIGHT = 0;
int RB_DARK = 1;
int RB_NFEAT = 245;

// (constants are plain top-level ints, never modified: this compiler's #define only supports the preprocessor-flag form)
// result codes of the top-level calls
int RB_OK_NOCHANGE = 0;
int RB_OK_CHANGED = 1;
int RB_PARTIAL = 2;          // converted, but some picks or powers could not be filled
int RB_BAD_STATE = 3;        // class or level not what the caller said
int RB_REFUSED = 4;          // a native refused (duplicate class, bad id, downgrade)

// ------------------------------------------------------------------------------------------------ marker bits on the creature
// Local booleans 0..63 (read back with != 0). Bits 32..58 hold the conversion marker so a crash between steps can be resumed:
//   32 pending | 33..37 old class | 38..43 old level | 44 hp done | 45 side chosen | 46 side | 47 mode | 48..58 hp before
int RB_B_PENDING = 32;
int RB_B_OLDCLASS = 33;
int RB_B_OLDLEVEL = 38;
int RB_B_HPDONE = 44;
int RB_B_SIDESET = 45;
int RB_B_SIDE = 46;
int RB_B_MODE = 47;
int RB_B_HPBEFORE = 48;

// ------------------------------------------------------------------------------------------------ where the marker lives
// Bits 32..58 are the marker. On a companion they are local booleans. On the PLAYER booleans 32..50 hold the story-gate release flags (nss/k2se_disp.nss),
// so the player's marker bits are kept in local numbers 1..4 (eight bits each) instead. Every marker access goes through these two functions.
int RB_MPlayer(object oC)
{
    return oC == GetFirstPC();
}

int RB_MGet(object oC, int n)
{
    if (n >= 32 && n <= 58 && RB_MPlayer(oC))
    {
        int b = n - 32;
        return (GetLocalNumber(oC, 1 + b / 8) >> (b % 8)) & 1;
    }
    return GetLocalBoolean(oC, n);
}

void RB_MPut(object oC, int n, int v)
{
    if (n >= 32 && n <= 58 && RB_MPlayer(oC))
    {
        int b = n - 32;
        int i = 1 + b / 8;
        int nCur = GetLocalNumber(oC, i);
        int nMask = 1 << (b % 8);
        if (v != 0) nCur = nCur | nMask;
        else nCur = nCur & (255 - nMask);
        SetLocalNumber(oC, i, nCur);
        return;
    }
    SetLocalBoolean(oC, n, v);
}

int RB_BitsGet(object oC, int nStart, int nWidth)
{
    int v = 0;
    int k;
    for (k = nWidth - 1; k >= 0; k--)
    {
        v = v * 2;
        if (RB_MGet(oC, nStart + k) != 0) v = v + 1;
    }
    return v;
}

void RB_BitsPut(object oC, int nStart, int nWidth, int nVal)
{
    int k;
    for (k = 0; k < nWidth; k++)
    {
        RB_MPut(oC, nStart + k, nVal % 2);
        nVal = nVal / 2;
    }
}

// ------------------------------------------------------------------------------------------------ small helpers
int RB_FindPos(object oC, int nClass)
{
    int p;
    for (p = 1; p <= 3; p++)
    {
        if (GetClassByPosition(p, oC) == nClass) return p - 1;
    }
    return -1;
}

int RB_CharLevel(object oC)
{
    return GetLevelByPosition(1, oC) + GetLevelByPosition(2, oC) + GetLevelByPosition(3, oC);
}

int RB_ConMod(object oC)
{
    int c = K2SE_GetAbilityScoreBase(oC, ABILITY_CONSTITUTION);
    if (c >= 10) return (c - 10) / 2;
    return -((11 - c) / 2);
}

string RB_Pad3(int n)
{
    string s = IntToString(n);
    while (GetStringLength(s) < 3) s = "0" + s;
    return s;
}

// 1 when feat f is one of the 3-digit entries of sList (aligned compare: FindSubString could match across two entries)
int RB_InList(string sList, int f)
{
    int n;
    for (n = 0; n < GetStringLength(sList) / 3; n++)
    {
        if (StringToInt(GetSubString(sList, n * 3, 3)) == f) return TRUE;
    }
    return FALSE;
}

string RB_Meta8(int f)
{
    if (f < 122) return GetSubString(RB_FeatMetaStr(0), f * 8, 8);
    return GetSubString(RB_FeatMetaStr(1), (f - 122) * 8, 8);
}

int RB_MetaMinLevel(int f) { return StringToInt(GetSubString(RB_Meta8(f), 0, 2)); }
int RB_MetaPre1(int f) { return StringToInt(GetSubString(RB_Meta8(f), 2, 3)); }
int RB_MetaPre2(int f) { return StringToInt(GetSubString(RB_Meta8(f), 5, 3)); }

// 1 when every prerequisite feat of f is held
int RB_PrereqsHeld(object oC, int f)
{
    int a = RB_MetaPre1(f);
    int b = RB_MetaPre2(f);
    if (a != 999 && !GetFeatAcquired(a, oC)) return FALSE;
    if (b != 999 && !GetFeatAcquired(b, oC)) return FALSE;
    return TRUE;
}

// companion flag for a feat: 0 none, 1 template extra, 2 forbidden, 3 the companion's own column feat; nNpc < 0 = no companion data, 12 = the player
int RB_CompFlag(int nNpc, int f)
{
    if (nNpc < 0) return 0;
    if (nNpc == 12) return StringToInt(GetSubString(RB_PcKeepStr(), f, 1));       // the player: pc_granted feats are kept
    return StringToInt(GetSubString(RB_CompStr(nNpc), f * 3, 1));
}

int RB_CompLevel(int nNpc, int f)
{
    if (nNpc < 0 || nNpc == 12) return 0;
    return StringToInt(GetSubString(RB_CompStr(nNpc), f * 3 + 1, 2));
}

// ------------------------------------------------------------------------------------------------ phase 1: feats the old class granted
// Remove, in dependency order, every feat the old class auto-granted up to its old level unless something else explains it:
//   the new class grants it, another class slot grants it, it is the companion's own column feat (or a template extra in KEEP mode),
//   or the new class lists it as a general pick (it stays and counts as one of that class's picks).
int RB_RemoveOldFeats(object oC, int nNew, int nLevel, int nOld, int nOldLevel, int nPosNew, int nNpc, int nMode)
{
    string sOld = RB_GrantStr(nOld);
    string sNew = RB_GrantStr(nNew);
    string sList = RB_ListStr(nNew);
    string sCand = "";
    int f;
    int p;
    int nRemoved = 0;
    for (f = 0; f < RB_NFEAT; f++)
    {
        int gOld = RB_Num(sOld, f, 2);
        if (gOld >= 1 && gOld <= nOldLevel && GetFeatAcquired(f, oC))
        {
            int gNew = RB_Num(sNew, f, 2);
            if (gNew >= 1 && gNew <= nLevel) continue;
            int nFlag = RB_CompFlag(nNpc, f);
            if (nFlag == 3) continue;
            if (nFlag == 1 && !(nMode == RB_STRIP && GetSubString(RB_ForceOnlyStr(), f, 1) == "1")) continue;
            if (GetSubString(sList, f, 1) == "1") continue;
            int bOther = FALSE;
            for (p = 1; p <= 3; p++)
            {
                if (p - 1 != nPosNew && GetClassByPosition(p, oC) != CLASS_TYPE_INVALID)
                {
                    int g = RB_Num(RB_GrantStr(GetClassByPosition(p, oC)), f, 2);
                    if (g >= 1 && g <= GetLevelByPosition(p, oC)) bOther = TRUE;
                }
            }
            if (bOther) continue;
            sCand = sCand + RB_Pad3(f);
        }
    }
    // STRIP: Force-only template extras (Atton's Force Sensitive and Jedi Sense) go too when the new class is not a Force class
    if (nMode == RB_STRIP && !RB_IsForce(nNew))
    {
        for (f = 0; f < RB_NFEAT; f++)
        {
            if (GetSubString(RB_ForceOnlyStr(), f, 1) == "1" && GetFeatAcquired(f, oC) && RB_CompFlag(nNpc, f) != 3
                && !RB_InList(sCand, f))
            {
                int gNew2 = RB_Num(sNew, f, 2);
                if (gNew2 >= 1 && gNew2 <= nLevel) continue;
                sCand = sCand + RB_Pad3(f);
            }
        }
    }
    // remove a candidate only when no other remaining candidate needs it; six passes cover every chain in feat.2da
    int nPass;
    int n;
    for (nPass = 0; nPass < 6 && GetStringLength(sCand) > 0; nPass++)
    {
        string sLeft = "";
        for (n = 0; n < GetStringLength(sCand) / 3; n++)
        {
            int c = StringToInt(GetSubString(sCand, n * 3, 3));
            int bNeeded = FALSE;
            int m;
            for (m = 0; m < GetStringLength(sCand) / 3; m++)
            {
                int o = StringToInt(GetSubString(sCand, m * 3, 3));
                if (o != c && (RB_MetaPre1(o) == c || RB_MetaPre2(o) == c)) bNeeded = TRUE;
            }
            if (bNeeded) sLeft = sLeft + RB_Pad3(c);
            else if (K2SE_RemoveFeat(oC, c) == 1) nRemoved++;
        }
        if (sLeft == sCand) break;
        sCand = sLeft;
    }
    return nRemoved;
}

// ------------------------------------------------------------------------------------------------ phase 2: powers nobody on the creature can have
// Only on a conversion (or STRIP to a non-Force class). A power stays if the new class can learn it or another class position can.
// Powers outside the class-learnable set (Droid Trick, Wookiee Rage ...) have no tier and are never touched.
int RB_RemovePowers(object oC, int nNew, int nOld, int nPosNew, int nMode)
{
    if (!((nOld >= 0 && nOld != nNew) || (nMode == RB_STRIP && !RB_IsForce(nNew)))) return 0;
    int nRemoved = 0;
    int sp;
    int p;
    for (sp = 0; sp < 282; sp++)
    {
        if (RB_PowTier(sp) >= 0 && GetSpellAcquired(sp, oC))
        {
            int bKeep = RB_PowerOk(nNew, sp);
            for (p = 1; p <= 3; p++)
            {
                if (p - 1 != nPosNew && GetClassByPosition(p, oC) != CLASS_TYPE_INVALID && RB_PowerOk(GetClassByPosition(p, oC), sp)) bKeep = TRUE;
            }
            if (!bKeep && K2SE_RemovePower(oC, sp) == 1) nRemoved++;
        }
    }
    return nRemoved;
}

// ------------------------------------------------------------------------------------------------ phase 3: auto-granted and companion feats
int RB_GrantFeats(object oC, int nNew, int nLevel, int nNpc)
{
    string sNew = RB_GrantStr(nNew);
    int nAdded = 0;
    int nPass;
    int f;
    int nChar = RB_CharLevel(oC);
    for (nPass = 0; nPass < 3; nPass++)
    {
        for (f = 0; f < RB_NFEAT; f++)
        {
            int g = RB_Num(sNew, f, 2);
            int bAuto = (g >= 1 && g <= nLevel);
            int nCL = RB_CompLevel(nNpc, f);
            int bCol = (RB_CompFlag(nNpc, f) == 3 && nCL >= 1 && nCL <= nChar);
            if ((bAuto || bCol) && RB_CompFlag(nNpc, f) != 2 && !GetFeatAcquired(f, oC))
            {
                // prerequisite first: Light armor before Medium before Heavy, Sneak Attack 1d6 before 2d6; the last pass grants regardless
                if (nPass == 2 || RB_PrereqsHeld(oC, f))
                {
                    GrantFeat(f, oC);
                    nAdded++;
                }
            }
        }
    }
    return nAdded;
}

// ------------------------------------------------------------------------------------------------ phase 4: general feat picks
// Slots earned = sum of featgain over levels 1..N of EVERY class position. A feat the creature holds that any of its classes lists as a
// general pick (and no class auto-grants, and is not the companion's own) counts as a pick already made. The rest come from the plan.
// Returns the number of picks still owed (negative or zero = complete).
int RB_PicksMissing(object oC, int nNpc)
{
    int nSlots = 0;
    int p;
    int l;
    for (p = 1; p <= 3; p++)
    {
        int nCls = GetClassByPosition(p, oC);
        if (nCls != CLASS_TYPE_INVALID)
        {
            string sSlot = RB_SlotStr(nCls);
            for (l = 1; l <= GetLevelByPosition(p, oC); l++) nSlots = nSlots + StringToInt(GetSubString(sSlot, l - 1, 1));
        }
    }
    int nHave = 0;
    int f;
    for (f = 0; f < RB_NFEAT; f++)
    {
        if (RB_CompFlag(nNpc, f) != 3 && GetFeatAcquired(f, oC))
        {
            int bListed = FALSE;
            int bGranted = FALSE;
            for (p = 1; p <= 3; p++)
            {
                int nC2 = GetClassByPosition(p, oC);
                if (nC2 != CLASS_TYPE_INVALID)
                {
                    if (GetSubString(RB_ListStr(nC2), f, 1) == "1") bListed = TRUE;
                    if (RB_Num(RB_GrantStr(nC2), f, 2) > 0) bGranted = TRUE;
                }
            }
            if (bListed && !bGranted) nHave++;
        }
    }
    return nSlots - nHave;
}

int RB_FillPicks(object oC, int nNew, int nLevel, int nNpc)
{
    int nNeed = RB_PicksMissing(oC, nNpc);
    int nMade = 0;
    string sPlan = RB_FeatPlanStr(nNew);
    int nN = GetStringLength(sPlan) / 3;
    int nChar = RB_CharLevel(oC);
    int nPass;
    int k;
    for (nPass = 0; nPass < 3 && nNeed > 0; nPass++)
    {
        int bProgress = FALSE;
        for (k = 0; k < nN && nNeed > 0; k++)
        {
            int f = StringToInt(GetSubString(sPlan, k * 3, 3));
            if (!GetFeatAcquired(f, oC) && RB_CompFlag(nNpc, f) != 2 && RB_MetaMinLevel(f) <= nChar && RB_PrereqsHeld(oC, f))
            {
                GrantFeat(f, oC);
                nMade++;
                nNeed--;
                bProgress = TRUE;
            }
        }
        if (!bProgress) break;
    }
    return nMade;
}

// ------------------------------------------------------------------------------------------------ phase 5: Force powers
// Count earned = sum of classpowergain over 1..N of EVERY Force class position; a held power that any of those classes can learn counts
// toward it. Fill from the side's plan, skipping tiers above the class level (cls_spgn_jedi caps at level + 1; the stricter reading is used
// until a live test says more).
int RB_PowersMissing(object oC)
{
    int nTarget = 0;
    int p;
    int l;
    for (p = 1; p <= 3; p++)
    {
        int nCls = GetClassByPosition(p, oC);
        if (nCls != CLASS_TYPE_INVALID && RB_IsForce(nCls))
        {
            string sPow = RB_PowStr(nCls);
            for (l = 1; l <= GetLevelByPosition(p, oC); l++) nTarget = nTarget + StringToInt(GetSubString(sPow, l - 1, 1));
        }
    }
    int nHave = 0;
    int sp;
    for (sp = 0; sp < 282; sp++)
    {
        if (GetSpellAcquired(sp, oC))
        {
            int bAny = FALSE;
            for (p = 1; p <= 3; p++)
            {
                int nC2 = GetClassByPosition(p, oC);
                if (nC2 != CLASS_TYPE_INVALID && RB_PowerOk(nC2, sp)) bAny = TRUE;
            }
            if (bAny) nHave++;
        }
    }
    return nTarget - nHave;
}

int RB_FillPowers(object oC, int nNew, int nLevel, int nSide)
{
    if (!RB_IsForce(nNew)) return 0;
    int nNeed = RB_PowersMissing(oC);
    int nMade = 0;
    string sPlan = RB_PowPlanStr(RB_PowerGroup(nNew) * 2 + nSide);
    int nN = GetStringLength(sPlan) / 3;
    int k;
    for (k = 0; k < nN && nNeed > 0; k++)
    {
        int sp = StringToInt(GetSubString(sPlan, k * 3, 3));
        if (!GetSpellAcquired(sp, oC) && RB_PowerOk(nNew, sp) && RB_PowTier(sp) <= nLevel)
        {
            GrantSpell(sp, oC);
            nMade++;
            nNeed--;
        }
    }
    return nMade;
}

// ------------------------------------------------------------------------------------------------ optional: equipment, skills
// A removed proficiency does not unequip what is already worn (K1 finding): take off any weapon, robe or armor whose required feats are gone.
int RB_FixEquipment(object oC)
{
    int nOff = 0;
    int i;
    for (i = 0; i < 3; i++)
    {
        int nSlot = INVENTORY_SLOT_RIGHTWEAPON;
        if (i == 1) nSlot = INVENTORY_SLOT_LEFTWEAPON;
        if (i == 2) nSlot = INVENTORY_SLOT_BODY;
        object oItem = GetItemInSlot(nSlot, oC);
        if (GetIsObjectValid(oItem))
        {
            string sReq = RB_ReqFeatStr(GetBaseItemType(oItem));
            int k;
            int bOk = TRUE;
            for (k = 0; k < 3; k++)
            {
                int f = StringToInt(GetSubString(sReq, k * 3, 3));
                if (f > 0 && !GetFeatAcquired(f, oC)) bOk = FALSE;
            }
            if (!bOk)
            {
                AssignCommand(oC, ActionUnequipItem(oItem, TRUE));
                nOff++;
            }
        }
    }
    return nOff;
}

// Skills (default OFF): keep the total number of ranks, move ranks out of skills that are cross-class for the new class into its class
// skills in the game's recommended order, up to level + 3 per skill. Droid classes skip skills a droid cannot use.
int RB_RepointSkills(object oC, int nNew, int nLevel)
{
    string sSk = RB_SkillStr(nNew);
    int nPool = 0;
    int s;
    for (s = 0; s < 8; s++)
    {
        int bClass = StringToInt(GetSubString(sSk, s * 4, 1));
        int bDroidOk = StringToInt(GetSubString(sSk, s * 4 + 1, 1));
        int nRank = K2SE_GetSkillRankBase(oC, s);
        int bDroidClass = (nNew == 6 || nNew == 7);
        if ((!bClass || (bDroidClass && !bDroidOk)) && nRank > 0)
        {
            nPool = nPool + nRank;
            K2SE_SetSkillRank(oC, s, 0);
        }
    }
    int nCap = nLevel + 3;
    int nPick;
    for (nPick = 1; nPick <= 8 && nPool > 0; nPick++)
    {
        for (s = 0; s < 8; s++)
        {
            if (StringToInt(GetSubString(sSk, s * 4 + 2, 2)) == nPick && StringToInt(GetSubString(sSk, s * 4, 1)) == 1)
            {
                int nHave = K2SE_GetSkillRankBase(oC, s);
                int nAdd = nCap - nHave;
                if (nAdd > nPool) nAdd = nPool;
                if (nAdd > 0)
                {
                    K2SE_SetSkillRank(oC, s, nHave + nAdd);
                    nPool = nPool - nAdd;
                }
            }
        }
    }
    return nPool;     // ranks that found no home (cap reached): 0 normally
}

// ------------------------------------------------------------------------------------------------ the content step (idempotent)
// nOld < 0: pure top-up. Returns a result code; the detail goes to k2se.log as one "RB|..." line.
int RB_RebuildClass(object oC, int nNew, int nLevel, int nOld, int nOldLevel, int nNpc, int nMode, int nSide)
{
    int nPos = RB_FindPos(oC, nNew);
    if (nPos < 0 || GetLevelByPosition(nPos + 1, oC) != nLevel) return RB_BAD_STATE;
    int nRemF = 0;
    int nRemP = 0;
    if (nOld >= 0 && nOld != nNew)
    {
        nRemF = RB_RemoveOldFeats(oC, nNew, nLevel, nOld, nOldLevel, nPos, nNpc, nMode);
    }
    else if (nMode == RB_STRIP && !RB_IsForce(nNew))
    {
        nRemF = RB_RemoveOldFeats(oC, nNew, nLevel, nNew, 0, nPos, nNpc, nMode);   // old level 0: only the STRIP list applies
    }
    nRemP = RB_RemovePowers(oC, nNew, nOld, nPos, nMode);
    int nAddF = RB_GrantFeats(oC, nNew, nLevel, nNpc);
    int nPick = RB_FillPicks(oC, nNew, nLevel, nNpc);
    int nAddP = RB_FillPowers(oC, nNew, nLevel, nSide);
    int nUnF = RB_PicksMissing(oC, nNpc);
    int nUnP = 0;
    if (RB_IsForce(nNew)) nUnP = RB_PowersMissing(oC);
    int nOff = RB_FixEquipment(oC);
    K2SE_Diag("RB", "npc=" + IntToString(nNpc) + " class=" + IntToString(nNew) + " L=" + IntToString(nLevel) + " old=" + IntToString(nOld)
        + " remF=" + IntToString(nRemF) + " addF=" + IntToString(nAddF) + " pick=" + IntToString(nPick) + " remP=" + IntToString(nRemP)
        + " addP=" + IntToString(nAddP) + " unfilledF=" + IntToString(nUnF) + " unfilledP=" + IntToString(nUnP) + " unequipped=" + IntToString(nOff)
        + " hp=" + IntToString(GetMaxHitPoints(oC)) + " fp=" + IntToString(GetMaxForcePoints(oC)));
    if (nUnF > 0 || nUnP > 0) return RB_PARTIAL;
    if (nRemF + nRemP + nAddF + nPick + nAddP + nOff > 0) return RB_OK_CHANGED;
    return RB_OK_NOCHANGE;
}

// ------------------------------------------------------------------------------------------------ conversion with a resumable marker
int RB_SideFor(object oC)
{
    if (RB_MGet(oC, RB_B_SIDESET) != 0)
    {
        if (RB_MGet(oC, RB_B_SIDE) != 0) return RB_DARK;
        return RB_LIGHT;
    }
    int nGE = GetGoodEvilValue(GetFirstPC());
    int nSide = RB_LIGHT;
    if (nGE < 50) nSide = RB_DARK;
    if (nGE == 50) nSide = Random(2);
    RB_MPut(oC, RB_B_SIDESET, 1);
    RB_MPut(oC, RB_B_SIDE, nSide);
    return nSide;
}

void RB_ClearMarker(object oC)
{
    RB_BitsPut(oC, RB_B_PENDING, 27, 0);
}

int RB_Finish(object oC, int nNew, int nLevel, int nNpc)
{
    int nOld = RB_BitsGet(oC, RB_B_OLDCLASS, 5);
    int nOldLevel = RB_BitsGet(oC, RB_B_OLDLEVEL, 6);
    int nMode = RB_MGet(oC, RB_B_MODE);
    if (nMode != 0) nMode = RB_STRIP;
    int nSide = RB_SideFor(oC);
    int nRes = RB_RebuildClass(oC, nNew, nLevel, nOld, nOldLevel, nNpc, nMode, nSide);
    if (nRes == RB_BAD_STATE) return nRes;
    // hit points: target = HP before the conversion + (new class sum - old class sum), each sum = level * (hit die + CON modifier).
    // Written once (the hp-done bit), so a resumed run cannot add it twice.
    if (RB_MGet(oC, RB_B_HPDONE) == 0)
    {
        int nCon = RB_ConMod(oC);
        int nBefore = RB_BitsGet(oC, RB_B_HPBEFORE, 11);
        int nTarget = nBefore + nLevel * (RB_HitDie(nNew) + nCon) - nOldLevel * (RB_HitDie(nOld) + nCon);
        if (nTarget < 1) nTarget = 1;
        SetMaxHitPoints(oC, nTarget);
        RB_MPut(oC, RB_B_HPDONE, 1);
    }
    // XP follows the level, never lowered (SetXP only raises): a class level written without XP would leave the two out of step
    int nXp = RB_XpForLevel(RB_CharLevel(oC));
    if (GetXP(oC) < nXp) SetXP(oC, nXp);
    RB_ClearMarker(oC);
    return nRes;
}

// Swap the class in position nPos (0 = base class) to nNewClass at nLevel and rebuild. Re-running it changes nothing.
int RB_ConvertClass(object oC, int nPos, int nNewClass, int nLevel, int nNpc, int nMode)
{
    if (!K2SE_IsPresent() || !GetIsObjectValid(oC)) return RB_REFUSED;
    if (nNewClass < 0 || nNewClass > 16 || nNewClass == 10 || nLevel < 1 || nLevel > 50 || nPos < 0 || nPos > 2) return RB_REFUSED;
    int nCur = GetClassByPosition(nPos + 1, oC);
    int nCurLevel = GetLevelByPosition(nPos + 1, oC);
    if (nCur == CLASS_TYPE_INVALID) return RB_REFUSED;                       // an empty position takes AddMultiClass, not a swap
    if (RB_MGet(oC, RB_B_PENDING) == 0)
    {
        if (nLevel < nCurLevel) return RB_REFUSED;                           // never lower a class level
        int nSideNow = RB_SideFor(oC);                                       // fixes the light/dark choice before any change
        RB_BitsPut(oC, RB_B_OLDCLASS, 5, nCur);
        RB_BitsPut(oC, RB_B_OLDLEVEL, 6, nCurLevel);
        RB_BitsPut(oC, RB_B_HPBEFORE, 11, GetMaxHitPoints(oC));
        RB_MPut(oC, RB_B_MODE, nMode);
        RB_MPut(oC, RB_B_HPDONE, 0);
        RB_MPut(oC, RB_B_PENDING, 1);
    }
    if (nCur != nNewClass)
    {
        if (K2SE_SetClassId(oC, nPos, nNewClass) != 1) { RB_ClearMarker(oC); return RB_REFUSED; }   // duplicate class, cut row, bad slot
    }
    if (nCurLevel != nLevel)
    {
        if (K2SE_SetClassLevel(oC, nPos, nLevel) != 1) { RB_ClearMarker(oC); return RB_REFUSED; }
    }
    return RB_Finish(oC, nNewClass, nLevel, nNpc);
}

// Add a further class directly: one AddMultiClass holds a pending level-0 class, so the level is written at once and the content rebuilt.
int RB_AddClass(object oC, int nClass, int nLevel, int nNpc, int nSide)
{
    if (!K2SE_IsPresent() || !GetIsObjectValid(oC)) return RB_REFUSED;
    if (nClass < 0 || nClass > 16 || nClass == 10 || nLevel < 1) return RB_REFUSED;
    if (RB_FindPos(oC, nClass) >= 0) return RB_REFUSED;                       // already has it: use RB_RebuildClass for a top-up
    if (GetClassByPosition(3, oC) != CLASS_TYPE_INVALID) return RB_REFUSED;   // three classes is the engine's limit
    if (GetClassByPosition(2, oC) != CLASS_TYPE_INVALID && GetLevelByPosition(2, oC) == 0) return RB_REFUSED;   // a pending class is already waiting
    AddMultiClass(nClass, oC);
    int nPos = RB_FindPos(oC, nClass);
    if (nPos < 0) return RB_REFUSED;
    if (K2SE_SetClassLevel(oC, nPos, nLevel) != 1) return RB_REFUSED;
    int nRes = RB_RebuildClass(oC, nClass, nLevel, -1, 0, nNpc, RB_KEEP, nSide);
    // HP: the engine adds the CON part per level; the hit-die part is ours
    SetMaxHitPoints(oC, GetMaxHitPoints(oC) + nLevel * RB_HitDie(nClass));
    int nXp = RB_XpForLevel(RB_CharLevel(oC));
    if (GetXP(oC) < nXp) SetXP(oC, nXp);
    return nRes;
}

// A run that was cut short leaves the pending bit set; the next area entry or console use calls this to finish it.
int RB_Resume(object oC, int nNpc)
{
    if (RB_MGet(oC, RB_B_PENDING) == 0) return RB_OK_NOCHANGE;
    int nPos;
    for (nPos = 0; nPos < 3; nPos++)
    {
        int nCls = GetClassByPosition(nPos + 1, oC);
        if (nCls != CLASS_TYPE_INVALID && nCls != RB_BitsGet(oC, RB_B_OLDCLASS, 5))
            return RB_Finish(oC, nCls, GetLevelByPosition(nPos + 1, oC), nNpc);
    }
    RB_ClearMarker(oC);                                                        // the swap never happened: nothing to finish
    return RB_OK_NOCHANGE;
}

// Self-test: a handful of table reads against values taken from the game files (prints through k2se.log; no creature needed).
int RB_SelfTest()
{
    int nBad = 0;
    if (RB_Num(RB_GrantStr(3), 116, 2) != 2) nBad++;          // Guardian grants Force Sensitive at class level 2
    if (RB_Num(RB_GrantStr(0), 4, 2) != 1) nBad++;            // Soldier grants Heavy Armor at level 1
    if (RB_PowTier(10) != 6) nBad++;                          // Cure is tier 6
    if (RB_PowerOk(3, 200)) nBad++;                           // base Jedi cannot learn Confusion
    if (!RB_PowerOk(11, 200)) nBad++;
    if (RB_HitDie(3) != 10 || RB_HitDie(4) != 6) nBad++;
    if (RB_XpForLevel(20) != 190000) nBad++;
    if (StringToInt(GetSubString(RB_SlotStr(3), 0, 1)) != 1) nBad++;
    K2SE_Diag("RB", "selftest bad=" + IntToString(nBad));
    return nBad;
}

// ------------------------------------------------------------------------------------------------ script entry (what the console runs)
// The caller runs  ExecuteScript("k2se_rb", oCompanion, nPack)  (synchronous: it returns after this script ends) and then reads the result
// from local booleans 59..61 of the companion (RB_BitsGet(oC, 59, 3) = one of the result codes above; the full line is in k2se.log).
//   nPack = kind + 4*class + 128*level + 8192*pos + 32768*mode + 65536*npc          (npc 15 = no companion data, 12 = the player)
//   kind: 0 convert the class at position pos, 1 add a class, 2 resume an interrupted conversion, 3 self-test only
int RB_Pack(int nKind, int nClass, int nLevel, int nPos, int nMode, int nNpc)
{
    return nKind + 4 * nClass + 128 * nLevel + 8192 * nPos + 32768 * nMode + 65536 * nNpc;
}

void main()
{
    object oC = OBJECT_SELF;
    int nArg = GetRunScriptVar();
    if (nArg < 0) { RB_SelfTest(); return; }
    int nKind = nArg % 4;      nArg = nArg / 4;
    int nClass = nArg % 32;    nArg = nArg / 32;
    int nLevel = nArg % 64;    nArg = nArg / 64;
    int nPos = nArg % 4;       nArg = nArg / 4;
    int nMode = nArg % 2;      nArg = nArg / 2;
    int nNpc = nArg % 16;
    if (nNpc == 15) nNpc = -1;
    int nRes = RB_REFUSED;
    if (nKind == 0) nRes = RB_ConvertClass(oC, nPos, nClass, nLevel, nNpc, nMode);
    else if (nKind == 1) nRes = RB_AddClass(oC, nClass, nLevel, nNpc, RB_SideFor(oC));
    else if (nKind == 2) nRes = RB_Resume(oC, nNpc);
    else { RB_SelfTest(); nRes = RB_OK_NOCHANGE; }
    RB_BitsPut(oC, 59, 3, nRes);
    if (nPos == 3) RB_RepointSkills(oC, nClass, nLevel);      // never taken (pos is 0..2): keeps the optional skill step compiled in the size below
}
