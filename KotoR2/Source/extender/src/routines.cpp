#include "routines.h"

#include <windows.h>

#include <cstdio>

#include "apfiles.h"
#include "cwrite.h"
#include "exostring.h"
#include "gameobj.h"
#include "log.h"
#include "offsets.h"
#include "probe.h"
#include "vm.h"
#include "vmstack.h"

// POC FORK NOTICE: trimmed from upstream K2SE (routines 885-908 -- fog,
// movement, FOV, camera, spawner, npcvariety -- dropped, not ported) and
// extended with one new routine, 885: K2SE_SetAbilityScoreBase, the write-side
// arm this fork exists to test. See ../../docs/ENGINE_DIFFERENCES.md.

namespace k2se {
namespace routines {
namespace {

// The stack accessors now live in vmstack.h, which also owns
// K2SE_ENABLE_STACK_ABI. Track B roughly doubled their number and added the
// CExoString lifetime rules, which is more than an anonymous namespace in the
// routine table should be carrying.
using vmstack::PopFloat;
using vmstack::PopInt;
using vmstack::PopObject;
using vmstack::PopString;
using vmstack::PushFloat;
using vmstack::PushInt;
using vmstack::PushObject;
using vmstack::PushString;

bool g_probeSeen = false;
bool g_extendedSeen = false;
bool g_selfTestSeen = false;
bool g_echoSeen = false;
bool g_bannerPosted = false;
uint32_t g_reportSeenMask = 0;  // test id 0..31 has been reported at least once
uint32_t g_reportPassMask = 0;  // ... and its last REPORTED answer was a pass

// Per-routine dispatch counts, indexed by position in kExtended (not by routine
// id). Only the trace thinning reads them; nothing may make a decision from one.
uint32_t g_dispatchCount[32] = {0};

// --- on-screen banner --------------------------------------------------------
// void __cdecl AurPostString(const char* text, int x, int y, float fLife)
// Verified by disassembly (see offsets.h). The text buffer is static because
// whether the engine copies the string or keeps the pointer is unproven --
// a static buffer is safe under either semantics.
using AurPostStringFn = void(__cdecl*)(const char* text, int x, int y, float fLife);

void PostBanner(int extendedCount) {
    if (g_bannerPosted) return;
    g_bannerPosted = true;
    static char banner[128];
    _snprintf(banner, sizeof(banner), "K2SE %d.%d.%d active - %d extended routines online",
              K2SE_VERSION_MAJOR, K2SE_VERSION_MINOR, K2SE_VERSION_PATCH, extendedCount);
    banner[sizeof(banner) - 1] = '\0';
    auto fn = reinterpret_cast<AurPostStringFn>(off::kAurPostString);
    fn(banner, 5, 5, 10.0f);
    log::Writef("banner posted on screen: \"%s\"", banner);
}

// --- the extended routine registry ------------------------------------------
// IDs are allocated from 877 upward and, once shipped in a release, are a
// PUBLIC CONTRACT: never reuse an ID. Keep this table, nss/k2se.nss and the
// header generator in tools/m4_deploy_test.py in lockstep -- nwnnsscomp
// assigns IDs by POSITION in nwscript.nss, so table order here must equal
// prototype order there.
//
// 878/879 are development-only self-test routines; they may be renumbered
// before the first public release (nothing has shipped yet).

using ExtendedHandler = int (*)(int nParams);

// 877: int K2SE_GetVersion()
int H_GetVersion(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    if (!PushInt(kVersionEncoded)) return off::kErrPushFailed;
#endif
    return 0;
}

// 878: int K2SE_SelfTest(int nFirst, float fSecond, int nThird)
// End-to-end check of the multi-argument ABI. The return value is
// order-sensitive on purpose: if arguments popped in any order other than
// declaration order, the checksum comes out different and the script-side
// comparison fails loudly.
int H_SelfTest(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    int nFirst = 0, nThird = 0;
    float fSecond = 0.0f;
    if (!PopInt(&nFirst)) return off::kErrParam;
    if (!PopFloat(&fSecond)) return off::kErrParam;
    if (!PopInt(&nThird)) return off::kErrParam;

    const int checksum =
        nFirst * 1000000 + static_cast<int>(fSecond * 10.0f) * 10000 + nThird;

    if (!g_selfTestSeen) {
        g_selfTestSeen = true;
        log::Writef("SelfTest pop order: first=%d  second(float x10)=%d  third=%d  -> %d",
                    nFirst, static_cast<int>(fSecond * 10.0f), nThird, checksum);
    }
    if (!PushInt(checksum)) return off::kErrPushFailed;
#endif
    return 0;
}

// 879: int K2SE_ReportTest(int nTestId, int nExpected, int nActual)
// Lets a compiled test script report what IT observed into k2se.log; the
// script is the only place the full round trip (compiler -> bytecode ->
// interpreter -> K2SE -> back) is visible. Returns 1 on match, 0 otherwise.
int H_ReportTest(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    int nTestId = 0, nExpected = 0, nActual = 0;
    if (!PopInt(&nTestId)) return off::kErrParam;
    if (!PopInt(&nExpected)) return off::kErrParam;
    if (!PopInt(&nActual)) return off::kErrParam;

    const bool pass = (nExpected == nActual);

    // One line per test id was the right instinct -- the battery rides a
    // heartbeat and re-runs every few seconds -- but reporting only the FIRST
    // sample made that sample the session's verdict. On 2026-08-29 the first
    // heartbeat fired before the PC could be resolved, five tests logged FAIL,
    // and the routines then worked for the rest of the session with nothing in
    // the log to say so. The on-screen banner disagreed with the log for two
    // hours and only a human looking at the screen could tell.
    //
    // So: still one line per id in the steady state, plus a line whenever the
    // ANSWER CHANGES. A stable session logs byte-for-byte what it logged
    // before; an unstable one becomes self-describing.
    const bool inRange = nTestId >= 0 && nTestId < 32;
    const uint32_t bit = inRange ? (1u << nTestId) : 0u;
    const bool firstTime = inRange && !(g_reportSeenMask & bit);
    const bool changed = inRange && !firstTime && (pass != ((g_reportPassMask & bit) != 0));

    if (firstTime || changed) {
        g_reportSeenMask |= bit;
        if (pass)
            g_reportPassMask |= bit;
        else
            g_reportPassMask &= ~bit;

        if (changed)
            log::Writef("TEST %2d: expected %d, got %d  ->  %s   "
                        "(CHANGED at t+%u ms -- it answered %s before)",
                        nTestId, nExpected, nActual, pass ? "PASS" : "FAIL",
                        log::MillisSinceInit(), pass ? "FAIL" : "PASS");
        else
            log::Writef("TEST %2d: expected %d, got %d  ->  %s", nTestId, nExpected,
                        nActual, pass ? "PASS" : "FAIL");
    } else {
        log::Trace("test %d: expected %d, got %d -> %s", nTestId, nExpected, nActual,
                   pass ? "pass" : "FAIL");
    }
    if (!PushInt(pass ? 1 : 0)) return off::kErrPushFailed;
#endif
    return 0;
}

// 880: string K2SE_EchoString(string sIn)
// The string round trip, end to end: pop a script-supplied string, then push it
// straight back. A script comparing the result against what it sent proves the
// whole path -- compiler, bytecode, VM stack, CExoString construction, and the
// engine's copy semantics in both directions.
//
// It is deliberately an identity function. Anything cleverer would make a
// failure ambiguous between "the string ABI is wrong" and "the transformation is
// wrong", and the string ABI is the thing under test.
int H_EchoString(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    // Must be constructed before the engine touches it: PopString copy-assigns,
    // which frees whatever pointer it finds in the destination first.
    ExoString value;
    if (!value.valid()) {
        log::Write("EchoString: CExoString construction failed");
        return off::kErrParam;
    }
    if (!PopString(&value)) return off::kErrParam;

    if (!g_echoSeen) {
        g_echoSeen = true;
        // Both numbers, because their DIFFERENCE is the finding: the engine's
        // second field counts the allocation, not the characters. For a fresh
        // string they differ by exactly one; after a buffer-reusing assignment
        // they differ by more, which is why length() scans rather than subtracts.
        log::Writef("*** FIRST STRING ROUND TRIP: received \"%s\" "
                    "(length %u, buffer %u) ***",
                    value.c_str(), value.length(), value.buffer_size());
    }

    // The engine allocates its own copy here, so `value` stays ours and its
    // destructor still runs on the way out of this scope.
    if (!PushString(&value)) return off::kErrPushFailed;
#endif
    return 0;
}

// --- the first routines meant for actual mods --------------------------------
// 881..884. Everything before these was plumbing that only proves K2SE works.
//
// All four are READ-ONLY, deliberately. The struct offsets they walk are the
// least-verified thing upstream -- imported layout claims that cannot be
// checked against the file, only by being right. A wrong offset on a read costs
// a wrong number; the same offset on a write corrupts a creature in the player's
// save. Upstream K2SE held the attribute setters back for exactly this reason,
// pending a confirmed live read path. THIS FORK exists to take that next step:
// see 885 (K2SE_SetAbilityScoreBase) below, the one mutator this POC adds and
// the thing it is actually testing.
//
// Every one returns a sentinel rather than failing the script, so a mod can test
// the result instead of dying:
//   -1  the creature, its stats, or the read could not be resolved

constexpr int kUnknown = -1;

// Shared prologue: pop an object id, resolve it to a creature's stats block.
// Returns null and leaves *popOk false if the argument itself could not be read,
// which is the one case where we must not push a result.
// `who` is the caller's name, and it is not decoration: all four routines share
// this path, so without it the log cannot say which one was asking.
void* PopCreatureStats(const char* who, bool* popOk) {
    *popOk = false;
#if K2SE_ENABLE_STACK_ABI
    // PopObject, not PopInt. The VM stack is typed -- the pop path checks the
    // slot's type tag before handing the value over (StackPopString, for
    // instance, tests for tag 5) -- so popping a declared `object` as an int
    // would simply fail. An OBJECT is a uint32 handle, but the accessors are not
    // interchangeable.
    uint32_t objectId = 0;
    if (!PopObject(&objectId)) return nullptr;
    *popOk = true;
    void* creature = gameobj::CreatureFromObjectId(objectId);
    void* stats = creature ? gameobj::CreatureStats(creature) : nullptr;
    gameobj::ReportWalk(who);
    return stats;
#else
    (void)who;
    return nullptr;
#endif
}

// 881: int K2SE_GetAbilityScoreBase(object oCreature, int nAbility)
// The base attribute, before items and effects. Reads a byte out of the stats
// block; makes no engine call at all, which makes it the safest of the four.
int H_GetAbilityScoreBase(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    bool popped = false;
    void* stats = PopCreatureStats("K2SE_GetAbilityScoreBase", &popped);
    if (!popped) return off::kErrParam;

    int ability = 0;
    if (!PopInt(&ability)) return off::kErrParam;

    int value = kUnknown;
    if (stats) gameobj::AbilityBase(stats, ability, &value);
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// 882: int K2SE_GetSkillRankBase(object oCreature, int nSkill)
// The rank the creature actually bought, without item or effect modifiers --
// which vanilla GetSkillRank cannot report.
int H_GetSkillRankBase(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    bool popped = false;
    void* stats = PopCreatureStats("K2SE_GetSkillRankBase", &popped);
    if (!popped) return off::kErrParam;

    int skill = 0;
    if (!PopInt(&skill)) return off::kErrParam;

    int value = kUnknown;
    if (stats) gameobj::SkillRankBase(stats, skill, &value);
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// 883: int K2SE_GetFeatAcquired(object oCreature, int nFeat)
// Whether the creature HAS the feat, as opposed to whether it can use it right
// now -- the distinction vanilla GetHasFeat blurs by folding in daily uses.
int H_GetFeatAcquired(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    bool popped = false;
    void* stats = PopCreatureStats("K2SE_GetFeatAcquired", &popped);
    if (!popped) return off::kErrParam;

    int feat = 0;
    if (!PopInt(&feat)) return off::kErrParam;

    int value = kUnknown;
    if (stats) gameobj::HasFeat(stats, feat, &value);
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// 884: int K2SE_GetSpellAcquired(object oCreature, int nSpell)
// Known, regardless of whether there are Force points to cast it.
int H_GetSpellAcquired(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    bool popped = false;
    void* stats = PopCreatureStats("K2SE_GetSpellAcquired", &popped);
    if (!popped) return off::kErrParam;

    int spell = 0;
    if (!PopInt(&spell)) return off::kErrParam;

    int value = kUnknown;
    if (stats) gameobj::HasSpell(stats, spell, &value);
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// --- the arm under test -------------------------------------------------------
// 885: int K2SE_SetAbilityScoreBase(object oCreature, int nAbility, int nValue)
//
// POC addition, not upstream K2SE. The write-side counterpart to 881 above.
// See gameobj.h's SetAbilityBase() doc comment and offsets.h for why this is
// a genuinely different confidence level from every routine before it: the
// address is confirmed only by prologue-byte match, and the call has never
// been exercised live before this fork. Returns TRUE only if the call
// completed without faulting -- a script MUST read the value back with
// K2SE_GetAbilityScoreBase to confirm it actually landed.
int H_SetAbilityScoreBase(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    bool popped = false;
    void* stats = PopCreatureStats("K2SE_SetAbilityScoreBase", &popped);
    if (!popped) return off::kErrParam;

    int ability = 0, value = 0;
    if (!PopInt(&ability)) return off::kErrParam;
    if (!PopInt(&value)) return off::kErrParam;

    bool ok = stats && gameobj::SetAbilityBase(stats, ability, value);
    log::Writef("K2SE_SetAbilityScoreBase: ability=%d value=%d stats=%p -> %s", ability, value,
                stats, ok ? "called" : "refused/faulted");
    if (!PushInt(ok ? 1 : 0)) return off::kErrPushFailed;
#endif
    return 0;
}

// 886: int K2SE_Diag(string sTag, string sMsg)
// Writes "[sTag] sMsg" to k2se.log and returns 1. Every line goes straight to the
// file, so a script's progress survives a crash that would lose on-screen text.
// Arguments pop in declaration order, tag first.
int H_Diag(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString tag;
    ExoString msg;
    if (!tag.valid() || !msg.valid()) {
        log::Write("K2SE_Diag: CExoString construction failed");
        return off::kErrParam;
    }
    if (!PopString(&tag)) return off::kErrParam;
    if (!PopString(&msg)) return off::kErrParam;
    log::Writef("[%s] %s", tag.c_str(), msg.c_str());
    if (!PushInt(1)) return off::kErrPushFailed;
#endif
    return 0;
}

// --- research probes ----------------------------------------------------------
// 887-891. Generic, field-agnostic tools for finding and checking struct offsets
// from inside a running game. nArea selects which struct of the creature the
// offset is relative to: 0 = CSWSCreature, 1 = CSWSCreatureStats.

// Resolves a script object to the base address of one of the creature's structs.
void* ResolveArea(uint32_t objectId, int area) {
    void* creature = gameobj::CreatureFromObjectId(objectId);
    if (!creature) return nullptr;
    if (area == 0) return creature;
    if (area == 1) return gameobj::CreatureStats(creature);
    return nullptr;
}

// 887: int K2SE_ConfigInt(string sKey, int nDefault)
// Reads "key=value" from %LOCALAPPDATA%\K2SE\config.txt on every call.
int H_ConfigInt(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString key;
    if (!key.valid()) return off::kErrParam;
    int fallback = 0;
    if (!PopString(&key)) return off::kErrParam;
    if (!PopInt(&fallback)) return off::kErrParam;
    const int value = probe::ConfigInt(key.c_str(), fallback);
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// 888: int K2SE_ReadMem(object oCreature, int nArea, int nOffset, int nWidth)
// Read-only. Returns the value, or probe::kReadFailed (-2147483647) on failure.
int H_ReadMem(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int area = 0, offset = 0, width = 0;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&area)) return off::kErrParam;
    if (!PopInt(&offset)) return off::kErrParam;
    if (!PopInt(&width)) return off::kErrParam;

    int value = probe::kReadFailed;
    const void* base = nullptr;
    if (area == 2) {
        // Absolute mode: nOffset IS the address (for following a pointer read earlier).
        // The object argument is ignored. Reads are fault-tolerant, so a bad address
        // returns the failure value instead of crashing.
        base = reinterpret_cast<const void*>(static_cast<uintptr_t>(static_cast<uint32_t>(offset)));
        offset = 0;
    } else {
        base = ResolveArea(objectId, area);
    }
    if (!base || !probe::ReadMem(base, offset, width, &value)) {
        value = probe::kReadFailed;
        log::Writef("K2SE_ReadMem: object=0x%08X area=%d offset=0x%X width=%d -> FAILED (base=%p)",
                    objectId, area, offset, width, base);
    } else {
        log::Trace("K2SE_ReadMem: area=%d offset=0x%X width=%d -> %d", area, offset, width, value);
    }
    if (!PushInt(value)) return off::kErrPushFailed;
#endif
    return 0;
}

// 889: int K2SE_DumpMem(object oCreature, int nArea, int nSize, string sLabel)
// Writes the first nSize bytes of the struct to %LOCALAPPDATA%\K2SE\dumps\<label>.bin
// for offline comparison. Returns bytes written, or -1.
int H_DumpMem(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int area = 0, size = 0;
    ExoString label;
    if (!label.valid()) return off::kErrParam;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&area)) return off::kErrParam;
    if (!PopInt(&size)) return off::kErrParam;
    if (!PopString(&label)) return off::kErrParam;

    int written = -1;
    const void* base = ResolveArea(objectId, area);
    if (base) written = probe::DumpMem(base, size, label.c_str());
    log::Writef("K2SE_DumpMem: label=%s area=%d base=%p requested=%d -> wrote %d bytes",
                label.c_str(), area, base, size, written);
    if (!PushInt(written)) return off::kErrPushFailed;
#endif
    return 0;
}

// 890: int K2SE_GetAddress(object oCreature, int nArea)
// The struct's base address as an integer, for external tools. 0 if unresolved.
int H_GetAddress(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int area = 0;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&area)) return off::kErrParam;
    const void* base = ResolveArea(objectId, area);
    log::Writef("K2SE_GetAddress: object=0x%08X area=%d -> %p", objectId, area, base);
    if (!PushInt(static_cast<int>(reinterpret_cast<uintptr_t>(base)))) return off::kErrPushFailed;
#endif
    return 0;
}

// 891: int K2SE_WriteMem(object oCreature, int nArea, int nOffset, int nWidth, int nValue)
// DANGEROUS. Raw write into a creature struct, for validating a candidate offset on
// a throwaway save. Refused unless config.txt contains allow_memwrite=1; that file is
// outside the game folder, so a shipped script cannot enable it. Returns 1 on a write.
int H_WriteMem(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int area = 0, offset = 0, width = 0, value = 0;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&area)) return off::kErrParam;
    if (!PopInt(&offset)) return off::kErrParam;
    if (!PopInt(&width)) return off::kErrParam;
    if (!PopInt(&value)) return off::kErrParam;

