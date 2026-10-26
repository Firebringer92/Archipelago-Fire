"""Client side of the poll's job dispatcher (generate_poll_shared.py, DtTick).

A job is one action for the game to apply at a calm moment. The client sends it to the extender as
DISPATCH:<seq>:<action>[:<args>]; the extender leaves it in the DLL's inbox; the game's heartbeat script takes it from there,
checks that no conversation, combat or scripted scene is running, applies it at most once, and logs AP|DISPATCH|APPLIED.
Only one job is in flight at a time: the next is sent after the game answers for the one before.

seq is a number 0-255 that counts jobs. The game keeps its copy in the save (PC local booleans 48-55), so a reloaded save
brings back the number that matches its own state. The game reports it as AP|DISPATCH|STATE|seq=N; a job with seq N+1 fires,
one with seq N is a duplicate and is dropped, anything else is answered with SYNC so this side can renumber.

A loaded older save brings back its own, lower number. The client keeps a ledger of every job the game counted, so when the number
goes back it sends the jobs the old save never had again, in their original order, and the game is rebuilt to where it was.

Answers from the game, all lines starting AP|DISPATCH|:
  STATE|seq=N            the saved number (on every change, at area changes, and about once a minute)
  WAIT|seq=N|gate=G      the job is held; G is a sum of the bits in GATE_NAMES
  APPLIED|seq=N|...      done
  DUP|seq=N              already applied in this save: counts as done
  SYNC|seq=N|have=S      wrong number: the game has S, the job is renumbered S+1 and sent again
  FAILED|seq=N|...       the action ran but could not do its job (e.g. no such item): not retried
  UNKNOWN|seq=N|...      the game does not know that action: not retried
  PROBE|mask=M|prev=P    the scene-like state changed (same bits as gate, minus 32 and 64); logged for study
"""
import asyncio
import collections
import logging
import re
import time
import typing

logger = logging.getLogger("Client")

GATE_NAMES = {
    1: "scripted scene", 2: "conversation", 4: "cutscene module", 8: "player locked", 16: "combat",
    32: "area just loaded", 64: "no party", 128: "cutscene restrictions", 256: "player dead",
}

# Actions that never show the player a message (a message box pauses the game's polling until it is dismissed, so it is
# kept for things the player needs to know about). Fixed arms are named by their args.
NO_MESSAGE_ACTIONS = {"set_credits", "set_xp"}
NO_MESSAGE_ARMS = {"xp", "credits"}
MESSAGE_LINE_BREAK = "~~"       # the game turns this into a line break
MAX_BATCH_CHARS = 300           # a job is at most 511 characters in the game's inbox

_DISPATCH_RE = re.compile(r"AP\|DISPATCH\|([A-Za-z_]+)((?:\|[^|\"]*)*)")


# A death (an incoming DeathLink, arm 32 force_death) is never replayed after a save is loaded. Loading an older save is how a player
# comes back from a death; sending the death again would kill them again, and that death would be sent on as a new DeathLink: a loop.
DEATH_ARMS = {"force_death", "32"}
RECEIPT_PREFIX = "You received: "       # how the client words an item's message (KotorClient.py, _do_deliver)


def is_death_job(action: str, args: str) -> bool:
    if action in ("force_death", "death"):
        return True
    return action == "arm" and args.split(":")[0].strip() in DEATH_ARMS


def replace_key(action: str, args: str) -> typing.Optional[str]:
    """Jobs of an exact-value kind replace a waiting job of the same kind instead of queueing behind it: the reconciler sends a
    correction again on every poll until the game agrees, and the latest value is the only one that matters. Increments (arms), items,
    traps and deaths have no key: each one counts."""
    if action in ("set_xp", "set_credits", "delevel"):
        return action
    if action == "companion_class":
        return "companion_class:" + args.split(":")[0]
    if action == "force_power":
        return "force_power:" + args
    return None


def wants_message(action: str, args: str) -> bool:
    if action in NO_MESSAGE_ACTIONS:
        return False
    return not (action == "arm" and args in NO_MESSAGE_ARMS)


