// kse.nss -- KOTOR Script Extender author-facing API.
//
// Usage: put this file where your compiler finds includes, then in your script:
//     #include "kse"
//     int m = KSE_Max(a, b);
//     int f = KSE_BitAnd(flags, MASK);
//
// IMPORTANT -- the #include must sit at TOP LEVEL, outside any function. Script
// editors (e.g. the KotOR Scripting Tool) often start a new file with an empty
// `void main() { }`; pasting a test script INSIDE that body puts the #include
// inside a function, and nwnnsscomp then expands these declarations where
// declarations are illegal. The symptom is misleading: dozens of
//     kse.nss(22): Error: Syntax error at "("
// errors blaming THIS file, starting at its first declaration. Nothing is wrong
// with this file in that case -- the including script has an extra wrapping
// `void main() { ... }` around everything. Delete the wrapper.
//
// Requires KSE installed (the proxy DLL). Without KSE, the underlying calls reach
// unimplemented engine slots, which return ZERO to the script. That is exactly what
// makes the one-line guard below reliable.
//
// So the guard is one line, and it is concrete rather than advisory:
//
//     if (KSE_GetVersion() <= 0) return;   // KSE absent, or too old for this function
//
// USE <= 0, NOT == 0, and the difference is the whole point of a version handshake.
// There are THREE cases, not two:
//
//     no KSE at all        -> 0             an unimplemented slot returns 0
//     an OLDER KSE         -> -559038737    the function exists here but this build
//                                           does not carry it
//     this KSE             -> 10000         major*10000 + minor*100 + patch
//
// `== 0` PASSES an older KSE, because -559038737 is not zero -- and a script would then
// proceed believing KSE is present. Any value <= 0 means "cannot rely on KSE".
//
// Check it ONCE at script entry, before any other KSE call. Ordered comparison works, so
// the strongest form states what you actually need:
//
//     if (KSE_GetVersion() < 10200) return;   // needs 1.2.0 or later -- covers both cases
//
// Everything below the "internal" line is the transport. Call only the KSE_* functions;
// do not call the SWMG_* names or the _kse_* helpers directly.
//
// All functions are integer-only (KOTOR ints are 32-bit signed). Shift counts are
// masked to 0..31. IPow/Sqr wrap on overflow (32-bit). PosMod is the non-negative
// (Euclidean) remainder. Isqrt is floor(sqrt). A domain error (e.g. PosMod by 0,
// Isqrt of a negative) returns the sentinel -559038737.

// Every function below requires the KSE DLL. Guard once at script entry:
//     if (KSE_GetVersion() <= 0) return;   // absent, or too old for this function

// ---- bitwise CONVENIENCE helpers ----
// NOTE: KOTOR NWScript already has native bitwise operators (& | ^ ~ << >>), so
// you can usually just write `a & b` directly. These wrappers are kept for
// convenience and back-compat; they are not filling a gap.
int KSE_BitAnd(int a, int b);   // a & b
int KSE_BitOr (int a, int b);   // a | b
int KSE_BitXor(int a, int b);   // a ^ b
int KSE_BitNot(int a);          // ~a
int KSE_Shl   (int a, int n);   // a << n   (n masked 0..31)
int KSE_Shr   (int a, int n);   // a >> n   arithmetic (sign-preserving)
int KSE_UShr  (int a, int n);   // a >> n   logical (zero-fill)

// ---- integer math CONVENIENCE helpers ----
// Most of these can be written as a few lines of ordinary NWScript, and KOTOR has
// native sqrt/pow/abs. Kept for convenience, not because the language cannot do them.
int KSE_Min   (int a, int b);
int KSE_Max   (int a, int b);
int KSE_Clamp (int v, int lo, int hi);
int KSE_Sign  (int a);          // -1, 0, or 1
int KSE_PosMod(int a, int b);   // non-negative modulo; b==0 -> sentinel
int KSE_IPow  (int base, int exp); // integer power; exp<0 -> 0; wraps on overflow
int KSE_Isqrt (int a);          // floor(sqrt(a)); a<0 -> sentinel
int KSE_Sqr   (int a);          // a*a (wraps on overflow)
int KSE_PopCount(int a);        // number of set bits in the 32-bit value

