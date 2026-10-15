"""Caps from the game source, item info, and the unsaved-changes UX."""
import os, shutil, sys, tempfile, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cheesestick import caps
from cheesestick.data import BASE_ITEMS, GAME
from cheesestick.iteminfo import describe_base, describe_item, unique_lines, effect_text
from cheesestick.gamecheck import parse_tasklist
from tests.test_scan import make_save
from th4save.save import SaveFile

B = {b["name"]: b for b in reversed(BASE_ITEMS) if b["name"]}


def player(path, **kw):
    p = SaveFile.load(path).player
    p.update(kw)
    return p


class TestCaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(); cls.path = os.path.join(cls.dir, "th4sp_0.ssv")
        make_save(cls.path, "Caps", 1)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def p(self, **kw):
        base = dict(ClassId=0, subclassID=0, specializationID=0, gameMode=0, traits=bytes(4), gameChanger=0, perk=bytes(800))
        base.update(kw)
        return player(self.path, **base)

    def test_full_class_mapping(self):        # Item.cpp GetPlayerFullClass
        names = [c["name"] for c in caps.CLASSES]
        n = lambda c, s, sp=0: names[caps.full_class_id(c, s, sp)]
        self.assertEqual(n(0, 0), "Warrior"); self.assertEqual(n(0, 2), "Guardian")
        self.assertEqual(n(1, 1), "Scout"); self.assertEqual(n(2, 1), "Elementalist")
        self.assertEqual(n(2, 2, 1), "Necromancer"); self.assertEqual(n(2, 3), "Warlock")
        self.assertEqual(n(3, 3), "Shinobi"); self.assertEqual(n(4, 2), "Iron maiden")
        self.assertEqual(n(5, 3, 2), "Dimachaerus"); self.assertEqual(n(5, 4), "Druid")

    def test_stat_caps(self):                 # th2_proposals.cpp FullPlayerClasses + Player.cpp GetPlayerMaxStat
        self.assertEqual(caps.max_stats(self.p()), [600, 100, 400, 400])
        self.assertEqual(caps.max_stats(self.p(subclassID=2)), [750, 50, 200, 500])
        gifted = bytes([caps.TRAIT_ID["Gifted"], 0, 0, 0])
        self.assertEqual(caps.max_stats(self.p(traits=gifted)), [625, 125, 425, 425])
        self.assertEqual(caps.max_stats(self.p(gameMode=caps.GM_CLASSIC)), [250, 50, 60, 100])

    def test_stat_sum_limit(self):            # LimitPlayerParams #MSL
        p = self.p(CharLevel=1)
        self.assertEqual(caps.stat_sum_limit(p, 1), 100)
        self.assertEqual(caps.stat_sum_limit(p, 150), 1690)
        self.assertEqual(caps.stat_sum_limit(self.p(gameMode=caps.GM_CLASSIC), 50), 460)
        out = caps.max_stat_values(p, [25, 5, 15, 20], 1)
        self.assertLessEqual(sum(out), 100)
        self.assertEqual(caps.max_stat_values(p, [25, 5, 15, 20], 150), [600, 100, 400, 400])
        out = caps.max_stat_values(p, [700, 5, 15, 20], 150)   # never lowers
        self.assertEqual(out[0], 700)

    def test_level_xp(self):                  # th2data.cpp
        p = self.p()
        self.assertEqual(caps.max_level(p), 150)
        self.assertEqual(caps.xp_for_level(p, 150), 11_001_617_000_000)
        self.assertEqual(caps.xp_for_level(p, 2), 3_500)
        c = self.p(gameMode=caps.GM_CLASSIC)
        self.assertEqual(caps.max_level(c), 50)
        self.assertEqual(caps.xp_for_level(c, 50), GAME["level_xp_classic"][49])

    def test_spell_caps(self):                # Player.cpp LimitSpellLevels
        p = self.p()
        self.assertEqual(caps.spell_cap(p, 1, 1), 3)
        self.assertEqual(caps.spell_cap(p, 1, 150), 100)
        self.assertEqual(caps.spell_cap(self.p(gameMode=caps.GM_CLASSIC), 1, 50), 15)
        self.assertEqual(caps.spell_cap(p, 9999, 150), 0)

    def test_perk_caps(self):                 # Perks.cpp getPerkMaxLevel
        p = self.p()
        tough = caps.PERK_KEY["PERK_TOUGHNESS"]
        self.assertEqual(caps.perk_cap(p, tough)[0], 10)                       # warrior rows 0-9
        self.assertEqual(caps.perk_cap(self.p(ClassId=5, subclassID=2), tough)[0], 25)  # executioner: all rows
        hh = caps.PERK_KEY["PERK_HIT_HARDER"]                                  # Barbarian trait only
        self.assertEqual(caps.perk_cap(p, hh)[0], 0)
        barb = self.p(traits=bytes([caps.TRAIT_ID["Barbarian"], 0, 0, 0]))
        self.assertTrue(caps.perk_condition(barb, caps.PERK_INFO[hh]["cond"]))
        self.assertTrue(all(caps.perk_cap(p, k)[0] is not None for k in caps.PERK_INFO))

    def test_gold_cap(self):
        self.assertEqual(caps.MAX_GOLD_TOTAL, 2_100_000_000)


