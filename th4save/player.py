"""PlayerInfo_v26 (LastPlayerInfo, save version 26/27) - th4src/src/structs.h.

Packed /Zp1 little-endian, 11,798 bytes. Parse -> edit -> serialize is
byte-exact: every byte (incl. reserved fields) is kept.
"""
import struct

PLAYER_INFO_SIZE = 11798          # public source (save version 26/27)
# Known on-disk sizes by save version. v30 (installed TH4 v0.773) = v26 layout
# + 19 bytes appended after gameMode (found by diffing real saves; meaning unknown,
# preserved verbatim as "tail_unknown").
KNOWN_SIZES = {11798: "v26/27 (public source)", 11817: "v30 (TH4 v0.773)"}
ITEM_SIZE = 64
SIGNATURE_HEL4 = 0x48454C34  # 'HEL4' as MSVC multichar constant -> bytes "4LEH" on disk

CLASS_NAMES = ["Warrior", "Archer", "Mage", "Monk", "Rogue", "Savage"]
GAME_MODES = ["Normal", "Hardcore", "Ironman", "Nightmare", "Easy", "Survival",
              "Hard", "Speedrun", "Coliseum", "Classic", "Outbreak", "Dark"]

# (name, struct fmt) in declaration order of ItemInfo64
ITEM_FIELDS = [
    ("genVersion", "H"), ("saveVersion", "H"), ("dropType", "i"), ("seed", "q"),
    ("quality", "h"), ("magicFind", "h"), ("baseItemIndex", "h"), ("uniqIndex", "h"),
    ("magicLevelAndIdentified", "B"), ("amount", "i"),
    ("curDurability", "h"), ("baseDurability", "h"), ("curCharges", "h"), ("baseCharges", "h"),
    ("socketsAdded", "B"), ("sockets", "6h"), ("enchantIndexes", "5h"),
    ("quenchAffix", "B"), ("quenchLevel", "B"), ("difficulty", "B"), ("charFlag", "B"),
]

# (name, fmt) for PlayerInfo_v26; "item[N]" marks an ItemInfo64 array
PLAYER_FIELDS = [
    ("signature", "I"), ("version", "I"),
    ("NextAction", "b"), ("state_reserved", "B"), ("MapRow", "h"), ("MapCol", "h"),
    ("dungeon", "b"), ("dungeon_reserved", "B"),
    ("Row", "h"), ("Col", "h"), ("XPos3", "h"), ("YPos3", "h"),
    ("CharName", "32s"), ("ClassId", "B"), ("subclassID", "b"), ("specializationID", "b"),
    ("BaseStrength", "h"), ("BaseMagic", "h"), ("BaseDexterity", "h"), ("BaseVitality", "h"),
    ("CharLevel", "h"), ("AvailableLvlPoints", "h"), ("Xp", "q"), ("TotalGold", "I"),
    ("BaseLife", "I"), ("MaxBaseLife", "I"), ("BaseMana", "I"), ("MaxBaseMana", "I"),
    ("SpellLevels", "128s"), ("AvailableSpellMask", "q"), ("AvailableSpellMask_64_128", "q"),
    ("OnBodySlots", "item[17]"), ("InventorySlots", "item[70]"),
    ("InvUsed", "70s"), ("InvItemCount", "B"), ("BeltInventory", "item[8]"),
    ("TalismanSlots", "item[70]"), ("TalUsed", "70s"), ("TalItemCount", "B"),
    ("UberDialogKilled", "b"), ("altWeaponIndex", "B"), ("CountOfReflectCharges", "H"),
    ("traits", "4s"), ("traits_reserved", "4s"),
    ("allowedDifficulty", "I"), ("Difficulty", "I"),
    ("griswoldLevel", "B"), ("reserved", "7s"), ("perk", "800s"),
    ("gameChanger", "q"), ("gameChangerReserved", "q"),
    ("CurrentSeedRun", "i"), ("CurrentSeedRun_64_reserved", "i"), ("gameMode", "b"),
]


def _layout(fields):
    off, out = 0, []
    for name, fmt in fields:
        if fmt.startswith("item["):
            n = int(fmt[5:-1]); size = n * ITEM_SIZE
        else:
            size = struct.calcsize("<" + fmt)
        out.append((name, fmt, off, size)); off += size
    return out, off


