// k2se.nss -- the K2SE modder-facing include.
//
// Put this in your override folder (or next to nwnnsscomp.exe) and
// #include "k2se" in your script.
//
// -----------------------------------------------------------------------------
// TWO DIFFERENT THINGS LIVE IN THIS FILE
//
// 1. K2SE_Version() works with the STOCK nwscript.nss. It rides on abs(),
//    vanilla routine 77, so it costs no routine ID and is safe to call on a
//    machine with no K2SE installed. ALWAYS gate on it.
//
// 2. Everything below the marked line needs the EXTENDED nwscript.nss shipped
//    with K2SE, because those functions are appended past routine 876.
//    A script that calls them on a machine without K2SE will NOT degrade
//    gracefully -- the VM's out-of-range path returns -2002 and what it does
//    with that is still being characterised. Gate every single call.
// -----------------------------------------------------------------------------

// POC FORK: this install's nwnnsscomp.exe (KotOR Scripting Tool, 2012-era)
// does not support the `const` keyword at all -- confirmed by isolated test
// (plain declarations compile, `const int X = Y;` fails with a syntax
// error). Dropped; NWScript has no real const-correctness to lose here.
int K2SE_PROBE_MAGIC = -1234567890;

// Returns major*10000 + minor*100 + patch, or 0 when K2SE is not installed.
// Safe on a vanilla install; needs no extended header.
int K2SE_Version()
{
    int nResult = abs(K2SE_PROBE_MAGIC);
    if (nResult == 1234567890) return 0;   // plain abs() -> K2SE absent
    return nResult;
}

int K2SE_IsPresent()
{
    return K2SE_Version() != 0;
}

// =============================================================================
// EVERYTHING BELOW REQUIRES THE EXTENDED nwscript.nss
// =============================================================================

// Routine 877. Same value as K2SE_Version(), reached the direct way.
// Present so the round trip through a genuinely new routine ID can be tested.
int K2SE_GetVersion();

// Routines 878/879 -- DEVELOPMENT ONLY self-test plumbing. These exercise the
// multi-argument stack ABI end to end and may be renumbered before the first
// public release; do not build mods against them.
//
// K2SE_SelfTest returns an order-sensitive checksum:
//   nFirst*1000000 + FloatToInt(fSecond*10.0)*10000 + nThird
// K2SE_ReportTest compares and writes one PASS/FAIL line per nTestId into
// k2se.log; returns TRUE on match.
int K2SE_SelfTest(int nFirst, float fSecond, int nThird);
int K2SE_ReportTest(int nTestId, int nExpected, int nActual);

// Routine 880 -- DEVELOPMENT ONLY. Returns sIn unchanged.
//
// An identity function on purpose: it exercises the whole string path (pop,
// CExoString construction, push, and the engine's copy semantics in both
// directions) while keeping a failure unambiguous. If what comes back differs
// from what went in, the string ABI is wrong -- there is nothing else it could
// be. Strings are the first K2SE type whose lifetime the engine shares, so this
// gets its own test rather than riding along in K2SE_SelfTest.
string K2SE_EchoString(string sIn);

// =============================================================================
// Creature queries -- the first K2SE functions meant for real mods.
//
// All read-only, and all return -1 rather than failing the script when the
// creature cannot be resolved. ALWAYS check for -1: it means "K2SE could not
// answer", which is not the same as 0.
//
//     if (!K2SE_IsPresent()) return;
//     int nStr = K2SE_GetAbilityScoreBase(oPC, ABILITY_STRENGTH);
//     if (nStr < 0) return;    // could not resolve -- do not treat as a score
// =============================================================================

// The attribute the creature actually has, before items and effects.
// nAbility is ABILITY_STRENGTH .. ABILITY_CHARISMA (0..5).
int K2SE_GetAbilityScoreBase(object oCreature, int nAbility);

// The skill rank the creature bought, without item or effect modifiers --
// which vanilla GetSkillRank cannot report separately.
int K2SE_GetSkillRankBase(object oCreature, int nSkill);

// TRUE if the creature HAS the feat, as opposed to whether it can use it right
// now. Vanilla GetHasFeat folds in daily uses and so answers a different
// question.
int K2SE_GetFeatAcquired(object oCreature, int nFeat);

