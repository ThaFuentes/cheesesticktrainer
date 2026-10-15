"""Item Browser: every base item, filtered, compared, and checked against the open character."""
import os

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QSpinBox, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QCheckBox, QAbstractItemView,
    QHeaderView, QDialog)

from .data import BASE_ITEMS, default_dur
from . import catalog
from .icons import cached_icon, glyph_for, build_cache, clear_icon_cache
from th4save.items import GOLD_BASE, new_item

BASE_ROLE = Qt.UserRole + 1
WIN = QColor("#1d4a32")
WIN_FG = QColor("#d8ffe8")
COLS = ["Icon", "Name", "Category", "Damage", "Armor", "Durability", "Str", "Mag", "Dex", "Lvl", "Size", "Quality", "Limits", "Rank"]
SLOTS = [
    (None, "Any slot"),
    ("EL_1_ONE_HANDED", "One-handed"), ("EL_2_TWO_HANDED", "Two-handed"),
    ("EL_3_TORSO", "Body"), ("EL_4_HEAD", "Head"), ("EL_5_FINGER", "Ring"),
    ("EL_6_NECK", "Amulet"), ("EL_7_INVENTORY", "Inventory"), ("EL_9_WAIST", "Belt"),
    ("EL_10_HANDS", "Gloves"), ("EL_11_FEET", "Boots"),
]
# (row key, title, higher-is-better). Requirements and size prefer the lower number.
_COMPARE = [
    ("dmg", "Damage", True), ("armor", "Armor", True), ("dur", "Durability", True),
    ("Str", "Strength", False), ("Mag", "Magic", False), ("Dex", "Dexterity", False),
    ("Vit", "Vitality", False), ("Lvl", "Level", False), ("size", "Size", False),
    ("qlvl", "Quality level", None), ("limits", "Limits", None),
]


def _spin(hi, tip):
    s = QSpinBox()
    s.setRange(0, hi)
    s.setSpecialValueText("any")
    s.setToolTip(tip)
    return s


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is None:
            return b is not None
        if b is None:
            return False
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class IconWorker(QThread):
    """Reads CEL frames off DIABDAT.MPQ / TH4data.mor. Never started by unit tests."""
    done = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        self.done.emit(build_cache(lambda: self._stop))


def _compare_value(fact, key):
    if key in ("Str", "Mag", "Dex", "Vit", "Lvl"):
        return fact["req"][key][0], fact["req"][key][1]
    if key == "limits":
        return fact["limits"], None
    if key == "qlvl":
        return (str(fact["qlvl"]) if fact["qlvl"] else ""), fact["qlvl"]
    if key == "size":
        return fact["size_text"], fact["size"]
    return fact["%s_text" % key], fact[key]


