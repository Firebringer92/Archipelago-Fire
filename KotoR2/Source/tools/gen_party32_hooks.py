"""Generates src/party32_hooks_generated.h: the Steam-build address and exact bytes of every patch site of the 32-slot party roster.

The sites are the 74 hooks of the Patch Manager mod PartyRosterLimit32K2 (MIT, by Vriff; github.com/LaneDibello/Kotor-Patch-Manager), which targets the
GOG build. Each site was located in the Steam exe by byte pattern plus the regional shift of the relocated code (research/patchmanager/). This script
re-checks every site against the GOG byte pattern (wildcards for build-specific addresses) and writes the bytes the Steam exe really holds, so the DLL
verifies exact bytes before it writes anything.

Usage: python -I tools/gen_party32_hooks.py <swkotor2.exe>
"""
import os
import re
import struct
import sys

# (hook number, steam address, gog pattern ('??' = build specific byte), replacement for a simple patch or None for a detour, group)
# group: 'core' = needed for script-level slots, 'equip' = equipment screen, 'gui' = paged party selection screen
SITES = [
    (1, 0x0089E319, "E8 42 26 00 00", "90 90 90 90 90", "gui"),
    (2, 0x006AB180, "0C", "20", "core"),
    (3, 0x006AB5AE, "0C", "20", "core"),
    (4, 0x006AD602, "0C", "20", "core"),
    (5, 0x006C015C, "0C", "20", "core"),
    (6, 0x008C76C8, "0C", "20", "equip"),
    (7, 0x008C9173, "0C", "20", "equip"),
    # 8: not located yet
    (9, 0x005F7EDE, "0C", "20", "core"),
    (10, 0x005FA8AE, "0C", "20", "core"),
    (11, 0x005FAA36, "89 4D F8 C6 45 FF 00", None, "core"),
    (12, 0x008AAF18, "0C", "20", "equip"),
    (13, 0x008AAF61, "0B", "1F", "equip"),
    (14, 0x008AAF96, "00", "01", "equip"),
    (15, 0x008AB106, "0C", "20", "equip"),
    (16, 0x008AB12B, "0C", "20", "equip"),
    (17, 0x005FE14D, "51", "50", "core"),
    (18, 0x005FE24A, "51", "50", "core"),
    (19, 0x005FEFCB, "51", "50", "core"),
    (20, 0x005F9955, "0C", "20", "core"),
    (21, 0x005F9965, "52", "50", "core"),
    (22, 0x005F99BF, "0C", "20", "core"),
    (23, 0x005F99CF, "51", "50", "core"),
    (24, 0x005F8E0D, "0C", "20", "core"),
    (25, 0x005FA631, "0C", "20", "core"),
    (26, 0x005FD9B2, "0C", "20", "core"),
    (27, 0x005FF3F4, "0C", "20", "core"),
    (28, 0x005F92D2, "8B 8D FC FE FF FF 8B 91 18 01 00 00 8B 8D FC FE FF FF 89 44 91 1C", None, "core"),
    (29, 0x005F9958, "8B 45 E8 8B 8D FC FE FF FF 8B 54 81 1C", None, "core"),
    (30, 0x005F99C2, "8B 55 E8 8B 85 FC FE FF FF 8B 4C 90 1C", None, "core"),
    (31, 0x0089D8E0, "E8 ?? ?? ?? ??", None, "gui"),
    (32, 0x0089DC30, "55 8B EC 6A FF 68 ?? ?? ?? ??", None, "gui"),
    (33, 0x005FDDC0, "55 8B EC 83 EC 08 89 4D F8", None, "core"),
    (34, 0x005FDE70, "55 8B EC 51 89 4D FC", None, "core"),
    (35, 0x005F7F30, "55 8B EC 6A FF 68 ?? ?? ?? ??", None, "core"),
    (36, 0x005F8130, "55 8B EC 6A FF 68 ?? ?? ?? ??", None, "core"),
    (37, 0x005FE466, "8B E5 5D C2 04 00", None, "core"),
    (38, 0x005FA9F0, "55 8B EC 51 89 4D FC", None, "core"),
    (39, 0x005FAA97, "8B 45 08 8B 4D FC 8B 55 0C 89 54 81 1C", None, "core"),
    (40, 0x005FB187, "8B 4D FC 03 4D 08 8A 55 0C 88 51 7C", None, "core"),
    (41, 0x005F76A0, "55 8B EC 83 EC 20 89 4D E8", None, "core"),
    (42, 0x005FB7C6, "68 ?? ?? ?? ??", None, "core"),
    (43, 0x005FC712, "6A 00 8D 45 88", None, "core"),
    (44, 0x008AB161, "8B 4D A8 8B 91 EC 50 00 00", None, "equip"),
    (45, 0x008AB2EB, "E9 ?? ?? ?? ??", None, "equip"),
    (46, 0x005FE13C, "8B 45 E0 8B 4D 98 8B 54 81 08 8B 45 98 8B 4C 90 1C", None, "core"),
    (47, 0x005FE239, "8B 45 D8 8B 4D 98 8B 54 81 08 8B 45 98 8B 4C 90 1C", None, "core"),
    (48, 0x005FEFB9, "0F B6 45 FF 8B 4D D8 8B 54 81 08 8B 45 D8 8B 4C 90 1C", None, "core"),
    (49, 0x005FEE00, "8B 55 FC 8B 45 E8 8B 4C 90 08 8B 55 E8 8B 44 8A 1C", None, "core"),
    (50, 0x005F8E18, "8B 4D FC 8B 55 CC 8B 44 8A 1C", None, "core"),
    (51, 0x005F8E3F, "8B 55 08 8B 45 CC 8B 4D 0C 89 4C 90 1C", None, "core"),
    (52, 0x005F9FF0, "55 8B EC 6A FF 68 ?? ?? ?? ??", None, "core"),
    (53, 0x005FA93B, "8B 4D 08 8B 55 FC C7 44 8A 4C 00 00 00 00", None, "core"),
    (54, 0x005FD9D3, "8B 4D 08 8B 55 D0 8B 44 8A 1C", None, "core"),
    (55, 0x005FD9FB, "8B 4D 08 8B 55 D0 C7 44 8A 1C 00 00 00 7F", None, "core"),
    (56, 0x005FDC38, "8B E5 5D C2 04 00", None, "core"),
    (57, 0x005FB0DC, "8B E5 5D C2 04 00", None, "core"),
    (58, 0x005FB12B, "8B E5 5D C2 04 00", None, "core"),
    (59, 0x005FE404, "8B E5 5D C2 04 00", None, "core"),
    (60, 0x005FA981, "8B E5 5D C2 04 00", None, "core"),
    (61, 0x005FA9E4, "8B E5 5D C2 04 00", None, "core"),
    (62, 0x005FF3FC, "8B 4D F8 8B 91 54 02 00 00 8B 45 F8 8B 4C 90 08 8B 55 F8 8B 44 8A 1C", None, "core"),
    (63, 0x005FAB2C, "8B 4D 08 8B 55 A0", None, "core"),
    (64, 0x005FB157, "8B 4D FC 03 4D 08", None, "core"),
    (65, 0x005FE5C0, "8B 85 04 FF FF FF 8B 88 18 01 00 00 8B 95 04 FF FF FF 8B 44 8A 1C", None, "core"),
    (66, 0x0089E000, "55 8B EC 6A FF 68 ?? ?? ?? ??", None, "gui"),
    (67, 0x0089EA06, "8B 4D F4 64 89 0D 00 00 00 00", None, "gui"),
    (68, 0x00662042, "8B 4D F4 64 89 0D 00 00 00 00", None, "core"),
    (69, 0x0089EA20, "55 8B EC 83 EC 28", None, "gui"),
    (70, 0x0089EB40, "8B E5 5D C3 CC", None, "gui"),
    (71, 0x0089FB40, "55 8B EC 51 89 4D FC", None, "gui"),
    (72, 0x0089ED90, "55 8B EC 83 EC 38", None, "gui"),
    (73, 0x0089FBD0, "55 8B EC 81 EC 94 01 00 00", None, "gui"),
    (74, 0x008A05AA, "C7 45 F0 00 00 00 00", None, "gui"),
]


