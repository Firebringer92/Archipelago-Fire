r"""
Capability check: no file of ours may gain a power without a person approving it.

The code in the download is largely written with AI help, so what it is allowed to DO is limited and written down. scripts/capabilities.json lists, for each kind of power, the
files that may use it and why. This check reads every Python file (as a syntax tree, nothing is run) and fails when

  * a file uses a power it is not listed for (a new subprocess call, a new socket, a new way to delete files, a dynamic import),
  * a file uses something that is never allowed (eval, exec, pickle, marshal, ctypes, the registry, shell=True), or
  * the manifest lists a file or power the code no longer uses (a permission nobody needs is removed, so the list stays tight).

The powers are grouped as: process (start another program), network (open or accept a connection), delete (remove files or folders) and dynamic_import (import code by name at run
time). A call counts however it is written: `subprocess.run`, `from subprocess import run`, and `import subprocess as sp` followed by `sp.run`. It is a safeguard against accidents
and unreviewed growth, not a proof of safety: it cannot see a power reached by an unusual route (for example getattr on a module).

  check_capabilities.py --root KotoR                 the repository folder (CI uses this)
  check_capabilities.py --zip PlayerBundle.zip       the files in a release zip (Archipelago's own core files are not ours and are skipped)
  check_capabilities.py --root KotoR --list          print what every file uses, to start or update the manifest
"""
import argparse
import ast
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MANIFEST = os.path.join(HERE, "capabilities.json")

# By the power they give: modules whose import is itself the power, calls (written as dotted names after aliases are resolved), and methods that count on any object.
POWERS = {
    "process": {
        "imports": {"pty"},
        "calls": {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
                  "subprocess.getstatusoutput", "os.system", "os.popen", "os.startfile", "os.spawnl", "os.spawnle", "os.spawnlp", "os.spawnlpe", "os.spawnv",
                  "os.spawnve", "os.spawnvp", "os.spawnvpe", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell", "multiprocessing.Process",
                  "multiprocessing.Pool"},
    },
    "network": {
        "imports": {"socket", "ssl", "socketserver", "http.client", "http.server", "urllib.request", "urllib3", "requests", "websockets", "aiohttp", "xmlrpc.client",
                    "webbrowser", "ftplib", "smtplib", "telnetlib"},
        "calls": {"asyncio.open_connection", "asyncio.start_server"},
        "attributes": {"create_connection", "create_server"},        # loop.create_connection(...), on any object
    },
    "delete": {
        "calls": {"os.remove", "os.unlink", "os.rmdir", "os.removedirs", "shutil.rmtree"},
        "attributes": {"unlink", "rmdir", "rmtree", "removedirs"},   # Path(...).unlink() and the like, on any object
    },
    "dynamic_import": {
        "imports": {"importlib", "runpy"},
        "calls": {"__import__"},
    },
}
# Reading a package's own data files is not a power.
HARMLESS_IMPORTS = {"importlib.resources", "importlib.metadata"}
# Never allowed, in any file (no manifest entry can allow them).
FORBIDDEN_IMPORTS = {"pickle", "cPickle", "marshal", "shelve", "ctypes", "cffi", "winreg", "_winreg", "code", "codeop"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "os.execv", "os.execl", "os.execve", "os.execvp", "os.execlp"}

# A path as the zip names it. The repository and the development folder keep the same files under longer names.
STRIP_PREFIXES = ("KotoR/", "Source/", "kotor_ap/", "Archipelago/")
SKIP_DIRS = {"__pycache__", ".git", "test", "tests", "backups", "node_modules", ".pytest_cache", "third_party", "work", "dist"}
# Archipelago's own files, at the zip root and in its package folders: not ours, and not ours to list.
AP_CORE_FILES = {"CommonClient.py", "NetUtils.py", "Utils.py", "settings.py", "ModuleUpdate.py", "kvui.py", "BaseClasses.py", "Fill.py", "Options.py", "entrance_rando.py",
                 "MultiServer.py", "Launcher.py"}
AP_CORE_DIRS = ("rule_builder/", "data/", "worlds/")
OUR_WORLD = "worlds/kotor/"


def normalize(path):
    p = path.replace("\\", "/")
    changed = True
    while changed:
        changed = False
        for prefix in STRIP_PREFIXES:
            if p.startswith(prefix):
                p = p[len(prefix):]
                changed = True
    return p


def is_ours(norm):
    if norm in AP_CORE_FILES:
        return False
    if norm.startswith(AP_CORE_DIRS) and not norm.startswith(OUR_WORLD):
        return False
    return True


def _named(name, wanted):
    """True when `name` is one of `wanted` or a module inside one of them (multiprocessing.pool counts as multiprocessing)."""
    return any(name == w or name.startswith(w + ".") for w in wanted)


