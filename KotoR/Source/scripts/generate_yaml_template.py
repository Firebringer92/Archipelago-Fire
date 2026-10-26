"""
Rebuilds KotoR_TEMPLATE.yaml's option comments from Options.py, so the template cannot drift from what the options really say.

The template keeps its own layout (header, the "Archipelago standard options" section, the section titles and the order of the options); every KotOR
option below those gets its comment from the option's docstring, a "Valid:" line made from the option class, and its default value. An option that
is in Options.py but not yet in the template is added after the option named in NEW_OPTION_AFTER (the key; the value lists what follows it).

Usage:
  python generate_yaml_template.py [--template <path to the existing template>] [--out <path>]
Defaults read and write ..\\..\\..\\Documents\\GitHub\\Archipelago-Fire\\KotoR\\Docs\\KotoR_TEMPLATE.yaml's current location given in DEFAULT_TEMPLATE
(the existing copy is the layout source, and the output goes to --out, or back over it with --in-place).
"""
import argparse
import dataclasses
import inspect
import os
import re
import sys
import textwrap

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "Archipelago"))

DEFAULT_TEMPLATE = r"C:\Users\User\Documents\GitHub\Archipelago-Fire\KotoR\Docs\KotoR_TEMPLATE.yaml"
# options kept exactly as written in the template (Archipelago's own standard options, documented by hand there)
KEEP_AS_WRITTEN = {"progression_balancing", "accessibility"}
# where an option that is new to the template goes
NEW_OPTION_AFTER = {"galactic_shop": ["quest_item_checks", "bazaar"]}
SECTION = re.compile(r"^  # --- .* -+\s*$")
KEY = re.compile(r"^  ([a-z_0-9]+):\s*(.*?)\s*$")


def parse(template: str):
    """(header lines up to and including 'KotOR:', [("section", line) | ("option", name, comment_lines, key_line)])"""
    lines = template.replace("\r", "").split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "KotOR:")
    header, body = lines[:start + 1], lines[start + 1:]
    items, pending = [], []
    for line in body:
        if SECTION.match(line):
            items.append(("section", line))
            pending = []
            continue
        m = KEY.match(line)
        if m and not line.lstrip().startswith("#"):
            comment = [l for l in pending]
            while comment and comment[0].strip() == "":
                comment.pop(0)
            while comment and comment[-1].strip() == "":
                comment.pop()
            items.append(("option", m.group(1), comment, line))
            pending = []
        else:
            pending.append(line)
    return header, items


def default_text(cls) -> str:
    from Options import Choice, Range, Toggle
    d = cls.default
    if issubclass(cls, Toggle):
        return "true" if d else "false"
    if issubclass(cls, Choice):
        return cls.name_lookup[d]
    return str(d)


def valid_line(cls) -> str:
    from Options import Choice, Range, Toggle
    if issubclass(cls, Toggle):
        return "Valid: true, false"
    if issubclass(cls, Choice):
        names = [cls.name_lookup[v] for v in sorted(cls.name_lookup)]
        # the order the options are declared in is clearer than the numeric order for these
        declared = [n[len("option_"):] for n in vars(cls) if n.startswith("option_")]
        return "Valid: " + ", ".join(declared or names)
    if issubclass(cls, Range):
        return f"Valid range: {cls.range_start} to {cls.range_end}"
    return ""


def doc_comment(cls) -> list:
    doc = inspect.cleandoc(cls.__doc__ or "")
    out = []
    for raw in doc.split("\n"):
        out.append(("  # " + raw).rstrip() if raw.strip() else "  #")
    v = valid_line(cls)
    if v:
        out += ["  #", "  # " + v]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--out", default=None)
    ap.add_argument("--in-place", action="store_true")
    args = ap.parse_args()

    from worlds.kotor.Options import KotorOptions
    classes = {f.name: f.type for f in dataclasses.fields(KotorOptions)}
    header, items = parse(open(args.template, encoding="utf-8").read())
    have = {it[1] for it in items if it[0] == "option"}

    new_items = []
    for it in items:
        new_items.append(it)
        if it[0] == "option":
            for name in NEW_OPTION_AFTER.get(it[1], []):
                if name not in have and name in classes:
                    new_items.append(("option", name, None, f"  {name}: {default_text(classes[name])}"))
                    have.add(name)
    out = list(header)
    for it in new_items:
        if it[0] == "section":
            out += ["", it[1], ""]
            continue
        _, name, comment, keyline = it
        cls = classes.get(name)
        if name in KEEP_AS_WRITTEN or cls is None or not inspect.isclass(cls) or cls.__doc__ is None or name == "death_link":
            body = comment or []
            if name == "death_link" and cls is not None:
                body = doc_comment(cls)
        else:
            body = doc_comment(cls)
        value = default_text(cls) if (cls is not None and inspect.isclass(cls) and name not in KEEP_AS_WRITTEN) else keyline.split(":", 1)[1].strip()
        out += [""] + body + [f"  {name}: {value}"]
    text = "\n".join(out).rstrip("\n") + "\n"
    target = args.template if args.in_place else (args.out or os.path.join(REPO_ROOT, "KotoR_TEMPLATE.generated.yaml"))
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    missing = [n for n in classes if n not in have and n not in KEEP_AS_WRITTEN and n not in
               {"local_items", "non_local_items", "start_inventory", "start_hints", "start_location_hints", "exclude_locations", "priority_locations",
                "item_links", "plando_items", "start_inventory_from_pool"}]
    print(f"wrote {target} ({len(out)} lines); options in Options.py but not in the template: {missing}")


if __name__ == "__main__":
    main()