// TRUE if the creature knows the Force power, regardless of current Force points.
int K2SE_GetSpellAcquired(object oCreature, int nSpell);

// =============================================================================
// POC FORK NOTICE: this file has been trimmed down from upstream K2SE
// (https://github.com/renanaugustomacena-ux/K2SE) to just the routines this
// proof-of-concept vendors and builds -- fog/movement/FOV/camera/spawner/
// npcvariety (upstream routines 885-908) were dropped, not ported. See
// ../docs/ENGINE_DIFFERENCES.md and ../README.md for the scope and status of
// this fork.
// =============================================================================

// Routine 885 -- THE ARM UNDER TEST. Writes the creature's BASE ability score
// (before items/effects), the TSL write-side counterpart to
// K2SE_GetAbilityScoreBase above.
//
// UNLIKE every routine above this one, the address this calls
// (CSWSCreatureStats::Set*Base, one function per ability -- offsets_generated.h)
// has only ever been confirmed by matching its x86 prologue bytes. It has
// NEVER been exercised live. Its real argument count/calling convention is an
// educated guess (thiscall, one int argument), not a confirmed fact the way
// every read routine above is. A wrong guess here does not just return a wrong
// number -- it can write through an unconfirmed address with an unconfirmed
// stack shape, which is exactly the "write corrupts a save" risk this
// project's upstream docs warn about. Test on a disposable save only.
//
// Returns TRUE if the write call completed without faulting (NOT proof the
// value is actually correct -- read it back with K2SE_GetAbilityScoreBase to
// confirm). FALSE if the creature/stats pointer could not be resolved, or the
// write itself faulted (caught, logged, and swallowed rather than crashing
// the game).
int K2SE_SetAbilityScoreBase(object oCreature, int nAbility, int nValue);

// Routine 886 -- writes "[sTag] sMsg" to k2se.log (%LOCALAPPDATA%\K2SE\k2se.log)
// and returns TRUE. Each line is written to the file immediately, so it survives
// a crash that on-screen text would not. Use it to log progress BEFORE a risky call.
int K2SE_Diag(string sTag, string sMsg);

// =============================================================================
// Research probes (887-891). Field-agnostic tools for finding and checking struct
// offsets inside a running game. nArea picks the struct the offset is relative to:
// 0 = CSWSCreature, 1 = CSWSCreatureStats. All failures are logged to k2se.log.
// =============================================================================

// Routine 887 -- reads "key=value" from %LOCALAPPDATA%\K2SE\config.txt on EVERY call
// (decimal or 0x hex), returning nDefault if the key is absent. Lets one compiled
// test script run different stages: edit the file, reload the save, no recompile
// and no game-folder write.
int K2SE_ConfigInt(string sKey, int nDefault);

// Routine 888 -- READ-ONLY. Value of a 1, 2 or 4 byte little-endian field at
// offset nOffset from the chosen struct. Returns -2147483647 when the read failed
// (the log line says why). nArea 2 is ABSOLUTE mode: nOffset is itself the address
// (oCreature is ignored), for following a pointer you read earlier, e.g. the skill
// rank array at stats+0x174. Bad addresses fail safely.
int K2SE_ReadMem(object oCreature, int nArea, int nOffset, int nWidth);

// Routine 889 -- writes the first nSize bytes (max 1 MB) of the chosen struct to
// %LOCALAPPDATA%\K2SE\dumps\<sLabel>.bin so two states can be diffed offline.
// Returns bytes written, or -1.
int K2SE_DumpMem(object oCreature, int nArea, int nSize, string sLabel);

// Routine 890 -- the chosen struct's base address as an integer (0 if unresolved),
// for external tools that attach to the process.
int K2SE_GetAddress(object oCreature, int nArea);

// Routine 891 -- DANGEROUS raw write of a 1, 2 or 4 byte value, for validating a
// candidate offset on a throwaway save. REFUSED unless config.txt contains
// allow_memwrite=1 (a file outside the game folder that a shipped script cannot
// create). Offsets above 0x3000 and non-writable pages are always refused.
// Returns 1 if written; the log records the old and new value.
int K2SE_WriteMem(object oCreature, int nArea, int nOffset, int nWidth, int nValue);

