"""Multiplayer launcher + path settings window.

Open directly:  python -m cheesestick.launcher   (from the CheeseStickTrainer folder)
"""
import os, subprocess, sys
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                               QLabel, QLineEdit, QPushButton, QSpinBox, QFileDialog, QListWidget,
                               QListWidgetItem, QMessageBox, QInputDialog, QComboBox, QPlainTextEdit, QCheckBox)
from . import paths_config


KEEP = ""  # "(keep current save)"
SEAT_DEFAULT_GROUP = {1: "Christopher's", 2: "Pres", 3: "Summoner", 4: "Tech"}
SEAT_DEFAULT_NAME = {1: "ThaFuentes", 2: "Pres.Shell", 3: "DavidL", 4: "AmyLee"}  # used when the group is empty


def prepare_seat_saves(cfg, seat_saves):
    """Single-player (or other mode) picks are converted into TH4_dev\\saves\\converted\\*.msv
    (source only read). Returns {slot: msv path}."""
    import time
    from th4save import convert
    out = {}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for n, p in seat_saves.items():
        if not p or p.lower().endswith(".msv"):
            out[n] = p; continue
        dest = os.path.join(cfg["game_dir"], "saves", "converted",
                            "%s_slot%d_%s.msv" % (os.path.splitext(os.path.basename(p))[0], n, stamp))
        if paths_config.is_real_game(dest, cfg):
            raise PermissionError("conversion target is inside the real game")
        convert.convert(p, dest)
        out[n] = dest
    return out


def build_command(cfg, bots, seat_saves=None, whatif=False, seat_labels=None, auto_host=False):
    """bots = bot seats only; the player seat (slot1, host) is always added and launched last.
    seat_saves: {slot:int -> save path}; empty/missing = keep the slot's current save."""
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", cfg["launcher_script"],
           "-Bots", str(int(bots)), "-Addr", cfg.get("addr", "127.0.0.1"),
           "-Host", cfg.get("host", "slot1"), "-Game", cfg.get("game_name", "TH4bots"), "-PlayerLast"]
    spec = ";".join("%d=%s" % (n, seat_saves[n]) for n in sorted(seat_saves or {})
                    if n <= int(bots) + 1 and seat_saves[n])
    if spec:
        cmd += ["-SeatSave", spec]
    labs = ";".join("%d=%s" % (n, seat_labels[n]) for n in sorted(seat_labels or {})
                    if 1 < n <= int(bots) + 1 and seat_labels[n])
    # custom window titles dropped: the game titles windows "#N", and #1 is always the player (slot1)
    if auto_host:
        cmd.append("-AutoHost")
    if whatif:
        cmd.append("-WhatIf")
    return cmd


def solo_save_dir(cfg):
    """SaveDir (relative to TH4_dev) for the solo group, default "Christopher's"."""
    grp = cfg.get("solo_group") or "Christopher's"
    dev = os.path.normcase(os.path.abspath(cfg["game_dir"]))
    for lab, d in cfg.get("save_dirs", []):
        full = os.path.normcase(os.path.abspath(d))
        if lab == grp and full.startswith(dev + os.sep):
            return os.path.relpath(d, cfg["game_dir"])
    return os.path.join("saves", "slot1")


def build_solo_command(cfg, whatif=False):
    script = os.path.join(os.path.dirname(cfg["launcher_script"]), "solo.ps1")
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script, "-Workshop", cfg["workshop_dir"],
           "-DevDir", cfg["game_dir"], "-SaveDir", solo_save_dir(cfg)]
    return cmd + (["-WhatIf"] if whatif else [])


def mp_save_choices(cfg=None):
    """[(display, path)] for multiplayer (.msv) saves in the labeled groups."""
    from th4save import scan
    try:
        es = scan.scan(roots=[], known=[], sources=paths_config.known_sources(cfg))
    except Exception:
        es = []
    out = []
    for e in sorted(es, key=lambda e: (e.source, e.file)):
        if e.ok:
            tag = "" if e.file.lower().endswith(".msv") else "  [converted to MP on launch]"
            out.append(("%s - %s (%s)%s" % (e.source, e.name or "?", e.file, tag), e.path))
    return out


