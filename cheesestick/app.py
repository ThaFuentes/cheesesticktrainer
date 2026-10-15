"""Main window. All edits happen on an in-memory SaveFile; File > Save writes a new
archive, re-reads and verifies it, makes a timestamped backup, then atomically
replaces the original (th4save.save.SaveFile.save_safely)."""
import os, random, sys, traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QSpinBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
    QCheckBox, QGroupBox, QHeaderView, QAbstractItemView, QScrollArea, QFrame,
    QSplitter, QSizePolicy)
from PySide6.QtGui import QAction, QKeySequence, QColor

from th4save.save import SaveFile, StaleSaveError
from th4save import scan
from th4save.player import CLASS_NAMES, GAME_MODES
from th4save.items import (Inventory, StashTabGrid, new_item, clone_item, blank_item,
                           mark_unique, MAX_GOLD_IN_CELL, GOLD_BASE)
from .finder import FinderPanel
from .widgets import (BaseItemPicker, Paperdoll, CellGrid, BeltBar, HeaderBar, quality_color,
                      quality_of)
from th4save.rules import SLOT_NAMES, why_not, category
from th4save.items import INV_W, INV_H
from .data import BASE_ITEMS, LEVEL_XP, SPELLS, PERKS, TRAITS, base_name, default_dur
from . import caps
from .iteminfo import describe_item, affix_rows, effect_text, item_name
from .data import UNIQUES, GAME, is_set_unique
from .gamecheck import running_game_processes
from . import catalog
from .icons import glyph_for, cached_icon, clear_icon_cache
from .browser import ItemBrowser
from .presets_panel import PresetsPanel
from th4save.presets import SeedHistory
from .brand import DEDICATION, icon as cheesestick_icon, pixmap as cheesestick_pixmap

APPLY_TEXT = "Apply (not saved)"
UNSAVED_MSG = "Unsaved changes, press Save (Ctrl+S)"

I16 = (-32768, 32767)
QUALITY_NAMES = {0: "Normal", 1: "Magic", 2: "Unique", 3: "Set"}
U32_MAX_SPIN = 2_147_483_647   # QSpinBox is 32-bit signed

# Item::SetSeed and SetRndSeed cast the saved i64 to a signed 32-bit int, so a
# full seed the game keeps is 10 digits. The save field itself is signed 64-bit.
GAME_SEED_DIGITS = 10
GAME_SEED_MIN = -2 ** 31
GAME_SEED_MAX = 2 ** 31 - 1
SAVE_SEED_MIN = -2 ** 63
SAVE_SEED_MAX = 2 ** 63 - 1
SEED_HELP = (
    "The save stores a signed 64-bit seed (up to 19 digits). "
    "The game keeps a signed 32-bit seed, 10 digits from -2147483648 to 2147483647, "
    "and drops the rest when the item loads. A shorter number still works. "
    "Reroll fills a full 10-digit seed. Apply writes the box onto the item."
)
_SEED_COLOR = {"short": "#f2c96d", "full": "#8fd18a", "wide": "#ff8a7a", "bad": "#ff8a7a"}


def describe_seed(text):
    """Return (message, kind) for the seed box. kind is short, full, wide, or bad.

    A short seed is legal. A wide seed still fits in the save until it passes
    the signed 64-bit limit. The game casts the saved seed to a signed 32-bit int.
    """
    raw = text.strip()
    why = " The game keeps 10; the save is 64-bit."
    if raw in ("", "+", "-"):
        return ("0 of 10 digits. 10 missing." + why, "short")
    try:
        seed = int(raw, 10)
    except ValueError:
        return ("Not a whole number.", "bad")
    if seed < SAVE_SEED_MIN or seed > SAVE_SEED_MAX:
        return ("Too big for the save. A signed 64-bit seed is at most 19 digits.", "bad")
    body = raw[1:] if raw[:1] in "+-" else raw
    digits = len(str(abs(seed)))
    pad = " Leading zeros do not count." if body.isdigit() and len(body) > digits else ""
    if seed < GAME_SEED_MIN or seed > GAME_SEED_MAX:
        extra = digits - GAME_SEED_DIGITS
        if extra > 0:
            msg = ("%d digits. %d past the 10 the game keeps. "
                   "Those extra digits are dropped on load." % (digits, extra))
        else:
            msg = ("Does not fit in the 10 digits the game keeps "
                   "(at most %d). The extra part is dropped on load." % GAME_SEED_MAX)
        return (msg + pad, "wide")
    missing = GAME_SEED_DIGITS - digits
    if missing > 0:
        return ("%d of 10 digits. %d missing.%s%s" % (digits, missing, why, pad), "short")
    return ("10 of 10 digits. The game keeps this whole seed." + pad, "full")
def spin(lo, hi, val=0):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(max(lo, min(hi, val))); return s


def maxbtn(tip, text="Max"):
    b = QPushButton(text); b.setObjectName("MaxButton"); b.setToolTip(tip); b.setFixedWidth(56); return b


class _ScrollText(QLabel):
    """Rich text that grows downward as it wraps, so the box around it can scroll."""

    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setObjectName("ItemInfo")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wrapped = self.heightForWidth(max(1, self.width()))
        if wrapped > 0 and wrapped != self.minimumHeight():
            self.setMinimumHeight(wrapped)


