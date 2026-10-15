"""Presets tab: saved item rolls and whole loadouts.

Applying a preset only edits the open character in memory and marks it unsaved.
File > Save still does the unpair prompt, the backup and the changed-on-disk check."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QLabel,
                               QGroupBox, QFileDialog, QInputDialog, QMessageBox, QPlainTextEdit,
                               QDialog, QFormLayout, QDialogButtonBox)

from th4save import presets as P
from th4save.rules import SLOT_NAMES
from .data import BASE_ITEMS
from . import catalog

AUTO = "Auto: first empty slot that fits"
INV = "Inventory (selected empty cell, else first free space)"
BELT = "Belt (first empty slot)"
SLOT_FILTERS = ["All", "Loadout", "Head", "Ring", "Amulet", "Hand", "Body", "Belt", "Gloves", "Boots",
                "Belt bar", "Other"]
# limits() reasons that mean the item cannot be worn at all by this class or mode.
HARD_LIMITS = ("Not for this class", "Classic only", "Not usable in classic", "Exiles cannot use this",
               "Class restriction could not be read")


class NameDialog(QDialog):
    def __init__(self, parent, title, name="", notes=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        f = QFormLayout(self)
        self.name = QLineEdit(name); self.name.setPlaceholderText("e.g. Angelwrath res roll")
        self.notes = QPlainTextEdit(notes); self.notes.setFixedHeight(80)
        f.addRow("Name", self.name); f.addRow("Notes", self.notes)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); f.addRow(bb)


class PresetsPanel(QWidget):
    COLS = ["Name", "Item", "Slot", "Category", "Notes", "Saved"]

    def __init__(self, main, store=None):
        super().__init__()
        self.main = main
        self.store = store
        v = QVBoxLayout(self); v.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search name, notes, item...")
        self.search.textChanged.connect(self.refresh)
        self.slot_filter = QComboBox(); self.slot_filter.addItems(SLOT_FILTERS)
        self.slot_filter.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.search, 1); top.addWidget(QLabel("Slot:")); top.addWidget(self.slot_filter)
        v.addLayout(top)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(lambda *_: self.show_detail())
        v.addWidget(self.table, 1)
        self.detail = QLabel(""); self.detail.setWordWrap(True); self.detail.setObjectName("HeaderSub")
        v.addWidget(self.detail)

        box = QGroupBox("Apply to the open character (marks it unsaved; Save writes the file)")
        b = QVBoxLayout(box)
        row = QHBoxLayout()
        self.target = QComboBox(); self.target.addItems([AUTO] + SLOT_NAMES + [INV, BELT])
        row.addWidget(QLabel("Target:")); row.addWidget(self.target, 1)
        self.apply_btn = QPushButton("Apply preset to selected slot or inventory cell")
        self.apply_btn.setObjectName("Primary"); self.apply_btn.clicked.connect(self.apply_selected)
        self.stash_btn = QPushButton("Add to stash"); self.stash_btn.setObjectName("ShellButton"); self.stash_btn.clicked.connect(self.add_to_stash)
        row.addWidget(self.apply_btn); row.addWidget(self.stash_btn)
        b.addLayout(row)
        row2 = QHBoxLayout()
        self.loadout_save_btn = QPushButton("Save whole loadout"); self.loadout_save_btn.setObjectName("ShellButton"); self.loadout_save_btn.clicked.connect(self.save_loadout)
        self.loadout_apply_btn = QPushButton("Apply loadout"); self.loadout_apply_btn.clicked.connect(self.apply_loadout)
        row2.addWidget(self.loadout_save_btn); row2.addWidget(self.loadout_apply_btn); row2.addStretch()
        b.addLayout(row2)
        v.addWidget(box)
        bot = QHBoxLayout()
        for text, fn in (("Rename / notes...", self.rename), ("Delete", self.delete),
                         ("Export...", self.export), ("Import...", self.import_)):
            btn = QPushButton(text); btn.clicked.connect(fn); bot.addWidget(btn)
        bot.addStretch()
        self.path_label = QLabel(""); self.path_label.setObjectName("HeaderSub"); bot.addWidget(self.path_label)
        v.addLayout(bot)
        self.refresh()

    # -- store
    def ensure_store(self):
        if self.store is None:
            try:
                self.store = P.PresetStore()
            except Exception as e:
                self.main.warn("Could not read presets file:\n%s" % e)
                self.store = P.PresetStore.__new__(P.PresetStore)
                self.store.path = P.default_path() + ".new"; self.store.presets = []
        return self.store

    def ask_name(self, title, name="", notes=""):
        if self.main.auto_preset_name is not None:          # tests
            return self.main.auto_preset_name
        d = NameDialog(self, title, name, notes)
        if d.exec() != QDialog.Accepted:
            return None
        return d.name.text(), d.notes.toPlainText()

    # -- list
    def refresh(self):
        st = self.ensure_store()
        f = self.slot_filter.currentText()
        rows = st.search(self.search.text(), "" if f == "All" else f)
        self.rows = rows
        self.table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            vals = [p["name"], p.get("label", ""), p.get("slot", ""), p.get("category", ""),
                    p.get("notes", "").replace("\n", " "), p.get("created", "")]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val)); it.setData(Qt.UserRole, p["id"]); self.table.setItem(r, c, it)
        self.path_label.setText(st.path)
        self.show_detail()

    def selected(self):
        r = self.table.currentRow()
        return self.rows[r] if 0 <= r < len(getattr(self, "rows", [])) else None

    def select_id(self, pid):
        for r, p in enumerate(self.rows):
            if p["id"] == pid:
                self.table.setCurrentCell(r, 0); return True
        return False

    def show_detail(self):
        p = self.selected()
        if p is None:
            self.detail.setText("Save an item with ★ Save as preset on the Equipped, Inventory, Belt or Stash tab."); return
        if p["kind"] == "loadout":
            self.detail.setText("Loadout from a %s: %s" % (p.get("class", "?"), ", ".join(
                "%s: %s" % (e.get("slot_name", e["slot"]), e.get("label", "")) for e in p["items"])))
        else:
            it = P.item_from_hex(p["item"])
            self.detail.setText("%s · seed %d · unique %d · quality %d · dur %d/%d · charges %d/%d" % (
                p.get("label", ""), it["seed"], it["uniqIndex"], it["quality"], it["curDurability"],
                it["baseDurability"], it["curCharges"], it["baseCharges"]))

    # -- saving
    def save_item(self, item, where=""):
        if item is None or item.empty:
            return self.main.warn("Select an item first.")
        ans = self.ask_name("Save item preset", P.base_of(item, BASE_ITEMS).get("name", ""))
        if not ans:
            return None
        p = self.ensure_store().add(P.make_item_preset(item, ans[0], ans[1], BASE_ITEMS))
        self.refresh(); self.select_id(p["id"])
        self.main.statusBar().showMessage("Preset '%s' saved to %s" % (p["name"], self.store.path))
        return p

    def save_loadout(self):
        if not self.main.save:
            return self.main.warn("Open a save first.")
        ans = self.ask_name("Save whole loadout", self.main.save.player.name + " loadout")
        if not ans:
            return None
        try:
            p = self.ensure_store().add(P.make_loadout(self.main.save.player, ans[0], ans[1], BASE_ITEMS))
        except ValueError as e:
            return self.main.warn(str(e))
        self.refresh(); self.select_id(p["id"])
        self.main.statusBar().showMessage("Loadout '%s' saved (%s)" % (p["name"], p["label"]))
        return p

    # -- editing
    def rename(self):
        p = self.selected()
        if not p:
            return
        ans = self.ask_name("Rename preset", p["name"], p.get("notes", ""))
        if ans:
            self.store.rename(p["id"], ans[0], ans[1]); self.refresh(); self.select_id(p["id"])

    def delete(self):
        p = self.selected()
        if not p:
            return
        ok = self.main.auto_confirm_delete if self.main.auto_confirm_delete is not None else (
            QMessageBox.question(self, "Delete preset", "Delete '%s'?" % p["name"]) == QMessageBox.Yes)
        if ok:
            self.store.delete(p["id"]); self.refresh()

    def export(self, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Export presets", "cheesestick_presets.json", "JSON (*.json)")
        if path:
            p = self.selected()
            ids = None
            if p and self.main.auto_export_all is None and QMessageBox.question(
                    self, "Export", "Export only '%s'?\n(No exports every preset.)" % p["name"]) == QMessageBox.Yes:
                ids = {p["id"]}
            n = self.ensure_store().export(path, ids)
            self.main.statusBar().showMessage("Exported %d preset(s) to %s" % (n, path))
            return n

    def import_(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Import presets", "", "JSON (*.json)")
        if path:
            try:
                n = self.ensure_store().import_file(path)
            except Exception as e:
                return self.main.warn("Could not import %s:\n%s" % (path, e))
            self.refresh(); self.main.statusBar().showMessage("Imported %d preset(s)" % n)
            return n

    # -- applying
    def _view(self):
        return catalog.view_from(self.main)

    def _warn_limits(self, item):
        b = P.base_of(item, BASE_ITEMS)
        msg = catalog.restriction_message(b, self._view()) if b else ""
        if msg:
            self.main.warn(msg)

    def _item_preset(self):
        if not self.main.save:
            self.main.warn("Open a save first."); return None
        p = self.selected()
        if p is None:
            self.main.warn("Pick a preset first."); return None
        if p["kind"] != "item":
            self.main.warn("That is a loadout. Use Apply loadout."); return None
        return P.item_from_hex(p["item"])

    def apply_selected(self):
        item = self._item_preset()
        if item is None:
            return False
        pl = self.main.save.player
        t = self.target.currentText()
        try:
            if t == INV:
                cell = getattr(self.main.lists["inv"], "last_empty_cell", None)
                P.apply_to_inventory(pl, item, BASE_ITEMS, cell)
                self.main.lists["inv"].last_empty_cell = None
                where = "inventory"
            elif t == BELT:
                slot = next((i for i, x in enumerate(pl["BeltInventory"]) if x.empty), None)
                if slot is None:
                    raise ValueError("the belt is full")
                P.apply_to_belt(pl, item, slot, BASE_ITEMS); where = "belt slot %d" % (slot + 1)
            else:
                if t == AUTO:
                    eq = self.main.lists["equip"]
                    r, cur = eq.current()
                    fits = P.fitting_slots(item, BASE_ITEMS)
                    if not fits:
                        raise ValueError("%s is not wearable; pick Inventory, Belt or Add to stash"
                                         % (P.base_of(item, BASE_ITEMS).get("name") or "This item"))
                    if cur is not None and cur.empty and r in fits:
                        slot = r
                    else:
                        slot = next((s for s in fits if pl["OnBodySlots"][s].empty), None)
                    if slot is None:
                        raise ValueError("every slot this item fits is occupied - remove one first")
                else:
                    slot = SLOT_NAMES.index(t)
                P.apply_to_equip(pl, item, slot, BASE_ITEMS); where = SLOT_NAMES[slot]
        except ValueError as e:
            self.main.warn(str(e)); return False
        self._warn_limits(item)
        self.main.after_item_change()
        self.main.statusBar().showMessage("Preset applied to %s. %s" % (where, self.main.unsaved_msg))
        return True

    def add_to_stash(self):
        item = self._item_preset()
        if item is None:
            return False
        tab = self.main.lists["stash"].tab_spin.value() - 1
        try:
            P.apply_to_stash(self.main.save.stash, item, BASE_ITEMS, tab)
        except ValueError as e:
            self.main.warn(str(e)); return False
        self._warn_limits(item)
        self.main.after_item_change()
        self.main.statusBar().showMessage("Preset added to stash tab %d. %s" % (tab + 1, self.main.unsaved_msg))
        return True

    def apply_loadout(self, replace=None):
        if not self.main.save:
            return self.main.warn("Open a save first.")
        p = self.selected()
        if p is None or p["kind"] != "loadout":
            return self.main.warn("Pick a loadout first (Slot filter: Loadout).")
        view = self._view()

        def check(item, slot):
            reasons = [r for r in catalog.limits(P.base_of(item, BASE_ITEMS), view) if r in HARD_LIMITS]
            return "; ".join(reasons)

        if replace is None:
            occupied = any(not self.main.save.player["OnBodySlots"][int(e["slot"])].empty for e in p["items"])
            replace = False
            if occupied:
                ans = self.main.auto_loadout_replace if self.main.auto_loadout_replace is not None else \
                    QMessageBox.question(self, "Apply loadout", "Some of those slots are already filled.\n"
                                         "Replace the worn items? (No keeps them and skips those pieces.)") == QMessageBox.Yes
                replace = bool(ans)
        applied, skipped = P.apply_loadout(self.main.save.player, p, BASE_ITEMS, check=check, replace=replace)
        self.last_loadout_result = (applied, skipped)
        if applied:
            self.main.after_item_change()
        msg = "Applied %d of %d items from '%s'." % (len(applied), len(p["items"]), p["name"])
        if skipped:
            msg += "\n\nSkipped:\n- " + "\n- ".join("%s (%s): %s" % s for s in skipped)
            self.main.warn(msg)
        self.main.statusBar().showMessage(msg.split("\n")[0] + (" " + self.main.unsaved_msg if applied else ""))
        return applied, skipped