    int ok = 0;
    if (probe::ConfigInt("allow_memwrite", 0) != 1) {
        log::Writef("K2SE_WriteMem: REFUSED (config.txt has no allow_memwrite=1): "
                    "area=%d offset=0x%X width=%d value=%d", area, offset, width, value);
    } else {
        void* base = nullptr;
        if (area == 3) {
            // Code patch (research): nOffset IS the address of game code to change.
            void* addr = reinterpret_cast<void*>(static_cast<uintptr_t>(static_cast<uint32_t>(offset)));
            int previousCode = 0;
            if (probe::WriteCode(addr, width, value, &previousCode)) {
                log::Writef("K2SE_WriteMem: CODE address=%p width=%d old=%d new=%d -> PATCHED", addr, width,
                            previousCode, value);
                if (!PushInt(1)) return off::kErrPushFailed;
            } else {
                log::Writef("K2SE_WriteMem: CODE address=%p width=%d value=%d -> FAILED", addr, width, value);
                if (!PushInt(0)) return off::kErrPushFailed;
            }
            return 0;
        }
        if (area == 2) {
            // Absolute mode, as in K2SE_ReadMem: nOffset IS the address. Needed for state that
            // is not on a creature, such as the player's credits.
            base = reinterpret_cast<void*>(static_cast<uintptr_t>(static_cast<uint32_t>(offset)));
            offset = 0;
        } else {
            base = const_cast<void*>(ResolveArea(objectId, area));
        }
        int previous = 0;
        if (base && probe::WriteMem(base, offset, width, value, &previous)) {
            ok = 1;
            log::Writef("K2SE_WriteMem: area=%d base=%p offset=0x%X width=%d old=%d new=%d -> WROTE",
                        area, base, offset, width, previous, value);
        } else {
            log::Writef("K2SE_WriteMem: area=%d base=%p offset=0x%X width=%d value=%d -> FAILED",
                        area, base, offset, width, value);
        }
    }
    if (!PushInt(ok)) return off::kErrPushFailed;
#endif
    return 0;
}

