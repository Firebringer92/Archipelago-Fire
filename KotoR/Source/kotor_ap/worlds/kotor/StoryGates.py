"""
Access rules and progression item placement for the story-gate Progression System (DEVELOPMENT_HISTORY.md section 17).

The game side (scripts/patch_story_gates.py) holds specific story beats until the player owns enough progression items
of one family. This module tells Archipelago the same thing, as pure state predicates ("holds at least N
progression items of family F"), so the generator only places an item where the player can really get to it.

Gates are story beats, never areas or travel, so the rules below describe which CHECKS wait for which
beat. A check not listed in GATE_EXTRAS only inherits its planet's baseline.

Soundness: over-requiring progression items for a check can only make a seed more conservative; leaving a check
free that the game actually gates can strand a progression item behind itself. When a check's exact beat is
uncertain it is listed with the higher requirement.
"""
import typing

from .Items import STORY_TOKEN_FAMILIES, STORY_TOKEN_NAMES, STORY_TOKENS_PER_FAMILY

# Requirement = tuple of (family key, progression items needed). Baselines accumulate down the story:
# leaving Taris needs the Taris gate 3; the open-world planets open once the Dantooine council has
# sent the player on; the Leviathan needs all four star maps; the Unknown World follows the Leviathan.
_TAR = ("tar", 3)
_DAN = ("dan", 3)
_STAR_MAPS = (("tat", 3), ("kas", 3), ("man", 3), ("kor", 3))

_PLANET_BASELINE: typing.Dict[str, typing.Tuple[typing.Tuple[str, int], ...]] = {
    "Endar Spire": (),
    "Taris": (),
    "Dantooine": (_TAR,),
    "Ebon Hawk": (_TAR,),
    "General": (_TAR, _DAN),
    "Kashyyyk": (_TAR, _DAN),
    "Korriban": (_TAR, _DAN),
    "Manaan": (_TAR, _DAN),
    "Tatooine": (_TAR, _DAN),
    "Leviathan": (_TAR, _DAN) + _STAR_MAPS,
    "Unknown World": (_TAR, _DAN) + _STAR_MAPS,
    "Star Forge": (_TAR, _DAN) + _STAR_MAPS + (("unk", 3),),
    "Final": (_TAR, _DAN) + _STAR_MAPS + (("unk", 3), ("fin", 3)),
}

OPEN_WORLD = ("Tatooine", "Kashyyyk", "Manaan", "Korriban")
# Planets a progression item can never be placed on: the player cannot return to them, so a skipped check there would
# strand the progression item. Taris and the Endar Spire are only open to the Taris family (see token_forbidden_families).
ONE_WAY_PLANETS = ("Leviathan", "Unknown World", "Star Forge", "Final")

# Where each planet's check physically sits when the check's own region is a catch-all.
_COMPANION_PLANET = {
    "Companion Recruited: Bastila Shan": "Taris",
    "Companion Recruited: Canderous Ordo": "Taris",
    "Companion Recruited: Carth Onasi": "Endar Spire",
    "Companion Recruited: HK-47": "Tatooine",
    "Companion Recruited: New Companion": "Tatooine",
    "Companion Recruited: Jolee Bindo": "Kashyyyk",
    "Companion Recruited: Juhani": "Dantooine",
    "Companion Recruited: Mission Vao": "Taris",
    "Companion Recruited: T3-M4": "Taris",
    "Companion Recruited: Zaalbar": "Taris",
}
_GENOHARADAN_PLANET = {
    "Genoharadan: Ithorak": "Manaan",
    "Genoharadan: Rulan": "Kashyyyk",
    "Genoharadan: Vorn": "Tatooine",
    "Genoharadan: Lorgal": "Korriban",
    "Genoharadan: Zuulan": "Dantooine",
}
_GENOHARADAN_FINALE = "Genoharadan"
_EXPLORATION_PLANETS = ("Endar Spire", "Taris", "Dantooine", "Kashyyyk", "Korriban", "Manaan", "Tatooine",
                        "Unknown World", "Star Forge", "Leviathan")

