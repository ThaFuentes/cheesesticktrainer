"""Runtime item icons from Christopher's own Diablo install.

objcurs.cel lives in DIABDAT.MPQ. The Hell sprites live in TH4data.mor.
Both stay where the game installed them. Decoded frames are cached as PNG
under %APPDATA%\\CheeseStickTrainer\\icons and are never shipped with the editor.
Missing files, or a frame that will not decode, fall back to a letter mark.
"""
import os, struct, zlib
from th4save.mpq import (
    FLAG_COMPRESS, FLAG_ENCRYPTED, FLAG_EXISTS, FLAG_FIX_KEY, FLAG_IMPLODE,
    HASH_BLOCK_FREED, HASH_BLOCK_UNUSED, HASH_CHECK0, HASH_CHECK1, HASH_ENCRYPTKEY,
    HASH_INDEX, ID_MPQ, KEY_BLOCK_TABLE, KEY_HASH_TABLE, MpqError, decrypt, mpq_hash)
from th4save import pkware
from .data import BASE_ITEMS

# GetItemSprites (Item.cpp): cursor id is GraphicValue + 12. That id is a 1-based
# dword index into the CEL (dword 0 is the frame count). TH2 starts after 179.
_CLASSIC_REMAP = {
    314 + 168: ("objcurs", 32 + 12),
    496 + 168: ("objcurs", 39 + 12),
    449 + 168: ("objcurs", 35 + 12),
    497 + 168: ("objcurs", 12),
    37: ("invobj1", 36 + 12),
    179 + 168: ("th2", 241 + 168 + 12 - 179),
}
_SHEETS = {
    "objcurs": ("diabdat", [r"data\inv\objcurs.cel", r"Data\Inv\Objcurs.CEL"]),
    "invobj1": ("mor", [r"Data\Inv\invobj1.CEL", r"data\inv\invobj1.cel"]),
    "th2": ("mor", [r"data\inv\TH2objcurs.cel", r"Data\Inv\TH2objcurs.cel"]),
    "th3": ("mor", [r"data\inv\TH3objcurs.cel", r"Data\Inv\TH3objcurs.cel"]),
}
_PAL_NAMES = [r"Levels\TownData\Town.pal", r"levels\towndata\town.pal"]
_GLYPH = {
    "Swords": "Sw", "Knives": "Kn", "Axes": "Ax", "Bows": "Bw", "Maces & clubs": "Mc",
    "Mallets": "Ml", "Staves": "St", "Claws": "Cl", "Pistols": "Pi", "Traps": "Tr",
    "Shields": "Sh", "Light armor": "La", "Medium armor": "Ma", "Heavy armor": "Ha",
    "Helms": "He", "Rings": "Rg", "Amulets": "Am", "Gloves": "Gl", "Boots": "Bo",
    "Belts": "Be", "Flasks": "Fl", "Gold": "Au", "Potions & elixirs": "Po",
    "Relicts & scrolls": "Re", "Books": "Bk", "Gems": "Gm", "Oils": "Oi",
}
_ICON_CACHE = {}


def glyph_for(b):
    if not b:
        return ""
    from th4save.rules import category
    return _GLYPH.get(category(b), (category(b)[:1] or "?"))


def sprite_loc(graphic, classic=False):
    """(sheet, 1-based CEL index) for a base item's GraphicValue. None if it has no sprite."""
    if not isinstance(graphic, int) or graphic < 0:
        return None
    if classic and graphic in _CLASSIC_REMAP:
        return _CLASSIC_REMAP[graphic]
    sprite = graphic + 12
    if sprite <= 179:
        return ("objcurs" if classic else "invobj1", sprite)
    if sprite <= 3896:
        return ("th2", sprite - 179)
    return ("th3", sprite - 3896)


def diabdat_path():
    env = os.environ.get("CHEESESTICK_DIABDAT")
    if env and os.path.isfile(env):
        return env
    p = r"C:\THE HELL4 Mod\GOG Galaxy\Games\Diablo\DIABDAT.MPQ"
    return p if os.path.isfile(p) else None


def mor_path():
    env = os.environ.get("CHEESESTICK_MOR")
    if env and os.path.isfile(env):
        return env
    p = r"C:\THE HELL4 Mod\TH4_v0.773\TH4data.mor"
    return p if os.path.isfile(p) else None


def cache_dir():
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "CheeseStickTrainer", "icons")


def cache_file(sheet, frame):
    return os.path.join(cache_dir(), "%s_%d.png" % (sheet, frame))


def clear_icon_cache():
    _ICON_CACHE.clear()


def icon_file(base, classic=False):
    """Path of a cached PNG, or None. Does not read MPQ or decode a frame."""
    if not base:
        return None
    loc = sprite_loc(base.get("graphic"), classic)
    if loc is None:
        return None
    path = cache_file(*loc)
    return path if os.path.isfile(path) else None


