"""Builds the gates table and the first-pass token placement analysis for the KOTOR 2 world.

Inputs (research, all static analysis):
  research/story/token_candidates.json   the 19 candidate gates (hook, flags, softlock note)
  research/gating/gating_plan.json       the 35-beat plan (which modules each beat uses, which gate each beat takes under model A)
  research/story/planets.json            module -> planet
  research/quests/quest_review.csv       the quests (planet, modules, missable / one-off flags)

Outputs:
  data/gates.json                        the gates table (edit this to move, disable or re-rate a gate)
  data/location_gate_requirements.csv    one row per quest: what it needs and whether a progression token may be placed there
  docs/GATES_AND_TOKEN_PLACEMENT.md      summary for review

Rules (first draft, all provisional):
  * Gate k of a family passes when the player holds k tokens of that family ("at least k", as in K1).
  * A module needs every gate of its own family whose beat is at or before the module's first beat; Telos gates apply to everything after them
    (the open phase starts after TEL3); the late game (Enclave onward) needs all four Master gates plus the Endgame gates by beat order.
  * Over-requiring is safe (a seed gets more conservative), under-requiring can strand a token, so ties go to the higher requirement.
  * Decision 2026-10-30 (user): every quest that can fire is a location and may hold a token, including quests whose window the player can miss.
    A repair step (to be designed) makes a missed quest fire anyway. Not used: cut quests (possibly restored by TSLRCM later), end-game quests/areas, and the two Pazaak Rules tutorials (dropped as checks).
    Access rules still apply: a location after the Enclave council needs the gates that lead there, so a token cannot sit behind its own gate.
"""
import csv
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


FAMILY_OF_PLANET = {
    "Nar Shaddaa": "NAR", "Dxun": "DXN", "Onderon": "DXN", "Dantooine": "DAN", "Korriban": "KOR",
}
SERIAL = ("TEL", "FIN")
RISK_WORD = ("high", "medium", "low")

EXTRA_NOTES = {
    "NAR1": "Window B for Zez-Kai Ell (the yacht arc) opens here. If the Visquis attack closes window A while a token is missing, only the yacht route remains and it needs this arc to have started. Re-rated by the playthrough.",
    "NAR3": "Gate BOTH spawn triggers (303NAR/a_zezconv and a_351zezconv). Reimplement them so he is created whenever the token is held and the Visquis audience has happened, even after the attack (to be confirmed in the game).",
    "DXN2": "502OND_End_First also unlocks the map after the blockade detour: do not let the gate hold that flag.",
    "DAN3": "Duplicate of FIN1 (the same script, 605DAN/k_enter_605). Disabled by default; FIN1 alone covers the Enclave.",
    "KOR2": "Needs a second wrapper on 701KOR/tr_exit702_end so the Academy door stays unlocked until 702KOR_Vash == 1.",
}
DEFAULT_DISABLED = {"DAN3"}
# Where the hook really is, from the decoded scripts (docs/GATING_PLAN.md corrections): replaces the candidate list's text for these gates.
HOOK_OVERRIDES = {
    "FIN1": {"kind": "T", "target": "605DAN/tr_enclave_cam (trigger ScriptOnEnter)", "called_from": "605DAN trigger tr_enclave_cam",
             "detail": "once 650DAN_Rebuilt != 0 the trigger starts dlg encl_cam, whose E1 runs a_open_door('door_650'); the gate holds that branch back. k_enter_605 only "
                       "sets Rebuilt and the Enclave_Door of the 605 sublevel, so it is left alone."},
    "NAR3": {"kind": "D", "target": "ap_jedi_inc (the Jedi count +1 at the nodes of dlg zezkaiel, which the client points at it)", "called_from": "dlg zezkaiel@303NAR E2/E113",
             "detail": "The conversation is never held back; the +1 on the Jedi count waits for the token (nss/k2ap_master.nss), then the dispatcher applies it."},
    "DXN3": {"kind": "D", "target": "ap_jedi_inc (the Jedi count +1 at the nodes of dlg kavar, which the client points at it)", "called_from": "dlg kavar@506OND E7/E88",
             "detail": "The conversation is never held back (the palace does not let the player leave); the +1 waits for the token."},
    "DAN2": {"kind": "D", "target": "ap_jedi_inc (the Jedi count +1 at the nodes of dlg vrook, which the client points at it)", "called_from": "dlg vrook@602DAN E11/E13/R0",
             "detail": "The conversation is never held back; the +1 waits for the token."},
    "KOR1": {"kind": "T", "target": "702KOR/a_open_door_ente (entry script of dlg kreia_si)", "called_from": "702KOR dlg kreia_si E2",
             "detail": "opens the Academy entrance door; held back, the door stays shut and the conversation can come round again"},
}


