#include "party32.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "hookkit.h"
#include "log.h"
#include "party32_hooks_generated.h"
#include "party32_steam.h"
#include "probe.h"

// 32-slot companion roster for the Steam build. Slots 0-11 keep using the game's own arrays inside the party table object; slots 12-31 are
// kept in gSlots below. The engine code that reads or writes a slot is redirected to the functions in this file by the patch sites in
// party32_hooks_generated.h.
//
// Design and site list: Patch Manager mod PartyRosterLimit32K2 (MIT, by Vriff). This file is our own implementation; the structure of the
// handlers follows that mod's source.

namespace k2se {
namespace party32 {
namespace {

using namespace steam;

constexpr int kStockSlots = 12;
constexpr int kMaxSlots = 32;
constexpr int kExtraSlots = kMaxSlots - kStockSlots;
constexpr int kActiveCapacity = 2;  // the party holds the player plus two followers
constexpr DWORD kNoObject = 0x7F000000u;
constexpr int kDefaultInfluence = -1;

// party table (CSWPartyTable) field offsets
constexpr int kOffMemberCount = 0x00;
constexpr int kOffMemberSlots = 0x08;
constexpr int kOffObjectIds = 0x1C;
constexpr int kOffAvailable = 0x4C;
constexpr int kOffSelectable = 0x7C;
constexpr int kOffLeaderSlot = 0x114;
constexpr int kOffPlayerSlot = 0x118;
constexpr int kOffTargetExperience = 0x16C;
constexpr int kOffNextPcCursor = 0x254;
constexpr int kOffEquipLogicalSlot = 0x50EC;  // equipment panel: the slot being shown

// creature / object field offsets
constexpr int kObjId = 0x04;
constexpr int kCreaturePostLoad = 0xF4;
constexpr int kCreatureExpAdjust = 0x26C;
constexpr int kCreatureStats = 0x1198;
constexpr int kCreaturePathfind = 0x380;
constexpr int kObjPosition = 0x94;
constexpr int kObjOrientation = 0xA0;
constexpr int kEffectType = 0x08;
constexpr int kEffectSubtypeFlags = 0x0A;

constexpr unsigned kCreatureSize = 0x1220;
constexpr unsigned kResGffSize = 0xA0;
constexpr unsigned kEffectSize = 0x8C;
constexpr unsigned short kSavedCreatureType = 0x07EB;

constexpr int kFlagConsumed = 0x100;  // handler result bit meaning "handled"

struct Slot {
    DWORD objectId = kNoObject;
    DWORD available = 0;
    BYTE selectable = 1;
    int influence = kDefaultInfluence;
};
std::array<Slot, kExtraSlots> gSlots{};

struct GffStruct { DWORD index; };
struct GffList { GffStruct s; char label[16]; };
using CExoStr = std::array<DWORD, 2>;

template <typename T> T Get(const void* o, int off) { return *reinterpret_cast<const T*>(static_cast<const BYTE*>(o) + off); }
template <typename T> void Put(void* o, int off, T v) { *reinterpret_cast<T*>(static_cast<BYTE*>(o) + off) = v; }
template <typename F> F Fn(uint32_t a) { return reinterpret_cast<F>(static_cast<uintptr_t>(a)); }

using GetNpcObjectFn = DWORD(__thiscall*)(void*, int, int, int);
using VoidThisFn = void(__thiscall*)(void*);
using GffGetListFn = int(__thiscall*)(void*, GffList*, GffStruct*, char*);
using GffGetCountFn = int(__thiscall*)(void*, GffList*);
using GffGetElementFn = int(__thiscall*)(void*, GffStruct*, GffList*, DWORD);
using GffReadByteFn = BYTE(__thiscall*)(void*, GffStruct*, char*, int*, BYTE);
using GffReadIntFn = int(__thiscall*)(void*, GffStruct*, char*, int*, int);
using GffWriteByteFn = int(__thiscall*)(void*, GffStruct*, BYTE, char*);
using GffWriteIntFn = int(__thiscall*)(void*, GffStruct*, int, char*);
using TwoDaGetIntFn = bool(__thiscall*)(void*, int, const void*, int*);
using GetPartyTableFn = void*(__thiscall*)(void*);
using StrCtorFn = void*(__thiscall*)(void*, const char*);
using NewFn = void*(__cdecl*)(unsigned);
using CreatureCtorFn = void*(__thiscall*)(void*, DWORD, int);
using LoadTemplateFn = int(__thiscall*)(void*, const void*, int);
using SaveCreatureFn = int(__thiscall*)(void*, void*, void*);
using ResGffCtorFn = void*(__thiscall*)(void*);
using ResGffCreateFn = int(__thiscall*)(void*, void*, const void*, const void*);
using ResGffWriteFn = int(__thiscall*)(void*, const void*, unsigned short);
using StatsLevelFn = BYTE(__thiscall*)(void*, int);
using ReceiveXpFn = void(__thiscall*)(void*, int);
using ClearActionsFn = void(__thiscall*)(void*, int);
using PlayerIdFn = DWORD(__thiscall*)(void*);
using GetFactionFn = void*(__thiscall*)(void*);
using FactionAddFn = void(__thiscall*)(void*, DWORD, int);
using SetMoveRateFn = void(__thiscall*)(void*, int);
using AiMasterFn = void*(__thiscall*)(void*);
using SetAiLevelFn = int(__thiscall*)(void*, void*, int);
using EffectCtorFn = void*(__thiscall*)(void*, int);
using ApplyEffectFn = void(__thiscall*)(void*, void*, int, int);
using StatusFn = short(__thiscall*)(void*, int);
using AsServerFn = void*(__thiscall*)(void*);
using ByObjectIdFn = void*(__thiscall*)(void*, DWORD);
using TransferFn = void(__thiscall*)(void*, void*);
using ToClientIdFn = DWORD(__thiscall*)(void*, DWORD);
using GetPartyFn = void*(__thiscall*)(void*);
using PartyCharFn = void*(__thiscall*)(void*, int);
using PartyIndexFn = int(__thiscall*)(void*, DWORD);
using ClientSetInPartyFn = void(__thiscall*)(void*, int);
using ClientToServerFn = void*(__thiscall*)(void*);
using ServerSetInPartyFn = void(__thiscall*)(void*, int, int);
using RemoveMemberFn = int(__thiscall*)(void*, int);
using SpawnNpcFn = DWORD(__thiscall*)(void*, int, int, const void*, const void*, int);
using AddMemberFn = int(__thiscall*)(void*, int, DWORD);
using VisibleGetFn = int(__thiscall*)(void*, DWORD);
using VisibleAddFn = void(__thiscall*)(void*, DWORD, int, int, int, int);
using VtableDtorFn = void*(__thiscall*)(void*, unsigned);

bool IsStock(int s) { return s >= 0 && s < kStockSlots; }
bool IsExtra(int s) { return s >= kStockSlots && s < kMaxSlots; }
bool IsValid(int s) { return s >= 0 && s < kMaxSlots; }
Slot& Extra(int s) { return gSlots[static_cast<size_t>(s - kStockSlots)]; }

// ---------------------------------------------------------------- engine objects

void* App(int off) {
    void* mgr = *reinterpret_cast<void**>(kAppManagerPtr);
    return Get<void*>(mgr, off);
}
void* Server() { return App(8); }
void* Client() { return App(4); }
void* PartyTable() { return Fn<GetPartyTableFn>(kGetCurrentPartyTable)(Server()); }

void* ServerCreature(DWORD id) {
    if (id == kNoObject) return nullptr;
    return Fn<ByObjectIdFn>(kGetCreatureByObjectId)(Server(), id);
}
void* PlayerCreature() { return ServerCreature(Fn<PlayerIdFn>(kGetPlayerCreatureId)(Server())); }

void* ClientCreature(DWORD serverId) {
    if (serverId == kNoObject) return nullptr;
    const DWORD cid = Fn<ToClientIdFn>(kServerToClientObjectId)(Client(), serverId);
    return Fn<ByObjectIdFn>(kClientGetCreatureByObjectId)(Client(), cid);
}

int ClientPartyIndex(DWORD serverId) {
    if (serverId == kNoObject) return -1;
    void* client = Client();
    void* party = Fn<GetPartyFn>(kClientGetParty)(client);
    if (!party) return -1;
    const DWORD cid = Fn<ToClientIdFn>(kServerToClientObjectId)(client, serverId);
    return Fn<PartyIndexFn>(kPartyGetIndex)(party, cid);
}

void* NewObject(unsigned size) { return Fn<NewFn>(kOperatorNew)(size); }
void DeleteObject(void* o) { (*reinterpret_cast<VtableDtorFn**>(o))[0](o, 1u); }

// ---------------------------------------------------------------- logical slot accessors

DWORD ObjectIdOf(void* table, int slot) {
    if (!IsValid(slot)) return kNoObject;
    if (IsExtra(slot)) return Extra(slot).objectId;
    return Get<DWORD>(table, kOffObjectIds + slot * 4);
}
void SetObjectIdOf(void* table, int slot, DWORD id) {
    if (!IsValid(slot)) return;
    if (IsExtra(slot)) { Extra(slot).objectId = id; return; }
    Put<DWORD>(table, kOffObjectIds + slot * 4, id);
}
DWORD AvailableOf(void* table, int slot) {
    if (!IsValid(slot)) return 0;
    if (IsExtra(slot)) return Extra(slot).available;
    return Get<DWORD>(table, kOffAvailable + slot * 4);
}
int FindSlotByObject(void* table, DWORD id) {
    if (id == kNoObject) return -1;
    for (int s = 0; s < kMaxSlots; ++s) if (ObjectIdOf(table, s) == id) return s;
    return -1;
}
int FindExtraSlotByObject(DWORD id) {
    if (id == kNoObject) return -1;
    for (int s = kStockSlots; s < kMaxSlots; ++s) if (Extra(s).objectId == id) return s;
    return -1;
}
int ActiveIndexOf(void* table, int slot) {
    int n = Get<int>(table, kOffMemberCount);
    n = std::max(0, std::min(n, kActiveCapacity));
    for (int i = 0; i < n; ++i) if (Get<int>(table, kOffMemberSlots + i * 4) == slot) return i;
    return -1;
}
bool IsPrimaryMember(void* table, int slot) {
    if (!IsValid(slot)) return false;
    const int n = Get<int>(table, kOffMemberCount);
    for (int i = 0; i < n; ++i) if (Get<int>(table, kOffMemberSlots + i * 4) == slot) return true;
    return false;
}
DWORD PrimaryMemberObject(void* table, int memberIndex) {
    const int slot = Get<int>(table, kOffMemberSlots + memberIndex * 4);
    return ObjectIdOf(table, slot);
}
DWORD ResolveOrCreate(void* table, int slot) { return Fn<GetNpcObjectFn>(kGetNpcObject)(table, slot, 1, 1); }

// ---------------------------------------------------------------- saving and loading the extra companions (saved game resources AVAILNPC<n>)

void MakeResRef(char out[16], int slot) {
    std::memset(out, 0, 16);
    std::snprintf(out, 16, "availnpc%d", slot);  // resource names are lower case; the snprintf also zero-terminates
}

int SaveToResource(int slot, void* creature) {
    void* gff = NewObject(kResGffSize);
    char path[32];
    std::snprintf(path, sizeof(path), "GAMEINPROGRESS:AVAILNPC%d", slot);
    CExoStr fileType, pathStr;
    auto ctor = Fn<StrCtorFn>(kCExoStringCtorCStr);
    auto dtor = Fn<VoidThisFn>(kCExoStringDtor);
    ctor(&fileType, "UTC ");
    ctor(&pathStr, path);
    Fn<ResGffCtorFn>(kResGffCtor)(gff);
    DWORD top = 0;
    Fn<ResGffCreateFn>(kResGffCreateFile)(gff, &top, &fileType, nullptr);
    Fn<SaveCreatureFn>(kCreatureSaveCreature)(creature, gff, &top);
    const int r = Fn<ResGffWriteFn>(kResGffWriteFile)(gff, &pathStr, kSavedCreatureType);
    DeleteObject(gff);
    dtor(&pathStr);
    dtor(&fileType);
    return r;
}

void SaveExtraByObject(int slot, DWORD id, int mode) {
    void* c = ServerCreature(id);
    if (!c) return;
    if (mode != 0) Fn<ClearActionsFn>(kObjectClearAllActions)(c, 1);
    SaveToResource(slot, c);
}

void RegisterWithAi(void* server, void* creature) {
    void** vt = *reinterpret_cast<void***>(creature);
    void* so = reinterpret_cast<AsServerFn>(vt[4])(creature);
    void* ai = Fn<AiMasterFn>(kGetAiMaster)(server);
    Fn<SetAiLevelFn>(kAiMasterSetAiLevel)(ai, so, 3);
}

void PostLoadRecovery(void* creature, int apply) {
    if (apply == 0) return;
    void** vt = *reinterpret_cast<void***>(creature);
    if (reinterpret_cast<StatusFn>(vt[0x9C / 4])(creature, 0) > 0) return;
    Put<DWORD>(creature, kCreaturePostLoad, 1u);
    void* eff = NewObject(kEffectSize);
    Fn<EffectCtorFn>(kGameEffectCtor)(eff, 1);
    const WORD type = *reinterpret_cast<const WORD*>(kEffectTypeWord);
    const WORD sub = *reinterpret_cast<const WORD*>(kEffectSubtypeWord);
    Put<WORD>(eff, kEffectType, type);
    WORD fl = Get<WORD>(eff, kEffectSubtypeFlags);
    fl = static_cast<WORD>((fl & static_cast<WORD>(~7)) | (sub & 7));
    Put<WORD>(eff, kEffectSubtypeFlags, fl);
    Fn<ApplyEffectFn>(kObjectApplyEffect)(creature, eff, 0, 0);
}

void AddToPlayerFaction(void* creature) {
    void* player = PlayerCreature();
    if (!player) return;
    void* faction = Fn<GetFactionFn>(kGetFaction)(player);
    if (!faction) return;
    Fn<FactionAddFn>(kFactionAddMember)(faction, Get<DWORD>(creature, kObjId), 0);
}

float RecruitXpScale(int slot) {
    void* root = *reinterpret_cast<void**>(k2daRootPtr);
    void* coll = root ? Get<void*>(root, 0x130) : nullptr;
    void* table = coll ? Get<void*>(coll, 0xF4) : nullptr;
    if (!table) return 1.0f;
    CExoStr col;
    Fn<StrCtorFn>(kCExoStringCtorCStr)(&col, "PercentXP");
    int percent = 0;
    const bool found = Fn<TwoDaGetIntFn>(k2daGetIntEntry)(table, slot, &col, &percent);
    Fn<VoidThisFn>(kCExoStringDtor)(&col);
    return (found && percent != 0) ? static_cast<float>(percent) / 100.0f : 1.0f;
}

void ApplyRecruitXp(void* table, int slot, void* creature) {
    const int target = static_cast<int>(static_cast<float>(Get<int>(table, kOffTargetExperience)) * RecruitXpScale(slot));
    void* stats = Get<void*>(creature, kCreatureStats);
    const int level = static_cast<int>(Fn<StatsLevelFn>(kStatsGetLevel)(stats, 0));
    const int threshold = level * (level - 1) * 500;
    Put<int>(creature, kCreatureExpAdjust, 0);
    Fn<ReceiveXpFn>(kReceiveExperience)(creature, threshold <= target ? target : threshold - target);
}

int DirectAddFromCreature(void* table, int slot, void* creature) {
    Slot& st = Extra(slot);
    st.available = 1;
    st.objectId = Get<DWORD>(creature, kObjId);
    Fn<TransferFn>(kTransferInventory)(table, creature);
    ApplyRecruitXp(table, slot, creature);
    AddToPlayerFaction(creature);
    void* stats = Get<void*>(creature, kCreatureStats);
    Fn<SetMoveRateFn>(kStatsSetMovementRate)(stats, 0);
    Fn<VoidThisFn>(kHandleAlignmentInfluence)(creature);
    const int r = SaveToResource(slot, creature);
    st.objectId = kNoObject;
    return r;
}

DWORD LoadExtraFromResource(void* table, void* server, int slot, int recovery) {
    void* creature = NewObject(kCreatureSize);
    Fn<CreatureCtorFn>(kCreatureCtor)(creature, kNoObject, 0);
    char ref[16];
    MakeResRef(ref, slot);
    Fn<VoidThisFn>(kAddGameInProgress)(table);
    const int ok = Fn<LoadTemplateFn>(kCreatureLoadFromTemplate)(creature, ref, 0);
    if (ok == 0) {
        DeleteObject(creature);
        return kNoObject;
    }
    Fn<VoidThisFn>(kRemoveGameInProgress)(table);
    PostLoadRecovery(creature, recovery);
    const DWORD id = Get<DWORD>(creature, kObjId);
    Extra(slot).objectId = id;
    RegisterWithAi(server, creature);
    return id;
}

// ---------------------------------------------------------------- adding and removing active extra members

bool RemoveExtraMember(void* table, int slot) {
    if (ActiveIndexOf(table, slot) < 0) return false;
    const DWORD id = ObjectIdOf(table, slot);
    const int idx = ClientPartyIndex(id);
    if (idx < 0) return false;
    void* cparty = Fn<GetPartyFn>(kClientGetParty)(Client());
    void* cmember = cparty ? Fn<PartyCharFn>(kPartyGetCharacter)(cparty, idx) : nullptr;
    if (!cmember) return false;
    void* creature = Fn<ClientToServerFn>(kClientCreatureGetServerCreature)(cmember);
    Fn<ClientSetInPartyFn>(kClientCreatureSetInParty)(cmember, 0);
    if (creature) Fn<ServerSetInPartyFn>(kServerCreatureSetInParty)(creature, 0, 1);
    return Fn<RemoveMemberFn>(kPartyTableRemoveMember)(table, slot) != 0;
}

bool AddExtraMember(void* table, int slot) {
    if (!IsExtra(slot) || AvailableOf(table, slot) == 0 || ActiveIndexOf(table, slot) >= 0) return false;
    const int count = Get<int>(table, kOffMemberCount);
    if (count < 0 || count >= kActiveCapacity) return false;
    void* player = PlayerCreature();
    if (!player) return false;
    BYTE* pb = static_cast<BYTE*>(player);
    const DWORD id = Fn<SpawnNpcFn>(kPartyTableSpawnNpc)(table, slot, 1, pb + kObjPosition, pb + kObjOrientation, 1);
    if (id == kNoObject || Fn<AddMemberFn>(kPartyTableAddMember)(table, slot, id) == 0) return false;
    void* creature = ServerCreature(id);
    if (!creature) return false;
    Fn<ClearActionsFn>(kObjectClearAllActions)(creature, 1);
    if (void* path = Get<void*>(creature, kCreaturePathfind)) Fn<VoidThisFn>(kPathfindResetWaypointData)(path);
    Fn<ServerSetInPartyFn>(kServerCreatureSetInParty)(creature, 1, 1);
    void** vt = *reinterpret_cast<void***>(creature);
    if (vt && vt[0x70 / 4]) reinterpret_cast<void(__thiscall*)(void*)>(vt[0x70 / 4])(creature);
    if (Fn<VisibleGetFn>(kGetVisibleListElement)(player, id) == 0) Fn<VisibleAddFn>(kAddToVisibleList)(player, id, 1, 1, 0, 0);
    void* cparty = Fn<GetPartyFn>(kClientGetParty)(Client());
    if (cparty) {
        const int n = Get<int>(table, kOffMemberCount);
        void* cmember = Fn<PartyCharFn>(kPartyGetCharacter)(cparty, n);
        if (cmember) Fn<ClientSetInPartyFn>(kClientCreatureSetInParty)(cmember, 1);
    }
    return true;
}

// ---------------------------------------------------------------- hook handlers (arguments follow the detour table in Apply)
// "frame" is the hooked function's ebp: arguments are at [ebp+8], [ebp+0xC], locals below ebp.

int __cdecl H_GetNumAvailable(void* table) {
    int count = 0;
    for (int s = 0; s < kMaxSlots; ++s) count += AvailableOf(table, s) != 0;
    return kFlagConsumed | (count & 0xFF);
}

void __cdecl H_StoreCreatePlayerObject(void* frame, DWORD id) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x104);
    SetObjectIdOf(table, Get<int>(table, kOffPlayerSlot), id);
}
DWORD __cdecl H_ResolveCreateMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return ObjectIdOf(*reinterpret_cast<void**>(ebp - 0x104), *reinterpret_cast<int*>(ebp - 0x18));
}

