# StarCraft II: Ghost Ops

An open mod for *Wings of Liberty* (client 3.1.4) that turns original campaign missions into special operations for a few operatives (Ghosts). Maps are never shipped:
a build reads **your own** copy of the original map and injects the Ghost Ops code. Each mission has its own variant (see "The first three missions and the campaign link" and the mission sections below);
the squad, the rules and what is changed differ per mission:

| mission | what the variant is | squad |
|---|---|---|
| *Liberation Day* (TRaynor01) | profiles easy / hard / extreme (experiments); a short scene with the wounded squad | 2 Ghosts (easy, hard), 1 Ghost (extreme) |
| *The Outlaws* (TRaynor02) | tactical variant (experiment): the Ghosts arrive by transport, a nuclear strike aimed by the Spotter; the death of the Spotter before the launch is added as a defeat | 2 Ghosts |
| *Zero Hour* (TRaynor03) | revision 4 (`defence_r4`, free test `defence_r4_free`: nuclear aiming from up to 48 cells without walking to the target, two grenade launchers, persistent marks); earlier `defence_r3`, `defence_next`, `defence`, `standard`; experiment: a pre-ordered garrison (bought with the campaign remainder), virus (garrison weapons work only inside the base circle), two missiles, victory = 20 game minutes AND all marked hatcheries, waves go on after the timer | 2 Ghosts with a free permanent cloak |
| *Evacuation* (THanson01) | revision 4 (`sniper_next_r4`, free test `sniper_next_free_r4`; the rifle shot no longer walks the Ghost to a far click); earlier revision 3 (`sniper_next_r3`, `sniper_next_free_r3`: extra SCVs in the order, containers without a limit, new rifle shot, shared ground salvo, sequential intro); sniper cover (experiment, `sniper`), prepared detonations (`sniper_next`; revision 2 `sniper_next_r2`: turret kits instead of ready turrets, campaign order, campaign result; test `sniper_next_free_r2`): manual convoy command, fuel containers | 1 Ghost (`sniper`), 2 Ghosts (the others) |
| *Outbreak* (THanson02) | free test (experiment, `epidemic_free`): hellion fuel and the abandoned gas truck, day-shielded structures, one night transport, containers and turret kits; the original story, day / night and victory kept | 2 Ghosts |
| older prototype configurations (TRaynor02 `prototype`, TTychus01) | squad of Nova + two Ghosts + two Medics with a free permanent cloak and an army damage bonus (x2 / x3) | Nova, 2 Ghosts, 2 Medics |

