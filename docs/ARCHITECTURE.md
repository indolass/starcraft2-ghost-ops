# Architecture (F0)

Four components, deliberately small.

1. **Core** (`core/GhostOpsCore.galaxy`) - mission independent.
   - *SquadManager*: `go_operatives` is the registry of operatives (`GhostOps_RegisterOperative`,
     `GhostOps_IsOperative`); nothing in Core compares unit type names.
   - *Squad*: `GhostOps_SpawnOperatives` creates the configured squad (`go_cfgSquadType[]`), grants the
     Blizzard cloak upgrades for Ghosts and registers every unit in the SquadManager before the first
     scan; 0.5 s later a one-shot trigger issues `GhostHoldFire` to all and `GhostCloak` to Ghosts.
   - *BaseSupport*: once per game second `GhostOps_ScanAll` looks at the units of covered players
     and gives each regular, non-structure, non-operative unit Blizzard's hidden behavior
     `DamageDealtDouble` (x2) or `DamageDealtMega` (x3) exactly once (`go_supported` group), so
     units that appear later (rescued, trained, reinforcements) are covered. Structures are not
     buffed automatically (bunkers would double the bonus together with their marines).
     `GhostOps_SetDamageMultiplier(1..3)` removes and re-applies the buff (menu entry point).
   - *Experimental*: the old invulnerable-allies model (`go_cfgInvulnerableAllies`) is kept but off;
     it skips units the mission made invulnerable itself and never combines with a multiplier.
2. **Adapter** (`adapters/<mission>/`) - `adapter.json` names the source map, the hook anchor and
   markers the map must contain; `adapter.galaxy` defines `GhostOps_OnMissionStart()` (covered
   players, spawn point). For `traynor02` the hook is placed after
   `TriggerExecute(gt_StartGame, true, false);` in `gt_IntroSequence_Func`, i.e. after the intro.
3. **Configuration** (`config/<mission>.json`, `schema_version` 4 in the validator (earlier text said 3): `operatives.squad` + `start_hold_fire` + `ghost_permanent_cloak` + `ghost_start_cloaked`, `base_support.damage_multiplier` 1/2/3, `experimental.invulnerable_allies`) - validated by the build and emitted
   as `GhostOps_ApplyConfig()`. Galaxy cannot read files at runtime, so a future menu will call the
   Core setters instead.
4. **Build and validation** (`tools/`) - read the source map (MPQ), generate the block, patch with
   exact anchors (refuses ambiguous or already patched scripts), structural lint, write the map,
   `verify` (only `MapScript.galaxy` and, when the squad has Nova, the map's `UnitData.xml` differ;
   removing our additions restores both originals exactly), reversible install into `Maps/GhostOps`.
   One adapter + one config per mission; Core and build are shared.

## Mission variants (TRaynor01, 2026-10-19)

The adapter and config format cover per-mission squads and a few optional generic rules, all validated
by the build and off unless configured:
- `adapter.json` may list several `start_hooks` (a mission can reach its start through different
  scenario branches; `GhostOps_ClaimStart()` in Core makes the squad appear once) and an `init_hook`
  inserted *before* a named statement (used to record `PlayerDifficulty(1)` before the mission's own
  difficulty triggers run; the value is printed in the first minute together with the current one).
- `operatives.disabled_abilities` (`Snipe`, `EMP`, `TacNukeStrike`): `TechTreeAbilityAllow(player, ability, false)`
  for the player, the campaign's own restriction call; the abilities are not merely hidden.
- `army.fragile_unit` (type + max life): every 0.2 s the maximum life and current life of that unit
  type for *covered players only* is lowered; nothing is killed or removed, no periodic healing is
  undone (the maximum stays at the configured value so Medics cannot raise it).
- `ghost_tuning` (config, optional, TRaynor01 only): the standard Ghost's energy and Snipe numbers written as
  map-local catalog overrides (`UnitData` energy start/max/regen, `GhostCloak` behavior drain, `GhostCloak` ability
  activation cost, `Snipe` cost and cast time, `SnipeDamage` amount). Net energy under cloak = unit regen + cloak
  modification, so the cloak modification is generated as (net - regen); regen +20 and net -10 give -30. The build
  creates `AbilData`/`BehaviorData`/`EffectData` in the map when it has none, refuses entries the map already
  defines, and `verify` proves every patched/created file restores to the original. The first 60 s of the mission
  print the values the game really uses (`CatalogFieldValueGet`), see `GhostOps_TuningText`.
- Liberation Day uses: squad Ghost, Ghost, Medic (no Nova data patch), normal cloak (no Crius Suit),
  fragile Marines (1 HP), `damage_multiplier` 1, Hard expected. Raynor, scenario triggers and enemies are
  untouched; only three hook calls and the Ghost Ops block are inserted into `MapScript.galaxy`.

## Profiles (TRaynor01)

A mission config may hold `presets` (name -> label, start message, small `overrides` that are deep-merged onto the common
settings) and `default_preset`. `tools/build.py` resolves the profile once per command (`resolve_config`): unknown names raise
`ConfigError`, missions without presets reject `--preset`. File names, manifests and install records are keyed by
mission + profile, so profiles never overwrite each other; missions without presets keep their old names. `launch` for a
mission with presets prepares (build, install the fresh file, refuse while SC2 runs, remove an old unnamed install) and starts SC2
detached; `--print-only` only prints. Menu: `tools/ghostops_menu.py` (console, no GUI framework), started by `GhostOps_TRaynor01.cmd`.
Graphical launcher: `GhostOps_Launcher.pyw` -> `tools/gui_launcher.py` (CustomTkinter view) -> `tools/launcher_core.py` (settings, profile
list from the config, one-run-at-a-time controller, stage callbacks) -> `build.prepare(args, progress)` + `build.start_detached` - the same
functions the CLI uses; there is no second builder. The backend is injectable, so tests use a fake. The worker thread talks to the UI
through a queue (no Tk calls off the main thread). Settings live in `%APPDATA%\GhostOps`, never in game configs. The `extreme` profile is
only `presets.extreme.overrides` (`operatives.squad` = one Ghost - lists are replaced, not merged; `ghost_tuning.ghost_life` 45, `snipe.cooldown` 10); `ghost_life` also adds the Ghost to the fragile-unit scan.
The Snipe cooldown is the game's own per-ability cost element (`Cost[0].Cooldown TimeUse`, default link = the ability itself, default
location = the casting unit), no script timer; the easy profile writes no cooldown element at all.

## MissionPressure (design, only the format exists; nothing is implemented)

