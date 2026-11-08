"""File link between the KOTOR 2 client and the game (extender natives 902-906).

  inbox   %LOCALAPPDATA%\\K2SE\\ap\\inbox.txt    the client writes ONE job at a time (atomic replace); the game's dispatcher script reads it
  outbox  %LOCALAPPDATA%\\K2SE\\ap\\outbox.txt   the game appends "<seq>|<line>"; the client reads new lines

The game numbers outbox lines from 1 for each game process, so a number that goes back means a new game session (or a deleted file).
"""
import os
import typing

DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "K2SE", "ap")


class Link:
    def __init__(self, directory: str = DEFAULT_DIR):
        self.directory = directory
        self.inbox_path = os.path.join(directory, "inbox.txt")
        self.outbox_path = os.path.join(directory, "outbox.txt")
        self._offset = 0
        self._last_seq = 0
        os.makedirs(directory, exist_ok=True)

    # ---- client -> game -------------------------------------------------------------------------------------------
    def write_job(self, seq: int, guard: int, action: str, args: str, message: str) -> bool:
        clean = lambda t: t.replace("\r", " ").replace("\n", " ")
        text = "job_seq=%d\njob_guard=%d\njob_action=%s\njob_args=%s\njob_msg=%s\n" % (seq, guard, clean(action), clean(args), clean(message)[:190])
        tmp = self.inbox_path + ".tmp"
        try:
            with open(tmp, "w", newline="\n", encoding="ascii", errors="replace") as f:
                f.write(text)
            os.replace(tmp, self.inbox_path)
            return True
        except OSError:
            return False

    def clear_inbox(self) -> None:
        try:
            os.remove(self.inbox_path)
        except FileNotFoundError:
            pass

    # ---- game -> client -------------------------------------------------------------------------------------------
    def read_new(self) -> typing.List[str]:
        """New outbox lines since the last call, without the game's own sequence prefix. A file that shrank or a sequence that went back is read
        from the start (a new game session)."""
        try:
            size = os.path.getsize(self.outbox_path)
        except FileNotFoundError:
            return []
        if size < self._offset:
            self._offset = 0
            self._last_seq = 0
        out: typing.List[str] = []
        try:
            with open(self.outbox_path, "rb") as f:
                f.seek(self._offset)
                data = f.read()
        except OSError:
            return []
        end = data.rfind(b"\n")
        if end < 0:
            return []
        self._offset += end + 1
        for raw in data[:end].split(b"\n"):
            line = raw.decode("ascii", "replace").strip()
            if not line:
                continue
            head, _, rest = line.partition("|")
            if head.isdigit():
                n = int(head)
                if n <= self._last_seq and n == 1:
                    out.append("SESSION|")        # a new game process started numbering again
                self._last_seq = n
                line = rest
            out.append(line)
        return out

    def skip_existing(self) -> None:
        """Ignore everything already in the outbox (used when the client starts and wants only what happens next)."""
        try:
            self._offset = os.path.getsize(self.outbox_path)
        except FileNotFoundError:
            self._offset = 0