// ---- strings ----
// KSE_StrTest returns "KSE:reversed:" + the reverse of its input
// (e.g. "KSE" -> "KSE:reversed:ESK"). A round-trip helper: it proves KSE can read a
// string argument and return a string.
string KSE_StrTest(string s);

// ---- arbitrary-key data store ----
// Storage KOTOR fundamentally lacks: unlimited, arbitrarily-NAMED key/value pairs.
// The game's own globals are a fixed pre-declared catalogue; these keys are any
// string you invent at runtime, with no catalogue and no pre-declaration.
//
// LIFETIME: the store is in-DLL memory that lives for the game process only. A
// value set and read back in the SAME session round-trips; across a game restart
// the store is EMPTY -- there is no save/disk persistence.
//
// BOUNDS: up to 256 keys; keys < 128 and values < 512 characters. A set past a cap
// returns KSE_DS_ERR (below) and logs; it does not crash or store partial data.
int    KSE_DS_ERR();                          // the cap/mismatch sentinel (-559038737)
int    KSE_SetData(string key, string val);   // store a string; 1 ok / KSE_DS_ERR() on cap
string KSE_GetData(string key);               // missing key or wrong type -> "" (empty)
int    KSE_SetInt (string key, int val);      // store an int; 1 ok / KSE_DS_ERR() on cap
int    KSE_GetInt (string key);               // missing key or wrong type -> 0
int    KSE_HasData(string key);               // 1 if the key exists (any type), else 0
int    KSE_DeleteData(string key);            // 1 if the key existed and was removed, else 0

// ---- engine calls (KSE asks the ENGINE to do the work) ----
// KSE_EngineStrLen returns the length of s, computed by the game engine's own
// string routine rather than by KSE. Its answer always equals the stock
// GetStringLength(s). Returns -559038737 if the engine's answer failed KSE's
// cross-check.
int    KSE_EngineStrLen(string s);

// ---- KOTOR 2 functions brought to KOTOR 1 ----
// TSL declares these; K1 does not. KSE exposes them by calling engine code K1
// already contains.
//
// KSE_GetFeatAcquired is TSL's GetFeatAcquired: TRUE if oCreature has ACQUIRED
// nFeat, whether or not it is currently usable. It is NOT the same as K1's stock
// GetHasFeat, which is "acquired AND usable" -- the engine uses two different
// functions for these. So GetHasFeat(f) implies KSE_GetFeatAcquired(f), but a
// feat that is acquired yet unusable reads TRUE here and FALSE from GetHasFeat.
// Returns 0 for a non-creature or an invalid object, matching GetHasFeat.
int    KSE_GetFeatAcquired(int nFeat, object oCreature = OBJECT_SELF);

// ---- (removed) KSE_GrantFeat / KSE_GrantFeatPersistent -----------------------
// These earlier feat-grant functions are gone: neither reached the save file. Use
// KSE_GrantFeatArrayA (below), which writes the array the save is genuinely built
// from. They were removed rather than left in place so a broken persistence route
// does not sit beside a working one.

// ---- creature stats ----
// KSE_AdjustCreatureSkills changes a creature's BASE skill rank by nAmount, the
// same slot K1's own GetSkillRank reads. TSL declares this; K1 does not.
// The result is clamped to 0..127. Out-of-range skills, non-creature targets, or
// any unresolvable engine state cause KSE to REFUSE (no write) and log an anomaly.
// NOTE: this changes save state -- test on a throwaway save.
void KSE_AdjustCreatureSkills(object oObject, int nSkill, int nAmount);