ITEM_LAYOUT, _isz = _layout(ITEM_FIELDS)
PLAYER_LAYOUT, _psz = _layout(PLAYER_FIELDS)
assert _isz == ITEM_SIZE, _isz
assert _psz == PLAYER_INFO_SIZE, _psz
OFFSETS = {name: off for name, _, off, _ in PLAYER_LAYOUT}


class Item(dict):
    @property
    def empty(self):
        # v30 saves store never-used slots as all-zero; cleared slots have baseItemIndex -1
        return self["baseItemIndex"] == -1 or (self["baseItemIndex"] == 0 and self["seed"] == 0 and self["amount"] == 0)

    @classmethod
    def parse(cls, b: bytes):
        it = cls()
        for name, fmt, off, size in ITEM_LAYOUT:
            v = struct.unpack_from("<" + fmt, b, off)
            it[name] = list(v) if len(v) > 1 else v[0]
        return it

    def pack(self) -> bytes:
        out = bytearray(ITEM_SIZE)
        for name, fmt, off, size in ITEM_LAYOUT:
            v = self[name]
            struct.pack_into("<" + fmt, out, off, *(v if isinstance(v, list) else [v]))
        return bytes(out)


class PlayerInfo(dict):
    @classmethod
    def parse(cls, b: bytes):
        if len(b) < PLAYER_INFO_SIZE:
            raise ValueError("hero block too small: %d bytes (need >= %d)" % (len(b), PLAYER_INFO_SIZE))
        p = cls()
        p["tail_unknown"] = bytes(b[PLAYER_INFO_SIZE:])
        for name, fmt, off, size in PLAYER_LAYOUT:
            if fmt.startswith("item["):
                p[name] = [Item.parse(b[o:o + ITEM_SIZE]) for o in range(off, off + size, ITEM_SIZE)]
            else:
                p[name] = struct.unpack_from("<" + fmt, b, off)[0]
        if p["version"] < 26:
            raise ValueError("hero save version %d is older than v26; not supported" % p["version"])
        return p

    def pack(self) -> bytes:
        out = bytearray(PLAYER_INFO_SIZE)
        for name, fmt, off, size in PLAYER_LAYOUT:
            v = self[name]
            if fmt.startswith("item["):
                out[off:off + size] = b"".join(i.pack() for i in v)
            else:
                struct.pack_into("<" + fmt, out, off, v)
        return bytes(out) + self.get("tail_unknown", b"")

    # convenience
    @property
    def name(self):
        return self["CharName"].split(b"\0", 1)[0].decode("latin-1")

    @name.setter
    def name(self, s):
        raw = s.encode("latin-1")
        if len(raw) > 31:
            raise ValueError("name max 31 chars")
        self["CharName"] = raw + bytes(32 - len(raw))

    def summary(self) -> dict:
        cls_id = self["ClassId"]
        gm = self["gameMode"]
        return {
            "name": self.name, "signature_ok": self["signature"] == SIGNATURE_HEL4,
            "version": self["version"],
            "layout": KNOWN_SIZES.get(PLAYER_INFO_SIZE + len(self.get("tail_unknown", b"")), "UNKNOWN size"),
            "tail_unknown_hex": self.get("tail_unknown", b"").hex(),
            "class": CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else cls_id,
            "subclass": self["subclassID"], "specialization": self["specializationID"],
            "level": self["CharLevel"], "xp": self["Xp"], "gold": self["TotalGold"],
            "stat_points": self["AvailableLvlPoints"],
            "str/mag/dex/vit": [self["BaseStrength"], self["BaseMagic"], self["BaseDexterity"], self["BaseVitality"]],
            "life(base/max)": [self["BaseLife"], self["MaxBaseLife"]],
            "mana(base/max)": [self["BaseMana"], self["MaxBaseMana"]],
            "game_mode": GAME_MODES[gm] if 0 <= gm < len(GAME_MODES) else gm,
            "difficulty": self["Difficulty"],
            "equipped_items": sum(not i.empty for i in self["OnBodySlots"]),
            "inventory_items": sum(not i.empty for i in self["InventorySlots"]),
            "belt_items": sum(not i.empty for i in self["BeltInventory"]),
            "talisman_items": sum(not i.empty for i in self["TalismanSlots"]),
            "nonzero_perks": sum(1 for x in self["perk"] if x),
        }
