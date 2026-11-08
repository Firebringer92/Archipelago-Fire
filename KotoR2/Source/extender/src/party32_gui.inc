// Included by party32.cpp inside its anonymous namespace (it uses that file's helpers). Not a standalone source file.
//
// Paged party selection screen. The stock screen has 12 portrait records at panel+0x84 (stride 0x478). We keep 16 records of our own that the
// new layout file (partyselect_p.gui: BTN_NPC0-15, LBL_CHAR0-15, LBL_NA0-15, BTN_PAGE_PREV/NEXT) binds by tag, and show slots 0-15 or 16-31 on them.
// Structure follows the Patch Manager mod PartyRosterLimit32K2 (MIT, by Vriff).

constexpr int kPageSlots = 16;
constexpr int kLastPageBase = kMaxSlots - kPageSlots;
constexpr int kRecordStride = 0x478;
constexpr int kPanelRecordBase = 0x84;
constexpr int kButtonObjectSize = 0x1D0;
constexpr int kStateCapacity = 2;

constexpr int kRecButton = 0x04;
constexpr int kRecBackPointer = 0x60;
constexpr int kRecSelected = 0x1D4;
constexpr int kRecInitParams = 0x100;
constexpr int kRecDefaultColor = 0x114;
constexpr int kRecNotAvailable = 0x1D8;
constexpr int kRecCharacter = 0x320;
constexpr int kRecTextureParams = 0x394;
constexpr int kRecAlpha = 0x3A4;
constexpr int kRecFlags = 0x468;
constexpr int kRecObjectIndex = 0x46C;
constexpr int kRecLogicalSlot = 0x470;
constexpr int kRecAux = 0x474;
constexpr int kRecControlOffsets[3] = {kRecCharacter, kRecButton, kRecNotAvailable};
constexpr DWORD kFlagEnabled = 0x1, kFlagHasObject = 0x2, kFlagForced = 0x4;
constexpr int kPanelSelectedCount = 0x6C;
constexpr int kPanelForcedMode = 0x70;
constexpr int kPanelMode = 0x74;
constexpr int kPanelDoneButton = 0x376C;
constexpr int kPanelCurrentPortrait = 0x48F8;
constexpr int kPanelControlArray = 0x24;
constexpr int kPanelControlCount = 0x28;
constexpr int kControlFlags = 0x48;
constexpr DWORD kControlVisible = 0x2, kControlMouseIgnore = 0x20;
constexpr int kEventPrimary = 0x27;
constexpr int kNavUp = 0;
constexpr size_t kButtonSetActiveVtable = 0x40 / 4;

struct ViewState {
    void* owner;
    BYTE* records;
    BYTE* pageButtons;
    unsigned constructedRecords;
    unsigned constructedButtons;
    int pageBase;
    bool ready;
    bool selected[kMaxSlots];
    bool forced[kMaxSlots];
};
ViewState gViews[kStateCapacity] = {};

using SetSelectedFn = void(__thiscall*)(void*, int);
using InitControlFn = void(__thiscall*)(void*, void*, const void*, int, int);
using AddControlFn = void(__thiscall*)(void*, void*);
using SetActiveControlFn = void(__thiscall*)(void*, void*, int);
using DelIndexFn = void(__thiscall*)(void*, int);
using AddEventFn = void(__thiscall*)(void*, int, void*, void*);
using IntThisFn = void(__thiscall*)(void*, int);
using SetMoveToFn = void(__thiscall*)(void*, int, void*);
using PtrThisFn = void*(__thiscall*)(void*);
using FillImageFn = void(__thiscall*)(void*, const void*, int);
using PulsingFn = void(__thiscall*)(void*, int, int, int);
using PortraitFn = void*(__thiscall*)(void*, void*);
struct ResRef16 { char s[16]; };

BYTE* StockRecord(void* panel, int i) { return static_cast<BYTE*>(panel) + kPanelRecordBase + i * kRecordStride; }

void* AllocAligned(size_t size, size_t align) {
    const size_t total = size + align - 1 + sizeof(void*);
    void* raw = std::malloc(total);
    if (!raw) return nullptr;
    const uintptr_t start = reinterpret_cast<uintptr_t>(raw) + sizeof(void*);
    const uintptr_t a = (start + align - 1) & ~(align - 1);
    reinterpret_cast<void**>(a)[-1] = raw;
    return reinterpret_cast<void*>(a);
}
void FreeAligned(void* m) { if (m) std::free(reinterpret_cast<void**>(m)[-1]); }

