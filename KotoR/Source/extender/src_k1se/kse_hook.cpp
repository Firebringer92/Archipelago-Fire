#include <cstdio>
#include "hook.h"
#include "offsets.h"
#include "version.h"
#include "log.h"
#include "MinHook.h"

// -----------------------------------------------------------------------------
// The dispatcher hook, in build-selectable stages.
//
// Hooking approach: MinHook -- a tested inline-hook library, chosen over a
// hand-rolled trampoline so the prologue relocation is correct.
//
//   STAGE 1  pure pass-through (no observable effect).
//   STAGE 2  pass-through + a call counter.
//   STAGE 4  pass-through except routine 587, which KSE answers (returns a value).
//   STAGE 5  STAGE 4 + routine 618, which READS an int argument (round-trip proof).
//   STAGE 6  integer-utility suite (bitwise/math) via a two-host opcode dispatcher.
//   STAGE 7  minimal string proof: read a string arg AND return a string
//            (the CExoString path) via two hosts.
//   STAGE 8  arbitrary-key data store (KIND 2, in-DLL key/value storage) via a
//            generalized operand-stack dispatch over four hosts.
//   STAGE 9  first engine-function call made purely to compute a result.
//   STAGE 10 GetFeatAcquired -- the first KOTOR 2 script function exposed in K1.
//
// Every stage forwards non-claimed calls through the identical proven path, so a
// bug in a handler is confined to the claimed IDs -- which no shipping script
// calls, so it cannot affect normal play.
// -----------------------------------------------------------------------------

// MinHook fills this with the trampoline (relocated prologue + jump past the patch).
static void* volatile g_trampoline = nullptr;

// =============================================================================
// SHARED ACCESSOR / BRIDGE LAYER.
//
// Every stage from 5 onward needs the same two things: the image base, and the VM
// state pointer the engine's argument accessors are called against. Each stage
// block defined them locally, so the identical pair existed EIGHT times -- three
// of those copies with cosmetically different formatting and two with a different
// typedef spelling for the same thunk.
//
// That duplication is why this is the first merge step and why it is the safe one:
// it removes copies of code that is already proven, without changing what any
// handler does. Nothing below this comment is new behaviour.
//
// THE CONTRACT. The accessors are
// __fastcall on the VM state object, take a pointer to a caller-owned out slot,
// POP the top VM-stack element after validating its type tag, RET 4, and return
// EAX = 1 on success / 0 on failure. Arguments are read in DECLARATION order, so a
// host declared (object, int) must read the object first even when the handler
// only wants the int -- reading them out of order silently returns the wrong
// value rather than failing.
//
// The typed per-family wrappers (ds_read_int, esl_read_int, feat_read_obj, ...)
// still live in their own stage blocks.
//
// âš  WHAT NOT TO HOIST NEXT, AND WHY -- read this before adding to this layer.
//
// `KseCore_Handle` looked like the obvious next candidate: five stage families
// defined a function by that exact name, so it read as one helper duplicated five
// times, exactly like KseImageBase above. It is not. The five have DIFFERENT
// SIGNATURES:
//     STAGE 4/5   (int routineId, const int* args, int argCount)      -> int
//     STAGE 6     (int opcode, const int* args, int argCount, int* ok)-> int
//     STAGE 8     (int op, int* ok)                                   -> int
// They are different functions wearing one name -- the per-family seam each stage
// happened to call the same thing. Hoisting "the" version would have compiled one
// family correctly and silently mis-shaped the rest, or failed to compile with an
// error pointing at the wrong place. They are renamed per family (KseN_Core)
// instead, which is the only correct answer and is not the one the name suggests.
//
// The general rule for this layer: **a shared name is not a shared function.**
// Compare signatures and bodies before hoisting, never names. The same mistake in
// the other direction produced the 632 "collision" that was really two names for
// one job -- identical bodies, assumed different.
// =============================================================================

static BYTE* KseImageBase()
{
    static BYTE* b = reinterpret_cast<BYTE*>(GetModuleHandleW(NULL));
    return b;
}

// A FRESH read for every accessor call -- the thunk dereferences it, and caching
// the dereferenced pointer across calls would outlive the VM state it points at.
static void* KseVM()
{
    return *reinterpret_cast<void**>(KseImageBase() + KSE_VM_STATE_RVA);
}

typedef int   (__fastcall *KseGetFn)     (void* thisptr, void* edx, void* out);
typedef int   (__fastcall *KseSetIntFn)  (void* thisptr, void* edx, int value);
typedef int   (__fastcall *KseSetStrFn)  (void* thisptr, void* edx, void* pSrc);
typedef void  (__fastcall *KseCtorFn)    (void* thisptr, void* edx);
typedef void  (__fastcall *KseDtorFn)    (void* thisptr, void* edx);
typedef void* (__fastcall *KseFromCStrFn)(void* thisptr, void* edx, const char* s);

// The engine's own string type: { char* ptr; int len; }. KSE never allocates one
// itself -- it constructs through the engine ctor and releases through the engine
// dtor, so every allocation is matched by the allocator that made it.
struct KseCExoStr { char* ptr; int len; };

// The transparency witness: EVERY dispatcher call, claimed or forwarded. Defined
// once here because all ten stage families incremented their own copy of it, and
// dllmain.cpp's worker reports it regardless of which stage is built.
volatile LONG g_hookCount = 0;

#if KSE_STAGE == 19
// THE SHARED STRING OPERAND, hoisted here for the unified build only.
//
// One buffer, one pending flag, filled by host 632 and read by every consumer:
// the string round trip, the engine-call probe, and the diagnostic channel. In a
// STAGE 7 build these are declared inside that stage's block, which is where they
// have always been; they move up here under 19 for an ordering reason, not a
// design one -- KseEval lives in STAGE 6's block, which the compiler sees BEFORE
// STAGE 7's, and 19's extra opcodes are handled there.
//
// It is one buffer rather than one per family on purpose: two buffers would need
// host 632 to fill both from a single VM-stack read (the accessors POP, so it
// cannot be read twice), and mirroring is a silent-divergence risk for no gain.
static char g_kseStr[512];        // fixed buffer -> zero DLL heap
static bool g_kseHave = false;    // is a pushed string pending an eval?
#if KSE_STAGE == 19
// KSE_BuildId stages its answer in g_kseStr and asks streval to return it
// AS-IS. Without this, streval's only behaviour is "KSE:reversed:" + reverse(stash),
// which is STAGE 7's proof and not a transport. One flag, set by exactly one opcode.
static bool g_kseStrVerbatim = false;
#endif
#endif




#if KSE_STAGE == 19
// ===========================================================================
// STAGE 6 -- the integer-utility suite via a two-host opcode dispatcher.
//
// Two safe never-called (object,int)->int hosts carry the whole suite:
//   _kse_push (host 627): push one int operand onto a small DLL-side stack.
//   _kse_eval (host 631): apply an opcode over the pushed operands, return int.
// kse.nss wrappers (KSE_BitAnd, ...) hide this: e.g. push a, push b, eval AND.
//
// STATEFUL-ORDERING RISK AND ITS CONTAINMENT (the reason this stage is de-risked
// harder than the stateless ones):
//   The design assumes the push(es) and the eval of one wrapper run consecutively
//   with nothing in between. On KOTOR's cooperative, single-threaded script VM
//   this holds -- a wrapper's body runs to completion without yielding, so its
//   ACTIONs are consecutive. IF that assumption were ever false (a second
//   sequence's pushes interleaving), the operand stack depth at eval time would
//   NOT equal the opcode's arity. KseEval checks depth==arity BEFORE computing and
//   clears the stack AFTER every eval, so a violation surfaces as a loud ANOMALY
//   log line and a sentinel return (KSE_ERR) -- an obviously-wrong answer that the
//   self-test flags -- never a silent, plausible miscomputation. The only way to
//   evade the arity check is an exact same-arity operand replacement mid-sequence,
//   which the single-threaded VM cannot produce; and even then the values would be
//   wrong and the known-answer test would catch it. The stress test hammers this
//   with thousands of back-to-back distinct sequences: all-correct across all of
//   them is the empirical proof the assumption holds.
// ===========================================================================


static const int KSE_MAXOPS = 4;          // max arity is 3 (CLAMP); +1 margin
static int  g_kseOps[KSE_MAXOPS];
static int  g_kseDepth = 0;
static const int KSE_ERR = -559038737;    // 0xDEADBEEF as signed: distinctive sentinel

// Opcodes -- MUST match include/kse.nss.
enum {
    OP_AND = 1, OP_OR = 2, OP_XOR = 3, OP_NOT = 4, OP_SHL = 5, OP_SHR = 6,
    OP_USHR = 7, OP_MIN = 8, OP_MAX = 9, OP_CLAMP = 10, OP_SIGN = 11,
    OP_POSMOD = 12, OP_IPOW = 13, OP_ISQRT = 14, OP_SQR = 15, OP_POPCOUNT = 16,
    OP_REPORT = 17
};

#if KSE_STAGE == 19
// Unified-build opcodes, deliberately far above the integer suite's 1..17 so the
// two spaces can never be confused by eye or by an off-by-one. See KseEval.
//   201  the engine-call probe (string pushed on 632, engine computes its length)
// 202 KSE_GetVersion -> KSE_VERSION_ENCODED
//   203  KSE_BuildId     -> stages KSE_BUILD_ID for streval to return VERBATIM
//   204  KSE_ERRNO       -> the last "why could this call not happen" code
//   900  the single diagnostic channel that replaces four
#define KSE_OP_ENGINE_STRLEN 201
#define KSE_OP_VERSION       202
#define KSE_OP_BUILDID       203
#define KSE_OP_ERRNO         204
#define KSE_OP_DIAG          900

// ---------------------------------------------------------------------------
// KSE_ERRNO -- "why could this call not happen"
//
// SCOPE IS NARROW ON PURPOSE, and the boundary is the point: this answers questions a
// modder can ACT on -- the call was refused, the host is absent, the version is wrong --
// and never "your argument was wrong". A bad argument is a programming error; it belongs
// in the log, where KSE_ERR and the ANOMALY lines already put it. A code that mixed both
// would teach modders to check it for the wrong reasons, and the useful signal would be
// buried in the noise of their own bugs.
//
// UNCONDITIONAL -- no diagnostic flag gates it. A silent no-op is the worst thing a
// tester can report, so the default must be the safe one.
//
// Set on the paths that REFUSE. Cleared by KSE_GetVersion, so a script can read it
// immediately after the call it is asking about without stale state from an earlier one.
// CODES START AT 1. ZERO IS RESERVED, and this is not tidiness -- a script calling an
// unclaimed slot reads 0. If KSE_E_OK were 0, KSE_ERRNO() could not
// distinguish "no KSE installed" from "nothing went wrong": both would read 0, and a
// modder who skipped the version check would conclude the call succeeded.
//
// THE CONSTRAINT GENERALISES TO EVERY FUNCTION ON THIS MECHANISM: a sentinel meaning
// ABSENT cannot also be a value the function legitimately returns. 0 is that sentinel
// here by measurement rather than by choice, so no int-returning KSE query may use it.
enum {
    KSE_E_OK           = 1,   // nothing refused since the last clear
    KSE_E_AT_CAPACITY  = 2,   // the grant hit count==cap and was refused
    KSE_E_NO_TARGET    = 3,   // the object resolved to nothing KSE could act on
    KSE_E_UNKNOWN_OP   = 4    // an opcode this build does not carry -- a VERSION mismatch
};
static volatile LONG g_kseErrno = KSE_E_OK;
#endif

static int OpArity(int op)
{
    switch (op) {
#if KSE_STAGE == 19
    case KSE_OP_ENGINE_STRLEN:
        return 0;   // its operand is the STRING pushed on 632, not an int
    case KSE_OP_VERSION:
    case KSE_OP_BUILDID:
    case KSE_OP_ERRNO:
        return 0;   // all three are pure queries, no operands
    case KSE_OP_DIAG:
        return 1;   // the code; the message rides in as the pushed string
#endif
    case OP_NOT: case OP_SIGN: case OP_ISQRT: case OP_SQR:
    case OP_POPCOUNT: case OP_REPORT:
        return 1;
    case OP_CLAMP:
        return 3;
    case OP_AND: case OP_OR: case OP_XOR: case OP_SHL: case OP_SHR:
    case OP_USHR: case OP_MIN: case OP_MAX: case OP_POSMOD: case OP_IPOW:
        return 2;
    default:
        return -1;   // unknown opcode
    }
}

static const char* OpName(int op)
{
    switch (op) {
    case OP_AND: return "AND"; case OP_OR: return "OR"; case OP_XOR: return "XOR";
    case OP_NOT: return "NOT"; case OP_SHL: return "SHL"; case OP_SHR: return "SHR";
    case OP_USHR: return "USHR"; case OP_MIN: return "MIN"; case OP_MAX: return "MAX";
    case OP_CLAMP: return "CLAMP"; case OP_SIGN: return "SIGN"; case OP_POSMOD: return "POSMOD";
    case OP_IPOW: return "IPOW"; case OP_ISQRT: return "ISQRT"; case OP_SQR: return "SQR";
    case OP_POPCOUNT: return "POPCOUNT"; case OP_REPORT: return "REPORT";
    default: return "?";
    }
}

// a[] holds operands in PUSH order: a[0] first pushed. Non-commutative ops
// (SHL/SHR/USHR/POSMOD/IPOW/CLAMP) rely on this order. `ok` is cleared on a
// domain error (e.g. divide by zero) so the caller returns the sentinel.
static int KseCompute(int op, const int* a, int* ok)
{
    *ok = 1;
    switch (op) {
    case OP_AND:  return a[0] & a[1];
    case OP_OR:   return a[0] | a[1];
    case OP_XOR:  return a[0] ^ a[1];
    case OP_NOT:  return ~a[0];
    case OP_SHL:  return (int)((unsigned)a[0] << (a[1] & 31));         // masked shift = defined
    case OP_SHR:  return a[0] >> (a[1] & 31);                          // arithmetic (sign-preserving)
    case OP_USHR: return (int)((unsigned)a[0] >> (a[1] & 31));         // logical
    case OP_MIN:  return a[0] < a[1] ? a[0] : a[1];
    case OP_MAX:  return a[0] > a[1] ? a[0] : a[1];
    case OP_CLAMP: { int v = a[0], lo = a[1], hi = a[2];
                    if (v < lo) return lo; if (v > hi) return hi; return v; }
    case OP_SIGN: return (a[0] > 0) - (a[0] < 0);
    case OP_POSMOD: { if (a[1] == 0) { *ok = 0; return KSE_ERR; }
                      int r = a[0] % a[1]; if (r < 0) r += (a[1] < 0 ? -a[1] : a[1]); return r; }
    case OP_IPOW: { int b = a[0], e = a[1]; if (e < 0) return 0;
                    long long r = 1, bb = b; while (e) { if (e & 1) r *= bb; bb *= bb; e >>= 1; }
                    return (int)r; }                                   // wraps mod 2^32 on overflow
    case OP_ISQRT: { if (a[0] < 0) { *ok = 0; return KSE_ERR; }
                     unsigned x = (unsigned)a[0], res = 0, bit = 1u << 30;
                     while (bit > x) bit >>= 2;
                     while (bit) { if (x >= res + bit) { x -= res + bit; res = (res >> 1) + bit; }
                                   else res >>= 1; bit >>= 2; }
                     return (int)res; }
    case OP_SQR:  return (int)((long long)a[0] * a[0]);                // wraps on overflow
    case OP_POPCOUNT: { unsigned v = (unsigned)a[0]; int c = 0; while (v) { c += v & 1; v >>= 1; } return c; }
    default: *ok = 0; return KSE_ERR;
    }
}

// --- accessor bridges -----------------------------------

// Both hosts are (object,int)->int: read the object arg (discard) then the int
// (declaration order). Returns false on any accessor failure.
static bool KseReadObjInt(int* outInt)
{
    BYTE* base = KseImageBase();
    void* P = *reinterpret_cast<void**>(base + KSE_VM_STATE_RVA);
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    int discard = 0;
    if (!getObject(P, nullptr, &discard)) return false;
    return getInt(P, nullptr, outInt) != 0;
}
static bool KseReturnInt(int v)
{
    BYTE* base = KseImageBase();
    void* P = *reinterpret_cast<void**>(base + KSE_VM_STATE_RVA);
    KseSetIntFn setret = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);
    return setret(P, nullptr, v) != 0;
}

// The channel-agnostic seam: for stage 6 the "command" is an opcode over operands.
static int Kse6_Core(int opcode, const int* args, int argCount, int* ok)
{
    (void)argCount;
    return KseCompute(opcode, args, ok);
}

// --- _kse_push (host 627) --------------------------------------------------
extern "C" int __stdcall KsePush(int argCount)
{
    if (argCount != 2) { Log("K1SE push: unexpected argCount=%d (host is object,int)", argCount); return -1; }
    int x = 0;
    if (!KseReadObjInt(&x)) { Log("K1SE push: arg read failed"); return -1; }
    if (g_kseDepth >= KSE_MAXOPS) {
        // Overflow can only happen if a prior sequence never evaluated (an
        // interrupted/leaked sequence). Reset loudly rather than corrupt.
        Log("K1SE ANOMALY push: operand stack overflow (depth=%d) -- interrupted sequence? resetting",
            g_kseDepth);
        g_kseDepth = 0;
    }
    g_kseOps[g_kseDepth++] = x;
    KseReturnInt(g_kseDepth);   // return current depth (wrappers ignore it)
    return 0;
}

