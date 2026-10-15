"""Root-cause regression: the .ssv 'game' entry holds a second copy of the hero that the
game loads on "Load Game". Saving must update it (or remove it) so edits stick."""
import os, shutil, struct, sys, tempfile, unittest
os.environ["CHEESESTICK_NO_ICONS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from th4save import mpq, codec
from th4save.save import SaveFile
from th4save.gamestate import GameState, NAME_OFF_V30
from tests.test_scan import synthetic_player, empty_stash

REAL = "/workspace/th4/real/diag/x/th4sp_0.ssv"


def make_game_entry(p, level=2, xp=3612, ctrl_offset=1):
    b = bytearray(b"HEL4" + struct.pack(">I", 30) + bytes(4000))
    g = GameState(bytes(b))
    g["playerName"] = p.name.encode() + b"\0" + b"\xfe" * (31 - len(p.name))
    g["ClassID"] = p["ClassId"]
    for cur, base, v in (("CurStrength", "BaseStrength", 30), ("CurMagic", "BaseMagic", 5),
                         ("CurDexterity", "BaseDexterity", 15), ("CurVitality", "BaseVitality", 20)):
        g[base] = v; g[cur] = v + 3          # +3 from items
    for pre, v in (("Life", 5248), ("Mana", 384)):
        for k in ("Base", "MaxBase", "Cur", "MaxCur"):
            g[k + pre] = v
    g["CharLevel"] = level; g["controlCharLevel"] = level - ctrl_offset; g["Xp"] = xp; g["NextLevelUp"] = 9000
    return g.pack()


def make_save_with_game(path, name="Gamer"):
    from th4save.items import blank_item
    p = synthetic_player(); p.name = name; p["CharLevel"] = 2; p["Xp"] = 3612
    for k in ("OnBodySlots", "BeltInventory"):
        p[k] = [blank_item() for _ in p[k]]
    p["InvUsed"] = bytes(70); p["InvItemCount"] = 0; p["TotalGold"] = 0
    p["SpellLevels"] = bytes(128); p["perk"] = bytes(800); p["traits"] = bytes(4); p["gameChanger"] = 0
    p["subclassID"] = p["specializationID"] = 0; p["AvailableLvlPoints"] = 0
    for pre in ("Life", "Mana"):
        p["Base" + pre] = p["MaxBase" + pre] = 5248 if pre == "Life" else 384
    p["BaseStrength"], p["BaseMagic"], p["BaseDexterity"], p["BaseVitality"] = 30, 5, 15, 20
    files = {"sphero": codec.encode(p.pack()), "spstash": codec.encode(empty_stash()),
             "game": codec.encode(make_game_entry(p)), "perml000": codec.encode(b"x" * 100)}
    with open(path, "wb") as f:
        f.write(mpq.MpqArchive(files).to_bytes())


class TestGameInProgress(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_save_with_game(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_edits_reach_the_copy_the_game_loads(self):
        s = SaveFile.load(self.path)
        self.assertTrue(s.game_state().ok)
        p = s.player
        p["CharLevel"] = 20; p["Xp"] = 1_094_223
        p["BaseStrength"] = 120; p["BaseVitality"] = 80; p["AvailableLvlPoints"] = 50
        p["BaseLife"] = p["MaxBaseLife"] = 9000 * 64 // 64
        s.save_safely(self.path)
        g = SaveFile.load(self.path).game_state()
        self.assertEqual(g["CharLevel"], 20); self.assertEqual(g["controlCharLevel"], 19)
        self.assertEqual(g["Xp"], 1_094_223); self.assertEqual(g["NextLevelUp"], 1_371_778)
        self.assertEqual((g["BaseStrength"], g["CurStrength"]), (120, 123))      # item bonus kept
        self.assertEqual((g["BaseVitality"], g["CurVitality"]), (80, 83))
        self.assertEqual(g["AvailableLvlPoints"], 50)
        self.assertEqual((g["MaxBaseLife"], g["MaxCurLife"], g["CurLife"]), (9000, 9000, 9000))
        self.assertEqual(g.name, "Gamer")

    def test_untouched_hero_leaves_game_alone(self):
        s = SaveFile.load(self.path)
        before = s.decoded("game")
        s.player["CharLevel"] = 2         # no change
        s.save_safely(self.path)
        self.assertEqual(SaveFile.load(self.path).decoded("game"), before)

    def test_xp_clamped_to_next_level_up(self):
        s = SaveFile.load(self.path); s.player["Xp"] = 10**12; s.save_safely(self.path)
        self.assertEqual(SaveFile.load(self.path).game_state()["Xp"], SaveFile.load(self.path).game_state()["NextLevelUp"])

    def test_drop_game_in_progress(self):
        s = SaveFile.load(self.path)
        s.player["SpellLevels"] = bytes([0, 5]) + bytes(126)
        self.assertIn("SpellLevels", s.hero_only_changes())
        s.drop_game = True; s.save_safely(self.path)
        t = SaveFile.load(self.path)
        self.assertNotIn("game", t.archive.files); self.assertNotIn("perml000", t.archive.files)
        self.assertEqual(t.player["SpellLevels"][1], 5)

    def test_bad_layout_left_untouched(self):
        s = SaveFile.load(self.path)
        bad = s.game_plain[:NAME_OFF_V30] + b"\0" * 40 + s.game_plain[NAME_OFF_V30 + 40:]
        s.archive.files["game"] = codec.encode(bad); s.game_plain = bad
        self.assertFalse(s.game_state().ok)
        s.player["BaseStrength"] = 99
        self.assertEqual(SaveFile(s.to_bytes()).decoded("game"), bad)

    def test_fresh_session_control_level_zero(self):
        """diag2: a New Game session at level 150 had controlCharLevel 0; still a valid layout."""
        s = SaveFile.load(self.path)
        g = GameState(s.game_plain); g["CharLevel"] = 150; g["controlCharLevel"] = 0
        self.assertTrue(GameState(g.pack()).ok)

    def test_stale_save_refused(self):
        from th4save.save import StaleSaveError
        a = SaveFile.load(self.path); b = SaveFile.load(self.path)
        b.player["BaseStrength"] = 77; b.save_safely(self.path)
        a.player["BaseStrength"] = 88
        with self.assertRaises(StaleSaveError):
            a.save_safely(self.path)
        self.assertEqual(SaveFile.load(self.path).player["BaseStrength"], 77)

    @unittest.skipUnless(os.path.exists(REAL), "diagnostic save not present")
    def test_real_v0773_save(self):
        tmp = os.path.join(self.dir, "real.ssv"); shutil.copy(REAL, tmp)
        s = SaveFile.load(tmp)
        g = s.game_state(); self.assertTrue(g.ok, g.why)
        self.assertEqual((g["CharLevel"], g["Xp"]), (2, 3612))       # game copy: old hero
        self.assertEqual(s.player["CharLevel"], 20)                  # hero: edited
        s.save_safely(tmp)                                           # re-saving fixes the mismatch
        g = SaveFile.load(tmp).game_state()
        self.assertEqual((g["CharLevel"], g["Xp"], g["AvailableLvlPoints"]), (20, 1_094_223, 50))


try:
    import PySide6  # noqa
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestGameInProgressGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from cheesestick.app import MainWindow
        self.dir = tempfile.mkdtemp(); self.path = os.path.join(self.dir, "th4sp_0.ssv")
        make_save_with_game(self.path)
        from PySide6.QtWidgets import QMessageBox
        self.w = MainWindow(); self.w.warn = lambda m: self.fail(m); self.w.game_running = lambda: []
        self.w.auto_apply_pending = QMessageBox.No
        self.w.finder.settings_file = os.path.join(self.dir, "settings.json")
        self.w.open_path(self.path)

    def tearDown(self):
        self.w.dirty = False; self.w.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def test_keep_syncs_core_stats(self):
        self.w.auto_game_in_progress = "keep"
        self.w.c_str.setValue(40); self.w.apply_character()
        self.assertTrue(self.w.save_file())
        msg, choices, default = self.w.last_pairing_prompt
        self.assertEqual(choices, ["unpair", "keep", "cancel"]); self.assertEqual(default, "unpair")
        t = SaveFile.load(self.path)
        self.assertIn("game", t.archive.files); self.assertEqual(t.game_state()["BaseStrength"], 40)

    def test_unpair(self):
        self.w.auto_game_in_progress = "unpair"
        self.w.spell_table.cellWidget(0, 2).setValue(3); self.w.apply_spells()
        self.assertTrue(self.w.save_file())
        self.assertNotIn("game", SaveFile.load(self.path).archive.files)

    def test_cancel(self):
        self.w.auto_game_in_progress = "cancel"
        self.w.c_str.setValue(41); self.w.apply_character()
        self.assertFalse(self.w.save_file()); self.assertTrue(self.w.dirty)

    def test_every_save_asks_and_remembers(self):
        self.w.auto_game_in_progress = "keep"
        self.w.c_str.setValue(42); self.w.apply_character(); self.assertTrue(self.w.save_file())
        self.w.last_pairing_prompt = None
        self.w.c_str.setValue(43); self.w.apply_character(); self.assertTrue(self.w.save_file())
        self.assertIsNotNone(self.w.last_pairing_prompt)               # asked again
        self.assertEqual(self.w.last_pairing_prompt[2], "keep")         # last choice is the default
        self.w.auto_game_in_progress = "unpair"
        self.w.c_str.setValue(44); self.w.apply_character(); self.assertTrue(self.w.save_file())
        self.w.last_pairing_prompt = None                              # no game now: still asks
        self.w.c_str.setValue(45); self.w.apply_character()
        self.w.auto_game_in_progress = "save"
        self.assertTrue(self.w.save_file())
        msg, choices, _ = self.w.last_pairing_prompt
        self.assertIn("No game in progress; edits will load on New Game", msg)
        self.assertEqual(choices, ["save", "cancel"])

    def test_stale_file_never_overwritten(self):
        """diag2 root cause: the game saved while the editor had the file open; the editor's
        save then put the old copy back. Now it refuses."""
        warnings = []; self.w.warn = warnings.append
        other = SaveFile.load(self.path); other.player["BaseLife"] = 97152
        other.save_safely(self.path)                                   # "the game" writes the file
        newer = open(self.path, "rb").read()
        self.w.auto_game_in_progress = "keep"
        self.w.c_str.setValue(50); self.w.apply_character()
        self.assertFalse(self.w.save_file())
        self.assertEqual(open(self.path, "rb").read(), newer)
        self.assertTrue(warnings and "after you opened it" in warnings[0])

    def test_spell_levels_get_learned_bit(self):
        self.w.auto_game_in_progress = "unpair"
        self.w.c_level.setValue(30); self.w.apply_character()
        r = next(r for r in range(self.w.spell_table.rowCount()) if self.w.spell_table.item(r, 0).text() == "1")
        self.w.spell_table.cellWidget(r, 2).setValue(10); self.w.apply_spells()
        self.assertTrue(self.w.save_file())
        p = SaveFile.load(self.path).player
        self.assertEqual(p["SpellLevels"][1], 10); self.assertTrue(p["AvailableSpellMask"] & 1)

if __name__ == "__main__":
    unittest.main()
