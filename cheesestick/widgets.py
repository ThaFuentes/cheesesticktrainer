"""Visual widgets: grouped base-item picker, paperdoll, cell grids, header bar."""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon
from .brand import DEDICATION, pixmap as cheesestick_pixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTreeWidget,
                               QTreeWidgetItem, QLabel, QSpinBox, QDialogButtonBox, QWidget, QPushButton,
                               QGridLayout, QFrame, QCheckBox, QStyledItemDelegate, QStyle, QStyleOptionViewItem)
from th4save.rules import SLOTS, allowed, category
from th4save.items import MAX_GOLD_IN_CELL, GOLD_BASE
from .data import BASE_ITEMS, UNIQUES, default_dur, base_name, is_set_unique
from .iteminfo import describe_base, describe_item, item_name, magic_level, unique_lines
from .icons import cached_icon
from . import catalog

CELL = 30            # px per inventory cell in the visual grids
DOLL_SCALE = 1.35    # scale of the 320-px in-game character panel coordinates

QUALITY_COLORS = {0: "#f0ece4", 1: "#6f8cff", 2: "#d9a93c", 3: "#3fbf5f"}  # normal, magic, unique, set
UNIQUE_GOLD = "#d9a93c"
SET_GREEN = "#3fbf5f"
PLAIN_INK = "#8d8278"
RARE_INK = "#e07070"


def _brush_color(value):
    if isinstance(value, QBrush):
        return value.color()
    if isinstance(value, QColor):
        return value
    return None


class MarkedTreeDelegate(QStyledItemDelegate):
    """Draw each cell in the item's own color.

    theme.qss sets QWidget color, and Qt then ignores QTreeWidgetItem foreground.
    Unique and plain rows would all render the same beige without this.
    """

    def paint(self, painter, option, index):
        fg = _brush_color(index.data(Qt.ForegroundRole))
        bg = _brush_color(index.data(Qt.BackgroundRole))
        if fg is None and bg is None:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        painter.save()
        selected = bool(opt.state & QStyle.State_Selected)
        if selected:
            painter.fillRect(opt.rect, QColor("#5a1414"))
        elif bg is not None:
            painter.fillRect(opt.rect, bg)
        else:
            painter.fillRect(opt.rect, opt.palette.base())
        painter.setFont(opt.font)
        painter.setPen(QColor("#ffe7a8") if selected and fg is None else (fg or QColor("#e6ddd0")))
        text = index.data(Qt.DisplayRole)
        if text:
            painter.drawText(opt.rect.adjusted(6, 0, -4, 0), int(Qt.AlignVCenter | Qt.AlignLeft), str(text))
        painter.restore()


def quality_of(item):
    """magicLevelAndIdentified = (MagicLevel << 1) | Identified  (msg.cpp / Item.cpp RecreateItem)."""
    ml = magic_level(item)
    if item["uniqIndex"] and ml == 0:
        ml = 2
    return ml if ml in QUALITY_COLORS else 0


def quality_color(item):
    return QColor(QUALITY_COLORS[quality_of(item)])


def spin(lo, hi, val=0):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(max(lo, min(hi, val))); return s


