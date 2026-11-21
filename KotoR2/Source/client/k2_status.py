"""What the client says about itself: the Status tab and the Heartbeat log. Everything here is plain Python (no Kivy), so it is tested without a window;
client/k2_gui.py puts the same text on the screen.

  * heartbeat      the logger behind the Heartbeat tab: the bookkeeping that would drown the main log (each job sent, the game's wrapper lines, what each
                   randomizer changed) and, every HEARTBEAT_EVERY seconds, one line that says whether the game is running and answering.
  * GameWatch      is the game's process running, and when did the game last write to the outbox? The outbox only gets a line when something happens, so
                   silence alone proves nothing: a game that runs, has jobs waiting and has said nothing for SILENT_AFTER seconds is the case worth a warning.
  * Snapshot       the numbers the Status tab shows, collected by the client in one place; render() turns it into the labels' text.
"""
import logging
import time
import typing
from dataclasses import dataclass

from k2_patch import game_running

heartbeat = logging.getLogger("Heartbeat")

HEARTBEAT_EVERY = 30.0          # seconds between the periodic lines of the Heartbeat log
PROCESS_EVERY = 5.0             # seconds between looks at the game's process
SILENT_AFTER = 90.0             # a running game with jobs waiting that has not written for this long is called silent


def ago(seconds: typing.Optional[float]) -> str:
    """'4 s ago', '3 min ago', 'never' for a time span."""
    if seconds is None:
        return "never"
    seconds = max(0, int(seconds))
    if seconds < 90:
        return "%d s ago" % seconds
    if seconds < 90 * 60:
        return "%d min ago" % round(seconds / 60)
    return "%.1f h ago" % (seconds / 3600)


class GameWatch:
    """The game's process and the time of its last report. `running` and `clock` are replaceable so a test needs neither the game nor real time."""

    def __init__(self, running: typing.Callable[[], bool] = game_running, clock: typing.Callable[[], float] = time.time):
        self._running = running
        self._clock = clock
        self.running: typing.Optional[bool] = None       # None until the process has been looked at once
        self.last_heard: typing.Optional[float] = None   # when a line from the game last reached the client (history from before the client started does not count)
        self.sessions = 0                                # game processes seen through their first outbox line (SESSION) since the client started
        self._last_check = 0.0
        self._last_beat = 0.0
        self._silent_noted = False

    def heard(self) -> None:
        self.last_heard = self._clock()
        self._silent_noted = False

    def new_session(self) -> None:
        self.sessions += 1
        self.heard()

    def since_heard(self) -> typing.Optional[float]:
        return None if self.last_heard is None else self._clock() - self.last_heard

    def silent(self, jobs_waiting: bool) -> bool:
        """The game is running, jobs wait for it, and it has been quiet for a long time (still loading, stuck at a menu, or its dispatcher loop has stopped)."""
        quiet = self.since_heard()
        return bool(self.running and jobs_waiting and (quiet is None or quiet > SILENT_AFTER))

    def process_due(self) -> bool:
        return self._clock() - self._last_check >= PROCESS_EVERY

    def refresh(self, force: bool = False) -> typing.List[str]:
        """Looks at the process when PROCESS_EVERY seconds have passed (a look takes about a tenth of a second: call it off the main thread). Returns the
        lines for the Heartbeat log about what changed."""
        now = self._clock()
        if not force and now - self._last_check < PROCESS_EVERY:
            return []
        self._last_check = now
        before = self.running
        try:
            self.running = bool(self._running())
        except Exception:                 # the process list could not be read: say nothing new rather than claim the game closed
            return []
        if before is None:
            return ["game process: %s" % ("running" if self.running else "not running")]
        if self.running and not before:
            return ["the game started"]
        if before and not self.running:
            self.last_heard = None
            return ["the game closed"]
        return []

    def beat_due(self) -> bool:
        now = self._clock()
        if now - self._last_beat >= HEARTBEAT_EVERY:
            self._last_beat = now
            return True
        return False

    def silence_note(self, jobs_waiting: bool) -> typing.Optional[str]:
        """One line, once per silence, for the Heartbeat log."""
        if self.silent(jobs_waiting) and not self._silent_noted:
            self._silent_noted = True
            return "the game is running but has not answered for %s while jobs wait" % ago(self.since_heard()).replace(" ago", "")
        return None


