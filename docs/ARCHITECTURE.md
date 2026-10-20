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

Nuclear strike chain (measured in the installed game 3.1.4, not guessed; `tactical_dev` + bank log `GhostOpsTac.SC2Bank`):
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
(`GhostOps_T1_OnOpeningLine` -> trigger `GhostOps_T1_SceneMsg`); hidden preset `easy_dev` writes `Banks\GhostOpsScene.SC2Bank`. TRaynor02: the scene stage machine got stage 8
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
