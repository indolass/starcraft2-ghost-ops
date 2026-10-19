# StarCraft II: Ghost Ops

An open mod for *Wings of Liberty* (client 3.1.4) that lets you play the original campaign
missions as tactical special operations: a squad of operatives (Nova first) is added to the
mission, and your regular army deals more damage (x2/x3, configurable) so you can concentrate on the operatives. Original scenario, waves,
timers and victory stay as Blizzard made them.

**Status: P0 accepted for testing, P0.1/P1 in progress.** See [ROADMAP.md](ROADMAP.md). Implemented:
squad of Nova + two standard Ghosts (free permanent cloak, hold fire from the start, hold fire /
weapons free for everybody), BaseSupport army bonus, missions *The Outlaws* and *Smash and Grab*.
Nothing else is implemented.

## How it works

Maps are never shipped. `tools/build.py` reads **your own** copy of the original map, injects the
Ghost Ops code into its `MapScript.galaxy` (one block plus one hook call) and writes a modified
copy. Everything else in the map is kept byte for byte, and `verify` proves it.

```
core/        mission independent Galaxy code (squad, protection)
adapters/    one folder per mission (traynor02, ttychus01): anchors + mission specific Galaxy
config/      one configuration per mission (schema_version 3), turned into Galaxy constants at build time
tools/       sc2mpq.py (MPQ reader/writer), galaxy_lint.py, build.py
tests/       python -m unittest discover -s tests
docs/        architecture, research notes, owner instructions
```

## Use

```
python tools/extract_map.py --casc tmp/thirdparty/casc.dll --mission ttychus01 --out tmp/source/TTychus01.SC2Map   # see docs/EXTRACT_MAP.md
python tools/build.py build   --mission traynor02|ttychus01 [--multiplier 1|2|3]
python tools/build.py install --mission ...     # copies to <SC2>/Maps/GhostOps only
python tools/build.py launch  --mission ...     # prints the direct launch command
python tools/build.py uninstall --mission ...   # exact rollback
```

`GHOSTOPS_SC2_DIR` overrides the install path (default `E:\Games\StarCraft II`).

## Licence

Code, tools and docs: [MIT](LICENSE). Blizzard data and maps are not part of this repository.
