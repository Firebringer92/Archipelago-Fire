"""
nwnsc writes NOP instructions that the KOTOR engine does not accept (it stops the script at the first one it runs, silently), so compile_nss() takes them out.
These tests build small compiled scripts by hand to check the remover: every NOP gone, every jump still landing on the same instruction, nothing else changed.
The compiler tests need tools/nwnsc and the game's nwscript.nss and are skipped without them.
"""
import os
import struct
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import ncs_nops  # noqa: E402


def asm(program):
    """Assembles a list of (label, mnemonic, operand) into an .ncs. Jump operands are label names; labels may be None."""
    sizes = {"JSR": 6, "JMP": 6, "JZ": 6, "JNZ": 6, "RETN": 2, "NOP": 2, "RSADD": 2, "MOVSP": 6, "CONSTI": 6, "ACTION": 5, "STORE_STATE": 10,
             "DESTRUCT": 8, "EQUALTT": 4, "ADDII": 2, "CPTOPSP": 8}
    pos = ncs_nops.HEADER_LEN
    where = {}
    for label, mnemonic, operand in program:
        if label:
            where[label] = pos
        pos += 4 + len(operand) if mnemonic == "CONSTS" else sizes[mnemonic]
    total = pos
    out = bytearray(ncs_nops.HEADER)
    out += struct.pack(">I", total)
    opcodes = {"JSR": 0x1E, "JMP": 0x1D, "JZ": 0x1F, "JNZ": 0x25}
    pos = ncs_nops.HEADER_LEN
    for label, mnemonic, operand in program:
        start = len(out)
        if mnemonic in opcodes:
            out += bytes([opcodes[mnemonic], 0]) + struct.pack(">i", where[operand] - pos)
        elif mnemonic == "RETN":
            out += bytes([0x20, 0])
        elif mnemonic == "NOP":
            out += bytes([0x2D, 0])
        elif mnemonic == "RSADD":
            out += bytes([0x02, 3])
        elif mnemonic == "MOVSP":
            out += bytes([0x1B, 0]) + struct.pack(">i", operand)
        elif mnemonic == "CONSTI":
            out += bytes([0x04, 3]) + struct.pack(">i", operand)
        elif mnemonic == "CONSTS":
            out += bytes([0x04, 5]) + struct.pack(">H", len(operand)) + operand.encode("ascii")
        elif mnemonic == "ACTION":
            out += bytes([0x05, 0]) + struct.pack(">HB", operand, 1)
        elif mnemonic == "STORE_STATE":
            out += bytes([0x2C, 0x10]) + struct.pack(">ii", 0, 0)
        elif mnemonic == "DESTRUCT":
            out += bytes([0x21, 0]) + struct.pack(">hhh", 4, 0, 4)
        elif mnemonic == "EQUALTT":
            out += bytes([0x0B, 0x24]) + struct.pack(">H", 12)
        elif mnemonic == "ADDII":
            out += bytes([0x14, 0x20])
        elif mnemonic == "CPTOPSP":
            out += bytes([0x03, 1]) + struct.pack(">ih", -4, 4)
        pos += len(out) - start
    assert len(out) == total
    return bytes(out)


def landing(data):
    """For every jump: (the jump's index, the index of the instruction it lands on), skipping NOPs, and the list of non-NOP opcodes."""
    ins = ncs_nops.parse(data)
    index = {pos: i for i, (pos, _) in enumerate(ins)}
    real = [pos for pos, _ in ins if data[pos] != ncs_nops.NOP]
    rank = {pos: i for i, pos in enumerate(real)}
    jumps = []
    for pos, _ in ins:
        if data[pos] in ncs_nops.JUMPS:
            target = ncs_nops._target(data, pos)
            while data[target] == ncs_nops.NOP:
                target += 2
            jumps.append((rank[pos], rank[target]))
    return jumps, [data[pos] for pos in real], index


# if (x) { ... } else { ... }  then more code: the shape nwnsc puts a NOP in
IF_ELSE = [
    (None, "JSR", "main"), (None, "RETN", None),
    ("main", "RSADD", None), (None, "CONSTI", 1),
    (None, "JZ", "else"), (None, "CONSTI", 5), (None, "JMP", "end"),
    ("else", "NOP", None), (None, "CONSTI", 6),
    ("end", "MOVSP", -4), (None, "RETN", None),
]