# Checks that sit behind a specific beat on top of their planet's baseline. Each entry is read from the beat
# maps in DEVELOPMENT_HISTORY.md section 17. Steps are the gate numbers: Taris 1 engine rooms / 2 Canderous / 3 leave;
# Dantooine 1 Dorak / 2 Juhani / 3 council; each open-world planet 1 / 2 / 3 in story order, 3 being the star
# map; Unknown World 1 guide / 2 summit scene / 3 computer; Star Forge 3 = the Malak fight.
GATE_EXTRAS: typing.Dict[str, typing.Tuple[typing.Tuple[str, int], ...]] = {
    # Taris
    "Taris: The Search for Bastila": (("tar", 1),),
    "Taris: Inside the Vulkar Base": (("tar", 1),),
    "Taris: Invited to a Party": (("tar", 3),),
    "Taris: Purchasing a Droid": (("tar", 2),),
    "Taris: Planetary Information": (("tar", 3),),
    "Companion Recruited: T3-M4": (("tar", 2),),
    "Taris: Escaping Taris": (("tar", 3),),
    "Companion Recruited: Bastila Shan": (("tar", 1),),
    "Companion Recruited: Canderous Ordo": (("tar", 3),),
    "Visited: Taris - Swoop Platform": (("tar", 1),),
    "Visited: Taris - Davik's Estate": (("tar", 3),),
    # The Sith base door opens only once Canderous has given the objective (tar_escape 20), which is his first meeting.
    "Visited: Taris - Sith Base": (("tar", 2),),
    # Dantooine: the base game keeps you in the council area until your Jedi training (Dorak's class conversation) is done, so everything
    # outside the Enclave sits behind the first Dantooine gate.
    "Visited: Dantooine - Courtyard": (("dan", 1),),
    "Visited: Dantooine - Matale Grounds": (("dan", 1),),
    "Visited: Dantooine - Grove": (("dan", 1),),
    "Visited: Dantooine - Sandral Grounds": (("dan", 1),),
    "Dantooine: Dead Settler": (("dan", 1),),
    "Dantooine: Missing Companion": (("dan", 1),),
    "Dantooine: Murdered Settler": (("dan", 1),),
    "Dantooine: Mandalorian Raiders": (("dan", 1),),
    "Dantooine: Sandral-Matale Feud": (("dan", 3),),
    "Genoharadan: Zuulan": (("dan", 1),),
    "Dantooine: Jedi Trials": (("dan", 2),),
    "Dantooine: The Jedi Council": (("dan", 2),),
    "Dantooine: Investigate Ruins": (("dan", 2),),
    "Visited: Dantooine - Ruins": (("dan", 2),),
    "Companion Recruited: Juhani": (("dan", 3),),
    # Tatooine
    "Tatooine: A Desert Hunt": (("tat", 2),),
    "Tatooine: Star Map: Tatooine": (("tat", 3),),
    # Kashyyyk
    "Companion Recruited: Jolee Bindo": (("kas", 1),),
    "Kashyyyk: Chieftain in Need": (("kas", 3),),
    "Kashyyyk: Star Map: Kashyyyk": (("kas", 2),),
    # Manaan
    "Manaan: Missing Selkath": (("man", 2),),
    "Manaan: Mission for the Republic": (("man", 3),),
    "Manaan: Star Map: Manaan": (("man", 3),),
    # Korriban: the academy, the Valley and the tombs are reached only through Yuthura's acceptance (gate 1) in the base layout
    "General: The Code of the Sith": (("kor", 1),),
    "Korriban: Enter the Sith Academy": (("kor", 1),),
    "Korriban: A Doubting Sith": (("kor", 1),),
    "Korriban: Aiding Lashowe": (("kor", 1),),
    "Korriban: The Double-Cross": (("kor", 1),),
    "Korriban: The Double-Double-Cross": (("kor", 1),),
    "Korriban: Finding Dustil": (("kor", 1),),
    "Korriban: The Mandalorian Weapons Cache": (("kor", 1),),
    "Korriban: Renegade Sith": (("kor", 1),),
    "Korriban: The Sword of Ajunta Pall": (("kor", 1),),
    "Korriban: The Hermit in the Hills": (("kor", 1),),
    "Korriban: Rogue Droid": (("kor", 1),),
    "Visited: Korriban - Sith Academy": (("kor", 1),),
    "Visited: Korriban - Valley of Dark Lords": (("kor", 1),),
    "Visited: Korriban - Shyrack Caves": (("kor", 1),),
    "Visited: Korriban - Tomb of Ajunta Pall": (("kor", 1),),
    "Visited: Korriban - Tomb of Tulak Hord": (("kor", 1),),
    "Visited: Korriban - Tomb of Naga Sadow": (("kor", 1),),
    "Korriban: The Way of the Sith": (("kor", 2),),
    "Korriban: Star Map: Korriban": (("kor", 3),),
    # Unknown World
    "Visited: Unknown World - Temple Main Floor": (("unk", 1),),
    "Visited: Unknown World - Temple Summit": (("unk", 1),),
    "Unknown World: Rakatan Research": (("unk", 1),),
    "Unknown World: Trapped on a Nameless World": (("unk", 2),),
    # The ending
    "Malak Defeated": (("fin", 3),),
    "Visited: Yavin Station": (("fin", 3),),
    # Ebon Hawk quests: several finish on other planets or late in the story, so all of them wait for the same items as the post-Leviathan Hawk.
    "Ebon Hawk: Unfinished Business": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Dwindling Supplies": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: The Ebon Hawk": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Jagi's Challenge": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Mission's Brother": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Pazaak Rules": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: The Trouble With Gizka": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Strange Stowaway": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Bastila": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Canderous": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Carth": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Bastila's Mother": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: HK-47": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Jolee Bindo": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Juhani": (_TAR, _DAN) + _STAR_MAPS,
    "Ebon Hawk: Threat from Xor": (_TAR, _DAN) + _STAR_MAPS,
    # Rapid Transit System is finished by using the map screen's Return button once. It can be done on Taris, but a player may skip it there, and the Enclave
    # blocks the button on arrival with no known release point, so after Taris it is only treated as certain once the whole Dantooine story is done.
    "Ebon Hawk: Rapid Transit System": (("dan", 3),),
    # Hawk module that exists only after the Leviathan (m41 is the Unknown World's number)
    "Visited: Ebon Hawk (ebo_m41aa)": (_TAR, _DAN) + _STAR_MAPS,
}


