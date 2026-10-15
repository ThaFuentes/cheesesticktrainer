"""Item catalog, hover text, same-slot rank, and the item browser."""
import os, struct, sys, tempfile, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cheesestick import catalog
from cheesestick.data import BASE_ITEMS
from cheesestick.icons import decode_frame, sprite_loc, write_png

B = {b["name"]: b for b in reversed(BASE_ITEMS) if b["name"]}


def _view(**kw):
    base = {
        "fcid": 0, "classic": False, "exile": False, "mode": 0, "mp": False,
        "stats": {"Str": 25, "Mag": 5, "Dex": 15, "Vit": 20, "Lvl": 1},
    }
    base.update(kw)
    return base


class TestCatalog(unittest.TestCase):
    def test_flag_counts(self):
        self.assertEqual(len(catalog.CLASSIC), 116)
        self.assertEqual(catalog.BOTH, {0})
        self.assertEqual(len(catalog.NO_EXILE), 87)
        self.assertNotIn(1, catalog.CLASSIC)
        self.assertNotIn(1, catalog.BOTH)
        self.assertNotIn(1, catalog.NO_EXILE)

    def test_every_class_mask_parses(self):
        for b in BASE_ITEMS:
            expr = b.get("classMask")
            if expr:
                self.assertIsNotNone(catalog.mask_of(expr), expr)

    def test_knife_class_and_stats(self):
        knife = B["Short Knife"]
        self.assertEqual(catalog.game_class_line(knife["classMask"]), "[Warriors only]")
        self.assertEqual(catalog.limits(knife, _view()), [])
        self.assertIn("Not for this class", catalog.limits(knife, _view(fcid=4)))
        self.assertIn("Not usable in classic", catalog.limits(knife, _view(classic=True, mode=9)))

    def test_classic_exile_mp_and_portal(self):
        cid = min(catalog.CLASSIC)
        classic = BASE_ITEMS[cid]
        self.assertIn("Classic", catalog.badges(classic))
        self.assertIn("Classic only", catalog.limits(classic, _view()))
        high = _view(classic=True, mode=9, stats={"Str": 999, "Mag": 999, "Dex": 999, "Vit": 999, "Lvl": 150})
        self.assertNotIn("Classic only", catalog.limits(classic, high))
        exile_id = min(catalog.NO_EXILE)
        banned = BASE_ITEMS[exile_id]
        self.assertIn("No exiles", catalog.badges(banned))
        self.assertIn("Exiles cannot use this", catalog.limits(banned, _view(fcid=24, exile=True)))
        self.assertNotIn("Exiles cannot use this", catalog.limits(banned, _view(fcid=0, exile=False)))
        relict = next(b for b in BASE_ITEMS if b.get("spell") == "PS_32_BONE_SPIRIT_REAL_RESSURECT")
        self.assertEqual(relict["baseId"], 398)
        self.assertIn("Multiplayer", catalog.badges(relict))
        rich = _view(mp=False, stats={"Str": 999, "Mag": 999, "Dex": 999, "Vit": 999, "Lvl": 150})
        self.assertIn("Multiplayer only", catalog.limits(relict, rich))
        self.assertNotIn("Multiplayer only", catalog.limits(relict, _view(mp=True, stats=rich["stats"])))
        portal = next(b for b in BASE_ITEMS if b.get("spell") == "PS_7_TOWN_PORTAL")
        self.assertIn("No town portal", catalog.badges(portal))
        blocked = _view(mode=3, stats=rich["stats"])
        self.assertIn("Town portal is disabled in this mode", catalog.limits(portal, blocked))
        self.assertNotIn("Town portal is disabled in this mode", catalog.limits(portal, _view(mode=4, stats=rich["stats"])))

    def test_rank_stays_inside_category_and_slot(self):
        knife = B["Short Knife"]
        ring = B["Ring"]
        self.assertNotEqual(catalog.rank_group(knife), catalog.rank_group(ring))
        info = catalog.rank_info(knife)
        self.assertEqual(info["group"], ("Swords", "EL_1_ONE_HANDED"))
        self.assertEqual(info["value"], 11)
        self.assertEqual(info["den"], 1)
        text = catalog.rank_text(knife)
        self.assertIn("11 ÷ 1 = 11", text)
        self.assertIn("among Swords, one-handed", text)
        self.assertIn("0 counts as 1", text)
        self.assertIsNone(catalog.rank_info(B["Potion of Healing"]))
        sword_ids = {b["baseId"] for b in BASE_ITEMS
                     if b.get("name") and catalog.rank_group(b) == info["group"]}
        ring_ids = {b["baseId"] for b in BASE_ITEMS
                    if b.get("name") and catalog.rank_group(b) == catalog.rank_group(ring)}
        self.assertTrue(sword_ids.isdisjoint(ring_ids))

    def test_helm_defense_beats_plain_and_magic_breaks_ties(self):
        def helm(name, armor, effects=None, bid=2):
            return {
                "baseId": bid, "name": name, "itemType": "ITEM_2_ARMOR", "itemCode": "IC_7_HELM",
                "equipLoc": "EL_4_HEAD", "classMask": "IPCM_ALL_CLASSES",
                "dmg": [0, 0, 0, 0], "armor": [armor, armor], "effects": effects or [],
                "spell": "PS_0_NONE",
            }
        plain = helm("Plain Cap", 5, bid=2)
        heavy = helm("Great Helm", 40, bid=3)
        magic = helm("Rune Cap", 5, effects=[["AE_STAT", "ST_STRENGTH", 10, 15, 0, 0, 0, 0]], bid=4)
        self.assertEqual(catalog.magic_magnitude(plain), 0)
        self.assertEqual(catalog.magic_magnitude(magic), 15)
        self.assertLess(catalog.power_key(heavy), catalog.power_key(plain))
        self.assertLess(catalog.power_key(magic), catalog.power_key(plain))
        self.assertLess(catalog.power_key(heavy), catalog.power_key(magic))
        zero = helm("Marked Cap", 5, effects=[["AE_TO_HIT", "0", 0, 0, 0, 0, 0, 0]], bid=5)
        self.assertEqual(catalog.magic_magnitude(zero), 0)
        self.assertEqual(catalog.magic_magnitude({"magicCode": "MC_23_STAFF", "spell": "PS_0_NONE", "effects": []}), 0)
        sword = {
            "baseId": 6, "name": "Blade", "itemType": "ITEM_1_WEAPON", "itemCode": "IC_1_SWORD",
            "equipLoc": "EL_1_ONE_HANDED", "dmg": [1, 1, 9, 12], "armor": [0, 0], "effects": [],
            "spell": "PS_0_NONE",
        }
        self.assertEqual(catalog.better_sort_key(sword)[3], "swords")
        self.assertEqual(catalog.better_sort_key(heavy)[3], "helms")
        self.assertNotEqual(catalog.rank_group(sword)[0], catalog.rank_group(heavy)[0])
        helms = [b for b in BASE_ITEMS if b.get("name") and b.get("itemCode") == "IC_7_HELM"]
        helms.sort(key=catalog.power_key)
        self.assertGreater(helms[0]["armor"][1], helms[-1]["armor"][1])
        mage = _view(fcid=8, mp=True, stats={"Str": 9999, "Mag": 9999, "Dex": 9999, "Vit": 9999, "Lvl": 150})
        for item, bid in ((plain, 900002), (heavy, 900003), (magic, 900004)):
            item["baseId"] = bid
            item["classMask"] = "IPCM_ALL_CLASSES"
        self.assertLess(catalog.power_key(heavy, mage), catalog.power_key(magic, mage))
        self.assertLess(catalog.power_key(magic, mage), catalog.power_key(plain, mage))

    def test_class_guides_lead_with_that_class_weapon(self):
        def lead(fcid):
            view = _view(fcid=fcid, mp=True,
                         stats={"Str": 9999, "Mag": 9999, "Dex": 9999, "Vit": 9999, "Lvl": 150})
            rows = [b for b in BASE_ITEMS if b.get("name") and not catalog.limits(b, view)]
            rows.sort(key=lambda b: catalog.better_sort_key(b, view))
            return view, rows

        _view_w, warrior = lead(0)
        self.assertIn(warrior[0]["itemCode"], catalog._MELEE_WEAPONS)
        sword_at = next(i for i, b in enumerate(warrior) if b["itemCode"] == "IC_1_SWORD")
        helm_at = next(i for i, b in enumerate(warrior) if b["itemCode"] == "IC_7_HELM")
        self.assertLess(sword_at, helm_at)
        plate = {"baseId": 900040, "name": "Tower", "itemType": "ITEM_2_ARMOR", "itemCode": "IC_9_HEAVY_ARMOR",
                 "equipLoc": "EL_3_TORSO", "classMask": "IPCM_ALL_CLASSES", "dmg": [0, 0, 0, 0],
                 "armor": [9999, 9999], "effects": [], "spell": "PS_0_NONE"}
        knife = {"baseId": 900041, "name": "Shard", "itemType": "ITEM_1_WEAPON", "itemCode": "IC_1_SWORD",
                 "equipLoc": "EL_1_ONE_HANDED", "classMask": "IPCM_ALL_CLASSES", "dmg": [1, 1, 1, 2],
                 "armor": [0, 0], "effects": [], "spell": "PS_0_NONE"}
        self.assertLess(catalog.better_sort_key(knife, _view_w), catalog.better_sort_key(plate, _view_w))

        _view_a, archer = lead(4)
        self.assertEqual(archer[0]["itemCode"], "IC_3_BOW")
        self.assertLess(0, next(i for i, b in enumerate(archer) if b["itemCode"] == "IC_1_SWORD"))

        _view_m, mage_rows = lead(8)
        self.assertEqual(mage_rows[0]["itemCode"], "IC_10_STAFF")
        self.assertLess(0, next(i for i, b in enumerate(mage_rows) if b["itemCode"] == "IC_7_HELM"))
        self.assertNotEqual(mage_rows[0]["itemCode"], warrior[0]["itemCode"])
        self.assertLess(catalog.better_sort_key(
            {"baseId": 900042, "name": "Rod", "itemType": "ITEM_1_WEAPON", "itemCode": "IC_10_STAFF",
             "equipLoc": "EL_2_TWO_HANDED", "classMask": "IPCM_ALL_CLASSES", "dmg": [1, 1, 1, 2],
             "armor": [0, 0], "effects": [], "spell": "PS_0_NONE"}, _view_m),
            catalog.better_sort_key(plate, _view_m))

        _view_i, inquisitor = lead(1)
        self.assertEqual(inquisitor[0]["itemCode"], "IC_4_MACE")
        self.assertLess(0, next(i for i, b in enumerate(inquisitor) if b["itemCode"] == "IC_1_SWORD"))

        _monk, monk = lead(14)
        self.assertEqual(monk[0]["itemCode"], "IC_10_STAFF")
        self.assertLess(0, next(i for i, b in enumerate(monk) if b["itemCode"] == "IC_1_SWORD"))

        helms = [b for b in warrior if b["itemCode"] == "IC_7_HELM"]
        self.assertGreater(helms[0]["armor"][1], helms[-1]["armor"][1])

    def test_two_class_line_uses_bit_order(self):
        shugoki = catalog.GAME["full_classes"][16]["name"]
        rogue = catalog.GAME["full_classes"][18]["name"]
        self.assertEqual(catalog.game_class_line("IPCM_ROGUE|IPCM_SHUGOKI"),
                         "[%s and %s only]" % (shugoki, rogue))
        self.assertEqual(catalog.game_class_line("IPCM_ALL_CLASSES"), "")
        self.assertEqual(catalog.game_class_line(""), "")


