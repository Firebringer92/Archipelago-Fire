"""A stand-in for the game's dispatcher script (nss/k2se_disp.nss), for client tests without the game.

It reads the inbox the way the script does (job_seq, job_guard, job_action, job_args, job_msg), keeps the saved counter and guard, applies a job once and
writes the same outbox lines. `effects` is the list of applied jobs of the current save: loading a save restores its list, like the real game state.
"""
import os
import typing

from k2_files import Link


class FakeGame:
    def __init__(self, link: Link, counter: int = 0, guard: int = 0):
        self.link = link
        self.counter = counter
        self.guard = guard
        self.calm = True
        self.effects: typing.List[typing.Tuple[int, str, str]] = []
        self.stages: typing.List[int] = []              # the tracker stages applied in the current save
        self.saves: typing.Dict[str, typing.Tuple[int, int, list, list]] = {}
        self._out_seq = 0
        self._last_state: typing.Optional[typing.Tuple[int, int]] = None
        self._last_report: typing.Optional[str] = None
        self.refuse_actions: typing.Set[str] = set()

    def _put(self, line: str) -> None:
        self._out_seq += 1
        with open(self.link.outbox_path, "ab") as f:
            f.write(("%d|%s\r\n" % (self._out_seq, line)).encode("ascii"))

    def _read_inbox(self) -> typing.Dict[str, str]:
        try:
            with open(self.link.inbox_path, encoding="ascii", errors="replace") as fh:
                text = fh.read()
        except FileNotFoundError:
            return {}
        out = {}
        for ln in text.splitlines():
            k, _, v = ln.partition("=")
            out[k.strip()] = v.strip()
        return out

    def _report_once(self, key: str, line: str) -> None:
        if self._last_report == key:
            return
        self._last_report = key
        self._put(line)

    def save(self, name: str) -> None:
        self.saves[name] = (self.counter, self.guard, list(self.effects), list(self.stages))

    def load(self, name: str) -> None:
        self.counter, self.guard, effects, stages = self.saves[name]
        self.effects = list(effects)
        self.stages = list(stages)
        self._last_state = None            # the script's loop starts again on area entry and reports the state

    def restart_process(self) -> None:
        """A new game process: numbering of outbox lines starts over."""
        self._out_seq = 0
        self._last_state = None
        self._last_report = None

    def poll(self) -> None:
        state = (self.counter, self.guard)
        if state != self._last_state:
            self._last_state = state
            self._put("T|%d|%d" % state)
        job = self._read_inbox()
        seq = int(job.get("job_seq", "0") or 0)
        if seq <= 0:
            return
        job_guard = int(job.get("job_guard", "0") or 0)
        if self.guard != 0 and job_guard != self.guard:
            self._report_once("G%d/%d" % (seq, self.counter), "G|%d|%d|%d" % (seq, self.guard, job_guard))
            return
        if seq == self.counter:
            self._report_once("U%d/%d" % (seq, self.counter), "U|%d|%d" % (seq, self.counter))
            return
        if seq != (self.counter % 255) + 1:
            self._report_once("S%d/%d" % (seq, self.counter), "S|%d|%d" % (seq, self.counter))
            return
        if not self.calm:
            return
        action, args = job.get("job_action", ""), job.get("job_args", "")
        if action in self.refuse_actions:
            self._put("W|%d|refused %s" % (seq, action))
        elif action == "tracker":
            self.stages.append(int(args))       # the Archipelago Tracker quest: counted like any job, kept apart so the tests of the items need not skip it
        else:
            self.effects.append((seq, action, args))
        if self.guard == 0 and job_guard > 0:
            self.guard = job_guard
        self.counter = seq
        self._put("D|%d|%s|%d" % (seq, action, seq))
