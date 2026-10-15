"""Item descriptions (HTML) for tooltips and the details panels. Data: base_items.json /
game.json (BaseItems.cpp, UniqueItems.cpp, Affixes.cpp). Pure Python, no Qt.

Until the item generator is ported, the panel shows base table ranges. Magic bonuses
are not computed; the panel says they are set by the seed.
"""
import html, re
from .data import BASE_ITEMS, UNIQUES, GAME, SPELLS, base_name, is_set_unique
from . import catalog
from .icons import icon_file
from th4save.items import D_UNIQ
from th4save.rules import category

ML_NAMES = {0: "Normal", 1: "Magic", 2: "Unique", 3: "Set"}
SEED_NOTE = "Magic bonuses are set by the seed."
UNIQ_BY_BASE = {}
for _uid, _u in UNIQUES.items():
    UNIQ_BY_BASE.setdefault(_u["baseId"], []).append(_uid)
_SPELL_KEY = {}


def _title(tok):
    tok = re.sub(r"^(AE|EA|ST|ET|MC|PS|IC|EL|ITEM)_(\d+_)?", "", tok or "")
    return tok.replace("_", " ").strip().capitalize()


def _pairs(nums):
    out = []
    for a, b in ((nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5]) if len(nums) > 5 else (0, 0)):
        if a or b:
            out.append(str(a) if a == b else "%d–%d" % (min(a, b), max(a, b)))
    return " / ".join(out)


def effect_text(eff):
    """[AE_ID, type, n1..n6] -> 'Stat Strength: 10–15'."""
    ae, typ, *nums = eff
    name = _title(ae)
    t = str(typ)
    if ae == "AE_FLAG":
        return _title(t)
    if t not in ("0", "", "-1"):
        name += " " + (_title(t) if not t.startswith("PS_") else _title(t))
    v = _pairs(nums + [0] * (6 - len(nums)))
    return name + (": " + v if v else "")


def magic_level(item):
    return (item["magicLevelAndIdentified"] >> 1) & 0x7F


def linked_unique(item):
    """Unique row to show, or None. Index 0 is a real unique, so a plain item must not match it."""
    if item is None or item.empty:
        return None
    uid = int(item["uniqIndex"])
    marked = bool(item["dropType"] & D_UNIQ) or magic_level(item) in (2, 3)
    if uid not in UNIQUES:
        return None
    if marked or uid:
        return uid
    return None


def item_name(item):
    if item is None or item.empty:
        return "(empty)"
    uid = linked_unique(item)
    if uid is not None:
        tag = "SET" if is_set_unique(uid) else "UNIQUE"
        return "%s  %s" % (tag, UNIQUES[uid]["name"])
    return base_name(item["baseItemIndex"])


def identified(item):
    return bool(item["magicLevelAndIdentified"] & 1)


def base_of(idx):
    return BASE_ITEMS[idx] if 0 <= idx < len(BASE_ITEMS) else None


def _rng(a, b):
    return str(a) if a == b else "%d–%d" % (a, b)


def base_lines(b):
    """Static facts from BaseItems.cpp."""
    L = []
    d = b.get("dmg") or [0, 0, 0, 0]
    if any(d):
        L.append("Damage: %s to %s" % (_rng(d[0], d[1]), _rng(d[2], d[3])))
    a = b.get("armor") or [0, 0]
    if any(a):
        L.append("Armor: %s" % _rng(a[0], a[1]))
    try:
        dmin, dmax = int(b.get("durMin") or 0), int(b.get("durMax") or 0)
    except ValueError:
        dmin = dmax = 0
    if dmax:
        L.append("Durability: %s" % _rng(dmin, dmax))
    req = [("%s %s" % (k, _rng(*v))) for k, v in (b.get("req") or {}).items() if any(v)]
    if req:
        L.append("Requires: " + ", ".join(req) + "  <i>(exact value rolled in this range)</i>")
    mc = b.get("magicCode", "")
    if mc and mc != "MC_0_NONE":
        L.append("Base effect: %s" % _title(mc))
    sp = b.get("spell", "")
    if sp and sp != "PS_0_NONE":
        L.append("Spell: %s" % _title(sp))
    for e in b.get("effects") or []:
        L.append("Built-in: %s" % effect_text(e))
    if b.get("classMask") and b["classMask"] != "IPCM_ALL_CLASSES":
        L.append("Classes: %s" % _title(b["classMask"].replace("IPCM_", "")).replace("Any ", "any "))
    if b.get("w"):
        L.append("Size: %dx%d cells" % (b["w"], b["h"]))
    if b.get("price") and any(b["price"]):
        L.append("Base price: %s gold" % _rng(*b["price"]))
    return L


