"""Find TH4 save files and read only their hero block (no Qt dependency).

Looks for single-player, Dark, and Outbreak save folders next to any TH4.exe
(plus loose saves beside TH4.exe when the save-folder option is off) under a
set of roots, depth-limited, and in user-added folders.
"""
import json, os, re, string, sys, time
from dataclasses import dataclass, asdict
from . import mpq, codec
from .player import PlayerInfo, CLASS_NAMES

SAVE_DIRS = ("th4_save_sp", "th4_save_mp", "th4_save_drk", "th4_save_ob", "th4_save_cls", "th4_save_col")
SAVE_EXT = (".ssv", ".msv", ".dsv", ".osv")
EXE_NAMES = ("th4.exe",)
_KNOWN_ROOT = r"C:\THE HELL4 Mod\TH4_v0.773"
DEFAULT_KNOWN = [os.path.join(_KNOWN_ROOT, d) for d in ("th4_save_sp", "th4_save_drk", "th4_save_ob")]
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", "programdata", "appdata",
             "node_modules", ".git", "__pycache__", "winsxs", "$windows.~bt", "$windows.~ws"}
_SLOT_RE = re.compile(r"th4(?:sp|mp|drk|ob)_(\d+)(?:[._][^\\/]*)?\.(?:ssv|msv|dsv|osv)$", re.I)


@dataclass
class SaveEntry:
    path: str
    file: str
    slot: str
    name: str = ""
    cls: str = ""
    level: int = 0
    gold: int = 0
    mtime: float = 0.0
    error: str = ""
    source: str = ""

    @property
    def ok(self):
        return not self.error


# ---------------- settings ----------------
def settings_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "CheeseStickTrainer", "settings.json")


def load_settings(path=None):
    path = path or settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        data = {}
    data.setdefault("folders", [])
    return data


def save_settings(data, path=None):
    path = path or settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def add_folder(folder, path=None):
    data = load_settings(path)
    folder = os.path.normpath(folder)
    if folder not in data["folders"]:
        data["folders"].append(folder)
        save_settings(data, path)
    return data


# ---------------- reading ----------------
def read_hero(path) -> SaveEntry:
    fn = os.path.basename(path)
    m = _SLOT_RE.search(fn)
    e = SaveEntry(path=os.path.abspath(path), file=fn, slot=m.group(1) if m else "?")
    try:
        e.mtime = os.path.getmtime(path)
        with open(path, "rb") as f:
            raw = f.read()
        from .save import HERO_NAMES
        arc = mpq.MpqArchive.from_bytes(raw, HERO_NAMES)
        if not arc.files:
            raise ValueError("no hero entry")
        hero = next(iter(arc.files.values()))
        p = PlayerInfo.parse(codec.decode(hero))
        e.name = p.name
        c = p["ClassId"]
        e.cls = CLASS_NAMES[c] if c < len(CLASS_NAMES) else str(c)
        e.level = p["CharLevel"]
        e.gold = p["TotalGold"]
    except Exception as ex:  # mark, never crash
        e.error = "%s: %s" % (type(ex).__name__, ex)
    return e


def saves_in_folder(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(os.path.join(folder, n) for n in names
                  if n.lower().endswith(SAVE_EXT) and ".bak" not in n.lower()
                  and os.path.isfile(os.path.join(folder, n)))


# ---------------- discovery ----------------
def default_roots():
    home = os.path.expanduser("~")
    roots = [r"C:\THE HELL4 Mod", os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), home]
    for sub in ("Documents", "Desktop", "Downloads", os.path.join("OneDrive", "Documents"),
                os.path.join("OneDrive", "Desktop")):
        roots.append(os.path.join(home, sub))
    drives = []
    if sys.platform == "win32":
        drives = ["%s:\\" % d for d in string.ascii_uppercase if os.path.exists("%s:\\" % d)]
        for d in drives:
            for g in ("GOG Galaxy\\Games", "GOG Games", "Program Files (x86)\\GOG Galaxy\\Games"):
                roots.append(os.path.join(d, g))
    return [(r, 4) for r in dict.fromkeys(roots) if r] + [(d, 3) for d in drives]


def find_save_folders(roots, progress=None, cancel=None):
    """roots: [(path, max_depth)]. Returns sorted set of folders containing saves."""
    found, seen = set(), set()
    for ri, (root, depth) in enumerate(roots):
        if progress:
            progress(ri, len(roots), root)
        if not os.path.isdir(root):
            continue
        stack = [(root, 0)]
        while stack:
            if cancel and cancel():
                return sorted(found)
            d, lv = stack.pop()
            key = os.path.normcase(os.path.abspath(d))
            if key in seen:
                continue
            seen.add(key)
            try:
                with os.scandir(d) as it:
                    entries = list(it)
            except OSError:
                continue
            names = {e.name.lower(): e for e in entries}
            if any(n in names for n in EXE_NAMES):
                for sd in SAVE_DIRS:
                    if sd in names and names[sd].is_dir():
                        found.add(os.path.abspath(names[sd].path))
                if saves_in_folder(d):
                    found.add(os.path.abspath(d))
            if lv < depth:
                for e in entries:
                    try:
                        if e.is_dir(follow_symlinks=False) and e.name.lower() not in SKIP_DIRS:
                            stack.append((e.path, lv + 1))
                    except OSError:
                        pass
    return sorted(found)


def scan(roots=None, extra_folders=None, progress=None, cancel=None, known=None, sources=None):
    """known: always-checked folders (default DEFAULT_KNOWN; pass [] in tests).
    sources: optional [(label, folder)] always scanned; label is shown as SaveEntry.source."""
    labels = {}
    for lab, f in (sources or []):
        if os.path.isdir(f):
            labels.setdefault(os.path.normcase(os.path.abspath(f)), lab)
    roots = default_roots() if roots is None else roots
    folders = set(find_save_folders(roots, progress, cancel))
    known = DEFAULT_KNOWN if known is None else known
    for f in list(known) + list(extra_folders or []):
        if os.path.isdir(f):
            folders.add(os.path.abspath(f))
            for sd in SAVE_DIRS:  # user may add the game folder itself
                if os.path.isdir(os.path.join(f, sd)):
                    folders.add(os.path.abspath(os.path.join(f, sd)))
    for k in labels:
        folders.add(k)
    entries, seen = [], set()
    for f in sorted(folders):
        for p in saves_in_folder(f):
            k = os.path.normcase(os.path.abspath(p))
            if k not in seen:
                seen.add(k); e = read_hero(p)
                e.source = labels.get(os.path.normcase(os.path.abspath(f)), "") or "Other"
                entries.append(e)
    entries.sort(key=lambda e: -e.mtime)
    return entries