void __cdecl H_ClearExtraMembers() { for (Slot& s : gSlots) s.objectId = kNoObject; }
void __cdecl H_ResetSidecar() { gSlots = {}; }

void __cdecl H_ClearPartyMember(const int* slot) { if (IsExtra(*slot)) Extra(*slot).objectId = kNoObject; }
void __cdecl H_SavePartyMember(const int* slot, const int* mode) {
    if (IsExtra(*slot)) SaveExtraByObject(*slot, Extra(*slot).objectId, *mode);
}
void __cdecl H_SavePartyMemberByObject(const int* slot, const DWORD* id) {
    if (IsExtra(*slot)) SaveExtraByObject(*slot, *id, 1);
}

void __cdecl H_FinalizeSetLeader(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x08);
    const DWORD id = *reinterpret_cast<DWORD*>(ebp + 0x08);
    const int slot = FindSlotByObject(table, id);
    if (IsExtra(slot)) Put<int>(table, kOffLeaderSlot, slot);
}

// like the stock slots, an unavailable slot ignores writes and reads back 0
void __cdecl H_SetInfluence(const int* slot, const int* value) { if (IsExtra(*slot) && Extra(*slot).available) Extra(*slot).influence = *value; }

void __cdecl H_StoreNpcObject(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    SetObjectIdOf(*reinterpret_cast<void**>(ebp - 0x04), *reinterpret_cast<int*>(ebp + 0x08), *reinterpret_cast<DWORD*>(ebp + 0x0C));
}
void __cdecl H_StoreSelectability(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x04);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    const BYTE v = *reinterpret_cast<BYTE*>(ebp + 0x0C);
    if (IsExtra(slot)) Extra(slot).selectable = v;
    else Put<BYTE>(table, kOffSelectable + slot, v);
}

