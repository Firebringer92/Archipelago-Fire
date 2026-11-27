// Included by party32.cpp inside its anonymous namespace (it uses that file's helpers). Not a standalone source file.
//
// Paged party selection screen for KOTOR 1. The stock screen has nine portrait records at panel+0x7C (stride 0x454). We keep 16 records of our own that the replacement layout
// file (Override\partyselection.gui: BTN_NPC0-15, LBL_CHAR0-15, LBL_NA0-15, BTN_PAGE_PREV/NEXT) binds by tag, and show slots 0-15 or 16-31 on them.
// Structure follows the Patch Manager mod PartyRosterLimit32K1 (MIT, Vriff and Patch Manager contributors).

constexpr int kPageSlots = 16;
constexpr int kLastPageBase = kMax - kPageSlots;
constexpr int kRecordStride = 0x454;        // CSWGuiPartySelectionData
constexpr int kPanelRecordBase = 0x7C;      // CSWGuiPartySelection::party_data
constexpr int kButtonObjectSize = 452;      // CSWGuiButton
constexpr int kStateCapacity = 2;

constexpr int kRecButton = 0x000;
constexpr int kRecBackPointer = 0x058;
constexpr int kRecAlpha = 0x08C;
constexpr int kRecInitParams = 0x0F4;
constexpr int kRecDefaultColor = 0x104;
constexpr int kRecSelected = 0x1C4;
constexpr int kRecNotAvailable = 0x1C8;     // portrait_label
constexpr int kRecCharacter = 0x308;        // character_label
constexpr int kRecTextureParams = 0x378;
constexpr int kRecSelectionAlpha = 0x384;
constexpr int kRecFlags = 0x448;
constexpr int kRecObjectIndex = 0x44C;
constexpr int kRecLogicalSlot = 0x450;
constexpr int kRecControlOffsets[3] = {kRecCharacter, kRecButton, kRecNotAvailable};
constexpr DWORD kFlagEnabled = 0x1, kFlagHasObject = 0x2, kFlagForced = 0x4;

constexpr int kPanelSelectedCount = 0x68;
constexpr int kPanelForcedMode = 0x6C;
constexpr int kPanelMode = 0x70;
constexpr int kPanelDoneButton = 0x28B0;
constexpr int kPanelCurrentPortrait = 0x38B8 + kButtonObjectSize;   // accept_button + one button object
constexpr int kPanelControlArray = 0x20;    // CExoArrayList<CSWGuiControl*>: data pointer, count, capacity
constexpr int kPanelControlCount = 0x24;
constexpr int kControlFlags = 0x44;         // CSWGuiControl::bit_flags
constexpr DWORD kControlVisible = 0x2, kControlMouseIgnore = 0x20;
constexpr int kControlEventOwner = 0x4C;
constexpr int kEventPrimary = 0x27, kEventClick = 0x2D;
constexpr int kNavUp = 0, kNavDown = 2;

