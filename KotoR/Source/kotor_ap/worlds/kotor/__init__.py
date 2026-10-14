import typing

from BaseClasses import Region
from Options import OptionError
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, components, Type

from . import EntranceRando
from .Items import KotorItem, item_table, item_name_to_id, filler_items, arm_name_to_item, read_gear_json, TRAP_ITEMS, VENDOR_UNLOCK_ITEMS, STORY_TOKEN_NAMES
from .Locations import KotorLocation, location_table, location_name_to_id, COMPANION_SUBPLOT_LOCATIONS
from .Options import (
    Goal, KotorOptions, STARTING_ABILITY_ARMS, STARTING_SKILL_ARMS,
)
from .Rules import set_rules, set_completion_rules

# Registers a "KOTOR Client" button in the Archipelago Launcher, the
# `x2wotc`/`tits_the_3rd`-style pattern confirmed working
# by reading those two real installed
# third-party apworlds' own __init__.py directly. KOTOR's own client is
# NOT bundled into this apworld and run in-process the way theirs are --
# KotorClient.py's whole job is bridging to a SEPARATELY installed
# PlayerBundle folder via _detect_repo_root() walking real directories
# relative to __file__, which breaks the instant it's imported from
# inside a zip (no real folder to walk). So this launches it as a
# subprocess instead, pointed at wherever install_playerbundle.py (see
# scripts/install_playerbundle.py) actually installed it -- recorded in
# the install-path marker that script writes on every install.


