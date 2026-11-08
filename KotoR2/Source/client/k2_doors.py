"""The area randomizer's game side: doors and walk-through exits are re-linked by rewriting the destination fields in each module's GIT.

The world sends door_plan.links: for every pooled door (or trigger) the module it is in, which list and index of the GIT it is, the module it now leads to and the
waypoint where the player arrives there. The client edits the GIT of each module in place (client/k2_modules.py: backup first, put back on revert) and unlocks the doors
it re-links: a door keeps the lock it had in its old place (a key, a quest flag), which may now be the only way into an area. Scripts that lock a door while the game runs
are not touched, so a few may still re-lock; the release note says so.
"""
import typing

LISTS = {"Door List": "door", "TriggerList": "trigger"}


def apply_links(root, links: typing.Sequence[dict], doors_seen: typing.List[str], problems: typing.List[str], module: str, done: typing.List[str]) -> bool:
    from pykotor.common.misc import ResRef
    changed = False
    for link in links:
        name = link["list"]
        if name not in LISTS or not root.exists(name):
            problems.append("the area randomizer: %s has no %s, door %s keeps its link" % (module, name, link["door"]))
            continue
        entries = root.get_list(name)
        index = int(link["index"])
        if index >= len(entries):
            problems.append("the area randomizer: %s has fewer than %d entries in %s, door %s keeps its link" % (module, index + 1, name, link["door"]))
            continue
        entry = entries[index]
        if not entry.exists("LinkedToModule") or not str(entry.get_resref("LinkedToModule")):
            problems.append("the area randomizer: %s entry %s:%d is not a transition, it keeps its link" % (module, name, index))
            continue
        entry.set_resref("LinkedToModule", ResRef(link["to_module"].lower()))
        entry.set_string("LinkedTo", link["to_waypoint"])
        if link["kind"] == "door" and entry.exists("TemplateResRef"):
            doors_seen.append(str(entry.get_resref("TemplateResRef")).lower())
        done.append(link["door"])
        changed = True
    return changed


def unlock(root) -> bool:
    changed = False
    for field in ("Locked", "KeyRequired"):
        if root.exists(field) and root.get_uint8(field):
            root.set_uint8(field, 0)
            changed = True
    return changed


def door_files(store, plan: dict) -> typing.Tuple[int, typing.List[str]]:
    """Re-links the doors of the plan and unlocks the re-linked doors' templates. Returns (links written, problems)."""
    problems: typing.List[str] = []
    links = (plan or {}).get("links") or []
    if not links:
        return 0, problems
    by_module: typing.Dict[str, typing.List[dict]] = {}
    for link in links:
        by_module.setdefault(link["module"], []).append(link)
    written = 0
    for module, mine in sorted(by_module.items()):
        if not store.exists(module):
            problems.append("the area randomizer: module %s was not found, its doors keep their links" % module)
            continue
        templates: typing.List[str] = []
        done: typing.List[str] = []
        try:
            if store.edit_gff(module, None, "git", lambda root, mine=mine, module=module: apply_links(root, mine, templates, problems, module, done)):
                written += len(done)
            if templates and store.exists(module, "_s"):
                wanted = set(templates)
                store.edit_resources(module, ("utd",), lambda resref, ext, root: resref in wanted and unlock(root), "_s")
        except Exception as e:
            problems.append("the area randomizer: %s could not be changed (%s), its doors keep their links" % (module, e))
    return written, problems