ViewState* FindView(void* panel) {
    for (ViewState& v : gViews) if (v.owner == panel) return &v;
    return nullptr;
}
ViewState* ReserveView(void* panel) {
    if (ViewState* v = FindView(panel)) return v;
    for (ViewState& v : gViews) {
        if (!v.owner) { std::memset(&v, 0, sizeof(v)); v.owner = panel; v.pageBase = -1; return &v; }
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
void BindControl(void* panel, void* dest, const char* tag) {
    CExoStr s;
    Fn<StrCtorFn>(kCExoStringCtorCStr)(&s, tag);
    Fn<InitControlFn>(kGuiPanelInitControl)(panel, dest, &s, 1, 1);
    Fn<VoidThisFn>(kCExoStringDtor)(&s);
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
    Put<int>(rec, kRecAux, 0);
    Put<float>(rec, kRecAlpha, 1.0f);
    BYTE* button = rec + kRecButton;
    BYTE* na = rec + kRecNotAvailable;
    BYTE* ch = rec + kRecCharacter;
    SetVisible(button, true);
    SetHitTest(button, false);
    Fn<IntThisFn>(kGuiButtonSetEnabled)(button, 0);
    SetVisible(na, slot < kStockSlots);
    SetHitTest(na, false);
    SetVisible(ch, false);
    SetHitTest(ch, false);
}

bool SetAvailableRecord(BYTE* rec, ViewState* st, void* table, int slot) {
    const DWORD id = ResolveOrCreate(table, slot);
    void* creature = ServerCreature(id);
    if (!creature) { SetUnavailableRecord(rec, slot); return false; }
    ResRef16 portrait = {};
    Fn<PortraitFn>(kObjectGetPortrait)(creature, &portrait);
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
    Put<int>(rec, kRecAux, 0);
    Put<float>(rec, kRecAlpha, 1.0f);
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
    std::memset(rec, 0, kRecordStride);
    Fn<PtrThisFn>(kPartySelectionRecordCtor)(rec);
    ++st->constructedRecords;
    char tag[32];
    std::snprintf(tag, sizeof(tag), "LBL_NA%d", i);   BindControl(panel, rec + kRecNotAvailable, tag);
    std::snprintf(tag, sizeof(tag), "LBL_CHAR%d", i); BindControl(panel, rec + kRecCharacter, tag);
    std::snprintf(tag, sizeof(tag), "BTN_NPC%d", i);  BindControl(panel, rec + kRecButton, tag);
    auto addEvent = Fn<AddEventFn>(kGuiControlAddEvent);
    BYTE* button = rec + kRecButton;
    addEvent(button, kEventPrimary, panel, reinterpret_cast<void*>(kPartySelectionOnToggled));
    addEvent(button, 0, panel, reinterpret_cast<void*>(kPartySelectionOnEnter));
    addEvent(button, 1, panel, reinterpret_cast<void*>(kPartySelectionOnExit));
    Put<void*>(rec, kRecBackPointer, rec);
    std::memcpy(rec + kRecDefaultColor, StockRecord(panel, 0) + kRecDefaultColor, sizeof(float) * 3);
    Fn<PulsingFn>(kGuiBorderSetPulsingAlpha)(rec + kRecInitParams, 1, 1, 0);
    Put<DWORD>(rec, kRecFlags, 0u);
    Put<int>(rec, kRecLogicalSlot, i);
    Put<int>(rec, kRecAux, 0);
    SetUnavailableRecord(rec, i);
}

void __fastcall PrevCallback(void* self, void*, void*);
void __fastcall NextCallback(void* self, void*, void*);

void InitPageButton(void* panel, ViewState* st, int index, const char* tag, void* callback) {
    BYTE* b = PageButton(st, index);
    std::memset(b, 0, kButtonObjectSize);
    Fn<PtrThisFn>(kGuiButtonCtor)(b);
    ++st->constructedButtons;
    BindControl(panel, b, tag);
    Fn<AddEventFn>(kGuiControlAddEvent)(b, kEventPrimary, panel, callback);
}

bool CreateView(void* panel) {
    ViewState* st = ReserveView(panel);
    if (!st || st->ready) return st && st->ready;
    st->records = static_cast<BYTE*>(AllocAligned(kPageSlots * kRecordStride, 16));
    st->pageButtons = static_cast<BYTE*>(AllocAligned(2 * kButtonObjectSize, 16));
    if (!st->records || !st->pageButtons) {
        FreeAligned(st->records);
        FreeAligned(st->pageButtons);
        std::memset(st, 0, sizeof(*st));
        return false;
    }
    for (int i = 0; i < kPageSlots; ++i) InitRecord(panel, st, i);
    InitPageButton(panel, st, 0, "BTN_PAGE_PREV", reinterpret_cast<void*>(&PrevCallback));
    InitPageButton(panel, st, 1, "BTN_PAGE_NEXT", reinterpret_cast<void*>(&NextCallback));
    st->ready = true;
    return true;
}

void DetachControl(void* panel, void* control) {
    void** controls = Get<void**>(panel, kPanelControlArray);
    const int count = Get<int>(panel, kPanelControlCount);
    for (int i = 0; i < count; ++i) {
        if (controls[i] == control) {
            Fn<DelIndexFn>(kExoArrayListPointerDelIndex)(static_cast<BYTE*>(panel) + kPanelControlArray, i);
            return;
        }
    }
}

void DetachControls(void* panel, ViewState* st, bool pageButtons) {
    for (int i = 0; i < kStockSlots; ++i) {
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
    for (int off : kRecControlOffsets) for (int i = 0; i < kStockSlots; ++i) add(panel, StockRecord(panel, i) + off);
}

int CountSelected(const ViewState* st) {
    int n = 0;
    for (int s = 0; s < kMaxSlots; ++s) n += st->selected[s] || st->forced[s];
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
    std::memset(st->selected, 0, sizeof(st->selected));
    int active = Get<int>(table, kOffMemberCount);
    active = std::max(0, std::min(active, kActiveCapacity));
    for (int i = 0; i < active; ++i) {
        const int slot = Get<int>(table, kOffMemberSlots + i * 4);
        if (IsValid(slot)) st->selected[slot] = true;
    }
    for (int s = 0; s < kMaxSlots; ++s) if (st->forced[s]) st->selected[s] = true;
    st->pageBase = -1;
    Put<int>(panel, kPanelSelectedCount, CountSelected(st));
}

void ClearPortraitContext(void* panel) {
    BYTE* prev = Get<BYTE*>(panel, kPanelCurrentPortrait);
    if (prev) {
        BYTE* button = prev + kRecButton;
        void** vt = *reinterpret_cast<void***>(button);
        reinterpret_cast<IntThisFn>(vt[kButtonSetActiveVtable])(button, 0);
    }
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
        if ((Get<DWORD>(na, kControlFlags) & kControlVisible) != 0) add(panel, na);
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
    std::memset(st, 0, sizeof(*st));
    AttachStockControls(panel);
}

// copies the choice made across the pages onto the 12 stock records the game's own accept code reads
void StageStockRecords(void* panel, ViewState* st, void* table) {
    auto setSelected = Fn<SetSelectedFn>(kPartySelectionButtonSetSelected);
    for (int slot = 0; slot < kStockSlots; ++slot) {
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
    for (int s = 0; s < kMaxSlots; ++s) {
        const bool avail = AvailableOf(table, s) != 0;
        enabled += avail;
        forced += avail && st->forced[s];
        selected += avail && (st->selected[s] || st->forced[s]);
    }
    auto setSelected = Fn<SetSelectedFn>(kPartySelectionButtonSetSelected);
    for (int i = 0; i < kStockSlots; ++i) {
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
    for (int s = kStockSlots; s < kMaxSlots; ++s) {
        if (ActiveIndexOf(table, s) < 0 || st->selected[s] || st->forced[s]) continue;
        removed |= RemoveExtraMember(table, s);
    }
    if (removed) {
        if (void* cp = Fn<GetPartyFn>(kClientGetParty)(Client())) Fn<VoidThisFn>(kPartyRecalculateFollowPoint)(cp);
    }
    StageStockRecords(panel, st, table);
}

void FinishAcceptModel(void* panel) {
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    for (int s = kStockSlots; s < kMaxSlots; ++s) {
        if (!(st->selected[s] || st->forced[s]) || AvailableOf(table, s) == 0 || ActiveIndexOf(table, s) >= 0) continue;
        if (!AddExtraMember(table, s)) st->selected[s] = false;
    }
    std::memset(st->forced, 0, sizeof(st->forced));
}

// ---- handlers for the screen's patch sites (hook numbers in party32_hooks_generated.h)

void __cdecl H_FinishLayout(void* panel) {  // hook 31: replaces the call that ends layout loading
    CreateView(panel);
    Fn<VoidThisFn>(kGuiPanelStopLoadFromLayout)(panel);
}
void __cdecl H_PanelDtor(void* panel) { DestroyView(panel); }  // hook 32
void __cdecl H_PanelAdded(void* panel) {                        // hook 66
    if (ViewState* st = FindView(panel)) st->pageBase = -1;
    AttachStockControls(panel);
}
void __cdecl H_PanelAddedDone(void* frame) {                    // hook 67
    void* panel = *reinterpret_cast<void**>(static_cast<BYTE*>(frame) - 0xDC);
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    InitModel(panel, st, table);
    ShowPage(panel, 0);
}
void __cdecl H_PanelRemoved(void* panel) {                      // hook 69
    if (ViewState* st = FindView(panel)) CapturePage(st);
    AttachStockControls(panel);
}
void __cdecl H_PanelRemovedDone(void* frame) {                  // hook 70
    void* panel = *reinterpret_cast<void**>(static_cast<BYTE*>(frame) - 0x24);
    ViewState* st = FindView(panel);
    if (!st) return;
    st->pageBase = -1;
    std::memset(st->selected, 0, sizeof(st->selected));
    std::memset(st->forced, 0, sizeof(st->forced));
    Put<DWORD>(panel, kPanelForcedMode, 0u);
}
void __cdecl H_SetForced(void* panel, const int* first, const int* second) {  // hook 71
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
void __cdecl H_PanelDone(void* panel) {                         // hook 72
    ViewState* st = FindView(panel);
    void* table = PartyTable();
    if (!st || !st->ready || !table) return;
    CapturePage(st);
    if (Get<int>(panel, kPanelMode) != 0) StageDecisionRecords(panel, st, table);
}
void __cdecl H_PanelAccept(void* panel) { PrepareAcceptModel(panel); }  // hook 73
void __cdecl H_PanelAcceptDone(void* frame) {                           // hook 74
    FinishAcceptModel(*reinterpret_cast<void**>(static_cast<BYTE*>(frame) - 0x194));
}
