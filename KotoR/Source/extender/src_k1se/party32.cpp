// 32-slot companion roster for KOTOR 1 (see party32.h).
//
// The engine code that reads or writes a companion slot is redirected, through the patch sites in party32_hooks_generated.h, to the handlers below. A slot number below
// 9 still uses the arrays inside the game's party table object; 9 to 31 are answered from gSlots. Handlers follow the structure of the Patch Manager mod
// PartyRosterLimit32K1 (MIT); the code here is our own implementation on this extender, with the engine addresses of the Steam 1.03 image.

#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <algorithm>

#include "MinHook.h"
#include "log.h"
#include "party32.h"
#include "party32_hooks_generated.h"

namespace party32 {
namespace {

constexpr int kStock = 9;
constexpr int kMax = 32;
constexpr int kExtra = kMax - kStock;
constexpr int kActiveCapacity = 2;          // the party holds the player plus two followers
constexpr DWORD kNoObject = 0x7F000000u;

// CSWPartyTable (Patch Manager kotor1_0_3.db)
constexpr int kOffMemberCount = 0x00;
constexpr int kOffMemberSlots = 0x04;
constexpr int kOffObjectIds = 0x0C;         // member slots (2) are followed by the nine NPC object ids
constexpr int kOffAvailable = 0x30;         // dword per slot
constexpr int kOffSelectable = 0x54;        // byte per slot
constexpr int kOffLeaderSlot = 0xEC;
constexpr int kOffPlayerSlot = 0xF0;

constexpr int kObjId = 0x04;
constexpr int kObjPosition = 0x90;
constexpr int kObjOrientation = 0x9C;
constexpr int kCreaturePostLoad = 0xF0;     // CSWSObject::is_raiseable
constexpr int kEffectType = 0x08;
constexpr int kEffectSubtype = 0x0A;
constexpr int kClientDeferredDelete = 0xE4;
constexpr unsigned kCreatureSize = 2760;    // CSWSCreature
constexpr unsigned kResGffSize = 160;       // CResGFF
constexpr unsigned kEffectSize = 140;       // CGameEffect
constexpr unsigned short kSavedCreatureType = 0x07EB;

// engine addresses (Steam 1.03, image base 0x400000; names from Patch Manager's kotor1_0_3.db)
constexpr uintptr_t kAppManagerPtr = 0x007A39FC;
constexpr uintptr_t kEffectTypeWord = 0x0074668C;
constexpr uintptr_t kEffectSubtypeWord = 0x007473B8;
constexpr uintptr_t kServerGetCreature = 0x004AE770;      // CServerExoApp::GetCreatureByGameObjectID
constexpr uintptr_t kServerGetPartyTable = 0x004AEE70;
constexpr uintptr_t kServerGetPlayerId = 0x004AEA40;
constexpr uintptr_t kClientGetCreature = 0x005ED5B0;      // CClientExoApp::GetCreatureByGameObjectID
constexpr uintptr_t kClientGetParty = 0x005ED8B0;         // CClientExoApp::GetSWParty
constexpr uintptr_t kServerToClientId = 0x005EDA50;       // CClientExoAppInternal::ServerToClientObjectId
constexpr uintptr_t kClientGetServerCreature = 0x0060FB20;   // CSWCCreature::GetServerCreature
constexpr uintptr_t kPartyGetCharacter = 0x006346C0;
constexpr uintptr_t kPartyGetIndex = 0x006349C0;
constexpr uintptr_t kClientSetInParty = 0x0060EF50;
constexpr uintptr_t kServerSetInParty = 0x004FDB20;
constexpr uintptr_t kClientSetFadeState = 0x0063E220;
constexpr uintptr_t kClientSetDesiredFadeState = 0x0063CE60;
constexpr uintptr_t kOperatorNew = 0x006FA7E6;
constexpr uintptr_t kCreatureCtor = 0x004F7A10;
constexpr uintptr_t kCreatureDeletingDtor = 0x004FDE20;
constexpr uintptr_t kCreatureLoadFromTemplate = 0x005026D0;
constexpr uintptr_t kCreatureSaveCreature = 0x00500610;
constexpr uintptr_t kCreatureForceEquipClothing = 0x00501C40;
constexpr uintptr_t kObjectClearAllActions = 0x004CCD80;
constexpr uintptr_t kObjectApplyEffect = 0x004D14F0;
constexpr uintptr_t kObjectGetCurrentHitPoints = 0x004CAEC0;
constexpr uintptr_t kGameEffectCtor = 0x00503E40;
constexpr uintptr_t kResGffCtor = 0x004105A0;
constexpr uintptr_t kResGffDeletingDtor = 0x00413010;
constexpr uintptr_t kResGffCreateFile = 0x00411260;
constexpr uintptr_t kResGffWriteFile = 0x00413030;
constexpr uintptr_t kGffGetList = 0x004118C0;
constexpr uintptr_t kGffGetListCount = 0x00411940;
constexpr uintptr_t kGffGetListElement = 0x00411990;
constexpr uintptr_t kGffAddListElement = 0x004124E0;
constexpr uintptr_t kGffReadFieldByte = 0x00411A60;
constexpr uintptr_t kGffWriteFieldByte = 0x00412620;
constexpr uintptr_t kExoStringCtorCStr = 0x005E5A90;
constexpr uintptr_t kExoStringDtor = 0x005E5C20;
constexpr uintptr_t kPartyAddGameInProgress = 0x005638D0;
constexpr uintptr_t kPartyRemoveGameInProgress = 0x00563950;
constexpr uintptr_t kPartyTransferInventory = 0x005641E0;
constexpr uintptr_t kPartyAddNpc = 0x005645F0;            // AddNPC_2(slot, CExoString* template)
constexpr uintptr_t kPartySpawnNpc = 0x00565130;
constexpr uintptr_t kPartyAddMember = 0x00565620;
constexpr uintptr_t kPartyRemoveMember = 0x00565560;
constexpr uintptr_t kServerMainLoop = 0x004AE860;

struct Slot {
    DWORD objectId = kNoObject;
    DWORD available = 0;
    BYTE selectable = 1;
};
Slot gSlots[kExtra];

struct ResStruct { DWORD index; };
struct ResList { ResStruct s; char label[16]; };
typedef DWORD ExoString[2];

template <typename T> T Get(const void* o, int off) { return *reinterpret_cast<const T*>(static_cast<const BYTE*>(o) + off); }
template <typename T> void Put(void* o, int off, T v) { *reinterpret_cast<T*>(static_cast<BYTE*>(o) + off) = v; }
template <typename F> F Fn(uintptr_t a) { return reinterpret_cast<F>(a); }

typedef void*(__thiscall* PtrThisFn)(void*);
typedef void(__thiscall* VoidThisFn)(void*);
typedef void*(__thiscall* ByIdFn)(void*, DWORD);
typedef DWORD(__thiscall* IdThisFn)(void*);
typedef DWORD(__thiscall* ToClientFn)(void*, DWORD);
typedef int(__thiscall* IndexFn)(void*, DWORD);
typedef void*(__thiscall* CharFn)(void*, int);
typedef void(__thiscall* SetIntFn)(void*, int);
typedef void(__thiscall* SetInPartyFn)(void*, int, int);
typedef void(__thiscall* FadeFn)(void*, BYTE);
typedef void(__thiscall* DesiredFadeFn)(void*, BYTE, int, DWORD, DWORD);
typedef void*(__cdecl* NewFn)(unsigned);
typedef void*(__thiscall* CreatureCtorFn)(void*, DWORD, int);
typedef int(__thiscall* LoadTemplateFn)(void*, const void*, int);
typedef int(__thiscall* SaveCreatureFn)(void*, void*, void*);
typedef void*(__thiscall* DeletingDtorFn)(void*, unsigned);
typedef void*(__thiscall* EffectCtorFn)(void*, int);
typedef void(__thiscall* ApplyEffectFn)(void*, void*, int, int);
typedef short(__thiscall* HitPointsFn)(void*, int);
typedef void*(__thiscall* ResGffCtorFn)(void*);
typedef int(__thiscall* ResGffCreateFn)(void*, void*, const void*, const void*);
typedef int(__thiscall* ResGffWriteFn)(void*, const void*, unsigned short);
typedef void*(__thiscall* StrCtorFn)(void*, const char*);
typedef int(__thiscall* GetListFn)(void*, ResList*, ResStruct*, char*);
typedef int(__thiscall* GetCountFn)(void*, ResList*);
typedef int(__thiscall* ElementFn)(void*, ResStruct*, ResList*, DWORD);
typedef BYTE(__thiscall* ReadByteFn)(void*, ResStruct*, char*, int*, BYTE);
typedef int(__thiscall* WriteByteFn)(void*, ResStruct*, BYTE, char*);
typedef void(__thiscall* TransferFn)(void*, void*);
typedef int(__thiscall* AddNpcFn)(void*, int, void*);
typedef DWORD(__thiscall* SpawnNpcFn)(void*, int, int, const void*, const void*, int);
typedef int(__thiscall* AddMemberFn)(void*, int, DWORD);
typedef int(__thiscall* RemoveMemberFn)(void*, int);
typedef void(__thiscall* MainLoopFn)(void*);

bool IsStock(int s) { return s >= 0 && s < kStock; }
bool IsExtra(int s) { return s >= kStock && s < kMax; }
bool IsValid(int s) { return s >= 0 && s < kMax; }
Slot& Extra(int s) { return gSlots[s - kStock]; }

void ResetSidecar() {
    for (Slot& s : gSlots) s = Slot();
}

// ---------------------------------------------------------------- engine objects

void* App(int off) { return Get<void*>(*reinterpret_cast<void**>(kAppManagerPtr), off); }
void* Server() { return App(8); }
void* Client() { return App(4); }
void* PartyTable() { return Fn<PtrThisFn>(kServerGetPartyTable)(Server()); }

void* ServerCreature(DWORD id) {
    if (id == kNoObject) return nullptr;
    return Fn<ByIdFn>(kServerGetCreature)(Server(), id);
}
void* PlayerCreature() { return ServerCreature(Fn<IdThisFn>(kServerGetPlayerId)(Server())); }

void* ClientCreature(DWORD serverId) {
    if (serverId == kNoObject) return nullptr;
    const DWORD cid = Fn<ToClientFn>(kServerToClientId)(Client(), serverId);
    return Fn<ByIdFn>(kClientGetCreature)(Client(), cid);
}

void* NewObject(unsigned size) { return Fn<NewFn>(kOperatorNew)(size); }

void* ServerCreatureOfClient(void* clientCreature) { return Fn<PtrThisFn>(kClientGetServerCreature)(clientCreature); }

int ClientPartyIndex(DWORD serverId) {
    if (serverId == kNoObject) return -1;
    void* client = Client();
    void* party = Fn<PtrThisFn>(kClientGetParty)(client);
    if (!party) return -1;
    const DWORD cid = Fn<ToClientFn>(kServerToClientId)(client, serverId);
    return Fn<IndexFn>(kPartyGetIndex)(party, cid);
}

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
void SetAvailableOf(void* table, int slot, DWORD v) {
    if (!IsValid(slot)) return;
    if (IsExtra(slot)) { Extra(slot).available = v; return; }
    Put<DWORD>(table, kOffAvailable + slot * 4, v);
}
int FindSlotByObject(void* table, DWORD id) {
    if (id == kNoObject) return -1;
    for (int s = 0; s < kMax; ++s) if (ObjectIdOf(table, s) == id) return s;
    return -1;
}
bool IsPrimaryMember(void* table, int slot) {
    if (!IsValid(slot)) return false;
    const int n = Get<int>(table, kOffMemberCount);
    for (int i = 0; i < n; ++i) if (Get<int>(table, kOffMemberSlots + i * 4) == slot) return true;
    return false;
}

int ActiveIndexOf(void* table, int slot) {
    int n = Get<int>(table, kOffMemberCount);
    n = std::max(0, std::min(n, kActiveCapacity));
    for (int i = 0; i < n; ++i) if (Get<int>(table, kOffMemberSlots + i * 4) == slot) return i;
    return -1;
}

// ---------------------------------------------------------------- saving, loading and creating the extra companions (saved resources AVAILNPC<n>)

void PostLoadRecovery(void* creature, int apply) {
    if (apply == 0) return;
    if (Fn<HitPointsFn>(kObjectGetCurrentHitPoints)(creature, 0) > 0) return;
    Put<DWORD>(creature, kCreaturePostLoad, 1u);
    void* eff = NewObject(kEffectSize);
    Fn<EffectCtorFn>(kGameEffectCtor)(eff, 1);
    Put<WORD>(eff, kEffectType, *reinterpret_cast<const WORD*>(kEffectTypeWord));
    WORD fl = Get<WORD>(eff, kEffectSubtype);
    fl = static_cast<WORD>((fl & static_cast<WORD>(~7)) | (*reinterpret_cast<const WORD*>(kEffectSubtypeWord) & 7));
    Put<WORD>(eff, kEffectSubtype, fl);
    Fn<ApplyEffectFn>(kObjectApplyEffect)(creature, eff, 0, 0);
}

void* LoadSavedCreature(void* table, int slot) {
    void* creature = NewObject(kCreatureSize);
    Fn<CreatureCtorFn>(kCreatureCtor)(creature, kNoObject, 0);
    char ref[16] = {0};
    _snprintf_s(ref, sizeof(ref), _TRUNCATE, "availnpc%d", slot);   // lower case, zero padded
    Fn<VoidThisFn>(kPartyAddGameInProgress)(table);
    const int ok = Fn<LoadTemplateFn>(kCreatureLoadFromTemplate)(creature, ref, 0);
    if (ok == 0) {
        Fn<DeletingDtorFn>(kCreatureDeletingDtor)(creature, 1u);
        return nullptr;
    }
    Fn<VoidThisFn>(kPartyRemoveGameInProgress)(table);
    return creature;
}

void SaveToResource(int slot, void* creature) {
    void* gff = NewObject(kResGffSize);
    Fn<ResGffCtorFn>(kResGffCtor)(gff);
    char path[48];
    _snprintf_s(path, sizeof(path), _TRUNCATE, "GAMEINPROGRESS:AVAILNPC%d", slot);
    ExoString fileType, pathStr;
    ResStruct top{};
    Fn<StrCtorFn>(kExoStringCtorCStr)(&fileType, "UTC ");
    Fn<StrCtorFn>(kExoStringCtorCStr)(&pathStr, path);
    Fn<ResGffCreateFn>(kResGffCreateFile)(gff, &top, &fileType, nullptr);
    Fn<SaveCreatureFn>(kCreatureSaveCreature)(creature, gff, &top);
    Fn<ResGffWriteFn>(kResGffWriteFile)(gff, &pathStr, kSavedCreatureType);
    Fn<DeletingDtorFn>(kResGffDeletingDtor)(gff, 1u);
    Fn<VoidThisFn>(kExoStringDtor)(&pathStr);
    Fn<VoidThisFn>(kExoStringDtor)(&fileType);
}

DWORD ResolveNpcObject(void* table, int slot, int create, int recovery) {
    if (AvailableOf(table, slot) == 0) return kNoObject;
    const DWORD current = ObjectIdOf(table, slot);
    if (current != kNoObject || create == 0) return current;
    void* creature = LoadSavedCreature(table, slot);
    if (!creature) return kNoObject;
    PostLoadRecovery(creature, recovery);
    const DWORD id = Get<DWORD>(creature, kObjId);
    SetObjectIdOf(table, slot, id);
    return id;
}

int DestroyNpcObject(void* table, int slot, int fade) {
    if (!IsValid(slot) || IsPrimaryMember(table, slot)) return 0;
    const DWORD id = ObjectIdOf(table, slot);
    void* creature = ServerCreature(id);
    SetObjectIdOf(table, slot, kNoObject);
    if (!creature) return 0;
    if (fade != 0) {
        if (void* cc = ClientCreature(id)) {
            Fn<FadeFn>(kClientSetFadeState)(cc, 0);
            Fn<DesiredFadeFn>(kClientSetDesiredFadeState)(cc, 0, 1, 0, 0);
            Put<DWORD>(cc, kClientDeferredDelete, 1u);
        }
    }
    Fn<DeletingDtorFn>(kCreatureDeletingDtor)(creature, 1u);
    return 1;
}

// ---------------------------------------------------------------- hook handlers (arguments follow the site table: registers by value, stack arguments by address)

int __cdecl GetIsNPCAvailable32(void* table, const int* slot) { return AvailableOf(table, *slot) != 0; }

int __cdecl GetNumNPCAvailable32(void* table) {
    int n = 0;
    for (int s = 0; s < kMax; ++s) n += AvailableOf(table, s) != 0;
    return n;
}

void __cdecl SetNPCObject32(void* table, const int* slot, const DWORD* id) {
    if (AvailableOf(table, *slot) != 0) SetObjectIdOf(table, *slot, *id);
}

int __cdecl GetIsMemberByObject32(void* table, const DWORD* id) { return IsPrimaryMember(table, FindSlotByObject(table, *id)); }

int __cdecl GetIsAvailableByObject32(void* table, const DWORD* id) {
    for (int s = 0; s < kMax; ++s) if (ObjectIdOf(table, s) == *id) return 1;
    return 0;
}

int __cdecl GetNPCSelectability32(void* table, const int* slot) {
    const int s = *slot;
    if (AvailableOf(table, s) == 0) return 0xFF;
    return IsStock(s) ? Get<BYTE>(table, kOffSelectable + s) : Extra(s).selectable;
}

void __cdecl SetNPCSelectability32(void* table, const int* slot, const BYTE* value) {
    const int s = *slot;
    if (AvailableOf(table, s) == 0) return;
    if (IsStock(s)) Put<BYTE>(table, kOffSelectable + s, *value);
    else Extra(s).selectable = *value;
}

int __cdecl KillNPCObject32(void* table, const int* slot, const int* fade) { return DestroyNpcObject(table, *slot, *fade); }

int __cdecl GetNPCID32(void* table, const DWORD* id) { return FindSlotByObject(table, *id); }

void __cdecl ClearMember32(void* table, const int* slot) { SetObjectIdOf(table, *slot, kNoObject); }

int __cdecl GetIsLeader32(void* table, const DWORD* id) {
    const int s = FindSlotByObject(table, *id);
    return s >= 0 && s == Get<int>(table, kOffLeaderSlot);
}

void __cdecl SetLeaderByObject32(void* table, const DWORD* id) { Put<int>(table, kOffLeaderSlot, FindSlotByObject(table, *id)); }

void __cdecl SaveMember32(void* table, const int* slot, const int* mode) {
    void* creature = ServerCreature(ObjectIdOf(table, *slot));
    if (!creature) return;
    if (*mode != 0) Fn<SetIntFn>(kObjectClearAllActions)(creature, 1);
    SaveToResource(*slot, creature);
}

int __cdecl RemoveNPC32(void* table, const int* slot) {
    if (AvailableOf(table, *slot) == 0) return 0;
    SetAvailableOf(table, *slot, 0);
    return 1;
}

DWORD __cdecl GetNPCObject32(void* table, const int* slot, const int* create, const int* recovery) {
    return ResolveNpcObject(table, *slot, *create, *recovery);
}

int __cdecl RejectUnavailableMemberSlot(void* table, const int* slot) { return AvailableOf(table, *slot) == 0; }

int __cdecl PrepareAddMemberSlot(void* table, const int* slot, const DWORD* id) {
    for (int s = 0; s < kMax; ++s) {
        if (s != *slot && ObjectIdOf(table, s) == *id) return 1;
    }
    const int count = Get<int>(table, kOffMemberCount);
    Put<int>(table, kOffMemberSlots + count * 4, *slot);
    SetObjectIdOf(table, *slot, *id);
    return 0;
}

void __cdecl ResetExtendedPartyTable() { ResetSidecar(); }

void __cdecl ClearExtendedPartyObjectIds() {
    for (Slot& s : gSlots) s.objectId = kNoObject;
}

// The extra slots ride along in the party table's saved PT_AVAIL_NPCS list.
void __cdecl WriteExtendedPartyPersistence(void* gff, void* parent) {
    ResList list{};
    char listLabel[] = "PT_AVAIL_NPCS";
    if (!Fn<GetListFn>(kGffGetList)(gff, &list, static_cast<ResStruct*>(parent), listLabel)) return;
    int count = std::max(0, Fn<GetCountFn>(kGffGetListCount)(gff, &list));
    char availLabel[] = "PT_NPC_AVAIL", selLabel[] = "PT_NPC_SELECT";
    for (int s = kStock; s < kMax; ++s) {
        ResStruct el{};
        if (s < count) {
            if (!Fn<ElementFn>(kGffGetListElement)(gff, &el, &list, static_cast<DWORD>(s))) continue;
        } else {
            while (count <= s) {
                ResStruct made{};
                if (!Fn<ElementFn>(kGffAddListElement)(gff, &made, &list, 0)) return;
                if (count == s) el = made;
                ++count;
            }
        }
        const Slot& st = Extra(s);
        Fn<WriteByteFn>(kGffWriteFieldByte)(gff, &el, st.available ? 1u : 0u, availLabel);
        Fn<WriteByteFn>(kGffWriteFieldByte)(gff, &el, st.selectable ? 1u : 0u, selLabel);
    }
}

void __cdecl ReadExtendedPartyPersistence(void* gff, void* parent) {
    ResetSidecar();
    ResList list{};
    char listLabel[] = "PT_AVAIL_NPCS";
    if (!Fn<GetListFn>(kGffGetList)(gff, &list, static_cast<ResStruct*>(parent), listLabel)) return;
    const int count = std::max(0, std::min(Fn<GetCountFn>(kGffGetListCount)(gff, &list), kMax));
    char availLabel[] = "PT_NPC_AVAIL", selLabel[] = "PT_NPC_SELECT";
    for (int s = kStock; s < count; ++s) {
        ResStruct el{};
        if (!Fn<ElementFn>(kGffGetListElement)(gff, &el, &list, static_cast<DWORD>(s))) continue;
        int ok = 0;
        Extra(s).available = Fn<ReadByteFn>(kGffReadFieldByte)(gff, &el, availLabel, &ok, 0) != 0;
        ok = 0;
        Extra(s).selectable = Fn<ReadByteFn>(kGffReadFieldByte)(gff, &el, selLabel, &ok, 1) != 0;
    }
}

int __cdecl RejectAlreadyAvailableNpc(void* table, int slot) { return AvailableOf(table, slot) != 0; }

// after the engine's own AddNPC validation succeeded
void __cdecl SetAddNpcAvailable(void* table, int slot) { SetAvailableOf(table, slot, 1); }

void* __cdecl ResolveActiveMemberCreature(void* table, const int* slot) { return ServerCreature(ResolveNpcObject(table, *slot, 1, 1)); }

void* __cdecl ResolveUnstealthMemberCreature(void* table, int counter) {
    const int index = counter & 0xFF;
    const int slot = Get<int>(table, kOffMemberSlots + index * 4);
    return ServerCreature(ResolveNpcObject(table, slot, 1, 1));
}

void __cdecl StoreCreatePartyPlayerObjectId(void* table, DWORD id) { SetObjectIdOf(table, Get<int>(table, kOffPlayerSlot), id); }

void __cdecl TransferExistingNpcInventories(void* table, void*) {
    for (int s = 0; s < kMax; ++s) {
        if (void* c = ServerCreature(ObjectIdOf(table, s))) Fn<TransferFn>(kPartyTransferInventory)(table, c);
    }
}

void __cdecl PostProcessExistingNpcs(void* table, void*) {
    for (int s = 0; s < kMax; ++s) {
        if (void* c = ServerCreature(ObjectIdOf(table, s))) Fn<VoidThisFn>(kCreatureForceEquipClothing)(c);
    }
}

int __cdecl RejectSwitchPlayerTarget(void* table, int slot) { return AvailableOf(table, slot) == 0; }

DWORD __cdecl ResolveSwitchPlayerTargetObjectId(void* table, int slot) { return ResolveNpcObject(table, slot, 0, 0); }

void __cdecl DestroyDetachedSwitchNpc(void* table, int slot) { DestroyNpcObject(table, slot, 1); }

#include "party32_gui.inc"

// ---------------------------------------------------------------- the handler table

struct HandlerEntry { const char* name; void* fn; };
#define H(n) {#n, reinterpret_cast<void*>(&n)}
const HandlerEntry kHandlers[] = {
    H(GetIsNPCAvailable32), H(GetNumNPCAvailable32), H(SetNPCObject32), H(GetIsMemberByObject32), H(GetIsAvailableByObject32), H(GetNPCSelectability32),
    H(SetNPCSelectability32), H(KillNPCObject32), H(GetNPCID32), H(ClearMember32), H(GetIsLeader32), H(SetLeaderByObject32), H(SaveMember32), H(RemoveNPC32),
    H(GetNPCObject32), H(RejectUnavailableMemberSlot), H(PrepareAddMemberSlot), H(ResetExtendedPartyTable), H(ClearExtendedPartyObjectIds),
    H(WriteExtendedPartyPersistence), H(ReadExtendedPartyPersistence), H(RejectAlreadyAvailableNpc), H(SetAddNpcAvailable), H(ResolveActiveMemberCreature),
    H(ResolveUnstealthMemberCreature), H(StoreCreatePartyPlayerObjectId), H(TransferExistingNpcInventories), H(PostProcessExistingNpcs),
    H(RejectSwitchPlayerTarget), H(ResolveSwitchPlayerTargetObjectId), H(DestroyDetachedSwitchNpc),
    // paged party-selection screen (party32_gui.inc)
    H(PreparePartySelectionOnDone), H(PreparePartySelectionAccept), H(FinishPartySelectionAccept), H(PrepareSetForcedNPC32), H(FinishPartySelectionLayout),
    H(PreparePartySelectionDestructor), H(PreparePartySelectionOnPanelAdded), H(FinishPartySelectionOnPanelAdded), H(PreparePartySelectionOnPanelRemoved),
    H(FinishPartySelectionOnPanelRemoved), H(AdjustPartySelectionAfterObjectRemoval), H(ClearPartySelectionForcedFlags),
};
#undef H

void* FindHandler(const char* name) {
    for (const HandlerEntry& h : kHandlers) if (!strcmp(h.name, name)) return h.fn;
    return nullptr;
}

// ---------------------------------------------------------------- code patching

uint8_t* gPool = nullptr;
size_t gPoolUsed = 0;
constexpr size_t kPoolSize = 64 * 1024;

uint8_t* Reserve(size_t n) {
    if (!gPool) {
        gPool = static_cast<uint8_t*>(VirtualAlloc(nullptr, kPoolSize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
        if (!gPool) return nullptr;
    }
    if (gPoolUsed + n > kPoolSize) return nullptr;
    uint8_t* p = gPool + gPoolUsed;
    gPoolUsed += (n + 15) & ~static_cast<size_t>(15);
    return p;
}

bool BytesMatch(uint32_t address, const uint8_t* expected, size_t n) {
    return memcmp(reinterpret_cast<const void*>(static_cast<uintptr_t>(address)), expected, n) == 0;
}

bool WriteCode(uint32_t address, const uint8_t* data, size_t n) {
    void* p = reinterpret_cast<void*>(static_cast<uintptr_t>(address));
    DWORD old = 0;
    if (!VirtualProtect(p, n, PAGE_EXECUTE_READWRITE, &old)) return false;
    memcpy(p, data, n);
    VirtualProtect(p, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, n);
    return true;
}

struct Emitter {
    uint8_t* base;
    size_t size = 0;
    explicit Emitter(uint8_t* b) : base(b) {}
    void B(uint8_t v) { base[size++] = v; }
    void Bytes(const void* p, size_t n) { memcpy(base + size, p, n); size += n; }
    void U32(uint32_t v) { Bytes(&v, 4); }
    void Jmp(uint32_t target) {
        B(0xE9);
        U32(static_cast<uint32_t>(target - (reinterpret_cast<uint32_t>(base) + static_cast<uint32_t>(size) + 4)));
    }
};

// pushad frame: edi lowest, eax highest
int PushadSlot(int kind) {
    static const int slot[7] = {28, 24, 20, 16, 8, 4, 0};   // eax ecx edx ebx ebp esi edi
    return slot[kind];
}

bool InstallDetour(const Site& s, void* handler) {
    uint8_t* mem = Reserve(160 + (s.skipOriginal ? 0 : s.length));
    if (!mem) return false;
    Emitter e(mem);
    const uint32_t returnTo = s.address + s.length;
    e.B(0x9C);   // pushfd
    e.B(0x60);   // pushad
    int pushed = 0;
    for (int i = s.argCount; i-- > 0;) {
        const ArgSpec& a = s.args[i];
        if (a.kind == 7) {
            e.B(0x8D); e.B(0x84); e.B(0x24); e.U32(static_cast<uint32_t>(36 + a.offset + 4 * pushed));   // lea eax,[esp+36+off+4*pushed]
        } else {
            e.B(0x8B); e.B(0x84); e.B(0x24); e.U32(static_cast<uint32_t>(PushadSlot(a.kind) + 4 * pushed));   // mov eax,[esp+slot+4*pushed]
        }
        e.B(0x50);   // push eax
        ++pushed;
    }
    e.B(0xB8); e.U32(reinterpret_cast<uint32_t>(handler));   // mov eax, handler
    e.B(0xFF); e.B(0xD0);                                    // call eax
    if (pushed) { e.B(0x83); e.B(0xC4); e.B(static_cast<uint8_t>(4 * pushed)); }   // add esp, 4*argc
    if (s.consumedExit != 0) {
        e.B(0x85); e.B(0xC0);                 // test eax,eax
        e.B(0x74);                            // jz notConsumed
        const size_t fix = e.size++;
        e.B(0x89); e.B(0x44); e.B(0x24); e.B(28);   // mov [esp+28], eax  (result survives popad)
        e.B(0x61); e.B(0x9D);                 // popad, popfd
        e.Jmp(s.consumedExit);
        e.base[fix] = static_cast<uint8_t>(e.size - (fix + 1));
        e.B(0x61); e.B(0x9D);
    } else {
        if (s.resultEax) { e.B(0x89); e.B(0x44); e.B(0x24); e.B(28); }
        e.B(0x61); e.B(0x9D);
    }
    if (!s.skipOriginal) e.Bytes(s.original, s.length);
    e.Jmp(returnTo);

    uint8_t patch[512];
    if (s.length > sizeof(patch)) return false;
    memset(patch, 0x90, s.length);
    patch[0] = 0xE9;
    const int32_t rel = static_cast<int32_t>(reinterpret_cast<uint32_t>(mem) - (s.address + 5));
    memcpy(patch + 1, &rel, 4);
    FlushInstructionCache(GetCurrentProcess(), mem, e.size);
    return WriteCode(s.address, patch, s.length);
}

// ---------------------------------------------------------------- configuration (and, in development builds, test commands)

// The path of a file beside the game executable.
bool BesideExe(const char* relative, char* out, size_t outSize) {
    DWORD n = GetModuleFileNameA(nullptr, out, static_cast<DWORD>(outSize));
    if (!n || n >= outSize) return false;
    char* slash = strrchr(out, '\\');
    if (!slash) return false;
    return strcpy_s(slash + 1, outSize - static_cast<size_t>(slash + 1 - out), relative) == 0;
}

// "ap_party32.txt": missing = default (on); a first line of 0, off or false turns the roster off (a switch for testing and support).
bool RosterEnabled() {
    char path[MAX_PATH];
    if (!BesideExe("ap_party32.txt", path, sizeof(path))) return true;
    FILE* f = nullptr;
    if (fopen_s(&f, path, "r") != 0 || !f) return true;
    char line[32] = {0};
    bool off = false;
    if (fgets(line, sizeof(line), f)) {
        char* e = line + strlen(line);
        while (e > line && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ')) *--e = 0;
        off = !_stricmp(line, "0") || !_stricmp(line, "off") || !_stricmp(line, "false");
    }
    fclose(f);
    return !off;
}

// The paged party screen needs the replacement layout (Override\partyselection.gui with the 32 portrait buttons and the two page buttons). Without it the screen
// patches stay off and the stock nine-slot screen is used.
bool LayoutReady() {
    char path[MAX_PATH];
    if (!BesideExe("Override\\partyselection.gui", path, sizeof(path))) return false;
    FILE* f = nullptr;
    if (fopen_s(&f, path, "rb") != 0 || !f) return false;
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    bool ok = false;
    if (size > 0 && size < (8 << 20)) {
        char* data = static_cast<char*>(malloc(static_cast<size_t>(size)));
        if (data && fread(data, 1, static_cast<size_t>(size), f) == static_cast<size_t>(size)) {
            auto has = [&](const char* needle) {
                const size_t n = strlen(needle);
                for (long i = 0; i + static_cast<long>(n) <= size; ++i) if (!memcmp(data + i, needle, n)) return true;
                return false;
            };
            ok = has("BTN_NPC31") && has("BTN_PAGE_NEXT") && has("BTN_PAGE_PREV") && has("LBL_NA31");
        }
        free(data);
    }
    fclose(f);
    return ok;
}

#ifdef AP_PARTY32_TEST   // a development build only: roster commands read from a file beside the game

void LogClientState(const char* what, void* table, int slot) {
    const DWORD id = ObjectIdOf(table, slot);
    void* client = Client();
    const DWORD cid = id == kNoObject ? kNoObject : Fn<ToClientFn>(kServerToClientId)(client, id);
    void* cc = id == kNoObject ? nullptr : Fn<ByIdFn>(kClientGetCreature)(client, cid);
    void* sc = ServerCreature(id);
    void* party = Fn<PtrThisFn>(kClientGetParty)(client);
    const int index = (party && cid != kNoObject) ? Fn<IndexFn>(kPartyGetIndex)(party, cid) : -2;
    Log("party32test: %s slot %d: server id 0x%08lX client id 0x%08lX serverCreature=%p clientCreature=%p clientInPartyFlag=%d clientPartyIndex=%d", what, slot, id, cid, sc, cc,
        cc ? Get<int>(cc, 0x3A4) : -1, index);
}

void ReportTable(void* table) {
    Log("party32test: party members=%d slots=[%d,%d] leader=%d player=%d", Get<int>(table, kOffMemberCount), Get<int>(table, kOffMemberSlots),
        Get<int>(table, kOffMemberSlots + 4), Get<int>(table, kOffLeaderSlot), Get<int>(table, kOffPlayerSlot));
    for (int s = 0; s < kMax; ++s) {
        if (AvailableOf(table, s) == 0 && ObjectIdOf(table, s) == kNoObject) continue;
        Log("party32test:   slot %2d available=%lu object=0x%08lX selectable=%d%s", s, AvailableOf(table, s), ObjectIdOf(table, s),
            IsStock(s) ? Get<BYTE>(table, kOffSelectable + s) : Extra(s).selectable, IsPrimaryMember(table, s) ? " IN PARTY" : "");
    }
}

void RunTestCommand(char* line) {
    char cmd[16] = {0}, arg[40] = {0};
    int slot = -1;
    const int n = sscanf_s(line, "%15s %d %39s", cmd, (unsigned)sizeof(cmd), &slot, arg, (unsigned)sizeof(arg));
    if (n < 1) return;
    void* table = PartyTable();
    if (!table) { Log("party32test: no party table yet (load a game first)"); return; }
    if (!_stricmp(cmd, "report")) {
        ReportTable(table);
    } else if (!_stricmp(cmd, "add") && n >= 3) {
        ExoString tmpl;
        Fn<StrCtorFn>(kExoStringCtorCStr)(&tmpl, arg);
        const int r = Fn<AddNpcFn>(kPartyAddNpc)(table, slot, &tmpl);
        Fn<VoidThisFn>(kExoStringDtor)(&tmpl);
        Log("party32test: add slot %d template '%s' -> %d", slot, arg, r);
    } else if (!_stricmp(cmd, "spawn") && n >= 2) {
        void* player = PlayerCreature();
        if (!player) { Log("party32test: no player creature"); return; }
        BYTE* pb = static_cast<BYTE*>(player);
        // optional offsets in metres from the player: "spawn <slot> <dx> <dy>", so many can be spawned side by side
        float dx = 0.0f, dy = 0.0f;
        float pos[3] = {Get<float>(pb, kObjPosition), Get<float>(pb, kObjPosition + 4), Get<float>(pb, kObjPosition + 8)};
        if (sscanf_s(line, "%*s %*d %f %f", &dx, &dy) == 2) { pos[0] += dx; pos[1] += dy; }
        const DWORD id = Fn<SpawnNpcFn>(kPartySpawnNpc)(table, slot, 1, pos, pb + kObjOrientation, 1);
        Log("party32test: spawn slot %d at +%.1f,%.1f -> object 0x%08lX", slot, dx, dy, id);
    } else if (!_stricmp(cmd, "join") && n >= 2) {
        const DWORD id = ObjectIdOf(table, slot);
        if (id == kNoObject) { Log("party32test: slot %d has no creature (spawn first)", slot); return; }
        LogClientState("join before", table, slot);
        const int r = Fn<AddMemberFn>(kPartyAddMember)(table, slot, id);
        if (r != 0) {
            void* cc = ClientCreature(id);
            void* sc = ServerCreature(id);
            if (cc) Fn<SetIntFn>(kClientSetInParty)(cc, 1);
            if (sc) Fn<SetInPartyFn>(kServerSetInParty)(sc, 1, 1);
        }
        Log("party32test: join slot %d -> %d", slot, r);
        LogClientState("join after", table, slot);
    } else if (!_stricmp(cmd, "leave") && n >= 2) {
        const DWORD id = ObjectIdOf(table, slot);
        LogClientState("leave before", table, slot);
        const int r = Fn<RemoveMemberFn>(kPartyRemoveMember)(table, slot);
        if (r != 0) {
            void* cc = ClientCreature(id);
            void* sc = ServerCreature(id);
            if (cc) Fn<SetIntFn>(kClientSetInParty)(cc, 0);
            if (sc) Fn<SetInPartyFn>(kServerSetInParty)(sc, 0, 1);
        }
        Log("party32test: leave slot %d -> %d", slot, r);
        LogClientState("leave after", table, slot);
    } else if (!_stricmp(cmd, "cinfo") && n >= 2) {
        LogClientState("info", table, slot);
    } else if (!_stricmp(cmd, "remove") && n >= 2) {
        Log("party32test: remove slot %d -> %d", slot, RemoveNPC32(table, &slot));
    } else {
        Log("party32test: unknown command '%s'", line);
    }
}

MainLoopFn gOrigMainLoop = nullptr;
volatile LONG gTestTick = 0;

void __fastcall MainLoopDetour(void* self, void*) {
    if ((InterlockedIncrement(&gTestTick) & 63) == 0) {
        char path[MAX_PATH];
        DWORD n = GetModuleFileNameA(nullptr, path, MAX_PATH);
        char* slash = n && n < MAX_PATH ? strrchr(path, '\\') : nullptr;
        if (slash) {
            strcpy_s(slash + 1, static_cast<size_t>(MAX_PATH - (slash + 1 - path)), "ap_party32_test.txt");
            FILE* f = nullptr;
            if (fopen_s(&f, path, "r") == 0 && f) {
                char lines[40][80];
                int count = 0;
                while (count < 40 && fgets(lines[count], sizeof(lines[count]), f)) ++count;
                fclose(f);
                char done[MAX_PATH];
                _snprintf_s(done, sizeof(done), _TRUNCATE, "%s.done", path);
                DeleteFileA(done);
                MoveFileA(path, done);   // each file runs once
                for (int i = 0; i < count; ++i) {
                    __try {
                        RunTestCommand(lines[i]);
                    } __except (EXCEPTION_EXECUTE_HANDLER) {
                        Log("party32test: command '%s' raised an exception", lines[i]);
                    }
                }
            }
        }
    }
    gOrigMainLoop(self);
}

#endif  // AP_PARTY32_TEST

}  // namespace

int Party32Install() {
    if (!RosterEnabled()) {
        Log("party32: off (ap_party32.txt says 0/off)");
        return 0;
    }
    const bool gui = LayoutReady();
    if (!gui) Log("party32: the replacement party-selection layout (Override\\partyselection.gui) is not installed: the stock party screen stays, slots above 9 cannot be picked on it");
    // 1. verify every site before writing any of them
    int wanted = 0;
    for (int i = 0; i < kSiteCount; ++i) {
        const Site& s = kSites[i];
        if (s.gui && !gui) continue;
        if (!s.simple && !FindHandler(s.handler)) { Log("party32: NOT applied: no handler '%s' for hook %d", s.handler, s.number); return 0; }
        if (!BytesMatch(s.address, s.original, s.length)) {
            Log("party32: NOT applied: hook %d at 0x%08X does not hold the expected bytes", s.number, s.address);
            return 0;
        }
        ++wanted;
    }
    ResetSidecar();
    // 2. apply them
    int applied = 0;
    for (int i = 0; i < kSiteCount; ++i) {
        const Site& s = kSites[i];
        if (s.gui && !gui) continue;
        bool ok;
        if (s.simple) {
            uint8_t repl = s.replacement;
            ok = WriteCode(s.address, &repl, 1);
        } else {
            ok = InstallDetour(s, FindHandler(s.handler));
        }
        if (!ok) Log("party32: hook %d at 0x%08X FAILED (the site may be half patched)", s.number, s.address);
        else ++applied;
    }
    Log("party32: %d of %d sites applied (slots 9-31 active, paged party screen %s)", applied, wanted, gui ? "ON" : "off: layout missing");
#ifdef AP_PARTY32_TEST
    if (applied == wanted && MH_CreateHook(reinterpret_cast<LPVOID>(kServerMainLoop), reinterpret_cast<LPVOID>(&MainLoopDetour), reinterpret_cast<LPVOID*>(&gOrigMainLoop)) == MH_OK &&
        MH_EnableHook(reinterpret_cast<LPVOID>(kServerMainLoop)) == MH_OK) {
        Log("party32: test commands are read from ap_party32_test.txt (add/spawn/join/leave/remove/report)");
    }
#endif
    return applied;
}

}  // namespace party32

int Party32Install() { return party32::Party32Install(); }
