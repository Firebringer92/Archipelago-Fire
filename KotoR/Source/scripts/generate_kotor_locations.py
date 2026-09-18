"""
Generates Archipelago/worlds/kotor/Locations.py from the real, verified
journal completion data (questtagmapping.json -- built by merging
scan_journal_values.py's NCS-bytecode results with
scan_journal_dlg_values.py's dialogue-node results -- global.jrl's own
documented entries were confirmed unreliable and are NOT the source here.
Both scan scripts themselves were later removed as one-off tools, since
their output is what this file actually reads), PLUS the alignment/level/
goal locations below (fixed data, not scanned from anything -- see
ALIGNMENT_THRESHOLDS/ALIGNMENT_BONUS_KEYS/LEVEL_RANGE/MALAK_LOCATION_NAME).

Re-run this any time the underlying journal-value scan data changes,
rather than hand-editing Locations.py -- hand-transcription from a partial
printed sample is exactly how the first draft of this file ended up with
several wrong target values.

IMPORTANT: this file must write the ENTIRE Locations.py from scratch,
every location type included -- an earlier version of this script only
knew about journal/companion/area, and re-running it after an unrelated
fix (a hardcoded-path update) SILENTLY WIPED the 33 alignment/level/goal
locations that had been added some other way, breaking every generation
with a 4-location fill shortfall (the 4
GOAL_EVENT_LOCATIONS in __init__.py -- Malak Defeated, Level 20 Reached,
and the two alignment extremes -- losing their locked-Event-item targets).
Reconstructed from first principles by cross-referencing every place that
depends on these locations by exact name/type: kotor_location_tracker.py's
LocationTracker.__init__ (the location_type strings and the
alignment_value/alignment_bonus/level_value fields it expects to exist on
LocationData), and __init__.py's GOAL_EVENT_LOCATIONS dict (the 4 exact
display names that MUST match byte-for-byte or the locked-item placement
silently fails to find them). If you ever need to change what this script
emits, grep both of those files first -- they're the real source of truth
for what names/fields downstream code depends on, not just this file.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCATIONS_JSON = os.path.join(REPO_ROOT, "questtagmapping.json")
AREAS_JSON = os.path.join(REPO_ROOT, "areatodisplaymap.json")
OUT_PATH = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "Locations.py")
# Override with --worlds-dir=<path> to target a different worlds/kotor
# checkout (e.g. a trimmed source export with no full Archipelago/ folder
# alongside it) instead of editing OUT_PATH by hand.
BASE_ID = 9210000

# The 10 real alignment threshold checks (50 itself doesn't count -- it's
# the neutral starting point, not a crossing) -- must exactly match
# kotor_location_tracker.py's ALIGNMENT_THRESHOLDS list, and each display
# name must byte-for-byte match __init__.py's GOAL_EVENT_LOCATIONS for the
# two extremes (0 and 100) or the locked-item goal placement silently
# fails to find them.
ALIGNMENT_THRESHOLDS = [0, 10, 20, 30, 40, 60, 70, 80, 90, 100]


def _alignment_display(value):
    if value == 0:
        return "Alignment: Dark Side 0"
    if value == 100:
        return "Alignment: Light Side 100"
    return f"Alignment: {'Dark' if value < 50 else 'Light'} Side {value}"


# 3 bonus alignment checks -- key must match kotor_location_tracker.py's
# _add_bonus() call keys exactly ("true_neutral"/"fallen_jedi"/
# "redeemed_sith").
ALIGNMENT_BONUS = [
    ("true_neutral", "Alignment: True Neutral"),
    ("fallen_jedi", "Alignment: Fallen Jedi"),
    ("redeemed_sith", "Alignment: Redeemed Sith"),
]

# Character levels 2-20 (1 is the starting value, not an accomplishment) --
# "Level 20 Reached" must byte-for-byte match __init__.py's
# GOAL_EVENT_LOCATIONS for the same reason as the alignment extremes above.
LEVEL_RANGE = range(2, 21)

# Must byte-for-byte match __init__.py's GOAL_EVENT_LOCATIONS key for the
# Malak entry.
MALAK_LOCATION_NAME = "Malak Defeated"

# Companion personal-subplot locations -- each "Ebon Hawk: ..."
# entry below is real vanilla content gated on a SPECIFIC companion being
# an active party member when it triggers (5 confirmed directly via a
# game-wide NCS disassembly scan for IsNPCPartyMember/IsAvailableCreature
# calls co-occurring with a journal advance; the plain "Ebon Hawk:
# <Companion>" generic-banter entries included defensively -- same category
# of risk even unconfirmed, since some companion-talk scripts live in the
# game's core chitin.key BIFs rather than any module .rim this scan
# covered). Single source of truth for two consumers: Rules.py's
# companion_mode=ap_gated self-referential access-rule guard (a
# companion's own item can't be circularly placed at their own gated
# check), and __init__.py's _active_locations() companion_mode=none
# filter (these are location_type="journal", not "companion", so they
# weren't caught by that filter's original "companion" type check even
# though companions never joining at all makes them just as permanently
# uncompletable as the 9 real "Companion Recruited: ..." locations are).
# Keyed by location name -> the AP item name for the companion it needs.
# NOT emitted as its own location_table entries -- these names must
# already exist as real journal locations from LOCATIONS_JSON above; this
# is purely a curated cross-reference of which of those need the guard.
COMPANION_SUBPLOT_LOCATIONS = {
    "Ebon Hawk: Bastila": "Companion: Bastila Shan",
    "Ebon Hawk: Bastila's Mother": "Companion: Bastila Shan",
    "Ebon Hawk: Canderous": "Companion: Canderous Ordo",
    "Ebon Hawk: Jagi's Challenge": "Companion: Canderous Ordo",
    "Ebon Hawk: Carth": "Companion: Carth Onasi",
    "Ebon Hawk: HK-47": "Companion: HK-47",
    "Ebon Hawk: Jolee Bindo": "Companion: Jolee Bindo",
    "Ebon Hawk: Juhani": "Companion: Juhani",
    "Ebon Hawk: Threat from Xor": "Companion: Juhani",
    "Ebon Hawk: Mission's Brother": "Companion: Mission Vao",
}

# Additional Enemies bounty cards: one location per bounty
# card the player can be carrying, count-based exactly like LEVEL_RANGE
# above (Plot=1 quest items can't be sold/dropped/destroyed, so the count
# in inventory only ever goes up -- same monotonic-counter shape as
# character level, just from a different source). 40 cards total, matching
# the 40 modules Additional Enemies places into (one bounty-carrying
# enemy per module) -- see scripts/patch_additional_enemies.py. Only
# active when additional_enemies isn't off (see __init__.py's
# _active_locations()); generated unconditionally here same as every
# other location type, filtering happens at the world level not here.
BOUNTY_CARD_COUNT = 40

# NPC_* index -> display name, matching nwscript.nss's NPC_BASTILA=0 etc.
COMPANIONS = [
    (0, "Bastila Shan"), (1, "Canderous Ordo"), (2, "Carth Onasi"),
    (3, "HK-47"), (4, "Jolee Bindo"), (5, "Juhani"),
    (6, "Mission Vao"), (7, "T3-M4"), (8, "Zaalbar"),
]

# Planet/category prefix -> readable region label, purely for a nicer
# display name prefix; doesn't affect detection (that's journal_tag/
# journal_target, both taken verbatim from the real scan data).
PREFIX_LABELS = [
    ("Geno_", "Genoharadan"), ("Genoharadan", "Genoharadan"),
    ("dan_", "Dantooine"), ("Dan", "Dantooine"),
    ("end_", "Endar Spire"),
    ("ebo", "Ebon Hawk"), ("k_ebonhawk", "Ebon Hawk"), ("k_swg_", "Ebon Hawk"),
    ("k_pebo_", "Ebon Hawk"), ("k_missbroth", "Ebon Hawk"), ("k_pazaak", "Ebon Hawk"),
    ("k_rapidtransit", "Ebon Hawk"), ("k_jagi", "Ebon Hawk"), ("k_xor", "Ebon Hawk"),
    ("kas", "Kashyyyk"),
    ("kor", "Korriban"),
    ("k_starforge", "Star Forge"),
    ("lev_", "Leviathan"),
    ("man", "Manaan"), ("Man26", "Manaan"),
    ("sta_", "Sith Base"),
    ("tar_", "Taris"), ("Tar_", "Taris"),
    ("tat", "Tatooine"), ("Tat", "Tatooine"),
    ("unk_", "Unknown World"),
    ("main_premium", "General"),
    ("Category000", "General"),
]


def region_for(tag):
    for prefix, label in PREFIX_LABELS:
        if tag.startswith(prefix):
            return label
    return "General"


def var_name(tag):
    return re.sub(r"[^a-zA-Z0-9_]", "_", tag)


def main():
    global OUT_PATH
    for a in sys.argv[1:]:
        if a.startswith("--worlds-dir="):
            OUT_PATH = os.path.join(a.split("=", 1)[1], "Locations.py")

    with open(LOCATIONS_JSON) as f:
        journal_locations = json.load(f)
    journal_locations.sort(key=lambda x: (region_for(x["tag"]), x["tag"]))

    with open(AREAS_JSON) as f:
        areas = json.load(f)
    areas.sort(key=lambda a: a["idx"])

    lines = []
    lines.append("import typing")
    lines.append("")
    lines.append("from BaseClasses import Location")
    lines.append("")
    lines.append("")
    lines.append("class LocationData(typing.NamedTuple):")
    lines.append("    id: int")
    lines.append('    region: str = "Adventure"')
    lines.append('    location_type: str = "journal"  # "journal", "companion", "area", "alignment",')
    lines.append('    # "alignment_bonus", "level", "malak_defeated", or "bounty" -- see')
    lines.append("    # kotor_location_tracker.py's LocationTracker.__init__ for how each is")
    lines.append("    # consumed; every field below is read directly from there, this is not")
    lines.append("    # a schema this file invented independently.")
    lines.append("    # journal: the journal tag (KOTOR's own quest identifier, e.g.")
    lines.append("    # \"dan_romance\") and the stage value that means \"complete\" -- the")
    lines.append("    # highest real value found for that tag across every script/dialogue")
    lines.append("    # that actually sets it (see scripts/scan_journal_values.py and")
    lines.append("    # scan_journal_dlg_values.py; global.jrl's own documented entries")
    lines.append("    # turned out to be unreliable and are NOT what these are built from).")
    lines.append('    journal_tag: str = ""')
    lines.append("    journal_target: int = 0")
    lines.append("    # companion: NPC_* index (nwscript.nss), fires the first time")
    lines.append("    # CHECK|COMPANION|<idx> is seen (IsAvailableCreature true) -- the")
    lines.append("    # client tracks 'seen companions' itself, same pattern as area visits.")
    lines.append("    companion_idx: int = -1")
    lines.append("    # area: covered-area index (extender/area_trampolines/_mapping.json),")
    lines.append("    # fires the first time CHECK|AREA|<idx> is seen for that index -- an")
    lines.append("    # exploration check, client-tracked the same way as companions.")
    lines.append("    area_idx: int = -1")
    lines.append("    # alignment: one of the 10 real threshold crossings (0-100, excluding 50).")
    lines.append("    alignment_value: int = -1")
    lines.append("    # alignment_bonus: one of the 3 history-based bonus checks (\"true_neutral\"/")
    lines.append("    # \"fallen_jedi\"/\"redeemed_sith\").")
    lines.append('    alignment_bonus: str = ""')
    lines.append("    # level: character level 2-20 (1 is the starting value, not tracked).")
    lines.append("    level_value: int = -1")
    lines.append("    # bounty: how many Additional Enemies bounty cards the player must be")
    lines.append("    # carrying (1-40) -- a plain count threshold, same shape as level_value,")
    lines.append("    # just driven by inventory count instead of character level.")
    lines.append("    bounty_value: int = -1")
    lines.append("")
    lines.append("")
    lines.append("class KotorLocation(Location):")
    lines.append('    game: str = "KotOR"')
    lines.append("")
    lines.append("")
    lines.append("# AUTO-GENERATED by scripts/generate_kotor_locations.py -- do not hand-edit,")
    lines.append("# re-run the generator instead (see its docstring for why, and for a real")
    lines.append("# incident where a version of this script that DIDN'T cover every location")
    lines.append("# type below silently wiped 33 of them on a re-run).")
    lines.append("#")
    lines.append("# Eight location types, all detected the same way client-side (the game")
    lines.append("# reports raw state every poll via CHECK|.../ALIGNMENT/LEVELREPORT/INVENTORY")
    lines.append("# events; the client tracks what's already been converted into a check and")
    lines.append("# fires on first occurrence -- see kotor_location_tracker.py):")
    lines.append("#   - journal: 100 real quest-completion checks spanning every planet")
    lines.append("#   - companion: 9 checks, one per companion, firing when they'd first")
    lines.append("#     become available (recruitment point reached)")
    lines.append("#   - area: 78 checks, one per covered area, firing on first visit")
    lines.append("#   - alignment: 10 real threshold crossings (0-100, excluding 50)")
    lines.append("#   - alignment_bonus: 3 history-based checks (true_neutral/fallen_jedi/")
    lines.append("#     redeemed_sith)")
    lines.append("#   - level: character levels 2-20 (1 is the starting value)")
    lines.append("#   - malak_defeated: one-shot, Malak's defeat")
    lines.append("#   - bounty: 40 checks, one per Additional Enemies bounty card carried")
    lines.append("#     (only active when additional_enemies isn't off)")
    lines.append(f"base_id = {BASE_ID}")
    lines.append("")
    lines.append("location_table: typing.Dict[str, LocationData] = {")

    idx_counter = 0
    for loc in journal_locations:
        region = region_for(loc["tag"])
        name = loc["display_name"]
        if name.startswith(region + ":") or name == region:
            display = name
        else:
            display = f"{region}: {name}"
        display = display.replace('"', '\\"')
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="{region}", '
            f'location_type="journal", journal_tag="{loc["tag"]}", journal_target={loc["target_value"]}),'
        )
        idx_counter += 1

    for npc_idx, name in COMPANIONS:
        display = f"Companion Recruited: {name}"
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Companions", '
            f'location_type="companion", companion_idx={npc_idx}),'
        )
        idx_counter += 1

    seen_area_names = {}
    for area in areas:
        seen_area_names[area["display_name"]] = seen_area_names.get(area["display_name"], 0) + 1
    for area in areas:
        base_display = f"Visited: {area['display_name']}"
        if seen_area_names[area["display_name"]] > 1:
            # disambiguate duplicates (some display names are legitimately
            # reused across distinct covered areas/modules) with the
            # underlying module name, so location names stay unique
            display = f"{base_display} ({area['base']})"
        else:
            display = base_display
        display = display.replace('"', '\\"')
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Exploration", '
            f'location_type="area", area_idx={area["idx"]}),'
        )
        idx_counter += 1

    for value in ALIGNMENT_THRESHOLDS:
        display = _alignment_display(value)
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Character", '
            f'location_type="alignment", alignment_value={value}),'
        )
        idx_counter += 1

    for key, display in ALIGNMENT_BONUS:
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Character", '
            f'location_type="alignment_bonus", alignment_bonus="{key}"),'
        )
        idx_counter += 1

    for level in LEVEL_RANGE:
        display = f"Level {level} Reached"
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Character", '
            f'location_type="level", level_value={level}),'
        )
        idx_counter += 1

    lines.append(
        f'    "{MALAK_LOCATION_NAME}": LocationData(base_id + {idx_counter}, region="Character", '
        f'location_type="malak_defeated"),'
    )
    idx_counter += 1

    for n in range(1, BOUNTY_CARD_COUNT + 1):
        display = f"Bounty Card #{n}"
        lines.append(
            f'    "{display}": LocationData(base_id + {idx_counter}, region="Additional Enemies", '
            f'location_type="bounty", bounty_value={n}),'
        )
        idx_counter += 1

    lines.append("}")
    lines.append("")
    lines.append("location_name_to_id: typing.Dict[str, int] = {name: data.id for name, data in location_table.items()}")
    lines.append("lookup_id_to_name: typing.Dict[int, str] = {data.id: name for name, data in location_table.items()}")

    # Fail loudly, not silently, if a curated cross-reference above ever
    # names a location that doesn't actually exist in what was just
    # generated -- exactly the class of drift this whole file's own
    # docstring warns about (a real location set silently disappearing on
    # a re-run went unnoticed for a while last time).
    generated_names = set()
    for loc in journal_locations:
        region = region_for(loc["tag"])
        name = loc["display_name"]
        generated_names.add(name if (name.startswith(region + ":") or name == region) else f"{region}: {name}")
    missing = sorted(set(COMPANION_SUBPLOT_LOCATIONS) - generated_names)
    if missing:
        sys.exit(f"COMPANION_SUBPLOT_LOCATIONS names not found among generated journal locations "
                 f"(typo, or the underlying journal data changed): {missing}")

    lines.append("")
    lines.append("# Companion personal-subplot locations -- each \"Ebon Hawk: ...\"")
    lines.append("# entry below is real vanilla content gated on a SPECIFIC companion being")
    lines.append("# an active party member when it triggers (5 confirmed directly via a")
    lines.append("# game-wide NCS disassembly scan for IsNPCPartyMember/IsAvailableCreature")
    lines.append("# calls co-occurring with a journal advance; the plain \"Ebon Hawk:")
    lines.append("# <Companion>\" generic-banter entries included defensively -- same category")
    lines.append("# of risk even unconfirmed, since some companion-talk scripts live in the")
    lines.append("# game's core chitin.key BIFs rather than any module .rim this scan")
    lines.append("# covered). Single source of truth for two consumers: Rules.py's")
    lines.append("# companion_mode=ap_gated self-referential access-rule guard (a")
    lines.append("# companion's own item can't be circularly placed at their own gated")
    lines.append("# check), and __init__.py's _active_locations() companion_mode=none")
    lines.append("# filter (these are location_type=\"journal\", not \"companion\", so they")
    lines.append("# weren't caught by that filter's original \"companion\" type check even")
    lines.append("# though companions never joining at all makes them just as permanently")
    lines.append("# uncompletable as the 9 real \"Companion Recruited: ...\" locations are).")
    lines.append("# Keyed by location name -> the AP item name for the companion it needs.")
    lines.append("COMPANION_SUBPLOT_LOCATIONS: typing.Dict[str, str] = {")
    for name, item_name in COMPANION_SUBPLOT_LOCATIONS.items():
        lines.append(f'    "{name}": "{item_name}",')
    lines.append("}")

    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT_PATH} ({idx_counter} locations: {len(journal_locations)} journal, {len(COMPANIONS)} companion, "
          f"{len(areas)} area, {len(ALIGNMENT_THRESHOLDS)} alignment, {len(ALIGNMENT_BONUS)} alignment_bonus, "
          f"{len(list(LEVEL_RANGE))} level, 1 malak_defeated, {BOUNTY_CARD_COUNT} bounty)")


if __name__ == "__main__":
    main()
