"""The door shuffle of the area randomizer: pure functions over the data in data/doors.json, no Archipelago objects, so they can be tested alone.

The pool is a set of doors (and walk-through triggers), each in one module, that the game links in coupled pairs: walk through door a and you arrive next to door b, and
back through b you arrive next to a. The shuffle builds new pairs with one guarantee: every pooled module can be reached from the roots (the modules the player reaches
without a door: the planets' landing areas) using only pooled pairs. It does that by construction, not by trying and repairing:
  1. the modules without a root are attached one by one, each to a random module that is already attached and still has a free door, using one free door on each side;
     modules with many doors are attached first so the supply of free doors does not run out; a try that runs out is thrown away and started again;
  2. the doors still free are paired at random, never two in the same module.
Then story requirements: every pooled module has its own requirement (tokens per family, from the area table). The requirement of reaching a module through the new
pairs is the cheapest route's: the largest need per family over the modules on the way. Locations in that module need it as well, so the generator never counts on a
place the player cannot yet walk to.
"""
import random
import typing

Pair = typing.Tuple[str, str]
Req = typing.Dict[str, int]


class ShuffleError(Exception):
    pass


def _attempt(doors: typing.Dict[str, dict], roots: typing.Sequence[str], rng: random.Random) -> typing.List[Pair]:
    by_module: typing.Dict[str, typing.List[str]] = {}
    for key in sorted(doors):
        by_module.setdefault(doors[key]["module"], []).append(key)
    for lst in by_module.values():
        rng.shuffle(lst)
    free = {m: list(lst) for m, lst in by_module.items()}
    attached = [m for m in roots if m in by_module]
    pending = [m for m in sorted(by_module) if m not in attached]
    pending.sort(key=lambda m: -(len(by_module[m]) + rng.random() * 1.5))        # many doors first, with some noise
    pairs: typing.List[Pair] = []
    for m in pending:
        parents = [p for p in attached if free[p]]
        if not parents:
            raise ShuffleError("ran out of free doors")
        weights = [len(free[p]) for p in parents]
        parent = rng.choices(parents, weights)[0]
        pairs.append((free[parent].pop(), free[m].pop()))
        attached.append(m)
    left = [d for m in sorted(free) for d in free[m]]
    for _ in range(60):
        rng.shuffle(left)
        rest = list(left)
        extra: typing.List[Pair] = []
        ok = True
        while rest:
            d = rest.pop()
            options = [e for e in rest if doors[e]["module"] != doors[d]["module"]]
            if not options:
                ok = False
                break
            e = rng.choice(options)
            rest.remove(e)
            extra.append((d, e))
        if ok:
            return pairs + extra
    raise ShuffleError("the doors left over could not be paired across modules")


def reachable(pairs: typing.Iterable[Pair], doors: typing.Dict[str, dict], roots: typing.Iterable[str]) -> typing.Set[str]:
    """The modules reachable from the roots through the pairs."""
    edges: typing.Dict[str, typing.Set[str]] = {}
    for a, b in pairs:
        ma, mb = doors[a]["module"], doors[b]["module"]
        edges.setdefault(ma, set()).add(mb)
        edges.setdefault(mb, set()).add(ma)
    seen = set(roots)
    stack = list(seen)
    while stack:
        for n in edges.get(stack.pop(), ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def shuffle(data: dict, rng: random.Random, tries: int = 300) -> typing.List[Pair]:
    """New coupled pairs for the pool in data (the contents of data/doors.json). Raises ShuffleError when no try gives a connected result."""
    doors = data["doors"]
    roots = data["roots"]
    modules = set(data["modules"])
    last = ""
    for _ in range(tries):
        try:
            pairs = _attempt(doors, roots, rng)
        except ShuffleError as e:
            last = str(e)
            continue
        if reachable(pairs, doors, roots) >= modules and sorted(d for p in pairs for d in p) == sorted(doors):
            return pairs
    raise ShuffleError("no connected door shuffle found in %d tries (%s)" % (tries, last))


def merge(a: Req, b: Req) -> Req:
    out = dict(a)
    for k, v in b.items():
        out[k] = max(out.get(k, 0), v)
    return out


def path_requirements(pairs: typing.Iterable[Pair], data: dict) -> typing.Dict[str, Req]:
    """For every pooled module, the cheapest requirement of walking to it from a root through the pairs, not counting the module's own requirement (its locations
    carry that). A module is entered through the modules before it, so their requirements all count; the cheapest route is the one with the smallest total need."""
    doors = data["doors"]
    own = data["module_requires"]
    edges: typing.Dict[str, typing.Set[str]] = {}
    for a, b in pairs:
        ma, mb = doors[a]["module"], doors[b]["module"]
        edges.setdefault(ma, set()).add(mb)
        edges.setdefault(mb, set()).add(ma)
    best: typing.Dict[str, Req] = {m: {} for m in data["roots"]}
    changed = True
    while changed:
        changed = False
        for m in sorted(best):
            through = merge(best[m], own.get(m, {}))
            for n in sorted(edges.get(m, ())):
                if n in data["roots"]:
                    continue
                if n not in best or sum(through.values()) < sum(best[n].values()):
                    best[n] = through
                    changed = True
    return best