// --- the shipped writers (892-900) ----------------------------------------------
// Thin adapters over cwrite.cpp, which resolves the creature and validates every argument. The
// scripts see: 1 changed, 0 refused, -1 could not resolve the creature or a pointer on the way.
// No config switch: these are the supported way to change those fields, unlike K2SE_WriteMem.
template <int (*Fn)(uint32_t, int)>
int HObjInt(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int a = 0;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&a)) return off::kErrParam;
    if (!PushInt(Fn(objectId, a))) return off::kErrPushFailed;
#endif
    return 0;
}

template <int (*Fn)(uint32_t, int, int)>
int HObjIntInt(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    uint32_t objectId = 0;
    int a = 0, b = 0;
    if (!PopObject(&objectId)) return off::kErrParam;
    if (!PopInt(&a)) return off::kErrParam;
    if (!PopInt(&b)) return off::kErrParam;
    if (!PushInt(Fn(objectId, a, b))) return off::kErrPushFailed;
#endif
    return 0;
}

int HInt(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    int a = 0;
    if (!PopInt(&a)) return off::kErrParam;
    if (!PushInt(cwrite::SetPartyCredits(a))) return off::kErrPushFailed;
#endif
    return 0;
}

// --- Archipelago delivery transport (902-906) ---------------------------------
// 902: int K2SE_InboxInt(string sKey, int nDefault)  -- integer value of a key in ap\inbox.txt
int H_InboxInt(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString key;
    if (!key.valid()) return off::kErrParam;
    int fallback = 0;
    if (!PopString(&key)) return off::kErrParam;
    if (!PopInt(&fallback)) return off::kErrParam;
    if (!PushInt(apfiles::InboxInt(key.c_str(), fallback))) return off::kErrPushFailed;
#endif
    return 0;
}

