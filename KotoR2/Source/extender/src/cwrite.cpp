#include "cwrite.h"

#include <windows.h>

#include "gameobj.h"
#include "log.h"
#include "offsets.h"
#include "probe.h"

namespace k2se {
namespace cwrite {
namespace {

// Layout of the creature stats block in TSL. Every offset here was found by disassembling the
// routine that reads it and then confirmed by reading and writing it in a running game
// (docs/OFFSETS.md, docs/COMPANION_SLOT_TEST.md).
constexpr int kStatsClassCount = 0x8D;      // byte
constexpr int kStatsClassId0 = 0xAB;        // byte: class id; the level byte follows at +1
constexpr int kStatsClassStride = 0x28;
constexpr int kStatsMaxClasses = 3;
constexpr int kStatsPowerList0 = 0x90;      // per class: {pointer, count, capacity}, 4 bytes each
constexpr int kStatsRace = 0xE0;            // word
constexpr int kStatsSaveBonus0 = 0x1B0;     // bytes: fortitude, will, reflex
constexpr int kStatsFeatListA = 0x00;       // {pointer, count, capacity}, entries are words
constexpr int kStatsFeatListB = 0x18;
constexpr int kStatsSkillArray = 0x174;     // pointer to one signed byte per skill (8 skills in TSL)
constexpr int kSkillCount = 8;
constexpr int kMaxSkillRank = 100;
constexpr int kCreatureCredits = 0x10E4;    // creature (not stats) +0x10E4, dword

constexpr int kNoClass = 255;               // class id byte of an empty slot
constexpr int kMaxClassLevel = 50;
constexpr int kMaxCredits = 999999999;
constexpr int kMaxSaveBonus = 100;

// classes.2da has rows 0..16; row 10 is the cut Bounty Hunter and is refused.
bool ValidClass(int id) { return id >= 0 && id <= 16 && id != 10; }

void* StatsOf(uint32_t objectId) {
    void* creature = gameobj::CreatureFromObjectId(objectId);
    if (!creature) return nullptr;
    void* stats = gameobj::CreatureStats(creature);
    if (!gameobj::LooksLikePointer(stats)) return nullptr;
    return stats;
}

bool Rd(void* base, int offset, int width, int* out) { return probe::ReadMem(base, offset, width, out); }

bool Wr(void* base, int offset, int width, int value) {
    return probe::WriteAbs(static_cast<char*>(base) + offset, width, value, nullptr);
}

bool ClassCount(void* stats, int* out) {
    int n = 0;
    if (!Rd(stats, kStatsClassCount, 1, &n)) return false;
    if (n < 1 || n > kStatsMaxClasses) return false;
    *out = n;
    return true;
}

int ClassOffset(int slot) { return kStatsClassId0 + slot * kStatsClassStride; }

// Removes `value` from a list of {pointer, count, capacity} whose entries are `width` bytes
// wide, by moving the last entry over it and shrinking the count. Returns 1 removed,
// 0 absent, -1 unreadable.
int RemoveFromList(void* stats, int listOffset, int width, int value) {
    int ptr = 0, count = 0;
    if (!Rd(stats, listOffset, 4, &ptr) || !Rd(stats, listOffset + 4, 4, &count)) return -1;
    if (count <= 0) return 0;
    if (count > 4096 || !gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(ptr)))) return -1;
    char* entries = reinterpret_cast<char*>(static_cast<uintptr_t>(ptr));
    for (int i = 0; i < count; ++i) {
        int v = 0;
        if (!Rd(entries, i * width, width, &v)) return -1;
        if (v != value) continue;
        int last = 0;
        if (!Rd(entries, (count - 1) * width, width, &last)) return -1;
        if (i != count - 1 && !Wr(entries, i * width, width, last)) return -1;
        return Wr(stats, listOffset + 4, 4, count - 1) ? 1 : -1;
    }
    return 0;
}

int Finish(const char* what, int result, int a, int b) {
    log::Writef("K2SE %s(%d, %d) -> %d", what, a, b, result);
    return result;
}

}  // namespace

int SetRace(uint32_t objectId, int race) {
    void* stats = StatsOf(objectId);
    if (!stats) return Finish("SetRace", -1, race, 0);
    if (race != 5 && race != 6) return Finish("SetRace", 0, race, 0);
    return Finish("SetRace", Wr(stats, kStatsRace, 2, race) ? 1 : -1, race, 0);
}

int SetCreatureCredits(uint32_t objectId, int amount) {
    void* creature = gameobj::CreatureFromObjectId(objectId);
    if (!creature) return Finish("SetCreatureCredits", -1, amount, 0);
    if (amount < 0 || amount > kMaxCredits) return Finish("SetCreatureCredits", 0, amount, 0);
    return Finish("SetCreatureCredits", Wr(creature, kCreatureCredits, 4, amount) ? 1 : -1, amount, 0);
}

int SetPartyCredits(int amount) {
    if (amount < 0 || amount > kMaxCredits) return Finish("SetPartyCredits", 0, amount, 0);
    // [[0xA1B4A4]+8] is the server object; the player's purse sits at ([server+4] + 0x1F0B4) + 0x170,
    // a plain addition after the second read (no further dereference).
    void* server = gameobj::ServerExoApp();
    if (!server) return Finish("SetPartyCredits", -1, amount, 0);
    int holder = 0;
    if (!Rd(server, 4, 4, &holder) ||
        !gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(holder))))
        return Finish("SetPartyCredits", -1, amount, 0);
    char* purse = reinterpret_cast<char*>(static_cast<uintptr_t>(holder)) + 0x1F0B4 + 0x170;
    return Finish("SetPartyCredits", probe::WriteAbs(purse, 4, amount, nullptr) ? 1 : -1, amount, 0);
}

