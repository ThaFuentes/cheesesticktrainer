"""Unit tests. C cross-checks run the ORIGINAL th4src routines via tests/cref/driver
(built by tests/cref/build.sh); they are skipped if the driver isn't built."""
import os, random, struct, subprocess, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from th4save import codec, mpq, pkware
from th4save.player import PlayerInfo, Item, PLAYER_INFO_SIZE, OFFSETS, SIGNATURE_HEL4
from th4save.save import SaveFile

DRIVER = os.path.join(os.path.dirname(__file__), "cref", "driver")
HAVE_C = os.path.exists(DRIVER)
rng = random.Random(1234)


def C(*args, data=b"", check=True):
    p = subprocess.run([DRIVER, *args], input=data, capture_output=True)
    if check and p.returncode:
        raise RuntimeError("driver %s failed rc=%d" % (args, p.returncode))
    return p.stdout


def rbytes(n):
    return bytes(rng.getrandbits(8) for _ in range(n))


def samples():
    return [b"x", rbytes(63), rbytes(64), rbytes(65), rbytes(1000), b"A" * 5000,
            rbytes(PLAYER_INFO_SIZE), bytes(PLAYER_INFO_SIZE)]


def empty_stash():
    return struct.pack(">II", 0x48454C34, 30) + (struct.pack(">I", 0) + bytes(260)) * 100


def synthetic_player():
    b = bytearray(rbytes(PLAYER_INFO_SIZE))
    struct.pack_into("<II", b, 0, SIGNATURE_HEL4, 27)
    p = PlayerInfo.parse(bytes(b))
    p.name = "CheeseStick"
    p["ClassId"] = 0; p["CharLevel"] = 12; p["TotalGold"] = 4321; p["gameMode"] = 0
    return p


class TestCodec(unittest.TestCase):
    def test_roundtrip(self):
        for d in samples():
            e = codec.encode(d)
            self.assertEqual(len(e), codec.encoded_size(len(d)))
            self.assertEqual(codec.decode(e), d)

    def test_tamper_detected(self):
        e = bytearray(codec.encode(rbytes(500))); e[10] ^= 1
        with self.assertRaises(codec.CodecError):
            codec.decode(bytes(e))

    def test_wrong_password(self):
        with self.assertRaises(codec.CodecError):
            codec.decode(codec.encode(b"hello" * 40), b"other")

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_encode_matches_c(self):
        for d in samples():
            self.assertEqual(codec.encode(d), C("encode", "xrgyrkj1", data=d))
            self.assertEqual(codec.encode(d, b"abc"), C("encode", "abc", data=d))

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_c_decodes_python(self):
        for d in samples():
            self.assertEqual(C("decode", "xrgyrkj1", data=codec.encode(d)), d)


class TestMpqPrimitives(unittest.TestCase):
    NAMES = ["(hash table)", "(block table)", "sphero", "spstash", "game", "perml005", "templ012", "wpnswp"]

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_hash_matches_c(self):
        for n in self.NAMES:
            for t in range(4):
                self.assertEqual(mpq.mpq_hash(n, t), int(C("hash", n, str(t)), 16), (n, t))

    def test_known_keys(self):  # standard MPQ constants
        self.assertEqual(mpq.KEY_HASH_TABLE, 0xC3AF3770)
        self.assertEqual(mpq.KEY_BLOCK_TABLE, 0xEC83B3A3)

    def test_crypt_roundtrip(self):
        d = rbytes(4096)
        self.assertEqual(mpq.decrypt(mpq.encrypt(d, 0x1234), 0x1234), d)

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_crypt_matches_c(self):
        d = rbytes(4096)
        for k in (0, 0xC3AF3770, 0xDEADBEEF):
            self.assertEqual(mpq.encrypt(d, k), C("encrypt", "%x" % k, data=d))
            self.assertEqual(mpq.decrypt(d, k), C("decrypt", "%x" % k, data=d))


class TestPkware(unittest.TestCase):
    DATA = None

    def data(self):
        return [b"", b"a", rbytes(4096), b"abcabcabcabd" * 300, bytes(4096),
                codec.encode(bytes(PLAYER_INFO_SIZE))[:4096], b"The Hell 4 save " * 256]

    def test_roundtrip(self):
        for d in self.data():
            for t in (pkware.CMP_BINARY, pkware.CMP_ASCII):
                self.assertEqual(pkware.explode(pkware.implode(d, t)), d)

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_python_explodes_c(self):
        for d in self.data():
            for t in ("0", "1"):
                self.assertEqual(pkware.explode(C("implode", t, data=d)), d)

    @unittest.skipUnless(HAVE_C, "C driver not built")
    def test_c_explodes_python(self):
        # pklib rejects a 0-byte stream as CMP_BAD_DATA; the game never implodes empty sectors.
        for d in [x for x in self.data() if x]:
            for t in (0, 1):
                self.assertEqual(C("explode", data=pkware.implode(d, t)), d)