constexpr uintptr_t kGuiPanelStopLoadFromLayout = 0x0040B8F0;
constexpr uintptr_t kGuiPanelInitControl = 0x0040B930;
constexpr uintptr_t kGuiPanelAddControl = 0x0040B9A0;
constexpr uintptr_t kGuiPanelSetActiveControl = 0x0040A630;
constexpr uintptr_t kGuiControlAddEvent = 0x0041AB20;
constexpr uintptr_t kGuiButtonSetEnabled = 0x00418DB0;
constexpr uintptr_t kGuiButtonSetActive = 0x00418E00;
constexpr uintptr_t kGuiSetMoveToControl = 0x00417660;
constexpr uintptr_t kGuiButtonCtor = 0x0041C0F0;
constexpr uintptr_t kGuiButtonDtor = 0x00419DA0;
constexpr uintptr_t kGuiBorderSetFillImage = 0x00414C00;
constexpr uintptr_t kGuiBorderSetPulsingAlpha = 0x00414D00;
constexpr uintptr_t kPartySelectionButtonSetSelected = 0x006BE370;
constexpr uintptr_t kPartySelectionRecordCtor = 0x006BED70;
constexpr uintptr_t kPartySelectionRecordDtor = 0x006BE420;
constexpr uintptr_t kPartySelectionOnToggled = 0x006BF2A0;
constexpr uintptr_t kPartySelectionOnEnter = 0x006BF5B0;
constexpr uintptr_t kPartySelectionHoverStub = 0x0060E760;      // a "ret 4" the original patch binds to the hover event
constexpr uintptr_t kPartySelectionUpdateCount = 0x006BE4E0;
constexpr uintptr_t kCreatureGetPortrait = 0x004F8370;
constexpr uintptr_t kPathfindResetWaypointData = 0x005CF060;
constexpr uintptr_t kCreatureGetVisibleListElement = 0x00517A20;
constexpr uintptr_t kCreatureAddToVisibleList = 0x0051B370;
constexpr uintptr_t kPartyRecalculateFollowPoint = 0x006359C0;
constexpr int kCreaturePathfind = 0x340;

struct ViewState {
    void* owner;
    BYTE* records;
    BYTE* pageButtons;
    unsigned constructedRecords;
    unsigned constructedButtons;
    int pageBase;
    bool ready;
    bool selected[kMax];
    bool forced[kMax];
};
ViewState gViews[kStateCapacity] = {};

typedef void(__thiscall* SetSelectedFn)(void*, int);
typedef void(__thiscall* InitControlFn)(void*, void*, const void*, int);
typedef void(__thiscall* AddControlFn)(void*, void*);
typedef void(__thiscall* SetActiveControlFn)(void*, void*, int);
typedef void(__thiscall* AddEventFn)(void*, int, void*, void*);
typedef void(__thiscall* IntThisFn)(void*, int);
typedef void(__thiscall* SetMoveToFn)(void*, int, void*);
typedef void(__thiscall* FillImageFn)(void*, const void*, int);
typedef void(__thiscall* PulsingFn)(void*, int, int, int);
typedef void*(__thiscall* PortraitFn)(void*, void*);
typedef int(__thiscall* VisibleGetFn)(void*, DWORD);
typedef void(__thiscall* VisibleAddFn)(void*, DWORD, int, int, int, int);
struct ResRef16 { char s[16]; };

BYTE* StockRecord(void* panel, int i) { return static_cast<BYTE*>(panel) + kPanelRecordBase + i * kRecordStride; }

void* AllocAligned(size_t size, size_t align) {
    const size_t total = size + align - 1 + sizeof(void*);
    void* raw = malloc(total);
    if (!raw) return nullptr;
    const uintptr_t start = reinterpret_cast<uintptr_t>(raw) + sizeof(void*);
    const uintptr_t a = (start + align - 1) & ~(align - 1);
    reinterpret_cast<void**>(a)[-1] = raw;
    return reinterpret_cast<void*>(a);
}
void FreeAligned(void* m) { if (m) free(reinterpret_cast<void**>(m)[-1]); }

ViewState* FindView(void* panel) {
    for (ViewState& v : gViews) if (v.owner == panel) return &v;
    return nullptr;
}
ViewState* ReserveView(void* panel) {
    if (ViewState* v = FindView(panel)) return v;
    for (ViewState& v : gViews) {
        if (!v.owner) { memset(&v, 0, sizeof(v)); v.owner = panel; v.pageBase = -1; return &v; }
    }
    return nullptr;
}
BYTE* ViewRecord(ViewState* v, int i) { return v->records + i * kRecordStride; }
BYTE* PageButton(ViewState* v, int i) { return v->pageButtons + i * kButtonObjectSize; }

