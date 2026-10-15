"""Item helpers: blank/new items, inventory grid (10x7 InvUsed), belt, cloning.

InvUsed convention (verified on a real v30 save): cell = row*10+col; the item's
bottom-left cell holds +(index+1), every other cell it covers holds -(index+1).
"""
import random
from .player import Item, ITEM_LAYOUT

INV_W, INV_H = 10, 7
GOLD_BASE = 0
MAX_GOLD_IN_CELL = 100_000_000  # dataseg.cpp MaxGoldInCell
GEN_VERSION = 7                 # CurItemGenVersion seen in real saves
# enums.h BIT(n) is 1<<(n-1), not 1<<n. D_UNIQ is BIT(6) = 0x20.
# 1<<6 is 0x40, which is D_GOOD: RecreateItem then rolls a magic item and never calls GetUniqueItem.
D_UNIQ = 0x20


def blank_item(save_version=30):
    it = Item({n: ([0] * 6 if n == "sockets" else [-1] * 5 if n == "enchantIndexes" else 0)
               for n, *_ in ITEM_LAYOUT})
    it["baseItemIndex"] = -1
    return it


def new_item(base_id, save_version, dur=0, amount=0, seed=None):
    it = blank_item(save_version)
    it.update(genVersion=GEN_VERSION, saveVersion=save_version, baseItemIndex=base_id,
              seed=seed if seed is not None else random.randrange(1, 2**31),
              curDurability=dur, baseDurability=dur, amount=amount)
    return it


def mark_unique(it, uniq_index, qlvl, set_item=False):
    """Mark a base item as a unique or set piece the game will rebuild on load.

    Magic level 2 is unique, 3 is set (GetUniqueItem). The low bit means identified.
    """
    it["dropType"] = D_UNIQ
    it["uniqIndex"] = int(uniq_index)
    it["quality"] = int(qlvl)
    it["magicLevelAndIdentified"] = ((3 if set_item else 2) << 1) | 1
    return it


def clone_item(it, new_seed=False):
    c = Item({k: (list(v) if isinstance(v, list) else v) for k, v in it.items()})
    if new_seed:
        c["seed"] = random.randrange(1, 2**31)
    return c


def _signed(b):
    return b - 256 if b > 127 else b


class Inventory:
    """Wraps PlayerInfo inventory: InventorySlots[70], InvUsed[70], InvItemCount."""

    def __init__(self, player):
        self.p = player

    @property
    def count(self):
        return self.p["InvItemCount"]

    def grid(self):
        return [_signed(b) for b in self.p["InvUsed"]]

    def _set_grid(self, g):
        self.p["InvUsed"] = bytes(v & 0xFF for v in g)

    def items(self):
        return self.p["InventorySlots"][:self.count]

    def cells_of(self, idx):
        return [i for i, v in enumerate(self.grid()) if abs(v) == idx + 1]

    def size_of(self, idx):
        cells = self.cells_of(idx)
        if not cells:
            return (1, 1)
        cols = {c % INV_W for c in cells}; rows = {c // INV_W for c in cells}
        return (len(cols), len(rows))

    def find_space(self, w, h):
        g = self.grid()
        for r in range(h - 1, INV_H):
            for c in range(0, INV_W - w + 1):
                cells = [(r - dy) * INV_W + c + dx for dy in range(h) for dx in range(w)]
                if all(g[x] == 0 for x in cells):
                    return r * INV_W + c, cells
        return None

    def add_at(self, item, w, h, top_left):
        """Place with the given top-left cell (row*10+col)."""
        r0, c0 = divmod(top_left, INV_W)
        if c0 + w > INV_W or r0 + h > INV_H:
            raise ValueError("a %dx%d item does not fit there" % (w, h))
        cells = [(r0 + dy) * INV_W + c0 + dx for dy in range(h) for dx in range(w)]
        g = self.grid()
        if any(g[x] for x in cells):
            raise ValueError("those cells are occupied")
        return self._put(item, cells, (r0 + h - 1) * INV_W + c0)

    def _put(self, item, cells, anchor):
        if self.count >= 70:
            raise ValueError("inventory item list is full")
        idx = self.count
        g = self.grid()
        for x in cells:
            g[x] = -(idx + 1)
        g[anchor] = idx + 1
        self._set_grid(g)
        self.p["InventorySlots"][idx] = item
        self.p["InvItemCount"] = idx + 1
        return idx

    def item_at(self, cell):
        v = self.grid()[cell]
        return abs(v) - 1 if v else None

    def add(self, item, w=1, h=1):
        if self.count >= 70:
            raise ValueError("inventory item list is full")
        spot = self.find_space(w, h)
        if spot is None:
            raise ValueError("no free %dx%d space in inventory" % (w, h))
        anchor, cells = spot
        idx = self.count
        g = self.grid()
        for x in cells:
            g[x] = -(idx + 1)
        g[anchor] = idx + 1
        self._set_grid(g)
        self.p["InventorySlots"][idx] = item
        self.p["InvItemCount"] = idx + 1
        return idx

    def remove(self, idx):
        n = self.count
        if not 0 <= idx < n:
            raise IndexError(idx)
        g = self.grid()
        out = []
        for v in g:
            a = abs(v)
            if a == idx + 1:
                out.append(0)
            elif a > idx + 1:
                out.append(v - 1 if v > 0 else v + 1)
            else:
                out.append(v)
        self._set_grid(out)
        slots = self.p["InventorySlots"]
        del slots[idx]
        slots.append(blank_item())
        self.p["InvItemCount"] = n - 1

    def recompute_gold(self):
        """TotalGold = sum of gold piles in inventory (as the game does)."""
        self.p["TotalGold"] = sum(i["amount"] for i in self.items() if i["baseItemIndex"] == GOLD_BASE)
        return self.p["TotalGold"]


# ---- generic grid helpers (used for stash tabs: 10x13 i16 usedFlags) ----
def grid_find_space(g, gw, gh, w, h):
    for r in range(h - 1, gh):
        for c in range(0, gw - w + 1):
            cells = [(r - dy) * gw + c + dx for dy in range(h) for dx in range(w)]
            if all(g[x] == 0 for x in cells):
                return r * gw + c, cells
    return None


class StashTabGrid:
    """One stash tab {'flags': [130 x i16], 'items': [Item]}. Same +bottom-left /
    -other-cells convention as the inventory (assumed; not yet seen in a real stash)."""
    W, H = 10, 13

    def __init__(self, tab):
        self.t = tab

    def add(self, item, w=1, h=1):
        spot = grid_find_space(self.t["flags"], self.W, self.H, w, h)
        if spot is None:
            raise ValueError("no free %dx%d space in this stash tab" % (w, h))
        anchor, cells = spot
        idx = len(self.t["items"])
        for x in cells:
            self.t["flags"][x] = -(idx + 1)
        self.t["flags"][anchor] = idx + 1
        self.t["items"].append(item)
        return idx

    def size_of(self, idx):
        cells = [i for i, v in enumerate(self.t["flags"]) if abs(v) == idx + 1]
        if not cells:
            return (1, 1)
        return (len({c % self.W for c in cells}), len({c // self.W for c in cells}))

    def remove(self, idx):
        f = self.t["flags"]
        for i, v in enumerate(f):
            a = abs(v)
            if a == idx + 1:
                f[i] = 0
            elif a > idx + 1:
                f[i] = v - 1 if v > 0 else v + 1
        del self.t["items"][idx]
