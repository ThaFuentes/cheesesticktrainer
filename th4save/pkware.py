"""Pure-Python PKWARE DCL implode/explode (tables from th4src/lib/pklib/implode.cpp).

The game compresses each 4096-byte MPQ sector with CMP_BINARY, dict 4096.
explode() handles binary and ASCII streams; implode() emits binary or ASCII.
The compressed bytes need not match pklib bit-for-bit -- only be valid DCL.
"""
CMP_BINARY, CMP_ASCII = 0, 1

DIST_BITS = bytes([
    0x02,0x04,0x04,0x05,0x05,0x05,0x05,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,0x06,
    0x06,0x06,0x06,0x06,0x06,0x06,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,0x07,
    0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08,0x08])
DIST_CODE = bytes([
    0x03,0x0D,0x05,0x19,0x09,0x11,0x01,0x3E,0x1E,0x2E,0x0E,0x36,0x16,0x26,0x06,0x3A,
    0x1A,0x2A,0x0A,0x32,0x12,0x22,0x42,0x02,0x7C,0x3C,0x5C,0x1C,0x6C,0x2C,0x4C,0x0C,
    0x74,0x34,0x54,0x14,0x64,0x24,0x44,0x04,0x78,0x38,0x58,0x18,0x68,0x28,0x48,0x08,
    0xF0,0x70,0xB0,0x30,0xD0,0x50,0x90,0x10,0xE0,0x60,0xA0,0x20,0xC0,0x40,0x80,0x00])
EX_LEN_BITS = [0,0,0,0,0,0,0,0,1,2,3,4,5,6,7,8]
LEN_BITS = [3,2,3,3,4,4,4,5,5,5,5,6,6,6,7,7]
LEN_CODE = [0x05,0x03,0x01,0x06,0x0A,0x02,0x0C,0x14,0x04,0x18,0x08,0x30,0x10,0x20,0x40,0x00]
LEN_BASE = [0,1,2,3,4,5,6,7,8,10,14,22,38,70,134,262]  # rep_length = base + extra + 2
CH_BITS_ASC = bytes.fromhex(
    "0b0c0c0c0c0c0c0c0c08070c0c070c0c0c0c0c0c0c0c0c0c0c0c0d0c0c0c0c0c"
    "040a080c0a0c0a08070708090706070807060707070708070708080c0b07090b"
    "0c06070606050708080 60b090607060607 0b06060607090809090b080b090c08".replace(" ", "")
    + "0c05060606050606060 50b07050605050 60a050505050807080 80a0b0b0c0c0c".replace(" ", "")
    + "0d" * 48 + "0c" * 48
    + "0d0c0d0d0d0c0d0d0d0c0d0d0d0d0c0d0d0d0c0c0c0d0d0d0d0d0d0d0d0d0d0d")
CH_CODE_ASC = [
    0x0490,0x0FE0,0x07E0,0x0BE0,0x03E0,0x0DE0,0x05E0,0x09E0,0x01E0,0x00B8,0x0062,0x0EE0,0x06E0,0x0022,0x0AE0,0x02E0,
    0x0CE0,0x04E0,0x08E0,0x00E0,0x0F60,0x0760,0x0B60,0x0360,0x0D60,0x0560,0x1240,0x0960,0x0160,0x0E60,0x0660,0x0A60,
    0x000F,0x0250,0x0038,0x0260,0x0050,0x0C60,0x0390,0x00D8,0x0042,0x0002,0x0058,0x01B0,0x007C,0x0029,0x003C,0x0098,
    0x005C,0x0009,0x001C,0x006C,0x002C,0x004C,0x0018,0x000C,0x0074,0x00E8,0x0068,0x0460,0x0090,0x0034,0x00B0,0x0710,
    0x0860,0x0031,0x0054,0x0011,0x0021,0x0017,0x0014,0x00A8,0x0028,0x0001,0x0310,0x0130,0x003E,0x0064,0x001E,0x002E,
    0x0024,0x0510,0x000E,0x0036,0x0016,0x0044,0x0030,0x00C8,0x01D0,0x00D0,0x0110,0x0048,0x0610,0x0150,0x0060,0x0088,
    0x0FA0,0x0007,0x0026,0x0006,0x003A,0x001B,0x001A,0x002A,0x000A,0x000B,0x0210,0x0004,0x0013,0x0032,0x0003,0x001D,
    0x0012,0x0190,0x000D,0x0015,0x0005,0x0019,0x0008,0x0078,0x00F0,0x0070,0x0290,0x0410,0x0010,0x07A0,0x0BA0,0x03A0,
    0x0240,0x1C40,0x0C40,0x1440,0x0440,0x1840,0x0840,0x1040,0x0040,0x1F80,0x0F80,0x1780,0x0780,0x1B80,0x0B80,0x1380,
    0x0380,0x1D80,0x0D80,0x1580,0x0580,0x1980,0x0980,0x1180,0x0180,0x1E80,0x0E80,0x1680,0x0680,0x1A80,0x0A80,0x1280,
    0x0280,0x1C80,0x0C80,0x1480,0x0480,0x1880,0x0880,0x1080,0x0080,0x1F00,0x0F00,0x1700,0x0700,0x1B00,0x0B00,0x1300,
    0x0DA0,0x05A0,0x09A0,0x01A0,0x0EA0,0x06A0,0x0AA0,0x02A0,0x0CA0,0x04A0,0x08A0,0x00A0,0x0F20,0x0720,0x0B20,0x0320,
    0x0D20,0x0520,0x0920,0x0120,0x0E20,0x0620,0x0A20,0x0220,0x0C20,0x0420,0x0820,0x0020,0x0FC0,0x07C0,0x0BC0,0x03C0,
    0x0DC0,0x05C0,0x09C0,0x01C0,0x0EC0,0x06C0,0x0AC0,0x02C0,0x0CC0,0x04C0,0x08C0,0x00C0,0x0F40,0x0740,0x0B40,0x0340,
    0x0300,0x0D40,0x1D00,0x0D00,0x1500,0x0540,0x0500,0x1900,0x0900,0x0940,0x1100,0x0100,0x1E00,0x0E00,0x0140,0x1600,
    0x0600,0x1A00,0x0E40,0x0640,0x0A40,0x0A00,0x1200,0x0200,0x1C00,0x0C00,0x1400,0x0400,0x1800,0x0800,0x1000,0x0000]