def unique_lines(uid, header=True):
    u = UNIQUES.get(uid)
    if u is None:
        return ["Unique #%d: not in UniqueItems.cpp" % uid]
    L = ["<b style='color:#d9a93c'>%s</b> (unique #%d, qlvl %d)" % (html.escape(u["name"]), uid, u["qlvl"])] if header else []
    L += ["• " + html.escape(effect_text(e)) for e in u["effects"]]
    return L


def _icon_html(b, classic):
    """Picture only when a decoded frame is already on disk. Never starts an MPQ read."""
    path = icon_file(b, classic)
    if not path:
        return ""
    src = html.escape(path.replace("\\", "/"), quote=True)
    return '<img src="%s" width="56">' % src


def _panel_lines(b, view, classic, skip_durability=False):
    """Shared hover body: base table numbers, who can wear it, and rank in this slot."""
    L = []
    img = _icon_html(b, classic)
    if img:
        L.append(img)
    L.append("%s · %s · base #%s · qlvl %s" % (
        category(b), html.escape(catalog.slot_phrase(b.get("equipLoc"))), b["baseId"], b["qlvl"]))
    for line in base_lines(b):
        if line.startswith("Classes:"):
            continue
        if skip_durability and line.startswith("Durability:"):
            continue
        L.append(line)
    L.append("These numbers are the base table ranges.")
    cls = catalog.game_class_line(b.get("classMask"))
    if cls:
        L.append(html.escape(cls))
    if view and b["baseId"] in catalog.NO_EXILE and view.get("exile"):
        L.append("[Can't wear item]")
    badges = ", ".join(catalog.badges(b))
    if badges:
        L.append("Limits: %s" % html.escape(badges))
    rank = catalog.rank_text(b)
    if rank:
        L.append(html.escape(rank))
    return L


def describe_base(b, html_out=True, view=None, classic=False):
    if b is None:
        return "?"
    L = ["<b>%s</b>" % html.escape(b["name"])]
    L += _panel_lines(b, view, classic)
    uq = UNIQ_BY_BASE.get(b["baseId"], [])
    if uq:
        names = ", ".join(html.escape(UNIQUES[u]["name"]) for u in uq[:8]) + (" …" if len(uq) > 8 else "")
        L.append("Uniques on this base (%d): %s" % (len(uq), names))
    if can_be_magic(b):
        L.append("<i>%s</i>" % SEED_NOTE)
    return "<br>".join(L)


def can_be_magic(b):
    """Weapons, armor and jewelry roll affixes/uniques; potions, oils, gold, scrolls do not."""
    return bool(b) and str(b.get("useOnce", "0")) in ("0", "") and b.get("itemCode") != "IC_11_GOLD" \
        and (b.get("itemType") in ("ITEM_1_WEAPON", "ITEM_2_ARMOR") or b.get("itemCode") in ("IC_12_RING", "IC_13_AMULET")
             or UNIQ_BY_BASE.get(b["baseId"]))


def describe_item(item, slot="", view=None, classic=False):
    """Placed item: the game-style panel. Bonuses stay "set by the seed" until the generator exists."""
    if item is None or item.empty:
        return "(empty)"
    b = base_of(item["baseItemIndex"])
    ml = magic_level(item)
    L = []
    if slot:
        L.append("<i>%s</i>" % html.escape(str(slot)))
    L.append("<b>%s</b>" % html.escape(item_name(item)))
    L.append("%s · %s%s" % (category(b) if b else "?", ML_NAMES.get(ml, "level %d" % ml),
                            "" if identified(item) or ml == 0 else " (unidentified)"))
    if item["baseDurability"] > 0:
        L.append("Durability now: %d / %d" % (item["curDurability"], item["baseDurability"]))
    if item["baseCharges"] > 0:
        L.append("Charges now: %d / %d" % (item["curCharges"], item["baseCharges"]))
    if item["amount"] > 1:
        L.append("Quantity: %s" % format(item["amount"], ","))
    if b:
        L += _panel_lines(b, view, classic, skip_durability=True)
    uid = linked_unique(item)
    if uid is not None:
        L += unique_lines(uid, header=False)
        L.append("Who: %s. %s." % (catalog.who_for(b), catalog.rarity_mark(UNIQUES[uid]["qlvl"])))
    elif b and can_be_magic(b):
        L.append("<i>%s</i>" % SEED_NOTE)
    elif ml == 1:
        L.append("<i>%s</i>" % SEED_NOTE)
    if ml == 1:
        L.append("<i>Prefix and suffix names are in Help › Uniques &amp; affixes.</i>")
    L.append("Seed: %d" % item["seed"])
    return "<br>".join(L)


def affix_rows():
    for a in GAME["affixes"]:
        yield (a["kind"], a["name"], effect_text([a["effect"], a["type"], *a["nums"]]), a["qlvl"], a["id"])