class BaseItemPicker(QDialog):
    """Base items grouped by category, filtered to what the target slot accepts."""

    def __init__(self, parent=None, container="inv", slot=None, show_size=True, title=None):
        super().__init__(parent)
        self.container, self.slot = container, slot
        where = {"equip": "slot: %s" % (SLOTS[slot][1] if slot is not None else "?"), "belt": "belt",
                 "inv": "inventory", "stash": "stash"}[container]
        self.setWindowTitle(title or "Add item - %s" % where)
        self.resize(560, 620)
        lay = QVBoxLayout(self); lay.setSpacing(8)
        self.hint = QLabel(""); self.hint.setObjectName("HeaderSub")
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(Qt.RichText)
        self.where = where
        self.search = QLineEdit(placeholderText="Search name, UNIQUE, SET, class, or rarity ...")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Kind", "Who", "Rarity"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 90)
        self.tree.setItemDelegate(MarkedTreeDelegate(self.tree))
        self.tree.setAlternatingRowColors(False)
        self.hide_unusable = QCheckBox("Hide items not usable by this character")
        self.hide_unusable.setChecked(True)
        self.hide_unusable.setToolTip("Class, mode, exile, multiplayer and stat limits for the open character. Stats use the Character tab, including edits that are not applied yet.")
        self.resize(900, 640)
        self.info = QLabel("Pick an item to see its details."); self.info.setWordWrap(True)
        self.info.setObjectName("ItemInfo"); self.info.setTextFormat(Qt.RichText)
        self.info.setAlignment(Qt.AlignTop | Qt.AlignLeft); self.info.setMinimumWidth(300)
        body = QHBoxLayout(); body.addWidget(self.tree, 3); body.addWidget(self.info, 2)
        lay.addWidget(self.hint); lay.addWidget(self.search); lay.addWidget(self.hide_unusable); lay.addLayout(body, 1)
        form = QFormLayout()
        self.w = spin(1, 4, 1); self.h = spin(1, 4, 1)
        self.amount = spin(0, MAX_GOLD_IN_CELL, 0); self.dur = spin(0, 32767, 0)
        self.size_note = QLabel("")
        if show_size:
            row = QHBoxLayout(); row.addWidget(self.w); row.addWidget(QLabel("x")); row.addWidget(self.h); row.addWidget(self.size_note, 1)
            form.addRow("Size (cells)", row)
        form.addRow("Amount / qty", self.amount); form.addRow("Durability", self.dur)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)
        self.valid = [b for b in BASE_ITEMS if allowed(b, container, slot)]
        self.search.textChanged.connect(self.refill)
        self.hide_unusable.toggled.connect(lambda *_: self.refill(self.search.text()))
        self.tree.currentItemChanged.connect(self.on_pick)
        self.tree.itemDoubleClicked.connect(lambda it, _c: it.data(0, Qt.UserRole) is not None and self.accept())
        self.refill("")

    def _character(self):
        return catalog.view_from(getattr(self.parent(), "main", None))

    def refill(self, text):
        self.hint.setText(
            "For the %s. "
            "<b style='color:%s'>UNIQUE</b> is a named unique. "
            "<b style='color:%s'>SET</b> is a named set piece. "
            "<b style='color:%s'>Plain</b> is a normal base. "
            "<b style='color:%s'>Rare</b> means quality level 40 or higher. "
            "Other classes stay hidden while the box below is checked."
            % (self.where, UNIQUE_GOLD, SET_GREEN, PLAIN_INK, RARE_INK))
        t = text.lower().strip()
        self.tree.clear()
        char = self._character()
        view = char if self.hide_unusable.isChecked() else None
        classic = bool(char and char["classic"])
        bold = QFont(); bold.setBold(True)
        groups = {}
        for b in self.valid:
            if view is not None and catalog.limits(b, view):
                continue
            cat = category(b)
            hay = "%d %s %s plain" % (b["baseId"], b["name"], cat)
            if t and t not in hay.lower():
                continue
            groups.setdefault(("plain", cat), []).append(b)
        for uid, u in UNIQUES.items():
            b = BASE_ITEMS[u["baseId"]] if 0 <= u["baseId"] < len(BASE_ITEMS) else None
            if not b or not allowed(b, self.container, self.slot):
                continue
            if view is not None and catalog.limits(b, view):
                continue
            kind = "SET" if is_set_unique(uid) else "UNIQUE"
            who = catalog.who_for(b)
            rare = catalog.rarity_mark(u["qlvl"])
            hay = "%s %s %s %s %s %s" % (kind, u["name"], base_name(u["baseId"]), who, rare, category(b))
            if t and t not in hay.lower():
                continue
            groups.setdefault((kind, category(b)), []).append((uid, u, b, kind, who, rare))

        def group_key(key):
            kind, cat = key
            rank = {"UNIQUE": 0, "SET": 1, "plain": 2}[kind]
            rows = groups[key]
            if kind == "plain":
                power = min(catalog.power_key(b, char) for b in rows)
            else:
                power = min(catalog.power_key(row[2], char) for row in rows)
            return (rank, power, cat.lower())

        for key in sorted(groups, key=group_key):
            kind, cat = key
            g = QTreeWidgetItem([cat])
            if kind == "plain":
                self._paint_group(g, QColor(PLAIN_INK), QColor("#1a1614"), bold=False)
                rows = sorted(groups[key], key=lambda b: catalog.power_key(b, char))
                for b in rows:
                    who = catalog.who_for(b)
                    it = QTreeWidgetItem([b["name"], "Plain", who, "—"])
                    it.setData(0, Qt.UserRole, b["baseId"])
                    it.setData(0, Qt.UserRole + 1, None)
                    it.setForeground(1, QColor(PLAIN_INK))
                    tip = describe_base(b, view=char, classic=classic)
                    for col in range(4):
                        it.setToolTip(col, tip)
                    g.addChild(it)
                g.setText(0, "Plain — %s  (%d)" % (cat, g.childCount()))
            else:
                color = QColor(SET_GREEN if kind == "SET" else UNIQUE_GOLD)
                band = QColor("#14281c" if kind == "SET" else "#2a2210")
                self._paint_group(g, color, band, bold=True)
                rows = sorted(groups[key], key=lambda row: (-int(row[1]["qlvl"]), row[1]["name"].lower()))
                for uid, u, b, tag, who, rare in rows:
                    it = QTreeWidgetItem(["%s  %s" % (tag, u["name"]), tag, who, rare])
                    it.setData(0, Qt.UserRole, b["baseId"])
                    it.setData(0, Qt.UserRole + 1, uid)
                    it.setFont(0, bold)
                    it.setFont(1, bold)
                    it.setForeground(0, color)
                    it.setForeground(1, color)
                    if rare.startswith("Rare"):
                        it.setForeground(3, QColor(RARE_INK))
                    tip = "%s\n%s · %s · %s\n%s" % (u["name"], tag, who, rare, "\n".join(unique_lines(uid, header=False)))
                    for col in range(4):
                        it.setToolTip(col, tip)
                    g.addChild(it)
                g.setText(0, "%s — %s  (%d)" % (kind, cat, g.childCount()))
            self.tree.addTopLevelItem(g)
            # setExpanded before the row is in the tree is ignored, so the Head list stayed shut.
            if kind == "plain":
                named = any(k[0] != "plain" for k in groups)
                if t or not named or g.childCount() <= 12:
                    self.tree.expandItem(g)
            else:
                self.tree.expandItem(g)

    def _paint_group(self, group, ink, band, bold):
        font = QFont()
        font.setBold(bold)
        for col in range(4):
            group.setForeground(col, ink)
            group.setBackground(col, band)
            if bold:
                group.setFont(col, font)

    def on_pick(self, it, _prev=None):
        if it is None or it.data(0, Qt.UserRole) is None:
            return
        uid = it.data(0, Qt.UserRole + 1)
        if uid is not None:
            self._show_unique(int(uid))
            return
        b = BASE_ITEMS[it.data(0, Qt.UserRole)]
        char = self._character()
        self.info.setText(describe_base(b, view=char, classic=bool(char and char["classic"])))
        if b.get("w"):
            self.w.setValue(b["w"]); self.h.setValue(b["h"]); self.size_note.setText("from game table")
        else:
            self.size_note.setText("unknown - match the in-game size")
        self.dur.setValue(default_dur(b["baseId"]))
        self.amount.setValue(1000 if b["baseId"] == GOLD_BASE else 0)

    def _show_unique(self, uid):
        u = UNIQUES[uid]
        b = BASE_ITEMS[u["baseId"]]
        char = self._character()
        kind = "SET" if is_set_unique(uid) else "UNIQUE"
        who = catalog.who_for(b)
        lines = ["<b style='color:%s'>%s  %s</b>" % (SET_GREEN if kind == "SET" else UNIQUE_GOLD, kind, u["name"]),
                 "%s · %s · %s" % (kind, who, catalog.rarity_mark(u["qlvl"])),
                 "Base: %s" % base_name(u["baseId"])]
        reasons = catalog.limits(b, char) if char else []
        if reasons:
            lines.append("This character: " + "; ".join(reasons))
        lines += unique_lines(uid, header=False)
        self.info.setText("<br>".join(lines))
        if b.get("w"):
            self.w.setValue(b["w"]); self.h.setValue(b["h"]); self.size_note.setText("from game table")
        else:
            self.size_note.setText("unknown - match the in-game size")
        self.dur.setValue(default_dur(b["baseId"]))
        self.amount.setValue(0)

    def selected(self):
        it = self.tree.currentItem()
        return None if it is None else it.data(0, Qt.UserRole)

    def selected_unique(self):
        it = self.tree.currentItem()
        if it is None:
            return None
        uid = it.data(0, Qt.UserRole + 1)
        return None if uid is None else int(uid)

    def select_id(self, base_id):  # for tests
        self.search.blockSignals(True)
        self.search.setText("")
        self.search.blockSignals(False)
        self.refill("")
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                if g.child(j).data(0, Qt.UserRole) == base_id and g.child(j).data(0, Qt.UserRole + 1) is None:
                    self.tree.setCurrentItem(g.child(j)); return True
        return False

    def select_unique(self, uid):  # for tests and the add flow
        from .data import UNIQUES as _U
        name = _U[int(uid)]["name"]
        self.search.blockSignals(True)
        self.search.setText(name)
        self.search.blockSignals(False)
        self.refill(name)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                if g.child(j).data(0, Qt.UserRole + 1) == int(uid):
                    self.tree.setCurrentItem(g.child(j)); return True
        return False


