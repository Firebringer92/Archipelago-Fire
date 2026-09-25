"""
Called by the extender (C code, via CreateProcess) whenever either (a) a
new check needs arming, or (b) the player's current area changes. Computes
the "armed set" = current area + its direct neighbors (from _graph.json),
regenerates any newly-in-scope area's trampoline with the CURRENT pending
batch, and clears (regenerates back to empty) any previously-armed area
that's fallen out of scope -- so stray un-fired batches don't linger
somewhere the player wandered away from.

State lives in three small JSON files next to the trampoline sources:
  _pending_queue.json  -- list of arm IDs not yet confirmed delivered
  _armed_state.json    -- {area_base: [arm_ids currently baked into its
                           trampoline]}, so we know what to clear later
  _armed_owner.json    -- {seed_name, slot} identifying which AP player
                           the state above currently belongs to (see
                           --reset-if-owner-changed= below)

Usage:
  python arm_orchestrator.py --area=<base>                 (area change; use current pending queue)
  python arm_orchestrator.py --queue-add=<arm_id>           (new check arrived; re-derive armed set for last-known area)
  python arm_orchestrator.py --queue-companion-class=<name>:<class>  (CompanionClass -- see Options.py)
  python arm_orchestrator.py --queue-additional-feats=<name>:<f1>,<f2>,<f3>  (AdditionalFeats -- see Options.py)
  python arm_orchestrator.py --queue-delevel=<level>:<xp>:<force>  (reconciler SetXP-gap fix -- force=-1 means don't touch Force)
  python arm_orchestrator.py --queue-trap=<trap_type>:<params>  (Traps -- see Options.py)
  python arm_orchestrator.py --queue-force-power=<spells.2da row id>  (TSL power port pilot / admin grant)
  python arm_orchestrator.py --delivered=<arm_id>,<arm_id>  (confirmed applied; remove from queue, clear fired areas)
  python arm_orchestrator.py --reset-if-owner-changed=<seed_name>:<slot>
      (Connect-time cross-slot leakage guard -- see KotorClient.py's
      _reset_trampolines_if_owner_changed. Two clients sharing one
      physical Override (e.g. testing two slots of the same multiworld
      seed sequentially) share these state files; an item armed-but-
      unconfirmed for one slot has no way to know it shouldn't fire for a
      DIFFERENT slot that later walks into the same area. If the given
      (seed_name, slot) doesn't match _armed_owner.json's current value,
      every armed area is force-cleaned back to plain baseline and the
      pending queue is cleared before recording the new owner -- a real
      slot switch always gets a guaranteed-clean handoff. A reconnect of
      the SAME slot is a no-op, so legitimately-pending items for an
      ongoing session are never wiped for no reason.)
  python arm_orchestrator.py --status                       (print current state, no changes)

  Any call above may also carry --game-dir=<path> (the compiled extender
  always passes this -- see ap_extender.c's ap_run_orchestrator -- since a
  player's own KOTOR install may live anywhere; defaults to the standard
  Steam location for manual/dev invocation).
"""
import json
import os
import sys
import subprocess
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "extender", "area_trampolines")
STATE_DIR = SRC_DIR
GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
QUEUE_PATH = os.path.join(STATE_DIR, "_pending_queue.json")
ARMED_PATH = os.path.join(STATE_DIR, "_armed_state.json")
CURRENT_AREA_PATH = os.path.join(STATE_DIR, "_current_area.json")
OWNER_PATH = os.path.join(STATE_DIR, "_armed_owner.json")
# Deliberately separate from QUEUE_PATH/ARMED_PATH: a
# notification (check found / item received) has no delivery confirmation
# to reconcile against, unlike every other queue entry -- there's no
# "AP|APPLIED|notify" to wait for, so it can't use the same persist-until-
# confirmed model. Instead it's baked into whatever's currently armed on
# every --queue-notify= call, and cleared unconditionally the next time the
# player's own --area-idx= fires (that's the DLL's signal that whatever WAS
# armed for the scope just played, on a real OnEnter) -- see --area-idx='s
# handling below.
NOTIFY_PATH = os.path.join(STATE_DIR, "_pending_notify.json")
BATCH_GEN = os.path.join(os.path.dirname(__file__), "generate_trampoline_batch.py")

