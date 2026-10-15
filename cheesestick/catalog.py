"""Base-item facts and who can use them.

Mode (classic / hell / both) and ForbiddenForExiles come from item_flags.json,
generated from BaseItems.cpp. Class masks are the IPCM_* bits in enums.h.
The editor does not copy item art.
"""
import json, os
from fractions import Fraction
from .data import BASE_ITEMS, GAME
from th4save.rules import category

_PFC = [
    "WARRIOR", "INQUISITOR", "GUARDIAN", "TEMPLAR",
    "ARCHER", "SCOUT", "SHARPSHOOTER", "TRAPPER",
    "MAGE", "ELEMENTALIST", "DEMONOLOGIST", "NECROMANCER", "BEASTMASTER", "WARLOCK",
    "MONK", "KENSEI", "SHUGOKI", "SHINOBI",
    "ROGUE", "ASSASSIN", "IRON_MAIDEN", "BOMBARDIER",
    "SAVAGE", "BERSERKER", "EXECUTIONER", "THRAEX", "MURMILLO", "DIMACHAERUS", "SECUTOR", "DRUID",
]


def _bits(*names):
    v = 0
    for n in names:
        v |= 1 << _PFC.index(n)
    return v


IPCM = {"IPCM_%s" % n: (1 << i) for i, n in enumerate(_PFC)}
IPCM.update({
    "IPCM_ANY_WARRIOR": _bits("WARRIOR", "INQUISITOR", "GUARDIAN", "TEMPLAR"),
    "IPCM_ANY_ARCHER": _bits("ARCHER", "SCOUT", "SHARPSHOOTER", "TRAPPER"),
    "IPCM_ANY_SUMMONER": _bits("DEMONOLOGIST", "NECROMANCER", "BEASTMASTER"),
    "IPCM_ANY_MAGE": _bits("MAGE", "ELEMENTALIST", "DEMONOLOGIST", "NECROMANCER", "BEASTMASTER", "WARLOCK"),
    "IPCM_ANY_MONK": _bits("MONK", "KENSEI", "SHUGOKI", "SHINOBI"),
    "IPCM_ANY_ROGUE": _bits("ROGUE", "ASSASSIN", "IRON_MAIDEN", "BOMBARDIER"),
    "IPCM_ANY_GLADIATOR": _bits("THRAEX", "MURMILLO", "DIMACHAERUS", "SECUTOR"),
    "IPCM_ANY_EXILE": _bits("EXECUTIONER", "THRAEX", "MURMILLO", "DIMACHAERUS", "SECUTOR"),
    "IPCM_ANY_SAVAGE": _bits("SAVAGE", "BERSERKER", "EXECUTIONER", "THRAEX", "MURMILLO", "DIMACHAERUS", "SECUTOR", "DRUID"),
    "IPCM_ALL_CLASSES": 0xFFFFFFFF,
})
# Item.cpp CheckItemReq: exiles are executioner and the four gladiators. Druid is not an exile.
EXILE_FCIDS = {24, 25, 26, 27, 28}
# Main.cpp isTownPortalForbidden: IRON (ironman, survival) and NIGHTMARE (nightmare, speedrun).
NO_PORTAL_MODES = {2, 3, 5, 7}
# Dropped in multiplayer and skipped in single player (Item.cpp). Not an equip check for elixirs.
MP_SPELLS = {"PS_32_BONE_SPIRIT_REAL_RESSURECT", "PS_34_HEAL_OTHER"}
PORTAL_SPELLS = {"PS_7_TOWN_PORTAL"}
ALL = 0xFFFFFFFF
GROUP_LABEL = {
    "IPCM_ANY_WARRIOR": "Warriors", "IPCM_ANY_ARCHER": "Archers", "IPCM_ANY_MAGE": "Mages",
    "IPCM_ANY_SUMMONER": "Summoners", "IPCM_ANY_MONK": "Monks", "IPCM_ANY_ROGUE": "Rogues",
    "IPCM_ANY_GLADIATOR": "Gladiators", "IPCM_ANY_EXILE": "Exiles", "IPCM_ANY_SAVAGE": "Savages",
}
_REQ = (("Str", "Strength"), ("Mag", "Magic"), ("Dex", "Dexterity"), ("Vit", "Vitality"), ("Lvl", "level"))

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "item_flags.json"), encoding="utf-8") as _f:
    _FLAGS = json.load(_f)