def risk_of(text):
    t = text.lower()
    for w in RISK_WORD:
        if t.startswith(w):
            return w
    for w in RISK_WORD:
        if w in t[:60]:
            return w
    return "unknown"


def build_gates(cands, beats):
    beat_of_gate = {}
    for i, b in enumerate(beats):
        gid = b["models"]["A"]
        if gid and gid != "-":
            beat_of_gate[gid] = (i, b["id"], b["name"])
    gates = []
    for c in cands:
        gid = c["id"]
        i, bid, bname = beat_of_gate.get(gid, (None, None, None))
        gates.append({
            "id": gid,
            "family": c["family"],
            "tokens_needed": c["gate"] if c["family"] != "Endgame" else c["gate"],
            "beat": bid,
            "beat_name": bname or c["beat"],
            "beat_index": i,
            "hook": HOOK_OVERRIDES.get(gid, c["hook"]),
            "risk": risk_of(c["softlock"]),
            "softlock_note": c["softlock"],
            "door_rando_bypass": c["door_rando_bypass"],
            "enabled": gid not in DEFAULT_DISABLED,
            "notes": EXTRA_NOTES.get(gid, ""),
            "confidence": c.get("confidence", ""),
        })
    return gates


def main():
    cands = load("research/story/token_candidates.json")["candidates"]
    plan = load("research/gating/gating_plan.json")
    beats = plan["beats"]
    planets = load("research/story/planets.json")["planets"]

    module_planet = {}
    for pname, pdata in planets.items():
        for m in pdata["modules"]:
            module_planet[m["module"].upper()] = pname

    gates = build_gates(cands, beats)
    enabled = {g["id"]: g for g in gates if g["enabled"]}

    first_beat = {}
    for i, b in enumerate(beats):
        for m in b["modules"]:
            first_beat.setdefault(m.upper(), i)

    # the point of no return: first beat that enters the Enclave council chain
    pnr = next(i for i, b in enumerate(beats) if "650DAN" in [m.upper() for m in b["modules"]])
    last_open = max(i for i, b in enumerate(beats) if b["phase"] == "P4")

    def module_requirements(mod):
        """{family: tokens needed} for reaching module `mod`."""
        mod = mod.upper()
        req = {}
        e = first_beat.get(mod)
        if e is None:
            return req, "no beat lists this module (baseline only)"
        # serial families by beat order
        for g in enabled.values():
            if g["beat_index"] is None or g["family"] == "Dxun/Onderon" or g["family"] in ("Nar Shaddaa", "Dantooine", "Korriban"):
                continue
            if g["beat_index"] <= e:
                fam = g["family"]
                req[fam] = max(req.get(fam, 0), g["tokens_needed"])
        # planet families: only for modules of that planet, gates whose beat is at or before the module's first beat
        planet = module_planet.get(mod)
        pfam = FAMILY_OF_PLANET.get(planet)
        fam_names = {"NAR": "Nar Shaddaa", "DXN": "Dxun/Onderon", "DAN": "Dantooine", "KOR": "Korriban"}
        if e <= last_open and pfam:
            for g in enabled.values():
                if g["family"] == fam_names[pfam] and g["beat_index"] is not None and g["beat_index"] <= e:
                    req[g["family"]] = max(req.get(g["family"], 0), g["tokens_needed"])
        # the late game needs the four Master gates (Jedi_Found == 4 is a vanilla requirement of the Enclave)
        if e > last_open:
            for gid in ("NAR3", "DXN3", "DAN2", "KOR2"):
                g = enabled.get(gid)
                if g:
                    req[g["family"]] = max(req.get(g["family"], 0), g["tokens_needed"])
        return req, ""

    rows = []
    with open(os.path.join(ROOT, "research", "quests", "quest_review.csv"), newline="", encoding="utf-8") as f:
        quests = list(csv.DictReader(f))
    for q in quests:
        mods = [m for m in (q["modules_direct"] + ";" + q["modules_via_shared_scripts"]).replace(",", ";").split(";") if m.strip()]
        req = {}
        notes = []
        latest_e = -1
        for m in mods:
            r, note = module_requirements(m.strip())
            if note:
                notes.append(m.strip() + ": " + note)
            for k, v in r.items():
                req[k] = max(req.get(k, 0), v)
            e = first_beat.get(m.strip().upper())
            if e is not None:
                latest_e = max(latest_e, e)
        # Decision 2026-10-30 (user): the only quests not used are cut quests (and end-game quests and areas). Every other quest that can fire is a
        # location and may hold a token, even if the player can miss its window; a repair step (still to design) makes a missed quest fire anyway.
        reasons = []
        if q["cut_unused"].strip().lower().startswith(("yes", "partial")):
            reasons.append("cut quest in vanilla (no script or dialogue writes its completion); the Restoration mod (TSLRCM) may bring it back: revisit with restore support")
        if q["display_name"].startswith("Pazaak Rules"):
            reasons.append("dropped as a check (user decision 2026-10-30): a tutorial popup, trivially completed")
        mod_beats = [first_beat.get(m.strip().upper()) for m in mods]
        known = [e for e in mod_beats if e is not None]
        if q["completes_only_at_game_end"].strip():
            reasons.append("end-game quest (completes at the end of the game)")
        elif known and all(e >= pnr for e in known):
            reasons.append("end-game area (only exists after the Council)")
        miss = q["can_be_missed"].strip().lower()
        missable = miss.startswith(("yes", "maybe", "partial"))
        companion = q["companion_specific"].strip()
        game_end = q["completes_only_at_game_end"].strip()
        rows.append({
            "tag": q["tag"], "name": q["display_name"], "planet": q["planet"], "modules": ";".join(m.strip() for m in mods),
            "requires": " ".join("%s>=%d" % (k.replace(" ", "").replace("/", ""), v) for k, v in sorted(req.items())),
            "missable": "yes" if missable else "no",
            "companion_dependent": companion[:60],
            "completes_late": game_end[:50],
            "after_point_of_no_return": "yes" if latest_e >= pnr else "no",
            "token_ok": "no" if reasons else "yes",
            "token_blocked_because": "; ".join(reasons),
            "notes": " | ".join(notes),
        })

    # ---- area visit locations (first visit to a module) ----
    area_rows = []
    with open(os.path.join(ROOT, "research", "areas", "module_classification.csv"), newline="", encoding="utf-8") as f:
        for m in csv.DictReader(f):
            mod = m["module"].upper()
            cat = m["category"]
            used = cat in ("story_critical", "optional")
            why = "" if used else "not an area check (%s)" % cat
            req, note = module_requirements(mod)
            e = first_beat.get(mod)
            late = e is not None and e >= pnr
            if used and late:
                used, why = False, "end-game area (only exists after the Council)"
            area_rows.append({
                "module": mod, "planet": m["planet"], "name": m["display_name"], "category": cat, "used": "yes" if used else "no",
                "why_not": why, "requires": " ".join("%s>=%d" % (k.replace(" ", "").replace("/", ""), v) for k, v in sorted(req.items())),
                "before_telos_escape": "yes" if (e is not None and e <= first_beat.get("231TEL", 99) - 1) else "no",
            })
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "gates.json"), "w", encoding="utf-8") as f:
        json.dump({"_doc": "Gates table for the KOTOR 2 world. Generated by tools/build_gate_tables.py from research/story/token_candidates.json and "
                           "research/gating/gating_plan.json; edit 'enabled', 'risk' or 'notes' to change a gate. tokens_needed = tokens of the family "
                           "that must be held to pass.", "gates": gates}, f, indent=1)
    with open(os.path.join(ROOT, "data", "location_gate_requirements.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with open(os.path.join(ROOT, "data", "area_locations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(area_rows[0].keys()))
        w.writeheader()
        w.writerows(area_rows)
    ok = [r for r in rows if r["token_ok"] == "yes"]
    no = [r for r in rows if r["token_ok"] == "no"]
    by_reason = {}
    for r in no:
        for reason in r["token_blocked_because"].split("; "):
            by_reason[reason] = by_reason.get(reason, 0) + 1
    lines = ["# Gates and where tokens may be placed (first draft)", "",
             "Generated by `tools/build_gate_tables.py`. Provisional: for review and for correction from the first playthrough.", "",
             "## Gates (%d candidates, %d enabled)" % (len(gates), len(enabled)), "",
             "| Gate | Family | Tokens | Beat | Hook | Risk | Enabled | Note |", "|---|---|---|---|---|---|---|---|"]
    for g in gates:
        lines.append("| %s | %s | %d | %s | %s %s | %s | %s | %s |" % (
            g["id"], g["family"], g["tokens_needed"], g["beat"] or "-", g["hook"]["kind"], g["hook"]["target"][:48], g["risk"],
            "yes" if g["enabled"] else "no", g["notes"][:110]))
    miss_n = sum(1 for r in ok if r["missable"] == "yes")
    comp_n = sum(1 for r in ok if r["companion_dependent"])
    late_n = sum(1 for r in ok if r["after_point_of_no_return"] == "yes")
    lines += ["", "## Quest locations: where a token may sit", "",
              "%d quests analysed: **%d are used and may hold a progression token**, %d are not used (cut quests, end-game quests and areas, Pazaak Rules tutorials)." % (len(rows), len(ok), len(no)), "",
              "Among the %d that may: %d are missable (need the repair step), %d depend on a companion, %d lie after the point of no return." % (
                  len(ok), miss_n, comp_n, late_n), "",
              "Known overshoot: a module counts from the first beat that uses it, so the Enclave courtyard (605DAN, first used by the Council beat) is treated as "
              "late and a few Dantooine side quests that touch it show the four-Master requirement although the courtyard is open from the start of the Dantooine visit. "
              "That makes them harder to reach in the logic (safe, but conservative); to be tightened from the first playthrough.", "",
              "Reasons a quest is not used:", ""]
    for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        lines.append("* %d: %s" % (n, reason))
    lines += ["", "### Quests that may hold a token, by what they need first", ""]
    groups = {}
    for r in ok:
        groups.setdefault(r["requires"] or "(nothing: open from the start)", []).append(r["name"])
    for k, names in sorted(groups.items(), key=lambda kv: (len(kv[0]), kv[0])):
        lines.append("* **%s** (%d): %s" % (k, len(names), ", ".join(sorted(names))))
    lines += ["", "### Quests that are not used", ""]
    for r in no:
        lines.append("* %s (%s): %s" % (r["name"], r["planet"], r["token_blocked_because"]))
    with open(os.path.join(ROOT, "docs", "GATES_AND_TOKEN_PLACEMENT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("gates: %d (%d enabled); quests: %d, token ok: %d, not ok: %d" % (len(gates), len(enabled), len(rows), len(ok), len(no)))
    print("point of no return beat index:", pnr, beats[pnr]["id"], "; last open-phase beat:", last_open, beats[last_open]["id"])


main()
