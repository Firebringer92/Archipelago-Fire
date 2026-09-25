#pragma once
#include <windows.h>
#include <stdint.h>

// -----------------------------------------------------------------------------
// Verified addresses and byte patterns for the supported game build.
//
// Each constant is an address or offset KSE depends on. If the game binary
// changes, these must be re-derived, not adjusted by feel.
// -----------------------------------------------------------------------------

// The engine-routine dispatcher. KSE installs its hook here.
//
// We store the RVA and add the module's *actual* base at runtime rather than
// baking in the absolute VA. The image is non-relocatable, so in practice it
// loads at its preferred base and the VA would be correct as-is -- but deriving
// the address from GetModuleHandle(NULL) is correct regardless, and costs nothing.
static const uintptr_t KSE_DISPATCHER_RVA = 0x0052C0D0u - 0x00400000u; // 0x0012C0D0

// Sentinel: the first ten bytes at the dispatcher, used as a readiness check.
// The module's code is not stable at load time; KSE waits until the bytes here
// match this pattern before hooking, which signals the function is present and
// safe to modify. The exact bytes are an implementation detail of that check.
static const unsigned char KSE_SENTINEL[] = {
    0x8B, 0x54, 0x24, 0x04, 0x81, 0xFA, 0x04, 0x03, 0x00, 0x00
};
static const size_t KSE_SENTINEL_LEN = sizeof(KSE_SENTINEL);

// -----------------------------------------------------------------------------
// The VM argument/return contract. Stored as RVAs and resolved against the module
// base at runtime.
//   KSE_VM_STATE_RVA   : global holding the VM object pointer; an accessor is
//                        called with ECX = *(void**)(base + RVA).
//   KSE_SETRET_INT_RVA : push-int-return accessor. Takes the int value directly.
static const uintptr_t KSE_VM_STATE_RVA   = 0x007a3a00u - 0x00400000u; // 0x003a3a00
static const uintptr_t KSE_SETRET_INT_RVA = 0x005d1010u - 0x00400000u; // 0x001d1010

// Argument GET accessors. Called with ECX = *(void**)(base + KSE_VM_STATE_RVA) and
// a pushed pointer to a 4-byte out slot; each pops the top VM-stack element after
// validating its type tag, RET 4, EAX = 1 ok / 0 fail.
static const uintptr_t KSE_GET_INT_RVA    = 0x005d1000u - 0x00400000u; // 0x001d1000
static const uintptr_t KSE_GET_OBJECT_RVA = 0x005d10c0u - 0x00400000u; // 0x001d10c0

// -----------------------------------------------------------------------------
// The integer-utility suite. No single host takes two ints and returns one, so two
// host routines carry the whole suite: one pushes an operand, one evaluates an
// opcode over the pushed operands. Both are safe, never-called host routines.
#define KSE_PUSH_ID 627   // SWMG_GetGunBankDamage(object,int)->int  -> _kse_push
#define KSE_EVAL_ID 631   // SWMG_GetGunBankTarget(object,int)->int  -> _kse_eval

// -----------------------------------------------------------------------------
// The string path: read a string arg AND return a string. No safe host has a
// string->string shape, so two hosts carry it:
//   KSE_PUSHSTR_ID = 632: reads its string arg and stashes it (void return).
//   KSE_STROUT_ID  = 583: takes no args, returns a string.
// The wrapper KSE_StrTest(string)->string in include/kse.nss hides the split.
#define KSE_PUSHSTR_ID 632  // void SWMG_SetGunBankBulletModel(object,int,string) -> push a string
#define KSE_STROUT_ID 583  // string SWMG_GetLastEvent()                          -> _kse_streval

// String accessors. Same call shape as the int getters: ECX = *(void**)(base +
// KSE_VM_STATE_RVA), one pushed pointer to a CExoString, RET 4, EAX = 1 ok / 0 fail.
// get.string copies the popped stack string into the caller's CExoString; set.string
// deep-copies the caller's CExoString onto the return slot -- so the caller still
// owns, and must destroy, its own CExoString either way.
static const uintptr_t KSE_GET_STRING_RVA    = 0x005d1080u - 0x00400000u; // 0x001d1080
static const uintptr_t KSE_SETRET_STRING_RVA = 0x005d1090u - 0x00400000u; // 0x001d1090

// CExoString lifecycle (layout { char* ptr @ +0; int len @ +4 }, 8 bytes). All are
// __thiscall (ECX = this). Using the engine's own ctor/dtor/copy keeps every
// allocation matched to the engine's free, so KSE never mixes allocators.
//   ctor  (default): sets { 0, 0 }.
//   dtor          : frees [this] if non-null, zeroes both.
//   copyFromCStr  : this <- copy of a C string; allocs len+1, copies incl. NUL.
// NOTE: copyFromCStr does NOT free an existing buffer first, so it is only ever
// called on a freshly default-constructed CExoString (no leak, no double free).
static const uintptr_t KSE_CEXOSTR_CTOR_RVA     = 0x005b3190u - 0x00400000u; // 0x001b3190
static const uintptr_t KSE_CEXOSTR_DTOR_RVA     = 0x005e5c20u - 0x00400000u; // 0x001e5c20
static const uintptr_t KSE_CEXOSTR_FROMCSTR_RVA = 0x005e5a90u - 0x00400000u; // 0x001e5a90

// -----------------------------------------------------------------------------
// The arbitrary-key data store (KSE keeps it in its own DLL memory): unlimited,
// arbitrarily-named key/value storage the base engine lacks. Operands are staged
// onto a small typed DLL-side stack by two push hosts, then one eval host applies
// an opcode; a separate eval host serves the one string-returning op. Four hosts,
// all safe never-called routines, distinct from the ones above.
#define KSE_DS_PUSHS_ID   633  // void   SWMG_SetGunBankGunModel(object,int,string) -> push a string operand
#define KSE_DS_PUSHI_ID   622  // void   SWMG_SetNumLoops(object,int)               -> push an int operand
#define KSE_DS_EVALI_ID   640  // int    SWMG_IsGunBankTargetting(object,int)->int  -> int-returning eval(op)
#define KSE_DS_GETDATA_ID 584  // string SWMG_GetLastEventModelName()->string       -> GetData (string return)
// The data store reuses the accessors and CExoString RVAs above -- no new offsets.