void SetVisible(void* c, bool on) {
    DWORD f = Get<DWORD>(c, kControlFlags);
    f = on ? (f | kControlVisible) : (f & ~kControlVisible);
    Put<DWORD>(c, kControlFlags, f);
}
void SetHitTest(void* c, bool on) {
    DWORD f = Get<DWORD>(c, kControlFlags);
    f = on ? (f & ~kControlMouseIgnore) : (f | kControlMouseIgnore);
    Put<DWORD>(c, kControlFlags, f);
}
bool IsVisible(void* c) { return (Get<DWORD>(c, kControlFlags) & kControlVisible) != 0; }

void BindControl(void* panel, void* dest, const char* tag) {
    ExoString s;
    Fn<StrCtorFn>(kExoStringCtorCStr)(&s, tag);
    Fn<InitControlFn>(kGuiPanelInitControl)(panel, dest, &s, 1);
    Fn<VoidThisFn>(kExoStringDtor)(&s);
}

bool Selectable(void* table, int slot) {
    if (!IsValid(slot) || AvailableOf(table, slot) == 0) return false;
    return IsStock(slot) ? Get<BYTE>(table, kOffSelectable + slot) != 0 : Extra(slot).selectable != 0;
}

void SetUnavailableRecord(BYTE* rec, int slot) {
    Fn<SetSelectedFn>(kPartySelectionButtonSetSelected)(rec + kRecButton, 0);
    Put<DWORD>(rec, kRecFlags, kFlagHasObject);
    Put<int>(rec, kRecObjectIndex, -1);
    Put<int>(rec, kRecLogicalSlot, slot);
    Put<float>(rec, kRecAlpha, 1.0f);
    Put<float>(rec, kRecSelectionAlpha, 0.25f);
    BYTE* button = rec + kRecButton;
    BYTE* na = rec + kRecNotAvailable;
    BYTE* ch = rec + kRecCharacter;
    SetVisible(button, true);
    SetHitTest(button, false);
    Fn<IntThisFn>(kGuiButtonSetEnabled)(button, 0);
    SetVisible(na, slot < kStock);
    SetHitTest(na, false);
    SetVisible(ch, false);
    SetHitTest(ch, false);
}

bool SetAvailableRecord(BYTE* rec, ViewState* st, void* table, int slot) {
    const DWORD id = ResolveNpcObject(table, slot, 1, 1);
    void* creature = ServerCreature(id);
    if (!creature) { SetUnavailableRecord(rec, slot); return false; }
    ResRef16 portrait = {};
    Fn<PortraitFn>(kCreatureGetPortrait)(creature, &portrait);
    Fn<FillImageFn>(kGuiBorderSetFillImage)(rec + kRecTextureParams, &portrait, 0);
    const int active = ActiveIndexOf(table, slot);
    const bool forced = st->forced[slot];
    const bool selected = st->selected[slot] || forced;
    const bool interactive = Selectable(table, slot) && !forced;
    DWORD flags = kFlagEnabled | kFlagHasObject;
    if (forced) flags |= kFlagForced;
    Put<DWORD>(rec, kRecFlags, flags);
    Put<int>(rec, kRecObjectIndex, active >= 0 ? ClientPartyIndex(id) : -1);
    Put<int>(rec, kRecLogicalSlot, slot);
    Put<float>(rec, kRecAlpha, 1.0f);
    Put<float>(rec, kRecSelectionAlpha, selected ? 1.0f : 0.25f);
    Fn<SetSelectedFn>(kPartySelectionButtonSetSelected)(rec + kRecButton, selected ? 1 : 0);
    BYTE* button = rec + kRecButton;
    BYTE* na = rec + kRecNotAvailable;
    BYTE* ch = rec + kRecCharacter;
    SetVisible(button, true);
    SetHitTest(button, interactive);
    Fn<IntThisFn>(kGuiButtonSetEnabled)(button, interactive ? 1 : 0);
    SetVisible(na, false);
    SetHitTest(na, false);
    SetVisible(ch, true);
    SetHitTest(ch, false);
    return true;
}