CLASSIC = set(_FLAGS["classic"])
BOTH = set(_FLAGS["both"])
NO_EXILE = set(_FLAGS["no_exile"])


def mode_of(base_id):
    """0 hell-only, 1 classic-only, 2 both. Hell-only is the default and is not stored."""
    if base_id in BOTH:
        return 2
    if base_id in CLASSIC:
        return 1
    return 0


def mask_of(expr):
    """IPCM expression -> bits, ALL, or None when a token is unknown."""
    expr = (expr or "").strip()
    if not expr or expr == "IPCM_ALL_CLASSES":
        return ALL
    val = 0
    for part in expr.split("|"):
        part = part.strip()
        if not part:
            continue
        bit = IPCM.get(part)
        if bit is None:
            return None
        val |= bit
    return val & ALL


def _class_name(bit):
    classes = GAME["full_classes"]
    if 0 <= bit < len(classes):
        return classes[bit]["name"]
    return "Class %d" % bit


def who_for(b):
    """Who can wear this base. Empty class mask means every class."""
    if not b:
        return "Unknown"
    return class_label(b.get("classMask")) or "Anyone"


def rarity_mark(qlvl):
    """QualityLevel from UniqueItems.cpp. 40 and above is marked Rare; the number is the game's own level."""
    try:
        q = int(qlvl)
    except (TypeError, ValueError):
        q = 0
    if q >= 40:
        word = "Rare"
    elif q >= 20:
        word = "Uncommon"
    else:
        word = "Common"
    return "%s · %d" % (word, q)


def class_label(expr):
    expr = (expr or "").strip()
    if not expr or expr == "IPCM_ALL_CLASSES":
        return ""
    if "|" in expr:
        return "Class limited"
    if expr in GROUP_LABEL:
        return GROUP_LABEL[expr]
    bit = IPCM.get(expr)
    if bit and bit & (bit - 1) == 0:
        return _class_name(bit.bit_length() - 1)
    return "Class limited"


def badges(b):
    """Static limits printed on the row. Hell-only items are not badged; they are the majority."""
    if not b:
        return []
    out = []
    mode = mode_of(b["baseId"])
    if mode == 1:
        out.append("Classic")
    if b["baseId"] in NO_EXILE:
        out.append("No exiles")
    label = class_label(b.get("classMask"))
    if label:
        out.append(label)
    spell = b.get("spell") or ""
    if spell in MP_SPELLS:
        out.append("Multiplayer")
    if spell in PORTAL_SPELLS:
        out.append("No town portal")
    return out


def limits(b, view):
    """Reasons this character cannot use the item. Empty means usable. view None means unknown."""
    if not b or not view:
        return []
    out = []
    mode = mode_of(b["baseId"])
    if mode == 1 and not view["classic"]:
        out.append("Classic only")
    elif mode == 0 and view["classic"]:
        out.append("Not usable in classic")
    mask = mask_of(b.get("classMask"))
    if mask is None:
        out.append("Class restriction could not be read")
    elif mask != ALL and not (mask & (1 << view["fcid"])):
        out.append("Not for this class")
    if b["baseId"] in NO_EXILE and view["exile"]:
        out.append("Exiles cannot use this")
    spell = b.get("spell") or ""
    if spell in MP_SPELLS and not view["mp"]:
        out.append("Multiplayer only")
    if spell in PORTAL_SPELLS and view["mode"] in NO_PORTAL_MODES:
        out.append("Town portal is disabled in this mode")
    stats = view["stats"]
    for key, label in _REQ:
        pair = (b.get("req") or {}).get(key) or [0, 0]
        try:
            lo = int(pair[0])
        except (TypeError, ValueError):
            lo = 0
        if lo > stats.get(key, 0):
            out.append("Needs %d %s" % (lo, label))
    return out


