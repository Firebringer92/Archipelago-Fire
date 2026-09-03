"""Generate a proxy-DLL .def that forwards every export to the user's real DLL.

Read-only. Parses the export table of a real DLL and emits a module-definition
file whose every entry forwards to `<target>.<name>` at the original ordinal, so
the proxy is a transparent stand-in.

KSE never redistributes the game's real DLL, and the export list is that DLL's
content, not ours. So:
  * this generator (our work) is committed;
  * its OUTPUT .def is a build artifact, generated from whatever DLL the user
    has, and is gitignored -- never committed.

Usage:
    python tools/generate_forwarders.py --dll <path-to-real.dll> \
        --target binkw32_real --out build/proxy.def

`--target` is the module the proxy forwards to. The install step renames the
game's real binkw32.dll to <target>.dll (default binkw32_real.dll); the proxy
loads that, never a copy we ship.
"""

import argparse
import struct
import sys


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def parse_exports(path):
    """Return (ordinal_base, [(name, ordinal), ...]) for the DLL at `path`."""
    d = read(path)
    if d[:2] != b"MZ":
        sys.exit("%s: not a PE (no MZ)" % path)
    e = struct.unpack_from("<I", d, 0x3C)[0]
    if d[e:e + 4] != b"PE\0\0":
        sys.exit("%s: not a PE (no PE signature)" % path)

    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    if magic != 0x10B:
        sys.exit("%s: not a 32-bit PE32 image (magic 0x%04x); the proxy must "
                 "match the 32-bit game" % (path, magic))

    exp_rva, exp_size = struct.unpack_from("<II", d, opt + 96)
    if exp_rva == 0:
        sys.exit("%s: has no export directory" % path)

    secs = []
    so = opt + optsz
    for i in range(nsec):
        o = so + i * 40
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", d, o + 8)
        secs.append((vaddr, vsize, roff, rsize))

    def rva2off(rva):
        for vaddr, vsize, roff, rsize in secs:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return roff + (rva - vaddr)
        sys.exit("%s: RVA 0x%x not in any section" % (path, rva))

    eo = rva2off(exp_rva)
    ordinal_base = struct.unpack_from("<I", d, eo + 16)[0]
    n_names = struct.unpack_from("<I", d, eo + 24)[0]
    names_rva = struct.unpack_from("<I", d, eo + 32)[0]
    ord_rva = struct.unpack_from("<I", d, eo + 36)[0]

    names = []
    no = rva2off(names_rva)
    oo = rva2off(ord_rva)
    for i in range(n_names):
        name_rva = struct.unpack_from("<I", d, no + i * 4)[0]
        noff = rva2off(name_rva)
        end = d.index(b"\0", noff)
        name = d[noff:end].decode("ascii", "replace")
        # AddressOfNameOrdinals[i] is the unbiased index; real ordinal adds base.
        unbiased = struct.unpack_from("<H", d, oo + i * 2)[0]
        names.append((name, ordinal_base + unbiased))

    return ordinal_base, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", required=True, help="path to the real DLL to mirror")
    ap.add_argument("--target", default="binkw32_real",
                    help="module the proxy forwards to (default binkw32_real)")
    ap.add_argument("--out", required=True, help="output .def path")
    args = ap.parse_args()

    ordinal_base, names = parse_exports(args.dll)
    if not names:
        sys.exit("%s: no named exports; cannot build a name-forwarding proxy" % args.dll)

    lines = []
    lines.append("; GENERATED FILE -- do not edit, do not commit.")
    lines.append("; Produced by tools/generate_forwarders.py from a local real DLL.")
    lines.append("; Every export forwards to the user's own DLL (%s.dll); this project" % args.target)
    lines.append("; ships no copy of it.")
    lines.append("EXPORTS")
    for name, ordinal in sorted(names, key=lambda x: x[1]):
        # name=target.name @ordinal
        #   * the token before '=' becomes our export name (identical, incl. any
        #     decoration like _Foo@12);
        #   * the token after '=' is the forwarder to the real DLL;
        #   * the trailing ' @<n>' fixes our ordinal to match the original, so the
        #     game resolves correctly whether it imports by name or by ordinal.
        lines.append("    %s=%s.%s @%d" % (name, args.target, name, ordinal))

    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="ascii") as fh:
        fh.write(text)

    print("wrote %s: %d forwarders -> %s.dll (ordinal base %d)"
          % (args.out, len(names), args.target, ordinal_base))


if __name__ == "__main__":
    main()
