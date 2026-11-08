// k2ap_master.nss -- the Master gates NAR3 (Zez-Kai Ell), DXN3 (Kavar) and DAN2 (Vrook): the Jedi count waits for the token (include file).
//
// Each Master's conversation adds 1 to the global 000_Jedi_Found at nodes that the client points at nss/ap_jedi_inc.nss (client/k2_dialogues.py patches the three conversations in their modules; the game's shared script a_global_inc is left alone). The conversation is
// never held back (a Master is spent after it, and the Onderon palace does not let the player leave); only the +1 is. A held +1 is remembered (a bit in the
// player's local number 7) and applied by the dispatcher's tick (K2AP_MasterCatchUp) as soon as the gate opens. The count therefore reaches 4, which the game
// needs for the Enclave, only when the three tokens (and the Vash gate) are in. The game's own equality tests on the count see the same values, later.
//
// The numbers below are those of data/gates.json (a test compares them).

#include "k2ap_gate"

// The gate of the Master a module belongs to, or "" (301NAR/303NAR/351NAR Zez-Kai Ell, 503OND/506OND Kavar, 602DAN/604DAN Vrook).
string K2AP_MasterGateFor(string sModule)
{
    if (sModule == "301nar" || sModule == "303nar" || sModule == "351nar") return "NAR3";
    if (sModule == "503ond" || sModule == "506ond") return "DXN3";
    if (sModule == "602dan" || sModule == "604dan") return "DAN2";
    return "";
}

int K2AP_MasterIndex(string sGate)
{
    if (sGate == "NAR3") return 0;
    if (sGate == "DXN3") return 1;
    return 2;
}

string K2AP_MasterFamily(string sGate)
{
    if (sGate == "NAR3") return "nar";
    if (sGate == "DXN3") return "dxn";
    return "dan";
}

string K2AP_MasterFamilyName(string sGate)
{
    if (sGate == "NAR3") return "Nar Shaddaa";
    if (sGate == "DXN3") return "Dxun/Onderon";
    return "Dantooine";
}

int K2AP_MasterNeeded(string sGate)
{
    if (sGate == "DAN2") return 2;
    return 3;
}

int K2AP_MasterGateOpen(string sGate)
{
    return K2AP_GateOpenQuiet(sGate, K2AP_MasterFamily(sGate), K2AP_MasterNeeded(sGate));
}

int K2AP_MasterPending(object oPC, string sGate)
{
    return (GetLocalNumber(oPC, 7) >> K2AP_MasterIndex(sGate)) & 1;
}

void K2AP_MasterSetPending(object oPC, string sGate, int nOn)
{
    int nMask = 1 << K2AP_MasterIndex(sGate);
    int nCur = GetLocalNumber(oPC, 7);
    if (nOn != 0) nCur = nCur | nMask;
    else nCur = nCur & (255 - nMask);
    SetLocalNumber(oPC, 7, nCur);
}

// The meeting happened but the token has not arrived: remember the +1.
void K2AP_MasterHold(string sGate)
{
    object oPC = GetFirstPC();
    K2AP_MasterSetPending(oPC, sGate, 1);
    K2SE_OutboxPut("GB|" + sGate + "|" + IntToString(K2AP_Tokens(K2AP_MasterFamily(sGate))) + "|" + IntToString(K2AP_MasterNeeded(sGate)) + "|count");
    FloatingTextStringOnCreature("This meeting will count for the Jedi Council once you have " + IntToString(K2AP_MasterNeeded(sGate)) + " " +
                                 K2AP_MasterFamilyName(sGate) + " Progression item(s).", oPC, FALSE);
}

// Applies every held +1 whose gate is open now. Called from the dispatcher's tick. Returns how many were applied.
int K2AP_MasterCatchUp(object oPC)
{
    if (GetLocalNumber(oPC, 7) == 0) return 0;
    int nApplied = 0;
    string sGate;
    int i;
    for (i = 0; i < 3; i++)
    {
        if (i == 0) sGate = "NAR3";
        else if (i == 1) sGate = "DXN3";
        else sGate = "DAN2";
        if (K2AP_MasterPending(oPC, sGate) != 0 && K2AP_MasterGateOpen(sGate))
        {
            SetGlobalNumber("000_Jedi_Found", GetGlobalNumber("000_Jedi_Found") + 1);
            K2AP_MasterSetPending(oPC, sGate, 0);
            K2SE_OutboxPut("GP|" + sGate + "|count");
            nApplied++;
        }
    }
    if (nApplied > 0) FloatingTextStringOnCreature("Your meeting with the Master now counts for the Jedi Council.", oPC, FALSE);
    return nApplied;
}