int SetSaveBonus(uint32_t objectId, int save, int value) {
    void* stats = StatsOf(objectId);
    if (!stats) return Finish("SetSaveBonus", -1, save, value);
    if (save < 0 || save > 2 || value < 0 || value > kMaxSaveBonus) return Finish("SetSaveBonus", 0, save, value);
    return Finish("SetSaveBonus", Wr(stats, kStatsSaveBonus0 + save, 1, value) ? 1 : -1, save, value);
}

int SetClassLevel(uint32_t objectId, int slot, int level) {
    void* stats = StatsOf(objectId);
    int count = 0;
    if (!stats || !ClassCount(stats, &count)) return Finish("SetClassLevel", -1, slot, level);
    if (slot < 0 || slot >= count || level < 0 || level > kMaxClassLevel) return Finish("SetClassLevel", 0, slot, level);
    if (slot == 0 && level < 1) return Finish("SetClassLevel", 0, slot, level);   // the base class keeps a level
    int id = 0;
    if (!Rd(stats, ClassOffset(slot), 1, &id) || id == kNoClass) return Finish("SetClassLevel", 0, slot, level);
    return Finish("SetClassLevel", Wr(stats, ClassOffset(slot) + 1, 1, level) ? 1 : -1, slot, level);
}

int SetClassId(uint32_t objectId, int slot, int classId) {
    void* stats = StatsOf(objectId);
    int count = 0;
    if (!stats || !ClassCount(stats, &count)) return Finish("SetClassId", -1, slot, classId);
    if (slot < 0 || slot >= count || !ValidClass(classId)) return Finish("SetClassId", 0, slot, classId);
    // A class may appear in only one slot: a duplicate class is what crashed a companion before.
    for (int s = 0; s < count; ++s) {
        int other = 0;
        if (!Rd(stats, ClassOffset(s), 1, &other)) return Finish("SetClassId", -1, slot, classId);
        if (s != slot && other == classId) return Finish("SetClassId", 0, slot, classId);
    }
    int current = 0;
    if (!Rd(stats, ClassOffset(slot), 1, &current) || current == kNoClass) return Finish("SetClassId", 0, slot, classId);
    return Finish("SetClassId", Wr(stats, ClassOffset(slot), 1, classId) ? 1 : -1, slot, classId);
}

int RemoveClass(uint32_t objectId, int slot) {
    void* stats = StatsOf(objectId);
    int count = 0;
    if (!stats || !ClassCount(stats, &count)) return Finish("RemoveClass", -1, slot, 0);
    if (slot < 1 || slot != count - 1) return Finish("RemoveClass", 0, slot, 0);   // last added class only
    int id = 0;
    if (!Rd(stats, ClassOffset(slot), 1, &id) || id == kNoClass) return Finish("RemoveClass", 0, slot, 0);
    bool ok = Wr(stats, ClassOffset(slot) + 1, 1, 0) &&                         // level
              Wr(stats, ClassOffset(slot) + 2, 1, 0) &&                         // the byte after the level
              Wr(stats, kStatsPowerList0 + slot * kStatsClassStride + 4, 4, 0) &&  // this class's power list
              Wr(stats, ClassOffset(slot), 1, kNoClass) &&                      // id
              Wr(stats, kStatsClassCount, 1, count - 1);                        // count last
    return Finish("RemoveClass", ok ? 1 : -1, slot, id);
}

int RemoveFeat(uint32_t objectId, int feat) {
    void* stats = StatsOf(objectId);
    if (!stats) return Finish("RemoveFeat", -1, feat, 0);
    if (feat < 0 || feat > 0x7FFF) return Finish("RemoveFeat", 0, feat, 0);
    int a = RemoveFromList(stats, kStatsFeatListA, 2, feat);
    int b = RemoveFromList(stats, kStatsFeatListB, 2, feat);
    if (a < 0 || b < 0) return Finish("RemoveFeat", -1, feat, 0);
    return Finish("RemoveFeat", (a > 0 || b > 0) ? 1 : 0, feat, 0);
}

int RemovePower(uint32_t objectId, int spell) {
    void* stats = StatsOf(objectId);
    int count = 0;
    if (!stats || !ClassCount(stats, &count)) return Finish("RemovePower", -1, spell, 0);
    if (spell < 0 || spell > 0xFFFF) return Finish("RemovePower", 0, spell, 0);
    int removed = 0;
    for (int s = 0; s < count; ++s) {
        int r = RemoveFromList(stats, kStatsPowerList0 + s * kStatsClassStride, 4, spell);
        if (r < 0) return Finish("RemovePower", -1, spell, s);
        if (r > 0) removed = 1;
    }
    return Finish("RemovePower", removed, spell, 0);
}

int SetSkillRank(uint32_t objectId, int skill, int rank) {
    void* stats = StatsOf(objectId);
    if (!stats) return Finish("SetSkillRank", -1, skill, rank);
    if (skill < 0 || skill >= kSkillCount || rank < 0 || rank > kMaxSkillRank) return Finish("SetSkillRank", 0, skill, rank);
    int ptr = 0;
    if (!Rd(stats, kStatsSkillArray, 4, &ptr) ||
        !gameobj::LooksLikePointer(reinterpret_cast<void*>(static_cast<uintptr_t>(ptr))))
        return Finish("SetSkillRank", -1, skill, rank);
    char* ranks = reinterpret_cast<char*>(static_cast<uintptr_t>(ptr));
    return Finish("SetSkillRank", Wr(ranks, skill, 1, rank) ? 1 : -1, skill, rank);
}

}  // namespace cwrite
}  // namespace k2se