// ---- saving throws ----
// TSL declares the three Modify*SavingThrowBase functions; K1 does not. These
// change the BASE saving-throw byte the engine's own GetFortitudeSavingThrow /
// GetReflexSavingThrow / GetWillSavingThrow read back, so a +N change moves the
// stock reader by exactly +N. KSE_GetSavingThrowBase is a KSE addition (neither
// game has it) so scripts can read-modify-write.
// Values clamp to 0..127. An invalid save selector or a non-creature target causes
// KSE to REFUSE (no write) and log an anomaly; the reader returns -559038737.
// NOTE: writes change save state -- throwaway save.
int KSE_SAVE_FORTITUDE();
int KSE_SAVE_REFLEX_();
int KSE_SAVE_WILL_();
void KSE_ModifyFortitudeSavingThrowBase(object oObject, int nAmount);
void KSE_ModifyReflexSavingThrowBase(object oObject, int nAmount);
void KSE_ModifyWillSavingThrowBase(object oObject, int nAmount);
int  KSE_GetSavingThrowBase(object oObject, int nSave);

// ============================ internal (do not call) ========================
// Opcodes -- MUST match the DLL.
int KSE_OP_AND()     { return 1;  }
int KSE_OP_OR()      { return 2;  }
int KSE_OP_XOR()     { return 3;  }
int KSE_OP_NOT()     { return 4;  }
int KSE_OP_SHL()     { return 5;  }
int KSE_OP_SHR()     { return 6;  }
int KSE_OP_USHR()    { return 7;  }
int KSE_OP_MIN()     { return 8;  }
int KSE_OP_MAX()     { return 9;  }
int KSE_OP_CLAMP()   { return 10; }
int KSE_OP_SIGN()    { return 11; }
int KSE_OP_POSMOD()  { return 12; }
int KSE_OP_IPOW()    { return 13; }
int KSE_OP_ISQRT()   { return 14; }
int KSE_OP_SQR()     { return 15; }
int KSE_OP_POPCOUNT(){ return 16; }
int KSE_OP_REPORT()  { return 17; }

// Transport: these two stock routine names are the slots KSE claims. The engine
// leaves them unimplemented; KSE routes them to its handler. The object
// argument is a required-by-signature placeholder KSE discards.
int _kse_push(int x)  { return SWMG_GetGunBankDamage(OBJECT_INVALID, x); }  // ACTION 627
int _kse_eval(int op) { return SWMG_GetGunBankTarget(OBJECT_INVALID, op); } // ACTION 631

int KSE_BitAnd(int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_AND()); }
int KSE_BitOr (int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_OR()); }
int KSE_BitXor(int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_XOR()); }
int KSE_BitNot(int a)                { _kse_push(a);               return _kse_eval(KSE_OP_NOT()); }
int KSE_Shl   (int a, int n)         { _kse_push(a); _kse_push(n); return _kse_eval(KSE_OP_SHL()); }
int KSE_Shr   (int a, int n)         { _kse_push(a); _kse_push(n); return _kse_eval(KSE_OP_SHR()); }
int KSE_UShr  (int a, int n)         { _kse_push(a); _kse_push(n); return _kse_eval(KSE_OP_USHR()); }
int KSE_Min   (int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_MIN()); }
int KSE_Max   (int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_MAX()); }
int KSE_Clamp (int v, int lo, int hi){ _kse_push(v); _kse_push(lo); _kse_push(hi); return _kse_eval(KSE_OP_CLAMP()); }
int KSE_Sign  (int a)                { _kse_push(a);               return _kse_eval(KSE_OP_SIGN()); }
int KSE_PosMod(int a, int b)         { _kse_push(a); _kse_push(b); return _kse_eval(KSE_OP_POSMOD()); }
int KSE_IPow  (int base, int exp)    { _kse_push(base); _kse_push(exp); return _kse_eval(KSE_OP_IPOW()); }
int KSE_Isqrt (int a)                { _kse_push(a);               return _kse_eval(KSE_OP_ISQRT()); }
int KSE_Sqr   (int a)                { _kse_push(a);               return _kse_eval(KSE_OP_SQR()); }
int KSE_PopCount(int a)              { _kse_push(a);               return _kse_eval(KSE_OP_POPCOUNT()); }