// 903: string K2SE_InboxStr(string sKey)  -- text of a key in ap\inbox.txt (up to 200 characters), "" if absent
int H_InboxStr(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString key;
    if (!key.valid()) return off::kErrParam;
    if (!PopString(&key)) return off::kErrParam;
    char buf[201];
    apfiles::InboxStr(key.c_str(), buf, sizeof(buf));
    ExoString out(buf);
    if (!out.valid()) return off::kErrParam;
    if (!PushString(&out)) return off::kErrPushFailed;
#endif
    return 0;
}

// 904: int K2SE_OutboxPut(string sLine)  -- appends "<seq>|<line>" to ap\outbox.txt
int H_OutboxPut(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString line;
    if (!line.valid()) return off::kErrParam;
    if (!PopString(&line)) return off::kErrParam;
    if (!PushInt(apfiles::OutboxPut(line.c_str()) ? 1 : 0)) return off::kErrPushFailed;
#endif
    return 0;
}

// 905: int K2SE_MemSet(string sKey, string sValue)  -- process-lifetime store
int H_MemSet(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString key;
    ExoString value;
    if (!key.valid() || !value.valid()) return off::kErrParam;
    if (!PopString(&key)) return off::kErrParam;
    if (!PopString(&value)) return off::kErrParam;
    if (!PushInt(apfiles::MemSet(key.c_str(), value.c_str()) ? 1 : 0)) return off::kErrPushFailed;
#endif
    return 0;
}