void InitRecord(void* panel, ViewState* st, int i) {
    BYTE* rec = ViewRecord(st, i);
    memset(rec, 0, kRecordStride);
    Fn<PtrThisFn>(kPartySelectionRecordCtor)(rec);
    ++st->constructedRecords;
    char tag[32];
    _snprintf_s(tag, sizeof(tag), _TRUNCATE, "LBL_NA%d", i);   BindControl(panel, rec + kRecNotAvailable, tag);
    _snprintf_s(tag, sizeof(tag), _TRUNCATE, "LBL_CHAR%d", i); BindControl(panel, rec + kRecCharacter, tag);
    _snprintf_s(tag, sizeof(tag), _TRUNCATE, "BTN_NPC%d", i);  BindControl(panel, rec + kRecButton, tag);
    auto addEvent = Fn<AddEventFn>(kGuiControlAddEvent);
    BYTE* button = rec + kRecButton;
    addEvent(button, kEventPrimary, panel, reinterpret_cast<void*>(kPartySelectionOnToggled));
    addEvent(button, kEventClick, panel, reinterpret_cast<void*>(kPartySelectionOnToggled));
    addEvent(button, 0, panel, reinterpret_cast<void*>(kPartySelectionOnEnter));
    addEvent(button, 1, panel, reinterpret_cast<void*>(kPartySelectionHoverStub));
    Put<void*>(rec, kRecBackPointer, rec);
    memcpy(rec + kRecDefaultColor, StockRecord(panel, 0) + kRecDefaultColor, sizeof(float) * 3);
    Fn<PulsingFn>(kGuiBorderSetPulsingAlpha)(rec + kRecInitParams, 1, 1, 0);
    Put<DWORD>(rec, kRecFlags, 0u);
    Put<int>(rec, kRecLogicalSlot, i);
    SetUnavailableRecord(rec, i);
}

void __fastcall PrevCallback(void* self, void*, void*);
void __fastcall NextCallback(void* self, void*, void*);

void InitPageButton(void* panel, ViewState* st, int index, const char* tag, void* callback) {
    BYTE* b = PageButton(st, index);
    memset(b, 0, kButtonObjectSize);
    Fn<PtrThisFn>(kGuiButtonCtor)(b);
    ++st->constructedButtons;
    BindControl(panel, b, tag);
    auto addEvent = Fn<AddEventFn>(kGuiControlAddEvent);
    addEvent(b, kEventPrimary, panel, callback);
    addEvent(b, kEventClick, panel, callback);
}

bool CreateView(void* panel) {
    ViewState* st = ReserveView(panel);
    if (!st || st->ready) return st && st->ready;
    st->records = static_cast<BYTE*>(AllocAligned(kPageSlots * kRecordStride, 16));
    st->pageButtons = static_cast<BYTE*>(AllocAligned(2 * kButtonObjectSize, 16));
    if (!st->records || !st->pageButtons) {
        FreeAligned(st->records);
        FreeAligned(st->pageButtons);
        memset(st, 0, sizeof(*st));
        return false;
    }
    for (int i = 0; i < kPageSlots; ++i) InitRecord(panel, st, i);
    InitPageButton(panel, st, 0, "BTN_PAGE_PREV", reinterpret_cast<void*>(&PrevCallback));
    InitPageButton(panel, st, 1, "BTN_PAGE_NEXT", reinterpret_cast<void*>(&NextCallback));
    st->ready = true;
    Log("party32: paged party screen built (16 records, 2 page buttons)");
    return true;
}

// The panel's control list holds plain pointers: removing one shifts the later ones down.
void DetachControl(void* panel, void* control) {
    void** controls = Get<void**>(panel, kPanelControlArray);
    int count = Get<int>(panel, kPanelControlCount);
    if (!controls || count <= 0 || count > 4096) return;
    for (int i = 0; i < count; ++i) {
        if (controls[i] == control) {
            for (int j = i; j + 1 < count; ++j) controls[j] = controls[j + 1];
            Put<int>(panel, kPanelControlCount, count - 1);
            return;
        }
    }
}