// -----------------------------------------------------------------------------
// Shipped writers (892-900). Each validates its arguments and returns 1 changed, 0 refused, -1 could not resolve.
// -----------------------------------------------------------------------------
// Sets the race: 5 = RACIAL_TYPE_DROID, 6 = RACIAL_TYPE_HUMAN (anything else is refused). A droid has no Force pool, so
// changing a Jedi to droid zeroes the maximum Force and back to human restores it. Returns 1 changed, 0 refused, -1 unresolved.
int K2SE_SetRace(object oCreature, int nRace);

// Sets a creature's own credits (0..999999999), what vanilla GetGold(oCreature) reads for a non-player. Vanilla can only
// add (GiveGoldToCreature); TakeGoldFromCreature does nothing. Returns 1 / 0 / -1 as for K2SE_SetRace.
int K2SE_SetCreatureCredits(object oCreature, int nAmount);

// Sets the player's credits (0..999999999), what GetGold(GetFirstPC()) reads. Returns 1 / 0 / -1.
int K2SE_SetPartyCredits(int nAmount);

// Sets the extra saving throw bonus: nSave 0 = Fortitude, 1 = Will, 2 = Reflex; nValue 0..100. It is added to the class
// saves, so GetFortitudeSavingThrow etc. rise by the difference. Returns 1 / 0 / -1.
int K2SE_SetSaveBonus(object oCreature, int nSave, int nValue);

// Sets the level of the class in slot 0..2 (slot must hold a class; level 0..50; the base class keeps at least 1).
// Hit dice, max Force and HP follow. It grants NO feats or powers; use the Level Up screen, GrantFeat or GrantSpell for
// those. Returns 1 / 0 / -1.
int K2SE_SetClassLevel(object oCreature, int nSlot, int nLevel);

// Replaces the class in an occupied slot with another (CLASS_TYPE ids 0..16 except the cut Bounty Hunter, 10) and refuses a
// class the creature already has. Max Force and the class level follow at once; the old class's feats and powers stay and the
// new class's are not granted. Returns 1 / 0 / -1.
int K2SE_SetClassId(object oCreature, int nSlot, int nClass);

// Removes the LAST class (slot 1 or 2; never the base class): clears its id, level and power list and lowers the class count.
// Its feats stay (remove them with K2SE_RemoveFeat). Returns 1 / 0 / -1.
int K2SE_RemoveClass(object oCreature, int nSlot);

// Removes a feat the creature has acquired. Returns 1 removed, 0 not present, -1 unresolved.
int K2SE_RemoveFeat(object oCreature, int nFeat);

// Removes a known Force power (every class slot's list). Returns 1 removed, 0 not present, -1 unresolved.
int K2SE_RemovePower(object oCreature, int nSpell);

// Sets the rank bought in one skill: nSkill 0..7 (computer use, demolitions, stealth, awareness, persuade, repair, security, treat injury), nRank 0..100.
// This is the base rank before items and effects (what K2SE_GetSkillRankBase reads), written absolutely, so traps and boosts do not depend on what the
// relative AdjustCreatureAttributes did before. Returns 1 changed, 0 refused, -1 could not resolve.
int K2SE_SetSkillRank(object oCreature, int nSkill, int nRank);

// ---- Archipelago delivery transport (files under %LOCALAPPDATA%\K2SEp\) ----

// Integer value of "key=value" in ap\inbox.txt (decimal or 0x hex), or nDefault if the file or key is absent.
int K2SE_InboxInt(string sKey, int nDefault);

// Text after "key=" in ap\inbox.txt (up to 200 characters), "" if absent.
string K2SE_InboxStr(string sKey);

// Appends "<seq>|<sLine>" to ap\outbox.txt for the client to read. Returns 1 on success.
int K2SE_OutboxPut(string sLine);

// Small in-memory store that lives until the game process ends (256 keys, key under 64 and value under 512 characters). Returns 1 on success.
int K2SE_MemSet(string sKey, string sValue);

// Value stored with K2SE_MemSet, or "" if none.
string K2SE_MemGet(string sKey);

// -----------------------------------------------------------------------------
// Usage pattern -- copy this shape:
//
//   #include "k2se"
//
//   void main()
//   {
//       if (!K2SE_IsPresent()) return;    // degrade silently, never crash
//       // ... K2SE-only calls here ...
//   }
// -----------------------------------------------------------------------------
