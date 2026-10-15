"""MPQ v1 reader/writer for Diablo/TH4 save archives (port of th4src/src/MpqSave.cpp
writer; the reader follows Storm semantics for MPQ v1).

Save layout written by the game:
  0x000 FileHeader (32 bytes) + 72-byte zero ExFileHeader
  0x068 block table (2048 x 16 bytes, encrypted with key Hash("(block table)",3))
  0x8068 hash table (2048 x 16 bytes, encrypted with key Hash("(hash table)",3))
  0x10068 file data. Files: flags 0x80000100 (exists|implode), 4096-byte sectors,
  plain (unencrypted) sector offset table, each sector imploded only if smaller.
"""
import struct
from . import pkware

ID_MPQ = 0x1A51504D
HEADER_SIZE = 32
EXHDR_SIZE = 72
SECTORSIZEID = 3
SECTORSIZE = 512 << SECTORSIZEID
HASH_ENTRIES = BLOCK_ENTRIES = 2048
BLOCK_TBL_OFFSET = HEADER_SIZE + EXHDR_SIZE
HASH_TBL_OFFSET = BLOCK_TBL_OFFSET + BLOCK_ENTRIES * 16
FIRST_FILE_START = HASH_TBL_OFFSET + HASH_ENTRIES * 16
HASH_INDEX, HASH_CHECK0, HASH_CHECK1, HASH_ENCRYPTKEY, HASH_ENCRYPTDATA = range(5)
HASH_BLOCK_FREED, HASH_BLOCK_UNUSED = 0xFFFFFFFE, 0xFFFFFFFF
FLAG_IMPLODE, FLAG_COMPRESS, FLAG_ENCRYPTED, FLAG_FIX_KEY, FLAG_EXISTS = 0x100, 0x200, 0x10000, 0x20000, 0x80000000
_M = 0xFFFFFFFF


class MpqError(ValueError):
    pass


def _make_hash_source():
    seed = 0x100001
    tbl = [[0] * 256 for _ in range(5)]
    for l1 in range(256):
        for l2 in range(5):
            seed = (seed * 0x7D + 3) % 0x2AAAAB; r1 = seed & 0xFFFF
            seed = (seed * 0x7D + 3) % 0x2AAAAB; r2 = seed & 0xFFFF
            tbl[l2][l1] = (r1 << 16) | r2
    return tbl


HASH_SOURCE = _make_hash_source()


def mpq_hash(name: str, htype: int) -> int:
    result, adjust = 0x7FED7FED, 0xEEEEEEEE
    for ch in name.encode("latin-1"):
        if 0x61 <= ch <= 0x7A:
            ch -= 0x20
        result = ((result + adjust) ^ HASH_SOURCE[htype][ch]) & _M
        adjust = (adjust + ch + result + (adjust << 5) + 3) & _M
    return result


def _next_key(key):
    return ((key >> 11) | ((((key << 21) & _M) ^ 0xFFE00000) + 0x11111111)) & _M


def decrypt(data: bytes, key: int) -> bytes:
    n = len(data) // 4
    words = list(struct.unpack_from("<%dI" % n, data))
    adjust = 0xEEEEEEEE
    for i in range(n):
        adjust = (adjust + HASH_SOURCE[HASH_ENCRYPTDATA][key & 0xFF]) & _M
        words[i] ^= (adjust + key) & _M
        adjust = (adjust + words[i] + (adjust << 5) + 3) & _M
        key = _next_key(key)
    return struct.pack("<%dI" % n, *words) + bytes(data[n * 4:])


def encrypt(data: bytes, key: int) -> bytes:
    n = len(data) // 4
    words = list(struct.unpack_from("<%dI" % n, data))
    adjust = 0xEEEEEEEE
    for i in range(n):
        orig = words[i]
        adjust = (adjust + HASH_SOURCE[HASH_ENCRYPTDATA][key & 0xFF]) & _M
        words[i] = orig ^ ((adjust + key) & _M)
        adjust = (adjust + orig + (adjust << 5) + 3) & _M
        key = _next_key(key)
    return struct.pack("<%dI" % n, *words) + bytes(data[n * 4:])


KEY_BLOCK_TABLE = mpq_hash("(block table)", HASH_ENCRYPTKEY)
KEY_HASH_TABLE = mpq_hash("(hash table)", HASH_ENCRYPTKEY)