void DetachControls(void* panel, ViewState* st, bool pageButtons) {
    for (int i = 0; i < kStock; ++i) {
        BYTE* rec = StockRecord(panel, i);
        for (int off : kRecControlOffsets) DetachControl(panel, rec + off);
    }
    if (st && st->records) {
        for (int i = 0; i < kPageSlots; ++i) {
            BYTE* rec = ViewRecord(st, i);
            for (int off : kRecControlOffsets) DetachControl(panel, rec + off);
        }
    }
    if (pageButtons && st && st->pageButtons) for (int i = 0; i < 2; ++i) DetachControl(panel, PageButton(st, i));
}

void AttachStockControls(void* panel) {
    ViewState* st = FindView(panel);
    DetachControls(panel, st, false);
    auto add = Fn<AddControlFn>(kGuiPanelAddControl);
    for (int off : kRecControlOffsets) for (int i = 0; i < kStock; ++i) add(panel, StockRecord(panel, i) + off);
}

int CountSelected(const ViewState* st) {
    int n = 0;
    for (int s = 0; s < kMax; ++s) n += st->selected[s] || st->forced[s];
    return n;
}

void CapturePage(ViewState* st) {
    if (!st || !st->ready || st->pageBase < 0) return;
    for (int i = 0; i < kPageSlots; ++i) {
        const int slot = st->pageBase + i;
        const bool sel = Get<int>(ViewRecord(st, i), kRecSelected) != 0;
        st->selected[slot] = sel || st->forced[slot];
    }
    Put<int>(st->owner, kPanelSelectedCount, CountSelected(st));
}

void InitModel(void* panel, ViewState* st, void* table) {
    memset(st->selected, 0, sizeof(st->selected));
    int active = Get<int>(table, kOffMemberCount);
    active = std::max(0, std::min(active, kActiveCapacity));
    for (int i = 0; i < active; ++i) {
        const int slot = Get<int>(table, kOffMemberSlots + i * 4);
        if (IsValid(slot)) st->selected[slot] = true;
    }
    for (int s = 0; s < kMax; ++s) if (st->forced[s]) st->selected[s] = true;
    st->pageBase = -1;
    Put<int>(panel, kPanelSelectedCount, CountSelected(st));
}

void ClearPortraitContext(void* panel) {
    void* prev = Get<void*>(panel, kPanelCurrentPortrait);
    if (prev) Fn<IntThisFn>(kGuiButtonSetActive)(prev, 0);
    Put<void*>(panel, kPanelCurrentPortrait, nullptr);
}

void ShowPage(void* panel, int base) {
    ViewState* st = FindView(panel);
    if (!st || !st->ready) return;
    CapturePage(st);
    void* table = PartyTable();
    if (!table) return;
    st->pageBase = base;
    auto setActive = Fn<SetActiveControlFn>(kGuiPanelSetActiveControl);
    auto add = Fn<AddControlFn>(kGuiPanelAddControl);
    auto setEnabled = Fn<IntThisFn>(kGuiButtonSetEnabled);
    setActive(panel, nullptr, 0);
    ClearPortraitContext(panel);
    DetachControls(panel, st, false);
    for (int i = 0; i < kPageSlots; ++i) {
        const int slot = base + i;
        BYTE* rec = ViewRecord(st, i);
        if (AvailableOf(table, slot) != 0) SetAvailableRecord(rec, st, table, slot);
        else SetUnavailableRecord(rec, slot);
    }
    for (int i = 0; i < kPageSlots; ++i) add(panel, ViewRecord(st, i) + kRecCharacter);
    void* firstInteractive = nullptr;
    for (int i = 0; i < kPageSlots; ++i) {
        BYTE* rec = ViewRecord(st, i);
        BYTE* button = rec + kRecButton;
        const DWORD flags = Get<DWORD>(rec, kRecFlags);
        const int slot = Get<int>(rec, kRecLogicalSlot);
        const bool interactive = (flags & kFlagEnabled) != 0 && (flags & kFlagForced) == 0 && Selectable(table, slot);
        add(panel, button);
        if (!firstInteractive && interactive) firstInteractive = button;
    }
    for (int i = 0; i < kPageSlots; ++i) {
        BYTE* na = ViewRecord(st, i) + kRecNotAvailable;
        if (IsVisible(na)) add(panel, na);
    }
    BYTE* prev = PageButton(st, 0);
    BYTE* next = PageButton(st, 1);
    setEnabled(prev, base != 0);
    setEnabled(next, base != kLastPageBase);
    BYTE* done = static_cast<BYTE*>(panel) + kPanelDoneButton;
    auto moveTo = Fn<SetMoveToFn>(kGuiSetMoveToControl);
    moveTo(prev, kNavUp, firstInteractive);
    moveTo(next, kNavUp, firstInteractive);
    moveTo(done, kNavUp, firstInteractive);
    moveTo(done, kNavDown, firstInteractive);
    Put<int>(panel, kPanelSelectedCount, CountSelected(st));
    Fn<VoidThisFn>(kPartySelectionUpdateCount)(panel);
    if (!firstInteractive) firstInteractive = base == 0 ? next : prev;
    setActive(panel, firstInteractive, 1);
}