def _slot_button(text=""):
    b = QPushButton(text); b.setProperty("slot", True); b.setCursor(Qt.PointingHandCursor)
    return b


def _restyle(w):
    w.style().unpolish(w); w.style().polish(w)


def _set_item_look(btn, item, label, slot="", view=None, classic=False):
    filled = item is not None and not item.empty
    btn.setProperty("filled", filled)
    btn.setIcon(QIcon())
    if filled:
        b = BASE_ITEMS[item["baseItemIndex"]] if 0 <= item["baseItemIndex"] < len(BASE_ITEMS) else None
        name = item_name(item)
        btn.setText(name)
        pic = cached_icon(b, classic) if b else None
        if pic is not None:
            btn.setIcon(pic)
            btn.setIconSize(QSize(28, 28))
        btn.setToolTip(describe_item(item, slot=slot or label, view=view, classic=classic))
        btn.setStyleSheet("color: %s;" % QUALITY_COLORS[quality_of(item)])
    else:
        btn.setText(label)
        btn.setToolTip("%s (empty) - click to add" % (slot or label))
        btn.setStyleSheet("")
    _restyle(btn)


SHORT = {"Left ring": "Ring L", "Right ring": "Ring R", "Amulet": "Amu", "Amulet 2": "Amu 2",
         "Left ring 2": "L2", "Left ring 3": "L3", "Left ring 4": "L4",
         "Right ring 2": "R2", "Right ring 3": "R3", "Right ring 4": "R4"}


