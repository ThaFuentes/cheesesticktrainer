"""Game caps, reproduced from the TH4 source (roboserg/the-hell-4-src). Pure Python, no Qt.

Everything the game enforces when it loads / validates a hero (Player.cpp ValidateCurPlayer,
LimitPlayerParams, LimitSpellLevels; Perks.cpp LimitPlayerPerks) is reproduced here, so
"Max" never sets a value the game would clamp or strip.
"""
from .data import GAME, TRAITS

C = GAME["consts"]
CLASSES = GAME["full_classes"]
PERK_INFO = {int(k): v for k, v in GAME["perks"].items()}
SPELL_INFO = {int(k): v for k, v in GAME["spells"].items()}
PERK_KEY = {v["key"]: k for k, v in PERK_INFO.items()}
TRAIT_ID = {v: k for k, v in TRAITS.items()}
GM_CLASSIC, GM_IRONMAN, GM_NIGHTMARE, GM_SPEEDRUN = 9, 2, 3, 7
GC_9_NIGHT_KIN = 9
MAX_GOLD_TOTAL = 2_147_483_647 // C["MaxGoldInCell"] * C["MaxGoldInCell"]   # Player.TotalGold is a signed int
STAT_KEYS = ("BaseStrength", "BaseMagic", "BaseDexterity", "BaseVitality")

# Item.cpp GetPlayerFullClass: (class, subclass) -> PFC index; summoner / gladiator use specialization
_FIRST = {0: 0, 1: 4, 2: 8, 3: 14, 4: 18, 5: 22}


def full_class_id(class_id, sub, spec):
    sub = sub if sub >= 0 else 0
    spec = spec if spec >= 0 else 0
    if class_id == 2:   # Mage, Elementalist, Summoner(Demonologist, Necromancer, Beastmaster), Warlock
        return {0: 8, 1: 9, 2: 10 + (spec if spec in (1, 2) else 0), 3: 13}.get(sub, 8)
    if class_id == 5:   # Savage, Berserker, Executioner, Gladiator(Thraex, Murmillo, Dimachaerus, Secutor), Druid
        return {0: 22, 1: 23, 2: 24, 3: 25 + (spec if spec in (1, 2, 3) else 0), 4: 29}.get(sub, 22)
    base = _FIRST.get(class_id, 0)
    return base + (sub if sub in (1, 2, 3) else 0)


def fcid(p):
    return full_class_id(p["ClassId"], p["subclassID"], p["specializationID"])


def full_class_name(p):
    return CLASSES[fcid(p)]["name"]


def classic(p):
    return p["gameMode"] == GM_CLASSIC


def has_trait(p, *names):
    ids = {TRAIT_ID[n] for n in names if n in TRAIT_ID}
    return any(t in ids for t in bytes(p["traits"]))


def perk_level(p, key):
    pid = PERK_KEY.get(key)
    return 0 if pid is None else bytes(p["perk"])[pid]


def perk_value(p, key):
    pid = PERK_KEY.get(key)
    if pid is None:
        return 0
    n = bytes(p["perk"])[pid]
    lv = PERK_INFO[pid]["levels"]
    return lv[min(n, len(lv)) - 1]["value"] if n > 0 and lv else 0


def night_kin(p):
    return bool(p["gameChanger"] & (1 << GC_9_NIGHT_KIN))


# ---- stats: Player.cpp GetPlayerMaxStat + LimitPlayerParams stat-sum limit (#MSL)
def max_stats(p):
    r = list(CLASSES[fcid(p)]["max"])
    t = lambda n: has_trait(p, n)
    if t("Mamluk"): r = [475, 150, 475, 400]
    if t("Pistoleer"): r = [600, 50, 400, 450]
    if t("Black_Witchery"): r = [300, 400, 500, 300]
    if t("BendTheRules"): r = [900, 900, 900, 900]
    if t("Gifted"): r = [x + 25 for x in r]
    if t("OldFashioned"): r[2] += 40
    if t("LitheBuild"): r[2] += 100
    if t("Bruiser"): r[0] += 150; r[2] -= 150
    if t("Negotiant"): r[3] -= 50
    if t("Paladin"): r[1] += 200 + perk_value(p, "SYNERGY_THAUMATURGY")
    if t("Leper"): r[1] += 75; r[2] += 75
    if t("Ranger"): r[1] += 40; r[3] -= 40
    if t("Crupellarius"): r[0] -= 100; r[3] += 100
    if t("Giant"): r[3] += 100
    if night_kin(p): r[1] += 225; r[2] += 125; r[0] -= 200
    o = perk_value(p, "SYNERGY_OSTENTATION")
    if o > 0: r = [x + o for x in r]
    if classic(p):
        r = {0: [250, 50, 60, 100], 1: [55, 70, 250, 80], 2: [45, 250, 85, 80]}.get(p["ClassId"], r)
    return [max(0, min(C["Limit_Stat"], x)) for x in r]


