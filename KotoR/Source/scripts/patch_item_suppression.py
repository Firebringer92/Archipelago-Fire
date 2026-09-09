r"""
Wires up item-pickup handling via KOTOR's native Mod_OnAcquirItem module
event (confirmed live via 11 real vanilla scripts already using it -- see
project research notes). What happens to a NON-whitelisted pickup (not
quest_dependent in gear_items.json -- whitelisted items are always left
alone no matter what) depends on the single loot_mode seed option --
see Options.py's LootMode docstring for the full description:

  normal (internal name "skip")  -- nothing is wired up at all, vanilla
    loot behaves exactly like stock KOTOR.
  destroy -- the pickup is destroyed immediately, no replacement (pure
    suppression).
  bonus   -- the pickup is kept, untouched; separately, one random item
    (drawn from the shop_randomize pool) is granted every time a running
    count of genuine non-whitelisted finds crosses a new multiple of 5 --
    see generate_poll_shared.py's CheckPickupCount() for the actual grant
    logic, which lives there now, not in this file's per-acquisition
    handler.
  replace -- the pickup is destroyed and immediately replaced with one
    random item from the same pool, one-for-one.

Two different mechanisms depending on what a module already has (this part
is mode-independent -- only WHAT the shared/wrapper scripts' CONTENT does
changes per mode, never whether a module needs its RIM touched at all):

  - ~86 modules with an EMPTY Mod_OnAcquirItem slot: the field itself has
    to be set (once, to the fixed SHARED_SUPPRESS_RESREF name), which
    means a real GFF edit inside that module's own RIM (module.ifo's
    resref is "module" for every module -- a loose Override copy would
    apply identically to ALL modules and corrupt their other per-module
    data, so this can't go through Override at all). This is the ONLY
    part of this project that directly repacks a base game file, hence
    the backup step -- see restore() / this script's --restore flag.
    Re-running with a DIFFERENT mode later does NOT need another RIM
    edit -- the field already points at SHARED_SUPPRESS_RESREF, only the
    Override file's CONTENT under that name needs to change.

  - 11 modules that ALREADY have a real vanilla script there (map reveals,
    quest-journal triggers keyed on specific pickups) -- these have their
    own unique resref names, so the existing, already-proven
    Override-file-swap trick (same one used for companion suppression)
    works untouched: preserve the original .ncs under a new resref, deploy
    a wrapper that runs it first then adds the pickup-handling check,
    under the ORIGINAL resref name. No RIM/IFO edit needed for these at
    all, in any mode.

Usage:
  python patch_item_suppression.py                          -- apply (backs up first)
  python patch_item_suppression.py --restore                -- restore all patched modules from backup
  python patch_item_suppression.py --game-dir "D:\...\swkotor" -- apply against a non-default install
  python patch_item_suppression.py --force --mode=<destroy|bonus|replace|skip> -- skip reading real
    seed data entirely, apply a manually-chosen mode instead

You must connect once with KotorClient.py before running this (see
README.md Step 6) -- loot_mode comes from your seed's real slot_data,
which KotorClient.py receives over the network on every Connect and
writes to extender/area_trampolines/_slot_data.json for this script to
read (see KotorClient.py's SLOT_DATA_PATH). This works identically
whether you're hosting or joining someone else's multiworld -- neither
needs local access to a generated AP_<seed>.zip at all (found broken
2026-09-04: the previous approach read the zip directly, which only ever
existed on whichever machine ran Generate.py -- a joining player never
has it, so this literally couldn't work for them before).

Doesn't need nwnnsscomp.exe (the NWScript compiler) on a tester's machine:
each mode's shared suppressor and all 11 wrapper scripts are deterministic
given the same gear_items.json whitelist, so precompiled copies for all 3
non-skip modes are checked into extender/scripts_src/ and get used
directly whenever the compiler isn't present. Only someone actually
changing the whitelist and rebuilding needs the compiler -- see
compile_and_deploy() below.
"""
import json
import os
import shutil
import subprocess
import sys

from pykotor.common.misc import ResRef
from pykotor.extract.installation import Installation
from pykotor.resource.formats.rim import read_rim, write_rim
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.type import ResourceType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"


def _arg_value(flag, default):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