assert len(CH_BITS_ASC) == 256 and len(CH_CODE_ASC) == 256


class PkError(ValueError):
    pass


def _lookup(bits, codes):
    return {(b, c): i for i, (b, c) in enumerate(zip(bits, codes))}


_LEN_LUT = _lookup(LEN_BITS, LEN_CODE)
_DIST_LUT = _lookup(DIST_BITS, DIST_CODE)
_ASC_LUT = _lookup(CH_BITS_ASC, CH_CODE_ASC)


class _BitReader:
    def __init__(self, data, pos):
        self.data, self.pos, self.buf, self.n = data, pos, 0, 0

    def bits(self, k):
        while self.n < k:
            if self.pos >= len(self.data):
                raise PkError("unexpected end of compressed data")
            self.buf |= self.data[self.pos] << self.n
            self.pos += 1; self.n += 8
        v = self.buf & ((1 << k) - 1)
        self.buf >>= k; self.n -= k
        return v

    def huff(self, lut, maxbits):
        code = 0
        for n in range(1, maxbits + 1):
            code |= self.bits(1) << (n - 1)
            hit = lut.get((n, code))
            if hit is not None:
                return hit
        raise PkError("bad huffman code")


def explode(data: bytes) -> bytes:
    if len(data) < 3:
        raise PkError("too short")
    ctype, dbits = data[0], data[1]
    if ctype not in (CMP_BINARY, CMP_ASCII):
        raise PkError("bad compression type")
    if dbits not in (4, 5, 6):
        raise PkError("bad dictionary size")
    r = _BitReader(data, 2)
    out = bytearray()
    while True:
        if r.bits(1):
            sym = r.huff(_LEN_LUT, 7)
            length = LEN_BASE[sym] + r.bits(EX_LEN_BITS[sym]) + 2
            if length == 519:
                break
            hi = r.huff(_DIST_LUT, 8)
            if length == 2:
                dist = (hi << 2) | r.bits(2)
            else:
                dist = (hi << dbits) | r.bits(dbits)
            src = len(out) - dist - 1
            if src < 0:
                raise PkError("distance too far back")
            for i in range(length):
                out.append(out[src + i])
        else:
            out.append(r.bits(8) if ctype == CMP_BINARY else r.huff(_ASC_LUT, 13))
    return bytes(out)


class _BitWriter:
    def __init__(self):
        self.out, self.buf, self.n = bytearray(), 0, 0

    def put(self, nbits, value):
        self.buf |= (value & ((1 << nbits) - 1)) << self.n
        self.n += nbits
        while self.n >= 8:
            self.out.append(self.buf & 0xFF); self.buf >>= 8; self.n -= 8

    def finish(self):
        if self.n:
            self.out.append(self.buf & 0xFF)
        return bytes(self.out)


def _len_code(length):
    v = length - 2
    for sym in range(15, -1, -1):
        if v >= LEN_BASE[sym]:
            return sym, v - LEN_BASE[sym]
    raise AssertionError


def implode(data: bytes, ctype: int = CMP_BINARY, dict_size: int = 4096) -> bytes:
    dbits = {1024: 4, 2048: 5, 4096: 6}[dict_size]
    w = _BitWriter()
    w.out += bytes([ctype, dbits])

    def lit(b):
        if ctype == CMP_BINARY:
            w.put(9, b << 1)
        else:
            w.put(CH_BITS_ASC[b] + 1, CH_CODE_ASC[b] << 1)

    def match(length, dist):  # dist is (distance - 1)
        sym, extra = _len_code(length)
        w.put(1, 1); w.put(LEN_BITS[sym], LEN_CODE[sym]); w.put(EX_LEN_BITS[sym], extra)
        if length == 2:
            w.put(DIST_BITS[dist >> 2], DIST_CODE[dist >> 2]); w.put(2, dist & 3)
        else:
            w.put(DIST_BITS[dist >> dbits], DIST_CODE[dist >> dbits]); w.put(dbits, dist & ((1 << dbits) - 1))

    n = len(data)
    heads = {}
    i = 0

    def insert(p):
        if p + 2 < n + 1 and p + 1 < n:
            heads.setdefault(data[p:p + 2], []).append(p)

    while i < n:
        best_len, best_d = 0, 0
        if i + 1 < n:
            cand = heads.get(data[i:i + 2], ())
            for p in reversed(cand[-64:]):
                d = i - p
                if d > dict_size:
                    break
                l = 2
                lim = min(518, n - i)
                while l < lim and data[p + l] == data[i + l]:
                    l += 1
                if l > best_len:
                    best_len, best_d = l, d
                    if l == lim:
                        break
        if best_len == 2 and best_d - 1 >= 0x100:
            best_len = 0
        if best_len >= 2:
            match(best_len, best_d - 1)
            for k in range(best_len):
                insert(i + k)
            i += best_len
        else:
            lit(data[i]); insert(i); i += 1
    match_end = 519
    sym, extra = _len_code(match_end)
    w.put(1, 1); w.put(LEN_BITS[sym], LEN_CODE[sym]); w.put(EX_LEN_BITS[sym], extra)
    return w.finish()