// persistence: the extra slots ride along in the party table's saved lists
void __cdecl H_WritePersistence(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* gff = *reinterpret_cast<void**>(ebp - 0x3C);
    GffStruct* parent = reinterpret_cast<GffStruct*>(ebp - 0x2C);
    auto getList = Fn<GffGetListFn>(kGffGetList);
    auto getCount = Fn<GffGetCountFn>(kGffGetListCount);
    auto getElem = Fn<GffGetElementFn>(kGffGetListElement);
    auto addElem = Fn<GffGetElementFn>(kGffAddListElement);

    auto element = [&](GffList& list, int& count, int slot, GffStruct& out) -> bool {
        if (slot < count) return getElem(gff, &out, &list, static_cast<DWORD>(slot)) != 0;
        while (count <= slot) {
            GffStruct made{};
            if (!addElem(gff, &made, &list, 0)) return false;
            if (count == slot) out = made;
            ++count;
        }
        return true;
    };

    GffList avail{};
    char availName[] = "PT_AVAIL_NPCS";
    if (getList(gff, &avail, parent, availName)) {
        int count = std::max(0, getCount(gff, &avail));
        char aLabel[] = "PT_NPC_AVAIL", sLabel[] = "PT_NPC_SELECT";
        for (int s = kStockSlots; s < kMaxSlots; ++s) {
            GffStruct el{};
            if (!element(avail, count, s, el)) { if (s >= count) return; continue; }
            const Slot& st = Extra(s);
            Fn<GffWriteByteFn>(kGffWriteFieldByte)(gff, &el, st.available ? 1u : 0u, aLabel);
            Fn<GffWriteByteFn>(kGffWriteFieldByte)(gff, &el, st.selectable ? 1u : 0u, sLabel);
        }
    }
    GffList infl{};
    char inflName[] = "PT_INFLUENCE";
    if (getList(gff, &infl, parent, inflName)) {
        int count = std::max(0, getCount(gff, &infl));
        char label[] = "PT_NPC_INFLUENCE";
        for (int s = kStockSlots; s < kMaxSlots; ++s) {
            GffStruct el{};
            if (!element(infl, count, s, el)) { if (s >= count) return; continue; }
            Fn<GffWriteIntFn>(kGffWriteFieldInt)(gff, &el, Extra(s).influence, label);
        }
    }
}