Original scenario, waves and victory stay as Blizzard made them **except where a mission variant says otherwise** (TRaynor03 changes the victory condition and adds waves after the timer; TRaynor02 adds a defeat;
the experimental prices, limits, multipliers and waves of the newer variants are the developer's numbers, not approved by the Owner). The 20-minute timer of TRaynor03 is the constant of the original map: other values are not supported by the current implementation yet.
A general time-pressure design (`MissionPressure`) exists only as a design in ROADMAP.md / docs; nothing of it is implemented. Nothing here is a confirmed full playthrough: see the open items in
[docs/MISSION_ROADMAP.md](docs/MISSION_ROADMAP.md). Status and history: [ROADMAP.md](ROADMAP.md).

## How it works

Maps are never shipped. `tools/build.py` reads **your own** copy of the original map, injects the
Ghost Ops code into its `MapScript.galaxy` (one block plus one hook call) and writes a modified
copy. Everything else in the map is kept byte for byte, and `verify` proves it.

```
core/        mission independent Galaxy code (squad, protection)
adapters/    one folder per mission (traynor01, traynor02, traynor03, thanson01, thanson02, ttychus01): anchors + mission specific Galaxy
config/      one configuration per mission (schema_version 4, as `validate_config` in tools/build.py demands), turned into Galaxy constants at build time
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

### Liberation Day (TRaynor01) variants

Double click **`GhostOps_Launcher.pyw`** (project root, no console window): the graphical launcher (CustomTkinter, Russian).
Pick a mission on the left, a difficulty card below the mission card (*Подробнее* shows exact numbers), press *Начать миссию*:
the map is built, verified, installed and started through the same code as the CLI (stages *Проверка окружения -> Подготовка
карты -> Проверка -> Установка -> Запуск*, no fake percentage). It remembers the last mission and profile (first start:
Liberation Day, Лёгкий), refuses a second start while one is running, and never closes a running StarCraft II (it tells you
to close it yourself). Settings (game folder, diagnostic log) are behind *Настройки*. Settings file:
`%APPDATA%\GhostOps\launcher_settings.json`; log: `%APPDATA%\GhostOps\launcher.log`; both are separate from the game configs.
First start installs CustomTkinter 5.2.2 into `tmp\thirdparty\ctk` (`requirements-gui.txt`; Pillow and tkinter come with
Python 3.12). Fallbacks stay: **`GhostOps_TRaynor01.cmd`** (console menu: *Лёгкий*, *Сложный*, *Экстремальный · эксперимент*,
*Отмена*) and the command line:

```
python tools\build.py launch --mission traynor01 --preset easy     # also the default without --preset
python tools\build.py launch --mission traynor01 --preset hard
python tools\build.py launch --mission traynor01 --preset extreme
python tools\build.py launch --mission traynor01 --preset hard --print-only   # only print the SC2 command
python tools\build.py build|verify|install|uninstall --mission traynor01 --preset easy|hard|extreme
```

Profiles live in `config/traynor01.json`: the common settings plus `presets.easy` / `presets.hard` / `presets.extreme` with small
`overrides`; `default_preset` is `easy`. An unknown profile name is an error, never a silent fallback. Each profile has
its own files (`dist/GhostOps_TRaynor01_<profile>.SC2Map`, `Maps/GhostOps/...`) and manifests, so building or installing
one never overwrites the other. `launch` refuses to run while StarCraft II is already open (it never closes your game),
and always makes sure the installed file is the fresh build of the chosen profile. The profile applies to the mission you
start now, not to an existing save. Enemy difficulty is Blizzard Hard in both; a short message at the start names the
variant. If a map ever opens to an empty black screen, read `Documents\StarCraft II\GameLogs\<time> ScriptError.txt`.
`--diag` adds the detailed catalog read-out (energy, costs, cast time, cooldown) to the start message.

| Setting | Лёгкий (easy) | Сложный (hard) | Экстремальный · эксперимент (extreme) |
|---|---|---|---|
| **Squad** | 2 Ghosts, no Medic | same | **1 Ghost**, no Medic |
| **Ghost HP** | 100/100 (game default) | same | **45/45** (only our Ghost) |
| Raynor01 / own Marines | 45/45 HP / 1/1 HP | same | same |
| Ghost energy | 100/100, +20/s outside cloak | same | same |
| Cloak | free to start, net -10/s | same | same |
| Snipe | 10 energy, 45 damage (ignores armour), 0.3 s cast, range 10 | same | **cost 0** (works at zero energy), otherwise the same |
| **Snipe cooldown** | **none** | **5 game seconds, per Ghost** | **8 game seconds** (was 10; 2026-10-21, unconfirmed) |
| EMP / nuclear strike | removed | same | same |
| Status | Owner considers it playable | Owner: "сложно, но проходимо" (balance judgement) | experimental; the last balance change, still needs an in-game confirmation |

Balance tuning of the first mission is finished on this set (easy / hard / extreme as above); the last change (extreme: one Ghost,
45/45, Snipe cooldown 8 s and cost 0 since the seventh task, was 10 s) is not yet confirmed in the game. A status panel (energy bar, state, remaining cloak time) is shown in the missions 1-2. The new maps are `GhostOps_TRaynor01_r2_<profile>` (see below).

Known limits of the launcher: it only lists missions this project can really start (*Вне закона* has one profile, *Тактический*;
*Smash and Grab* is a prototype with its single existing way of starting, no invented profiles); the mission picture is the map's own minimap
from `tmp\source` or a generated placeholder; Windows scaling is handled by CustomTkinter (checked at 200% plus an extra 1.5x);
at the minimum window size the right pane scrolls instead of clipping.

**Wounded squad scene (all three profiles).** Right after Raynor's standard first line (hook in `gt_OpeningLineQ_Func`, once: `go_sceneDone`), queued behind the standard talks:
Raynor «Войска готовы к бою?» -> 0.5 s (real) -> Marine «Высылайте подмогу!» (portrait Marine1) -> 0.5 s -> another Marine «Доктора! Доктора!» (Marine2); the directive
text «Отряд пострадал при высадке. Морпехи тяжело ранены.» appears with the second line. Config key `scene` (durations 3.0 / 3.5 / 3.0 real seconds, texts, clip ids),
clips in `assets/audio/traynor01/`. It does not repeat when the reinforcements arrive or after a load; balance, squad and profiles are untouched.

### Evacuation (THanson01): sniper cover (experiment, added 2026-10-20)

Launch: the GUI (mission *Эвакуация*, profile *Снайперское прикрытие*) or

```
python tools\build.py launch --mission thanson01 --preset sniper          # build, verify, install, start (Hard)
python tools\build.py launch --mission thanson01 --preset sniper --print-only
```

Map: `<SC2>\Maps\GhostOps\GhostOps_THanson01_sniper.SC2Map`. Idea: a finite squad, no development, convoys leave **on the player's command**, one Ghost covers
them with single Snipe shots. Everything of the original (story, terrain, route, scenes, voice, waves, nydus, drop pods, colonist logic, allied escort and its refill, late
Mutalisk raids, victory 50 colonists, defeat at 20 dead colonists on Hard) is kept; the code is `core/GhostOpsHanson.galaxy` + `adapters/thanson01/` + `config/thanson01.json`.

| item | what it does / where to change it |
|---|---|
| **Ghost** | exactly one ordinary male Ghost, created once at the start of the playable part (`gt_IntroSequence_Func` is the only way in, so a skipped intro gives the same result; `GhostOps_ClaimStart`) beside the starting squad at `hanson.ghost_spawn` [110, 49]; life 45/45 (`ghost_tuning.ghost_life`), permanent cloak without energy use (`operatives.ghost_permanent_cloak` = Blizzard's Crius Suit upgrade, `ghost_start_cloaked`, activation cost 0, drain 0), rifle kept (no hold fire), EMP and nuke removed. Snipe (`ghost_tuning.snipe`): cost 0, cast 0.3 s, cooldown 1.0 s, damage 1000 (the stock `SnipeDamage` effect, armor ignored), range stock 10; `exclude_friendly: true` turns the target filter into "biological, visible; not own / ally / neutral / structure / destructible ..." (stock Snipe could hit own and allied units). Never refilled; no separate defeat for its death |
| **Development lock** | `hanson.lock_development`: `TechTreeUnitAllow` / `TechTreeUpgradeAllow` = false for everything the player's own unit types can produce (read from the game: `TechTreeUnitProducesUnit/Upgrade`, scanned every second, so SCV builds, Command Center, Barracks, add-ons, research, mercenaries are covered) plus a fixed list of base types (`GhostOps_Hanson_LockFixed`). Existing structures stay, SCVs keep moving / mining / repairing. Colonists, allied escort and its refill, script-created enemies and the evacuation ships are script-created and not affected |
| **Convoy command** | button (screen dialog, top left under the objectives): *Конвой: сбор колонистов* (disabled) -> *ОТПРАВИТЬ КОНВОЙ* (enabled, ping + message) -> *Конвой в пути* (disabled). The original starts a trip in `gt_ConvoySpawned_Func`; the hook in front of its first action (`GhostOps_Hanson_Hold`) ends the function while the command is missing and remembers the trigger; the click (`GhostOps_Hanson_OnClick`: state 2 -> 3 first, then `TriggerExecute` of the remembered trigger) runs the original function from its beginning exactly once. No waiting thread (a load cannot cut it), no Stop orders. The colonists' gathering (`gt_Gathercolonistspriortoevacuation_Func`, hook `GhostOps_Hanson_Preparing`) is kept; the button is ready when the original says the convoy is ready. The dialog is created again after a load (`TriggerAddEventLoadGameDone`) |
| **Turrets** | `hanson.turrets.list` (x, y, role base / houses / air), owner 4 (the settlement's player, so defeat rules are untouched); stock Missile Turret, repaired by SCVs (autocast), no new ones can be built. 15 turrets: base 8, houses 4, air approaches 3, all inside the settlement (the far north belongs to the Zerg: turrets there were killed by the map's Zerglings). The engine moves a turret to the nearest valid place, so the config holds the places the engine really gave |
| **Raids** | the original late raids are kept (`gt_DoomsdayZergAttackWaves`: after the 6th trip on Hard, 8, then 12 + 2 Overseers, then 16 + 2 Overseers Mutalisks, driven by `gt_DoomsdayZergAI`) |
| **Dev preset** | `sniper_dev` (hidden): `hanson.debug_log` writes `Documents\StarCraft II\Banks\GhostOpsDevHanson.SC2Bank`, `hanson.autotest.mode` runs a scripted check (1 Snipe, 2 lock / repair / refill, 3 command log, 4 command + automatic clicks, 5 raids on the turrets, 6 pathing map, 7 placement probe) |

### The Outlaws (TRaynor02): tactical variant (experiment)

Double click `GhostOps_Launcher.pyw`, pick *Вне закона* (one card: *Тактический*, badge *Эксперимент*), or
`python tools\build.py launch --mission traynor02 --preset tactical`. The previous prototype (Nova, two Ghosts, two Medics, army bonus)
is still there: `--preset prototype` (hidden in the GUI). Everything else of the mission is the original: map, story, Blizzard Hard
enemies, victory (all Dominion units with PreventDefeat dead) and the final scene.

| What | Rule |
|---|---|
| **Garrison** (the 6 Marines that stand at the start base when the mission starts, fixed by unit) | normal life and armor; damage x20 (catalog behavior `GhostOpsGarrisonDamage`, added once; measured 119 per hit on armor 1 = 6 x 20 - 1); the weapon exists only inside the defence zone (`UnitWeaponRemove/Add`, checked 4 times a second): outside it is removed, back inside it returns once; life is never healed by crossing the border; border marked by a ring of 36 small "+" text tags |
| **Defence zone** | circle around the original start base, centre (86.0; 31.0), radius 16.0 (`tactical.garrison.zone`): covers the command center, barracks, depot, the academy and all six Marines, does not reach the road of the advance (rebel base, Dominion base); not tied to any building |
| **Trained Marines** (any Marine that is neither garrison nor rescued) | life 1/1 (set when the unit is created, healing cannot raise it) and **no weapon at all** (`UnitWeaponRemove`, when the unit is created): no automatic fire, no attack order, no attack-move (measured: 0 hits against a static Barracks while a plain Marine made 20 hits of 5.0). The earlier x0.1 factor is gone. The garrison factor is a catalog `DamageDealtFraction`, which is **additive**: the build writes factor - 1 (19), measured 119 per hit on armor 1 = 6 x 20 - 1 |
| **Rescued rebels** (hook right after the original change of owner in `gt_RebelsCompleteQ`) | untouched: normal Marines and Medics, keep their wounds, act on the whole map |
| **Ghosts** | exactly two, **delivered by a transport** (see the story scene below): *Наводчик* (Spotter) and *Оперативник* (Operative), 45/45 life, no replacement (training and a second academy are banned, a foreign Ghost is removed); energy 100/100, +20/s outside cloak, free cloak start, net -10/s under cloak; Snipe 10 energy, 45 damage ignoring armor, 0.3 s cast, range 10, cooldown 7 game seconds per Ghost; EMP removed; names are text tags above the units |
| **Ghost Academy** | created near the base (98.5; 28.5), visible and vulnerable, no hidden invulnerable building and no extra defeat condition; its research and hero/spectre arming abilities are removed; the single Nuke is armed for free (1 s) at the start |
| **Nuclear strike** | one missile; only the Spotter may use it (`UnitAbilityEnable(Operative, TacNukeStrike, false)` + an order guard); states: ready -> aiming (12 game seconds, the Ghost cannot move: stock `Uninterruptible`) -> **irreversible launch** (start of the effect `GhostOpsNukeFlight`, the Spotter is free at once: `FinishTime` 0) -> 6 game seconds of flight -> blast. Damage, radii (4/6/8) and falloff of the blast are the **installed game's own** (300, +200 on structures); friendly fire stays |
| **Cancel** | the stock chain spends the missile on a cancel (measured: `Nuke` 1 -> 0, stage 5 of the ability); the module arms the same single missile again for free (1 s) and the strike is ready again; the launch counter is the flight effect, never the click, so there is never a second launch |
| **Save / load** (real game save through the game menu, measured) | before aiming and in flight both restore: two Ghosts and their roles, one missile (none after the launch), the Operative still cannot use the strike, the zone and the Marine groups work, the ring and the names are drawn again; after the load the Spotter's death before the launch gives the defeat, in flight it does not and the blast still happens; no new missile |
| **Defeat** | Spotter dies before the irreversible launch: message + end of the mission (`libCamp_gf_EndCampaignMission`, same call as the original defeat); after the launch his death (also from his own blast) is no defeat, the missile still lands; Operative's death alone ends nothing; original defeat (no PreventDefeat unit left) unchanged; every check is switched off when the original victory / defeat sequence starts |
| **Enemy production** | the original's, untouched: the strike kills troops, the pause is used for the rebels' assault; surviving production works by the original rules (waves, AI rebuilding, scripted squads, victory). Our earlier "stop after the production is destroyed" logic was removed |

**Story scene** (the original intro and talk stay; everything below is portrait transmissions with a short voice clip each, no camera move, no cinematic mode,
the player keeps control; delays are in `tactical.story` in mission (game) seconds, message durations in real seconds):

| when | what |
|---|---|
| mission start | the Ghost Academy, the garrison and the zone are ready; there are no Ghosts yet (so the Spotter's death cannot end the mission before the delivery) |
| 15 s after the start, and after the original talk has left the dialogue queue (`TriggerQueueEnter`) | Adjutant portrait, title «Тревога!», text about the infected base computers (14 s on screen); tip «Вирус на базе» is added to the tips |
| 15 s (`tactical.story.second_delay`, mission seconds) after the end of that whole transmission (portrait, text, sound) | Swann portrait, «Я решил, что помощь тебе не помешает.» (6 s); when this message really starts (it waits in the dialogue queue behind any original talk) a `SpecialOpsDropship` (the map's own drop ship, not selectable / targetable / using supply) is created at the reinforcement point with the two Ghosts inside (`UnitCargoCreate`), flies to a free drop point of the start base (the first of the map's own points 32 / 688 / 1025 / 1105 / 1112 / 1110 without a structure of the player within 3) and unloads (`SpecOpsDropshipTransport`); the landing is pinged on the minimap |
| when the cargo is empty | once (not per unit) the Ghost portrait says «Призрак явился.»; text about the special unit and the single missile (directive area), a secondary task «Спецотряд и ядерный удар» (the details and the rules), tips for Ghosts / strike / rebels; the roles' names appear above the Ghosts |
| after that | the transport flies to the edge of the map (region 31) and is removed there (never while it still carries somebody) |

**Voice** (2026-10-20): three short clips of the voice lab (`assets/audio/traynor02/`, sources and hashes in `assets/audio/SOURCES.md`): Adjutant «Тревога.»,
Swann «Я решил, что помощь тебе не помешает.», one ordinary Ghost line «Призрак явился.». The build imports them (config `audio.clips`: id + file; the WAV is
copied to `Assets\Sounds\GhostOps\` in the map archive, a `CSound` of category *Dialogue* is added to the map's `SoundData.xml`, manifest key `audio`, `verify`
checks the hash); the scene plays them with `SoundLink("<id>", 0)`. A clip is replaced by changing the file / the `source` of its entry, nothing else. The details stay
in the text: the lines are also shown by the script in the subtitle message area (a transmission with a sound link shows its own subtitle only when the player's
subtitle option is on, the Owner's is off). The ASR texts of the clips were not checked by a human. The scene stage is a global saved with the game; a loaded
game goes on from the same stage, never shows a finished message again and never creates a second transport or a second pair; the Ghost line has its own once-flag.

Test launches of the game by the tools (not the Owner's launch) follow the rules in `CLAUDE.md`: second monitor, 1024x768 window, no sound,
own PID only.

**Seventh task (2026-10-21, experimental numbers, NOT Owner-approved; the Owner checks the balance):** new maps `GhostOps_TRaynor02_r2_tactical.SC2Map` (and
`GhostOps_TRaynor01_r2_{easy,hard,extreme}`): the old-named maps stay untouched for started playthroughs. Changes: Snipe cost 0 and cooldown 5 s (old 7 s) for both
Ghosts; nuke aim range 24 (old 12), and while the strike is really being aimed (effect `NukePersistent`, not the walk to the point) the cloak drain is paused (buff
`GhostOpsAimHold`; detectors still see him); the Operative's *Бронебойная граната* (2 charges, 500 damage in radius 2.0, range 9, prep 0.8 s, no energy; only enemy
ground vehicles and structures, one hit destroys the intact entrance bunker); once-only rebel-rescue scene (clip + two explanations, minimap pings, Barracks lift-off
re-allowed); Raynor clip after the Adjutant alarm; the Ghost landing line about the two charges; larger explanation text; status panel; portraits move their mouth during
clips and explanations (silent lip-sync drivers, see `docs/MISSION_ROADMAP.md`, seventh task). Technical checks of 2026-10-21 (panel layout, portrait mouth recordings, nuke aim geometry at the entrance bunker, grenade results; in-flight save NOT run because the game's save was locked) are in `docs/MISSION_ROADMAP.md`.


### The Outlaws, version 2 (TRaynor02 `tactical_next`, 2026-10-22, experimental numbers, NOT Owner-approved)

Separate map `GhostOps_TRaynor02_r2_tactical_next.SC2Map`, launcher card *Вне закона, версия 2* (`python toolsuild.py launch --mission traynor02 --preset tactical_next`); the Owner's `tactical` map is not touched. Armor-piercing strike: 2 charges (counter on the squad panel), area circle under the cursor, key G, radius 3 / damage 500; nuclear strike: aiming range 48 (was 24) and a mission-only damage profile 600 + 900 vs structures, radii 4 / 7 / 10 (the stock 300 + 200 left a Command Center at 1000 of 1500); "Повстанец" labels over the rescued fighters; new victory: all enemy barracks, factories, command centers and starports (also lifted off) are destroyed. Measured values and open checks: `docs/MISSION_ROADMAP.md` section 6.1, architecture: `docs/ARCHITECTURE.md`.


### Evacuation, prepared detonations (THanson01 `sniper_next`, 2026-10-22, experimental numbers, NOT Owner-approved)

Separate map `GhostOps_THanson01_sniper_next.SC2Map`, launcher card *Подготовленные подрывы* (`python toolsuild.py launch --mission thanson01 --preset sniper_next`); the earlier `sniper` map and its saves are untouched. Two Ghosts (45 life, permanent cloak), Snipe 250 / 2 s; the Firebats place fuel containers next to themselves (key C, 25 gas, shared stock 12) that explode from the first hit of any fighter (200 damage within 3 to ground enemies, air is not hit, own side takes 25 % on hard); a convoy leaves only on your command and costs 100 gas; the gas comes from one Refinery (put SCVs on gas yourself after the base is handed over). Verified values and open checks: `docs/MISSION_ROADMAP.md` 8.1; the replicas: `docs/handoff/thanson01.sniper_next.lines.seed.json`.

### The first three missions and the campaign link (2026-10-20, experiment)

Plan and statuses: [docs/MISSION_ROADMAP.md](docs/MISSION_ROADMAP.md); economy and save rules (the one contract): [docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md](docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md).

| mission | how to start | what it is |
|---|---|---|
| *Liberation Day* (TRaynor01) | launcher card, profiles easy / hard / extreme | unchanged balance; the wounded-squad scene now ends with Raynor's closing words (portrait + text) |
| *The Outlaws* (TRaynor02) | launcher card *Тактический*; or the campaign window | the accepted tactical variant; Raynor explains that resources are kept for the next operations (text only); the victory writes a **result proposal** (remainder, report) |
| *Zero Hour* (TRaynor03) | launcher card *Час икс* (standalone test, recommended order, no campaign) or the campaign window | pre-ordered garrison, two Ghosts with a free permanent cloak (energy regenerates under the cloak, Snipe still costs 10), two missiles, victory = 20 game minutes AND every marked hatchery destroyed; short original lines of Raynor, Matt and the marines before the explanatory texts (voice mode, see "Voice") |

**Campaign window** (launcher button *Кампания: Вне закона → Час икс*): the stock of the campaign, step 1 *Вне закона* (no purchases; start / continue a saved attempt / free restart / refuse), the
map's result shown as a proposal with the report (start, mined, found, derived net of spending, passed remainder) that you confirm ONCE, step 2 *Час икс*: the order form (marines, bunkers,
turrets, SCVs: prices, limits, total, shortage; the cost of the chosen order is charged once, no credit and no hidden surcharge) and *Оплатить и начать*. State file:
`%APPDATA%\GhostOps\campaign.json` (one atomic write for the stock change and the accepted mark). Each operation gets its own map file
`Maps\GhostOps\GhostOps_<Mission>_<profile>__<operation>.SC2Map` that later builds never overwrite.

**Saves.** Save and load freely with the game's own menu (F10): a load returns exactly the saved state (verified in the installed game, RESEARCH.md "CE-0"), costs nothing and the losses of the
cancelled future are not kept. Closing the game does not abandon the attempt: save, close, start the same operation with *Продолжить сохранение* (the map starts, you load your save inside the game).
A full restart (*Перезапустить*) is free and gives the original paid order again. Loading from the SC2 *main menu* was not tried (it needs your login). Do not delete the map file of an
operation you still want to continue: a save names the map by its path.

**Prices and limits of TRaynor03 are experimental numbers** in `config/traynor03.json` (`zerohour.prices`, `limits`, `recommended`), not approved by the Owner: marine 40, bunker 75, turret 75, SCV 50
minerals; recommended order 16 / 4 / 4 / 8 = 1640 minerals (it was 8 / 4 / 4 / 4 = 1120 until 2026-10-21; that kit did not hold the base for 20 minutes in the scripted-player defence test, details in docs/MISSION_ROADMAP.md) (the base price of a marine 50, bunker and turret 100 scaled by a factor; see the report in docs/MISSION_ROADMAP.md). A standalone test of the map
never writes into the campaign.

**TRaynor03 balance fixed until the Owner's review (2026-10-21):** 16 marines / 4 bunkers / 4 turrets / 8 repair SCVs = 1640 minerals, garrison damage x8; no further automatic tuning of the kit or the multiplier is planned.
Full playability of TRaynor03 is NOT confirmed: loading from the main menu, a full playthrough by a human and the balance of the order are for the Owner to judge. The voice of Raynor in TRaynor02 and the explanatory texts have no clips (portrait + text only).

**TRaynor03 *Оборона и диверсии* (preset `defence`, implemented 2026-10-21 as an EXPERIMENT):** a separate profile next to the previous *Zero Hour* (`standard`, unchanged, its map and operations are not touched). Player-built paid bunkers / turrets (kits from the order), a six-marine pod landing then the rest of the order, a manual ground salvo of the turrets (enabled by Swann), waves weakened by the share of living marked incubators of each base group, Matt's message and a short target reveal, victory = timer AND all marked incubators. All numbers are developer experiments in the `defence` section of `config/traynor03.json`; what was really checked and what is not: `docs/MISSION_ROADMAP.md` 7.8. Full playability and balance are for the Owner to judge.

**TRaynor03 «Оборона и диверсии», версия 2 (`defence_next`, 2026-10-22):** отдельная карточка запускателя и карта `GhostOps_TRaynor03_defence_next.SC2Map`; версия 1 (`defence`) не меняется. Вступление Рейнора после запуска оригинальных таймеров, залп по области с указателем и клавишей A (перезарядка 8 с, экспериментально), пассивная способность призраков «Анализ детекторов» (круги обнаружения видимых вражеских детекторов при выделенном призраке), сцена Свонна про сканеры. Что проверено и что нет: `docs/MISSION_ROADMAP.md` 7.10.

## Developer notes: the Owner's versions and in-game tests

- **Owner version vs development.** Installed maps the Owner plays (`python tools/isolation.py status`) are protected: `build.py`, the launcher and the campaign window never rebuild, replace, uninstall or rename them (a protected map is started as it is). A new version is built under its own hidden preset (for the TRaynor03 defence variant: `defence_next`, probe builds `defence_next_dev` / `defence_next_slow_dev`) and gets its own map file. `python tools/isolation.py protect-all` registers the installed maps once.
- **In-game tests wait for a free game.** `python tools/test_queue.py enqueue --label L --mission traynor03 --preset defence_next_dev -- python tools/ce0_steps.py tests/scenarios/salvo_area.json` puts a prepared scenario into a queue served by a detached runner: while ANY StarCraft II process exists it only waits (checks every 5 s), after the game closed it waits 10 s, checks again and launches the test through the test-launch guard (windowed 1024x768, second monitor if present, only the test process muted). `status`, `cancel [JOB|--all]` (a running test is stopped and only its own game is closed), `stop` / `go`, `resume JOB`. The launcher shows a compact queue line with cancel / resume / log. Results and logs: `tmp/testqueue/jobs/<id>/`.

## What this repository does NOT contain (and how to restore it locally)

Published: Galaxy sources, build tools, launcher, configs, tests, docs and the audio **manifest** `assets/audio/SOURCES.md`. NOT published (git-ignored, never committed): the game, CASC data,
Blizzard maps, saves, Banks, models, voice lab and the extracted voice WAVs (`assets/audio/**/*.wav`, Blizzard voice lines).

To use it after a clone you need your own StarCraft II client 3.1.4 (the tools read the original campaign maps from it; set the game folder in the launcher or `--game-dir`) and Python 3.
The build does not download or recreate anything: it patches the maps of YOUR installation.

### Voice (clips are prepared locally; a build without added voice exists)

A clone has **no sound clips**: they are Blizzard voice lines and are never committed (`assets/audio/**/*.wav` is git-ignored). What is published is the recipe list `assets/audio/clips.json`
(whole original ruRU line, its path in the game's storage, the interval, the ASR text, the hash of the file the author used) and the manifest `assets/audio/SOURCES.md`.

Two ways to build, both explicit:

1. **With the voice (normal mode).** Prepare the clips from YOUR installed game (needs the same CascLib DLL as the map extraction, docs/EXTRACT_MAP.md, and `pip install -r requirements-audio.txt --target tmp\thirdparty\audio`):
   `python tools/prepare_audio.py` (`--check` only reports which files are missing; `--game-dir` / `--casc` choose the game folder and the DLL). It cuts the listed interval, applies a 3 ms fade-in and a 15 ms fade-out, keeps the original level and writes 16-bit WAV files.
   Five of the six older clips come out byte-identical to the author's files; one may differ in a few bits (reported as "hash differs", not an error). Nothing of the author's private voice lab is needed.
2. **Without added voice.** `python tools/build.py build|install|launch --mission M --preset P --no-voice` (launcher: Settings, "Без добавленной озвучки"). No clip is imported or played; portraits (with their talking animation),
   subtitles, explanatory texts, the order of the scenes and the mechanics stay unchanged. The map file gets the suffix `_novoice` (it never overwrites the voiced map).

In the normal mode a missing clip is **never skipped silently**: the build stops with "audio clip ...: file not found" and a message that names both ways. The remaining manual step: the clip texts are Whisper ASR
(not human-checked) and nobody has listened to the clips yet; the in-game sound of the new TRaynor03 lines was not heard by the author (the process was muted in tests).

## Licence

Code, tools and docs: [MIT](LICENSE). Blizzard data and maps are not part of this repository.


### Outbreak (THanson02): free test (experiment, added 2026-10-24, numbers NOT Owner-approved)

Map `<SC2>\Maps\GhostOps\GhostOps_THanson02_epidemic_free.SC2Map`, launcher card *Эпидемия — Тест: бесплатный отряд* (`python tools/build.py launch --mission thanson02 --preset epidemic_free`). The original mission with a finite squad: 2 Ghosts (45 life, free Snipe, day cloak free / night cloak drains energy), the stock infantry, 2 extra Hellions, 8 turret kits, 10 containers (key C). Hellions run on fuel (the local gas is poor): they stop far from the base, Swann and Tychus point to an abandoned gas truck that infantry must capture and bring to the stalled Hellions (automatic refuelling in a radius, the fuel leaves the truck). By day a few big infested buildings are protected, at night they are vulnerable and one transport can carry troops (it leaves at dawn). Victory is the stock one. Nothing is charged or credited. Details and checks: `docs/MISSION_ROADMAP.md` (last section).


Revision 2 (`epidemic_free_r2`, card "Эпидемия — Тест: бесплатный отряд (ревизия 2)", the recommended one) adds the manual **ground salvo** of the turrets the player builds from the kits: select a turret, press **A**, point at the area (the circle shows the whole area), click; Esc or the right button cancel without a shot or cooldown; 5 missiles of 30 damage, range 11, cooldown 8 s per turret (experimental numbers, taken from `defence_next`). The turrets fire at air by themselves. The squad: 2 Ghosts, 14 Marines (6 stock + 8 added), 2 added Hellions, 8 turret kits. Revision 1 (`epidemic_free`) is kept as it was.

## Prepared builds and the Mission Workshop (2026-10-27)

- `python tools/prebuild.py [--status-only]` builds, checks and installs the CURRENT maps of the three playable missions in advance and prints the time of every stage; a map that is up to date is skipped. The launcher shows "Готова к запуску" / "Нужна сборка" on the mission card.
- "Мастерская миссий" (button in the launcher): variants of Hour X, Evacuation and Epidemic with a full snapshot of the settings; free tests only, the real campaign is never touched. Checks: `python tools/workshop_window_check.py OUTDIR` (real window), `python tools/workshop_run_check.py MISSION` (real build and start; run it through `tools/test_queue.py` like every game start).
- Revisions: Hour X `defence_r5`, Evacuation `sniper_next_r5`, Epidemic `epidemic_free_r4` (free tests `*_free*`); all numbers are experimental, see `docs/MISSION_ROADMAP.md`.