// -----------------------------------------------------------------------------
// CExoString::GetLength -- an engine function KSE calls to compute a string length
// on a script's behalf. __thiscall (ECX = CExoString*), no stack args, EAX = length;
// null/empty buffer returns 0.
static const uintptr_t KSE_CEXOSTR_GETLEN_RVA = 0x005e5790u - 0x00400000u; // 0x001e5790

// -----------------------------------------------------------------------------
// GetFeatAcquired -- a KOTOR 2 function exposed in KOTOR 1. It is NOT the same as
// K1's GetHasFeat:
//   KSE_FEAT_QUERY_RVA (0x005a6630): pure membership -- scans the creature's feat
//     arrays for nFeat, returns 1/0. == GetFeatAcquired.
//   0x005a6680: gates on the above, then applies feat-2DA usability math.
//     == GetHasFeat ("acquired AND currently usable").
// So GetHasFeat implies GetFeatAcquired, but not the converse.
//
// The handler replicates the object-resolution chain a stock handler uses, so any
// input that could fault here would equally fault stock GetHasFeat:
//   a. seed   = *(void**)(*(void**)KSE_OBJ_ROOT_RVA + 8)
//   b. table  = KSE_OBJ_TABLE_GET(seed)                  __thiscall, no stack args
//   c. rc     = KSE_OBJ_RESOLVE(table, objectId, &obj)   __thiscall, RET 8; writes
//               the object pointer to *out; AL = the byte at KSE_RESOLVE_OK_RVA on
//               success (compared against that global, not a hardcoded constant).
//   d. stats  = (*(void***)obj)[0x30/4](obj)   virtual; NULL for non-creatures. On
//               the creature class this slot is identity, so stats == obj and
//               [obj+0xa74] is the stat block directly.
//   e. list   = *(void**)((BYTE*)stats + 0xa74)
//   f. result = KSE_FEAT_QUERY(list, nFeat)              __thiscall, RET 4, EAX = 1/0
#define KSE_FEAT_ID 685   // int SWMG_GetSoundFrequencyIsRandom(object,int)->int; a
                          // safe never-called host whose (object,int)->int shape
                          // carries the whole function with no push/eval split.

static const uintptr_t KSE_OBJ_ROOT_RVA     = 0x007a39fcu - 0x00400000u; // 0x003a39fc
static const uintptr_t KSE_OBJ_TABLE_GET_RVA= 0x004aed70u - 0x00400000u; // 0x000aed70
// KOTOR AP ADDITION, TEMPORARY (credits chain confirmation):
// second candidate for the credits HUD code's call target, tried after
// KSE_OBJ_TABLE_GET_RVA was confirmed NOT to be it (live test returned
// garbage). KSE_OBJ_TABLE_GET_RVA returns a TABLE
// that needs a further KSE_OBJ_RESOLVE_RVA(table, objectId, &obj) step
// with an explicit object id (see KSE_FEAT_ID's chain above) -- but the
// raw disassembly of the credits HUD code showed only ONE call whose
// return value was used directly as pRes, no id argument, no second call.
// That's consistent with this being a DIFFERENT, dedicated "get the one
// party/campaign resource" accessor (no id needed, only one such resource
// exists) rather than the general per-object table getter -- which would
// also explain the original manual decode's 0x100 discrepancy as a real
// distinct function, not an arithmetic slip.
static const uintptr_t KSE_OBJ_TABLE_GET_ALT_RVA = 0x004aee70u - 0x00400000u; // 0x000aee70
static const uintptr_t KSE_OBJ_RESOLVE_RVA  = 0x004d8230u - 0x00400000u; // 0x000d8230
static const uintptr_t KSE_RESOLVE_OK_RVA   = 0x0074666cu - 0x00400000u; // 0x0034666c
static const uintptr_t KSE_FEAT_QUERY_RVA   = 0x005a6630u - 0x00400000u; // 0x001a6630
#define KSE_VT_GETSTATS_OFF 0x30   // vtable byte offset for the get-stats slot
#define KSE_STATS_FEATLIST_OFF 0xa74

// -----------------------------------------------------------------------------
// AdjustCreatureSkills -- a write-type operation. Skills were chosen over feats as
// the safest first write: fixed slots, one signed byte each, no counts, no
// capacity, no parallel bookkeeping -- a skill either changes by the exact amount
// or it does not.
//
// KSE does not call an engine setter (none was located). It writes the same byte
// the engine's own reader reads, using the engine's own bound: nSkill is validated
// against *(BYTE*)([rules mgr] + KSE_RULES_SKILLCOUNT_OFF). If that manager pointer
// is null the handler refuses to write rather than assume a skill count.
#define KSE_SKILL_ID 684   // void SWMG_SetSoundFrequency(object,int,int); a safe
                           // never-called host whose (object,int,int) void shape
                           // matches AdjustCreatureSkills exactly.

static const uintptr_t KSE_RULES_MGR_RVA   = 0x007a3a28u - 0x00400000u; // 0x003a3a28
#define KSE_RULES_SKILLCOUNT_OFF 0xab   // byte: number of skills (the getter's bound)
#define KSE_STATS_SKILLARRAY_OFF 0x168  // statBlock+0x168 -> BYTE* skill ranks
#define KSE_SKILL_RANK_MAX 127          // KSE's own clamp; the slot is a signed byte

