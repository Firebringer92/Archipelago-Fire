"""Writes the seed's files into the game's Override folder when the client connects ("connect, patch, then launch").

What it does and keeps track of:
  * every file is compared with what is already there and only changed when different;
  * a file that already existed and was not ours is copied to Override/_k2ap_backup first and put back on revert;
  * files an earlier seed wrote that this seed does not need are removed (a switched-off feature must not keep last seed's data);
  * a manifest in the K2SE/ap folder lists what was written, so revert and clean-up are exact.
The seed's numbers go into a marked block of the extender's config.txt (outside the game folder, in %LOCALAPPDATA%/K2SE); everything else in that file is kept.
A file that did not exist when the game started is invisible until the game is relaunched; a file that only changed is read again when used. The result says
which case applies.
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import typing

MANIFEST = "patch_manifest.json"
CONFIG_BEGIN = "# --- k2ap begin (written by the Archipelago client; do not edit) ---"
CONFIG_END = "# --- k2ap end ---"
CONFIG_LIMIT = 8191        # the extender reads only this many bytes of config.txt
BACKUP_DIR = "_k2ap_backup"
EXE = "swkotor2.exe"
STEAM_DEFAULTS = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II",
    r"C:\Program Files\Steam\steamapps\common\Knights of the Old Republic II",
    r"C:\GOG Games\Star Wars - KotOR2",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Star Wars - KotOR2",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_game_dir(preferred: typing.Optional[str], saved_file: str) -> typing.Optional[str]:
    """The game folder: the given one, the saved choice, the environment, then the usual install places. None when no folder holds the game."""
    candidates = [preferred, os.environ.get("K2_GAME_DIR")]
    try:
        with open(saved_file) as f:
            candidates.insert(1, f.read().strip())
    except OSError:
        pass
    candidates += list(STEAM_DEFAULTS)
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, EXE)):
            return os.path.normpath(c)
    return None


def game_running() -> bool:
    """True while the game process exists (only known on Windows; False elsewhere)."""
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + EXE, "/NH"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return EXE.lower() in out.lower()


class PatchResult:
    def __init__(self) -> None:
        self.created: typing.List[str] = []
        self.changed: typing.List[str] = []
        self.same: typing.List[str] = []
        self.removed: typing.List[str] = []
        self.backed_up: typing.List[str] = []
        self.errors: typing.List[str] = []
        self.game_was_running = False

    @property
    def relaunch_needed(self) -> bool:
        """New files are invisible to a game that is already running."""
        return self.game_was_running and bool(self.created or self.removed)

    def summary(self) -> str:
        parts = ["%d new" % len(self.created), "%d updated" % len(self.changed), "%d unchanged" % len(self.same)]
        if self.removed:
            parts.append("%d removed" % len(self.removed))
        text = "KOTOR 2 patch: " + ", ".join(parts) + "."
        if self.errors:
            text += " Problems: " + "; ".join(self.errors)
        if self.relaunch_needed:
            text += " The game is running: close it and start it again so it sees the new files."
        return text


class Patcher:
    def __init__(self, game_dir: str, state_dir: str, running: typing.Callable[[], bool] = game_running,
                 config_path: typing.Optional[str] = None):
        self.config_path = config_path or os.path.join(os.path.dirname(os.path.abspath(state_dir)), "config.txt")
        self.game_dir = game_dir
        self.override = os.path.join(game_dir, "Override")
        self.backup = os.path.join(self.override, BACKUP_DIR)
        self.manifest_path = os.path.join(state_dir, MANIFEST)
        self._running = running

    # ---- module files (the K1 way: edited in place after a backup, put back on revert; client/k2_modules.py) ----------------------
    def module_store(self):
        from k2_modules import ModuleStore
        return ModuleStore(os.path.join(self.game_dir, "modules"), os.path.dirname(self.manifest_path))

    def restore_modules(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        """(restored, left alone): puts every module file this client edited back to the game's own."""
        try:
            return self.module_store().restore_all()
        except Exception as e:
            logging.getLogger("Client").warning("KOTOR 2: module files could not be restored: %s" % e)
            return [], []

    # ---- manifest ----------------------------------------------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self.manifest_path) as f:
                data = json.load(f)
            if data.get("game_dir", "").lower() == self.game_dir.lower():
                return data
        except (OSError, ValueError):
            pass
        return {"game_dir": self.game_dir, "files": {}}

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.manifest_path)

    # ---- apply ---------------------------------------------------------------------------------------------------------
    def apply(self, files: typing.Dict[str, bytes], prune: bool = True, config: typing.Optional[typing.Sequence[str]] = None) -> PatchResult:
        """Make Override hold `files` (name -> bytes). With prune, files an earlier patch wrote that are not in `files` are removed (or restored).
        With `config`, the marked block of config.txt is set to those lines."""
        res = PatchResult()
        res.game_was_running = self._running()
        data = self._load()
        known: dict = data["files"]
        try:
            os.makedirs(self.override, exist_ok=True)
        except OSError as e:
            res.errors.append("cannot use %s (%s)" % (self.override, e))
            return res
        for name, blob in sorted(files.items()):
            path = os.path.join(self.override, name)
            digest = _sha(blob)
            entry = known.get(name)
            try:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        current = f.read()
                    if _sha(current) == digest:
                        res.same.append(name)
                        if entry is None:
                            # already there with the very content we want, and not written by this client (an older deployment, or the game's own file): keep a
                            # copy so a revert gives it back instead of deleting it (a research script may call it, like a harness script its own _orig)
                            os.makedirs(self.backup, exist_ok=True)
                            shutil.copy2(path, os.path.join(self.backup, name))
                            known[name] = {"sha": digest, "backup": True}
                        continue
                    if entry is None:                      # somebody else's file: keep a copy
                        os.makedirs(self.backup, exist_ok=True)
                        shutil.copy2(path, os.path.join(self.backup, name))
                        res.backed_up.append(name)
                        entry = {"backup": True}
                    self._write(path, blob)
                    res.changed.append(name)
                else:
                    self._write(path, blob)
                    res.created.append(name)
                    entry = entry or {"backup": False}
                entry["sha"] = digest
                known[name] = entry
            except OSError as e:
                res.errors.append("%s: %s" % (name, e))
        if prune:
            for name in sorted(set(known) - set(files)):
                self._drop(name, known, res)
        if config is not None:
            self.apply_config(config, res)
        self._save(data)
        return res

    # ---- config.txt -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _without_block(text: str) -> str:
        out, skipping = [], False
        for line in text.splitlines():
            if line.strip() == CONFIG_BEGIN:
                skipping = True
            elif line.strip() == CONFIG_END:
                skipping = False
            elif not skipping:
                out.append(line)
        return "\n".join(out).rstrip("\n")

    def apply_config(self, lines: typing.Sequence[str], res: typing.Optional[PatchResult] = None) -> bool:
        """Replace the marked block of config.txt with `lines` (empty: take the block out). Returns False and records a problem on failure."""
        res = res if res is not None else PatchResult()
        try:
            with open(self.config_path, encoding="ascii", errors="replace") as f:
                old = f.read()
        except OSError:
            old = ""
        base = self._without_block(old)
        parts = [base] if base else []
        if lines:
            parts.append("\n".join([CONFIG_BEGIN] + list(lines) + [CONFIG_END]))
        text = "\n".join(parts) + "\n" if parts else ""
        if len(text.encode("ascii", "replace")) > CONFIG_LIMIT:
            res.errors.append("config.txt would be over %d bytes, the game would ignore the end of it" % CONFIG_LIMIT)
            return False
        if text == old.replace("\r\n", "\n"):
            return True
        tmp = self.config_path + ".k2ap_tmp"
        last: typing.Optional[OSError] = None
        for _ in range(20):                      # the game may have the file open for a moment
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(tmp, "w", newline="\n", encoding="ascii", errors="replace") as f:
                    f.write(text)
                os.replace(tmp, self.config_path)
                return True
            except OSError as e:
                last = e
                time.sleep(0.05)
        res.errors.append("config.txt: %s" % last)
        return False

    def revert(self) -> PatchResult:
        """Take away everything this client put into Override and put back the files it replaced."""
        res = PatchResult()
        res.game_was_running = self._running()
        data = self._load()
        for name in sorted(data["files"]):
            self._drop(name, data["files"], res)
        restored, left_alone = self.restore_modules()
        res.removed += restored
        res.errors += ["%s was changed by something else and was left alone" % name for name in left_alone]
        try:
            from k2_journal import restore_strings
            put_back, kept = restore_strings(self.game_dir, os.path.dirname(self.manifest_path), res.game_was_running)
            res.removed += put_back
            res.errors += ["%s was changed by something else and was left alone" % name for name in kept]
        except Exception as e:
            res.errors.append("dialog.tlk could not be put back: %s" % e)
        self.apply_config([], res)
        self._save(data)
        return res

    def _drop(self, name: str, known: dict, res: PatchResult) -> None:
        path = os.path.join(self.override, name)
        saved = os.path.join(self.backup, name)
        try:
            if known[name].get("backup") and os.path.exists(saved):
                shutil.move(saved, path)
            elif os.path.exists(path):
                os.remove(path)
            del known[name]
            res.removed.append(name)
        except OSError as e:
            res.errors.append("%s: %s" % (name, e))

    @staticmethod
    def _write(path: str, blob: bytes) -> None:
        tmp = path + ".k2ap_tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)


