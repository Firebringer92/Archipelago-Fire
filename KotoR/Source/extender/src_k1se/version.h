#pragma once

// -----------------------------------------------------------------------------
// KSE's own version and build identity.
//
// TWO QUESTIONS, DELIBERATELY SEPARATE:
//   KSE_GetVersion()  -> "which API can I rely on?"   an ordered int
//   KSE_BuildId()     -> "which ARTIFACT is this?"    a string
//
// A version answers compatibility; a build id answers provenance. Two builds can
// share a version number yet be different artifacts, so conflating the two is how a
// stale DLL becomes indistinguishable from a current one. Keep them separate.
// -----------------------------------------------------------------------------

#define KSE_VER_MAJOR 1
#define KSE_VER_MINOR 0
#define KSE_VER_PATCH 0

// major*10000 + minor*100 + patch. 1.0.0 -> 10000. Ordered comparison is what a modder
// actually needs -- `if (KSE_GetVersion() < 10200) return;` -- and it fits an int with
// room for 21 major versions before the sign bit is anywhere near.
#define KSE_VERSION_ENCODED \
    (KSE_VER_MAJOR * 10000 + KSE_VER_MINOR * 100 + KSE_VER_PATCH)

// -----------------------------------------------------------------------------
// THE "NEVER ZERO" RULE, ENFORCED RATHER THAN REMEMBERED
//
// A script that calls a KSE function on a build without KSE reads back 0. That makes
// the presence probe a single line -- `if (KSE_GetVersion() <= 0)` means KSE is absent
// or too old -- and it makes ZERO A RESERVED VALUE: a build that reported 0 would be
// indistinguishable from one that is not there.
//
// A rule living only in a comment is one refactor away from silent breakage, so it is a
// compile error instead.
//
// TWO ASSERTIONS THAT LOOK REDUNDANT AND ARE NOT:
//
//   * MAJOR >= 1 protects the VALUE. It is the real invariant -- a major of at least 1
//     makes the encoded result >= 10000 by construction, whatever the minor and patch.
//
//   * ENCODED != 0 protects the ARITHMETIC. It is the one that survives someone changing
//     the multipliers above. If the *10000 ever became *0, or the expression were
//     rewritten wrongly, MAJOR >= 1 would still hold and the encoding would still be
//     broken. Only the second assertion catches that.
//
// Delete either and a real failure mode stops being caught.
// -----------------------------------------------------------------------------

static_assert(KSE_VER_MAJOR >= 1,
    "KSE_VER_MAJOR must be >= 1. Zero is RESERVED: a script reads 0 when K1SE is absent, "
    "so a version of 0 is indistinguishable from K1SE not being present. This protects the "
    "VALUE.");

static_assert(KSE_VERSION_ENCODED != 0,
    "KSE_VERSION_ENCODED must never be 0. This is NOT redundant with the assertion above: "
    "it is the one that catches a broken ENCODING, e.g. if the multipliers were changed. "
    "MAJOR >= 1 protects the value; this protects the arithmetic that turns it into the "
    "value.");

// -----------------------------------------------------------------------------
// WHAT THESE ASSERTIONS CANNOT COVER -- written down so nobody assumes they were enough.
//
// They guarantee the ENCODING is well-formed and non-zero. They say NOTHING about whether
// the handler is wired to the right opcode, or whether a script calling KSE_GetVersion()
// actually receives this constant. That is a runtime property; compile-time proof of the
// constant is not proof of the channel.
// -----------------------------------------------------------------------------

// The artifact identity. Changed deliberately per build that is meant to be
// distinguishable -- it is what a user's log carries when they report a problem.
#define KSE_BUILD_ID "K1SE 1.0.0 STAGE19+optin 2026-08-04"