# Numeric arm IDs that are unsafe to have more than one copy of in
# _pending_queue.json at once.
# MUST stay in sync with KotorClient.py's own HEAVY_ARMS set -- same 15
# arms, same reasoning (class switches/companion recruits/PC's own
# starting-class roll all do a one-shot, non-additive engine write --
# AddMultiClass, ShowLevelUpGUI, AddAvailableNPCByTemplate,
# KSE_SetCreatureField -- unlike skill/ability arms, which are DESIGNED to
# be queued multiple times, one entry per point of real catch-up needed
# (see kotor_reconciliation.py's _reconcile()). A blanket dedup or size
# cap across ALL arms would risk silently dropping those legitimate
# repeats; this list is deliberately narrow -- only the arms where a
# second copy can never be correct, never the ones where it might be.
#
# Real bug this fixes: class_consular (14) can accumulate multiple
# copies in the pending queue over the course of one session (a stalled
# extender relay losing confirmations means more gets queued than ever
# gets confirmed-cleared). Because
# generate_trampoline_batch.py bakes one copy of an arm's body per queue
# token, this caused the SAME class-switch code to run multiple times
# within a single trampoline execution -- confirmed via kse.log showing
# "AP|APPLIED|class_consular" twice at the identical timestamp -- which
# is exactly the crash mechanism already documented elsewhere in this
# project (a duplicate class-switch resend once crashed the game).
ONE_SHOT_ARM_IDS = {
    9, 10, 13, 14, 19, 20, 21, 22, 23, 24, 25, 26, 34, 35, 36,
}

# Not a hard cap -- see this constant's own usage in _save_queue() for why
# a blanket size limit isn't the fix (it would risk silently dropping
# legitimate skill/ability catch-up corrections rather than just
# deduplicating accidental repeats). This purely makes bloat VISIBLE the
# moment it starts, in the orchestrator's own stdout (which flows into
# the extender's log), rather than being discovered only once something
# breaks -- a real queue was once seen growing to 23 entries with zero
# warning anywhere along the way.
QUEUE_BLOAT_WARN_THRESHOLD = 40


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _kse_log_path():
    base = os.environ.get("LOCALAPPDATA", ".")
    return os.path.join(base, "KSE", "kse.log")


def _append_ap_diag_line(marker):
    """Appends a line containing an AP| marker directly to kse.log -- the
    exact file the extender's log-tail thread already watches
    (ap_kse_log_tail_thread in ap_extender.c matches ANY line containing
    "AP|", not just ones the KSE DLL itself wrote, and relays it verbatim
    over the socket as "EVENT:<line>"). Reuses that already-working relay
    with zero C-side changes. Originally built for the queue-bloat warning
    (a print() that only ever reached this script's own stdout -- captured
    by ap_run_orchestrator() in the C extender only when the orchestrator
    call exits non-zero -- so a warning on a call that still exits 0 was
    silently dropped every time); also used by --queue-add='s one-shot-arm
    diagnostic below, same reasoning.

    Best-effort: a missing kse.log directory (extender never launched at
    all this session) or a transient write collision with the KSE DLL's
    own concurrent writes (same file, no cross-process lock -- an
    accepted, pre-existing risk class for this diagnostic-only, rare-by-
    threshold append, not something worth adding real IPC locking for)
    should never crash the orchestrator over a diagnostic line."""
    try:
        path = _kse_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", errors="ignore") as f:
            f.write(marker + "\n")
    except Exception as e:
        print(f"  (couldn't push {marker!r} to kse.log: {e})")


def _push_queue_bloat_warning_to_client(count):
    _append_ap_diag_line(f"AP|WARNING|QUEUE_BLOAT|{count}")