void __cdecl H_ReadPersistence(void* frame) {
    gSlots = {};
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* gff = *reinterpret_cast<void**>(ebp - 0x74);
    GffStruct* parent = reinterpret_cast<GffStruct*>(ebp - 0x64);
    GffList avail{};
    char availName[] = "PT_AVAIL_NPCS";
    if (Fn<GffGetListFn>(kGffGetList)(gff, &avail, parent, availName)) {
        const int count = std::max(0, std::min(Fn<GffGetCountFn>(kGffGetListCount)(gff, &avail), kMaxSlots));
        char aLabel[] = "PT_NPC_AVAIL", sLabel[] = "PT_NPC_SELECT";
        for (int s = kStockSlots; s < count; ++s) {
            GffStruct el{};
            if (!Fn<GffGetElementFn>(kGffGetListElement)(gff, &el, &avail, static_cast<DWORD>(s))) continue;
            int ok = 0;
            Extra(s).available = Fn<GffReadByteFn>(kGffReadFieldByte)(gff, &el, aLabel, &ok, 0) != 0;
            ok = 0;
            Extra(s).selectable = Fn<GffReadByteFn>(kGffReadFieldByte)(gff, &el, sLabel, &ok, 1) != 0;
        }
    }
    GffList infl{};
    char inflName[] = "PT_INFLUENCE";
    if (Fn<GffGetListFn>(kGffGetList)(gff, &infl, parent, inflName)) {
        const int count = std::max(0, std::min(Fn<GffGetCountFn>(kGffGetListCount)(gff, &infl), kMaxSlots));
        char label[] = "PT_NPC_INFLUENCE";
        for (int s = kStockSlots; s < count; ++s) {
            GffStruct el{};
            if (!Fn<GffGetElementFn>(kGffGetListElement)(gff, &el, &infl, static_cast<DWORD>(s))) continue;
            int ok = 0;
            Extra(s).influence = Fn<GffReadIntFn>(kGffReadFieldInt)(gff, &el, label, &ok, kDefaultInfluence);
        }
    }
}

