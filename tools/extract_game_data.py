"""Extract game rules / caps / item reference data from th4src -> cheesestick/data/game.json

Sources (all th4src/src):
  th2_proposals.cpp  FullPlayerClasses[]  (name, start stats, MaxStat)
  Item.cpp           GetPlayerFullClass()  (mapping is reproduced in cheesestick/rules2.py)
  PerksData.cpp      Perks[]  (per level: charLevel, requiredClassMask, perkReq, spellReq, s/d/m/v, value[0])
  Perks.cpp          PerkAvailable() special cases (perks whose availability depends on traits/game changers)
  Spells.cpp         Spells[]  (BookQuality, RequiredClassMask)
  th2data.cpp        LevelUpTable / LevelUpTableClassic
  UniqueItems.cpp    UniqueItemsData[]  (name, baseId, qlvl, effects)
  Affixes.cpp        Affixes[]  (prefix/suffix names + effect ranges)
Usage: python tools/extract_game_data.py [th4src_dir] > cheesestick/data/game.json
"""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
S = (sys.argv[1] if len(sys.argv) > 1 else "/workspace/th4/th4src") + "/src/"
rd = lambda f: open(S + f, encoding="utf-8", errors="replace").read()
uncomment = lambda t: "\n".join(l.split("//", 1)[0] for l in re.sub(r"/\*.*?\*/", " ", t, flags=re.S).splitlines())

def enum_values(text, name, env=None):
    body = re.search(r"enum (?:class )?%s\b[^{]*\{(.*?)\};" % name, text, re.S).group(1)
    body = uncomment(body)
    vals, cur = {}, -1
    for part in [p.strip() for p in body.replace("\n", ",").split(",") if p.strip()]:
        if "=" in part:
            k, v = [x.strip() for x in part.split("=", 1)]
            try: cur = int(eval(v.replace("'", "").replace("static_cast<uint>( -1 )", "0xFFFFFFFF")
                                .replace("static_cast<uint>(-1)", "0xFFFFFFFF"), {}, dict(env or {}, **vals)))
            except Exception: continue
        else:
            k = part; cur += 1
        if re.match(r"^\w+$", k): vals[k] = cur & 0xFFFFFFFF if cur < 0 else cur
    return vals

enums = rd("enums.h")
PFC = enum_values(enums, "PLAYER_FULL_CLASS")
IPCM = enum_values(enums, "ITEM_PLAYER_CLASS_MASK", PFC)
IPCM["IPCM_ALL_CLASSES"] = 0xFFFFFFFF
PERK = enum_values(enums, "PERKS")
PS = enum_values(enums, "PLAYER_SPELL")
def mask(expr):
    expr = expr.strip()
    if re.fullmatch(r"[\w\s|&~()]+", expr) is None: raise ValueError(expr)
    return eval(expr, {}, dict(IPCM, **PFC)) & 0xFFFFFFFF

# ---- full classes
fp = uncomment(rd("th2_proposals.cpp").split("FullPlayerClasses[PFC_COUNT] = {", 1)[1])
classes = []
for m in re.finditer(r'\{\s*"([^"]+)"\s*,\s*\{([-\d,\s]+)\}\s*,\s*\{([-\d,\s]+)\}', fp):
    classes.append({"name": m.group(1), "start": [int(x) for x in m.group(2).split(",")],
                    "max": [int(x) for x in m.group(3).split(",")]})
    if len(classes) == len([k for k in PFC if k != "PFC_COUNT"]): break

# ---- perks
pd = rd("PerksData.cpp")
perks = {}
blocks = re.split(r'\n\s*\{\s*((?:PERK|SYNERGY|SYMPTOM)_\w+)\s*,', pd)
for name, blk in zip(blocks[1::2], blocks[2::2]):
    hm = re.match(r'\s*\{(.*?)\}\s*,\s*"([^"]*)"', blk, re.S)
    if not hm or name not in PERK: continue
    descs = re.findall(r'"((?:[^"\\]|\\.)*)"', hm.group(1))
    levels = []
    for lm in re.finditer(r'/\*\s*\d+\s*\*/\s*\{\s*(\d+)\s*,([^{]*),\s*\{([^}]*)\}[^,]*,\s*\{([^}]*)\}[^,]*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*,\s*([-\d]+)\s*(?:/\*sdmv\*/)?\s*,\s*([-\d]+)', blk):
        clvl = int(lm.group(1))
        if clvl == 0: break
        pr = [x.strip() for x in lm.group(3).split(",") if x.strip()]
        sr = [x.strip() for x in lm.group(4).split(",") if x.strip()]
        levels.append({"clvl": clvl, "mask": mask(lm.group(2)),
                       "perkReq": [[PERK[pr[i]], int(pr[i + 1])] for i in range(0, len(pr) - 1, 2)],
                       "spellReq": [[PS.get(sr[i], -1), int(sr[i + 1])] for i in range(0, len(sr) - 1, 2)],
                       "sdmv": [int(lm.group(i)) for i in (5, 6, 7, 8)], "value": int(lm.group(9))})
        if blk[lm.end():].lstrip().startswith("}"): pass
    # stop at the end of this perk's level list
    perks[PERK[name]] = {"key": name, "name": hm.group(2), "desc": descs, "levels": levels}

