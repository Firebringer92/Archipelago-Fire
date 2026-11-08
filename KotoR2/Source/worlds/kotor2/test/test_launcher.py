"""The Launcher button: it is registered, and the plan it makes from the marker files starts the client the way the tests of the client expect."""
import os
import sys
import tempfile
import unittest

from ..ClientLauncher import CLIENT_FILE, plan_launch, read_marker


class TestRegistered(unittest.TestCase):
    def test_the_button_is_in_the_launcher(self):
        from worlds.LauncherComponents import Type, components
        import worlds.kotor2  # noqa: F401  (registers the button)
        mine = [c for c in components if c.display_name == "KOTOR 2 Client"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0].type, Type.CLIENT)
        self.assertTrue(callable(mine[0].func))


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state")
        self.install = os.path.join(self.tmp.name, "client")
        self.core = os.path.join(self.tmp.name, "core")
        os.makedirs(self.state)
        os.makedirs(self.install)
        os.makedirs(self.core)
        self.python = os.path.join(self.tmp.name, "python.exe")
        open(self.python, "wb").close()
        open(os.path.join(self.install, CLIENT_FILE), "w").close()

    def mark(self, name, value):
        with open(os.path.join(self.state, name), "w", encoding="utf-8") as f:
            f.write(value)

    def test_without_an_install_the_player_is_told_what_to_do(self):
        plan, messages = plan_launch(self.state, [], lambda p: True)
        self.assertIsNone(plan)
        self.assertIn("install_path.txt", messages[0])

    def test_a_missing_client_file_is_reported(self):
        self.mark("install_path.txt", os.path.join(self.tmp.name, "gone"))
        plan, messages = plan_launch(self.state, [], lambda p: True)
        self.assertIsNone(plan)
        self.assertIn(CLIENT_FILE, messages[0])

    def test_the_recorded_python_and_folders_make_the_command(self):
        self.mark("install_path.txt", self.install + "\n")
        self.mark("python_path.txt", self.python)
        self.mark("core_path.txt", self.core)
        plan, messages = plan_launch(self.state, ["--connect", "localhost:38281"], lambda p: True, base_env={"PYTHONPATH": "old"})
        self.assertEqual(messages, [])
        self.assertEqual(plan["command"], ["cmd", "/K", self.python, os.path.join(self.install, CLIENT_FILE), "--connect", "localhost:38281"])
        self.assertEqual(plan["env"]["PYTHONPATH"], os.pathsep.join([self.core, self.install, "old"]))
        self.assertEqual(plan["cwd"], self.core)

    def test_without_a_core_folder_the_client_runs_from_its_own(self):
        self.mark("install_path.txt", self.install)
        self.mark("python_path.txt", self.python)
        plan, _ = plan_launch(self.state, [], lambda p: True, base_env={})
        self.assertEqual((plan["cwd"], plan["env"]["PYTHONPATH"]), (self.install, self.install))

    def test_without_kivy_the_console_client_is_used_unless_the_caller_chose(self):
        self.mark("install_path.txt", self.install)
        self.mark("python_path.txt", self.python)
        plan, _ = plan_launch(self.state, [], lambda p: False, base_env={})
        self.assertEqual(plan["command"][-1], "--nogui")
        plan, _ = plan_launch(self.state, ["--gui"], lambda p: False, base_env={})
        self.assertNotIn("--nogui", plan["command"])
        plan, _ = plan_launch(self.state, [], lambda p: True, base_env={})
        self.assertNotIn("--nogui", plan["command"])

    def test_a_missing_python_or_core_is_a_message_not_a_crash(self):
        self.mark("install_path.txt", self.install)
        self.mark("python_path.txt", os.path.join(self.tmp.name, "nope.exe"))
        self.mark("core_path.txt", os.path.join(self.tmp.name, "nocore"))
        plan, messages = plan_launch(self.state, [], lambda p: True, base_env={})
        self.assertIsNotNone(plan)
        self.assertEqual(len(messages), 2)
        self.assertEqual(plan["command"][2], sys.executable)
        self.assertEqual(plan["cwd"], self.install)

    def test_markers_are_looked_for_in_the_folders_in_order(self):
        second = os.path.join(self.tmp.name, "machine")
        os.makedirs(second)
        for name, value in (("install_path.txt", self.install), ("python_path.txt", self.python)):
            with open(os.path.join(second, name), "w", encoding="utf-8") as f:
                f.write(value)
        plan, messages = plan_launch([self.state, second], [], lambda p: True, base_env={})       # nothing in the first folder: the second one is used
        self.assertEqual((messages, plan["cwd"]), ([], self.install))
        self.mark("python_path.txt", sys.executable)                                               # now the first folder has one: it wins
        plan, _ = plan_launch([self.state, second], [], lambda p: True, base_env={})
        self.assertEqual(plan["command"][2], sys.executable)
        plan, messages = plan_launch([self.state, os.path.join(self.tmp.name, "empty")], [], lambda p: True)
        self.assertIsNone(plan)
        self.assertIn(self.state, messages[0])

    def test_an_empty_marker_counts_as_missing(self):
        self.mark("install_path.txt", "  \n")
        self.assertIsNone(read_marker(self.state, "install_path.txt"))


if __name__ == "__main__":
    unittest.main()