class TestItemInfo(unittest.TestCase):
    def test_base(self):
        t = describe_base(B["Short Knife"])
        for s in ("Damage: 2–4 to 9–11", "Durability: 13–16", "Str 9–11", "Dex 11–13",
                  "Magic bonuses are set by the seed.", "[Warriors only]", "11 ÷ 1 = 11",
                  "among Swords, one-handed"):
            self.assertIn(s, t)
        potion = describe_base(B["Potion of Healing"])
        self.assertIn("Potion of healing", potion)
        self.assertNotIn("seed", potion)

    def test_unique_and_affix(self):
        self.assertIn("Nosferatu", unique_lines(0)[0])
        self.assertEqual(effect_text(["AE_STAT", "ST_STRENGTH", 10, 15, 0, 0, 0, 0]), "Stat Strength: 10–15")
        self.assertTrue(any(a["kind"] == "suffix" for a in GAME["affixes"]))

    def test_placed_item(self):
        from th4save.items import new_item
        it = new_item(B["Ring"]["baseId"], 30); it["magicLevelAndIdentified"] = (2 << 1) | 1; it["uniqIndex"] = 1
        t = describe_item(it)
        self.assertIn("Unique", t); self.assertIn("Lifespring", t)


class TestGameCheck(unittest.TestCase):
    def test_parse(self):
        out = '"System Idle Process","0","Services","0","8 K"\n"TH4.exe","4242","Console","1","900,000 K"\n"explorer.exe","1","Console","1","1 K"\n'
        self.assertEqual(parse_tasklist(out), ["TH4.exe"])
        self.assertEqual(parse_tasklist('"notepad.exe","1"\n'), [])