GAME_DIR = _arg_value("--game-dir", DEFAULT_GAME_DIR)
MOD_DIR = os.path.join(GAME_DIR, "modules")
OVERRIDE = os.path.join(GAME_DIR, "Override")
from nwnnsscomp_path import resolve_nwnnsscomp  # noqa: E402 -- see that module's docstring
NWNNSSCOMP = resolve_nwnnsscomp()
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
BACKUP_DIR = os.path.join(REPO_ROOT, "extender", "backup", "modules")
# Written by KotorClient.py on every successful Connect -- see its own
# SLOT_DATA_PATH/write_slot_data_for_patch_scripts() for why this replaced
# reading a locally generated AP_<seed>.zip directly (found broken
# 2026-09-04: that file never exists at all for a player joining someone
# ELSE's multiworld, and the old code didn't even filter for THIS
# player's own slot). Same path both scripts must agree on -- kept as a
# plain module-level constant rather than a flag, since there's no
# reason it would ever need to be anywhere else: both this script and
# KotorClient.py compute REPO_ROOT the same way, and the whole point of
# README.md Step 1 is that they live in the same Client folder.
SLOT_DATA_PATH = os.path.join(REPO_ROOT, "extender", "area_trampolines", "_slot_data.json")
# A real tester's checkout only ever has kotor.apworld as a zip in
# custom_worlds/ -- there is no loose worlds/kotor/gear_items.json file to
# find on disk there at all, since the apworld's contents are never
# extracted. This whitelist is a fixed classification tied to the
# apworld's own version, not per-seed data, so package_playerbundle.py
# ships a static copy of it directly alongside this script (found broken
# 2026-09-04, fixed by shipping that copy) -- no cross-checkout dependency
# needed for a PlayerBundle-style install.
#
# BUT a dev checkout (this repo, running scripts/ directly against the
# real Archipelago/worlds/kotor/ folder) never has scripts/gear_items.json
# at all -- package_playerbundle.py only creates it as a packaging step,
# not something that exists by default. Found broken live 2026-09-08
# (FileNotFoundError running this against a real dev-machine test seed)
# -- fixed by falling back to the real source location when the packaged
# copy isn't present, so this script works in both layouts.
GEAR_JSON = os.path.join(REPO_ROOT, "scripts", "gear_items.json")
if not os.path.isfile(GEAR_JSON):
    GEAR_JSON = os.path.join(REPO_ROOT, "Archipelago", "worlds", "kotor", "gear_items.json")

# Fixed deploy name every empty-slot module's Mod_OnAcquirItem field points
# at -- never changes across modes, so the RIM edit only ever needs to
# happen once (see module docstring). The dev-side SOURCE files carry a
# mode suffix instead (ap_item_suppress_<mode>.nss/.ncs) so all 3 non-skip
# modes' precompiled fallbacks can coexist in the repo simultaneously.
SHARED_SUPPRESS_RESREF = "ap_item_suppress"

# name, module, original resref -- the 11 modules with a real vanilla
# Mod_OnAcquirItem script already in place. Confirmed via prior research
# (map reveal / quest-journal-on-pickup logic); module names resolved by
# scanning each candidate module's own IFO for a matching non-empty field.
EXISTING_SCRIPT_NAMES = {
    "k_pdan_itemacq", "k_pdan_14b_itmaq", "k_pebn_acquire",
    "k_pkas24aa_acqui", "k_pkas25aa_acqui", "k_ptar_acquire",
    "k_ptar_acquire04", "k_ptar_acquire05", "tar09_acquire",
    "k_ptat18aa_acqui", "k_ptat20aa_acqui",
}

WRAPPER_TEMPLATE = """// Item-pickup wrapper -- runs {module}'s real vanilla
// Mod_OnAcquirItem script ({resref}, preserved as apo_{resref}_orig)
// first, then applies this seed's pickup-handling mode.
#include "kse"

{body}

void main()
{{
    ExecuteScript("apo_{resref}_orig", OBJECT_SELF);
    HandleAcquiredItem();
}}
"""

SHARED_TEMPLATE = """// Shared item-pickup handler for modules with no existing
// vanilla Mod_OnAcquirItem script. See patch_item_suppression.py's module
// docstring for this seed's configured mode (destroy/bonus/replace).
#include "kse"

{body}

void main()
{{
    HandleAcquiredItem();
}}
"""

# Mode name -> (deploy suffix for dev-side source files, diag code, diag marker).
_MODE_DIAG = {
    "destroy": (86, "AP|SUPPRESSED_ITEM|"),
    "bonus": (87, "AP|BONUS_ITEM|"),
    "replace": (88, "AP|REPLACED_ITEM|"),
}

# Options.py's LootMode value -> internal mode name ("skip" is this file's
# own long-standing internal name for what the option now calls "normal" --
# not renamed throughout this file to keep the diff to the option schema
# change itself, same reasoning CompanionMode's "none" vs. this project's
# other "off" namings already coexist elsewhere).
_LOOT_MODE_NAMES = {0: "skip", 1: "destroy", 2: "bonus", 3: "replace"}

# REDESIGNED 2026-08-30: the two time-based debounces that used to live
# here (BONUS_DEBOUNCE_SECONDS=3, PER_TAG_COOLDOWN_SECONDS=5) are gone,
# replaced by a real fix instead of a timing-window workaround -- see
# build_handler_body()'s docstring for the full reasoning. Short version:
# `replace` mode now guards on a per-tag HELD-QUANTITY delta (computed
# fresh from a live inventory scan, not a timestamp) instead of time --
# immune to the engine's spurious re-firing by construction, since a
# re-fire for an already-held item produces no quantity change. `bonus`
# mode no longer acts per-acquisition-event at all; its grant is now
# driven by generate_poll_shared.py's CheckPickupCount(), a heartbeat-tick
# snapshot of TOTAL held suppress-eligible quantity -- one bonus item per
# every 5 genuine items found (a running count), also immune to re-firing
# by construction for the same reason.


def build_random_pick_fn(loot_pool):
    """GetRandomLootItem() -- returns one resref chosen uniformly from
    loot_pool via a flat Random(N)-indexed if/else chain. NWScript has no
    native array/list type, so this is the only way to encode "pick one of
    N strings" -- test-compiled clean against the real 577-item
    shop_randomize pool (~42KB output, ~100ms compile), so this scales
    fine at the real pool size."""
    lines = ["string GetRandomLootItem()", "{"]
    lines.append(f"    int nRoll = Random({len(loot_pool)});")
    for i, resref in enumerate(loot_pool):
        kw = "if" if i == 0 else "else if"
        lines.append(f'    {kw} (nRoll == {i}) return "{resref}";')
    lines.append('    return "";')
    lines.append("}")
    return "\n".join(lines)


