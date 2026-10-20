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

## TTychus01 artifact race (analysis 2026-10-19, not implemented)
Chain, from the 3.1.4 script: `gt_StartAI` -> `gt_ZergAttackWavesProtoss` starts `gv_zergSpeedBumpTimer`
(Hard 1440 s, AI time; Brutal 1260) and `...Shorter` (timer - 60 s) and sends Zerg waves targeting
waypoint 724 (the approach to the artifact at 170,52). `gt_AddZergSpeedBumpUnit` takes every Zerg
unit entering region 61 ("Zerg Speed Bump", near 154,68) under script control; `gt_ZergSpeedBumpController`
makes them wander and fight in region 62 (the Upper Protoss base). When the timer expires,
`gt_ZergSpeedBumpTimerExpires` releases them (`AIAttackWaveUseGroup` + `AIAttackWaveSend` to 724).
`...NearsExpiration` (60 s before) adds drop-pod Zerglings and boosts Protoss Gateways. Zerg units
that enter region 6 (162,63) join `gv_zergArtifactAttackers`; `gt_ZergArtifactAttacking` (every 2 s,
from the start) sends them at the guardians. `gt_ArtifactGuardianDestroyed`: all south guardians dead
or (all north dead and the player has more units than Zerg in region 63) = victory; all north dead
otherwise = the Zerg Overlord takes the artifact and `gt_DefeatArtifactLost` runs. So the timer
only delays the Zerg stream; defeat before expiry is possible by Zerg that reach region 6 without the
bump (flyers such as Mutalisks; burrowed units from `gt_ZergAttackWavesPlayer` go to the player).
Proposal (needs Owner approval): pause `gv_zergSpeedBumpTimer` and `gv_zergSpeedBumpTimerShorter`
(`TimerPause`) at the post-intro hook. Zerg keep fighting the Protoss in region 62, waves, upgrades and
Protoss warp-ins continue, difficulty is untouched, the artifact, guardians, victory and
`gt_DefeatArtifactLost` stay as they are. Side effects: timer-threshold hints and Protoss reactions
(`< 60/120/180 s`) never fire, the extra drop-pod wave never comes, Zerg stay held in region 62 (they
can block the route there). `relaxed` would instead restart both timers with a longer duration.

## TRaynor01 notes (2026-10-19)
- Intro has two branches: watched (`gt_IntroCleanupNoEscape`, cargo marines change owner to player 1) and skipped
  (`gt_IntroCleanupEscape`, Raynor01 + 5 Marines are created at points 505/415/581/737/885/1020). Both call
  `TriggerExecute(gt_StartGame...)`; Ghost Ops hooks both (squad appears once, `GhostOps_ClaimStart`). The 9 later
  Marines come from `gt_RiksvilleTownSquareDropPods` (3 + 3 + 3, created for player 1 in drop pods); the 0.2 s
  fragile scan lowers their maximum life before they land.
- Hard: `-difficulty 3` on `SC2Switcher_x64.exe` works on 3.1.4: the in-game message showed
  "PlayerDifficulty at init = 3, now = 3" (init value recorded by a hook before `gt_Init06Difficulties`).
  The mission's own Hard effects are in `gt_Init06Difficulties` (Dominion infantry armor +1 on Hard).
- Direct launch shows a **black world view after the intro even for the unmodified original map** (both the
  repacked extraction and the original read straight from CASC via `-run "Campaign\TRaynor01.SC2Map"`), with the
  objective panel visible. So it is not caused by Ghost Ops. A `CameraPan` to Raynor's start point was added to
  the adapter as a diagnostic; whether it helps is for the Owner's game check.
