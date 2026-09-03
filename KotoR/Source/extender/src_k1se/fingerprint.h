#pragma once
#include <stdint.h>

// Generated fingerprint table -- do not hand-edit.
//
// A set of code fingerprints KSE checks against the loaded game before installing
// its hook. Each entry is a hash of a span of the target image, not a copy of it,
// so this header carries no game content: a mismatch reports which fingerprint
// failed, not what was there.
//
// A full match means the loaded binary is the one KSE's addresses were built for.
// The check covers code only; it does not by itself validate the struct offsets.

typedef struct {
    const char* name;      // reported in the refuse-to-install log line
    uint32_t    rva;       // relative to a 0x00400000 preferred base
    uint32_t    len;
    uint32_t    hash;      // FNV-1a 32 over the probed span
} KseProbe;

// Each probe covers one function KSE depends on; the name identifies it.

static const KseProbe KSE_PROBES[] = {
    { "DISPATCHER",       0x0012C0D0u, 0x040u, 0xE0883AFAu },
    { "VM_ACCESSOR_SPAN", 0x001D1000u, 0x0E0u, 0x55EE5523u },
    { "CEXOSTR_CTOR",     0x001B3190u, 0x010u, 0x07CF9CECu },
    { "CEXOSTR_FROMCSTR", 0x001E5A90u, 0x010u, 0x090A79E5u },
    { "CEXOSTR_DTOR",     0x001E5C20u, 0x010u, 0xE35C4750u },
    { "CEXOSTR_GETLEN",   0x001E5790u, 0x010u, 0x6835C3BFu },
    { "OBJ_TABLE_GET",    0x000AED70u, 0x010u, 0x327451D6u },
    { "OBJ_RESOLVE",      0x000D8230u, 0x010u, 0x415AA04Cu },
    { "FEAT_QUERY",       0x001A6630u, 0x010u, 0xE1C57DFAu },
    { "FEAT_ROWLOOKUP",   0x00150C00u, 0x010u, 0xA2F12998u },
    { "ARRAYA_ADD",       0x001AA810u, 0x010u, 0xA3A1B7FFu },
};
static const size_t KSE_PROBE_COUNT = sizeof(KSE_PROBES) / sizeof(KSE_PROBES[0]);

static_assert(KSE_PROBE_COUNT == 11,
    "The probe count is derived from the set of functions KSE calls, not chosen. "
    "Change it only by regenerating this table, not by editing this file.");

// FNV-1a 32, matching the table above; inline so it needs no library.
static uint32_t KseFnv1a32(const unsigned char* p, size_t n)
{
    uint32_t h = 0x811C9DC5u;
    for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 0x01000193u; }
    return h;
}