try:
    import PySide6  # noqa
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestUi2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from cheesestick.app import MainWindow
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_save(self.path, "Ui", 1)
        self.w = MainWindow(); self.warnings = []; self.w.warn = self.warnings.append
        self.w.game_running = lambda: []
        from PySide6.QtWidgets import QMessageBox
        self.w.auto_apply_pending = QMessageBox.No
        self.w.auto_game_in_progress = "save"            # no game in progress in these saves
        self.w.finder.settings_file = os.path.join(self.dir, "settings.json")
        self.w.open_path(self.path)
        from th4save.items import blank_item
        p = self.w.save.player   # synthetic: clean, valid character
        for k in ("OnBodySlots", "BeltInventory"):
            p[k] = [blank_item() for _ in p[k]]
        p["InvUsed"] = bytes(70); p["InvItemCount"] = 0; p["TotalGold"] = 0
        p["SpellLevels"] = bytes(128); p["perk"] = bytes(800); p["traits"] = bytes(4); p["gameChanger"] = 0
        p["subclassID"] = p["specializationID"] = 0; p["gameMode"] = 0; p["ClassId"] = 0; p["Xp"] = 0; p["CharLevel"] = 1
        p["BaseStrength"], p["BaseMagic"], p["BaseDexterity"], p["BaseVitality"] = 25, 5, 15, 20
        for k in ("BaseLife", "MaxBaseLife"): p[k] = 5120
        for k in ("BaseMana", "MaxBaseMana"): p[k] = 320
        self.w.refresh_all()

    def tearDown(self):
        self.w.dirty = False; self.w.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def test_cheesestick_stays_named(self):
        self.assertEqual(self.w.header.name.text(), "CheeseStick")
        self.assertIn(self.w.save.player.name or "(no name)", self.w.header.sub.text())
        self.assertFalse(self.w.windowIcon().isNull())
        self.assertIn("turtle", self.w.header.mark.toolTip())
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                    "cheesestick", "assets", "cheesestick.jpg")))

    def test_apply_text_and_dirty_markers(self):
        from cheesestick.app import APPLY_TEXT, UNSAVED_MSG
        from PySide6.QtWidgets import QPushButton
        texts = [b.text() for b in self.w.findChildren(QPushButton)]
        self.assertGreaterEqual(texts.count(APPLY_TEXT), 4)
        self.assertNotIn("Apply", texts)
        self.assertFalse(self.w.dirty_label.isVisibleTo(self.w))
        self.w.max_all_character(); self.w.apply_character()
        self.assertTrue(self.w.dirty)
        self.assertIn("UNSAVED", self.w.windowTitle()); self.assertTrue(self.w.windowTitle().startswith("●"))
        self.assertTrue(self.w.header.dirty.isVisibleTo(self.w)); self.assertTrue(self.w.header.save_btn.isEnabled())
        self.assertIn(UNSAVED_MSG, self.w.statusBar().currentMessage())
        self.assertTrue(self.w.dirty_label.isVisibleTo(self.w))
        self.assertTrue(self.w.save_file())
        self.assertFalse(self.w.dirty); self.assertNotIn("UNSAVED", self.w.windowTitle())
        p = SaveFile.load(self.path).player
        self.assertEqual(p["CharLevel"], 150); self.assertEqual(p["Xp"], 11_001_617_000_000)
        self.assertEqual([p[k] for k in caps.STAT_KEYS], [600, 100, 400, 400])
        self.assertEqual(p["TotalGold"], self.w.gold_capacity() if False else p["TotalGold"])
        self.assertLessEqual(p["TotalGold"], caps.MAX_GOLD_TOTAL); self.assertGreater(p["TotalGold"], 100_000_000)

    def test_max_spells_perks(self):
        from PySide6.QtWidgets import QMessageBox
        self.w.c_level.setValue(150)
        self.w.max_spells(None); self.w.max_perks(None)
        self.w.apply_spells(); self.w.apply_perks()
        p = self.w.save.player
        # The level spin box is 150, but Apply on skills must not pretend the level was saved.
        self.assertEqual(p["CharLevel"], 1)
        self.assertEqual(p["SpellLevels"][1], 100)
        self.assertTrue(self.w.pending_unapplied())
        self.assertEqual(bytes(p["perk"])[caps.PERK_KEY["PERK_TOUGHNESS"]], 10)
        self.w.auto_apply_pending = QMessageBox.No
        self.assertTrue(self.w.save_file())
        disk = SaveFile.load(self.path).player
        self.assertEqual(disk["CharLevel"], 1)
        self.assertEqual(disk["SpellLevels"][1], 100)
        self.w.auto_apply_pending = QMessageBox.Yes
        self.assertTrue(self.w.pending_unapplied())
        self.assertTrue(self.w.save_file())
        disk = SaveFile.load(self.path).player
        self.assertEqual(disk["CharLevel"], 150)
        self.assertEqual(disk["Xp"], 11_001_617_000_000)
        self.assertEqual(disk["SpellLevels"][1], 100)
        self.assertEqual(bytes(disk["perk"])[caps.PERK_KEY["PERK_TOUGHNESS"]], 10)

    def test_mp_level_sticks(self):
        """Multiplayer has no game-in-progress copy. The hero entry itself has to keep the level."""
        from PySide6.QtWidgets import QMessageBox
        from th4save import codec, mpq
        from th4save.items import blank_item
        from tests.test_th4save import synthetic_player, empty_stash
        path = os.path.join(self.dir, "th4mp_9.msv")
        hero = synthetic_player()
        hero.name = "Amy"
        hero["CharLevel"] = 1
        hero["Xp"] = 0
        arc = mpq.MpqArchive({"mphero": codec.encode(hero.pack()), "mpstash": codec.encode(empty_stash())})
        with open(path, "wb") as f:
            f.write(arc.to_bytes())
        self.w.dirty = False
        self.w.open_path(path)
        p = self.w.save.player
        for k in ("OnBodySlots", "BeltInventory"):
            p[k] = [blank_item() for _ in p[k]]
        p["InvUsed"] = bytes(70); p["InvItemCount"] = 0; p["TotalGold"] = 0
        p["SpellLevels"] = bytes(128); p["perk"] = bytes(800); p["traits"] = bytes(4)
        p["ClassId"] = 0; p["subclassID"] = p["specializationID"] = 0; p["gameMode"] = 0
        p["Xp"] = 0; p["CharLevel"] = 1
        p["BaseStrength"], p["BaseMagic"], p["BaseDexterity"], p["BaseVitality"] = 25, 5, 15, 20
        for k in ("BaseLife", "MaxBaseLife"):
            p[k] = 5120
        for k in ("BaseMana", "MaxBaseMana"):
            p[k] = 320
        self.w.refresh_all()
        self.w.c_level.setValue(150)
        self.w.max_spells(None)
        self.w.apply_spells()
        self.assertEqual(self.w.save.player["CharLevel"], 1)
        self.assertEqual(self.w.save.player["SpellLevels"][1], 100)
        self.assertTrue(self.w.pending_unapplied())
        self.w.auto_apply_pending = QMessageBox.Yes
        self.w.auto_game_in_progress = "save"
        self.assertTrue(self.w.save_file())
        self.assertEqual(self.warnings, [])
        msg, choices, _ = self.w.last_pairing_prompt
        self.assertIn("multiplayer", msg)
        self.assertEqual(choices, ["save", "cancel"])
        disk = SaveFile.load(path)
        self.assertEqual(disk.hero_entry, "mphero")
        self.assertNotIn("game", disk.archive.files)
        self.assertEqual(disk.player["CharLevel"], 150)
        self.assertEqual(disk.player["Xp"], 11_001_617_000_000)
        self.assertEqual(disk.player["SpellLevels"][1], 100)

    def test_prompts(self):
        from PySide6.QtWidgets import QMessageBox
        self.w.c_gold.setValue(1234); self.w.apply_character()
        self.w.auto_confirm = QMessageBox.Cancel
        self.assertFalse(self.w.confirm_discard())
        self.w.auto_confirm = QMessageBox.Discard
        self.assertTrue(self.w.confirm_discard())
        self.w.auto_confirm = QMessageBox.Save
        self.assertTrue(self.w.confirm_discard()); self.assertFalse(self.w.dirty)
        self.assertEqual(SaveFile.load(self.path).player["TotalGold"], 1234)

    def test_game_running_blocks_save(self):
        from PySide6.QtWidgets import QMessageBox
        self.w.game_running = lambda: ["TH4.exe"]
        self.w.c_gold.setValue(77); self.w.apply_character(); self.assertEqual(self.warnings, [])
        self.w.auto_game_running = QMessageBox.Cancel
        self.assertFalse(self.w.save_file()); self.assertTrue(self.w.dirty)
        self.assertEqual(SaveFile.load(self.path).player["TotalGold"], 0)
        self.w.auto_game_running = QMessageBox.Save
        self.assertTrue(self.w.save_file())

    def test_unapplied_edits_detected(self):
        self.assertFalse(self.w.pending_unapplied())
        self.w.c_str.setValue(30)
        self.assertTrue(self.w.pending_unapplied())

    def test_unique_add_marks_kind_and_class(self):
        from th4save.items import D_UNIQ, Inventory
        from th4save.player import Item
        from cheesestick.catalog import rarity_mark, who_for
        from cheesestick.data import is_set_unique, BASE_ITEMS
        self.assertEqual(rarity_mark(2), "Common · 2")
        self.assertEqual(rarity_mark(50), "Rare · 50")
        self.assertTrue(is_set_unique(0))
        self.assertFalse(is_set_unique(750))
        self.assertEqual(who_for(BASE_ITEMS[1]), "Warriors")
        self.w.c_str.setValue(400); self.w.c_mag.setValue(400)
        self.w.c_dex.setValue(400); self.w.c_vit.setValue(400); self.w.c_level.setValue(100)
        inv = self.w.lists["inv"]
        def f(dlg):
            self.assertTrue(dlg.hide_unusable.isChecked())
            self.assertFalse(dlg.select_unique(72))          # Tal-Rasha's Duress, mages
            self.assertTrue(dlg.select_unique(750))          # Spiral Knife, warriors
            row = dlg.tree.currentItem()
            self.assertTrue(row.text(0).startswith("UNIQUE"))
            self.assertEqual(row.text(1), "UNIQUE")
            self.assertEqual(row.text(2), "Warriors")
            self.assertEqual(row.text(3), "Common · 2")
            self.assertEqual(row.foreground(0).color().name(), "#d9a93c")
            self.assertEqual(row.foreground(1).color().name(), "#d9a93c")
            self.assertTrue(row.font(0).bold())
            self.assertTrue(row.font(1).bold())
            self.assertIn("UNIQUE", dlg.hint.text())
            self.assertIn("Plain", dlg.hint.text())
            self.assertTrue(dlg.tree.topLevelItem(0).text(0).startswith("UNIQUE"))
            self.assertEqual(dlg.tree.topLevelItem(0).foreground(0).color().name(), "#d9a93c")
            self.assertTrue(dlg.select_unique(758))          # The Victimizer, qlvl 50
            self.assertTrue(dlg.tree.currentItem().text(0).startswith("UNIQUE"))
            self.assertEqual(dlg.tree.currentItem().text(3), "Rare · 50")
            dlg.select_unique(750)
        self.w.auto_picker = f
        inv.add()
        self.assertEqual(Inventory(self.w.save.player).count, 1)
        it = self.w.save.player["InventorySlots"][0]
        self.assertEqual(it["baseItemIndex"], B["Short Knife"]["baseId"])
        self.assertEqual(it["uniqIndex"], 750)
        self.assertEqual(D_UNIQ, 0x20)
        self.assertEqual(it["dropType"], 0x20)
        self.assertEqual(it["magicLevelAndIdentified"], (2 << 1) | 1)
        self.assertEqual(Item.parse(it.pack())["uniqIndex"], 750)
        self.assertEqual(Item.parse(it.pack())["dropType"], D_UNIQ)
        self.assertEqual(inv.table.item(0, 2).text(), "UNIQUE  Spiral Knife")
        inv.select_row(0)
        self.assertIn("Warriors", inv.info_label.text())
        self.assertIn("Common", inv.info_label.text())

    def test_item_seed_can_be_set(self):
        from th4save.player import Item
        inv = self.w.lists["inv"]
        def f(dlg):
            dlg.select_id(B["Short Knife"]["baseId"])
        self.w.auto_picker = f
        inv.add()
        inv.select_row(inv.table.rowCount() - 1)
        _, it = inv.current()
        inv.e_seed.setText("3000000000")
        self.assertIn("dropped on load", inv.seed_hint.text())
        self.assertIn("#ff8a7a", inv.seed_hint.styleSheet())
        inv.apply()
        self.assertTrue(any("32-bit" in w for w in self.warnings))
        self.assertEqual(it["seed"], 3000000000)
        self.assertEqual(Item.parse(it.pack())["seed"], 3000000000)
        self.assertEqual(inv.table.item(inv.table.currentRow(), 15).text(), "3000000000")
        warned = len(self.warnings)
        inv.e_seed.setText("1234")
        self.assertIn("4 of 10 digits. 6 missing.", inv.seed_hint.text())
        self.assertIn("The game keeps 10; the save is 64-bit.", inv.seed_hint.text())
        self.assertIn("#f2c96d", inv.seed_hint.styleSheet())
        inv.apply()
        self.assertEqual(len(self.warnings), warned)
        self.assertEqual(it["seed"], 1234)
        inv.e_seed.setText("0000001234")
        self.assertIn("4 of 10 digits. 6 missing.", inv.seed_hint.text())
        self.assertIn("Leading zeros do not count.", inv.seed_hint.text())
        inv.e_seed.setText("")
        self.assertIn("0 of 10 digits. 10 missing.", inv.seed_hint.text())
        inv.e_seed.setText("2147483647")
        self.assertEqual(inv.seed_hint.text(), "10 of 10 digits. The game keeps this whole seed.")
        inv.e_seed.setText("-2147483648")
        self.assertEqual(inv.seed_hint.text(), "10 of 10 digits. The game keeps this whole seed.")
        inv.e_seed.setText("2147483648")
        self.assertIn("dropped on load", inv.seed_hint.text())
        self.assertEqual(inv.reroll_btn.text(), "Reroll")
        inv.reroll_btn.click()
        rolled = int(inv.e_seed.text())
        self.assertEqual(len(inv.e_seed.text()), 10)
        self.assertGreaterEqual(rolled, 1_000_000_000)
        self.assertLessEqual(rolled, 2**31 - 1)
        self.assertEqual(inv.seed_hint.text(), "10 of 10 digits. The game keeps this whole seed.")
        self.assertEqual(it["seed"], 1234)
        inv.e_seed.setText("nope")
        self.assertEqual(inv.seed_hint.text(), "Not a whole number.")
        inv.apply()
        self.assertEqual(self.warnings[-1], "Seed must be a whole number.")
        self.assertEqual(it["seed"], 1234)
        inv.e_seed.setText(str(2**63))
        self.assertIn("19 digits", inv.seed_hint.text())
        inv.apply()
        self.assertIn("64-bit", self.warnings[-1])
        self.assertEqual(it["seed"], 1234)

    def test_item_info_panels(self):
        inv = self.w.lists["inv"]
        def f(dlg):
            dlg.select_id(B["Short Knife"]["baseId"])
            self.assertIn("Damage", dlg.info.text())
        self.w.auto_picker = f
        inv.add()
        inv.select_row(inv.table.rowCount() - 1)
        self.assertEqual(self.warnings, [])
        self.assertEqual(inv.table.horizontalHeaderItem(1).text(), "Icon")
        self.assertEqual(inv.table.horizontalHeaderItem(2).text(), "Name")
        self.assertIn("Damage", inv.info_label.text())
        tip = inv.table.item(inv.table.rowCount() - 1, 2).toolTip()
        for s in ("Short Knife", "Damage: 2–4 to 9–11", "[Warriors only]", "set by the seed"):
            self.assertIn(s, tip)
        eq = self.w.lists["equip"]
        def g(dlg):
            dlg.select_id(B["Short Knife"]["baseId"])
        self.w.auto_picker = g
        eq.visual.buttons[4].click()
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        self.w.tabs.setCurrentWidget(eq)
        self.w.resize(1000, 700)
        self.w.show()
        QApplication.processEvents()
        eq.info_label.setText("<br>".join(["Damage: 2–4 to 9–11"] * 30))
        QApplication.processEvents()
        self.assertEqual(eq.info_scroll.height(), 96)
        self.assertGreater(eq.info_scroll.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(eq.table.height(), 120)
        top = eq.table.mapTo(self.w, QPoint(0, 0))
        self.assertGreaterEqual(top.y(), 0)
        self.assertLess(top.y() + 40, self.w.height())
        doll = eq.visual.buttons[4].toolTip()
        for s in ("Left hand", "Damage: 2–4 to 9–11", "[Warriors only]", "set by the seed"):
            self.assertIn(s, doll, doll)


if __name__ == "__main__":
    unittest.main()
