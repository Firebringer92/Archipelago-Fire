"""Re-verify every address K2SE depends on, straight out of the binary.

This is milestone M0: nothing in DESIGN.md should be taken on faith. Run it
before trusting a single line of hook code.

Usage:
    python tools/verify_offsets.py [path-to-swkotor2.exe]

Defaults to the pristine backup, falling back to the live exe.

Three layers of checking, in increasing breadth:

  1. the hand-derived probes -- exact dword/byte values at sites whose meaning
     was established by disassembly. A mismatch here means the wrong build.
  2. the imported address table (data/k2se_addresses.csv) -- every function
     entry point must be in .text behind an MSVC prologue. This is what makes a
     third-party address usable rather than merely plausible.
  3. header freshness -- src/offsets_generated.h must match the CSV, so the
     compiled constants cannot silently drift from the verified data.
"""

import hashlib
import struct
import sys

import addressdb
import peimage
from peimage import EXPECTED_IMAGEBASE, EXPECTED_TIMESTAMP

PROBES_DWORD = [
    ("vtable[0]",                 0x009940D0, 0x00536BE0),
    ("vtable[1] InitializeCmds",  0x009940D4, 0x00665F50),
    ("vtable[2] ExecuteCommand",  0x009940D8, 0x00668FD0),
    ("vtable[3]",                 0x009940DC, 0x00669020),
    ("alloc size 877*4",          0x00665F5A, 0x0DB4),
    ("init bound 877",            0x00665F87, 0x36D),
    ("dispatch bound 877",        0x00668FDC, 0x36D),
    # rel32 of verified E8 calls to the stack accessors, read from handlers
    # that provably use them (math handler / GetArea / GetFirstPC)
    ("PopFloat call site",        0x0068C514, 0x000714C8),  # -> 0x006FD9E0
    ("PushFloat call site",       0x0068C774, 0x00071288),  # -> 0x006FDA00
    ("PopObject call site",       0x0067A0BA, 0x00083A32),  # -> 0x006FDAF0
    ("PushObject call site",      0x00687692, 0x0007647A),  # -> 0x006FDB10
    ("AurPostString prologue",    0x00474C00, 0x6AEC8B55),  # 55 8B EC 6A
]

PROBES_BYTE = [
    ("m_pCommands (init)",     0x00665F71, 0x0C),
    ("m_pCommands (dispatch)", 0x00668FE7, 0x0C),
    ("m_pInternal",            0x006FD9B0, 0x1C),
]

# The GL imports M5 depends on. Verified by NAME against the PE import directory
# rather than by address: a hardcoded IAT slot is a guess, an import name is a
# fact. See DESIGN.md 5 and the fog track.
IAT_EXPECTED = [
    (0x0098632C, "OPENGL32.dll", "wglGetProcAddress"),
    (0x00986028, "GLU32.dll", "gluPerspective"),
    (0x00986394, "OPENGL32.dll", "glFogf"),
    (0x00986398, "OPENGL32.dll", "glFogfv"),
    (0x009863B0, "OPENGL32.dll", "glFogi"),
]

RTTI_STRING = b".?AVCSWVirtualMachineCommands@@"
RTTI_VA = 0x00A0F4F8


def read_iat(img):
    """Map every IAT slot VA -> (dll, import name).

    Data directory entry 1 is the import table: 24 bytes of PE header, then the
    optional header, whose data directories start at +0x60; import is the second,
    hence +0x68.
    """
    imp_rva = struct.unpack_from("<I", img.data, img.pe + 24 + 0x68)[0]
    slots = {}
    o = img.off(img.image_base + imp_rva)
    if o is None:
        return slots
    while True:
        oft, _ts, _fc, nm, ft = struct.unpack_from("<IIIII", img.data, o)
        if nm == 0:
            break
        dll = img.data[img.off(img.image_base + nm):].split(b"\0")[0].decode("ascii", "replace")
        table = oft or ft
        to = img.off(img.image_base + table)
        k = 0
        while True:
            e = struct.unpack_from("<I", img.data, to + k * 4)[0]
            if e == 0:
                break
            slot = img.image_base + ft + k * 4
            if e & 0x80000000:
                name = "#%d" % (e & 0xFFFF)
            else:
                name = img.data[img.off(img.image_base + e) + 2:].split(b"\0")[0].decode(
                    "ascii", "replace")
            slots[slot] = (dll, name)
            k += 1
        o += 20
    return slots