// --- _kse_eval (host 631) --------------------------------------------------
extern "C" int __stdcall KseEval(int argCount)
{
    if (argCount != 2) { Log("K1SE eval: unexpected argCount=%d (host is object,int)", argCount); return -1; }
    int op = 0;
    if (!KseReadObjInt(&op)) { Log("K1SE eval: arg read failed"); return -1; }

    int arity = OpArity(op);
    if (arity < 0) {
        Log("K1SE ANOMALY eval: unknown opcode %d (depth=%d); sentinel", op, g_kseDepth);
#if KSE_STAGE == 19
        // An opcode this build does not carry is precisely a VERSION MISMATCH: a newer
        // script against an older KSE. That is a modder-actionable condition, so it is
        // exactly what KSE_ERRNO is for.
        InterlockedExchange(&g_kseErrno, KSE_E_UNKNOWN_OP);
#endif
        g_kseDepth = 0; KseReturnInt(KSE_ERR); return 0;
    }
    // The ordering-assumption guard: the staged operand count MUST equal the
    // opcode's arity. Any mismatch is the signature of an interrupted/leaked
    // sequence -> log loudly, discard, return the sentinel (never miscompute).
    if (g_kseDepth != arity) {
        Log("K1SE ANOMALY eval: op=%s(%d) expected %d operands, found %d -- "
            "interrupted/leaked sequence; sentinel", OpName(op), op, arity, g_kseDepth);
        g_kseDepth = 0; KseReturnInt(KSE_ERR); return 0;
    }

    int a[KSE_MAXOPS];
    for (int i = 0; i < arity; ++i) a[i] = g_kseOps[i];
    g_kseDepth = 0;   // clear AFTER snapshotting -> no residue leaks to the next sequence

#if KSE_STAGE == 19
    if (op == KSE_OP_VERSION) {
        // Clearing errno here is deliberate: a script's first KSE call is the presence
        // check, so it starts from a known state and any code it reads afterwards belongs
        // to the call it just made -- not to something earlier in the session.
        InterlockedExchange(&g_kseErrno, KSE_E_OK);
        KseReturnInt(KSE_VERSION_ENCODED);
        return 0;
    }
    if (op == KSE_OP_ERRNO) {
        KseReturnInt((int)g_kseErrno);
        return 0;
    }
    if (op == KSE_OP_BUILDID) {
        const char* b = KSE_BUILD_ID;
        size_t k = 0;
        for (; b[k] && k < sizeof(g_kseStr) - 1; ++k) g_kseStr[k] = b[k];
        g_kseStr[k] = '\0';
        g_kseHave = true;
        g_kseStrVerbatim = true;      // streval must NOT reverse this one
        KseReturnInt((int)k);         // the length, so a caller can sanity-check
        return 0;
    }
#endif
    if (op == OP_REPORT) {
        // Self-test channel: the wrapper KSE_Report(fails) lands here; log the value
        // so the outcome is visible in kse.log without a save editor.
        Log("K1SE SELFTEST: fails-bitmask=%d (0 = every check passed)", a[0]);
        KseReturnInt(a[0]);
        return 0;
    }

#if KSE_STAGE == 19
    // ---- opcodes that exist ONLY in the unified build --------------------------
    // Host 683 retires, so STAGE 9's engine call moves onto this host, and the four
    // self-test channels fold into one. Both live in a RANGE well clear of the
    // integer suite's 1..17, so the two opcode spaces cannot ever be confused.
    //
    // Guarded to STAGE 19 deliberately: a STAGE 6 build keeps the exact opcode set
    // it was proven with (132 calls, bitmask 0), so this cannot regress it. That is
    // do not disturb evidence you are about to rely on.
    if (op == KSE_OP_ENGINE_STRLEN) {
        // The engine computes the length of the string pushed on host 632 -- the
        // point being that KSE calls the ENGINE rather than doing it itself.
        if (!g_kseHave) {
            Log("K1SE ANOMALY diag/enginestrlen: no pushed string pending; sentinel");
            KseReturnInt(KSE_ERR); return 0;
        }
        typedef int (__fastcall *Kse19GetLenFn)(void* thisptr, void* edx);
        BYTE* base = KseImageBase();
        KseCtorFn     ctor     = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
        KseDtorFn     dtor     = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);
        KseFromCStrFn fromCStr = reinterpret_cast<KseFromCStrFn>(base + KSE_CEXOSTR_FROMCSTR_RVA);
        Kse19GetLenFn getLen   = reinterpret_cast<Kse19GetLenFn>(base + KSE_CEXOSTR_GETLEN_RVA);
        KseCExoStr s;
        ctor(&s, nullptr);
        fromCStr(&s, nullptr, g_kseStr);
        const int engineLen = getLen(&s, nullptr);
        dtor(&s, nullptr);                       // matched alloc/free, always

        // Cross-check against our own count: the engine's answer is the product, and
        // a disagreement means the call convention is wrong, not that the string is.
        int mine = 0; while (g_kseStr[mine]) ++mine;
        if (engineLen != mine) {
            Log("K1SE ANOMALY enginestrlen: engine says %d, we count %d; sentinel",
                engineLen, mine);
            KseReturnInt(KSE_ERR); return 0;
        }
        Log("K1SE ENGINESTRLEN: %d (engine and K1SE agree)", engineLen);
        KseReturnInt(engineLen);
        return 0;
    }

    if (op == KSE_OP_DIAG) {
        // THE single diagnostic channel. It replaces four: STAGE 6's KSE_Report,
        // STAGE 8's KSE_LogInt, STAGE 9's KSE_EngineSelfTest and STAGE 10's
        // KSE_FeatSelfTest -- which used four different hosts, so no single build
        // could run them all. This one channel replaces all of them.
        Log("K1SE DIAG: code=%d msg=\"%s\"", a[0], g_kseHave ? g_kseStr : "");
        g_kseHave = false;
        KseReturnInt(a[0]);
        return 0;
    }
#endif

    int ok = 1;
    int result = Kse6_Core(op, a, arity, &ok);
    if (arity == 1)
        LogDiag("K1SE eval %s(%d) -> %d%s", OpName(op), a[0], result, ok ? "" : " [domain error -> sentinel]");
    else if (arity == 2)
        LogDiag("K1SE eval %s(%d,%d) -> %d%s", OpName(op), a[0], a[1], result, ok ? "" : " [domain error -> sentinel]");
    else
        LogDiag("K1SE eval %s(%d,%d,%d) -> %d%s", OpName(op), a[0], a[1], a[2], result, ok ? "" : " [domain error -> sentinel]");
    KseReturnInt(result);
    return 0;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 7 -- the minimal string proof: read a string arg AND return a string.
//
// This is the FIRST time a KSE handler touches CExoString -- an engine memory
// object with its own allocation. Everything before it moved plain 4-byte ints.
// The whole stage exists to prove BOTH directions of the CExoString path
// with the smallest possible transform, so correctness is
// obvious in the log and the memory lifecycle can be watched in isolation.
//
// Two safe never-called null hosts (offsets.h) carry it, as in STAGE 6 -- no
// single safe null routine has a string->string shape:
//   _kse_strpush (host 632, void(object,int,string)): read+stash the string.
//   _kse_streval (host 583, string()): return "KSE:reversed:" + reverse(stash).
// The wrapper KSE_StrTest(string)->string in include/kse.nss hides the split.
//
// TRANSFORM = "KSE:reversed:" + reverse(input) (e.g. "KSE" -> "KSE:reversed:ESK").
// Reversing forces reading EVERY input character and re-emitting it in mirrored
// order -- a per-character read/write correctness check that a prefix alone would
// not give. It also changes the length (+13), so the return must build a NEW,
// differently sized CExoString rather than handing back the input's storage, and
// the "KSE:reversed:" tag makes the result self-describing and impossible to
// confuse with the input in the log.
//
// MEMORY SAFETY -- the one genuinely new surface. Three ways it can go wrong,
// how each is prevented, and its first-run signature:
//
//   (1) LEAK -- an engine allocation never freed.
//       * get.string copies the popped string INTO our local CExoString (engine
//         operator=): our local now owns an engine-malloc'd buffer.
//       * copyFromCStr allocates a buffer into our return local.
//       Guard: every local is destroyed via the engine dtor (0x005e5c20) on
//       EVERY path (success and abort) before the handler returns -- see the
//       single-exit dtor calls below. set.string DEEP-COPIES (it reads our
//       local via c_str and allocates its own), so freeing our local afterward
//       is correct, not premature.
//       First-run signature: no crash, but process memory climbs steadily across
//       the heartbeat stress (thousands of calls). Steady RSS == no leak.
//
//   (2) DOUBLE FREE / allocator mismatch -- freeing the same buffer twice, or
//       freeing a buffer we did not allocate with the engine allocator.
//       Guard: each local is default-constructed ({0,0}) exactly once, filled by
//       exactly one engine routine (get.string or copyFromCStr, both using the
//       engine allocator that the dtor's free 0x006fa390 matches), and destroyed
//       exactly once. We NEVER wrap our static g_kseStr buffer in a CExoString we
//       then destroy, so the engine free is never handed a non-engine pointer.
//       First-run signature: an immediate access violation inside the allocator
//       during/just after the FIRST call -- a hard crash, not a slow drift.
//
//   (3) STACK IMBALANCE / buffer overrun -- popping the wrong number of args or
//       overflowing our copy buffer.
//       Guard: strpush pops EXACTLY its 3 declared args in declaration order
//       (object, int, string) and pushes nothing (void); streval pops 0 and
//       pushes exactly 1 string. The copy into g_kseStr is bounded to
//       sizeof-1 and always NUL-terminated. ECX (=VM state P) is reloaded fresh
// for every accessor call, as the thunks require.
//       First-run signature: corruption LATER, not at the call site -- the game
//       runs, then misbehaves/crashes elsewhere as the unbalanced VM stack is
//       used. The round-trip log (received vs returned) also flags a bad read at
//       once. The heartbeat stress surfaces both fast.
//
//   (4) CROSS-CALL STATE -- the stash lives between the two host calls, so, as in
//       STAGE 6, it assumes push then eval run consecutively. On KOTOR's
//       single-threaded, cooperative script VM a wrapper body runs to completion
//       without yielding, so they are. If that were ever false, streval would
//       find g_kseHave clear -> it logs an ANOMALY and returns "KSE!ERR" (an
//       obviously-wrong, non-crashing sentinel), never a plausible wrong string.
// ===========================================================================

static volatile LONG g_strpushCount = 0;
static volatile LONG g_strevalCount = 0;

// CExoString: { char* ptr @ +0; int len @ +4 } (8 bytes), verified from the dtor.



// __thiscall accessors/lifecycle emulated as __fastcall (ECX=this, EDX unused).

// The channel-agnostic seam (mirrors STAGE 4/5/6): build the reply string from the
// received one. Kept tiny and pure so the transform is obviously correct.
static void Kse7_CoreStr(const char* in, char* out, size_t outSz)
{
    // out = "KSE:reversed:" + reverse(in), bounded. Reversing forces reading EVERY
    // input character and re-emitting it in mirrored order (a per-character
    // read/write correctness check), and still changes the length (+13) so the
    // return must build a new, differently sized CExoString. The "KSE:reversed:"
    // tag makes the output self-describing and impossible to confuse with the input
    // in the log.
    const char* pfx = "KSE:reversed:";
    size_t i = 0;
    for (; pfx[i] && i < outSz - 1; ++i) out[i] = pfx[i];
    size_t n = 0;
    while (in[n]) ++n;                                     // strlen(in)
    for (size_t k = n; k > 0 && i < outSz - 1; --k, ++i) out[i] = in[k - 1];
    out[i] = '\0';
}

// -------- _kse_strpush (host 632): void(object, int, string) ----------------
// Reads+stashes the string arg. Void return -> the read side needs no return
// accessor (the cleanest possible exercise of get.string).
extern "C" int __stdcall KseStrPush(int argCount)
{
    if (argCount != 3) {   // declared (object, int, string)
        Log("K1SE ANOMALY strpush: unexpected argCount=%d (declared 3); no args consumed",
            KSE_PUSHSTR_ID);
        return -1;
    }
    BYTE* base = KseImageBase();
    KseGetFn  getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn  getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseGetFn  getString = reinterpret_cast<KseGetFn>(base + KSE_GET_STRING_RVA);
    KseCtorFn ctor      = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn dtor      = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);

    // DECLARATION ORDER: object, int, string. object+int are popped and
    // discarded purely for stack balance; only the string is kept.
    int discard = 0;
    if (!getObject(KseVM(), nullptr, &discard)) {
        Log("K1SE ANOMALY strpush: get.object (arg 1) failed; aborting"); return -1;
    }
    if (!getInt(KseVM(), nullptr, &discard)) {
        Log("K1SE ANOMALY strpush: get.int (arg 2) failed; aborting"); return -1;
    }

    KseCExoStr s;
    ctor(&s, nullptr);                         // { 0, 0 } -- fresh, so no pre-existing buffer
    int ok = getString(KseVM(), nullptr, &s);  // engine copies the popped string INTO s
    if (ok) {
        const char* c = s.ptr ? s.ptr : "";    // CExoString is NUL-terminated; guard empty
        size_t i = 0;
        for (; c[i] && i < sizeof(g_kseStr) - 1; ++i) g_kseStr[i] = c[i];   // bounded copy
        g_kseStr[i] = '\0';
        g_kseHave = true;
        LogDiag("K1SE strpush received \"%s\" (len %d)", g_kseStr, (int)i);
    } else {
        g_kseHave = false;
        Log("K1SE ANOMALY strpush: get.string (arg 3) failed");
    }
    dtor(&s, nullptr);   // ALWAYS: frees s.ptr if get.string filled it; a no-op on {0,0}
    InterlockedIncrement(&g_strpushCount);
    return ok ? 0 : -1;
}

// -------- _kse_streval (host 583): string() -------------------------------
// No args to pop. Builds "KSE:reversed:"+reverse(stash) as a CExoString and pushes
// it (set.string).
extern "C" int __stdcall KseStrEval(int argCount)
{
    if (argCount != 0) {   // declared ()
        Log("K1SE ANOMALY streval: unexpected argCount=%d (declared 0)", KSE_STROUT_ID);
        return -1;
    }
    BYTE* base = KseImageBase();
    KseCtorFn     ctor    = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn     dtor    = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);
    KseFromCStrFn fromCStr= reinterpret_cast<KseFromCStrFn>(base + KSE_CEXOSTR_FROMCSTR_RVA);
    KseSetStrFn   setStr  = reinterpret_cast<KseSetStrFn>(base + KSE_SETRET_STRING_RVA);

    char out[sizeof(g_kseStr) + 16];   // room for the "KSE:reversed:" tag (13) + NUL
#if KSE_STAGE == 19
    if (g_kseHave && g_kseStrVerbatim) {
        // KSE_BuildId staged its answer; hand it back untouched.
        size_t k = 0; for (; g_kseStr[k] && k < sizeof(out) - 1; ++k) out[k] = g_kseStr[k];
        out[k] = '\0';
    } else
#endif
    if (g_kseHave) {
        Kse7_CoreStr(g_kseStr, out, sizeof(out));   // "KSE:reversed:" + reverse(received)
    } else {
        // Ordering assumption violated (see note (4)): fail loud, never miscompute.
        Log("K1SE ANOMALY streval: no pushed string pending (interrupted sequence); sentinel");
        const char* sentinel = "KSE!ERR";
        size_t k = 0; for (; sentinel[k]; ++k) out[k] = sentinel[k]; out[k] = '\0';
    }
    g_kseHave = false;   // consume the stash whether ok or sentinel
#if KSE_STAGE == 19
    g_kseStrVerbatim = false;   // one-shot: never leaks into the next streval
#endif

    // Build a fresh engine CExoString from our C buffer, push it, then destroy it.
    KseCExoStr s;
    ctor(&s, nullptr);              // { 0, 0 }
    fromCStr(&s, nullptr, out);     // s <- engine-allocated copy of `out`
    int ok = setStr(KseVM(), nullptr, &s);   // DEEP-COPIES s onto the VM return slot
    if (!ok) Log("K1SE ANOMALY streval: set.string failed; no return pushed");
    dtor(&s, nullptr);             // free our copy (set.string kept its own deep copy)

    LogDiag("K1SE streval -> \"%s\"", out);
    InterlockedIncrement(&g_strevalCount);
    return ok ? 0 : -1;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 8 -- the arbitrary-key data store (KIND 2: our own in-DLL storage).
