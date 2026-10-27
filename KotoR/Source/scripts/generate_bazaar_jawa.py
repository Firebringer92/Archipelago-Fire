"""
Archipelago Bazaar -- the Jawa who stands next to the Archipelago Vendor on the Ebon Hawk (worlds/kotor Locations.py:
"Archipelago Bazaar: Purchase 1-5" and "Bazaar Token Exchange 1-20").

The Jawa gives the player a CHECK, never an item:
  - Purchases: 1,000 credits for the first, then +2,000 for each after (1k, 3k, 5k, 7k, 9k), five in all.
  - Token exchange: five Bazaar tokens (ap_bz_token, found in module containers, see patch_bazaar_tokens.py) for one exchange, twenty in all.
Each completed deal gives the player one plot receipt (ap_bz_buy / ap_bz_swap). The number of receipts held is the number of deals done,
so the price and the exchange count both live in the save (a reloaded save simply holds fewer receipts) and the client credits the
checks by count (kotor_location_tracker.py, poll line AP|BAZAAR|<purchases>|<exchanges> from generate_poll_shared.py CheckBazaar).

Files written to extender/scripts_src (sources, compiled scripts, the dialog and the NPC template) and extender/raw_override_files (the
static files for packaging). Nothing is copied to the game's Override unless --deploy is given.

Engine constraints this follows (see generate_ap_vendor.py): TakeGoldFromCreature is a no-op, so credits are taken with KSE_SetCredits;
DLGLink active1_not is never used by the base game, so each branch gets its own pair of conditional scripts; dialog entries and
replies strictly alternate; every node sets plot_index -1; resrefs stay under 16 characters.
"""
import argparse
import json
import os
import subprocess
import sys

from pykotor.extract.installation import Installation
from pykotor.resource.type import ResourceType
from pykotor.resource.formats.gff import read_gff, write_gff
from pykotor.resource.generics.utc import construct_utc, dismantle_utc
from pykotor.resource.generics.uti import construct_uti, dismantle_uti
from pykotor.resource.generics.dlg import DLG, DLGEntry, DLGReply, DLGLink, dismantle_dlg
from pykotor.common.language import LocalizedString
from pykotor.common.misc import ResRef, Game

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nwnnsscomp_path import resolve_nwnnsscomp, compile_nss  # noqa: E402 -- see that module's docstring

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\swkotor"
SRC_DIR = os.path.join(REPO_ROOT, "extender", "scripts_src")
RAW_DIR = os.path.join(REPO_ROOT, "extender", "raw_override_files")
MANIFEST_PATH = os.path.join(SRC_DIR, "_bazaar_manifest.json")

NPC_RESREF = "ap_jawa_npc"
DLG_RESREF = "ap_jawa_dlg"
BUY_RESREF = "ap_bz_buy"      # receipt: one per purchase
SWAP_RESREF = "ap_bz_swap"    # receipt: one per token exchange
TOKEN_RESREF = "ap_bz_token"  # the exchange token

PURCHASES = 5
FIRST_PRICE = 1000
PRICE_STEP = 2000
EXCHANGES = 20
TOKENS_PER_EXCHANGE = 5
# Base item and the vanilla Jawa whose look the NPC takes (the vendor NPC's template supplies everything else).
ITEM_BASE = "g_i_datapad001"
# The token looks like the Sith Medallion (same icon and model: a copy of that item's template with its own tag and name). Its base item type
# (Plot_Useable_Items) stacks to 99, which the exchange counts on.
TOKEN_LOOK_TEMPLATE = "k33_itm_sithmdln"
JAWA_LOOK_TEMPLATE = "tat17_xxjawa_01"
VENDOR_NPC_TEMPLATE = "ap_vendor_npc"
CUSTOM_STATUS = 9011
CUSTOM_PRICE = 9012

NWNNSSCOMP = resolve_nwnnsscomp()
_COMPILED = []


def _arg_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--game-dir", default=DEFAULT_GAME_DIR)
    p.add_argument("--deploy", action="store_true", help="also copy the generated files to <game-dir>\\Override")
    return p


# One shared helper block: how many of an item the player holds (the stack size of the one stack).
_COUNT_FUNC = """int Held(object oPC, string sTag)
{
    object oItem = GetItemPossessedBy(oPC, sTag);
    if (!GetIsObjectValid(oItem)) return 0;
    return GetItemStackSize(oItem);
}
"""
_PRICE_EXPR = f"({FIRST_PRICE} + {PRICE_STEP} * nBought)"


