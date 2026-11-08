"""Client side of the game's job dispatcher (nss/k2se_disp.nss). Ported from the K1 client's kotor_dispatcher.py, simplified for the file link.

One job is in flight at a time. A job carries a number 1..255 (wrapping); the game keeps the number of the last applied job in its save, so a
loaded older save brings back the matching number. The game answers on the outbox:
  T|counter|guard          the saved number (sent when it changes and at game start)
  D|seq|action|counter     applied
  U|seq|counter            already applied (counts as done)
  S|seq|counter            out of order: the game has `counter`; renumber to counter+1 and send again
  G|seq|saved|job          the save belongs to another seed: the job is failed, with a plain explanation
  W|seq|reason             the action ran but was refused (the number still advances, a D line follows)

Rollback: every job the game counted is kept in a ledger (this session only). When the game reports a number lower than ours, the jobs the old
save never had are sent again in their original order, except deaths.
"""
import asyncio
import collections
import logging
import time
import typing

logger = logging.getLogger("Client")

NO_MESSAGE_ACTIONS = {"xp", "credits", "set_credits", "set_xp", "tracker"}
MESSAGE_LINE_BREAK = "~~"
MAX_BATCH_CHARS = 180            # the game reads at most 200 characters of the message
DEATH_ACTIONS = {"trap:death", "force_death"}
RECEIPT_PREFIX = "You received: "


def counter_of(abs_index: int) -> int:
    """Game counter after `abs_index` counted jobs: 0, then 1..255 repeating."""
    return 0 if abs_index <= 0 else ((abs_index - 1) % 255) + 1


def next_seq(counter: int) -> int:
    return (counter % 255) + 1


class Job:
    def __init__(self, action: str, args: str = "", message: str = "", seq: typing.Optional[int] = None):
        self.action = action
        self.args = args
        self.message = message
        self.message_full = message
        self.seq = seq
        self.fixed_seq = seq is not None
        self.state = "queued"             # queued, sent, applied, duplicate, failed, replaced
        self.fail_reason = ""
        self.refused = ""
        self.sends = 0
        self.last_sign = time.time()
        self.index = -1                   # AP item index this job delivers, if any
        self.item_name = ""
        self.carried: typing.List[str] = []
        self.done = asyncio.Event()

    @property
    def text(self) -> str:
        return "%s:%s" % (self.action, self.args) if self.args else self.action

    def finish(self, state: str) -> None:
        self.state = state
        self.done.set()


