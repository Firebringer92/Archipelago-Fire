"""Validate the built version.dll against everything it has to satisfy.

Checks:
  1. 32-bit PE (the game is a 32-bit process; a 64-bit DLL can never load)
  2. it is a DLL
  3. its export names match the real SysWOW64\\version.dll exactly
  4. its imports (goal: KERNEL32 only, so no VC++ redistributable is needed)

Usage:
    python tools/check_dll.py [path-to-built-version.dll]
"""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build"))
from generate_proxy import read_exports, REAL_DLL  # noqa: E402

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "version.dll")


def parse(path):
    with open(path, "rb") as fh:
        data = fh.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    chars = struct.unpack_from("<H", data, pe + 22)[0]
    opt = pe + 24

    sections = []
    sec = opt + optsize
    for i in range(nsec):
        o = sec + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, vaddr = struct.unpack_from("<II", data, o + 8)
        rawsize, raw = struct.unpack_from("<II", data, o + 16)
        sections.append((name, vaddr, vsize, raw, rawsize))

    def r2o(rva):
        for _n, vaddr, vsize, raw, _rs in sections:
            if vaddr <= rva < vaddr + max(vsize, 1):
                return raw + (rva - vaddr)
        return None

    imports = []
    imp_rva = struct.unpack_from("<I", data, opt + 104)[0]
    if imp_rva:
        off = r2o(imp_rva)
        while True:
            entry = data[off:off + 20]
            if len(entry) < 20 or entry == b"\0" * 20:
                break
            name_rva = struct.unpack_from("<I", entry, 12)[0]
            if name_rva == 0:
                break
            no = r2o(name_rva)
            end = data.index(b"\0", no)
            imports.append(data[no:end].decode("ascii", "replace"))
            off += 20

    return {"machine": machine, "chars": chars, "imports": imports, "sections": sections}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.exists(path):
        raise SystemExit("not found: %s (build it first)" % path)

    info = parse(path)
    failures = 0

    print("file: %s" % os.path.abspath(path))
    print("size: %d bytes\n" % os.path.getsize(path))

    is32 = info["machine"] == 0x014C
    print("%-4s 32-bit PE (machine 0x%04X, expected 0x014C)"
          % ("OK" if is32 else "FAIL", info["machine"]))
    failures += 0 if is32 else 1

    is_dll = bool(info["chars"] & 0x2000)
    print("%-4s marked as DLL (characteristics 0x%04X)"
          % ("OK" if is_dll else "FAIL", info["chars"]))
    failures += 0 if is_dll else 1

    ours = sorted(read_exports(path))
    theirs = sorted(read_exports(REAL_DLL))
    same = ours == theirs
    print("%-4s exports match the real version.dll (%d ours / %d theirs)"
          % ("OK" if same else "FAIL", len(ours), len(theirs)))
    failures += 0 if same else 1
    if not same:
        missing = [n for n in theirs if n not in ours]
        extra = [n for n in ours if n not in theirs]
        if missing:
            print("       MISSING: %s" % ", ".join(missing))
        if extra:
            print("       EXTRA  : %s" % ", ".join(extra))

    imports = [i.upper() for i in info["imports"]]
    only_kernel = imports == ["KERNEL32.DLL"]
    print("%-4s imports only KERNEL32 -> %s"
          % ("OK" if only_kernel else "WARN", ", ".join(info["imports"]) or "(none)"))

    print("\nsections:")
    for name, vaddr, vsize, _raw, rawsize in info["sections"]:
        print("  %-8s VA 0x%06X  vsize 0x%06X  raw 0x%06X" % (name, vaddr, vsize, rawsize))

    print("")
    if failures:
        print("%d CHECK(S) FAILED" % failures)
        return 1
    print("ALL CHECKS PASSED -- this DLL can be dropped next to swkotor2.exe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