// -----------------------------------------------------------------------------
// The saving-throw base family -- the same fixed-slot write pattern as skills:
// write one byte the engine's own reader reads back; refuse bad input. Each base
// contributes linearly to the stock reader's total, so writing +N changes the
// reader's answer by exactly +N.
//
// NOTE THE ORDER: the three base bytes are consecutive but are Fortitude, WILL,
// REFLEX -- NOT the Fortitude/Reflex/Will order the script constants suggest. The
// selector below maps KSE's API numbering to the real byte offsets in one place.
//
// As with skills, no engine setter is called (none located); KSE writes the byte
// the engine's own reader reads.
#define KSE_SAVE_WRITE_ID 686  // void SWMG_SetSoundFrequencyIsRandom(object,int,int) -> (object,nSave,nAmount); safe never-called
#define KSE_SAVE_READ_ID  687  // int  SWMG_GetSoundVolume(object,int)->int           -> (object,nSave) -> base; safe never-called
// One host pair carries all four functions (three modifiers + one base reader).

// nSave selector -- KSE's own API numbering, mapped to the engine's byte offsets
// below. Ordered Fortitude/Reflex/Will to match the familiar convention, so the
// mapping to the real (Fort/Will/Reflex) byte layout lives in one place.
#define KSE_SAVE_FORT   0
#define KSE_SAVE_REFLEX 1
#define KSE_SAVE_WILL   2
#define KSE_STATS_SAVE_FORT_OFF   0x1a0
#define KSE_STATS_SAVE_WILL_OFF   0x1a1
#define KSE_STATS_SAVE_REFLEX_OFF 0x1a2
#define KSE_SAVE_BASE_MAX 127     // the slot is a signed byte

// -----------------------------------------------------------------------------
// The engine's own feat-id validator, used by stock GetHasFeat: __thiscall(rulesMgr,
// WORD nFeat) -> row pointer, or NULL if the id is out of range or the row's
// validity bit is clear. KSE validates with this rather than inventing a bound, so
// an id the engine would reject is refused before anything is written.
// KSE_FEAT_ADD_RVA is an alternative engine feat-adder, retained but not currently
// used (the shipping grant path uses KSE_ARRAYA_ADD_RVA below).
static const uintptr_t KSE_FEAT_ROWLOOKUP_RVA = 0x00550c00u - 0x00400000u; // 0x00150c00
static const uintptr_t KSE_FEAT_ADD_RVA       = 0x005cb150u - 0x00400000u; // 0x001cb150

// -----------------------------------------------------------------------------
// Feat record-container addresses, retained but not currently used by the shipping
// grant path. Kept for reference:
//   KSE_CREATURE_GETHOLDER_RVA : years-old label, IDENTIFIED 2026-09-20 via
//                                LaneDibello/Kotor-Patch-Manager's AddressDatabases/
//                                kotor1_0_3.db as the real CSWSObject::GetClientObject()
//                                -- __thiscall(CSWSObject* this) -> CSWCObject*, no other
//                                params. This is the real, confirmed way to get from a
//                                resolved SERVER object to its CLIENT-side mirror (see
//                                KSE_FIELD_DIAG_SCAN_CLIENT_STATS below) -- prefer this
//                                function call over reading CSWSObject.client_object
//                                (offset 548) directly, which came back NULL live for
//                                the PC, meaning the field isn't simply what this
//                                function returns (or isn't populated the same way for
//                                the locally-controlled player).
//   KSE_LIST_FEAT_ADD_RVA      : __thiscall(listHead, WORD nFeat), RET 4; dedups,
//                                grows when full, appends. Takes the LIST HEAD.
//   KSE_CONTAINER_FEATHAS_RVA  : container-side membership test, __thiscall(container,
//                                WORD nFeat) -> int. Takes the CONTAINER, not the head.
// NOTE: these three neighbours take different arguments (stat block vs list head vs
// container); passing the wrong one is a wrong-memory write, not a crash.
static const uintptr_t KSE_CREATURE_GETHOLDER_RVA = 0x004cc2b0u - 0x00400000u; // 0x000cc2b0
static const uintptr_t KSE_LIST_FEAT_ADD_RVA     = 0x005a7670u - 0x00400000u; // 0x001a7670
static const uintptr_t KSE_CONTAINER_FEATHAS_RVA = 0x00649340u - 0x00400000u; // 0x00249340

// -----------------------------------------------------------------------------
// Save-path function addresses, retained but not currently used by the shipping
// path (they were observer targets during development). Kept for reference.
static const uintptr_t KSE_SERIALIZER_RVA = 0x006123e0u - 0x00400000u; // 0x002123e0
static const uintptr_t KSE_DRAINER_RVA    = 0x00648320u - 0x00400000u; // 0x00248320
static const uintptr_t KSE_STATWRITER_RVA = 0x005aec90u - 0x00400000u; // 0x001aec90

#define KSE_STATBLOCK_FEATA_COUNT_OFF 0x04  // array A count
#define KSE_STATBLOCK_FEATB_COUNT_OFF 0x1c  // array B count

#define KSE_HOLDER_CONTAINER_OFF     0x2f8  // [holder+0x2f8] -> container
#define KSE_CONTAINER_FEATLIST_OFF   0xb0   // container feat array ptr
#define KSE_CONTAINER_FEATCOUNT_OFF  0xb4   // container feat count
#define KSE_CONTAINER_FEATCAP_OFF    0xb8   // container feat capacity

// -----------------------------------------------------------------------------
// The array-A grant: the shipping feat-grant path.
//
//   KSE_ARRAYA_ADD_RVA (0x005aa810): the engine's own array-A adder.
//     __thiscall(statBlock /*ECX*/, WORD featId /*pushed*/), RET 4, no return.
//     (a) validates the id via the feat-id validator and REJECTS cleanly on an
//         invalid id -- nothing written; (b) appends to array A, whose layout at
//         statBlock +0x00/+0x04/+0x08 is {ptr, count, capacity}; (c) has a
//         use-counter branch gated on the feat row's UsesPerDay byte (+0x33). That
//         column is empty for every KOTOR feat, so the branch never runs on shipped
//         data -- but the grant guard reads it per-feat so it stays correct if a mod
//         ever populates the column. This adder does not null-check the rules
//         manager, so the wrapper must.
static const uintptr_t KSE_ARRAYA_ADD_RVA = 0x005aa810u - 0x00400000u; // 0x001aa810

