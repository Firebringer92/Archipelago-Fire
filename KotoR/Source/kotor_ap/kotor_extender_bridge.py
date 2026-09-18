"""
kotor_extender_bridge.py -- the real socket connection from KotorClient.py
to the injected extender (127.0.0.1:25586)

Protocol (see extender/src/dllmain.c):
  Outgoing:  "APPLY:<arm_name>\n"       -- request a grant be queued/armed
             "NOTIFY:<url-encoded text>\n" -- one-shot on-screen message
                                           (see send_notify), not a grant
                                           --Indicates in game feedback screen that they are connected
  Incoming:  "STAGED:<arm_name>\n"      -- ack for an APPLY: we sent
             "ERROR:<message>\n"        -- an APPLY: (or other request) failed
             "EVENT:<log line>\n"       -- a kse.log line the extender's
                                           log-tail thread matched (AP|...
                                           marker), pushed unprompted

#BK Notes - Shouldn''t above incoming event detail out AP-Applied confirms receipt of the appllied arms.
#To confirm if any current apply will not be notifying the logging mechanisms.
#
# _track_delivery_from_event below is generic -- it matches ANY
# "AP|APPLIED|<name>|..." line, not a fixed list, so any arm whose
# NWScript emits that marker gets tracked automatically. Every real grant
# arm in generate_trampoline_batch.py (skills, XP, credits, companions,
# give_item, companion_class, etc.) ends with a matching
# KSE_Diag("AP|APPLIED|...") call -- this is the same marker
# arm_orchestrator.py's own --delivered= dequeue depends on, so a
# systematically-missing one would show up as "this arm re-arms forever,"
# a much louder bug than a stale GUI label.
# ONE confirmed, deliberate exception: `notify` actions (one-shot on-screen
# messages, see send_notify) never emit AP|APPLIED at all -- there's no
# real "success" state to confirm for a text message, so
# arm_orchestrator.py clears them unconditionally on the next area
# transition instead (see its own NOTIFY_PATH comment). This means a
# `notify` entry in kotor_extender_bridge's `deliveries` table would stay
# "queued" forever if one were ever tracked there -- but notify isn't
# routed through send_apply/deliveries at all (send_notify doesn't create
# a DeliveryRecord), so this doesn't actually surface as a bug in practice.

This module owns the persistent connection and a small delivery-tracking
table (arm_name -> DeliveryRecord) so the GUI can show, per item, one of
three states -- see delivery_state() and DeliveryRecord's own field
comments:
  Queued  -- we decided to send it and wrote to the socket
  Staged  -- the extender's STAGED: ack confirmed it actually RECEIVED
             the command and queued it into the trampoline system (not
             just that our local write() didn't raise -- see
             wait_staged()'s docstring for the real casualty this
             distinction was built to catch)
  Settled -- AP|APPLIED|... confirmed the trampoline actually fired
             in-game
This is the "why hasn't everything arrived yet" visibility the batching
model needs, since a queued item can sit for a bit before the player's next
area entry delivers it.
"""

from __future__ import annotations