// equipment screen: walks the slots; for extra slots it supplies the client creature itself
int __cdecl H_EquipNextCandidate(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* panel = *reinterpret_cast<void**>(ebp - 0x58);
    const int slot = Get<int>(panel, kOffEquipLogicalSlot);
    if (!IsExtra(slot)) return 0;
    void* table = *reinterpret_cast<void**>(ebp - 0x20);
    const DWORD id = ResolveOrCreate(table, slot);
    void* cc = ClientCreature(id);
    *reinterpret_cast<void**>(ebp - 0x18) = cc;
    *reinterpret_cast<int*>(ebp - 0x1C) = cc != nullptr;
    return 1;
}
int __cdecl H_EquipRoute(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return *reinterpret_cast<int*>(ebp - 0x1C) == 0;
}

DWORD __cdecl H_ExpFeatMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return PrimaryMemberObject(*reinterpret_cast<void**>(ebp - 0x68), *reinterpret_cast<int*>(ebp - 0x20));
}
DWORD __cdecl H_ExpRecipient(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return PrimaryMemberObject(*reinterpret_cast<void**>(ebp - 0x68), *reinterpret_cast<int*>(ebp - 0x28));
}
DWORD __cdecl H_UnstealthMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return PrimaryMemberObject(*reinterpret_cast<void**>(ebp - 0x28), static_cast<int>(*reinterpret_cast<BYTE*>(ebp - 0x01)));
}
DWORD __cdecl H_AutoLevelMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return PrimaryMemberObject(*reinterpret_cast<void**>(ebp - 0x18), *reinterpret_cast<int*>(ebp - 0x04));
}
DWORD __cdecl H_AddMemberDuplicate(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return ObjectIdOf(*reinterpret_cast<void**>(ebp - 0x34), *reinterpret_cast<int*>(ebp - 0x04));
}
void __cdecl H_StoreAddMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    SetObjectIdOf(*reinterpret_cast<void**>(ebp - 0x34), *reinterpret_cast<int*>(ebp + 0x08), *reinterpret_cast<DWORD*>(ebp + 0x0C));
}
void __cdecl H_ClearAvailability(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x04);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    if (IsStock(slot)) Put<DWORD>(table, kOffAvailable + slot * 4, 0u);
    else if (IsExtra(slot)) Extra(slot).available = 0;
}
DWORD __cdecl H_KillNpcObject(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    return ObjectIdOf(*reinterpret_cast<void**>(ebp - 0x30), *reinterpret_cast<int*>(ebp + 0x08));
}
void __cdecl H_ClearKillNpcObject(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    SetObjectIdOf(*reinterpret_cast<void**>(ebp - 0x30), *reinterpret_cast<int*>(ebp + 0x08), kNoObject);
}
DWORD __cdecl H_NextPcMember(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x08);
    return PrimaryMemberObject(table, Get<int>(table, kOffNextPcCursor));
}
DWORD __cdecl H_SwitchBackPlayer(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0xFC);
    return ObjectIdOf(table, Get<int>(table, kOffPlayerSlot));
}

