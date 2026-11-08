"""
The client and the game's extender talk over one TCP connection that must never leave this computer. capabilities.json lists kotor_extender_bridge.py as the one file
that opens a connection and says it is to 127.0.0.1, but the capability check only sees that a connection is opened, not where. These tests hold both ends to the address:
the client side connects only to a host constant that is 127.0.0.1, and the extender (C source) binds only to 127.0.0.1, never to every interface.
"""
import ast
import os
import re
import unittest

import kotor_extender_bridge

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
EXTENDER_C = os.path.join(REPO_ROOT, "extender", "src_k1se", "ap_extender.c")

CONNECT_CALLS = {"open_connection", "create_connection", "start_server", "create_server"}


def _dotted_tail(func):
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


class TestClientSide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(kotor_extender_bridge.__file__, encoding="utf-8") as f:
            cls.tree = ast.parse(f.read())

    def test_the_host_constant_is_loopback(self):
        self.assertEqual(kotor_extender_bridge.EXTENDER_HOST, "127.0.0.1")

    def test_the_host_constant_is_assigned_once_and_only_from_a_literal(self):
        assigns = [n for n in ast.walk(self.tree) if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                   and any(isinstance(t, ast.Name) and t.id == "EXTENDER_HOST" for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))]
        self.assertEqual(len(assigns), 1, "EXTENDER_HOST must be set in exactly one place")
        self.assertIsInstance(assigns[0], ast.Assign)
        self.assertIsInstance(assigns[0].value, ast.Constant, "EXTENDER_HOST must be a literal, not read from a setting, argument or environment variable")
        self.assertNotIn("global EXTENDER_HOST", ast.unparse(self.tree), "nothing may rebind the host at run time")

    def test_every_connection_goes_to_the_host_constant(self):
        calls = [n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and _dotted_tail(n.func) in CONNECT_CALLS]
        self.assertTrue(calls, "the bridge is expected to open its connection with one of " + ", ".join(sorted(CONNECT_CALLS)))
        for call in calls:
            with self.subTest(line=call.lineno):
                self.assertTrue(call.args, f"line {call.lineno}: the host must be the first positional argument")
                first = call.args[0]
                self.assertTrue(isinstance(first, ast.Name) and first.id == "EXTENDER_HOST", f"line {call.lineno}: connects to {ast.unparse(first)}, not EXTENDER_HOST")
                self.assertFalse(call.keywords and any(k.arg in ("host", "local_addr", "sock") for k in call.keywords), f"line {call.lineno}: host given as a keyword as well")

    def test_nothing_in_the_bridge_listens_for_connections(self):
        calls = {_dotted_tail(n.func) for n in ast.walk(self.tree) if isinstance(n, ast.Call)}
        self.assertFalse(calls & {"start_server", "create_server", "listen", "bind", "accept"}, "the client only connects out; it must not open a port")


@unittest.skipUnless(os.path.isfile(EXTENDER_C), "the extender source is not in this layout")
class TestExtenderSide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(EXTENDER_C, encoding="utf-8", errors="replace") as f:
            cls.source = f.read()
        # Comments are not code: a note that mentions 0.0.0.0 must not fail the test, and a commented-out bind must not pass it.
        text = re.sub(r"/\*.*?\*/", " ", cls.source, flags=re.S)
        cls.code = re.sub(r"//[^\n]*", " ", text)
        # The same with the text inside string literals blanked (same length, so positions line up): a log message that says "bind() failed" is not a call to bind().
        cls.code_without_strings = re.sub(r'"(?:\\.|[^"\\\n])*"', lambda m: '"' + " " * (len(m.group()) - 2) + '"', cls.code)

    def test_the_only_address_it_ever_sets_is_loopback(self):
        addresses = re.findall(r'inet_addr\(\s*"([^"]*)"\s*\)', self.code)
        self.assertTrue(addresses, "the extender is expected to set its listening address with inet_addr")
        self.assertEqual(set(addresses), {"127.0.0.1"})

    def test_it_never_listens_on_every_interface(self):
        for bad in ("INADDR_ANY", "in6addr_any", "0.0.0.0", "htonl(0)", "getaddrinfo", "AI_PASSIVE"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, self.code)

    def test_there_is_exactly_one_bind_and_it_follows_the_loopback_address(self):
        binds = [m.start() for m in re.finditer(r"\bbind\s*\(", self.code_without_strings)]
        self.assertEqual(len(binds), 1, "more than one bind() in the extender: check where the second one listens")
        before = self.code[max(0, binds[0] - 400):binds[0]]
        self.assertIn('inet_addr("127.0.0.1")', before, "the bind() is not directly preceded by the loopback address being set")

    def test_the_port_the_client_uses_is_the_one_the_extender_listens_on(self):
        port = re.search(r"#define\s+AP_EXTENDER_PORT\s+(\d+)", self.code)
        self.assertIsNotNone(port)
        self.assertEqual(int(port.group(1)), kotor_extender_bridge.EXTENDER_PORT)


if __name__ == "__main__":
    unittest.main()