def write_and_compile(resref, source, deploy_dir):
    nss_path = os.path.join(SRC_DIR, f"{resref}.nss")
    ncs_path = os.path.join(SRC_DIR, f"{resref}.ncs")
    with open(nss_path, "w") as f:
        f.write(source)
    mtime_before = os.path.getmtime(ncs_path) if os.path.exists(ncs_path) else None
    result = compile_nss(nss_path, ncs_path, cwd=SRC_DIR, timeout=30)
    compiled_fresh = os.path.exists(ncs_path) and (mtime_before is None or os.path.getmtime(ncs_path) != mtime_before)
    if not compiled_fresh:
        print(f"  COMPILE FAILED: {resref}\n{result.stdout}\n{result.stderr}")
        return False
    with open(ncs_path, "rb") as f:
        data = f.read()
    for d in (RAW_DIR, deploy_dir):
        if d:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{resref}.ncs"), "wb") as f:
                f.write(data)
    _COMPILED.append(resref)
    print(f"  compiled {resref}.ncs")
    return True


def build_scripts(deploy_dir):
    ok = True
    # Condition on every link into the greeting: fills the two custom tokens the dialog text uses. A condition runs before the line it guards
    # is shown, so the text always has current numbers (an entry's own action script is not guaranteed to run before its text is drawn).
    ok &= write_and_compile("ap_jw_greet", f'''#include "kse"

{_COUNT_FUNC}
int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    int nBought = Held(oPC, "{BUY_RESREF}");
    int nSwapped = Held(oPC, "{SWAP_RESREF}");
    int nTokens = Held(oPC, "{TOKEN_RESREF}");
    SetCustomToken({CUSTOM_STATUS}, "Finds bought: " + IntToString(nBought) + " of {PURCHASES}. Trades done: " + IntToString(nSwapped) + " of {EXCHANGES}. Tokens in your pack: " + IntToString(nTokens) + ".");
    SetCustomToken({CUSTOM_PRICE}, IntToString({_PRICE_EXPR}));
    return TRUE;
}}
''', deploy_dir)
    # Conditionals: which options show, and the two outcomes of each deal.
    conds = {
        "ap_jw_canbuy": f'return Held(oPC, "{BUY_RESREF}") < {PURCHASES};',
        "ap_jw_cantrd": f'return Held(oPC, "{SWAP_RESREF}") < {EXCHANGES};',
        "ap_jw_gold": f'int nBought = Held(oPC, "{BUY_RESREF}"); return nBought < {PURCHASES} && GetGold(oPC) >= {_PRICE_EXPR};',
        "ap_jw_nogold": f'int nBought = Held(oPC, "{BUY_RESREF}"); return nBought < {PURCHASES} && GetGold(oPC) < {_PRICE_EXPR};',
        "ap_jw_tok": f'return Held(oPC, "{SWAP_RESREF}") < {EXCHANGES} && Held(oPC, "{TOKEN_RESREF}") >= {TOKENS_PER_EXCHANGE};',
        "ap_jw_notok": f'return Held(oPC, "{SWAP_RESREF}") < {EXCHANGES} && Held(oPC, "{TOKEN_RESREF}") < {TOKENS_PER_EXCHANGE};',
    }
    for resref, body in conds.items():
        ok &= write_and_compile(resref, f'''#include "kse"

{_COUNT_FUNC}
int StartingConditional()
{{
    object oPC = GetPCSpeaker();
    {body}
}}
''', deploy_dir)
    # Actions: the purchase takes the credits and gives the receipt; the exchange takes the tokens and gives the receipt.
    ok &= write_and_compile("ap_jw_buy", f'''#include "kse"

{_COUNT_FUNC}
void main()
{{
    object oPC = GetPCSpeaker();
    int nBought = Held(oPC, "{BUY_RESREF}");
    if (nBought >= {PURCHASES}) return;
    int nPrice = {_PRICE_EXPR};
    if (GetGold(oPC) < nPrice) return;
    int nAfter = KSE_SetCredits(oPC, GetGold(oPC) - nPrice);
    CreateItemOnObject("{BUY_RESREF}", oPC, 1);
    KSE_Diag(204, "AP|APPLIED|bazaar_buy|price=" + IntToString(nPrice) + "|creditsAfter=" + IntToString(nAfter) + "|count=" + IntToString(nBought + 1));
}}
''', deploy_dir)
    ok &= write_and_compile("ap_jw_swap", f'''#include "kse"

{_COUNT_FUNC}
void main()
{{
    object oPC = GetPCSpeaker();
    int nSwapped = Held(oPC, "{SWAP_RESREF}");
    if (nSwapped >= {EXCHANGES}) return;
    object oTokens = GetItemPossessedBy(oPC, "{TOKEN_RESREF}");
    if (!GetIsObjectValid(oTokens)) return;
    int nHave = GetItemStackSize(oTokens);
    if (nHave < {TOKENS_PER_EXCHANGE}) return;
    if (nHave == {TOKENS_PER_EXCHANGE}) DestroyObject(oTokens);
    else SetItemStackSize(oTokens, nHave - {TOKENS_PER_EXCHANGE});
    CreateItemOnObject("{SWAP_RESREF}", oPC, 1);
    KSE_Diag(205, "AP|APPLIED|bazaar_swap|tokensLeft=" + IntToString(nHave - {TOKENS_PER_EXCHANGE}) + "|count=" + IntToString(nSwapped + 1));
}}
''', deploy_dir)
    return ok


