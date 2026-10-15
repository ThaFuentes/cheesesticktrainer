"""Item presets, loadouts and seed history: core (stdlib) and headless GUI."""
import json, os, shutil, sys, tempfile, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="cst_presets_")
os.environ["CHEESESTICK_PRESETS"] = os.path.join(_TMP, "presets.json")   # never the real %APPDATA% file

from th4save import presets as P
from th4save.save import SaveFile
from th4save.items import new_item, Inventory, blank_item
from th4save.rules import SLOT_NAMES
from cheesestick.data import BASE_ITEMS, UNIQUES

REAL_SP = "/workspace/th4/real/th4sp_0_v2.ssv"
REAL_MP = "/workspace/th4/real/mp/d/th4mp_0.msv"


def base_for(loc, cls_all=True):
    from cheesestick import catalog
    for b in BASE_ITEMS:
        if b.get("name") and b.get("equipLoc") == loc and (not cls_all or catalog.mask_of(b.get("classMask")) == catalog.ALL):
            return b
    raise LookupError(loc)


def strip_gear(player):
    """Synthetic test heroes carry random bytes in the body slots; start bare."""
    for i in range(len(player["OnBodySlots"])):
        player["OnBodySlots"][i] = blank_item()
    player["InventorySlots"] = [blank_item() for _ in range(70)]
    player["InvUsed"] = bytes(70); player["InvItemCount"] = 0
    player["BeltInventory"] = [blank_item() for _ in range(8)]


def make_bare_save(path, name, level):
    from tests.test_scan import synthetic_player, empty_stash
    from th4save import mpq, codec
    p = synthetic_player(); p.name = name; p["CharLevel"] = level; p["Xp"] = 0; p["TotalGold"] = 0; strip_gear(p)
    arc = mpq.MpqArchive({"sphero": codec.encode(p.pack()), "spstash": codec.encode(empty_stash())})
    with open(path, "wb") as f:
        f.write(arc.to_bytes())


def potion():
    from th4save.rules import belt_ok
    return next(b for b in BASE_ITEMS if b.get("name") and belt_ok(b))