int __cdecl H_AddPartyNpc(void* table, const int* slot, void* const* creature) {
    if (!IsExtra(*slot)) return 0;
    if (*creature && Extra(*slot).available == 0) return DirectAddFromCreature(table, *slot, *creature);
    return 0;
}

int __cdecl H_FinalizeNpcId(void* frame, int stock) {
    if (stock >= 0) return stock;
    BYTE* ebp = static_cast<BYTE*>(frame);
    return FindExtraSlotByObject(*reinterpret_cast<DWORD*>(ebp + 0x08));
}
int __cdecl H_FinalizeIsMember(void* frame, int stock) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    const DWORD id = *reinterpret_cast<DWORD*>(ebp + 0x08);
    if (id == kNoObject) return 0;
    if (stock != 0) return stock;
    void* table = *reinterpret_cast<void**>(ebp - 0x0C);
    return IsPrimaryMember(table, FindSlotByObject(table, id));
}
int __cdecl H_FinalizeIsAvailableByObject(void* frame, int stock) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    const DWORD id = *reinterpret_cast<DWORD*>(ebp + 0x08);
    if (id == kNoObject) return 0;
    if (stock != 0) return stock;
    return FindExtraSlotByObject(id) >= 0;
}
int __cdecl H_FinalizeIsLeader(void* frame, int stock) {
    if (stock != 0) return stock;
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x08);
    const int leader = Get<int>(table, kOffLeaderSlot);
    if (!IsExtra(leader)) return 0;
    return FindSlotByObject(table, *reinterpret_cast<DWORD*>(ebp + 0x08)) == leader;
}
int __cdecl H_FinalizeAvailability(void* frame, int stock) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    return IsExtra(slot) ? (Extra(slot).available != 0) : stock;
}
int __cdecl H_FinalizeInfluence(void* frame, int stock) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    if (!IsExtra(slot)) return stock;
    return Extra(slot).available ? Extra(slot).influence : 0;
}