def build_handler_body(mode, suppress_resrefs, loot_pool, progression_resrefs=()):
    """The full script body (HandleAcquiredItem(), plus GetRandomLootItem()
    when the mode needs randomness) for one of the 3 non-skip modes.
    Shared by both the shared handler and every per-module wrapper -- a
    single big OR-chain of tag string comparisons against the acquired
    item identifies "is this whitelisted." Cheap: this only runs once per
    actual pickup, not on a timer.

    NWScript in this engine build has no GetResRef() at all (confirmed via
    a compile error -- "Undeclared identifier"), so this identifies items
    by GetTag() instead, same as vanilla KOTOR's own Mod_OnAcquirItem
    scripts (k_pdan_itemacq/k_pebn_acquire both key off GetTag(), not
    resref) and same as this project's own CheckInventory() poll. Items
    default to Tag == ResRef unless a UTI template explicitly overrides
    it, which is the same assumption everything else in this project
    already makes.

    Root cause, confirmed live across both bonus AND replace mode:
    Mod_OnAcquirItem does not only fire on a genuine ground pickup -- it
    ALSO re-fires for non-whitelisted items you're already holding, most
    often correlated with area transitions but not exclusively (see
    below). Confirmed via kse.log evidence: bonus mode showed one held
    item earning 10 separate grants over 25 minutes; replace mode showed
    ~28 grants across 6+ different tags in a single 125ms burst.

    A transition-relative timing fix (suppress anything firing within a
    few seconds AFTER a stamped area transition) was tried first and found
    insufficient: most duplicate bursts actually land shortly BEFORE the
    next area's OnEnter reports (during the loading-screen gap after
    leaving the OLD module), which an entry-side-only stamp can't see. The
    natural fix -- also instrumenting OnExit to close that gap -- turned
    out to be a dead end: confirmed live (fresh game restart, first-ever
    load of a test area, genuine door-based exit) that OnExit does not
    fire at all in this engine build. Also found at least one duplicate
    with no nearby transition at all (11.6s from the same tag's own prior
    grant) -- believed likely a genuine double real pickup (two physical
    items sharing a tag, looted close together), not a re-fire bug.

    Given no working way to key off transition timing, and object
    identity already confirmed unreliable (references aren't stable
    across re-firings), the ORIGINAL fix (superseded, see below) used two
    independent, purely time-based debounces -- neither depending on
    transitions or item identity at all -- to collapse re-fire bursts down
    to one grant. That held as the live mitigation for a while but stayed
    fundamentally fragile (tuning a window length against an engine
    behavior whose exact cadence was never fully characterized), and a
    later live session found fresh duplicate cases even with it in place.

    **REDESIGNED 2026-08-30: replaced with a real held-quantity-based
    fix for each of bonus/replace, not another timing window.** The
    insight: a spurious Mod_OnAcquirItem re-fire for an item you already
    hold produces NO actual change in how much of it you're holding --
    so checking the real quantity delta (not the event-firing rate) makes
    the whole debounce category of fix unnecessary.
      - `replace` mode now computes this tag's TOTAL held quantity via a
        live inventory scan (GetFirstItemInInventory/GetItemStackSize) and
        compares it to the last value recorded for this tag ("qty_" +
        sTag in KSE_SetData). Proceeds (destroy + immediately grant a
        replacement, same 1:1 instant behavior as before) only if the
        quantity actually increased; otherwise it's a re-fire echo, no
        timing window involved at all. Explicit design choice, confirmed
        with the user: replace mode keeps its original "destroy the
        pickup and immediately provide a replacement" shape -- it does
        NOT move to the count-based milestone system bonus mode uses
        below, since replace inherently needs to react to a specific
        acquisition to know what to destroy.
      - `bonus` mode uses the exact same per-tag held-quantity delta
        guard as `replace` below, then feeds the genuine delta into a
        persistent running counter and grants one bonus item every time
        that counter crosses a new multiple of 5 -- i.e. "1 bonus item
        per 5 genuine items found," a real design change from the old
        1-bonus-per-pickup behavior. A spurious Mod_OnAcquirItem re-fire
        produces zero quantity delta for that one tag, so it can never
        trigger a spurious grant -- same reasoning as `replace`'s guard,
        just feeding a shared counter instead of gating a 1:1 swap.

        REVISED 2026-08-31 (superseding an intermediate design): an
        earlier version of this fix moved bonus mode's grant logic
        entirely into a periodic generate_poll_shared.py
        CheckPickupCount(), snapshotting TOTAL held quantity across
        every one of 672 suppress-eligible tags COMBINED on every 5s
        heartbeat tick. That confirmed-live regression (see
        FutureDesign.md): scanning either every held ITEM against all
        672 tags (the original version) or all 672 tags against current
        holdings (an interim fix) on EVERY tick, forever, regardless of
        whether anything changed, is real recurring cost that isn't
        needed at all -- this handler already runs the SAME 672-way
        `conditions` OR-chain once per actual acquisition EVENT (cheap,
        since pickups are inherently rare compared to a 5s timer), and
        already knows exactly which ONE tag just fired. There's no
        reason to also scan the OTHER 671 tags nobody just interacted
        with. Moving the whole delta+counter+grant flow back into this
        event-driven handler (matching `replace`'s already-proven
        pattern below) eliminates the periodic scan entirely --
        generate_poll_shared.py no longer generates CheckPickupCount()
        at all.

    "destroy" mode is unaffected by any of the above and keeps its
    original, simpler per-OBJECT LocalBoolean marker (the same "have I
    already handled this object" pattern generate_trampoline_batch.py
    uses for per-store restock tracking) -- destroying an already-destroyed
    object is a harmless no-op, so a stray re-registration echo there was
    never a visible bug.

    Purchase detection (2026-08-29, applies to ALL THREE modes): the
    whitelist was narrowed from "quest_dependent OR included_as_item OR
    shop_randomize" down to "quest_dependent" only, so curated gear and
    shop-pool items are no longer automatically exempt when found as
    ordinary vanilla loot. That raised a real problem: Mod_OnAcquirItem
    also fires when an item is BOUGHT from a shop, not just picked up off
    the ground -- without a guard, buying a shop_randomize item would get
    it destroyed/replaced the instant the player paid for it. Fixed with a
    global "last known credit total" comparison: if GetGold(oPC) has gone
    DOWN since the last check, a purchase almost certainly just happened,
    so this acquisition is left alone entirely (no destroy, no bonus, no
    replace) regardless of mode. Runs once per acquisition, before any
    mode-specific action, using the same KSE_SetData timestamp-style
    pattern as the debounces below.

    Permanent per-tag exemption (2026-08-29, "granted_exempt_" + sTag,
    applies to ALL THREE modes): the debounces above only cover re-fires
    landing within a few seconds of each other -- they say nothing about
    Mod_OnAcquirItem re-firing HOURS later for an item this project itself
    already legitimately put in the player's hands (a bonus/replace grant,
    or a shop purchase). That's a real, still-unsolved case: this project
    has no general way to tell "genuine fresh pickup" from "engine
    re-registered something you already own" at the moment the event
    fires (confirmed this session: even a same-instant re-fire couldn't be
    distinguished by object identity, which is why the debounces are
    purely time-based). Closing that gap for EVERY resref would need a
    real acquired-vs-owned distinction this engine doesn't expose.
    Instead, this closes it for the one subset that's actually knowable:
    once a specific tag has been granted by our own GetRandomLootItem()
    draw, or bought from a shop (detected via the credit-drop check
    above), that tag is marked permanently exempt (KSE_SetData,
    "granted_exempt_" + sTag = "1") and every future Mod_OnAcquirItem for
    that same tag skips suppression handling entirely, checked right after
    sTag is computed -- before the whitelist match, so it overrides
    suppression even for a tag that IS in suppress_resrefs. This does NOT
    protect an ordinary item's very first, legitimate ground pickup (it
    has no grant/purchase history yet, so a spurious re-registration of it
    is still only covered by the short debounces) -- it specifically
    protects items the player already has because of this project's own
    delivery mechanism, which is the case the user asked to close given
    the debounces alone can't fully solve the general problem."""
    # 2026-09-08: "skip" has no _MODE_DIAG entry -- never needed one before
    # progression_system existed, since this whole function was never
    # deployed at all for skip. Guarded here; the actual skip early-return
    # happens further down, after the progression check is emitted.
    diag_code, diag_marker = _MODE_DIAG[mode] if mode != "skip" else (None, None)
    conditions = " ||\n        ".join(f'sTag == "{r}"' for r in suppress_resrefs)

    lines = ["void HandleAcquiredItem()", "{"]
    lines.append("    object oItem = GetModuleItemAcquired();")
    if mode == "destroy":
        lines.append("    if (GetLocalBoolean(oItem, 0)) return;")
    lines.append("    string sTag = GetStringLowerCase(GetTag(oItem));")
    if progression_resrefs:
        # 2026-09-08, Progression System: unconditional, ALWAYS-destroy
        # check, completely independent of loot_mode/the whitelist below.
        # NARROWED 2026-09-08 (same day, later) to just 2 items -- Sith
        # Armor (ptar_sitharmor, via k_ptar_acquire) and Shield Codes
        # (ptar_shieldcodes, via tar09_acquire) -- the only 2 of the 8
        # Progression System items whose real vanilla acquisition
        # actually fires through Mod_OnAcquirItem (both are already in
        # EXISTING_SCRIPT_NAMES). The other 6 (Sith Papers, Enviro Suit,
        # and the 4 Star Maps) never flow through this mechanism at all --
        # their real gates are dedicated wrapper scripts generated by
        # apply_progression_checkpoint_wrappers() below (Sith Papers'/the
        # Star Maps'/Enviro Suit's real creation or completion points
        # turned out not to be simple item-pickup scripts; see
        # FutureDesign.md's 2026-09-08 entries for the full derivation of
        # each one). These 2 are quest_dependent=True (protected from the
        # generic suppression this whole function otherwise applies), but
        # when Progression System is on they need the OPPOSITE treatment:
        # always suppressed at their normal vanilla acquisition point,
        # regardless of mode, since the real grant comes from the paired
        # AP check via give_item: instead (see Items.py's
        # PROGRESSION_ITEM_RESREFS). No conditional "already delivered?"
        # check needed -- destroying is correct either way, per the design
        # confirmed with the user: suppression before delivery, harmless
        # no-op after (the player already has their AP-granted copy).
        # Checked BEFORE granted_exempt_/whitelist logic since none of
        # that applies to this category at all.
        prog_conditions = " ||\n        ".join(f'sTag == "{r}"' for r in progression_resrefs)
        lines.append(f"    if ({prog_conditions})")
        lines.append("    {")
        lines.append('        KSE_Diag(89, "AP|PROGRESSION_SUPPRESSED|" + sTag);')
        lines.append("        DestroyObject(oItem);")
        lines.append("        return;")
        lines.append("    }")
    if mode == "skip":
        # 2026-09-08: mode=="skip" (loot_mode=normal) means the GENERAL
        # suppression system is off, but this function can still be
        # deployed for the progression check alone -- see main()'s
        # adjusted early-exit. _MODE_DIAG has no "skip" entry (there was
        # never a reason to deploy this function at all for skip before
        # progression_system existed), so nothing below this point is
        # reachable/valid for skip -- close out here rather than falling
        # into destroy/bonus/replace-specific logic that assumes a real
        # mode.
        lines.append("}")
        return "\n".join(lines)
    lines.append('    if (KSE_HasData("granted_exempt_" + sTag)) return;')
    lines.append(f"    if ({conditions})")
    lines.append("    {")
    lines.append("        object oPC = GetFirstPC();")
    lines.append("        int nCurCredits = GetGold(oPC);")
    lines.append('        if (KSE_HasData("last_credits"))')
    lines.append("        {")
    lines.append('            int nLastCredits = StringToInt(KSE_GetData("last_credits"));')
    lines.append("            if (nCurCredits < nLastCredits)")
    lines.append("            {")
    lines.append('                KSE_SetData("last_credits", IntToString(nCurCredits));')
    lines.append('                KSE_SetData("granted_exempt_" + sTag, "1");')
    lines.append("                return;")  # likely a purchase -- leave this acquisition alone entirely, and exempt this tag going forward
    lines.append("            }")
    lines.append("        }")
    lines.append('        KSE_SetData("last_credits", IntToString(nCurCredits));')
    if mode == "destroy":
        lines.append("        SetLocalBoolean(oItem, 0, TRUE);")
        lines.append(f'        KSE_Diag({diag_code}, "{diag_marker}" + sTag);')
        lines.append("        DestroyObject(oItem);")
    elif mode == "bonus":
        # Item is kept, untouched, exactly like vanilla -- only the
        # counter/grant bookkeeping below happens. Per-tag held-quantity
        # delta guard identical in shape to replace mode's below (see
        # docstring for why this replaced a periodic heartbeat scan).
        lines.append("        int nHeld = 0;")
        lines.append("        object oScan = GetFirstItemInInventory(oPC);")
        lines.append("        while (GetIsObjectValid(oScan))")
        lines.append("        {")
        lines.append("            if (GetStringLowerCase(GetTag(oScan)) == sTag) nHeld = nHeld + GetItemStackSize(oScan);")
        lines.append("            oScan = GetNextItemInInventory(oPC);")
        lines.append("        }")
        lines.append("        int nLastHeld = 0;")
        lines.append('        if (KSE_HasData("qty_" + sTag)) nLastHeld = StringToInt(KSE_GetData("qty_" + sTag));')
        lines.append('        KSE_SetData("qty_" + sTag, IntToString(nHeld));')
        lines.append("        int nDelta = nHeld - nLastHeld;")
        lines.append("        if (nDelta <= 0) return;")  # no real increase -- re-fire echo, not a genuine pickup
        lines.append("        int nCounter = 0;")
        lines.append('        if (KSE_HasData("pickup_running_count")) nCounter = StringToInt(KSE_GetData("pickup_running_count"));')
        lines.append("        int nOldMilestones = nCounter / 5;")
        lines.append("        nCounter = nCounter + nDelta;")
        lines.append("        int nNewMilestones = nCounter / 5;")
        lines.append('        KSE_SetData("pickup_running_count", IntToString(nCounter));')
        lines.append("        int i = nOldMilestones;")
        lines.append("        while (i < nNewMilestones)")
        lines.append("        {")
        lines.append("            string sRandom = GetRandomLootItem();")
        lines.append('            KSE_SetData("granted_exempt_" + GetStringLowerCase(sRandom), "1");')
        lines.append("            CreateItemOnObject(sRandom, oPC, 1);")
        lines.append(f'            KSE_Diag({diag_code}, "{diag_marker}milestone=" + IntToString(i + 1) + "|" + sRandom);')
        lines.append("            i = i + 1;")
        lines.append("        }")
    else:  # replace -- destroy + immediately grant, guarded by a
        # per-tag held-quantity delta instead of a timing window (see
        # docstring). A spurious re-fire for an already-held tag produces
        # no quantity change here, so it's naturally skipped.
        lines.append("        int nHeld = 0;")
        lines.append("        object oScan = GetFirstItemInInventory(oPC);")
        lines.append("        while (GetIsObjectValid(oScan))")
        lines.append("        {")
        lines.append("            if (GetStringLowerCase(GetTag(oScan)) == sTag) nHeld = nHeld + GetItemStackSize(oScan);")
        lines.append("            oScan = GetNextItemInInventory(oPC);")
        lines.append("        }")
        lines.append("        int nLastHeld = 0;")
        lines.append('        if (KSE_HasData("qty_" + sTag)) nLastHeld = StringToInt(KSE_GetData("qty_" + sTag));')
        lines.append('        KSE_SetData("qty_" + sTag, IntToString(nHeld));')
        lines.append("        if (nHeld <= nLastHeld) return;")  # no real increase -- re-fire echo, not a genuine pickup
        lines.append("        string sRandom = GetRandomLootItem();")
        lines.append('        KSE_SetData("granted_exempt_" + GetStringLowerCase(sRandom), "1");')
        lines.append("        DestroyObject(oItem);")
        lines.append("        CreateItemOnObject(sRandom, oPC, 1);")
        lines.append(f'        KSE_Diag({diag_code}, "{diag_marker}" + sTag + "->" + sRandom);')
    lines.append("    }")
    lines.append("}")
    handler = "\n".join(lines)

    if mode in ("replace", "bonus"):
        return build_random_pick_fn(loot_pool) + "\n\n" + handler
    return handler