- Screenshots for diagnostics must only be taken while the game window is in front (they otherwise capture the
  user's desktop).

## Galaxy source must be ASCII; where compile errors are logged (2026-10-19)
- A Cyrillic/em-dash string literal in the injected block (the profile message) made `MapScript.galaxy` fail to compile:
  the map opened with an empty black HUD and no mission. The game writes the reason to
  `Documents\StarCraft II\GameLogs\<time> ScriptError.txt` ("Script compile error: MapScript.galaxy (line) ...");
  an empty file means no error. Check it after every launch of a new build.
- Fix: texts for players live in the map's `GameStrings.txt` (build adds `Param/Value/GhostOpsProfile` to the ruRU and
  enUS files, marked and restorable) and Galaxy reads them with `StringExternal`; the build refuses a non-ASCII script block.


## TRaynor02 notes (2026-10-19, tactical variant)
- Original script (5123 lines): player 1 start base at (82.5; 29.5) with 6 Marines, Barracks, depot; rebels (P4: 4 Marines, 3 Medics, Barracks,
  depots, TechLab) at (36..48; 20..36), rescued all at once by `gt_RebelsCompleteQ_Func` through `libNtve_gf_RescueUnit` (hook point); Dominion (P2)
  main base around (43; 98) with 2 Barracks, Factory, CC, 4 depots, bunker, tank. Defeat: no PreventDefeat unit of player 1 left; victory: none of
  player 2. `gt_StartAI` starts the campaign AI of P2 and P4; waves come from `gt_DominionAttackWaves` (units asked from the AI, i.e. from its
  production); P5 marines are created by script in `gt_DominionAttackerSquads` and `gt_MineGuardsActivate` (independent of buildings). On Hard the
  Dominion structures have `AIRebuild` = 1, so the AI rebuilds destroyed production. Owner decision (2026-10-19): all of this stays the original's; the
  earlier module logic that stopped the spawner triggers and banned rebuilding after the production was destroyed was removed.
- The mission's campaign tech restrictions hide the nuke chain (arming shows only with `AllowUnitGhost` and a Factory) and the player starts at
  supply 20/19 (a Marine cannot be trained before a depot is built: original behavior).
- Launching a test through `-run` from `Maps\GhostOps` always logs "not authorized" campaign init lines in `ScriptError.txt`: known noise.
- Automatic test launches: `tools/test_launch.py` (second monitor, windowed, muted per process, see `CLAUDE.md`); window measured: client
  1024x768 -> outer 1050x791 at the second monitor's work area; audio session of the process found and muted (`sessions=1 confirmed=1`).
- Tested in the real game by script (mode 1..5 of `tactical_dev`): arming, aim 12.0 s, cancel and re-arm, launch, flight 6.0 s, blast with stock
  damage (13 of 15 enemy Marines and 3 of 7 SCVs died, structures survive: stock 300+200 damage), retreat to 19.8 at the blast (alive), no
  retreat -> the Spotter dies of its own missile without a defeat, death while aiming -> defeat, the Operative cannot order the strike,
  garrison weapon off outside / back inside once / x20 vs x0.1 damage measured on a Barracks (1000 life: 375 vs about 50 in comparable time),
  rescued Marine untouched, real barracks Marine gets 1/1 by the creation event.
- Not tested: save/load, the victory scene, the real run through the mission, the zone border look (second monitor window is usually covered).


## TRaynor02 final stage (2026-10-19): damage, save/load
- `DamageDealtFraction` of a catalog behavior is additive: the first build (values 20 and 0.1) measured x21 (125 per hit on armor 1) and x1.1 (5.601 per hit
  against 5.0 of a plain Marine); the old "about 50 damage in 8 s" of a trained Marine was therefore really ~9 hits of 5.6 plus nothing, not a x0.1
  result. After the fix: garrison 119, plain 5.0, trained 0.5 per hit (minimum damage 0.5 after armor).