def restriction_message(b, view):
    reasons = limits(b, view)
    if not reasons:
        return ""
    return "%s was added, but this character may not be able to use it:\n- %s" % (
        b.get("name") or "Item", "\n- ".join(reasons))


def view_from(main):
    """Character tab values the hide-unusable filter compares against. None if no save is open."""
    if main is None or not getattr(main, "save", None):
        return None
    from . import caps
    p = main.save.player
    fid = caps.fcid(p)
    return {
        "fcid": fid,
        "classic": bool(caps.classic(p)),
        "exile": fid in EXILE_FCIDS,
        "mode": p["gameMode"],
        "mp": main.save.hero_entry == "mphero",
        "stats": {
            "Str": main.c_str.value(), "Mag": main.c_mag.value(), "Dex": main.c_dex.value(),
            "Vit": main.c_vit.value(), "Lvl": main.ui_level(),
        },
    }


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _rng(a, b):
    return str(a) if a == b else "%d–%d" % (a, b)


def fact_of(b):
    """Display text plus the number used for sorting, filtering and compare."""
    d = [_num(x) for x in (b.get("dmg") or [0, 0, 0, 0])[:4]]
    while len(d) < 4:
        d.append(0)
    a = [_num(x) for x in (b.get("armor") or [0, 0])[:2]]
    while len(a) < 2:
        a.append(0)
    dmin, dmax = _num(b.get("durMin")), _num(b.get("durMax"))
    req = {}
    for key, _label in _REQ:
        pair = (b.get("req") or {}).get(key) or [0, 0]
        lo, hi = _num(pair[0]), _num(pair[1] if len(pair) > 1 else pair[0])
        req[key] = ("" if not (lo or hi) else _rng(lo, hi), lo)
    w, h = b.get("w"), b.get("h")
    if w and h:
        size_text, size = "%dx%d" % (w, h), w * h
    else:
        size_text, size = "?", None
    q = _num(b.get("qlvl"))
    return {
        "name": b.get("name") or "",
        "cat": category(b),
        "dmg_text": "" if not any(d) else "%s to %s" % (_rng(d[0], d[1]), _rng(d[2], d[3])),
        "dmg": d[3],
        "armor_text": "" if not any(a) else _rng(a[0], a[1]),
        "armor": a[1],
        "dur_text": "" if not dmax else _rng(dmin, dmax),
        "dur": dmax,
        "req": req,
        "size_text": size_text,
        "size": size,
        "qlvl": q,
        "limits": ", ".join(badges(b)),
    }


_FACTS = None


def facts():
    global _FACTS
    if _FACTS is None:
        _FACTS = {b["baseId"]: fact_of(b) for b in BASE_ITEMS if b.get("name")}
    return _FACTS


# Item.cpp printItemClassReqInfo walks these groups in this order. Mage wins over
# Summoner, and Savage wins over Gladiator, when both would match. The buffer holds
# two groups; a third makes the game print "Available to multiple classes".
_GROUP_STEPS = (
    ((IPCM["IPCM_ANY_WARRIOR"], "Warriors"),),
    ((IPCM["IPCM_ANY_ARCHER"], "Archers"),),
    ((IPCM["IPCM_ANY_MAGE"], "Mages"), (IPCM["IPCM_ANY_SUMMONER"], "Summoners")),
    ((IPCM["IPCM_ANY_MONK"], "Monks"),),
    ((IPCM["IPCM_ANY_ROGUE"], "Rogues"),),
    ((IPCM["IPCM_ANY_SAVAGE"], "Savages"), (IPCM["IPCM_ANY_GLADIATOR"], "Gladiators")),
)
_SLOT_PHRASE = {
    "EL_1_ONE_HANDED": "one-handed", "EL_2_TWO_HANDED": "two-handed", "EL_3_TORSO": "body",
    "EL_4_HEAD": "head", "EL_5_FINGER": "ring", "EL_6_NECK": "amulet",
    "EL_7_INVENTORY": "inventory", "EL_9_WAIST": "belt", "EL_10_HANDS": "gloves",
    "EL_11_FEET": "boots",
}


