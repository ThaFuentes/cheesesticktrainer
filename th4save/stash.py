"""Personal stash entry ('spstash'), VisualStash.cpp StashPanel_Save():
  u32 BE signature 'HEL4', u32 BE version, then 100 tabs x
  { u32 BE itemCount, i16[130] usedFlags (LE, 10x13 grid), ItemInfo64[itemCount] }.
Parse/serialize is byte-exact; any trailing bytes are preserved."""
import struct
from .player import Item, ITEM_SIZE

TABS = 100
SLOTS = 130
STASH_W, STASH_H = 10, 13


class Stash:
    def __init__(self, raw: bytes):
        self.signature, self.version = struct.unpack_from(">II", raw, 0)
        pos = 8
        self.tabs = []
        for _ in range(TABS):
            (n,) = struct.unpack_from(">I", raw, pos); pos += 4
            flags = list(struct.unpack_from("<%dh" % SLOTS, raw, pos)); pos += SLOTS * 2
            items = [Item.parse(raw[pos + i * ITEM_SIZE:pos + (i + 1) * ITEM_SIZE]) for i in range(n)]
            pos += n * ITEM_SIZE
            self.tabs.append({"flags": flags, "items": items})
        self.tail = raw[pos:]

    def pack(self) -> bytes:
        out = bytearray(struct.pack(">II", self.signature, self.version))
        for t in self.tabs:
            out += struct.pack(">I", len(t["items"]))
            out += struct.pack("<%dh" % SLOTS, *t["flags"])
            out += b"".join(i.pack() for i in t["items"])
        return bytes(out) + self.tail

    def item_count(self):
        return sum(len(t["items"]) for t in self.tabs)
