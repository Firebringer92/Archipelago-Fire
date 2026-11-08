// k2se_routines.nss -- the K2SE extended script routines (ids 877 and up), declared after the game's own routines (the last of those is id 876,
// RebuildPartyTable). Appended to the game's nwscript.nss to make the extended nwscript.nss the compiler uses (tools/k2compile.py). Ours; the game's file
// is read from the player's install and never stored in the project.

// ============================================================
// K2SE extended routines. Appended past the last vanilla entry
// (RebuildPartyTable = id 876). nwnnsscomp assigns ids positionally, so order
// here IS the id -- never insert, only append.
// ============================================================
// 877:
int K2SE_GetVersion();
// 878:
int K2SE_SelfTest(int nFirst, float fSecond, int nThird);
// 879:
int K2SE_ReportTest(int nTestId, int nExpected, int nActual);
// 880:
string K2SE_EchoString(string sIn);
// 881:
int K2SE_GetAbilityScoreBase(object oCreature, int nAbility);
// 882:
int K2SE_GetSkillRankBase(object oCreature, int nSkill);
// 883:
int K2SE_GetFeatAcquired(object oCreature, int nFeat);
// 884:
int K2SE_GetSpellAcquired(object oCreature, int nSpell);
// 885:
int K2SE_SetAbilityScoreBase(object oCreature, int nAbility, int nValue);
// 886:
int K2SE_Diag(string sTag, string sMsg);
// 887:
int K2SE_ConfigInt(string sKey, int nDefault);
// 888:
int K2SE_ReadMem(object oCreature, int nArea, int nOffset, int nWidth);
// 889:
int K2SE_DumpMem(object oCreature, int nArea, int nSize, string sLabel);
// 890:
int K2SE_GetAddress(object oCreature, int nArea);
// 891:
int K2SE_WriteMem(object oCreature, int nArea, int nOffset, int nWidth, int nValue);
// 892:
int K2SE_SetRace(object oCreature, int nRace);
// 893:
int K2SE_SetCreatureCredits(object oCreature, int nAmount);
// 894:
int K2SE_SetPartyCredits(int nAmount);
// 895:
int K2SE_SetSaveBonus(object oCreature, int nSave, int nValue);
// 896:
int K2SE_SetClassLevel(object oCreature, int nSlot, int nLevel);
// 897:
int K2SE_SetClassId(object oCreature, int nSlot, int nClass);
// 898:
int K2SE_RemoveClass(object oCreature, int nSlot);
// 899:
int K2SE_RemoveFeat(object oCreature, int nFeat);
// 900:
int K2SE_RemovePower(object oCreature, int nSpell);
// 901:
int K2SE_SetSkillRank(object oCreature, int nSkill, int nRank);
// 902:
int K2SE_InboxInt(string sKey, int nDefault);
// 903:
string K2SE_InboxStr(string sKey);
// 904:
int K2SE_OutboxPut(string sLine);
// 905:
int K2SE_MemSet(string sKey, string sValue);
// 906:
string K2SE_MemGet(string sKey);