def uses_of(source):
    """{(kind, name): [line, ...]} for every power and forbidden thing the source touches. kind is a power, or 'forbidden'."""
    tree = ast.parse(source)
    found = {}

    def add(kind, name, line):
        found.setdefault((kind, name), []).append(line)

    # what each name in the file stands for: `import subprocess as sp` makes sp mean subprocess, `from os import remove as rm` makes rm mean os.remove
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"

    def dotted(expr):
        if isinstance(expr, ast.Name):
            return aliases.get(expr.id, expr.id)
        if isinstance(expr, ast.Attribute):
            base = dotted(expr.value)
            return f"{base}.{expr.attr}" if base else None
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif node.module and not node.level:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                if node.module == "importlib" and all(a.name in ("resources", "metadata") for a in node.names):
                    names = []                                               # from importlib import resources
            else:
                names = []
            for name in names:
                if _named(name, HARMLESS_IMPORTS):
                    continue
                if _named(name, FORBIDDEN_IMPORTS) or name in FORBIDDEN_CALLS:
                    add("forbidden", name, node.lineno)                      # import pickle / from os import execv
                for power, spec in POWERS.items():
                    if _named(name, spec.get("imports", ())):
                        add(power, name, node.lineno)                        # import socket
        elif isinstance(node, ast.Call):
            name = dotted(node.func)
            if name in FORBIDDEN_CALLS:
                add("forbidden", name, node.lineno)
            for kw in node.keywords:
                if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                    add("forbidden", "shell=True", node.lineno)             # a command line built as one string is how an argument becomes a command
            for power, spec in POWERS.items():
                if name in spec.get("calls", ()):
                    add(power, name, node.lineno)
                if isinstance(node.func, ast.Attribute) and node.func.attr in spec.get("attributes", ()):
                    add(power, node.func.attr, node.lineno)
    return found


def collect_tree(root):
    out = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                full = os.path.join(folder, name)
                norm = normalize(os.path.relpath(full, root))
                if is_ours(norm):
                    out[norm] = full
    return out


def tree_sources(root):
    """{normalized path: source} for our Python files under a repository or development folder."""
    sources = {}
    for n, p in collect_tree(root).items():
        with open(p, encoding="utf-8", errors="replace") as f:
            sources[n] = f.read()
    return sources


def zip_sources(path):
    """{normalized path: source} for our Python files in a release zip."""
    sources = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            n = normalize(info.filename)
            if n.endswith(".py") and is_ours(n) and not any(part in SKIP_DIRS for part in n.split("/")[:-1]):
                sources[n] = zf.read(info).decode("utf-8", "replace")
    return sources


def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {power: data.get("allowed", {}).get(power, {}) for power in POWERS}


def check(sources, manifest, tree_mode):
    """sources: {normalized path: source text}. Returns (problems, uses) where uses is {path: {(kind, name): [lines]}}."""
    problems, uses = [], {}
    used_powers = {p: set() for p in POWERS}
    for path, text in sorted(sources.items()):
        try:
            found = uses_of(text)
        except SyntaxError as e:
            problems.append(f"{path}: cannot be parsed ({e.msg}, line {e.lineno})")
            continue
        uses[path] = found
        for (kind, name), lines in sorted(found.items()):
            where = f"{path}:{lines[0]}"
            if kind == "forbidden":
                problems.append(f"{where}: uses {name}, which is never allowed in this project's code")
            else:
                used_powers[kind].add(path)
                if path not in manifest.get(kind, {}):
                    problems.append(f"{where}: new power [{kind}] via {name}. Review it, then add \"{path}\" under allowed.{kind} in capabilities.json with the reason")
    if tree_mode:
        for power, files in manifest.items():
            for path in sorted(files):
                if path not in sources:
                    problems.append(f"capabilities.json lists {path} under {power}, but there is no such file in this tree. Remove the entry")
                elif path not in used_powers[power]:
                    problems.append(f"capabilities.json lists {path} under {power}, but the file no longer uses it. Remove the entry")
    return problems, uses


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", help="repository folder to check (for example KotoR)")
    ap.add_argument("--zip", nargs="*", help="release zip(s) to check")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--list", action="store_true", help="print what every file uses instead of checking")
    args = ap.parse_args()
    if not args.root and not args.zip:
        ap.error("give --root or --zip")
    manifest = load_manifest(args.manifest)
    failed = False

    targets = []
    if args.root:
        targets.append((f"repository folder {args.root}", tree_sources(args.root), True))
    for z in args.zip or []:
        targets.append((f"zip {os.path.basename(z)}", zip_sources(z), False))

    for label, sources, tree_mode in targets:
        problems, uses = check(sources, manifest, tree_mode)
        if args.list:
            print(f"== {label}: {len(sources)} Python files")
            for power in list(POWERS) + ["forbidden"]:
                rows = [(p, sorted({n for (k, n) in u if k == power})) for p, u in sorted(uses.items()) if any(k == power for (k, _n) in u)]
                print(f"  [{power}] {len(rows)} file(s)")
                for p, names in rows:
                    print(f"      {p}: {', '.join(names)}")
            continue
        if problems:
            failed = True
            print(f"capabilities: {len(problems)} problem(s) in {label}")
            for line in problems:
                print("  " + line)
        else:
            counts = {p: sum(1 for f in uses.values() if any(k == p for (k, _n) in f)) for p in POWERS}
            print(f"capabilities: {len(sources)} files in {label}: OK ({', '.join(f'{c} {p}' for p, c in counts.items())})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
