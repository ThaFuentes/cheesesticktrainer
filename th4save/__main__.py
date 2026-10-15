import argparse, json, os, shutil, sys
from .save import SaveFile


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m th4save")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="print archive entries and hero summary")
    d.add_argument("file"); d.add_argument("--full", action="store_true", help="print every field")
    r = sub.add_parser("roundtrip", help="load and re-write without edits, then verify")
    r.add_argument("infile"); r.add_argument("outfile")
    a = ap.parse_args(argv)

    if a.cmd == "dump":
        s = SaveFile.load(a.file)
        print("archive entries:")
        for n, data in s.archive.files.items():
            print("  %-20s %7d bytes (encoded)" % (n, len(data)))
        if s.archive.unknown_blocks:
            print("  + %d entries with unknown names" % len(s.archive.unknown_blocks))
        print("hero entry:", s.hero_entry)
        out = s.player.summary()
        if a.full:
            out = {k: v for k, v in s.player.items() if not isinstance(v, list)}
            out = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in out.items()}
        print(json.dumps(out, indent=2))
        return 0

    if os.path.abspath(a.infile) == os.path.abspath(a.outfile):
        print("refusing to overwrite the input file", file=sys.stderr); return 2
    s = SaveFile.load(a.infile)
    data = s.to_bytes()
    with open(a.outfile, "wb") as f:
        f.write(data)
    s2 = SaveFile.load(a.outfile)
    ok = s2.hero_plain == s.hero_plain and all(
        s2.decoded(n) == s.decoded(n) for n in s.archive.files)
    print("wrote %s (%d bytes); decoded contents identical: %s" % (a.outfile, len(data), ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