def compile_and_deploy(nss_path, ncs_path, deploy_name):
    """Recompiles from nss_path if nwnnsscomp.exe is available (dev
    machine, rebuilding after a whitelist change). Otherwise falls back to
    whatever's already at ncs_path -- a precompiled copy checked into the
    repo under extender/scripts_src/, byte-identical to what the compiler
    would produce from the current gear_items.json, since a tester's
    machine has no reason to need a *different* whitelist than the one
    shipped. This is what makes item pickup handling work without a
    NWScript compiler on a tester's machine at all."""
    if os.path.exists(NWNNSSCOMP):
        result = subprocess.run(
            [NWNNSSCOMP, "-c", nss_path, "-o", ncs_path],
            capture_output=True, text=True, cwd=SRC_DIR,
        )
        if not os.path.exists(ncs_path):
            print(f"  COMPILE FAILED: {nss_path}\n{result.stdout}\n{result.stderr}")
            return False
    elif os.path.exists(ncs_path):
        print(f"  nwnnsscomp.exe not found -- using precompiled {ncs_path} as-is")
    else:
        print(f"  COMPILE FAILED: nwnnsscomp.exe not found, and no precompiled "
              f"fallback at {ncs_path} either -- can't produce this script.")
        return False

    deploy_path = os.path.join(OVERRIDE, f"{deploy_name}.ncs")
    with open(ncs_path, "rb") as f:
        data = f.read()
    with open(deploy_path, "wb") as f:
        f.write(data)
    print(f"  deployed -> {deploy_path}")
    return True


