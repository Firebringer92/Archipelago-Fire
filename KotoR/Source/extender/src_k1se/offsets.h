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
//   KSE_CREATURE_GETHOLDER_RVA : engine creature->holder accessor, __thiscall(creature).
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
// as empirically confirmed rather than source-verified. See this project's
// own memory notes (kotor_engine_constraints.md) for the full test history.
// -----------------------------------------------------------------------------
// KOTOR AP ADDITION, TEMPORARY (research pass, Force Powers offset hunt --
// see kotor_engine_constraints memory / PHASE14.md): dump raw bytes starting
// at the SAME statBlock pointer KseField_StatBlock() already resolves, for a
// live before/after diff around a real Force-power grant. Not a shipped
// feature -- remove this routine once the research pass is done, or keep it
// (renamed/promoted) if a real Force Powers native gets built on what it
// finds.
#define KSE_DUMPSB_ID 638  // void SWMG_SetGunBankTarget(object,int,int); confirmed
                           // 0 real callers via scan_opcode_usage.py, not
                           // claimed by any other KSE_*_ID in this file --
                           // used as (object oCreature, int nOffset, int nLength).

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

#define KSE_STATS_CLASS0_TYPE_OFF  0xa7
#define KSE_STATS_CLASS0_LEVEL_OFF 0xa8
#define KSE_STATS_CLASS1_TYPE_OFF  0xcf
#define KSE_STATS_CLASS1_LEVEL_OFF 0xd0
#define KSE_STATS_FORCE_OFF        0x124