//
// The headline capability: unlimited, arbitrarily-NAMED key/value storage, which
// KOTOR's script API fundamentally lacks: the game's globals are a fixed
// pre-declared catalogue a script cannot extend. This stage is pure assembly of
// proven parts: read string/int args, return strings/ints, and hold self-managed
// C++ state safely under stress. No new engine mechanism is introduced.
//
// DISPATCH: a generalized STAGE-6 operand stack. Two push hosts stage typed
// operands (string / int); one int-returning eval host applies an opcode; GetData
// -- the only string-returning op -- has its own no-arg string host. Wrappers in
// include/kse.nss (KSE_SetData/GetData/SetInt/GetInt/HasData/DeleteData) hide it.
//
// LIFETIME (state honestly, so the capability is not oversold):
//   * The store is PURE IN-DLL MEMORY. It lives exactly as long as the game
//     process. Set-then-get in the SAME session round-trips; across a game
//     restart the store is EMPTY. There is NO save-file or disk persistence here
//     (that is a deliberately separate later stage). In-memory only.
//
// MEMORY SAFETY -- this holds real user data, so the model is chosen to make whole
// classes of bug IMPOSSIBLE by construction rather than merely guarded:
//   * FIXED-CAPACITY TABLE, ZERO HEAP. Every entry is a fixed-size slot
//     { key[128], type, sval[512], ival }. There is no malloc/free anywhere in the
//     store, so a LEAK or DOUBLE-FREE cannot occur -- overwriting a key is a
//     bounded in-place copy into the existing slot (the "free-on-overwrite" path
//     reduces to "overwrite the buffer"; nothing to free). Delete just clears a
//     slot's `used` flag. (A std::map<string,string> would be the classic place
//     for overwrite/churn leaks; we sidestep it entirely.)
//   * BOUNDED. At most KSE_DS_MAX_ENTRIES keys; keys < KSE_DS_KEYBUF and values <
//     KSE_DS_VALBUF bytes. Exceeding any cap FAILS GRACEFULLY: the op returns the
//     sentinel KSE_DS_ERR and logs a loud line -- never a crash, never silent
//     truncation stored as if valid (an over-long operand is flagged at push time
//     and rejected at eval). Lifting the 127-char key cap by hashing keys is a
//     deliberate follow-up, kept out of this stage so the code recorded as proven
//     is exactly the code that ran on hardware.
//   * ORDERING (same as STAGE 6): push(es) then eval run consecutively on KOTOR's
//     single-threaded, cooperative script VM. eval checks the operand count AND
//     each operand's type against the opcode's arity; a mismatch (interrupted /
//     leaked sequence) logs an ANOMALY, clears the stack, and returns the sentinel
//     -- never a plausible wrong value.
//   * REENTRANCY: single VM thread; no locking needed. The transparency counter is
//     the only cross-thread value and stays interlocked.
// ===========================================================================


// ---- store shape (fixed capacity, zero heap) ------------------------------
static const int KSE_DS_MAX_ENTRIES = 256;  // key-count cap
static const int KSE_DS_KEYBUF      = 128;  // max key length 127 + NUL
static const int KSE_DS_VALBUF      = 512;  // max value length 511 + NUL
static const int KSE_DS_MAXOPS      = 4;    // operand-stack depth (max arity is 2, +margin)
static const int KSE_DS_ERR         = -559038737;  // 0xDEADBEEF signed: cap/mismatch sentinel

enum { KSE_T_STR = 1, KSE_T_INT = 2 };      // value/operand type tags
// Opcodes -- MUST match include/kse.nss. GETDATA is dispatched by its own host, so
// it is not reachable through the int-eval opcode switch.
enum { DSOP_SETDATA = 1, DSOP_SETINT = 2, DSOP_GETINT = 3, DSOP_HASDATA = 4,
       DSOP_DELETE  = 5, DSOP_REPORT = 6, DSOP_GETDATA = 7 };

// KEY MODEL -- each slot stores the key verbatim in a fixed buffer and matches by
// string compare. Simple and allocation-free; the cost is a hard 127-character key
// limit, which is enforced (not silently truncated): an over-long key is rejected
// with the sentinel. Hashing keys to lift that limit is a deliberate follow-up,
// kept out of this stage so the version recorded as proven is exactly the version
// that ran on hardware.
struct KseEntry { bool used; int type; char key[KSE_DS_KEYBUF]; char sval[KSE_DS_VALBUF]; int ival; };
static KseEntry g_store[KSE_DS_MAX_ENTRIES];
static int      g_storeUsed = 0;

// Operand: a string OR an int, plus a truncation flag set when the incoming value
// was longer than its buffer (so eval can reject rather than store truncated data).
struct KseOperand { int type; int ival; char sval[KSE_DS_VALBUF]; bool truncated; };
static KseOperand g_dsOps[KSE_DS_MAXOPS];
static int        g_dsDepth = 0;

// ---- tiny bounded string helpers (no CRT dependence; matches STAGE 7 style) --
static size_t ds_len(const char* s) { size_t n = 0; while (s[n]) ++n; return n; }
static bool   ds_eq(const char* a, const char* b)
{ while (*a && *b) { if (*a != *b) return false; ++a; ++b; } return *a == *b; }
// Copy s into d (size dsz). Returns true if it FIT, false if it had to truncate.
static bool ds_copy(char* d, size_t dsz, const char* s)
{ size_t i = 0; for (; s[i] && i < dsz - 1; ++i) d[i] = s[i]; d[i] = '\0'; return s[i] == '\0'; }

// ---- the store (fixed slots; no allocation, so no leak/double-free possible) --
static int ds_find(const char* key)
{ for (int i = 0; i < KSE_DS_MAX_ENTRIES; ++i) if (g_store[i].used && ds_eq(g_store[i].key, key)) return i; return -1; }
static int ds_alloc()
{ for (int i = 0; i < KSE_DS_MAX_ENTRIES; ++i) if (!g_store[i].used) return i; return -1; }

// Returns the slot index for key, creating it if absent; -1 if the table is full.
static int ds_slot_for(const char* key)
{
    int idx = ds_find(key);
    if (idx >= 0) return idx;                        // existing key -> overwrite in place
    idx = ds_alloc();
    if (idx < 0) return -1;                          // full
    g_store[idx].used = true;
    ds_copy(g_store[idx].key, KSE_DS_KEYBUF, key);   // key length already validated by caller
    ++g_storeUsed;
    return idx;
}



static bool ds_read_object_discard()
{ int d = 0; KseGetFn g = reinterpret_cast<KseGetFn>(KseImageBase() + KSE_GET_OBJECT_RVA); return g(KseVM(), nullptr, &d) != 0; }
static bool ds_read_int(int* out)
{ KseGetFn g = reinterpret_cast<KseGetFn>(KseImageBase() + KSE_GET_INT_RVA); return g(KseVM(), nullptr, out) != 0; }

// Read a string arg into `out` (bounded). *fit is false if the source was longer
// than the buffer. Manages its own CExoString via the engine ctor/dtor (matched
// alloc/free), so no leak regardless of outcome.
static bool ds_read_string(char* out, size_t outSz, bool* fit)
{
    BYTE* base = KseImageBase();
    KseGetFn  getString = reinterpret_cast<KseGetFn>(base + KSE_GET_STRING_RVA);
    KseCtorFn ctor      = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn dtor      = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);
    KseCExoStr s;
    ctor(&s, nullptr);                       // { 0, 0 }
    int ok = getString(KseVM(), nullptr, &s);
    if (ok) *fit = ds_copy(out, outSz, s.ptr ? s.ptr : "");
    dtor(&s, nullptr);                       // ALWAYS free (no-op on {0,0})
    return ok != 0;
}

static void ds_return_int(int v)
{ KseSetIntFn s = reinterpret_cast<KseSetIntFn>(KseImageBase() + KSE_SETRET_INT_RVA); s(KseVM(), nullptr, v); }

static void ds_return_string(const char* v)
{
    BYTE* base = KseImageBase();
    KseCtorFn     ctor     = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn     dtor     = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);
    KseFromCStrFn fromCStr = reinterpret_cast<KseFromCStrFn>(base + KSE_CEXOSTR_FROMCSTR_RVA);
    KseSetStrFn   setStr   = reinterpret_cast<KseSetStrFn>(base + KSE_SETRET_STRING_RVA);
    KseCExoStr s;
    ctor(&s, nullptr);
    fromCStr(&s, nullptr, v);                // engine-allocated copy of v
    setStr(KseVM(), nullptr, &s);            // deep-copies onto the return slot
    dtor(&s, nullptr);                       // free our copy (matched alloc/free)
}

// ---- operand stack --------------------------------------------------------
static void ds_push_str(const char* s, bool fit)
{
    if (g_dsDepth >= KSE_DS_MAXOPS) {
        Log("K1SE ANOMALY ds push: operand overflow (depth=%d) -- interrupted sequence? resetting", g_dsDepth);
        g_dsDepth = 0;
    }
    KseOperand& op = g_dsOps[g_dsDepth++];
    op.type = KSE_T_STR; op.ival = 0; op.truncated = !fit;
    ds_copy(op.sval, KSE_DS_VALBUF, s);
}
static void ds_push_int(int v)
{
    if (g_dsDepth >= KSE_DS_MAXOPS) {
        Log("K1SE ANOMALY ds push: operand overflow (depth=%d) -- interrupted sequence? resetting", g_dsDepth);
        g_dsDepth = 0;
    }
    KseOperand& op = g_dsOps[g_dsDepth++];
    op.type = KSE_T_INT; op.ival = v; op.truncated = false; op.sval[0] = '\0';
}

// The channel-agnostic seam: apply one data-store opcode over the staged operands.
// Returns the int result; writes a c-string result to `sout` for string ops.
static int Kse8_Core(int op, int* ok)
{
    *ok = 1;
    switch (op) {
    case DSOP_SETDATA: {
        const char* key = g_dsOps[0].sval; const char* val = g_dsOps[1].sval;
        if (g_dsOps[0].truncated || g_dsOps[1].truncated || ds_len(key) >= KSE_DS_KEYBUF) {
            Log("K1SE ds SETDATA key=\"%s\": operand too long -> sentinel", key); *ok = 0; return KSE_DS_ERR;
        }
        int idx = ds_slot_for(key);
        if (idx < 0) { Log("K1SE ds SETDATA key=\"%s\": store full (%d) -> sentinel", key, g_storeUsed); *ok = 0; return KSE_DS_ERR; }
        g_store[idx].type = KSE_T_STR; ds_copy(g_store[idx].sval, KSE_DS_VALBUF, val);
        Log("K1SE ds SETDATA key=\"%s\" val=\"%s\" -> ok (%d keys)", key, val, g_storeUsed);
        return 1;
    }
    case DSOP_SETINT: {
        const char* key = g_dsOps[0].sval; int val = g_dsOps[1].ival;
        if (g_dsOps[0].truncated || ds_len(key) >= KSE_DS_KEYBUF) {
            Log("K1SE ds SETINT key=\"%s\": key too long -> sentinel", key); *ok = 0; return KSE_DS_ERR;
        }
        int idx = ds_slot_for(key);
        if (idx < 0) { Log("K1SE ds SETINT key=\"%s\": store full (%d) -> sentinel", key, g_storeUsed); *ok = 0; return KSE_DS_ERR; }
        g_store[idx].type = KSE_T_INT; g_store[idx].ival = val;
        Log("K1SE ds SETINT key=\"%s\" val=%d -> ok (%d keys)", key, val, g_storeUsed);
        return 1;
    }
    case DSOP_GETINT: {
        const char* key = g_dsOps[0].sval;
        int idx = ds_find(key);
        int r = (idx >= 0 && g_store[idx].type == KSE_T_INT) ? g_store[idx].ival : 0;   // missing/mismatch -> 0
        if (idx >= 0 && g_store[idx].type != KSE_T_INT)
            Log("K1SE ds GETINT key=\"%s\": type mismatch (stored string) -> 0", key);
        else
            LogDiag("K1SE ds GETINT key=\"%s\" -> %d%s", key, r, idx < 0 ? " (absent)" : "");
        return r;
    }
    case DSOP_HASDATA: {
        const char* key = g_dsOps[0].sval;
        int r = ds_find(key) >= 0 ? 1 : 0;
        LogDiag("K1SE ds HASDATA key=\"%s\" -> %d", key, r);
        return r;
    }
    case DSOP_DELETE: {
        const char* key = g_dsOps[0].sval;
        int idx = ds_find(key);
        if (idx >= 0) { g_store[idx].used = false; --g_storeUsed; }
        Log("K1SE ds DELETE key=\"%s\" -> %d (%d keys)", key, idx >= 0 ? 1 : 0, g_storeUsed);
        return idx >= 0 ? 1 : 0;
    }
    case DSOP_REPORT: {
        int v = g_dsOps[0].ival;
        Log("K1SE ds SELFTEST: fails-bitmask=%d (0 = every check passed)", v);
        return v;
    }
    default:
        Log("K1SE ANOMALY ds eval: unknown opcode %d -> sentinel", op); *ok = 0; return KSE_DS_ERR;
    }
}

// Validate that the staged operands match an opcode's declared arity+types. On a
// mismatch (the signature of an interrupted/leaked sequence) log loudly and clear.
static bool ds_check(int op)
{
    int wantN; int t0 = KSE_T_STR, t1 = 0;   // t1==0 -> no second operand
    switch (op) {
    case DSOP_SETDATA: wantN = 2; t1 = KSE_T_STR; break;
    case DSOP_SETINT:  wantN = 2; t1 = KSE_T_INT; break;
    case DSOP_GETINT: case DSOP_HASDATA: case DSOP_DELETE: case DSOP_GETDATA: wantN = 1; break;
    case DSOP_REPORT:  wantN = 1; t0 = KSE_T_INT; break;
    default: return false;
    }
    if (g_dsDepth != wantN) {
        Log("K1SE ANOMALY ds eval: op %d expected %d operands, found %d -- interrupted sequence", op, wantN, g_dsDepth);
        return false;
    }
    if (g_dsOps[0].type != t0 || (t1 && g_dsOps[1].type != t1)) {
        Log("K1SE ANOMALY ds eval: op %d operand type mismatch", op);
        return false;
    }
    return true;
}

// -------- push hosts -------------------------------------------------------
extern "C" int __stdcall KseDsPushS(int argCount)  // host 633: void(object,int,string)
{
    if (argCount != 3) { Log("K1SE ANOMALY ds pushs: argCount=%d (declared 3)", argCount); return -1; }
    if (!ds_read_object_discard()) { Log("K1SE ANOMALY ds pushs: get.object failed"); return -1; }
    int discard = 0;
    if (!ds_read_int(&discard))    { Log("K1SE ANOMALY ds pushs: get.int failed"); return -1; }
    char buf[KSE_DS_VALBUF]; bool fit = true;
    if (!ds_read_string(buf, sizeof(buf), &fit)) { Log("K1SE ANOMALY ds pushs: get.string failed"); return -1; }
    ds_push_str(buf, fit);
    return 0;
}
extern "C" int __stdcall KseDsPushI(int argCount)  // host 622: void(object,int)
{
    if (argCount != 2) { Log("K1SE ANOMALY ds pushi: argCount=%d (declared 2)", argCount); return -1; }
    if (!ds_read_object_discard()) { Log("K1SE ANOMALY ds pushi: get.object failed"); return -1; }
    int v = 0;
    if (!ds_read_int(&v))          { Log("K1SE ANOMALY ds pushi: get.int failed"); return -1; }
    ds_push_int(v);
    return 0;
}

