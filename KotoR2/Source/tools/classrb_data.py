"""Loads the TSL class-content tables into plain Python structures for the class rebuild design.

Read-only. Uses tools/tsl_data.py (Override > chitin precedence), so it sees the same 2DAs the game does.
Every table below is read from the game's own files; nothing is hand-typed except the class-id map and the
companion slot map (both already recorded in docs/CLASS_SYSTEM.md).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsl_data as T  # noqa: E402

N_LEVELS = 50
CLASS_IDS = list(range(17))
# class id -> feat.2da / skills.2da / featgain.2da column code (classes.2da featstable / skillstable / featgain)
# are read from classes.2da; they differ only in the armor column (JDG/JDC/..) which the rebuild does not use.

# spells.2da hard-named Force class columns -> class id
FORCE_COLS = {3: "guardian", 4: "consular", 5: "sentinel", 11: "weapmstr", 12: "jedimaster", 13: "watchman",
              14: "marauder", 15: "sithlord", 16: "assassin"}
# classpowergain.2da column for each Force class (classes.2da spellgaintable, lower-cased)
COMPANION_FEAT_COLS = ["handmaiden", "baodur", "hanharr", "hk47", "g0t0", "atton", "kreia"]

SKILL_NAMES = ["ComputerUse", "Demolitions", "Stealth", "Awareness", "Persuade", "Repair", "Security", "TreatInjury"]

JEDI_BASE = (3, 4, 5)
PRESTIGE = (11, 12, 13, 14, 15, 16)
FORCE_CLASSES = JEDI_BASE + PRESTIGE
DROID_CLASSES = (6, 7)
NONFORCE_CLASSES = (0, 1, 2, 6, 7, 8, 9, 10)


def cell(row, col):
    try:
        v = row.get_string(col)
    except Exception:  # noqa: BLE001
        return ""
    return "" if v in ("****", None) else v


def toint(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def load():
    d = {}
    cl = T.twoda("classes")
    d["classes"] = {}
    for i in range(cl.get_height()):
        r = cl.get_row(i)
        d["classes"][i] = {k: cell(r, k) for k in cl.get_headers()}
        d["classes"][i]["id"] = i
    d["class_label"] = {i: d["classes"][i]["label"] for i in d["classes"]}

    f = T.twoda("feat")
    d["feat_heads"] = f.get_headers()
    d["feats"] = {}
    for i in range(f.get_height()):
        r = f.get_row(i)
        d["feats"][i] = {k: cell(r, k) for k in f.get_headers()}
    sp = T.twoda("spells")
    d["spell_heads"] = sp.get_headers()
    d["spells"] = {}
    for i in range(sp.get_height()):
        r = sp.get_row(i)
        d["spells"][i] = {k: cell(r, k) for k in sp.get_headers()}
    sk = T.twoda("skills")
    d["skills"] = {}
    for i in range(sk.get_height()):
        r = sk.get_row(i)
        d["skills"][i] = {k: cell(r, k) for k in sk.get_headers()}
    fg = T.twoda("featgain")
    d["featgain"] = {}  # level -> {col: int}
    for i in range(fg.get_height()):
        r = fg.get_row(i)
        d["featgain"][i + 1] = {k: toint(cell(r, k), 0) for k in fg.get_headers() if k != "label"}
    pg = T.twoda("classpowergain")
    d["powergain"] = {}
    for i in range(pg.get_height()):
        r = pg.get_row(i)
        d["powergain"][i + 1] = {k: toint(cell(r, k), 0) for k in pg.get_headers() if k != "label"}
    cap = T.twoda("cls_spgn_jedi")
    d["power_cap"] = {}
    for i in range(cap.get_height()):
        r = cap.get_row(i)
        d["power_cap"][toint(cell(r, "level"))] = toint(cell(r, "spelllevel0"))
    d["cap_heads"] = cap.get_headers()
    # per-class tables: saves, attack
    d["saves"] = {}
    d["bab"] = {}
    for cid, c in d["classes"].items():
        st = T.twoda(c["savingthrowtable"].lower())
        d["saves"][cid] = {}
        for i in range(st.get_height()):
            r = st.get_row(i)
            d["saves"][cid][i + 1] = (toint(cell(r, "fortsave"), 0), toint(cell(r, "refsave"), 0), toint(cell(r, "willsave"), 0))
        at = T.twoda(c["attackbonustable"].lower())
        d["bab"][cid] = {i + 1: toint(cell(at.get_row(i), "bab"), 0) for i in range(at.get_height())}
    return d


def tlk(strref):
    s = toint(strref)
    return T.tlk_text(s) if s is not None and s >= 0 else ""


if __name__ == "__main__":
    d = load()
    print(len(d["feats"]), "feats", len(d["spells"]), "spells", len(d["featgain"]), "featgain levels",
          len(d["powergain"]), "powergain levels", "cap", list(d["power_cap"].items())[:5])