int __cdecl H_GetNpcObject(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    void* table = *reinterpret_cast<void**>(ebp - 0x60);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    if (!IsExtra(slot)) return 0;
    const int create = *reinterpret_cast<int*>(ebp + 0x0C);
    const int mode = *reinterpret_cast<int*>(ebp + 0x10);
    DWORD result = Extra(slot).objectId;
    if (result == kNoObject && create != 0) result = LoadExtraFromResource(table, Server(), slot, mode);
    *reinterpret_cast<DWORD*>(ebp - 0x5C) = result;
    return 1;
}
int __cdecl H_GetSelectability(void* frame) {
    BYTE* ebp = static_cast<BYTE*>(frame);
    const int slot = *reinterpret_cast<int*>(ebp + 0x08);
    if (!IsExtra(slot)) return 0;
    return kFlagConsumed | static_cast<int>(Extra(slot).selectable);
}

// end of the routine that rebuilds the party table after a load: bring the available extra companions back as objects
void __cdecl H_FinishRebuild() {
    void* table = PartyTable();
    for (int s = kStockSlots; s < kMaxSlots; ++s) {
        const Slot& st = Extra(s);
        if (st.available == 0 || st.objectId != kNoObject) continue;
        ResolveOrCreate(table, s);
    }
}

#include "party32_gui.inc"

// ---------------------------------------------------------------- the detour table

struct Spec {
    int number;
    void* handler;
    hookkit::Arg args[3];
    size_t argCount;
    bool skip;
    hookkit::ResultReg result;
    uint32_t consumedExit;
};

using hookkit::ArgKind;
constexpr hookkit::Arg kEbp{ArgKind::kEbp, 0};
constexpr hookkit::Arg kEcx{ArgKind::kEcx, 0};
constexpr hookkit::Arg kEax{ArgKind::kEax, 0};
constexpr hookkit::Arg kSp4{ArgKind::kStackArg, 4};
constexpr hookkit::Arg kSp8{ArgKind::kStackArg, 8};
constexpr hookkit::ResultReg kNoRes = hookkit::ResultReg::kNone;
constexpr hookkit::ResultReg kResEax = hookkit::ResultReg::kEax;

const Spec kSpecs[] = {
    {11, (void*)H_GetNumAvailable, {kEcx}, 1, true, kNoRes, 0x005FAA70},
    {28, (void*)H_StoreCreatePlayerObject, {kEbp, kEax}, 2, true, kNoRes, 0},
    {29, (void*)H_ResolveCreateMember, {kEbp}, 1, true, kResEax, 0},
    {30, (void*)H_ResolveCreateMember, {kEbp}, 1, true, kResEax, 0},
    {33, (void*)H_ClearExtraMembers, {}, 0, false, kNoRes, 0},
    {34, (void*)H_ClearPartyMember, {kSp4}, 1, false, kNoRes, 0},
    {35, (void*)H_SavePartyMember, {kSp4, kSp8}, 2, false, kNoRes, 0},
    {36, (void*)H_SavePartyMemberByObject, {kSp4, kSp8}, 2, false, kNoRes, 0},
    {37, (void*)H_FinalizeSetLeader, {kEbp}, 1, false, kNoRes, 0},
    {38, (void*)H_SetInfluence, {kSp4, kSp8}, 2, false, kNoRes, 0},
    {39, (void*)H_StoreNpcObject, {kEbp}, 1, true, kNoRes, 0},
    {40, (void*)H_StoreSelectability, {kEbp}, 1, true, kNoRes, 0},
    {41, (void*)H_ResetSidecar, {}, 0, false, kNoRes, 0},
    {42, (void*)H_WritePersistence, {kEbp}, 1, false, kNoRes, 0},
    {43, (void*)H_ReadPersistence, {kEbp}, 1, false, kNoRes, 0},
    {44, (void*)H_EquipNextCandidate, {kEbp}, 1, false, kNoRes, 0x008AB2EB},
    {45, (void*)H_EquipRoute, {kEbp}, 1, true, kNoRes, 0x008AB0FA},
    {46, (void*)H_ExpFeatMember, {kEbp}, 1, true, kResEax, 0},
    {47, (void*)H_ExpRecipient, {kEbp}, 1, true, kResEax, 0},
    {48, (void*)H_UnstealthMember, {kEbp}, 1, true, kResEax, 0},
    {49, (void*)H_AutoLevelMember, {kEbp}, 1, true, kResEax, 0},
    {50, (void*)H_AddMemberDuplicate, {kEbp}, 1, true, kResEax, 0},
    {51, (void*)H_StoreAddMember, {kEbp}, 1, true, kNoRes, 0},
    {52, (void*)H_AddPartyNpc, {kEcx, kSp4, kSp8}, 3, false, kNoRes, 0x005FA3AA},
    {53, (void*)H_ClearAvailability, {kEbp}, 1, true, kNoRes, 0},
    {54, (void*)H_KillNpcObject, {kEbp}, 1, true, kResEax, 0},
    {55, (void*)H_ClearKillNpcObject, {kEbp}, 1, true, kNoRes, 0},
    {56, (void*)H_FinalizeNpcId, {kEbp, kEax}, 2, false, kResEax, 0},
    {57, (void*)H_FinalizeIsMember, {kEbp, kEax}, 2, false, kResEax, 0},
    {58, (void*)H_FinalizeIsAvailableByObject, {kEbp, kEax}, 2, false, kResEax, 0},
    {59, (void*)H_FinalizeIsLeader, {kEbp, kEax}, 2, false, kResEax, 0},
    {60, (void*)H_FinalizeAvailability, {kEbp, kEax}, 2, false, kResEax, 0},
    {61, (void*)H_FinalizeInfluence, {kEbp, kEax}, 2, false, kResEax, 0},
    {62, (void*)H_NextPcMember, {kEbp}, 1, true, kResEax, 0},
    {63, (void*)H_GetNpcObject, {kEbp}, 1, false, kNoRes, 0x005FAD4B},
    {64, (void*)H_GetSelectability, {kEbp}, 1, false, kNoRes, 0x005FB164},
    {65, (void*)H_SwitchBackPlayer, {kEbp}, 1, true, kResEax, 0},
    {68, (void*)H_FinishRebuild, {}, 0, false, kNoRes, 0},
    {31, (void*)H_FinishLayout, {kEcx}, 1, true, kNoRes, 0},
    {32, (void*)H_PanelDtor, {kEcx}, 1, false, kNoRes, 0},
    {66, (void*)H_PanelAdded, {kEcx}, 1, false, kNoRes, 0},
    {67, (void*)H_PanelAddedDone, {kEbp}, 1, false, kNoRes, 0},
    {69, (void*)H_PanelRemoved, {kEcx}, 1, false, kNoRes, 0},
    {70, (void*)H_PanelRemovedDone, {kEbp}, 1, false, kNoRes, 0},
    {71, (void*)H_SetForced, {kEcx, kSp4, kSp8}, 3, false, kNoRes, 0},
    {72, (void*)H_PanelDone, {kEcx}, 1, false, kNoRes, 0},
    {73, (void*)H_PanelAccept, {kEcx}, 1, false, kNoRes, 0},
    {74, (void*)H_PanelAcceptDone, {kEbp}, 1, false, kNoRes, 0},
};