def gate_text(mask: int) -> str:
    names = [name for bit, name in GATE_NAMES.items() if mask & bit]
    return ", ".join(names) if names else "nothing"


def parse_dispatch_event(event: str) -> typing.Optional[typing.Tuple[str, typing.Dict[str, str]]]:
    m = _DISPATCH_RE.search(event)
    if m is None:
        return None
    fields: typing.Dict[str, str] = {}
    for part in m.group(2).split("|"):
        if "=" in part:
            key, _, value = part.partition("=")
            fields[key] = value
    return m.group(1).upper(), fields


class Job:
    def __init__(self, action: str, args: str, seq: typing.Optional[int] = None, message: str = ""):
        self.action = action
        self.args = args
        self.message = message               # shown to the player in the same apply, after the action
        self.message_full = message          # what was asked for, before batching held or merged it (kept for a replay)
        self.key: typing.Optional[str] = replace_key(action, args)   # a waiting job with the same key is replaced by this one
        self.index = -1                      # the AP item index this job delivers, if it came from a received item
        self.item_name = ""                  # that item's name, for the delivery log
        self.fail_reason = ""                # set when the job failed (see DispatchClient._fail)
        self.carried: typing.List[str] = []  # lines of earlier jobs' messages folded into this job's (see _batch_message)
        self.fixed_seq = seq is not None      # a replay on purpose: never renumbered
        self.seq: typing.Optional[int] = seq
        self.state = "queued"                  # queued, sent, staged, waiting, applied, duplicate, failed
        self.gate = 0
        self.sends = 0
        self.resyncs = 0
        self.created = time.time()
        self.last_sign = time.time()
        self.finished: typing.Optional[float] = None
        self.done = asyncio.Event()

    @property
    def text(self) -> str:
        return f"{self.action}:{self.args}" if self.args else self.action

    @property
    def label(self) -> str:
        """What the player recognises: the item's name when the job came from one, else a plain description."""
        if self.item_name:
            return self.item_name
        full = self.message_full or ""
        if full.startswith(RECEIPT_PREFIX):
            return full[len(RECEIPT_PREFIX):]
        if self.action == "arm":
            return self.args
        if self.action == "give_item":
            resref, _, count = self.args.partition(":")
            return f"item {resref}" + (f" x{count}" if count not in ("", "1") else "")
        if self.action == "set_xp":
            return f"set XP to {self.args}"
        if self.action == "set_credits":
            return f"set credits to {self.args}"
        if self.action == "delevel":
            return "level correction"
        if self.action == "companion_class":
            name, _, cls = self.args.partition(":")
            return f"{name}: class {cls}"
        if self.action == "force_power":
            return f"Force power {self.args}"
        if self.action == "trap":
            return "trap " + self.args.split(":")[0]
        if self.action == "notify":
            return "message"
        return self.text

    def finish(self, state: str) -> None:
        self.state = state
        self.finished = time.time()
        self.done.set()