def save_queue(queue):
    """ALWAYS use this instead of save_json(QUEUE_PATH, ...) directly, so
    every add path gets the same bloat visibility -- see
    QUEUE_BLOAT_WARN_THRESHOLD's own comment."""
    if len(queue) >= QUEUE_BLOAT_WARN_THRESHOLD:
        print(f"ORCHESTRATOR WARNING: pending queue has grown to {len(queue)} entries "
              f"(threshold {QUEUE_BLOAT_WARN_THRESHOLD}) -- confirmations may not be "
              "flowing back (check whether the extender's log-tail relay is alive), "
              "or a real backlog has built up. Not auto-trimmed: some of these may be "
              "legitimate repeated skill/ability corrections.")
        _push_queue_bloat_warning_to_client(len(queue))
    save_json(QUEUE_PATH, queue)


def load_graph():
    with open(os.path.join(SRC_DIR, "_graph.json")) as f:
        return json.load(f)


def load_idx_to_base():
    with open(os.path.join(SRC_DIR, "_mapping.json")) as f:
        mapping = json.load(f)
    return {info["idx"]: base for base, info in mapping.items()}


def armed_set_for(area_base, graph):
    if area_base is None:
        return set()
    neighbors = graph.get(area_base, [])
    return {area_base} | set(neighbors)


def _cli_token(item):
    """A queue item is a plain int arm ID, a parameterized value action
    dict {"action": "set_xp"/"set_credits", "value": N}, a give_item dict
    {"action": "give_item", "resref": R, "count": N}, or a notify dict
    {"action": "notify", "text": T} -- serialize any of these into the
    token generate_trampoline_batch.py's argv parser expects. Passed as
    one element of a subprocess.run() argv LIST (no shell involved), so
    an arbitrary notify text with spaces/punctuation/colons arrives intact
    as a single argv token -- no shell quoting needed."""
    if isinstance(item, dict):
        if item["action"] == "give_item":
            return f"give_item:{item['resref']}:{item['count']}"
        if item["action"] == "companion_class":
            return f"companion_class:{item['name']}:{item['class_name']}"
        if item["action"] == "additional_feats":
            return f"additional_feats:{item['name']}:{','.join(str(f) for f in item['feat_ids'])}"
        if item["action"] == "trap":
            return f"trap:{item['trap_type']}:{item['params']}"
        if item["action"] == "force_power":
            return f"force_power:{item['spell_id']}"
        if item["action"] == "notify":
            return f"notify:{item['text']}"
        if item["action"] == "delevel":
            # REAL BUG this case fixes: a delevel dict has {level, xp,
            # force} keys, not {value}, so
            # any batch containing one fell through to the generic
            # f"{action}:{value}" branch below and crashed with a
            # KeyError the moment regenerate() tried to serialize it --
            # a real delevel entry sitting in
            # _pending_queue.json crashes every single regenerate() that
            # includes it (arm_orchestrator.py exits non-zero, caught by
            # the C caller, but the batch never actually compiles). Matches generate_trampoline_batch.py's own
            # "delevel:<level>:<xp>:<force>" argv parser exactly.
            return f"delevel:{item['level']}:{item['xp']}:{item['force']}"
        return f"{item['action']}:{item['value']}"
    return str(item)


# Set by regenerate() on any subprocess failure and checked at the very end
# of main() -- a failed regenerate used to just print a warning and let
# arm_orchestrator.py exit 0 anyway, which meant dllmain.c's CreateProcess
# (which only sees ITS direct child's exit code, not generate_trampoline_
# batch.py's) had no way to know anything went wrong. A real example: a
# stale _shop_stock.json schema crashed generate_trampoline_batch.py on
# every single call for a shop-bearing area, silently blocking every arm
# delivery for that area for hours, with "STAGED" confirmations reaching
# the client the whole time.
_had_failure = False


# Bastila's companion grant (arm 9) must never be armed into end_m01aa --
# the Endar Spire's own scripted hand-off of Trask into the party uses the
# same party slot a CreateObject+AddPartyMember for Bastila would claim,
# and firing there first leaves Trask unable to join. Centralized here
# (rather than at each regenerate() call site) so every caller -- area
# entry, --queue-add= re-arming, etc. -- is covered automatically.
_BLOCK_ARM_IN_AREA = {9: "end_m01aa"}


