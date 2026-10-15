"""Port of th4src/src/SHA.cpp + CodeSave.cpp (Diablo 1 save codec).

Faithful quirks:
* Blizzard "SHA1": no rotate-left in the message schedule, signed (arithmetic)
  right shift inside the rotate macro S(n,x), no padding/finalisation; the
  "digest" is just the 5 state words read as little-endian bytes.
* Key setup uses MSVC rand() seeded with 0x7058.
* Trailer AppendRec: u32 checkValue, u8 version(=0), u8 lastBlockSize, u16 reserved.
"""
import struct

BLOCK = 64
DIGEST = 20
SAVE_GAME_KEY = 0x7058
PASSWORD_SP = b"xrgyrkj1"
KEYREC_SIZE = 3 * 8 * 2 + 3 * 8 + 64  # ideakey[3][8] u16, deskey[3][8], shaInitVect[64] = 136
_M = 0xFFFFFFFF


class CodecError(ValueError):
    pass


def _s32(x):
    x &= _M
    return x - 0x100000000 if x & 0x80000000 else x


def _rol_signed(n, x):
    """((x << n) | (x >> (32-n))) on a signed 32-bit int (arithmetic shift!)."""
    x = _s32(x)
    return ((x << n) | (x >> (32 - n))) & _M


class BlizzSha:
    __slots__ = ("digest", "count_lo", "count_hi")

    def __init__(self):
        self.digest = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
        self.count_lo = 0
        self.count_hi = 0

    def last_hash(self) -> bytes:
        return struct.pack("<5I", *self.digest)

    def update(self, block: bytes):
        assert len(block) % BLOCK == 0
        size = len(block)
        if ((self.count_lo + (size << 3)) & _M) < self.count_lo:
            self.count_hi = (self.count_hi + 1) & _M
        self.count_lo = (self.count_lo + (size << 3)) & _M
        self.count_hi = (self.count_hi + (size >> 29)) & _M
        for off in range(0, size, BLOCK):
            self._transform(block[off:off + BLOCK])

    def _transform(self, data: bytes):
        w = list(struct.unpack("<16I", data)) + [0] * 64
        for i in range(16, 80):
            w[i] = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]  # no rotate (Blizzard bug)
        a, b, c, d, e = self.digest
        for i in range(80):
            if i < 20:
                f = ((~b) & d) | (b & c); k = 0x5A827999
            elif i < 40:
                f = b ^ c ^ d; k = 0x6ED9EBA1
            elif i < 60:
                f = (b & c) | (d & (b | c)); k = 0x8F1BBCDC
            else:
                f = b ^ c ^ d; k = 0xCA62C1D6
            temp = (_rol_signed(5, a) + (f & _M) + e + k + w[i]) & _M
            e = d; d = c; c = _rol_signed(30, b); b = a; a = temp
        dg = self.digest
        self.digest = [(dg[0] + a) & _M, (dg[1] + b) & _M, (dg[2] + c) & _M,
                       (dg[3] + d) & _M, (dg[4] + e) & _M]


def msvc_rand_bytes(seed: int, n: int) -> bytes:
    out = bytearray()
    s = seed & _M
    for _ in range(n):
        s = (s * 214013 + 2531011) & _M
        out.append(((s >> 16) & 0x7FFF) & 0xFF)
    return bytes(out)


def _init_ctx(password: bytes) -> BlizzSha:
    keyset = bytearray(msvc_rand_bytes(SAVE_GAME_KEY, KEYREC_SIZE))
    pw = password.split(b"\0", 1)[0]
    if not pw:
        raise CodecError("empty password")
    orig = bytes(pw[i % len(pw)] for i in range(BLOCK))
    h = BlizzSha(); h.update(orig); hashed = h.last_hash()
    for i in range(KEYREC_SIZE):
        keyset[i] ^= hashed[i % DIGEST]
    ctx = BlizzSha()
    ctx.update(bytes(keyset[KEYREC_SIZE - 64:]))  # shaInitVect (ctx 1,2 unused by codec)
    return ctx


def encoded_size(n: int) -> int:
    if n & (BLOCK - 1):
        n += BLOCK - (n & (BLOCK - 1))
    return n + 8


def encode(plain: bytes, password: bytes = PASSWORD_SP) -> bytes:
    ctx = _init_ctx(password)
    out = bytearray()
    last = 0
    for off in range(0, len(plain), BLOCK):
        chunk = plain[off:off + BLOCK]
        last = len(chunk)
        buf = chunk + b"\0" * (BLOCK - last)
        hsh = ctx.last_hash()
        ctx.update(buf)
        out += bytes(buf[i] ^ hsh[i % DIGEST] for i in range(BLOCK))
    check = struct.unpack_from("<I", ctx.last_hash())[0]
    out += struct.pack("<IBBH", check, 0, last, 0)
    return bytes(out)


def decode(data: bytes, password: bytes = PASSWORD_SP) -> bytes:
    if len(data) <= 8 or (len(data) - 8) % BLOCK:
        raise CodecError("bad encoded length %d" % len(data))
    ctx = _init_ctx(password)
    body = len(data) - 8
    out = bytearray()
    for off in range(0, body, BLOCK):
        hsh = ctx.last_hash()
        buf = bytes(data[off + i] ^ hsh[i % DIGEST] for i in range(BLOCK))
        ctx.update(buf)
        out += buf
    check, version, last, _ = struct.unpack_from("<IBBH", data, body)
    if version > 0:
        raise CodecError("unsupported codec version %d" % version)
    if check != struct.unpack_from("<I", ctx.last_hash())[0]:
        raise CodecError("checksum mismatch (wrong password or corrupt data)")
    return bytes(out[:body + last - BLOCK])
