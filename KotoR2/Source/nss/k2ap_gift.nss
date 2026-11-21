// k2ap_gift.nss -- the AP Companion Gift (include file).
//
// A gift is an item (ap_gift, tag ap_gift) that stacks. Using it opens the menu ap_gift: one reply per companion you can pick (condition k2ap_gok), each ending in the
// answer script k2ap_gans with the companion's slot as its script parameter. The answer takes one gift out of the stack and moves that companion's influence by
// +20 or -20: +20 when the gift suits the companion's leaning (the light side or the dark side) with the leaning the Exile has now, -20 when it does not.
// Companions without a leaning of their own (Atton, Mandalore, Kreia, T3-M4) follow the Exile's side instead: +20 for a light-leaning Exile, -20 for a dark-leaning one, so a gift can
// never only push them up and their low-influence conversations stay reachable. Gifts are not part of the seed: the client puts 10 in the Exile's inventory at the start and
// hides 50 in containers of the free-roam areas (client/k2_gift.py).

int K2AP_GiftAmount()
{
    return 20;
}

// 1 = a light side companion, -1 = a dark side one, 0 = no leaning (follows the Exile's side). Slots: 0 Atton, 1 Bao-Dur, 2 Mandalore, 3 G0-T0, 4 Handmaiden, 5 HK-47,
// 6 Kreia, 7 Mira, 8 T3-M4, 9 Visas, 10 Hanharr, 11 the Disciple.
int K2AP_GiftLean(int nSlot)
{
    if (nSlot == 1 || nSlot == 4 || nSlot == 7 || nSlot == 9 || nSlot == 11) return 1;
    if (nSlot == 3 || nSlot == 5 || nSlot == 10) return -1;
    return 0;
}

string K2AP_GiftName(int nSlot)
{
    if (nSlot == 0) return "Atton Rand";
    if (nSlot == 1) return "Bao-Dur";
    if (nSlot == 2) return "Mandalore";
    if (nSlot == 3) return "G0-T0";
    if (nSlot == 4) return "Handmaiden";
    if (nSlot == 5) return "HK-47";
    if (nSlot == 6) return "Kreia";
    if (nSlot == 7) return "Mira";
    if (nSlot == 8) return "T3-M4";
    if (nSlot == 9) return "Visas Marr";
    if (nSlot == 10) return "Hanharr";
    return "the Disciple";
}

// A companion is offered when the player can pick them right now (1 = selectable; -1 = not recruited, 0 = hidden or locked by the story or the seed).
int K2AP_GiftOffered(int nSlot)
{
    if (nSlot < 0 || nSlot > 11) return FALSE;
    return GetNPCSelectability(nSlot) == 1;
}

// The change a gift makes to this companion's influence for this player.
int K2AP_GiftDelta(object oPC, int nSlot)
{
    int nLean = K2AP_GiftLean(nSlot);
    int nLight = GetGoodEvilValue(oPC) >= 50;
    if (nLean == 0)                                              // no leaning: the Exile's own side decides
    {
        if (nLight != 0) return K2AP_GiftAmount();
        return -K2AP_GiftAmount();
    }
    if ((nLean == 1) == (nLight != 0)) return K2AP_GiftAmount();
    return -K2AP_GiftAmount();
}

// One line to the player, in the dispatcher's message box (the box k2se_msg shows custom token 9201).
void K2AP_GiftMessage(object oPC, string sMessage)
{
    SetCustomToken(9201, sMessage);
    AssignCommand(oPC, ActionStartConversation(oPC, "k2se_msg", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}

// The menu: its header is token 9230, the reply for slot n is token 9231 + n and the last reply (close) is token 9243.
void K2AP_GiftMenu(object oPC)
{
    object oGift = GetItemPossessedBy(oPC, "ap_gift");
    int nLeft = 0;
    if (GetIsObjectValid(oGift)) nLeft = GetItemStackSize(oGift);
    SetCustomToken(9230, "Give an AP Companion Gift to whom? Gifts left: " + IntToString(nLeft) + ".");
    int nSlot;
    for (nSlot = 0; nSlot < 12; nSlot++) SetCustomToken(9231 + nSlot, K2AP_GiftName(nSlot));
    SetCustomToken(9243, "Never mind.");
    AssignCommand(oPC, ActionStartConversation(oPC, "ap_gift", FALSE, CONVERSATION_TYPE_CINEMATIC, TRUE));
}

// The answer: one gift is used up and the companion's influence moves.
void K2AP_GiftGive(object oPC, int nSlot)
{
    if (!K2AP_GiftOffered(nSlot)) return;
    object oGift = GetItemPossessedBy(oPC, "ap_gift");
    if (!GetIsObjectValid(oGift))
    {
        DelayCommand(0.5, K2AP_GiftMessage(oPC, "You have no AP Companion Gifts left."));
        return;
    }
    int nStack = GetItemStackSize(oGift);
    if (nStack > 1) SetItemStackSize(oGift, nStack - 1);
    else DestroyObject(oGift);
    int nDelta = K2AP_GiftDelta(oPC, nSlot);
    ModifyInfluence(nSlot, nDelta);
    string sLine;
    if (nDelta > 0) sLine = K2AP_GiftName(nSlot) + " is pleased with the gift: influence +" + IntToString(nDelta) + ".";
    else sLine = K2AP_GiftName(nSlot) + " did not care for the gift: influence " + IntToString(nDelta) + ".";
    DelayCommand(0.5, K2AP_GiftMessage(oPC, sLine));
}