Goal: separate combat difficulty (Hard, untouched) from forced hurry. Planned per-mission setting
`mission_pressure`: `original` (default), `relaxed`, `no_rush`. Each adapter lists the explicitly
verified Galaxy statements for each mode; the build injects them at the same hook site that calls
`GhostOps_OnMissionStart()` (mission globals are in scope there, Core code is not). No global AI
stop, no game-speed change, no blanket timer edits. Classes of scripted time limits and what is
allowed per class:
1. *Race against an enemy army* (TTychus01): restart or pause the one gating timer; never remove the defeat trigger.
2. *Countdown to defeat*: lengthen the timer only; the defeat condition and its sequence stay.
3. *Defend until the timer ends = victory*: the timer is the objective; keep it (removing it breaks victory).
4. *Periodic hazards* (lava, day/night): part of the level; keep.
5. *Escort / moving story objects*: tied to waypoints, not to a clock; keep.
6. *No real time pressure*: nothing to do.

## Decisions

- Code is injected **inline** into `MapScript.galaxy` instead of using `include`, to avoid
  depending on how the engine resolves includes inside a map archive.
- BaseSupport uses a polling scan, not unit-creation events, because only natives already used by
  Blizzard's own map scripts are relied upon.
- Invulnerability was dropped as the default: invulnerable units are not attacked by the enemy AI
  and cannot pick up resource containers (observed in the first playtest).
- The Nova is the Liberty campaign unit `Nova` (hero Ghost with Snipe, Domination, permanent
  cloak and the Heroic nuclear strike). Her standard abilities are left unchanged in the PoC.

- Nova fire control: `core/data/NovaFireControl.xml` is inserted into the map's own
  `Base.SC2Data/GameData/UnitData.xml` (a catalog override, not a runtime API). `AbilArray` and
  `LayoutButtons` additions carry explicit indices (next free slot of the 3.1.4 Liberty campaign
  `Nova` unit: abilities 0-6, buttons 0-11), because index-less appends are silently dropped.
  The build refuses a map that already overrides `Nova`.
- Ghost cloak: `GhostCloak` is gated by the requirement `UsePersonalCloaking` (upgrade
  `PersonalCloaking`), so Core grants it with `TechTreeUpgradeAddLevel`; the Crius Suit upgrade
  `PermanentCloakGhost` (campaign data) then sets the cloak cost to 0 and uses `PersonalCloakingFree`.

## Known limits (PoC)

- Galaxy is compiled by the game; the build can only lint structure. A script error is visible
  as an error when the map loads (the Editor's test run shows the message).
- The buff multiplies damage dealt; the observed in-game multiplier has not been measured yet.


## TRaynor02 tactical variant (module `core/GhostOpsTactical.galaxy`)

Built only into maps whose `adapter.json` lists `modules` (TRaynor02); inert when the config has no `tactical` section
(`go_tacEnabled = false`, so the `prototype` preset behaves as before). The adapter calls `GhostOps_Tac_Start(spotter, operative)` after
`GhostOps_SpawnOperatives` (the Core keeps `go_squadUnit[]`, `GhostOps_SquadUnit(i)`). Hooks of `adapters/traynor02/adapter.json`
(all inside original trigger functions, tagged `// GHOSTOPS HOOK`, removed again by `verify`): start (`gt_IntroSequence_Func`), the rescue
(`gt_RebelsCompleteQ_Func`, per unit), the original victory (`gt_VictoryDominionOutpostCompleted_Func`, `gt_VictorySetup_Func`) and defeat
(`gt_DefeatBaseDead_Func`) which only switch the module off.

Nuclear strike chain (measured in the installed game 3.1.4, not guessed; `tactical_dev` + bank log `GhostOpsDevTac.SC2Bank`):
- Campaign data of this mission hides the arming (`TrainNuke` shows only if Ghosts are allowed and needs a Factory): the build overrides
  `TrainNuke` (Use and Show -> "no nuke queued"), the Nuke unit costs 0, `ArmSiloWithNuke` Ammo1 takes 1 s; the module lifts the campaign tech
  restrictions of the chain and arms the missile by order.
- **Disabling `ArmSiloWithNuke` on the academy (UnitAbilityEnable) blocks the strike itself**; the player-level `TechTreeAbilityAllow(arm, false)`
  does not. So a second arming is stopped on the player level, per unit access to the strike by `UnitAbilityEnable(unit, "TacNukeStrike", false)`.
- Ability stages: -3 order accepted, 0..4 start of the cast, 5 = cancel, 6 = cancel recovery (2.5 s), -6 end of the recovery, -4 end of a normal channel
  (it comes just after the launch effect, so it is not used). Effect events (`TriggerAddEventPlayerEffectUsed`) work: `NukePersistent` (aiming
  begins), `GhostOpsNukeFlight` (**irreversible launch**), `NukeDetonate` / `NukeDamage` (blast).
- Data: `NukePersistent` InitialDelay 0 and PeriodCount 60 (x0.2 = 12.0 s measured), ExpireEffect -> new `GhostOpsNukeFlight` (ExpireDelay 6 ->
  `NukeDetonate`, InitialDelay 0; blast measured 6.0 s after the launch), `FinishTime` 0 (the Spotter walks at once: 2.0 per game second measured).
  `NukeDamage` is not overridden. Final effect `NukeSuicide` is kept (spends the missile at the normal end and on a cancel).
- The Ghost's own `AbilArray` indices 5 (TacNukeStrike) and 7 (EMP) are as in the base data; the Ghost Academy indices 3..6 (research, merc
  compound, hero and spectre nukes added by the campaign data) are removed.

Marines: garrison / trained / rescued are disjoint groups (`go_tacGarrison`, `go_tacTrained`, `go_tacRescued`); trained status is applied by the
unit-created event (measured: for a real barracks Marine at the moment of creation) with a 0.2 s scan as safety net; the global fragile-unit and
BaseSupport mechanisms are not used by this variant.


Final stage (2026-10-19): the module no longer touches the enemy production in any way (the earlier watcher that stopped the scripted spawners
and banned rebuilding after the production was destroyed is removed: `GhostOps_Tac_RegisterSources`, `GhostOps_Tac_StopSources`,
`GhostOps_Tac_ProductionCount`, `GhostOps_Tac_AfterBlastTick`, the three trigger variables, the `gt_StartAI_Func` hook and the text
`ProductionDestroyed`). A `LoadGameDone` trigger redraws the text tags (ring and names) after a loaded game. Catalog damage behaviors are written as
factor - 1 (additive `DamageDealtFraction`).


Story scene (2026-10-19): `adapters/traynor02/adapter.galaxy` holds a small stage machine (`go_tacScStage`, `go_tacScT` live in the module so that they are saved
and visible to the test module): a periodic trigger `GhostOps_Scene_Tick` (0.5 s) drives it; messages are separate helper triggers that
wait in the dialogue queue (`TriggerQueueEnter`/`Exit`) and send text-only transmissions (`TransmissionSend` with portrait models `AdjutantPortrait` and
`SwannPortrait`, no sound link). The squad is created by `GhostOps_SpawnOperativesInCargo` (Core) inside the transport and handed to the module with
`GhostOps_Tac_OnGhostsDelivered` (roles, personal access, info text, death rule). A watchdog covers a message thread lost in a load. Delays come from
`tactical.story`; the dev preset shortens them.