class TestPlayer(unittest.TestCase):
    def test_offsets(self):
        exp = {"CharName": 24, "ClassId": 56, "BaseStrength": 59, "CharLevel": 67, "Xp": 71,
               "TotalGold": 79, "SpellLevels": 99, "OnBodySlots": 243, "InventorySlots": 1331,
               "BeltInventory": 5882, "TalismanSlots": 6394, "traits": 10949, "perk": 10973,
               "gameMode": 11797}
        for k, v in exp.items():
            self.assertEqual(OFFSETS[k], v, k)

    def test_exact_roundtrip(self):
        b = bytearray(rbytes(PLAYER_INFO_SIZE)); struct.pack_into("<II", b, 0, SIGNATURE_HEL4, 27)
        self.assertEqual(PlayerInfo.parse(bytes(b)).pack(), bytes(b))

    def test_edit(self):
        p = synthetic_player(); p["TotalGold"] = 999999
        q = PlayerInfo.parse(p.pack())
        self.assertEqual(q["TotalGold"], 999999); self.assertEqual(q.name, "CheeseStick")
        self.assertEqual(q.pack()[79:83], struct.pack("<I", 999999))


class TestOffsetsAgainstGcc(unittest.TestCase):
    """Compiles PlayerInfo_v26/ItemInfo64 extracted verbatim from th4src and compares offsetof()."""
    @unittest.skipUnless(HAVE_C, "C toolchain/driver not available")
    def test_gcc_offsets(self):
        out = subprocess.run([os.path.join(os.path.dirname(DRIVER), "offsets_gen.sh")],
                             capture_output=True, text=True, check=True).stdout.split("\n")
        vals = {}
        for line in out:
            parts = line.split()
            for i in range(0, len(parts) - 1, 2):
                vals[parts[i]] = int(parts[i + 1])
        self.assertEqual(vals["size"], PLAYER_INFO_SIZE)
        self.assertEqual(vals["item"], 64)
        for k, v in vals.items():
            if k in OFFSETS:
                self.assertEqual(OFFSETS[k], v, k)


class TestArchive(unittest.TestCase):
    def build(self):
        p = synthetic_player()
        arc = mpq.MpqArchive({"sphero": codec.encode(p.pack()),
                              "spstash": codec.encode(empty_stash()),
                              "game": codec.encode(b"G" * 20000),
                              "perml001": codec.encode(rbytes(3000))})
        return arc.to_bytes(), p

    def test_save_roundtrip(self):
        raw, p = self.build()
        s = SaveFile(raw)
        self.assertEqual(s.hero_entry, "sphero")
        self.assertEqual(s.player.pack(), p.pack())
        self.assertEqual(s.archive.unknown_blocks, [])
        s2 = SaveFile(s.to_bytes())
        for n in s.archive.files:
            self.assertEqual(s2.decoded(n), s.decoded(n))

    def test_edit_persists(self):
        raw, _ = self.build()
        s = SaveFile(raw); s.player["CharLevel"] = 50; s.player["TotalGold"] = 777
        s2 = SaveFile(s.to_bytes())
        self.assertEqual((s2.player["CharLevel"], s2.player["TotalGold"]), (50, 777))

    def test_layout_constants(self):
        raw, _ = self.build()
        sig, hsize, fsize, ver, ssid, hoff, boff, hc, bc = struct.unpack_from("<3I2H4I", raw)
        self.assertEqual((sig, hsize, fsize, ver, ssid, hoff, boff, hc, bc),
                         (0x1A51504D, 32, len(raw), 0, 3, 0x8068, 0x68, 2048, 2048))


REAL = os.path.join("/workspace/th4/real", "th4sp_0_v2.ssv")


class TestV30AndHelpers(unittest.TestCase):
    def test_tail_preserved(self):
        b = bytearray(rbytes(PLAYER_INFO_SIZE + 19)); struct.pack_into("<II", b, 0, SIGNATURE_HEL4, 30)
        p = PlayerInfo.parse(bytes(b))
        self.assertEqual(len(p["tail_unknown"]), 19)
        self.assertEqual(p.pack(), bytes(b))

    def test_inventory_add_remove(self):
        from th4save.items import Inventory, new_item
        p = synthetic_player(); p["InvUsed"] = bytes(70); p["InvItemCount"] = 0
        inv = Inventory(p)
        a = inv.add(new_item(1, 30), 1, 3); b = inv.add(new_item(0, 30, amount=500)); c = inv.add(new_item(395, 30), 2, 2)
        self.assertEqual(inv.size_of(a), (1, 3)); self.assertEqual(inv.size_of(c), (2, 2))
        self.assertEqual(inv.recompute_gold(), 500)
        inv.remove(a)
        g = inv.grid()
        self.assertEqual(inv.count, 2); self.assertNotIn(3, [abs(x) for x in g])
        self.assertEqual(inv.items()[0]["baseItemIndex"], 0)
        self.assertEqual(inv.size_of(1), (2, 2))

    def test_stash_roundtrip(self):
        from th4save.stash import Stash
        raw = empty_stash()
        st = Stash(raw); self.assertEqual(st.pack(), raw)
        st.tabs[0]["items"].append(Item.parse(rbytes(64))); st.tabs[0]["flags"][0] = 1
        self.assertEqual(Stash(st.pack()).pack(), st.pack())

    @unittest.skipUnless(os.path.exists(REAL), "real save not present")
    def test_real_save(self):
        s = SaveFile.load(REAL)
        self.assertEqual(s.player["version"], 30)
        self.assertEqual(len(s.hero_plain), 11817)
        self.assertEqual(s.player.pack(), s.hero_plain)
        self.assertEqual(s.stash.pack(), s.stash_plain)
        s2 = SaveFile(s.to_bytes())
        for n in s.archive.files:
            self.assertEqual(s2.decoded(n), s.decoded(n), n)


if __name__ == "__main__":
    unittest.main()