def load(path):
    data = open(path, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    sec = pe + 24 + opt
    for i in range(nsec):
        name, vsize, va, rsize, raw = struct.unpack_from("<8sIIII", data, sec + 40 * i)
        if name.rstrip(b"\0") == b".text":
            return data, base + va, raw
    raise SystemExit("no .text")


def main():
    data, va0, raw0 = load(sys.argv[1])

    def at(a, n):
        return data[raw0 + (a - va0): raw0 + (a - va0) + n]

    rows = []
    bad = 0
    for num, addr, pat, repl, group in SITES:
        toks = pat.split()
        n = len(toks)
        have = at(addr, n)
        ok = all(t == "??" or int(t, 16) == b for t, b in zip(toks, have))
        if not ok:
            print("MISMATCH hook %d at 0x%08X: want %s have %s" % (num, addr, pat, have.hex(" ").upper()))
            bad += 1
        rows.append((num, addr, have, repl, group))
    if bad:
        raise SystemExit("%d sites do not match: nothing written" % bad)

    out = []
    out.append("// GENERATED by tools/gen_party32_hooks.py from the Steam swkotor2.exe. Do not edit by hand.")
    out.append("// Sites of the 32-slot party roster (see research/patchmanager/ and docs/PARTY_SLOTS_32.md).")
    out.append("#pragma once")
    out.append("#include <cstdint>")
    out.append("")
    out.append("namespace k2se {")
    out.append("namespace party32 {")
    out.append("")
    out.append("enum class Group : uint8_t { kCore, kEquip, kGui };")
    out.append("")
    out.append("struct Site {")
    out.append("    int number;            // hook number in the Patch Manager table")
    out.append("    uint32_t address;")
    out.append("    uint8_t length;")
    out.append("    uint8_t original[24];  // exact bytes in the Steam exe")
    out.append("    uint8_t replacement;   // simple one-byte patches only (length 1, or the 5 nops of hook 1 use kNops)")
    out.append("    bool simple;")
    out.append("    Group group;")
    out.append("};")
    out.append("")
    out.append("constexpr Site kSites[] = {")
    for num, addr, have, repl, group in rows:
        n = len(have)
        if n > 24:
            raise SystemExit("hook %d is longer than 24 bytes" % num)
        orig = ", ".join("0x%02X" % b for b in have) + (", 0" * (24 - n) if n < 24 else "")
        simple = repl is not None
        r = int(repl.split()[0], 16) if simple else 0
        g = {"core": "kCore", "equip": "kEquip", "gui": "kGui"}[group]
        out.append("    {%d, 0x%08X, %d, {%s}, 0x%02X, %s, Group::%s}," % (num, addr, n, orig, r, "true" if simple else "false", g))
    out.append("};")
    out.append("")
    out.append("}  // namespace party32")
    out.append("}  // namespace k2se")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "party32_hooks_generated.h")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print("wrote %s: %d sites (hook 8 is not located yet)" % (os.path.normpath(path), len(rows)))


main()