def _entry(text):
    e = DLGEntry()
    e.text = LocalizedString.from_english(text)
    e.plot_index = -1
    e.speaker = NPC_RESREF
    return e


def _reply(text):
    r = DLGReply()
    r.text = LocalizedString.from_english(text)
    r.plot_index = -1
    return r


def _link(node, active=None):
    link = DLGLink(node)
    if active:
        link.active1 = ResRef(active)
    return link


def build_dlg():
    dlg = DLG()
    # Skippable: the player can click through a line. Left off (the default) every line has to run out its reading time, which is what made these menus slow.
    dlg.skippable = True
    greet = _entry(f"Utinni! Jawa trade fair! <CUSTOM{CUSTOM_STATUS}>")
    bought = _entry("Good bargain! Jawa find you a fine thing. Take it, take it!")
    bought.script1 = ResRef("ap_jw_buy")
    poor = _entry(f"Not enough credits! This one costs <CUSTOM{CUSTOM_PRICE}>. Come back with more, yes?")
    traded = _entry("Shiny tokens! Jawa take them. Here is your find!")
    traded.script1 = ResRef("ap_jw_swap")
    no_tokens = _entry(f"Jawa want {TOKENS_PER_EXCHANGE} tokens for a find. Bring more shiny tokens, yes?")

    # An entry never links to another entry: a blank reply loops every outcome back to the greeting.
    again = _reply("")
    again.links.append(_link(greet, "ap_jw_greet"))
    for node in (bought, poor, traded, no_tokens):
        node.links.append(_link(again))

    buy = _reply(f"Buy a find for <CUSTOM{CUSTOM_PRICE}> credits.")
    buy.links.append(_link(bought, "ap_jw_gold"))
    buy.links.append(_link(poor, "ap_jw_nogold"))
    trade = _reply(f"Trade {TOKENS_PER_EXCHANGE} Bazaar tokens for a find.")
    trade.links.append(_link(traded, "ap_jw_tok"))
    trade.links.append(_link(no_tokens, "ap_jw_notok"))
    leave = _reply("Goodbye.")

    greet.links.append(_link(buy, "ap_jw_canbuy"))
    greet.links.append(_link(trade, "ap_jw_cantrd"))
    greet.links.append(_link(leave))
    dlg.starters.append(_link(greet, "ap_jw_greet"))
    return dlg


