"""Slot rules from th4src: ITEM_SLOT order (enums.h), BaseSlots layout and
equip locations (InventoryPanel.cpp), belt rule (InventoryPanel.cpp ~line 384:
1x1, UseOnceFlag, not gold, EL_7_INVENTORY)."""

# index, name, x, y (pixels in the 320-wide char panel), w, h (cells), allowed equip locations
SLOTS = [
    (0, "Head", 133, 2, 2, 2, ("EL_4_HEAD",)),
    (1, "Left ring", 90, 150, 1, 1, ("EL_5_FINGER",)),
    (2, "Right ring", 203, 150, 1, 1, ("EL_5_FINGER",)),
    (3, "Amulet", 205, 32, 1, 1, ("EL_6_NECK",)),
    (4, "Left hand", 18, 32, 2, 4, ("EL_1_ONE_HANDED", "EL_2_TWO_HANDED")),
    (5, "Right hand", 249, 32, 2, 4, ("EL_1_ONE_HANDED", "EL_2_TWO_HANDED")),
    (6, "Body", 132, 76, 2, 3, ("EL_3_TORSO",)),
    (7, "Belt", 133, 166, 2, 1, ("EL_9_WAIST",)),
    (8, "Gloves", 18, 148, 2, 2, ("EL_10_HANDS",)),
    (9, "Boots", 249, 148, 2, 2, ("EL_11_FEET",)),
    (10, "Left ring 2", 90, 182, 1, 1, ("EL_5_FINGER",)),
    (11, "Left ring 3", 90, 118, 1, 1, ("EL_5_FINGER",)),
    (12, "Left ring 4", 90, 86, 1, 1, ("EL_5_FINGER",)),
    (13, "Right ring 2", 203, 182, 1, 1, ("EL_5_FINGER",)),
    (14, "Right ring 3", 203, 118, 1, 1, ("EL_5_FINGER",)),
    (15, "Right ring 4", 203, 86, 1, 1, ("EL_5_FINGER",)),
    (16, "Amulet 2", 92, 32, 1, 1, ("EL_6_NECK",)),
]
SLOT_NAMES = [s[1] for s in SLOTS]

CATEGORY = {
    "IC_1_SWORD": "Swords", "IC_21_KNIFE": "Knives", "IC_2_AXE": "Axes", "IC_3_BOW": "Bows",
    "IC_4_MACE": "Maces & clubs", "IC_22_MALLET": "Mallets", "IC_10_STAFF": "Staves",
    "IC_20_CLAW": "Claws", "IC_23_PISTOL": "Pistols", "IC_19_TRAP": "Traps", "IC_5_SHIELD": "Shields",
    "IC_6_LIGHT_ARMOR": "Light armor", "IC_8_MID_ARMOR": "Medium armor", "IC_9_HEAVY_ARMOR": "Heavy armor",
    "IC_7_HELM": "Helms", "IC_12_RING": "Rings", "IC_13_AMULET": "Amulets", "IC_15_GLOVE": "Gloves",
    "IC_16_BOOTS": "Boots", "IC_17_BELT": "Belts", "IC_18_FLASK": "Flasks", "IC_11_GOLD": "Gold",
}


def category(b):
    c = CATEGORY.get(b.get("itemCode"))
    if c:
        return c
    mc = b.get("magicCode", "")
    if "POTION" in mc or "ELIXIR" in mc:
        return "Potions & elixirs"
    if "SCROLL" in mc or "RELIC" in mc:
        return "Relicts & scrolls"
    if "BOOK" in mc:
        return "Books"
    if "GEM" in mc:
        return "Gems"
    if "OIL" in mc:
        return "Oils"
    return "Other"


def belt_ok(b):
    return (b.get("equipLoc") == "EL_7_INVENTORY" and str(b.get("useOnce")) == "1"
            and b.get("itemCode") != "IC_11_GOLD" and b.get("w") in (None, 1) and b.get("h") in (None, 1))


def allowed(b, container, slot=None):
    """container: 'equip' (slot = ITEM_SLOT index), 'belt', 'inv', 'stash'."""
    if not b.get("name"):
        return False
    if container == "equip":
        return b.get("equipLoc") in SLOTS[slot][6]
    if container == "belt":
        return belt_ok(b)
    return True


def why_not(b, container, slot=None):
    if allowed(b, container, slot):
        return ""
    if container == "equip":
        return "%s cannot go in the %s slot (needs %s)." % (b.get("name"), SLOTS[slot][1], "/".join(SLOTS[slot][6]))
    if container == "belt":
        return "%s cannot go in the belt (only 1x1 use-once items like potions and scrolls)." % b.get("name")
    return "not allowed"
