"""Item presets, loadouts and per-session seed history (standard library only).

A preset keeps the whole 64-byte ItemInfo64 record as hex, so base, seed, unique
index, quality, durability, charges, sockets and enchants all come back exactly.
Store: %APPDATA%\\CheeseStickTrainer\\presets.json (CHEESESTICK_PRESETS overrides).
Nothing here touches a save file: applying only edits the in-memory player."""
import json, os, time, uuid

from .player import Item, ITEM_SIZE, CLASS_NAMES
from .rules import SLOTS, SLOT_NAMES, allowed, why_not, category
from .items import Inventory, StashTabGrid, clone_item

FORMAT = "cheesestick-presets"
VERSION = 1


def default_path():
    env = os.environ.get("CHEESESTICK_PRESETS")
    if env:
        return env
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "CheeseStickTrainer", "presets.json")


def item_hex(item):
    return item.pack().hex()


def item_from_hex(h):
    raw = bytes.fromhex(h)
    if len(raw) != ITEM_SIZE:
        raise ValueError("preset item must be %d bytes, got %d" % (ITEM_SIZE, len(raw)))
    return Item.parse(raw)


def base_of(item, bases):
    i = item["baseItemIndex"]
    return bases[i] if bases and 0 <= i < len(bases) else {}


def item_size(item, bases):
    b = base_of(item, bases)
    return (b.get("w") or 1, b.get("h") or 1)


def fitting_slots(item, bases):
    b = base_of(item, bases)
    return [s[0] for s in SLOTS if allowed(b, "equip", s[0])]


def slot_group(item, bases):
    """Coarse slot filter label: Head, Ring, Amulet, Hand, Body, Belt, Gloves, Boots, Belt bar, Other."""
    fits = fitting_slots(item, bases)
    if not fits:
        return "Belt bar" if allowed(base_of(item, bases), "belt") else "Other"
    name = SLOT_NAMES[fits[0]]
    for key in ("ring", "Amulet", "hand"):
        if key in name:
            return {"ring": "Ring", "hand": "Hand"}.get(key, key)
    return name


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def make_item_preset(item, name, notes="", bases=None, label=""):
    if item.empty:
        raise ValueError("that slot is empty")
    b = base_of(item, bases)
    return {"id": uuid.uuid4().hex, "kind": "item", "name": name.strip() or "Unnamed preset",
            "notes": notes, "created": _now(), "label": label or b.get("name", ""),
            "category": category(b) if b else "Other", "slot": slot_group(item, bases),
            "item": item_hex(item)}


def make_loadout(player, name, notes="", bases=None):
    items = [{"slot": i, "slot_name": SLOT_NAMES[i], "item": item_hex(it),
              "label": base_of(it, bases).get("name", "")}
             for i, it in enumerate(player["OnBodySlots"]) if not it.empty]
    if not items:
        raise ValueError("this character has nothing equipped")
    cid = player["ClassId"]
    return {"id": uuid.uuid4().hex, "kind": "loadout", "name": name.strip() or "Unnamed loadout",
            "notes": notes, "created": _now(), "category": "Loadout", "slot": "Loadout",
            "label": "%d items" % len(items),
            "class": CLASS_NAMES[cid] if cid < len(CLASS_NAMES) else str(cid), "items": items}


def validate_preset(p):
    if not isinstance(p, dict) or p.get("kind") not in ("item", "loadout") or not p.get("name"):
        raise ValueError("not a preset")
    if p["kind"] == "item":
        item_from_hex(p["item"])
    else:
        for e in p["items"]:
            if not 0 <= int(e["slot"]) < len(SLOTS):
                raise ValueError("bad loadout slot %r" % e["slot"])
            item_from_hex(e["item"])
    return p


