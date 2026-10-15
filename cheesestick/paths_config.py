"""Editable path settings for CheeseStick (no Qt). Stored in cheesestick_paths.json next to main.py."""
import json, os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, "cheesestick_paths.json")
REAL_GAME = r"C:\THE HELL4 Mod\TH4_v0.773"
_WS = r"C:\THE HELL4 Mod\TH4_Workshop"
_DEV = os.path.join(_WS, "TH4_dev")
MODES = ("th4_save_sp", "th4_save_mp", "th4_save_drk", "th4_save_ob", "th4_save_cls", "th4_save_col")

DEFAULTS = {
    "game_dir": _DEV,
    "workshop_dir": _WS,
    "launcher_script": os.path.join(_WS, "scripts", "mp_session.ps1"),
    "real_game_dir": REAL_GAME,
    "bots": 2, "addr": "127.0.0.1", "host": "slot1", "game_name": "TH4bots",
    # [group label, folder]. Several folders may share a label (= one group).
    # Mode subfolders (th4_save_*) are picked up automatically. Unlisted saves go to "Other".
    "save_dirs": [
        ["Christopher's", os.path.join(_DEV, "saves", "slot1")],
        ["Pres", os.path.join(_DEV, "saves", "slot2")],
        ["Summoner", os.path.join(_DEV, "saves", "slot3")],
        ["Dev", os.path.join(_DEV, "saves")],
        ["Dev", _DEV],
        ["Backups", os.path.join(_DEV, "saves", "backup")],
        ["Real game (read-only)", REAL_GAME],
    ],
}


def load(path=None):
    path = path or CONFIG_FILE
    data = json.loads(json.dumps(DEFAULTS))
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user, dict):
            data.update(user)
    except (OSError, ValueError):
        pass
    return data


def save(data, path=None):
    path = path or CONFIG_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def is_real_game(p, cfg=None):
    real = os.path.normcase(os.path.abspath((cfg or {}).get("real_game_dir") or REAL_GAME))
    p = os.path.normcase(os.path.abspath(p))
    return p == real or p.startswith(real + os.sep)


def known_sources(cfg=None):
    """[(label, folder)] for every existing save folder, incl. mode subfolders and backup subfolders."""
    cfg = cfg or load()
    out, seen = [], set()

    def add(label, f):
        k = os.path.normcase(os.path.abspath(f))
        if k not in seen and os.path.isdir(f):
            seen.add(k); out.append((label, os.path.abspath(f)))

    for label, base in cfg.get("save_dirs", []):
        if not os.path.isdir(base):
            continue
        add(label, base)
        for m in MODES:
            add(label, os.path.join(base, m))
        if os.path.basename(base).lower() == "backup":
            try:
                for n in sorted(os.listdir(base)):
                    sub = os.path.join(base, n)
                    if os.path.isdir(sub):
                        add(label, sub)
                        for m in MODES:
                            add(label, os.path.join(sub, m))
            except OSError:
                pass
    return out


OTHER = "Other"


def group_labels(cfg=None):
    cfg = cfg or load()
    seen = []
    for lab, _ in cfg.get("save_dirs", []):
        if lab not in seen:
            seen.append(lab)
    return seen + ([OTHER] if OTHER not in seen else [])


def backup_root(cfg=None):
    cfg = cfg or load()
    return os.path.join(cfg.get("game_dir") or _DEV, "saves", "backup")


def _recycle(path):
    """Send one file to the Windows Recycle Bin (SHFileOperationW, FOF_ALLOWUNDO)."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, os.path.abspath(path) + "\0", None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc or op.fAnyOperationsAborted or os.path.exists(path):
        raise OSError("Recycle Bin move failed (code %s)" % rc)


def recycle_save(path, cfg=None, backup_dir=None):
    """Back up to <backup>\\deleted_<time>\\, then send to the Recycle Bin. Never for real-game saves.
    Returns the backup copy path."""
    import shutil, time
    cfg = cfg or load()
    if is_real_game(path, cfg):
        raise PermissionError("Real game saves cannot be deleted from CheeseStick.")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    dest_dir = os.path.join(backup_dir or backup_root(cfg), "deleted_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    shutil.copy2(path, dest)
    _recycle(path)
    return dest