def regenerate(area_bases, batch_items):
    """Regenerate+compile+deploy a list of areas with the given batch (empty
    list = clear back to the plain preserved-original+poll_shared form).
    See _BLOCK_ARM_IN_AREA for the one hardcoded arm/area exclusion."""
    global _had_failure
    if not area_bases:
        return
    for arm_id, blocked_base in _BLOCK_ARM_IN_AREA.items():
        if blocked_base in area_bases and arm_id in batch_items:
            others = [b for b in area_bases if b != blocked_base]
            regenerate([blocked_base], [item for item in batch_items if item != arm_id])
            if others:
                regenerate(others, batch_items)
            return
    args = ["python", BATCH_GEN] + [_cli_token(x) for x in batch_items] + [f"--areas={','.join(area_bases)}", f"--game-dir={GAME_DIR}"]
    # timeout=90 (hang-safeguard): "a handful of recompiles"
    # (per ap_extender.c's own comment on this call's caller) takes well
    # under a second each -- generous, not tight. Real risk this closes:
    # this subprocess.run() previously had NO timeout, and this script is
    # itself the middle of a 3-layer chain (extender's C code -> this
    # file -> generate_trampoline_batch.py -> nwnnsscomp.exe) where NONE
    # of the 3 subprocess calls had one -- a hang anywhere downstream
    # (nwnnsscomp.exe is the most likely: antivirus real-time scanning
    # intercepting a frequently-spawned, less-common .exe is a plausible,
    # ordinary trigger, not just a dev-editing collision) would leave the
    # C extender's log-tail thread blocked forever inside its own
    # untimed ReadFile, silently freezing all future event relay for the
    # rest of the game session -- this is the "extender silently died"
    # symptom. generate_trampoline_batch.py's
    # OWN nwnnsscomp call already got the same fix, but bounding this
    # call too is real defense in depth: it's what actually guarantees
    # THIS script exits and closes its own output handle promptly even
    # if some future subprocess call gets added downstream without a
    # timeout of its own.
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=90)
        print(result.stdout.strip())
        if result.returncode != 0 or "FAILED" in result.stdout:
            _had_failure = True
            print("ORCHESTRATOR WARNING: regenerate had failures:")
            print("  cmd:", " ".join(args))
            print("  stdout:", result.stdout.strip()[:1000])
            print("  stderr:", result.stderr.strip()[:1000])
    except subprocess.TimeoutExpired as e:
        _had_failure = True
        print(f"ORCHESTRATOR WARNING: regenerate TIMED OUT after 90s (hung child process, killed): {' '.join(args)}")
        print("  stdout:", (e.stdout or "")[:1000])
        print("  stderr:", (e.stderr or "")[:1000])


def reset_all():
    """Force-cleans every area currently listed in _armed_state.json back
    to plain baseline, regardless of scope/neighbors -- unlike
    apply_armed_set(), which only clears areas that fell OUT of a given
    area's scope. Used when a cross-slot owner change is detected (see
    --reset-if-owner-changed=): an area armed for a PREVIOUS slot's
    session could be anywhere on the map, not just near whatever area the
    new slot's player currently happens to be in, so scope-relative
    clearing isn't enough here."""
    armed = load_json(ARMED_PATH, {})
    if armed:
        regenerate(sorted(armed.keys()), [])
    save_json(ARMED_PATH, {})
    save_json(QUEUE_PATH, [])