def slot_phrase(loc):
    if not loc:
        return "no slot"
    return _SLOT_PHRASE.get(loc, loc)


def _class_names(mask, limit):
    classes = GAME["full_classes"]
    out = []
    for i in range(min(len(_PFC), len(classes))):
        if mask & (1 << i):
            out.append(classes[i]["name"])
            if len(out) >= limit:
                break
    return out


def _matching_groups(mask):
    """Groups whose bits sit entirely inside the mask, in the game's check order."""
    found, check = [], 0
    for options in _GROUP_STEPS:
        for bits, name in options:
            if bits and (mask & bits) == bits:
                if len(found) < 2:
                    found.append(name)
                    check |= bits
                break
    return found, (check & ALL) == (mask & ALL)


def _class_list(mask):
    """Used where the game would collapse the line to "Available to multiple classes"."""
    names = _class_names(mask, len(_PFC))
    if not names:
        return "[Available to multiple classes]"
    return "Classes: " + ", ".join(names)


def _class_req_phrase(required):
    """Same brackets as printItemClassReqInfoInBuffer, without the current player's traits."""
    required &= ALL
    count = bin(required).count("1")
    if count < 16:
        if count <= 2:
            names = _class_names(required, 2)
            if count == 1 and len(names) == 1:
                return "[%s only]" % names[0]
            if count == 2 and len(names) == 2:
                return "[%s and %s only]" % (names[0], names[1])
            return _class_list(required)
        groups, exact = _matching_groups(required)
        if not exact or not groups:
            return _class_list(required)
        if len(groups) == 1:
            return "[%s only]" % groups[0]
        return "[%s and %s only]" % (groups[0], groups[1])
    inv = (~required) & ALL
    dis = 32 - count
    if dis <= 2:
        names = _class_names(inv, 2)
        if dis == 1 and len(names) == 1:
            return "[for all but %s]" % names[0]
        if dis == 2 and len(names) == 2:
            return "[for all but %s and %s]" % (names[0], names[1])
        return _class_list(required)
    groups, exact = _matching_groups(inv)
    if not exact or not groups:
        return _class_list(required)
    if len(groups) == 1:
        return "[for all but %s]" % groups[0]
    return "[for all but %s and %s]" % (groups[0], groups[1])


def game_class_line(expr):
    """Who can wear it, in the game's bracket. No line when every class can.

    The game skips the line for IPCM_ALL_CLASSES. Trait overrides (Mamluk, Elementalist,
    and the rest) rewrite the line for the player who is looking, so a catalog tooltip
    keeps the base mask. When the game would say "Available to multiple classes", the
    classes are listed instead.
    """
    mask = mask_of(expr)
    if mask is None:
        return "Class restriction could not be read"
    if mask == ALL:
        return ""
    if mask == 0:
        return "[No one can wear it]"
    return _class_req_phrase(mask)


def rank_group(b):
    """Category plus equip slot. A sword and a ring are never in the same group."""
    if not b:
        return None
    return (category(b), b.get("equipLoc") or "")


def _level_divisor(b):
    """Low end of the level requirement. 0 counts as 1 so the ratio stays defined."""
    pair = (b.get("req") or {}).get("Lvl") or [0, 0]
    lo = _num(pair[0] if pair else 0)
    return lo if lo > 0 else 1


def _score_parts(b):
    d = [_num(x) for x in (b.get("dmg") or [0, 0, 0, 0])[:4]]
    while len(d) < 4:
        d.append(0)
    a = [_num(x) for x in (b.get("armor") or [0, 0])[:2]]
    while len(a) < 2:
        a.append(0)
    if any(d):
        return "damage", d[3], _level_divisor(b)
    if any(a):
        return "armor", a[1], _level_divisor(b)
    return None