def cached_icon(base, classic=False):
    """QIcon for a cached PNG, or None so the caller can draw a letter instead."""
    path = icon_file(base, classic)
    if path is None:
        return None
    hit = _ICON_CACHE.get(path)
    if hit is not None:
        return hit
    if not os.path.isfile(path):
        return None
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QIcon, QPixmap
    pix = QPixmap(path)
    if pix.isNull():
        return None
    icon = QIcon(pix.scaled(QSize(28, 28), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    _ICON_CACHE[path] = icon
    return icon


def decode_frame(cel, index, palette):
    """One CEL frame -> (width, height, RGBA). Rows in the file are bottom-up.

    The game's graphics id is a 1-based index: pixel data for id N starts at
    dword[N], and dword[N+1] is the next frame. A leading uint16 is a byte
    skip to the RLE. A byte >= 128 is that many transparent pixels (256-byte);
    a smaller byte is that many opaque palette indexes. Width starts at 28
    and grows by 28 until every row consumes exactly that many pixels.
    """
    if cel is None or len(cel) < 12 or not palette:
        return None
    count = struct.unpack_from("<I", cel, 0)[0]
    if not 1 <= index <= count:
        return None
    if (index + 2) * 4 > len(cel):
        return None
    start = struct.unpack_from("<I", cel, index * 4)[0]
    end = struct.unpack_from("<I", cel, (index + 1) * 4)[0]
    if not (0 <= start < end <= len(cel)):
        return None
    frame = cel[start:end]
    if len(frame) < 2:
        return None
    skip = struct.unpack_from("<H", frame, 0)[0]
    if skip >= len(frame):
        return None
    pix = frame[skip:]
    width = 28
    rows = None
    while width <= 28 * 4:
        rows = _decode_rows(pix, width)
        if rows:
            break
        width += 28
    if not rows:
        return None
    rows.reverse()
    h, w = len(rows), width
    out = bytearray(w * h * 4)
    for y, row in enumerate(rows):
        for x, idx in enumerate(row):
            if not idx:
                continue
            r, g, b = palette[idx]
            o = (y * w + x) * 4
            out[o:o + 4] = bytes((r, g, b, 255))
    return w, h, bytes(out)


def _decode_rows(pix, width):
    i, n, rows = 0, len(pix), []
    while i < n:
        left, row = width, []
        while left > 0:
            if i >= n:
                return None
            b = pix[i]
            i += 1
            if b == 0:
                return None
            count = (256 - b) if b >= 128 else b
            if count > left:
                return None
            if b >= 128:
                row.extend([0] * count)
            else:
                if i + count > n:
                    return None
                row.extend(pix[i:i + count])
                i += count
            left -= count
        rows.append(row)
        if len(rows) > 300:
            return None
    return rows or None


def write_png(path, w, h, rgba):
    if len(rgba) != w * h * 4:
        raise ValueError("png buffer is %d bytes for %dx%d" % (len(rgba), w, h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(png)
    os.replace(tmp, path)


def palette_from_bytes(raw):
    """Town.pal is 256 colors, 6-bit RGB. The game draws them shifted up by 2 bits."""
    if raw is None or len(raw) < 768:
        raise ValueError("palette is %s bytes" % (None if raw is None else len(raw)))
    pal = []
    for i in range(256):
        r, g, b = raw[i * 3:i * 3 + 3]
        pal.append((min(255, r * 4), min(255, g * 4), min(255, b * 4)))
    return pal


class _Archive:
    """Seeking reader. Save code loads a whole archive; these two files are 0.5 GB and 1.5 GB."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.f.seek(0)
        hdr = struct.unpack("<3I2H4I", self.f.read(32))
        sig, _hsize, _asize, ver, ssid, hoff, boff, hcount, bcount = hdr
        if sig != ID_MPQ or ver != 0:
            raise MpqError("not an MPQ v1 archive: %s" % path)
        if hcount == 0 or hcount & (hcount - 1):
            raise MpqError("hash table size %d is not a power of two" % hcount)
        self.sector = 512 << ssid
        self.hcount = hcount
        self.f.seek(hoff)
        self.htab = decrypt(self.f.read(hcount * 16), KEY_HASH_TABLE)
        self.f.seek(boff)
        self.btab = decrypt(self.f.read(bcount * 16), KEY_BLOCK_TABLE)
        self.bcount = bcount

    def close(self):
        self.f.close()

    def read(self, names):
        for name in names:
            block = self._find(name)
            if block is not None:
                return self._read_block(block, name)
        raise MpqError("not in %s: %s" % (os.path.basename(self.path), ", ".join(names)))

    def _find(self, name):
        h0, c0, c1 = (mpq_hash(name, t) for t in (HASH_INDEX, HASH_CHECK0, HASH_CHECK1))
        e = h0 & (self.hcount - 1)
        for _ in range(self.hcount):
            a, b, lcid, block = struct.unpack_from("<4I", self.htab, e * 16)
            if block == HASH_BLOCK_UNUSED:
                return None
            if a == c0 and b == c1 and lcid == 0 and block not in (HASH_BLOCK_FREED, HASH_BLOCK_UNUSED):
                return block
            e = (e + 1) & (self.hcount - 1)
        return None

    def _read_block(self, index, name):
        if index >= self.bcount:
            raise MpqError("block %d out of range for %s" % (index, name))
        offset, _alloc, plain, flags = struct.unpack_from("<4I", self.btab, index * 16)
        if not flags & FLAG_EXISTS:
            raise MpqError("%s is an empty block" % name)
        if flags & FLAG_COMPRESS:
            raise MpqError("%s uses multi-compression, which these item files do not" % name)
        if not flags & (FLAG_IMPLODE | FLAG_ENCRYPTED):
            self.f.seek(offset)
            data = self.f.read(plain)
            if len(data) != plain:
                raise MpqError("short read of %s" % name)
            return data
        key = mpq_hash(name.replace("/", "\\").split("\\")[-1], HASH_ENCRYPTKEY)
        if flags & FLAG_FIX_KEY:
            key = (key + offset) ^ plain
        nsec = (plain + self.sector - 1) // self.sector
        self.f.seek(offset)
        table = self.f.read((nsec + 1) * 4)
        if flags & FLAG_ENCRYPTED:
            table = decrypt(table, (key - 1) & 0xFFFFFFFF)
        offs = struct.unpack("<%dI" % (nsec + 1), table)
        out = bytearray()
        for i in range(nsec):
            self.f.seek(offset + offs[i])
            chunk = self.f.read(offs[i + 1] - offs[i])
            if flags & FLAG_ENCRYPTED:
                chunk = decrypt(chunk, (key + i) & 0xFFFFFFFF)
            want = min(self.sector, plain - i * self.sector)
            if len(chunk) != want:
                if flags & FLAG_IMPLODE and len(chunk) < want:
                    chunk = pkware.explode(chunk)
                else:
                    raise MpqError("sector %d of %s is %d bytes, expected %d" % (i, name, len(chunk), want))
            if len(chunk) != want:
                raise MpqError("sector %d of %s exploded to %d bytes, expected %d" % (i, name, len(chunk), want))
            out += chunk
        return bytes(out)


def _open_sources():
    """name -> _Archive for the files that are actually installed."""
    opened = {}
    for kind, path in (("diabdat", diabdat_path()), ("mor", mor_path())):
        if path:
            opened[kind] = _Archive(path)
    return opened


def load_sheet(sheet, opened=None):
    own = opened is None
    arcs = opened if opened is not None else _open_sources()
    try:
        kind, names = _SHEETS[sheet]
        arc = arcs.get(kind)
        if arc is None:
            return None
        return arc.read(names)
    finally:
        if own:
            for a in arcs.values():
                a.close()


def load_palette(opened=None):
    own = opened is None
    arcs = opened if opened is not None else _open_sources()
    try:
        arc = arcs.get("diabdat")
        if arc is None:
            return None
        return palette_from_bytes(arc.read(_PAL_NAMES))
    finally:
        if own:
            for a in arcs.values():
                a.close()


def build_cache(stop=None):
    """Decode every missing frame into the local cache. Returns a status string (empty = ok)."""
    stop = stop or (lambda: False)
    try:
        return _build_cache(stop)
    except Exception as e:
        return "Item icons were not loaded: %s" % e


def _build_cache(stop):
    needed = {}
    for b in BASE_ITEMS:
        g = b.get("graphic")
        if not isinstance(g, int):
            continue
        for classic in (False, True):
            loc = sprite_loc(g, classic)
            if loc and not os.path.isfile(cache_file(*loc)):
                needed.setdefault(loc[0], set()).add(loc[1])
    if not needed:
        return ""
    if not diabdat_path() and not mor_path():
        return ("Diablo's icon files were not found, so items use letter marks. "
                "Icons are read from DIABDAT.MPQ and TH4data.mor on this PC and are not part of the editor.")
    arcs = _open_sources()
    failed = []
    try:
        try:
            pal = load_palette(arcs)
        except (MpqError, ValueError, OSError) as e:
            return "Item icons were not loaded: palette: %s" % e
        os.makedirs(cache_dir(), exist_ok=True)
        for sheet, frames in needed.items():
            if stop():
                return "Icon loading was stopped."
            try:
                cel = load_sheet(sheet, arcs)
            except (MpqError, OSError) as e:
                failed.append("%s (%s)" % (sheet, e))
                continue
            if cel is None:
                failed.append(sheet)
                continue
            for frame in frames:
                if stop():
                    return "Icon loading was stopped."
                img = decode_frame(cel, frame, pal)
                if img is None:
                    continue
                write_png(cache_file(sheet, frame), img[0], img[1], img[2])
    finally:
        for a in arcs.values():
            a.close()
    if failed:
        return "Some item icons could not be read: %s. Those rows use letter marks." % ", ".join(failed)
    return ""
