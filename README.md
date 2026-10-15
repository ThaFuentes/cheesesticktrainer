# CheeseStickTrainer: The Hell 4 save editor (core + PySide6 GUI)

A pure-Python (3.13, standard library only, works on Windows) reader and writer for **vanilla The Hell 4 v0.77x** single-player saves (`th4sp_<slot>.ssv`).
It is ported from the public source in `/workspace/th4/th4src`.

```
python -m th4save dump  th4sp_0.ssv [--full]
python -m th4save roundtrip th4sp_0.ssv copy.ssv     # never overwrites the input
python -m unittest -v tests.test_th4save             # C cross-checks need tests/cref/build.sh (g++)
```

| Module | What |
|---|---|
| `th4save/mpq.py` | MPQ v1 hash/crypt tables, Hash/Encrypt/Decrypt, archive reader (implode sectors) and writer (same layout as MpqSave.cpp) |
| `th4save/pkware.py` | PKWARE DCL explode and implode (binary and ASCII), pure Python |
| `th4save/codec.py` | Diablo save codec: Blizzard SHA1 quirks, MSVC rand key setup, password `xrgyrkj1`, 8-byte AppendRec trailer |
| `th4save/player.py` | `PlayerInfo_v26` (11,798 B) + `ItemInfo64` (64 B), named fields, byte-exact round-trip |
| `th4save/save.py` | `SaveFile`: archive → hero decode → PlayerInfo → re-encode/re-pack |
| `tests/cref/` | Builds the original `SHA.cpp`, `CodeSave.cpp`, the Engine.cpp hash/crypt and pklib implode/explode with g++ for byte-for-byte checks |
| `tools/extract_base_items.py` | Prototype item table extractor (2,683 base items → `tools/base_items.json`) |

Safety: edit a **copy** and keep a backup. Single player only. Close the game before editing.

## Item tables for the GUI (plan)
`TH4data.mor` holds only graphics and sound. Item, affix and unique data is compiled into TH4.exe from the C++ tables, so the source is the data source:
- **Base items:** `src/BaseItems.cpp` `BaseItemsData[]`. Row index = `baseId` = `ItemInfo64.baseItemIndex`. Already extracted (name, type, slot, item code, qlvl).
- **Affixes:** `src/Affixes.cpp` (+ AffixesRare/Enchant/Classic/Coliseum) gives `{id, "Name", AE_effect, min, max, qlvl, IA_ mask ...}`. Same regex approach.
- **Uniques/sets:** `src/UniqueItems.cpp`, `UniqueSets.cpp` give the names for `uniqIndex`.
- **Caveat:** a saved item is `seed + baseItemIndex + quality/uniqIndex + dropType`. The game regenerates affixes from the seed with the item gen code (`CurItemGenVersion = 7`). A picker can safely set base, unique, quality, durability, charges and amount. Showing or choosing exact random affixes would need a port of the item generator (`Item.cpp`, and the MSVC-style RNG). That's a later phase. Safe first editor scope is stats, level/xp, gold, points, spell levels, perks and duplicating/cloning existing items.
- The extractor must target the **same source revision as the installed exe**. th4src may lag v0.773.


## Run on Windows (PyCharm)
1. Install Python 3.13 (python.org), then open this folder in PyCharm (File > Open > `CheeseStickTrainer`).
2. Settings > Project > Python Interpreter > Add > Virtualenv (Python 3.13).
3. PyCharm terminal: `pip install -r requirements.txt`
4. Right-click `main.py` > Run (or `python main.py "C:\THE HELL4 Mod\TH4_v0.773\th4sp_0.ssv"`).
   Saves live next to TH4.exe (or in `th4_save_sp\` when the save-folder option is on).
5. **Close the game first.** File > Save writes a temp archive, re-reads and verifies it, copies the
   original to `th4sp_0.ssv.YYYYMMDD-HHMMSS.bak`, then atomically replaces the original.
   To undo: rename the .bak back to `th4sp_0.ssv`.

Tabs: Character (name, class, level, XP + "XP for level", stats, free points, gold, raw life/mana ÷64),
Skills/Spells, Perks/Traits, Equipped, Inventory, Belt, Stash (100 tabs). Item lists: Add (searchable
base-item picker), Remove, Clone (optionally with a new seed), edit qty/durability/charges/unique/quality.
Gold is stored as inventory gold piles. The Gold field rebalances the piles, and TotalGold is recomputed.

## Save version notes
- The installed v0.773 writes hero **save version 30**, 11,817 bytes. That is the public-source v26 layout (all offsets verified on
  a real save) plus **19 extra bytes appended after `gameMode`** (offset 11798..11816). Their meaning is unknown, and they are kept verbatim
  as `tail_unknown`. A fresh save shows `00..00 02 000000` (byte +15 = 2).
- Empty slots: equipped, belt and stash use `baseItemIndex = -1`. Never-used talisman slots are all zero.
- Life/mana are fixed-point ×64 (5120 = 80 life), confirmed.
- Item cell sizes come from `ItemWidthTable`/`ItemHeightTable` where the source has them (821 of 2,683 bases). For the rest you
  must enter the size in the picker. A wrong size can make items overlap in the grid.
- The stash grid convention (+bottom-left / -other cells) is copied from the inventory. It is verified for the inventory but not yet for the stash.

## Find Characters
The app opens on the **Find Characters** tab and scans in the background. You can also use File > Find Characters (Ctrl+F) or the button.
- It looks for `th4_save_sp` / `th4_save_mp` (and loose `.ssv`/`.msv`) next to any `TH4.exe` under these places:
  - `C:\THE HELL4 Mod`
  - the Program Files folders
  - your home folder, Documents, Desktop and Downloads (plus their OneDrive versions)
  - GOG Galaxy / GOG Games folders
  - every drive root, 3 folders deep. The other places are searched 4 deep.
- It always checks `C:\THE HELL4 Mod\TH4_v0.773\th4_save_sp`.
- **Add folder...** remembers a folder in `%APPDATA%\CheeseStickTrainer\settings.json`. That can be a save folder or the game folder.
- Only the hero block is read. Unreadable files show as red **UNREADABLE**, with the reason in the tooltip. `.bak` backups are hidden.
- Double-click a row to open it in the editor. Right-click gives **Show in folder**.

## Slot-aware items and theme
- **Equipped:** a paperdoll laid out like the in-game character screen, using the `BaseSlots` coordinates from `InventoryPanel.cpp`. Click an empty slot and the picker shows only the items its equip location allows (`EL_*`, both hands take one- and two-handed weapons).
- **Inventory:** click an empty cell to place an item with its top-left corner there. Click an item to select it.
- **Belt:** 8 boxes. Only items that pass the game's own belt rule are offered: 1x1, use-once (potions, relicts, oils), not gold.
- The picker groups items by category and has search. Every placement is checked again before it is written (`th4save/rules.py`).
- Dark theme in `cheesestick/theme.qss` (Qt stylesheet only, no new dependencies). Item names are coloured by quality: normal white, magic blue, unique gold, set green.

## Setting up on another PC

1. Install Python 3.13 and Git, then `git clone https://github.com/ThaFuentes/cheesesticktrainer.git`
2. `cd cheesesticktrainer`
3. `python -m venv .venv` then activate it (`.venv\Scripts\Activate.ps1`)
4. `pip install -r requirements.txt`
5. Copy `cheesestick_paths.example.json` to `cheesestick_paths.json` (machine-specific, not committed) and adjust the paths, or set them in the launcher.
6. Run `python -m cheesestick.launcher` and set/confirm the game and save paths in the launcher.
