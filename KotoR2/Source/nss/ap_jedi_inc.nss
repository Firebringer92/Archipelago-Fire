// ap_jedi_inc.nss -- the script the three Masters' conversations run at their "+1 on the Jedi count" nodes (the client points the nodes of the dialogues zezkaiel,
// kavar and vrook at it, client/k2_dialogues.py). It does what the game's shared script a_global_inc does (SetGlobalNumber(global, global + parameter 1)), except
// that while the Master's gate is closed the +1 is held back and remembered (nss/k2ap_master.nss). Nothing else in the game runs this script.
#include "k2ap_master"

void main()
{
    string sGlobal = GetScriptStringParameter();
    int nAdd = GetScriptParameter(1);
    string sGate = K2AP_MasterGateFor(GetStringLowerCase(GetModuleName()));
    if (sGate != "")
    {
        if (!K2AP_MasterGateOpen(sGate))
        {
            K2AP_Trace("ap_jedi_inc", "the Jedi count +" + IntToString(nAdd) + " is held back by " + sGate);
            K2AP_MasterHold(sGate);
            return;
        }
        K2AP_Trace("ap_jedi_inc", "the Jedi count +" + IntToString(nAdd) + " counts (" + sGate + " open)");
    }
    SetGlobalNumber(sGlobal, GetGlobalNumber(sGlobal) + nAdd);
}