// Feat-row +0x33 = the "UsesPerDay" column. Non-zero would mean the adder also
// appends to the use-counter list (growable, its own capacity). Zero for every
// KOTOR feat, but the grant guard reads it per-feat so it stays correct if a mod
// ever populates the column.
#define KSE_FEATROW_USESPERDAY_OFF 0x33

// Feat-row prerequisite columns. Read ONLY to WARN when a removal orphans a
// dependent -- KSE does not enforce prerequisites. Both are `word`; the engine uses
// 0xffff as "none", so treat 0 and 0xffff alike as "no prerequisite".
#define KSE_FEATROW_PREREQ1_OFF 0x38
#define KSE_FEATROW_PREREQ2_OFF 0x3a

// The stat block opens with THREE consecutive {ptr,count,capacity} triples: array A
// (feats, 2-byte ids -- what the save reads), the use-counter list (4-byte records),
// and array B (feats, 2-byte ids). The grant refuses if either growable list is
// full. Array A's capacity is read at run time, never assumed.
#define KSE_SB_FEATA_PTR_OFF    0x00  // array A: feats (2-byte ids) -- what the save reads
#define KSE_SB_FEATA_COUNT_OFF  0x04
#define KSE_SB_FEATA_CAP_OFF    0x08
#define KSE_SB_USECTR_PTR_OFF   0x0c  // use-counters (4-byte records)
#define KSE_SB_USECTR_COUNT_OFF 0x10
#define KSE_SB_USECTR_CAP_OFF   0x14
#define KSE_SB_FEATB_PTR_OFF    0x18  // array B: feats (2-byte ids)
#define KSE_SB_FEATB_COUNT_OFF  0x1c
#define KSE_SB_FEATB_CAP_OFF    0x20

#define KSE_GRANTA_ID 618  // void SWMG_SetMaxHitPoints(object,int) used as
                           // (object oCreature, int nFeat). A safe never-called host.
                           // Void return, so the test reads back via 685 in the same
                           // pass to tell a grant from a silent no-op.

// -----------------------------------------------------------------------------
// REMOVE a feat from array A, by DRAIN-AND-REBUILD.
//
// WHY DRAIN-AND-REBUILD RATHER THAN SHIFT-IN-PLACE. A shift MOVES existing elements,
// which addition never does, so anything holding an INDEX into array A would
// silently start pointing at the wrong feat. Whether such an index exists is
// unproven; drain-and-rebuild is immune to the question by construction -- it never
// moves an element into another element's slot, it rebuilds the whole list. KSE
// snapshots the survivors, zeroes array A's count (a direct write to statBlock+0x04),
// and re-adds each survivor through the same array-A adder.
//
// WHY NO REALLOC. The rebuild re-adds at most count-1 elements into a list whose
// capacity is unchanged (the drain never touches +0x08), and the adder grows only
// when count == capacity, so no reallocation can fire here.
//
// TRANSIENT-EMPTY ASSUMPTION, stated so it can be challenged. Between the drain and
// the last re-add, array A is empty or partial. This is safe ONLY IF nothing reads
// array A during that window: script routines run synchronously on the VM's single
// dispatch thread, the handler makes no call that can re-enter script, and it
// neither sleeps nor yields. Recorded as an assumption, not a proof.
#define KSE_REMOVEA_ID 634 // void SWMG_SetGunBankDamage(object,int,int) used as
                           // (object oCreature, int nFeat, int nReserved=0). A safe
                           // never-called host. NOT the same routine as 627
                           // (SWMG_GetGunBankDamage, the push host) -- one is the
                           // setter, one the getter; do not conflate them.

// -----------------------------------------------------------------------------
// NOT IMPLEMENTED: ability-score writes. Deliberately left out. Ability scores have
// DERIVED consequences that skills and saving throws do not (CON drives max HP, DEX
// drives AC), and whether writing the raw byte triggers the engine's recalculation
// of those is unverified -- so a write could leave a character internally
// inconsistent in a way the obvious referee would miss. A floor-of-3 clamp on the
// accessor also breaks exact-delta verification near the bottom.

// -----------------------------------------------------------------------------
// KOTOR AP ADDITION (not part of upstream K1SE): SetCreatureField -- a generic
// fixed-slot byte/int writer for class type, class level, and Force points.
// Same proven shape as AdjustCreatureSkills/the saving-throw writes: one
// engine-reader-matching write per call, no lists, no counts, no capacity.
//
// Offsets confirmed via live differential-scan testing against a real running
// game (Cheat Engine, cross-referenced on multiple creatures/species), NOT
// derived from disassembly the way the K1SE offsets above were -- treat these
// as empirically confirmed rather than source-verified.
// -----------------------------------------------------------------------------
// KSE_DUMPSB_ID (638, generic statBlock hex dumper) and KSE_CREDITS_CHAIN_ID
// (606, read-only credits-chain diagnostic) were both TEMPORARY research
// hosts, removed once the research they supported concluded and
// shipped as real natives/offsets. Archived at
// extender/research_archive/kse_hook_temp_natives_2026-09-06.cpp.txt. Both
// IDs (638, 606) are now unclaimed again -- do not reuse without re-running
// scan_opcode_usage.py fresh, per this project's own opcode-safety discipline.

