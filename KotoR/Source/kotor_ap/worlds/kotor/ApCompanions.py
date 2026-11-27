"""AP companions (0.2.1): generated companions, one per "AP Companion <n>" item, each named after a player of the multiworld with a seeded random class, look and
portrait. They sit in party slots 15 and up (the extra companions from Items.EXTRA_COMPANIONS take 9 to 14) and are added by the same extra_companion action.

The plan below is made when the seed is generated and sent to the client in slot_data ("ap_companions"); the client writes one creature template per entry
(scripts/generate_new_companion_assets.py). The look is a disguise applied on spawn by one shared script, ap_apc_spawn, which reads the appearance row from the
creature's tag ("apl<row>x<n>"), so no per-companion script is needed.
"""
import typing

AP_COMPANION_FIRST_SLOT = 15
AP_COMPANION_MAX = 8
AP_COMPANION_TEMPLATE = "p_apc{n}"
AP_COMPANION_TAG = "apl{row}x{n}"

# Looks: (appearance.2da row, gender 0 male / 1 female). Only rows of the game's NPC humanoid models, none of them a story companion's look. Twi'lek, Rodian, Duros,
# Bith, Mandalorian, Wookiee, Trandoshan, Rakata, Sand People, Vandar's species and human soldiers, officers, Jedi and Sith; the rows are the game's own (Alien_*, Republic_*,
# Jedi_*, Sith_* in appearance.2da). Every row here was seen in the game as a spawned companion and looked right; the Wookiee, Trandoshan, Rakata, Sand People and
# Vandar rows were also tried in the party with weapons and fighting. Tried and left out: Gamorrean, Ithorian and Jawa (creature-style models: no weapons, broken walking),
# Selkath (needs changes).
AP_LOOKS: typing.Tuple[typing.Tuple[int, int], ...] = (
    # Twi'lek
    (47, 1), (48, 0), (269, 0), (270, 1), (366, 1), (446, 1), (447, 1), (448, 1), (449, 0), (450, 0),
    # Rodian, Duros, Bith, Mandalorian
    (39, 0), (256, 0), (257, 0), (258, 0), (451, 0), (24, 0), (373, 0), (374, 0), (12, 0), (35, 0), (351, 0), (352, 0),
    # humans: Republic soldiers and officers
    (38, 0), (283, 0), (284, 0), (355, 0), (356, 1), (357, 1), (360, 1), (367, 1), (37, 0), (287, 0),
    # humans: Jedi
    (31, 0), (214, 0), (218, 0), (223, 0), (304, 0), (30, 1), (200, 1), (204, 1), (209, 1), (306, 1),
    # humans: Sith
    (42, 1), (43, 0), (291, 1), (292, 1), (296, 0), (297, 0), (301, 1), (302, 0),
    # Wookiee, Trandoshan, Rakata, Sand People, Vandar's species
    (51, 0), (271, 0), (272, 0), (273, 0), (50, 1), (275, 1), (276, 1), (452, 0), (453, 0), (36, 0), (254, 0), (46, 0), (266, 0), (90, 1), (52, 0),
)

# The game's ordinary head portraits (portraits.2da rows): female, male.
AP_PORTRAITS: typing.Dict[int, typing.Tuple[int, ...]] = {
    1: (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17),
    0: (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32),
}

AP_CLASSES = ("soldier", "scout", "scoundrel", "guardian", "consular", "sentinel")


def item_name(n: int) -> str:
    """The static item name of the n-th AP companion (1 based). The name of the character comes from the seed's plan, not from the item."""
    return f"AP Companion {n}"


def build_plan(rng, names: typing.Sequence[str], count: int) -> typing.List[typing.Dict[str, typing.Any]]:
    """The seeded plan for `count` AP companions. `names` are the player names to draw from, in order (other players first, then this one); when there are more
    companions than names the next round of names get a number ("Alex 2"). Looks are dealt without repeats until the pool runs out, then the pool is shuffled again."""
    count = max(0, min(int(count), AP_COMPANION_MAX))
    names = [n for n in names if n] or ["Companion"]
    plan: typing.List[typing.Dict[str, typing.Any]] = []
    looks: typing.List[typing.Tuple[int, int]] = []
    for k in range(count):
        if not looks:
            looks = list(AP_LOOKS)
            rng.shuffle(looks)
        row, gender = looks.pop()
        base = names[k % len(names)][:20]
        turn = k // len(names)
        n = k + 1
        plan.append({
            "n": n,
            "name": base if turn == 0 else f"{base} {turn + 1}",
            "appearance": row,
            "gender": gender,
            "portrait": rng.choice(AP_PORTRAITS[gender]),
            "class": rng.choice(AP_CLASSES),
            "slot": AP_COMPANION_FIRST_SLOT + k,
            "template": AP_COMPANION_TEMPLATE.format(n=n),
            "tag": AP_COMPANION_TAG.format(row=row, n=n),
        })
    return plan