// 906: string K2SE_MemGet(string sKey)
int H_MemGet(int /*nParams*/) {
#if K2SE_ENABLE_STACK_ABI
    ExoString key;
    if (!key.valid()) return off::kErrParam;
    if (!PopString(&key)) return off::kErrParam;
    ExoString out(apfiles::MemGet(key.c_str()));
    if (!out.valid()) return off::kErrParam;
    if (!PushString(&out)) return off::kErrPushFailed;
#endif
    return 0;
}

struct Extended {
    int id;
    const char* name;
    int argc;  // Q7: the compiler always emits the full declared argc,
               // materializing omitted defaults itself -- so a mismatch here
               // means a foreign or corrupted script, and we refuse to touch
               // the VM stack rather than desynchronize it.
    ExtendedHandler handler;
};

constexpr Extended kExtended[] = {
    {877, "K2SE_GetVersion", 0, &H_GetVersion},
    {878, "K2SE_SelfTest", 3, &H_SelfTest},
    {879, "K2SE_ReportTest", 3, &H_ReportTest},
    {880, "K2SE_EchoString", 1, &H_EchoString},
    {881, "K2SE_GetAbilityScoreBase", 2, &H_GetAbilityScoreBase},
    {882, "K2SE_GetSkillRankBase", 2, &H_GetSkillRankBase},
    {883, "K2SE_GetFeatAcquired", 2, &H_GetFeatAcquired},
    {884, "K2SE_GetSpellAcquired", 2, &H_GetSpellAcquired},
    {885, "K2SE_SetAbilityScoreBase", 3, &H_SetAbilityScoreBase},
    {886, "K2SE_Diag", 2, &H_Diag},
    {887, "K2SE_ConfigInt", 2, &H_ConfigInt},
    {888, "K2SE_ReadMem", 4, &H_ReadMem},
    {889, "K2SE_DumpMem", 4, &H_DumpMem},
    {890, "K2SE_GetAddress", 2, &H_GetAddress},
    {891, "K2SE_WriteMem", 5, &H_WriteMem},
    {892, "K2SE_SetRace", 2, &HObjInt<cwrite::SetRace>},
    {893, "K2SE_SetCreatureCredits", 2, &HObjInt<cwrite::SetCreatureCredits>},
    {894, "K2SE_SetPartyCredits", 1, &HInt},
    {895, "K2SE_SetSaveBonus", 3, &HObjIntInt<cwrite::SetSaveBonus>},
    {896, "K2SE_SetClassLevel", 3, &HObjIntInt<cwrite::SetClassLevel>},
    {897, "K2SE_SetClassId", 3, &HObjIntInt<cwrite::SetClassId>},
    {898, "K2SE_RemoveClass", 2, &HObjInt<cwrite::RemoveClass>},
    {899, "K2SE_RemoveFeat", 2, &HObjInt<cwrite::RemoveFeat>},
    {900, "K2SE_RemovePower", 2, &HObjInt<cwrite::RemovePower>},
    {901, "K2SE_SetSkillRank", 3, &HObjIntInt<cwrite::SetSkillRank>},
    {902, "K2SE_InboxInt", 2, &H_InboxInt},
    {903, "K2SE_InboxStr", 1, &H_InboxStr},
    {904, "K2SE_OutboxPut", 1, &H_OutboxPut},
    {905, "K2SE_MemSet", 2, &H_MemSet},
    {906, "K2SE_MemGet", 1, &H_MemGet},
};
constexpr int kExtendedCount = static_cast<int>(sizeof(kExtended) / sizeof(kExtended[0]));