class DispatchClient:
    RESEND_AFTER = 20.0
    MAX_SENDS = 30
    LEARN_WAIT = 20.0         # how long to wait for the game's first report of its number

    def __init__(self, link, guard: int = 0):
        self.link = link
        self.guard = guard
        self.counter: typing.Optional[int] = None      # the number the game last reported
        self.current: typing.Optional[Job] = None
        self.history: typing.Deque[Job] = collections.deque(maxlen=50)
        self._queue: typing.Deque[Job] = collections.deque()
        self._held: typing.List[str] = []
        self._task: typing.Optional[asyncio.Task] = None
        self.abs_applied: typing.Optional[int] = None
        self.ledger: typing.List[typing.Tuple[int, str, str, str, bool]] = []
        self.on_failure: typing.Optional[typing.Callable[[Job, str], None]] = None
        self.on_applied: typing.Optional[typing.Callable[[Job], None]] = None
        self.stats = collections.Counter()

    # ---- keeping the work across a restart --------------------------------------------------------------------------
    def pending_jobs(self) -> typing.List[Job]:
        """The jobs not finished yet: the one in flight and those waiting behind it."""
        jobs = [self.current] if self.current is not None and not self.current.done.is_set() else []
        return jobs + list(self._queue)

    def export_state(self) -> dict:
        """Everything a restarted client needs to carry on: the number of jobs the game has counted, the ledger (to send again what an older save lacks) and the
        jobs that have not been applied yet."""
        return {"abs_applied": self.abs_applied, "ledger": [list(e) for e in self.ledger],
                "pending": [{"action": j.action, "args": j.args, "message": j.message_full, "index": j.index, "item_name": j.item_name} for j in self.pending_jobs()]}

    def import_state(self, data: dict) -> typing.List[dict]:
        """Take back the counted-jobs number and the ledger of an earlier run of the client; returns its pending jobs for the caller to submit again."""
        self.abs_applied = data.get("abs_applied")
        self.ledger = [(int(a), str(b), str(c), str(d), bool(e)) for a, b, c, d, e in data.get("ledger", [])][-1000:]
        return list(data.get("pending", []))

    # ---- submitting ------------------------------------------------------------------------------------------------
    def submit(self, action: str, args: str = "", message: str = "", index: int = -1, item_name: str = "",
               replay_seq: typing.Optional[int] = None) -> Job:
        job = Job(action, args, message if action not in NO_MESSAGE_ACTIONS else "", replay_seq)
        job.index, job.item_name = index, item_name
        self._queue.append(job)
        self._ensure_pump()
        return job

    def _ensure_pump(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._pump())

    def _fail(self, job: Job, reason: str) -> None:
        job.fail_reason = reason
        self.stats["failed"] += 1
        if self.on_failure:
            try:
                self.on_failure(job, reason)
            except Exception:
                logger.exception("[dispatch] failure callback raised")
        job.finish("failed")

    def _record(self, job: Job) -> None:
        if job.fixed_seq:
            return
        if self.abs_applied is None:
            self.abs_applied = ((job.seq or 1) - 1) % 255
        self.abs_applied += 1
        replayable = job.text not in DEATH_ACTIONS and job.action != "death"
        self.ledger.append((self.abs_applied, job.action, job.args, job.message_full, replayable))
        del self.ledger[:-1000]

    def _batch_message(self, job: Job) -> None:
        """One message box per run of jobs: while more jobs wait behind this one its message is held; the last job of the run carries all lines."""
        lines = self._held + ([job.message] if job.message else [])
        if self._queue and len(MESSAGE_LINE_BREAK.join(lines)) < MAX_BATCH_CHARS:
            self._held = lines
            job.message = ""
            return
        job.carried = list(self._held)
        self._held = []
        job.message = MESSAGE_LINE_BREAK.join(lines)[:MAX_BATCH_CHARS + 20]

    async def _learn_counter(self) -> None:
        end = time.time() + self.LEARN_WAIT
        while self.counter is None and time.time() < end:
            await asyncio.sleep(0.25)
        if self.counter is None:
            logger.warning("[dispatch] the game has not reported its job number; numbering from 1 and letting the game correct it.")

    async def _pump(self) -> None:
        while self._queue or self.current is not None:
            if self.current is None:
                job = self.current = self._queue.popleft()
                self._batch_message(job)
                if job.seq is None:
                    if self.counter is None:
                        await self._learn_counter()
                    if self.current is not job:
                        continue                   # while we waited for the game's number a rollback took this job back into the queue: it is taken up again from there
                    job.seq = next_seq(self.counter or 0)
                logger.info("[dispatch] sending job %d: %s" % (job.seq, job.text))
                self._send(job)
            job = self.current
            if job is None:
                continue
            if job.done.is_set():
                self.history.append(job)
                self.current = None
                if job.state == "failed" and job.carried:
                    self._queue.appendleft(Job("notify", "", MESSAGE_LINE_BREAK.join(job.carried)))
                continue
            await asyncio.sleep(0.25)
            if job.done.is_set():
                continue
            if time.time() - job.last_sign > self.RESEND_AFTER:
                if job.sends >= self.MAX_SENDS:
                    self._fail(job, "no answer from the game after %d sends" % job.sends)
                    continue
                self._send(job)

    def _send(self, job: Job) -> None:
        job.sends += 1
        job.last_sign = time.time()
        job.state = "sent" if job.state in ("queued", "sent") else job.state
        if not self.link.write_job(job.seq, self.guard, job.action, job.args, job.message):
            logger.warning("[dispatch] could not write the job file; will retry")

    # ---- answers from the game --------------------------------------------------------------------------------------
    def on_event(self, line: str) -> None:
        parts = line.split("|")
        kind = parts[0]
        if kind == "SESSION":
            self.counter = None       # a new game process: its number arrives with its first T line
            return
        try:
            if kind == "T":
                self._on_state(int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
            elif kind == "D":
                self._on_done(int(parts[1]), "applied", int(parts[3]) if len(parts) > 3 else None)
            elif kind == "U":
                self._on_done(int(parts[1]), "duplicate", int(parts[2]) if len(parts) > 2 else None)
            elif kind == "S":
                self._on_sync(int(parts[1]), int(parts[2]))
            elif kind == "G":
                self._on_guard(int(parts[1]), int(parts[2]), int(parts[3]))
            elif kind == "W":
                self._on_refused(int(parts[1]), parts[2] if len(parts) > 2 else "")
        except (ValueError, IndexError):
            logger.debug("[dispatch] could not read game line %r" % line)

    def _on_state(self, counter: int, guard: int) -> None:
        previous = self.counter
        self.counter = counter
        if self.abs_applied is None and counter > 0:
            self.abs_applied = counter          # joined mid-way: the ledger starts here
        if self.abs_applied is not None and counter_of(self.abs_applied) != counter:
            self._rolled_back(counter)

    def _on_done(self, seq: int, state: str, counter: typing.Optional[int]) -> None:
        job = self.current
        if job is None or job.seq != seq or job.done.is_set():
            return
        if state == "applied":
            self.counter = seq
            self._record(job)
            self.stats["applied"] += 1
            job.finish("applied")
            if self.on_applied:
                self.on_applied(job)
        else:
            self.stats["duplicate"] += 1
            job.finish("duplicate")

    def _on_sync(self, seq: int, counter: int) -> None:
        job = self.current
        self.counter = counter
        if job is None or job.seq != seq or job.fixed_seq or job.done.is_set():
            return
        if self.abs_applied is not None and counter_of(self.abs_applied) != counter:
            self._rolled_back(counter)
        job.seq = next_seq(counter)
        self.stats["resync"] += 1
        logger.info("[dispatch] the game has job number %d; renumbering to %d" % (counter, job.seq))
        self._send(job)

    def _on_guard(self, seq: int, saved: int, job_guard: int) -> None:
        job = self.current
        if job is not None and job.seq == seq and not job.done.is_set():
            self._fail(job, "this save belongs to a different seed (save %d, this run %d). Load the save made for this run." % (saved, job_guard))

    def _on_refused(self, seq: int, reason: str) -> None:
        job = self.current
        if job is not None and job.seq == seq:
            job.refused = reason
            logger.warning("[dispatch] the game refused job %d (%s)" % (seq, job.text))

    def _rolled_back(self, counter: int) -> None:
        """The game's number is lower than ours: an older save was loaded. Send again the jobs it never had, in order."""
        if self.abs_applied is None:
            return
        target = None
        for idx in range(self.abs_applied, max(0, self.abs_applied - 255), -1):
            if counter_of(idx) == counter:
                target = idx
                break
        if counter == 0 and target is None:
            target = 0
        if target is None:
            return
        missing = [e for e in self.ledger if e[0] > target]
        self.stats["rollback"] += 1
        logger.info("[dispatch] an older save was loaded (game number %d, expected %d): replaying %d job(s)" % (
            counter, counter_of(self.abs_applied), len(missing)))
        self.abs_applied = target
        replay: typing.List[Job] = []
        for idx, action, args, message, replayable in missing:
            seq = counter_of(idx)
            if replayable:
                replay.append(Job(action, args, "", seq))
            else:
                replay.append(Job("notify", "", "", seq))   # the number still has to be counted; a death is never repeated
            self.stats["replayed"] += 1
        self.ledger = [e for e in self.ledger if e[0] <= target]
        for job in reversed(replay):
            self._queue.appendleft(job)
        # the job in flight (if any) is renumbered after the replay: put it back
        if self.current is not None and not self.current.fixed_seq:
            cur = self.current
            self.current = None
            cur.seq = None
            cur.state = "queued"
            self._queue.insert(len(replay), cur)
        self._ensure_pump()