class DispatchClient:
    # Seconds without any answer before the same job is sent again (the game drops a repeat of an applied one). The game's
    # polling is paused while a message box or a scene is up, so a short wait only floods the log.
    RESEND_AFTER = 35.0
    MAX_SENDS = 15           # about five minutes without an answer: give up on the job

    def __init__(self, bridge):
        self.bridge = bridge
        self.seq: typing.Optional[int] = None     # the number the game last reported (None until it has)
        self.current: typing.Optional[Job] = None
        self.last_applied: typing.Optional[Job] = None
        self.history: typing.Deque[Job] = collections.deque(maxlen=50)
        self._queue: typing.Deque[Job] = collections.deque()
        self._held: typing.List[str] = []      # messages of applied jobs waiting to be shown with the last job of a run
        self._pump_task: typing.Optional[asyncio.Task] = None
        self._last_gate_logged = -1
        self.applied_count = 0
        self.duplicate_count = 0
        self.resync_count = 0
        self.rollback_count = 0
        self.replayed_count = 0
        self.replaced_count = 0
        self.failed_count = 0
        # Called as on_failure(job, reason) when a job fails for good, to write it to the delivery log (set by KotorContext).
        self.on_failure: typing.Optional[typing.Callable[[Job, str], None]] = None
        # Every job the game counted, in order: (index, action, args, message, replayable). The index is the running count of
        # counted jobs, so the game's number (index modulo 256) says how far back a loaded save went. A failed job is counted by the
        # game but not replayable.
        self.abs_applied: typing.Optional[int] = None
        self.ledger: typing.List[typing.Tuple[int, str, str, str, bool]] = []

    # ---- submitting ----------------------------------------------------------------------------------------------
    def submit(self, action: str, args: str = "", replay_seq: typing.Optional[int] = None, message: str = "",
               index: int = -1, item_name: str = "") -> Job:
        job = Job(action, args, replay_seq, message if wants_message(action, args) else "")
        job.index, job.item_name = index, item_name
        if job.key is not None and replay_seq is None:
            # only a job that has not been sent yet is replaced; one in flight may already be running in the game and is left to finish
            stale = [j for j in self._queue if j.key == job.key and j.seq is None]
            if stale:
                self._queue = collections.deque(j for j in self._queue if j not in stale)
                for j in stale:
                    j.finish("replaced")
                    self.replaced_count += 1
        self._queue.append(job)
        self._ensure_pump()
        return job

    def _fail(self, job: Job, reason: str) -> None:
        """A job that will not be applied: remembered with its reason, reported to on_failure (the delivery log), and finished."""
        job.fail_reason = reason
        self.failed_count += 1
        if self.on_failure is not None:
            try:
                self.on_failure(job, reason)
            except Exception:
                logger.exception("[dispatch] could not write the failed job to the delivery log")
        job.finish("failed")

    def _ensure_pump(self) -> None:
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.ensure_future(self._pump())

    def _record(self, job: Job, replayable: bool) -> None:
        """Notes that the game counted this job. A replay on purpose (fixed number) is not a new job."""
        if job.fixed_seq:
            return
        if self.abs_applied is None:
            self.abs_applied = ((job.seq or 1) - 1) % 256
        self.abs_applied += 1
        # counted by the game, so the numbers stay in step, but never sent again after a reload (see DEATH_ARMS)
        self.ledger.append((self.abs_applied, job.action, job.args, job.message_full,
                            replayable and not is_death_job(job.action, job.args)))
        del self.ledger[:-1000]

    def _next_seq(self) -> int:
        # With no number from the game yet, assume a fresh game (0): a wrong guess is answered with SYNC.
        return ((self.seq if self.seq is not None else 0) + 1) % 256

    async def _send(self, job: Job) -> None:
        job.sends += 1
        job.last_sign = time.time()
        if job.state in ("queued", "sent", "staged"):
            job.state = "sent"
        ok = await self.bridge.send_dispatch(job.seq, job.action, job.args, job.message)
        if not ok:
            logger.info(f"[dispatch] job {job.seq} ({job.text}) not sent: the extender is not connected. Will retry.")

    def _batch_message(self, job: Job) -> None:
        """One message box per run of jobs, not one per job: while more jobs are queued behind this one its message is held,
        and the last job of the run carries all the held lines (joined by MESSAGE_LINE_BREAK). A run too long for one
        message is cut and the box shown with the job that reaches the limit."""
        lines = self._held + ([job.message] if job.message else [])
        if self._queue and len(MESSAGE_LINE_BREAK.join(lines)) < MAX_BATCH_CHARS:
            self._held = lines
            job.message = ""
            return
        job.carried = list(self._held)
        self._held = []
        job.message = MESSAGE_LINE_BREAK.join(lines)

    async def _learn_seq(self) -> None:
        """Asks the game for its saved number (the action "state" is answered with a STATE line and changes nothing), so the
        first job is numbered from fact. A guess could land on a number the game has already counted, and that job would be
        dropped as a repeat without ever being applied."""
        for attempt in range(10):
            if self.seq is not None:
                return
            if attempt == 0:
                logger.info("[dispatch] asking the game for its job number before sending the first job.")
            await self.bridge.send_dispatch(0, "state", "")
            for _ in range(12):
                await asyncio.sleep(0.5)
                if self.seq is not None:
                    return
        logger.warning("[dispatch] the game did not report its job number; numbering from 1 and letting the game correct it.")

    async def _pump(self) -> None:
        while self._queue or self.current is not None:
            if self.current is None:
                self.current = self._queue.popleft()
                job = self.current
                self._batch_message(job)
                if job.seq is None:
                    await self._learn_seq()
                    job.seq = self._next_seq()
                logger.info(f"[dispatch] sending job {job.seq}: {job.text}")
                await self._send(job)
            job = self.current
            if job.done.is_set():
                self.history.append(job)
                self.current = None
                if job.state == "failed" and job.carried:
                    # the earlier jobs' lines rode on this one and never got shown: send them on their own
                    self._queue.appendleft(Job("notify", MESSAGE_LINE_BREAK.join(job.carried)))
                continue
            await asyncio.sleep(0.5)
            if job.done.is_set():
                continue
            if time.time() - job.last_sign > self.RESEND_AFTER:
                if job.sends >= self.MAX_SENDS:
                    logger.warning(f"[dispatch] job {job.seq} ({job.text}) got no answer from the game after {job.sends} sends; giving up on it.")
                    self._fail(job, f"no answer from the game after {job.sends} sends")
                    continue
                if self.bridge.is_connected:
                    logger.info(f"[dispatch] no answer for job {job.seq} yet; sending it again (send {job.sends + 1}).")
                await self._send(job)

    # ---- answers from the extender (the reply to the write itself) ------------------------------------------------
    def on_reply(self, kind: str, seq: int) -> None:
        job = self.current
        if job is None or job.seq != seq:
            return
        job.last_sign = time.time()
        if kind == "staged" and job.state == "sent":
            job.state = "staged"
        elif kind == "toolong":
            logger.warning(f"[dispatch] job {seq} ({job.text}) is too long for the game's inbox; dropped.")
            self._fail(job, "too long for the game's inbox")
        # "busy": the DLL mailbox was being written at that moment; the resend timer sends it again

    # ---- answers from the game ---------------------------------------------------------------------------------------
    def on_event(self, event: str) -> None:
        if "AP|DISPATCH|" not in event:
            return
        parsed = parse_dispatch_event(event)
        if parsed is None:
            return
        kind, f = parsed
        job = self.current
        n = int(f["seq"]) if f.get("seq", "").lstrip("-").isdigit() else None
        if kind == "STATE":
            self._on_state(n)
        elif kind == "WAIT" and job is not None and job.seq == n:
            job.last_sign = time.time()
            gate = int(f.get("gate", "0") or 0)
            job.state, job.gate = "waiting", gate
            if gate != self._last_gate_logged:
                self._last_gate_logged = gate
                logger.info(f"[dispatch] job {n} is waiting for a calm moment: {gate_text(gate)}.")
        elif kind == "APPLIED" and job is not None and job.seq == n:
            self.seq = n
            self._record(job, True)
            self.last_applied = job
            self.applied_count += 1
            self._last_gate_logged = -1
            waited = f.get("waited", "?")
            logger.info(f"[dispatch] job {n} applied in the game ({job.text}); it waited {waited} poll(s).")
            job.finish("applied")
        elif kind == "DUP" and job is not None and job.seq == n:
            self.seq = n
            self._record(job, True)
            self.duplicate_count += 1
            logger.info(f"[dispatch] job {n} was already applied in this save; the game dropped the repeat.")
            job.finish("duplicate")
        elif kind == "SYNC" and job is not None and job.seq == n:
            have = int(f.get("have", "0") or 0)
            self.seq = have
            self.resync_count += 1
            if job.fixed_seq:
                logger.info(f"[dispatch] replay of job {n} answered SYNC (the game's number is {have}); a replay is not renumbered.")
                job.finish("failed")
                return
            job.resyncs += 1
            job.seq = (have + 1) % 256
            logger.warning(f"[dispatch] the game's job number is {have}, not {n - 1}; renumbering the job to {job.seq} and sending it again.")
            asyncio.ensure_future(self._send(job))
        elif kind == "FAILED" and job is not None and job.seq == n:
            self.seq = n
            self._record(job, False)
            logger.warning(f"[dispatch] the game could not apply job {n} ({job.text}), for example an item that does not exist; "
                           "it counted the job and will not run it again. Written to the delivery log.")
            self._fail(job, "the game could not apply it (for example the item does not exist or nothing was created)")
        elif kind == "UNKNOWN" and job is not None and job.seq == n:
            self.seq = n
            self._record(job, False)
            logger.warning(f"[dispatch] the game does not know the action {job.action!r} (job {n}); not retried. "
                           "Written to the delivery log.")
            self._fail(job, f"the game does not know the action {job.action!r} {job.args!r}")
        elif kind == "PROBE":
            mask = int(f.get("mask", "0") or 0)
            prev = int(f.get("prev", "0") or 0)
            logger.info(f"[dispatch] game state changed: {gate_text(prev)} -> {gate_text(mask)}")
        elif kind in ("SCENE_START", "SCENE_END", "BAD"):
            logger.info(f"[dispatch] game: {kind.lower()} {f}")

    def _on_state(self, n: typing.Optional[int]) -> None:
        if n is None:
            return
        job = self.current
        in_flight_counted = job is not None and job.seq is not None and n == job.seq and not job.fixed_seq
        if self.abs_applied is None:
            self.abs_applied = n
        elif self.seq is not None and n != self.seq and not in_flight_counted:
            self._on_rollback(n)
            job = self.current
        self.seq = n
        if job is None or job.seq is None or job.done.is_set() or job.fixed_seq:
            return
        if n == job.seq:
            # the number already includes this job: it was applied
            self._record(job, True)
            self.duplicate_count += 1
            logger.info(f"[dispatch] job {n} is already counted in the game's saved number; done.")
            job.finish("duplicate")
        elif job.seq != (n + 1) % 256:
            job.resyncs += 1
            job.seq = (n + 1) % 256
            logger.info(f"[dispatch] renumbering the job to {job.seq} to follow the game's number {n}.")
            asyncio.ensure_future(self._send(job))

    def _on_rollback(self, n: int) -> None:
        """The game's number is not what this client last had: a save was loaded. If it went back, the jobs counted after that
        point are gone from the game, so they are sent again in their original order, ahead of whatever was already waiting."""
        base = self.abs_applied
        a = None
        for cand in range(base, max(base - 256, -1), -1):
            if cand % 256 == n:
                a = cand
                break
        if a is None:
            logger.info(f"[dispatch] the game's job number is {n}, ahead of what this client has counted; following it.")
            self.abs_applied = n
            return
        if a == base:
            return
        lost = [e for e in self.ledger if e[0] > a and e[4]]
        self.ledger = [e for e in self.ledger if e[0] <= a]
        self.abs_applied = a
        self.rollback_count += 1
        self._held = []
        restore: typing.List[Job] = []
        cur = self.current
        if cur is not None and not cur.done.is_set() and not cur.fixed_seq:
            if is_death_job(cur.action, cur.args):
                cur.finish("dropped")
                logger.info("[dispatch] a death job that was being sent when the save was loaded is dropped, not sent again.")
            else:
                clone = Job(cur.action, cur.args, None, cur.message_full)
                clone.carried = list(cur.carried)
                restore.append(clone)
                cur.finish("requeued")
        # A death still waiting to be applied belongs to the life that was just left: it must not kill the reloaded one.
        waiting = [j for j in self._queue if is_death_job(j.action, j.args)]
        if waiting:
            self._queue = collections.deque(j for j in self._queue if not is_death_job(j.action, j.args))
            for j in waiting:
                j.finish("dropped")
            logger.info(f"[dispatch] {len(waiting)} death job(s) waiting when the save was loaded were dropped.")
        replay = [Job(action, args, None, message) for (_i, action, args, message, _r) in lost]
        for job in reversed(replay + restore):
            self._queue.appendleft(job)
        self.replayed_count += len(replay)
        if replay:
            logger.warning(f"[dispatch] a save was loaded: the game's job number went back from {base % 256} to {n}. "
                           f"Sending the {len(replay)} job(s) it no longer has again, in order.")
            self._ensure_pump()
        else:
            logger.warning(f"[dispatch] a save was loaded: the game's job number went back from {base % 256} to {n}. "
                           "None of the jobs after it can be replayed (they failed or are unknown).")

    def has_unfinished(self, action: str, args: str) -> bool:
        """True while a job with this action and these arguments is still queued, being sent or waiting for a calm moment."""
        jobs = list(self._queue) + ([self.current] if self.current is not None else [])
        return any(j.action == action and j.args == args and not j.done.is_set() for j in jobs)

    # ---- status ----------------------------------------------------------------------------------------------------
    def window_text(self) -> typing.Dict[str, str]:
        """What the client window and /ap_status show, in three blocks: "waiting" (what is queued and what it is waiting for), "failed"
        (empty when nothing has failed) and "recent" (the last jobs the game applied)."""
        count = len(self._queue) + (1 if self.current is not None else 0)
        if not count:
            waiting = "Deliveries waiting: none"
        else:
            rows = [f"Deliveries waiting: {count}"]
            if self.current is not None:
                job = self.current
                if job.state == "waiting":
                    state = f"waiting for a calm moment ({gate_text(job.gate)})"
                elif job.state in ("sent", "staged"):
                    state = "sent to the game, waiting for its answer"
                else:
                    state = "about to be sent"
                rows.append(f"  Now: {job.label} - {state}")
            for job in list(self._queue)[:3]:
                rows.append(f"  Next: {job.label}")
            if len(self._queue) > 3:
                rows.append(f"  ... and {len(self._queue) - 3} more")
            waiting = "\n".join(rows)
        failed_jobs = [j for j in self.history if j.state == "failed"][-5:]
        failed = ""
        if self.failed_count:
            rows = [f"Failed ({self.failed_count}, written to the delivery log):"]
            rows += [f"  {j.label}: {j.fail_reason or 'failed'}" for j in failed_jobs]
            failed = "\n".join(rows)
        done = [j for j in self.history if j.state in ("applied", "duplicate")][-8:]
        if done:
            rows = ["Recently delivered:"]
            for job in reversed(done):
                took = f"{(job.finished or time.time()) - job.created:.0f}s"
                rows.append(f"  {job.label} ({took})")
            recent = "\n".join(rows)
        else:
            recent = "Recently delivered: none"
        return {"waiting": waiting, "failed": failed, "recent": recent}

    def status_lines(self) -> typing.List[str]:
        lines = [f"Dispatcher: game's job number {self.seq if self.seq is not None else 'not reported yet'}, "
                 f"applied {self.applied_count}, repeats dropped {self.duplicate_count}, renumbered {self.resync_count}, "
                 f"save reloads {self.rollback_count} (jobs sent again {self.replayed_count})."]
        if self.current is not None:
            job = self.current
            extra = f", waiting for: {gate_text(job.gate)}" if job.state == "waiting" else ""
            lines.append(f"  in flight: job {job.seq} {job.text} [{job.state}{extra}], sent {job.sends} time(s)")
        if self._queue:
            lines.append(f"  queued behind it: {len(self._queue)}")
        for job in list(self.history)[-5:]:
            took = f"{(job.finished or time.time()) - job.created:.1f}s"
            lines.append(f"  job {job.seq} {job.text}: {job.state} in {took}")
        return lines