def _launch_kotor_client(log, *args: str) -> None:
    import os
    import subprocess
    import sys

    state_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP")
    marker_path = os.path.join(state_dir, "install_path.txt")
    log(f"button clicked; marker {marker_path!r} exists={os.path.isfile(marker_path)}")
    if not os.path.isfile(marker_path):
        print("KOTOR Client: no PlayerBundle install found. Extract the PlayerBundle zip and "
              "double-click Install.bat inside it first (see README.md), then use this button "
              "again.")
        return

    with open(marker_path, encoding="utf-8") as f:
        install_path = f.read().strip()
    # KotorClient.py ships at the Client folder root (see
    # package_playerbundle.py), not a "KotorClient\" subfolder -- this
    # path must match that layout or the button's isfile check below
    # fails silently.
    kotor_client_path = os.path.join(install_path, "KotorClient.py")
    log(f"client path {kotor_client_path!r} exists={os.path.isfile(kotor_client_path)}")
    if not os.path.isfile(kotor_client_path):
        print(f"KOTOR Client: the recorded install path ({install_path!r}) doesn't have "
              f"KotorClient.py any more -- was it moved, renamed, or deleted? "
              f"Re-run Install.bat to fix this.")
        return

    # This button runs INSIDE the compiled
    # Archipelago Launcher .exe, where sys.executable is the frozen
    # Launcher's OWN exe path, not a python interpreter -- using it
    # directly would just relaunch a second, confused Launcher
    # instance instead of KotorClient.py (a real python.exe would run this
    # fine; a frozen app's sys.executable never is one). Use the real
    # interpreter install_playerbundle.py recorded when it ran (always a
    # genuine python.exe, since it's launched via Install.bat's `py -3`/
    # `python`), falling back to sys.executable only if that marker is
    # somehow missing (e.g. an install from before this fix).
    python_marker = os.path.join(state_dir, "python_path.txt")
    python_exe = sys.executable
    if os.path.isfile(python_marker):
        with open(python_marker, encoding="utf-8") as f:
            recorded = f.read().strip()
        if recorded and os.path.isfile(recorded):
            python_exe = recorded
        else:
            print(f"KOTOR Client: recorded python interpreter ({recorded!r}) not found -- "
                  f"falling back to {python_exe!r}, which may not work if this is a frozen app. "
                  f"Re-run Install.bat to fix this.")
    else:
        print(f"KOTOR Client: no recorded python interpreter -- falling back to {python_exe!r}, "
              f"which may not work if this is a frozen app. Re-run Install.bat to fix this.")

    # Even with the right interpreter, a raw
    # `Popen([python_exe, ...])` window closes the instant the process
    # exits -- if KotorClient.py crashes on startup (e.g. GUI mode's Kivy
    # dependency missing/broken), the window flashes and closes before
    # anyone can read why. Routed through `cmd /K` instead, which leaves
    # the console open after the command finishes so any error is
    # actually readable; the user closes it manually when done. Also
    # falls back to --nogui (below) when Kivy can't be imported, unless
    # the caller already specified --gui/--nogui.
    log(f"python interpreter {python_exe!r}")
    args_list = list(args)
    if "--nogui" not in args_list and "--gui" not in args_list:
        # GUI mode (the normal connect window) when this interpreter can
        # import Kivy/KivyMD, the same dependency every other Archipelago
        # client needs; otherwise the console client, so a broken or
        # missing Kivy can't crash the launch.
        try:
            kivy_ok = subprocess.run(
                [python_exe, "-c", "import kivy, kivymd"],
                capture_output=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).returncode == 0
        except (OSError, subprocess.SubprocessError) as e:
            log(f"kivy probe failed to run: {e!r}")
            kivy_ok = False
        log(f"kivy importable={kivy_ok}")
        if not kivy_ok:
            args_list.append("--nogui")
    # Launched from the compiled Launcher.exe (a windowed app
    # with no console of its own), a bare `cmd /K` Popen has nowhere to
    # actually attach an interactive console -- the process starts but
    # --nogui's "enter your slot name" stdin prompt is unreachable, so the
    # client just sits there forever looking hung (running the same
    # command directly from an already-open terminal works fine, since
    # that terminal already provides a real console). jakanddaxter's own
    # client.py (worlds/jakanddaxter/client.py) hits the identical problem
    # launching its own REPL from the Launcher and fixes it the same way:
    # CREATE_NEW_CONSOLE forces a real, fresh console window regardless of
    # what console context (or lack of one) the parent process has.
    log(f"starting: cmd /K {python_exe} {kotor_client_path} {' '.join(args_list)}")
    subprocess.Popen(["cmd", "/K", python_exe, kotor_client_path, *args_list],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
    log("process started")


def launch_kotor_client(*args: str) -> None:
    # Every step goes to %LOCALAPPDATA%\KotorAP\launcher.log: this runs
    # inside the Launcher, where prints and exceptions are invisible, so
    # a button that "does nothing" otherwise leaves no trace at all.
    import os
    import time
    import traceback

    log_path = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KotorAP", "launcher.log")

    def log(message: str) -> None:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except OSError:
            pass

    try:
        _launch_kotor_client(log, *args)
    except Exception:
        log("FAILED:\n" + traceback.format_exc())
        raise


components.append(Component("KOTOR Client", "KOTORClient", func=launch_kotor_client, component_type=Type.CLIENT))

JEDI_CLASS_ITEMS = {
    0: "Class Switch: Jedi Guardian",
    1: "Class Switch: Jedi Consular",
    2: "Class Switch: Jedi Sentinel",
}
# StartingClass=random_class -- item name for each of all 6 classes, keyed by
# class NAME (unlike JEDI_CLASS_ITEMS above, which is keyed by jedi_class's
# own option index) since random_class ignores jedi_class and rolls a
# class name directly via ALL_CLASS_NAMES below.
CLASS_NAME_TO_ITEM = {
    "guardian": "Class Switch: Jedi Guardian",
    "consular": "Class Switch: Jedi Consular",
    "sentinel": "Class Switch: Jedi Sentinel",
    "soldier": "PC Class: Soldier",
    "scout": "PC Class: Scout",
    "scoundrel": "PC Class: Scoundrel",
}
COMPANION_ITEM_NAMES = [
    "Companion: Bastila Shan", "Companion: Canderous Ordo", "Companion: Carth Onasi",
    "Companion: HK-47", "Companion: Jolee Bindo", "Companion: Juhani",
    "Companion: Mission Vao", "Companion: T3-M4", "Companion: Zaalbar",
]

# CompanionClass (Options.py) -- the 7 non-droid companions, and the 4 of
# those who are NOT already Jedi in vanilla (jedi_companion mode only ever
# touches these 4; Bastila/Jolee/Juhani keep their vanilla Jedi class in
# that mode). Keys match KotorClient.py's COMPANION_IDX_TO_ARM suffix
# ("companion_<key>") and generate_trampoline_batch.py's _COMPANION_TAGS.
COMPANION_CLASS_KEYS = ["bastila", "canderous", "carth", "jolee", "juhani", "mission", "zaalbar"]
# Deliberately NOT edited to add "hk47" directly -- this list (and the
# additional_feats eligibility list, which reuses it) must stay conditional
# on new_companion, not static, or vanilla HK-47 (a droid, in seeds where
# the replacement isn't even selected) would incorrectly become eligible
# for class randomization/Additional Feats. See KotorWorld._companion_class_keys().
# Her internal key stays "hk47" (matches every arm/tag/NPC-const token
# elsewhere in this codebase) even though her AP-facing name is "New
# Companion" -- COMPANION_CLASS_DISPLAY_NAMES is the one place that needs
# an explicit override, since "hk47".capitalize() would otherwise produce
# the broken-looking "Hk47" in a generated item name.
COMPANION_CLASS_DISPLAY_NAMES = {"hk47": "New Companion"}
NON_JEDI_COMPANION_KEYS = ["carth", "canderous", "zaalbar", "mission"]
BASE_CLASS_NAMES = ["soldier", "scout", "scoundrel"]
JEDI_CLASS_NAMES = ["guardian", "consular", "sentinel"]
ALL_CLASS_NAMES = BASE_CLASS_NAMES + JEDI_CLASS_NAMES

# CompanionClass=droid. Looks are appearance.2da rows, grouped by model: at most 2 companions share a model, and then only
# with different paint jobs. Rows 58 (war droid) and 82 (assassin droid) are the human-rig models patched in by
# scripts/generate_droid_assets.py; the rest are vanilla rows. HK-47's own look (3), his PC-only variant (1) and
# T3-M4's (2) are deliberately not in the pool, nor are the protocol (63, 233-235) and probe (62) droids.
DROID_LOOK_MODEL = {
    58: "war", 82: "assassin", 64: "sentry", 65: "spyder", 437: "spyder", 60: "markone", 436: "markone",
    61: "marktwo", 59: "markfour", 57: "astromech", 231: "astromech", 232: "astromech",
}
DROID_HUMAN_RIG_LOOKS = (58, 82)
DROID_COMBAT, DROID_EXPERT, DROID_BATTLE = 6, 7, 9
DROID_CLASS_HAND = [DROID_COMBAT] * 3 + [DROID_EXPERT] * 2 + [DROID_BATTLE] * 2

# Base item types a droid (race 5) can actually use once the droid patch has opened melee weapons to it. Everything else in
# gear_items.json (armor, robes, masks, gloves, belts, implants, forearm bands, medpacs, stims, saber crystals) is human-only.
DROID_USABLE_BASE_ITEMS = frozenset({
    "Quarter_Staff", "Stun_Baton", "Long_Sword", "Vibro_Sword", "Short_Sword", "Vibro_Blade", "Double_Bladed_Sword",
    "Vibro_Double_Blade", "Lightsaber", "Double_Bladed_Lightsaber", "Short_Lightsaber", "Ghaffi_Stick", "Wookie_Warblade",
    "Gammorean_Battleaxe",
    "Blaster_Pistol", "Heavy_Blaster", "Hold_Out_Blaster", "Ion_Blaster", "Disrupter_Pistol", "Sonic_Pistol", "Ion_Rifle",
    "Bowcaster", "Blaster_Carbine", "Disrupter_Rifle", "Sonic_Rifle", "Repeating_Blaster", "Heavy_Repeating_Blaster",
    "Blaster_Rifle",
    "Fragmentation_Grenades", "Stun_Grenades", "Thermal_Detonator", "Poison_Grenade", "Flash_Grenade", "Sonic_Grenade",
    "Adhesive_Grenade", "Cryoban_Grenade", "Fire_Grenade", "Ion_Grenade",
    "Trap_Kit", "Security_Spikes", "Programming_Spikes",
    "Droid_Light_Plating", "Droid_Medium_Plating", "Droid_Heavy_Plating", "Droid_Search_Scope_x", "Droid_Motion_Sensors_x",
    "Droid_Sonic_Sensors_x", "Droid_Targeting_Computers", "Droid_Computer_Spike_Mount_x", "Droid_Security_Spike_Mount",
    "Droid_Shield", "Droid_Utility_Device", "Droid_Repair_Equipment",
})


# Skills a droid cannot use (skills.2da droidcanuse = 0). With starting_class=droid their skill items and starting boosts are
# left out, so no item is a dead one.
DROID_UNUSABLE_SKILL_ARMS = frozenset({"stealth", "persuade", "treat_injury"})
# Items that only make sense for a character with Force powers; left out of the pool when the PC is a droid (a droid PC never
# becomes a Jedi). The vendor pass is the only way into the vendor's Force power menu.
DROID_PC_EXCLUDED_ITEMS = frozenset({"Vendor Pass: Force Power Training", "Trap: Remove Half Known Force Powers"})


def roll_droid_companions(rng, keys) -> typing.Dict[str, typing.List[int]]:
    """{companion key: [appearance row, droid class]} for CompanionClass=droid. Seven distinct looks (max 2 per model) and
    the 3/2/2 Combat/Expert/Battle hand dealt out at random; then the human-rig looks (war and assassin droid, the only
    pool models with real hands) are swapped onto Battle Droids when one is available, since only that class equips melee."""
    rows = sorted(DROID_LOOK_MODEL)
    rng.shuffle(rows)
    picked: typing.List[int] = []
    per_model: typing.Dict[str, int] = {}
    for row in rows:
        model = DROID_LOOK_MODEL[row]
        if len(picked) < len(keys) and per_model.get(model, 0) < 2:
            picked.append(row)
            per_model[model] = per_model.get(model, 0) + 1
    hand = list(DROID_CLASS_HAND)
    rng.shuffle(hand)
    plan = {key: [row, cls] for key, row, cls in zip(keys, picked, hand)}
    for key, (row, cls) in plan.items():
        if row in DROID_HUMAN_RIG_LOOKS and cls != DROID_BATTLE:
            swap = next((k for k, (r, c) in plan.items() if c == DROID_BATTLE and r not in DROID_HUMAN_RIG_LOOKS), None)
            if swap is not None:
                plan[swap][1], plan[key][1] = cls, DROID_BATTLE
    return plan

# The completion-condition markers (Rules.py's set_completion_rules) --
# real items (see Items.py's own comment on why NOT code=None Events)
# locked via place_locked_item() at their matching Locations.py locations
# instead of drawing a normal random reward. Location name -> item name.
# Two are dedicated new locations (Level 20 Reached/Malak Defeated); the
# true_balance pair and reach_leviathan's first-area visit reuse EXISTING
# locations instead of adding new ones. Only the markers the selected Goal's completion
# condition needs are locked (see KotorWorld._goal_event_locations());
# every other location in this table is an ordinary check that draws a
# normal reward. See create_items() for the matching pool-count adjustment.
GOAL_EVENT_LOCATIONS: typing.Dict[str, str] = {
    "Malak Defeated": "Malak Defeated",
    "Level 20 Reached": "Reached Level 20",
    "Alignment: Dark Side 0": "Reached Dark Side 0",
    "Alignment: Light Side 100": "Reached Light Side 100",
    "Visited: Leviathan - Prison Block": "Reached Leviathan",
}

# equipment_slot values (gear_items.json) that count as "Armor/Equipment"
# for item_distribution_type's weighted draw -- everything else with a
# blank slot is a Consumable, and "Weapon" is its own category. See
# KotorWorld._gear_category_pools().
_ARMOR_SLOTS = {"Arm", "Belt", "Body", "Hands", "Hands/Implant", "Head", "Implant"}

# The 6 planets with covered shops, keyed by name (used as fill_slot_data's
# per-planet shop_stock dict key) -- module-prefix mapping duplicated in
# generate_trampoline_batch.py since that's a separate dev-tooling script,
# not part of this apworld package (arm_orchestrator.py's --set-shop-stock=
# handler is planet-name-agnostic, no duplicate copy needed there). Same
# real module prefixes EntranceRando.py already relies on elsewhere in
# this file.
#
# FIX: Tatooine ("tatooine") was missing entirely -- confirmed
# a real bug, not by-design scope: tat_m17ab/tat_m17ad genuinely have
# real store objects (see extender/area_trampolines/_shop_map.json), but
# with this key absent, _shop_stock() below never generated a "tatooine"
# entry at all, so those 2 stores always restocked with an EMPTY catalog
# (see build_shop_stock_block's destroy-then-recreate-from-list logic --
# an empty list still runs the destroy half, just adds nothing back).
# NOT a "shares Kashyyyk's shop data" bug, despite tat_m17ab/tat_m17ad's
# own real vanilla store resrefs confusingly starting with "kas_" (a
# genuine, verified-against-the-real-game-files naming quirk in the
# original dev data, unrelated to this bug -- GetObjectByTag is scoped
# to the current module regardless of what the tag string looks like, so
# that part was never actually broken).
PLANET_MODULE_PREFIXES: typing.Dict[str, str] = {
    "taris": "tar_m",
    "dantooine": "danm",
    "kashyyyk": "kas_m",
    "manaan": "manm",
    "korriban": "korr_m",
    "tatooine": "tat_m",
}

# Fixed baseline used when item_distribution_type is "normal" -- a
# sensible mix that doesn't need any tuning. Player-decided weights are
# read from the matching Options.py Range fields instead; "randomized"
# rolls its own per-seed. See Options.py's ItemDistributionType docstring.
_DEFAULT_DISTRIBUTION_WEIGHTS: typing.Dict[str, int] = {
    "weapon": 30, "armor": 20, "consumable": 30,
    "exp": 20, "credit": 10, "skill": 5, "ability": 5,
    # Only ever biddable when Traps=item_filler (the category's candidate
    # list is empty otherwise and _distribute_items drops it) -- so this
    # baseline changes nothing for off/fixed_amount seeds.
    "trap": 5,
}


def _shop_pool() -> typing.List[str]:
    """resrefs flagged shop_randomize in gear_items.json, sorted for a
    deterministic sample() regardless of the JSON's own key order (which
    can shift as the user hand-edits it)."""
    gear = read_gear_json()
    return sorted(resref for resref, data in gear.items() if data.get("shop_randomize"))


def _is_droid_gear(gear_data: dict) -> bool:
    """Whether a gear_items.json entry is something a droid can use (see DROID_USABLE_BASE_ITEMS)."""
    return gear_data.get("base_item_type") in DROID_USABLE_BASE_ITEMS


class KotorWebWorld(WebWorld):
    theme = "stone"
    tutorials = []


class KotorWorld(World):
    """
    Archipelago integration for Knights of the Old Republic. Locations are
    real, game-wide quest completions (100 of KOTOR's 101 journal
    categories, spanning every planet), companion recruitments, area
    visits, alignment thresholds, character levels 2-20, and Malak's
    defeat -- see worlds/kotor/Locations.py. All detected live via the
    injected extender reading the game's own state. Items cover the full
    set of grants the extender can apply: skills, companions, class
    switches, ability increases, xp, and credits. Feats are deliberately
    not an AP item -- left entirely to normal in-game level-up choices.
    Regions are currently flat/ungated (see Rules.py) -- real progression
    gating is separate future work. The Level 20/Malak Defeated locations
    each carry a locked Event item instead of a normal reward, giving
    set_completion_rules() a real, non-trivial signal for the
    defeat_malak/max_level Goal options (true_balance's own completion
    signal is still entirely client-side -- see Rules.py).
    """
    game = "KotOR"
    web = KotorWebWorld()
    options_dataclass = KotorOptions
    options: KotorOptions

    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id

    def _companion_class_keys(self) -> list:
        """COMPANION_CLASS_KEYS, plus "hk47" when new_companion is on. Must
        be computed per-call (not a static list edit) so a seed where the
        replacement isn't selected never makes vanilla HK-47 (a droid)
        eligible for class randomization/Additional Feats -- see
        COMPANION_CLASS_KEYS's own comment. Used by generate_early()'s
        no_jedi/randomize_all rolls and by create_items()'s Additional
        Feats eligibility list; NOT used for jedi_companion (mode 2), which
        keeps its own separate NON_JEDI_COMPANION_KEYS untouched by design."""
        keys = list(COMPANION_CLASS_KEYS)
        if self.options.new_companion:
            keys.append("hk47")
        return keys

    def _goal_event_locations(self) -> typing.Dict[str, str]:
        """The subset of GOAL_EVENT_LOCATIONS the selected Goal's completion
        condition (Rules.py's set_completion_rules) actually checks. The
        other goals' locations stay ordinary checks."""
        names_by_goal = {
            Goal.option_defeat_malak: ("Malak Defeated",),
            Goal.option_max_level: ("Level 20 Reached",),
            Goal.option_true_balance: ("Alignment: Dark Side 0", "Alignment: Light Side 100"),
            Goal.option_reach_leviathan: ("Visited: Leviathan - Prison Block",),
        }
        names = names_by_goal.get(self.options.goal.value, ())
        return {name: GOAL_EVENT_LOCATIONS[name] for name in names}

    def _active_locations(self) -> dict:
        """location_table filtered for companion_mode=none, which removes
        the 9 "companion" location_type entries AND the 10
        COMPANION_SUBPLOT_LOCATIONS entries (those are
        location_type="journal", so they aren't caught by the
        "companion" type check alone, even though companions never joining
        at all makes them just as permanently uncompletable) entirely
        rather than leaving them stuck. Also filters the 40 "bounty" locations
        when additional_enemies is off -- with no additional
        enemies placed at all, no bounty card can ever be carried, so
        these would otherwise be 40 permanently-uncompletable locations,
        same shape as the companion_mode=none case. Used by both
        create_regions() and create_items() so the pool size always
        matches what's actually placed -- computing this independently in
        each would risk the two silently drifting out of sync."""
        result = location_table
        if self.options.companion_mode == 2:  # none
            result = {name: data for name, data in result.items()
                       if data.location_type != "companion"
                       and name not in COMPANION_SUBPLOT_LOCATIONS}
        elif self.options.companion_mode == 3:  # ap_limited: the recruit moments stay, the subplot checks cannot be promised
            result = {name: data for name, data in result.items()
                       if name not in COMPANION_SUBPLOT_LOCATIONS}
        if self.options.additional_enemies == 0:  # off
            result = {name: data for name, data in result.items()
                       if data.location_type != "bounty"}
        # new_companion: "Companion Recruited: HK-47" and
        # "Companion Recruited: New Companion" share the same companion_idx
        # (both fire off IsAvailableCreature(3) -- see Locations.py), so
        # exactly one of the two must be active, never both/neither, or
        # active_count (create_items()) and the real fillable location
        # count would drift apart. "Ebon Hawk: HK-47" is dropped outright
        # (no new_companion equivalent) when the replacement is selected --
        # her personal subplot dialogue that used to complete it is gone,
        # replaced with a single placeholder greeting, so the check would
        # otherwise sit permanently uncompletable (same failure shape as
        # the companion_mode=none journal-location bug above, this time
        # self-inflicted by the dialogue cut rather than her never joining
        # at all). When companion_mode=none has already stripped all
        # companion-type/subplot locations above, these two filters are a
        # harmless no-op against an already-absent name.
        if self.options.new_companion:
            result = {name: data for name, data in result.items()
                       if name not in ("Companion Recruited: HK-47", "Ebon Hawk: HK-47")}
        else:
            result = {name: data for name, data in result.items()
                       if name != "Companion Recruited: New Companion"}
        return result

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        active = self._active_locations()
        region_names = sorted({data.region for data in active.values()})
        regions = {}
        for name in region_names:
            r = Region(name, self.player, self.multiworld)
            self.multiworld.regions.append(r)
            menu.connect(r)
            regions[name] = r

        goal_events = self._goal_event_locations()
        for loc_name, loc_data in active.items():
            region = regions[loc_data.region]
            location = KotorLocation(self.player, loc_name, loc_data.id, region)
            region.locations.append(location)
            event_item_name = goal_events.get(loc_name)
            if event_item_name is not None:
                # Real item with a real code (see Items.py's own comment on
                # why this can't be a code=None Event) via the normal
                # create_item() path -- NOT constructed by hand here, so it
                # goes through item_table like everything else and can't
                # drift out of sync with it.
                location.place_locked_item(self.create_item(event_item_name))

        # Separate physical-module region graph purely for door/trigger
        # entrance randomization -- does not touch the thematic regions
        # built above, which are what actually govern location access.
        # See EntranceRando.py's module docstring for why these coexist
        # independently.
        if self.options.area_randomizer:
            EntranceRando.create_transition_regions(self)

    def connect_entrances(self) -> None:
        if self.options.area_randomizer:
            EntranceRando.connect_entrances(self)

    def create_item(self, name: str) -> KotorItem:
        data = item_table[name]
        return KotorItem(name, data.classification, data.code, self.player)

    def _droid_mode(self) -> int:
        """How many of starting_class / companion_class are set to droid (0, 1 or 2). 2 means droid-only item pool and
        shops; 1 means droid gear is simply more common."""
        return int(self.options.starting_class == 4) + int(self.options.companion_class == 4)

    def generate_early(self) -> None:
        # CompanionClass=droid rebuilds the 7 non-droid companions and leaves HK-47 alone, so a new_companion
        # replacement is silently ignored rather than rejected.
        if self.options.companion_class == 4:
            self.options.new_companion.value = 0

        """Precollected (starting-inventory) items: the starting_class
        choice (only when starting_class is "jedi_start" -- "jedi_granted"
        places the same item in the shuffled pool instead, see
        create_items()) and
        any starting ability/skill boosts. These are handed to the player
        immediately rather than placed in the shuffled pool."""
        if self.options.starting_class == 1:  # jedi_start
            class_name = JEDI_CLASS_ITEMS[self.options.jedi_class.value]
            self.multiworld.push_precollected(self.create_item(class_name))
        elif self.options.starting_class == 3:  # random_class
            # Independent of jedi_class entirely -- rolls all 6 classes,
            # applied immediately like "start" above (precollected, not
            # item-gated). Same seeded-RNG-in-generate_early() pattern as
            # the CompanionClass companion rolls just below.
            rolled_class = self.random.choice(ALL_CLASS_NAMES)
            item_name = CLASS_NAME_TO_ITEM[rolled_class]
            self.multiworld.push_precollected(self.create_item(item_name))
        elif self.options.starting_class == 4:  # droid
            # Ignores jedi_class; precollected like jedi_start, so the conversion arrives as soon as the client connects.
            self.multiworld.push_precollected(self.create_item("PC Droid Conversion"))

        # CompanionClass companion rolls -- computed once, here, using this
        # player's own seeded RNG, so both create_items() (jedi_companion's
        # guaranteed item placement) and fill_slot_data() (no_jedi/
        # randomize_all's companion_class_rolls map, applied automatically at
        # recruit by KotorClient.py) see the same values. self.companion_class_rolls
        # is sent to the client as-is; self.jedi_companion_items is
        # consulted only by create_items() below (not sent directly -- the
        # class per companion is implicit in which of the 3 static items
        # gets placed).
        self.companion_class_rolls: typing.Dict[str, str] = {}
        self.jedi_companion_items: typing.Dict[str, str] = {}
        mode = self.options.companion_class.value
        # jedi_companion (mode 2) deliberately keeps iterating the static
        # NON_JEDI_COMPANION_KEYS, NOT self._companion_class_keys() -- per
        # design, new_companion has no effect on this mode (she's not one
        # of the 4 target companions it converts).
        if mode == 1:  # no_jedi
            for key in self._companion_class_keys():
                self.companion_class_rolls[key] = self.random.choice(BASE_CLASS_NAMES)
        elif mode == 2:  # jedi_companion
            for key in NON_JEDI_COMPANION_KEYS:
                self.jedi_companion_items[key] = self.random.choice(JEDI_CLASS_NAMES)
        elif mode == 3:  # randomize_all
            for key in self._companion_class_keys():
                self.companion_class_rolls[key] = self.random.choice(ALL_CLASS_NAMES)

        # CompanionClass=droid: looks and droid classes are dealt here (seeded) and sent in slot_data; the client's
        # droid patcher writes them into the companion templates. Nothing is delivered at recruit time.
        self.companion_droid_plan: typing.Dict[str, typing.List[int]] = {}
        if mode == 4:  # droid
            self.companion_droid_plan = roll_droid_companions(self.random, COMPANION_CLASS_KEYS)

        # CompanionMode=ap_limited: the order the nine companions are earned in. Drawn only for that mode so every
        # other mode's later random draws are unchanged.
        self.companion_unlock_order: typing.List[str] = []
        if self.options.companion_mode == 3:  # ap_limited
            keys = ["bastila", "canderous", "carth", "hk47", "jolee", "juhani", "mission", "t3m4", "zaalbar"]
            self.random.shuffle(keys)
            self.companion_unlock_order = keys

        for arm_name, option_name in STARTING_ABILITY_ARMS.items():
            points = getattr(self.options, option_name).value
            item_name = arm_name_to_item[arm_name]
            for _ in range(points):  # +1 point per firing
                self.multiworld.push_precollected(self.create_item(item_name))

        for arm_name, option_name in STARTING_SKILL_ARMS.items():
            if self.options.starting_class == 4 and arm_name in DROID_UNUSABLE_SKILL_ARMS:
                continue
            points = getattr(self.options, option_name).value
            item_name = arm_name_to_item[arm_name]
            firings = -(-points // 2)  # +2 points per firing, rounded up
            for _ in range(firings):
                self.multiworld.push_precollected(self.create_item(item_name))

        # No LootMode=destroy/replace safety net here (AP-
        # granted precollected items) -- replaced by directly
        # baking Security Spikes into the Endar Spire's own starting
        # locker (footlker001, end_m01aa_s.rim) at patch time instead, see
        # patch_loot_disturb.py's ensure_starting_locker_gear(). Real
        # motivation: this precollected burst was firing as a big batch of
        # simultaneous grants on every fresh-character connect, which was
        # confusing to observe live and unnecessary now that the actual
        # vanilla locker can just be guaranteed correct directly. The
        # other 3 (Computer Spikes/Vibroblade/Clothing) were already
        # covered by the real vanilla locker contents once footlker001/
        # footlker003 were excluded from loot suppression entirely (see
        # PLACEABLE_EXCLUDE) -- only Security Spikes was never actually a
        # vanilla item there, hence the one direct addition.

    def create_items(self) -> None:
        # -len(self._goal_event_locations()): the selected goal's marker
        # locations got a locked item in create_regions() instead of drawing
        # from this pool -- without this adjustment the pool would be short
        # of the real number of fillable (non-event) location slots.
        active_count = len(self._active_locations()) - len(self._goal_event_locations())

        # Companions (when companion_mode is ap_gated) and the starting_class
        # class item (when starting_class is "jedi_granted") are the only
        # things ever unconditionally guaranteed in the pool -- "jedi_granted"
        # means the player WILL become a Jedi at some point, never a matter of
        # luck, same guarantee companions get. When starting_class is
        # "jedi_start" the item is precollected in generate_early() instead
        # (not part of this pool-sizing math at all); when "off" there's no
        # class item anywhere. Everything else -- curated gear, Skills,
        # Abilities, EXP, Credits -- is drawn through the weighted
        # distribution in _distribute_items() instead. Feats are not an AP
        # item at all any more (see Items.py) -- left entirely to normal
        # in-game level-up choices.
        if self.options.companion_mode == 0:  # ap_gated
            # new_companion: swap "Companion: HK-47" for
            # "Companion: New Companion" -- exactly one of the two is ever
            # placed, matching _active_locations()'s companion-location
            # swap above (both key off the same companion_idx=3 signal).
            companion_names = COMPANION_ITEM_NAMES
            if self.options.new_companion:
                companion_names = [
                    "Companion: New Companion" if n == "Companion: HK-47" else n
                    for n in companion_names
                ]
            mandatory_names = list(companion_names)
        else:
            mandatory_names = []
        if self.options.starting_class == 2:  # jedi_granted
            mandatory_names = mandatory_names + [JEDI_CLASS_ITEMS[self.options.jedi_class.value]]
        # CompanionClass=jedi_companion: same guaranteed-placement guarantee
        # as starting_class=granted -- the roll already happened in
        # generate_early(), this just places whichever of the 3 static
        # per-companion items matches it.
        for key, class_name in self.jedi_companion_items.items():
            mandatory_names = mandatory_names + [f"Jedi Training: {key.capitalize()} ({class_name.capitalize()})"]

        # AdditionalFeats: guaranteed placement, same reasoning
        # as the Jedi Training items above -- a fixed count tied directly to
        # the option, not subject to the weighted _distribute_items() draw.
        # 1 item (PC only) when companion_mode is "none" (no companions
        # exist to target at all), else 8 (PC + all 7 non-droid companions,
        # regardless of CompanionClass -- KotorClient.py's own recruited/
        # class-finalized gating handles waiting for each one correctly,
        # this is just pool placement).
        if self.options.additional_feats:
            mandatory_names = mandatory_names + ["Additional Feats Character: PC"]
            if self.options.companion_mode != 2:  # not "none"
                # self._companion_class_keys(), not the raw COMPANION_CLASS_KEYS
                # constant, so new_companion=on makes her eligible here too.
                # COMPANION_CLASS_DISPLAY_NAMES.get(key, ...)
                # falls back to .capitalize() for every real name (unaffected),
                # and only overrides "hk47" -- ".capitalize()" alone would
                # produce the broken-looking "Additional Feats Character: Hk47".
                mandatory_names = mandatory_names + [
                    f"Additional Feats Character: {COMPANION_CLASS_DISPLAY_NAMES.get(key, key.capitalize())}"
                    for key in self._companion_class_keys()
                ]

        # ProgressionSystem: the 24 story-gate progression items (8 families of 3) are guaranteed placement. The
        # access rules in StoryGates.py assume every item exists, so there is no weighted draw.
        if self.options.progression_system:
            for token_names in STORY_TOKEN_NAMES.values():
                mandatory_names = mandatory_names + list(token_names)

        # ArchipelagoVendor: the five Vendor Pass items are guaranteed placement (they replace filler,
        # so the pool size is unchanged). Useful, never progression.
        if self.options.archipelago_vendor:
            mandatory_names = mandatory_names + [
                n for n in VENDOR_UNLOCK_ITEMS if not (self.options.starting_class == 4 and n in DROID_PC_EXCLUDED_ITEMS)]

        # Traps=fixed_amount: all 12
        # items guaranteed placement, same reasoning as Additional Feats/
        # Progression System above -- "always exactly 12 exist," not a
        # weighted-chance draw. item_filler mode is handled inside
        # _distribute_items() as its own weighted category instead (see
        # the "trap" entry there); off adds nothing anywhere. See Items.py's
        # TRAP_ITEMS for the full list/arm_name mapping and Options.py's
        # Traps docstring for what each one does.
        if self.options.enable_traps == 2:  # fixed_amount
            mandatory_names = mandatory_names + [
                n for n in TRAP_ITEMS if not (self.options.starting_class == 4 and n in DROID_PC_EXCLUDED_ITEMS)]

        pool = [self.create_item(name) for name in mandatory_names]
        pool += self._distribute_items(active_count - len(pool))
        self.multiworld.itempool += pool

    def _gear_category_pools(self) -> typing.Dict[str, typing.List[str]]:
        """item_table names (already included_as_item, real AP items with
        real codes) split into weapon/armor/consumable buckets by their
        real equipment_slot in gear_items.json. Used only by
        _distribute_items() below."""
        pools: typing.Dict[str, typing.List[str]] = {"weapon": [], "armor": [], "consumable": []}
        gear = read_gear_json()
        if not gear:
            return pools
        for name, data in item_table.items():
            if not data.arm_name.startswith("give_item:"):
                continue
            resref = data.arm_name[len("give_item:"):]
            gear_data = gear.get(resref)
            if gear_data is None:
                continue
            # Only rows flagged included_as_item are generic gear. The 8
            # hand-written "Progression Item: ..." entries also use a
            # give_item: arm and their resrefs sit in gear_items.json, but
            # flagged included_as_item=False; without this check they were
            # drawn as ordinary armor/consumables with Progression System off
            # (and as duplicates of the mandatory copies with it on).
            if not gear_data.get("included_as_item"):
                continue
            # Both options droid: only gear a droid can use. One option droid: droid gear is listed three times so it is
            # drawn about three times as often (the draw is with replacement, so a repeat is harmless).
            droid_mode = self._droid_mode()
            is_droid_gear = _is_droid_gear(gear_data)
            if droid_mode == 2 and not is_droid_gear:
                continue
            copies = 3 if (droid_mode == 1 and is_droid_gear) else 1
            slot = gear_data.get("equipment_slot") or ""
            if slot == "Weapon":
                pools["weapon"] += [name] * copies
            elif slot in _ARMOR_SLOTS:
                pools["armor"] += [name] * copies
            else:
                pools["consumable"] += [name] * copies
        return pools

    def _skill_ability_pools(self) -> typing.Tuple[typing.List[str], typing.List[str]]:
        """Item names for the 8 Skill and 6 Ability Increase items,
        derived from Options.py's STARTING_SKILL_ARMS/STARTING_ABILITY_ARMS
        arm-name keys (the same source of truth generate_early() uses for
        starting boosts) rather than a second hand-written list."""
        skills = [arm_name_to_item[arm] for arm in STARTING_SKILL_ARMS if arm in arm_name_to_item
                  and not (self.options.starting_class == 4 and arm in DROID_UNUSABLE_SKILL_ARMS)]
        abilities = [arm_name_to_item[arm] for arm in STARTING_ABILITY_ARMS if arm in arm_name_to_item]
        return skills, abilities

    def _distribute_items(self, needed: int) -> typing.List[KotorItem]:
        """Fills `needed` pool slots -- almost the entire pool, since only
        companions are ever separately guaranteed (see create_items()) --
        by drawing from 8 weighted categories: Weapons, Armor/Equipment,
        Consumables, EXP, Credits, Skills, Abilities, Traps (the last only
        when Traps=item_filler). "normal" uses a
        fixed baseline (_DEFAULT_DISTRIBUTION_WEIGHTS); "player_decided"
        reads the matching weight options instead; "randomized" rolls its
        own per-seed. Weights are relative, not required to sum to 100. A
        category with no real candidates given other options (e.g. EXP
        when experience_mode is off, or Weapons/Armor/Consumables
        when receive_inventory_items is off) is dropped and the rest
        renormalized automatically. See Options.py's ItemDistributionType
        docstring for the full design."""
        if needed <= 0:
            return []

        gear_pools = self._gear_category_pools() if self.options.receive_inventory_items else \
            {"weapon": [], "armor": [], "consumable": []}
        skill_pool, ability_pool = self._skill_ability_pools()
        categories: typing.Dict[str, typing.List[str]] = {
            "weapon": gear_pools["weapon"],
            "armor": gear_pools["armor"],
            "consumable": gear_pools["consumable"],
            "exp": ["Experience Points"] if self.options.experience_mode == 2 else [],
            "credit": ["Republic Credits"] if self.options.credit_mode == 2 else [],
            "skill": skill_pool,
            "ability": ability_pool,
            # Traps=item_filler: the 12 trap types become a
            # weighted category like any other, drawn WITH replacement --
            # the same trap type can land more than once in a seed (each
            # copy is a distinct delivery; the client's per-(character,
            # index) dedup keys on the item index, not the name). Empty for
            # off (no traps anywhere) and fixed_amount (create_items()
            # already placed exactly 12 as mandatory items).
            "trap": [n for n in TRAP_ITEMS if not (self.options.starting_class == 4 and n in DROID_PC_EXCLUDED_ITEMS)]
                    if self.options.enable_traps == 1 else [],
        }

        dist_type = self.options.item_distribution_type.value
        if dist_type == 0:  # normal -- fixed project-chosen baseline
            weights = dict(_DEFAULT_DISTRIBUTION_WEIGHTS)
        elif dist_type == 2:  # randomized -- weights rolled per-seed via this player's own seeded RNG
            weights = {k: self.random.randint(1, 100) for k in categories}
        else:  # player_decided
            weights = {
                "weapon": self.options.weapon_weight.value,
                "armor": self.options.armor_weight.value,
                "consumable": self.options.consumable_weight.value,
                "exp": self.options.exp_weight.value,
                "credit": self.options.credit_weight.value,
                "skill": self.options.skill_weight.value,
                "ability": self.options.ability_weight.value,
                "trap": self.options.trap_weight.value,
            }

        available = {k: w for k, w in weights.items() if w > 0 and categories[k]}
        if not available:
            # Nothing biddable at all (e.g. every relevant option toggled
            # off, including skill/ability weights zeroed under
            # player_decided) -- fall back to a safely-repeatable filler
            # rather than dividing by zero on an empty weight table.
            return [self.create_item("Skill: Computer Use") for _ in range(needed)]

        total_weight = sum(available.values())
        result: typing.List[KotorItem] = []
        for _ in range(needed):
            roll = self.random.uniform(0, total_weight)
            upto = 0.0
            for key, w in available.items():
                upto += w
                if roll <= upto:
                    result.append(self.create_item(self.random.choice(categories[key])))
                    break
        return result

    def get_filler_item_name(self) -> str:
        return filler_items[0]

    def fill_slot_data(self) -> dict:
        """Exposed so KotorClient.py can read the active companion/XP/credits
        mode after connecting -- these change client-side behavior (whether
        a companion check self-fulfills, whether XP gets clamped on area
        transitions, and by how much) that can't be inferred from the item
        pool alone."""
        return {
            "companion_mode": self.options.companion_mode.value,
            # ap_limited: the seeded order companions are earned in (empty for every other mode)
            "companion_unlock_order": self.companion_unlock_order,
            "new_companion": self.options.new_companion.value,
            "starting_class": self.options.starting_class.value,
            "experience_mode": self.options.experience_mode.value,
            "experience_limiter": self.options.experience_limiter.value,
            "experience_item": self.options.experience_item.value,
            "credit_mode": self.options.credit_mode.value,
            "credit_limiter": self.options.credit_limiter.value,
            "credit_item": self.options.credit_item.value,
            "death_link": bool(self.options.death_link),
            # TrapLink (KotorClient.py adds/removes the
            # "TrapLink" connection tag from this, exactly like death_link
            # above drives update_death_link), the raw Traps mode (0=off/
            # 1=item_filler/2=fixed_amount -- an incoming linked trap is
            # ignored when 0), and Galactic Shop (drives the local
            # patch_galactic_shop.py module edit on Connect, same seed-gated
            # pattern as loot_mode/door_mapping below).
            "trap_link": bool(self.options.trap_link),
            "traps_mode": self.options.enable_traps.value,
            "galactic_shop": bool(self.options.galactic_shop),
            # Archipelago Vendor on the Ebon Hawk (generate_trampoline_batch.py reads this from the
            # saved slot data to decide whether the Hawk's trampoline spawns the vendor NPC).
            "archipelago_vendor": bool(self.options.archipelago_vendor),
            "receive_inventory_items": bool(self.options.receive_inventory_items),
            "consumable_stack_count": self.options.consumable_stack_count.value,
            "shop_item_count": self.options.shop_item_count.value,
            "loot_mode": self.options.loot_mode.value,
            # Raw value (0=off/1=coupled/2=decoupled), not just a bool --
            # patch_door_randomizer.py only ever needs "is there a
            # door_mapping to apply" (any nonzero value already implies
            # that), but scripts/review_door_mapping.py's report needs the
            # actual mode to describe the seed accurately.
            "area_randomizer": self.options.area_randomizer.value,
            "door_mapping": getattr(self, "kotor_door_mapping", None),
            # door_graph keys _repair_orphaned_modules repointed for this
            # seed -- lets a review tool label a repaired entry separately
            # from a cleanly-coupled one instead of presenting one
            # undifferentiated list (see EntranceRando.py's connect_entrances).
            "door_mapping_repairs": getattr(self, "kotor_door_repairs", []),
            "goal": self.options.goal.value,
            "shop_stock": self._shop_stock(),
            # CompanionClass=no_jedi/randomize_all only -- jedi_companion's
            # assignments are implicit in which "Jedi Training: ..." item
            # got placed (see create_items()), not sent here. Empty dict
            # for off/jedi_companion.
            "companion_class_rolls": self.companion_class_rolls,
            # The raw mode value itself (0=off/1=no_jedi/
            # 2=jedi_companion/3=randomize_all) -- companion_class_rolls alone
            # can't distinguish "off" from "jedi_companion" (both leave it
            # empty), which the Additional Feats feature's class-finalization
            # check needs to tell apart (jedi_companion means an eligible
            # companion DOES have a class change still coming, just not
            # reflected in companion_class_rolls; off means none ever will).
            "companion_class_mode": self.options.companion_class.value,
            # CompanionClass=droid only: {companion key: [appearance row, droid class]}, written into the companion
            # templates by scripts/generate_droid_assets.py on Connect. Empty otherwise.
            "companion_droid_plan": self.companion_droid_plan,
            # Additional Enemies mode (0=off/1=area_appropriate/
            # 2=random_sane/3=fully_random) -- read by the local,
            # tester-run scripts/patch_additional_enemies.py, which consumes
            # extender/area_trampolines/_enemy_spawn_points.json +
            # _enemy_cr_bands.json, same seed-gated pattern as loot_mode/
            # door_mapping above (not baked into the item pool -- this is a
            # pure area modification, no AP items involved).
            "additional_enemies_mode": self.options.additional_enemies.value,
            # Whether Progression System is active -- the
            # local KotorClient.py (via patch_item_suppression.py's
            # checkpoint wrappers and patch_loot_disturb.py's
            # progression_resrefs handling) needs this before it suppresses
            # any of the 10 real
            # quest items' vanilla acquisition scripts, same seed-gated
            # pattern as loot_mode/door_mapping/additional_enemies_mode
            # above.
            "progression_system": bool(self.options.progression_system),
        }

    def _shop_stock(self) -> typing.Dict[str, typing.List[str]]:
        """Picks shop_item_count resrefs from the shop_randomize pool
        INDEPENDENTLY per planet, using this player's seeded RNG -- each of
        the 5 covered planets (Taris/Dantooine/Kashyyyk/Manaan/Korriban)
        gets its own distinct catalog instead of one universal list shared
        by every shop (see Options.py's ShopItemCount).

        ALWAYS returns all 5 planet keys, even when shop_randomizer is off
        (empty list per planet then): returning {} instead when
        shop_randomizer is off would make KotorClient.py skip sending
        anything at all for an empty dict, which would mean
        _shop_stock.json (a file that persists across
        sessions/seeds on the player's machine, not tied to any one
        connection) never gets cleared when reconnecting to a
        shop_randomizer=off seed after previously playing one with it on --
        stale stock from the OLD seed would silently keep populating any
        store the player walked into. Returning real (even if empty) lists
        for every planet, unconditionally, means every fresh Connect always
        overwrites all 5 planets' entries with the CURRENT seed's real
        answer -- never leaves a previous seed's data lying around."""
        if not self.options.shop_randomizer:
            return {planet: [] for planet in PLANET_MODULE_PREFIXES}
        count = self.options.shop_item_count.value
        pool = _shop_pool()
        droid_mode = self._droid_mode()
        if droid_mode:
            gear = read_gear_json()
            droid_pool = [r for r in pool if _is_droid_gear(gear.get(r, {}))]
            if droid_mode == 2:  # both droid: every shop item is something a droid can use
                pool = droid_pool
            else:  # one droid: at least ~40% of each shop is droid gear
                droid_set = set(droid_pool)
                human_pool = [r for r in pool if r not in droid_set]
                droid_share = min(len(droid_pool), -(-count * 2 // 5))
                return {
                    planet: self.random.sample(droid_pool, droid_share)
                    + self.random.sample(human_pool, min(count - droid_share, len(human_pool)))
                    for planet in PLANET_MODULE_PREFIXES
                }
        return {
            planet: self.random.sample(pool, min(count, len(pool)))
            for planet in PLANET_MODULE_PREFIXES
        }

    def set_rules(self) -> None:
        set_rules(self.multiworld, self.player)
        set_completion_rules(self.multiworld, self.player)