// String transport. Two more stock routine slots KSE claims:
//   _kse_pushstr -> ACTION 632: KSE reads and stashes the string; object/int are
//                   placeholders.
//   _kse_streval -> ACTION 583: KSE returns "KSE:reversed:" + the reverse of the
//                   stashed string.
void   _kse_pushstr(string s) { SWMG_SetGunBankBulletModel(OBJECT_INVALID, 0, s); }
string _kse_streval()         { return SWMG_GetLastEvent(); }

string KSE_StrTest(string s)  { _kse_pushstr(s); return _kse_streval(); }

// Data-store transport. Four more stock routine slots KSE claims. A call stages its
// operands (string key, then a string or int value) with the push helpers, then
// applies an opcode with an eval helper. Opcodes MUST match the DLL.
void   _kse_ds_pushs(string s) { SWMG_SetGunBankGunModel(OBJECT_INVALID, 0, s); }
void   _kse_ds_pushi(int v)    { SWMG_SetNumLoops(OBJECT_INVALID, v); }
int    _kse_ds_eval_i(int op)  { return SWMG_IsGunBankTargetting(OBJECT_INVALID, op); }
string _kse_ds_getdata()       { return SWMG_GetLastEventModelName(); }

int    KSE_DS_ERR()  { return -559038737; }   // 0xDEADBEEF signed

int KSE_SetData(string key, string val) { _kse_ds_pushs(key); _kse_ds_pushs(val); return _kse_ds_eval_i(1); }
string KSE_GetData(string key)          { _kse_ds_pushs(key); return _kse_ds_getdata(); }
int KSE_SetInt(string key, int val)     { _kse_ds_pushs(key); _kse_ds_pushi(val);  return _kse_ds_eval_i(2); }
int KSE_GetInt(string key)              { _kse_ds_pushs(key); return _kse_ds_eval_i(3); }
int KSE_HasData(string key)             { _kse_ds_pushs(key); return _kse_ds_eval_i(4); }
int KSE_DeleteData(string key)          { _kse_ds_pushs(key); return _kse_ds_eval_i(5); }

// The version handshake, the build id, and KSE_ERRNO.
//
// KSE_GetVersion() -- 0 MEANS ABSENT. An unimplemented slot returns 0 to the caller,
// so a build that does not carry this function answers 0 by itself. KSE never
// returns 0 when present.
//
// KSE_BuildId() answers a DIFFERENT question: which ARTIFACT, not which API. Two
// different builds can report the same version number; the build id tells them apart.
//
// KSE_ERRNO() answers "why could this call not happen". NARROW BY DESIGN: refused by a
// guard, host absent, version mismatch. Never "your argument was wrong" -- that is a
// programming error and belongs in the log, and mixing the two would teach you to check
// this for the wrong reasons.
//
// FOOTGUN, stated as one rather than left as a convention: KSE_GetVersion() CLEARS the
// errno. Call it first, then the operation, then KSE_ERRNO(). Get the order wrong -- an
// operation, then a version check, then KSE_ERRNO -- and you read a CLEARED code and
// conclude nothing went wrong. The failure is silent and looks like success.
int KSE_OP_VERSION()   { return 202; }
int KSE_OP_BUILDID()   { return 203; }
int KSE_OP_ERRNO()     { return 204; }