_RANKS = None


def _ranks():
    global _RANKS
    if _RANKS is not None:
        return _RANKS
    groups = {}
    for b in BASE_ITEMS:
        if not b.get("name"):
            continue
        parts = _score_parts(b)
        if parts is None:
            continue
        metric, value, den = parts
        groups.setdefault(rank_group(b), []).append((b["baseId"], value, den, metric))
    out = {}
    for key, rows in groups.items():
        rows.sort(key=lambda t: (Fraction(-t[1], t[2]), t[0]))
        total = len(rows)
        i = 0
        while i < total:
            score = Fraction(rows[i][1], rows[i][2])
            j = i + 1
            while j < total and Fraction(rows[j][1], rows[j][2]) == score:
                j += 1
            for k in range(i, j):
                bid, value, den, metric = rows[k]
                out[bid] = {
                    "rank": i + 1, "total": total, "value": value, "den": den,
                    "metric": metric, "group": key,
                }
            i = j
    _RANKS = out
    return out


def rank_info(b):
    """Competition rank inside this category and slot, or None when there is nothing to score."""
    if not b:
        return None
    return _ranks().get(b["baseId"])


# Weapon types each class is published as using, ahead of other categories.
# Inside one category, defense (armor) or damage still decides, then built-in magic.
# The Google sheet the trainer was pointed at is a TH2 perk calculator (Strong Arm, Overdraw),
# not a gear list. The unique-item wiki is The Hell 1, split into strength, dexterity, and
# magic lines (bows on dexterity, swords/axes/maces on strength, wands and staves on magic;
# several staves are noted as made for monks). TH4's class compendium matches that split:
# archers want bows, mages want staves over raw armor, warriors and savages
# want melee weapons and then armor. Inquisitors are called out for scepters (maces).
# Druid and bombardier have no weapon named in those sources, so they follow the parent
# (savage and rogue). Rolled resists, crit, thorns, dread, and ruin are not in the base
# table, so they are not part of this order. Traits (Pistoleer, Barbarian, and the rest)
# are not on the character view.
_MELEE_WEAPONS = frozenset({
    "IC_1_SWORD", "IC_2_AXE", "IC_4_MACE", "IC_22_MALLET", "IC_21_KNIFE",
})
_MACES = frozenset({"IC_4_MACE"})
_BOWS = frozenset({"IC_3_BOW"})
_STAVES = frozenset({"IC_10_STAFF"})
_BOWS_AND_TRAPS = frozenset({"IC_3_BOW", "IC_19_TRAP"})
_ARMOR = frozenset({
    "IC_5_SHIELD", "IC_6_LIGHT_ARMOR", "IC_8_MID_ARMOR", "IC_9_HEAVY_ARMOR", "IC_7_HELM",
    "IC_15_GLOVE", "IC_16_BOOTS", "IC_17_BELT",
})
# fcid -> preferred item codes, best tier first. A code is in one tier only.
_CLASS_GEAR = {}
for _i in (0, 2, 3, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29):
    _CLASS_GEAR[_i] = (_MELEE_WEAPONS, _ARMOR)
_CLASS_GEAR[1] = (_MACES, _MELEE_WEAPONS - _MACES, _ARMOR)  # inquisitor: scepters
for _i in (4, 5, 6):
    _CLASS_GEAR[_i] = (_BOWS, _ARMOR)  # archer, scout, sharpshooter
_CLASS_GEAR[7] = (_BOWS_AND_TRAPS, _ARMOR)  # trapper
for _i in range(8, 14):
    _CLASS_GEAR[_i] = (_STAVES, _ARMOR)  # mage family
for _i in range(14, 18):
    _CLASS_GEAR[_i] = (_STAVES, _MELEE_WEAPONS, _ARMOR)  # monks: staves, then other melee


