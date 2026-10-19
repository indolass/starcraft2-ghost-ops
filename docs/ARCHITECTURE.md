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
3. **Configuration** (`config/<mission>.json`, `schema_version` 3: `operatives.squad` + `start_hold_fire` + `ghost_permanent_cloak` + `ghost_start_cloaked`, `base_support.damage_multiplier` 1/2/3, `experimental.invulnerable_allies`) - validated by the build and emitted
   as `GhostOps_ApplyConfig()`. Galaxy cannot read files at runtime, so a future menu will call the
   Core setters instead.
4. **Build and validation** (`tools/`) - read the source map (MPQ), generate the block, patch with
   exact anchors (refuses ambiguous or already patched scripts), structural lint, write the map,
   `verify` (only `MapScript.galaxy` and, when the squad has Nova, the map's `UnitData.xml` differ;
   removing our additions restores both originals exactly), reversible install into `Maps/GhostOps`.
   One adapter + one config per mission; Core and build are shared.

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
