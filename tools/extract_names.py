"""Extract spell, perk and trait names from th4src -> tools/names.json
spells: index -> name (Spells.cpp row order, PS_ index); perks: id -> name; traits: id -> name."""
import json, re, sys
S = (sys.argv[1] if len(sys.argv) > 1 else "/workspace/th4/th4src") + "/src/"
rd = lambda f: open(S + f, encoding="utf-8", errors="replace").read()

def enum_values(text, name):
    body = re.search(r"enum (?:class )?%s\b[^{]*\{(.*?)\};" % name, text, re.S).group(1)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    vals, cur = {}, -1
    for line in body.splitlines():
        line = line.split("//", 1)[0].strip().rstrip(",")
        for part in [p.strip() for p in line.split(",") if p.strip()]:
            if "=" in part:
                k, v = [x.strip() for x in part.split("=", 1)]
                try: cur = int(eval(v.replace("'", ""), {}, vals))
                except Exception: continue
            else:
                k = part; cur += 1
            if re.match(r"^\w+$", k): vals[k] = cur
    return vals

enums = rd("enums.h")
spells = {}
for m in re.finditer(r'\{\s*(PS_\w+)\s*,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*"([^"]*)"', rd("Spells.cpp")):
    spells[m.group(1)] = m.group(2)
ps = enum_values(enums, "PLAYER_SPELL")
spell_list = {}
for i, (k, n) in enumerate(spells.items()):
    spell_list[ps.get(k, i)] = n
perk_enum = enum_values(enums, "PERKS")
perks = {}
for m in re.finditer(r'\{\s*(PERK_\w+|SYNERGY_\w+)\s*,\s*\{[^}]*\}\s*,\s*"([^"]*)"', rd("PerksData.cpp")):
    perks[m.group(1)] = m.group(2)
perk_list = {}
for i, (k, n) in enumerate(perks.items()):
    perk_list[perk_enum.get(k, i)] = n
traits = {v: k for k, v in enum_values(enums, "TraitId").items()}
json.dump({"spells": spell_list, "perks": perk_list, "traits": traits,
           "_note": "perk ids from enum if found else table order"}, sys.stdout, indent=0)
print("\n%d spells, %d perks (enum %s), %d traits" % (len(spell_list), len(perk_list), bool(perk_enum), len(traits)), file=sys.stderr)