- Save / load: `GameSaveCreate` is "Blizzard maps only" (not authorized here), so the save is made through the game's own menu (F10 -> Save), sent as posted
  window messages to our test window (`tools/sc2_ui.py`, no focus change); `TriggerAddEventSaveGame/SaveGameDone/LoadGameDone` fire for these saves.
  Saves land in `Documents\StarCraft II\Saves\Multiplayer` and were deleted after the test. Case A (before aiming) and case B (in flight, dev flight time
  60 s so that the save fits) both passed (see README). Window screenshots: `PrintWindow` of our own window works while other windows cover it.
- Galaxy: a function with a very long string concatenation fails the whole script load with "register overflow" (Russian message
  "Переполнение регистра"): split long log lines.
- One launch of the production map ended at the Battle.net login screen instead of the mission (no ScriptError was written); the repeat launch of the same
  installed file started normally. Seen once, cause not found.


## TRaynor02 story scene (2026-10-19)
- Portraits: models `AdjutantPortrait` (liberty mod) and `SwannPortrait` (liberty campaign) exist and show with `TransmissionSourceFromModel` + `TransmissionSend(...,
  soundlink null, speaker, subtitle, duration, c_transmissionDurationSet, wait)`; the speaker text is shown as the colored name before the subtitle ("Тревога!:", "Свонн:");
  with `TriggerQueueEnter` the first message waited for the original talk (production timing: start 1.8 s, message at 34.3 s, over at 51.9 s; the next 30.4 s later).
- The transport pattern of the map itself (`gt_SupplySafetyCreateDrop`): `SpecialOpsDropship` at point 472, not selectable / targetable / supply, cargo by
  `UnitCargoCreate`, `SpecOpsDropshipTransport` index 2 at the drop point, then `move` to the center of region 31. Measured here: created -> unloaded 12 mission seconds, removed 7 s later.
- Real saves of the scene (menu save at stage 2 and with the transport on the way, then load): scene stage kept, one transport, two Ghosts, one missile, no repeated
  message (a message thread cut by the load simply ends: not repeated). The `Doubled Barracks` the Owner once saw on the base were the developer map's test units (see CLAUDE.md rule 8).
- `UnitSetInfoText` gives the Ghosts a tooltip with role and description; `ObjectiveCreate` (secondary) and `HelpPanelAddTip` keep the explanation reviewable.


