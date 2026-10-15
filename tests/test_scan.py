"""Scan tests on temp folder trees + headless GUI check (skipped without PySide6)."""
import os, shutil, sys, tempfile, time, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from th4save import scan, mpq, codec
from tests.test_th4save import synthetic_player, empty_stash


def make_save(path, name="Tester", level=7, gold=0):
    p = synthetic_player(); p.name = name; p["CharLevel"] = level; p["TotalGold"] = gold
    arc = mpq.MpqArchive({"sphero": codec.encode(p.pack()), "spstash": codec.encode(empty_stash())})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(arc.to_bytes())


class TestScan(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        g = os.path.join(self.root, "Games", "TH4_v0.773")          # depth 2
        os.makedirs(g); open(os.path.join(g, "TH4.exe"), "wb").close()
        make_save(os.path.join(g, "th4_save_sp", "th4sp_0.ssv"), "Clarkkent", 5, 100)
        make_save(os.path.join(g, "th4_save_mp", "th4mp_1.msv"), "Bruce", 9)
        shutil.copy(os.path.join(g, "th4_save_sp", "th4sp_0.ssv"),
                    os.path.join(g, "th4_save_sp", "th4sp_0.ssv.20261012-210000.bak"))
        with open(os.path.join(g, "th4_save_sp", "th4sp_2.ssv"), "wb") as f:
            f.write(b"garbage not an mpq")
        # save folder with no TH4.exe beside it -> not auto-found
        make_save(os.path.join(self.root, "loose", "th4_save_sp", "th4sp_3.ssv"), "Loose")
        # TH4.exe too deep
        deep = os.path.join(self.root, "a", "b", "c", "d", "e")
        os.makedirs(deep); open(os.path.join(deep, "TH4.exe"), "wb").close()
        make_save(os.path.join(deep, "th4_save_sp", "th4sp_4.ssv"), "Deep")
        self.settings = os.path.join(self.root, "cfg", "settings.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_finds_and_marks(self):
        res = scan.scan([(self.root, 3)], [], known=[])
        names = {e.file: e for e in res}
        self.assertEqual(set(names), {"th4sp_0.ssv", "th4mp_1.msv", "th4sp_2.ssv"})
        self.assertEqual((names["th4sp_0.ssv"].name, names["th4sp_0.ssv"].level, names["th4sp_0.ssv"].gold, names["th4sp_0.ssv"].slot),
                         ("Clarkkent", 5, 100, "0"))
        self.assertEqual(names["th4mp_1.msv"].name, "Bruce")
        self.assertFalse(names["th4sp_2.ssv"].ok); self.assertTrue(names["th4sp_2.ssv"].error)

    def test_depth_limit(self):
        self.assertNotIn("th4sp_4.ssv", {e.file for e in scan.scan([(self.root, 3)], [], known=[])})
        self.assertIn("th4sp_4.ssv", {e.file for e in scan.scan([(self.root, 6)], [], known=[])})

    def test_finds_dark_and_outbreak(self):
        g = os.path.join(self.root, "Games", "TH4_v0.773")
        make_save(os.path.join(g, "th4_save_drk", "th4drk_0.dsv"), "Dark", 1)
        make_save(os.path.join(g, "th4_save_ob", "th4ob_0.osv"), "outbreak", 1)
        res = scan.scan([(self.root, 3)], [], known=[])
        names = {e.file: e for e in res}
        self.assertEqual(names["th4drk_0.dsv"].name, "Dark")
        self.assertEqual(names["th4drk_0.dsv"].slot, "0")
        self.assertEqual(names["th4ob_0.osv"].name, "outbreak")
        self.assertEqual(names["th4ob_0.osv"].slot, "0")
        real = r"C:\THE HELL4 Mod\TH4_v0.773"
        from th4save.save import SaveFile
        for folder, fn, hero, name, mode in (
                ("th4_save_drk", "th4drk_0.dsv", "drkhero", "Dark", 11),
                ("th4_save_ob", "th4ob_0.osv", "obhero", "outbreak", 10)):
            path = os.path.join(real, folder, fn)
            if not os.path.isfile(path):
                continue
            saved = SaveFile.load(path)
            self.assertEqual(saved.hero_entry, hero)
            self.assertTrue(saved.player.name)  # real saves get renamed
            self.assertEqual(saved.player["gameMode"], mode)
            self.assertIsNotNone(saved.stash)

    def test_added_folder_remembered(self):
        loose = os.path.join(self.root, "loose")
        scan.add_folder(loose, self.settings); scan.add_folder(loose, self.settings)
        data = scan.load_settings(self.settings)
        self.assertEqual(data["folders"], [os.path.normpath(loose)])
        res = scan.scan([], data["folders"], known=[])
        self.assertEqual([e.name for e in res], ["Loose"])

    def test_missing_roots_and_bad_settings(self):
        self.assertEqual(scan.scan([(os.path.join(self.root, "nope"), 3)], [], known=[]), [])
        os.makedirs(os.path.dirname(self.settings), exist_ok=True)
        with open(self.settings, "w") as f:
            f.write("{broken")
        self.assertEqual(scan.load_settings(self.settings)["folders"], [])

    def test_cancel(self):
        self.assertEqual(scan.find_save_folders([(self.root, 3)], cancel=lambda: True), [])


try:
    import PySide6  # noqa
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestGuiHeadless(unittest.TestCase):
    def test_finder_and_open(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from cheesestick.app import MainWindow
        app = QApplication.instance() or QApplication([])
        root = tempfile.mkdtemp()
        try:
            g = os.path.join(root, "TH4"); os.makedirs(g); open(os.path.join(g, "TH4.exe"), "wb").close()
            make_save(os.path.join(g, "th4_save_sp", "th4sp_0.ssv"), "GuiGuy", 3)
            with open(os.path.join(g, "th4_save_sp", "th4sp_1.ssv"), "wb") as f:
                f.write(b"bad")
            w = MainWindow()
            w.finder.roots = [(root, 3)]
            w.finder.settings_file = os.path.join(root, "settings.json")
            w.finder.known = []
            w.finder.start_scan()
            t0 = time.time()
            while (w.finder.worker.isRunning() or not w.finder.entries) and time.time() - t0 < 20:
                app.processEvents(); time.sleep(0.02)
            app.processEvents()
            self.assertEqual(w.finder.table.rowCount(), 2)
            texts = {w.finder.table.item(r, 2).text() for r in range(2)}
            self.assertEqual(texts, {"GuiGuy", "UNREADABLE"})
            row = next(r for r in range(2) if w.finder.table.item(r, 2).text() == "GuiGuy")
            w.finder._open_row(row)
            self.assertEqual(w.save.player.name, "GuiGuy")
            self.assertIs(w.outer.currentWidget(), w.tabs)
            bad = next(r for r in range(2) if r != row)
            w.finder._open_row(bad)                       # unreadable row: ignored, no crash
            self.assertEqual(w.save.player.name, "GuiGuy")
            w.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
