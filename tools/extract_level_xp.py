"""Extract LevelUpTable (non-classic) from th4src/src/th2data.cpp -> tools/level_xp.json"""
import json, re, sys
src = (sys.argv[1] if len(sys.argv) > 1 else "/workspace/th4/th4src") + "/src/th2data.cpp"
t = open(src, encoding="utf-8", errors="replace").read()
body = t.split("LevelUpTable[ PlayerMaxLevel_150 + 1 ] = {", 1)[1].split("};", 1)[0]
body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
body = "\n".join(l.split("//", 1)[0] for l in body.splitlines())
vals = [int(x.replace("'", "")) for x in re.findall(r"\d[\d']*", body)]
json.dump(vals, sys.stdout)
print("\n%d levels" % len(vals), file=sys.stderr)
