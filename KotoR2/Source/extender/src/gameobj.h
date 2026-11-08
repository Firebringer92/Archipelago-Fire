#pragma once
#include <cstdint>

// ============================================================================
// Turning a script OBJECT id into a live game object.
//
// This is the boundary where K2SE stops being self-contained. Everything up to
// now touched addresses whose meaning was established by disassembling this
// executable. Here we also rely on STRUCT OFFSETS -- claims about an object's
// runtime layout that cannot be checked by reading the file, only by being
// right. They were imported from a third-party database whose KOTOR 2 rows were
// auto-ported from another build.
//
// So the posture is different from the rest of K2SE: assume every pointer might
// be wrong. Each hop is range-checked, every dereference runs under a structured
// exception handler, and a failure returns a sentinel the script can test
// instead of taking the game down. A creature accessor that returns "I don't
// know" is recoverable; one that reads a wild pointer is not.
// ============================================================================

namespace k2se {
namespace gameobj {

// The CServerExoApp singleton, or null if the game has not built it yet.
void* ServerExoApp();

// Script OBJECT id -> CSWSCreature*, or null if the id names something that is
// not a creature (or nothing at all). OBJECT_INVALID is rejected up front.
void* CreatureFromObjectId(uint32_t objectId);

// CSWSCreature* -> CSWSCreatureStats*, or null. Reads through kCreatureOffStats,
// the least-verified step in the chain.
void* CreatureStats(void* creature);

// nAbility is NWScript's ABILITY_* (0..5). False if the index is out of range or
// the read faults.
bool AbilityBase(void* stats, int ability, int* out);

// POC addition, not upstream K2SE. Writes the base ability score via the
// engine's own CSWSCreatureStats::Set<ABILITY>Base call -- one real function
// per ability (offsets_generated.h), not a raw struct-offset byte write like
// AbilityBase() above. Those addresses are confirmed only by prologue-byte
// match, never by disassembly or a live call, so this is genuinely
// unexercised code: false if the index/value is out of range, the pointer
// chain cannot be walked, or the call itself faults (caught, not crashed).
// True means the call returned without faulting -- NOT proof the value
// actually landed; always confirm with a follow-up AbilityBase() read.
bool SetAbilityBase(void* stats, int ability, int value);

// Engine calls. Each returns false rather than a wrong answer when the pointer
// chain could not be walked.
bool SkillRankBase(void* stats, int skill, int* out);
bool HasFeat(void* stats, int feat, int* out);
bool HasSpell(void* stats, int spell, int* out);

// True if the pointer is plausibly a heap object rather than a small integer or
// a sentinel that slipped through. Cheap and catches the common failure.
bool LooksLikePointer(const void* p);

// Says out loud what the last CreatureFromObjectId/CreatureStats pair did: every
// hop with its real value, and the name of the step that stopped it.
//
// This exists because of a specific failure. On 2026-08-29 five routines
// returned -1 five times and wrote not one line explaining any of them, because
// every refusal in this file was a bare `return nullptr`. The chain was in fact
// healthy; nothing in the log could say so. Silence was the bug.
//
// It reports TRANSITIONS, not calls. The callers ride a creature heartbeat, so a
// line per call would bury the log -- instead a line is written the first time
// an outcome is seen and every time the outcome CHANGES, closing the previous
// run with how long it lasted. A healthy session costs one line. The session
// described above would have cost three, and been diagnosed from them.
//
// `who` names the calling routine, so the log says which of 881-884 asked.
void ReportWalk(const char* who);

}  // namespace gameobj
}  // namespace k2se