void __fastcall PrevCallback(void* self, void*, void*) { ShowPage(self, 0); }
void __fastcall NextCallback(void* self, void*, void*) { ShowPage(self, kLastPageBase); }

void DestroyView(void* panel) {
    ViewState* st = FindView(panel);
    if (!st) return;
    DetachControls(panel, st, true);
    while (st->constructedButtons > 0) {
        --st->constructedButtons;
        Fn<VoidThisFn>(kGuiButtonDtor)(PageButton(st, static_cast<int>(st->constructedButtons)));
    }
    while (st->constructedRecords > 0) {
        --st->constructedRecords;
        Fn<VoidThisFn>(kPartySelectionRecordDtor)(ViewRecord(st, static_cast<int>(st->constructedRecords)));
    }
    FreeAligned(st->pageButtons);
    FreeAligned(st->records);
    memset(st, 0, sizeof(*st));
    AttachStockControls(panel);
}

// Removes an active extra member the way the game's own party code does it.
bool RemoveExtraMember(void* table, int slot) {
    if (ActiveIndexOf(table, slot) < 0) return true;
    const int idx = ClientPartyIndex(ObjectIdOf(table, slot));
    if (idx < 0) return false;
    void* cparty = Fn<PtrThisFn>(kClientGetParty)(Client());
    void* cmember = cparty ? Fn<CharFn>(kPartyGetCharacter)(cparty, idx) : nullptr;
    if (!cmember) return false;
    const DWORD id = ObjectIdOf(table, slot);
    Fn<SetIntFn>(kClientSetInParty)(cmember, 0);
    if (void* creature = ServerCreatureOfClient(cmember)) Fn<SetInPartyFn>(kServerSetInParty)(creature, 0, 1);
    const bool removed = Fn<RemoveMemberFn>(kPartyRemoveMember)(table, slot) != 0;
    if (removed) {
        // A dropped extra has no home spot for the game's scripts to send it to, so it would stay standing in the area. Keep its current state
        // in the saved record (AVAILNPC<slot>), then remove the creature; picking it again rebuilds it from that record.
        if (void* c = ServerCreature(id)) SaveToResource(slot, c);
        DestroyNpcObject(table, slot, 1);
    }
    return removed;
}