class Paperdoll(QFrame):
    """Equipped slots laid out like the in-game character panel (BaseSlots coordinates)."""
    slot_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Paperdoll")
        self.setStyleSheet("#Paperdoll { background: qradialgradient(cx:0.5, cy:0.45, radius:0.8, stop:0 #2a1416, stop:1 #0d0a0b);"
                           " border: 1px solid #5a4630; border-radius: 12px; }")
        self.setFixedSize(int(320 * DOLL_SCALE) + 16, int(215 * DOLL_SCALE) + 16)
        self.buttons = []
        for idx, name, x, y, w, h, _ in SLOTS:
            b = _slot_button(name); b.setParent(self)
            b.setGeometry(int(x * DOLL_SCALE) + 8, int(y * DOLL_SCALE) + 8,
                          int(w * 28 * DOLL_SCALE) - 3, int(h * 28 * DOLL_SCALE) - 3)
            b.clicked.connect(lambda _=False, i=idx: self.slot_clicked.emit(i))
            self.buttons.append(b)

    def update_items(self, items, selected=None, view=None, classic=False):
        for (idx, name, *_), b in zip(SLOTS, self.buttons):
            _set_item_look(b, items[idx], SHORT.get(name, name), slot=name, view=view, classic=classic)
            if not b.property("filled"):
                b.setToolTip("%s (empty) - click to add" % name)
            if b.property("filled") and name in SHORT:  # 1x1 boxes: abbreviate item names
                b.setText(b.text()[:6] + "…" if len(b.text()) > 7 else b.text())
            b.setProperty("selected", idx == selected); _restyle(b)


