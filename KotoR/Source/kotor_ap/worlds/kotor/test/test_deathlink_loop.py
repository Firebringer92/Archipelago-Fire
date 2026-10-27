"""A death the client itself caused for an incoming DeathLink is not sent on as a new DeathLink (two linked players would otherwise kill each other for ever)."""
import asyncio
import os
import time
import unittest

KOTOR_CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "KotorClient.py")


def _context():
    import KotorClient
    ctx = KotorClient.KotorContext.__new__(KotorClient.KotorContext)   # no connection, no UI: only the fields the death hook reads
    ctx._link_death_applied_at = 0.0
    ctx.sent = []

    async def send_death(text=""):
        ctx.sent.append(text)
    ctx.send_death = send_death
    return ctx


@unittest.skipUnless(os.path.exists(KOTOR_CLIENT), "client not next to this world")
class TestDeathLinkDoesNotEcho(unittest.IsolatedAsyncioTestCase):
    async def test_an_own_death_is_sent(self):
        ctx = _context()
        ctx._on_local_death()
        await asyncio.sleep(0)
        self.assertEqual(len(ctx.sent), 1)

    async def test_a_death_just_after_a_link_death_is_not_sent_on(self):
        ctx = _context()
        ctx._link_death_applied_at = time.time()
        ctx._on_local_death()
        await asyncio.sleep(0)
        self.assertEqual(ctx.sent, [])
        self.assertEqual(ctx._link_death_applied_at, 0.0)      # used up: the next death is the player's own

    async def test_an_old_link_death_does_not_hide_a_new_own_death(self):
        import KotorClient
        ctx = _context()
        ctx._link_death_applied_at = time.time() - KotorClient.LINK_DEATH_ECHO_SECONDS - 1
        ctx._on_local_death()
        await asyncio.sleep(0)
        self.assertEqual(len(ctx.sent), 1)
