"""Slot rules + headless GUI checks for slot-aware adding and the paperdoll."""
import os, shutil, sys, tempfile, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from th4save.rules import allowed, belt_ok, category, SLOTS
from cheesestick.data import BASE_ITEMS

B = {b["name"]: b for b in reversed(BASE_ITEMS) if b["name"]}


class TestRules(unittest.TestCase):
    def test_equip_slots(self):
        self.assertTrue(allowed(B["Short Knife"], "equip", 4))       # hand
        self.assertTrue(allowed(B["Wooden Shield"], "equip", 5))
        self.assertFalse(allowed(B["Short Knife"], "equip", 0))      # not head
        self.assertTrue(allowed(B["Skull Cap"], "equip", 0))
        self.assertFalse(allowed(B["Skull Cap"], "equip", 6))
        self.assertTrue(allowed(B["Hauberk"], "equip", 6))
        self.assertFalse(allowed(B["Potion of Healing"], "equip", 3))

    def test_every_slot_has_candidates(self):
        for s in SLOTS:
            self.assertTrue(any(allowed(b, "equip", s[0]) for b in BASE_ITEMS), s[1])

    def test_belt(self):
        self.assertTrue(belt_ok(B["Potion of Healing"]))
        self.assertFalse(belt_ok(B["Gold"]))
        self.assertFalse(belt_ok(B["Short Knife"]))
        self.assertFalse(belt_ok(B["Sodalite (grade 1)"]))
        self.assertTrue(all(b["equipLoc"] == "EL_7_INVENTORY" for b in BASE_ITEMS if belt_ok(b)))

    def test_inventory_any(self):
        self.assertTrue(allowed(B["Hauberk"], "inv") and allowed(B["Gold"], "stash"))

    def test_categories(self):
        self.assertEqual(category(B["Wooden Shield"]), "Shields")
        self.assertEqual(category(B["Potion of Healing"]), "Potions & elixirs")


try:
    import PySide6  # noqa
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestSlotGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from cheesestick.app import apply_theme
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        from cheesestick.app import MainWindow
        from tests.test_scan import make_save
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_save(self.path, "Doll", 4)
        self.w = MainWindow()
        self.warnings = []
        self.w.warn = self.warnings.append
        self.w.open_path(self.path)
        p = self.w.save.player   # synthetic: clear all containers
        from th4save.items import blank_item
        for k in ("OnBodySlots", "BeltInventory"):
            p[k] = [blank_item() for _ in p[k]]
        p["InvUsed"] = bytes(70); p["InvItemCount"] = 0; p["TotalGold"] = 0
        self.w.refresh_all()

    def tearDown(self):
        self.w.dirty = False; self.w.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def pick(self, name, seen=None):
        def f(dlg):
            # Hide-unusable is on by default. These saves have random stats, so the
            # slot list (dlg.valid) stays complete and the tree is unfiltered for the test.
            dlg.hide_unusable.setChecked(False)
            if dlg.container == "equip" and dlg.slot == 0:
                kinds = [dlg.tree.topLevelItem(i).text(0).split(" — ", 1)[0]
                         for i in range(dlg.tree.topLevelItemCount())]
                self.assertEqual(kinds[0], "UNIQUE")
                self.assertIn("Plain", kinds)
                head = dlg.tree.topLevelItem(0)
                self.assertTrue(head.isExpanded())
                self.assertTrue(head.child(0).text(0).startswith("UNIQUE"))
                self.assertEqual(head.child(0).text(1), "UNIQUE")
                plain = next(dlg.tree.topLevelItem(i) for i in range(dlg.tree.topLevelItemCount())
                             if dlg.tree.topLevelItem(i).text(0).startswith("Plain"))
                self.assertFalse(plain.isExpanded())
            if seen is not None:
                seen.extend(b["baseId"] for b in dlg.valid)
            self.assertTrue(dlg.select_id(B[name]["baseId"]), "%s not offered" % name)
        self.w.auto_picker = f

    def test_paperdoll_slot_filters_and_places(self):
        eq = self.w.lists["equip"]; seen = []
        self.pick("Skull Cap", seen)
        eq.visual.buttons[0].click()                      # click Head on the paperdoll
        self.assertEqual(self.w.save.player["OnBodySlots"][0]["baseItemIndex"], B["Skull Cap"]["baseId"])
        self.assertTrue(all(BASE_ITEMS[i]["equipLoc"] == "EL_4_HEAD" for i in seen))
        self.assertIn("Skull Cap", eq.visual.buttons[0].text())

    def test_belt_filter_and_validation(self):
        belt = self.w.lists["belt"]; seen = []
        self.pick("Potion of Healing", seen)
        belt.visual.buttons[2].click()
        self.assertEqual(self.w.save.player["BeltInventory"][2]["baseItemIndex"], B["Potion of Healing"]["baseId"])
        self.assertTrue(seen and all(belt_ok(BASE_ITEMS[i]) for i in seen))
        from th4save.items import new_item
        with self.assertRaises(ValueError):                  # direct placement is validated too
            belt.place(new_item(B["Short Knife"]["baseId"], 30), slot=3)
        with self.assertRaises(ValueError):
            self.w.lists["equip"].place(new_item(B["Hauberk"]["baseId"], 30), slot=0)

    def test_inventory_cell_click_places_at_cell(self):
        inv = self.w.lists["inv"]
        def f(dlg):
            dlg.hide_unusable.setChecked(False)
            dlg.select_id(B["Wooden Shield"]["baseId"]); dlg.w.setValue(2); dlg.h.setValue(2)
        self.w.auto_picker = f
        inv.visual.buttons[23].click()                    # row 2, col 3 = top-left
        from th4save.items import Inventory
        i = Inventory(self.w.save.player)
        self.assertEqual(i.count, 1)
        self.assertEqual(sorted(i.cells_of(0)), [23, 24, 33, 34])
        self.assertEqual(i.grid()[33], 1)                 # bottom-left anchor

    def test_quality_color(self):
        from cheesestick.widgets import quality_of
        from th4save.items import new_item
        it = new_item(1, 30); self.assertEqual(quality_of(it), 0)
        # (MagicLevel << 1) | Identified, msg.cpp / Item.cpp RecreateItem
        it["magicLevelAndIdentified"] = 1; self.assertEqual(quality_of(it), 0)   # identified normal
        it["magicLevelAndIdentified"] = 3; self.assertEqual(quality_of(it), 1)   # identified magic
        it["magicLevelAndIdentified"] = 4; self.assertEqual(quality_of(it), 2)   # unidentified unique


if __name__ == "__main__":
    unittest.main()