# Progression System checkpoint wrappers (2026-09-08): 4 vanilla scripts
# whose REAL gate isn't a Mod_OnAcquirItem-style item pickup at all, so
# the generic HandleAcquiredItem() mechanism above never touches them --
# see FutureDesign.md's 2026-09-08 entries for the full derivation of
# each one's real mechanism. All 4 live at the CHITIN level (confirmed
# via Installation.resource() succeeding with no module context loaded),
# not any module's own _s.rim overlay -- unlike EXISTING_SCRIPT_NAMES,
# this is a ONE-TIME global extraction, not a per-module RIM-scanning
# loop. 3 of the 4 (k_sup_galaxymap/k_pla_actmap/k_pman_suituse) are
# "gate-and-delegate": preserve the true original as apo_<name>_orig.ncs,
# deploy a small wrapper under the real name that either blocks (not yet
# granted) or hands off to the untouched original via ExecuteScript
# (granted) -- see each .nss's own comment for why that specific script
# needs gating at all. The 4th (k_ptar_sithpaper) is a
# StartingConditional and can't use that pattern (ExecuteScript can't
# relay a return value back to the caller), so it's a full faithful
# reimplementation instead, gated directly -- no _orig preservation
# needed for it.
PROGRESSION_CHECKPOINT_WRAPPERS = {
    "k_sup_galaxymap": "k_sup_galaxymap_progression",
    "k_pla_actmap": "k_pla_actmap_progression",
    "k_pman_suituse": "k_pman_suituse_progression",
    "k_ptar_sithpaper": "k_ptar_sithpaper_progression",
}
PROGRESSION_CHECKPOINT_NEEDS_ORIG = {"k_sup_galaxymap", "k_pla_actmap", "k_pman_suituse"}


