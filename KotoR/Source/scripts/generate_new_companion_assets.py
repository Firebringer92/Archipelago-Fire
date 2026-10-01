"""
Builds and deploys the assets for Options.py's new_companion option --
either Meetra Surik (the Jedi Sentinel, "mystery") or Darth Malak (the
Jedi Guardian, "malak") replacing HK-47 in his party slot. See
DEVELOPMENT_HISTORY.md's "New Companion: replacing HK-47 with an
original human character" section for the full feasibility research and
__init__.py/Locations.py/Items.py/Rules.py/
generate_trampoline_batch.py for the AP-side wiring this feeds.

Three pieces per character, all handled here:
1. p_meetra.utc / p_malak.utc (build_new_companion_utc/
   build_malak_companion_utc) -- level-1 stat block, built from a real
   companion template of the same class as a guide (Bastila for Meetra's
   Sentinel, Juhani for Malak's Guardian -- the one real companion of
   that exact class).
2. The vanilla Tatooine trigger's 3-way variant (deploy_vanilla_trigger)
   -- apo_hk47_vanilla.ncs (true vanilla, spawns p_hk47), apo_hk47_new.ncs
   (spawns p_meetra), apo_hk47_malak.ncs (spawns p_malak) -- each
   confirmed via a compile+disassemble+diff pass to differ from vanilla
   by exactly 1 opcode (the template string). All precompiled and checked
   into extender/scripts_src/, same "no compiler needed at runtime"
   convention patch_item_suppression.py already uses for its own mode
   variants -- this script just copies the right one to
   Override/apo_hk47_orig.ncs, the name the companion-suppression
   wrapper's ExecuteScript call expects.
3. k_hmee_dialog.dlg / k_hmal_dialog.dlg (build_placeholder_greeting_dlg)
   -- HK-47's entire personal Ebon Hawk subplot replaced with one greeting
   line, cut entirely for this option. Referenced by each .utc's own
   `conversation` field.

Malak additionally needs a brand-new portraits.2da row (no usable vanilla
portrait exists for him -- his real in-game PortraitId values are
leftover garbage, one of them literally Carth's portrait) --
see ensure_malak_portrait_row(), same add_row() precedent
patch_tsl_powers.py already established for spells.2da.

Usage: python generate_new_companion_assets.py [--game-dir=<path>] [--new-companion=0|1|2]
  Deploys the right pieces to that install's Override folder in one call
  (0=off/vanilla, 1=mystery/Meetra, 2=malak). Meant to be invoked the same
  way patch_item_suppression.py's other conditional deploy steps are --
  once per Connect, gated on _slot_data.json's new_companion value -- not
  a one-time setup step: deploy_vanilla_trigger() must run on EVERY
  connect regardless of the value, to restore the true vanilla trigger
  when new_companion is off just as much as to install either
  replacement. --new-companion= overrides reading _slot_data.json, for
  standalone testing.
"""
import json
import os
import shutil
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import Game, ResRef
from pykotor.extract.installation import Installation, SearchLocation
from pykotor.resource.formats.gff import write_gff
from pykotor.resource.formats.twoda import read_2da, write_2da
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGLink, dismantle_dlg
from pykotor.resource.generics.utc import UTC, UTCClass, dismantle_utc
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
RAW_OVERRIDE_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")

VANILLA_TRIGGER_NCS = os.path.join(SRC_DIR, "apo_hk47_vanilla.ncs")
NEW_TRIGGER_NCS = os.path.join(SRC_DIR, "apo_hk47_new.ncs")
MALAK_TRIGGER_NCS = os.path.join(SRC_DIR, "apo_hk47_malak.ncs")
_TRIGGER_NCS_BY_MODE = {0: VANILLA_TRIGGER_NCS, 1: NEW_TRIGGER_NCS, 2: MALAK_TRIGGER_NCS}

# Jedi Sentinel (class_id 5) cross-class + signature feats, confirmed via
# feat.2da against GameMechanics.md's own class-feat table: Weapon Prof.
# Blaster/Lightsaber/Melee Weapons + Jedi Defense + Force Sensitive + Jedi
# Sense are shared by all 3 Jedi classes; Force Immunity: Fear is Sentinel's
# own signature (matches generate_trampoline_batch.py's _JEDI_FEATS=(55,43,
# 116,107) + _JEDI_UNIQUE_POWER_FEAT["sentinel"]=98 -- the SAME recipe
# already used for companion_class conversions, just applied here as her
# from-creation baseline instead of an incremental grant).
STARTING_FEATS = [
    39,   # WEAPON_PROF_BLASTER
    43,   # WEAPON_PROF_LIGHTSABER
    44,   # WEAPON_PROF_MELEE_WEAPONS
    55,   # JEDI_DEFENSE
    116,  # FORCE_SENSITIVE
    107,  # JEDI_SENSE
    98,   # FORCE_IMMUNITY_FEAR (Sentinel signature)
]

# The 5 "base tier" starting Force powers real Jedi templates carry from
# creation -- confirmed via Bastila's own real p_bastilla.utc (levels 1-5
# have no normal spell-list access at all; GameMechanics.md's own level-gate
# table starts at 6). These exact 5 are also confirmed in GameMechanics.md's
# "13 base-tier powers not learnable via normal level-up" list, so they are
# not something she'd otherwise gain at level 1 through ordinary means --
# they have to be baked into the template directly, same as they are for
# every other real Jedi companion.
STARTING_POWERS = [
    6,   # FORCE_POWER_AFFECT_MIND
    18,  # FORCE_POWER_FORCE_AURA
    23,  # FORCE_POWER_FORCE_PUSH
    46,  # FORCE_POWER_STUN
    49,  # FORCE_POWER_LIGHT_SABER_THROW
]

