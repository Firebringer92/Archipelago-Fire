// Randomised dialogue replies (0.2.1).
//
// When the player picks a reply in a conversation, the game is made to run a different one of the replies that were on screen. Only the replies the
// game itself offered are ever chosen (the server already dropped the ones whose conditions failed), so every swap lands on a valid reply.
//
// Two detours, both in the Steam swkotor.exe 1.03 image (addresses verified in research/patchmanager_k1/SPIKE_RESULTS.md):
//   CSWSObject::StartDialog (0x004CF490)        remembers the name of the conversation that is starting.
//   CGuiInGame::SetDialogSelection (0x0062ADA0) every click on a reply ends here as (position, reply count, flag); the position is replaced.
//
// The feature is off unless the file "ap_dialogrand.txt" exists beside the game executable and its first line is 1/on/true. The file is read again when a
// conversation starts, so it can be switched without restarting the game. Further lines "exclude=<resref>" or "exclude=<prefix>*" add conversations that are
// never randomised. Built in: every "ap_*" conversation (the AP menus) and the two conversations that hold the final choice about Bastila.

#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "MinHook.h"
#include "log.h"

namespace {

constexpr uintptr_t kStartDialogVa = 0x004CF490u;
constexpr uintptr_t kSetDialogSelectionVa = 0x0062ADA0u;

// Expected original bytes (verified against the decrypted image).
constexpr uint8_t kSetSelBytes[] = {0x8B, 0x44, 0x24, 0x04, 0x8B, 0x54, 0x24, 0x08, 0x89, 0x81, 0xC8, 0x00, 0x00, 0x00};
constexpr uint8_t kStartDialogBytes[] = {0x6A, 0xFF, 0x68, 0x9E, 0x9D, 0x71, 0x00, 0x64, 0xA1, 0x00, 0x00, 0x00, 0x00};

// Conversations that are never randomised: AP menus (prefix), the Bastila choice on the Unknown World, and the code recitations (Zhar's Jedi Code on Dantooine, Uthar Wynn's Sith Code on Korriban), and the Dantooine trial computer terminals (dan15_comp*).
const char* const kBuiltinExcluded[] = {"ap_*", "unk44_evilbast", "unk44_evilbast2", "dan13_zhar", "kor35_utharwynn", "dan15_comp*"};

typedef int(__thiscall* StartDialogFn)(void* self, int a1, void* name, int a3);
typedef void(__thiscall* SetSelFn)(void* self, int sel, int count, int flag);
typedef void*(__thiscall* GetDialogResrefFn)(void* self, void* out);

StartDialogFn gOrigStart = nullptr;
SetSelFn gOrigSetSel = nullptr;

char gConversation[20] = {0};   // lower-case name of the conversation that started last
volatile LONG gEnabled = 0;
char gExtra[64][20];              // extra exclusions from the config file
int gExtraCount = 0;
uint32_t gRng = 0x9E3779B9u;
volatile LONG gSwaps = 0;

uint32_t Next() {
    gRng ^= gRng << 13;
    gRng ^= gRng >> 17;
    gRng ^= gRng << 5;
    return gRng;
}

bool Matches(const char* pattern, const char* name) {
    const size_t n = strlen(pattern);
    if (n && pattern[n - 1] == '*') return strncmp(name, pattern, n - 1) == 0;
    return strcmp(name, pattern) == 0;
}

bool IsExcluded(const char* name) {
    for (const char* p : kBuiltinExcluded) if (Matches(p, name)) return true;
    for (int i = 0; i < gExtraCount; ++i) if (Matches(gExtra[i], name)) return true;
    return false;
}

void ReloadConfig() {
    char path[MAX_PATH];
    DWORD n = GetModuleFileNameA(nullptr, path, MAX_PATH);
    if (!n || n >= MAX_PATH) return;
    char* slash = strrchr(path, '\\');
    if (!slash) return;
    strcpy_s(slash + 1, static_cast<size_t>(MAX_PATH - (slash + 1 - path)), "ap_dialogrand.txt");
    FILE* f = nullptr;
    if (fopen_s(&f, path, "r") != 0 || !f) {
        InterlockedExchange(&gEnabled, 0);
        gExtraCount = 0;
        return;
    }
    char line[96];
    bool first = true;
    int extra = 0;
    LONG enabled = 0;
    while (fgets(line, sizeof(line), f)) {
        char* e = line + strlen(line);
        while (e > line && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ')) *--e = 0;
        if (first) {
            enabled = (!_stricmp(line, "1") || !_stricmp(line, "on") || !_stricmp(line, "true")) ? 1 : 0;
            first = false;
        } else if (!_strnicmp(line, "exclude=", 8) && extra < 64) {
            strncpy_s(gExtra[extra], sizeof(gExtra[extra]), line + 8, _TRUNCATE);
            _strlwr_s(gExtra[extra], sizeof(gExtra[extra]));
            ++extra;
        }
    }
    fclose(f);
    gExtraCount = extra;
    if (InterlockedExchange(&gEnabled, enabled) != enabled)
        Log("dialogrand: %s (%d extra exclusion(s))", enabled ? "ENABLED" : "disabled", extra);
}

// Copies the conversation's name into gConversation (lower case). Memory reads are guarded: a bad pointer leaves the name empty.
void RememberConversation(void* self, void* name) {
    char out[17] = {0};
    __try {
        const char* text = name ? *reinterpret_cast<const char**>(name) : nullptr;
        const int len = name ? *reinterpret_cast<const int*>(static_cast<const char*>(name) + 4) : 0;
        if (text && len > 0) {
            const int m = len < 16 ? len : 16;
            memcpy(out, text, static_cast<size_t>(m));
        } else if (self) {
            // No name in the call: the speaker's own conversation (virtual GetDialogResref, slot 0x80).
            void** vt = *reinterpret_cast<void***>(self);
            GetDialogResrefFn get = reinterpret_cast<GetDialogResrefFn>(vt[0x80 / 4]);
            char res[16] = {0};
            get(self, res);
            memcpy(out, res, 16);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        out[0] = 0;
    }
    out[16] = 0;
    _strlwr_s(out, sizeof(out));
    strcpy_s(gConversation, sizeof(gConversation), out);
}

int __fastcall StartDialogDetour(void* self, void*, int a1, void* name, int a3) {
    ReloadConfig();
    RememberConversation(self, name);
    return gOrigStart(self, a1, name, a3);
}

void __fastcall SetSelDetour(void* self, void*, int sel, int count, int flag) {
    if (gEnabled && sel >= 0 && count >= 2 && count <= 20 && !IsExcluded(gConversation)) {
        int pick = static_cast<int>(Next() % static_cast<uint32_t>(count - 1));
        if (pick >= sel) ++pick;
        const LONG k = InterlockedIncrement(&gSwaps);
        Log("dialogrand: #%ld conversation '%s': reply %d of %d replaced by %d", k, gConversation, sel, count, pick);
        sel = pick;
    }
    gOrigSetSel(self, sel, count, flag);
}

bool BytesMatch(uintptr_t va, const uint8_t* expected, size_t n) {
    return memcmp(reinterpret_cast<const void*>(va), expected, n) == 0;
}

}  // namespace

// Called once from the worker thread, after the code is decrypted and the dispatcher hook is in. Never throws; leaves the game untouched on any mismatch.
bool DialogRandInstall() {
    if (!BytesMatch(kSetDialogSelectionVa, kSetSelBytes, sizeof(kSetSelBytes)) ||
        !BytesMatch(kStartDialogVa, kStartDialogBytes, sizeof(kStartDialogBytes))) {
        Log("dialogrand: NOT installed: the code at the hook sites is not the expected original");
        return false;
    }
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    gRng ^= static_cast<uint32_t>(t.LowPart) ^ GetTickCount();
    if (!gRng) gRng = 0x9E3779B9u;
    MH_Initialize();   // already initialised by the dispatcher hook: the status is irrelevant
    if (MH_CreateHook(reinterpret_cast<LPVOID>(kStartDialogVa), reinterpret_cast<LPVOID>(&StartDialogDetour), reinterpret_cast<LPVOID*>(&gOrigStart)) != MH_OK ||
        MH_CreateHook(reinterpret_cast<LPVOID>(kSetDialogSelectionVa), reinterpret_cast<LPVOID>(&SetSelDetour), reinterpret_cast<LPVOID*>(&gOrigSetSel)) != MH_OK) {
        Log("dialogrand: NOT installed: MH_CreateHook failed");
        return false;
    }
    if (MH_EnableHook(reinterpret_cast<LPVOID>(kStartDialogVa)) != MH_OK || MH_EnableHook(reinterpret_cast<LPVOID>(kSetDialogSelectionVa)) != MH_OK) {
        Log("dialogrand: NOT installed: MH_EnableHook failed");
        return false;
    }
    ReloadConfig();
    Log("dialogrand: installed (%s)", gEnabled ? "enabled" : "off: ap_dialogrand.txt is missing or its first line is not 1");
    return true;
}
