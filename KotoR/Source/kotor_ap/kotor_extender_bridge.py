"""
kotor_extender_bridge.py -- the real socket connection from KotorClient.py
to the injected extender (127.0.0.1:25586)

Every delivery to the game is a job for the job dispatcher (kotor_dispatcher.py): the send_* methods below turn their arguments into one
job, and the dispatcher writes it to the extender as DISPATCH:<seq>:<action>[:<args>] when it is its turn. The game applies it at a calm
moment, once, and answers with AP|DISPATCH|APPLIED (or FAILED / UNKNOWN). The older staged-arm commands (APPLY:, APPLYVALUE:, NOTIFY:) are
no longer sent.

Protocol (see extender/src_k1se/ap_extender.c):
  Outgoing:  "DISPATCH:<seq>:<action>[:<args>][^^<message>]\n"  -- one dispatcher job
             "SHOPSTOCK:<planet>:<resref>,...\n"                -- the stores' catalog (baked into the area-entry scripts)
  Incoming:  "STAGED:..."  -- ack for a command the extender queued (a DISPATCH: job is answered "staged" / "busy" / "toolong")
             "ERROR:<message>" -- a request failed
             "EVENT:<log line>" -- a kse.log line the extender's log-tail thread matched (AP|... marker), pushed unprompted

This module owns the persistent connection and a small delivery table (key -> DeliveryRecord) that the rest of the client reads
(wait_staged, rejection, the heavy-arm confirmation). A record follows its job: queued and staged when the job is accepted (the
dispatcher resends until the game answers, so there is nothing further to wait for), settled when the game answers APPLIED or DUP,
rejected when the job fails, removed when a newer job replaces it. See _submit_job and _watch_job.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import typing
import urllib.parse

logger = logging.getLogger("Extender")
client_logger = logging.getLogger("Client")

EXTENDER_HOST = "127.0.0.1"
EXTENDER_PORT = 25586
RECONNECT_DELAY = 3.0


class DeliveryRecord(typing.NamedTuple):
    arm_name: str
    queued_at: float  # Queued: we decided to send it and wrote to the socket
    staged_at: typing.Optional[float]  # Staged: extender's STAGED: ack -- it actually
                                        # received the command and queued it into the
                                        # trampoline system, not just that our local
                                        # write() didn't raise. See wait_staged()'s
                                        # docstring for the real bug this distinction
                                        # closes.
    applied_at: typing.Optional[float]  # Settled: AP|APPLIED|... confirmation, the
                                         # trampoline actually fired in-game
    detail: str  # the raw "before=X|after=Y" tail from an APPLIED line, once known
    # Rejected: the extender answered ERROR instead of STAGED (for example "unknown item"), so this send will never
    # be staged or applied. Kept as its own state so it is not shown as a delivery that is merely waiting.
    rejected_at: typing.Optional[float] = None
    reject_detail: str = ""



class ExtenderBridge:
    """Owns the TCP connection to the extender and the send/receive halves
    of the protocol. Call `connect_forever()` as a background asyncio task;
    it reconnects automatically if the game/extender isn't up yet or the
    connection drops (e.g. game closed/restarted)."""

    def __init__(
        self,
        on_event: typing.Callable[[str], None],
        on_connect: typing.Optional[typing.Callable[[], None]] = None,
    ):
        self._on_event = on_event
        # Fires every time this socket (re)connects, including every
        # automatic reconnect after the local game process itself
        # restarts -- distinct from the AP server's own Connected
        # package, which doesn't refire just because the LOCAL game
        # crashed and relaunched (the AP session usually stays open
        # across that). See KotorContext's wiring for what this resets.
        self._on_connect = on_connect
        self._writer: typing.Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.deliveries: typing.Dict[str, DeliveryRecord] = {}
        self._delivery_seq = 0
        # The job dispatcher every delivery goes through (set by KotorContext), and the job behind each delivery key.
        self.dispatcher = None
        self._jobs: typing.Dict[str, typing.Any] = {}
        # Set by the dispatcher client (kotor_dispatcher.py): called as (kind, seq) for the extender's reply to a DISPATCH: line.
        self.on_dispatch_reply: typing.Optional[typing.Callable[[str, int], None]] = None

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect_forever(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_connection(EXTENDER_HOST, EXTENDER_PORT)
                self._writer = writer
                self.connected = True
                # Before anything can stream in and be read against
                # leftover state from a previous connection -- see
                # __init__'s comment on _on_connect for why this can't
                # wait for the AP server's own Connected package.
                if self._on_connect is not None:
                    self._on_connect()
                logger.info(f"Connected to extender at {EXTENDER_HOST}:{EXTENDER_PORT}")
                client_logger.info("Extender: connected.")
                await self._read_loop(reader)
            except (ConnectionRefusedError, OSError) as e:
                if self.connected:
                    logger.info(f"Extender connection lost ({e}); will retry.")
                    client_logger.info("Extender: disconnected, retrying...")
                self.connected = False
                self._writer = None
            await asyncio.sleep(RECONNECT_DELAY)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                self._handle_line(line)
        finally:
            self.connected = False
            self._writer = None

    def _handle_line(self, line: str) -> None:
        if line.startswith("EVENT:"):
            event = line[len("EVENT:"):]
            try:
                self._track_delivery_from_event(event)
                self._on_event(event)
            except Exception:
                # A bug in event parsing/handling must never kill this read
                # loop -- an uncaught exception here previously propagated
                # all the way out of connect_forever() (which only catches
                # ConnectionRefusedError/OSError), silently ending the whole
                # bridge task with no visible error. One bad line should log
                # and move on, not take down the entire connection.
                logger.exception(f"[extender] error handling event, dropping this line: {event!r}")
        elif line.startswith("STAGED:"):
            if not self._dispatch_reply(line[len("STAGED:"):]):
                self._track_staged_from_line(line[len("STAGED:"):])
            logger.info(f"[extender] {line}")
        elif line.startswith("ERROR:"):
            if not self._dispatch_reply(line[len("ERROR:"):]):
                self._track_error_from_line(line[len("ERROR:"):])
            logger.info(f"[extender] {line}")
        # ACK:/SCANNED:/etc from diagnostic commands -- not used by the
        # normal item-delivery path, nothing to do with them here.

    _UNKNOWN_ITEM_RE = re.compile(r"unknown item '([^']*)'")
    _DISPATCH_REPLY_RE = re.compile(r"^dispatch(?: (busy|too long))?:(\d+)")

    def _dispatch_reply(self, rest: str) -> bool:
        """The extender's answer to a DISPATCH: line (STAGED:dispatch:<seq>, ERROR:dispatch busy:<seq>, ERROR:dispatch too
        long:<seq>), handed to the dispatcher client. These are not item deliveries, so they never get a DeliveryRecord.
        Returns True if the line was one of them."""
        m = self._DISPATCH_REPLY_RE.match(rest)
        if m is None:
            return False
        if self.on_dispatch_reply is not None:
            kind = {None: "staged", "busy": "busy", "too long": "toolong"}[m.group(1)]
            self.on_dispatch_reply(kind, int(m.group(2)))
        return True

    def _track_error_from_line(self, rest: str) -> None:
        """Marks a delivery Rejected when the extender answers 'ERROR:unknown item '<name>'': it does not know the
        command it was sent, so no STAGED or APPLIED will ever follow for it. Other ERROR replies name no delivery
        and are left to the log. Same per-type key derivation as _track_staged_from_line."""
        m = self._UNKNOWN_ITEM_RE.search(rest)
        if m is None:
            return
        parts = m.group(1).split(":")
        head = parts[0]
        if head in ("give_item", "companion_class", "trap", "force_power") and len(parts) > 1:
            key = f"{head}:{parts[1]}"
        else:
            key = head
        record = self.deliveries.get(key)
        if record is not None and record.staged_at is None and record.applied_at is None:
            self.deliveries[key] = record._replace(rejected_at=time.time(), reject_detail=rest.strip())

    def rejection(self, key: str) -> typing.Optional[str]:
        """The extender's ERROR text if this delivery was rejected, else None."""
        record = self.deliveries.get(key)
        if record is not None and record.rejected_at is not None and record.staged_at is None:
            return record.reject_detail or "rejected"
        return None

    def _track_staged_from_line(self, rest: str) -> None:
        """Watches for 'STAGED:<...>' -- the extender's own confirmation
        that it actually RECEIVED and queued a command (ap_run_orchestrator
        already returned by the time this reply is sent), not just that our
        local socket write() didn't raise. See wait_staged()'s docstring
        for the real bug this distinction closes: a write can succeed at
        the OS level even when the receiving process is already dying, so
        "our write didn't throw" was never sufficient proof the extender
        actually got it.

        Same per-type key derivation as _track_delivery_from_event, just
        parsing STAGED's colon-delimited wire format
        (see ap_extender.c's _snprintf(reply, ..., "STAGED:...") call
        sites) instead of AP|APPLIED|'s pipe-delimited one. shopstock/
        notify replies have no matching DeliveryRecord at all (not
        per-item deliveries) -- .get() returning None there is expected,
        not a bug."""
        parts = rest.split(":")
        head = parts[0]
        if head in ("give_item", "companion_class", "trap") and len(parts) > 1:
            key = f"{head}:{parts[1]}"
        elif head == "force_power" and len(parts) > 1:
            key = f"force_power:{parts[1]}"
        else:
            # Bare arm name (class_sentinel, companion_bastila, ...) or a
            # single-token parameterized action (set_xp, set_credits,
            # delevel) -- the key is just the first token either way.
            key = head
        record = self.deliveries.get(key)
        if record is not None and record.staged_at is None:
            self.deliveries[key] = record._replace(staged_at=time.time())

    async def wait_staged(self, key: str, timeout: float = 15.0) -> bool:
        """Waits for this delivery's STAGED: ack -- see _track_staged_
        from_line's docstring for why this matters and DeliveryRecord's
        own field comments for the 3-state model (Queued/Staged/Settled).
        Callers should treat a False return as a real send failure (do NOT
        log a settled outcome), not just log-and-continue: a real casualty
        was found this way -- a give_item write succeeded locally while
        the game process was already dying from an unrelated crash, so
        the command never actually reached a live extender, and the item
        was permanently marked "sent" (settled, never retried) despite
        never having been queued at all. 15s default is generous for a
        local subprocess round-trip (ap_run_orchestrator's own internal
        timeout is 90s, but that's for a hung compile, not the normal
        case)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            record = self.deliveries.get(key)
            if record is not None and record.staged_at is not None:
                return True
            if record is not None and record.rejected_at is not None:
                return False  # the extender refused it; waiting out the timeout would change nothing
            await asyncio.sleep(0.1)
        return False

    def _track_delivery_from_event(self, event: str) -> None:
        """Watches for 'AP|APPLIED|<name>|before=X|after=Y' lines to flip a
        queued delivery record over to confirmed-applied, for the GUI's
        pending-vs-delivered view."""
        marker = "AP|APPLIED|"
        idx = event.find(marker)
        if idx < 0:
            return
        rest = event[idx + len(marker):]
        parts = rest.split("|", 1)
        name = parts[0]
        # .rstrip('"'): the raw kse.log line quotes its own message
        # (msg="..."), and this is the tail end of that string -- strip the
        # closing quote so it doesn't leak into the GUI's displayed detail
        # text (cosmetic only, doesn't affect the name/arm_id matching
        # above, which already terminates correctly on a real "|").
        detail = parts[1].rstrip('"') if len(parts) > 1 else ""
        if name == "give_item":
            # The trampoline's give_item confirmation always logs under the
            # fixed literal "give_item", not a per-resref name (see
            # generate_trampoline_batch.py's build_give_item_block) -- key
            # on the specific resref instead so concurrent grants of two
            # different gear items don't collide under one shared record.
            for field in detail.split("|"):
                if field.startswith("resref="):
                    name = f"give_item:{field[len('resref='):]}"
                    break
        elif name == "companion_class":
            # Same shape as give_item above -- the trampoline confirmation
            # logs under the fixed literal "companion_class", keyed further
            # by the specific companion name (see build_companion_class_block).
            for field in detail.split("|"):
                if field.startswith("name="):
                    name = f"companion_class:{field[len('name='):]}"
                    break
        elif name == "trap":
            # Same shape again -- the trampoline confirmation logs under
            # the fixed literal "trap", keyed further by the specific
            # trap_type (see build_trap_block).
            for field in detail.split("|"):
                if field.startswith("type="):
                    name = f"trap:{field[len('type='):]}"
                    break
        elif name == "force_power":
            # Same shape again, keyed by spells.2da row id (see
            # build_force_power_block).
            for field in detail.split("|"):
                if field.startswith("id="):
                    name = f"force_power:{field[len('id='):]}"
                    break
        record = self.deliveries.get(name)
        if record is not None and record.applied_at is None:
            self.deliveries[name] = record._replace(applied_at=time.time(), detail=detail)

    # ---- delivery through the job dispatcher -----------------------------------------------------------------------
    # Every delivery is a dispatcher job (kotor_dispatcher.py): the game applies it at a calm moment, once, and answers APPLIED. The
    # DeliveryRecord keeps the three states the rest of the client already reads: queued (accepted here), staged (set at the same
    # moment: the dispatcher resends until the game answers, so there is nothing further to wait for), settled (the game answered
    # APPLIED or DUP) -- or rejected (the game could not do it, or does not know the action).
    def _submit_job(self, key: str, action: str, args: str = "", message: str = "") -> bool:
        if self._writer is None:
            logger.warning(f"{key}: not connected to extender, not sent.")
            return False
        if self.dispatcher is None:
            logger.warning(f"{key}: no dispatcher attached, not sent.")
            return False
        now = time.time()
        job = self.dispatcher.submit(action, args, message=message)
        self.deliveries[key] = DeliveryRecord(key, now, now, None, "")
        self._jobs[key] = job
        logger.info(f"[extender] queued: {key} ({action} {args})".rstrip())
        asyncio.ensure_future(self._watch_job(key, job))
        return True

    async def _watch_job(self, key: str, job) -> None:
        """Turns the job's final state into the delivery record's."""
        await job.done.wait()
        if self._jobs.get(key) is not job:
            return          # a newer job for the same delivery has taken over the record
        record = self.deliveries.get(key)
        if record is None:
            return
        if job.state in ("applied", "duplicate"):
            self.deliveries[key] = record._replace(applied_at=time.time(), detail=f"dispatcher: {job.state}")
        elif job.state in ("replaced", "dropped"):
            self.deliveries.pop(key, None)
        else:
            # a rejected delivery is one that never reached "staged" (rejection() and delivery_state() read it that way)
            self.deliveries[key] = record._replace(staged_at=None, rejected_at=time.time(), reject_detail=job.fail_reason or job.state)

    async def send_apply_value(self, action: str, value: int, message: str = "") -> bool:
        """An exact-value correction (set_xp, set_credits): a dispatcher job that replaces a waiting one of the same kind."""
        return self._submit_job(action, action, str(value), message)

    async def send_delevel(self, new_level: int, new_xp: int, new_force: int = -1) -> bool:
        """The reconciler's delevel fix (level, XP and Force points, -1 = leave the Force points alone) as a dispatcher job."""
        return self._submit_job("delevel", "delevel", f"{new_level}:{new_xp}:{new_force}")

    async def send_force_power(self, spell_id: int, message: str = "") -> bool:
        """Grants one Force power (a spells.2da row) as a dispatcher job."""
        return self._submit_job(f"force_power:{spell_id}", "force_power", str(spell_id), message)

    async def send_dispatch(self, seq: int, action: str, args: str = "", message: str = "") -> bool:
        """Sends DISPATCH:<seq>:<action>[:<args>] -- one job for the poll's dispatcher (see kotor_dispatcher.py). The
        extender's STAGED:dispatch:<seq> reply only means the job is in the DLL's inbox; the game's own
        AP|DISPATCH|APPLIED line is the confirmation. The args are free text, so line breaks are removed. The optional
        message is shown to the player in the same apply, after the action (sent after a ^^ marker)."""
        if self._writer is None:
            return False
        text = f"{seq}:{action}" + (f":{args}" if args else "") + (f"^^{message.replace('^^', '^')}" if message else "")
        text = text.replace("\r", " ").replace("\n", " ")
        try:
            self._writer.write(f"DISPATCH:{text}\n".encode())
            await self._writer.drain()
        except (ConnectionError, OSError):
            return False
        return True

    async def send_apply_item(self, resref: str, count: int, message: str = "") -> bool:
        """Creates `count` of an item on the player as a dispatcher job."""
        return self._submit_job(f"give_item:{resref}", "give_item", f"{resref}:{count}", message)

    async def send_companion_class(self, name: str, class_name: str, message: str = "") -> bool:
        """Sets a companion's class (the companion must be in the party; the game answers FAILED otherwise) as a dispatcher job."""
        return self._submit_job(f"companion_class:{name}", "companion_class", f"{name}:{class_name}", message)

    async def send_trap(self, trap_type: str, params: str, message: str = "") -> bool:
        """A trap item as a dispatcher job: trap:<type>:<params> ("-" when the type takes none)."""
        return self._submit_job(f"trap:{trap_type}", "trap", f"{trap_type}:{params}", message)

    async def send_raw(self, command: str) -> bool:
        """Sends an arbitrary raw line straight to the extender socket, no
        framing/parsing on this side -- e.g. `DUMPMEM:16EBB958:64`,
        `READBYTE:...`, `SCANBYTES:...`, `SNAPSHOT:...`, any of the
        diagnostic commands ap_extender.c's ap_dispatch_command already
        understands. Research/diagnostic escape hatch (built for the Force
        Powers memory-offset hunt, so live memory could be inspected
        without an external scanner). Deliberately reuses THIS connection
        rather than opening a second one, since the extender's socket
        server only services one client at a time."""
        if self._writer is None:
            logger.warning(f"send_raw({command!r}): not connected to extender, not sent.")
            return False
        self._writer.write(f"{command}\n".encode())
        await self._writer.drain()
        logger.info(f"[extender] sent raw: {command}")
        return True

    async def send_apply(self, arm_name: str, message: str = "") -> bool:
        """A fixed arm (a class, a companion, a skill, XP, a death...) as a dispatcher job."""
        return self._submit_job(arm_name, "arm", arm_name, message)

    async def send_shop_stock(self, planet_stock: typing.Dict[str, typing.List[str]]) -> bool:
        """Sends SHOPSTOCK:<planet>:<resref1>,<resref2>,... ONCE PER PLANET
        set once at Connect (see KotorContext.on_package), not a queued grant.
        orchestrator.py parses the planet prefix and persists each planet's
        list to its own key in _shop_stock.json, force-regenerating
        whatever's currently armed."""
        if self._writer is None:
            logger.warning(f"send_shop_stock({len(planet_stock)} planets): not connected to extender, not sent.")
            return False
        for planet, resrefs in planet_stock.items():
            self._writer.write(f"SHOPSTOCK:{planet}:{','.join(resrefs)}\n".encode())
            await self._writer.drain()
            logger.info(f"[extender] sent shop catalog for {planet}: {len(resrefs)} items")
        return True

    async def send_notify(self, text: str) -> bool:
        """A message for the player, shown by the dispatcher when the game is calm."""
        text = text.replace("\n", " ").replace("\r", " ")[:200]
        return self._submit_job(f"notify:{text}", "notify", "", text)

    def pending_deliveries(self) -> typing.List[DeliveryRecord]:
        return [d for d in self.deliveries.values() if d.applied_at is None]

    def recent_deliveries(self, limit: int = 20) -> typing.List[DeliveryRecord]:
        return sorted(self.deliveries.values(), key=lambda d: d.queued_at, reverse=True)[:limit]

    def recently_settled(self, limit: int = 20) -> typing.List[DeliveryRecord]:
        """Settled deliveries only, most recently CONFIRMED first (by
        applied_at, not queued_at) -- a "Recently Settled" view distinct
        from recent_deliveries()'s queued-order listing, which mixes in
        everything still Queued/Staged too."""
        settled = [d for d in self.deliveries.values() if d.applied_at is not None]
        return sorted(settled, key=lambda d: d.applied_at, reverse=True)[:limit]


def delivery_state(record: DeliveryRecord) -> str:
    """Single source of truth for the 3-state label (Queued/Staged/Settled)
    -- shared by /ap_status and the GUI status panel so they can't drift
    out of sync with each other."""
    if record.applied_at is not None:
        return "Settled"
    if record.staged_at is not None:
        return "Staged"
    if record.rejected_at is not None:
        return "Rejected"
    return "Queued"
