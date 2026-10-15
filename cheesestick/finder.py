"""'Find Characters' panel: background scan (QThread) + results table."""
import os, subprocess, sys, time
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar,
                               QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QMenu,
                               QFileDialog, QMessageBox)
from th4save import scan
from .brand import DEDICATION, pixmap as cheesestick_pixmap
from . import paths_config


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(list)

    def __init__(self, roots=None, extra=None, known=None, sources=None):
        super().__init__()
        self.roots, self.extra, self.known, self._stop = roots, extra, known, False
        self.sources = sources

    def stop(self):
        self._stop = True

    def run(self):
        try:
            res = scan.scan(self.roots, self.extra,
                            progress=lambda i, n, r: self.progress.emit(i, n, r),
                            cancel=lambda: self._stop, known=self.known,
                            sources=self.sources)
        except Exception as e:  # never kill the GUI
            res = [scan.SaveEntry(path="", file="(scan failed)", slot="", error=str(e))]
        self.done.emit(res)


class FinderPanel(QWidget):
    COLS = ["Slot", "File", "Character", "Class", "Level", "Gold", "Modified", "Source", "Path"]
    open_requested = Signal(str)

    def __init__(self, parent=None, roots=None, settings_file=None):
        super().__init__(parent)
        self.roots, self.settings_file = roots, settings_file
        self.known = None  # None -> scan.DEFAULT_KNOWN
        self.worker = None
        self.entries = []
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_scan = QPushButton("Find Characters"); self.btn_scan.clicked.connect(self.start_scan)
        self.btn_add = QPushButton("Add folder..."); self.btn_add.clicked.connect(self.add_folder_dialog)
        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.status = QLabel("")
        for w in (self.btn_scan, self.btn_add, self.progress):
            top.addWidget(w)
        top.addWidget(self.status, 1)
        v.addLayout(top)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.table)
        foot = QHBoxLayout()
        mark = QLabel()
        pic = cheesestick_pixmap(28)
        if not pic.isNull():
            mark.setPixmap(pic)
        mark.setToolTip(DEDICATION)
        foot.addWidget(mark)
        foot.addWidget(QLabel("Double-click a character to edit it. Right-click for 'Show in folder'. .bak backups are hidden."))
        foot.addStretch()
        v.addLayout(foot)

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        extra = scan.load_settings(self.settings_file)["folders"]
        try:  # configured save folders; skipped when a caller pins known (tests)
            sources = paths_config.known_sources() if self.known is None else []
        except Exception:
            sources = []
        self.worker = ScanWorker(self.roots, extra, self.known, sources)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.btn_scan.setEnabled(False)
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        self.status.setText("Scanning...")
        self.worker.start()

    def _on_progress(self, i, n, root):
        self.progress.setRange(0, max(1, n)); self.progress.setValue(i)
        self.status.setText("Scanning %s" % root)

    def _on_done(self, entries):
        self.entries = entries
        self.btn_scan.setEnabled(True); self.progress.setVisible(False)
        bad = sum(not e.ok for e in entries)
        try:
            order = paths_config.group_labels()
        except Exception:
            order = [paths_config.OTHER]
        groups = {}
        for i, e in enumerate(entries):
            groups.setdefault(e.source or paths_config.OTHER, []).append(i)
        names = [g for g in order if g in groups] + sorted(g for g in groups if g not in order)
        headers = len(names) > 1  # a single group needs no header rows
        self.row_map = []
        for g in names:
            if headers:
                self.row_map.append(("header", g, len(groups[g])))
            self.row_map += [("entry", i) for i in groups[g]]
        self.status.setText("Found %d save(s) in %d group(s)%s." % (len(entries), len(names),
                            (", %d unreadable" % bad) if bad else ""))
        self.table.clearSpans()
        self.table.setRowCount(len(self.row_map))
        bold = QFont(); bold.setBold(True)
        for r, rm in enumerate(self.row_map):
            if rm[0] == "header":
                it = QTableWidgetItem("%s  (%d)" % (rm[1], rm[2])); it.setFont(bold)
                it.setBackground(QColor(60, 60, 70)); it.setForeground(QColor(255, 210, 120))
                for c in range(len(self.COLS)):
                    self.table.setItem(r, c, it if c == 0 else QTableWidgetItem(""))
                self.table.setSpan(r, 0, 1, len(self.COLS))
                continue
            e = entries[rm[1]]
            vals = [e.slot, e.file, e.name if e.ok else "UNREADABLE", e.cls, e.level if e.ok else "",
                    e.gold if e.ok else "", time.strftime("%Y-%m-%d %H:%M", time.localtime(e.mtime)) if e.mtime else "",
                    e.source, e.path]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if not e.ok:
                    it.setForeground(Qt.red); it.setToolTip(e.error)
                elif paths_config.is_real_game(e.path):
                    it.setForeground(Qt.gray); it.setToolTip("Real game save: listed read-only, not opened for editing")
                self.table.setItem(r, c, it)
    def add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Add a TH4 or save folder")
        if d:
            self.add_folder(d)

    def add_folder(self, d):
        scan.add_folder(d, self.settings_file)
        self.start_scan()

    def _entry_at(self, row):
        rm = getattr(self, "row_map", None)
        if rm is None:
            return self.entries[row] if 0 <= row < len(self.entries) else None
        if 0 <= row < len(rm) and rm[row][0] == "entry":
            return self.entries[rm[row][1]]
        return None

    def _open_row(self, row, _col=0):
        e = self._entry_at(row)
        if e is not None and e.ok:
            if paths_config.is_real_game(e.path):
                self.status.setText("Real game saves are read-only here. Copy the hero into TH4_dev to edit it.")
                return
            self.open_requested.emit(e.path)

    def _menu(self, pos):
        e = self._entry_at(self.table.rowAt(pos.y()))
        if e is None:
            return
        real = paths_config.is_real_game(e.path)
        m = QMenu(self)
        a_open = m.addAction("Open in editor"); a_open.setEnabled(e.ok and not real)
        a_show = m.addAction("Show in folder")
        m.addSeparator()
        a_del = m.addAction("Delete save (Recycle Bin)...")
        a_del.setEnabled(not real)
        if real:
            a_del.setToolTip("Real game saves cannot be deleted")
        act = m.exec(self.table.viewport().mapToGlobal(pos))
        if act is a_open:
            self._open_row(self.table.rowAt(pos.y()))
        elif act is a_show:
            show_in_folder(e.path)
        elif act is a_del:
            self.delete_entry(e)

    def delete_entry(self, e, confirm=None):
        """Confirm, back up to saves\\backup\\deleted_<time>\\, then Recycle Bin. confirm: test hook."""
        if paths_config.is_real_game(e.path):
            QMessageBox.warning(self, "Not allowed", "Real game saves cannot be deleted from CheeseStick.")
            return None
        text = ("Delete this save?\n\nFile: %s\nGroup: %s\nCharacter: %s\nFolder: %s\n\n"
                "A backup copy goes to TH4_dev\\saves\\backup\\deleted_<time>\\ and the file "
                "goes to the Recycle Bin." % (e.file, e.source or paths_config.OTHER, e.name or "?",
                                               os.path.dirname(e.path)))
        ok = confirm(text) if confirm else (QMessageBox.question(
            self, "Delete save", text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes)
        if not ok:
            return None
        try:
            dest = paths_config.recycle_save(e.path)
        except Exception as ex:
            QMessageBox.warning(self, "Delete failed", "%s\n\nNothing was removed." % ex)
            return None
        self.status.setText("Sent %s to the Recycle Bin (backup: %s)" % (e.file, dest))
        self.start_scan()
        return dest

def show_in_folder(path):
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