// -------- eval hosts -------------------------------------------------------
extern "C" int __stdcall KseDsEvalI(int argCount)  // host 640: int(object,int)->int
{
    if (argCount != 2) { Log("K1SE ANOMALY ds evali: argCount=%d (declared 2)", argCount); return -1; }
    if (!ds_read_object_discard()) { Log("K1SE ANOMALY ds evali: get.object failed"); return -1; }
    int op = 0;
    if (!ds_read_int(&op))         { Log("K1SE ANOMALY ds evali: get.int failed"); return -1; }
    if (!ds_check(op)) { g_dsDepth = 0; ds_return_int(KSE_DS_ERR); return 0; }
    int ok = 1;
    int result = Kse8_Core(op, &ok);
    g_dsDepth = 0;                            // clear after every eval -> no residue
    ds_return_int(result);
    return 0;
}
extern "C" int __stdcall KseDsGetData(int argCount)  // host 584: string()->string
{
    if (argCount != 0) { Log("K1SE ANOMALY ds getdata: argCount=%d (declared 0)", argCount); return -1; }
    if (!ds_check(DSOP_GETDATA)) { g_dsDepth = 0; ds_return_string(""); return 0; }
    const char* key = g_dsOps[0].sval;
    int idx = ds_find(key);
    const char* val = (idx >= 0 && g_store[idx].type == KSE_T_STR) ? g_store[idx].sval : "";
    if (idx >= 0 && g_store[idx].type != KSE_T_STR)
        Log("K1SE ds GETDATA key=\"%s\": type mismatch (stored int) -> \"\"", key);
    else
        LogDiag("K1SE ds GETDATA key=\"%s\" -> \"%s\"%s", key, val, idx < 0 ? " (absent)" : "");
    g_dsDepth = 0;
    ds_return_string(val);
    return 0;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 9 -- the first engine-function call made purely to COMPUTE a result for
// a script.
//
// HONEST FRAMING (see offsets.h): our handlers have called engine code since
// STAGE 7 -- the VM accessors and the CExoString ctor/dtor/copyFromCStr are all
// engine functions, invoked with the correct convention and proven at runtime.
// The raw mechanism is therefore NOT new. What is new: calling an engine function
// that we do not need for plumbing, purely to have the ENGINE do work whose
// result the script receives.
//
// TARGET: CExoString::GetLength (KSE_CEXOSTR_GETLEN_RVA). Pure (no side effects,
// no game state), trivial context (ECX = a CExoString we own; zero stack args),
// and exactly verifiable (strlen semantics). See offsets.h for the address.
//
// TRANSPARENCY: unchanged. Only the two claimed IDs diverge; every other routine
// takes the identical proven pass-through (`jmp [g_trampoline]`).
//
// WHAT COULD GO WRONG, AND HOW IT IS CAUGHT:
//   (1) WRONG ADDRESS / WRONG FUNCTION -> a wrong number or a crash. Guard: the
//       handler computes the length ITSELF as well and compares. A disagreement
//       logs "KSE ANOMALY" and returns the sentinel, so a wrong engine result can
//       never masquerade as a correct one. (The value returned to the script is
//       the ENGINE's, not ours -- ours is only the referee.)
//   (2) WRONG CALLING CONVENTION -> stack imbalance, corruption later. Guard: the
//       convention is __thiscall, ECX = this, and BOTH exit paths end in a plain
//       `ret` (no `ret N`), so there are
//       zero stack arguments to get wrong. Emulated as __fastcall(this, edx).
//   (3) BAD `this` POINTER -> access violation. Guard: `this` is a CExoString we
//       construct with the engine's own ctor and destroy with its own dtor on
//       every path (the STAGE 7 lifecycle, already proven). We never hand it a
//       pointer we did not build.
//   (4) ORDERING (push then eval) -- the STAGE 6/8 discipline: eval checks that a
//       string is actually pending; if not it logs an anomaly and returns the
//       sentinel rather than computing on stale data.
// ===========================================================================


static const int  KSE_ESL_VALBUF = 512;
static const int  KSE_ESL_ERR    = -559038737;   // 0xDEADBEEF signed: sentinel
static char       g_eslStr[KSE_ESL_VALBUF];      // fixed buffer -> zero DLL heap
static bool       g_eslHave = false;
static volatile LONG g_eslCalls = 0;



// THE ENGINE FUNCTION: __thiscall, ECX = CExoString*, no stack args, EAX = length.
typedef int   (__fastcall *KseGetLenFn)  (void* thisptr, void* edx);

static size_t esl_len(const char* s) { size_t n = 0; while (s[n]) ++n; return n; }
static bool   esl_copy(char* d, size_t dsz, const char* s)
{ size_t i = 0; for (; s[i] && i < dsz - 1; ++i) d[i] = s[i]; d[i] = '\0'; return s[i] == '\0'; }

// -------- host 632: void(object,int,string) -- stage the string --------------
extern "C" int __stdcall KseEslPush(int argCount)
{
    if (argCount != 3) { Log("K1SE ANOMALY esl push: argCount=%d (declared 3)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn  getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn  getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseGetFn  getString = reinterpret_cast<KseGetFn>(base + KSE_GET_STRING_RVA);
    KseCtorFn ctor      = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn dtor      = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);

    int discard = 0;                                  // declaration order: object, int, string
    if (!getObject(KseVM(), nullptr, &discard)) { Log("K1SE ANOMALY esl push: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &discard))    { Log("K1SE ANOMALY esl push: get.int failed"); return -1; }

    KseCExoStr s;
    ctor(&s, nullptr);
    int ok = getString(KseVM(), nullptr, &s);
    if (ok) { esl_copy(g_eslStr, sizeof(g_eslStr), s.ptr ? s.ptr : ""); g_eslHave = true; }
    else    { g_eslHave = false; Log("K1SE ANOMALY esl push: get.string failed"); }
    dtor(&s, nullptr);                                // ALWAYS (no-op on {0,0})
    return ok ? 0 : -1;
}

// -------- host 683: int(object,int)->int -- make the ENGINE call -------------
extern "C" int __stdcall KseEslEval(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY esl eval: argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn      getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn      getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseSetIntFn   setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);
    KseCtorFn     ctor      = reinterpret_cast<KseCtorFn>(base + KSE_CEXOSTR_CTOR_RVA);
    KseDtorFn     dtor      = reinterpret_cast<KseDtorFn>(base + KSE_CEXOSTR_DTOR_RVA);
    KseFromCStrFn fromCStr  = reinterpret_cast<KseFromCStrFn>(base + KSE_CEXOSTR_FROMCSTR_RVA);
    KseGetLenFn   engineLen = reinterpret_cast<KseGetLenFn>(base + KSE_CEXOSTR_GETLEN_RVA);

    int discard = 0, opcode = 0;
    if (!getObject(KseVM(), nullptr, &discard)) { Log("K1SE ANOMALY esl eval: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &opcode))     { Log("K1SE ANOMALY esl eval: get.int failed"); return -1; }

    if (!g_eslHave) {   // ordering guard (STAGE 6/8 discipline)
        Log("K1SE ANOMALY esl eval: no pushed string pending (interrupted sequence); sentinel");
        setRetInt(KseVM(), nullptr, KSE_ESL_ERR);
        return 0;
    }
    g_eslHave = false;
    if (opcode == 2) {
        // Self-test channel. The staged string carries the script's summary, so the
        // outcome is visible in kse.log without needing STAGE 8's report hosts
        // (a STAGE 9 build only claims the two hosts above).
        Log("K1SE ENGINECALL SELFTEST: %s", g_eslStr);
        setRetInt(KseVM(), nullptr, 0);
        return 0;
    }
    if (opcode != 1) {
        Log("K1SE ANOMALY esl eval: unknown opcode %d; sentinel", opcode);
        setRetInt(KseVM(), nullptr, KSE_ESL_ERR);
        return 0;
    }

    // ---- THE NEW THING: hand a CExoString to the engine and let IT compute ----
    KseCExoStr s;
    ctor(&s, nullptr);                       // { 0, 0 } -- fresh
    fromCStr(&s, nullptr, g_eslStr);         // engine-allocated copy of our buffer
    int fromEngine = engineLen(&s, nullptr); // <-- the engine function call
    dtor(&s, nullptr);                       // free our copy (matched alloc/free)

    // ---- referee: our own strlen, used ONLY to detect a bad engine result ----
    int ours = (int)esl_len(g_eslStr);
    int result;
    if (fromEngine != ours) {
        Log("K1SE ANOMALY esl eval: engine returned %d but string \"%s\" is %d long -- "
            "engine call is WRONG; sentinel", fromEngine, g_eslStr, ours);
        result = KSE_ESL_ERR;
    } else {
        result = fromEngine;                 // return the ENGINE's value, not ours
        LogDiag("K1SE engine-call GetLength(\"%s\") -> %d (agrees with our %d) [call #%ld]",
            g_eslStr, fromEngine, ours, (long)InterlockedIncrement(&g_eslCalls));
    }
    setRetInt(KseVM(), nullptr, result);
    return 0;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 10 -- GetFeatAcquired: the first KOTOR 2 script function exposed in
// KOTOR 1.
//
// TSL declares `int GetFeatAcquired(int nFeat, object oCreature)`; K1 does not.
// K1's engine nevertheless contains the exact query, because K1's own GetHasFeat
// (routine 285) reads the same feat list. Note that 0x005a6630 (pure membership) is
// a DIFFERENT function from GetHasFeat (membership + usability).
//
// SAFETY -- the core argument. This handler replicates the resolution chain of
// routine 285's shipped handler EXACTLY, step for step, and differs only in the
// final call. It invents no traversal of its own. Consequently any object that
// could fault here would equally fault stock GetHasFeat, which the retail game
// calls constantly. On top of that every step is null-checked and the resolver's
// success byte is compared against the engine's own global (never a hardcoded
// constant), so a structural surprise degrades to a logged miss, not a crash.
//
// READ-ONLY. Nothing in this path writes engine memory. Worst case is a bad read.
//
// FAILURE POLICY, chosen to keep the referee test meaningful:
//   * Structural anomalies (null root, accessor failure) -> log ANOMALY, return
//     the sentinel. These mean KSE is broken and must be loud.
//   * "Object is not a creature" / "object id not found" -> return FALSE (0),
//     WITHOUT the sentinel. That is exactly what routine 285 does (it initialises
//     its result to 0 and only sets 1 on the success path), so mirroring it keeps
//     our answer comparable to the referee's on every input.
// ===========================================================================

static volatile LONG g_featCalls = 0;
static const int KSE_FEAT_ERR = -559038737;   // 0xDEADBEEF signed


// Engine functions, all __thiscall emulated as __fastcall (ECX = this, EDX unused):
typedef void* (__fastcall *KseObjTableFn) (void* thisptr, void* edx);                       // 0x4aed70, RET 0
typedef unsigned char (__fastcall *KseResolveFn)(void* thisptr, void* edx, int id, void** out); // 0x4d8230, RET 8
typedef void* (__fastcall *KseVGetStatsFn)(void* thisptr, void* edx);                       // virtual [vt+0x30]
typedef int   (__fastcall *KseFeatQueryFn)(void* thisptr, void* edx, int nFeat);            // 0x5a6630, RET 4

// The channel-agnostic seam. Returns 1/0, or leaves *ok false on a structural
// anomaly (caller then returns the sentinel).
static int Kse10_Core(int objectId, int nFeat, int* ok)
{
    *ok = 1;
    BYTE* base = KseImageBase();

    // (a) the object root -> seed. Null here means the engine is not in a state
    //     we understand; that is an anomaly, not a "creature lacks the feat".
    void* root = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!root) { Log("K1SE ANOMALY feat: object root is null"); *ok = 0; return KSE_FEAT_ERR; }
    void* seed = *reinterpret_cast<void**>(static_cast<BYTE*>(root) + 8);
    if (!seed) { Log("K1SE ANOMALY feat: object seed is null"); *ok = 0; return KSE_FEAT_ERR; }

    // (b) seed -> object table
    KseObjTableFn getTable = reinterpret_cast<KseObjTableFn>(base + KSE_OBJ_TABLE_GET_RVA);
    void* table = getTable(seed, nullptr);
    if (!table) { Log("K1SE ANOMALY feat: object table is null"); *ok = 0; return KSE_FEAT_ERR; }

    // (c) resolve the object id. The handler compares the returned byte against
    //     the engine's own success constant, so we read that global too rather
    //     than assuming its value.
    KseResolveFn resolve = reinterpret_cast<KseResolveFn>(base + KSE_OBJ_RESOLVE_RVA);
    void* obj = nullptr;
    unsigned char rc = resolve(table, nullptr, objectId, &obj);
    unsigned char okByte = *reinterpret_cast<unsigned char*>(base + KSE_RESOLVE_OK_RVA);
    if (rc != okByte || !obj) return 0;   // not found -> FALSE, same as routine 285

    // (d) creature stats via the vtable slot routine 285 uses. NULL for anything
    //     that is not a creature -- BioWare's own type guard, reused as-is.
    void** vtbl = *reinterpret_cast<void***>(obj);
    if (!vtbl) return 0;
    void* slot = vtbl[KSE_VT_GETSTATS_OFF / 4];
    if (!slot) return 0;
    KseVGetStatsFn getStats = reinterpret_cast<KseVGetStatsFn>(slot);
    void* stats = getStats(obj, nullptr);
    if (!stats) return 0;                 // not a creature -> FALSE

    // (e) the feat list, then (f) the membership query itself.
    void* featList = *reinterpret_cast<void**>(static_cast<BYTE*>(stats) + KSE_STATS_FEATLIST_OFF);
    if (!featList) return 0;
    KseFeatQueryFn query = reinterpret_cast<KseFeatQueryFn>(base + KSE_FEAT_QUERY_RVA);
    return query(featList, nullptr, nFeat) ? 1 : 0;
}

// -------- host 685: int(object, int) -> int ---------------------------------
extern "C" int __stdcall KseFeatAcquired(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY feat: argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn    getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn    getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseSetIntFn setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);

    // Declaration order: the host is (object oFollower, int nSound), so the
    // object is read first. Our wrapper passes (oCreature, nFeat) in that order.
    int objectId = 0, nFeat = 0;
    if (!getObject(KseVM(), nullptr, &objectId)) { Log("K1SE ANOMALY feat: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nFeat))       { Log("K1SE ANOMALY feat: get.int failed"); return -1; }

    // Self-test channel: real K1 feat ids are >= 1, so a negative id is
    // unambiguously the test reporting its bitmask rather than a feat query.
    if (nFeat < 0) {
        Log("K1SE FEAT SELFTEST: fails-bitmask=%d (0 = every check passed)", -nFeat - 1);
        setRetInt(KseVM(), nullptr, 0);
        return 0;
    }

    int ok = 1;
    int result = Kse10_Core(objectId, nFeat, &ok);
    if (!ok) { setRetInt(KseVM(), nullptr, KSE_FEAT_ERR); return 0; }

    LogDiag("K1SE GetFeatAcquired(feat=%d, obj=0x%08X) -> %d [call #%ld]",
        nFeat, (unsigned)objectId, result, (long)InterlockedIncrement(&g_featCalls));
    setRetInt(KseVM(), nullptr, result);
    return 0;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 11 -- AdjustCreatureSkills: the FIRST WRITE-type operation.
//
// Every prior engine interaction only READ. This one CHANGES creature state that
// is serialised into the save, so the target is the safest write available rather
// than the most-demanded one (see offsets.h for why skills and not feats).
//
// WHAT IT WRITES: exactly one signed byte, in a fixed slot, in an array the
// engine allocated -- `((BYTE*)*(void**)(statBlock + 0x168))[nSkill]`. There is no
// count to maintain, no capacity to overflow, and no parallel bookkeeping array
// that could be left inconsistent. That is the entire reason this target was
// picked to prove the write pattern.
//
// WHAT COULD GO WRONG, AND THE GUARD FOR EACH:
//   (1) Writing through a bad pointer -> corruption. Guard: the object-resolution
//       chain is byte-for-byte the sequence routine 315's own handler performs
//       (validated in STAGE 10), and EVERY pointer in it is null-checked before
//       use. Any failure logs and returns WITHOUT WRITING.
//   (2) Writing out of bounds -> corrupting whatever follows the skill array.
//       Guard: nSkill is checked against the ENGINE'S OWN bound, the same byte the
//       getter uses (*(BYTE*)([rulesMgr] + 0xab)). If the rules manager pointer is
//       null we REFUSE rather than assume a skill count -- we never invent a bound.
//   (3) Writing a nonsense value -> a broken character. Guard: the result is
//       clamped to [0, KSE_SKILL_RANK_MAX]; the slot is a signed byte so anything
//       above 127 would wrap negative.
//   (4) A non-creature target -> the vtable slot returns NULL, which BioWare's own
//       handlers rely on as the type guard; we check it the same way.
// On ANY guard failing, the handler logs "KSE ANOMALY skill" and performs NO
// write. A refusal is always preferred to a partial or speculative write.
//
// The write is verifiable with no blind spot: stock GetSkillRank reads the very
// byte we set, so the value either moved by exactly the requested amount or it did
// not. (Unlike the feat case, where a half-formed entry still reads as TRUE.)
// ===========================================================================


static const int KSE_SK_ERR = -559038737;
static volatile LONG g_skillWrites = 0;


typedef unsigned char (__fastcall *KseResolveFn)(void* thisptr, void* edx, int objId, void** out);
typedef void* (__fastcall *KseTableGetFn) (void* thisptr, void* edx);
typedef void* (__fastcall *KseVFn)        (void* thisptr, void* edx);

// Resolve a script object id to its creature stat block, replicating routine 315's
// own chain exactly. Returns NULL (never a guess) if any step fails.
static void* Kse11_StatBlock(int objId, const char** why)
{
    BYTE* base = KseImageBase();
    void* root = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!root) { *why = "object root null"; return nullptr; }
    void* seed = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(root) + 8);
    if (!seed) { *why = "object manager null"; return nullptr; }

    KseTableGetFn tableGet = reinterpret_cast<KseTableGetFn>(base + KSE_OBJ_TABLE_GET_RVA);
    void* table = tableGet(seed, nullptr);
    if (!table) { *why = "object table null"; return nullptr; }

    KseResolveFn resolve = reinterpret_cast<KseResolveFn>(base + KSE_OBJ_RESOLVE_RVA);
    void* obj = nullptr;
    unsigned char rc = resolve(table, nullptr, objId, &obj);
    // Compare against the engine's own success byte, exactly as the handler does.
    unsigned char okByte = *reinterpret_cast<unsigned char*>(base + KSE_RESOLVE_OK_RVA);
    if (rc != okByte || !obj) { *why = "object not found"; return nullptr; }

    void** vtbl = *reinterpret_cast<void***>(obj);
    if (!vtbl) { *why = "vtable null"; return nullptr; }
    KseVFn getStats = reinterpret_cast<KseVFn>(vtbl[KSE_VT_GETSTATS_OFF / 4]);
    if (!getStats) { *why = "stats vslot null"; return nullptr; }
    void* stats = getStats(obj, nullptr);
    if (!stats) { *why = "not a creature"; return nullptr; }   // BioWare's own type guard

    void* block = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(stats) + KSE_STATS_FEATLIST_OFF);
    if (!block) { *why = "stat block null"; return nullptr; }
    return block;
}

// The channel-agnostic seam. Returns the NEW rank, or KSE_SK_ERR if it refused.
static int Kse11_Core(void* statBlock, int nSkill, int nAmount)
{
    BYTE* base = KseImageBase();

    // Bound nSkill with the ENGINE'S OWN skill count -- never an invented constant.
    void* rules = *reinterpret_cast<void**>(base + KSE_RULES_MGR_RVA);
    if (!rules) {
        Log("K1SE ANOMALY skill: rules manager null -- refusing to write (no trusted bound)");
        return KSE_SK_ERR;
    }
    unsigned char skillCount = *(reinterpret_cast<BYTE*>(rules) + KSE_RULES_SKILLCOUNT_OFF);
    if (nSkill < 0 || nSkill >= (int)skillCount) {
        Log("K1SE ANOMALY skill: nSkill=%d out of range (engine count=%u); no write",
            nSkill, (unsigned)skillCount);
        return KSE_SK_ERR;
    }

    signed char* ranks = *reinterpret_cast<signed char**>(
        reinterpret_cast<BYTE*>(statBlock) + KSE_STATS_SKILLARRAY_OFF);
    if (!ranks) {
        Log("K1SE ANOMALY skill: skill array null; no write");
        return KSE_SK_ERR;
    }

    int oldRank = (int)ranks[nSkill];
    int newRank = oldRank + nAmount;
    if (newRank < 0) newRank = 0;
    if (newRank > KSE_SKILL_RANK_MAX) newRank = KSE_SKILL_RANK_MAX;

    ranks[nSkill] = (signed char)newRank;      // <-- THE WRITE: one byte, fixed slot
    Log("K1SE AdjustCreatureSkills skill=%d %+d : %d -> %d [write #%ld]",
        nSkill, nAmount, oldRank, newRank, (long)InterlockedIncrement(&g_skillWrites));
    return newRank;
}

// -------- host 684: void SWMG_SetSoundFrequency(object,int,int) --------------
extern "C" int __stdcall KseAdjustSkills(int argCount)
{
    if (argCount != 3) { Log("K1SE ANOMALY skill: argCount=%d (declared 3)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);

    int objId = 0, nSkill = 0, nAmount = 0;    // declaration order: object, int, int
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY skill: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nSkill))   { Log("K1SE ANOMALY skill: get.int (skill) failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nAmount))  { Log("K1SE ANOMALY skill: get.int (amount) failed"); return -1; }

    const char* why = "";
    void* block = Kse11_StatBlock(objId, &why);
    if (!block) {
        Log("K1SE ANOMALY skill: %s; no write performed", why);
        return 0;                               // void host: pop 3, push 0. No write.
    }
    Kse11_Core(block, nSkill, nAmount);
    return 0;
}


#endif

#if KSE_STAGE == 19
// ===========================================================================
// STAGE 12 -- the saving-throw base family. BATCHED on the proven STAGE 11 shape.
//
// STAGE 11 proved fixed-slot writing: write one byte that the engine's own reader
// reads back, and refuse out-of-range input. These targets are the identical
// shape (three consecutive bytes, each contributing LINEARLY to a stock reader),
// so this is repetition of a proven mechanism, not a new risk surface -- the same
// justification that allowed the STAGE 6 math pack to be batched.
//
// FOUR FUNCTIONS, TWO HOSTS:
//   686 (object,int,int) void -> Modify{Fortitude,Reflex,Will}SavingThrowBase
//   687 (object,int)->int     -> KSE_GetSavingThrowBase  (the READ that pairs with
//                                the writes, so scripts can read-modify-write)
//
// See offsets.h for how the byte offsets were located, and for why ability-score
// writes are deliberately NOT in this stage.
//
// GUARDS (same discipline as STAGE 11, and the test EXERCISES each one):
//   * nSave must be one of the three selectors -- anything else refuses.
//   * The object must resolve to a creature (BioWare's own vtable-returns-NULL
//     type guard) -- otherwise refuse.
//   * Every pointer in the resolution chain is null-checked.
//   * The result is clamped to [0,127]; the slot is a signed byte.
// A refusal logs "KSE ANOMALY save" and performs NO write.
// ===========================================================================


static const int KSE_SV_ERR = -559038737;
static volatile LONG g_saveWrites = 0;


typedef unsigned char (__fastcall *KseResolveFn)(void* thisptr, void* edx, int objId, void** out);
typedef void* (__fastcall *KseTableGetFn) (void* thisptr, void* edx);
typedef void* (__fastcall *KseVFn)        (void* thisptr, void* edx);

// Identical to STAGE 11's resolver: byte-for-byte the chain routine 315's own
// handler performs, every pointer checked. Returns NULL rather than any guess.
static void* Kse12_StatBlock(int objId, const char** why)
{
    BYTE* base = KseImageBase();
    void* root = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!root) { *why = "object root null"; return nullptr; }
    void* seed = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(root) + 8);
    if (!seed) { *why = "object manager null"; return nullptr; }
    KseTableGetFn tableGet = reinterpret_cast<KseTableGetFn>(base + KSE_OBJ_TABLE_GET_RVA);
    void* table = tableGet(seed, nullptr);
    if (!table) { *why = "object table null"; return nullptr; }
    KseResolveFn resolve = reinterpret_cast<KseResolveFn>(base + KSE_OBJ_RESOLVE_RVA);
    void* obj = nullptr;
    unsigned char rc = resolve(table, nullptr, objId, &obj);
    unsigned char okByte = *reinterpret_cast<unsigned char*>(base + KSE_RESOLVE_OK_RVA);
    if (rc != okByte || !obj) { *why = "object not found"; return nullptr; }
    void** vtbl = *reinterpret_cast<void***>(obj);
    if (!vtbl) { *why = "vtable null"; return nullptr; }
    KseVFn getStats = reinterpret_cast<KseVFn>(vtbl[KSE_VT_GETSTATS_OFF / 4]);
    if (!getStats) { *why = "stats vslot null"; return nullptr; }
    void* stats = getStats(obj, nullptr);
    if (!stats) { *why = "not a creature"; return nullptr; }
    void* block = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(stats) + KSE_STATS_FEATLIST_OFF);
    if (!block) { *why = "stat block null"; return nullptr; }
    return block;
}

// KSE's selector -> the engine's byte offset. The engine's internal order is
// Fortitude/Will/Reflex (0x1a0/0x1a1/0x1a2), which is NOT the order the script
// constants suggest, so the mapping is centralised here and nowhere else.
static int KseSaveOffset(int nSave)
{
    switch (nSave) {
    case KSE_SAVE_FORT:   return KSE_STATS_SAVE_FORT_OFF;
    case KSE_SAVE_REFLEX: return KSE_STATS_SAVE_REFLEX_OFF;
    case KSE_SAVE_WILL:   return KSE_STATS_SAVE_WILL_OFF;
    default:              return -1;
    }
}
static const char* KseSaveName(int nSave)
{
    switch (nSave) {
    case KSE_SAVE_FORT: return "FORT"; case KSE_SAVE_REFLEX: return "REFLEX";
    case KSE_SAVE_WILL: return "WILL"; default: return "?";
    }
}

// The channel-agnostic seam. Returns the new base, or KSE_SV_ERR on refusal.
static int Kse12_Core(void* statBlock, int nSave, int nAmount, bool write)
{
    int off = KseSaveOffset(nSave);
    if (off < 0) {
        Log("K1SE ANOMALY save: nSave=%d invalid (expect 0=FORT,1=REFLEX,2=WILL); no %s",
            nSave, write ? "write" : "read");
        return KSE_SV_ERR;
    }
    signed char* slot = reinterpret_cast<signed char*>(statBlock) + off;
    int oldVal = (int)*slot;
    if (!write) {
        LogDiag("K1SE GetSavingThrowBase %s -> %d", KseSaveName(nSave), oldVal);
        return oldVal;
    }
    int newVal = oldVal + nAmount;
    if (newVal < 0) newVal = 0;
    if (newVal > KSE_SAVE_BASE_MAX) newVal = KSE_SAVE_BASE_MAX;
    *slot = (signed char)newVal;               // <-- THE WRITE: one byte, fixed slot
    Log("K1SE ModifySavingThrowBase %s %+d : %d -> %d [write #%ld]",
        KseSaveName(nSave), nAmount, oldVal, newVal, (long)InterlockedIncrement(&g_saveWrites));
    return newVal;
}

// -------- host 686: void(object,int,int) -- the three Modify* functions --------
extern "C" int __stdcall KseSaveWrite(int argCount)
{
    if (argCount != 3) { Log("K1SE ANOMALY save: argCount=%d (declared 3)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    int objId = 0, nSave = 0, nAmount = 0;      // declaration order: object, int, int
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY save: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nSave))    { Log("K1SE ANOMALY save: get.int (save) failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nAmount))  { Log("K1SE ANOMALY save: get.int (amount) failed"); return -1; }

    const char* why = "";
    void* block = Kse12_StatBlock(objId, &why);
    if (!block) { Log("K1SE ANOMALY save: %s; no write performed", why); return 0; }
    Kse12_Core(block, nSave, nAmount, true);
    return 0;
}

// -------- host 687: int(object,int)->int -- the paired base reader -------------
extern "C" int __stdcall KseSaveRead(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY save: read argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn    getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn    getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseSetIntFn setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);
    int objId = 0, nSave = 0;
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY save: read get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nSave))    { Log("K1SE ANOMALY save: read get.int failed"); return -1; }

    const char* why = "";
    void* block = Kse12_StatBlock(objId, &why);
    if (!block) {
        Log("K1SE ANOMALY save: %s; read returns sentinel", why);
        setRetInt(KseVM(), nullptr, KSE_SV_ERR);
        return 0;
    }
    setRetInt(KseVM(), nullptr, Kse12_Core(block, nSave, 0, false));
    return 0;
}


// Earlier feat-grant stages (an array-B grant, a record-container grant, and their
// read-only save-path observers) were here and have been removed. Neither grant
// route reached the save file; the shipping grant path is KSE_GrantFeatArrayA
// (host 618, STAGE 17), below.

// ===========================================================================
// KOTOR AP ADDITION (not part of upstream K1SE) -- SetCreatureField, host 688.
//
// Same fixed-slot write discipline as AdjustCreatureSkills/the saving-throw
// writes above: one byte or int written to a location the engine's own reader
// already reads, no lists, no counts, no capacity. Unlike those, the offsets
// here were confirmed empirically via live differential memory scanning
// against a running game (not derived from disassembly) -- see this
// project's own memory notes for the full test history. Resolver is
// byte-for-byte the same chain every other host in this file uses.
// ===========================================================================
static volatile LONG g_fieldWrites = 0;

// KseResolveObj -- the FIRST half of the object-resolution chain: turns an
// NWScript object id into the raw, resolved engine object ("obj" in this
// project's own research notes -- see FutureDesign.md's HP research entry).
// This is NOT the creature's stat block yet -- KseField_Obj/KseField_StatBlock
// below each take it one step further, to whichever destination they need.
// Split out 2026-09-06 so Current HP (which lives on "obj" itself, at
// +0xDC -- confirmed live, see FutureDesign.md) has its own real resolver,
// not just a comment fragment of KseField_StatBlock's.
static void* KseResolveObj(int objId, const char** why)
{
    BYTE* base = KseImageBase();
    void* root = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!root) { *why = "object root null"; return nullptr; }
    void* seed = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(root) + 8);
    if (!seed) { *why = "object manager null"; return nullptr; }
    KseTableGetFn tableGet = reinterpret_cast<KseTableGetFn>(base + KSE_OBJ_TABLE_GET_RVA);
    void* table = tableGet(seed, nullptr);
    if (!table) { *why = "object table null"; return nullptr; }
    KseResolveFn resolve = reinterpret_cast<KseResolveFn>(base + KSE_OBJ_RESOLVE_RVA);
    void* obj = nullptr;
    unsigned char rc = resolve(table, nullptr, objId, &obj);
    unsigned char okByte = *reinterpret_cast<unsigned char*>(base + KSE_RESOLVE_OK_RVA);
    if (rc != okByte || !obj) { *why = "object not found"; return nullptr; }
    return obj;
}

