r"""
Joins compiled scripts (.ncs) into one script, without ExecuteScript.

Why this exists: a script that another script starts with ExecuteScript does not get the event it was started by. The game's area entry scripts, trigger scripts and
dialogue action scripts read that event (GetEnteringObject(), GetScriptParameter(1) ...), so a hook that runs the game's script through ExecuteScript changes what the
script does (live, 2026-11-14: the Ithorian attack in 204TEL never started; the Telos shuttle gave a black screen). Here the game's own compiled script is kept byte for
byte and our code is called from the same script, by a subroutine call, so the engine's event stays.

A compiled script starts with a 13 byte header and a small stub, "JSR main ; RETN" (a script that returns an int starts with "RSADDI" first and leaves the int on the
stack). Every part is copied whole, stub included, behind a new stub of our own that calls the parts in order; all jump distances inside a part stay right because the
part moves as one piece. A part is called like a function:

    pre     an int script (nss: int StartingConditional()); a non-zero answer ends the merged script before anything else runs (a held gate, a replaced turret)
    pickers int scripts, one per module-specific original: non-zero means "this is the original to run here"
    body    the game's own script (void)
    post    a void script that runs after the original (the token return, the dispatcher start)

    JSR pre ; JNZ end
    JSR picker1 ; JZ next1 ; JSR body1 ; JMP after ; next1:
    JSR body_last                       (the original without a picker: the fall-through one)
    after: JSR post
    end:   RETN

Only the stub shape "JSR main ; RETN" (void) or "RSADDI ; JSR main ; RETN" (int) is accepted for a part; anything else is refused (a script with global variables starts with the same stub, so it merges), and so is a
result that does not decode to its last byte or has a jump that does not land on an instruction.
"""
import struct

import ncs_nops

HEADER = b"NCS V1.0B"
HEADER_LEN = 13
_JSR, _JMP, _JZ, _JNZ, _RETN = 0x1E, 0x1D, 0x1F, 0x25, 0x20
_VOID_STUB = bytes([0x1E, 0x00, 0x00, 0x00, 0x00, 0x08, 0x20, 0x00])
_INT_STUB = bytes([0x02, 0x03]) + _VOID_STUB


class MergeError(Exception):
    pass


def part(data, kind, what="script"):
    """The bytes of a compiled script after its header, checked to start with the stub of `kind` ("void" or "int")."""
    try:
        ncs_nops.parse(data)
    except ncs_nops.NcsError as e:
        raise MergeError("%s cannot be read: %s" % (what, e))
    body = data[HEADER_LEN:]
    stub = _VOID_STUB if kind == "void" else _INT_STUB
    if body[:len(stub)] != stub:
        raise MergeError("%s does not start with the plain %s stub (a different return type, or a different start)" % (what, kind))
    return body


def merge(bodies, pre=None, post=None):
    """bodies: [(script bytes, picker script bytes or None)]; only the last may have no picker (it is the fall-through; with a picker on every original, nothing runs in
    a module no picker names). Returns the merged script bytes."""
    for i, (_, picker) in enumerate(bodies):
        if picker is None and i != len(bodies) - 1:
            raise MergeError("only the last original may be without a picker")
    code = []                                   # ("op", opcode, label) | ("call", part index) | ("label", name) | ("retn",)
    parts = []

    def add(data, kind, what):
        parts.append(part(data, kind, what))
        return len(parts) - 1
    if pre is not None:
        code += [("jump", _JSR, add(pre, "int", "pre-check")), ("jump", _JNZ, "end")]
    for i, (body, picker) in enumerate(bodies):
        if picker is not None:
            code += [("jump", _JSR, add(picker, "int", "picker %d" % (i + 1))), ("jump", _JZ, "next%d" % i),
                     ("jump", _JSR, add(body, "void", "original %d" % (i + 1))), ("jump", _JMP, "after"), ("label", "next%d" % i)]
        else:
            code += [("jump", _JSR, add(body, "void", "original %d" % (i + 1)))]
    code.append(("label", "after"))
    if post is not None:
        code.append(("jump", _JSR, add(post, "void", "post")))
    code += [("label", "end"), ("retn",)]

    pos = HEADER_LEN
    labels = {}
    for item in code:
        if item[0] == "label":
            labels[item[1]] = pos
        elif item[0] == "jump":
            pos += 6
        else:
            pos += 2
    starts = []
    for p in parts:
        starts.append(pos)
        pos += len(p)
    out = bytearray(HEADER + b"\x00\x00\x00\x00")
    for item in code:
        if item[0] == "label":
            continue
        if item[0] == "retn":
            out += bytes([_RETN, 0x00])
            continue
        target = starts[item[2]] if isinstance(item[2], int) else labels[item[2]]
        out += bytes([item[1], 0x00]) + struct.pack(">i", target - len(out))
    for p in parts:
        out += p
    struct.pack_into(">I", out, 9, len(out))
    result = bytes(out)
    check(result)
    return result


def check(data):
    """Raises MergeError unless every instruction decodes and every jump lands on an instruction start."""
    try:
        ins = ncs_nops.parse(data)
    except ncs_nops.NcsError as e:
        raise MergeError(str(e))
    starts = {p for p, _ in ins}
    for p, _ in ins:
        if data[p] in ncs_nops.JUMPS and ncs_nops._target(data, p) not in starts:
            raise MergeError("the jump at offset %d does not land on an instruction" % p)
    return True