bool AddExtraMember(void* table, int slot) {
    int count = Get<int>(table, kOffMemberCount);
    if (count < 0 || count >= kActiveCapacity) return false;
    void* player = PlayerCreature();
    if (!player) return false;
    BYTE* pb = static_cast<BYTE*>(player);
    const DWORD id = Fn<SpawnNpcFn>(kPartySpawnNpc)(table, slot, 1, pb + kObjPosition, pb + kObjOrientation, 1);
    if (id == kNoObject || Fn<AddMemberFn>(kPartyAddMember)(table, slot, id) == 0) return false;
    void* creature = ServerCreature(id);
    if (!creature) return false;
    Fn<SetIntFn>(kObjectClearAllActions)(creature, 1);
    if (void* path = Get<void*>(creature, kCreaturePathfind)) Fn<VoidThisFn>(kPathfindResetWaypointData)(path);
    Fn<SetInPartyFn>(kServerSetInParty)(creature, 1, 1);
    void** vt = *reinterpret_cast<void***>(creature);
    if (vt && vt[0x70 / 4]) reinterpret_cast<VoidThisFn>(vt[0x70 / 4])(creature);
    if (Fn<VisibleGetFn>(kCreatureGetVisibleListElement)(player, id) == 0) Fn<VisibleAddFn>(kCreatureAddToVisibleList)(player, id, 1, 1, 0, 0);
    if (void* cparty = Fn<PtrThisFn>(kClientGetParty)(Client())) {
        count = Get<int>(table, kOffMemberCount);
        if (void* cmember = Fn<CharFn>(kPartyGetCharacter)(cparty, count)) Fn<SetIntFn>(kClientSetInParty)(cmember, 1);
    }
    return true;
}

// copies the choice made across the pages onto the nine stock records the game's own accept code reads
void StageStockRecords(void* panel, ViewState* st, void* table) {
    auto setSelected = Fn<SetSelectedFn>(kPartySelectionButtonSetSelected);
    for (int slot = 0; slot < kStock; ++slot) {
        BYTE* rec = StockRecord(panel, slot);
        const bool avail = AvailableOf(table, slot) != 0;
        const bool selected = avail && (st->selected[slot] || st->forced[slot]);
        const int active = ActiveIndexOf(table, slot);
        const int clientIdx = active >= 0 ? ClientPartyIndex(ObjectIdOf(table, slot)) : -1;
        DWORD flags = kFlagHasObject;
        if (avail) flags |= kFlagEnabled;
        if (st->forced[slot]) flags |= kFlagForced;
        Put<DWORD>(rec, kRecFlags, flags);
        Put<int>(rec, kRecObjectIndex, clientIdx);
        Put<int>(rec, kRecLogicalSlot, slot);
        setSelected(rec + kRecButton, selected ? 1 : 0);
    }
}

// in "decision" mode the game only counts enabled / forced / selected records; give it the counts over all 32 slots
void StageDecisionRecords(void* panel, ViewState* st, void* table) {
    int enabled = 0, forced = 0, selected = 0;
    for (int s = 0; s < kMax; ++s) {
        const bool avail = AvailableOf(table, s) != 0;
        enabled += avail;
        forced += avail && st->forced[s];
        selected += avail && (st->selected[s] || st->forced[s]);
    }
    auto setSelected = Fn<SetSelectedFn>(kPartySelectionButtonSetSelected);
    for (int i = 0; i < kStock; ++i) {
        BYTE* rec = StockRecord(panel, i);
        DWORD flags = kFlagHasObject;
        if (i < enabled) flags |= kFlagEnabled;
        if (i < forced) flags |= kFlagForced;
        Put<DWORD>(rec, kRecFlags, flags);
        setSelected(rec + kRecButton, i < selected ? 1 : 0);
    }
}

void PrepareAcceptModel(void* panel) {
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    CapturePage(st);
    bool removed = false;
    for (int s = kStock; s < kMax; ++s) {
        if (ActiveIndexOf(table, s) < 0 || st->selected[s] || st->forced[s]) continue;
        removed |= RemoveExtraMember(table, s);
    }
    if (removed) {
        if (void* cp = Fn<PtrThisFn>(kClientGetParty)(Client())) Fn<VoidThisFn>(kPartyRecalculateFollowPoint)(cp);
    }
    StageStockRecords(panel, st, table);
}