// KseField_Obj -- the raw resolved object itself, no further dereferencing.
// Current HP lives here directly at +0xDC (confirmed live, 2026-09-06 --
// see FutureDesign.md's HP research entry: definitively NOT on statBlock,
// NOT computed like Max HP, a real static field on THIS object).
static void* KseField_Obj(int objId, const char** why)
{
    return KseResolveObj(objId, why);
}

static void* KseField_StatBlock(int objId, const char** why)
{
    void* obj = KseResolveObj(objId, why);
    if (!obj) return nullptr;
    void** vtbl = *reinterpret_cast<void***>(obj);
    if (!vtbl) { *why = "vtable null"; return nullptr; }
    BYTE* base = KseImageBase();
    KseVFn getStats = reinterpret_cast<KseVFn>(vtbl[KSE_VT_GETSTATS_OFF / 4]);
    if (!getStats) { *why = "stats vslot null"; return nullptr; }
    void* stats = getStats(obj, nullptr);
    if (!stats) { *why = "not a creature"; return nullptr; }   // BioWare's own type guard
    void* block = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(stats) + KSE_STATS_FEATLIST_OFF);
    if (!block) { *why = "stat block null"; return nullptr; }
    return block;
}

// nFieldType -> byte offset + write width. Centralised here, same reasoning as
// KseSaveOffset: one place maps the API's selector numbering to real offsets.
static int KseFieldOffset(int nFieldType)
{
    switch (nFieldType) {
    case KSE_FIELD_CLASS0_TYPE:  return KSE_STATS_CLASS0_TYPE_OFF;
    case KSE_FIELD_CLASS0_LEVEL: return KSE_STATS_CLASS0_LEVEL_OFF;
    case KSE_FIELD_CLASS1_TYPE:  return KSE_STATS_CLASS1_TYPE_OFF;
    case KSE_FIELD_CLASS1_LEVEL: return KSE_STATS_CLASS1_LEVEL_OFF;
    case KSE_FIELD_FORCE:        return KSE_STATS_FORCE_OFF;
    default:                     return -1;
    }
}
static const char* KseFieldName(int nFieldType)
{
    switch (nFieldType) {
    case KSE_FIELD_CLASS0_TYPE:  return "CLASS0_TYPE";
    case KSE_FIELD_CLASS0_LEVEL: return "CLASS0_LEVEL";
    case KSE_FIELD_CLASS1_TYPE:  return "CLASS1_TYPE";
    case KSE_FIELD_CLASS1_LEVEL: return "CLASS1_LEVEL";
    case KSE_FIELD_FORCE:        return "FORCE";
    default:                     return "?";
    }
}

static void KseField_Core(void* statBlock, int nFieldType, int nValue)
{
    int off = KseFieldOffset(nFieldType);
    if (off < 0) {
        Log("K1SE ANOMALY field: nFieldType=%d invalid; no write", nFieldType);
        return;
    }
    BYTE* slot = reinterpret_cast<BYTE*>(statBlock) + off;
    if (nFieldType == KSE_FIELD_FORCE) {
        int oldVal = *reinterpret_cast<int*>(slot);
        *reinterpret_cast<int*>(slot) = nValue;    // <-- THE WRITE: 4-byte int, fixed slot
        Log("K1SE SetCreatureField %s : %d -> %d [write #%ld]",
            KseFieldName(nFieldType), oldVal, nValue, (long)InterlockedIncrement(&g_fieldWrites));
    } else {
        int oldVal = (int)*slot;
        *slot = (BYTE)nValue;                      // <-- THE WRITE: one byte, fixed slot
        Log("K1SE SetCreatureField %s : %d -> %d [write #%ld]",
            KseFieldName(nFieldType), oldVal, nValue, (long)InterlockedIncrement(&g_fieldWrites));
    }
}

