# Research notes (2026-10-19)

## Environment
- SC2 client/editor 3.1.4.41219 (Build Key 9a72e883...), `E:\Games\StarCraft II`, `Versions\Base39576`,
  data locale ruRU. `SC2Data` is CASC (240 files, ~26 GB). There is no loose `Maps\Campaign`.
- Original WoL maps exist only in CASC. Route chosen by the Owner: SC2 Editor `File -> Open ->
  Campaign` + `Save As` into `tmp/source`. Fallback if that fails: an existing CASC library;
  no home-grown CASC parser for now.
- Direct launch: `Support64\SC2Switcher_x64.exe -run "<map>.SC2Map" -displaymode 2`.
- `tools/sc2mpq.py` was checked on a real 3.1.4-era map (`.SC2Map` with a version 3 MPQ header):
  rebuilt archive reads back, all untouched files identical. Game acceptance of the rebuilt
  archive (version 1 header) is expected from earlier work and is checked with the real map.

## Mission data (from the public SC2GameData dump, reference only, not redistributed)
- *The Outlaws* script includes `NativeLib`, `LibertyLib`, `CampaignLib`; players: 1 user,
  2 Dominion (enemy), 3 Colonists (neutral), 4 Rebels (neutral, rescued marines move to the user),
  5 Patrol (enemy).
- `gt_IntroSequence_Func` ends with `TriggerExecute(gt_StartGame, true, false);` - our hook.
- Liberty campaign data has `CUnit id="Nova"` (NovaSnipe, Domination, permanent cloak,
  `HeroNuclearStrike`).

## Sources and licences
| Source | Licence | Use |
|---|---|---|
| PBetzler/wol-unbalanced | MIT (Blizzard data excluded) | patterns only; ideas credited |
| ArchipelagoMW/Archipelago | MIT | reference |
| erivgout/sc2-map-editor-mcp | MIT | experimental, not a dependency |
| SC2Mapster/SC2GameData | none (Blizzard data) | read-only reference, never copied or published |
| 7thAce/SC2CCM | none | reference only |

## Lessons taken from wol-unbalanced (docs/learnings.md)
- Campaign UI prefers loose `Maps/Campaign/<name>.SC2Map` over CASC; maps are MPQs.
- Changing a map's dependencies needs three patches (DocumentInfo, binary DocumentHeader,
  MapScript include). We do not change dependencies, so only MapScript is patched.
- Array appends in catalog XML need an explicit `index`; per-player catalog edits only change
  scalar fields. Not needed for the PoC (no catalog changes).
- The SC2 Editor test run is a sanctioned validation path; retail API live reads are not usable.
- Galaxy is single pass: declare before use.

## Map extraction attempts (2026-10-19)
- SC2 Editor: starts (PID launched and closed by us). Shows "Downloading Required Dependencies
  0/3040, 1.04 GB, Download Failed" - the 3.1.4 install is missing editor data and the CDN no
  longer serves it. Its GUI menu is not exposed through UI Automation (Win32 menu ids are readable);
  sending window messages to it was blocked by the permission classifier, so no GUI automation was attempted further.
- CASCConsole v1.0.240 (WoW-Tools/CASCExplorer, no licence file, local tool only, kept in git-ignored `tmp/thirdparty`):
  fails with NullReferenceException in `CASCConfig.get_FileIndex` - this old install has no
  `file-index` in its CDN config, so the C# CascLib cannot open it.
- Jev's approach (not copied; no licence): C++ CascLib (ladislav-zezula/CascLib, MIT) reads
  `campaigns\liberty.sc2campaign\base.sc2maps\maps\campaign\traynor02.sc2map\*` and the files are
  repacked into an MPQ (skipping localisations other than base/enUS). We can repack with `tools/sc2mpq.py`.
  CascLib releases ship no binaries and the machine has no C++ compiler.
