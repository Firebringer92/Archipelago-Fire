r"""
Removes the NOP instructions from a compiled script (.ncs).

nwnsc puts a NOP (opcode 0x2D, "do nothing") at some jump landing spots, mostly where an if/else ends. The original BioWare compiler never emits one, and the KOTOR
engine stops running a script when it reaches one: no error, the rest of the script simply never runs. Taking a NOP out is exact: a jump that landed on it lands on the
instruction after it, and every other jump distance is adjusted for the two bytes that are gone.

compile_nss() (nwnnsscomp_path.py) runs strip_nops() on every script nwnsc produces. The reader is self-contained (it needs no pykotor) and checks its own work: it
refuses a file it cannot read to the last byte, a jump that does not land on an instruction, and a result whose instructions are not the original ones minus the NOPs.

  ncs_nops.py FILE.ncs [...]        count the NOPs in each file
  ncs_nops.py --strip FILE.ncs ...  remove them in place
"""
import os
import struct
import sys

NOP = 0x2D
JUMPS = (0x1D, 0x1E, 0x1F, 0x25)                        # JMP, JSR, JZ, JNZ: a signed 32-bit distance from the start of the instruction
HEADER = b"NCS V1.0B"
HEADER_LEN = 13                                          # "NCS V1.0", 'B', then the file size as 4 bytes (big endian)

# Instruction lengths in bytes: opcode, qualifier, then the operands (big endian). CONST of a string is handled separately.
_FIXED = {
    0x01: 8,        # CPDOWNSP   offset(4) size(2)
    0x02: 2,        # RSADD
    0x03: 8,        # CPTOPSP
    0x05: 5,        # ACTION     routine(2) argument count(1)
    0x1B: 6,        # MOVSP      offset(4)
    0x1C: 2,        # STORE_STATEALL
    0x1D: 6, 0x1E: 6, 0x1F: 6,                  # JMP JSR JZ
    0x20: 2,        # RETN
    0x21: 8,        # DESTRUCT   size(2) offset(2) keep(2)
    0x22: 2,        # NOT
    0x23: 6, 0x24: 6,                           # DECISP INCISP
    0x25: 6,        # JNZ
    0x26: 8, 0x27: 8,                           # CPDOWNBP CPTOPBP
    0x28: 6, 0x29: 6,                           # DECIBP INCIBP
    0x2A: 2, 0x2B: 2,                           # SAVEBP RESTOREBP
    0x2C: 10,       # STORE_STATE bp(4) sp(4)
    0x2D: 2,        # NOP
}
_NO_OPERAND = set(range(0x06, 0x1B))                     # the arithmetic, comparison and logic operators, 2 bytes each


class NcsError(Exception):
    pass


def _length(data, pos):
    op = data[pos]
    if op in _FIXED:
        return _FIXED[op]
    if op in _NO_OPERAND:
        if op in (0x0B, 0x0C) and pos + 1 < len(data) and data[pos + 1] == 0x24:     # EQUAL / NEQUAL of two structures carry their size
            return 4
        return 2
    if op == 0x04:                                                                   # CONST: int, float, string (length + bytes), object
        qual = data[pos + 1]
        if qual in (0x03, 0x04, 0x06):
            return 6
        if qual == 0x05:
            return 4 + struct.unpack_from(">H", data, pos + 2)[0]
    raise NcsError(f"unknown instruction 0x{op:02X} at offset {pos}")


def parse(data):
    """Returns [(offset, length)] for every instruction. Raises NcsError unless the file is read exactly to its end."""
    if data[:9] != HEADER:
        raise NcsError("not a compiled script (header is not 'NCS V1.0B')")
    size = struct.unpack_from(">I", data, 9)[0]
    if size != len(data):
        raise NcsError(f"the header says {size} bytes, the file has {len(data)}")
    out = []
    pos = HEADER_LEN
    try:
        while pos < len(data):
            n = _length(data, pos)
            out.append((pos, n))
            pos += n
    except (IndexError, struct.error):
        raise NcsError("an instruction runs past the end of the file")
    if pos != len(data):
        raise NcsError("the last instruction runs past the end of the file")
    return out