// KOTOR AP ADDITION (2026-09-06): Add/Remove Force Power, sharing host 688
// rather than claiming a new opcode -- see offsets.h's KSE_FIELD_ADD_FORCE_POWER
// / KSE_FIELD_REMOVE_FORCE_POWER comments for the field-type contract. Operates
// on the confirmed known-powers array record (statBlock+0x8C+category*40).
// Add does its own search-before-append (skip if already known -- a real
// duplicate-grant test on 2026-09-06 confirmed this would otherwise be
// harmless anyway, but skipping keeps count/capacity honest). Remove
// safely no-ops if the id isn't found, as explicitly required.
static void KseForcePowerOp(void* statBlock, int nFieldType, int spellId)
{
    BYTE* record = reinterpret_cast<BYTE*>(statBlock) + KSE_STATS_CATEGORY_TABLE_OFF
                 + KSE_FORCE_POWER_CATEGORY * KSE_STATS_CATEGORY_STRIDE;
    int* arrayPtr   = *reinterpret_cast<int**>(record + KSE_CATEGORY_PTR_OFF);
    int* countPtr   = reinterpret_cast<int*>(record + KSE_CATEGORY_COUNT_OFF);
    int  capacity   = *reinterpret_cast<int*>(record + KSE_CATEGORY_CAP_OFF);
    int  count      = *countPtr;

    if (!arrayPtr) {
        Log("K1SE ANOMALY forcepowerop: known-powers array ptr null; no write");
        return;
    }

    int foundIndex = -1;
    for (int i = 0; i < count; i++) {
        if (arrayPtr[i] == spellId) { foundIndex = i; break; }
    }

    if (nFieldType == KSE_FIELD_ADD_FORCE_POWER) {
        if (foundIndex >= 0) {
            Log("K1SE SetCreatureField ADD_FORCE_POWER: spell %d already known at index %d; no-op",
                spellId, foundIndex);
            return;
        }
        if (count >= capacity) {
            Log("K1SE ANOMALY forcepowerop: known-powers list full (count=%d cap=%d); cannot add spell %d",
                count, capacity, spellId);
            return;
        }
        arrayPtr[count] = spellId;
        *countPtr = count + 1;
        Log("K1SE SetCreatureField ADD_FORCE_POWER: spell %d added at index %d, count %d -> %d [write #%ld]",
            spellId, count, count, count + 1, (long)InterlockedIncrement(&g_fieldWrites));
    } else { // KSE_FIELD_REMOVE_FORCE_POWER
        if (foundIndex < 0) {
            Log("K1SE SetCreatureField REMOVE_FORCE_POWER: spell %d not known; no-op", spellId);
            return;
        }
        for (int i = foundIndex; i < count - 1; i++) {
            arrayPtr[i] = arrayPtr[i + 1];
        }
        *countPtr = count - 1;
        Log("K1SE SetCreatureField REMOVE_FORCE_POWER: spell %d removed from index %d, count %d -> %d [write #%ld]",
            spellId, foundIndex, count, count - 1, (long)InterlockedIncrement(&g_fieldWrites));
    }
}

// -------- host 688: void SWMG_SetSoundVolume(object,int,int) -------------------
extern "C" int __stdcall KseSetCreatureField(int argCount)
{
    if (argCount != 3) { Log("K1SE ANOMALY field: argCount=%d (declared 3)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    int objId = 0, nFieldType = 0, nValue = 0;   // declaration order: object, int, int
    if (!getObject(KseVM(), nullptr, &objId))    { Log("K1SE ANOMALY field: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nFieldType))  { Log("K1SE ANOMALY field: get.int (fieldType) failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nValue))      { Log("K1SE ANOMALY field: get.int (value) failed"); return -1; }

    const char* why = "";

    if (nFieldType == KSE_FIELD_CURRENT_HP) {
        void* obj = KseField_Obj(objId, &why);
        if (!obj) { Log("K1SE ANOMALY field: %s; no write performed", why); return 0; }
        BYTE* slot = reinterpret_cast<BYTE*>(obj) + KSE_OBJ_CURRENT_HP_OFF;
        int oldVal = *reinterpret_cast<int*>(slot);
        *reinterpret_cast<int*>(slot) = nValue;
        Log("K1SE SetCreatureField CURRENT_HP : %d -> %d [write #%ld]",
            oldVal, nValue, (long)InterlockedIncrement(&g_fieldWrites));
        return 0;
    }

    if (nFieldType == KSE_FIELD_ADD_FORCE_POWER || nFieldType == KSE_FIELD_REMOVE_FORCE_POWER) {
        void* block = KseField_StatBlock(objId, &why);
        if (!block) { Log("K1SE ANOMALY field: %s; no write performed", why); return 0; }
        KseForcePowerOp(block, nFieldType, nValue);
        return 0;
    }

    void* block = KseField_StatBlock(objId, &why);
    if (!block) { Log("K1SE ANOMALY field: %s; no write performed", why); return 0; }
    KseField_Core(block, nFieldType, nValue);
    return 0;
}

// -------- host 617: int SWMG_GetMaxHitPoints(object oFollower)->int ------------
// KOTOR AP ADDITION (2026-09-06): Current HP getter -- see offsets.h's
// KSE_OBJ_CURRENT_HP_OFF comment for the confirmed offset/derivation. Uses
// KseField_Obj() (the raw resolved object), NOT KseField_StatBlock() --
// Current HP is one step earlier in the resolution chain than every other
// field this project reads/writes. Returns -1 if the object can't be
// resolved (never dereferences a null).
extern "C" int __stdcall KseGetCurrentHP(int argCount)
{
    if (argCount != 1) { Log("K1SE ANOMALY getcurrenthp: argCount=%d (declared 1)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseSetIntFn setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);
    int objId = 0;
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY getcurrenthp: get.object failed"); return -1; }

    const char* why = "";
    void* obj = KseField_Obj(objId, &why);
    if (!obj) {
        Log("K1SE ANOMALY getcurrenthp: %s; returning -1", why);
        setRetInt(KseVM(), nullptr, -1);
        return 0;
    }
    int hp = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(obj) + KSE_OBJ_CURRENT_HP_OFF);
    setRetInt(KseVM(), nullptr, hp);
    return 0;
}

// KseDumpStatBlock (host 638) and KseTestCreditsChain (host 606) -- both
// TEMPORARY research diagnostics -- were removed 2026-09-06 once the
// research they supported concluded and shipped as real natives/offsets.
// Archived verbatim at
// extender/research_archive/kse_hook_temp_natives_2026-09-06.cpp.txt.

// Shared resolver for the confirmed credits chain -- KSE_OBJ_ROOT_RVA ->
// seed -> KSE_OBJ_TABLE_GET_ALT_RVA(seed) -> pRes. Used by KseSetCredits's
// real write (below); the old KseTestCreditsChain diagnostic that first
// exercised this chain inline is archived (see comment above). Returns
// nullptr and sets *why on any failure; never dereferences a null.
static void* KseResolveCreditsRes(const char** why)
{
    BYTE* base = KseImageBase();
    void* objRoot = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!objRoot) { *why = "objRoot null"; return nullptr; }
    void* seed = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(objRoot) + 8);
    if (!seed) { *why = "seed null"; return nullptr; }
    typedef void* (__fastcall *KseObjTableGetFn)(void* thisptr, void* edx);
    KseObjTableGetFn getRes = reinterpret_cast<KseObjTableGetFn>(base + KSE_OBJ_TABLE_GET_ALT_RVA);
    void* pRes = getRes(seed, nullptr);
    if (!pRes) { *why = "pRes null"; return nullptr; }
    return pRes;
}

// -------- host 683: int SWMG_GetSoundFrequency(object,int)->int --------
// The real, write-capable credits native (see offsets.h's
// KSE_SET_CREDITS_ID comment). Resolves pRes via the confirmed chain and
// writes nValue directly to [pRes+0xFC], returning the value read back
// from that same address immediately after the write -- a genuine
// confirmation the write landed, not just an echo of the input. Returns a
// distinct negative sentinel on any failure along the chain.
extern "C" int __stdcall KseSetCredits(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY setcredits: argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn    getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn    getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseSetIntFn setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);

    int discard = 0, nValue = 0;
    if (!getObject(KseVM(), nullptr, &discard)) { Log("K1SE ANOMALY setcredits: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nValue))     { Log("K1SE ANOMALY setcredits: get.int (value) failed"); return -1; }

    const char* why = "";
    void* pRes = KseResolveCreditsRes(&why);
    if (!pRes) {
        Log("K1SE setcredits: %s; no write performed", why);
        setRetInt(KseVM(), nullptr, -1);
        return 0;
    }

    int* slot = reinterpret_cast<int*>(reinterpret_cast<BYTE*>(pRes) + 0xFC);
    int before = *slot;
    *slot = nValue;
    int after = *slot;
    Log("K1SE SETCREDITS pRes=%p %d -> %d (requested %d) [write #%ld]",
        pRes, before, after, nValue, (long)InterlockedIncrement(&g_fieldWrites));
    setRetInt(KseVM(), nullptr, after);
    return 0;
}

#endif

#if KSE_STAGE == 17 || KSE_STAGE == 18 || KSE_STAGE == 19
// ===========================================================================
// STAGE 18 adds REMOVAL to STAGE 17's grant+read, on one further host (634).
// Everything below is STAGE 17's instrument UNCHANGED -- same resolver, same
// gates, same BEFORE/AFTER contents logging -- because the removal result is
// only trustworthy if the thing measuring it is the thing already proven. The
// STAGE 17 build's log format is preserved byte-for-byte via KSE_ST_TAG, so a
// STAGE 17 log and a STAGE 18 log are never confusable.
//
// STAGE 18 -- REMOVE from array A by DRAIN-AND-REBUILD. See offsets.h's
// KSE_REMOVEA_ID block for why this shape and not shift-in-place, what part of
// it is a direct KSE write rather than an engine call, and the transient-empty
// assumption it rests on.
// ===========================================================================
//
// STAGE 17 -- the ARRAY-A grant.
//
// This grants into ARRAY A -- the array the loader fills, the membership test scans
// first, the prerequisite-resolver reads, and the aggregate "FeatList" is built from
// -- via the engine's OWN complete adder (KSE_ARRAYA_ADD_RVA).
//
// TWO HOSTS, both int(object,int)-shaped:
//   618  KseArrayA_Grant   -- the A-grant. VOID host, so no VM return is set;
//        the script reads back via 685 in the same pass, so a silent no-op is
//        distinguishable from a grant that fired.
//   685  KseFeatRead       -- GetFeatAcquired, reused. Reports which array holds
//        the feat and array A's ptr/count.
//
// A-ONLY, DELIBERATELY. Array B is NOT written.
//
// The handler logs the full id lists of A and B plus all three {ptr,count,capacity}
// triples on every grant/read. It REFUSES to grant if a list the grant will actually
// TOUCH is full, so the grant never runs through the array-grow path. Array A is
// always touched; the use-counter list is touched only when the feat row's UsesPerDay
// byte (+0x33) is non-zero, and that column is empty in every KOTOR feat -- so for a
// passive feat only array A's headroom is required.
// ===========================================================================


// Log tag: STAGE 17 and 18 lines are tagged at compile time so their logs are never
// confusable.
#if KSE_STAGE == 18 || KSE_STAGE == 19
#define KSE_ST_TAG "ST18"
#else
#define KSE_ST_TAG "ST17"
#endif

static const int KSE_FT_ERR = -559038737;
// Non-static so the worker thread (dllmain.cpp) can log the totals unconditionally.
volatile LONG g_granta = 0;
volatile LONG g_areads = 0;
#if KSE_STAGE == 18 || KSE_STAGE == 19
volatile LONG g_removea = 0;
#endif


typedef unsigned char (__fastcall *KseResolveFn)(void* thisptr, void* edx, int objId, void** out);
typedef void* (__fastcall *KseTableGetFn) (void* thisptr, void* edx);
typedef void* (__fastcall *KseVFn)        (void* thisptr, void* edx);
typedef int   (__fastcall *KseFeatHasFn)  (void* thisptr, void* edx, int nFeat);
typedef void  (__fastcall *KseArrayAAddFn)(void* thisptr, void* edx, int nFeat);   // 0x005aa810
typedef void* (__fastcall *KseFeatRowFn)  (void* thisptr, void* edx, int nFeat);   // 0x00550c00

// The creature-resolution chain, every pointer checked.
static bool KseResolveCreature(int objId, void** outObj, void** outStats,
                               void** outBlock, const char** why)
{
    *outObj = nullptr; *outStats = nullptr; *outBlock = nullptr;
    BYTE* base = KseImageBase();
    void* root = *reinterpret_cast<void**>(base + KSE_OBJ_ROOT_RVA);
    if (!root) { *why = "object root null"; return false; }
    void* seed = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(root) + 8);
    if (!seed) { *why = "object manager null"; return false; }
    KseTableGetFn tableGet = reinterpret_cast<KseTableGetFn>(base + KSE_OBJ_TABLE_GET_RVA);
    void* table = tableGet(seed, nullptr);
    if (!table) { *why = "object table null"; return false; }
    KseResolveFn resolve = reinterpret_cast<KseResolveFn>(base + KSE_OBJ_RESOLVE_RVA);
    void* obj = nullptr;
    unsigned char rc = resolve(table, nullptr, objId, &obj);
    unsigned char okByte = *reinterpret_cast<unsigned char*>(base + KSE_RESOLVE_OK_RVA);
    if (rc != okByte || !obj) { *why = "object not found"; return false; }
    void** vtbl = *reinterpret_cast<void***>(obj);
    if (!vtbl) { *why = "vtable null"; return false; }
    KseVFn getStats = reinterpret_cast<KseVFn>(vtbl[KSE_VT_GETSTATS_OFF / 4]);
    if (!getStats) { *why = "stats vslot null"; return false; }
    void* stats = getStats(obj, nullptr);
    if (!stats) { *why = "not a creature"; return false; }
    void* block = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(stats) + KSE_STATS_FEATLIST_OFF);
    if (!block) { *why = "stat block null"; return false; }
    *outObj = obj; *outStats = stats; *outBlock = block;
    return true;
}

static int KseFeatPresent(void* statBlock, int nFeat)   // engine membership test (scans A AND B)
{
    KseFeatHasFn has = reinterpret_cast<KseFeatHasFn>(KseImageBase() + KSE_FEAT_QUERY_RVA);
    return has(statBlock, nullptr, nFeat) ? 1 : 0;
}

// Scan ONE embedded list (WORD ids, `stride` bytes each) for a feat id. Capped so a
// garbage count cannot run away.
static bool KseFeatInList(void* sb, int ptrOff, int cntOff, int stride, int feat)
{
    BYTE* base = reinterpret_cast<BYTE*>(sb);
    BYTE* arr  = *reinterpret_cast<BYTE**>(base + ptrOff);
    int   count = *reinterpret_cast<int*>(base + cntOff);
    if (!arr || count <= 0) return false;
    int lim = count > 4096 ? 4096 : count;
    for (int i = 0; i < lim; ++i)
        if (*reinterpret_cast<unsigned short*>(arr + (size_t)i * stride) == (unsigned short)feat)
            return true;
    return false;
}

// Minimal decimal formatter -- no CRT/user32, so the same helpers are safe if ever
// reused on the shutdown path.
static size_t KseDec(unsigned v, char* b)
{
    char t[12]; int n = 0;
    if (!v) t[n++] = '0';
    while (v) { t[n++] = (char)('0' + v % 10); v /= 10; }
    for (int i = 0; i < n; ++i) b[i] = t[n - 1 - i];
    return (size_t)n;
}

// "[a,b,c]" (up to KSE_IDLIST_CAP ids, then ",...") from a {ptr,count} WORD list.
#define KSE_IDLIST_CAP 96
static void KseIdList(void* sb, int ptrOff, int cntOff, int stride, char* out, size_t outsz)
{
    BYTE* base = reinterpret_cast<BYTE*>(sb);
    BYTE* arr  = *reinterpret_cast<BYTE**>(base + ptrOff);
    int   count = *reinterpret_cast<int*>(base + cntOff);
    size_t pos = 0;
    if (pos < outsz - 1) out[pos++] = '[';
    if (arr && count > 0) {
        int lim = count > KSE_IDLIST_CAP ? KSE_IDLIST_CAP : count;
        for (int i = 0; i < lim; ++i) {
            if (i && pos < outsz - 1) out[pos++] = ',';
            unsigned short id = *reinterpret_cast<unsigned short*>(arr + (size_t)i * stride);
            char num[12]; size_t n = KseDec((unsigned)id, num);
            for (size_t k = 0; k < n && pos < outsz - 1; ++k) out[pos++] = num[k];
        }
        if (lim < count) {
            const char* more = ",...";
            for (int k = 0; more[k] && pos < outsz - 1; ++k) out[pos++] = more[k];
        }
    }
    if (pos < outsz - 1) out[pos++] = ']';
    out[pos] = '\0';
}

// The instrument: log all three triples and the FULL id lists of A and B.
static void KseLogStatFeats(void* sb, const char* when)
{
    BYTE* b = reinterpret_cast<BYTE*>(sb);
    char aIds[512], bIds[512], uIds[512];
    KseIdList(sb, KSE_SB_FEATA_PTR_OFF,  KSE_SB_FEATA_COUNT_OFF,  2, aIds, sizeof(aIds));
    KseIdList(sb, KSE_SB_FEATB_PTR_OFF,  KSE_SB_FEATB_COUNT_OFF,  2, bIds, sizeof(bIds));
    KseIdList(sb, KSE_SB_USECTR_PTR_OFF, KSE_SB_USECTR_COUNT_OFF, 4, uIds, sizeof(uIds));
    LogDiag("K1SE " KSE_ST_TAG " %s  A  ptr=%p count=%d cap=%d ids=%s", when,
        *reinterpret_cast<void**>(b + KSE_SB_FEATA_PTR_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_FEATA_COUNT_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_FEATA_CAP_OFF), aIds);
    LogDiag("K1SE " KSE_ST_TAG " %s  UC ptr=%p count=%d cap=%d ids=%s", when,
        *reinterpret_cast<void**>(b + KSE_SB_USECTR_PTR_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_USECTR_COUNT_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_USECTR_CAP_OFF), uIds);
    LogDiag("K1SE " KSE_ST_TAG " %s  B  ptr=%p count=%d cap=%d ids=%s", when,
        *reinterpret_cast<void**>(b + KSE_SB_FEATB_PTR_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_FEATB_COUNT_OFF),
        *reinterpret_cast<int*>(b + KSE_SB_FEATB_CAP_OFF), bIds);
}