const Spec* FindSpec(int number) {
    for (const Spec& s : kSpecs) if (s.number == number) return &s;
    return nullptr;
}

bool AddressesReady() {
    const uint32_t needed[] = {
        kObjectClearAllActions, kGetFaction, kFactionAddMember, kHandleAlignmentInfluence, kServerCreatureSetInParty,
        kPathfindResetWaypointData, kGetVisibleListElement, kAddToVisibleList, kServerToClientObjectId, kClientGetCreatureByObjectId,
        kClientGetParty, kPartyGetCharacter, kPartyGetIndex, kClientCreatureSetInParty, kClientCreatureGetServerCreature,
    };
    for (uint32_t a : needed) if (a == 0) return false;
    return true;
}

}  // namespace

int Apply() {
    if (probe::ConfigInt("party32", 0) == 0) return 0;
    if (!AddressesReady()) {
        log::Write("party32: NOT applied: some engine addresses are not resolved yet (party32_steam.h)");
        return 0;
    }
    const bool equip = probe::ConfigInt("party32_equip", 1) != 0;
    const bool gui = probe::ConfigInt("party32_gui", 0) != 0;

    // 1. verify every site we are going to touch before writing any of them
    int wanted = 0;
    for (const Site& s : kSites) {
        if (s.group == Group::kGui && !gui) continue;
        if (s.group == Group::kEquip && !equip) continue;
        if (!s.simple && !FindSpec(s.number)) { log::Writef("party32: NOT applied: no handler for hook %d", s.number); return 0; }
        if (!hookkit::CheckBytes(s.address, s.original, s.length)) {
            log::Writef("party32: NOT applied: hook %d at 0x%08X does not hold the expected bytes", s.number, s.address);
            return 0;
        }
        ++wanted;
    }

    // 2. apply them
    int applied = 0;
    for (const Site& s : kSites) {
        if (s.group == Group::kGui && !gui) continue;
        if (s.group == Group::kEquip && !equip) continue;
        bool ok;
        if (s.simple) {
            uint8_t repl[8];
            std::memset(repl, s.replacement, sizeof(repl));
            ok = hookkit::PatchBytes(s.address, s.original, repl, s.length);
        } else {
            const Spec* sp = FindSpec(s.number);
            hookkit::Detour d{"party32", s.address, s.original, s.length, sp->handler, sp->args, sp->argCount, sp->skip, sp->result, sp->consumedExit};
            ok = hookkit::InstallDetour(d);
        }
        if (!ok) log::Writef("party32: hook %d at 0x%08X FAILED", s.number, s.address);
        else ++applied;
    }
    log::Writef("party32: %d of %d sites applied (slots 12-31 active%s%s)", applied, wanted, equip ? "" : ", equipment screen sites skipped", gui ? ", paged party screen on" : "");
    return applied;
}

}  // namespace party32
}  // namespace k2se