class MpqArchive:
    """In-memory archive: ordered dict name -> bytes. Names are not stored in
    Diablo saves (no listfile), so reading needs the candidate names."""

    def __init__(self, files=None):
        self.files = dict(files or {})

    # ---------- reading ----------
    @classmethod
    def from_bytes(cls, raw: bytes, names):
        hdr = struct.unpack_from("<3I2H4I", raw, 0)
        sig, hsize, fsize, ver, ssid, hoff, boff, hcount, bcount = hdr
        if sig != ID_MPQ:
            raise MpqError("not an MPQ archive")
        if ver != 0:
            raise MpqError("unsupported MPQ version %d" % ver)
        sector = 512 << ssid
        htab = decrypt(raw[hoff:hoff + hcount * 16], KEY_HASH_TABLE)
        btab = decrypt(raw[boff:boff + bcount * 16], KEY_BLOCK_TABLE)
        arc = cls()
        arc.header = hdr
        arc.raw_size = len(raw)
        used = {struct.unpack_from("<I", htab, e * 16 + 12)[0] for e in range(hcount)}
        used = {b for b in used if b < bcount}
        found = set()
        for name in names:
            idx = cls._find(htab, hcount, name)
            if idx is None:
                continue
            blk = struct.unpack_from("<4I", btab, idx * 16)
            arc.files[name] = cls._read_file(raw, blk, sector, name)
            found.add(idx)
        arc.unknown_blocks = sorted(used - found)  # entries whose name we could not guess
        return arc

    @staticmethod
    def _find(htab, hcount, name):
        h0, c0, c1 = (mpq_hash(name, t) for t in (HASH_INDEX, HASH_CHECK0, HASH_CHECK1))
        e = h0 & (hcount - 1)
        for _ in range(hcount):
            a, b, lcid, block = struct.unpack_from("<4I", htab, e * 16)
            if block == HASH_BLOCK_UNUSED:
                return None
            if a == c0 and b == c1 and lcid == 0 and block != HASH_BLOCK_FREED:
                return block
            e = (e + 1) & (hcount - 1)
        return None

    @staticmethod
    def _read_file(raw, blk, sector, name):
        offset, salloc, sfile, flags = blk
        if not flags & FLAG_EXISTS:
            raise MpqError("block for %r not in use" % name)
        if flags & FLAG_ENCRYPTED:
            raise MpqError("encrypted file data not supported (saves are unencrypted)")
        if not flags & (FLAG_IMPLODE | FLAG_COMPRESS):
            return bytes(raw[offset:offset + sfile])
        nsec = (sfile + sector - 1) // sector
        table = struct.unpack_from("<%dI" % (nsec + 1), raw, offset)
        out = bytearray()
        for s in range(nsec):
            chunk = raw[offset + table[s]:offset + table[s + 1]]
            want = min(sector, sfile - s * sector)
            if len(chunk) < want:
                if flags & FLAG_IMPLODE:
                    chunk = pkware.explode(chunk)
                else:
                    raise MpqError("multi-compression (0x200) sectors not supported")
            if len(chunk) != want:
                raise MpqError("sector %d of %r has size %d, expected %d" % (s, name, len(chunk), want))
            out += chunk
        return bytes(out)

    # ---------- writing ----------
    def to_bytes(self) -> bytes:
        htab = bytearray(b"\xff" * (HASH_ENTRIES * 16))
        btab = bytearray(BLOCK_ENTRIES * 16)
        body = bytearray()
        pos = FIRST_FILE_START
        for bi, (name, data) in enumerate(self.files.items()):
            h0, c0, c1 = (mpq_hash(name, t) for t in (HASH_INDEX, HASH_CHECK0, HASH_CHECK1))
            e = h0 & (HASH_ENTRIES - 1)
            while struct.unpack_from("<I", htab, e * 16 + 12)[0] != HASH_BLOCK_UNUSED:
                e = (e + 1) & (HASH_ENTRIES - 1)
            struct.pack_into("<4I", htab, e * 16, c0, c1, 0, bi)
            nsec = (len(data) + SECTORSIZE - 1) // SECTORSIZE
            tsize = (nsec + 1) * 4
            secs, offs, cur = [], [], tsize
            for s in range(nsec):
                plain = data[s * SECTORSIZE:(s + 1) * SECTORSIZE]
                comp = pkware.implode(plain)
                chunk = comp if len(comp) < len(plain) else plain
                offs.append(cur); secs.append(chunk); cur += len(chunk)
            offs.append(cur)
            fdata = struct.pack("<%dI" % (nsec + 1), *offs) + b"".join(secs)
            struct.pack_into("<4I", btab, bi * 16, pos, len(fdata), len(data), FLAG_IMPLODE | FLAG_EXISTS)
            body += fdata
            pos += len(fdata)
        total = FIRST_FILE_START + len(body)
        hdr = struct.pack("<3I2H4I", ID_MPQ, HEADER_SIZE, total, 0, SECTORSIZEID,
                          HASH_TBL_OFFSET, BLOCK_TBL_OFFSET, HASH_ENTRIES, BLOCK_ENTRIES)
        return (hdr + bytes(EXHDR_SIZE) + encrypt(bytes(btab), KEY_BLOCK_TABLE)
                + encrypt(bytes(htab), KEY_HASH_TABLE) + bytes(body))


def th4_candidate_names():
    """Every entry name the TH4 source can write into a save archive."""
    names = []
    for p in ("sp", "mp", "cl", "cp", "drk", "ob"):
        names += [p + "hero", p + "stash"]
    names += ["hero", "stash", "game", "wpnswp", "spellhotkeys", "additionalherodata", "trans"]
    names += ["templ%03d" % i for i in range(1000)] + ["perml%03d" % i for i in range(1000)]
    return names
