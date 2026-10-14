// Story-gate helpers shared by every gate script (scripts/patch_story_gates.py).
//
// A gate is "the player holds at least N progression items of one family". Progression items are
// plot items with their own tags (ap_tk_<family><1..3>), delivered by the
// ordinary give_item: path, so the count is simply how many of the three
// tags the PC holds. No global or local variable is involved, which keeps
// the check correct across saves and reloads.
//
// ApFamilySize() is the number of progression items each family contains this seed;
// ApNeed() caps a gate's step so a smaller family can still open every gate.

#include "kse"

int ApFamilySize()
{
    return 3;
}

int ApNeed(int nStep)
{
    int nSize = ApFamilySize();
    if (nStep > nSize) return nSize;
    return nStep;
}

int ApTokenCount(string sFamily)
{
    object oPC = GetFirstPC();
    int nHeld = 0;
    int i;
    for (i = 1; i <= 3; i++)
    {
        if (GetIsObjectValid(GetItemPossessedBy(oPC, "ap_tk_" + sFamily + IntToString(i)))) nHeld++;
    }
    return nHeld;
}

string ApFamilyKey(string sFamilyName)
{
    if (sFamilyName == "Star Forge") return "fin";
    return GetStringLowerCase(GetStringLeft(sFamilyName, 3));
}

string ApFamilyName(string sKey)
{
    if (sKey == "tar") return "Taris";
    if (sKey == "dan") return "Dantooine";
    if (sKey == "tat") return "Tatooine";
    if (sKey == "kas") return "Kashyyyk";
    if (sKey == "man") return "Manaan";
    if (sKey == "kor") return "Korriban";
    if (sKey == "unk") return "Unknown World";
    return "Star Forge";
}

// The story is a chain, so a family's gates also need the family before it to be complete (all of its items). Dantooine needs Taris; each of the four
// open-world planets needs Taris and Dantooine; the Unknown World needs all four open-world families (which already implies the two before them,
// since those planets' own gates need them); the Star Forge needs the Unknown World. Returns the key of the first family that is not complete, or ""
// when the chain is satisfied. This matches the Archipelago logic's planet baselines (worlds/kotor/StoryGates.py), so shuffled doors cannot open a
// later phase early.
string ApMissingPrerequisite(string sFamily)
{
    int nFull = ApNeed(3);
    if (sFamily == "dan" || sFamily == "tat" || sFamily == "kas" || sFamily == "man" || sFamily == "kor")
    {
        if (ApTokenCount("tar") < nFull) return "tar";
    }
    if (sFamily == "tat" || sFamily == "kas" || sFamily == "man" || sFamily == "kor")
    {
        if (ApTokenCount("dan") < nFull) return "dan";
    }
    if (sFamily == "unk")
    {
        if (ApTokenCount("tat") < nFull) return "tat";
        if (ApTokenCount("kas") < nFull) return "kas";
        if (ApTokenCount("man") < nFull) return "man";
        if (ApTokenCount("kor") < nFull) return "kor";
    }
    if (sFamily == "fin")
    {
        if (ApTokenCount("unk") < nFull) return "unk";
    }
    return "";
}

int ApGateOpen(string sFamily, int nStep)
{
    if (ApMissingPrerequisite(sFamily) != "") return FALSE;
    return ApTokenCount(sFamily) >= ApNeed(nStep);
}

// Ends the cooldown a dialog-starter gate sets so one click gives one spoken line (DelayCommand needs a void action).
void ApGateCooldownOff()
{
    KSE_SetData("ap_gate_cd", "0");
}

// For a dialog-starter gate that returned FALSE: waits (checking once a second, for up to a minute) until the player is out of any conversation, e.g.
// the ordinary greeting the dialog fell back to, then has the player say the one-line dialog ap_gate_msg. The text is already in custom token 901.
// If the conversation start does not work from inside this function, the line is simply not shown.
void ApGateSayWhenFree(int nTries)
{
    object oPC = GetFirstPC();
    if (GetIsInConversation(oPC) && nTries < 60)
    {
        DelayCommand(1.0, ApGateSayWhenFree(nTries + 1));
        return;
    }
    DelayCommand(0.5, AssignCommand(oPC, ActionStartConversation(oPC, "ap_gate_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE)));
}

// The text a closed gate shows. It names the earlier family when that is what is missing, otherwise this family. Gate scripts that can start a
// conversation put it into custom token 901 (SetCustomToken(901, ApGateText(...))) and start the one-line dialog ap_gate_msg, which has the
// player speaking it; the floating text of ApGateMsg below is not reliably shown by the engine.
string ApGateText(string sFamilyName, int nStep)
{
    string sKey = ApFamilyKey(sFamilyName);
    string sMissing = ApMissingPrerequisite(sKey);
    string sShown = sFamilyName;
    int nNeed = ApNeed(nStep);
    if (sMissing != "")
    {
        sShown = ApFamilyName(sMissing);
        nNeed = ApNeed(3);
    }
    string sNoun = " Progression items";
    if (nNeed == 1) sNoun = " Progression item";
    return "I need " + IntToString(nNeed) + " " + sShown + sNoun + " before I can go on.";
}

void ApGateMsg(string sFamilyName, int nStep)
{
    string sKey = ApFamilyKey(sFamilyName);
    string sMissing = ApMissingPrerequisite(sKey);
    string sShown = sFamilyName;
    int nNeed = ApNeed(nStep);
    string sVia = "";
    if (sMissing != "")
    {
        // An earlier part of the story is incomplete: name that family and its full count, not this one.
        sShown = ApFamilyName(sMissing);
        nNeed = ApNeed(3);
        sKey = sMissing;
        sVia = "|via=" + sFamilyName;
    }
    // Logged so a test run can see which gate held (log code 191; the client ignores the line).
    KSE_Diag(191, "AP|GATE|closed|" + sShown + "|need=" + IntToString(nNeed) + "|held=" + IntToString(ApTokenCount(sKey)) + sVia);
    FloatingTextStringOnCreature(ApGateText(sFamilyName, nStep), GetFirstPC(), FALSE);
}

// For a gate that is decided in the middle of a conversation (a node script or a link condition), where a conversation cannot be
// started: the player says the closed-gate line once the running conversation has ended. The condition can be evaluated several
// times for one click, so a short cooldown keeps it to one line.
void ApGateSayLater(string sFamilyName, int nStep)
{
    if (KSE_GetData("ap_gate_cd") == "1") return;
    KSE_SetData("ap_gate_cd", "1");
    DelayCommand(4.0, ApGateCooldownOff());
    SetCustomToken(901, ApGateText(sFamilyName, nStep));
    DelayCommand(0.6, ApGateSayWhenFree(0));
}