// CODES START AT 1 -- 0 IS RESERVED for "no KSE". An unimplemented slot returns 0, so
// if OK were 0 you could not tell "nothing went wrong" from "KSE is not installed".
// Check the version first; then a 0 from KSE_ERRNO is impossible.
int KSE_E_ABSENT()      { return 0; }   // you did not check KSE_GetVersion() first
int KSE_E_OK()          { return 1; }   // nothing refused since the last clear
int KSE_E_AT_CAPACITY() { return 2; }   // the grant hit count==cap and was refused
int KSE_E_NO_TARGET()   { return 3; }   // no object KSE could act on
int KSE_E_UNKNOWN_OP()  { return 4; }   // this build does not carry that opcode -- OLDER KSE

int    KSE_GetVersion() { return _kse_eval(KSE_OP_VERSION()); }
int    KSE_ERRNO()      { return _kse_eval(KSE_OP_ERRNO()); }
string KSE_BuildId()    { _kse_eval(KSE_OP_BUILDID()); return _kse_streval(); }

int KSE_OP_ENGINE_STRLEN() { return 201; }
int KSE_OP_DIAG()          { return 900; }

int KSE_EngineStrLen(string s) { _kse_pushstr(s); return _kse_eval(KSE_OP_ENGINE_STRLEN()); }

// The diagnostic channel. nCode is echoed back as the return value, so a caller can
// assert on it. sMsg is logged verbatim. Pass "" if there is nothing to say.
int KSE_Diag(int nCode, string sMsg)
{
    _kse_pushstr(sMsg);
    _kse_push(nCode);
    return _kse_eval(KSE_OP_DIAG());
}

// Feat-read transport. One stock slot carries the whole call, because its declared
// shape (object, int) -> int is exactly what we need:
//   _kse_feat -> ACTION 685
// Note the argument ORDER: the host takes the object first, so the wrapper passes
// (oCreature, nFeat) even though the author-facing signature is (nFeat, oCreature),
// matching TSL's declaration order.
int _kse_feat(object oCreature, int nFeat) { return SWMG_GetSoundFrequencyIsRandom(oCreature, nFeat); }

int KSE_GetFeatAcquired(int nFeat, object oCreature = OBJECT_SELF)
{
    return _kse_feat(oCreature, nFeat);
}


// Skill-write transport. One stock routine slot KSE claims:
//   ACTION 684 -- its (object,int,int) void shape matches TSL's AdjustCreatureSkills
//   exactly, so no push/eval split.
void KSE_AdjustCreatureSkills(object oObject, int nSkill, int nAmount)
{
    SWMG_SetSoundFrequency(oObject, nSkill, nAmount);
}

// Saving-throw transport. Two stock routine slots carry four functions:
//   ACTION 686 -> modify
//   ACTION 687 -> read base
// The selector must match the DLL: 0=FORT, 1=REFLEX, 2=WILL.
int KSE_SAVE_FORTITUDE() { return 0; }
int KSE_SAVE_REFLEX_()   { return 1; }
int KSE_SAVE_WILL_()     { return 2; }

void _kse_sv_write(object o, int nSave, int nAmount) { SWMG_SetSoundFrequencyIsRandom(o, nSave, nAmount); }
int  _kse_sv_read (object o, int nSave)              { return SWMG_GetSoundVolume(o, nSave); }

void KSE_ModifyFortitudeSavingThrowBase(object oObject, int nAmount) { _kse_sv_write(oObject, 0, nAmount); }
void KSE_ModifyReflexSavingThrowBase   (object oObject, int nAmount) { _kse_sv_write(oObject, 1, nAmount); }
void KSE_ModifyWillSavingThrowBase     (object oObject, int nAmount) { _kse_sv_write(oObject, 2, nAmount); }
int  KSE_GetSavingThrowBase(object oObject, int nSave)               { return _kse_sv_read(oObject, nSave); }

int KSE_GRANT_ERR() { return -559038737; }   // 0xDEADBEEF signed -- the refusal sentinel