def apply_progression_checkpoint_wrappers(game_dir):
    """Deploys the 4 Progression System checkpoint wrappers (see
    PROGRESSION_CHECKPOINT_WRAPPERS above). Only called when
    progression_system is on. Returns the count successfully deployed."""
    install = Installation(game_dir)
    deployed = 0
    for real_name, dev_basename in PROGRESSION_CHECKPOINT_WRAPPERS.items():
        if real_name in PROGRESSION_CHECKPOINT_NEEDS_ORIG:
            res = install.resource(real_name, ResourceType.NCS)
            if res is None:
                print(f"  {real_name}: TRUE ORIGINAL NOT FOUND in installation -- skipping, "
                      "Progression System's gate for this script will NOT be applied.")
                continue
            orig_deploy = os.path.join(OVERRIDE, f"apo_{real_name}_orig.ncs")
            with open(orig_deploy, "wb") as f:
                f.write(res.data)
            print(f"  {real_name}: true original preserved -> {orig_deploy}")
        nss_path = os.path.join(SRC_DIR, f"{dev_basename}.nss")
        ncs_path = os.path.join(SRC_DIR, f"{dev_basename}.ncs")
        if not os.path.exists(nss_path):
            print(f"  {real_name}: expected source {nss_path} not found -- skipping.")
            continue
        if compile_and_deploy(nss_path, ncs_path, real_name):
            deployed += 1
        else:
            print(f"  {real_name}: wrapper failed to compile/deploy.")
    return deployed