// g_dispatchCount is indexed by position in this table. Growing the table past
// the counter array must be a compile error, not a stray write past the end.
static_assert(kExtendedCount <= static_cast<int>(sizeof(g_dispatchCount) /
                                                sizeof(g_dispatchCount[0])),
              "g_dispatchCount is too small for kExtended -- grow it");

}  // namespace

void Init() {
    log::Writef("extended routines registered: %d (first free vanilla ID is %d)", kExtendedCount,
                off::kFirstExtendedId);
    for (const Extended& e : kExtended)
        log::Writef("  id %d -> %s (argc %d)", e.id, e.name, e.argc);
    log::Writef("stack ABI: %s",
                K2SE_ENABLE_STACK_ABI ? "ENABLED" : "disabled (DESIGN.md Q5 unresolved)");
}

bool Intercepts(int id) { return id == off::kRoutineAbs; }

bool DispatchVanillaOverride(void* self, int id, int nParams, int* result) {
    if (id != off::kRoutineAbs) return false;

#if !K2SE_ENABLE_STACK_ABI
    // Without a verified stack ABI we must not touch arguments. Fall through to
    // the engine so abs() keeps working exactly as it always did.
    (void)self;
    (void)nParams;
    (void)result;
    if (!g_probeSeen) {
        g_probeSeen = true;
        log::Write("abs() intercept reached, but the stack ABI is disabled -> passing through.");
    }
    return false;
#else
    (void)self;
    // abs() takes exactly one argument and has no defaults, so any other argc
    // is not the routine we think it is -- hand it back to the engine.
    if (nParams != 1) return false;

    int value = 0;
    if (!PopInt(&value)) {
        log::Write("abs() intercept: StackPopInteger failed");
        *result = off::kErrParam;  // same code the engine's own handler returns
        return true;
    }

    if (value == kProbeMagic) {
        if (!g_probeSeen) {
            g_probeSeen = true;
            log::Writef("PRESENCE PROBE answered with version %d", kVersionEncoded);
        }
        PostBanner(kExtendedCount);
        if (!PushInt(kVersionEncoded)) {
            *result = off::kErrPushFailed;
            return true;
        }
        *result = 0;
        return true;
    }

    // Faithful reimplementation for every other input. abs() is pure, has no
    // default parameters and argc is always 1, so this is bit-identical to
    // vanilla (abs(INT_MIN) is UB in both).
    if (!PushInt(value < 0 ? -value : value)) {
        *result = off::kErrPushFailed;
        return true;
    }
    *result = 0;
    return true;
#endif
}