# The open-world star map checks close each planet's chain and depend on a single placeable or trigger in a late area, so no
# progression item (Progression or companion) may sit on them. Dantooine's ruins check is not listed: it fires on the star pad pickup,
# which needs only two Dantooine items, and the council scene that needs the third comes after it.
STAR_MAP_LOCATIONS = frozenset({
    "Tatooine: Star Map: Tatooine", "Kashyyyk: Star Map: Kashyyyk", "Manaan: Star Map: Manaan", "Korriban: Star Map: Korriban",
})

# Checks whose own region is a catch-all but which belong to a story phase.
_NAME_PLANET = {
    "Malak Defeated": "Final",
    # The Sith code lessons are taught by Uthar and Yuthura inside the academy, and the Premium Merchant's store is the Dreshdae bartender's.
    "General: The Code of the Sith": "Korriban",
    "General: Premium Merchant": "Korriban",
}


def location_planet(name: str, data) -> typing.Optional[str]:
    """Which planet's baseline a check inherits, or None for checks no gate touches (levels, alignment,
    bounties, boss datapads: they only ever hold non-progression items)."""
    region = data.region
    if name in _NAME_PLANET:
        return _NAME_PLANET[name]
    if region == "Exploration":
        label = name[len("Visited: "):] if name.startswith("Visited: ") else name
        if label.startswith("Yavin"):
            return "Final"
        if label.startswith("Ebon Hawk"):
            return "Ebon Hawk"
        for planet in _EXPLORATION_PLANETS:
            if label.startswith(planet):
                return planet
        return None
    if region == "Companions":
        return _COMPANION_PLANET.get(name)
    if region == "Genoharadan":
        return _GENOHARADAN_PLANET.get(name)
    if region == "Sith Base":
        # sta_confront is the Bastila scene at the Star Forge, before the Malak fight.
        return "Star Forge"
    if region in _PLANET_BASELINE:
        return region
    return None


def location_requirements(name: str, data) -> typing.Tuple[typing.Tuple[str, int], ...]:
    """The merged requirement for one check: each family once, at its highest step."""
    if name == _GENOHARADAN_FINALE:
        # The questline's finale branches across all four open-world planets.
        return _merge(_PLANET_BASELINE["Tatooine"] + _STAR_MAPS)
    planet = location_planet(name, data)
    if planet is None:
        return ()
    base = _PLANET_BASELINE.get(planet, ())
    return _merge(base + GATE_EXTRAS.get(name, ()))


def _merge(reqs) -> typing.Tuple[typing.Tuple[str, int], ...]:
    best: typing.Dict[str, int] = {}
    for fam, step in reqs:
        best[fam] = max(best.get(fam, 0), step)
    return tuple(sorted(best.items()))


def token_forbidden_families(name: str, data) -> typing.Set[str]:
    """Families whose progression items must not be placed at this check.

    Progression items never go on a planet the player cannot come back to after leaving (a skipped check would
    strand the progression item). Taris and the Endar Spire are one-way too, but the Taris progression items are needed to
    leave Taris, so only the Taris family may sit there. A planet's own progression items stay off its own planet
    for the four open worlds, so a planet's progression comes from elsewhere."""
    planet = location_planet(name, data)
    if planet is None:
        return set()
    if planet in ONE_WAY_PLANETS:
        return set(STORY_TOKEN_FAMILIES)
    forbidden: typing.Set[str] = set()
    if planet in ("Taris", "Endar Spire"):
        forbidden |= set(STORY_TOKEN_FAMILIES) - {"tar"}
    if planet in OPEN_WORLD:
        forbidden.add({"Tatooine": "tat", "Kashyyyk": "kas", "Manaan": "man", "Korriban": "kor"}[planet])
    return forbidden


def _family_rule(state, player: int, fam: str, need: int) -> bool:
    return state.count_from_list(STORY_TOKEN_NAMES[fam], player) >= min(need, STORY_TOKENS_PER_FAMILY)


def apply_story_gate_rules(world) -> None:
    """Adds the access rules and progression item-placement rules for every active check."""
    from worlds.generic.Rules import add_rule, add_item_rule

    multiworld, player = world.multiworld, world.player
    token_to_family = {n: fam for fam, names in STORY_TOKEN_NAMES.items() for n in names}
    for name, data in world._active_locations().items():
        location = multiworld.get_location(name, player)
        reqs = location_requirements(name, data)
        if reqs:
            add_rule(location, lambda state, reqs=reqs: all(_family_rule(state, player, f, n) for f, n in reqs))
        if name in STAR_MAP_LOCATIONS:
            add_item_rule(location, lambda item: not item.advancement)
        banned = token_forbidden_families(name, data)
        if banned:
            add_item_rule(location, lambda item, banned=banned: token_to_family.get(item.name) not in banned)