def apply_armed_set(new_area_base, graph, force_clean=False):
    queue = load_json(QUEUE_PATH, [])
    armed = load_json(ARMED_PATH, {})
    # Merged into every regenerate of to_arm below -- NOT just when
    # --queue-notify= itself runs. Real bug this fixes: a
    # notify correctly baked into an area's trampoline could get silently
    # overwritten and lost minutes before the player ever entered that
    # area, because a LATER, unrelated event (a duplicate skill-grant
    # --queue-add=) called this same function, which used to only know
    # about _pending_queue.json -- it had no idea a notify was sitting in
    # the trampoline it was about to regenerate, so it dropped it. Now
    # every call path that can trigger a regenerate (--queue-add=,
    # --delivered=, --area=, --area-idx=, and --queue-notify= itself)
    # consistently preserves whatever's still pending until the player's
    # own --area-idx= transition actually consumes it (see that handler
    # below) -- not just the one code path that happened to originate it.
    pending_notify = load_json(NOTIFY_PATH, [])
    notify_items = [{"action": "notify", "text": t} for t in pending_notify]
    full_batch = queue + notify_items

    new_scope = armed_set_for(new_area_base, graph)
    old_scope = set(armed.keys())

    to_clear = old_scope - new_scope
    to_arm = new_scope  # re-arm everything in scope with the current queue
    # (cheap enough -- regenerate is fast, and guarantees every in-scope
    # area actually reflects the LATEST queue, not a stale one from when it
    # first entered scope)

    if to_clear:
        regenerate(sorted(to_clear), [])
        for b in to_clear:
            armed.pop(b, None)

    if full_batch and to_arm:
        regenerate(sorted(to_arm), full_batch)
        # armed_state.json intentionally tracks the PERSISTED queue only,
        # never the ephemeral notify list (see NOTIFY_PATH's own comment)
        # -- so a later diff here still correctly detects "nothing real
        # pending" even while a notify is transiently baked in.
        for b in to_arm:
            armed[b] = list(queue)
    elif to_arm and not full_batch:
        # nothing pending -- make sure in-scope areas are clean too.
        # force_clean covers a real gap: armed_state.json
        # only ever tracks the real queue, never notify content, so
        # "does this area need cleaning" checked here alone would mean
        # "did it last have a real grant" -- an area that ONLY ever had a
        # notify baked in (never a real grant) would always look
        # already-clean by that check, even though its compiled script
        # still has the full notify chain sitting in it (which can restart
        # a multi-step chained notification from step 1 on a LATER,
        # unrelated area entry, since nothing ever actually regenerated
        # that area's script back to empty after its notify was consumed).
        # --area-idx='s handler now passes force_clean=True whenever it
        # just cleared a non-empty NOTIFY_PATH, guaranteeing the entire
        # entered scope gets a real regenerate even when armed_state.json
        # alone would say there's nothing to do.
        stale = [b for b in to_arm if armed.get(b) or force_clean]
        if stale:
            regenerate(sorted(stale), [])
        for b in to_arm:
            armed[b] = []

    save_json(ARMED_PATH, armed)
    save_json(CURRENT_AREA_PATH, {"area": new_area_base})
    print(f"armed_set={sorted(new_scope)} queue={queue}")


def main():
    _dispatch()
    if _had_failure:
        sys.exit(1)