class TestCore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_bare_save(self.path, "Core", 20)
        self.save = SaveFile.load(self.path); self.p = self.save.player
        self.store = P.PresetStore(os.path.join(self.dir, "sub", "presets.json"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def helm(self, seed=1234567890):
        b = base_for("EL_4_HEAD")
        it = new_item(b["baseId"], self.p["version"], dur=20, seed=seed)
        it.update(curCharges=1, baseCharges=3, quality=7)
        return it

    def test_default_path_uses_appdata(self):
        old = dict(os.environ)
        try:
            os.environ.pop("CHEESESTICK_PRESETS"); os.environ["APPDATA"] = r"C:\Users\x\AppData\Roaming"
            self.assertEqual(P.default_path(), os.path.join(r"C:\Users\x\AppData\Roaming", "CheeseStickTrainer", "presets.json"))
        finally:
            os.environ.clear(); os.environ.update(old)

    def test_round_trip_all_64_bytes(self):
        it = self.helm(); it["sockets"] = [1, 2, 3, 4, 5, 6]; it["enchantIndexes"] = [9, -1, 7, -1, 2]
        p = self.store.add(P.make_item_preset(it, "Helm roll", "nice res", BASE_ITEMS))
        again = P.PresetStore(self.store.path).get(p["id"])
        self.assertEqual(P.item_from_hex(again["item"]).pack(), it.pack())
        self.assertEqual((again["slot"], again["notes"]), ("Head", "nice res"))

    def test_rename_delete_search_filter(self):
        a = self.store.add(P.make_item_preset(self.helm(), "Angelwrath res roll", "", BASE_ITEMS))
        r = new_item(base_for("EL_5_FINGER")["baseId"], self.p["version"])
        b = self.store.add(P.make_item_preset(r, "Ring of speed", "fast", BASE_ITEMS))
        self.assertEqual([x["id"] for x in self.store.search("angel")], [a["id"]])
        self.assertEqual([x["id"] for x in self.store.search(slot="Ring")], [b["id"]])
        self.assertEqual([x["id"] for x in self.store.search("fast")], [b["id"]])
        self.store.rename(a["id"], "Best helm", "keep")
        self.assertEqual(P.PresetStore(self.store.path).get(a["id"])["name"], "Best helm")
        self.store.delete(b["id"])
        self.assertEqual(len(P.PresetStore(self.store.path).presets), 1)

    def test_export_import(self):
        p = self.store.add(P.make_item_preset(self.helm(), "Exported", "", BASE_ITEMS))
        out = os.path.join(self.dir, "share.json")
        self.assertEqual(self.store.export(out, {p["id"]}), 1)
        self.assertEqual(json.load(open(out))["format"], P.FORMAT)
        self.assertEqual(self.store.import_file(out), 1)            # same id -> imported as a copy
        self.assertEqual(len({x["id"] for x in self.store.presets}), 2)
        bad = os.path.join(self.dir, "bad.json")
        json.dump({"presets": [{"kind": "item", "name": "x", "item": "00"}]}, open(bad, "w"))
        self.assertEqual(self.store.import_file(bad), 0)            # broken entries are dropped
        with self.assertRaises(ValueError):
            json.dump({"nope": 1}, open(bad, "w")); self.store.import_file(bad)

    def test_apply_equip_validates_slot(self):
        it = self.helm()
        with self.assertRaises(ValueError):
            P.apply_to_equip(self.p, it, SLOT_NAMES.index("Boots"), BASE_ITEMS)
        P.apply_to_equip(self.p, it, 0, BASE_ITEMS)
        self.assertEqual(self.p["OnBodySlots"][0].pack(), it.pack())
        self.assertIsNot(self.p["OnBodySlots"][0], it)
        with self.assertRaises(ValueError):                         # occupied
            P.apply_to_equip(self.p, it, 0, BASE_ITEMS)

    def test_apply_inventory_belt_stash(self):
        it = self.helm()
        idx = P.apply_to_inventory(self.p, it, BASE_ITEMS, cell=0)
        w, h = P.item_size(it, BASE_ITEMS)
        self.assertEqual(Inventory(self.p).size_of(idx), (w, h))
        with self.assertRaises(ValueError):
            P.apply_to_inventory(self.p, it, BASE_ITEMS, cell=0)
        with self.assertRaises(ValueError):
            P.apply_to_belt(self.p, it, 0, BASE_ITEMS)
        pot = new_item(potion()["baseId"], self.p["version"])
        P.apply_to_belt(self.p, pot, 0, BASE_ITEMS)
        n = self.save.stash.item_count()
        P.apply_to_stash(self.save.stash, it, BASE_ITEMS, 3)
        self.assertEqual(self.save.stash.item_count(), n + 1)
        self.assertEqual(len(self.save.stash.tabs[3]["items"]), 1)

    def test_loadout_skips_and_reports(self):
        P.apply_to_equip(self.p, self.helm(), 0, BASE_ITEMS)
        ring = new_item(base_for("EL_5_FINGER")["baseId"], self.p["version"], seed=55)
        P.apply_to_equip(self.p, ring, 1, BASE_ITEMS)
        lo = P.make_loadout(self.p, "Kit", "", BASE_ITEMS)
        self.assertEqual([e["slot"] for e in lo["items"]], [0, 1])
        lo["items"].append({"slot": SLOT_NAMES.index("Boots"), "item": P.item_hex(self.helm()), "label": "helm on feet"})
        make_bare_save(os.path.join(self.dir, "t.ssv"), "Target", 5)
        tgt = SaveFile.load(os.path.join(self.dir, "t.ssv")).player
        applied, skipped = P.apply_loadout(tgt, lo, BASE_ITEMS, check=lambda it, s: "Not for this class" if s == 1 else "")
        self.assertEqual([a[0] for a in applied], [0])
        self.assertEqual([(s[0], s[2]) for s in skipped][0], ("Left ring", "Not for this class"))
        self.assertIn("Boots", skipped[1][0])
        a2, s2 = P.apply_loadout(tgt, lo, BASE_ITEMS)                # occupied -> skipped without replace
        self.assertIn("occupied", s2[0][2])
        a3, _ = P.apply_loadout(tgt, lo, BASE_ITEMS, replace=True)
        self.assertEqual(len(a3), 2)

    def test_empty_inputs(self):
        with self.assertRaises(ValueError):
            P.make_loadout(self.p, "none")
        with self.assertRaises(ValueError):
            P.make_item_preset(self.p["OnBodySlots"][0], "x")

    def test_seed_history(self):
        h = P.SeedHistory(); k = ("a", 1)
        for s in (5, 6, 6, 7):
            h.push(k, s)
        self.assertEqual(h.list(k), [5, 6, 7])
        self.assertEqual(h.back(k), 6); self.assertEqual(h.back(k), 5); self.assertIsNone(h.back(k))

    @unittest.skipUnless(os.path.exists(REAL_SP) and os.path.exists(REAL_MP), "real saves not present")
    def test_real_loadout_sp_to_mp(self):
        sp = SaveFile.load(REAL_SP).player
        lo = P.make_loadout(sp, "Clarkkent kit", "", BASE_ITEMS)
        for e in lo["items"]:
            self.assertEqual(P.item_from_hex(e["item"]).pack(), sp["OnBodySlots"][e["slot"]].pack())
        tmp = os.path.join(self.dir, "th4mp_0.msv"); shutil.copy(REAL_MP, tmp)
        mp = SaveFile.load(tmp)
        applied, skipped = P.apply_loadout(mp.player, lo, BASE_ITEMS, replace=True)
        self.assertEqual(len(applied) + len(skipped), len(lo["items"]))
        mp.save_safely(tmp)
        again = SaveFile.load(tmp).player
        for s, _ in applied:
            self.assertEqual(again["OnBodySlots"][s].pack(), mp.player["OnBodySlots"][s].pack())


try:
    import PySide6  # noqa
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestPresetsGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox
        from cheesestick.app import MainWindow
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_bare_save(self.path, "Gui", 30)
        os.environ["CHEESESTICK_PRESETS"] = os.path.join(self.dir, "presets.json")
        self.warnings = []
        self.w = MainWindow(); self.w.warn = self.warnings.append; self.w.game_running = lambda: []
        self.w.auto_apply_pending = QMessageBox.No
        self.w.finder.settings_file = os.path.join(self.dir, "settings.json")
        self.w.open_path(self.path)
        self.pp = self.w.presets
        b = base_for("EL_4_HEAD")
        self.helm = new_item(b["baseId"], self.w.save.player["version"], dur=15, seed=1111111111)
        self.w.save.player["OnBodySlots"][0] = self.helm; self.w.refresh_all(); self.w.set_dirty(False)

    def tearDown(self):
        self.w.dirty = False; self.w.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def test_tab_exists_and_store_path(self):
        titles = [self.w.tabs.tabText(i) for i in range(self.w.tabs.count())]
        self.assertTrue(any("Presets" in t for t in titles))
        self.assertEqual(self.pp.store.path, os.path.join(self.dir, "presets.json"))

    def save_helm(self, name="Helm res roll"):
        eq = self.w.lists["equip"]; eq.select_row(0)
        self.w.auto_preset_name = (name, "notes here")
        return eq.save_preset()

    def test_save_apply_marks_unsaved_only(self):
        p = self.save_helm()
        self.assertTrue(os.path.exists(self.pp.store.path))
        self.pp.select_id(p["id"])
        before = open(self.path, "rb").read()
        self.pp.target.setCurrentText(SLOT_NAMES[0]); self.assertFalse(self.pp.apply_selected())  # occupied
        self.pp.target.setCurrentText("Boots"); self.assertFalse(self.pp.apply_selected())        # wrong slot
        self.assertFalse(self.w.dirty)
        from cheesestick.presets_panel import INV
        self.pp.target.setCurrentText(INV); self.assertTrue(self.pp.apply_selected())
        self.assertTrue(self.pp.add_to_stash())
        self.assertTrue(self.w.dirty)
        self.assertEqual(open(self.path, "rb").read(), before)       # nothing written by apply
        inv = Inventory(self.w.save.player)
        self.assertEqual(inv.items()[-1].pack(), self.helm.pack())

    def test_inventory_cell_target(self):
        p = self.save_helm(); self.pp.select_id(p["id"])
        from cheesestick.presets_panel import INV
        self.w.lists["inv"].last_empty_cell = 25
        self.pp.target.setCurrentText(INV); self.assertTrue(self.pp.apply_selected())
        inv = Inventory(self.w.save.player)
        self.assertIn(25, inv.cells_of(inv.count - 1))

    def test_rename_delete_filter_export_import(self):
        p = self.save_helm("Alpha")
        self.w.auto_preset_name = ("Beta", "n2"); self.pp.select_id(p["id"]); self.pp.rename()
        self.assertEqual(self.pp.store.get(p["id"])["name"], "Beta")
        self.pp.slot_filter.setCurrentText("Ring"); self.assertEqual(self.pp.table.rowCount(), 0)
        self.pp.slot_filter.setCurrentText("Head"); self.assertEqual(self.pp.table.rowCount(), 1)
        self.pp.search.setText("zzz"); self.assertEqual(self.pp.table.rowCount(), 0)
        self.pp.search.setText(""); self.pp.slot_filter.setCurrentText("All")
        out = os.path.join(self.dir, "x.json"); self.w.auto_export_all = True
        self.assertEqual(self.pp.export(out), 1)
        self.pp.select_id(p["id"]); self.w.auto_confirm_delete = True; self.pp.delete()
        self.assertEqual(self.pp.table.rowCount(), 0)
        self.assertEqual(self.pp.import_(out), 1); self.assertEqual(self.pp.table.rowCount(), 1)

    def test_loadout_to_other_character_and_safe_save(self):
        self.w.auto_preset_name = ("Kit", "")
        lo = self.pp.save_loadout()
        self.assertEqual(lo["kind"], "loadout")
        other = os.path.join(self.dir, "th4sp_1.ssv"); make_bare_save(other, "Other", 3)
        self.w.open_path(other); self.assertFalse(self.w.dirty)
        self.pp.select_id(lo["id"])
        applied, skipped = self.pp.apply_loadout()
        self.assertEqual((len(applied), skipped), (1, []))
        self.assertTrue(self.w.dirty)
        self.w.auto_loadout_replace = False
        applied, skipped = self.pp.apply_loadout()                  # now occupied: reported as skipped
        self.assertEqual(len(applied), 0); self.assertIn("occupied", skipped[0][2])
        self.assertTrue(any("Skipped" in m for m in self.warnings))
        # file changed on disk -> refused, still unsaved
        make_bare_save(other, "Other", 4)
        st = os.stat(other); os.utime(other, (st.st_atime, st.st_mtime + 5))
        self.w.auto_game_in_progress = "save"   # no game in progress: the prompt offers Save/Cancel
        self.assertFalse(self.w.save_file()); self.assertTrue(self.w.dirty)
        # reopen, apply, real save writes and keeps the item
        self.w.dirty = False; self.w.open_path(other); self.pp.select_id(lo["id"]); self.pp.apply_loadout()
        ok = self.w.save_file()
        self.assertIsNotNone(self.w.last_pairing_prompt)               # the save prompt still ran
        self.assertTrue(ok, (self.warnings[-1:], self.w.statusBar().currentMessage()))
        self.assertEqual(SaveFile.load(other).player["OnBodySlots"][0].pack(), self.helm.pack())
        self.assertTrue(any(f.endswith(".bak") for f in os.listdir(self.dir)))

    def test_loadout_class_skip(self):
        from cheesestick import catalog
        self.w.auto_preset_name = ("Kit", ""); lo = self.pp.save_loadout()
        real = catalog.limits
        catalog.limits = lambda b, v: ["Not for this class"]
        try:
            self.pp.select_id(lo["id"]); self.w.save.player["OnBodySlots"][0] = P.item_from_hex("00" * 64)
            self.w.save.player["OnBodySlots"][0]["baseItemIndex"] = -1
            applied, skipped = self.pp.apply_loadout(replace=True)
        finally:
            catalog.limits = real
        self.assertEqual(applied, []); self.assertEqual(skipped[0][2], "Not for this class")

    def test_seed_history_back(self):
        eq = self.w.lists["equip"]; eq.select_row(0)
        self.assertFalse(eq.seed_back_btn.isEnabled())
        eq.roll_seed(); first = eq.e_seed.text(); eq.roll_seed()
        self.assertTrue(eq.seed_back_btn.isEnabled())
        self.assertEqual(eq.previous_seed(), int(first))
        self.assertEqual(eq.previous_seed(), 1111111111)
        eq.apply()
        self.assertEqual(self.w.save.player["OnBodySlots"][0]["seed"], 1111111111)
        eq.roll_seed(); eq.apply(); rolled = self.w.save.player["OnBodySlots"][0]["seed"]
        self.w.refresh_all(); eq.select_row(0)                       # history survives a refresh
        self.assertEqual(eq.previous_seed(), 1111111111); self.assertNotEqual(rolled, 1111111111)

    def test_theme_has_shell_touches(self):
        from cheesestick.brand import shell_qss, shell_texture_path, SHELL_GREEN
        self.assertTrue(os.path.exists(shell_texture_path()))
        self.assertIn(SHELL_GREEN, shell_qss())
        self.assertFalse(self.w.header.mark.pixmap().isNull())


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)