def type_preference(b, view=None):
    """Lower is the gear this class is published as wanting. Same for one item code.

    Two helms therefore still sort by defense. No character, or an unknown class, returns
    the same tier for every item.
    """
    fcid = None if not view else view.get("fcid")
    ranks = _CLASS_GEAR.get(fcid)
    if not ranks:
        return 1
    code = (b or {}).get("itemCode") or ""
    for i, codes in enumerate(ranks):
        if code in codes:
            return i
    return len(ranks)


_CAT_BEST = None


def _category_best():
    """Highest defense or damage in each category. Used only to order categories that share a tier."""
    global _CAT_BEST
    if _CAT_BEST is not None:
        return _CAT_BEST
    best = {}
    for b in BASE_ITEMS:
        if not b.get("name"):
            continue
        primary, _magic = item_power(b)
        cat = category(b)
        if primary > best.get(cat, 0):
            best[cat] = primary
    _CAT_BEST = best
    return best


def magic_magnitude(b):
    """Strength of magic already written on the base, before the item seed rolls affixes.

    A non-zero built-in effect counts, and so does a spell carried by the base.
    The magic code is the item family (potion, staff, oil), not a bonus.
    """
    if not b:
        return 0
    mag = 0
    spell = b.get("spell") or ""
    if spell and spell != "PS_0_NONE":
        mag += 1
    for eff in b.get("effects") or []:
        peak = 0
        for n in eff[2:]:
            try:
                peak = max(peak, abs(int(n)))
            except (TypeError, ValueError):
                pass
        if peak:
            mag += peak
    return mag


def item_power(b):
    """(primary, magic). Armor is ranked by defense. Weapons are ranked by damage."""
    if not b:
        return 0, 0
    dmg = [_num(x) for x in (b.get("dmg") or [0, 0, 0, 0])[:4]]
    armor = [_num(x) for x in (b.get("armor") or [0, 0])[:2]]
    while len(dmg) < 4:
        dmg.append(0)
    while len(armor) < 2:
        armor.append(0)
    defense = armor[1] if any(armor) else 0
    damage = dmg[3] if any(dmg) else 0
    if b.get("itemType") == "ITEM_2_ARMOR" or (defense and not damage):
        primary = defense
    else:
        primary = damage
    return primary, magic_magnitude(b)


def power_key(b, view=None):
    """Lower sorts first: usable, then the class's preferred type, then defense or damage, then built-in magic."""
    usable = 1 if view is not None and limits(b, view) else 0
    primary, magic = item_power(b)
    tier = type_preference(b, view) if view and view.get("fcid") is not None else 0
    return (usable, tier, -primary, -magic, (b.get("name") or "").lower(), b.get("baseId") or 0)


def better_sort_key(b, view=None):
    """Preferred types for this class first. Inside one type, higher defense or damage, then built-in magic.

    A sword's damage is not compared with a helm's armor: those types sit in different tiers, and
    categories that share a tier stay in one block.
    """
    usable = 1 if view is not None and limits(b, view) else 0
    primary, magic = item_power(b)
    cat = category(b)
    name = (b.get("name") or "").lower()
    bid = b.get("baseId") or 0
    loc = b.get("equipLoc") or ""
    if view and view.get("fcid") is not None:
        group = (type_preference(b, view), -_category_best().get(cat, 0), cat.lower())
    else:
        group = (0, 0, cat.lower())
    return (usable,) + group + (loc, -primary, -magic, name, bid)


def rank_text(b):
    rec = rank_info(b)
    if not rec:
        return ""
    cat, loc = rec["group"]
    metric = "max damage" if rec["metric"] == "damage" else "max armor"
    if rec["den"] and rec["value"] % rec["den"] == 0:
        shown = str(rec["value"] // rec["den"])
    else:
        shown = "%.2f" % (rec["value"] / rec["den"])
    return ("Rank %d of %d among %s, %s, by %s ÷ level requirement (%d ÷ %d = %s). "
            "A level requirement of 0 counts as 1." % (
                rec["rank"], rec["total"], cat, slot_phrase(loc), metric,
                rec["value"], rec["den"], shown))