// -------- host 618: void(object,int) -- grant to array A ----------------------
extern "C" int __stdcall KseArrayA_Grant(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY granta: argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    int objId = 0, nFeat = 0;
    // Consume BOTH args even on failure -- a void routine pushes no return, so the
    // VM stack is balanced only if the two pushed args are read.
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY granta: get.object failed"); return 0; }
    if (!getInt(KseVM(), nullptr, &nFeat))    { Log("K1SE ANOMALY granta: get.int failed"); return 0; }

    void *obj = nullptr, *stats = nullptr, *block = nullptr;
    const char* why = "";
    if (!KseResolveCreature(objId, &obj, &stats, &block, &why)) {
        Log("K1SE ANOMALY granta: REFUSED reason=\"%s\" feat=%d; nothing written", why, nFeat);
        return 0;  // void host: no setRetInt
    }
    // 0x005aa810 fetches the rules manager itself and does NOT null-check it.
    void* rules = *reinterpret_cast<void**>(base + KSE_RULES_MGR_RVA);
    if (!rules) { Log("K1SE ANOMALY granta: rules manager null; no grant"); return 0; }

    Log("K1SE " KSE_ST_TAG " GrantA feat=%d obj=%p stats=%p (obj==stats:%d)",
        nFeat, obj, stats, obj == stats ? 1 : 0);
    if (obj != stats)
        Log("K1SE ANOMALY granta: obj=%p != stats=%p -- 3.28 identity does NOT hold; proceeding with stats", obj, stats);
    KseLogStatFeats(block, "BEFORE");

    // Already in array A? The adder's dedup would no-op -- no append, no realloc.
    if (KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, nFeat)) {
        Log("K1SE " KSE_ST_TAG " GrantA feat=%d : already in array A -> no-op (no grant, no realloc)", nFeat);
        return 0;
    }

    // CAPACITY HEADROOM. Refuse if a list the grant will actually TOUCH is full, so
    // the persistence test never runs through an untested allocator path. The guard
    // is gated per-list on what the array-A adder will write:
    //   - array A: always touched by a valid grant -> always checked.
    //   - use-counter list: touched ONLY when the feat row's UsesPerDay byte (+0x33)
    //     is non-zero. That byte is 0 for every KOTOR feat, so the earlier
    //     unconditional check refused every passive grant against the empty
    //     (0/0/0) use-counter list -- a bug. Read the row and gate accordingly.
    // An invalid id (row NULL) touches NEITHER list -- the adder self-rejects -- so
    // no capacity gate applies; the call proceeds deliberately (this is A0's path).
    int aCount = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_COUNT_OFF);
    int aCap   = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_CAP_OFF);
    int uCount = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_USECTR_COUNT_OFF);
    int uCap   = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_USECTR_CAP_OFF);
    KseFeatRowFn rowFn = reinterpret_cast<KseFeatRowFn>(base + KSE_FEAT_ROWLOOKUP_RVA);
    void* featRow = rowFn(rules, nullptr, nFeat);
    bool invalidId = (featRow == nullptr);
    if (invalidId) {
        Log("K1SE " KSE_ST_TAG " GrantA feat=%d : engine feat-row lookup NULL (invalid id) -- calling "
            "the adder to exercise its self-reject; array A must be UNCHANGED", nFeat);
    } else {
        bool touchesUC = *(reinterpret_cast<BYTE*>(featRow) + KSE_FEATROW_USESPERDAY_OFF) != 0;
        if (aCount >= aCap) {
            // LOG FIRST, BYPASS SECOND. The diagnostic read happens on BOTH paths --
            // putting the opt-in check ahead of it would silence the log at exactly the
            // moment worth observing, which is the crossing itself.
            //
            // The opt-in is STAGE 19 ONLY. This function is shared with 17 and 18, which
            // are historical builds: they keep the unconditional refusal and their
            // original log text, because changing what a historical build does would make
            // it no longer that build. (The guard is NOT in a 19-only block -- it lives in
            // the shared 17/18/19 family, which is why this #if is needed at all.)
#if KSE_STAGE == 19
            bool allow = KseCapacityCrossingAllowed();
            Log("K1SE " KSE_ST_TAG " GrantA feat=%d : REALLOC WOULD FIRE on array A (%d/%d) -- %s",
                nFeat, aCount, aCap,
                allow ? "PROCEEDING (capacity opt-in armed) -- about to grow the feat "
                        "array; watch A.ptr"
                      : "REFUSING; growing the feat array needs the opt-in marker file");
            if (!allow) {
                // A refusal is otherwise visible only in the log, which a modder does
                // not read. Setting errno is what lets a script tell a refused grant
                // from one that succeeded.
                InterlockedExchange(&g_kseErrno, KSE_E_AT_CAPACITY);
                return 0;
            }
#else
            Log("K1SE " KSE_ST_TAG " GrantA feat=%d : REALLOC WOULD FIRE on array A (%d/%d) -- REFUSING; "
                "capacity-crossing is a separate later run", nFeat, aCount, aCap);
            return 0;
#endif
        }
        if (touchesUC && uCount >= uCap) {
            Log("K1SE " KSE_ST_TAG " GrantA feat=%d : REALLOC WOULD FIRE on use-counter list (%d/%d, "
                "UsesPerDay set) -- REFUSING; capacity-crossing is a separate later run",
                nFeat, uCount, uCap);
            return 0;
        }
    }

    // Capture array A's identity so the invalid-id path can prove it was UNTOUCHED.
    void* aPtrBefore = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_PTR_OFF);
    int   aCntBefore = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_COUNT_OFF);

    // The engine's own array-A adder: validates (self-rejects a bad id) and appends
    // to array A. (Its use-counter branch is gated on UsesPerDay, empty for every
    // KOTOR feat, so it never runs here.)
    KseArrayAAddFn add = reinterpret_cast<KseArrayAAddFn>(base + KSE_ARRAYA_ADD_RVA);
    add(block, nullptr, nFeat);

    // Self-referee.
    int   present = KseFeatPresent(block, nFeat);
    bool  inA = KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, nFeat);
    bool  inB = KseFeatInList(block, KSE_SB_FEATB_PTR_OFF, KSE_SB_FEATB_COUNT_OFF, 2, nFeat);
    void* aPtrAfter = *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_PTR_OFF);
    int   aCntAfter = *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_COUNT_OFF);
    KseLogStatFeats(block, "AFTER ");

    // Invalid id (A0's path): "absent after the adder" is the EXPECTED, correct
    // outcome -- the engine rejected it -- not an anomaly. Confirm array A is
    // untouched and say so as a clean rejection, so the run reads as "engine
    // rejected it," never as a silent nothing or a scary sentinel.
    if (invalidId) {
        bool unchanged = (aPtrAfter == aPtrBefore && aCntAfter == aCntBefore && !inA);
        Log("K1SE " KSE_ST_TAG " GrantA feat=%d : engine REJECTED (invalid id) -- array A %s "
            "(ptr %p->%p count %d->%d), self-reject confirmed [no state change]",
            nFeat, unchanged ? "UNCHANGED" : "*** CHANGED, UNEXPECTED ***",
            aPtrBefore, aPtrAfter, aCntBefore, aCntAfter);
        return 0;
    }

    // Valid id: absent after the adder IS a genuine anomaly.
    if (!inA) {
        Log("K1SE ANOMALY granta: feat=%d still ABSENT from array A after the adder ran; sentinel", nFeat);
        return 0;
    }
    if (inB)
        Log("K1SE ANOMALY granta: feat=%d appeared in array B -- A-only expected; the model is wrong", nFeat);
    Log("K1SE " KSE_ST_TAG " GrantA feat=%d : ABSENT -> GRANTED to array A (inA=%d inB=%d GetHasFeat=%d) [granta #%ld]",
        nFeat, inA ? 1 : 0, inB ? 1 : 0, present, (long)InterlockedIncrement(&g_granta));
    return 0;
}

#if KSE_STAGE == 18 || KSE_STAGE == 19
// -------- host 634: void(object,int,int) -- REMOVE from array A ----------------
//
// DRAIN-AND-REBUILD. Snapshot the survivors, zero array A's count (the one direct
// KSE write -- engine-ATTESTED by the drainer's first loop, but not an engine
// CALL), then push every survivor back through the engine's own adder 0x005aa810.
//
// EVERY re-add is logged and verified INDIVIDUALLY. The adder validates via
// 0x00550c00 and rejects an invalid id by writing NOTHING, so a
// survivor that fails validation would vanish with no error and no exception. A
// final count check would not catch it either -- two compensating errors give the
// right count. So each id is confirmed
// present immediately after its own re-add, and the whole set is re-verified after.
#define KSE_A_SNAPSHOT_CAP 128
extern "C" int __stdcall KseArrayA_Remove(int argCount)
{
    if (argCount != 3) { Log("K1SE ANOMALY removea: argCount=%d (declared 3)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    int objId = 0, nFeat = 0, nReserved = 0;
    // Consume ALL THREE args even on failure -- void host, so the VM stack balances
    // only if every pushed arg is read.
    if (!getObject(KseVM(), nullptr, &objId))  { Log("K1SE ANOMALY removea: get.object failed"); return 0; }
    if (!getInt(KseVM(), nullptr, &nFeat))     { Log("K1SE ANOMALY removea: get.int(feat) failed"); return 0; }
    if (!getInt(KseVM(), nullptr, &nReserved)) { Log("K1SE ANOMALY removea: get.int(reserved) failed"); return 0; }

    void *obj = nullptr, *stats = nullptr, *block = nullptr;
    const char* why = "";
    if (!KseResolveCreature(objId, &obj, &stats, &block, &why)) {
        Log("K1SE ANOMALY removea: REFUSED reason=\"%s\" feat=%d; nothing written", why, nFeat);
        return 0;
    }
    void* rules = *reinterpret_cast<void**>(base + KSE_RULES_MGR_RVA);
    if (!rules) { Log("K1SE ANOMALY removea: rules manager null; no removal"); return 0; }

    Log("K1SE " KSE_ST_TAG " RemoveA feat=%d obj=%p stats=%p (obj==stats:%d)",
        nFeat, obj, stats, obj == stats ? 1 : 0);
    if (obj != stats)
        Log("K1SE ANOMALY removea: obj=%p != stats=%p -- 3.28 identity does NOT hold; proceeding with stats", obj, stats);
    KseLogStatFeats(block, "BEFORE");

    BYTE* sb    = reinterpret_cast<BYTE*>(block);
    void* aPtr0 = *reinterpret_cast<void**>(sb + KSE_SB_FEATA_PTR_OFF);
    int   aCnt0 = *reinterpret_cast<int*>(sb + KSE_SB_FEATA_COUNT_OFF);
    int   aCap0 = *reinterpret_cast<int*>(sb + KSE_SB_FEATA_CAP_OFF);

    if (!KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, nFeat)) {
        Log("K1SE " KSE_ST_TAG " RemoveA feat=%d : not in array A -> no-op (nothing drained, nothing rebuilt)", nFeat);
        return 0;
    }
    if (!aPtr0 || aCnt0 <= 0 || aCnt0 > KSE_A_SNAPSHOT_CAP) {
        Log("K1SE ANOMALY removea: array A unusable (ptr=%p count=%d cap=%d, snapshot cap %d); REFUSING",
            aPtr0, aCnt0, aCap0, KSE_A_SNAPSHOT_CAP);
        return 0;
    }

    // USE-COUNTER PARALLEL LIST (see offsets.h). Empty for every feat in KOTOR's
    // SHIPPED feat.2da because UsesPerDay is blank in all 125 rows -- but KSE ships
    // to modders, and a mod that populates that column makes the engine fill this
    // list. A removal with no parallel path would orphan a counter entry pointing at
    // a feat the creature no longer has. This build does NOT implement the parallel
    // removal; it REFUSES, loudly, so the limitation can never silently corrupt a
    // modded install. On shipped data this branch never fires.
    int ucCount = *reinterpret_cast<int*>(sb + KSE_SB_USECTR_COUNT_OFF);
    if (ucCount != 0) {
        Log("K1SE " KSE_ST_TAG " RemoveA feat=%d : REFUSING -- use-counter list is NON-EMPTY "
            "(count=%d). Shipped KOTOR leaves UsesPerDay blank in all 125 feat.2da rows, so this "
            "list is always empty; a non-empty one means modded feat data, and removal has no "
            "parallel path for it yet. Nothing was drained.", nFeat, ucCount);
        return 0;
    }

    // Snapshot survivors, dropping the FIRST occurrence of nFeat. The adder dedups so
    // a duplicate cannot exist, but drop-first is still the right rule: it removes
    // exactly one element regardless of what is in the buffer.
    unsigned short survivors[KSE_A_SNAPSHOT_CAP];
    int nSurv = 0, removedIndex = -1;
    unsigned short* arr = reinterpret_cast<unsigned short*>(aPtr0);
    for (int i = 0; i < aCnt0; ++i) {
        if (removedIndex < 0 && (int)arr[i] == nFeat) { removedIndex = i; continue; }
        survivors[nSurv++] = arr[i];
    }
    Log("K1SE " KSE_ST_TAG " RemoveA feat=%d : found at index %d of %d; %d survivor(s) to rebuild",
        nFeat, removedIndex, aCnt0, nSurv);

    // ---- DRAIN. The one direct KSE write. Count only: pointer, capacity and buffer
    // contents are left alone, exactly as the drainer's first loop does.
    *reinterpret_cast<int*>(sb + KSE_SB_FEATA_COUNT_OFF) = 0;

    // ---- REBUILD through the engine's own adder, verifying each id individually.
    KseArrayAAddFn add = reinterpret_cast<KseArrayAAddFn>(base + KSE_ARRAYA_ADD_RVA);
    int lost = 0;
    for (int i = 0; i < nSurv; ++i) {
        int id = (int)survivors[i];
        add(block, nullptr, id);
        if (!KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, id)) {
            ++lost;
            Log("K1SE ANOMALY removea: re-add LOST feat=%d (survivor %d/%d) -- the adder rejected "
                "it and wrote nothing; array A is now SHORT one feat", id, i + 1, nSurv);
        }
    }

    // ---- VERIFY. Contents, not counts.
    void* aPtr1 = *reinterpret_cast<void**>(sb + KSE_SB_FEATA_PTR_OFF);
    int   aCnt1 = *reinterpret_cast<int*>(sb + KSE_SB_FEATA_COUNT_OFF);
    int   aCap1 = *reinterpret_cast<int*>(sb + KSE_SB_FEATA_CAP_OFF);
    bool  gone  = !KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, nFeat);
    int   present = KseFeatPresent(block, nFeat);
    bool  inB   = KseFeatInList(block, KSE_SB_FEATB_PTR_OFF, KSE_SB_FEATB_COUNT_OFF, 2, nFeat);
    KseLogStatFeats(block, "AFTER ");

    if (aPtr1 != aPtr0)
        Log("K1SE ANOMALY removea: array A POINTER MOVED %p -> %p -- a realloc fired, which this "
            "path must never do", aPtr0, aPtr1);
    if (aCap1 != aCap0)
        Log("K1SE ANOMALY removea: array A CAPACITY changed %d -> %d -- unexpected", aCap0, aCap1);
    if (aCnt1 != nSurv)
        Log("K1SE ANOMALY removea: array A count=%d but %d survivors were rebuilt", aCnt1, nSurv);
    if (!gone)
        Log("K1SE ANOMALY removea: feat=%d STILL PRESENT in array A after the rebuild", nFeat);
    if (inB)
        Log("K1SE ANOMALY removea: feat=%d present in array B -- A-only expected", nFeat);

    // ---- ORPHAN WARNING. KSE removes exactly what it was told
    // and does NOT police prerequisite closure, because GrantFeatArrayA does not
    // maintain it either (0x005aa810 is not the recursive prerequisite granter).
    // Warn loudly, change nothing.
    KseFeatRowFn rowFn = reinterpret_cast<KseFeatRowFn>(base + KSE_FEAT_ROWLOOKUP_RVA);
    for (int i = 0; i < nSurv; ++i) {
        void* row = rowFn(rules, nullptr, (int)survivors[i]);
        if (!row) continue;
        BYTE* r = reinterpret_cast<BYTE*>(row);
        unsigned short p1 = *reinterpret_cast<unsigned short*>(r + KSE_FEATROW_PREREQ1_OFF);
        unsigned short p2 = *reinterpret_cast<unsigned short*>(r + KSE_FEATROW_PREREQ2_OFF);
        if ((p1 && p1 != 0xffff && (int)p1 == nFeat) || (p2 && p2 != 0xffff && (int)p2 == nFeat))
            Log("K1SE " KSE_ST_TAG " RemoveA ORPHAN WARNING: feat=%d is still held and lists the "
                "REMOVED feat %d as a prerequisite (prereq1=%u prereq2=%u). The creature is now in "
                "a state the engine's own level-up path never produces. NOT corrected -- K1SE "
                "removes exactly what it was told.",
                (int)survivors[i], nFeat, (unsigned)p1, (unsigned)p2);
    }

    Log("K1SE " KSE_ST_TAG " RemoveA feat=%d : PRESENT -> REMOVED from array A (index %d, count "
        "%d->%d, ptr %p->%p UNCHANGED=%d, cap %d, rebuilt=%d lost=%d, gone=%d GetHasFeat=%d) "
        "[removea #%ld]",
        nFeat, removedIndex, aCnt0, aCnt1, aPtr0, aPtr1, aPtr1 == aPtr0 ? 1 : 0, aCap1,
        nSurv - lost, lost, gone ? 1 : 0, present, (long)InterlockedIncrement(&g_removea));
    return 0;
}
#endif // KSE_STAGE == 18