def payload_files(directory: typing.Optional[str]) -> typing.Dict[str, bytes]:
    """Static files shipped with the client (compiled scripts, items, dialogues): every regular file in the folder, by name."""
    out: typing.Dict[str, bytes] = {}
    if directory and os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            p = os.path.join(directory, name)
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    out[name] = f.read()
    return out


# ---- the report behind /k2_paths -----------------------------------------------------------------------------------------------
# Files of the payload without which the game side does not work at all (names in Override, lower case). The full list comes from tools/build_payload.py.
PAYLOAD_KEY_FILES = ("k2se_ap_enter.ncs", "k2se_rb.ncs", "a_bet3m4.ncs", "a_hatchopen.ncs", "ap_jedi_inc.ncs", "ap_vd_do.ncs", "k2se_cwb.ncs", "k_ptat_sandper.ncs")
OUR_PREFIXES = ("k2se_", "k2ap_", "ap_", "apvendor", "apbz")
EXTENDER = "version.dll"            # the extender's proxy DLL, next to the game's exe


def path_report(game_dir: typing.Optional[str], state_dir: str, config_path: str, payload_dir: str, running: typing.Callable[[], bool] = game_running) -> typing.List[str]:
    """Plain-language lines about every place the client uses and whether it is in order. Read only."""
    lines: typing.List[str] = []

    def line(ok: typing.Optional[bool], text: str) -> None:
        lines.append(("OK    " if ok else "WRONG " if ok is not None else "NOTE  ") + text)

    if not game_dir:
        line(False, "game folder: not found (the folder that contains swkotor2.exe). Use /k2_patch <folder> once, or start the client with --game-dir.")
    else:
        line(True, "game folder: %s" % game_dir)
        line(os.path.isfile(os.path.join(game_dir, EXTENDER)), "extender (%s next to the exe)%s" % (EXTENDER, "" if os.path.isfile(os.path.join(game_dir, EXTENDER)) else
                                                                                                  ": missing, the game cannot receive jobs or send reports"))
        override = os.path.join(game_dir, "Override")
        names = sorted(os.listdir(override)) if os.path.isdir(override) else []
        line(os.path.isdir(override), "Override folder: %d files%s" % (len(names), "" if os.path.isdir(override) else " (it does not exist yet; the patch creates it)"))
        manifest = Patcher(game_dir, state_dir)._load()["files"]
        line(True, "files written by this client: %d" % len(manifest))
        foreign = [n for n in names if n.lower().startswith(OUR_PREFIXES + ("a_bet3m4", "a_hatchopen")) and n not in manifest and not n.endswith("_orig.ncs")]
        if foreign:
            line(None, "%d file(s) in Override that look like ours but were not written by this client (older research files; the patch backs them up when it replaces "
                       "them): %s%s" % (len(foreign), ", ".join(foreign[:8]), " ..." if len(foreign) > 8 else ""))
        mods = os.path.join(game_dir, "Modules")
        try:
            with open(os.path.join(state_dir, "modules_manifest.json")) as f:
                patched = len(json.load(f).get("files", {}))
        except (OSError, ValueError, AttributeError):
            patched = 0
        if not os.path.isdir(mods):
            line(False, "the game's Modules folder was not found in %s" % game_dir)
        else:
            line(None, "module files edited by this client: %d" % patched)
    line(os.path.isdir(state_dir), "client state / job folder: %s" % state_dir)
    for name in ("inbox.txt", "outbox.txt"):
        line(None, "%s: %s" % (name, "present" if os.path.exists(os.path.join(state_dir, name)) else "not there (the game creates the outbox when it first runs)" if name.startswith("o") else
                               "not there (written when the first job is sent)"))
    try:
        with open(config_path, encoding="ascii", errors="replace") as f:
            config = f.read()
        line(True, "extender config: %s (%d of %d bytes)" % (config_path, len(config.encode("ascii", "replace")), CONFIG_LIMIT))
        line(True if CONFIG_BEGIN in config else None, "seed block in config.txt: %s" % ("present" if CONFIG_BEGIN in config else "not written yet (connect to a seed)"))
        enabled = any(l.strip().replace(" ", "") == "disp_enable=1" for l in Patcher._without_block(config).splitlines())
        line(enabled, "disp_enable=1 in config.txt%s" % ("" if enabled else ": missing, so the game will not start the delivery loop (the installer must set it)"))
    except OSError:
        line(False, "extender config: %s does not exist (the extender creates it; without disp_enable=1 nothing is delivered)" % config_path)
    if not os.path.isdir(payload_dir):
        line(False, "payload (compiled scripts and area files): %s does not exist. Run /k2_prepare (or tools/build_payload.py): without it the game has none of our scripts." % payload_dir)
    else:
        have = {n.lower() for n in os.listdir(payload_dir) if os.path.isfile(os.path.join(payload_dir, n))}
        count = sum(1 for n in have if n.endswith((".ncs", ".are")))
        missing = [n for n in PAYLOAD_KEY_FILES if n not in have]
        line(not missing and count > 0, "payload: %d script and area files in %s%s" % (count, payload_dir, "" if not missing else "; missing key files: " + ", ".join(missing) +
                                                                                       ". Run /k2_prepare."))
        stray = sorted(n for n in have if not n.endswith((".ncs", ".are")))
        if stray:
            line(False, "payload folder holds files that are not scripts or area files and would be copied into Override: %s" % ", ".join(stray[:6]))
    line(None, "the game is %srunning" % ("" if running() else "not "))
    return lines