// ---- array-A grant: add a feat to the creature's aggregate feat array ---------
// KSE_GrantFeatArrayA appends nFeat to the creature's aggregate feat array via the
// engine's own adder -- the same array the loader fills, the membership test scans
// first, the prerequisite-resolver reads, and the aggregate feat list is built from.
// It uses the engine's own path and validates the feat id.
//
// PERSISTENCE: a granted feat reaches the save file through the game's own save
// writer and survives a reload in a fresh process, including across area
// transitions. So a successful grant here IS a persisted feat. Tested with a
// passive feat, on one build.
//
// FEAT TYPE. The grant path is the same for a passive feat (Toughness) and an
// activated one (Flurry, Power Attack, Critical Strike). But same grant path is NOT
// same outcome: an activated feat needs a combat-mode entry a passive one does not,
// and whether array-A membership alone lets the UI offer it as a selectable mode is
// UNEXAMINED. Activated feats are runtime-untested. Prefer passive feats until an
// activated one is tested end to end.
//
// This host is a VOID routine, so this returns nothing. Read the result back with
// KSE_GetFeatAcquired in the SAME script pass, so a silent no-op is distinguishable
// from a grant that fired. The DLL log carries the full before/after id lists.
//
// UNDO: KSE_RemoveFeatArrayA (below). Without it a grant is permanent on that
// character.
void _kse_granta(object o, int nFeat) { SWMG_SetMaxHitPoints(o, nFeat); }   // ACTION 618

void KSE_GrantFeatArrayA(int nFeat, object oCreature = OBJECT_SELF) { _kse_granta(oCreature, nFeat); }

// ---- array-A REMOVAL: the undo GrantFeatArrayA never had -----------------------
// KSE_RemoveFeatArrayA takes nFeat back OFF the creature's aggregate feat array, by
// DRAIN-AND-REBUILD: KSE snapshots the survivors, zeroes the array's count, and
// pushes every survivor back through the engine's own adder. That shape is immune to
// anything holding an index into the array, because it never moves an element into
// another element's slot.
//
// SIDE EFFECTS WORTH KNOWING:
//   - The array is REORDERED. Survivors come back in iteration order and the removed
//     element's position closes up. Do not depend on feat order.
//   - It removes exactly ONE feat and does NOT touch prerequisites. If you remove a
//     feat that another held feat requires, you get a state the engine's own
//     level-up path never produces. KSE logs a loud ORPHAN WARNING and does nothing
//     else, deliberately -- KSE_GrantFeatArrayA does not maintain prerequisite
//     closure either. Removing the dependents is YOUR call.
//   - It REFUSES if the creature's use-counter list is non-empty. That list is
//     always empty on shipped KOTOR data; a non-empty one means modded feat.2da
//     rows with UsesPerDay set, which removal has no parallel path for yet.
//
// This host is VOID, so this returns nothing. Read the result back with
// KSE_GetFeatAcquired in the SAME script pass, exactly as with the grant. The DLL log
// carries the full before/after id lists and the removed index.
void _kse_removea(object o, int nFeat, int nReserved) { SWMG_SetGunBankDamage(o, nFeat, nReserved); }  // ACTION 634

void KSE_RemoveFeatArrayA(int nFeat, object oCreature = OBJECT_SELF) { _kse_removea(oCreature, nFeat, 0); }

