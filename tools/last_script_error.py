"""Prints the compile / load lines of the newest ScriptError.txt of the game (read only): python tools/last_script_error.py [N lines]"""
import glob
import os
import sys

DOCS = os.path.join(os.path.expanduser('~'), 'Documents', 'StarCraft II', 'GameLogs')
files = sorted(glob.glob(os.path.join(DOCS, '*ScriptError.txt')), key=os.path.getmtime)
if not files:
    raise SystemExit('no ScriptError.txt')
text = open(files[-1], encoding='utf-8-sig', errors='replace').read()
lines = text.splitlines()
keep = [i for i, l in enumerate(lines) if 'compile error' in l or 'load failed' in l]
print(os.path.basename(files[-1]), 'compile/load lines:', len(keep))
for i in keep[: int(sys.argv[1]) if len(sys.argv) > 1 else 6]:
    for l in lines[i:i + 2]:
        print(l.encode('ascii', 'replace').decode()[:240])
