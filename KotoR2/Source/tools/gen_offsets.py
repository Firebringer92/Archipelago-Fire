"""Generate src/offsets_generated.h from data/k2se_addresses.csv.

    python tools/gen_offsets.py [--check]

--check exits non-zero if the header on disk differs from what the CSV implies,
so CI (and verify_offsets.py) can prove the two have not drifted.

The generated names live in k2se::off::game, deliberately separate from the
hand-derived constants in offsets.h. Keeping them apart is what makes the
cross-check static_asserts at the bottom of offsets.h meaningful: they compare
two independent derivations of the same address, and the build fails if the two
ever disagree.
"""

import os
import sys

import addressdb

HEADER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "src", "offsets_generated.h")

BANNER = """\
// =============================================================================
// GENERATED FILE -- DO NOT EDIT.
//
//   source: data/k2se_addresses.csv
//   regen : python tools/gen_offsets.py
//
// Addresses for swkotor2.exe, Aspyr/Steam build, FileVersion 1.0.2.0,
// TimeDateStamp 0x5603005D. The executable is RELOCS_STRIPPED with no ASLR, so
// every value here is a stable absolute VA.
//
// Provenance is recorded per constant:
//   kpm-db       Kotor-Patch-Manager AddressDatabases/kotor2_steam_aspyr.db (MIT).
//                Data only -- no code from that project is used in K2SE.
//   k2se-ghidra  derived in this project.
//
// Verification is a claim about THIS binary, not about the source:
//   runtime      exercised in a live game session
//   disasm       the function body was read
//   callsite     reached via the rel32 of a verified E8 in a real handler
//   prologue     entry point is in .text and starts with 55 8B EC
//   unverified   imported but unchecked -- MUST NOT be called from shipping code
//
// tools/verify_offsets.py re-checks every row against the executable.
// =============================================================================

#pragma once
#include <cstdint>

namespace k2se {
namespace off {
namespace game {
"""


def render(rows):
    out = [BANNER]

    for kind, title, note in (
        ("function", "functions", "engine entry points"),
        ("global", "globals", "pointer variables; dereference to reach the object"),
        ("offset", "struct offsets", "byte displacement from `this`"),
        ("constant", "constants", "values read out of instruction immediates"),
        ("vtable", "vtables", "virtual function table addresses"),
        ("class", "class sizes", "sizeof, where it has been established"),
    ):
        sel = [r for r in rows if r["kind"] == kind]
        if not sel:
            continue
        out.append("\n// --- %s %s\n// %s\n" % (title, "-" * max(0, 60 - len(title)), note))

        by_class = {}
        for r in sel:
            by_class.setdefault(r["class"], []).append(r)

        for cls in sorted(by_class):
            group = sorted(by_class[cls], key=lambda r: r["name"])
            if cls:
                out.append("\n// %s\n" % cls)
            width = max(len(addressdb.cpp_identifier(r)) for r in group)
            for r in group:
                ident = addressdb.cpp_identifier(r)
                comment = r["verified_by"]
                if r["notes"]:
                    comment += " -- " + r["notes"]
                out.append("constexpr uint32_t %-*s = %s;  // %s\n"
                           % (width, ident, r["value"], comment))

    out.append("""
}  // namespace game
}  // namespace off
}  // namespace k2se
""")
    return "".join(out)


def main():
    check = "--check" in sys.argv
    rows = addressdb.load()
    if not rows:
        raise SystemExit("data/k2se_addresses.csv is empty; run tools/import_kpm_db.py first")

    text = render(rows)

    if check:
        if not os.path.exists(HEADER_PATH):
            print("FAIL  src/offsets_generated.h is missing; run tools/gen_offsets.py")
            return 1
        with open(HEADER_PATH, "r", encoding="utf-8", newline="") as fh:
            current = fh.read()
        if current.replace("\r\n", "\n") != text:
            print("FAIL  src/offsets_generated.h is stale relative to "
                  "data/k2se_addresses.csv")
            print("      run: python tools/gen_offsets.py")
            return 1
        print("OK    src/offsets_generated.h matches data/k2se_addresses.csv (%d rows)"
              % len(rows))
        return 0

    with open(HEADER_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)

    counts = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    unver = sum(1 for r in rows if r["verified_by"] == "unverified")
    print("wrote %s" % HEADER_PATH)
    plural = {"class": "classes", "vtable": "vtables", "function": "functions",
              "global": "globals", "offset": "offsets", "constant": "constants"}
    print("  %s" % ", ".join("%d %s" % (v, plural.get(k, k + "s"))
                             for k, v in sorted(counts.items())))
    print("  %d verified on this binary, %d unverified" % (len(rows) - unver, unver))
    return 0


if __name__ == "__main__":
    sys.exit(main())