def count_nops(data):
    return sum(1 for pos, _ in parse(data) if data[pos] == NOP)


def _target(data, pos):
    return pos + struct.unpack_from(">i", data, pos + 2)[0]


def strip_nops(data):
    """Returns the script without its NOPs (the same bytes when there are none)."""
    ins = parse(data)
    nops = [pos for pos, _ in ins if data[pos] == NOP]
    if not nops:
        return data
    starts = {pos for pos, _ in ins}
    # where each instruction lands in the new file, and where a jump that pointed at a NOP goes instead (the next instruction that is not a NOP)
    new_pos = {}
    removed = 0
    for pos, n in ins:
        if data[pos] == NOP:
            removed += n
        else:
            new_pos[pos] = pos - removed
    next_real = {}
    following = None
    for pos, _ in reversed(ins):
        if data[pos] == NOP:
            next_real[pos] = following
        else:
            following = pos
    out = bytearray(data[:HEADER_LEN])
    for pos, n in ins:
        if data[pos] == NOP:
            continue
        chunk = bytearray(data[pos:pos + n])
        if data[pos] in JUMPS:
            target = _target(data, pos)
            if target not in starts:
                raise NcsError(f"the jump at offset {pos} does not land on an instruction")
            if data[target] == NOP:
                target = next_real[target]
                if target is None:
                    raise NcsError(f"the jump at offset {pos} lands on a NOP with nothing after it")
            struct.pack_into(">i", chunk, 2, new_pos[target] - new_pos[pos])
        out += chunk
    struct.pack_into(">I", out, 9, len(out))
    result = bytes(out)
    _verify(data, result)
    return result


def _verify(before, after):
    """The result must be the original instructions minus the NOPs, every jump landing on the same instruction as before."""
    a, b = parse(before), parse(after)
    kept = [(pos, n) for pos, n in a if before[pos] != NOP]
    if len(kept) != len(b):
        raise NcsError("the stripped script has a different number of instructions than expected")
    index_in_after = {pos: i for i, (pos, _) in enumerate(b)}
    index_in_kept = {pos: i for i, (pos, _) in enumerate(kept)}
    for (old_pos, old_n), (new_pos, new_n) in zip(kept, b):
        if before[old_pos:old_pos + 2] != after[new_pos:new_pos + 2] or old_n != new_n:
            raise NcsError("an instruction changed")
        if before[old_pos] in JUMPS:
            t_old = _target(before, old_pos)
            while before[t_old] == NOP:                 # a jump to a NOP means: the next real instruction
                t_old += 2
            t_new = _target(after, new_pos)
            if t_new not in index_in_after or index_in_kept.get(t_old) != index_in_after[t_new]:
                raise NcsError(f"the jump at offset {old_pos} lands on a different instruction after the NOPs were removed")
        elif before[old_pos:old_pos + old_n] != after[new_pos:new_pos + new_n]:
            raise NcsError("an instruction's operands changed")


def strip_nops_file(path):
    """Strips the file in place (written next to it, then moved over it). Returns the number of NOPs removed."""
    with open(path, "rb") as f:
        data = f.read()
    n = count_nops(data)
    if n:
        tmp = path + ".stripping"
        with open(tmp, "wb") as f:
            f.write(strip_nops(data))
        os.replace(tmp, path)
    return n


def nops_in_zip(zip_path):
    """[(name, count)] for every .ncs in the zip that holds a NOP, and [(name, reason)] for every one that cannot be read. Used by the packager and the release gate."""
    import zipfile
    with_nops, unreadable = [], []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.filename.lower().endswith(".ncs"):
                try:
                    n = count_nops(z.read(info))
                except NcsError as e:
                    unreadable.append((info.filename, str(e)))
                    continue
                if n:
                    with_nops.append((info.filename, n))
    return with_nops, unreadable


def main(argv):
    strip = "--strip" in argv
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)
    total = 0
    for path in files:
        try:
            if strip:
                n = strip_nops_file(path)
                print(f"{path}: removed {n} NOP(s)")
            else:
                with open(path, "rb") as f:
                    n = count_nops(f.read())
                print(f"{path}: {n} NOP(s)")
            total += n
        except NcsError as e:
            print(f"{path}: cannot read ({e})")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
