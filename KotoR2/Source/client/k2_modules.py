"""Editing the game's module files, the way the KotOR 1 patchers do: the module's .rim is changed in place after a backup, and put back on revert.

Used by the features that must change what a module holds (the Bazaar's tokens in containers; later the shops, the loot, the doors and the enemies). The rules:
  * the first time a module file is changed its original is copied to the backup folder; an existing backup is never overwritten, so it is always the game's own file;
  * every edit goes through edit_gff, which changes one resource of the module (usually the GIT) and writes the file back; the file's hash is kept in the manifest;
  * restore_all puts the backups back, but only for a file that still is what we wrote (a game update or another mod that changed it since is left alone and reported);
  * the client restores everything first and then applies the new seed's edits, so a module is never edited twice and a seed never inherits another seed's edits.
"""
import hashlib
import json
import os
import shutil
import typing

MANIFEST = "modules_manifest.json"


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ModuleStore:
    def __init__(self, modules_dir: str, state_dir: str):
        self.modules_dir = modules_dir
        self.backup_dir = os.path.join(state_dir, "module_backups")
        self.manifest_path = os.path.join(state_dir, MANIFEST)
        self._manifest = self._load()

    # ---- manifest ----------------------------------------------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self.manifest_path) as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("modules_dir", "").lower() == self.modules_dir.lower():
                return data
        except (OSError, ValueError):
            pass
        return {"modules_dir": self.modules_dir, "files": {}}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._manifest, f, indent=1, sort_keys=True)
        os.replace(tmp, self.manifest_path)

    # ---- files -------------------------------------------------------------------------------------------------------
    @staticmethod
    def _extension(suffix: str) -> str:
        return ".erf" if suffix == "_dlg" else ".rim"            # a module's conversations are in <module>_dlg.erf; everything else in the .rim files

    def path(self, module: str, suffix: str = "") -> str:
        return os.path.join(self.modules_dir, "%s%s%s" % (module, suffix, self._extension(suffix)))

    @staticmethod
    def _read(path: str):
        from pykotor.resource.formats.erf import read_erf
        from pykotor.resource.formats.rim import read_rim
        return read_erf(path) if path.lower().endswith(".erf") else read_rim(path)

    @staticmethod
    def _write(container, path: str) -> None:
        from pykotor.resource.formats.erf import write_erf
        from pykotor.resource.formats.rim import write_rim
        from pykotor.resource.type import ResourceType
        if path.lower().replace(".k2ap_tmp", "").endswith(".erf"):
            if container.description_strref < 0:
                container.description_strref &= 0xFFFFFFFF          # the game's archives hold 0xCDCDCDCD here, which the reader returns as a negative number
            write_erf(container, path, ResourceType.ERF)
        else:
            write_rim(container, path)

    def exists(self, module: str, suffix: str = "") -> bool:
        return os.path.isfile(self.path(module, suffix))

    def resources(self, module: str, suffix: str = "") -> typing.Dict[typing.Tuple[str, str], bytes]:
        """{(resref lower case, type extension): bytes} of a module file."""
        out = {}
        for res in self._read(self.path(module, suffix)):
            out[(str(res.resref).lower(), res.restype.extension)] = res.data
        return out

    def edit_gff(self, module: str, resref: typing.Optional[str], extension: str, change: typing.Callable[[typing.Any], bool], suffix: str = "") -> bool:
        """Applies change(gff root) to one resource of a module file; when it returns True the file is written back (after the one-time backup)."""
        from pykotor.resource.formats.gff import bytes_gff, read_gff
        from pykotor.resource.type import ResourceType
        path = self.path(module, suffix)
        rim = self._read(path)
        restype = ResourceType.from_extension(extension)
        found = next((r for r in rim if r.restype == restype and (not resref or str(r.resref).lower() == resref.lower())), None)      # no resref: the first of the type
        if found is None:
            return False
        gff = read_gff(found.data)
        if not change(gff.root):
            return False
        rim.set_data(str(found.resref), restype, bytes_gff(gff))
        self._backup(path)
        tmp = path + ".k2ap_tmp"
        self._write(rim, tmp)
        os.replace(tmp, path)
        self._manifest["files"][os.path.basename(path)] = {"patched_sha": _sha(path)}
        self._save()
        return True

    def modules(self, suffix: str = "") -> typing.List[str]:
        """The module names that have a file with this suffix ("" for the main file, "_s" for the second one), upper case, sorted."""
        out = []
        for name in os.listdir(self.modules_dir):
            low = name.lower()
            ext = self._extension(suffix)
            if not low.endswith(suffix.lower() + ext):
                continue
            base = name[:len(name) - len(suffix) - len(ext)]
            if suffix == "" and base.lower().endswith("_s"):
                continue                                          # a main-file listing must not take the second files
            out.append(base)
        return sorted(out, key=str.lower)

    def edit_resources(self, module: str, extensions: typing.Sequence[str], change: typing.Callable[[str, str, typing.Any], bool], suffix: str = "") -> int:
        """Applies change(resref, extension, gff root) to every resource of the given types in a module file and writes the file back once if any returned True
        (after the one-time backup). Returns how many resources were changed."""
        from pykotor.resource.formats.gff import bytes_gff, read_gff
        path = self.path(module, suffix)
        rim = self._read(path)
        wanted = {e.lower() for e in extensions}
        changed = 0
        for res in list(rim):
            ext = res.restype.extension
            if ext not in wanted:
                continue
            gff = read_gff(res.data)
            if change(str(res.resref).lower(), ext, gff.root):
                rim.set_data(str(res.resref), res.restype, bytes_gff(gff))
                changed += 1
        if not changed:
            return 0
        self._backup(path)
        tmp = path + ".k2ap_tmp"
        self._write(rim, tmp)
        os.replace(tmp, path)
        self._manifest["files"][os.path.basename(path)] = {"patched_sha": _sha(path)}
        self._save()
        return changed

    def _backup(self, path: str) -> None:
        os.makedirs(self.backup_dir, exist_ok=True)
        target = os.path.join(self.backup_dir, os.path.basename(path))
        if not os.path.exists(target):
            shutil.copy2(path, target)

    def restore_all(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        """(restored file names, files left alone because they are no longer what we wrote)."""
        restored, skipped = [], []
        for name, info in sorted(self._manifest["files"].items()):
            current = os.path.join(self.modules_dir, name)
            backup = os.path.join(self.backup_dir, name)
            if not os.path.isfile(backup):
                skipped.append(name)
                continue
            if os.path.isfile(current) and _sha(current) != info.get("patched_sha"):
                skipped.append(name)                    # something else changed it since (a game update or another mod): ours is no longer the file, so its
                os.remove(backup)                       # backup is stale too; keeping it would put an old copy back over the newer file later
                continue
            shutil.copy2(backup, current)
            os.remove(backup)
            restored.append(name)
        self._manifest["files"] = {}
        self._save()
        return restored, skipped
