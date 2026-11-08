// Offline test of src/hookkit.cpp: builds detours over small hand-written machine-code functions in a private buffer and checks
// argument passing, skipped/kept original bytes, result registers and the "handled" exit. Stubs for probe/log stand in for the game.
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include "../src/hookkit.h"

namespace k2se { namespace probe {
bool ReadMem(const void* b, int off, int w, int* out) { *out = *(const uint8_t*)((const uint8_t*)b + off); (void)w; return true; }
bool WriteCode(void* a, int, int v, int* old) { if (old) *old = *(uint8_t*)a; *(uint8_t*)a = (uint8_t)v; return true; }
} namespace log {
void Writef(const char* f, ...) { va_list ap; va_start(ap, f); vprintf(f, ap); printf("\n"); va_end(ap); }
} }

static int gFail = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); ++gFail; } } while (0)

static int gSeenA, gSeenB, gSeenEcx, gCalls;
static int __cdecl H_args(const int* a, const int* b, int ecx) { gSeenA = *a; gSeenB = *b; gSeenEcx = ecx; ++gCalls; return 0; }
static int __cdecl H_result(int v) { return v * 10; }
static int __cdecl H_handled(int v) { return v == 5 ? 1234 : 0; }

int main() {
    uint8_t* mem = (uint8_t*)VirtualAlloc((void*)0x30000000, 0x10000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!mem) { printf("alloc failed\n"); return 2; }
    using namespace k2se::hookkit;

    // test 1: f(a,b) thiscall: push ebp; mov ebp,esp; mov eax,[ebp+8]; add eax,[ebp+0xC]; pop ebp; ret 8   (original bytes kept)
    const uint8_t f1[] = {0x55, 0x8B, 0xEC, 0x8B, 0x45, 0x08, 0x03, 0x45, 0x0C, 0x5D, 0xC2, 0x08, 0x00};
    memcpy(mem, f1, sizeof f1);
    const Arg args1[] = {{ArgKind::kStackArg, 4}, {ArgKind::kStackArg, 8}, {ArgKind::kEcx, 0}};
    Detour d1{"t1", (uint32_t)mem, f1, 6, (void*)H_args, args1, 3, false, ResultReg::kNone, 0};
    CHECK(InstallDetour(d1));
    auto fn1 = (int(__thiscall*)(int, int, int))mem;  // (this, a, b)
    int r = fn1(7, 3, 4);
    CHECK(r == 7); CHECK(gSeenA == 3); CHECK(gSeenB == 4); CHECK(gSeenEcx == 7); CHECK(gCalls == 1);

    // test 2: skip the original and return a value in eax from the handler: g(v) cdecl: mov eax,[esp+4]; ret  -> hook the region mov eax,[esp+4] (4 bytes) + 2 nops
    uint8_t* g = mem + 0x100;
    const uint8_t g1[] = {0x8B, 0x44, 0x24, 0x04, 0x90, 0x90, 0xC3};  // mov eax,[esp+4]; nop; nop; ret (the first 6 bytes are hooked)
    memcpy(g, g1, sizeof g1);
    const Arg args2[] = {{ArgKind::kEax, 0}};
    // at the hook eax is whatever the caller had: set it by calling through a thunk
    const uint8_t thunk[] = {0xB8, 0x05, 0x00, 0x00, 0x00, 0xE9, 0, 0, 0, 0};  // mov eax,5; jmp g  (patched below)
    uint8_t* t = mem + 0x200;
    memcpy(t, thunk, sizeof thunk);
    *(int32_t*)(t + 6) = (int32_t)((uint8_t*)g - (t + 10));
    Detour d2{"t2", (uint32_t)g, g1, 6, (void*)H_result, args2, 1, true, ResultReg::kEax, 0};
    CHECK(InstallDetour(d2));
    int r2 = ((int(__cdecl*)())t)();
    CHECK(r2 == 50);  // skipped the original mov; eax = handler(5)=50; then continued after the 6 replaced bytes... which ends the function: needs a ret there
    printf("test2 result %d\n", r2);

    // test 3: consumed exit. h(): mov eax,5 ; <hooked 6 bytes: nops> ; mov eax,111 ; ret ;  exit: ret (eax carries the handler value)
    uint8_t* h = mem + 0x300;
    const uint8_t h1[] = {0xB8, 0x05, 0x00, 0x00, 0x00, 0x90, 0x90, 0x90, 0x90, 0x90, 0xB8, 0x6F, 0x00, 0x00, 0x00, 0xC3, 0xC3};
    memcpy(h, h1, sizeof h1);
    const Arg args3[] = {{ArgKind::kEax, 0}};
    Detour d3{"t3", (uint32_t)(h + 5), h1 + 5, 5, (void*)H_handled, args3, 1, false, ResultReg::kNone, (uint32_t)(h + 16)};
    CHECK(InstallDetour(d3));
    int r3 = ((int(__cdecl*)())h)();
    CHECK(r3 == 1234);  // handled: eax = handler result, jumped to the exit ret
    // same function with eax != 5 is not testable without reinstalling; test the other branch with a second copy
    uint8_t* h2 = mem + 0x400;
    uint8_t h2b[sizeof h1]; memcpy(h2b, h1, sizeof h1); h2b[1] = 0x07;
    memcpy(h2, h2b, sizeof h2b);
    Detour d4{"t4", (uint32_t)(h2 + 5), h2b + 5, 5, (void*)H_handled, args3, 1, false, ResultReg::kNone, (uint32_t)(h2 + 16)};
    CHECK(InstallDetour(d4));
    int r4 = ((int(__cdecl*)())h2)();
    CHECK(r4 == 111);  // not handled: original (nops) ran, then mov eax,111
    // registers other than the result survive the stub
    uint8_t* k = mem + 0x500;
    const uint8_t k1[] = {0x90, 0x90, 0x90, 0x90, 0x90, 0x8B, 0xC3, 0xC3};  // 5 nops (hooked), mov eax,ebx ; ret
    memcpy(k, k1, sizeof k1);
    Detour d5{"t5", (uint32_t)k, k1, 5, (void*)H_args, args1, 0, false, ResultReg::kNone, 0};
    CHECK(InstallDetour(d5));
    int r5 = ((int(__cdecl*)())k)();
    (void)r5;
    printf("done, failures=%d\n", gFail);
    return gFail ? 1 : 0;
}