# Equipment restriction (Head/Body/Hands only -- weapons/belt/implant/
# forearm-bands untouched), settled 2026-09-27 after race_id=5 (droid)
# was tried and rejected live: it didn't just block armor, it collapsed
# his ENTIRE weapon selection down to "Blaster Pistol, None" only.
#
# subrace_id=2 ("Beast" -- subrace.2da's real, defined 3rd slot:
# 0=None/1=Wookie/2=Beast) reuses baseitems.2da's existing denysubrace
# bitmask mechanic instead -- the SAME mechanic already used, today, to
# stop Wookiees from being offered Jedi robes their body shape can't
# wear (Jedi_Robe's real denysubrace=0x2 = bit for subrace_id=1/Wookie,
# confirmed via subrace.2da). Bit 0x4 (subrace_id=2/Beast) is confirmed
# unused anywhere in baseitems.2da today -- a genuinely clean, already-
# defined slot to reuse rather than an arbitrary invented number.
MALAK_SUBRACE_ID = 2
MALAK_DENYSUBRACE_BIT = 1 << MALAK_SUBRACE_ID  # 0x4

# Real base-item rows covering Head/Body/Hands, confirmed via a full
# equipableslots scan of baseitems.2da -- deliberately excludes the 9
# Droid_*_Plating/Sensors/Spike_Mount rows also in that slot range,
# since those are droid-only equipment a human-race Malak was never
# going to be offered anyway.
MALAK_RESTRICTED_GEAR_LABELS = [
    "Jedi_Robe", "Jedi_Knight_Robe", "Jedi_Master_Robe",
    "Armor_Class_4", "Armor_Class_5", "Armor_Class_6",
    "Armor_Class_7", "Armor_Class_8", "Armor_Class_9",
    "Mask", "Gauntlets", "Basic_Clothing", "Revan_Armor", "Disguise_Item",
]

# Jedi Guardian (class_id 3) cross-class + signature feats, confirmed via
# feat.2da against GameMechanics.md's own class-feat table: same 6 shared
# Jedi feats as Sentinel above, but Force Jump (101) is Guardian's own
# signature feat instead of Sentinel's Force Immunity: Fear (98).
MALAK_STARTING_FEATS = [
    39,   # WEAPON_PROF_BLASTER
    43,   # WEAPON_PROF_LIGHTSABER
    44,   # WEAPON_PROF_MELEE_WEAPONS
    55,   # JEDI_DEFENSE
    116,  # FORCE_SENSITIVE
    107,  # JEDI_SENSE
    101,  # FORCE_JUMP (Guardian signature)
]

# Force Powers are NOT class-gated at all in K1 (GameMechanics.md: "zero
# Force Powers differ by Jedi class") -- same 5 base-tier powers as
# Meetra's STARTING_POWERS, no changes needed.
MALAK_STARTING_POWERS = list(STARTING_POWERS)