import asyncio
import logging
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
                # Best-effort: dropped silently if no area is known yet
                # (e.g. the game hasn't loaded a save into the world yet at
                # the moment this socket connects) -- same "cosmetic, fine
                # to lose" design as every other send_notify call. Only
                # shows once the player's next area transition plays it,
                # same one-transition lag as every other notify/grant.
                await self.send_notify("Connected to KotorClient")
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
            self._track_staged_from_line(line[len("STAGED:"):])
            logger.info(f"[extender] {line}")
        elif line.startswith("ERROR:"):
            logger.info(f"[extender] {line}")
        # ACK:/SCANNED:/etc from diagnostic commands -- not used by the
        # normal item-delivery path, nothing to do with them here.

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
        if head in ("give_item", "companion_class", "additional_feats", "trap") and len(parts) > 1:
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

    async def send_apply_value(self, action: str, value: int) -> bool:
        """Sends APPLYVALUE:<action>:<value> -- the parameterized-action
        counterpart to send_apply, for exact-value corrections (set_xp,
        set_credits) rather than fixed-increment grants. Replace-semantics
        on the extender side: a new value supersedes an earlier pending one
        for the same action, so tracking it under its action name (not a
        per-call unique key) is correct here too."""
        if self._writer is None:
            logger.warning(f"send_apply_value({action}, {value}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:{action}:{value}\n".encode())
        await self._writer.drain()
        self.deliveries[action] = DeliveryRecord(action, time.time(), None, None, "")
        logger.info(f"[extender] queued: {action}={value}")
        return True

    async def send_delevel(self, new_level: int, new_xp: int, new_force: int = -1) -> bool:
        """Sends APPLYVALUE:delevel:<level>:<xp>:<force> -- the reconciler's
        fix for the documented SetXP gap: native SetXP() can't lower XP
        below the CURRENT level's banked threshold once vanilla
        combat/quest XP has carried the player past it. Writes level and XP
        directly via KSE_SetCreatureField instead. new_force=-1 (default)
        means "don't touch Force" (non-Jedi PC); pass the reconciler's own
        proportionally-scaled value (currentForce * newLevel/oldLevel) for a
        Jedi PC -- see kotor_reconciliation.py's delevel trigger. Replace
        semantics on the extender side, same as send_apply_value."""
        if self._writer is None:
            logger.warning(f"send_delevel({new_level}, {new_xp}, {new_force}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:delevel:{new_level}:{new_xp}:{new_force}\n".encode())
        await self._writer.drain()
        self.deliveries["delevel"] = DeliveryRecord("delevel", time.time(), None, None, "")
        logger.info(f"[extender] queued: delevel level={new_level} xp={new_xp} force={new_force}")
        return True

    async def send_force_power(self, spell_id: int) -> bool:
        """Sends APPLYVALUE:force_power:<spells.2da row id> -- grants one
        Force Power to the PC (the TSL power-port pilot's grant half; see
        generate_trampoline_batch.py's build_force_power_block
        and scripts/patch_tsl_powers.py). Id-keyed like give_item, so two
        different powers can be pending at once without colliding."""
        if self._writer is None:
            logger.warning(f"send_force_power({spell_id}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:force_power:{spell_id}\n".encode())
        await self._writer.drain()
        key = f"force_power:{spell_id}"
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, None, "")
        logger.info(f"[extender] queued: force_power {spell_id}")
        return True

    async def send_apply_item(self, resref: str, count: int) -> bool:
        """Sends APPLYVALUE:give_item:<resref>:<count> -- the generic gear-
        grant path (CreateItemOnObject), distinct from send_apply_value's
        single-int actions (set_xp/set_credits) since this needs both a
        resref and a count encoded together."""
        if self._writer is None:
            logger.warning(f"send_apply_item({resref}, {count}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:give_item:{resref}:{count}\n".encode())
        await self._writer.drain()
        key = f"give_item:{resref}"
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, None, "")
        logger.info(f"[extender] queued: give_item {resref} x{count}")
        return True

    async def send_companion_class(self, name: str, class_name: str) -> bool:
        """Sends APPLYVALUE:companion_class:<name>:<class_name> -- the
        CompanionClass mechanism (Options.py), used both for a real
        jedi_companion AP item (arm_name is literally
        "companion_class:<name>:<class_name>", see Items.py) and as a
        client-initiated follow-up right after a companion recruit arm
        fires for no_jedi/randomize_all (see KotorClient.py's
        _maybe_queue_companion_class). Tracked under a per-name key so
        concurrent assignments for different companions don't collide,
        same reasoning as send_apply_item's per-resref keying."""
        if self._writer is None:
            logger.warning(f"send_companion_class({name}, {class_name}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:companion_class:{name}:{class_name}\n".encode())
        await self._writer.drain()
        key = f"companion_class:{name}"
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, None, "")
        logger.info(f"[extender] queued: companion_class {name} -> {class_name}")
        return True

    async def send_additional_feats(self, name: str, feat_ids: typing.List[int]) -> bool:
        """Sends APPLYVALUE:additional_feats:<name>:<f1>,<f2>,<f3> -- the
        AdditionalFeats mechanism (Options.py). Unlike every other
        parameterized action, the target/values here are decided entirely
        client-side at delivery time (see KotorContext._check_pending_
        additional_feats), not baked into the received item itself -- the
        item is just a marker saying "grant 3 for character <name>
        eventually." feat_ids is always exactly 3 real feat.2da row ids
        from the fixed 18-feat combined pool (KotorClient.py's
        ADDITIONAL_FEATS_POOL);
        comma-joined since APPLYVALUE's own framing is colon-delimited.
        Tracked under a per-name key, same reasoning as
        send_companion_class."""
        if self._writer is None:
            logger.warning(f"send_additional_feats({name}, {feat_ids}): not connected to extender, not sent.")
            return False
        feat_csv = ",".join(str(f) for f in feat_ids)
        self._writer.write(f"APPLYVALUE:additional_feats:{name}:{feat_csv}\n".encode())
        await self._writer.drain()
        key = f"additional_feats:{name}"
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, None, "")
        logger.info(f"[extender] queued: additional_feats {name} -> {feat_ids}")
        return True

    async def send_trap(self, trap_type: str, params: str) -> bool:
        """Sends APPLYVALUE:trap:<trap_type>:<params> -- the single
        consolidated wire action for every Traps item (Options.py's
        Traps). One action name covers all 12 trap types, mirroring
        additional_feats:'s "decided client-side at delivery" shape: the
        item itself is just a marker (arm_name="trap:<trap_type>"),
        KotorClient.py computes the real specifics from the character's
        live state (which feat/power ids, which companion, how much to
        reduce a stat by) and passes them here pre-encoded as params
        (comma-joined ids, a companion key, a bare int -- whatever that
        specific trap_type expects, see generate_trampoline_batch.py's
        build_trap_block for the exact per-type shape). Tracked under a
        per-trap_type key -- traps are one-time-only by design (see
        Traps' docstring), so a collision here would mean the same
        trap type firing twice in-flight at once, which shouldn't happen
        given the delivery-log dedup every item already goes through."""
        if self._writer is None:
            logger.warning(f"send_trap({trap_type}, {params}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLYVALUE:trap:{trap_type}:{params}\n".encode())
        await self._writer.drain()
        key = f"trap:{trap_type}"
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, None, "")
        logger.info(f"[extender] queued: trap {trap_type} -> {params}")
        return True

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

    async def send_apply(self, arm_name: str) -> bool:
        """Sends APPLY:<arm_name> to the extender. Returns False immediately
        (no send attempted) if not currently connected -- callers should
        surface that to the user rather than silently dropping the item."""
        if self._writer is None:
            logger.warning(f"send_apply({arm_name}): not connected to extender, not sent.")
            return False
        self._writer.write(f"APPLY:{arm_name}\n".encode())
        await self._writer.drain()
        self.deliveries[arm_name] = DeliveryRecord(arm_name, time.time(), None, None, "")
        logger.info(f"[extender] queued: {arm_name}")
        return True

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
        """Sends NOTIFY:<url-encoded text> -- a one-shot on-screen message
        for confirmation of connection status in game client"""
        if self._writer is None:
            return False
        text = text.replace("\n", " ").replace("\r", " ")[:200]
        encoded = urllib.parse.quote(text, safe="")
        self._writer.write(f"NOTIFY:{encoded}\n".encode())
        await self._writer.drain()
        return True

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
    return "Queued"
