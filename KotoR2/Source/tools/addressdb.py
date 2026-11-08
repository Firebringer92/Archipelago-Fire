"""Read/write data/k2se_addresses.csv -- K2SE's address table.

The CSV is the single source of truth for every address K2SE did not derive by
hand. src/offsets_generated.h is produced from it and must never be edited
directly.

Columns
-------
kind         function | global | offset | constant | vtable | class
             vtable: name="vtable", value = the vftable's address
             class:  name="size",   value = sizeof
class        owning class, or "Other" for free functions
name         member name
value        hex, 0x-prefixed
provenance   where the value came from:
               kpm-db      Kotor-Patch-Manager kotor2_steam_aspyr.db
               k2se-ghidra our own Ghidra project
verified_by  how it was checked ON THIS BINARY:
               prologue    entry point is in .text and starts with 55 8B EC
               callsite    reached via the rel32 of a verified E8 in a real handler
               disasm      the function body was read and understood
               runtime     exercised in a live game session
               unverified  imported but not yet checked -- never call these
notes        free text

A row's `verified_by` is a claim about *this* executable, not about the source it
came from. Nothing marked `unverified` may be called from shipping code.
"""

import csv
import os

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "k2se_addresses.csv")

FIELDS = ["kind", "class", "name", "value", "provenance", "verified_by", "notes"]

KINDS = ("function", "global", "offset", "constant", "vtable", "class")
VERIFIED_LEVELS = ("unverified", "prologue", "callsite", "disasm", "runtime")


def key(row):
    return (row["kind"], row["class"], row["name"])


def load(path=CSV_PATH):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["value_int"] = int(r["value"], 16)
    return rows


def save(rows, path=CSV_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ordered = sorted(rows, key=lambda r: (KINDS.index(r["kind"]), r["class"], r["name"]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    return len(ordered)


def merge(existing, incoming):
    """Merge `incoming` into `existing`, keyed on (kind, class, name).

    A row is only overwritten when the incoming one is verified at least as
    strongly -- so re-running a low-confidence import can never downgrade a value
    that has since been confirmed by disassembly or in a live session.
    Returns (rows, added, updated, kept).
    """
    by_key = {key(r): r for r in existing}
    added = updated = kept = 0
    for r in incoming:
        k = key(r)
        old = by_key.get(k)
        if old is None:
            by_key[k] = r
            added += 1
            continue
        old_rank = VERIFIED_LEVELS.index(old.get("verified_by", "unverified"))
        new_rank = VERIFIED_LEVELS.index(r.get("verified_by", "unverified"))
        if new_rank >= old_rank:
            # Preserve hand-written notes when the incoming row has none.
            if not r.get("notes") and old.get("notes"):
                r["notes"] = old["notes"]
            by_key[k] = r
            updated += 1
        else:
            kept += 1
    return list(by_key.values()), added, updated, kept


def cpp_identifier(row):
    """The constexpr name emitted into src/offsets_generated.h."""
    kind = row["kind"]
    if kind == "offset":
        return "kOff_%s_%s" % (row["class"], row["name"])
    if kind == "global":
        return "kGlobal_%s" % row["name"]
    if kind == "vtable":
        return "kVtable_%s" % row["class"]
    if kind == "class":
        return "kSizeof_%s" % row["class"]
    return "k%s_%s" % (row["class"], row["name"])
