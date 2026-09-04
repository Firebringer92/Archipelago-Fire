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
# Claude reply (2026-09-02): _track_delivery_from_event below is generic --
# it matches ANY "AP|APPLIED|<name>|..." line, not a fixed list, so any arm
# whose NWScript emits that marker gets tracked automatically. Checked
# generate_trampoline_batch.py: every real grant arm (skills, XP, credits,
# companions, give_item, companion_class, etc.) ends with a matching
# KSE_Diag("AP|APPLIED|...") call -- confirmed by both the sheer count (38
# emissions in that file, matching arm count) and by this being the same
# marker arm_orchestrator.py's own --delivered= dequeue depends on, so a
# systematically-missing one would show up as "this arm re-arms forever,"
# a much louder bug than a stale GUI label -- never observed.
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
table (arm_name -> "queued" | "applied") so the GUI can show, per item,
whether it's just been sent to the game or has actually been confirmed
applied -- the "why hasn't everything arrived yet" visibility the batching
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
    queued_at: float
    applied_at: typing.Optional[float]
    detail: str  # the raw "before=X|after=Y" tail from an APPLIED line, once known



class ExtenderBridge:
    """Owns the TCP connection to the extender and the send/receive halves
    of the protocol. Call `connect_forever()` as a background asyncio task;
    it reconnects automatically if the game/extender isn't up yet or the
    connection drops (e.g. game closed/restarted)."""

    def __init__(self, on_event: typing.Callable[[str], None]):
        self._on_event = on_event
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
        elif line.startswith("STAGED:") or line.startswith("ERROR:"):
            logger.info(f"[extender] {line}")
        # ACK:/SCANNED:/etc from diagnostic commands -- not used by the
        # normal item-delivery path, nothing to do with them here.

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
        detail = parts[1] if len(parts) > 1 else ""
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
        self.deliveries[action] = DeliveryRecord(action, time.time(), None, "")
        logger.info(f"[extender] queued: {action}={value}")
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
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, "")
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
        self.deliveries[key] = DeliveryRecord(key, time.time(), None, "")
        logger.info(f"[extender] queued: companion_class {name} -> {class_name}")
        return True

    async def send_raw(self, command: str) -> bool:
        """Sends an arbitrary raw line straight to the extender socket, no
        framing/parsing on this side -- e.g. `DUMPMEM:16EBB958:64`,
        `READBYTE:...`, `SCANBYTES:...`, `SNAPSHOT:...`, any of the
        diagnostic commands ap_extender.c's ap_dispatch_command already
        understands. TEMPORARY/research escape hatch. used for researching force powers in game without
        memory hunting using cheat engine, see FutureDesign.md) --
        deliberately reuses THIS connection rather than opening a second
        one, since the extender's socket server only services one client at a time. Used for diagnosis/rsearch"""
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
        self.deliveries[arm_name] = DeliveryRecord(arm_name, time.time(), None, "")
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