class TestRemovingNops(unittest.TestCase):
    def test_a_script_without_nops_comes_back_unchanged(self):
        program, label = [], None
        for p in IF_ELSE:
            if p[1] == "NOP":
                label = p[0]                                # the NOP's label moves to the instruction after it
                continue
            program.append((label, p[1], p[2]) if label else p)
            label = None
        data = asm(program)
        self.assertEqual(ncs_nops.count_nops(data), 0)
        self.assertIs(ncs_nops.strip_nops(data), data)

    def test_the_nop_is_removed_and_the_jumps_still_land_on_the_same_instructions(self):
        data = asm(IF_ELSE)
        self.assertEqual(ncs_nops.count_nops(data), 1)
        out = ncs_nops.strip_nops(data)
        self.assertEqual(ncs_nops.count_nops(out), 0)
        self.assertEqual(len(out), len(data) - 2)
        self.assertEqual(struct.unpack_from(">I", out, 9)[0], len(out))                 # the size in the header follows
        self.assertEqual(landing(out)[:2], landing(data)[:2])

    def test_a_jump_that_spans_the_nop_gets_shorter_and_one_that_landed_on_it_lands_after_it(self):
        data = asm(IF_ELSE)
        out = ncs_nops.strip_nops(data)
        before = {data[p]: ncs_nops._target(data, p) - p for p, _ in ncs_nops.parse(data) if data[p] in (0x1F, 0x1D)}
        after = {out[p]: ncs_nops._target(out, p) - p for p, _ in ncs_nops.parse(out) if out[p] in (0x1F, 0x1D)}
        self.assertEqual(after[0x1D], before[0x1D] - 2)           # JMP over the else part: spans the NOP
        self.assertEqual(after[0x1F], before[0x1F] + 0)           # JZ to the NOP: now lands on the CONST after it, which is where the NOP started

    def test_a_backward_jump_across_a_nop(self):
        program = [(None, "JSR", "main"), (None, "RETN", None), ("main", "RSADD", None), ("top", "CONSTI", 1), (None, "NOP", None), (None, "CONSTI", 2),
                   (None, "JNZ", "top"), (None, "MOVSP", -4), (None, "RETN", None)]
        data = asm(program)
        out = ncs_nops.strip_nops(data)
        self.assertEqual(landing(out)[:2], landing(data)[:2])
        self.assertEqual(ncs_nops.count_nops(out), 0)

    def test_several_nops_in_a_row(self):
        program = [(None, "JSR", "main"), (None, "RETN", None), ("main", "RSADD", None), (None, "CONSTI", 1), (None, "JZ", "a"), (None, "CONSTI", 3),
                   ("a", "NOP", None), (None, "NOP", None), (None, "NOP", None), (None, "MOVSP", -8), (None, "RETN", None)]
        data = asm(program)
        out = ncs_nops.strip_nops(data)
        self.assertEqual(ncs_nops.count_nops(out), 0)
        self.assertEqual(len(out), len(data) - 6)
        self.assertEqual(landing(out)[:2], landing(data)[:2])

    def test_every_kind_of_instruction_is_read_with_the_right_length(self):
        program = [(None, "JSR", "main"), (None, "RETN", None), ("main", "RSADD", None), (None, "CONSTS", "hello"), (None, "CONSTI", 7),
                   (None, "ACTION", 150), (None, "STORE_STATE", None), (None, "JMP", "skip"), (None, "DESTRUCT", None), (None, "RETN", None),
                   ("skip", "EQUALTT", None), (None, "ADDII", None), (None, "CPTOPSP", None), (None, "NOP", None), (None, "RETN", None)]
        data = asm(program)
        self.assertEqual(len(ncs_nops.parse(data)), len(program))
        self.assertEqual(ncs_nops.count_nops(ncs_nops.strip_nops(data)), 0)

    def test_a_jump_to_a_nop_with_nothing_after_it_is_refused(self):
        program = [(None, "JSR", "end"), (None, "RETN", None), ("end", "NOP", None)]
        with self.assertRaises(ncs_nops.NcsError):
            ncs_nops.strip_nops(asm(program))

    def test_a_file_that_is_not_a_compiled_script_is_refused(self):
        good = asm(IF_ELSE)
        for bad in (b"", b"just text", good[:-1], good + b"\x00", b"NCS V1.0B" + struct.pack(">I", 99) + b"\x00" * 10,
                    good[:ncs_nops.HEADER_LEN] + b"\xEE\x00" + good[ncs_nops.HEADER_LEN + 2:]):
            with self.assertRaises(ncs_nops.NcsError, msg=bad[:20]):
                ncs_nops.strip_nops(bad)

    def test_strip_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.ncs")
            with open(path, "wb") as f:
                f.write(asm(IF_ELSE))
            self.assertEqual(ncs_nops.strip_nops_file(path), 1)
            with open(path, "rb") as f:
                self.assertEqual(ncs_nops.count_nops(f.read()), 0)
            self.assertEqual(ncs_nops.strip_nops_file(path), 0)
            self.assertEqual(os.listdir(tmp), ["t.ncs"])


