"""
Called by the extender (C code, via CreateProcess) whenever either (a) a
new check needs arming, or (b) the player's current area changes. Computes
the "armed set" = current area + its direct neighbors (from _graph.json),
regenerates any newly-in-scope area's trampoline with the CURRENT pending
batch, and clears (regenerates back to empty) any previously-armed area
that's fallen out of scope -- so stray un-fired batches don't linger
somewhere the player wandered away from.

State lives in two small JSON files next to the trampoline sources:
  _pending_queue.json  -- list of arm IDs not yet confirmed delivered
  _armed_state.json    -- {area_base: [arm_ids currently baked into its
                           trampoline]}, so we know what to clear later

Usage:
  python arm_orchestrator.py --area=<base>                 (area change; use current pending queue)
  python arm_orchestrator.py --queue-add=<arm_id>           (new check arrived; re-derive armed set for last-known area)
  python arm_orchestrator.py --queue-companion-class=<name>:<class>  (RandomizeClass -- see Options.py)
  python arm_orchestrator.py --delivered=<arm_id>,<arm_id>  (confirmed applied; remove from queue, clear fired areas)
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
# Deliberately separate from QUEUE_PATH/ARMED_PATH (2026-08-29): a
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


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


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
        if item["action"] == "notify":
            return f"notify:{item['text']}"
        return f"{item['action']}:{item['value']}"
    return str(item)


# Set by regenerate() on any subprocess failure and checked at the very end
# of main() -- a failed regenerate used to just print a warning and let
# arm_orchestrator.py exit 0 anyway, which meant dllmain.c's CreateProcess
# (which only sees ITS direct child's exit code, not generate_trampoline_
# batch.py's) had no way to know anything went wrong. Confirmed live: a
# stale _shop_stock.json schema crashed generate_trampoline_batch.py on
# every single call for a shop-bearing area, silently blocking every arm
# delivery for that area for hours, with "STAGED" confirmations reaching
# the client the whole time.
_had_failure = False


def regenerate(area_bases, batch_items):
    """Regenerate+compile+deploy a list of areas with the given batch (empty
    list = clear back to the plain preserved-original+poll_shared form)."""
    global _had_failure
    if not area_bases:
        return
    args = ["python", BATCH_GEN] + [_cli_token(x) for x in batch_items] + [f"--areas={','.join(area_bases)}", f"--game-dir={GAME_DIR}"]
    result = subprocess.run(args, capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0 or "FAILED" in result.stdout:
        _had_failure = True
        print("ORCHESTRATOR WARNING: regenerate had failures:")
        print("  cmd:", " ".join(args))
        print("  stdout:", result.stdout.strip()[:1000])
        print("  stderr:", result.stderr.strip()[:1000])


def apply_armed_set(new_area_base, graph, force_clean=False):
    queue = load_json(QUEUE_PATH, [])
    armed = load_json(ARMED_PATH, {})
    # Merged into every regenerate of to_arm below -- NOT just when
    # --queue-notify= itself runs. Real bug found live (2026-08-29): a
    # notify correctly baked into an area's trampoline got silently
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
        # force_clean (2026-08-29) covers a real gap: armed_state.json
        # only ever tracked the real queue, never notify content, so
        # "does this area need cleaning" here used to mean "did it last
        # have a real grant" -- an area that ONLY ever had a notify baked
        # in (never a real grant) always looked already-clean by this
        # check, even though its compiled script still had the full
        # notify chain sitting in it. Confirmed live: a 3-step chained
        # notification restarted from step 1 on a LATER, unrelated area
        # entry, because nothing had ever actually regenerated that
        # area's script back to empty after its notify was consumed.
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
        # empty. Confirmed live: a 3-step chained notification restarted
        # from step 1 on a completely unrelated later area entry, because
        # the script that had it baked in was simply never touched again.
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
        # script's argv (confirmed live: "Connected to AP Server" arrived
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
        # notify existed -- confirmed live, a "Check found" notification
        # never displayed because a duplicate skill-grant queued
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
        queue.append(arm_id)
        save_json(QUEUE_PATH, queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
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
        save_json(QUEUE_PATH, queue)
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
        save_json(QUEUE_PATH, queue)
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
        save_json(QUEUE_PATH, queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    if arg.startswith("--set-shop-stock="):
        # Format is "<planet>:<resref1>,<resref2>,..." -- one call per
        # planet (2026-08-29, was a single universal list before), sent as
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
            if i in ("set_xp", "set_credits"):
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
            else:
                i = int(i)
                if i in queue:
                    queue.remove(i)
        save_json(QUEUE_PATH, queue)
        current = load_json(CURRENT_AREA_PATH, {}).get("area")
        apply_armed_set(current, graph)
        return

    print(f"unknown argument: {arg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