// -------- host 685: int(object,int)->int -- GetFeatAcquired (the read) ---------
extern "C" int __stdcall KseFeatRead(int argCount)
{
    if (argCount != 2) { Log("K1SE ANOMALY featread: argCount=%d (declared 2)", argCount); return -1; }
    BYTE* base = KseImageBase();
    KseGetFn    getObject = reinterpret_cast<KseGetFn>(base + KSE_GET_OBJECT_RVA);
    KseGetFn    getInt    = reinterpret_cast<KseGetFn>(base + KSE_GET_INT_RVA);
    KseSetIntFn setRetInt = reinterpret_cast<KseSetIntFn>(base + KSE_SETRET_INT_RVA);
    int objId = 0, nFeat = 0;
    if (!getObject(KseVM(), nullptr, &objId)) { Log("K1SE ANOMALY featread: get.object failed"); return -1; }
    if (!getInt(KseVM(), nullptr, &nFeat))    { Log("K1SE ANOMALY featread: get.int failed"); return -1; }
    void *obj = nullptr, *stats = nullptr, *block = nullptr;
    const char* why = "";
    if (!KseResolveCreature(objId, &obj, &stats, &block, &why)) {
        Log("K1SE ANOMALY featread: %s; returns 0", why);
        setRetInt(KseVM(), nullptr, 0);
        return 0;
    }
    int  present = KseFeatPresent(block, nFeat);
    bool inA = KseFeatInList(block, KSE_SB_FEATA_PTR_OFF, KSE_SB_FEATA_COUNT_OFF, 2, nFeat);
    bool inB = KseFeatInList(block, KSE_SB_FEATB_PTR_OFF, KSE_SB_FEATB_COUNT_OFF, 2, nFeat);
    Log("K1SE GetFeatAcquired feat=%d -> %d (inA=%d inB=%d A.ptr=%p A.count=%d) [aread #%ld]",
        nFeat, present, inA ? 1 : 0, inB ? 1 : 0,
        *reinterpret_cast<void**>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_PTR_OFF),
        *reinterpret_cast<int*>(reinterpret_cast<BYTE*>(block) + KSE_SB_FEATA_COUNT_OFF),
        (long)InterlockedIncrement(&g_areads));
    setRetInt(KseVM(), nullptr, present);
    return 0;
}

// ---- session-end marker: DLL_PROCESS_DETACH, raw Win32 only -----------
static char* KseA_Str(char* p, char* end, const char* s) { while (*s && p < end) *p++ = *s++; return p; }
static char* KseA_ULong(char* p, char* end, unsigned long v)
{
    char t[16]; int n = 0;
    if (!v) t[n++] = '0';
    while (v && n < 16) { t[n++] = (char)('0' + (v % 10)); v /= 10; }
    while (n > 0 && p < end) *p++ = t[--n];
    return p;
}
void KseSt17_ShutdownFlush()
{
    char buf[192];
    char* p = buf;
    char* end = buf + sizeof(buf) - 3;
    // The stage number is part of the marker, not decoration: this is the line that
    // says a run ended cleanly rather than being killed, and a run attributed to the
    // wrong build is worse than one attributed to none: a stale build certifying
    // itself under the wrong stage number would be believed, because it came from the
    // running build's own log.
#if KSE_STAGE == 19
    p = KseA_Str(p, end, "[shutdown] STAGE 19 session end: grants=");
#elif KSE_STAGE == 18
    p = KseA_Str(p, end, "[shutdown] STAGE 18 session end: grants=");
#else
    p = KseA_Str(p, end, "[shutdown] STAGE 17 session end: grants=");
#endif
    p = KseA_ULong(p, end, (unsigned long)g_granta);
#if KSE_STAGE == 18 || KSE_STAGE == 19
    p = KseA_Str(p, end, " removes=");
    p = KseA_ULong(p, end, (unsigned long)g_removea);
#endif
    p = KseA_Str(p, end, " reads=");
    p = KseA_ULong(p, end, (unsigned long)g_areads);
    p = KseA_Str(p, end, " dispatcher-fired=");
    p = KseA_ULong(p, end, (unsigned long)g_hookCount);
    *p++ = '\r'; *p++ = '\n'; *p = '\0';
    LogRaw(buf);
}

#if KSE_STAGE != 19
// Not compiled into the unified build: its inline asm carries ACTION ids as
// immediates, including retired ones, and 'the linker probably strips it' is
// not a verification. STAGE 19 uses Kse19_Detour alone.
__declspec(naked) static void Kse17_Detour()
{
    __asm
    {
        pushfd
        lock inc dword ptr [g_hookCount]
        popfd
        cmp  dword ptr [esp + 4], KSE_GRANTA_ID
        je   kse_do_granta
        cmp  dword ptr [esp + 4], KSE_FEAT_ID
        je   kse_do_featread
#if KSE_STAGE == 18 || KSE_STAGE == 19
        cmp  dword ptr [esp + 4], KSE_REMOVEA_ID
        je   kse_do_removea
#endif
        jmp  dword ptr [g_trampoline]
    kse_do_granta:
        push dword ptr [esp + 8]
        call KseArrayA_Grant
        ret  8
    kse_do_featread:
        push dword ptr [esp + 8]
        call KseFeatRead
        ret  8
#if KSE_STAGE == 18 || KSE_STAGE == 19
    kse_do_removea:
        push dword ptr [esp + 8]
        call KseArrayA_Remove
        ret  8
#endif
    }
}
#endif

#endif

// The stage list is now a set of INDEPENDENT blocks rather than an if/elif chain,
// because STAGE 19 (the unified build) compiles eight of them at once. An invalid
// stage therefore no longer falls out of a trailing #else -- it is checked here.
// The early stages (1-12) have been deleted; the unified build carries every
// function. What went is the dead half: stages
// 1/2/4/5 outright, and each deleted stage's own detour install. Stages 6-12 shared
// their handler BODIES with 19 -- those bodies stayed and are now guarded `== 19`
// alone, because 17 and 18 never compiled them and must not start.
//
// THE BAR INVERTED. It used to be "all 13 stages build". It is now:
//     STAGE 19 builds, 17 and 18 build, and 1-12 must FAIL TO COMPILE.
// A stage that still builds means the deletion did not work -- an arm or a body
// survived. That is stronger than the old bar, which could tell you something was
// broken but never that something was still there.
//
// This is one of TWO independent nets; the other is the KSE_ACTIVE_DETOUR selector's
// trailing #else. This one exists to give a readable message.
#if !(KSE_STAGE == 17 || KSE_STAGE == 18 || KSE_STAGE == 19)
#  error "KSE_STAGE must be 17, 18, or 19 (unified)."
#endif


#if KSE_STAGE == 19
// =============================================================================
// THE UNIFIED DETOUR -- one dispatch over all FOURTEEN hosts.
//
// This replaces nine per-stage detours. Every one of them had the identical shape,
// and this is that shape with a longer comparison chain -- deliberately, because
// the alternative (a table, a computed jump) would be new machinery on the path
// every script call in the game takes. A linear chain of CMPs is what the previous
// nine were proven with; it stays.
//
// THE CONTRACT, unchanged from every detour before it:
//   [esp + 0] = return address     (we are entered by MinHook's 5-byte jump)
//   [esp + 4] = routineId          (the dispatcher's first stack argument)
//   [esp + 8] = argCount           (its second)
// A claimed id pushes argCount, calls the handler, and RET 8 -- consuming both of
// the dispatcher's arguments, which is what the engine's own callee-cleanup
// convention expects. An unclaimed id falls through to the trampoline UNTOUCHED,
// which is the transparency property proven at ~4.3M forwarded calls.
//
// g_hookCount is incremented for EVERY call, claimed or not, with the flags saved
// around it -- the transparency witness. `lock` because the VM is not the only
// thread in the process.
//
// ORDER IS PERFORMANCE, NOT CORRECTNESS. The ids are compared in rough
// expected-frequency order: the feat read first (a script polling feats calls it
// per feat), then the multiplex pair, then everything else. Any order is correct;
// this one just does less work in the common case.
//
// TWO HANDLERS EXIST FOR HOST 685 and only one is routed. STAGE 10's
// KseFeatAcquired and STAGE 17/18's KseFeatRead both answer it; KseFeatRead is
// chosen because it also logs array A's pointer, count and membership. KseFeatAcquired
// stays compiled and unreferenced rather than deleted -- STAGE 10's version.
// =============================================================================
__declspec(naked) static void Kse19_Detour()
{
    __asm
    {
        pushfd
        lock inc dword ptr [g_hookCount]
        popfd

        // -- feat read: the hottest claimed id -------------------------------
        cmp  dword ptr [esp + 4], KSE_FEAT_ID
        je   k19_featread
        // -- shared multiplex ------------------------------------------------
        cmp  dword ptr [esp + 4], KSE_PUSH_ID
        je   k19_push
        cmp  dword ptr [esp + 4], KSE_EVAL_ID
        je   k19_eval
        cmp  dword ptr [esp + 4], KSE_PUSHSTR_ID
        je   k19_pushstr
        cmp  dword ptr [esp + 4], KSE_STROUT_ID
        je   k19_streval
        // -- data store, on its own four hosts ------------------------
        cmp  dword ptr [esp + 4], KSE_DS_PUSHS_ID
        je   k19_dspushs
        cmp  dword ptr [esp + 4], KSE_DS_PUSHI_ID
        je   k19_dspushi
        cmp  dword ptr [esp + 4], KSE_DS_EVALI_ID
        je   k19_dsevali
        cmp  dword ptr [esp + 4], KSE_DS_GETDATA_ID
        je   k19_dsgetdata
        // -- direct typed hosts ----------------------------------------------
        cmp  dword ptr [esp + 4], KSE_GRANTA_ID
        je   k19_granta
        cmp  dword ptr [esp + 4], KSE_REMOVEA_ID
        je   k19_removea
        cmp  dword ptr [esp + 4], KSE_SKILL_ID
        je   k19_skill
        cmp  dword ptr [esp + 4], KSE_SAVE_WRITE_ID
        je   k19_savewrite
        cmp  dword ptr [esp + 4], KSE_SAVE_READ_ID
        je   k19_saveread
        // KOTOR AP ADDITION (not part of upstream K1SE) -- host 688.
        cmp  dword ptr [esp + 4], KSE_FIELD_ID
        je   k19_field
        // KOTOR AP ADDITION (not part of upstream K1SE) -- host 617.
        cmp  dword ptr [esp + 4], KSE_GETCURRENTHP_ID
        je   k19_getcurrenthp
        // KOTOR AP ADDITION (real credits write) -- host 683.
        cmp  dword ptr [esp + 4], KSE_SET_CREDITS_ID
        je   k19_setcredits

        jmp  dword ptr [g_trampoline]

    k19_field:     push dword ptr [esp + 8]
                   call KseSetCreatureField
                   ret  8
    k19_getcurrenthp: push dword ptr [esp + 8]
                   call KseGetCurrentHP
                   ret  8
    k19_setcredits: push dword ptr [esp + 8]
                   call KseSetCredits
                   ret  8
    k19_featread:  push dword ptr [esp + 8]
                   call KseFeatRead
                   ret  8
    k19_push:      push dword ptr [esp + 8]
                   call KsePush
                   ret  8
    k19_eval:      push dword ptr [esp + 8]
                   call KseEval
                   ret  8
    k19_pushstr:   push dword ptr [esp + 8]
                   call KseStrPush
                   ret  8
    k19_streval:   push dword ptr [esp + 8]
                   call KseStrEval
                   ret  8
    k19_dspushs:   push dword ptr [esp + 8]
                   call KseDsPushS
                   ret  8
    k19_dspushi:   push dword ptr [esp + 8]
                   call KseDsPushI
                   ret  8
    k19_dsevali:   push dword ptr [esp + 8]
                   call KseDsEvalI
                   ret  8
    k19_dsgetdata: push dword ptr [esp + 8]
                   call KseDsGetData
                   ret  8
    k19_granta:    push dword ptr [esp + 8]
                   call KseArrayA_Grant
                   ret  8
    k19_removea:   push dword ptr [esp + 8]
                   call KseArrayA_Remove
                   ret  8
    k19_skill:     push dword ptr [esp + 8]
                   call KseAdjustSkills
                   ret  8
    k19_savewrite: push dword ptr [esp + 8]
                   call KseSaveWrite
                   ret  8
    k19_saveread:  push dword ptr [esp + 8]
                   call KseSaveRead
                   ret  8
    }
}
#endif

// The active detour. Each stage family owns exactly one, and this is the single
// point that names it.
//
// THIS ONE STAYS AN #if/#elif CHAIN while the stage blocks above are now
// independent #if blocks -- the difference is load-bearing. A build selects
// EXACTLY ONE detour, so the arms must be mutually exclusive; the stage blocks
// select several at once under STAGE 19, so they must not be. Converting this to
// independent blocks would redefine KSE_ACTIVE_DETOUR eight times under 19.
//
// Note 4/5 and 17/18 share a detour because they share a source block: STAGE 5 is
// STAGE 4 plus a second host, and STAGE 18 is STAGE 17 plus the remover.
// STAGES 1-12'S ARMS WERE DELETED with their detours. This chain is the
// SECOND net making the inverted bar structural rather than conventional: a deleted
// stage falls to the #else and fails HERE even if someone later widens the stage list
// above. The guarantee lives in this #else; the list above only supplies the message.
#if   KSE_STAGE == 19
#  define KSE_ACTIVE_DETOUR Kse19_Detour
#elif KSE_STAGE == 17 || KSE_STAGE == 18
#  define KSE_ACTIVE_DETOUR Kse17_Detour
#else
#  error "No detour defined for this KSE_STAGE."
#endif

#if KSE_STAGE == 19
// ---------------------------------------------------------------------------
// The opt-in marker.
//
// A marker FILE beside the DLL. Chosen over an environment variable or a config key:
//   1. it cannot be created by accident, and cannot be created by a script;
//   2. it is VISIBLE in the game directory, so someone who has one can see why their
//      build behaves oddly -- an env var is invisible;
//   3. the mode goes in the banner on EVERY run, armed or not, so every log is
//      self-identifying;
//   4. it is greppable in the logs.
//
// Resolved ONCE here, at install, and cached. Never re-read per grant: a mode that
// could change mid-session would make the log ambiguous about which regime produced
// which line.
//
// Raw Win32, no CRT -- same discipline as log.cpp's detach path.
static bool g_kseXingResolved = false;
static bool g_kseXingAllowed  = false;

void KseResolveCapacityOptIn()
{
    if (g_kseXingResolved) return;
    g_kseXingResolved = true;
    g_kseXingAllowed  = false;

    // Beside the DLL, not beside the EXE: the sentinel travels with the thing it
    // arms. GetModuleFileNameW(our own module) then swap the leaf.
    wchar_t path[MAX_PATH];
    HMODULE self = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            reinterpret_cast<LPCWSTR>(&KseResolveCapacityOptIn), &self))
        return;
    DWORD n = GetModuleFileNameW(self, path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return;
    wchar_t* slash = path;
    for (wchar_t* p = path; *p; ++p) if (*p == L'\\' || *p == L'/') slash = p;
    static const wchar_t kName[] = L"\\KSE_LAB_MODE";
    if ((size_t)(slash - path) + sizeof(kName) / sizeof(wchar_t) >= MAX_PATH) return;
    lstrcpyW(slash, kName);

    DWORD attr = GetFileAttributesW(path);
    g_kseXingAllowed = (attr != INVALID_FILE_ATTRIBUTES) &&
                       !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

bool KseCapacityCrossingAllowed()
{
    return g_kseXingAllowed;
}
#endif

bool InstallDispatcherHook(void* target)
{
    if (MH_Initialize() != MH_OK) {
        Log("hook: MH_Initialize failed");
        return false;
    }
#if KSE_STAGE == 19
    KseResolveCapacityOptIn();   // once, before any grant can reach the guard
#endif
    MH_STATUS s = MH_CreateHook(target, (LPVOID)&KSE_ACTIVE_DETOUR, (LPVOID*)&g_trampoline);
    if (s != MH_OK) {
        Log("hook: MH_CreateHook failed (status %d)", (int)s);
        return false;
    }
    // MinHook suspends other threads while it writes the 5-byte jump.
    s = MH_EnableHook(target);
    if (s != MH_OK) {
        Log("hook: MH_EnableHook failed (status %d)", (int)s);
        return false;
    }

// STAGE 15/16's observer installs were here. Removed with those stages: they
// referenced SerializerDetour / DrainerDetour / StatWriterDetour and their
// trampolines, none of which exist any more. The guards were never true, so
// this compiled as dead text rather than failing -- which is exactly why it
// survived the deletion unnoticed.
    return true;
}
