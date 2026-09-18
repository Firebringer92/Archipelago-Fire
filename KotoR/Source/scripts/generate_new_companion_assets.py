"""
Builds and deploys the assets for Options.py's new_companion toggle -- Meetra
Surik, the Jedi Sentinel replacing HK-47 in his party slot. See
DEVELOPMENT_HISTORY.md's "New Companion: replacing HK-47 with an
original human character" section for the full feasibility research and
__init__.py/Locations.py/Items.py/Rules.py/
generate_trampoline_batch.py for the AP-side wiring this feeds.

Three pieces, all handled here:
1. p_meetra.utc (build_new_companion_utc/write_new_companion_template) --
   her level-1 stat block, built from Bastila's real template as a guide.
2. The vanilla Tatooine trigger's dual variant (deploy_vanilla_trigger) --
   apo_hk47_vanilla.ncs (true vanilla, spawns p_hk47) vs. apo_hk47_new.ncs
   (identical except spawns p_meetra -- confirmed via a compile+disassemble+
   diff pass showing exactly 1 opcode differs across all 38, the template
   string). Both are precompiled and checked into extender/scripts_src/,
   same "no compiler needed at runtime" convention patch_item_suppression.py
   already uses for its own mode variants -- this script just copies the
   right one to Override/apo_hk47_orig.ncs, the name the companion-
   suppression wrapper's ExecuteScript call expects.
3. k_hmee_dialog.dlg (build_placeholder_greeting_dlg/write_placeholder_dlg)
   -- her entire personal Ebon Hawk subplot replaced with one greeting
   line, cut entirely for this option. Referenced by the .utc's
   own `conversation` field.

Usage: python generate_new_companion_assets.py [--game-dir=<path>] [--new-companion=0|1]
  Deploys all 3 pieces to that install's Override folder in one call.
  Meant to be invoked the same way patch_item_suppression.py's other
  conditional deploy steps are -- once per Connect, gated on
  _slot_data.json's new_companion flag -- not a one-time setup step:
  deploy_vanilla_trigger() must run on EVERY connect regardless of the
  flag's value, to restore the true vanilla trigger when new_companion is
  off just as much as to install the new one when it's on. --new-companion=
  overrides reading _slot_data.json, for standalone testing.
"""
import json
import os
import sys

from pykotor.common.language import LocalizedString
from pykotor.common.misc import Game, ResRef
from pykotor.resource.formats.gff import write_gff
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGLink, dismantle_dlg
from pykotor.resource.generics.utc import UTC, UTCClass, dismantle_utc

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")

VANILLA_TRIGGER_NCS = os.path.join(SRC_DIR, "apo_hk47_vanilla.ncs")
NEW_TRIGGER_NCS = os.path.join(SRC_DIR, "apo_hk47_new.ncs")

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
    # EVERY equippable clothing/armor/robe in the game. portrait_id 6
    # (po_pfhc1) confirmed via portraits.2da as appearance 122's real
    # paired portrait (appearancenumber=122, forpc=1), not an arbitrary
    # pick.
    utc.race_id = 6
    utc.gender_id = 1
    utc.appearance_id = 122
    utc.portrait_id = 6
    # Bastila's own soundset (75) is HER dedicated VO bank (lines recorded
    # specifically for her dialogue) -- not reusable for a different
    # character's combat barks/acknowledgements. Left at the UTC default
    # (0) rather than guessed; assign a real generic female soundset before
    # this ships if 0 turns out to render silent/wrong in a live test (not
    # yet verified).
    utc.soundset_id = 0

    # Ability scores copied directly from Bastila's real template -- these
    # don't scale with level in this engine, so her level-3 values are
    # exactly as valid a level-1 baseline as any other level for the same
    # character build.
    utc.strength = 12
    utc.dexterity = 18
    utc.constitution = 12
    utc.intelligence = 10
    utc.wisdom = 12
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

    # Level 1 HP/FP, independently derived (NOT copied from Bastila's
    # level-3 27/18) -- classes.2da: JediSentinel hitdie=8, forcedie=6.
    # KOTOR grants max hit-die value at level 1 (not rolled), same for the
    # force die: HP = 8 + CON mod(+1 from CON 12) = 9; FP = 6 + WIS
    # mod(+1 from WIS 12) = 7. The companion auto-level-sync mechanism
    # takes over from here as the PC's own level climbs, same as every
    # other companion -- this is only the from-creation baseline.
    utc.current_hp = 9
    utc.max_hp = 9
    utc.hp = 9
    # No current_fp field on this UTC class (only max_fp/fp exist) --
    # confirmed via a direct vars() dump before writing this, not assumed.
    utc.max_fp = 7
    utc.fp = 7

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

    # k_hen_dialogue01/k_hen_spawn01 are the shared generic Henchman-
    # framework hooks every real companion's template points at (confirmed
    # by Bastila's own template using the exact same two resrefs) -- not
    # Bastila-specific, safe to reuse verbatim rather than writing new ones.
    utc.on_dialog = ResRef("k_hen_dialogue01")
    utc.on_spawn = ResRef("k_hen_spawn01")

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


def deploy_vanilla_trigger(override_dir: str, new_companion: bool) -> None:
    """Copies whichever precompiled variant matches `new_companion` to
    Override/apo_hk47_orig.ncs -- the exact filename the companion-
    suppression wrapper's ExecuteScript("apo_hk47_orig", OBJECT_SELF) call
    expects (see generate_companion_suppressors.py's WRAPPER_TEMPLATE).
    MUST run on every Connect regardless of new_companion's value, not
    just when it's on -- restoring the true vanilla trigger when the
    option is off again is just as much this function's job as installing
    the new one, same restore-on-switch discipline as Loot Mode."""
    src = NEW_TRIGGER_NCS if new_companion else VANILLA_TRIGGER_NCS
    with open(src, "rb") as f:
        data = f.read()
    dest = os.path.join(override_dir, "apo_hk47_orig.ncs")
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  deployed {'new-companion' if new_companion else 'vanilla'} trigger -> {dest} ({len(data)} bytes)")


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


def _connected_new_companion() -> bool:
    """Same read-_slot_data.json pattern as patch_item_suppression.py's
    _connected_progression_system() and generate_trampoline_batch.py's own
    copy of this helper -- False (real vanilla) if the file doesn't exist
    or doesn't parse."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("new_companion", False))
    except Exception:
        return False


def main():
    game_dir = DEFAULT_GAME_DIR
    new_companion = None
    for arg in sys.argv[1:]:
        if arg.startswith("--game-dir="):
            game_dir = arg[len("--game-dir="):]
        elif arg.startswith("--new-companion="):
            new_companion = arg[len("--new-companion="):] not in ("0", "false", "False")
    if new_companion is None:
        new_companion = _connected_new_companion()

    override_dir = os.path.join(game_dir, "Override")
    deploy_vanilla_trigger(override_dir, new_companion)
    if new_companion:
        # Only meaningful when the option is actually on -- when it's off,
        # p_meetra.utc/k_hmee_dialog.dlg being absent or stale in Override
        # is harmless, since nothing points at them (the vanilla trigger
        # just deployed spawns p_hk47, not p_meetra).
        write_new_companion_template(override_dir)
        write_placeholder_dlg(override_dir)


if __name__ == "__main__":
    main()