@unittest.skipUnless(os.path.isfile(os.path.join(REPO_ROOT, "tools", "nwnsc", "nwnsc.exe")), "needs tools/nwnsc")
class TestCompilerOutput(unittest.TestCase):
    SOURCE = ("void main() { int n = GetLocalNumber(OBJECT_SELF, 1); if (n == 1) { n = 2; } else { n = 3; } SetLocalNumber(OBJECT_SELF, 2, n); }\n")

    def setUp(self):
        self.src_dir = os.path.join(REPO_ROOT, "extender", "scripts_src")
        if not os.path.isfile(os.path.join(self.src_dir, "nwscript.nss")):
            self.skipTest("nwscript.nss has not been written from a KOTOR install yet")

    def test_nwnsc_really_does_write_a_nop_for_an_if_else(self):
        # if this stops being true the remover is no longer needed, and this test says so
        import subprocess
        import nwnnsscomp_path
        with tempfile.TemporaryDirectory() as tmp:
            nss, ncs = os.path.join(tmp, "t.nss"), os.path.join(tmp, "t.ncs")
            with open(nss, "w") as f:
                f.write(self.SOURCE)
            subprocess.run([nwnnsscomp_path.NWNSC, "-q", "-i", tmp + ";" + self.src_dir, "-r", ncs, nss], capture_output=True, cwd=tmp, timeout=60)
            with open(ncs, "rb") as f:
                self.assertGreater(ncs_nops.count_nops(f.read()), 0)

    def test_compile_nss_leaves_no_nop_and_no_side_file(self):
        import nwnnsscomp_path
        with tempfile.TemporaryDirectory() as tmp:
            nss, ncs = os.path.join(tmp, "t.nss"), os.path.join(tmp, "t.ncs")
            with open(nss, "w") as f:
                f.write(self.SOURCE)
            result = nwnnsscomp_path.compile_nss(nss, ncs, cwd=self.src_dir, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with open(ncs, "rb") as f:
                self.assertEqual(ncs_nops.count_nops(f.read()), 0)
            self.assertEqual(sorted(os.listdir(tmp)), ["t.ncs", "t.nss"])

    def test_a_failed_compile_leaves_an_older_script_alone(self):
        import nwnnsscomp_path
        with tempfile.TemporaryDirectory() as tmp:
            nss, ncs = os.path.join(tmp, "t.nss"), os.path.join(tmp, "t.ncs")
            with open(nss, "w") as f:
                f.write("void main() { int x = ; }\n")
            with open(ncs, "wb") as f:
                f.write(b"older")
            nwnnsscomp_path.compile_nss(nss, ncs, cwd=self.src_dir, timeout=60)
            with open(ncs, "rb") as f:
                self.assertEqual(f.read(), b"older")
            self.assertEqual(sorted(os.listdir(tmp)), ["t.ncs", "t.nss"])


if __name__ == "__main__":
    unittest.main()