class PresetStore:
    def __init__(self, path=None):
        self.path = path or default_path()
        self.presets = []
        self.load()

    def load(self):
        self.presets = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.presets = self._parse(json.load(f))
        return self.presets

    @staticmethod
    def _parse(data):
        lst = data.get("presets") if isinstance(data, dict) else data
        if not isinstance(lst, list):
            raise ValueError("no preset list in that file")
        out = []
        for p in lst:
            try:
                out.append(validate_preset(p))
            except (ValueError, KeyError, TypeError):
                continue
        return out

    def _dump(self, presets):
        return {"format": FORMAT, "version": VERSION, "presets": presets}

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._dump(self.presets), f, indent=1)
        os.replace(tmp, self.path)

    def get(self, pid):
        return next((p for p in self.presets if p["id"] == pid), None)

    def add(self, preset):
        self.presets.append(validate_preset(preset)); self.save(); return preset

    def rename(self, pid, name, notes=None):
        p = self.get(pid)
        if p is None:
            raise KeyError(pid)
        if name.strip():
            p["name"] = name.strip()
        if notes is not None:
            p["notes"] = notes
        self.save()

    def delete(self, pid):
        self.presets = [p for p in self.presets if p["id"] != pid]; self.save()

    def search(self, text="", slot="", kind=""):
        t = text.lower().strip()
        out = []
        for p in self.presets:
            if kind and p["kind"] != kind:
                continue
            if slot and slot not in (p.get("slot"), p.get("category")):
                continue
            hay = " ".join(str(p.get(k, "")) for k in ("name", "notes", "label", "category", "slot")).lower()
            if t and t not in hay:
                continue
            out.append(p)
        return out

    def export(self, path, ids=None):
        sel = [p for p in self.presets if ids is None or p["id"] in ids]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._dump(sel), f, indent=1)
        return len(sel)

    def import_file(self, path):
        with open(path, encoding="utf-8") as f:
            incoming = self._parse(json.load(f))
        have = {p["id"] for p in self.presets}
        for p in incoming:
            if p["id"] in have:
                p = dict(p, id=uuid.uuid4().hex)
            self.presets.append(p)
        self.save()
        return len(incoming)


# ---- applying (in memory only; the caller marks the save unsaved)
def apply_to_equip(player, item, slot, bases):
    cur = player["OnBodySlots"][slot]
    if not cur.empty:
        raise ValueError("%s is occupied - remove that item first" % SLOT_NAMES[slot])
    msg = why_not(base_of(item, bases), "equip", slot)
    if msg:
        raise ValueError(msg)
    player["OnBodySlots"][slot] = clone_item(item)
    return slot


def apply_to_belt(player, item, slot, bases):
    if not player["BeltInventory"][slot].empty:
        raise ValueError("Belt slot %d is occupied - remove that item first" % (slot + 1))
    msg = why_not(base_of(item, bases), "belt", slot)
    if msg:
        raise ValueError(msg)
    player["BeltInventory"][slot] = clone_item(item)
    return slot


def apply_to_inventory(player, item, bases, cell=None):
    w, h = item_size(item, bases)
    inv = Inventory(player)
    c = clone_item(item)
    return inv.add_at(c, w, h, cell) if cell is not None else inv.add(c, w, h)


def apply_to_stash(stash, item, bases, tab=0):
    if stash is None:
        raise ValueError("this save has no stash entry")
    w, h = item_size(item, bases)
    return StashTabGrid(stash.tabs[tab]).add(clone_item(item), w, h)


def apply_loadout(player, loadout, bases, check=None, replace=False):
    """Equip each loadout item in its own slot.

    check(item, slot) -> reason or "" adds a class/usability rule (the GUI passes
    the catalog limits). Items whose slot rule or check fails are skipped.
    replace=True clears an occupied slot first; otherwise occupied slots are skipped.
    Returns (applied [(slot, label)], skipped [(slot_name, label, reason)])."""
    applied, skipped = [], []
    for e in loadout["items"]:
        slot = int(e["slot"]); item = item_from_hex(e["item"])
        label = e.get("label") or base_of(item, bases).get("name", "item")
        b = base_of(item, bases)
        reason = why_not(b, "equip", slot) if b else "unknown base item %d" % item["baseItemIndex"]
        if not reason and check:
            reason = check(item, slot) or ""
        if not reason and not player["OnBodySlots"][slot].empty and not replace:
            reason = "slot is occupied"
        if reason:
            skipped.append((SLOT_NAMES[slot], label, reason)); continue
        player["OnBodySlots"][slot] = item
        applied.append((slot, label))
    return applied, skipped


class SeedHistory:
    """Per-session list of seeds per item key. Each Reroll/apply pushes; back() pops."""

    def __init__(self):
        self.h = {}

    def push(self, key, seed):
        lst = self.h.setdefault(key, [])
        if not lst or lst[-1] != seed:
            lst.append(seed)

    def list(self, key):
        return list(self.h.get(key, []))

    def back(self, key):
        """Drop the current seed and return the previous one (None if there is none)."""
        lst = self.h.get(key, [])
        if len(lst) < 2:
            return None
        lst.pop()
        return lst[-1]

    def clear(self):
        self.h.clear()