def restore():
    if not os.path.isdir(BACKUP_DIR):
        print("No backup directory found -- nothing to restore.")
        return
    restored = 0
    for fname in os.listdir(BACKUP_DIR):
        src = os.path.join(BACKUP_DIR, fname)
        dst = os.path.join(MOD_DIR, fname)
        shutil.copy2(src, dst)
        restored += 1
        print(f"  restored {fname}")
    print(f"Restored {restored} module RIM(s) from backup.")


def _connected_seed_mode():
    """Reads loot_mode out of _slot_data.json -- written by KotorClient.py
    on every successful Connect, straight from the real slot_data the AP
    server sent THIS player for THEIR OWN slot (see SLOT_DATA_PATH above
    for the full reasoning). Returns None if that file doesn't exist yet
    (never connected) or doesn't parse, so the caller can print a clear
    "connect first" message rather than silently defaulting either way."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return None
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return _LOOT_MODE_NAMES.get(data.get("loot_mode"))
    except Exception as e:
        print(f"  (couldn't read {SLOT_DATA_PATH}: {e})")
        return None


def _connected_progression_system() -> bool:
    """Reads progression_system out of _slot_data.json the same way
    _connected_seed_mode() reads loot_mode -- see KotorClient.py's
    write_slot_data_for_patch_scripts(). False (safe default) if the file
    doesn't exist or doesn't parse."""
    if not os.path.isfile(SLOT_DATA_PATH):
        return False
    try:
        with open(SLOT_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("progression_system", False))
    except Exception:
        return False


def main():
    if "--restore" in sys.argv:
        restore()
        return

    if "--force" not in sys.argv:
        mode = _connected_seed_mode()
        if mode is None:
            print(f"No usable data at {SLOT_DATA_PATH} -- connect once with KotorClient.py first "
                  "(see README.md Step 6), which writes your seed's real loot_mode there on every "
                  "successful Connect. Otherwise, pass --force with a manually-set mode.")
            return
        print(f"Connected seed resolves to mode={mode!r} -- applying.")
    else:
        mode = _arg_value("--mode", None)
        if mode == "normal":
            mode = "skip"
        if mode not in ("destroy", "bonus", "replace", "skip"):
            print("--force given but no valid --mode=<destroy|bonus|replace|skip> -- nothing to apply.")
            return

    if "--force" in sys.argv:
        progression_system = "--progression-system" in sys.argv
    else:
        progression_system = _connected_progression_system()

    if mode == "skip" and not progression_system:
        print("Mode is 'skip' (randomize_loot=False, allow_normal_loot=True) and Progression System "
              "is off -- nothing to wire up, vanilla loot is left alone.")
        return

    with open(GEAR_JSON, encoding="utf-8") as f:
        gear = json.load(f)
    # 2026-09-08: only 2 of the 8 Progression System items (Sith Armor,
    # Shield Codes) actually flow through Mod_OnAcquirItem -- ALWAYS
    # suppressed at their vanilla acquisition point when progression_system
    # is on, completely independent of loot_mode/the whitelist below (see
    # build_handler_body's own comment on this). Empty list (no-op) when
    # the option is off, same as before this feature existed. The other 6
    # items are handled by apply_progression_checkpoint_wrappers() below,
    # a completely separate mechanism (their real gates aren't
    # Mod_OnAcquirItem pickups at all).
    progression_resrefs = sorted(
        r for r, v in gear.items() if v.get("progression_suppression") == "1"
    ) if progression_system else []
    if progression_system:
        print(f"Progression System is on -- {len(progression_resrefs)} quest item(s) always-suppressed "
              f"at their vanilla acquisition point.")
        deployed = apply_progression_checkpoint_wrappers(GAME_DIR)
        print(f"Progression System checkpoint wrappers: {deployed}/{len(PROGRESSION_CHECKPOINT_WRAPPERS)} deployed.")
    # NARROWED 2026-08-29 (second attempt) to quest_dependent-only.
    #
    # First attempt (same day, earlier) narrowed this the same way and was
    # REVERTED after live testing found a real structural conflict:
    # build_random_pick_fn's GetRandomLootItem() loot pool is drawn from
    # shop_randomize items, and every included_as_item item is ALSO
    # shop_randomize (144 of 144, a strict subset, zero exceptions) -- so
    # a bonus/replace-granted item's OWN tag would immediately become
    # suppress-eligible too. Since Mod_OnAcquirItem re-fires for an
    # already-held item regardless of how it entered inventory (confirmed
    # live: a bonus-granted item got re-suppressed later, e.g. on equip),
    # narrowing without a fix meant this project's own grants ate
    # themselves.
    #
    # This second attempt is only safe because of two exemption fixes
    # added alongside it: (1) build_handler_body()'s bonus/replace branch
    # marks its own GetRandomLootItem() draw "granted_exempt_" +
    # permanently exempt BEFORE creating it, and the credit-drop purchase
    # check marks a bought item's tag the same way -- both close the loop
    # for THIS module's own suppression-adjacent grants; (2)
    # generate_trampoline_batch.py's build_give_item_block() (the
    # SEPARATE code path that delivers a real AP check's gear reward) now
    # marks the SAME "granted_exempt_" key before its own
    # CreateItemOnObject call -- without this second fix, narrowing here
    # would have made real AP check rewards (any of the 144
    # included_as_item resrefs) destroyable/replaceable the instant
    # they're delivered, since CreateItemOnObject fires Mod_OnAcquirItem
    # the same as any pickup and that handler is a completely different
    # script than this one. Both handlers read the same KSE_HasData
    # store, so either one marking a tag protects it from the other.
    #
    # Impact: suppress-eligible resrefs jump from 95 (old 3-flag
    # whitelist) to 672 (of 810 total) -- every shop_randomize/
    # included_as_item resref not also quest_dependent is now
    # suppressible as ordinary vanilla loot, same as the original intent
    # of the first attempt. The credit-drop purchase check and the
    # shop-cost-floor fix (patch_shop_item_costs.py) both stay in place
    # regardless -- neither depends on which whitelist is active.
    suppress_resrefs = sorted(
        r for r, v in gear.items() if not v.get("quest_dependent")
    )
    loot_pool = sorted(r for r, v in gear.items() if v.get("shop_randomize"))
    print(f"Non-whitelisted (suppressible) resrefs: {len(suppress_resrefs)}, "
          f"random-loot pool: {len(loot_pool)}")
    body = build_handler_body(mode, suppress_resrefs, loot_pool, progression_resrefs)

    # 1. Shared handler for empty-slot modules. Dev-side source carries the
    # mode suffix; deployed Override file is always the fixed
    # SHARED_SUPPRESS_RESREF name regardless of mode (see module docstring).
    shared_nss = os.path.join(SRC_DIR, f"{SHARED_SUPPRESS_RESREF}_{mode}.nss")
    shared_ncs = os.path.join(SRC_DIR, f"{SHARED_SUPPRESS_RESREF}_{mode}.ncs")
    with open(shared_nss, "w") as f:
        f.write(SHARED_TEMPLATE.format(body=body))
    if not compile_and_deploy(shared_nss, shared_ncs, SHARED_SUPPRESS_RESREF):
        print("Aborting -- shared handler failed to compile.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)

    rim_files = sorted(f for f in os.listdir(MOD_DIR) if f.lower().endswith(".rim") and not f.lower().endswith("_s.rim"))
    empty_patched = 0
    existing_wrapped = 0
    skipped = 0

    for fname in rim_files:
        base = fname[:-4]
        path = os.path.join(MOD_DIR, fname)
        try:
            r = read_rim(path)
        except Exception as e:
            print(f"  {base}: could not read RIM ({e}), skipping")
            skipped += 1
            continue

        ifo_res = None
        for res in r:
            if res.restype == ResourceType.IFO:
                ifo_res = res
                break
        if ifo_res is None:
            skipped += 1
            continue

        gff = read_gff(ifo_res.data)
        current = gff.root.get_resref("Mod_OnAcquirItem")
        current_str = current.get() if current else ""

        if not current_str:
            # Empty slot -- real RIM/IFO edit needed, but only the FIRST
            # time regardless of mode (see module docstring) -- if it's
            # already pointed at our shared resref from an earlier run,
            # there's nothing left to do here.
            if current_str == SHARED_SUPPRESS_RESREF:
                continue
            backup_path = os.path.join(BACKUP_DIR, fname)
            if not os.path.exists(backup_path):
                shutil.copy2(path, backup_path)
            gff.root.set_resref("Mod_OnAcquirItem", ResRef(SHARED_SUPPRESS_RESREF))
            new_ifo_data = bytearray()
            write_gff(gff, new_ifo_data)
            r.set_data(ifo_res.resref, ResourceType.IFO, bytes(new_ifo_data))
            write_rim(r, path)
            empty_patched += 1
        elif current_str.lower() in EXISTING_SCRIPT_NAMES:
            # Existing script -- Override-swap only, no RIM edit. The
            # compiled .ncs itself lives in the _s.rim instance overlay,
            # not the base .rim (same split generate_companion_suppressors.py
            # already relies on for the exact same reason).
            orig_resref = current_str
            ncs_data = None
            s_rim_path = os.path.join(MOD_DIR, f"{base}_s.rim")
            if os.path.exists(s_rim_path):
                r_s = read_rim(s_rim_path)
                for res in r_s:
                    if res.resref.get().lower() == orig_resref.lower() and res.restype == ResourceType.NCS:
                        ncs_data = res.data
                        break
            if ncs_data is None:
                print(f"  {base}: expected script {orig_resref} not found in {base}_s.rim, skipping")
                skipped += 1
                continue
            orig_deploy = os.path.join(OVERRIDE, f"apo_{orig_resref}_orig.ncs")
            with open(orig_deploy, "wb") as f:
                f.write(ncs_data)
            wrapper_nss = os.path.join(SRC_DIR, f"{orig_resref}_itemsuppress_{mode}.nss")
            wrapper_ncs = os.path.join(SRC_DIR, f"{orig_resref}_itemsuppress_{mode}.ncs")
            with open(wrapper_nss, "w") as f:
                f.write(WRAPPER_TEMPLATE.format(module=base, resref=orig_resref, body=body))
            if compile_and_deploy(wrapper_nss, wrapper_ncs, orig_resref):
                existing_wrapped += 1
            else:
                skipped += 1
        # else: some OTHER non-empty script we didn't expect -- leave untouched, don't guess.

    print(f"\nDone. mode={mode}. empty-slot modules patched: {empty_patched}, "
          f"existing-script modules wrapped: {existing_wrapped}, skipped: {skipped}")


if __name__ == "__main__":
    main()
