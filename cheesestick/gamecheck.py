"""Is The Hell 4 running? Windows only, via the built-in `tasklist` (no extra dependencies)."""
import csv, io, re, subprocess, sys

GAME_EXE = re.compile(r"^(th4.*|the ?hell ?4.*)\.exe$", re.I)


def parse_tasklist(text):
    """tasklist /FO CSV /NH output -> matching image names."""
    names = []
    for row in csv.reader(io.StringIO(text)):
        if row and GAME_EXE.match(row[0].strip()):
            names.append(row[0].strip())
    return names


def running_game_processes():
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return []
    return parse_tasklist(out)
