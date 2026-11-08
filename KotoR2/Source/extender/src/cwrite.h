#pragma once
#include <cstdint>

// Validated creature writers behind the shipped natives K2SE_Set* / K2SE_Remove*.
//
// Every function resolves the script object itself, checks every argument against the
// game's own limits, reads the current state before changing it and refuses (returns 0)
// instead of writing something the game's own code could not have produced. None of them
// depends on config.txt; the raw K2SE_WriteMem probe stays the only gated writer.
//
// Result codes: 1 changed (or already in that state), 0 refused (bad argument or the
// state does not allow it), -1 the creature or a pointer on the way to it could not be
// resolved.
namespace k2se {
namespace cwrite {

int SetRace(uint32_t objectId, int race);                    // 5 = Droid, 6 = Human
int SetCreatureCredits(uint32_t objectId, int amount);       // a creature's own balance
int SetPartyCredits(int amount);                             // the player's balance
int SetSaveBonus(uint32_t objectId, int save, int value);    // 0 fort, 1 will, 2 reflex; 0..100
int SetClassLevel(uint32_t objectId, int slot, int level);   // slot 0..2
int SetClassId(uint32_t objectId, int slot, int classId);    // swaps a class in place
int RemoveClass(uint32_t objectId, int slot);                // the last class only, never slot 0
int RemoveFeat(uint32_t objectId, int feat);                 // 1 if it was removed, 0 if absent
int RemovePower(uint32_t objectId, int spell);               // 1 if it was removed, 0 if absent
int SetSkillRank(uint32_t objectId, int skill, int rank);    // skill 0..7, rank 0..100: the rank bought, before items and effects

}  // namespace cwrite
}  // namespace k2se