def build_new_companion_utc() -> UTC:
    """Meetra Surik, level 1 Jedi Sentinel. Ability scores, skill-point
    allocation, and every combat-tuning field below are taken directly from
    Bastila's own real p_bastilla.utc (same class -- her template's
    class_id is 5, Jedi Sentinel) wherever the field
    doesn't scale with level; HP/FP/feats/powers/challenge_rating are
    independently re-derived for level 1 specifically rather than copied
    from Bastila's level-3 values (see STARTING_FEATS/STARTING_POWERS
    above and the HP/FP comments below) -- copying her level-3 numbers
    directly would have overstated a level-1 companion by 2 levels' worth
    of everything, including 9 feats (2 of which -- Two Weapon Fighting,
    Flurry -- are her own level-2/3 bonus feat picks) and her personal
    Battle Meditation feat, which is unique to her character and has no
    place on a different companion's template."""
    utc = UTC()
    utc.resref = ResRef("p_meetra")
    # Tag MUST stay "HK47" -- confirmed via disassembly that ~450 of 498
    # game-wide "HK47" string hits are one generic, shared
    # 9-companion tag-exclusion check every companion is subject to; this
    # is also the exact key generate_trampoline_batch.py's _COMPANION_TAGS
    # now carries for her ("hk47": "HK47"). Changing this tag would both
    # break that shared safety check AND desync her from the class-change/
    # additional-feats codegen that resolves her by this same tag.
    utc.tag = "HK47"
    utc.first_name = LocalizedString.from_english("Meetra")
    utc.last_name = LocalizedString.from_english("Surik")
    utc.conversation = ResRef("k_hmee_dialog")  # placeholder greeting .dlg, not yet built

    # Human female -- appearance_id 122 (P_FEM_C_MED_01), matched to a
    # real PC save's Mod_PlayerList entry (Appearance_Type=122,
    # PortraitId=6, Gender=1, Race=6). Same PC party-member body-row
    # family as an alternate pick (107=P_FEM_B_MED_01, just a different
    # body variant letter) -- still guaranteed to render correctly under
    # EVERY equippable clothing/armor/robe in the game.
    utc.race_id = 6
    utc.gender_id = 1
    utc.appearance_id = 122
    # portrait_id 6 (po_pfhc1) is her body model's real, correct native
    # pairing (confirmed against a real PC save: Appearance_Type=122,
    # PortraitId=6). An earlier diagnostic swap to row 11 (appearance
    # 107's own pairing, NOT hers) was left in place mid-investigation
    # after portrait 6 showed blank/white specifically on the
    # party-selection screen once -- that test was never actually
    # concluded (no record of whether 11 rendering correctly meant the
    # bug was portrait-6-specific, or whether it was something tied to
    # her reusing HK-47's tag/slot instead). Reverted back to the correct
    # pairing (2026-09-27) -- verify the party-select screen specifically
    # when next testing her live, since that's the one screen this was
    # ever reported broken on.
    utc.portrait_id = 6
    # Bastila's own soundset (75) is HER dedicated VO bank (lines recorded
    # specifically for her dialogue) -- not reusable for a different
    # character's combat barks/acknowledgements. Left at the UTC default
    # (0) rather than guessed; assign a real generic female soundset before
    # this ships if 0 turns out to render silent/wrong in a live test (not
    # yet verified).
    utc.soundset_id = 0

    # Ability scores -- STR/INT/CHA kept from Bastila's real template;
    # DEX/CON/WIS deliberately adjusted (2026-09-27) to 14/14/18.
    utc.strength = 12
    utc.dexterity = 14
    utc.constitution = 14
    utc.intelligence = 10
    utc.wisdom = 18
    utc.charisma = 15

    # Skill allocation also copied directly from Bastila -- NOT a level-3
    # total needing to be scaled down. Jedi Sentinel skillpointbase=4 +
    # INT-10 modifier(0), x4 at level 1 = 16 points to spend, capped at
    # (level+3)=4 ranks per class skill; Bastila's Awareness=4/Treat
    # Injury=4 is exactly two class skills hit at their level-1 cap, 0
    # elsewhere -- a genuine level-1 allocation pattern, not a higher-level
    # accumulation.
    utc.computer_use = 0
    utc.demolitions = 0
    utc.stealth = 0
    utc.awareness = 4
    utc.persuade = 0
    utc.repair = 0
    utc.security = 0
    utc.treat_injury = 4

    # Level 1 HP/FP, re-derived for the adjusted CON/WIS above (2026-09-27)
    # -- classes.2da: JediSentinel hitdie=8, forcedie=6. KOTOR grants max
    # hit-die value at level 1 (not rolled), same for the force die:
    # HP = 8 + CON mod(+2 from CON 14) = 10; FP = 6 + WIS mod(+4 from
    # WIS 18) = 10. The companion auto-level-sync mechanism takes over
    # from here as the PC's own level climbs, same as every other
    # companion -- this is only the from-creation baseline.
    utc.current_hp = 10
    utc.max_hp = 10
    utc.hp = 10
    # No current_fp field on this UTC class (only max_fp/fp exist) --
    # confirmed via a direct vars() dump before writing this, not assumed.
    utc.max_fp = 10
    utc.fp = 10

    utc.save_will = 0
    utc.save_fortitude = 0
    utc.alignment = 70  # light-leaning default, matching Bastila's own -- purely a roleplay/dialogue-gating value, not mechanically load-bearing given her placeholder-only dialogue
    utc.challenge_rating = 1.0  # level-1-appropriate; Bastila's own template is 3.0 at class_level 3

    # Every field below is a combat-AI/behavior tuning constant, not
    # level-dependent -- copied directly from Bastila's real template.
    utc.faction_id = 2
    utc.perception_id = 11
    utc.walkrate_id = 7
    utc.natural_ac = 0
    utc.reflex_bonus = 0
    utc.willpower_bonus = 0
    utc.fortitude_bonus = 0
    utc.morale = 0
    utc.morale_recovery = 0
    utc.morale_breakpoint = 0
    utc.multiplier_set = 0
    utc.blindspot = 0.0
    utc.body_variation = 1
    utc.texture_variation = 1
    utc.min1_hp = False
    utc.no_perm_death = True  # companions can't be permanently killed, only knocked out -- must match every other companion
    utc.party_interact = False
    utc.disarmable = False
    utc.not_reorienting = False
    utc.plot = False
    utc.is_pc = False

    # k_hen_* are the shared generic Henchman-framework hooks every real
    # companion's template points at, byte-identical across Bastila/
    # Juhani/Carth (confirmed directly) -- not character-specific, safe to
    # reuse verbatim. FIX: this build previously only set on_dialog/
    # on_spawn, missing on_attacked/on_blocked/on_damaged/on_end_round/
    # on_heartbeat/on_notice entirely -- found live (2026-09-29) via
    # Meetra not naturally following the party, which on_heartbeat
    # (k_hen_heartbt01) is what actually drives.
    utc.on_dialog = ResRef("k_hen_dialogue01")
    utc.on_spawn = ResRef("k_hen_spawn01")
    utc.on_attacked = ResRef("k_hen_attacked01")
    utc.on_blocked = ResRef("k_hen_blocked01")
    utc.on_damaged = ResRef("k_hen_damage01")
    utc.on_end_round = ResRef("k_hen_combend01")
    utc.on_heartbeat = ResRef("k_hen_heartbt01")
    utc.on_notice = ResRef("k_hen_percept01")

    utc.classes = [UTCClass(5, 1)]  # CLASS_TYPE_JEDISENTINEL, level 1
    utc.classes[0].powers = list(STARTING_POWERS)
    utc.feats = list(STARTING_FEATS)

    return utc