# ----------------------------------------------------------------- dialogs
class ItemList(QWidget):
    """One item container: visual view (paperdoll / grid / belt bar) + table + editor.
    kind: equip|inv|belt|stash. Adds are slot-aware and validated (th4save.rules).
    Inventory and stash use the item-browser columns. Equipped and belt stay slot tables."""
    SLOT_COLS = ["#", "Base", "Name", "Size", "Qty", "Dur", "MaxDur", "Chg", "MaxChg", "Unique", "Quality", "Seed"]
    DETAIL_COLS = ["#", "Icon", "Name", "Category", "Damage", "Armor", "Durability",
                   "Str", "Mag", "Dex", "Lvl", "Size", "Quality", "Limits", "Qty", "Seed", "Rank"]

    def __init__(self, main, kind):
        super().__init__()
        self.main, self.kind = main, kind
        self.detail = kind in ("inv", "stash")
        self.COLS = self.DETAIL_COLS if self.detail else self.SLOT_COLS
        self.pending_cell = None
        outer = QVBoxLayout(self); outer.setSpacing(0); outer.setContentsMargins(8, 8, 8, 8)
        self.visual = None
        if kind == "equip":
            self.visual = Paperdoll(); self.visual.slot_clicked.connect(self.on_slot_clicked)
        elif kind == "inv":
            self.visual = CellGrid(INV_W, INV_H); self.visual.cell_clicked.connect(self.on_cell_clicked)
        elif kind == "belt":
            self.visual = BeltBar(); self.visual.slot_clicked.connect(self.on_slot_clicked)
        top_host = QWidget()
        top = QHBoxLayout(top_host); top.setSpacing(12); top.setContentsMargins(4, 4, 4, 4)
        if self.visual is not None:
            top.addWidget(self.visual, 0, Qt.AlignTop)
        box = QGroupBox("Selected item"); f = QFormLayout(box); f.setSpacing(6)
        self.sel_label = QLabel("-"); self.sel_label.setWordWrap(True); f.addRow(self.sel_label)
        self.e_amount = spin(0, MAX_GOLD_IN_CELL); self.e_cd = spin(*I16); self.e_bd = spin(*I16)
        self.e_cc = spin(*I16); self.e_bc = spin(*I16); self.e_uniq = spin(*I16); self.e_qual = spin(*I16)
        fields = (("Quantity / gold", self.e_amount), ("Durability", self.e_cd), ("Max durability", self.e_bd),
                  ("Charges", self.e_cc), ("Max charges", self.e_bc), ("Unique index", self.e_uniq),
                  ("Quality", self.e_qual))
        left, right = QFormLayout(), QFormLayout()
        for lay in (left, right):
            lay.setSpacing(6); lay.setContentsMargins(0, 0, 0, 0)
        pair = QHBoxLayout(); pair.setSpacing(16)
        pair.addLayout(left, 1); pair.addLayout(right, 1)
        for i, (lbl, w) in enumerate(fields):
            (left if i % 2 == 0 else right).addRow(lbl, w)
        f.addRow(pair)
        self.e_seed = QLineEdit()
        self.e_seed.setPlaceholderText("type a seed, or Reroll")
        self.e_seed.setToolTip(SEED_HELP)
        self.reroll_btn = QPushButton("Reroll")
        self.reroll_btn.setToolTip("Fill a full 10-digit seed the game will keep. Apply writes it onto the item.")
        self.reroll_btn.clicked.connect(self.roll_seed)
        self.seed_back_btn = QPushButton("↶ Previous seed")
        self.seed_back_btn.setToolTip("Go back to the seed before the last Reroll or Apply for this item (this session).")
        self.seed_back_btn.clicked.connect(self.previous_seed)
        seed_row = QHBoxLayout(); seed_row.addWidget(self.e_seed, 1); seed_row.addWidget(self.reroll_btn)
        seed_row.addWidget(self.seed_back_btn)
        f.addRow("Seed", seed_row)
        self.seed_hist_label = QLabel(""); self.seed_hist_label.setWordWrap(True)
        self.seed_hist_label.setObjectName("HeaderSub"); f.addRow(self.seed_hist_label)
        self.seed_hint = QLabel("")
        self.seed_hint.setWordWrap(True)
        self.seed_hint.setToolTip(SEED_HELP)
        self.e_seed.textChanged.connect(self.refresh_seed_hint)
        self.refresh_seed_hint()
        f.addRow(self.seed_hint)
        ap = QPushButton(APPLY_TEXT); ap.setObjectName("Primary"); ap.clicked.connect(self.apply)
        ap.setToolTip("Writes the values into the edited character in memory. Use File > Save (Ctrl+S) to write the save file.")
        f.addRow(ap); self.apply_btn = ap
        note = QLabel("Apply writes the number in the box. A short seed is fine. The game rolls affixes from it on load and keeps 10 digits. The unique index must be valid for the base.")
        note.setWordWrap(True); note.setObjectName("HeaderSub"); f.addRow(note)
        top.addWidget(box, 1)
        self.top_scroll = QScrollArea()
        self.top_scroll.setWidgetResizable(True)
        self.top_scroll.setFrameShape(QFrame.NoFrame)
        self.top_scroll.setWidget(top_host)
        self.top_scroll.setMinimumHeight(160)
        self.top_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.top_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        bottom = QWidget()
        below = QVBoxLayout(bottom); below.setSpacing(8); below.setContentsMargins(4, 4, 4, 4)
        self.info_label = _ScrollText()
        self.info_scroll = QScrollArea()
        self.info_scroll.setWidget(self.info_label)
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setFrameShape(QFrame.NoFrame)
        self.info_scroll.setFixedHeight(96)
        self.info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.info_scroll.setToolTip("Item details. Scroll this box for the rest. The table underneath lists every slot.")
        below.addWidget(self.info_scroll)

        if kind == "stash":
            row = QHBoxLayout(); row.addWidget(QLabel("Stash tab:"))
            self.tab_spin = spin(1, 100, 1); self.tab_spin.valueChanged.connect(self.refresh)
            row.addWidget(self.tab_spin); row.addStretch(); below.addLayout(row)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        if self.detail:
            self.table.setIconSize(QSize(28, 28))
            self.table.verticalHeader().setDefaultSectionSize(32)
            self.table.horizontalHeaderItem(4).setToolTip("Base damage range. Magic bonuses are set by the seed.")
            self.table.horizontalHeaderItem(12).setToolTip("Rolled quality of this item (normal, magic, unique, set).")
            self.table.horizontalHeaderItem(16).setToolTip(
                "Rank inside this category and slot. A sword is not ranked against a ring.")
        self.table.currentCellChanged.connect(lambda *_: self.on_row_changed())
        self.table.setMinimumHeight(160)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        below.addWidget(self.table, 1)
        btns = QHBoxLayout()
        for text, fn in (("＋ Add...", self.add), ("✕ Remove", self.remove), ("⧉ Clone", self.clone),
                         ("★ Save as preset", self.save_preset)):
            b = QPushButton(text); b.clicked.connect(fn); btns.addWidget(b)
        self.new_seed = QCheckBox("clone with new seed"); btns.addWidget(self.new_seed)
        btns.addStretch(); below.addLayout(btns)
        bottom.setMinimumHeight(220)
        self.split = QSplitter(Qt.Vertical)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.top_scroll)
        self.split.addWidget(bottom)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setHandleWidth(8)
        outer.addWidget(self.split)

    # -- container access
    def save(self):
        return self.main.save

    def container(self):
        p = self.save().player
        if self.kind == "equip":
            return p["OnBodySlots"]
        if self.kind == "belt":
            return p["BeltInventory"]
        if self.kind == "inv":
            return Inventory(p).items()
        return self.stash_tab()["items"] if self.save().stash else []

    def stash_tab(self):
        return self.save().stash.tabs[self.tab_spin.value() - 1]

    def size_of(self, i):
        if self.kind == "inv":
            return Inventory(self.save().player).size_of(i)
        if self.kind == "stash":
            return StashTabGrid(self.stash_tab()).size_of(i)
        return None

    def refresh(self):
        if not self.main.save:
            self.table.setRowCount(0); return
        items = self.container()
        self.table.blockSignals(True)
        self.table.setRowCount(len(items))
        classic = caps.classic(self.save().player)
        view = catalog.view_from(self.main)
        for r, it in enumerate(items):
            label = SLOT_NAMES[r] if self.kind == "equip" else str(r + 1 if self.kind == "belt" else r)
            sz = self.size_of(r) if not it.empty else None
            slot = SLOT_NAMES[r] if self.kind == "equip" and not it.empty else ""
            tip = describe_item(it, slot=slot, view=view, classic=classic) if not it.empty else ""
            if self.detail:
                vals = self._detail_vals(it, label, sz, classic)
            else:
                vals = [label, it["baseItemIndex"], item_name(it) if not it.empty else "(empty)",
                        "%dx%d" % sz if sz else "", it["amount"], it["curDurability"], it["baseDurability"],
                        it["curCharges"], it["baseCharges"], it["uniqIndex"], it["quality"], it["seed"]]
            for c, v in enumerate(vals):
                cell = v if isinstance(v, QTableWidgetItem) else QTableWidgetItem(str(v))
                if c == 2:
                    cell.setForeground(quality_color(it) if not it.empty else QColor("#6d6258"))
                if tip:
                    cell.setToolTip(tip)
                self.table.setItem(r, c, cell)
        self.table.blockSignals(False)
        self.update_visual()
        self.load_editor()

    def _detail_vals(self, it, label, sz, classic):
        """Browser columns for one owned item. Name stays in column 2."""
        empty = it.empty
        b = BASE_ITEMS[it["baseItemIndex"]] if not empty and 0 <= it["baseItemIndex"] < len(BASE_ITEMS) else None
        fact = catalog.facts().get(it["baseItemIndex"]) if b else None
        icon = QTableWidgetItem("" if b is None else ("" if cached_icon(b, classic) else glyph_for(b)))
        pic = cached_icon(b, classic) if b else None
        if pic is not None:
            icon.setIcon(pic)
        if fact and it["baseDurability"]:
            dur = "%d/%d" % (it["curDurability"], it["baseDurability"])
        elif fact:
            dur = fact["dur_text"]
        else:
            dur = ""
        size = "%dx%d" % sz if sz else (fact["size_text"] if fact else "")
        qual = QUALITY_NAMES.get(quality_of(it), str(it["quality"])) if not empty else ""
        req = fact["req"] if fact else {}
        def req_text(key):
            return req[key][0] if req else ""
        rec = catalog.rank_info(b) if b else None
        rank = "" if rec is None else "%d/%d" % (rec["rank"], rec["total"])
        return [label, icon, item_name(it) if not empty else "(empty)",
                fact["cat"] if fact else "", fact["dmg_text"] if fact else "", fact["armor_text"] if fact else "",
                dur, req_text("Str"), req_text("Mag"), req_text("Dex"), req_text("Lvl"), size, qual,
                fact["limits"] if fact else "", it["amount"] if not empty else "", it["seed"] if not empty else "",
                rank]

    def update_visual(self):
        if self.visual is None or not self.main.save:
            return
        r = self.table.currentRow()
        view = catalog.view_from(self.main)
        classic = caps.classic(self.save().player)
        if self.kind == "inv":
            self.visual.update_grid(Inventory(self.save().player).grid(), self.container(), r if r >= 0 else None,
                                    view=view, classic=classic)
        else:
            self.visual.update_items(self.container(), r if r >= 0 else None, view=view, classic=classic)

    def on_row_changed(self):
        self.update_visual(); self.load_editor()

    def current(self):
        r = self.table.currentRow()
        items = self.container() if self.main.save else []
        return (r, items[r]) if 0 <= r < len(items) else (None, None)

    def select_row(self, r):
        self.table.setCurrentCell(r, 0)

    # -- visual clicks
    def on_slot_clicked(self, idx):
        """Paperdoll / belt box: select; if empty, open the slot-filtered picker."""
        self.select_row(idx)
        if self.container()[idx].empty:
            self.add()

    def on_cell_clicked(self, cell):
        inv = Inventory(self.save().player)
        idx = inv.item_at(cell)
        if idx is not None:
            self.select_row(idx)
        else:
            self.last_empty_cell = cell
            self.pending_cell = cell
            try:
                self.add()
            finally:
                self.pending_cell = None

    def load_editor(self):
        r, it = self.current()
        if it is None:
            self.sel_label.setText("-"); self.info_label.setText(""); self.e_seed.setText(""); return
        if it.empty:
            self.info_label.setText(""); self.e_seed.setText("")
            where = SLOT_NAMES[r] if self.kind == "equip" else "slot %d" % (r + 1)
            self.sel_label.setText("<i>%s is empty - click it to add an item</i>" % where); return
        b = BASE_ITEMS[it["baseItemIndex"]] if 0 <= it["baseItemIndex"] < len(BASE_ITEMS) else {}
        self.sel_label.setText("<b style='color:%s'>%s</b><br>%s · %s" % (
            quality_color(it).name(), item_name(it), category(b) if b else "?",
            QUALITY_NAMES[quality_of(it)]))
        slot = SLOT_NAMES[r] if self.kind == "equip" else ""
        self.info_label.setText(describe_item(
            it, slot=slot, view=catalog.view_from(self.main), classic=caps.classic(self.save().player)))
        self.e_amount.setValue(max(0, it["amount"])); self.e_cd.setValue(it["curDurability"])
        self.e_bd.setValue(it["baseDurability"]); self.e_cc.setValue(it["curCharges"])
        self.e_bc.setValue(it["baseCharges"]); self.e_uniq.setValue(it["uniqIndex"]); self.e_qual.setValue(it["quality"])
        self.e_seed.setText(str(int(it["seed"])))
        self.show_seed_history()

    # -- seed history (session only)
    def seed_key(self):
        r, it = self.current()
        if it is None or it.empty:
            return None
        tab = self.tab_spin.value() if self.kind == "stash" else 0
        return (self.main.path, self.kind, tab, r, it["baseItemIndex"])

    def show_seed_history(self):
        key = self.seed_key()
        lst = self.main.seed_history.list(key) if key else []
        self.seed_back_btn.setEnabled(len(lst) >= 2)
        self.seed_hist_label.setText("Seed history: " + " → ".join(str(x) for x in lst[-6:]) if len(lst) >= 2 else "")

    def previous_seed(self):
        key = self.seed_key()
        if key is None:
            return None
        prev = self.main.seed_history.back(key)
        if prev is not None:
            self.e_seed.setText(str(prev))
        self.show_seed_history()
        return prev

    def save_preset(self):
        r, it = self.current()
        return self.main.presets.save_item(it)

    def refresh_seed_hint(self):
        msg, kind = describe_seed(self.e_seed.text())
        self.seed_hint.setText(msg)
        self.seed_hint.setStyleSheet("color: %s; font-size: 9pt;" % _SEED_COLOR[kind])

    def roll_seed(self):
        key = self.seed_key()
        if key is not None:
            try:
                self.main.seed_history.push(key, int(self.e_seed.text().strip(), 10))
            except ValueError:
                pass
        # 10**(digits-1) is the smallest 10-digit seed. GAME_SEED_MAX is included.
        self.e_seed.setText(str(random.randrange(10 ** (GAME_SEED_DIGITS - 1), GAME_SEED_MAX + 1)))
        if key is not None:
            self.main.seed_history.push(key, int(self.e_seed.text()))
            self.show_seed_history()

    def _seed_value(self):
        text = self.e_seed.text().strip()
        try:
            seed = int(text, 10)
        except ValueError:
            self.main.warn("Seed must be a whole number.")
            return None
        if seed < SAVE_SEED_MIN or seed > SAVE_SEED_MAX:
            self.main.warn("Seed must fit in a signed 64-bit number.")
            return None
        return seed

    def apply(self):
        r, it = self.current()
        if it is None or it.empty:
            return
        if self.e_cd.value() > self.e_bd.value():
            return self.main.warn("Durability cannot exceed max durability.")
        if self.e_cc.value() > self.e_bc.value():
            return self.main.warn("Charges cannot exceed max charges.")
        if it["baseItemIndex"] == GOLD_BASE and not 0 < self.e_amount.value() <= MAX_GOLD_IN_CELL:
            return self.main.warn("A gold pile must hold 1 to %d gold." % MAX_GOLD_IN_CELL)
        seed = self._seed_value()
        if seed is None:
            return
        if seed < GAME_SEED_MIN or seed > GAME_SEED_MAX:
            self.main.warn(
                "This seed is wider than the game keeps. The save will store it, "
                "but on load the game keeps a signed 32-bit value (10 digits, at most %d) "
                "and drops the rest." % GAME_SEED_MAX)
        it.update(amount=self.e_amount.value(), curDurability=self.e_cd.value(), baseDurability=self.e_bd.value(),
                  curCharges=self.e_cc.value(), baseCharges=self.e_bc.value(), uniqIndex=self.e_uniq.value(),
                  quality=self.e_qual.value(), seed=seed)
        key = self.seed_key()
        if key is not None:
            self.main.seed_history.push(key, seed)
        self.main.after_item_change()

    # -- placement (validated)
    def target_slot(self):
        """For equip/belt: the selected slot if empty, else the first empty one."""
        r, cur = self.current()
        slots = self.container()
        if cur is not None and cur.empty:
            return r
        return next((i for i, x in enumerate(slots) if x.empty), None)

    def place(self, item, w=1, h=1, slot=None, cell=None):
        b = BASE_ITEMS[item["baseItemIndex"]] if 0 <= item["baseItemIndex"] < len(BASE_ITEMS) else {}
        p = self.save().player
        if self.kind in ("equip", "belt"):
            if slot is None:
                slot = self.target_slot()
            if slot is None:
                raise ValueError("no empty slot - remove an item first")
            if not self.container()[slot].empty:
                raise ValueError("%s is occupied - remove that item first" % (SLOT_NAMES[slot] if self.kind == "equip" else "Belt slot %d" % (slot + 1)))
            msg = why_not(b, self.kind, slot)
            if msg:
                raise ValueError(msg)
            self.container()[slot] = item
            return slot
        if self.kind == "inv":
            inv = Inventory(p)
            return inv.add_at(item, w, h, cell) if cell is not None else inv.add(item, w, h)
        if not self.save().stash:
            raise ValueError("this save has no stash entry")
        return StashTabGrid(self.stash_tab()).add(item, w, h)

    def add(self):
        if not self.main.save:
            return
        slot = self.target_slot() if self.kind in ("equip", "belt") else None
        if self.kind in ("equip", "belt") and slot is None:
            return self.main.warn("No empty slot - remove an item first.")
        dlg = BaseItemPicker(self, container=self.kind, slot=slot, show_size=self.kind in ("inv", "stash"))
        if self.main.auto_picker:          # test hook
            self.main.auto_picker(dlg)
        elif dlg.exec() != QDialog.Accepted:
            return
        uid = dlg.selected_unique()
        base_id = dlg.selected()
        if uid is None and base_id is None:
            return
        ver = self.save().player["version"]
        if uid is not None:
            u = UNIQUES[uid]
            base_id = u["baseId"]
            item = new_item(base_id, ver, dur=dlg.dur.value(), amount=0)
            mark_unique(item, uid, u["qlvl"], set_item=is_set_unique(uid))
        else:
            item = new_item(base_id, ver, dur=dlg.dur.value(), amount=dlg.amount.value())
        try:
            self.place(item, dlg.w.value(), dlg.h.value(), slot=slot, cell=self.pending_cell)
        except ValueError as e:
            return self.main.warn(str(e))
        b = BASE_ITEMS[base_id] if isinstance(base_id, int) and 0 <= base_id < len(BASE_ITEMS) else None
        msg = catalog.restriction_message(b, catalog.view_from(self.main)) if b else ""
        if msg:
            self.main.warn(msg)
        self.main.after_item_change()

    def remove(self):
        r, it = self.current()
        if it is None or it.empty:
            return
        p = self.save().player
        if self.kind == "inv":
            Inventory(p).remove(r)
        elif self.kind == "stash":
            StashTabGrid(self.stash_tab()).remove(r)
        else:
            self.container()[r] = blank_item()
        self.main.after_item_change()

    def clone(self):
        r, it = self.current()
        if it is None or it.empty:
            return
        c = clone_item(it, self.new_seed.isChecked())
        try:
            if self.kind in ("inv", "stash"):
                w, h = self.size_of(r)
                self.place(c, w, h)
            else:  # equipped/belt clones go to inventory
                w, h = 1, 1
                b = BASE_ITEMS[it["baseItemIndex"]] if 0 <= it["baseItemIndex"] < len(BASE_ITEMS) else {}
                if b.get("w"):
                    w, h = b["w"], b["h"]
                Inventory(self.save().player).add(c, w, h)
        except ValueError as e:
            return self.main.warn(str(e))
        self.main.after_item_change()


