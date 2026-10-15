"""Prototype: pull base item rows out of th4src/src/BaseItems.cpp into JSON for GUI pickers.
Usage: python tools/extract_base_items.py [th4src_dir] > base_items.json
Columns follow the header comment in BaseItems.cpp (baseId, isClassic, ChanceToDrop,
ItemType, EquippedLocation, ..., ItemCode, uniqLine, throwing, Name, Name2, QualityLevel, ...)."""
import json, re, sys
src = (sys.argv[1] if len(sys.argv) > 1 else "/workspace/th4/th4src") + "/src/BaseItems.cpp"
text = open(src, encoding="utf-8", errors="replace").read()
body = text.split("BaseItemsData[] = {", 1)[1]
rows, gvs = [], []
def _i(x):
    try: return int(eval(x.replace("'", ""), {}))
    except Exception: return 0
def extra(cols):
    """damage/armor ranges, requirements (min-max), class mask, spell, price, base effects (8 per effect)"""
    effs = []
    rest = cols[57:]  # col 56 = base effect count
    for i in range(0, len(rest) - 7, 8):
        effs.append([rest[i], rest[i + 1], *[_i(x) for x in rest[i + 2:i + 8]]])
    return {"dmg": [_i(c) for c in cols[16:20]], "armor": [_i(c) for c in cols[20:22]],
            "req": {k: [_i(cols[j]), _i(cols[j + 1])] for k, j in (("Str", 36), ("Mag", 38), ("Dex", 40), ("Vit", 42), ("Lvl", 44))},
            "classMask": cols[46], "spell": cols[51], "price": [_i(cols[54]), _i(cols[55])], "effects": effs}
for line in body.splitlines():
    line = re.sub(r"/\*.*?\*/", "", line).split("//", 1)[0].strip()
    if not line.startswith("{"):
        if line.startswith("};"): break
        continue
    cols = [c.strip() for c in re.findall(r'"[^"]*"|[^,{}]+', line) if c.strip()]
    if len(cols) < 14: continue
    rows.append({"baseId": int(cols[0]), "itemType": cols[3], "equipLoc": cols[4],
                 "itemCode": cols[8], "name": cols[11].strip('"'), "name2": cols[12].strip('"'),
                 "qlvl": cols[13], "durMin": cols[14], "durMax": cols[15], "magicCode": cols[49] if len(cols) > 52 else "", "useOnce": cols[52] if len(cols) > 52 else "0",
                 **(extra(cols) if len(cols) > 55 else {})})
    gvs.append(eval(re.sub(r"[^0-9+\-* ]", "", cols[7]) or "0"))
# inventory size in cells from dataseg.cpp ItemWidthTable/ItemHeightTable (pixels, 28 per cell)
ds = open(src.replace("BaseItems.cpp", "dataseg.cpp"), encoding="utf-8", errors="replace").read()
def table(name):
    body = ds.split(name + "[MAX_9000_ITEM_PICS] = {", 1)[1].split("};", 1)[0]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return [int(x) for x in re.findall(r"-?\d+", body)]
W, H = table("ItemWidthTable"), table("ItemHeightTable")
CM_12 = 12
for r, gv in zip(rows, gvs):
    g = gv + CM_12
    r["graphic"] = gv
    r["w"] = max(1, round(W[g] / 28)) if g < len(W) and W[g] else None  # None: size only known at runtime (sprite)
    r["h"] = max(1, round(H[g] / 28)) if g < len(H) and H[g] else None
json.dump(rows, sys.stdout, indent=1)
print("\n%d base items" % len(rows), file=sys.stderr)
