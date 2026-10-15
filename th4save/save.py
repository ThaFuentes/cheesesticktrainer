"""High-level: open .ssv -> decoded entries -> PlayerInfo/Stash; safe write back."""
import hashlib, json, os, re, shutil, time
from . import mpq, codec
from .gamestate import GameState, HERO_ONLY_FIELDS
from .player import PlayerInfo
from .stash import Stash

HERO_NAMES = ("sphero", "mphero", "clhero", "cphero", "drkhero", "obhero", "hero")
STASH_NAMES = ("spstash", "mpstash", "clstash", "cpstash", "drkstash", "obstash", "stash")


class StaleSaveError(RuntimeError):
    pass


class SaveFile:
    def __init__(self, raw: bytes, password: bytes = codec.PASSWORD_SP):
        self.password = password
        self.archive = mpq.MpqArchive.from_bytes(raw, mpq.th4_candidate_names())
        self.hero_entry = next((n for n in HERO_NAMES if n in self.archive.files), None)
        if self.hero_entry is None:
            raise ValueError("no hero entry found in archive")
        self.hero_plain = codec.decode(self.archive.files[self.hero_entry], password)
        self.player = PlayerInfo.parse(self.hero_plain)
        self.stash_entry = next((n for n in STASH_NAMES if n in self.archive.files), None)
        self.stash_plain = self.decoded(self.stash_entry) if self.stash_entry else None
        self.stash = Stash(self.stash_plain) if self.stash_plain else None
        self.game_plain = self.decoded("game") if "game" in self.archive.files else None
        self.drop_game = False   # True: remove the game-in-progress so the game must load the hero

    # ---- the game-in-progress copy of the hero (see gamestate.py for why this matters)
    def game_state(self):
        return GameState(self.game_plain) if self.game_plain is not None else None

    def hero_changed(self):
        return self.player.pack() != self.hero_plain

    def hero_only_changes(self):
        """Edited hero fields that the game-in-progress copy cannot receive."""
        old = PlayerInfo.parse(self.hero_plain)
        return [k for k in HERO_ONLY_FIELDS if k in old and old[k] != self.player[k]]

    def _next_level_up(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cheesestick", "data", "game.json")
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        tab = g["level_xp_classic"] if self.player["gameMode"] == 9 else g["level_xp"]
        return tab[min(self.player["CharLevel"], len(tab) - 1)]   # LevelUp(clvl) = table[clvl]
    @classmethod
    def load(cls, path, **kw):
        with open(path, "rb") as f:
            raw = f.read()
        s = cls(raw, **kw)
        s.disk_sha1 = hashlib.sha1(raw).hexdigest()
        return s

    disk_sha1 = None

    def changed_on_disk(self, path):
        """True if the file is no longer what we loaded / last wrote (e.g. the game saved it
        while the editor had it open). Writing then would throw away the game's newer data."""
        if self.disk_sha1 is None or not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest() != self.disk_sha1

    def decoded(self, name):
        return codec.decode(self.archive.files[name], self.password)

    def to_bytes(self) -> bytes:
        if self.archive.unknown_blocks:
            raise ValueError("archive has %d entries with unknown names; refusing to rewrite"
                             % len(self.archive.unknown_blocks))
        new_plain = self.player.pack()
        if new_plain != self.hero_plain:
            self.archive.files[self.hero_entry] = codec.encode(new_plain, self.password)
        if self.drop_game:
            for n in [n for n in self.archive.files if n == "game" or re.fullmatch(r"(templ|perml|temps|perms)\d{3}", n)]:
                del self.archive.files[n]
        elif self.game_plain is not None:
            gs = self.game_state()
            if not gs.ok:
                pass   # unreadable layout: left untouched (the GUI offers to remove it instead)
            else:
                gs.sync_from_hero(self.player, self._next_level_up())
                if gs.pack() != self.game_plain:
                    self.archive.files["game"] = codec.encode(gs.pack(), self.password)
        if self.stash is not None:
            sp = self.stash.pack()
            if sp != self.stash_plain:
                self.archive.files[self.stash_entry] = codec.encode(sp, self.password)
        return self.archive.to_bytes()

    def save_safely(self, path, allow_stale=False) -> str:
        """Write new archive to a temp file, re-read and verify it, back up the
        original (timestamped copy beside it), then atomically replace.
        Returns the backup path."""
        if not allow_stale and self.changed_on_disk(path):
            raise StaleSaveError("The save file changed on disk since it was opened (the game probably "
                                 "saved it). Reload it before editing; nothing was written.")
        data = self.to_bytes()
        tmp = path + ".cheesestick.tmp"
        with open(tmp, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            chk = SaveFile.load(tmp, password=self.password)
            if chk.player.pack() != self.player.pack():
                raise ValueError("verification failed: hero data differs after re-read")
            if self.stash is not None and chk.stash.pack() != self.stash.pack():
                raise ValueError("verification failed: stash differs after re-read")
            if set(chk.archive.files) != set(self.archive.files):
                raise ValueError("verification failed: entry list differs")
            for n in self.archive.files:
                if chk.decoded(n) != self.decoded(n):
                    raise ValueError("verification failed for entry %s" % n)
        except Exception:
            os.remove(tmp)
            raise
        backup = None
        if os.path.exists(path):
            backup = "%s.%s.bak" % (path, time.strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(path, backup)
        os.replace(tmp, path)
        self.disk_sha1 = hashlib.sha1(data).hexdigest()
        self.hero_plain = self.player.pack()
        self.stash_plain = self.stash.pack() if self.stash else None
        self.game_plain = self.decoded("game") if "game" in self.archive.files else None
        self.drop_game = False
        return backup