class LauncherDialog(QDialog):
    def __init__(self, parent=None, config_file=None):
        super().__init__(parent)
        self.setWindowTitle("CheeseStick - Multiplayer Launcher")
        self.config_file = config_file
        self.cfg = paths_config.load(config_file)
        v = QVBoxLayout(self)

        run = QGroupBox("Launch private multiplayer session"); f = QFormLayout(run)
        self.bots = QSpinBox(); self.bots.setRange(1, 3); self.bots.setValue(int(self.cfg.get("bots", 2)))
        self.seats = QLabel(); self.bots.valueChanged.connect(self._seats); self._seats()
        row = QHBoxLayout(); row.addWidget(self.bots); row.addWidget(self.seats); row.addStretch()
        f.addRow("Bot seats:", row)
        self.choices = mp_save_choices(self.cfg)
        saved = {int(k): v for k, v in (self.cfg.get("seat_saves") or {}).items()}
        self.seat_combo = {}
        for n in (2, 3, 4):
            self.seat_combo[n] = self._combo(n, saved)
            f.addRow("Bot seat %d (slot%d) save:" % (n - 1, n), self.seat_combo[n])
        self.seat_combo[1] = self._combo(1, saved)
        f.addRow("Your seat (slot1, host, opens last):", self.seat_combo[1])
        self.bots.valueChanged.connect(self._enable_seats); self._enable_seats()
        self.auto_host = QCheckBox("Auto-host for me (skip the menus in #1; off = you pick the multiplayer method and New Game)")
        self.auto_host.setChecked(bool(self.cfg.get("auto_host", False)))
        f.addRow(self.auto_host)
        h2 = QHBoxLayout()
        self.btn_launch = QPushButton("Launch session"); self.btn_launch.clicked.connect(self.launch)
        self.btn_dry = QPushButton("Dry run (no game)"); self.btn_dry.clicked.connect(self.dry_run)
        h2.addWidget(self.btn_launch); h2.addWidget(self.btn_dry); h2.addStretch(); f.addRow(h2)
        h3 = QHBoxLayout()
        self.solo_group = QComboBox(); self.solo_group.addItems(paths_config.group_labels(self.cfg))
        i = self.solo_group.findText(self.cfg.get("solo_group") or "Christopher's"); self.solo_group.setCurrentIndex(max(i, 0))
        self.btn_solo = QPushButton("Play solo (just me)"); self.btn_solo.clicked.connect(self.play_solo)
        self.btn_solo_dry = QPushButton("Solo dry run"); self.btn_solo_dry.clicked.connect(lambda: self.play_solo(dry=True))
        h3.addWidget(self.btn_solo); h3.addWidget(QLabel("save group:")); h3.addWidget(self.solo_group)
        h3.addWidget(self.btn_solo_dry); h3.addStretch(); f.addRow(h3)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True); self.out.setMaximumHeight(120)
        f.addRow(self.out)
        f.addRow(QLabel("#1 is you: window \"THEHELL4 [TH4 #1]\" = slot1, the host, your save, port %d. "
                        "Bots are #2 and #3 (#4 with 3 bots)." % (47774 + 1)))
        f.addRow(QLabel("Bots open first, your window last. Auto-join is not reliable yet: if a bot "
                        "doesn't join, join it by hand at 127.0.0.1."))
        v.addWidget(run)

        paths = QGroupBox("Paths (saved to %s)" % os.path.basename(config_file or paths_config.CONFIG_FILE))
        pf = QFormLayout(paths); self.edits = {}
        for key, label, is_dir in (("game_dir", "Game (TH4_dev) folder", True),
                                   ("workshop_dir", "Workshop folder", True),
                                   ("launcher_script", "Launcher script", False),
                                   ("real_game_dir", "Real game (read-only)", True)):
            e = QLineEdit(self.cfg.get(key, "")); self.edits[key] = e
            b = QPushButton("Browse..."); b.clicked.connect(lambda _=False, k=key, d=is_dir: self._browse(k, d))
            h = QHBoxLayout(); h.addWidget(e, 1); h.addWidget(b); pf.addRow(label + ":", h)
        self.dirs = QListWidget()
        for lab, d in self.cfg.get("save_dirs", []):
            self._add_dir_item(lab, d)
        pf.addRow("Save groups\n(label - folder):", self.dirs)
        h = QHBoxLayout()
        for text, fn in (("Add folder...", self._add_dir), ("Edit / change group...", self._edit_dir),
                         ("Rename group...", self._rename_group), ("Remove", self._remove_dir)):
            b = QPushButton(text); b.clicked.connect(fn); h.addWidget(b)
        h.addStretch(); pf.addRow(h)
        v.addWidget(paths)

        bottom = QHBoxLayout(); bottom.addStretch()
        b = QPushButton("Save settings"); b.clicked.connect(self.save); bottom.addWidget(b)
        b = QPushButton("Close"); b.clicked.connect(self.close); bottom.addWidget(b)
        v.addLayout(bottom)
        self.resize(720, 520)

    def _combo(self, n, saved):
        c = QComboBox(); c.addItem("(fresh / keep current - create a new character in game)", KEEP)
        for disp, path in self.choices:
            c.addItem(disp, path)
        want = saved.get(n)
        idx = c.findData(want) if want else -1
        if idx < 0 and not want:
            g = SEAT_DEFAULT_GROUP.get(n, "")
            idx = next((i for i in range(c.count()) if c.itemText(i).startswith(g + " - ")), -1)
            if idx < 0:
                nm = SEAT_DEFAULT_NAME.get(n, "")
                idx = next((i for i in range(c.count()) if (" - %s (" % nm) in c.itemText(i)
                            and "Real game" not in c.itemText(i) and "Backups" not in c.itemText(i)), 0)
        c.setCurrentIndex(max(idx, 0))
        return c

    def _enable_seats(self):
        for n in (2, 3, 4):
            self.seat_combo[n].setEnabled(n <= self.bots.value() + 1)

    def seat_saves(self):
        return {n: c.currentData() for n, c in self.seat_combo.items()
                if (n == 1 or n <= self.bots.value() + 1) and c.currentData() and os.path.isfile(c.currentData())}

    def seat_labels(self):
        out = {}
        for n, c in self.seat_combo.items():
            txt = c.currentText()
            out[n] = txt.split(" - ", 1)[0] if c.currentData() else SEAT_DEFAULT_GROUP.get(n, "")
        return out

    def dry_run(self):
        cfg = self.collect()
        cmd = build_command(cfg, self.bots.value(), self.seat_saves(), whatif=True, seat_labels=self.seat_labels(), auto_host=self.auto_host.isChecked())
        conv = [n for n, p in self.seat_saves().items() if not p.lower().endswith(".msv")]
        note = ("(on a real launch, seats %s are converted to MP first)\n" % conv) if conv else ""
        try:
            r = subprocess.run(cmd, cwd=cfg["workshop_dir"], capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.out.setPlainText(note + " ".join(cmd) + "\n\n" + r.stdout + r.stderr)
        except Exception as e:
            self.out.setPlainText("Dry run failed: %s" % e)

    def play_solo(self, dry=False):
        """One TH4_dev window, single player, no bots. dry=True runs -WhatIf and shows the output."""
        cfg = self.collect()
        cmd = build_solo_command(cfg, whatif=dry)
        if any(paths_config.is_real_game(p, cfg) for p in (cfg["workshop_dir"], cfg["game_dir"], cmd[4])):
            QMessageBox.warning(self, "Blocked", "Paths point at the real game. Use the TH4_Workshop copy."); return None
        if not os.path.isfile(cmd[4]):
            QMessageBox.warning(self, "Missing", "solo.ps1 not found next to the launcher script."); return None
        self.cfg = cfg; paths_config.save(cfg, self.config_file)
        if dry:
            r = subprocess.run(cmd, cwd=cfg["workshop_dir"], capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.out.setPlainText(" ".join(cmd) + "\n\n" + r.stdout + r.stderr); return cmd
        subprocess.Popen(cmd, cwd=cfg["workshop_dir"], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return cmd

    def _seats(self):
        self.seats.setText("+ your seat = %d windows (%d bot%s, then you)" % (self.bots.value() + 1, self.bots.value(),
                                                                 "" if self.bots.value() == 1 else "s"))

    def _browse(self, key, is_dir):
        cur = self.edits[key].text()
        if is_dir:
            p = QFileDialog.getExistingDirectory(self, "Choose folder", cur)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Choose script", os.path.dirname(cur), "PowerShell (*.ps1);;All (*)")
        if p:
            self.edits[key].setText(os.path.normpath(p))

    def _add_dir_item(self, lab, d):
        it = QListWidgetItem("%s  -  %s" % (lab, d)); it.setData(256, [lab, d]); self.dirs.addItem(it)

    def _labels(self):
        out = []
        for i in range(self.dirs.count()):
            lab = self.dirs.item(i).data(256)[0]
            if lab not in out:
                out.append(lab)
        return out or [paths_config.OTHER]

    def _pick_label(self, title, current):
        labs = self._labels()
        if current not in labs:
            labs = [current] + labs
        lab, ok = QInputDialog.getItem(self, title, "Group label (pick one or type a new one):",
                                       labs, labs.index(current), True)
        return (lab.strip() or current) if ok else None

    def _add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Add save folder")
        if d:
            lab = self._pick_label("Group", paths_config.OTHER)
            if lab:
                self._add_dir_item(lab, os.path.normpath(d))

    def _edit_dir(self):
        it = self.dirs.currentItem()
        if not it:
            return
        lab, d = it.data(256)
        nd = QFileDialog.getExistingDirectory(self, "Change folder (Cancel keeps it)", d) or d
        nl = self._pick_label("Group", lab)
        if nl:
            self._set_item(it, nl, os.path.normpath(nd))

    def _set_item(self, it, lab, d):
        it.setData(256, [lab, d]); it.setText("%s  -  %s" % (lab, d))

    def rename_group(self, old, new):
        for i in range(self.dirs.count()):
            it = self.dirs.item(i); lab, d = it.data(256)
            if lab == old:
                self._set_item(it, new, d)

    def _rename_group(self):
        labs = self._labels()
        cur = self.dirs.currentItem()
        start = labs.index(cur.data(256)[0]) if cur else 0
        old, ok = QInputDialog.getItem(self, "Rename group", "Group:", labs, start, False)
        if not ok:
            return
        new, ok = QInputDialog.getText(self, "Rename group", "New label for '%s':" % old, text=old)
        if ok and new.strip():
            self.rename_group(old, new.strip())
    def _remove_dir(self):
        r = self.dirs.currentRow()
        if r >= 0:
            self.dirs.takeItem(r)  # removes from the list only; nothing on disk is touched

    def collect(self):
        cfg = dict(self.cfg)
        for k, e in self.edits.items():
            cfg[k] = e.text().strip()
        cfg["bots"] = self.bots.value()
        if hasattr(self, "auto_host"):
            cfg["auto_host"] = self.auto_host.isChecked()
        if hasattr(self, "solo_group"):
            cfg["solo_group"] = self.solo_group.currentText()
        if hasattr(self, "seat_combo"):
            cfg["seat_saves"] = {str(n): c.currentData() for n, c in self.seat_combo.items()}
        cfg["save_dirs"] = [self.dirs.item(i).data(256) for i in range(self.dirs.count())]
        return cfg

    def save(self):
        self.cfg = self.collect()
        paths_config.save(self.cfg, self.config_file)
        QMessageBox.information(self, "Saved", "Settings saved.")

    def launch(self):
        cfg = self.collect()
        ws, script = cfg["workshop_dir"], cfg["launcher_script"]
        for p in (ws, script, cfg["game_dir"]):
            if paths_config.is_real_game(p, cfg):
                QMessageBox.warning(self, "Blocked", "Paths point at the real game. Use the TH4_Workshop copy.")
                return
        if not os.path.isdir(ws) or not os.path.isfile(script):
            QMessageBox.warning(self, "Missing", "Workshop folder or launcher script not found. Fix the paths below.")
            return
        try:
            seats = prepare_seat_saves(cfg, self.seat_saves())
        except Exception as e:
            QMessageBox.warning(self, "Save conversion failed", str(e)); return
        cmd = build_command(cfg, self.bots.value(), seats, seat_labels=self.seat_labels(), auto_host=self.auto_host.isChecked())
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(cmd, cwd=ws, creationflags=flags)
        self.cfg = cfg; paths_config.save(cfg, self.config_file)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    d = LauncherDialog(); d.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