def stat_sum_limit(p, level=None):
    clvl = p["CharLevel"] if level is None else level
    t = lambda n: has_trait(p, n)
    if classic(p):
        return 460
    paladin = (200 + perk_value(p, "SYNERGY_THAUMATURGY")) if t("Paladin") else 0
    lim = (10 * clvl + (clvl // 2 + 50 if p["gameMode"] in (GM_IRONMAN, GM_SPEEDRUN, GM_NIGHTMARE) else 0)
           + 90 + (2 * clvl // 3) + (40 if t("BlueBlood") else 0) + (100 if t("Gifted") else 0)
           + (100 if t("Giant") else 0) + paladin + (140 if night_kin(p) else 0)
           + (40 if t("OldFashioned") else 0) + (150 if t("Leper") else 0) + (100 if t("LitheBuild") else 0))
    if t("BendTheRules"):
        lim = min(lim, 1400 + paladin) + perk_value(p, "PERK_RAISE_THE_BAR")
    return lim + 4 * perk_value(p, "SYNERGY_OSTENTATION")


def max_stat_values(p, current, level=None, only=None):
    """Return new [str, mag, dex, vit]: each field raised to its class cap as far as the
    stat-sum limit allows (only=index -> raise just that one). Never lowers a value."""
    caps, lim = max_stats(p), stat_sum_limit(p, level)
    out = list(current)
    order = [only] if only is not None else [3, 0, 2, 1]   # Vit, Str, Dex, Mag
    for i in order:
        room = lim - sum(out)
        if room > 0 and out[i] < caps[i]:
            out[i] = min(caps[i], out[i] + room)
    return out


# ---- level / xp: th2data.cpp PlayerMaxLevel, LevelUp; ValidateCurPlayer clamps Xp <= NextLevelUp
def max_level(p):
    return C["PlayerMaxLevelClassic"] if classic(p) else C["PlayerMaxLevel"]


def xp_for_level(p, level):
    tab = GAME["level_xp_classic"] if classic(p) else GAME["level_xp"]
    level = max(1, min(max_level(p), level))
    return tab[level - 1]          # LevelUpTable[i] = XP needed to reach level i+1


# ---- spells: Player.cpp LimitSpellLevels
def spell_cap(p, spell, level=None):
    clvl = p["CharLevel"] if level is None else level
    info = SPELL_INFO.get(spell)
    if info is None or not (info["mask"] & (1 << fcid(p))):
        return 0
    book_max = C["SpellLevelBookMaxClassic"] if classic(p) else C["SpellLevelBookMax"]
    return min(2 * clvl // 3 + 3, book_max)


# ---- perks: Perks.cpp getPerkMaxLevel (class-mask part); special perks need traits/game changers
def perk_cap(p, pid):
    """(cap, note) like getPerkMaxLevel: levels open while the level row's class mask allows
    the full class and PerkAvailable's special rule (if any) holds. cap None = unknown rule."""
    info = PERK_INFO.get(pid)
    if info is None or not info["levels"]:
        return 0, "no levels in PerksData.cpp"
    if info.get("special"):
        ok = perk_condition(p, info.get("cond"))
        if ok is None:
            return None, "availability depends on rules this editor cannot evaluate"
        if not ok:
            return 0, "not available with your traits / game changers / mode (Perks.cpp PerkAvailable)"
    bit = 1 << fcid(p)
    n = 0
    for lv in info["levels"]:
        if not (lv["mask"] & bit):
            break
        n += 1
    return n, "%d of %d levels open to %s" % (n, len(info["levels"]), full_class_name(p))


def perk_condition(p, cond):
    """Evaluate the PerkAvailable() special-case condition (translated by the extractor)."""
    if not cond:
        return None
    env = dict(T=lambda *n: has_trait(p, *n), GC=lambda n: bool(p["gameChanger"] & (1 << n)),
               GM=p["gameMode"], FC=fcid(p), CID=p["ClassId"], GMT_NORMAL=p["gameMode"] in (0, 4, 6, 8, 9))
    try:
        return bool(eval(cond, {"__builtins__": {}}, env))
    except Exception:
        return None


def perk_points_cap_note():
    return ("The game does not strip perks above your perk-point budget or char-level row "
            "requirement on load; Max uses the class limit the game enforces (LimitPlayerPerks).")


# ---- learned spells: Player.cpp ValidateCurPlayer keeps AvailableSpellMask bits only for book
# spells (BookQuality != -1) and LimitSpellLevels clears spells the class cannot use.
def learned_masks(p, levels):
    """(AvailableSpellMask, AvailableSpellMask_64_128) with a bit for every spell that has a level
    > 0 and can be learned; existing bits are kept. A level without its bit is not usable."""
    lo, hi = p["AvailableSpellMask"] & (2**64 - 1), p["AvailableSpellMask_64_128"] & (2**64 - 1)
    bit = 1 << fcid(p)
    for i in range(1, min(len(levels), 129)):
        info = SPELL_INFO.get(i)
        if levels[i] > 0 and info and info["book"] != -1 and info["mask"] & bit:
            if i <= 64: lo |= 1 << (i - 1)
            else: hi |= 1 << (i - 65)
    to_signed = lambda v: v - 2**64 if v >= 2**63 else v
    return to_signed(lo), to_signed(hi)
