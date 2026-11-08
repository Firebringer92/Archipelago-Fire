#pragma once
#include <cstddef>

// File transport and process-lifetime store for the Archipelago delivery system.
//
//   inbox   %LOCALAPPDATA%\K2SE\ap\inbox.txt   written by the client (atomic replace), read by scripts: "key=value" lines
//   outbox  %LOCALAPPDATA%\K2SE\ap\outbox.txt  appended to by scripts, read by the client: "<seq>|<line>"
//   store   256 keys in memory, alive until the game process ends (used for loop generation stamps)
//
// None of this touches game memory.

namespace k2se {
namespace apfiles {

// Integer value of "key" in the inbox (decimal or 0x hex), or fallback if the file or key is absent.
int InboxInt(const char* key, int fallback);

// Rest of the line of "key" (trimmed, at most cap-1 characters). False if absent.
bool InboxStr(const char* key, char* out, size_t cap);

// Appends "<seq>|<line>" to the outbox. seq counts from 1 per process. False on failure.
bool OutboxPut(const char* line);

// In-memory key/value store. Keys under 64 characters, values under 512. False when full or too long.
bool MemSet(const char* key, const char* value);
// Value or "" when absent.
const char* MemGet(const char* key);

}  // namespace apfiles
}  // namespace k2se