## Voice clips in maps (2026-10-20)
- A `CSound` with `parent="SM_Old"` (category Dialogue, so the campaign's `SetAllSoundChannelVolumes(Cinematic)` that zeroes the Voice category does not mute it) and
  `<AssetArray File="Assets\Sounds\GhostOps\x.wav"/>` plays with `SoundLink("id", 0)`; the file lives in the map archive. `SoundLengthSync` returned 0.00 for it (and for
  nothing else useful: the original dialogue id gave 6.00), but a probe transmission with `c_transmissionDurationAdd, 0.0` lasted 2.75 mission s for the 1.45 s clip (a
  transmission always adds about 1 s), i.e. the engine reads the clip. Pure listening is not verifiable while the test game is muted.
- A transmission with a sound link does not show its text argument when the player option `subtitles` is 0 (the Owner's): the script shows the lines with
  `UIDisplayMessage(c_messageAreaSubtitle, ...)` itself (lines pile up in the area; screenshots in the session notes).
- Transmission durations (`c_transmissionDurationSet`) are real seconds + about 1 s; mission time (`GameGetMissionTime`, `c_timeGame`) runs 1.2x at the game's Fast speed
  (1.4x at Faster): 0.5 s real pause measured as 0.62 mission s.
- The dialogue queue (`TriggerQueueEnter`) holds our messages behind the original talk: in the dev build an original talk of about 28 s delayed Swann (and the transport that
  now starts with him) from +15.2 s to +28 s after the Adjutant message.


## THanson01 (2026-10-20), facts from the installed map
- The phases: `gv_missionPhase` 0 = tactical (2 Firebats + 2 Medics reach the colony, region 29), then 1 = escort; entering region 29 hands the settlement (SCVs, Command
  Center, Barracks, depot, refinery, Merc Compound) to player 1 and the convoy loop starts about 43 s later: `gt_Preparenextconvoy` -> `gt_Gathercolonistspriortoevacuation`
  (colonists every 2.25 s, + 18 s) -> `gt_ConvoySpawned` (the trip: `gt_SendColonists` with the AI escort wave of 2 / 3 / 4 Marines, then one of `gt_ConvoyAttack1..7`, each waits
  with `gf_WaitForColonistToEnterRegion` for **colonists** in the road regions, so the Ghost scouting does not start attacks) -> `gt_WaveOverLogic` (colonists all gone) -> wait
  `gv_waveDelay` (Hard 25 s) -> `gt_Preparenextconvoy`.
- Hard values: unload 10/10/10/12/12/16 colonists, victory 50 saved, defeat 20 killed (`libNtve_gf_DifficultyValueInt(0,0,20,20)`), late raids once `gv_convoyTrucksSent` >= 6,
  raid size 4 Mutalisks per spawn point (2 points) +2 each time, Overseers from the second raid, marine refill every 10 s up to the initial 7 near point 2079.
- The Zerg players are *neutral/passive* towards player 1 and 4 (alliance 5 in `libNtve_gf_SetAlliance`); a test unit of player 2 neither auto-acquired nor damaged a Marine
  with an explicit attack order until the alliance was set to 8 (enemy). The original waves still hurt (colonists died in the test), the AI evidently ignores the flag.
- Snipe (stock): target filter `Biological,Visible;Self,Structure,Destructible,Stasis,Dead,Hidden,Invulnerable` (own and allied units were allowed), damage 45 `Death=Silentkill`,
  `ArmorReduction 0`. An override of `TargetFilters` needs `index="0"`, without it the stock filter stayed. With damage 1000: Zergling, Hydralisk, Roach, Mutalisk,
  Overseer, Corruptor, Ultralisk (600 life), Baneling, Queen died in one shot; Marine (ally), Civilian, ColonistTransport, SpineCrawler and an own Marine were refused.
  Cooldown 1.0 s counts from the hit: two shots, second death 1.56 s after the first (0.56 s = cast 0.3 + flight).
- Development lock: `TechTreeUnitProducesUnitCount/Unit/UpgradeCount/Upgrade` give 19 units + 19 upgrades for the SCV, 10 + 10 for the Barracks, 2 + 2 for the Command Center;
  after `TechTreeUnitAllow(false)` every train / research / add-on / Merc order was refused (order count 0); an SCV order `TerranBuild` index 0 (Command Center) was accepted until
  the type was forbidden explicitly, afterwards it built nothing (fixed list `GhostOps_Hanson_LockFixed`).
- Screen button: `DialogCreate` + `DialogControlCreate(button)` with no template draws a plain small button (about 0.57 of its size at a 1024 window), text via
  `DialogControlSetPropertyAsText`, click via `TriggerAddEventDialogControl(... c_triggerControlEventTypeClick)`; the dialog is lost with a load and made again in `TriggerAddEventLoadGameDone`.
- `GameSetGlobalTimeScale` did not speed the mission up in the test game. `UnitCreate` moves a structure to the nearest valid place (up to 7 cells), logs show the real one.
- Passability dump of the settlement (`hanson.autotest.mode` 6) and the turret layout are in the session notes; the far north (y >= 60) is full of the map's Zerg units, which
  killed turrets placed there; late raids (8, 14, 18 Mutalisks) cleared by 15 turrets in 50-75 s, 12 turrets of 15 left with 71 % of their life, no repair by the player.


## CE-0 (2026-10-20): saves, Bank, map set, resources, turret events (installed game 3.1.4, real runs)

Method: hidden dev presets `ce0_dev` (TRaynor02, THanson01) and `ce0_wait_dev` (TRaynor02, Swann wait 70 s) build the probe `core/GhostOpsCe0.galaxy` +
`adapters/*/ce0_extra.galaxy` (config key `ce0`, never in a playable profile: `tests/test_ce0_build.py`). The probe writes a journal into the Bank `GhostOpsCe0`
(`Documents\StarCraft II\Banks\GhostOpsCe0.SC2Bank`, section `j`; result proposals in section `r`) and takes chat commands (Enter, text, Enter) typed into the
test window. Helpers: `tools/ce0_session.py`, `tools/ce0_ui.py` (menu flows checked on screenshots), `tools/sc2_ui.py`. The test window was on the PRIMARY monitor
(no second monitor was detected in this session; 1024x768 start size, muted by process, never activated). All saves were made through the game menu
(F10 -> Save), named `CE0_*`, and are deleted after the work; the Owner's saves were never touched.

Saves and loads
- A load returns the whole saved state: Ghosts (life, energy), Marines, resources, ammunition (nukes 1 -> 0 after a launch -> 1 after the load), scene stage,
  transport and passengers, kit counters, a mission counter that lives only in the game (`marker`). Evidence: journal rows `SNAP ...` at SAVEGAME vs `SNAP LOAD done`.
- TRaynor02 nuclear chain with three named saves of ONE attempt (N1 ready, N2 aiming, N3 in flight), loaded in the order N2, N1, N3, N1: N2 -> the aiming goes on and
  the launch happens once (nukes 0), N3 -> the blast happens once, no second missile, no new Ghosts, no false defeat (`ended=0`), N1 -> ready again, nukes 1.
- Loss of two Marines, Ghost life 20, energy 7 after N1, then load N1: Marines 6, Ghosts 45/45, energy 100, minerals as saved.
- Swann wait (`ce0_wait_dev`): save at stage 2 (waiting), let the first delivery finish, load: stage 2 again, one transport, one message, two Ghosts, one `Ghost line`.
- THanson01: save with the convoy command ready (state 2) and during the trip (state 3, `sent` 1): loads give exactly those states, no second convoy, the command
  can be given again from the state-2 save (real click on the screen button, client coordinates).
- Closing the game: WM_CLOSE -> confirm dialog -> normal exit; a record written before survives; `taskkill` after a record also keeps it. A new process then
  loads a save of the old process (the map started by `-run`, then F10 -> Load): the loaded game has the SAVED attempt identity.
- `SC2Switcher_x64.exe -run <save>` does NOT open a save: it ends at the Battle.net login screen. A load has to be done inside a running game; loading from the main
  menu needs the Owner's login and was not tried.
- The F10 menu pauses the game, the in-game restart ("Начать задание заново") asks for a difficulty (default Ветеран = Hard) and starts the map from the beginning.
- Defeat screen offers Load / Restart / Abort / Exit.

Bank behaviour (important for any result channel)
- A production-style map in `Maps\GhostOps` writes the Bank file on every `BankSave`; Python reads it without problems (no signature needed; the probe sets
  `BankOptionSet(.., c_bankOptionSignature, false)`).
- A save contains the Banks: `save.ioBanks` holds a snapshot of the banks of the game (also all Blizzard campaign banks listed in `save.ioBankList`).
  A LOAD RESTORES THE BANK TO THE SAVED STATE: rows of the cancelled future disappear, the next write overwrites the file with the restored content, and the
  Bank's own sequence counter repeats (never use a Bank sequence as a global order or an id).
- Editing the Bank file from another process breaks it for the game: after an external edit the next `BankReload` / write produced an empty bank. The launcher
  must only READ the Bank (and delete it only while no game runs). A launcher -> map channel through a Bank needs a valid signature and was not found.
- A fresh process or an in-game restart starts with an empty bank (the old file is not read back); the file on disk is stale only until the first write
  (about 2 s after the map starts).
- `RandomInt` differs per fresh start (attempt ids differ) and is deterministic after a load (the same values at the same moment after loading the same save twice).

Map set for saves (`.SC2Save` = MPQ with `save.details`, `save.initData`, `save.download`, `save.ioSync/ioAsync`, `save.ioBanks`, `save.ioBankList`, `save.ioLoadInfo`)
- The save names the map by RELATIVE PATH under `Maps` (`GhostOps/GhostOps_TRaynor02_ce0_dev.SC2Map`) and the Liberty mod/campaign; the map file itself is not inside.
- Original file present: loads. Same path, DIFFERENT content (a rebuild, other sha256): loads, and the game continues with the code of the SAVE (the new `mine` command
  was unknown after loading an old save); data (catalog / strings) effects of a different content were not examined. Original bytes put back: loads.
- File missing, the same bytes under another file name in the same folder, the same name in another folder: "Невозможно открыть карту" and the process falls back to the login screen.
- Consequence: the set of a started operation needs its own UNIQUE file name that is never overwritten, kept until no supported save depends on it (rule of keeping:
  Owner decision). One hash is not proof of save compatibility (not checked by the game in the tested case, so it cannot be used as proof either).

Resources
- `c_playerPropMineralsCollected` = mined minerals only (script grants are not counted; SCV mining +125 observed on min 100 -> 225). Spending a Marine lowers the
  mineral count by 50 with no native "spent" counter. There is no native "found" counter. So the report can state start, mined (native) and the NET of found/spent;
  found and spent need own accounting at the places that grant or spend (mission handler / kit events).
- The standard victory sequence is started by `gt_VictoryDominionOutpostCompleted_Func`; our hook after `gv_gameOver = true;` reads the resources BEFORE the sequence
  (min 950 at the hook, 1020 a few game seconds later because mining goes on).

Turret kits (THanson01, `ce0_dev`; dev fixture: an Engineering Bay created by the probe; no price)
- A structure built by an SCV: `TriggerAddEventUnitCreated(.., "TerranBuild", ..)` fires at placement (life 25), the progress events have the SCV as `EventUnit()` and the
  structure as `EventUnitProgressUnit()` (`EventUnitProgressObjectType` = MissileTurret); there is no `EventUnitProgressStage`, one trigger per stage is needed.
- `CatalogFieldValueSet(c_gameCatalogUnit, "MissileTurret", "CostResource[Minerals]", 1, "0")` works at run time (the turret became free for player 1);
  `TechTreeUnitAllow(1, "MissileTurret", free kits > 0)` makes the next order invalid when no kit is free (third build refused with 2 kits).
- Complete -> spent; killing a FINISHED turret returns nothing (measured). The player's own cancel (select the unfinished turret, Escape) gives the progress event
  `Cancel` FIRST (the structure is already gone: alive 0) and the death event second; killing an UNFINISHED turret gives the death event FIRST and the `Cancel`
  progress event second. So the order of the two events tells "cancelled by the player" (kit returns) from "destroyed unfinished" (the probe counts it as
  `lostUnfinished`; whether that kit returns is an OPEN rule question for the Owner). Script `CancelBuilding` / `BuildInProgress` orders did NOT cancel.
- A save during construction restores the reserved kit and the turret under construction (the kill made after the save is not kept).
- Kit rule N ordered -> N free builds (start reserves, cancel returns, completion spends, finished-turret death returns nothing) is technically possible
  with these events. This is a PROBE; nothing of it is in a playable profile.

Not verified in CE-0: loading from the SC2 main menu (needs the Owner's login), data (catalog) effects of replacing a map file under the same name,
quick save, named slots beyond the menu, autosave, loads of a save whose Galaxy globals changed, an uninterrupted `ScriptError` review of every long run (compile
was clean in each launch; the known campaign-init "not authorized" lines appear).
Side effect to know: every run of a map from `Maps\GhostOps` (and every load) rewrites the Blizzard campaign Bank files in `Documents\StarCraft II\Banks`
(TCampaign, TRaynor01, ..., listed in `save.ioBankList`) with the snapshot the game holds; this is the existing behaviour of the campaign init code, not of the probe.