// ===========================================================================
// KOTOR AP ADDITION (not part of upstream K1SE) -- SetCreatureField.
//
// A generic fixed-slot writer for class type, class level, and Force points --
// the class/level/Force offsets this project's own live testing confirmed
// (see kotor_engine_constraints.md in project memory for the full test
// history). Same one-write-per-call discipline as KSE_AdjustCreatureSkills
// above: no lists, no counts, no capacity, just a value written to a slot
// the engine's own reader already reads.
//
// ACTION 688 -- SWMG_SetSoundVolume's (object,int,int) void shape carries it
// exactly, same as skills on 684. Confirmed zero real callers in every
// vanilla/mod script in the game AND not claimed by any other KSE host.
//
// nFieldType selectors (must match dllmain/offsets.h exactly):
int KSE_FIELD_CLASS0_TYPE()  { return 0; }  // primary class slot's type byte
int KSE_FIELD_CLASS0_LEVEL() { return 1; }  // primary class slot's level byte
int KSE_FIELD_CLASS1_TYPE()  { return 2; }  // second class slot's type byte
int KSE_FIELD_CLASS1_LEVEL() { return 3; }  // second class slot's level byte
int KSE_FIELD_FORCE()        { return 4; }  // current/max Force points (4-byte int)
int KSE_FIELD_CURRENT_HP()   { return 5; }  // current HP (4-byte int) -- see
                                             // KSE_GetCurrentHP below for why
                                             // Max HP has no counterpart here
                                             // (it's computed, not stored).
int KSE_FIELD_ADD_FORCE_POWER()    { return 6; }  // nValue = spells.2da row id.
                                                   // No-ops if already known.
int KSE_FIELD_REMOVE_FORCE_POWER() { return 7; }  // nValue = spells.2da row id.
                                                   // No-ops if not known.

void KSE_SetCreatureField(object oCreature, int nFieldType, int nValue)
{
    SWMG_SetSoundVolume(oCreature, nFieldType, nValue);
}

// -----------------------------------------------------------------------------
// KOTOR AP ADDITION (2026-09-06): Current HP getter -- the read-side
// counterpart to KSE_FIELD_CURRENT_HP() above. Max HP has NO equivalent
// native: it has no memory field at all (confirmed via a thorough double-
// diff, see FutureDesign.md), and is computed instead from class/level/CON
// -- read it with the standard GetMaxHitPoints(). Current and Max Force
// Points also need no new native -- GetCurrentForcePoints()/
// GetMaxForcePoints() already work; only the write side
// (KSE_FIELD_FORCE()) needed this project's own extension.
//
// ACTION 617 -- SWMG_GetMaxHitPoints's (object)->int shape carries it
// exactly. Confirmed zero real callers via scan_opcode_usage.py
// (2026-09-06) and not claimed by any other KSE host (see offsets.h's
// KSE_GETCURRENTHP_ID comment).
int KSE_GetCurrentHP(object oCreature)
{
    return SWMG_GetMaxHitPoints(oCreature);
}

// KSE_DumpStatBlock (ACTION 638) and KSE_TestCreditsChain (ACTION 606) --
// both TEMPORARY research wrappers -- were removed 2026-09-06 once the
// research they supported concluded and shipped as real natives/offsets.
// Archived at extender/research_archive/kse_hook_temp_natives_2026-09-06.cpp.txt.
// Both underlying ACTION ids are unclaimed again -- do not reuse without
// re-running scan_opcode_usage.py fresh.

// -----------------------------------------------------------------------------
// KOTOR AP ADDITION (not part of upstream K1SE): SetCredits -- the real,
// write-capable promotion of the old credits-chain diagnostic (2026-09-03).
// Resolves pRes via the same confirmed chain and writes nValue directly to
// [pRes+0xFC] -- an exact, bidirectional set. Replaces the old
// GiveGoldToCreature/TakeGoldFromCreature dance (TakeGoldFromCreature is a
// confirmed no-op in this engine build, so that mechanism could only ever
// top credits up, never reduce them). oPC is unused/discarded -- credits
// aren't per-creature -- kept only because it's part of the hijacked
// host's real signature. Returns the value read back immediately after
// the write, a genuine confirmation rather than an echo of the input.
//
// ACTION 683 -- SWMG_GetSoundFrequency's (object,int)->int shape carries
// it exactly. Confirmed zero real callers via scan_opcode_usage.py
// (2026-09-03) and not claimed by any other KSE host (see offsets.h's
// KSE_SET_CREDITS_ID comment).
int KSE_SetCredits(object oPC, int nValue)
{
    return SWMG_GetSoundFrequency(oPC, nValue);
}
