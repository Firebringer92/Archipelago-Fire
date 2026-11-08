"""Compiles the Bazaar Jawa's conversation scripts (ap_jw_*) from data/bazaar.json into a folder.

They contain no game content (only routine numbers), so the compiled files can be shipped with the client as payload; the dialogue, creature and item files are made on the
player's machine by client/k2_bazaar.py. Compiler: tools/k2compile.py (nwnsc, NOPs stripped), the game's own nwscript.nss read from the install.

  python tools/build_bazaar.py --game-dir <K2 folder> --out DIR
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "client"))


def script_sources(cfg: dict) -> dict:
    buy, swap, tok = "ap_bz_buy", "ap_bz_swap", "ap_bz_token"
    n, step, first = cfg["purchases"], cfg["price_step"], cfg["first_price"]
    price = "(%d + %d * nBought)" % (first, step)
    head = '#include "k2ap_bazaar"\n\n'
    out = {}
    out["ap_jw_greet"] = head + '''int StartingConditional()
{
    object oPC = GetPCSpeaker();
    int nBought = K2AP_Held(oPC, "%s");
    int nSwapped = K2AP_Held(oPC, "%s");
    int nTokens = K2AP_Held(oPC, "%s");
    SetCustomToken(9011, "Finds bought: " + IntToString(nBought) + " of %d. Trades done: " + IntToString(nSwapped) + " of %d. Tokens in your pack: " + IntToString(nTokens) + ".");
    SetCustomToken(9012, IntToString(%s));
    return TRUE;
}
''' % (buy, swap, tok, n, cfg["exchanges"], price)
    conds = {
        "ap_jw_canbuy": 'return K2AP_Held(oPC, "%s") < %d;' % (buy, n),
        "ap_jw_cantrd": 'return K2AP_Held(oPC, "%s") < %d;' % (swap, cfg["exchanges"]),
        "ap_jw_gold": 'int nBought = K2AP_Held(oPC, "%s"); return nBought < %d && GetGold(oPC) >= %s;' % (buy, n, price),
        "ap_jw_nogold": 'int nBought = K2AP_Held(oPC, "%s"); return nBought < %d && GetGold(oPC) < %s;' % (buy, n, price),
        "ap_jw_tok": 'return K2AP_Held(oPC, "%s") < %d && K2AP_Held(oPC, "%s") >= %d;' % (swap, cfg["exchanges"], tok, cfg["tokens_per_exchange"]),
        "ap_jw_notok": 'return K2AP_Held(oPC, "%s") < %d && K2AP_Held(oPC, "%s") < %d;' % (swap, cfg["exchanges"], tok, cfg["tokens_per_exchange"]),
    }
    for name, body in conds.items():
        out[name] = head + "int StartingConditional()\n{\n    object oPC = GetPCSpeaker();\n    %s\n}\n" % body
    out["ap_jw_buy"] = head + '''void main()
{
    object oPC = GetPCSpeaker();
    int nBought = K2AP_Held(oPC, "%s");
    if (nBought >= %d) return;
    int nPrice = %s;
    if (GetGold(oPC) < nPrice) return;
    K2SE_SetPartyCredits(GetGold(oPC) - nPrice);
    CreateItemOnObject("%s", oPC, 1);
    K2AP_Trace("bazaar", "purchase " + IntToString(nBought + 1) + " for " + IntToString(nPrice));
}
''' % (buy, n, price, buy)
    out["ap_jw_swap"] = head + '''void main()
{
    object oPC = GetPCSpeaker();
    int nSwapped = K2AP_Held(oPC, "%s");
    if (nSwapped >= %d) return;
    object oTokens = GetItemPossessedBy(oPC, "%s");
    if (!GetIsObjectValid(oTokens)) return;
    int nHave = GetItemStackSize(oTokens);
    if (nHave < %d) return;
    if (nHave == %d) DestroyObject(oTokens);
    else SetItemStackSize(oTokens, nHave - %d);
    CreateItemOnObject("%s", oPC, 1);
    K2AP_Trace("bazaar", "exchange " + IntToString(nSwapped + 1));
}
''' % (swap, cfg["exchanges"], tok, cfg["tokens_per_exchange"], cfg["tokens_per_exchange"], cfg["tokens_per_exchange"], swap)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import k2compile
    with open(os.path.join(ROOT, "data", "bazaar.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, "_work")
    k2compile.prepare_include_dir(work, a.game_dir)
    problems = 0
    for name, source in script_sources(cfg).items():
        with open(os.path.join(work, name + ".nss"), "w", newline="\n") as f:
            f.write(source)
        ok, message = k2compile.compile_script(work, name)
        if ok:
            with open(os.path.join(work, name + ".ncs"), "rb") as r, open(os.path.join(a.out, name + ".ncs"), "wb") as w:
                w.write(r.read())
        else:
            print("PROBLEM: %s did not compile: %s" % (name, message[-500:]))
            problems += 1
    print("%d scripts compiled into %s, %d problem(s)" % (len(script_sources(cfg)) - problems, a.out, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