pa = rd("Perks.cpp")
pa = pa.split("bool PerkAvailable(", 1)[1].split("default: available = true;", 1)[0]
special = sorted({PERK[k] for k in re.findall(r"case\s+((?:PERK|SYNERGY|SYMPTOM)_\w+)\s*:", uncomment(pa)) if k in PERK})
GMV = enum_values(enums, "GAME_MODE")
PCV = enum_values(enums, "PLAYER_CLASS")
def py_cond(e):
    """C condition from PerkAvailable -> small Python expression over T(), GC(), GM, FC, CID, GMT_NORMAL."""
    e = re.sub(r"HasTrait\(\s*playerIndex\s*,([^)]*)\)", lambda m: "T(%s)" % ",".join(
        repr(x.strip().replace("TraitId::", "")) for x in m.group(1).split(",")), e)
    e = re.sub(r"(?:player|Players\[\w+\])\.gameChanger\s*&\s*BIT\(\s*GC_(\d+)_\w*\s*\)", r"GC(\1)", e)
    e = re.sub(r"is\(\s*GameMode\s*,([^)]*)\)", r"(GM in (\1,))", e)
    e = e.replace("GameModeType() == GAME_MODE_TYPE::NORMAL", "GMT_NORMAL")
    e = e.replace("player.fullClassId", "FC").replace("player.ClassID", "CID").replace("GameMode", "GM")
    e = e.replace("MaxCountOfPlayersInGame", "1")
    e = re.sub(r"\bGM_\w+", lambda m: str(GMV[m.group(0)]), e)
    e = re.sub(r"\bPFC_\w+", lambda m: str(PFC[m.group(0)]), e)
    e = re.sub(r"\bPC_\w+", lambda m: str(PCV[m.group(0)]), e)
    e = e.replace("&&", " and ").replace("||", " or ")
    e = re.sub(r"!(?!=)", " not ", e).replace("true", "True").replace("false", "False")
    e = " ".join(e.split())
    env = dict(T=lambda *a: False, GC=lambda n: False, GM=0, FC=0, CID=0, GMT_NORMAL=True)
    eval(compile(e, "cond", "eval"), {"__builtins__": {}}, env)   # must be a valid expression
    return e
body = uncomment(pa).split("switch( perkIndex ){", 1)[1]
conds, pending = {}, []
for m in re.finditer(r"case\s+(\w+)\s*:|available\s*=(.*?);\s*break\s*;", body, re.S):
    if m.group(1):
        pending.append(m.group(1)); continue
    try: c = py_cond(m.group(2))
    except Exception as ex: c = None
    for k in pending:
        if k in PERK: conds[PERK[k]] = c
    pending = []
for p in special:
    if p in perks:
        perks[p]["special"] = True
        perks[p]["cond"] = conds.get(p)

# ---- spells
spells = {}
for m in re.finditer(r'\{\s*(PS_\w+)\s*,([^}]*)\}', rd("Spells.cpp")):
    cols = [c.strip() for c in re.findall(r'"[^"]*"|[^,]+', m.group(2))]
    if m.group(1) not in PS or len(cols) < 13: continue
    try:
        spells[PS[m.group(1)]] = {"name": cols[4].strip('"'), "book": int(cols[6]), "reqMagic": int(cols[10]),
                                  "reqClvl": int(cols[11]), "mask": mask(cols[12])}
    except Exception: pass

# ---- XP tables
xd = rd("th2data.cpp")
def xp(name):
    body = uncomment(xd.split(name, 1)[1].split("{", 1)[1].split("};", 1)[0])
    return [int(x.replace("'", "")) for x in re.findall(r"\d[\d']*", body)]

# ---- uniques
uq = uncomment(rd("UniqueItems.cpp").split("UniqueItemsData[] = {", 1)[1].split("\n};", 1)[0])
uniques = {}
for m in re.finditer(r'\{\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\d+\s]+,(.*?)\}', uq, re.S):
    toks = [t.strip() for t in m.group(9).split(",") if t.strip()]
    effs = []
    for i in range(0, len(toks) - 7, 8):
        effs.append([toks[i], toks[i + 1], *[int(x) if re.fullmatch(r"-?\d+", x) else 0 for x in toks[i + 2:i + 8]]])
    uniques[int(m.group(1))] = {"name": m.group(2), "baseId": int(m.group(3)), "qlvl": int(m.group(6)),
                                "effects": effs[:int(m.group(7))]}

# ---- affixes (reference only: which affixes an item has comes from its seed)
af = rd("Affixes.cpp").split("Affixes[] = {", 1)[1].split("\n};", 1)[0]
pre, _, suf = af.partition("SUFFIXES")
pre, suf = uncomment(pre), uncomment(suf)
affixes = []
for kind, part in (("prefix", pre), ("suffix", suf)):
    for m in re.finditer(r'\{\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)', part):
        affixes.append({"id": int(m.group(1)), "kind": kind, "name": m.group(2), "effect": m.group(3),
                        "type": m.group(4), "nums": [int(m.group(i)) for i in range(5, 11)], "qlvl": int(m.group(11))})

out = {"_source": "roboserg/the-hell-4-src via tools/extract_game_data.py",
       "full_classes": classes, "perks": perks, "perk_special": special, "spells": spells,
       "level_xp": xp("LevelUpTable["), "level_xp_classic": xp("LevelUpTableClassic["),
       "uniques": uniques, "affixes": affixes,
       "consts": {"PlayerMaxLevel": 150, "PlayerMaxLevelClassic": 50, "SpellLevelBookMax": 100,
                  "SpellLevelBookMaxClassic": 15, "SpellLevelMax": 200, "MaxGoldInCell": 100000000,
                  "Limit_Stat": 4000, "GM_CLASSIC": 9}}
json.dump(out, sys.stdout, indent=0)
print("\n%d classes, %d perks (%d special), %d spells, %d uniques, %d affixes, xp %d/%d" % (
    len(classes), len(perks), len(special), len(spells), len(uniques), len(affixes),
    len(out["level_xp"]), len(out["level_xp_classic"])), file=sys.stderr)
