"""Builds the player bundle: the zip a player extracts to play (the client, the tools that build the game files on their machine, the extension, the licences).
The Archipelago world is a separate download (tools/package_world.py).

  python tools/package_bundle.py                        a release build: dist/KotorTwoAP-PlayerBundle-v<version>.zip
  python tools/package_bundle.py --dev                  a trial build: dist/dev/...-DEV.zip; it accepts a version.dll that is not yet recorded in provenance.json
  python tools/package_bundle.py --core DIR             also carry an Archipelago core (its files go to core/), with the world, so the client needs no other install
  python tools/package_bundle.py --dll PATH --version X.Y.Z --out FILE --no-smoke

What goes in is decided by what the code needs, not by a list that has to be kept up by hand (the KotOR 1 bundle lost files that way twice):
  * every client module except tests and the fake game;
  * the tools reachable from tools/build_payload.py through imports and file names (collect_tools), the compiler (tools/nwnsc) with its licence and credits;
  * the data tables and scripts those files name (collect_data, collect_scripts); a table that stays local (stage_publish.RESEARCH_ONLY) makes the build stop;
  * version.dll, the notices and the user documents.
What never goes in: compiled scripts, the payload folder, anything from the game's own files (nwscript.nss and the generated class tables are built on the player's machine).

Before the zip is kept it must pass the same checks as the GitHub repository: tools/check_provenance.py (a program is listed with its SHA-256), tools/check_capabilities.py,
a compile of every Python file, no path of the maintainer's machine, and a start of the client's modules from the extracted bundle. The zip is reproducible: the same inputs give
the same bytes (sorted names, fixed timestamps), so a third party can rebuild it and compare.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import typing
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_capabilities  # noqa: E402
import check_provenance  # noqa: E402
import stage_publish  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, ".."))
# Versioning rule (the same as KotOR 1): WORLD_VERSION in package_world.py moves only for a change that needs a new Archipelago world. A fix on the client or game side moves only this number.
BUNDLE_VERSION = "0.1.0"
ENTRY_TOOLS = ("build_payload.py",)                       # what the client runs on the player's machine (KotorTwoClient._cmd_k2_prepare); everything else is found from here
CLIENT_NOT_SHIPPED = {"fake_game.py"}                     # plus every test_*.py
USER_DOCS = ("README.md", "SECURITY.md", "PROVENANCE.md")
DLL_ARCNAME = "extender/version.dll"
# the installer (installer/ in the project): the three batch files go to the bundle's top folder, the Python script it runs to installer/
INSTALLER_ROOT_FILES = ("Install.bat", "Uninstall.bat", "Start_KOTOR2_Client.bat")
INSTALLER_SCRIPT = "install_bundle.py"
NWNSC_FILES = ("nwnsc.exe", "LICENSE.txt", "CREDITS.txt")
# MDLOps 1.0.0 (GPL) builds the droid models on the player's machine (tools/build_droid_models.py). It ships unchanged: the program, its Perl source, licence, readme and tutorials.
MDLOPS_FILES = ("mdlops.exe", "mdlops.pl", "MDLOpsM.pm", "GPL.txt", "readme_MDLOps_1-0.txt", "KotOR_Tutorial.txt", "Quick_tutorial.txt", "replacer_tutorial.txt", "changelog.txt", "icon.bmp")
DEFAULT_DLL = os.path.join(ROOT, "build_k2ap", "Release", "version.dll")
# the files of an Archipelago install the client imports (the same list the KotOR 1 bundle carries); folders are copied whole
CORE_FILES = ["CommonClient.py", "NetUtils.py", "Utils.py", "settings.py", "ModuleUpdate.py", "kvui.py", "BaseClasses.py", "Fill.py", "Options.py", "entrance_rando.py",
              "MultiServer.py", "Launcher.py", "LICENSE", "worlds/__init__.py", "worlds/AutoWorld.py", "worlds/LauncherComponents.py", "worlds/Files.py",
              "data/client.kv", "data/launcher.kv", "data/options.yaml", "data/GLOBAL.apignore"]
CORE_TREES = ["rule_builder", "worlds/generic"]
# ModuleUpdate reads requirements.txt next to the core's files; only the packages the client's window and connection need (the same list the KotOR 1 bundle keeps).
# pykotor, numpy and pillow, which our own code needs, are installed by the installer, not asked for here.
REQUIREMENT_NAMES = {"colorama", "websockets", "pyyaml", "jellyfish", "jinja2", "schema", "kivy", "bsdiff4", "platformdirs", "certifi", "typing_extensions", "pathspec", "kivymd"}
SKIP_PARTS = {"__pycache__", "logs", "test", "tests"}
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
PERSONAL_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_. -]+[\\/]", re.IGNORECASE)


class BundleError(Exception):
    pass


# ---- what is needed -----------------------------------------------------------------------------------------------------------------------
def _parse(path: str) -> ast.AST:
    with open(path, encoding="utf-8") as f:
        try:
            return ast.parse(f.read(), path)
        except SyntaxError as e:
            raise BundleError("%s does not compile (%s, line %s)" % (path.replace(os.sep, "/"), e.msg, e.lineno))


def _names_in(path: str) -> typing.Tuple[typing.Set[str], typing.Set[str]]:
    """(imported module names, every string constant) of a Python file."""
    imports: typing.Set[str] = set()
    strings: typing.Set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
    return imports, strings


def client_files(root: str) -> typing.List[str]:
    folder = os.path.join(root, "client")
    return sorted(n for n in os.listdir(folder) if n.endswith(".py") and not n.startswith("test_") and n not in CLIENT_NOT_SHIPPED and os.path.isfile(os.path.join(folder, n)))


def collect_tools(root: str, entries: typing.Iterable[str] = ENTRY_TOOLS) -> typing.List[str]:
    """Names of the tools/*.py the player machine needs: the entry tools, every tool a client module imports or names as a string, and, repeatedly, every tool that a collected tool does."""
    tools = os.path.join(root, "tools")
    have = {n for n in os.listdir(tools) if n.endswith(".py")}
    wanted: typing.Set[str] = set()
    todo = [os.path.join(tools, e) for e in entries]
    for name in client_files(root):                           # a client module that imports a tool (inside a function too) needs it on the player's machine
        imports, strings = _names_in(os.path.join(root, "client", name))
        todo.extend(os.path.join(tools, ref) for ref in sorted({i + ".py" for i in imports} | strings) if ref in have)
    while todo:
        path = todo.pop()
        name = os.path.basename(path)
        if name in wanted:
            continue
        wanted.add(name)
        imports, strings = _names_in(path)
        for ref in {i + ".py" for i in imports} | strings:
            if ref in have and ref not in wanted:
                todo.append(os.path.join(tools, ref))
    return sorted(wanted)


def collect_data(root: str, python_files: typing.Iterable[str]) -> typing.List[str]:
    """Names of the data/ tables that the shipped Python files name. A table that stays local is an error: shipped code would break on the player's machine."""
    data = os.path.join(root, "data")
    have = {n for n in os.listdir(data) if os.path.isfile(os.path.join(data, n))}
    wanted: typing.Set[str] = set()
    for path in python_files:
        wanted.update(s for s in _names_in(path)[1] if s in have)
    local_only = sorted(wanted & stage_publish.RESEARCH_ONLY.get("data", set()))
    if local_only:
        raise BundleError("shipped code names data tables that stay on the maintainer's machine: %s. Either move what it needs into a shipped table or stop shipping the code that reads it." % ", ".join(local_only))
    return sorted(wanted)


def collect_scripts(root: str) -> typing.List[str]:
    """The NWScript sources: all of nss/ except the game's own nwscript, the tables generated from the game, and the research scripts (the same rule as the repository)."""
    folder = os.path.join(root, "nss")
    skip = stage_publish.SKIP_NAMES | stage_publish.RESEARCH_ONLY.get("nss", set())
    return sorted(n for n in os.listdir(folder) if n.endswith(".nss") and n not in skip)


def collect_core(core: str, world_dir: str) -> typing.Dict[str, str]:
    """{arcname: source path} for an Archipelago core folder, plus the K2 world, under core/. The world's tests and caches are left out."""
    files: typing.Dict[str, str] = {}
    for rel in CORE_FILES:
        full = os.path.join(core, *rel.split("/"))
        if not os.path.isfile(full):
            raise BundleError("the Archipelago core folder %s has no %s" % (core, rel))
        files["core/" + rel] = full
    for rel in CORE_TREES:
        base = os.path.join(core, *rel.split("/"))
        if not os.path.isdir(base):
            raise BundleError("the Archipelago core folder %s has no %s folder" % (core, rel))
        files.update(_walk("core/" + rel, base, lambda n: n.endswith((".pyc", ".pyo", ".png"))))
    files.update(_walk("core/worlds/kotor2", world_dir, lambda n: n.endswith((".pyc", ".pyo"))))
    files["core/requirements.txt"] = slim_requirements(core)
    return files


def slim_requirements(core: str) -> bytes:
    path = os.path.join(core, "requirements.txt")
    if not os.path.isfile(path):
        raise BundleError("the Archipelago core folder %s has no requirements.txt" % core)
    keep = []
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            m = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
            if m and m.group(1).lower() in REQUIREMENT_NAMES and not line.lstrip().startswith("#"):
                keep.append(line.rstrip())
    return ("\n".join(keep) + "\n").encode("utf-8")


def _walk(arc_root: str, base: str, skip_file: typing.Callable[[str], bool]) -> typing.Dict[str, str]:
    out: typing.Dict[str, str] = {}
    for folder, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS]
        for n in names:
            if not skip_file(n):
                full = os.path.join(folder, n)
                out[arc_root + "/" + os.path.relpath(full, base).replace(os.sep, "/")] = full
    return out


# ---- the notices ----------------------------------------------------------------------------------------------------------------------------
def notices(root: str, core: typing.Optional[str], mdlops: typing.Optional[str] = None) -> str:
    rule = "=" * 80
    parts = ["THIRD-PARTY NOTICES\n\nThis download contains software from other projects, under their own licences. The notices are below.\n"
             "Libraries that the installer downloads with pip (kivy, kivymd, websockets, PyYAML, pykotor and the others) are not part of this download and keep their own licences.\n"]
    with open(os.path.join(root, "tools", "nwnsc", "LICENSE.txt"), encoding="utf-8") as f:
        nwnsc_licence = f.read().replace("\r", "").rstrip()
    parts.append("\n%s\nnwnsc 1.1.5 - tools/nwnsc (the NWScript compiler, https://github.com/nwneetools/nwnsc; run as a separate program)\n%s\n"
                 "Copyright (C) 2008-2014 Ken Johnson (Skywing); _NscLib: Copyright (c) 2002-2003 Edward T. Smith and (c) 2003 The Open Knights Consortium.\n"
                 "Its licence follows (also tools/nwnsc/LICENSE.txt).\n\n%s\n" % (rule, rule, nwnsc_licence))
    with open(os.path.join(mdlops or os.path.join(root, "tools", "mdlops"), "GPL.txt"), encoding="utf-8", errors="replace") as f:
        gpl = f.read().replace("\r", "").rstrip()
    parts.append("\n%s\nMDLOps 1.0.0 - tools/mdlops (a model tool, https://deadlystream.com/files/file/779-mdlops/; run as a separate program, shipped unchanged)\n%s\n"
                 "Written by Chuck Chargin Jr., with animation support by JdNoa, version 1.0 by ndix UR and many other contributors (submitted to Deadly Stream by Fair Strides).\n"
                 "It is licensed under the GNU General Public License. Its Perl source (mdlops.pl, MDLOpsM.pm), readme and tutorials are in tools/mdlops next to the program.\n"
                 "The licence follows (also tools/mdlops/GPL.txt).\n\n%s\n" % (rule, rule, gpl))
    parts.append("\n%s\nK2SE - extender/version.dll\n%s\n"
                 "The game-side extension is forked from K2SE, https://github.com/renanaugustomacena-ux/K2SE (renanaugustomacena-ux), which states in its README that it is MIT licensed.\n"
                 "The repository has no LICENSE file and names no copyright holder; the maintainer decided on 2026-11-08 to publish it with this credit (see README.md, Credits).\n"
                 "Part of the extension's address table comes from Kotor-Patch-Manager, https://github.com/LaneDibello/Kotor-Patch-Manager (LaneDibello, MIT), and the 32-slot companion\n"
                 "roster follows the design of its PartyRosterLimit32K2 mod by Vriff (our own implementation).\n" % (rule, rule))
    if core:
        licence = os.path.join(core, "LICENSE")
        if os.path.isfile(licence):
            with open(licence, encoding="utf-8-sig") as f:
                parts.append("\n%s\nArchipelago (the files under core/ come from the Archipelago source)\n%s\n%s\n" % (rule, rule, f.read().replace("\r", "").rstrip()))
    return "".join(parts)


# ---- the build -------------------------------------------------------------------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gather(root: str, dll: str, core: typing.Optional[str] = None, mdlops: typing.Optional[str] = None) -> typing.Dict[str, typing.Union[str, bytes]]:
    """{arcname: path or bytes} of everything in the bundle (without the manifest, which lists these)."""
    files: typing.Dict[str, typing.Union[str, bytes]] = {}
    for n in client_files(root):
        files["client/" + n] = os.path.join(root, "client", n)
    python = [os.path.join(root, "client", n) for n in client_files(root)]
    tools = collect_tools(root)
    for n in tools:
        files["tools/" + n] = os.path.join(root, "tools", n)
        python.append(os.path.join(root, "tools", n))
    for n in NWNSC_FILES:
        path = os.path.join(root, "tools", "nwnsc", n)
        if not os.path.isfile(path):
            raise BundleError("tools/nwnsc/%s is missing (the compiler is downloaded unchanged from the nwnsc release page; see PROVENANCE.md)" % n)
        files["tools/nwnsc/" + n] = path
    mdlops = mdlops or os.path.join(root, "tools", "mdlops")
    for n in MDLOPS_FILES:
        path = os.path.join(mdlops, n)
        if not os.path.isfile(path):
            raise BundleError("%s is missing (MDLOps 1.0.0 from https://deadlystream.com/files/file/779-mdlops/ goes unchanged into tools/mdlops, or pass --mdlops DIR; see PROVENANCE.md)" % path)
        files["tools/mdlops/" + n] = path
    for n in collect_data(root, python):
        files["data/" + n] = os.path.join(root, "data", n)
    for n in collect_scripts(root):
        files["nss/" + n] = os.path.join(root, "nss", n)
    if not os.path.isfile(dll):
        raise BundleError("version.dll was not found at %s. Build the extender first (cmake, Release, Win32) or pass --dll." % dll)
    files[DLL_ARCNAME] = dll
    for n in INSTALLER_ROOT_FILES + (INSTALLER_SCRIPT,):
        path = os.path.join(root, "installer", n)
        if not os.path.isfile(path):
            raise BundleError("installer/%s is missing" % n)
        files[("installer/" + n) if n == INSTALLER_SCRIPT else n] = path
        if n == INSTALLER_SCRIPT:
            python.append(path)
    for n in USER_DOCS:
        path = os.path.join(root, "docs", n)
        if not os.path.isfile(path):
            raise BundleError("docs/%s is missing" % n)
        files[n] = path
    if core:
        files.update(collect_core(core, os.path.join(root, "worlds", "kotor2")))
    files["THIRD_PARTY_NOTICES.txt"] = notices(root, core, mdlops).encode("utf-8")
    return files


def _read(src: typing.Union[str, bytes]) -> bytes:
    if isinstance(src, bytes):
        return src
    with open(src, "rb") as f:
        return f.read()


def write_zip(path: str, files: typing.Dict[str, typing.Union[str, bytes]], manifest: dict) -> None:
    """Writes the zip with sorted names and fixed timestamps; BUNDLE_MANIFEST.json (what is in it, with every SHA-256) goes in last."""
    listing = []
    blobs: typing.Dict[str, bytes] = {}
    for arc in sorted(files):
        data = _read(files[arc])
        blobs[arc] = data
        listing.append({"path": arc, "size": len(data), "sha256": _sha256(data)})
    blobs["BUNDLE_MANIFEST.json"] = (json.dumps(dict(manifest, files=listing), indent=1, sort_keys=True) + "\n").encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arc in sorted(blobs):
            info = zipfile.ZipInfo(arc, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, blobs[arc])


def dll_entry(sha: str) -> dict:
    return {"zip_path": DLL_ARCNAME, "sha256": sha, "origin": "built from Source/extender/src with CMake (Win32, Release); forked from K2SE (see README.md, Credits)",
            "licence_zip_path": "THIRD_PARTY_NOTICES.txt", "notice_must_mention": ["K2SE"]}


def checks(zip_path: str, manifest_path: str, dev: bool, sha: str) -> typing.List[str]:
    """Every check a release has to pass, on the finished zip. Returns the problems (empty when it is fine)."""
    problems: typing.List[str] = []
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    listed = any(b.get("zip_path") == DLL_ARCNAME and b.get("sha256", "").lower() == sha for b in manifest["binaries"])
    if not listed:
        entry = json.dumps(dll_entry(sha), indent=2)
        if dev:
            manifest["binaries"] = [b for b in manifest["binaries"] if b.get("zip_path") != DLL_ARCNAME] + [dll_entry(sha)]
        else:
            problems.append("version.dll (SHA-256 %s) is not recorded in provenance.json. After you have read what changed, add this entry under \"binaries\" (and put the hash in the "
                            "patch notes), or build with --dev for a trial:\n%s" % (sha, entry))
    with tempfile.TemporaryDirectory() as tmp:
        used = os.path.join(tmp, "provenance.json")
        with open(used, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        found, _count = check_provenance.check_zip(zip_path, check_provenance.Rules(used))
        skip_dll = not listed and not dev                       # already explained above, with the entry to add
        problems += ["provenance: " + p for p in found if not (skip_dll and "version.dll" in p)]
    caps, _uses = check_capabilities.check(check_capabilities.zip_sources(zip_path), check_capabilities.load_manifest(os.path.join(HERE, "capabilities.json")), False)
    problems += ["capabilities: " + p for p in caps]
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            data = z.read(name) if name.endswith((".py", ".nss", ".md", ".txt", ".json")) else b""
            text = data.decode("utf-8", "replace")
            if name.endswith(".py"):
                try:
                    ast.parse(data, name)
                except SyntaxError as e:
                    problems.append("%s: does not compile (%s, line %s)" % (name, e.msg, e.lineno))
            if not name.startswith("core/") and (name.endswith((".py", ".nss", ".json")) or name == "THIRD_PARTY_NOTICES.txt"):
                for m in PERSONAL_PATH.finditer(text):
                    problems.append("%s: has a path of the maintainer's machine (%s...)" % (name, m.group(0)[:40]))
                    break
            if name.endswith((".ncs", ".pyc")) or name.startswith("client/payload/"):
                problems.append("%s: build output must not ship" % name)
    return problems


SMOKE = r"""
import importlib, os, sys
bundle, core = sys.argv[1], sys.argv[2]
sys.path[:0] = [os.path.join(bundle, "client"), os.path.join(bundle, "tools"), core]
failed = []
for name in sorted(n[:-3] for n in os.listdir(os.path.join(bundle, "client")) if n.endswith(".py")):
    try:
        importlib.import_module(name)
    except Exception as e:
        failed.append("client/%s.py: %s: %s" % (name, type(e).__name__, e))
for name in sorted(n[:-3] for n in os.listdir(os.path.join(bundle, "tools")) if n.endswith(".py")):
    try:
        importlib.import_module(name)
    except Exception as e:
        failed.append("tools/%s.py: %s: %s" % (name, type(e).__name__, e))
print("\n".join(failed))
sys.exit(1 if failed else 0)
"""


def smoke(zip_path: str, core: typing.Optional[str]) -> typing.List[str]:
    """Extracts the bundle into a scratch folder and imports every client and tool module from there with only the bundle (and the Archipelago core) on the path: a module or a file the bundle forgot shows up here."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        use_core = os.path.join(tmp, "core") if os.path.isdir(os.path.join(tmp, "core")) else core
        if not use_core or not os.path.isfile(os.path.join(use_core, "CommonClient.py")):
            return ["smoke test skipped: no Archipelago core to import the client against (give --core, or run tools/run_world_tests.py once to prepare ap_core)"]
        run = subprocess.run([sys.executable, "-I", "-c", SMOKE, tmp, use_core], capture_output=True, text=True, timeout=300, cwd=tmp)
        return ["smoke test: " + line for line in run.stdout.splitlines() if line.strip()] if run.returncode else []


def build(root: str = ROOT, out: typing.Optional[str] = None, version: str = BUNDLE_VERSION, dll: typing.Optional[str] = None, core: typing.Optional[str] = None,
          dev: bool = False, run_smoke: bool = True, manifest_path: typing.Optional[str] = None, smoke_core: typing.Optional[str] = None,
          mdlops: typing.Optional[str] = None) -> typing.Tuple[typing.Optional[str], typing.List[str]]:
    """Builds and checks the bundle. Returns (path of the kept zip or None, problems). Nothing is left at `out` unless every check passed."""
    manifest_path = manifest_path or os.path.join(HERE, "provenance.json")
    dll = dll or DEFAULT_DLL
    try:
        files = gather(root, dll, core, mdlops)
    except BundleError as e:
        return None, [str(e)]
    with open(dll, "rb") as f:
        sha = _sha256(f.read())
    name = "KotorTwoAP-PlayerBundle-v%s%s.zip" % (version, "-DEV" if dev else "")
    out = out or os.path.join(root, "dist", "dev" if dev else "", name)
    with tempfile.TemporaryDirectory() as tmp:
        built = os.path.join(tmp, name)
        write_zip(built, files, {"bundle": "KotorTwoAP", "version": version, "dev": dev, "version_dll_sha256": sha, "core_included": bool(core),
                                 "build_tools": "package_bundle.py"})
        problems = checks(built, manifest_path, dev, sha)
        if run_smoke:
            problems += smoke(built, smoke_core or core)
        blocking = [p for p in problems if not p.startswith("smoke test skipped")]
        if not blocking:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copyfile(built, out)
            return out, problems
    return None, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", default=BUNDLE_VERSION)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dll", default=None, help="the built version.dll (default: build_k2ap/Release/version.dll)")
    ap.add_argument("--core", default=None, help="an Archipelago source folder to carry as core/ (ask which version the players run; do not take this machine's)")
    ap.add_argument("--dev", action="store_true", help="a trial build: accepts a version.dll that is not recorded in provenance.json yet and is named -DEV")
    ap.add_argument("--mdlops", default=None, help="the folder that holds MDLOps 1.0.0 unchanged (default: tools/mdlops)")
    ap.add_argument("--no-smoke", action="store_true", help="skip the start of the modules from the extracted bundle")
    a = ap.parse_args()
    smoke_core = os.path.join(ROOT, "ap_core") if os.path.isdir(os.path.join(ROOT, "ap_core")) else None
    path, problems = build(out=a.out, version=a.version, dll=a.dll, core=a.core, dev=a.dev, run_smoke=not a.no_smoke, smoke_core=smoke_core, mdlops=a.mdlops)
    for p in problems:
        print(("NOTE  " if p.startswith("smoke test skipped") else "FAIL  ") + p)
    if path is None:
        print("The bundle was NOT written.")
        return 1
    with zipfile.ZipFile(path) as z:
        n = len(z.namelist())
    print("%s%s: %d files, %.1f MB" % ("DEV BUILD, not for release: " if a.dev else "", path, n, os.path.getsize(path) / 1e6))
    print("sha256 " + _sha256(open(path, "rb").read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
