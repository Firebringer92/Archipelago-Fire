"""Minimal PE reader shared by the K2SE tools.

Every tool here answers the same question -- "what byte is actually at this VA
in the shipped executable" -- so the parsing lives in one place. No third-party
modules: the toolchain must run on a bare Python 3.
"""

import os
import struct

DEFAULT_GAME = r"G:\SteamLibrary\steamapps\common\Knights of the Old Republic II"

# The pristine backup first: it is the copy the address database is keyed to.
# The live exe is accepted too, since the LAA patch only touches the PE header.
DEFAULT_CANDIDATES = [
    os.path.join(DEFAULT_GAME, "swkotor2.exe.pre-laa-backup"),
    os.path.join(DEFAULT_GAME, "swkotor2.exe"),
]

EXPECTED_TIMESTAMP = 0x5603005D
EXPECTED_IMAGEBASE = 0x00400000

# SHA-256 of the pristine Steam/Aspyr swkotor2.exe. Cross-checked against
# Kotor-Patch-Manager's kotor2_steam_aspyr.db game_version row, which carries the
# same value -- two independent records of the same file.
#
# NOTE: this is for the identity block in the log and for tooling only. K2SE must
# never gate installation on a whole-file hash: the 4GB/LAA patch and Steam's
# DeSteamify-style edits rewrite the file on disk, and gating on this would reject
# the very users who patched their exe. See DESIGN.md 3.6.
PRISTINE_SHA256 = "6A522E71631DCEE93467BD2010F3B23D9145326E1E2E89305F13AB104DBBFFEF"

# MSVC frame prologue: push ebp; mov ebp,esp. Every one of the 877 vanilla routine
# handlers starts with it, which is what makes it a usable liveness test for an
# address that claims to be a function entry point.
MSVC_PROLOGUE = b"\x55\x8b\xec"


class Image(object):
    def __init__(self, path):
        with open(path, "rb") as fh:
            self.data = fh.read()
        self.path = path
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        self.pe = pe
        self.num_sections = struct.unpack_from("<H", self.data, pe + 6)[0]
        self.timestamp = struct.unpack_from("<I", self.data, pe + 8)[0]
        self.opt_size = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.characteristics = struct.unpack_from("<H", self.data, pe + 22)[0]
        self.image_base = struct.unpack_from("<I", self.data, pe + 24 + 28)[0]

        self.sections = []
        sec = pe + 24 + self.opt_size
        for i in range(self.num_sections):
            o = sec + i * 40
            name = self.data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
            vsize, vaddr = struct.unpack_from("<II", self.data, o + 8)
            rawsize, raw = struct.unpack_from("<II", self.data, o + 16)
            self.sections.append((name, vaddr, vsize, raw, rawsize))

    # --- address translation -------------------------------------------------
    def off(self, va):
        rva = va - self.image_base
        for _n, vaddr, vsize, raw, _rs in self.sections:
            if vaddr <= rva < vaddr + vsize:
                return raw + (rva - vaddr)
        return None

    def section_of(self, va):
        rva = va - self.image_base
        for name, vaddr, vsize, _raw, _rs in self.sections:
            if vaddr <= rva < vaddr + vsize:
                return name
        return None

    # --- readers -------------------------------------------------------------
    def dword(self, va):
        o = self.off(va)
        if o is None or o + 4 > len(self.data):
            return None
        return struct.unpack_from("<I", self.data, o)[0]

    def byte(self, va):
        o = self.off(va)
        if o is None or o >= len(self.data):
            return None
        return self.data[o]

    def read(self, va, n):
        o = self.off(va)
        if o is None:
            return None
        return self.data[o:o + n]

    def text_range(self):
        for name, vaddr, vsize, _raw, _rs in self.sections:
            if name == ".text":
                return (self.image_base + vaddr, self.image_base + vaddr + vsize)
        return (0, 0)

    # --- the acceptance test for an imported function address ----------------
    def has_prologue(self, va):
        """True if `va` is in .text and starts with the MSVC frame prologue.

        This is the check that promotes a third-party address from 'claimed' to
        'verified on this binary'. It is not proof the function does what its
        name says -- only that something callable lives there.
        """
        if self.section_of(va) != ".text":
            return False
        b = self.read(va, len(MSVC_PROLOGUE))
        return b == MSVC_PROLOGUE


def find_default():
    for cand in DEFAULT_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return None


def open_default(argv_path=None):
    path = argv_path or find_default()
    if not path or not os.path.exists(path):
        raise SystemExit(
            "swkotor2.exe not found; pass the path as an argument\n"
            "  (looked in: %s)" % ", ".join(DEFAULT_CANDIDATES))
    return Image(path)