Audio import and scenes (2026-10-20): config key `audio.clips` [{id, source}] is turned by `tools/build.py` into WAV members `Assets\Sounds\GhostOps\<name>.wav`
of the map archive plus `CSound` entries (parent `SM_Old` = category Dialogue, 2D) in `Base.SC2Data\GameData\SoundData.xml` (patched when the map has one, created
otherwise); the manifest lists them (`audio`), `verify` checks the hashes and that only the expected files were added. The clip files and where they came from:
`assets/audio/` + `SOURCES.md`. Extra hooks: adapter key `extra_hooks` (same form as `start_hooks`). TRaynor01 scene: config key `scene` -> generated
`GhostOps_ApplySceneConfig()` + globals (`gen_scene`), texts `Param/Value/GhostOpsScene_*`, code in `adapters/traynor01/adapter.galaxy`
(`GhostOps_T1_OnOpeningLine` -> trigger `GhostOps_T1_SceneMsg`); hidden preset `easy_dev` writes `Banks\GhostOpsDevScene.SC2Bank`. TRaynor02: the scene stage machine got stage 8
(Swann queued: the transport is created when the Swann message really starts), `GhostOps_Scene_GhostMsg` plays the single Ghost line.


THanson01 (2026-10-20): `adapters/thanson01/` + `core/GhostOpsHanson.galaxy` (+ `core/GhostOpsHansonTest.galaxy` only for `hanson.autotest`). The adapter key
`generators: ["hanson"]` makes `build_block` emit `GhostOps_ApplyHansonConfig()` (turrets, button, flags) instead of the TRaynor02 generators; `modules` lists the Galaxy file.
Hook kinds: `start_hooks` / `init_hook` as before, `extra_hooks` (`after` or `before` an anchor) for the module's entry points: `gt_Gathercolonistspriortoevacuation_Func`
(preparing), `gt_ConvoySpawned_Func` (the hold gate, a hook line may be an `if (...) { return true; }`), `gt_DoomsdayZergAI_Func` (a once-a-second probe that hands the
mission's counters to the module). `verify` strips every line ending with the hook tag, so the "original restored exactly" proof covers any hook shape.
Other mission-wide pieces are reused: `ghost_tuning` (new opt-in `snipe.exclude_friendly`; `cloak_net_per_second` may be 0), the core squad and cover code, the launcher
(MISSIONS entry, `hanson_lines`). Where to change what: Ghost = `config/thanson01.json` `operatives` / `ghost_tuning`; turrets = `hanson.turrets.list`; convoy command =
`core/GhostOpsHanson.galaxy` (`GhostOps_Hanson_Hold`, `OnClick`, `UpdateUI`, state 0..3) and the hook in `adapters/thanson01/adapter.json`; button size / place = `hanson.button`;
texts = `hanson.texts`. Original parts touched: only the five hook lines in `MapScript.galaxy` (initialisation, intro sequence end, gathering start, convoy start, raid AI tick)
and the catalog / string-table entries of the Ghost.


## Configurable missions and campaign economy (design, 2026-10-20; nothing of it is implemented)

Full contract (the one contract; this section is only a summary): [MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md](MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md). Every statement there is labelled
IMPL / AGREED / AGREED-V1 / REQUIREMENT / DESIGN / OPEN (Owner decision or technical check). Summary of what is fixed:
- Seven parts: catalog, campaign rules, mission settings (today's `config/<mission>.json` is their seed), profiles (today's `presets`), operation plan,
  campaign save, mission adapter. Our profile names (Лёгкий, ...) are never the native SC2 difficulty (Hard).
- Order of layers: catalog -> campaign rules -> mission settings -> profile parent (`extends`) -> profile overrides. The plan is validated against the
  result and is never a layer. An ordinary list is replaced **whole** (current `deep_merge`); changing or removing one entity by `id` is a separate, explicitly
  marked operation whose syntax is only a draft - the current `deep_merge` does not support it and there is no automatic gluing of lists (contract 6.2).
- Ownership: the **launcher side owns the campaign state**; the map executes the current attempt of the current operation only. Plan reaches the map by build-time embedding
  (existing mechanism); the result returns as a **proposal** that the launcher accepts once, in one consistent operation (stock change and "accepted" mark together).
  The carrier (a Bank file) is unverified and marked as needing a technical check; a Bank file on disk is not proof that it is the result to accept.
- **Right to make a mistake (Owner, agreed):** free manual save and load inside a mission, loading is never punished (no money, no campaign losses, no smaller
  reward, no extra equipment), losses of a cancelled future are not kept, no mandatory ironman, no limit on attempts. Save, load, full restart of the same paid operation
  and a new operation are four different actions; `operation_id` (one paid order), `attempt_id` (one run) and `result_id` (one proposal) have separate duties
  (contract 7.1, 7.5, 7.6). A Galaxy flag is part of a save and does not survive a full restart. Not built; save methods other than the game-menu save are unverified.
- A started operation keeps an **immutable operation set** (built map, settings snapshot, order, dependency versions, ids and checksums) so that its saves can be
  continued; "map under the shared name mission + profile, snapshot in the manifest" was judged insufficient. A hash alone does not promise SC2Save
  compatibility (contract 7.8). Loading an old mission after its result was accepted has an **open** policy (7.3) that does not block ordinary saves and loads.
- Units, roles, source and story identity are four separate properties; roles are assigned by the mission adapter (today only the TRaynor02 module does; TRaynor01
  has no `garrison` role). Protected scenario objects (heroes included) are never matched or replaced by a mass rule and keep their references, but a modder may still set a hero's
  life, weapons and abilities explicitly; a hero gets no extra survivability automatically. Some replacements need a mission handler and the validator refuses them without one.
  Unsupported keys are errors.
- The «Вне закона» (TRaynor02) design keeps its agreed minimal scope; a complete ban on training new soldiers was discussed and is **not** approved.
- Note: the config format is `schema_version` 4 (`validate_config`); the "Configuration" item of the first section and the README now say 4 as well (corrected 2026-10-20, documentation only).


## Campaign, operation sets and TRaynor03 (2026-10-20, implemented; contract: MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md sections 7 and 14)
Components (all new files are small and sit next to the existing ones):
- `core/GhostOpsCampaign.galaxy` (config key `campaign`, adapter keys `campaign_hooks`): the map-side journal. At a fresh start it makes the attempt id (a saved global), writes
  `START` / `LOADED` / `DEFEAT` rows and one `RESULT` row (a PROPOSAL: resources read before the standard victory sequence, start stock, mined = native collected counter, found = pallets of the
  original) into the Bank `GhostOpsCampaign`. The Bank is only written, never read back; a load restores it with the save (measured, RESEARCH.md "CE-0").
- `tools/campaign.py`: the launcher-side state file `%APPDATA%\GhostOps\campaign.json` (env `GHOSTOPS_CAMPAIGN_FILE` for tests): stock, ledger, operations (`paid` -> `started` ->
  `accepted` / `abandoned`), attempts, accepted results. ONE atomic write changes the stock and marks a result accepted (temp file + `os.replace`). Rules: one charge per operation, a result
  is accepted once, an abandoned attempt's result is never accepted automatically, a Bank file older than the launch is stale, the active attempt is the one of the last journal rows.
- `tools/campaign_flow.py` (logic) and `tools/gui_campaign.py` (window "Кампания" of the launcher): order -> quote (limits / prices of the resolved config, a shortage is shown, no credit) ->
  pay once -> `build.py --plan` builds the UNIQUE map file `GhostOps_<Mission>_<profile>__<operation>.SC2Map` (never overwritten; `prepare_existing` keeps an installed set as it is) ->
  start -> after the game exits the fresh journal is read and the proposal is shown for confirmation.
- `build.py`: `apply_ce0` assembles optional modules from the RESOLVED config (`ce0` dev probe, `campaign`); `--plan` merges an operation plan (`operation_id`, `order`) into the config; the manifest
  carries `operation_id` and `data_hash` (hash of the settings snapshot, baked into the map and returned in the proposal).
- `core/GhostOpsZeroHour.galaxy` (config key `zerohour`, adapter `adapters/traynor03/`): the order (marines / bunkers / turrets removed beyond the order, extra SCVs created), the targets, the victory
  gate in front of the original timer victory, the post-timer waves, the scenes. The tactical module (`core/GhostOpsTactical.galaxy`) is shared with TRaynor02 and generalised by config:
  `tactical.nuke.count` (missiles = successful launches), `tactical.nuke.both_may_aim`, `tactical.spotter_defeat` (defaults keep TRaynor02 as it was).
- The CE-0 probe (`core/GhostOpsCe0.galaxy`, `adapters/*/ce0_extra.galaxy`, `tools/ce0_session.py`, `tools/ce0_ui.py`) stays dev-only; no playable profile contains it (`tests/test_ce0_build.py`).

## TRaynor03 redesign (agreed 2026-10-21; implemented as the experimental preset `defence`, see below)

The implemented TRaynor03 (section above: `core/GhostOpsZeroHour.galaxy`, `adapters/traynor03/`, `config/traynor03.json`) is the previous build and stays as it is. The agreed new design (mission text: `docs/MISSION_ROADMAP.md` 7.7; paid kit: `docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md` 9.3) adds, as separate responsibilities and not as a second contract:
- **Landing and kit accounting** (player-built bunkers / turrets, kit counters as saved globals): mission module + adapter; the economy rules stay in the contract (7, 9.3); construction events are a technical check.
- **Manual ground salvo of the turrets**: a catalog ability on the turret plus a small mission-side unlock scene; the stock air fire is not touched; simultaneous firing is a prototype check. No resource cost.
- **Wave weakening by incubator groups**: a mission-side layer over the ORIGINAL wave sources (no AI rewrite); the table "incubator group -> wave handler" must be derived from the original script first (before and after the timer, regrowth of targets). Formula undefined.
- **Story lines** use the existing line table mechanism (`tactical.lines`, `GhostOps_Line`), so a later voice recording is a config change.
- **Saves:** every new state above is a saved global; a load must not repeat a landing or grant a kit (contract 7.5-7.8). The new version is a separate build with a new map file name.
Boundary: the tactical module stays shared with TRaynor02 and is generalised by config only; the grenade of TRaynor02 is not part of TRaynor03.

## TRaynor03 «Оборона и диверсии» (preset `defence`, implemented 2026-10-21)

Module `core/GhostOpsDefence.galaxy` (kit accounting, landings, scenes, wave weakening, target reveal) + the `defence` key of `config/traynor03.json` + generated catalog data (`defence_fragments` in `tools/build.py`: free Bunker / Missile Turret, the turret ability, pointer actors). The overlay is added by `apply_ce0` only when the resolved config has `defence`; the old `standard` build only gets stubs. The wave weakening is a generated TAIL block of the script (`GhostOps_DEF_<source>` copies of the original attack functions, hooked `before "// Actions"`; verify strips head, hooks and tail and compares with the original). Facts that shaped it: the original starts the AI in the intro before the mission-start hooks (the mode flag is set by a hook before `TriggerExecute(gt_StartAI`); `AIAttackWaveSend(..., wait=true)` blocks its thread, so the shared wave buffer is emptied before the send. Status and what was verified: `docs/MISSION_ROADMAP.md` 7.8 / 7.9.

### Aimed ground salvo (2026-10-21)
Built the way the Odin's Barrage is built in the Liberty campaign data (3.1.4; `campaigns\liberty.sc2campaign\...bildata.xml` `OdinBarrage`): `CAbilEffectTarget` with `CursorEffect`; actors `*CursorSplat` (parent `TerranCursorSplat`), `*CursorModel` (parent `TerranCursorModel`), `*Range` (parent `RangeAbil`) bound with `abil=`; one persistent effect with periodic missile launches; the stock explosion model `BarrageModel` (Thor missile impact) on every impact. Own parts: the damage radius of ONE missile (`salvo.radius`), the circle of impact points (`salvo.spread`: fixed sunflower points through `PeriodicOffsetArray`, no random numbers, nothing to repeat after a load) and the pointer radius = radius + spread (effect `GhostOpsSalvoAim`, read only by `CursorEffect`, never executed), so the pointer shows the real total area. Not taken from the Odin: energy, stun, damage 125, `RevealRadius` / `Unfog` (the pointer must not reveal anything), the channel animation.

## Isolation of the Owner's versions and the queue of in-game tests (2026-10-21)

- **Owner version vs development.** `tools/isolation.py` keeps `build/owner_maps.json` (git-ignored): every map of `Maps\GhostOps` that the Owner plays or may load saves of (registered by `protect-all` and by the Owner's normal launch, `build.start_detached(owner=True)`), with a frozen copy in `build/owner_maps/`. `build.py` refuses to install over, uninstall or replace a protected map, and `prepare()` (used by the CLI, the launcher and the campaign window) starts a protected map as it is instead of rebuilding it; the map of a running game is protected while it runs. Development uses its own hidden presets (`defence_next`, `defence_next_dev`, `defence_next_slow_dev`; `extends` resolves through a chain) and therefore its own map files. Maps of started operations stay immutable (unique name per operation). No separate worktree: the Owner plays an installed `.SC2Map`, source edits cannot reach it.
- **Test data.** A job of the queue has its own directory (`tmp/testqueue/jobs/<id>/`: campaign file, bank directory, session state, log, result) and the environment variables `GHOSTOPS_CAMPAIGN_FILE`, `GHOSTOPS_BANK_DIR`, `GHOSTOPS_SESSION_STATE`; probes write only the dev Banks (`GhostOpsDev*`), saves are named `CE0_*` and deleted afterwards.
- **Queue** (`tools/test_queue.py`, `tools/ce0_steps.py`, scenarios in `tests/scenarios/`): one detached runner (OS file lock, dies with its process); waits while any SC2 process exists (checks every 5 s, touches nothing), 10 s settle, re-check right before the launch; a job = one hidden preset build + one bounded command; states waiting / preparing / running / done / cancelled / error / interrupted (never auto-resumed); cancel stops only the job's own test script and closes only a game whose pid AND creation time were recorded by the test-launch guard (`isolation.record_owned`); an appearing foreign game (guard exit 9) sends the job back to waiting (bounded). The launcher shows a compact status line with cancel / resume / log.

## Shared lines table (text bridge with Voice Studio, 2026-10-21)

One source of the TEXT of the replicas: the shared lines tables of the voice lab (`games/starcraft2-ghost-ops-voice-lab/shared_lines/<mission>[.<profile>].lines.json`, contract `docs/SHARED_LINES.md` and `docs/MESSAGE_FOR_MAIN_DEVELOPER_SHARED_LINES.md` of the lab). Connected exactly as the lab's handoff prescribes: `tools/lines_table.py` is an unchanged copy of the lab module, `tools/build.py` got the lab's patch (`shared_lines_dir()`, `apply_shared_lines()`; one changed line in `resolve_config`). The folder is chosen by `GHOSTOPS_LINES_DIR` or the one line of `build/shared_lines_dir.txt` (outside git; here it points at the lab folder); without a folder or without a table of the mission nothing changes and the config text stays the source. The texts of the table are put into the RAW config before the presets are merged (config files are never written), so an edit made in the studio reaches the NEXT build of any profile; installed / protected maps and started operations are not rebuilt (`defence` of the Owner keeps its text). Bindings: TRaynor02 `tactical.lines[id=X].text` (kept), TRaynor03 `presets.defence.overrides.defence.texts.*` and `zerohour.texts.*`, TRaynor01 `scene.texts.*`. A line without a binding (new recording not yet connected) or of mode `game_native` is skipped and never blocks a text scene; a binding that points nowhere is a build error. Events, timings, conditions and balance stay in this project; the table holds only words. The build marks the table as read (`consumers.game`, the studio shows "game connected"). Tests never read the lab folder (they set `GHOSTOPS_LINES_DIR` to a missing folder; `tests/test_shared_lines.py` uses temporary tables). `python tools/lines_table.py check <tables folder> <project folder>` reports table <-> config drift (read only; 0 now).

## TRaynor03 version 2 (`defence_next`, 2026-10-22): intro, detector analysis, trace profile

- **Start order.** The original creates its first objective and starts ALL its timers (first special wave 70 s, evacuation, warnings) inside one trigger-queue entry (`gt_ObjectiveHoldOutCreateQ` -> `gt_StartTimers`). A scene of ours that takes the shared queue before that delays every timer (measured: +24 s for a 20 s intro). The intro therefore waits for a hook at the end of `gt_StartTimers` (`GhostOps_DEF_OnTimersStarted`, config `defence.scenes.raynor_wait_timers`) and then takes the queue: timers 7.9 s, first special wave 77.9 s, marine transmission 89.9 s - the same as the original. Our scenes use `TriggerQueueEnter/Exit` like the original transmissions, so they never overlap them. The original has NO spoken intro in the map: the briefing (`gt_BriefingQ` / `BriefingScene01-03`) is registered as campaign footage and is only played from the campaign lobby; `gt_IntroSequence` is a camera swoosh that starts the AI and `gt_StartGame`. `gt_BriefingQ` is never called by us (it sets cinematic / gameOver, pauses units and the AI).
- **Detector analysis** (`detector_analysis`, `core/GhostOpsDetector.galaxy`). Mechanic reused from the Liberty campaign data: the "Hero Detector Radar" of Nova / Tosh / Zeratul (behavior `HeroDetectorRadar` -> periodic `CEffectEnumArea` radius 25, filter `Visible,Detector`, enemies only -> buff `HeroDetectorRadarDetected` 0.5 s). Only that part is taken (no Nova ability set, no new dependency). The stock range actors did not draw on this map, so own `CActorRange` actors `GhostOpsDetRange10/11/12` (behavior `Detector1x` = the real detection radius, validators `HasDetector1x`, dense icons) react to the stock buff. A 0.25 s trigger gives a Ghost the behavior only while it is selected (`UnitIsSelected`): other selections hide the circles, a mixed selection keeps them. The state lives in behaviors and actors of the engine: no saved globals. A unit in the fog is not `Visible`: no buff, no circle. The passive icon (`Type="Passive"`, slot row 1 column 4) does not touch cloak / Snipe / nuke.
- **Development trace** (`ce0.trace`, profile `orig_trace_dev` = the original mission without any Ghost Ops module, `null` in `overrides` removes a module of the base config): a `TRACE` journal line at the start of every original scene / transmission / wave function (`build.trace_hooks`), `arr` (per Zerg player: alive, near the base, first arrival, deaths near the base) and `uid` probes. `tests/test_wave_copies.py` proves that the generated wave copies of the defence variant equal the original text except the wrapped calls.

## TRaynor02 version 2 (`tactical_next`, 2026-10-22): options of the tactical module

The Owner played `tactical` (map `GhostOps_TRaynor02_r2_tactical.SC2Map`, protected, not rebuilt). Version 2 is the separate preset `tactical_next` (visible card "Вне закона, версия 2", map `GhostOps_TRaynor02_r2_tactical_next.SC2Map`) plus the hidden `tactical_next_dev` (CE-0 probe, journal) and `tactical_next_slow_dev` (slow projectile so that a game can be saved while it flies). Every new behaviour is an OPTIONAL config key, so the old profile builds exactly as before (a test compares the fragments):

- `tactical.nuke.range` (1..100) and optional `tactical.nuke.damage` {`amount`, `structure_bonus`, `areas` = three [radius, fraction] pairs}. The damage profile is a map-local override of the stock `CEffectDamage NukeDamage` (the other missions and the stock campaign data are not touched). **Experimental numbers**, chosen from the measurements in the roadmap (section 6.1), not Owner-approved.
- `tactical.grenade`: `flight_speed` (own `CMoverMissile`, cells per second), `hotkey` (one capital letter, shown on the button and in the tooltip), `pointer` (cursor splat = the area of the `CursorEffect` search effect, i.e. the real damage radius, plus the range indicator `GhostOpsAPRange`), `effects` (impact flash and explosion sound as actors that react to `Effect.GhostOpsAPSearch.Impact`; they draw only, the damage stays the one `CEffectEnumArea` search effect, so there is no double damage). The stock models / sounds of the campaign data are used (`BarrageModel`, `Terran_ExplosionLarge`); no audio is extracted or published.
- Charge counter: the module's own counter `go_tacGrenadeAmmo` is changed ONLY by the launch effect `GhostOpsAPLaunch` (a cancelled order never reaches it) and it also switches the ability off at 0; the panel (core) shows `Name - Бронебойные заряды: N/M` in the footer line for any selection, and "dead" when the Operative is dead. There is no separate UI counter: the panel reads the same variable the ability gate uses, which a loaded game restores.
- `tactical.rebel_labels`: a text tag per rescued unit (`TextTagAttachToUnit`, not shown in the fog), `UnitSetInfoText` for the selected unit; tags are destroyed by the load, so the 1 s tick destroys the tags of dead units and labels every rescued unit that has no tag (an array of unit/tag pairs prevents duplicates).
- `tactical.victory` {`enabled`, `types`}: `adapters/traynor02/adapter.galaxy` counts the living structures of player 2 of the listed types every second (flying variants are listed explicitly) and, when the count has been above 0 once and falls to 0, calls `GhostOps_Tac_VictoryFire()`. That function lives in the TAIL (`adapters/traynor02/tail.galaxy`, adapter key `tail_source`, appended after the original script so it can see `gv_gameOver` and `gt_VictoryDominionOutpostCompleted_Func`): it runs the ORIGINAL victory trigger with the conditions skipped, i.e. the same objective, hooks (campaign result, CE-0) and victory sequence, once (`gv_gameOver` guards a second call). Allied buildings are another player and are not counted; bunkers, depots and units are not in the list.
- Optional texts have defaults in `build.TAC_DEFAULT_TEXTS`, so the module text references exist in every profile.
- Tail and `verify`: the generic strip of `TAIL_BEGIN..TAIL_END` already restores the original script; `build.patch_script` concatenates the defence tail and the `tail_source` file.
- Galaxy trap found here: the CE-0 file lives in the module block BEFORE the original script; it cannot name `gv_*` globals (compile error "syntax error" without a useful line), and a statement with about 25 string operands also fails: split the journal lines.

## THanson01 "prepared detonations" (preset `sniper_next`, 2026-10-22): design, implementation state in the last paragraph

Agreed mechanic and experimental numbers: `docs/MISSION_ROADMAP.md` 8.1, economy contract 9.2.1. Technical plan (all optional config keys of `hanson`, the old `sniper` profile builds as before):
- **Container** = a catalog unit `GhostOpsFuelContainer` (parent: the campaign data's `ExplodingBarrelLarge`, which brings the barrel model and death explosion visuals), owned by the neutral player 0, Biological, not Destructible, no pathing footprint (cannot block a road). Neutral ownership is what keeps it out of every enemy / own targeting and away from automatic fire; the Ghost's Snipe filter of this profile drops "Neutral" from the excluded classes (`ghost_tuning.snipe.container_target`), own units stay excluded.
- **Detonation** is the death of a container whose damage source is a Ghost (script `UnitDied` event, not a proximity or timer rule): the module creates a damage area at its position: enemies (ground, no air, no neutral so no chain) take `containers.damage`; a second search effect hits own / allied ground units and own structures for `damage * friendly multiplier` (multiplier per difficulty, 0 = none). The explosion model / sound are actors on the effect (draw only).
- **Placement** is an ability on the Firebat (map-local `AbilArray` + card button, hotkey from the config) with a cursor splat of the real radius; the unit is created by the ability's effect and the MODULE validates it (gas, shared limit, passable ground, no structure): invalid = the unit is removed and nothing is charged; valid = 25 gas and one limit slot are taken once. The ability is switched off while gas or the limit is short (the HUD line says why). A selected container shows its radius (range actor).
- **Convoy fuel** reuses the existing hold gate (`GhostOps_Hanson_Hold` / button); the click checks the gas, takes it once, sets the paid flag and releases the original trip once. State, paid flag, gas, container list and counters are plain saved globals and units: a load restores them.
- **Lines**: `hanson.lines` (stable ids, speaker, seconds) + the text bridge of the voice lab (`build/shared_lines_dir.txt`); portrait + text through the campaign transmission call, scenes queued behind the original talk.

**THanson01 `sniper_next` lines (handoff, 2026-10-22).** The replicas of the variant are `hanson.lines` of the preset (11 lines, stable ids, ru / en text; the first nine are the Owner's wording split into short replicas, `RAYNOR_FUEL` and `HARD_WARNING` are additions, flagged here for the Owner's approval). The game reads their text from the string table `Param/Value/GhostOpsH_L_<id>`. To connect the text bridge the lab needs a table `thanson01.sniper_next.lines.json` in its `shared_lines` folder: a ready seed in the lab's schema, with the exact bindings (`presets.sniper_next.overrides.hanson.lines[id=<ID>].text`), is `docs/handoff/thanson01.sniper_next.lines.seed.json` (copy it unchanged into the lab folder; this project does NOT write into the lab). Until then the config texts are the source; no clip exists (portrait + subtitle + the silent talk drivers). Already recorded / approved replicas of other missions are untouched.

**THanson01 `sniper_next`: implementation as built (2026-10-22, replaces the plan above where they differ).** The container unit is `GhostOpsFuelContainer` (parent `ExplodingBarrelLarge`, model and actor of the stock `GasCanister`; the barrel has no model path of its own and showed as a grey dome), owner 0 (neutral), Biological, life 1 (any first hit kills), the stock barrel footprint. The Firebats' ability `GhostOpsPlaceContainer` is a `CAbilEffectTarget` whose executed effect is only the harmless search `GhostOpsContainerArea` (a `CEffectCreateUnit` inside the ability made every order invalid; found by splitting the effect from the ability): `PlaceUnit` / `Placeholder` give the cursor model and the footprint colours, the module's trigger on the cast (`c_unitAbilStageExecute`) validates (gas, shared limit, passable, no structure), charges once and creates the unit; a trigger on `c_unitAbilStageQueue` cancels an order further than `containers.place_range`. The explosion is the module's reaction to the container's death by any unit of player 1 or 4 (`EventUnitDamageSourceUnit`): two search effects at the place (enemy ground: damage; own side: damage x the difficulty multiplier; neither hits neutral units, so no chain). The development lock derives "everything a unit can produce" and would forbid the container and the Refinery: `TechTreeUnitAllow` after the lock loop. Traps found: a unit created by the ability's own effect makes the order invalid; `UnitCreate` at the map edge moves the unit to the nearest valid place; the CE-0 file cannot name original globals; the constant is `c_playerPropOperSetTo`.


**THanson02 "Epidemic" (2026-10-24).** `adapters/thanson02/` (adapter.json: modules Hanson + Epidemic, generators `hanson` + `epidemic`, start hook after `TriggerExecute(gt_StartGame...)`, hooks on the original day / night counters `gv_night` / `gv_day`, the intro hellion drop and `Init06Difficulties`) + `core/GhostOpsEpidemic.galaxy` (fuel as unit energy, behaviours `GhostOpsNoFuel` / `GhostOpsTruckShow` / `GhostOpsDayShield`, the neutral gas truck, the night transport, scenes through `GhostOps_Talk`, saved state `go_e*`). Config `config/thanson02.json`; `tools/build.py` has `validate_epidemic`, `gen_epidemic`, `epidemic_fragments`; containers got `structure_bonus` (effect `GhostOpsCBlastStr`); hotkeys are written to `GameHotkeys.txt`. Hidden dev presets `epidemic_free_ce0_dev` / `epidemic_free_cycle_dev` carry the CE-0 probe (`adapters/thanson02/ce0_extra.galaxy`) and an optional `dev_cycle` (short day / night, dev only).


**Shared turret salvo (2026-10-24).** `tools/build.py` `salvo_fragments(sv, with_cost)` holds the catalog data of the manual ground salvo (`GhostOpsTurretSalvo`: ability with a cooldown per unit, aiming effect, Odin-style cursor actors, missile effects); `defence_fragments` (TRaynor03) and `epidemic_fragments` (THanson02, key `epidemic.salvo`, validated by `validate_salvo`) both use it, and the two Missile Turret blocks are merged per id. The tooltip numbers come from the settings (`salvo_text`). The ability needs no script: it is present for every turret that the player builds.


**Общие способности и явные отличия миссий (требование Owner, 2026-10-25; реализация не начата).** Способность, перешедшая из одной миссии в другую (наземный залп турелей, метки повстанцев, бронебойный гранатомёт, анализ детекторов, взрывные контейнеры), должна иметь одну реализацию и одинаковое управление; миссии различаются настройками (наличие, урон, дальность, боезапас, перезарядка, сюжетное открытие), а не копиями кода. Нового универсального движка способностей не проектируется: используются существующие модули. Фактическое состояние (что есть и в какой миссии), расхождения и критерии проверки: `docs/MISSION_ROADMAP.md`, последний раздел (таблица применимости).


## Mission Workshop and prepared builds (agreed concept 2026-10-26; NOT implemented)

Source and status labels: `docs/MISSION_ROADMAP.md`, section "Итоги прохождения Owner 2026-10-26 и концепция «Мастерской миссий»". Documents only; no code was changed.

- **Place.** A built-in mode of the existing launcher (`tools/gui_launcher.py` + `tools/launcher_core.py`), not a separate program and not part of the Hyperion menu (moving the menu there is out of the first stage). Path: pick a mission, create a variant from an existing version, change parameters, build and run a free test, save the variant.
- **Single source of numbers.** The summary panel, price, recommendation, tooltips, card text and the build all read the RESOLVED mission config (`build.resolve_config`); the Workshop only writes a variant config (a preset that `extends` its base, as `*_r3`/`*_r4` do today). A field is shown only if the change reaches the build and works (no fake toggles); dependent fields follow the chosen mode.
- **Storage and version safety.** Variants live inside their mission's card; every setting set is its own build with its own map file name (the existing rule: a played or paid map is never overwritten, a save keeps its map, the operation plan pins its profile and settings); the link build ↔ settings is kept (manifest). A successful build or scenario check does not mean confirmed playability. Free tests never touch the real campaign.
- **Validation.** Technically impossible values are blocked (existing `validate_*` functions are the base), unusual balance is a warning, strong experimental variants are allowed when the engine and the mechanic support them.
- **Prepared builds.** Recommended variants and free tests are built and installed in advance; a normal start of an up-to-date map does not rebuild; a change of sources, used resources, settings or order marks the build stale; a paid operation is built once and reused by continue / restart; statuses "ready" / "needs build" / "building". Measure build, install and game start separately before optimising. Today: `prepare` already reports "already installed and identical"; the statuses are not shown in the launcher.
- **Shared abilities.** The shared modules (ground salvo, detector analysis, grenade, containers, rifle shot, rebel labels) stay single implementations switched per mission by config (applicability table in the roadmap). Pending design item: early warning of the detector circle (before detection), see roadmap section B; the cause of the late circle is NOT established (hypothesis: ordinary visibility of the detector and the 0.25 s period of `HeroDetectorRadar`).
- **Future, separate mechanics (not part of the first Workshop stage):** folding and redeploying fortifications; the "ultra-realism" mode with a finite supply of people.
- **Order of later work (a plan, not a permission):** (1) mission fixes from the playthrough reviews, (2) prepared builds and a clear start, (3) the first Workshop, (4) folding fortifications and ultra-realism.

## Revisions r5 / r5 / r4, early detector warning, kit labels, prepared builds and the Mission Workshop (2026-10-27, implemented; numbers experimental)

- **Early detector warning** (`core/GhostOpsDetectorEarly.galaxy`, config `detector_analysis.early_warning`, used together with the permanent radar of `GhostOpsDetector.galaxy`): the stock Hero Detector Radar marks only VISIBLE detectors, so a detector in the fog never gets its circle and the circle of a visible one appears at the edge of the detection. Every 0.2 s the module reveals a 2-cell patch (0.5 s) around each enemy detector (behaviors Detector10/11/12) within radius + margin of any living Ghost; the stock radar then draws the real-radius circle on the now visible detector and it follows a moving one. Cost (measured in the game): `VisRevealArea` reveals a patch of radius 2 around the detector, not the detector alone: points up to 1.5 cells from it are visible, from 2 cells not; an ordinary enemy 1.5 cells from the detector is seen, at 4 cells not. The rest of the map and army is not revealed. Margin limit 13 (the radar searches 25 cells). A group loop inside a group loop of one function ends the outer loop after its first unit (the second Ghost was skipped): one scan function with ONE loop per Ghost.
- **Auto-fire switch** (`ghost_tuning.fire_control`): the stock Hold Fire / Weapons Free pair (`GhostHoldFire`, `GhostWeaponsFree`) put on the card of a Ghost that lacks them in the campaign map; one of the two buttons is available at a time (the state), hotkeys F / G.
- **Kit counters on build buttons** (`GhostOps_KitLabel` in `core/GhostOpsCore.galaxy`, called from the kit ticks of the defence and Hanson modules): the NAME of the stock buttons `Bunker` / `MissileTurret` is set with `CatalogFieldValueSet` to a prepared text "Bunker, kits: N" (texts 0..30 generated by `text_entries`). The number is in the name (tooltip, aim panel); there is NO digit over the icon (not implemented).
- **Container approach and refusals** (`GhostOps_Hanson_ContSpotTick`): a point that is not passable, not connected with the Firebat, or inside a structure / container is refused at once with nothing charged; otherwise the Firebat walks, the gas, the limit and the place are checked again at the Complete stage.
- **Prepared builds**: `build.build_status` (inputs digest vs build manifest, built file vs installed file) lets `prepare()` skip a map that is up to date; the launcher shows the status; `tools/prebuild.py` prepares the current maps. The install / uninstall guard used a PowerShell process query that took 17-25 s while the game ran; `procs.command_line` (NtQueryInformationProcess) takes milliseconds. The creation time of an own test game is read with GetProcessTimes (the old query could return nothing, so the record had no creation time and the safe cleanup refused), compared as instants (`isolation.same_moment`).
- **Mission Workshop** (`tools/workshop.py`, `tools/gui_workshop.py`): variants inside the mission card, a frozen resolved base + a dict of changed field ids, `effective_cfg`, a full snapshot per built revision (the build plan carries `snapshot`, a snapshot with a `campaign` part is refused), map name `..__WK<id>R<revision>`; a changed base never changes a built variant. Real-window check `tools/workshop_window_check.py`, real build + start check `tools/workshop_run_check.py` (through the test queue).

## TTychus01 pheromone decoys: architecture notes (agreed 2026-10-27; implemented as `core/GhostOpsTychus.galaxy`, partly verified in the game, see MISSION_ROADMAP "TTychus01 first implementation")

- **Shared:** the turret ground salvo (key A, area aim, cancel, cooldown) is the module of Hour X, not a copy; the Ghost abilities (permanent cloak, early detector warning, auto-fire switch, rifle shot) are the shared ones; their availability for TTychus01 is a mission setting recorded in the applicability table of `docs/MISSION_ROADMAP.md`.
- **New mission mechanics (design only):** a decoy shell of the marauder (point target, capsule unit with a health bar, the nearest suitable Zerg walk to it and attack it, then a short rage against the Protoss, then the normal behaviour; only attracted units are affected; a point the ground Zerg cannot reach creates no decoy and spends no charge); an artifact that only an SCV extracts and carries (marker, drop on death, pick-up by another SCV, cancel does not move it); an evacuation transport as a landing point with an "Evacuate" command.
- **Original checks to replace:** the guardian-destroyed victory / artifact-lost defeat and the "Zerg reached the artifact" condition of the original script conflict with invulnerable guardians and the evacuation victory (see `docs/RESEARCH.md`, "TTychus01 artifact race").
- **Save / load requirement:** decoys and attracted groups, the artifact (place, ground, carrier, transport), the phase of the assault and evacuation, timers and one-shot events without repeats.

## Folding and redeploying fortifications: architecture notes (agreed 2026-10-27; implemented as `core/GhostOpsFold.galaxy`, config key `fold`)

- **One shared mechanic**, availability and parameters per mission setting; no per-map implementations. First queue: bunkers and missile turrets; other buildings are an open question; flying buildings keep their stock movement.
- **Flow (proposal):** select the structure, command "Fold"; an SCV walks up and dismantles for a time; only on completion the structure disappears and one kit of the same type is added to the existing shared kit counter (the one that reserves on construction start and releases on cancel, shown in the build button name); the SCV may then place it elsewhere through the ordinary build menu; no second payment for the structure and no refund when folding.
- **Rules:** the bunker garrison is unloaded first; cancel or death of the dismantling SCV leaves the structure and gives no kit; destruction of the structure during the dismantling gives no kit; health and the cooldown of the ground salvo are carried over, not reset; save / load never produces a building and its kit at the same time.
- **Open:** dismantling time, the list of other buildings, how the stored state of a returned kit is represented and shown.

### Implementation notes (2026-10-27)
- **Fold:** one module with owner hooks (`GhostOps_Fold_OnReserve / OnFinish / OnCancel / OnBurn`) that the kit counter of each mission calls (Hanson families 0 turret / 1 bunker, Defence codes 1 bunker / 2 turret, Tychus module); stored kits keep life and the end time of the salvo cooldown; only the nearest free SCV works, any other order or a distance over 4.5 cancels, one kit per dismantling; the structure stays vulnerable.
- **Decoy:** shell = `CEffectLaunchMissile` with the stock grenade shell, capsule = own unit (egg model of the Zerg with a green tint and the fungal cloud, no barrel data), owner 0 after the cast so that neither the Protoss nor the guardians choose it (they only pick enemies) while the Zerg attack it by order; charges = `Charge` with `TimeUse` inside the Charge element (a separate Cooldown element does not restore charges); `BestUnit` makes one Marauder of a selected group throw; the order to an unreachable point is stopped by a 0.1 s scan (`PointPathingIsConnected` with a Zerg-side point); attracted Zerg are script controlled, taken out of the original groups, and re-ordered when the AI overrides.
- **Guardians:** damage events of a player-1 source give the life back; the original attack triggers are preceded by a hook that orders the guardians at the nearest Zerg of their area; the original guardian-destroyed victory/defeat is replaced by the module (hook `GhostOps_Ty_OnGuardianDied`), the result goes to the original victory/defeat triggers through the poll hook in `gt_DefeatBaseDead_Func`.
- **Scenario traps:** the Galaxy type of a text tag is `int`; do not name a dev command like another (`tpg` was both "teleport Ghosts" and "pause guardians"); alliance id constants other than `c_allianceIdVision` / `Pushable` are not defined in this build.

## Epidemic: night sorties with dropped barrels and the base supply zone (agreed 2026-10-27; NOT implemented, requirement for the next stage)

- **Barrel drop (replaces the earlier idea of fire support from the Hercules and of a "weak infested only" damage filter):** one ability on the night transport ("Drop barrel", point target, button + hotkey); the ship flies to the point (no long-range bombing), a barrel unit visibly falls from the ship and explodes on touching the ground with the look and rules of the existing fuel container blast (`core/GhostOpsHanson.galaxy`, config `hanson.containers`); the ground-placed barrels (key C) are not changed. Charges: 2 per sortie, refilled when the ship is back at the base (a per-unit charge with a script refill, no production, no loading); the ship stays vulnerable to anti-air. Number, range and sufficiency of the blast are experimental parameters.
- **Supply zone:** defined by the measured perimeter of the original base (not the current circle `epidemic.base`, radius 18) so that the defence positions are inside; inside it the fuel is not spent, an empty Hellion (the `GhostOpsNoFuel` buff) moves freely and the tank refills to the available limit; the rule "small field reserve until the truck returns, full tank after" and the fuel use outside the zone stay.
- **Save / load requirement:** the charges, a barrel in flight, the zone state and the truck phase restore without duplicates (a barrel in flight needs an explicit decision at the save).
- **Truck (implemented in revision 6):** detection and capture are separate events; ownership is handed over once when a ground fighter is within `capture_radius` of the truck; before that the truck is nobody's and not a target.