def write_new_companion_template(override_dir: str) -> None:
    utc = build_new_companion_utc()
    gff = dismantle_utc(utc)
    path = os.path.join(override_dir, "p_meetra.utc")
    write_gff(gff, path)
    print(f"  wrote {path}")


def deploy_malak_spawn_script(override_dir: str) -> None:
    """k_hmal_spawn01.ncs is precompiled and checked into extender/
    scripts_src/ (see build_malak_head_model.py-adjacent convention --
    same "no compiler needed at runtime" reasoning patch_item_suppression.py
    already uses for its own mode variants). Just a copy, same shape as
    deploy_vanilla_trigger()'s own NCS deploys."""
    src = os.path.join(SRC_DIR, "k_hmal_spawn01.ncs")
    dest = os.path.join(override_dir, "k_hmal_spawn01.ncs")
    shutil.copy2(src, dest)
    print(f"  deployed spawn script -> {dest}")


def _party_npc_juhani_appearance_row(game_dir: str) -> int:
    """Looked up by label, not a hardcoded row index (real appearance.2da
    row numbers shift depending on other Override edits already applied,
    e.g. AP_Malak_Companion from an earlier pipeline version). Only needs
    to be ANY safe, ordinary humanoid party-member appearance now that
    build_malak_companion_utc()'s OnSpawn self-applies EffectDisguise --
    Juhani's real row is a genuine Guardian-class companion (matching
    Malak's own class), but nothing here depends on that specifically."""
    override_dir = os.path.join(game_dir, "Override")
    appearance_path = os.path.join(override_dir, "appearance.2da")
    if os.path.isfile(appearance_path):
        with open(appearance_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("appearance", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)
    for i in range(twoda.get_height()):
        if twoda.get_cell(i, "label") == "Party_NPC_Juhani":
            return i
    raise RuntimeError("appearance.2da row 'Party_NPC_Juhani' not found")


def build_malak_companion_utc(appearance_id: int, portrait_id: int) -> UTC:
    """Darth Malak, level 1 Jedi Guardian. Same construction method as
    build_new_companion_utc() above, but based on Juhani's real
    p_juhani.utc instead of Bastila's -- she's the one real KOTOR1
    companion who is actually class_id 3 (Jedi Guardian), confirmed
    directly via pykotor (str/dex/con/int/wis/cha=13/16/14/14/12/13,
    faction_id=2/perception_id=11/walkrate_id=7 -- same combat-tuning
    constants Bastila's template also uses, confirming these are
    companion-universal, not class-specific). HP/FP independently
    re-derived for level 1 (not copied from her level-6 accumulated
    values), same reasoning as Meetra's own build.

    appearance_id/portrait_id are parameters, not hardcoded -- real row
    indices _party_npc_juhani_appearance_row()/ensure_malak_portrait_row()
    just resolved/added, and must be found before this is called (see
    main()). appearance_id is a fallback only, not the real look -- see
    utc.on_spawn below."""
    utc = UTC()
    utc.resref = ResRef("p_malak")
    # Tag MUST stay "HK47" -- same slot/reasoning as Meetra's build above.
    utc.tag = "HK47"
    utc.first_name = LocalizedString.from_english("Darth")
    utc.last_name = LocalizedString.from_english("Malak")
    utc.conversation = ResRef("k_hmal_dialog")  # placeholder greeting .dlg

    # appearance_id is just a safe fallback humanoid row (see
    # _party_npc_juhani_appearance_row) -- the real, visible appearance
    # comes from OnSpawn's EffectDisguise instead (see utc.on_spawn
    # below), which overrides it entirely once applied.
    utc.race_id = 6
    utc.subrace_id = 0
    utc.gender_id = 0
    utc.appearance_id = appearance_id
    utc.portrait_id = portrait_id
    utc.soundset_id = 0  # placeholder, same caveat as Meetra's own soundset_id

    # Ability scores based on Juhani's real template (the one real Jedi
    # Guardian companion), confirmed via pykotor -- STR/DEX deliberately
    # swapped from her values (13/16 -> 16/13) to better fit Malak as a
    # heavy melee bruiser rather than an agile duelist.
    utc.strength = 16
    utc.dexterity = 13
    utc.constitution = 14
    utc.intelligence = 14
    utc.wisdom = 12
    utc.charisma = 13

    # Guardian skillpointbase=2 + INT-14 mod(+2), x4 at level 1 = 16
    # points, capped at 4 ranks/class skill at level 1 -- same "two class
    # skills at cap, 0 elsewhere" shape as Meetra's Awareness/Treat Injury
    # pick above.
    utc.computer_use = 0
    utc.demolitions = 0
    utc.stealth = 0
    utc.awareness = 4
    utc.persuade = 0
    utc.repair = 0
    utc.security = 0
    utc.treat_injury = 4

    # Level 1 HP/FP, independently derived -- classes.2da: JediGuardian
    # hitdie=10, forcedie=4 (confirmed directly via pykotor). HP = 10 +
    # CON mod(+2 from CON 14) = 12; FP = 4 + WIS mod(+1 from WIS 12) = 5.
    utc.current_hp = 12
    utc.max_hp = 12
    utc.hp = 12
    utc.max_fp = 5
    utc.fp = 5

    utc.save_will = 0
    utc.save_fortitude = 0
    utc.alignment = 0  # full dark side -- roleplay/dialogue-gating value only, matches his character
    utc.challenge_rating = 1.0  # level-1-appropriate

    # Combat-tuning constants -- confirmed identical on Juhani's AND
    # Bastila's real templates, so companion-universal, not class-specific.
    utc.faction_id = 2
    utc.perception_id = 11
    utc.walkrate_id = 7
    utc.natural_ac = 0
    utc.reflex_bonus = 0
    utc.willpower_bonus = 0
    utc.fortitude_bonus = 0
    utc.morale = 0
    utc.morale_recovery = 0
    utc.morale_breakpoint = 0
    utc.multiplier_set = 0
    utc.blindspot = 0.0
    utc.body_variation = 1
    utc.texture_variation = 1
    utc.min1_hp = False
    utc.no_perm_death = True
    utc.party_interact = False
    utc.disarmable = False
    utc.not_reorienting = False
    utc.plot = False
    utc.is_pc = False

    # Same fix as build_new_companion_utc() (Meetra) -- this build only
    # ever set on_dialog/on_spawn, missing the rest of the shared k_hen_*
    # companion-framework suite entirely.
    utc.on_dialog = ResRef("k_hen_dialogue01")
    # k_hmal_spawn01 runs the real k_hen_spawn01 init, then self-applies a
    # permanent EffectDisguise(DISGUISE_TYPE_N_DARTHMALAK) -- his real,
    # unmodified boss appearance (row 21). Replaces the custom appearance-
    # row/spliced-head-model approach entirely -- see that script's own
    # header comment. appearance_id above just needs to be ANY safe,
    # ordinary humanoid party-member row now (never actually seen once the
    # disguise effect lands), not a custom Malak-specific one.
    utc.on_spawn = ResRef("k_hmal_spawn01")
    utc.on_attacked = ResRef("k_hen_attacked01")
    utc.on_blocked = ResRef("k_hen_blocked01")
    utc.on_damaged = ResRef("k_hen_damage01")
    utc.on_end_round = ResRef("k_hen_combend01")
    utc.on_heartbeat = ResRef("k_hen_heartbt01")
    utc.on_notice = ResRef("k_hen_percept01")

    utc.classes = [UTCClass(3, 1)]  # CLASS_TYPE_JEDIGUARDIAN, level 1
    utc.classes[0].powers = list(MALAK_STARTING_POWERS)
    utc.feats = list(MALAK_STARTING_FEATS)

    return utc


def write_malak_companion_template(override_dir: str, appearance_id: int, portrait_id: int) -> None:
    utc = build_malak_companion_utc(appearance_id, portrait_id)
    gff = dismantle_utc(utc)
    path = os.path.join(override_dir, "p_malak.utc")
    write_gff(gff, path)
    print(f"  wrote {path}")


def deploy_vanilla_trigger(override_dir: str, new_companion: int) -> None:
    """Copies whichever precompiled variant matches `new_companion` (0=
    vanilla, 1=mystery/Meetra, 2=malak) to Override/apo_hk47_orig.ncs --
    the exact filename the companion-suppression wrapper's
    ExecuteScript("apo_hk47_orig", OBJECT_SELF) call expects (see
    generate_companion_suppressors.py's WRAPPER_TEMPLATE). MUST run on
    every Connect regardless of new_companion's value, not just when it's
    on -- restoring the true vanilla trigger when the option is off again
    is just as much this function's job as installing either replacement,
    same restore-on-switch discipline as Loot Mode."""
    src = _TRIGGER_NCS_BY_MODE[new_companion]
    with open(src, "rb") as f:
        data = f.read()
    dest = os.path.join(override_dir, "apo_hk47_orig.ncs")
    with open(dest, "wb") as f:
        f.write(data)
    label = {0: "vanilla", 1: "new-companion (mystery)", 2: "new-companion (malak)"}[new_companion]
    print(f"  deployed {label} trigger -> {dest} ({len(data)} bytes)")


def build_placeholder_greeting_dlg() -> DLG:
    """Her entire personal Ebon Hawk subplot (252 real dialogue entries in
    the vanilla k_hhkd_dialog, confirmed clean to cut -- no
    cross-companion or global-variable dependencies beyond her own
    content) replaced with one greeting line and nothing else -- no
    replies, so the conversation just ends after it plays."""
    dlg = DLG()
    entry = DLGEntry()
    entry.text = LocalizedString.from_english(
        "It's been awhile since we last seen each other, its great to see you!"
    )
    entry.speaker = ""
    entry.delay = -1
    entry.camera_angle = 0
    dlg.starters.append(DLGLink(entry))
    return dlg


def write_placeholder_dlg(override_dir: str) -> None:
    dlg = build_placeholder_greeting_dlg()
    gff = dismantle_dlg(dlg, Game.K1)
    path = os.path.join(override_dir, "k_hmee_dialog.dlg")
    write_gff(gff, path)
    print(f"  wrote {path}")


def build_malak_placeholder_greeting_dlg() -> DLG:
    """Same shape as build_placeholder_greeting_dlg() above -- one
    greeting line, no replies, conversation just ends after it plays.
    Musing/reflective tone, a subtle nod to shared history without
    naming names -- works whether or not this particular playthrough
    leans into that reveal."""
    dlg = DLG()
    entry = DLGEntry()
    entry.text = LocalizedString.from_english(
        "Interesting circumstances we find ourselves in -- allies, of all "
        "things, while a false Malak leads the Sith. Fate has a sense of "
        "humor, it seems... and perhaps a memory longer than either of us "
        "would like."
    )
    entry.speaker = ""
    entry.delay = -1
    entry.camera_angle = 0
    dlg.starters.append(DLGLink(entry))
    return dlg


def write_malak_placeholder_dlg(override_dir: str) -> None:
    dlg = build_malak_placeholder_greeting_dlg()
    gff = dismantle_dlg(dlg, Game.K1)
    path = os.path.join(override_dir, "k_hmal_dialog.dlg")
    write_gff(gff, path)
    print(f"  wrote {path}")


def ensure_malak_appearance_row(game_dir: str) -> int:
    """Adds a clone of appearance.2da row 21 (Unique_Darth_Malak, his real
    vanilla cutscene/boss appearance) with ONE field changed from the
    original: modeltype 'F' -> 'B' (the same category every real working
    companion body uses -- Meetra/Carth confirmed -- instead of 'F',
    his vanilla row's value, confirmed live to mean "no visible AI-combat
    animation at all"). modela stays "N_DarthMalak", his real model --
    the modified n_darthmalak_ap model (supermodel NULL -> P_CarthBB, for
    walk/run/follow behavior) crashed on area load, root cause not yet
    understood; reverted to the last confirmed-stable config pending
    further research (see deploy_malak_body_model(), currently unused).

    Deliberately a NEW row, not an edit to row 21 itself -- his 7 real
    vanilla story appearances (Leviathan/Star Forge) must keep using the
    original, untouched row and model. Idempotent across repeated
    Connects: re-checks modela/modeltype even if the row already exists,
    same "don't let a stale value from an earlier version of this script
    silently survive" reasoning as ensure_malak_portrait_row() below."""
    override_dir = os.path.join(game_dir, "Override")
    appearance_path = os.path.join(override_dir, "appearance.2da")
    if os.path.isfile(appearance_path):
        with open(appearance_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("appearance", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)

    label = "AP_Malak_Companion"
    row = None
    for i in range(twoda.get_height()):
        if twoda.get_cell(i, "label") == label:
            row = i
            break

    if row is None:
        row = twoda.add_row(str(twoda.get_height()))
        for header in twoda.get_headers():
            twoda.set_cell(row, header, twoda.get_cell(21, header))
        twoda.set_cell(row, "label", label)

    changed = False
    if twoda.get_cell(row, "modeltype") != "B":
        twoda.set_cell(row, "modeltype", "B")
        changed = True
    if twoda.get_cell(row, "modela") != "N_DarthMalak":
        twoda.set_cell(row, "modela", "N_DarthMalak")
        changed = True

    if changed:
        os.makedirs(override_dir, exist_ok=True)
        write_2da(twoda, appearance_path)
        print(f"  updated appearance.2da row {row} ({label}, modeltype=B, modela=N_DarthMalak) -> {appearance_path}")
    return row


def ensure_malak_heads_row(game_dir: str) -> int:
    """Adds a 'p_malakh' row to Override/heads.2da if not already present.
    This is the standalone head model the game's own headhook system
    attaches at runtime to whichever body appearance references it via
    normalhead -- see p_malakh.mdl's own build notes (extender/raw_
    override_files/, built by grafting Malak's real facial geometry onto
    a proven male-PC head chassis, main face mesh converted to a plain
    rigid attach since pykotor's MDL writer can't correctly serialize a
    modified skin mesh's bind-pose data). Idempotent, same add_row()
    precedent as ensure_malak_portrait_row()."""
    override_dir = os.path.join(game_dir, "Override")
    heads_path = os.path.join(override_dir, "heads.2da")
    if os.path.isfile(heads_path):
        with open(heads_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("heads", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)

    for i in range(twoda.get_height()):
        if twoda.get_cell(i, "head") == "p_malakh":
            return i

    row = twoda.add_row(str(twoda.get_height()))
    twoda.set_cell(row, "head", "p_malakh")
    os.makedirs(override_dir, exist_ok=True)
    write_2da(twoda, heads_path)
    print(f"  added heads.2da row {row} (p_malakh) -> {heads_path}")
    return row


def ensure_malak_appearance_row_v2(game_dir: str, normalhead_id: int) -> int:
    """Adds a clone of appearance.2da's 'Party_NPC_Carth' row -- NOT
    'P_MAL_A_MED_01' (tried first, reverted): that row's naming
    (P_<SEX>_<BUILD>_<VARIANT>) and the fact every one of its siblings
    only differs by which of a handful of normalhead face indices it
    points at strongly indicates it's a player-character-CREATION-SCREEN
    template, selected through the "Customize" UI at game start, never
    spawned as a live NPC by the game itself -- its head-attachment may
    depend on customization-screen-specific code a companion recruit
    script never triggers, which would explain the body rendering fine
    while the separate head model silently failed to attach at all.
    Carth's own row proves the identical mechanism (separable head via
    normalhead + full modelb..j armor-variant set) working correctly
    every single day in ordinary gameplay, since that's exactly how his
    own head/body render -- a much smaller, better-verified change:
    inherit his proven wiring, only repoint normalhead.

    Looked up by label, not a hardcoded row index, same reasoning as
    ensure_malak_portrait_row()'s appearance_id parameter."""
    override_dir = os.path.join(game_dir, "Override")
    appearance_path = os.path.join(override_dir, "appearance.2da")
    if os.path.isfile(appearance_path):
        with open(appearance_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("appearance", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)

    template_row = None
    label = "AP_Malak_Companion"
    row = None
    for i in range(twoda.get_height()):
        cell_label = twoda.get_cell(i, "label")
        if cell_label == "Party_NPC_Carth":
            template_row = i
        if cell_label == label:
            row = i

    if template_row is None:
        raise RuntimeError("appearance.2da row 'Party_NPC_Carth' not found")

    changed = False
    if row is None:
        row = twoda.add_row(str(twoda.get_height()))
        changed = True

    # Re-clone every field from the template each time, not just on first
    # creation -- this row previously belonged to the old row-21-clone
    # approach (modela=N_DarthMalak, no modelb..j), and label-match alone
    # would otherwise let those stale values silently survive under the
    # same marker, same class of bug ensure_malak_portrait_row() already
    # guards against for appearancenumber.
    for header in twoda.get_headers():
        if header == "label":
            continue
        template_val = twoda.get_cell(template_row, header)
        if twoda.get_cell(row, header) != template_val:
            twoda.set_cell(row, header, template_val)
            changed = True
    if twoda.get_cell(row, "label") != label:
        twoda.set_cell(row, "label", label)
        changed = True

    if twoda.get_cell(row, "normalhead") != str(normalhead_id):
        twoda.set_cell(row, "normalhead", str(normalhead_id))
        changed = True

    if changed:
        os.makedirs(override_dir, exist_ok=True)
        write_2da(twoda, appearance_path)
        print(f"  updated appearance.2da row {row} ({label}, normalhead={normalhead_id}) -> {appearance_path}")
    return row


def deploy_malak_head_model(override_dir: str) -> None:
    """p_malakh.mdl/.mdx are checked-in source assets (extender/raw_
    override_files/) -- see ensure_malak_heads_row()'s docstring for how
    they were built."""
    for ext in ("mdl", "mdx"):
        src = os.path.join(RAW_OVERRIDE_DIR, f"p_malakh.{ext}")
        dest = os.path.join(override_dir, f"p_malakh.{ext}")
        shutil.copy2(src, dest)
    print(f"  deployed head model -> {override_dir}\\p_malakh.mdl/.mdx")


def ensure_malak_portrait_row(game_dir: str, appearance_id: int) -> int:
    """Adds a 'po_malak' row to Override/portraits.2da if not already
    present -- idempotent across repeated Connects, same add_row()
    precedent patch_tsl_powers.py already established for spells.2da (see
    that script's own k1_dir/chitin.key base-2DA resolution for the exact
    precedent this mirrors). No TLK entry needed -- portraits.2da carries
    no name/label strref column at all (confirmed via its real headers:
    baseresref, sex, appearancenumber, race, inanimatetype, plot, lowgore,
    appearance_s, appearance_l, forpc, baseresrefe/ve/vve/vvve).

    Returns the row index to use as build_malak_companion_utc()'s
    portrait_id -- deliberately NOT a hardcoded constant, to avoid any
    assert-vs-drift risk if the base table's real height ever changes."""
    override_dir = os.path.join(game_dir, "Override")
    portraits_path = os.path.join(override_dir, "portraits.2da")
    if os.path.isfile(portraits_path):
        with open(portraits_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("portraits", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)

    for i in range(twoda.get_height()):
        if twoda.get_cell(i, "baseresref") == "po_malak":
            # Keep appearancenumber current -- it must track whichever
            # appearance.2da row build_malak_companion_utc() is actually
            # using (the modeltype=B clone, not the raw literal 21), and
            # a stale value here from before that clone existed would
            # otherwise silently survive future re-runs.
            if twoda.get_cell(i, "appearancenumber") != str(appearance_id):
                twoda.set_cell(i, "appearancenumber", str(appearance_id))
                write_2da(twoda, portraits_path)
                print(f"  updated portraits.2da row {i} (po_malak) appearancenumber -> {appearance_id}")
            return i

    row = twoda.add_row(str(twoda.get_height()))
    # Shape matches existing male companion rows (Carth/Canderous), just
    # pointed at Malak's own real appearance/race.
    twoda.set_cell(row, "baseresref", "po_malak")
    twoda.set_cell(row, "sex", "0")
    twoda.set_cell(row, "appearancenumber", str(appearance_id))
    twoda.set_cell(row, "race", "6")
    twoda.set_cell(row, "plot", "0")
    twoda.set_cell(row, "forpc", "0")
    os.makedirs(override_dir, exist_ok=True)
    write_2da(twoda, portraits_path)
    print(f"  added portraits.2da row {row} (po_malak) -> {portraits_path}")
    return row


def ensure_malak_gear_restriction(game_dir: str) -> None:
    """Ors MALAK_DENYSUBRACE_BIT into Override/baseitems.2da's denysubrace
    cell for every row in MALAK_RESTRICTED_GEAR_LABELS -- see that
    constant's own comment for why these 14 rows specifically (Head/Body/
    Hands only) and why subrace_id=2/Beast. OR, not overwrite: Jedi_Robe
    already legitimately carries 0x2 (denying Wookiees) -- this must
    become 0x6 (both bits), not silently drop the existing restriction.
    Idempotent: re-running with the bit already set is a harmless no-op,
    same as every other ensure_malak_*() function."""
    override_dir = os.path.join(game_dir, "Override")
    baseitems_path = os.path.join(override_dir, "baseitems.2da")
    if os.path.isfile(baseitems_path):
        with open(baseitems_path, "rb") as f:
            twoda = read_2da(f.read())
    else:
        inst = Installation(game_dir)
        twoda = read_2da(inst.resource("baseitems", ResourceType.TwoDA, [SearchLocation.CHITIN]).data)

    label_to_row = {twoda.get_cell(i, "label"): i for i in range(twoda.get_height())}
    changed = False
    for label in MALAK_RESTRICTED_GEAR_LABELS:
        row = label_to_row.get(label)
        if row is None:
            print(f"  WARNING: baseitems.2da row {label!r} not found, skipping")
            continue
        current = twoda.get_cell(row, "denysubrace")
        current_val = int(current, 16) if current and current.startswith("0x") else int(current or "0")
        new_val = current_val | MALAK_DENYSUBRACE_BIT
        if new_val != current_val:
            twoda.set_cell(row, "denysubrace", f"0x{new_val:08X}")
            changed = True

    if changed:
        os.makedirs(override_dir, exist_ok=True)
        write_2da(twoda, baseitems_path)
        print(f"  updated baseitems.2da denysubrace on {len(MALAK_RESTRICTED_GEAR_LABELS)} rows -> {baseitems_path}")
    else:
        print("  baseitems.2da denysubrace already correct, no change needed")


def deploy_malak_body_model(override_dir: str) -> None:
    """n_darthmalak_ap.mdl/.mdx are checked-in source assets (extender/
    raw_override_files/), same category as po_malak.tpc -- built once by
    reading the real n_darthmalak.mdl/.mdx, changing ONLY `name` (to this
    new resref) and `supermodel` (NULL -> P_CarthBB), and round-trip
    verified byte-for-byte identical otherwise (same 111 nodes, same 66
    animations) before being checked in. Never touches the original
    n_darthmalak files his 7 real vanilla story appearances still use."""
    for ext in ("mdl", "mdx"):
        src = os.path.join(RAW_OVERRIDE_DIR, f"n_darthmalak_ap.{ext}")
        dest = os.path.join(override_dir, f"n_darthmalak_ap.{ext}")
        shutil.copy2(src, dest)
    print(f"  deployed body model -> {override_dir}\\n_darthmalak_ap.mdl/.mdx")


def deploy_malak_portrait(override_dir: str) -> None:
    """po_malak.tpc is a checked-in source asset (extender/raw_override_
    files/, the project's existing checked-in-binary-asset folder --
    same category as the .dlg placeholders already there), not generated
    -- built once from the game's own title-screen Malak art, round-trip
    verified as a genuine 64x64 RGB TPC matching vanilla companion
    portraits' own format (e.g. po_pcarth)."""
    src = os.path.join(RAW_OVERRIDE_DIR, "po_malak.tpc")
    dest = os.path.join(override_dir, "po_malak.tpc")
    shutil.copy2(src, dest)
    print(f"  deployed portrait -> {dest}")


def _connected_new_companion() -> int:
    """Same read-_slot_data.json pattern as patch_item_suppression.py's
    _connected_progression_system() and generate_trampoline_batch.py's own
    copy of this helper -- 0 (real vanilla) if the file doesn't exist or
    doesn't parse."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return 0
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("new_companion", 0))
    except Exception:
        return 0


def main():
    game_dir = DEFAULT_GAME_DIR
    new_companion = None
    for arg in sys.argv[1:]:
        if arg.startswith("--game-dir="):
            game_dir = arg[len("--game-dir="):]
        elif arg.startswith("--new-companion="):
            new_companion = int(arg[len("--new-companion="):])
    if new_companion is None:
        new_companion = _connected_new_companion()

    override_dir = os.path.join(game_dir, "Override")
    deploy_vanilla_trigger(override_dir, new_companion)
    if new_companion == 1:
        # Only meaningful when this specific mode is active -- when it's
        # not, p_meetra.utc/k_hmee_dialog.dlg being absent or stale in
        # Override is harmless, since nothing points at them.
        write_new_companion_template(override_dir)
        write_placeholder_dlg(override_dir)
    elif new_companion == 2:
        # v3: EffectDisguise(DISGUISE_TYPE_N_DARTHMALAK), self-applied on
        # spawn (k_hmal_spawn01) -- his real, unmodified boss appearance
        # (row 21), a real standard KOTOR effect (the same mechanism the
        # game's own Sith Armor disguise uses). Supersedes v2 (Carth's body
        # + a hand-spliced head model, ensure_malak_appearance_row_v2/
        # ensure_malak_heads_row/deploy_malak_head_model, left in place
        # below but unused) and the original row-21-clone approach --
        # three separate model/appearance-row attempts deployed without
        # errors but never actually rendered live, one suspected of
        # causing a real crash. appearance_id only needs to be ANY safe,
        # ordinary humanoid party-member row now (never actually seen once
        # the disguise effect lands on spawn) -- reuses Juhani's real row
        # directly (a genuine Guardian-class companion, matching Malak's
        # own class, but not load-bearing).
        deploy_malak_spawn_script(override_dir)
        appearance_id = _party_npc_juhani_appearance_row(game_dir)
        portrait_id = ensure_malak_portrait_row(game_dir, appearance_id)
        write_malak_companion_template(override_dir, appearance_id, portrait_id)
        write_malak_placeholder_dlg(override_dir)
        deploy_malak_portrait(override_dir)


if __name__ == "__main__":
    main()
