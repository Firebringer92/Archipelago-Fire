#include "gameobj.h"

#include <windows.h>

#include "log.h"
#include "offsets.h"

namespace k2se {
namespace gameobj {
namespace {

using GetCreatureByIdFn = void*(__thiscall*)(void* server, uint32_t objectId);
using GetSkillRankFn = uint8_t(__thiscall*)(void* stats, uint8_t skill, void* unused,
                                            int baseOnly);
using HasFeatFn = uint8_t(__thiscall*)(void* stats, uint16_t feat);
using HasSpellFn = uint8_t(__thiscall*)(void* stats, uint8_t cls, uint32_t spell, int flag);

// The game is a 32-bit process; with the 4GB/LAA patch its heap can reach up to
// 0x7FFFFFFF, without it 0x7FFFFFFF is still the ceiling for user space. Anything
// below the image base is not an object -- most importantly it catches a small
// integer that has been mistaken for a pointer, which is what a wrong struct
// offset usually produces.
constexpr uintptr_t kMinPlausible = 0x00010000;
constexpr uintptr_t kMaxPlausible = 0x7FFFFFFF;

// Every read through an imported struct offset goes through these. A wrong
// offset should cost us a logged refusal, not the player's session.
bool SafeReadPtr(const void* at, void** out) {
    __try {
        *out = *reinterpret_cast<void* const*>(at);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeReadByte(const void* at, uint8_t* out) {
    __try {
        *out = *reinterpret_cast<const volatile uint8_t*>(at);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// Calling into the engine with a pointer we are not certain about. The call
// itself is what might fault, so it is the call that is guarded.
bool SafeCallSkillRank(void* stats, uint8_t skill, int* out) {
    __try {
        auto fn = reinterpret_cast<GetSkillRankFn>(off::kStatsGetSkillRank);
        // (skill, NULL, baseOnly=1): the base rank, without item or effect
        // modifiers. Argument count confirmed by the epilogue's `ret 12`.
        *out = static_cast<int>(fn(stats, skill, nullptr, 1));
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeCallHasFeat(void* stats, uint16_t feat, int* out) {
    __try {
        auto fn = reinterpret_cast<HasFeatFn>(off::kStatsHasFeat);
        *out = fn(stats, feat) ? 1 : 0;
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeCallHasSpell(void* stats, uint32_t spell, int* out) {
    __try {
        auto fn = reinterpret_cast<HasSpellFn>(off::kStatsHasSpell);
        *out = fn(stats, 0, spell, 0) ? 1 : 0;
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SafeCallCreatureById(void* server, uint32_t objectId, void** out) {
    __try {
        auto fn = reinterpret_cast<GetCreatureByIdFn>(off::kGetCreatureByGameObjectID);
        *out = fn(server, objectId);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// --- what the last walk actually did -----------------------------------------
// Ordered by how far the walk got, so the value doubles as a progress marker.
enum Stage {
    kStageOk = 0,
    kStageIdInvalid,         // OBJECT_INVALID; the engine was never asked
    kStageAppFault,          // the read of [kAppManagerGlobal] faulted
    kStageAppRejected,       // ... gave a value LooksLikePointer refused
    kStageServerFault,       // the read of [appManager + 0x08] faulted
    kStageServerRejected,
    kStageLookupFault,       // GetCreatureByGameObjectID faulted
    kStageCreatureNull,      // the engine returned 0 -- no such creature
    kStageCreatureRejected,  // it returned something implausible
    kStageStatsFault,        // the read of [creature + kCreatureOffStats] faulted
    kStageStatsNull,
    kStageStatsRejected,
    kStageCount
};

const char* const kStageName[kStageCount] = {
    "OK",           "ID_INVALID",      "APP_FAULT",    "APP_REJECTED",
    "SERVER_FAULT", "SERVER_REJECTED", "LOOKUP_FAULT", "CREATURE_NULL",
    "CREATURE_REJECTED", "STATS_FAULT", "STATS_NULL",  "STATS_REJECTED",
};

struct Walk {
    uint32_t objectId;
    void* appManager;
    void* server;
    void* creature;
    void* stats;
    int stage;
};

// Written only by the three walk functions, read only by ReportWalk. Script
// routines run on the game's main thread, so no lock is involved or needed.
Walk g_walk = {0, nullptr, nullptr, nullptr, nullptr, kStageOk};

uint32_t g_walkCount = 0;
int g_lastStage = -1;      // outcome of the previous walk; -1 before the first
uint32_t g_runLength = 0;  // consecutive walks with that outcome
uint32_t g_runFirstMs = 0;
uint32_t g_linesWritten = 0;
bool g_capped = false;

// A hard ceiling, because an outcome that flapped every heartbeat would still
// flood. Transition-only logging makes a healthy session cost one line, so this
// is generous by two orders of magnitude and cheap insurance either way.
constexpr uint32_t kMaxReportLines = 96;

bool LineBudget() {
    if (g_capped) return false;
    if (g_linesWritten >= kMaxReportLines) {
        g_capped = true;
        log::Write("gameobj: chain diagnostics capped at 96 lines -- the outcome is "
                   "flapping; arm K2SE_DIAGNOSTIC for the full trace");
        return false;
    }
    ++g_linesWritten;
    return true;
}

unsigned Hex(const void* p) {
    return static_cast<unsigned>(reinterpret_cast<uintptr_t>(p));
}

void ResetWalk(uint32_t objectId) {
    ++g_walkCount;
    g_walk.objectId = objectId;
    g_walk.appManager = nullptr;
    g_walk.server = nullptr;
    g_walk.creature = nullptr;
    g_walk.stats = nullptr;
    g_walk.stage = kStageOk;
}

}  // namespace

bool LooksLikePointer(const void* p) {
    const uintptr_t v = reinterpret_cast<uintptr_t>(p);
    return v >= kMinPlausible && v <= kMaxPlausible && (v & 3) == 0;
}

void* ServerExoApp() {
    void* appManager = nullptr;
    if (!SafeReadPtr(reinterpret_cast<const void*>(off::kAppManagerGlobal), &appManager)) {
        g_walk.stage = kStageAppFault;
        return nullptr;
    }
    g_walk.appManager = appManager;
    if (!LooksLikePointer(appManager)) {
        g_walk.stage = kStageAppRejected;
        return nullptr;
    }

    void* server = nullptr;
    if (!SafeReadPtr(static_cast<const char*>(appManager) + off::kAppManagerOffServer,
                     &server)) {
        g_walk.stage = kStageServerFault;
        return nullptr;
    }
    g_walk.server = server;
    if (!LooksLikePointer(server)) {
        g_walk.stage = kStageServerRejected;
        return nullptr;
    }
    return server;
}

void* CreatureFromObjectId(uint32_t objectId) {
    // Cleared BEFORE the first hop, never after the last: an early return must
    // not leave a previous call's pointers standing where the report would read
    // them as this call's.
    ResetWalk(objectId);

    if (objectId == off::kObjectInvalid) {
        g_walk.stage = kStageIdInvalid;
        return nullptr;
    }

    void* server = ServerExoApp();
    if (!server) return nullptr;  // ServerExoApp has already named the stage

    void* creature = nullptr;
    if (!SafeCallCreatureById(server, objectId, &creature)) {
        g_walk.stage = kStageLookupFault;
        log::Write("gameobj: GetCreatureByGameObjectID faulted");
        return nullptr;
    }
    g_walk.creature = creature;
    // Null and implausible are the same refusal to the caller and always have
    // been. They are split here only so the log can say which one happened.
    if (creature == nullptr) {
        g_walk.stage = kStageCreatureNull;
        return nullptr;
    }
    if (!LooksLikePointer(creature)) {
        g_walk.stage = kStageCreatureRejected;
        return nullptr;
    }
    return creature;
}

void* CreatureStats(void* creature) {
    if (!LooksLikePointer(creature)) {
        g_walk.stage = kStageCreatureRejected;
        return nullptr;
    }
    void* stats = nullptr;
    if (!SafeReadPtr(static_cast<const char*>(creature) + off::kCreatureOffStats, &stats)) {
        g_walk.stage = kStageStatsFault;
        return nullptr;
    }
    g_walk.stats = stats;
    if (stats == nullptr) {
        g_walk.stage = kStageStatsNull;
        return nullptr;
    }
    if (!LooksLikePointer(stats)) {
        g_walk.stage = kStageStatsRejected;
        return nullptr;
    }
    return stats;
}

void ReportWalk(const char* who) {
    const Walk w = g_walk;  // snapshot; nothing below may observe a later walk
    const uint32_t nowMs = log::MillisSinceInit();

    if (w.stage == g_lastStage) {
        ++g_runLength;
        // Marker-gated and thinned even then: one line per 64 walks, not one
        // per walk.
        if ((g_runLength & 63) == 0)
            log::Trace("gameobj: %s still %s (%u in a row)", who, kStageName[w.stage],
                       g_runLength);
        return;
    }

    // Close the run that just ended. Printing it HERE, rather than at the start
    // of the next one, is what makes a recovery legible: "ID_INVALID repeated 6
    // times over 6180 ms" followed by "-> OK" is the entire diagnosis, and it is
    // exactly what the 2026-08-29 session could not say.
    if (g_lastStage >= 0 && LineBudget())
        log::Writef("gameobj: ... previous outcome %s repeated %u time(s) over %u ms",
                    kStageName[g_lastStage], g_runLength, nowMs - g_runFirstMs);

    g_lastStage = w.stage;
    g_runLength = 1;
    g_runFirstMs = nowMs;

    if (!LineBudget()) return;
    log::Writef("gameobj: %s walk #%u at t+%u ms -> %s | id=0x%08X app=0x%08X "
                "srv=0x%08X cre=0x%08X sts=0x%08X",
                who, g_walkCount, nowMs, kStageName[w.stage], w.objectId,
                Hex(w.appManager), Hex(w.server), Hex(w.creature), Hex(w.stats));
}

bool AbilityBase(void* stats, int ability, int* out) {
    if (!LooksLikePointer(stats) || !out) return false;
    if (ability < 0 || ability >= off::kAbilityCount) return false;

    const char* at = static_cast<const char*>(stats) + off::kStatsOffAbilityBase +
                     ability * off::kStatsAbilityStride;
    uint8_t value = 0;
    if (!SafeReadByte(at, &value)) return false;
    *out = value;
    return true;
}

// --- POC addition, not upstream K2SE ----------------------------------------
// The six per-ability setters (offsets_generated.h, off::game::
// kCSWSCreatureStats_Set*Base), one real engine function per ability rather
// than one generic function with an index -- unlike the single generic
// AbilityBase() read above. Each entry here is ONLY verified by its x86
// prologue (55 8B EC) matching in the binary; the real argument count and
// return type were never disassembled or exercised, unlike every address
// above this point in the file. The shape assumed below --
// __thiscall void Set<X>Base(void* stats, int value) -- is an educated guess
// (it mirrors AddFeat/RemoveFeat's single-value shape and K1SE's own
// ability-setter convention), not a confirmed fact. If the real function
// takes more/fewer stack arguments, __thiscall's callee-cleanup means the
// stack unbalances silently rather than crashing immediately -- exactly the
// "write corrupts a save" risk this project's own docs warn about. This is
// the one call in this file that has not been live-validated; treat every
// result from it as provisional until confirmed by reading the value back
// with AbilityBase().
using SetAbilityFn = void(__thiscall*)(void* stats, int value);

constexpr uint32_t kSetAbilityAddr[off::kAbilityCount] = {
    off::game::kCSWSCreatureStats_SetSTRBase,
    off::game::kCSWSCreatureStats_SetDEXBase,
    off::game::kCSWSCreatureStats_SetCONBase,
    off::game::kCSWSCreatureStats_SetINTBase,
    off::game::kCSWSCreatureStats_SetWISBase,
    off::game::kCSWSCreatureStats_SetCHABase,
};

bool SafeCallSetAbility(void* stats, int ability, int value) {
    __try {
        auto fn = reinterpret_cast<SetAbilityFn>(kSetAbilityAddr[ability]);
        fn(stats, value);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

bool SetAbilityBase(void* stats, int ability, int value) {
    if (!LooksLikePointer(stats)) return false;
    if (ability < 0 || ability >= off::kAbilityCount) return false;
    // D20 ability scores: 0 is the engine's own floor for an incapacitated
    // creature, 255 is the single byte AbilityBase() reads back out of --
    // never ask the unverified setter to write something the verified getter
    // could not even represent.
    if (value < 0 || value > 255) return false;
    return SafeCallSetAbility(stats, ability, value);
}

bool SkillRankBase(void* stats, int skill, int* out) {
    if (!LooksLikePointer(stats) || !out) return false;
    if (skill < 0 || skill > 0xFF) return false;
    return SafeCallSkillRank(stats, static_cast<uint8_t>(skill), out);
}

bool HasFeat(void* stats, int feat, int* out) {
    if (!LooksLikePointer(stats) || !out) return false;
    if (feat < 0 || feat > 0xFFFF) return false;
    return SafeCallHasFeat(stats, static_cast<uint16_t>(feat), out);
}

bool HasSpell(void* stats, int spell, int* out) {
    if (!LooksLikePointer(stats) || !out) return false;
    if (spell < 0) return false;
    return SafeCallHasSpell(stats, static_cast<uint32_t>(spell), out);
}

}  // namespace gameobj
}  // namespace k2se