void FinishAcceptModel(void* panel) {
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    for (int s = kStock; s < kMax; ++s) {
        if (!(st->selected[s] || st->forced[s]) || AvailableOf(table, s) == 0 || ActiveIndexOf(table, s) >= 0) continue;
        if (!AddExtraMember(table, s)) st->selected[s] = false;
    }
    memset(st->forced, 0, sizeof(st->forced));
}

// ---- handlers for the screen's patch sites (names as in the hook table)

void __cdecl FinishPartySelectionLayout(void* panel) {       // replaces the call that ends layout loading
    CreateView(panel);
    Fn<VoidThisFn>(kGuiPanelStopLoadFromLayout)(panel);
}
void __cdecl PreparePartySelectionDestructor(void* panel) { DestroyView(panel); }
void __cdecl PreparePartySelectionOnPanelAdded(void* panel) {
    if (ViewState* st = FindView(panel)) st->pageBase = -1;
    AttachStockControls(panel);
}
void __cdecl FinishPartySelectionOnPanelAdded(void* panel) {
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    InitModel(panel, st, table);
    ShowPage(panel, 0);
}
void __cdecl PreparePartySelectionOnPanelRemoved(void* panel) {
    if (ViewState* st = FindView(panel)) CapturePage(st);
    AttachStockControls(panel);
}
void __cdecl FinishPartySelectionOnPanelRemoved(void* panel) {
    ViewState* st = FindView(panel);
    if (!st) return;
    st->pageBase = -1;
    memset(st->selected, 0, sizeof(st->selected));
    memset(st->forced, 0, sizeof(st->forced));
    Put<DWORD>(panel, kPanelForcedMode, 0u);
}
void __cdecl PrepareSetForcedNPC32(void* panel, const int* first, const int* second) {
    ViewState* st = FindView(panel);
    if (!st) return;
    const int slots[2] = {*first, *second};
    bool any = false;
    for (int s : slots) {
        if (!IsValid(s)) continue;
        st->forced[s] = true;
        st->selected[s] = true;
        any = true;
    }
    if (any) Put<DWORD>(panel, kPanelForcedMode, 1u);
}
void __cdecl PreparePartySelectionOnDone(void* panel, void* const* control) {
    if (!control || !*control || Get<void*>(*control, kControlEventOwner) == nullptr) return;
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    CapturePage(st);
    if (Get<int>(panel, kPanelMode) != 0) StageDecisionRecords(panel, st, table);
}
void __cdecl PreparePartySelectionAccept(void* panel) { PrepareAcceptModel(panel); }
void __cdecl FinishPartySelectionAccept(void* panel) { FinishAcceptModel(panel); }

// the game removed an object from the party: shift the stored object indices of both the stock and our records down
void __cdecl AdjustPartySelectionAfterObjectRemoval(void* panel, const int* removedIndex) {
    for (int i = 0; i < kStock; ++i) {
        BYTE* rec = StockRecord(panel, i);
        const int idx = Get<int>(rec, kRecObjectIndex);
        if (idx > *removedIndex) Put<int>(rec, kRecObjectIndex, idx - 1);
    }
    ViewState* st = FindView(panel);
    if (!st || !st->ready) return;
    for (int i = 0; i < kPageSlots; ++i) {
        BYTE* rec = ViewRecord(st, i);
        const int idx = Get<int>(rec, kRecObjectIndex);
        if (idx > *removedIndex) Put<int>(rec, kRecObjectIndex, idx - 1);
    }
}
void __cdecl ClearPartySelectionForcedFlags(void* panel) {
    if (ViewState* st = FindView(panel)) {
        memset(st->forced, 0, sizeof(st->forced));
        for (int i = 0; i < kPageSlots; ++i) {
            BYTE* rec = ViewRecord(st, i);
            Put<DWORD>(rec, kRecFlags, Get<DWORD>(rec, kRecFlags) & ~kFlagForced);
        }
    }
    Put<DWORD>(panel, kPanelForcedMode, 0u);
}
