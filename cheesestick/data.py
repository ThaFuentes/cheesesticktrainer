import json, os
_D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(name):
    with open(os.path.join(_D, name), encoding="utf-8") as f:
        return json.load(f)


BASE_ITEMS = _load("base_items.json")          # index == baseItemIndex
LEVEL_XP = _load("level_xp.json")              # XP to reach level i+1 (index 0 = level 1)
_N = _load("names.json")
SPELLS = {int(k): v for k, v in _N["spells"].items()}
PERKS = {int(k): v for k, v in _N["perks"].items()}
TRAITS = {int(k): v for k, v in _N["traits"].items()}
GAME = _load("game.json")                       # tools/extract_game_data.py
UNIQUES = {int(k): v for k, v in GAME["uniques"].items()}
# uniqueId -> uniqueSetIndex, only where UniqueItems.cpp has a set (not -1).
UNIQUE_SETS = {int(k): int(v) for k, v in _load("unique_sets.json").items()}


def is_set_unique(uid):
    return int(uid) in UNIQUE_SETS


def base_name(idx):
    if idx == -1:
        return "(empty)"
    if 0 <= idx < len(BASE_ITEMS):
        return BASE_ITEMS[idx]["name"]
    return "?base %d" % idx


def default_dur(idx):
    try:
        return int(BASE_ITEMS[idx]["durMax"])
    except (IndexError, ValueError, KeyError):
        return 0