def build_npc(installation):
    """The Archipelago Vendor's own template (faction, scripts, stats) with the Jawa's look and this dialog."""
    base = installation.resource(VENDOR_NPC_TEMPLATE, ResourceType.UTC)
    look = installation.resource(JAWA_LOOK_TEMPLATE, ResourceType.UTC)
    if look is None:
        sys.exit(f"vanilla {JAWA_LOOK_TEMPLATE}.utc not found -- is --game-dir a real KOTOR install?")
    if base is not None:
        base_data = base.data
    else:
        # The vendor's template is generated by generate_ap_vendor.py; fall back to its saved copy.
        with open(os.path.join(SRC_DIR, f"{VENDOR_NPC_TEMPLATE}.utc"), "rb") as f:
            base_data = f.read()
    npc = construct_utc(read_gff(base_data))
    jawa = construct_utc(read_gff(look.data))
    for field in ("appearance_id", "portrait_id", "gender_id", "race_id", "soundset_id", "phenotype_id", "body_variation", "texture_variation", "bodybag_id"):
        if hasattr(jawa, field):
            setattr(npc, field, getattr(jawa, field))
    npc.resref = ResRef(NPC_RESREF)
    npc.tag = NPC_RESREF
    npc.first_name = LocalizedString.from_english("Bazaar Trader")
    npc.last_name = LocalizedString.from_english("")
    npc.conversation = ResRef(DLG_RESREF)
    data = bytearray()
    write_gff(dismantle_utc(npc), data)
    return bytes(data)


# A new item of these templates is ONE item: the largest stack comes from the base item (99 for plot items), never from the template. A template saying 99 made every
# container the token patch put "one token" into hold 99 (a playtest got 99 tokens from one container).
ITEM_STACK_SIZE = 1


def build_item(installation, resref, title, description, stack=ITEM_STACK_SIZE, base=ITEM_BASE):
    src = installation.resource(base, ResourceType.UTI)
    if src is None:
        sys.exit(f"vanilla {base}.uti not found -- is --game-dir a real KOTOR install?")
    uti = construct_uti(read_gff(src.data))
    uti.resref = ResRef(resref)
    uti.tag = resref
    uti.name = LocalizedString.from_english(title)
    uti.description = LocalizedString.from_english(description)
    uti.plot = 1
    uti.stack_size = stack
    data = bytearray()
    write_gff(dismantle_uti(uti), data)
    return bytes(data)


def main():
    args = _arg_parser().parse_args()
    deploy_dir = os.path.join(args.game_dir, "Override") if args.deploy else None
    os.makedirs(RAW_DIR, exist_ok=True)

    print("Building scripts...")
    if not build_scripts(deploy_dir):
        sys.exit("ABORT: a script failed to compile.")

    installation = Installation(args.game_dir)
    files = {}

    print("Building dialog...")
    gff = dismantle_dlg(build_dlg(), Game.K1)
    data = bytearray()
    write_gff(gff, data)
    files[f"{DLG_RESREF}.dlg"] = bytes(data)

    print("Building Jawa template...")
    files[f"{NPC_RESREF}.utc"] = build_npc(installation)

    print("Building items...")
    files[f"{BUY_RESREF}.uti"] = build_item(installation, BUY_RESREF, "Bazaar Find",
        "A find bought from the Bazaar Trader on the Ebon Hawk. Can't be sold, dropped, or destroyed.")
    files[f"{SWAP_RESREF}.uti"] = build_item(installation, SWAP_RESREF, "Bazaar Trade Receipt",
        "Proof of a trade of Bazaar tokens with the Bazaar Trader on the Ebon Hawk. Can't be sold, dropped, or destroyed.")
    files[f"{TOKEN_RESREF}.uti"] = build_item(installation, TOKEN_RESREF, "Bazaar Token",
        f"A shiny token. The Bazaar Trader on the Ebon Hawk trades a find for {TOKENS_PER_EXCHANGE} of these. Can't be sold or dropped.",
        base=TOKEN_LOOK_TEMPLATE)

    for name, blob in files.items():
        for d in (SRC_DIR, RAW_DIR, deploy_dir):
            if d:
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, name), "wb") as f:
                    f.write(blob)
        print(f"  wrote {name} ({len(blob)} bytes)")

    raw_files = sorted(list(files) + [f"{r}.ncs" for r in _COMPILED])
    with open(MANIFEST_PATH, "w", encoding="utf8") as f:
        json.dump({"scripts": sorted(_COMPILED), "raw_files": raw_files}, f, indent=1)
    print(f"Wrote manifest: {len(_COMPILED)} scripts, {len(raw_files)} files.")
    if deploy_dir:
        print(f"Deployed to {deploy_dir}. The game scans Override once at startup: relaunch before testing.")
    else:
        print("Not deployed (no --deploy).")


if __name__ == "__main__":
    main()
