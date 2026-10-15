"""Pull classic-mode and exile flags out of BaseItems.cpp.

base_items.json does not store column 1 (mode / isClassic) or column 47
(ForbiddenForExiles). Those two lists are what the item browser needs.
The script writes compact id lists, not item art.

Usage:
  python tools/extract_item_flags.py <th4src>/src/BaseItems.cpp cheesestick/data/item_flags.json
"""
import json, re, sys

src = sys.argv[1]
out = sys.argv[2]
text = open(src, encoding="utf-8", errors="replace").read()
body = text.split("BaseItemsData[] = {", 1)[1]
classic, both, exile, seen = [], [], [], []
for line in body.splitlines():
    line = re.sub(r"/\*.*?\*/", "", line).split("//", 1)[0].strip()
    if not line.startswith("{"):
        if line.startswith("};"):
            break
        continue
    cols = [c.strip() for c in re.findall(r'"[^"]*"|[^,{}]+', line) if c.strip()]
    if len(cols) < 48:
        continue
    bid, mode = int(cols[0]), int(cols[1])
    flag = cols[47].lower()
    seen.append(bid)
    if mode == 1:
        classic.append(bid)
    elif mode == 2:
        both.append(bid)
    elif mode != 0:
        raise SystemExit("unexpected mode %s on base %s" % (mode, bid))
    if flag in ("true", "1"):
        exile.append(bid)
    elif flag not in ("false", "0"):
        raise SystemExit("unexpected exile flag %r on base %s" % (cols[47], bid))

if seen[0] != 0 or seen[1] != 1:
    raise SystemExit("expected Gold then Short Knife, got %s" % seen[:2])
if 0 not in both or 0 in exile or 1 in classic or 1 in exile:
    raise SystemExit("Gold/Short Knife flags did not match BaseItems.cpp")
doc = {"classic": classic, "both": both, "no_exile": exile,
       "_source": "BaseItems.cpp columns mode (isClassic) and ForbiddenForExiles"}
with open(out, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=1)
    f.write("\n")
print("rows %d  classic %d  both %d  no_exile %d" % (len(seen), len(classic), len(both), len(exile)))