class CompareDialog(QDialog):
    def __init__(self, bases, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare items")
        self.resize(780, 520)
        self.bases = list(bases)
        self.same_group = len({catalog.rank_group(b) for b in bases}) == 1
        self.marked = set()
        facts = [catalog.fact_of(b) for b in bases]
        v = QVBoxLayout(self)
        self.table = QTableWidget(len(_COMPARE) + 1, 1 + len(bases))
        self.table.setHorizontalHeaderLabels(["Stat"] + [f["name"] for f in facts])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, (key, title, higher) in enumerate(_COMPARE):
            self.table.setItem(r, 0, QTableWidgetItem(title))
            nums, texts = [], []
            for fact in facts:
                text, num = _compare_value(fact, key)
                texts.append(text)
                nums.append(num)
            present = [n for n in nums if isinstance(n, int)]
            winners = set()
            if self.same_group and higher is True and present and min(present) != max(present):
                winners = {i for i, n in enumerate(nums) if n == max(present)}
            elif self.same_group and higher is False and present and min(present) != max(present):
                winners = {i for i, n in enumerate(nums) if n == min(present)}
            for c, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                if c in winners:
                    cell.setBackground(WIN)
                    cell.setForeground(WIN_FG)
                    self.marked.add((r, c + 1))
                self.table.setItem(r, c + 1, cell)
        rank_row = len(_COMPARE)
        self.table.setItem(rank_row, 0, QTableWidgetItem("Rank in category and slot"))
        for c, b in enumerate(bases):
            rec = catalog.rank_info(b)
            text = "" if rec is None else "%d of %d" % (rec["rank"], rec["total"])
            self.table.setItem(rank_row, c + 1, QTableWidgetItem(text))
        v.addWidget(self.table)
        if self.same_group:
            msg = ("Green is the better base value inside this category and slot. "
                   "Damage, armor and durability prefer higher. Requirements and size prefer lower. "
                   "Rank is max damage, or max armor when the item has no damage, divided by the level requirement. "
                   "A level requirement of 0 counts as 1. Magic bonuses are set by the seed.")
        else:
            msg = ("These items are not the same category and slot, so nothing is marked better. "
                   "Ranking a sword against a ring does not mean much. "
                   "Rank only compares items of the same category and slot.")
        self.note = QLabel(msg)
        self.note.setWordWrap(True)
        self.note.setObjectName("HeaderSub")
        v.addWidget(self.note)


class ItemBrowser(QWidget):
    icons_ready = Signal(str)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self._filled = False
        self._icon_worker = None
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        self.search = QLineEdit(placeholderText="Search name, category or id ...")
        v.addWidget(self.search)
        row = QHBoxLayout()
        self.cat = QComboBox()
        self.slot = QComboBox()
        for loc, label in SLOTS:
            self.slot.addItem(label, loc)
        self.hide_unusable = QCheckBox("Hide items not usable by this character")
        self.hide_unusable.setChecked(True)
        self.hide_unusable.setToolTip("Uses the class, mode, stats and level on the Character tab, including edits that are not applied yet.")
        row.addWidget(self.cat, 1)
        row.addWidget(self.slot, 1)
        row.addWidget(self.hide_unusable)
        v.addLayout(row)
        row2 = QHBoxLayout()
        self.dmg = _spin(9999, "Only items whose highest base damage is at least this. Any means no limit.")
        self.armor = _spin(9999, "Only items whose highest base armor is at least this. Any means no limit.")
        self.dur = _spin(9999, "Only items whose highest base durability is at least this. Any means no limit.")
        self.lvl = _spin(150, "Hide items whose level requirement is above this. Any means no limit.")
        for lab, w in (("Damage ≥", self.dmg), ("Armor ≥", self.armor), ("Durability ≥", self.dur), ("Level req ≤", self.lvl)):
            row2.addWidget(QLabel(lab))
            row2.addWidget(w)
        row2.addStretch(1)
        v.addLayout(row2)
        row3 = QHBoxLayout()
        cmp_b = QPushButton("Compare")
        cmp_b.setToolTip("Select 2 to 4 rows. Better base values are highlighted.")
        cmp_b.clicked.connect(self.compare_selected)
        add_b = QPushButton("Add to inventory")
        add_b.setObjectName("Primary")
        add_b.clicked.connect(self.add_to_inventory)
        self.count_label = QLabel("")
        self.count_label.setObjectName("HeaderSub")
        row3.addWidget(cmp_b)
        row3.addWidget(add_b)
        row3.addWidget(self.count_label, 1)
        v.addLayout(row3)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeaderItem(11).setToolTip("Base quality level. The rolled quality of an owned item is on the Inventory tab.")
        self.table.horizontalHeaderItem(3).setToolTip("Base damage range. Magic bonuses are set by the seed.")
        self.table.horizontalHeaderItem(2).setToolTip(
            "Opens with the weapon types this class is known to use, then armor. "
            "Helms and armor use defense. Weapons use damage. Built-in magic breaks the tie. "
            "Resists, crit, thorns, dread, and ruin are set by the seed.")
        self.table.horizontalHeaderItem(13).setToolTip(
            "Rank inside this category and slot, by max damage or max armor divided by the level requirement. "
            "A level requirement of 0 counts as 1. A sword is not ranked against a ring.")
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setIconSize(QSize(28, 28))
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSortingEnabled(False)
        self._user_sorted = False
        self.table.horizontalHeader().sectionClicked.connect(self._header_clicked)
        v.addWidget(self.table, 1)
        self.note = QLabel("Preferred weapons for this class are listed first. Inside a type, higher defense or damage is first.")
        self.note.setToolTip("Bows for archers, staves for mages and monks, maces for inquisitors, "
                             "melee weapons for warriors, rogues, and savages. "
                             "Helms and armor use defense. Weapons use damage. Built-in magic breaks a tie. "
                             "A sword is not ordered against a helm. "
                             "Resists, crit, thorns, dread, and ruin are still set by the seed. "
                             "Icons are read from your Diablo install the first time you open an item tab and cached on this PC.")
        self.note.setWordWrap(True)
        self.note.setObjectName("HeaderSub")
        v.addWidget(self.note)
        for w in (self.search, self.cat, self.slot, self.hide_unusable, self.dmg, self.armor, self.dur, self.lvl):
            sig = w.textChanged if isinstance(w, QLineEdit) else (w.toggled if isinstance(w, QCheckBox) else
                                                                  (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged))
            sig.connect(lambda *_: self.refilter())

    def ensure_ready(self):
        if self._filled:
            self.refilter()
            return
        named = [b for b in BASE_ITEMS if b.get("name")]
        cats = sorted({catalog.facts()[b["baseId"]]["cat"] for b in named})
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem("All categories", None)
        for c in cats:
            self.cat.addItem(c, c)
        self.cat.blockSignals(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(named))
        classic = self._classic()
        for r, b in enumerate(named):
            self._fill_row(r, b, classic)
        self.table.setSortingEnabled(True)
        self._filled = True
        self.refilter()

    def ensure_icons(self):
        if os.environ.get("CHEESESTICK_NO_ICONS"):
            return
        if self._icon_worker is not None:
            return
        self._icon_worker = IconWorker()
        self._icon_worker.done.connect(self._icons_done)
        self._icon_worker.start()

    def shutdown_icons(self):
        w = self._icon_worker
        if w is not None and w.isRunning():
            w.stop()
            w.wait(5000)

    def _icons_done(self, msg):
        clear_icon_cache()
        self.icons_ready.emit(msg)

    def _classic(self):
        view = catalog.view_from(self.main)
        return bool(view and view["classic"])

    def _fill_row(self, r, b, classic):
        fact = catalog.facts()[b["baseId"]]
        icon = cached_icon(b, classic)
        cells = [
            ("", fact["name"].lower(), glyph_for(b) if icon is None else ""),
            (fact["name"], fact["name"].lower(), fact["name"]),
            (fact["cat"], fact["cat"].lower(), fact["cat"]),
            (fact["dmg_text"], fact["dmg"], fact["dmg_text"]),
            (fact["armor_text"], fact["armor"], fact["armor_text"]),
            (fact["dur_text"], fact["dur"], fact["dur_text"]),
            (fact["req"]["Str"][0], fact["req"]["Str"][1], fact["req"]["Str"][0]),
            (fact["req"]["Mag"][0], fact["req"]["Mag"][1], fact["req"]["Mag"][0]),
            (fact["req"]["Dex"][0], fact["req"]["Dex"][1], fact["req"]["Dex"][0]),
            (fact["req"]["Lvl"][0], fact["req"]["Lvl"][1], fact["req"]["Lvl"][0]),
            (fact["size_text"], fact["size"] if fact["size"] is not None else 999, fact["size_text"]),
            (str(fact["qlvl"]) if fact["qlvl"] else "", fact["qlvl"], str(fact["qlvl"]) if fact["qlvl"] else ""),
            (fact["limits"], fact["limits"].lower(), fact["limits"]),
            self._rank_cell(b),
        ]
        from .iteminfo import describe_base
        tip = describe_base(b, classic=classic)
        for c, (sort_text, sort_key, shown) in enumerate(cells):
            item = SortItem(shown)
            item.setData(Qt.UserRole, sort_key)
            item.setData(BASE_ROLE, b["baseId"])
            if c == 0 and icon is not None:
                item.setIcon(icon)
            item.setToolTip(tip)
            self.table.setItem(r, c, item)

    def _rank_cell(self, b):
        rec = catalog.rank_info(b)
        if rec is None:
            return ("", 10 ** 9, "")
        shown = "%d/%d" % (rec["rank"], rec["total"])
        return (shown, rec["rank"], shown)

    def refresh_icons(self):
        if not self._filled:
            return
        from .iteminfo import describe_base
        classic = self._classic()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is None:
                continue
            b = BASE_ITEMS[item.data(BASE_ROLE)]
            tip = describe_base(b, classic=classic)
            icon = cached_icon(b, classic)
            if icon is not None:
                item.setIcon(icon)
                item.setText("")
            for c in range(self.table.columnCount()):
                cell = self.table.item(r, c)
                if cell is not None:
                    cell.setToolTip(tip)

    def refilter(self):
        if not self._filled:
            return
        view = catalog.view_from(self.main)
        text = self.search.text().lower().strip()
        cat = self.cat.currentData()
        slot = self.slot.currentData()
        shown = 0
        total = self.table.rowCount()
        for r in range(total):
            name = self.table.item(r, 1)
            bid = name.data(BASE_ROLE)
            b = BASE_ITEMS[bid]
            fact = catalog.facts()[bid]
            ok = True
            if text and text not in ("%d %s %s %s" % (bid, fact["name"], fact["cat"], b.get("name2") or "")).lower():
                ok = False
            if ok and cat and fact["cat"] != cat:
                ok = False
            if ok and slot and b.get("equipLoc") != slot:
                ok = False
            if ok and self.dmg.value() and fact["dmg"] < self.dmg.value():
                ok = False
            if ok and self.armor.value() and fact["armor"] < self.armor.value():
                ok = False
            if ok and self.dur.value() and fact["dur"] < self.dur.value():
                ok = False
            if ok and self.lvl.value() and fact["req"]["Lvl"][1] > self.lvl.value():
                ok = False
            if ok and self.hide_unusable.isChecked() and limits_hit(b, view):
                ok = False
            self.table.setRowHidden(r, not ok)
            shown += ok
        self._write_fit_keys(view)
        if not self._user_sorted:
            self._sort_for_character()
        self.count_label.setText("Showing %d of %d" % (shown, total))

    def _header_clicked(self, index):
        # Category is the "best of this type" order. Any other header is the user's own sort.
        self._user_sorted = index != 2

    def _write_fit_keys(self, view):
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 1)
            cell = self.table.item(r, 2)
            if name is None or cell is None:
                continue
            b = BASE_ITEMS[name.data(BASE_ROLE)]
            cell.setData(Qt.UserRole, catalog.better_sort_key(b, view))
        if sorting:
            self.table.setSortingEnabled(True)

    def _sort_for_character(self):
        self.table.sortItems(2, Qt.AscendingOrder)
        self.table.horizontalHeader().setSortIndicator(2, Qt.AscendingOrder)

    def is_visible_id(self, base_id):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item is not None and item.data(BASE_ROLE) == base_id:
                return not self.table.isRowHidden(r)
        return False

    def visible_ids(self):
        out = []
        for r in range(self.table.rowCount()):
            if self.table.isRowHidden(r):
                continue
            item = self.table.item(r, 1)
            if item is not None:
                out.append(item.data(BASE_ROLE))
        return out

    def selected_ids(self):
        out, seen = [], set()
        for idx in self.table.selectionModel().selectedRows():
            if self.table.isRowHidden(idx.row()):
                continue
            item = self.table.item(idx.row(), 1)
            bid = item.data(BASE_ROLE) if item is not None else None
            if bid is not None and bid not in seen:
                seen.add(bid)
                out.append(bid)
        return out

    def compare_selected(self):
        ids = self.selected_ids()
        if not 2 <= len(ids) <= 4:
            return self.main.warn("Select 2 to 4 items to compare.")
        dlg = CompareDialog([BASE_ITEMS[i] for i in ids], self)
        if getattr(self.main, "auto_compare", None) == "skip":
            self._compare = dlg
            return dlg
        dlg.exec()
        return dlg

    def add_to_inventory(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            return self.main.warn("Select one item to add to inventory.")
        if not self.main.save:
            return self.main.warn("Open a character first.")
        b = BASE_ITEMS[ids[0]]
        w, h = b.get("w") or 1, b.get("h") or 1
        item = new_item(b["baseId"], self.main.save.player["version"], dur=default_dur(b["baseId"]),
                        amount=1000 if b["baseId"] == GOLD_BASE else 0)
        try:
            self.main.lists["inv"].place(item, w, h)
        except ValueError as e:
            return self.main.warn(str(e))
        msg = catalog.restriction_message(b, catalog.view_from(self.main))
        if msg:
            self.main.warn(msg)
        self.main.after_item_change()


def limits_hit(b, view):
    return bool(catalog.limits(b, view))
