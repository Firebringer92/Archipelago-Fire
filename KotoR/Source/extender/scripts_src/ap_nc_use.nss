#include "kse"

void main()
{
    KSE_Diag(206, "AP|NCTERM|used");
    ActionStartConversation(GetLastUsedBy(), "", FALSE, CONVERSATION_TYPE_COMPUTER, FALSE);
}