// KOTOR AP ADDITION: item-object-id resolve diagnostic, for
// loot-window memory-hunting research. REUSES host 638 (freed above when
// KseDumpStatBlock was archived) -- confirmed still unclaimed via a fresh
// grep of this file and kse_hook.cpp immediately before reuse (not a full
// scan_opcode_usage.py re-run, but sufficient given nothing else in this
// codebase currently references it). Same (object,int,int) void-returning
// SWMG_SetGunBankTarget shape KseDumpStatBlock used -- object arg discarded,
// first int is the object id to resolve, second int unused/reserved.
//
// Resolves a script object id through the SAME chain KSE_FEAT_ID/KSE_FIELD_ID
// use (object root -> seed -> KSE_OBJ_TABLE_GET_RVA -> KSE_OBJ_RESOLVE_RVA),
// but stops at the raw resolved pointer -- deliberately SKIPS the
// creature-specific vtable get-stats step (KSE_VT_GETSTATS_OFF) those hosts
// perform next, since an item is not a creature and that call would return
// NULL for it. Reads the item struct fields confirmed via Cheat Engine
// research (type @ +0x0C matches real baseitems.2da row ids;
// quantity @ +0x28C matches real held stack sizes -- both cross-verified
// against actual in-game items), logging the result to kse.log rather than returning it structured,
// since this is a one-shot verification tool, not a shipping feature.
#define KSE_RESOLVE_ITEM_ID 638   // void SWMG_SetGunBankTarget(object,int,int);
                                  // object discarded, int1=objectId, int2=unused.

// KOTOR AP ADDITION (not part of upstream K1SE): SetCredits -- the real,
// write-capable promotion of the old credits-chain diagnostic.
// Resolves pRes via the SAME confirmed chain, then writes the caller's
// value directly to [pRes+0xFC] -- an exact, bidirectional set, unlike the
// old GiveGoldToCreature/TakeGoldFromCreature dance (TakeGoldFromCreature
// is a confirmed no-op in this engine build, so that old mechanism could
// only ever top credits up, never reduce them). See
// generate_trampoline_batch.py's build_set_credits_block().
#define KSE_SET_CREDITS_ID 683  // int SWMG_GetSoundFrequency(object,int)->int;
                           // confirmed 0 real callers via scan_opcode_usage.py,
                           // not claimed by any other KSE_*_ID
                           // in this file -- used as (object oPC [unused,
                           // discarded for stack balance], int nValue).

#define KSE_FIELD_ID 688   // void SWMG_SetSoundVolume(object,int,int); confirmed
                           // zero real callers in every vanilla/mod script in the
                           // game (exhaustive scan) AND not claimed by any other
                           // K1SE host above -- doubly confirmed safe to reuse.

// nFieldType selector, passed as the second (int) argument.
#define KSE_FIELD_CLASS0_TYPE  0   // primary class slot's type byte
#define KSE_FIELD_CLASS0_LEVEL 1   // primary class slot's level byte
#define KSE_FIELD_CLASS1_TYPE  2   // second class slot's type byte
#define KSE_FIELD_CLASS1_LEVEL 3   // second class slot's level byte
#define KSE_FIELD_FORCE        4   // current/max Force points, 4-byte int
#define KSE_FIELD_CURRENT_HP   5   // current HP, 4-byte int -- lives on
                                   // KseField_Obj()'s object, NOT the
                                   // statBlock every other field above
                                   // uses. See KSE_STATS_CURRENT_HP_OFF's
                                   // own comment for why this field is
                                   // special-cased to a different base.
#define KSE_FIELD_ADD_FORCE_POWER    6   // nValue = spells.2da row id. Searches
                                          // the known-powers array first; if the
                                          // id is already present, no-ops (a real
                                          // duplicate grant was confirmed harmless,
                                          // but skipping it anyway keeps count/capacity
                                          // sane). Appends at [count] and increments
                                          // count if not present and count < capacity
                                          // (16, observed fixed on every creature).
#define KSE_FIELD_REMOVE_FORCE_POWER 7   // nValue = spells.2da row id. Searches the
                                          // known-powers array; if found at index i,
                                          // shifts every later entry down by one and
                                          // decrements count. If NOT found, safely
                                          // no-ops (explicitly required -- must not
                                          // crash or corrupt count on a missing id).
#define KSE_FIELD_XP 8   // raw XP, 4-byte int, same statBlock as CLASS0_LEVEL/FORCE
                          // (not KseField_Obj() -- see KSE_STATS_XP_OFF below).
                          // Added to bypass native SetXP()'s apparent
                          // refusal to lower XP below the current level's already-
                          // banked threshold (the reason the original "Cut Level in
                          // Half" trap was retired: the level dropped, the XP didn't).
                          // A raw memory write has no such validation to race
                          // against; caller is responsible for also writing a
                          // matching CLASS0_LEVEL via a separate call so the two
                          // stay consistent (this project's own XP->level table
                          // is kotor_reconciliation.py's _EXPTABLE).