@dataclass
class Snapshot:
    """Everything the Status tab shows, as plain values."""
    server_connected: bool = False
    slot_name: str = ""
    seed_name: str = ""
    game_running: typing.Optional[bool] = None
    since_heard: typing.Optional[float] = None
    sessions: int = 0
    module: str = ""
    level: int = 0
    alignment: int = 50
    xp: typing.Optional[int] = None
    patching: bool = False
    patch_text: str = ""
    patch_problems: bool = False
    patch_age: typing.Optional[float] = None
    checks_done: int = 0
    checks_total: int = 0
    victory: bool = False
    goal_sent: bool = False
    job_counter: typing.Optional[int] = None
    waiting: str = "Deliveries waiting: none"
    failed: str = ""
    recent: str = "Recently delivered: none"
    jobs_waiting: int = 0
    jobs_failed: int = 0
    jobs_applied: int = 0


def alignment_word(value: int) -> str:
    return "light side" if value >= 67 else "dark side" if value <= 33 else "neutral"


def warnings_for(s: Snapshot, silent: bool) -> typing.List[str]:
    """The things a player has to know about, most important first."""
    out: typing.List[str] = []
    if not s.server_connected:
        out.append("Not connected to the Archipelago server: type the address in the bar at the top and press Connect.")
    if s.patch_problems:
        out.append("The last patch finished with problems: read the warnings in the Archipelago tab before starting the game.")
    if s.game_running is False and s.jobs_waiting:
        out.append("%d delivery(ies) wait for the game: they are sent when it runs." % s.jobs_waiting)
    if silent:
        out.append("The game is running but has not answered for %s while deliveries wait. It may still be loading; if this lasts, load a save game." % ago(s.since_heard).replace(" ago", ""))
    if s.jobs_failed:
        out.append("%d delivery(ies) failed in this run: they are tried again when the game reports its state." % s.jobs_failed)
    return out


def render(s: Snapshot, silent: bool = False) -> typing.Dict[str, str]:
    """The text of each label of the Status tab."""
    if s.server_connected:
        server = "Archipelago server: connected as %s%s" % (s.slot_name or "?", " (seed %s)" % s.seed_name if s.seed_name else "")
    else:
        server = "Archipelago server: not connected"
    if s.game_running is None:
        game = "Game: looking ..."
    elif not s.game_running:
        game = "Game: not running"
    else:
        game = "Game: running; last report %s" % ago(s.since_heard)
        if s.sessions > 1:
            game += "; %d game sessions this run" % s.sessions
    state = ""
    if s.game_running and s.level:
        state = "Area %s, level %d, %s (%d)" % (s.module or "?", s.level, alignment_word(s.alignment), s.alignment)
        if s.xp is not None:
            state += ", %d XP" % s.xp
    if s.patching:
        patch = "Game files: being written now ..."
    elif s.patch_text:
        patch = "Game files: " + s.patch_text + ("" if s.patch_age is None else " (%s)" % ago(s.patch_age))
    else:
        patch = "Game files: not written in this run"
    checks = "Checks: %d / %d" % (s.checks_done, s.checks_total)
    if s.goal_sent:
        checks += " - goal reached, reported to the server"
    elif s.victory:
        checks += " - goal reached"
    jobs = "Game job number: %s; applied this run: %d" % ("unknown" if s.job_counter is None else s.job_counter, s.jobs_applied)
    warn = "\n".join("! " + w for w in warnings_for(s, silent))
    return {"server": server, "game": game, "state": state, "patch": patch, "checks": checks, "jobs": jobs,
            "waiting": s.waiting, "failed": s.failed, "recent": s.recent, "warnings": warn}


def heartbeat_line(s: Snapshot) -> str:
    """The periodic line of the Heartbeat log: one glance at whether everything that should be moving is."""
    game = "unknown" if s.game_running is None else "running, last report %s" % ago(s.since_heard) if s.game_running else "not running"
    return "heartbeat: server %s; game %s; job %s; %d waiting, %d applied, %d failed; checks %d/%d" % (
        "connected" if s.server_connected else "not connected", game, "?" if s.job_counter is None else s.job_counter,
        s.jobs_waiting, s.jobs_applied, s.jobs_failed, s.checks_done, s.checks_total)