int DispatchExtended(void* /*self*/, int id, int nParams) {
    for (const Extended& e : kExtended) {
        if (e.id != id) continue;
        if (!g_extendedSeen) {
            g_extendedSeen = true;
            log::Writef("*** FIRST EXTENDED ROUTINE CALL: id=%d (%s), nParams=%d ***", id, e.name,
                        nParams);
            log::Write("*** a compiled NWScript reached a routine that did not exist "
                       "in this engine. ***");
        }
        if (nParams != e.argc) {
            // Q7 guarantees the compiler emits the full declared argc, so this
            // is a script compiled against a mismatched header. Popping an
            // unknown number of values would desynchronize the VM stack;
            // refuse instead. -2001 aborts only the calling script.
            log::Writef("%s called with nParams=%d, declared argc=%d -> refusing (-2001)", e.name,
                        nParams, e.argc);
            return off::kErrParam;
        }
        // Thinned, because unthinned this was the whole log. A traced session on
        // 2026-08-30 wrote 205,808 of these two lines and reached 9 MB, which
        // buries the handful of lines anyone actually opens the file for. The
        // first few calls of each routine are where the interesting information
        // is -- that it dispatched at all, with what argc, returning what -- and
        // after that it is the same line forever. So: the first eight in full,
        // then one in every 1024 carrying the running count.
        const size_t slot = static_cast<size_t>(&e - kExtended);
        const uint32_t n = ++g_dispatchCount[slot];
        const bool loud = (n <= 8) || ((n & 1023) == 0);

        if (loud) log::Trace("extended routine %d (%s), nParams=%d [call %u]", id, e.name,
                             nParams, n);
        const int rc = e.handler(nParams);
        if (loud) log::Trace("  -> rc=%d", rc);
        PostBanner(kExtendedCount);
        return rc;
    }

    // Unregistered extended ID: return exactly what the engine returns for an
    // out-of-range routine, so behaviour with K2SE matches behaviour without it.
    log::Trace("unregistered extended routine %d -> %d", id, off::kErrCommandNotFound);
    return off::kErrCommandNotFound;
}

}  // namespace routines
}  // namespace k2se