def main():
    img = peimage.open_default(sys.argv[1] if len(sys.argv) > 1 else None)

    print("file        : %s" % img.path)
    print("size        : %d bytes" % len(img.data))
    print("sha256      : %s" % hashlib.sha256(img.data).hexdigest().upper())
    print("ImageBase   : 0x%08X  (expected 0x%08X)" % (img.image_base, EXPECTED_IMAGEBASE))
    print("TimeDateStamp: 0x%08X (expected 0x%08X)" % (img.timestamp, EXPECTED_TIMESTAMP))
    laa = " [4GB/LAA patched]" if img.characteristics & 0x20 else " [pristine]"
    print("Characteristics: 0x%04X%s" % (img.characteristics, laa))
    lo, hi = img.text_range()
    print(".text range : 0x%08X - 0x%08X" % (lo, hi))
    print("")

    failures = 0

    if img.timestamp != EXPECTED_TIMESTAMP:
        print("FAIL  TimeDateStamp mismatch -- this is a different build")
        failures += 1

    # --- 1. hand-derived probes --------------------------------------------
    print("--- hand-derived probes (DESIGN.md 2) ---")
    o = img.off(RTTI_VA)
    got = img.data[o:o + len(RTTI_STRING)] if o is not None else b""
    ok = got == RTTI_STRING
    print("%-4s  RTTI class name @0x%08X -> %s" % ("OK" if ok else "FAIL", RTTI_VA,
                                                   got.decode("ascii", "replace")))
    failures += 0 if ok else 1

    for name, va, expected in PROBES_DWORD:
        actual = img.dword(va)
        ok = actual == expected
        failures += 0 if ok else 1
        shown = "unreadable" if actual is None else "0x%08X" % actual
        print("%-4s  %-26s @0x%08X = %-12s expected 0x%08X"
              % ("OK" if ok else "FAIL", name, va, shown, expected))

    for name, va, expected in PROBES_BYTE:
        actual = img.byte(va)
        ok = actual == expected
        failures += 0 if ok else 1
        shown = "unreadable" if actual is None else "0x%02X" % actual
        print("%-4s  %-26s @0x%08X = %-12s expected 0x%02X"
              % ("OK" if ok else "FAIL", name, va, shown, expected))

    # --- 2. GL imports, resolved by name -----------------------------------
    print("\n--- GL imports (M5 fog), resolved by name from the import directory ---")
    slots = read_iat(img)
    for va, dll, name in IAT_EXPECTED:
        got = slots.get(va)
        ok = got is not None and got[1] == name
        failures += 0 if ok else 1
        shown = "%s!%s" % got if got else "not an IAT slot"
        print("%-4s  %-16s @0x%08X = %-28s expected %s" %
              ("OK" if ok else "FAIL", name, va, shown, name))

    # --- 3. the imported address table -------------------------------------
    rows = addressdb.load()
    print("\n--- imported address table (data/k2se_addresses.csv, %d rows) ---" % len(rows))
    fns = [r for r in rows if r["kind"] == "function"]
    bad_fns = []
    for r in fns:
        if not img.has_prologue(r["value_int"]):
            bad_fns.append(r)
    print("%-4s  function entry points with an MSVC prologue in .text: %d / %d"
          % ("OK" if not bad_fns else "FAIL", len(fns) - len(bad_fns), len(fns)))
    for r in bad_fns:
        print("      FAIL %s::%s @%s  (%s)"
              % (r["class"], r["name"], r["value"], img.section_of(r["value_int"])))
    failures += len(bad_fns)

    globs = [r for r in rows if r["kind"] == "global"]
    bad_globs = [r for r in globs if img.section_of(r["value_int"]) not in (".data", ".rdata")]
    print("%-4s  globals in a data section: %d / %d"
          % ("OK" if not bad_globs else "FAIL", len(globs) - len(bad_globs), len(globs)))
    for r in bad_globs:
        print("      FAIL %s @%s" % (r["name"], r["value"]))
    failures += len(bad_globs)

    unver = [r for r in rows if r["verified_by"] == "unverified"]
    print("      %d row(s) marked unverified -- these must not be called from "
          "shipping code" % len(unver))

    # --- 4. generated header freshness --------------------------------------
    print("\n--- generated header ---")
    import gen_offsets
    saved = sys.argv
    sys.argv = ["gen_offsets.py", "--check"]
    try:
        failures += gen_offsets.main()
    finally:
        sys.argv = saved

    # POC FORK: upstream also checks a first-person-camera eye-height table
    # here (gen_eyetable.py / model_measure.py) -- dropped along with the rest
    # of the camera/movement subsystem this fork doesn't vendor. See
    # ../docs/ENGINE_DIFFERENCES.md.

    print("")
    if failures:
        print("%d PROBE(S) FAILED -- do not hook this binary." % failures)
        return 1
    print("ALL PROBES PASSED -- the addresses in src/offsets.h, "
          "src/offsets_generated.h and data/k2se_addresses.csv match this binary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