// Absolute base-ability-score setters (STR/DEX/INT/WIS/CHA -- CON deliberately
// excluded, see below). nValue = the new base score, 0-255 (engine takes a
// BYTE). Real engine member functions, NOT a raw offset poke -- same
// AddFeat-precedent reasoning KSE_ARRAYA_ADD_RVA already established (call the
// engine's own setter over guessing a byte layout). These 5 addresses were
// never independently reverse-engineered by this project: they come from
// LaneDibello/Kotor-Patch-Manager's AddressDatabases/kotor1_0_3.db (queried
// directly, 2026-09-19), the SAME build/version this project targets --
// confirmed trustworthy because that same database's AddFeat entry is
// byte-identical to KSE_ARRAYA_ADD_RVA above, which THIS project already
// independently confirmed live. All 5 sit in the same tight address range as
// AddFeat (0x5a9fe0-0x5aa170, AddFeat itself at 0x5aa810) alongside dozens of
// other real CSWSCreatureStats members in that DB, consistent with genuine
// adjacent member functions, not a fabricated/guessed cluster.
//
// WHY THIS EXISTS: the previous mechanism for ability traps/grants
// (ApplyEffectToObject + EffectAbilityIncrease/EffectAbilityDecrease) stacks
// a NEW, separate effect object on the creature every single call rather
// than rewriting one value -- confirmed live, 2026-09-19, a real character's
// Dexterity got permanently stuck unable to rise past 11 after accumulating
// ~20 stacked increase/decrease effects from repeated trap/admin activity,
// while Strength (far fewer stacked effects on the same character) kept
// working normally. These setters replace the stacking entirely: one call
// writes the real base score, full stop, so there's nothing left to
// accumulate and no ceiling to hit.
//
// CON's real engine setter, unlike the 5 above, takes an explicit HP-
// recalculate flag (Patch Manager's own SetCONBase(BYTE value, int setHP),
// same AddressDatabases/kotor1_0_3.db source, same tight address cluster
// as the other 5). Calling it with setHP=TRUE lets the engine recompute
// Max HP itself rather than this project inventing its own formula. Not
// reused by the "Cut Max Health in Half" trap or Train Ability's own CON
// purchase -- both keep their own separate, existing mechanisms
// (KotorClient.py's _con_decrease_for_half_max_hp; Train Ability's CON
// stays on the EffectAbilityIncrease path) untouched.
static const uintptr_t KSE_SET_STR_BASE_RVA = 0x005a9fe0u - 0x00400000u; // 0x001a9fe0
static const uintptr_t KSE_SET_DEX_BASE_RVA = 0x005aa020u - 0x00400000u; // 0x001aa020
static const uintptr_t KSE_SET_CON_BASE_RVA = 0x005aa060u - 0x00400000u; // 0x001aa060
static const uintptr_t KSE_SET_INT_BASE_RVA = 0x005aa0f0u - 0x00400000u; // 0x001aa0f0
static const uintptr_t KSE_SET_WIS_BASE_RVA = 0x005aa130u - 0x00400000u; // 0x001aa130
static const uintptr_t KSE_SET_CHA_BASE_RVA = 0x005aa170u - 0x00400000u; // 0x001aa170

// True base-ability-score BYTE offsets within CSWSCreatureStats, 2 bytes
// apart (NOT the same spacing as the client-side CSWCCreatureStats fields
// documented elsewhere in this project -- don't assume the two structs
// mirror each other here). Lets a native ability-base increment read the
// real base value directly: NWScript's GetAbilityScore(oCreature,
// nAbility) has no "base only" form in this engine (only the 2-arg
// signature exists in K1's own nwscript.nss), so it returns the EFFECTIVE
// score (base + any equipped item bonus) -- computing "new base =
// GetAbilityScore(...) + 1" in NWScript would silently bake a temporary
// item bonus in as a permanent base stat increase. Reading the true base
// here avoids that.
static const uintptr_t KSE_STATS_STR_BASE_OFF = 233;
static const uintptr_t KSE_STATS_DEX_BASE_OFF = 235;
static const uintptr_t KSE_STATS_CON_BASE_OFF = 237;
static const uintptr_t KSE_STATS_INT_BASE_OFF = 239;
static const uintptr_t KSE_STATS_WIS_BASE_OFF = 241;
static const uintptr_t KSE_STATS_CHA_BASE_OFF = 243;

// Real engine function for granting a known Force Power, replacing the
// hand-rolled raw known-powers-array poke KseForcePowerOp currently uses for
// the ADD side (KSE_FIELD_ADD_FORCE_POWER). Same LaneDibello/Kotor-Patch-
// Manager AddressDatabases/kotor1_0_3.db source as the ability-base setters
// above (queried 2026-09-19), sitting in the same confirmed-trustworthy
// address cluster. Signature per that DB/their CSWSCreatureStats.h:
// AddKnownSpell(CSWSCreatureStats* this, BYTE classId, DWORD spellId) --
// classId is WHICH class slot's known-spell list to add to, not part of
// KSE_SetCreatureField's existing (object, nFieldType, nValue) shape, so
// this hardcodes classId=0: this project's own class-slot convention
// already treats slot 0 as the Jedi/Force-using slot for both the PC
// (class_guardian/class_sentinel/etc. overwrite CLASS0_TYPE directly, never
// add a second slot) and every Jedi companion (Bastila/Jolee/Juhani start
// with Jedi in slot 0). UNPROVEN for this specific call: whether that
// assumption holds is exactly what this swap is meant to test, alongside
// whether using the real function fixes the PC-specific persistence gap
// documented for feats (KotorClient.py's additional_feats research) --
// unconfirmed either way for force powers specifically, not assumed to
// fail the same way just because feats did.
static const uintptr_t KSE_ADD_KNOWN_SPELL_RVA = 0x005aa9b0u - 0x00400000u; // 0x001aa9b0

#define KSE_FIELD_SET_STR_BASE 9    // nValue = new base Strength
#define KSE_FIELD_SET_DEX_BASE 10   // nValue = new base Dexterity
#define KSE_FIELD_SET_INT_BASE 11   // nValue = new base Intelligence
#define KSE_FIELD_SET_WIS_BASE 12   // nValue = new base Wisdom
#define KSE_FIELD_SET_CHA_BASE 13   // nValue = new base Charisma

#define KSE_FIELD_SET_CON_BASE 16   // nValue = new base Constitution (0-255); always recalculates Max HP (setHP=TRUE)

// nValue = signed delta added to the TRUE base score (read natively,
// never via NWScript's GetAbilityScore -- see KSE_STATS_STR_BASE_OFF's
// comment for why), then written via the same real engine setter the
// absolute KSE_FIELD_SET_*_BASE fields above use.
#define KSE_FIELD_INCREMENT_STR_BASE 17
#define KSE_FIELD_INCREMENT_DEX_BASE 18
#define KSE_FIELD_INCREMENT_INT_BASE 19
#define KSE_FIELD_INCREMENT_WIS_BASE 20
#define KSE_FIELD_INCREMENT_CHA_BASE 21

