"""The "game" entry: the saved game-in-progress (Saving.cpp SaveGame/LoadGame).

ROOT CAUSE of "edits revert in game": a .ssv holds the hero TWICE.
  * "sphero"  = LastPlayerInfo, read by the character-select screen (CharSlots.cpp).
  * "game"    = the game-in-progress. LoadGame() -> LoadPlayer() reads a raw copy of the
                runtime Player struct from it (SavePlayer writes sizeof(Player) verbatim),
                and that copy replaces the hero when you pick "Load Game".
So editing only sphero shows on the select screen, then the game loads the old copy.

This module patches the core character block of that raw Player copy. Field order is
structs.h `struct Player` (packed): playerName, ClassID, Cur/Base Str, Mag, Dex, Vit,
AvailableLvlPoints, BaseDamage, BlockBonus, Base/MaxBase/Cur/MaxCur Life, RatioLifeGlobe,
Base/MaxBase/Cur/MaxCur Mana, RatioManaGlobe, CharLevel, controlCharLevel, Xp, NextLevelUp,
TotalGold. Offsets were confirmed on a real v0.773 (save version 30) game entry.
Items, spells, perks and traits sit in parts of the runtime struct whose v30 layout is not
public, so they are NOT patched (see HERO_ONLY_FIELDS).
"""
import struct

NAME_OFF_V30 = 710      # offset of Player.playerName in a version-30 "game" entry
SIG = b"HEL4"
# name: (offset from playerName, struct fmt)
F = {
    "playerName": (0, "32s"), "ClassID": (32, "B"),
    "CurStrength": (33, "h"), "BaseStrength": (35, "h"), "CurMagic": (37, "h"), "BaseMagic": (39, "h"),
    "CurDexterity": (41, "h"), "BaseDexterity": (43, "h"), "CurVitality": (45, "h"), "BaseVitality": (47, "h"),
    "AvailableLvlPoints": (49, "h"), "BaseDamage": (51, "i"), "BlockBonus": (55, "i"),
    "BaseLife": (59, "i"), "MaxBaseLife": (63, "i"), "CurLife": (67, "i"), "MaxCurLife": (71, "i"),
    "RatioLifeGlobe": (75, "i"),
    "BaseMana": (79, "i"), "MaxBaseMana": (83, "i"), "CurMana": (87, "i"), "MaxCurMana": (91, "i"),
    "RatioManaGlobe": (95, "i"),
    "CharLevel": (99, "h"), "controlCharLevel": (101, "h"), "Xp": (103, "q"), "NextLevelUp": (111, "q"),
    "TotalGold": (119, "i"),
}
STATS = (("CurStrength", "BaseStrength"), ("CurMagic", "BaseMagic"),
         ("CurDexterity", "BaseDexterity"), ("CurVitality", "BaseVitality"))
# hero fields whose game-in-progress copy cannot be patched (yet)
HERO_ONLY_FIELDS = ("ClassId", "subclassID", "specializationID", "SpellLevels", "AvailableSpellMask",
                    "perk", "traits", "gameChanger", "OnBodySlots", "InventorySlots", "InvUsed", "InvItemCount",
                    "BeltInventory", "TalismanSlots", "TotalGold")


class GameState:
    def __init__(self, plain: bytes):
        self.plain = bytearray(plain)
        self.ok, self.why = self._check()

    def _check(self):
        b = self.plain
        if b[:4] != SIG:
            return False, "unknown game-entry signature %r" % bytes(b[:4])
        ver = struct.unpack(">I", b[4:8])[0]
        if ver != 30:
            return False, "game entry save version %d (only 30 is mapped)" % ver
        if len(b) < NAME_OFF_V30 + 200:
            return False, "game entry too short"
        name = bytes(b[NAME_OFF_V30:NAME_OFF_V30 + 32]).split(b"\0", 1)[0]
        lvl, xp = self["CharLevel"], self["Xp"]
        if not name or not all(32 <= c < 127 for c in name) or not 0 <= self["ClassID"] < 6 \
                or not 1 <= lvl <= 150 or xp < 0 \
                or not 0 <= self["controlCharLevel"] <= lvl:
            return False, "player block not where expected (layout check failed)"
        return True, ""

    def __getitem__(self, k):
        off, fmt = F[k]
        return struct.unpack_from("<" + fmt, self.plain, NAME_OFF_V30 + off)[0]

    LIMITS = {"h": (-32768, 32767), "i": (-2**31, 2**31 - 1), "q": (-2**63, 2**63 - 1), "B": (0, 255)}

    def __setitem__(self, k, v):
        off, fmt = F[k]
        if fmt in self.LIMITS:
            lo, hi = self.LIMITS[fmt]; v = max(lo, min(hi, v))
        struct.pack_into("<" + fmt, self.plain, NAME_OFF_V30 + off, v)

    @property
    def name(self):
        return self["playerName"].split(b"\0", 1)[0].decode("latin-1")

    def summary(self):
        return {k: self[k] for k in F if k != "playerName"} | {"name": self.name}

    def sync_from_hero(self, p, next_level_up):
        """Copy the hero's core values into the game-in-progress copy, keeping derived fields
        consistent: Cur stats keep their item bonus (Cur - Base), Cur/MaxCur life and mana shift
        by the change of the max base value, controlCharLevel keeps its offset to CharLevel, NextLevelUp =
        LevelUp(CharLevel), Xp <= NextLevelUp (ValidateCurPlayer would clamp it)."""
        if not self.ok:
            raise ValueError(self.why)
        raw = bytearray(self["playerName"])
        nm = p.name.encode("latin-1")[:31]
        raw[:len(nm) + 1] = nm + b"\0"
        self["playerName"] = bytes(raw)
        for (cur, base), key in zip(STATS, ("BaseStrength", "BaseMagic", "BaseDexterity", "BaseVitality")):
            bonus = self[cur] - self[base]
            self[base] = p[key]; self[cur] = max(0, p[key] + bonus)
        self["AvailableLvlPoints"] = p["AvailableLvlPoints"]
        for pre in ("Life", "Mana"):
            d = p["MaxBase" + pre] - self["MaxBase" + pre]
            self["Base" + pre] = p["Base" + pre]; self["MaxBase" + pre] = p["MaxBase" + pre]
            self["MaxCur" + pre] = max(0, self["MaxCur" + pre] + d)
            self["Cur" + pre] = max(0, min(self["MaxCur" + pre], self["Cur" + pre] + d))
        # controlCharLevel is not simply CharLevel in v0.773 (seen: CharLevel-1, and 0 in a fresh
        # New Game session at level 150); keep its offset to CharLevel
        off = self["CharLevel"] - self["controlCharLevel"]
        self["CharLevel"] = p["CharLevel"]; self["controlCharLevel"] = max(0, p["CharLevel"] - off)
        self["NextLevelUp"] = next_level_up
        self["Xp"] = min(p["Xp"], next_level_up)

    def pack(self):
        return bytes(self.plain)