class CellGrid(QFrame):
    """Clickable grid (inventory 10x7) showing which item covers each cell."""
    cell_clicked = Signal(int)

    def __init__(self, cols, rows, parent=None):
        super().__init__(parent)
        self.cols, self.rows = cols, rows
        lay = QGridLayout(self); lay.setSpacing(2); lay.setContentsMargins(6, 6, 6, 6)
        self.buttons = []
        for i in range(cols * rows):
            b = _slot_button(""); b.setFixedSize(CELL * 2, CELL)
            b.clicked.connect(lambda _=False, c=i: self.cell_clicked.emit(c))
            lay.addWidget(b, i // cols, i % cols); self.buttons.append(b)

    def update_grid(self, grid, items, selected=None, view=None, classic=False):
        for i, b in enumerate(self.buttons):
            v = grid[i] if i < len(grid) else 0
            idx = abs(v) - 1 if v else None
            it = items[idx] if idx is not None and idx < len(items) else None
            _set_item_look(b, it, "", view=view, classic=classic)
            if it is not None and v < 0:
                b.setText("")  # name only on the anchor cell
            b.setProperty("selected", idx is not None and idx == selected); _restyle(b)


class BeltBar(QFrame):
    slot_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setSpacing(4)
        self.buttons = []
        for i in range(8):
            b = _slot_button(str(i + 1)); b.setFixedSize(CELL * 3, CELL * 2)
            b.clicked.connect(lambda _=False, c=i: self.slot_clicked.emit(c))
            lay.addWidget(b); self.buttons.append(b)
        lay.addStretch()

    def update_items(self, items, selected=None, view=None, classic=False):
        for i, b in enumerate(self.buttons):
            _set_item_look(b, items[i], str(i + 1), slot="Belt %d" % (i + 1), view=view, classic=classic)
            b.setProperty("selected", i == selected); _restyle(b)


class HeaderBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeaderBar"); self.setFixedHeight(76)
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 6, 18, 6)
        self.mark = QLabel(); self.mark.setObjectName("CheeseMark")
        pic = cheesestick_pixmap(60)
        if not pic.isNull():
            self.mark.setPixmap(pic)
        self.mark.setToolTip(DEDICATION)
        self.name = QLabel("CheeseStick"); self.name.setObjectName("HeaderName")
        self.name.setToolTip(DEDICATION)
        self.sub = QLabel("Open or find a character"); self.sub.setObjectName("HeaderSub")
        lay.addWidget(self.mark); lay.addSpacing(10); lay.addWidget(self.name); lay.addSpacing(18); lay.addWidget(self.sub); lay.addStretch()
        self.dirty = QLabel("● UNSAVED CHANGES"); self.dirty.setObjectName("HeaderDirty"); self.dirty.setVisible(False)
        self.save_btn = QPushButton("💾  Save  (Ctrl+S)"); self.save_btn.setObjectName("Primary"); self.save_btn.setEnabled(False)
        self.save_btn.setToolTip("Write the save file (verified, with a timestamped backup)")
        lay.addWidget(self.dirty); lay.addSpacing(10); lay.addWidget(self.save_btn); lay.addSpacing(14)
        self.badge = QLabel("The Hell 4 · v0.773"); self.badge.setObjectName("HeaderSub")
        lay.addWidget(self.badge)

    def set_dirty(self, dirty):
        self.dirty.setVisible(dirty); self.save_btn.setEnabled(dirty)

    def set_character(self, name, cls, level, extra=""):
        self.name.setText("CheeseStick")
        self.sub.setText("%s  ·  %s  ·  Level %d%s" % (name, cls, level, ("  ·  " + extra) if extra else ""))