// Same shape as the 5 above, routed through the CON-specific setter
// (setHP=TRUE) since CON's real engine setter takes the extra HP-recalc
// parameter the others don't.
#define KSE_FIELD_INCREMENT_CON_BASE 22

// Self-contained "reduce to half" operation: reads the TRUE base score,
// computes base - (base/2), and writes it via the same real setter --
// entirely in native code, since the caller has no way to read the true
// base to compute this itself. No-ops (same as a NWScript-side "already
// minimal" check) when the base is already <= 1. nValue is unused. CON
// isn't included -- its own trap needs a specific decrease amount, not a
// flat halving, so it uses KSE_FIELD_INCREMENT_CON_BASE with a negative
// delta instead.
#define KSE_FIELD_HALVE_STR_BASE 23
#define KSE_FIELD_HALVE_DEX_BASE 24
#define KSE_FIELD_HALVE_INT_BASE 25
#define KSE_FIELD_HALVE_WIS_BASE 26
#define KSE_FIELD_HALVE_CHA_BASE 27

// Self-contained "Cut Max Health in Half" operation: computes the CON
// decrease that lands Max HP closest to half (the hit-die term is fixed
// and can't be touched via CON alone, so exact half isn't always
// reachable) entirely from the true base CON and both class-slot type/
// level bytes already read natively elsewhere in this file (see
// KSE_STATS_CLASS0_TYPE_OFF/KSE_STATS_CON_BASE_OFF above), then applies it
// via KSE_FIELD_INCREMENT_CON_BASE's own setter. Replaces a Python-side
// search over a cached ability/class snapshot that could go stale between
// the poll and the trap actually firing -- every input here is read live
// from the stat block at the moment of the call. nValue is unused.
#define KSE_FIELD_HALVE_MAX_HP_VIA_CON 28

// TEMPORARY RESEARCH DIAGNOSTIC (2026-09-20) -- retire once the offset
// below is confirmed and wired into a real fix. Investigating why a
// force power/feat correctly granted and PERSISTED on the server side
// (CSWSCreatureStats, everything this file's KSE_FIELD_* family already
// writes to) still doesn't show up on the live hotbar/combat menu.
// LaneDibello/Kotor-Patch-Manager's AddressDatabases/kotor1_0_3.db
// confirms KOTOR keeps a CLIENT-side mirror of creature stats
// (CSWCCreatureStats, distinct from CSWSCreatureStats) with its own
// AddKnownSpell -- the UI almost certainly reads from this mirror, which
// our server-side writes never touch. CSWSObject.client_object (confirmed
// offset 548/0x224 in the same DB) gets from a resolved server object to
// its CSWCObject*, but the DB doesn't have the further offset from there
// to the CSWCCreatureStats* the UI actually needs -- this project's own
// old KSE_HOLDER_CONTAINER_OFF (0x2f8) guess from years ago looks WRONG
// (0x2f8 = 760 decimal coincidentally matches CSWCCreature's real
// lvl_up_stats field instead, a level-up-screen-only structure, not the
// general stats object). CSWCCreatureStats's own vtable address IS known
// (0x751c60) -- this diagnostic scans the client object's own memory for
// a pointer whose target starts with that exact vtable address, to find
// the real offset empirically instead of guessing further.
#define KSE_FIELD_DIAG_SCAN_CLIENT_STATS 14   // nValue unused/reserved
#define KSE_OBJ_CLIENT_OBJECT_OFF 548          // CSWSObject.client_object (0x224)
#define KSE_CLIENT_STATS_VTABLE_VA 0x751c60u   // CSWCCreatureStats's own vtable

// PIVOT, 2026-09-20 -- a full read-only vtable dump of the resolved client
// object (all 80 slots cross-referenced against Patch Manager's DB) came
// back entirely animation/visual-effect/portrait/sync methods, no
// GetStats-shaped getter anywhere. CSWCCreature::GetSelfForcePowers /
// GetHostileForcePowers are real, NAMED, NON-virtual functions (not in the
// vtable at all -- called directly by address, same as every other real
// engine function this project already calls), and are much closer to the
// actual problem: they're plausibly the exact functions the UI calls to
// build its self/ally and hostile action lists. GetSelfForcePowers takes
// an output CExoArrayList* (this project's own {ptr,count,capacity}
// 12-byte shape, already used for the force-power category record) --
// calling it directly with a fresh empty list and reading back what it
// populates tests whether the UNDERLYING DATA is actually already correct
// (in which case the real bug is a UI-refresh/cache issue, not a missing
// client-side sync) without needing to fully solve the CSWCCreatureStats
// client-mirror question at all.
static const uintptr_t KSE_GET_SELF_FORCE_POWERS_RVA = 0x00616230u - 0x00400000u; // 0x00216230
#define KSE_FIELD_DIAG_CALL_GET_SELF_FORCE_POWERS 15   // nValue unused/reserved

// RESOLVED, 2026-09-20 -- CONFIRMED LIVE via a real memory-snapshot diff
// around a real level-up (Juhani learning Force Valor, spell id 22):
// KSE_HOLDER_CONTAINER_OFF (0x2f8, defined near KSE_CREATURE_GETHOLDER_RVA
// above) genuinely IS the offset from a resolved client CSWCCreature* to
// its own CSWCCreatureStats* -- the years-old offset was right all along.
// An automated pointer-scan for this exact offset earlier today came back
// with zero matches only because it compared against KSE_CLIENT_STATS_
// VTABLE_VA=0x751c60 exactly, but the REAL vtable value read live at this
// exact offset is 0x751c64 -- off by 4, so the scan silently skipped past
// the right answer. KSE_CONTAINER_FEATLIST_OFF (0xb0 = 176 decimal) also
// lines up exactly with CSWCCreatureStats.feats' real offset per Patch
// Manager's own DB -- both old offsets were correct the whole time, just
// never live-verified until now. Confirmed structure, read from a
// resolved clientObj: clientObj+0x2f8 -> CSWCCreatureStats*; that +212 ->
// classes[0] (a Jedi-only-from-start companion's class, matching Bastila/
// Jolee/Juhani); classes[0]+0 -> known_spells CExoArrayList
// {ptr,count,capacity}, contents matched Juhani's real known powers
// including the freshly-learned 22 exactly.
static const uintptr_t KSE_CLIENT_ADD_KNOWN_SPELL_RVA = 0x00649f90u - 0x00400000u; // 0x00249f90 -- CSWCCreatureStats::AddKnownSpell(classId, spellId), same signature as the server-side one

