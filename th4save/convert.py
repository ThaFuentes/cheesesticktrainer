"""Experimental single-player -> multiplayer save conversion (TH4).

Observed format (TH4_dev saves, Oct 2026): .ssv and .msv use the same MPQ container and the
same codec password. They differ only in entry names: sphero/spstash vs mphero/mpstash, and MP
saves carry no 'game' (game in progress) or 'perml###' (level state) entries. Conversion renames
the hero/stash entries and drops those. The source is only read. NOT yet verified in-game.
"""
import os
from . import mpq
from .save import SaveFile

RENAME = {"sphero": "mphero", "spstash": "mpstash", "drkhero": "mphero", "drkstash": "mpstash",
          "obhero": "mphero", "obstash": "mpstash", "clhero": "mphero", "clstash": "mpstash"}
KEEP = ("additionalherodata", "spellhotkeys", "trans", "wpnswp")


def to_mp_bytes(src_path):
    with open(src_path, "rb") as f:
        raw = f.read()
    arc = mpq.MpqArchive.from_bytes(raw, mpq.th4_candidate_names())
    if "mphero" in arc.files:
        return raw
    out = {}
    for name, data in arc.files.items():
        if name in RENAME:
            out[RENAME[name]] = data
        elif name in KEEP:
            out[name] = data
    if "mphero" not in out:
        raise ValueError("no hero entry to convert in %s" % src_path)
    return mpq.MpqArchive(out).to_bytes()


def convert(src_path, dest_path):
    data = to_mp_bytes(src_path)
    if os.path.exists(dest_path):
        raise FileExistsError(dest_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    chk = SaveFile.load(dest_path)  # must read back as an MP hero
    if chk.hero_entry != "mphero":
        raise ValueError("converted file did not read back as multiplayer")
    return chk.player.name