class TestIcons(unittest.TestCase):
    def test_sprite_loc(self):
        self.assertEqual(sprite_loc(2470, False), ("th2", 2303))
        self.assertEqual(sprite_loc(2470, True), ("th2", 2303))
        self.assertEqual(sprite_loc(4, False), ("invobj1", 16))
        self.assertEqual(sprite_loc(4, True), ("objcurs", 16))

    def test_decode_is_bottom_up(self):
        pal = [(0, 0, 0)] * 256
        pal[1] = (4, 8, 12)
        opaque = bytes([28]) + bytes([1] * 28)
        clear = bytes([0xE4])
        body = struct.pack("<H", 2) + opaque + clear
        cel = struct.pack("<III", 1, 12, 12 + len(body)) + body
        w, h, rgba = decode_frame(cel, 1, pal)
        self.assertEqual((w, h), (28, 2))
        self.assertEqual(rgba[3], 0)
        self.assertEqual(rgba[28 * 4:28 * 4 + 4], bytes((4, 8, 12, 255)))

    def test_write_png_ihdr(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            write_png(path, 2, 1, bytes((1, 2, 3, 255, 4, 5, 6, 255)))
            with open(path, "rb") as f:
                data = f.read()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(data[12:16], b"IHDR")
            self.assertEqual(struct.unpack(">II", data[16:24]), (2, 1))
        finally:
            os.remove(path)


class TestLiveFrames(unittest.TestCase):
    def test_knife_frame_matches_the_game_index(self):
        from cheesestick import icons
        if not icons.diabdat_path() or not icons.mor_path():
            self.skipTest("DIABDAT.MPQ or TH4data.mor is not on this PC")
        arcs = icons._open_sources()
        try:
            pal = icons.load_palette(arcs)
            obj = icons.load_sheet("objcurs", arcs)
            th2 = icons.load_sheet("th2", arcs)
        finally:
            for arc in arcs.values():
                arc.close()
        self.assertEqual(struct.unpack_from("<I", obj, 0)[0], 179)
        self.assertEqual(struct.unpack_from("<I", th2, 0)[0], 3717)
        self.assertEqual(struct.unpack_from("<I", th2, 4)[0], 14876)
        img = decode_frame(th2, 2303, pal)
        self.assertIsNotNone(img)
        self.assertEqual(img[0], 28)
        self.assertEqual(img[1], 56)
        opaque = sum(1 for i in range(3, len(img[2]), 4) if img[2][i])
        self.assertGreater(opaque, 0)


try:
    import PySide6  # noqa
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestBrowserGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import shutil
        from cheesestick.app import MainWindow
        from tests.test_scan import make_save
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_save(self.path, "Browse", 1)
        self.w = MainWindow()
        self.warnings = []
        self.w.warn = self.warnings.append
        self.w.game_running = lambda: []
        from PySide6.QtWidgets import QMessageBox
        self.w.auto_apply_pending = QMessageBox.No
        self.w.auto_game_in_progress = "save"
        self.w.finder.settings_file = os.path.join(self.dir, "settings.json")
        self.w.open_path(self.path)
        from th4save.items import blank_item
        p = self.w.save.player
        for k in ("OnBodySlots", "BeltInventory"):
            p[k] = [blank_item() for _ in p[k]]
        p["InvUsed"] = bytes(70); p["InvItemCount"] = 0; p["TotalGold"] = 0
        p["ClassId"] = 0; p["subclassID"] = p["specializationID"] = 0; p["gameMode"] = 0
        p["CharLevel"] = 1; p["Xp"] = 0
        p["BaseStrength"], p["BaseMagic"], p["BaseDexterity"], p["BaseVitality"] = 25, 5, 15, 20
        self.w.refresh_all()
        self._shutil = shutil

    def tearDown(self):
        self.w.dirty = False
        self.w.close()
        self._shutil.rmtree(self.dir, ignore_errors=True)

    def test_filters_and_hide(self):
        browser = self.w.browser
        browser.ensure_ready()
        helm_index = browser.cat.findData("Helms")
        self.assertGreaterEqual(helm_index, 0)
        browser.cat.setCurrentIndex(helm_index)
        from PySide6.QtCore import Qt
        armors = []
        for r in range(browser.table.rowCount()):
            if browser.table.isRowHidden(r):
                continue
            bid = browser.table.item(r, 1).data(Qt.UserRole + 1)
            armors.append(int(BASE_ITEMS[bid]["armor"][1]))
        self.assertGreater(len(armors), 2)
        self.assertEqual(armors, sorted(armors, reverse=True))
        browser.cat.setCurrentIndex(0)
        named = sum(1 for b in BASE_ITEMS if b.get("name"))
        self.assertEqual(browser.table.rowCount(), named)
        self.assertEqual(browser.table.horizontalHeaderItem(1).text(), "Name")
        self.assertEqual(browser.table.horizontalHeaderItem(13).text(), "Rank")
        self.assertTrue(browser.is_visible_id(1))
        self.assertFalse(browser.is_visible_id(14))
        from PySide6.QtCore import Qt as _Qt
        first = None
        for r in range(browser.table.rowCount()):
            if browser.table.isRowHidden(r):
                continue
            first = browser.table.item(r, 1).data(_Qt.UserRole + 1)
            break
        self.assertIn(BASE_ITEMS[first]["itemCode"], catalog._MELEE_WEAPONS)
        self.assertFalse(browser.is_visible_id(398))
        browser.search.setText("short knife")
        self.assertTrue(browser.is_visible_id(1))
        self.assertFalse(browser.is_visible_id(2))
        browser.search.clear()
        browser.dmg.setValue(12)
        self.assertFalse(browser.is_visible_id(1))
        browser.dmg.setValue(0)
        cid = min(catalog.CLASSIC)
        self.assertFalse(browser.is_visible_id(cid))
        browser.hide_unusable.setChecked(False)
        self.assertTrue(browser.is_visible_id(cid))
        tip = browser.table.item(0, 1).toolTip()
        self.assertTrue(tip)

    def test_compare_refuses_mixed_groups(self):
        from cheesestick.browser import CompareDialog
        mixed = CompareDialog([B["Gold"], B["Short Knife"]])
        self.assertFalse(mixed.same_group)
        self.assertEqual(mixed.marked, set())
        self.assertIn("category and slot", mixed.note.text())
        swords = [b for b in BASE_ITEMS
                  if b.get("name") and b.get("itemCode") == "IC_1_SWORD" and b.get("equipLoc") == "EL_1_ONE_HANDED"
                  and (b.get("dmg") or [0, 0, 0, 0])[3]]
        swords.sort(key=lambda b: b["dmg"][3])
        low, high = swords[0], swords[-1]
        self.assertNotEqual(low["dmg"][3], high["dmg"][3])
        same = CompareDialog([low, high])
        self.assertTrue(same.same_group)
        self.assertIn((0, 2), same.marked)
        self.assertNotIn((0, 1), same.marked)

    def test_place_restricted_warns_and_places(self):
        from th4save.items import Inventory
        browser = self.w.browser
        browser.ensure_ready()
        browser.hide_unusable.setChecked(False)
        cid = min(catalog.CLASSIC)
        self.assertTrue(self._select(browser, cid))
        browser.add_to_inventory()
        self.assertTrue(any("Classic only" in m for m in self.warnings))
        self.assertEqual(Inventory(self.w.save.player).count, 1)

    def _select(self, browser, base_id):
        from PySide6.QtCore import Qt
        role = Qt.UserRole + 1
        for r in range(browser.table.rowCount()):
            item = browser.table.item(r, 1)
            if item is not None and item.data(role) == base_id:
                browser.table.selectRow(r)
                return True
        return False


if __name__ == "__main__":
    unittest.main()