#define KSE_STATS_CLASS0_TYPE_OFF  0xa7
#define KSE_STATS_CLASS0_LEVEL_OFF 0xa8
#define KSE_STATS_CLASS1_TYPE_OFF  0xcf
#define KSE_STATS_CLASS1_LEVEL_OFF 0xd0
#define KSE_STATS_FORCE_OFF        0x124
// CONFIRMED via a live memory dump at
// the resolved statBlock matching the real XPREPORT value exactly (323175),
// used at the time purely as a validation landmark for a DIFFERENT research
// question (confirming an object was really the stat block), not built out as
// a usable field until now. READ was proven that day; WRITE was never tried
// until this addition -- test live before trusting it the way CLASS0_LEVEL/
// FORCE are already trusted.
#define KSE_STATS_XP_OFF           0x68

// Current HP -- CONFIRMED via live differential testing to live at
// this offset from KseField_Obj()'s object (the raw resolved engine
// object, one step EARLIER in the resolution chain than every other
// field above, which all use KseField_StatBlock()'s further-dereferenced
// object instead). This is also, independently, the exact offset a 2012
// public Cheat Engine table for this game proposed for "current HP" --
// that offset was real all along; it had just been tested against the
// wrong base object in an earlier pass this same night before this one
// was confirmed correct. Max HP has NO equivalent field anywhere
// (confirmed absent via a thorough double-diff of both objects across a
// real Max HP change) -- it must be computed from class/level/CON, not
// read from a fixed offset (KotorClient.py's _compute_max_hp holds the
// confirmed formula). Confirmed alternative: EffectAbilityIncrease/Decrease
// correctly triggers the engine's own Max HP recalculation, both
// directions, including proper current-HP clamping on a decrease.
#define KSE_OBJ_CURRENT_HP_OFF     0xDC

// Force Powers (known-list) category record -- CONFIRMED at a
// fixed offset from KseField_StatBlock()'s object, same base every other
// field above uses. This "category table" IS the real CSWSCreatureStats::
// classes[] array (confirmed 2026-09-20 against LaneDibello/Kotor-Patch-
// Manager's AddressDatabases/kotor1_0_3.db: KSE_STATS_CATEGORY_TABLE_OFF/
// STRIDE are byte-identical to classes[]'s own offset/stride, and
// known_spells sits at offset 0 of each 40-byte ClassInfo entry, matching
// this record's ptr/count/cap layout) -- "category" is really just which
// CLASS SLOT (0 or 1) a creature's known-spells list belongs to.
#define KSE_STATS_CATEGORY_TABLE_OFF   0x8C  // + (category * KSE_STATS_CATEGORY_STRIDE)
#define KSE_STATS_CATEGORY_STRIDE      40
// RETIRED 2026-09-20 -- was a hardcoded "category 1" assumption, only ever
// confirmed correct for a naturally-leveled character (Jedi taken as a
// genuine second class via the Dantooine trials, base class staying in
// slot 0). Wrong for a character whose Jedi class lives in slot 0 instead
// (Bastila/Jolee/Juhani starting Jedi-only, or anyone converted through
// this project's own class_guardian/class_sentinel admin arms, which
// overwrite slot 0 directly). KseForcePowerOp (kse_hook.cpp) now resolves
// the correct slot live on every call instead -- see its own
// KseResolveJediClassSlot. Left here, unused, as a comment of what NOT to
// go back to, not renumbered/removed.
#define KSE_FORCE_POWER_CATEGORY_RETIRED_DO_NOT_USE 1
// Record layout, relative to the category's own base (STATS_CATEGORY_TABLE_OFF
// + category*STRIDE): {ptr, count, capacity}, the same 12-byte header shape
// every other array in this stat block already uses.
#define KSE_CATEGORY_PTR_OFF   0x00
#define KSE_CATEGORY_COUNT_OFF 0x04
#define KSE_CATEGORY_CAP_OFF   0x08

// -----------------------------------------------------------------------------
// KOTOR AP ADDITION: one new getter for Current HP, chosen the
// same way every prior opcode choice in this project was --
// scripts/scan_opcode_usage.py re-run fresh against all 77 SWMG_ candidate
// ids, filtered against BOTH K1SE's own already-claimed list (583, 584,
// 618, 622, 627, 631-634, 640, 685-687) and this project's own (606, 638,
// 683, 688). NOTE: an earlier pass picked 588/589 for this
// purpose without checking their declared nwscript.nss signatures --
// both turned out to be zero-argument functions
// (SWMG_GetLastBulletHitTarget/Shooter), incompatible with the needed
// (object)->int shape. 617 was then chosen instead, verified BOTH for zero
// real callers AND the exact required signature.
#define KSE_GETCURRENTHP_ID 617   // int SWMG_GetMaxHitPoints(object oFollower);
                                   // confirmed zero real callers via
                                   // scan_opcode_usage.py, not K1SE-claimed,
                                   // and its (object)->int signature exactly
                                   // matches what KseGetCurrentHP needs.
                                   // Everything else this session's design
                                   // needed (SetCurrentHP, AddForcePower,
                                   // RemoveForcePower) fits as new
                                   // nFieldType selectors on the existing
                                   // KSE_FIELD_ID (688) host instead --
                                   // see KSE_FIELD_ADD_FORCE_POWER/
                                   // KSE_FIELD_REMOVE_FORCE_POWER above.