def _dispatch():
    global GAME_DIR
    graph = load_graph()
    args = []
    for a in sys.argv[1:]:
        if a.startswith("--game-dir="):
            GAME_DIR = a.split("=", 1)[1]
        else:
            args.append(a)
    if not args:
        print(__doc__)
        sys.exit(1)

    arg = args[0]
    if arg == "--status":
        print("queue:", load_json(QUEUE_PATH, []))
        print("armed:", load_json(ARMED_PATH, {}))
        print("current_area:", load_json(CURRENT_AREA_PATH, {}))
        return

    if arg.startswith("--area="):
        new_area = arg.split("=", 1)[1]
        apply_armed_set(new_area, graph)
        return

    if arg.startswith("--area-idx="):
        idx = int(arg.split("=", 1)[1])
        idx_to_base = load_idx_to_base()
        new_area = idx_to_base.get(idx)
        if new_area is None:
            print(f"unknown area idx {idx}, ignoring")
            return
        # The DLL only sends --area-idx= when the player's OWN OnEnter for
        # a NEW area index just fired -- i.e. whatever notify text was
        # baked into the scope computed at the LAST area is guaranteed to
        # have already played. Clear it here unconditionally so it doesn't
        # keep re-appearing on every future regenerate of that scope.
        #
        # force_clean=True whenever a non-empty NOTIFY_PATH just got
        # cleared -- without this, an area whose ONLY baked-in content was
        # a notify (no real grant ever queued for it) looks "already
        # clean" to apply_armed_set's normal armed_state.json check, so
        # its compiled script never actually gets regenerated back to
        # empty (which can restart a multi-step chained notification from
        # step 1 on a completely unrelated later area entry, since the
        # script that had it baked in is never touched again).
        had_notify = bool(load_json(NOTIFY_PATH, []))
        if os.path.exists(NOTIFY_PATH):
            os.remove(NOTIFY_PATH)
        apply_armed_set(new_area, graph, force_clean=had_notify)
        return

    if arg.startswith("--queue-notify="):
        # Percent-decoded here -- kotor_extender_bridge.py's send_notify()
        # encodes it before sending, since dllmain.c's ap_run_orchestrator()
        # builds an unquoted CreateProcessA command line that would
        # otherwise split this on every space before it even reaches this
        # script's argv (e.g. "Connected to AP Server" arriving
        # here as just "Connected").
        #
        # Just appends and delegates to apply_armed_set() -- same pattern
        # as --queue-add=/--queue-give-item= below. Used to have its own
        # bespoke scope-computation + regenerate() call here, duplicating
        # apply_armed_set()'s logic; that duplication is exactly what let
        # a real bug slip through (see apply_armed_set()'s own comment on
        # NOTIFY_PATH): a notify baked in via THIS code path could still
        # get silently overwritten by a LATER, unrelated apply_armed_set()
        # call (a real grant queuing, a --delivered=) that didn't know
        # notify existed -- e.g. a "Check found" notification
        # never displaying because a duplicate skill-grant queued
        # afterward wiped its trampoline before the player ever
        # transitioned there. Routing through the same apply_armed_set()
        # both callers use means EVERY regenerate consistently preserves
        # whatever's pending, not just this one origin point.
        pending = load_json(NOTIFY_PATH, [])
        pending.append(urllib.parse.unquote(arg.split("=", 1)[1]))
        save_json(NOTIFY_PATH, pending)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        if current is None:
            # No known current area yet (e.g. before the player's first
            # real area entry this session) -- nowhere to bake this into
            # yet. NOT dropped like the old code did -- left in
            # NOTIFY_PATH so the player's first real --area-idx= (which
            # calls apply_armed_set itself) picks it up naturally, rather
            # than losing it just because it arrived early.
            print("no current area known yet, notify left pending for the first real area-idx=")
            return
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-add="):
        arm_id = int(arg.split("=", 1)[1])
        queue = load_json(QUEUE_PATH, [])
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        if arm_id in ONE_SHOT_ARM_IDS and arm_id in queue:
            # See ONE_SHOT_ARM_IDS' own comment -- a second copy of a
            # class-switch/companion-recruit/pc-class arm is never
            # correct (unlike skill/ability arms, deliberately not in
            # this set, which legitimately queue more than once). Skip
            # rather than append -- the existing, still-pending copy
            # will fire once confirmations are flowing again.
            print(f"arm {arm_id} already pending (one-shot arm, not re-queuing a duplicate)")
            # Diagnostic breadcrumb for ONE_SHOT_ARM_IDS specifically: a
            # real incident (companion_canderous, 2026-09-25) showed two
            # --queue-add= calls for the same arm_id 3s apart, during the
            # single riskiest window in a session (seconds after the
            # game's first post-launch dispatcher burst), and the arm's
            # own AP|APPLIED| never fired for either call -- with no way
            # after the fact to tell whether this dedup skip ever ran, or
            # whether the arm was still mid-regenerate when the second
            # call arrived. Unlike the print() above (silently dropped
            # unless this call exits non-zero -- see _append_ap_diag_
            # line's docstring), this always reaches kse.log.
            _append_ap_diag_line(f"AP|ORCHESTRATOR|DUPLICATE_ONE_SHOT|arm={arm_id}|area={current}")
        else:
            queue.append(arm_id)
            save_queue(queue)
            if arm_id in ONE_SHOT_ARM_IDS:
                _append_ap_diag_line(f"AP|ORCHESTRATOR|QUEUE_ADD|arm={arm_id}|area={current}")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-set-xp=") or arg.startswith("--queue-set-credits="):
        action = "set_xp" if arg.startswith("--queue-set-xp=") else "set_credits"
        value = int(arg.split("=", 1)[1])
        queue = load_json(QUEUE_PATH, [])
        # Replace semantics, not accumulate: an exact-value target
        # supersedes any earlier one still pending, it doesn't stack with
        # it (unlike arm IDs, which are discrete grants that should all
        # fire). Only one set_xp/set_credits action is ever pending at once.
        queue = [q for q in queue if not (isinstance(q, dict) and q["action"] == action)]
        queue.append({"action": action, "value": value})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-delevel="):
        # Reconciler fix for the documented SetXP gap: native
        # SetXP() silently refuses to lower XP below the CURRENT level's
        # banked threshold once vanilla XP has carried a player past it
        # -- the reconciler detects this
        # (expected XP maps to a lower level than the player's real
        # current level) and sends an exact level+XP+Force correction
        # instead of a plain set_xp. Replace semantics, matching
        # set_xp/set_credits -- only one delevel target should ever be
        # pending at once, a later correction supersedes an earlier
        # unresolved one rather than stacking. force=-1 is the sentinel
        # for "don't touch Force" (non-Jedi character).
        level_s, xp_s, force_s = arg.split("=", 1)[1].split(":")
        queue = load_json(QUEUE_PATH, [])
        queue = [q for q in queue if not (isinstance(q, dict) and q.get("action") == "delevel")]
        queue.append({"action": "delevel", "level": int(level_s), "xp": int(xp_s), "force": int(force_s)})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-give-item="):
        resref, count = arg.split("=", 1)[1].split(":")
        queue = load_json(QUEUE_PATH, [])
        # Append, not replace: unlike set_xp/set_credits (one exact-value
        # target, later supersedes earlier), give_item grants are discrete
        # -- several different items (or repeats of the same one) can be
        # pending at once and should all eventually fire.
        queue.append({"action": "give_item", "resref": resref, "count": int(count)})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-companion-class="):
        name, class_name = arg.split("=", 1)[1].split(":")
        queue = load_json(QUEUE_PATH, [])
        # Append, not replace: like give_item, several different companions
        # (or, in principle, the same one again) can legitimately be
        # pending at once.
        queue.append({"action": "companion_class", "name": name, "class_name": class_name})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-additional-feats="):
        name, feats_csv = arg.split("=", 1)[1].split(":")
        feat_ids = [int(f) for f in feats_csv.split(",")]
        queue = load_json(QUEUE_PATH, [])
        # Append, not replace: same reasoning as companion_class -- each
        # character's grant is a distinct, one-shot delivery (the 3 feat
        # ids were already chosen client-side, see KotorClient.py's
        # _check_pending_additional_feats), and in principle more than one
        # could be pending at once (e.g. the PC's and a companion's both
        # clearing their gates in the same poll cycle).
        queue.append({"action": "additional_feats", "name": name, "feat_ids": feat_ids})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-trap="):
        # Format is "<trap_type>:<params>" -- split(":", 1), not a bare
        # split(":"), since params' own internal shape can legitimately
        # contain more colons (reduce_skill's "<skill_key>:<amount>"). One new
        # queue action for all 12 Traps items (Options.py) -- see
        # generate_trampoline_batch.py's build_trap_block for what each
        # trap_type actually does.
        trap_type, params = arg.split("=", 1)[1].split(":", 1)
        queue = load_json(QUEUE_PATH, [])
        # Append, not replace: same reasoning as additional_feats -- a
        # one-shot delivery, and in principle more than one trap could be
        # pending at once (e.g. two traps received close together).
        queue.append({"action": "trap", "trap_type": trap_type, "params": params})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--queue-force-power="):
        # One spells.2da row id per call (see generate_trampoline_batch.py's
        # build_force_power_block). Append, dedup'd on the id: the block is
        # GetHasSpell-guarded so a repeat would be harmless, but two copies
        # of the same grant in one batch is just noise.
        spell_id = int(arg.split("=", 1)[1])
        queue = load_json(QUEUE_PATH, [])
        if not any(isinstance(q, dict) and q.get("action") == "force_power" and q.get("spell_id") == spell_id
                   for q in queue):
            queue.append({"action": "force_power", "spell_id": spell_id})
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--set-shop-stock="):
        # Format is "<planet>:<resref1>,<resref2>,..." -- one call per
        # planet, sent as
        # 5 separate wire messages by kotor_extender_bridge.py so no
        # individual message risks overflowing dllmain.c's fixed args[700]
        # buffer. _shop_stock.json is now {planet: [resrefs]} -- each call
        # only updates its own planet's key, merging into whatever the
        # other planets' earlier calls already wrote this connection.
        planet, _, resref_str = arg.split("=", 1)[1].partition(":")
        resrefs = [x for x in resref_str.split(",") if x]
        shop_stock_path = os.path.join(SRC_DIR, "_shop_stock.json")
        all_stock = load_json(shop_stock_path, {})
        all_stock[planet] = resrefs
        save_json(shop_stock_path, all_stock)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        queue = load_json(QUEUE_PATH, [])
        armed = load_json(ARMED_PATH, {})
        scope = armed_set_for(current, graph)
        if scope:
            # Force a real regenerate, bypassing apply_armed_set's normal
            # stale-skip (which only tracks arm-queue history, not shop
            # stock) -- otherwise an empty-queue area that's already
            # "armed clean" would silently keep its pre-shop-stock content
            # until its next unrelated queue change.
            regenerate(sorted(scope), queue)
            for b in scope:
                armed[b] = list(queue)
            save_json(ARMED_PATH, armed)
        print(f"shop_stock set for {planet} ({len(resrefs)} items), regenerated scope={sorted(scope)}")
        return

    if arg.startswith("--delivered="):
        ids = [x for x in arg.split("=", 1)[1].split(",") if x]
        queue = load_json(QUEUE_PATH, [])
        for i in ids:
            if i in ("set_xp", "set_credits", "delevel"):
                queue = [q for q in queue if not (isinstance(q, dict) and q["action"] == i)]
            elif i.startswith("give_item:"):
                resref = i.split(":", 1)[1]
                # Remove just the first matching entry, not every entry
                # with this resref -- the same item could legitimately be
                # queued more than once (e.g. two separate checks each
                # granting the same gear item), and each is a distinct
                # delivery that needs its own confirmation to clear.
                for idx, q in enumerate(queue):
                    if isinstance(q, dict) and q.get("action") == "give_item" and q.get("resref") == resref:
                        queue.pop(idx)
                        break
            elif i.startswith("companion_class:"):
                name = i.split(":", 1)[1]
                # Same first-match-only removal as give_item -- see that
                # branch's comment.
                for idx, q in enumerate(queue):
                    if isinstance(q, dict) and q.get("action") == "companion_class" and q.get("name") == name:
                        queue.pop(idx)
                        break
            elif i.startswith("additional_feats:"):
                name = i.split(":", 1)[1]
                # Same first-match-only removal as give_item/companion_class.
                for idx, q in enumerate(queue):
                    if isinstance(q, dict) and q.get("action") == "additional_feats" and q.get("name") == name:
                        queue.pop(idx)
                        break
            elif i.startswith("trap:"):
                trap_type = i.split(":", 1)[1]
                # Same first-match-only removal as the others above --
                # traps are one-shot by design (Options.py's Traps),
                # so in the normal case only one entry per trap_type is
                # ever queued at once, but first-match-only is still the
                # correct/safe behavior if that ever isn't true.
                for idx, q in enumerate(queue):
                    if isinstance(q, dict) and q.get("action") == "trap" and q.get("trap_type") == trap_type:
                        queue.pop(idx)
                        break
            elif i.startswith("force_power:"):
                spell_id = int(i.split(":", 1)[1])
                queue = [q for q in queue
                         if not (isinstance(q, dict) and q.get("action") == "force_power" and q.get("spell_id") == spell_id)]
            else:
                i = int(i)
                if i in queue:
                    queue.remove(i)
        save_queue(queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--reset-if-owner-changed="):
        seed_name, slot = arg.split("=", 1)[1].split(":", 1)
        owner = load_json(OWNER_PATH, {})
        if owner.get("seed_name") == seed_name and owner.get("slot") == slot:
            print(f"owner unchanged (seed_name={seed_name} slot={slot}) -- no reset needed")
            return
        armed = load_json(ARMED_PATH, {})
        reset_all()
        save_json(OWNER_PATH, {"seed_name": seed_name, "slot": slot})
        print(f"owner changed ({owner or 'none'} -> seed_name={seed_name} slot={slot}) "
              f"-- reset {len(armed)} armed area(s)")
        return

    print(f"unknown argument: {arg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