class ReferenceDialog(QDialog):
    """Searchable list of uniques (UniqueItems.cpp) and affixes (Affixes.cpp)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Uniques & affixes reference (from the game source)")
        self.resize(900, 640)
        v = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="Search name or effect ...")
        v.addWidget(self.search)
        self.table = QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["Kind", "Name", "Base / qlvl", "Effects", "Id"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.addWidget(self.table, 1)
        self.rows = []
        for uid, u in sorted(UNIQUES.items()):
            b = BASE_ITEMS[u["baseId"]] if 0 <= u["baseId"] < len(BASE_ITEMS) else None
            kind = "SET" if is_set_unique(uid) else "UNIQUE"
            who = catalog.who_for(b)
            self.rows.append((kind, u["name"], "%s · %s · %s" % (base_name(u["baseId"]), who, catalog.rarity_mark(u["qlvl"])),
                              "; ".join(effect_text(e) for e in u["effects"]), uid))
        for kind, name, eff, q, aid in affix_rows():
            self.rows.append((kind, name, "qlvl %d" % q, eff, aid))
        self.search.textChanged.connect(self.fill); self.fill("")

    def fill(self, t):
        t = t.lower().strip()
        rows = [r for r in self.rows if not t or t in " ".join(str(x) for x in r[:4]).lower()][:3000]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, val in enumerate(r):
                it = QTableWidgetItem(str(val))
                if c == 1 and r[0] == "UNIQUE":
                    it.setForeground(QColor("#d9a93c"))
                elif c == 1 and r[0] == "SET":
                    it.setForeground(QColor("#3fbf5f"))
                self.table.setItem(i, c, it)


# ----------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.save = None
        self.path = None
        self.dirty = False
        self.setWindowTitle("CheeseStick - The Hell 4 save editor")
        self.setWindowIcon(cheesestick_icon())
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(cheesestick_icon())
        self.resize(1180, 820)
        self.auto_picker = None  # tests: callable(dialog) instead of dlg.exec()
        self.auto_confirm = None        # tests: QMessageBox.Save/Discard/Cancel answer for the unsaved prompt
        self.auto_game_running = None   # tests: answer for the game-running prompt
        self.auto_apply_pending = None     # tests: QMessageBox.Yes/No for "apply pending edits?"
        self.auto_game_in_progress = None
        self.auto_preset_name = None       # tests: (name, notes) instead of the name dialog
        self.auto_confirm_delete = None    # tests: True/False for "delete preset?"
        self.auto_export_all = None        # tests: skip the "export only this one?" question
        self.auto_loadout_replace = None   # tests: True/False for "replace worn items?"
        self.unsaved_msg = UNSAVED_MSG
        self.seed_history = SeedHistory()
        self.last_pairing_prompt = None  # tests: "remove" | "keep" | "cancel"
        self.game_running = running_game_processes
        self._snap = {}
        central = QWidget(); cv = QVBoxLayout(central); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(0)
        self.header = HeaderBar(); cv.addWidget(self.header)
        self.outer = QTabWidget(); self.outer.setDocumentMode(False)
        wrap = QWidget(); wl = QVBoxLayout(wrap); wl.setContentsMargins(12, 10, 12, 10); wl.addWidget(self.outer)
        cv.addWidget(wrap, 1)
        self.setCentralWidget(central)
        self.finder = FinderPanel(self)
        self.finder.open_requested.connect(self.open_from_finder)
        self.outer.addTab(self.finder, "🔍  Find Characters")
        self.tabs = QTabWidget(); self.outer.addTab(self.tabs, "⚔  Editor")
        self._build_menu()
        self._build_character()
        self._build_spells()
        self._build_perks()
        self.lists = {}
        for kind, title in (("equip", "🛡  Equipped"), ("inv", "🎒  Inventory"), ("belt", "🧪  Belt"), ("stash", "📦  Stash")):
            w = ItemList(self, kind); self.lists[kind] = w; self.tabs.addTab(w, title)
        self.browser = ItemBrowser(self)
        self.tabs.addTab(self.browser, "📖  Item Browser")
        self.presets = PresetsPanel(self)
        self.tabs.addTab(self.presets, "★  Presets")
        self.browser.icons_ready.connect(self.on_icons)
        self.tabs.currentChanged.connect(self._editor_tab)
        self.tabs.setEnabled(False)
        for sp in [self.c_level] + self.stat_spins:
            sp.valueChanged.connect(lambda *_: self.save and self.update_caps())
        self.dirty_label = QLabel("  ● " + UNSAVED_MSG + "  "); self.dirty_label.setObjectName("DirtyStatus")
        self.dirty_label.setVisible(False); self.statusBar().addPermanentWidget(self.dirty_label)
        stick = QLabel()
        mark = cheesestick_pixmap(18)
        if not mark.isNull():
            stick.setPixmap(mark)
        stick.setToolTip(DEDICATION)
        self.statusBar().addPermanentWidget(stick)
        self.header.save_btn.clicked.connect(self.save_file)
        self.statusBar().showMessage("CheeseStick is here. Open a single-player, Dark, or Outbreak save (close the game first).")

    # ---- UI construction
    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        for text, key, fn in (("&Open...", QKeySequence.Open, self.open_dialog),
                              ("&Save", QKeySequence.Save, self.save_file),
                              ("&Find Characters", QKeySequence("Ctrl+F"), self.find_characters),
                              ("&Quit", QKeySequence.Quit, self.close)):
            a = QAction(text, self); a.setShortcut(key); a.triggered.connect(fn); m.addAction(a)
        g = self.menuBar().addMenu("&Multiplayer")
        a = QAction("Launcher && paths...", self); a.setShortcut(QKeySequence("Ctrl+L"))
        a.triggered.connect(self.show_launcher); g.addAction(a)
        h = self.menuBar().addMenu("&Help")
        a = QAction("About CheeseStick...", self); a.triggered.connect(self.show_about); h.addAction(a)
        a = QAction("Uniques && affixes reference...", self); a.triggered.connect(self.show_reference); h.addAction(a)

    def show_launcher(self):
        from .launcher import LauncherDialog
        d = LauncherDialog(self); d.exec()
        self.finder.start_scan()  # paths may have changed

    def _build_character(self):
        w = QWidget(); outer = QHBoxLayout(w); outer.setContentsMargins(14, 14, 14, 14)
        box = QGroupBox("Character"); f = QFormLayout(box); f.setSpacing(8); f.setLabelAlignment(Qt.AlignRight)
        outer.addWidget(box, 0); outer.addStretch(1)
        self.c_name = QLineEdit(); self.c_name.setMaxLength(31)
        self.c_class = QComboBox(); self.c_class.addItems(CLASS_NAMES)
        self.c_level = spin(1, 150); self.c_level_xp = QPushButton("Set XP to level minimum")
        self.c_level_xp.clicked.connect(self.xp_for_level)
        self.c_level_max = maxbtn("Max level for this game mode, with the matching XP (th2data.cpp PlayerMaxLevel / LevelUpTable)")
        self.c_level_max.clicked.connect(self.max_level)
        self.c_xp = QLineEdit()
        self.c_str, self.c_mag, self.c_dex, self.c_vit = (spin(0, I16[1]) for _ in range(4))
        self.c_points = spin(0, I16[1])
        self.c_gold = spin(0, U32_MAX_SPIN)
        self.c_life, self.c_maxlife, self.c_mana, self.c_maxmana = (spin(0, U32_MAX_SPIN) for _ in range(4))
        self.c_info = QLabel()
        f.addRow("Name", self.c_name); f.addRow("Class", self.c_class)
        lv = QHBoxLayout(); lv.addWidget(self.c_level); lv.addWidget(self.c_level_xp); lv.addWidget(self.c_level_max); f.addRow("Level", lv)
        f.addRow("Experience", self.c_xp)
        self.stat_spins = [self.c_str, self.c_mag, self.c_dex, self.c_vit]
        self.stat_caps = []
        for i, (lbl, s) in enumerate((("Strength", self.c_str), ("Magic", self.c_mag), ("Dexterity", self.c_dex),
                                      ("Vitality", self.c_vit))):
            b = maxbtn("Raise to the class cap (GetPlayerMaxStat), limited by the stat-sum cap for the level")
            b.clicked.connect(lambda _=False, i=i: self.max_stats(i))
            cap = QLabel(""); cap.setObjectName("HeaderSub"); self.stat_caps.append(cap)
            row = QHBoxLayout(); row.addWidget(s); row.addWidget(b); row.addWidget(cap, 1); f.addRow(lbl, row)
        self.c_stats_all = QPushButton("Max all stats"); self.c_stats_all.clicked.connect(lambda: self.max_stats(None))
        self.c_stat_sum = QLabel(""); self.c_stat_sum.setObjectName("HeaderSub")
        row = QHBoxLayout(); row.addWidget(self.c_stats_all); row.addWidget(self.c_stat_sum, 1); f.addRow("", row)
        f.addRow("Free stat points", self.c_points)
        self.c_gold_max = maxbtn("Fill free inventory cells with %s-gold piles (MaxGoldInCell), total capped at %s (TotalGold is a 32-bit int)"
                                 % (format(MAX_GOLD_IN_CELL, ","), format(caps.MAX_GOLD_TOTAL, ",")))
        self.c_gold_max.clicked.connect(self.max_gold)
        self.c_gold_note = QLabel(""); self.c_gold_note.setObjectName("HeaderSub")
        row = QHBoxLayout(); row.addWidget(self.c_gold); row.addWidget(self.c_gold_max); row.addWidget(self.c_gold_note, 1)
        f.addRow("Gold (inventory piles)", row)
        self.c_max_all = QPushButton("Max all (level, XP, stats, gold)"); self.c_max_all.clicked.connect(self.max_all_character)
        for lbl, s in (("Life (raw, /64)", self.c_life), ("Max life (raw, /64)", self.c_maxlife),
                       ("Mana (raw, /64)", self.c_mana), ("Max mana (raw, /64)", self.c_maxmana)):
            f.addRow(lbl, s)
        f.addRow(self.c_max_all)
        ap = QPushButton(APPLY_TEXT); ap.setObjectName("Primary"); ap.clicked.connect(self.apply_character); f.addRow(ap)
        ap.setToolTip("Puts these values into the character in memory. Nothing is written until File > Save (Ctrl+S).")
        self.apply_buttons = [ap]
        f.addRow(self.c_info)
        self.tabs.addTab(w, "👤  Character")

    def _build_spells(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.spell_note = QLabel(""); self.spell_note.setObjectName("HeaderSub"); self.spell_note.setWordWrap(True); v.addWidget(self.spell_note)
        self.spell_table = QTableWidget(0, 5); self.spell_table.setHorizontalHeaderLabels(["Id", "Spell", "Level", "Game cap", ""])
        self.spell_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.spell_table.verticalHeader().setVisible(False)
        v.addWidget(self.spell_table)
        row = QHBoxLayout()
        b = QPushButton("Max all spells"); b.clicked.connect(lambda: self.max_spells(None)); row.addWidget(b)
        ap = QPushButton(APPLY_TEXT); ap.setObjectName("Primary"); ap.clicked.connect(self.apply_spells); row.addWidget(ap, 1)
        v.addLayout(row)
        self.tabs.addTab(w, "✨  Skills")

    def _build_perks(self):
        w = QWidget(); v = QVBoxLayout(w)
        tr = QHBoxLayout(); tr.addWidget(QLabel("Traits:"))
        self.trait_boxes = []
        for _ in range(4):
            cb = QComboBox()
            for k in sorted(TRAITS):
                cb.addItem("%d %s" % (k, TRAITS[k]), k)
            self.trait_boxes.append(cb); tr.addWidget(cb)
        v.addLayout(tr)
        self.perk_note = QLabel(caps.perk_points_cap_note()); self.perk_note.setObjectName("HeaderSub"); self.perk_note.setWordWrap(True)
        v.addWidget(self.perk_note)
        self.perk_table = QTableWidget(0, 5); self.perk_table.setHorizontalHeaderLabels(["Id", "Perk", "Level", "Game cap", ""])
        self.perk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.perk_table.verticalHeader().setVisible(False)
        v.addWidget(self.perk_table)
        row = QHBoxLayout()
        b = QPushButton("Max all perks"); b.clicked.connect(lambda: self.max_perks(None)); row.addWidget(b)
        ap = QPushButton(APPLY_TEXT); ap.setObjectName("Primary"); ap.clicked.connect(self.apply_perks); row.addWidget(ap, 1)
        v.addLayout(row)
        self.tabs.addTab(w, "⭐  Perks / Traits")

    # ---- helpers
    def warn(self, msg):
        QMessageBox.warning(self, "CheeseStick", msg)

    def mark_dirty(self):
        self.set_dirty(True)

    def set_dirty(self, dirty):
        self.dirty = dirty
        name = os.path.basename(self.path or "")
        self.setWindowTitle(("● %s - UNSAVED - CheeseStick" if dirty else "%s - CheeseStick") % name
                            if name else "CheeseStick - The Hell 4 save editor")
        self.header.set_dirty(dirty)
        self.dirty_label.setVisible(dirty)
        if dirty:
            self.statusBar().showMessage(UNSAVED_MSG)

    def confirm_discard(self, action="continue"):
        """True if it is OK to drop the in-memory edits (saved, discarded, or none)."""
        if not self.dirty:
            return True
        if self.auto_confirm is not None:          # tests
            ans = self.auto_confirm
        else:
            ans = QMessageBox.question(self, "Unsaved changes",
                                       "You have unsaved changes to %s.\nSave them before you %s?" % (os.path.basename(self.path or ""), action),
                                       QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if ans == QMessageBox.Save:
            return self.save_file()
        return ans == QMessageBox.Discard

    # ---- load / save
    def open_dialog(self):
        if not self.confirm_discard("open another save"):
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open The Hell 4 save", "", "TH4 saves (*.ssv *.msv *.dsv *.osv *.csv *.ksv);;All files (*)")
        if path:
            self.open_path(path)

    def find_characters(self):
        self.outer.setCurrentWidget(self.finder)
        self.finder.start_scan()

    def open_from_finder(self, path):
        if not self.confirm_discard("open another save"):
            return
        self.open_path(path)

    def open_path(self, path):
        from . import paths_config
        if paths_config.is_real_game(path):
            QMessageBox.warning(self, "Read-only", "This save belongs to the real game (TH4_v0.773), which "
                                "CheeseStick keeps read-only.\n\nCopy the hero into TH4_dev to edit it.\n\n%s" % path)
            return False
        try:
            self.save = SaveFile.load(path)
        except Exception as e:
            self.save = None
            return self.warn("Could not open save:\n%s" % e)
        self.path = path; self.set_dirty(False)
        self.tabs.setEnabled(True)
        self.refresh_all()
        self.outer.setCurrentWidget(self.tabs)
        self._editor_tab(self.tabs.currentIndex())
        sm = self.save.player.summary()
        self.statusBar().showMessage("Loaded %s - %s, save v%d, layout %s" % (os.path.basename(path), sm["name"], sm["version"], sm["layout"]))

    def validate(self):
        p = self.save.player
        errs = []
        if not p.name:
            errs.append("Name is empty.")
        if not 1 <= p["CharLevel"] <= 150:
            errs.append("Level must be 1-150.")
        if p["Xp"] < 0:
            errs.append("XP is negative.")
        inv = Inventory(p)
        for i, it in enumerate(inv.items()):
            if not inv.cells_of(i):
                errs.append("Inventory item %d has no grid cell." % i)
            if it["baseItemIndex"] == GOLD_BASE and not 0 < it["amount"] <= MAX_GOLD_IN_CELL:
                errs.append("Gold pile %d amount out of range." % i)
        if p["TotalGold"] != sum(i["amount"] for i in inv.items() if i["baseItemIndex"] == GOLD_BASE):
            errs.append("TotalGold does not match inventory gold piles.")
        return errs

    HERO_ONLY_LABELS = {"SpellLevels": "spell levels", "AvailableSpellMask": "learned spells", "perk": "perks",
                        "traits": "traits", "gameChanger": "game changers", "ClassId": "class", "subclassID": "subclass",
                        "specializationID": "specialization", "TotalGold": "gold", "OnBodySlots": "equipped items",
                        "InventorySlots": "inventory items", "InvUsed": "inventory items", "InvItemCount": "inventory items",
                        "BeltInventory": "belt items", "TalismanSlots": "talismans"}

    def pairing_default(self):
        try:
            return scan.load_settings(self.finder.settings_file).get("pairing_choice", "unpair")
        except Exception:
            return "unpair"

    def remember_pairing(self, choice):
        try:
            d = scan.load_settings(self.finder.settings_file); d["pairing_choice"] = choice
            scan.save_settings(d, self.finder.settings_file)
        except Exception:
            pass

    def pairing_question(self):
        """Text + available choices for the 'game in progress' question asked on EVERY save."""
        sv = self.save
        if sv.game_plain is None:
            if sv.hero_entry == "mphero":
                return ("This is a multiplayer save. There is no game-in-progress copy; "
                        "the game loads this hero directly.", ["save", "cancel"])
            return ("No game in progress; edits will load on New Game.", ["save", "cancel"])
        gs = sv.game_state()
        other = sorted({self.HERO_ONLY_LABELS.get(k, k) for k in sv.hero_only_changes()})
        msg = ("This save is paired with a game in progress. The game loads the hero from that game "
               "(Load Game), not from the character you edited.\n\n"
               "Unpair (recommended): remove the game in progress so your edits always load. Pick the hero "
               "and start a New Game (you begin in town; that session's dungeon levels are regenerated).\n\n"
               "Keep: keep the game in progress and copy level, XP, stats, stat points, life and mana into it.")
        if other:
            msg += " These edits would NOT carry over: %s." % ", ".join(other)
        choices = ["unpair", "keep", "cancel"]
        if not gs.ok:
            msg += "\n\nKeep is unavailable: the game-in-progress copy could not be read (%s)." % gs.why
            choices.remove("keep")
        return msg, choices

    def handle_game_in_progress(self):
        """Ask on every save (Christopher's rule). Returns False to cancel the save."""
        msg, choices = self.pairing_question()
        default = self.pairing_default()
        if self.auto_game_in_progress is not None:          # tests
            ans = self.auto_game_in_progress
            self.last_pairing_prompt = (msg, choices, default)
        else:
            box = QMessageBox(QMessageBox.Warning if "unpair" in choices else QMessageBox.Information,
                              "Save: game in progress", msg, QMessageBox.NoButton, self)
            btn = {}
            if "save" in choices:
                btn["save"] = box.addButton("Save", QMessageBox.AcceptRole)
            if "unpair" in choices:
                btn["unpair"] = box.addButton("Unpair (recommended)", QMessageBox.AcceptRole)
            if "keep" in choices:
                btn["keep"] = box.addButton("Keep with core-stat sync", QMessageBox.AcceptRole)
            btn["cancel"] = box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(btn.get(default) or btn.get("unpair") or btn.get("save"))
            box.exec()
            ans = next((k for k, b in btn.items() if b is box.clickedButton()), "cancel")
        if ans not in choices or ans == "cancel":
            return False
        if ans in ("unpair", "keep"):
            self.remember_pairing(ans)
        self.save.drop_game = ans == "unpair"
        return True

    def save_file(self):
        """Returns True when the file was written and verified."""
        if not self.save:
            return False
        if self.pending_unapplied():
            if (self.auto_apply_pending if self.auto_apply_pending is not None else QMessageBox.question(self, "Not applied yet", "Some fields were edited but not applied.\n"
                                    "Apply the Character / Skills / Perks tabs now and then save?")) == QMessageBox.Yes:
                self.apply_all_tabs()
        errs = self.validate()
        if errs:
            self.warn("Fix these before saving:\n- " + "\n- ".join(errs)); return False
        if self.save.changed_on_disk(self.path):
            self.warn("The game (or another program) saved %s after you opened it.\n\nSaving now would "
                      "overwrite the game's newer progress with the old copy loaded here, so nothing was "
                      "written. Close and reopen the save (File > Open or Find Characters), then redo your "
                      "edits." % os.path.basename(self.path))
            self.statusBar().showMessage("Not saved: file changed on disk, reopen it. " + UNSAVED_MSG)
            return False
        if not self.handle_game_in_progress():
            return False
        procs = self.game_running()
        if procs:
            msg = ("The Hell 4 appears to be running (%s).\n\nThe game keeps the hero in memory and overwrites "
                   "the save when you leave or quit, so your edits would be lost. Quit the game to the main "
                   "menu or desktop first.\n\nSave anyway?" % ", ".join(sorted(set(procs))))
            ans = self.auto_game_running if self.auto_game_running is not None else \
                QMessageBox.warning(self, "Game is running", msg, QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
            if ans != QMessageBox.Save:
                self.statusBar().showMessage("Not saved: the game is running. " + UNSAVED_MSG); return False
        dropped = self.save.drop_game
        try:
            backup = self.save.save_safely(self.path)
        except Exception as e:
            traceback.print_exc(); self.save.drop_game = False
            self.warn("Save FAILED, original file untouched:\n%s" % e); return False
        self.set_dirty(False)
        extra = ("  Game in progress removed: pick the hero and start (New Game)." if dropped else
                 "  Game-in-progress copy updated too." if self.save.game_plain is not None else "")
        self.statusBar().showMessage("Saved and verified ✔%s  Backup: %s" % (extra, backup))
        return True

    # ---- refresh
    def refresh_all(self):
        p = self.save.player
        gm0 = p["gameMode"]
        self.header.set_character(p.name or "(no name)", CLASS_NAMES[p["ClassId"]] if p["ClassId"] < len(CLASS_NAMES) else "?",
                                  p["CharLevel"], "%s · %s gold" % (GAME_MODES[gm0] if 0 <= gm0 < len(GAME_MODES) else gm0,
                                                                   format(p["TotalGold"], ",")))
        self.c_name.setText(p.name)
        self.c_class.setCurrentIndex(min(p["ClassId"], len(CLASS_NAMES) - 1))
        self.c_level.setValue(max(1, min(150, p["CharLevel"])))
        self.c_xp.setText(str(p["Xp"]))
        for s, k in ((self.c_str, "BaseStrength"), (self.c_mag, "BaseMagic"), (self.c_dex, "BaseDexterity"),
                     (self.c_vit, "BaseVitality"), (self.c_points, "AvailableLvlPoints")):
            s.setValue(max(0, p[k]))
        self.c_gold.setValue(min(U32_MAX_SPIN, p["TotalGold"]))
        for s, k in ((self.c_life, "BaseLife"), (self.c_maxlife, "MaxBaseLife"), (self.c_mana, "BaseMana"), (self.c_maxmana, "MaxBaseMana")):
            s.setValue(min(U32_MAX_SPIN, p[k]))
        gm = p["gameMode"]
        self.c_info.setText("Game mode: %s   Difficulty: %d   Subclass: %d   Save version: %d   Life %.1f/%.1f  Mana %.1f/%.1f"
                            % (GAME_MODES[gm] if 0 <= gm < len(GAME_MODES) else gm, p["Difficulty"], p["subclassID"],
                               p["version"], p["BaseLife"] / 64, p["MaxBaseLife"] / 64, p["BaseMana"] / 64, p["MaxBaseMana"] / 64))
        # spells
        ids = sorted(k for k, v in SPELLS.items() if v and k < 128)
        self.spell_table.setRowCount(len(ids))
        for r, k in enumerate(ids):
            self.spell_table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.spell_table.setItem(r, 1, QTableWidgetItem(SPELLS[k]))
            self.spell_table.setCellWidget(r, 2, spin(0, 255, p["SpellLevels"][k]))
            b = maxbtn("Highest level the game keeps for this class and level (Player.cpp LimitSpellLevels)")
            b.clicked.connect(lambda _=False, r=r: self.max_spells(r)); self.spell_table.setCellWidget(r, 4, b)
        # perks
        pids = sorted(k for k in PERKS if k < 800)
        self.perk_table.setRowCount(len(pids))
        perk = p["perk"]
        for r, k in enumerate(pids):
            self.perk_table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.perk_table.setItem(r, 1, QTableWidgetItem(PERKS[k]))
            v = perk[k] - 256 if perk[k] > 127 else perk[k]
            self.perk_table.setCellWidget(r, 2, spin(0, 127, max(0, v)))
            b = maxbtn("Highest rank the game keeps for this character (Perks.cpp getPerkMaxLevel)")
            b.clicked.connect(lambda _=False, r=r: self.max_perks(r)); self.perk_table.setCellWidget(r, 4, b)
            info = caps.PERK_INFO.get(k)
            if info and info["desc"]:
                self.perk_table.item(r, 1).setToolTip("<br>".join(d.replace("%i", "N") for d in info["desc"]))
        for cb, t in zip(self.trait_boxes, p["traits"]):
            i = cb.findData(t); cb.setCurrentIndex(i if i >= 0 else 0)
        for l in self.lists.values():
            l.refresh()
        self.update_caps()
        self._snap = self.ui_state()

    # ---- caps / Max buttons (cheesestick/caps.py, all from the game source)
    def ui_level(self):
        return self.c_level.value()

    def update_caps(self):
        if not self.save:
            return
        p = self.save.player
        lvl = self.ui_level()
        self.c_level.setMaximum(caps.max_level(p))
        mx = caps.max_stats(p)
        for lab, m in zip(self.stat_caps, mx):
            lab.setText("class cap %d" % m)
        self.c_stat_sum.setText("%s: stat-sum cap at level %d is %d (now %d)" % (
            caps.full_class_name(p), lvl, caps.stat_sum_limit(p, lvl), sum(x.value() for x in self.stat_spins)))
        self.c_gold_note.setText("max %s" % format(self.gold_capacity(), ","))
        self.spell_note.setText("Game cap = min(2×level/3 + 3, %d) for spells your class can use; the game lowers anything "
                                "higher when it loads the hero (Player.cpp LimitSpellLevels). Based on level %d."
                                % (caps.C["SpellLevelBookMaxClassic"] if caps.classic(p) else caps.C["SpellLevelBookMax"], lvl))
        for r in range(self.spell_table.rowCount()):
            k = int(self.spell_table.item(r, 0).text())
            self.spell_table.setItem(r, 3, QTableWidgetItem(str(caps.spell_cap(p, k, lvl))))
        for r in range(self.perk_table.rowCount()):
            k = int(self.perk_table.item(r, 0).text())
            cap, note = caps.perk_cap(p, k)
            it = QTableWidgetItem("?" if cap is None else str(cap)); it.setToolTip(note)
            self.perk_table.setItem(r, 3, it)
        if getattr(self, "browser", None) is not None:
            self.browser.refilter()

    def max_level(self):
        p = self.save.player
        lv = caps.max_level(p)
        self.c_level.setValue(lv); self.c_xp.setText(str(caps.xp_for_level(p, lv)))
        self.update_caps(); self.statusBar().showMessage("Level set to %d with %s XP. Press %s." % (lv, format(caps.xp_for_level(p, lv), ","), APPLY_TEXT))

    def max_stats(self, only=None):
        p = self.save.player
        new = caps.max_stat_values(p, [x.value() for x in self.stat_spins], self.ui_level(), only)
        for sp, v in zip(self.stat_spins, new):
            sp.setValue(v)
        self.update_caps()

    def gold_capacity(self):
        p = self.save.player
        inv = Inventory(p)
        piles = sum(1 for it in inv.items() if it["baseItemIndex"] == GOLD_BASE)
        free = sum(1 for c in inv.grid() if c == 0)
        return min(caps.MAX_GOLD_TOTAL, (piles + free) * MAX_GOLD_IN_CELL)

    def max_gold(self):
        self.c_gold.setValue(self.gold_capacity()); self.update_caps()

    def max_all_character(self):
        self.max_level(); self.max_stats(None); self.max_gold()

    def max_spells(self, row=None):
        p = self.save.player
        rows = range(self.spell_table.rowCount()) if row is None else [row]
        for r in rows:
            k = int(self.spell_table.item(r, 0).text())
            self.spell_table.cellWidget(r, 2).setValue(caps.spell_cap(p, k, self.ui_level()))

    def max_perks(self, row=None):
        p = self.save.player
        rows = range(self.perk_table.rowCount()) if row is None else [row]
        skipped = 0
        for r in rows:
            cap, _ = caps.perk_cap(p, int(self.perk_table.item(r, 0).text()))
            if cap is None:
                skipped += 1; continue
            self.perk_table.cellWidget(r, 2).setValue(cap)
        if skipped:
            self.statusBar().showMessage("%d perk(s) left unchanged: their availability rule could not be evaluated." % skipped)

    def _char_state(self):
        return [self.c_name.text(), self.c_class.currentIndex(), self.c_level.value(), self.c_xp.text(),
                self.c_points.value(), self.c_gold.value(), self.c_life.value(), self.c_maxlife.value(),
                self.c_mana.value(), self.c_maxmana.value()] + [x.value() for x in self.stat_spins]

    def _widget_values(self, table):
        out = []
        for r in range(table.rowCount()):
            w = table.cellWidget(r, 2)
            out.append(0 if w is None else w.value())
        return out

    def _spell_state(self):
        return self._widget_values(self.spell_table)

    def _perk_state(self):
        return self._widget_values(self.perk_table)

    def _trait_state(self):
        return [cb.currentData() for cb in self.trait_boxes]

    def ui_state(self):
        return {"char": self._char_state(), "spells": self._spell_state(),
                "perks": self._perk_state(), "traits": self._trait_state()}

    def _restore_values(self, table, values):
        for r, v in enumerate(values):
            if r >= table.rowCount():
                break
            w = table.cellWidget(r, 2)
            if w is not None:
                w.setValue(v)

    def _restore_spells(self, values):
        self._restore_values(self.spell_table, values)

    def _restore_perks(self, perks, traits):
        self._restore_values(self.perk_table, perks)
        for cb, t in zip(self.trait_boxes, traits):
            i = cb.findData(t)
            if i >= 0:
                cb.setCurrentIndex(i)

    def _remember(self, **parts):
        """Snapshot only the tabs that were just applied.

        Applying spells used to copy the whole window, including a level that
        was still sitting in the spin box. Save then skipped that level.
        """
        old = self._snap if isinstance(self._snap, dict) else {}
        merged = self.ui_state()
        for key, val in old.items():
            if key not in parts:
                merged[key] = val
        merged.update(parts)
        self._snap = merged

    def pending_unapplied(self):
        return bool(self.save) and self.ui_state() != self._snap

    def apply_all_tabs(self):
        # apply_character rebuilds the spell and perk widgets from the save.
        # Keep what the user typed, write the character, then put those values back.
        spells, perks, traits = self._spell_state(), self._perk_state(), self._trait_state()
        self.apply_character()
        self._restore_spells(spells)
        self._restore_perks(perks, traits)
        self.apply_spells()
        self.apply_perks()

    def show_about(self):
        d = QDialog(self)
        d.setWindowTitle("CheeseStick")
        d.setWindowIcon(cheesestick_icon())
        v = QVBoxLayout(d)
        pic = QLabel()
        pm = cheesestick_pixmap(280)
        if not pm.isNull():
            pic.setPixmap(pm)
        pic.setAlignment(Qt.AlignCenter)
        v.addWidget(pic)
        title = QLabel("CheeseStick")
        title.setObjectName("HeaderName")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)
        body = QLabel(DEDICATION + "\n\nThe Hell 4 save editor. Nothing is written until you save.")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        v.addWidget(body)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(d.accept)
        v.addWidget(bb)
        d.resize(440, 520)
        d.exec()

    def show_reference(self):
        ReferenceDialog(self).exec()

    # ---- apply
    def xp_for_level(self):
        self.c_xp.setText(str(caps.xp_for_level(self.save.player, self.c_level.value())))

    def apply_character(self):
        p = self.save.player
        try:
            xp = int(self.c_xp.text())
            if not 0 <= xp < 2**63:
                raise ValueError
        except ValueError:
            return self.warn("XP must be a whole number >= 0.")
        try:
            p.name = self.c_name.text().strip()
        except (ValueError, UnicodeEncodeError) as e:
            return self.warn("Bad name: %s" % e)
        if not p.name:
            return self.warn("Name cannot be empty.")
        if self.c_life.value() > self.c_maxlife.value() or self.c_mana.value() > self.c_maxmana.value():
            return self.warn("Current life/mana cannot exceed max.")
        p["ClassId"] = self.c_class.currentIndex()
        lv = min(self.c_level.value(), caps.max_level(p))
        lo = caps.xp_for_level(p, lv)
        hi = (GAME["level_xp_classic"] if caps.classic(p) else GAME["level_xp"])[min(lv, 150)]
        fixed_xp = max(lo, min(xp, hi))   # game: level stays, Xp clamped to NextLevelUp
        p["CharLevel"] = lv; p["Xp"] = fixed_xp
        p["BaseStrength"], p["BaseMagic"], p["BaseDexterity"], p["BaseVitality"] = (
            self.c_str.value(), self.c_mag.value(), self.c_dex.value(), self.c_vit.value())
        p["AvailableLvlPoints"] = self.c_points.value()
        p["BaseLife"], p["MaxBaseLife"] = self.c_life.value(), self.c_maxlife.value()
        p["BaseMana"], p["MaxBaseMana"] = self.c_mana.value(), self.c_maxmana.value()
        try:
            self.set_gold(self.c_gold.value())
        except ValueError as e:
            return self.warn(str(e))
        self.mark_dirty(); self.refresh_all()
        self.statusBar().showMessage(("XP adjusted to %s to match level %d. " % (format(fixed_xp, ","), lv) if fixed_xp != xp else "")
                                     + "Character changes applied. " + UNSAVED_MSG)

    def set_gold(self, total):
        """Gold lives in inventory piles; rebalance piles so they sum to total."""
        inv = Inventory(self.save.player)
        if total == self.save.player["TotalGold"]:
            return
        piles = [i for i, it in enumerate(inv.items()) if it["baseItemIndex"] == GOLD_BASE]
        if total == 0:
            for i in reversed(piles):
                inv.remove(i)
        else:
            if not piles:
                inv.add(new_item(GOLD_BASE, self.save.player["version"], amount=0), 1, 1)
                piles = [inv.count - 1]
            for i in reversed(piles[1:]):
                inv.remove(i)
            need = total
            first = piles[0]
            amt = min(need, MAX_GOLD_IN_CELL)
            inv.items()[first]["amount"] = amt
            need -= amt
            while need > 0:
                amt = min(need, MAX_GOLD_IN_CELL)
                inv.add(new_item(GOLD_BASE, self.save.player["version"], amount=amt), 1, 1)
                need -= amt
        inv.recompute_gold()

    def apply_spells(self):
        lv = bytearray(self.save.player["SpellLevels"])
        clamped = 0
        # Cap follows the level typed on the Character tab, not the level last written.
        for r in range(self.spell_table.rowCount()):
            k = int(self.spell_table.item(r, 0).text())
            w = self.spell_table.cellWidget(r, 2)
            v = w.value()
            cap = caps.spell_cap(self.save.player, k, self.ui_level())
            if v > cap:
                v = cap
                clamped += 1
                w.setValue(v)
            lv[k] = v
        self.save.player["SpellLevels"] = bytes(lv)
        # a spell level only works if the spell is also learned (AvailableSpellMask bit)
        p = self.save.player
        p["AvailableSpellMask"], p["AvailableSpellMask_64_128"] = caps.learned_masks(p, lv)
        self.update_caps()
        self._remember(spells=self._spell_state())
        self.mark_dirty(); self.statusBar().showMessage(("%d spell(s) lowered to the game cap. " % clamped if clamped else "")
                                                        + "Spell levels applied. " + UNSAVED_MSG)

    def apply_perks(self):
        p = self.save.player
        perk = bytearray(p["perk"])
        for r in range(self.perk_table.rowCount()):
            k = int(self.perk_table.item(r, 0).text())
            w = self.perk_table.cellWidget(r, 2)
            cap = caps.perk_cap(p, k)[0]
            v = w.value()
            if cap is not None and v > cap:
                v = cap
                w.setValue(v)
            perk[k] = v
        p["perk"] = bytes(perk)
        p["traits"] = bytes(cb.currentData() for cb in self.trait_boxes)
        self.update_caps()
        self._remember(perks=self._perk_state(), traits=self._trait_state())
        self.mark_dirty(); self.statusBar().showMessage("Perks/traits applied. " + UNSAVED_MSG)

    def after_item_change(self):
        Inventory(self.save.player).recompute_gold()
        self.mark_dirty(); self.refresh_all()

    def _editor_tab(self, index):
        w = self.tabs.widget(index)
        if w is None or getattr(self, "browser", None) is None:
            return
        if w is self.browser:
            self.browser.ensure_ready()
            self.browser.ensure_icons()
        elif w in self.lists.values():
            self.browser.ensure_icons()

    def on_icons(self, msg):
        clear_icon_cache()
        if self.save:
            for kind in ("equip", "inv", "belt", "stash"):
                self.lists[kind].refresh()
            self.browser.refresh_icons()
        self.statusBar().showMessage(msg or "Item icons cached on this PC.")

    def closeEvent(self, ev):
        if not self.confirm_discard("quit"):
            ev.ignore(); return
        if self.finder.worker and self.finder.worker.isRunning():
            self.finder.worker.stop(); self.finder.worker.wait(3000)
        if getattr(self, "browser", None) is not None:
            self.browser.shutdown_icons()
        ev.accept()


def apply_theme(app):
    """Dark Diablo-style theme from theme.qss (pure Qt stylesheet, no extra deps)."""
    app.setStyle("Fusion")
    qss = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme.qss")
    try:
        with open(qss, encoding="utf-8") as f:
            qss_text = f.read()
    except OSError:
        qss_text = ""
    try:
        from .brand import shell_qss
        qss_text += shell_qss()
    except Exception:
        pass
    app.setStyleSheet(qss_text)


def run(argv=None):
    app = QApplication(argv or sys.argv)
    apply_theme(app)
    w = MainWindow(); w.show()
    args = (argv or sys.argv)[1:]
    if args:
        w.open_path(args[0])
    else:
        w.finder.start_scan()  # find characters on startup
    return app.exec()
