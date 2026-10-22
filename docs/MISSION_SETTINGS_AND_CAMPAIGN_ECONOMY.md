# Mission settings and campaign economy (design contract)

Created 2026-10-20 (documentation task; no code, balance config, map, save or game setting was changed).
Revised 2026-10-20 (second documentation task, same rule: no code, config, map, save or game setting changed, no game or test run): the Owner's **right to make a mistake**
(free save / load inside an operation), the separation of save, load, restart and a new operation (7.1, 7.5, 7.6), the result as a proposal accepted once and atomically (7.7), the immutable operation set
for saves (7.8), unambiguous list merging (6.2), hero identity versus balance (4), the status of the «Вне закона» design (9.1) and corrected cross-references. This file stays the one contract; no second contract exists.
Revised 2026-10-20 (third task, CE-0 and the roadmap queue): closing the game is not abandoning an attempt; an abandoned attempt's result is not accepted automatically; CE-0 results and the decisions they force are in section 14; the nearest sequence is TRaynor02 -> TRaynor03 preparation (THanson01 stays a later stage, its 1000 / 500 stays its own). The mission roadmap is [MISSION_ROADMAP.md](MISSION_ROADMAP.md); it is NOT a second economy contract.
Linked from [ARCHITECTURE.md](ARCHITECTURE.md) (section "Configurable missions and campaign economy") and [../ROADMAP.md](../ROADMAP.md) (stage CE).

## 0. Status labels

Every statement below carries one of these labels, nothing unlabelled counts as done.

| Label | Meaning |
|---|---|
| **[IMPL]** | exists in the repository today and is covered by the build / tests / game checks named in ARCHITECTURE and README |
| **[AGREED]** | an Owner decision about what must hold (a principle or a rule), binding for the design; not built unless the same row is also marked **[IMPL]** |
| **[AGREED-V1]** | the Owner agreed it for the first version of the economy experiment (section 9); not built |
| **[CE0-VERIFIED]** | confirmed in the installed game by the CE-0 technical probe (hidden dev presets only, 2026-10-20; evidence in RESEARCH.md "CE-0"). It proves the platform fact, **not** that a playable profile already uses it |
| **[REQUIREMENT]** | what any implementation of an agreed or designed rule must guarantee. It is architecture, **not** a statement that code already does it |
| **[DESIGN]** | provided for by the architecture so that it can be added later without rebuilding the base; not agreed for the first version, not built |
| **[OPEN - Owner decision]** | needs a decision of the Owner; nothing is assumed, no default is invented |
| **[OPEN - technical check]** | needs a check in the installed game / the real build before it can be relied on; compatibility is **not** assumed. A check is a technical step: once its stage is assigned it needs no separate permission |

The whole of this document except the rows marked **[IMPL]** is a design. Do not read any other row as a capability. Five things are kept apart everywhere: implemented and confirmed (**[IMPL]**), agreed for development
(**[AGREED]**, **[AGREED-V1]**), architectural requirement (**[REQUIREMENT]**, **[DESIGN]**), open question (**[OPEN - Owner decision]**) and technical check (**[OPEN - technical check]**).

## 1. Principles

1. A modder changes troops, abilities, limits and economy of one mission **through that mission's settings**, not through code. **[DESIGN]**
2. Ordinary changes are data. A special mechanic is a separate handler plugged in through the mission adapter. There is no universal game engine and no programming language in JSON. **[DESIGN]**
3. The first implementation is minimal; the structure only has to leave room for later, richer rules. No empty subsystems, no dozens of files created in advance.
4. The map executes the rules of the current operation. It does not own the campaign.
5. Unsupported or unknown settings are an error, never silently ignored (section 6.4).
6. Combat difficulty, mission pressure and economy are independent settings (see ROADMAP, CA requirement 4).
7. **The right to make a mistake. [AGREED]** (Owner, 2026-10-20.) The player saves and loads freely during a mission and may, for example, lose fighters, load a save made two minutes earlier and try another tactic.
   Loading costs nothing: no money, no campaign losses, no smaller reward, no extra equipment spent. The losses of a future cancelled by a load are not kept. There is no mandatory ironman, no irreversible death
   accounting and no limit on the number of attempts. Rules: 7.5 - 7.7. It is a decision of the Owner, not a description of working code.

## 2. What exists today (verified against the repository, 2026-10-20)

| Area | State | Where |
|---|---|---|
| Per-mission config + adapter (`config/<mission>.json`, `adapters/<mission>/adapter.json`) | **[IMPL]** | ARCHITECTURE, `tools/build.py` |
| Config `schema_version` **4** is what `validate_config` demands (`schema_version must be 4`). README said 3; corrected to 4 on 2026-10-20 (documentation only, validator and schema untouched); ARCHITECTURE section "Configuration" already says 4 | **[IMPL]** | `tools/build.py` `validate_config` |
| Squad of 1..6 of `Nova` / `Ghost` / `Medic` (`operatives.squad`) | **[IMPL]** | `core/GhostOpsCore.galaxy`, `SQUAD_TYPES` |
| Type-level army rules: `army.fragile_unit` (type, max life, covered players only), `base_support.damage_multiplier` (1..3) | **[IMPL]** | ARCHITECTURE |
| Role groups in one mission (TRaynor02 garrison / trained / rescued Marines; Spotter / Operative Ghosts) | **[IMPL]**, hard-coded in the mission module | `core/GhostOpsTactical.galaxy` |
| Ability parameters of the *standard Ghost*: energy, cloak drain / cost, Snipe cost, cast time, cooldown, damage, `exclude_friendly`; `disabled_abilities` (`Snipe`, `EMP`, `TacNukeStrike`) | **[IMPL]** | `ghost_tuning`, `operatives.disabled_abilities` |
| Adding an existing ability to a unit type through the map catalog with explicit `AbilArray` / `LayoutButtons` indices (Nova hold fire) | **[IMPL]** | `core/data/NovaFireControl.xml` |
| Profiles: `presets.<name>` with `label`, `message`, `overrides`, optional `extends`, `default_preset`; `deep_merge` (dicts merge, **lists and scalars are replaced**); unknown name is a `ConfigError`; files keyed by mission + profile | **[IMPL]** | `resolve_config` in `tools/build.py` |
| Launcher (GUI, console, CLI) lists missions and profiles from the config and starts the same `build.prepare` | **[IMPL]** | `tools/launcher_core.py`, `GhostOps_Launcher.pyw` |
| Config-driven story messages and imported voice clips (`scene`, `audio.clips`, TRaynor02 stage machine) | **[IMPL]** | README, ARCHITECTURE |
| THanson01: development lock, 15 pre-placed turrets, one Ghost, convoy command | **[IMPL]** (profile `sniper`, experiment) | `core/GhostOpsHanson.galaxy` |
| Build-time embedding of resolved config into generated Galaxy constants | **[IMPL]** | `build_block` |
| Game-side write of a Bank file (dev logging: `GhostOpsDevTac.SC2Bank`, `GhostOpsDevScene.SC2Bank`, `GhostOpsDevHanson.SC2Bank`) | **[IMPL]** only in `*_dev` presets | dev presets |
| Saving and loading a running mission through the game's own menu (F10 -> Save, `LoadGameDone` redraw trigger). Checked in a real game for **specific** states only: TRaynor02 (before aiming, in flight, stage 8) and THanson01 (convoy wait and trip). `GameSaveCreate` is "Blizzard maps only" (not authorized for our maps), so a map cannot create a save by script | **[IMPL]**, limited to what README / RESEARCH / ROADMAP name | README (Save / load row), RESEARCH ("TRaynor02 final stage"), `LoadGameDone` in `core/` |
| Operation / attempt / result identifiers, a campaign save, acceptance of a result, a charge, a restart that re-issues a paid order, an immutable operation set, any autosave, a check that every state listed in 7.6 B survives a load | **none exists, nothing checked** | - |
| Persistent campaign state, resources between missions, purchases, plans, reports, roles as data, mission-level economy, a settings panel | **none exists** | - |

Consequences: today a mission's "squad" is a list of types without roles; roles exist only as code in the TRaynor02 module; there is no money, no price and no cross-mission state.

## 3. Separation of responsibility (A-G)

Names follow the project: *mission* = `config/<mission>.json` + `adapters/<mission>/`; *profile* = `presets.<name>` (Russian GUI word «профиль»); *Core* = `core/`.

### A. Catalog **[DESIGN]**
Definitions of units, equipment and abilities with default parameters, prices and purchase units (`kit` = one set, `soldier` = one fighter, `batch` = one batch), and **stable identifiers** (`unit.marine`, `kit.turret_missile`, `ability.snipe`). Identifiers never change meaning and are never reused. The catalog describes *what exists in the game and what it costs by default*; it does not say what a mission offers. One catalog file, shared by all missions (created only when the first purchasable item is built).

### B. Campaign rules **[DESIGN]**
Resources and starting stock, availability of missions and goods, what is carried over between operations, replay rules (section 7.3, open). One document for the whole campaign, versioned.

### C. Mission settings **[DESIGN]**, exists today only as the mission config
Per mission: preparation cost; available purchases and limits; initial squad and extra squads; unit roles; construction / training / research; abilities and their parameters; zones and the conditions in which a rule applies; changes of objectives and completion conditions; story messages and the events that trigger them. Today's `config/<mission>.json` is the seed of this layer; new sections are added to it as optional blocks (as `hanson`, `tactical`, `scene` were) rather than a second file.

### D. Profiles **[IMPL]** mechanism, **[DESIGN]** economy content
Differences of combat balance and of economy. A profile only overrides mission settings (and may `extends` another profile).
**Naming rule:** our profile «Лёгкий» (`easy`) is a Ghost Ops balance profile of the mission. The campaign difficulty of the SC2 map (Hard, `PlayerDifficulty`, `-difficulty 3`) is separate: it is a property of how the original map runs, kept at Hard for every profile ([IMPL], `difficulty.expected`). A profile may *declare* which native difficulty it expects; it never renames it or replaces it. Documents, GUI text and logs must say "profile" for ours and "Hard / native difficulty" for the map's.

### E. Operation plan **[DESIGN]**
One record per **operation** (one paid order; its runs are *attempts*, section 7.1): selected mission and profile; ordered equipment and mercenaries; cost; a **snapshot of the final resolved settings** and the **data version** (catalog version + hash of the resolved config). The plan is checked against the resolved settings and cannot change any characteristic or limit (section 6.4). Once the operation has started, the plan, the snapshot and the build are frozen as the immutable operation set (section 7.8).

### F. Campaign save **[DESIGN]**
Actual resources and property; completed operations; the active operation (`operation_id`, state, plan, charges already made, the list of its attempts with their `attempt_id`s, the reference to its immutable set); accepted results (`result_id`s). Owned by the launcher side (section 5), stored apart from `launcher_settings.json` and from game configs. A save made inside the game is **not** the campaign save and never changes it (7.6).

### G. Mission adapter **[IMPL]** for hooks, **[DESIGN]** for the economy duties
Connects general rules to the source map's events: where the intro ends (`start_hooks`, `GhostOps_ClaimStart`), recognises original and rescued troops (TRaynor02 rescue hook), connects completion (victory / defeat hooks) and special story mechanics. Where a generic rule cannot be expressed through data, the adapter carries a handler for that mission (section 4). The adapter also **assigns roles** to units after they are created or rescued; a role that no adapter assigns does not exist for that mission.

## 4. Roles and squads (section on troops) **[DESIGN]**

Four independent properties of a unit; no rule may infer one from another.

| Property | Meaning | Examples |
|---|---|---|
| **type** | game unit type (catalog id) | Marine, Ghost, Firebat, Medic |
| **role** | what the unit is for in rules | `garrison`, `operative`, `spotter`, `rescued`, `mercenary` |
| **source** | how the unit entered the mission | `scenario` (map-made), `plan` (ordered), `rescue`, `trained`, `reinforcement` |
| **identity** | an individual story identity | Raynor, a named Ghost, objects the scenario refers to |

A general rule must never read "operative = Ghost" or "garrison = Marine". A role is attached to a unit **after** it is created or rescued (the TRaynor02 module already does this for its own groups, **[IMPL]**; the general mechanism is **[DESIGN]**). A squad entry is `{id, type, role, source, count, anchor, event}` where `anchor` is a point or zone id of the adapter and `event` is an adapter event id (`mission_start`, `intro_end`, `rescue_complete` ...).

Supported operations (**[DESIGN]**; today only "replace the whole `operatives.squad` list" exists):
- keep the original composition (default, a profile that says nothing changes nothing);
- **replace** selected ordinary units: `match` by role/source/original type (never by "all Marines");
- **add** a defined squad: count, point, appearance event;
- assign a role after creation or rescue.

**Protected objects - protection of identity, not a ban on balance.** Story heroes and scenario objects (Raynor, units the scenario counts, the units behind defeat conditions) are listed in the adapter as `protected`. A mass or role rule can never match them, replace them, lose their stored references or break the original conditions of the mission. Replacing Marines by Firebats must not replace Raynor, break stored references in the original script or the defeat condition.
Protection does **not** forbid balance. A modder may set the life, weapons and abilities of a hero **explicitly, addressed to that hero by his identity**, and the hero stays the same unit with the same references. A hero gets **no** extra survivability automatically: nothing is raised unless the modder writes it. **[DESIGN]**; today only the type-level `army.fragile_unit` and the Ghost parameters exist (**[IMPL]**, section 2).
**Roles come from the adapter.** A role (`garrison`, `operative` ...) is attached by the mission adapter to a unit after it is created or rescued; it is not a property the original script provides. Today only the TRaynor02 module assigns roles (its garrison / trained / rescued Marines, **[IMPL]**). **TRaynor01 has no ready `garrison` role**; a profile that names one (the example in section 11) first needs the TRaynor01 adapter to assign it.

**When a mission handler is required** (no promise that any replacement works by data alone):
- the unit is created by original script that stores it in a variable which other scenario code reads (counts, conditions, dialogues, cinematics);
- the replacement changes what the scenario code expects (type checks, cargo capacity, a count compared to a constant);
- the unit is part of a cutscene or a scripted order chain;
- the new type needs data the map does not contain (catalog / model / abilities).
In those cases the adapter provides a handler for that mission and the rule names it; the validator (section 6.4) refuses a replacement of such a unit when no handler is declared. Existing example: TRaynor01 Marines at 1/1 life works as a *type-level* rule (`army.fragile_unit`), because the scenario's own Marines are only a type to the rest of the code; that is not evidence that any replacement works.

## 5. Ownership of campaign state and handoff

**Owner of the general campaign state: the launcher side** (a Python component next to `launcher_core`), because Galaxy cannot read files at runtime (ARCHITECTURE, Configuration) and a map is rebuilt per run. The campaign save is a file in `%APPDATA%\GhostOps` (new file name reserved: `campaign_save.json`; it is **not** `launcher_settings.json`). **[DESIGN]**

**The map owns only the current attempt of the current operation**: the plan it was built with and the running counters, kept in saved Galaxy globals so that a **loaded game continues from the state of its save** (the existing stage-machine pattern, **[IMPL]** for TRaynor02 scene stages; which states survive a load is checked case by case, section 2 and 7.6 B). The map never touches the campaign stock directly, and nothing it writes outside the save is read back as gameplay state (7.6 B).

Handoff:
1. **Campaign → map: the plan is baked in at build time.** The build already turns the resolved config into Galaxy constants and a manifest (**[IMPL]**); the plan snapshot (`operation_id`, ordered kits, mercenaries, handed resources, `data_hash`) is added to the same generated block. No runtime file read is needed. The build that carries it is kept as part of the immutable operation set (7.8). **[DESIGN]**, mechanism **[IMPL]**. Where the `attempt_id` of a run comes from (the launcher at launch, or the map at its own start into a saved global, which would travel with a save) is **[OPEN - technical check]**; nothing is decided.
2. **Map → campaign: a result *proposal*, not an accounting entry.** At the original victory (hooks exist: `gt_VictoryDominionOutpostCompleted_Func`, `gt_VictorySetup_Func` for TRaynor02, **[IMPL]** as hooks that only switch our module off) the map writes one proposal: `operation_id`, `attempt_id`, `result_id`, `data_hash`, outcome, end-of-mission resources, counters (found, spent, mined, kits used). Writing it changes nothing in the campaign. A Bank file present in the folder is **not** evidence that this proposal is the one to accept: it can be left from an earlier launch (7.7). Candidate carrier: a Bank file written by the map, read by the launcher after the game exits. **[OPEN - technical check]**: Bank writing is proven only for the dev presets; it must be checked that (a) a production map from `Maps\GhostOps` can write it, (b) the file path / author folder is predictable, (c) a record written just before the victory sequence survives a normal exit and an abnormal exit, (d) save/load cannot produce two records, (e) reading the player's resources at the victory moment is correct before the original end sequence changes anything. Compatibility is **not assumed**; if the Bank route fails, another channel has to be chosen and documented (not decided).
3. **Acceptance** happens in the launcher and only there: it checks the proposal against the operation, the attempt, the immutable set and the list of accepted results (7.7), and then changes the campaign stock and marks the result accepted in **one** consistent operation (7.7).

## 6. Configuration order, inheritance and validation

### 6.1 Order of application **[DESIGN]**, extends **[IMPL]**
From weakest to strongest; each later layer overrides the earlier one:

1. Core defaults and catalog defaults (A)
2. Campaign rules (B) - only for campaign-level fields; they are not overridden by a mission except where B says so
3. Mission settings (C) - `config/<mission>.json` base (everything except `presets` / `default_preset`)
4. Profile parent (`presets.<x>.extends`), **[IMPL]** one level
5. Profile overrides (`presets.<name>.overrides`)

The **operation plan (E) is not a layer**: it is validated against the result and then recorded; it can only *select* from what the result offers.

### 6.2 Merge rules **[IMPL]** for current keys, explicit forms **[DESIGN]**
- Mappings merge key by key; scalars replace.
- **An ordinary list is replaced whole** (current behaviour **[IMPL]**; example: `extreme` replaces `operatives.squad` with one Ghost). Lists are never concatenated and **never glued automatically**, so troops cannot accumulate silently. A modder who writes a list in a profile replaces the **entire** list of the layer below: a squad written in a profile replaces the whole squad.
- **Changing or removing one entity of a list, addressed by its `id`, is a separate, explicitly marked operation, never a side effect of writing a list.** The planned entity lists of the new sections (squad entries, purchases) carry an `id` per entry; a duplicate id inside one list is a validation error. Only a marked operation touches one entry; writing the list itself replaces all of it. A modder must know in advance whether his change replaces the whole squad (a list) or one fighter (an id operation). **[DESIGN]**
- The **syntax of these operations is a draft** (for example a marked change `{"id": "...", ...}` and an explicit removal `{"id": "...", "remove": true}` were only sketched). The **current `deep_merge` does not support any of them** and must not be declared as supporting them: it merges mappings and replaces lists and scalars, nothing more. Until the operations are specified and built they are not part of the format, and a config must not use them; the target behaviour of the validator for an unknown or not-yet-implemented key is an error that names it (6.4). How the present validators react to such a marker has not been checked and is not claimed.
- The merged result, not the input, is validated.
- Override of a key that does not exist in the layer below is an error unless the key is declared as optional in the format.

### 6.3 Provenance view **[DESIGN]**, not built
A future command (`build.py show-config --mission M --preset P`) prints the final configuration with, for every value, the layer and file it came from (catalog / campaign / mission / profile parent / profile) and what it replaced. The same report is stored in the plan snapshot. Until then, the only inspection is the resolved config the build already writes into the manifest.

### 6.4 Validation **[DESIGN]** (today `validate_config`, `validate_tactical`, `validate_hanson`, `validate_ghost_tuning` check only their own keys)
Before a build or a plan is accepted, the resolved settings and the plan are checked for:
- unknown identifiers (unit, kit, ability, zone, event, role, handler);
- wrong types, negative or non-integer quantities / prices / limits;
- zones and events that the adapter does not define;
- purchases above the limit; a plan that differs from the resolved prices or limits;
- composition conflicts with protected objects (a rule that matches a protected object; a replacement without the handler the adapter requires, section 4);
- **unsupported parameters**: every key must be known to the format or to a named handler; an unknown or not-yet-implemented key is an error that names the key. Nothing is silently ignored (this is how the current validators behave for their sections, **[IMPL]**).

### 6.5 Units **[DESIGN]** convention, existing keys stay as they are
| Quantity | Unit |
|---|---|
| time | **game seconds** (Galaxy game time, the unit of `tactical.story`, `snipe.cooldown`); real-time values are separate fields written with a `real` marker in the key name (current clip durations are real seconds). The two are never mixed in one field |
| resources | whole minerals / gas (integers) |
| distance, range | game distance units (map cells, 1.0 = one cell) |
| multipliers | factor, 1.0 = unchanged. The catalog behavior `DamageDealtFraction` is additive, so the build writes factor - 1 (**[IMPL]**, see ARCHITECTURE "Final stage") |
| energy, life | game points |

## 7. Plan, save and accounting rules

### 7.1 Identifiers and operation states **[DESIGN]**
Three identifiers, and none carries the duties of another:

| Identifier | Names | Created | Carries | Is never |
|---|---|---|---|---|
| `operation_id` | **one paid order**: mission, profile, plan (equipment, mercenaries), price | when the order is planned | the one preparation charge; the immutable operation set (7.8); the stock handed to the surface; the mark "accepted" | the name of one run on the map or of one result |
| `attempt_id` | **one run** of that operation on the map, begun from the operation's baseline (its paid composition, ammunition and resources) | at the first start and at every full restart (7.6 C) | belongs to exactly one operation; every game save made in it belongs to it; loading one of its saves continues it | created by a load; a purchase |
| `result_id` | **one result proposal** written by an attempt (7.7) | when the attempt writes the proposal | the key of acceptance: one `result_id` is accepted at most once | reused by a second proposal |

Where the `attempt_id` comes from (the launcher at launch, or the map at its own start into a saved global that would travel with a save) is **[OPEN - technical check]**; the rules below only need that it is unique and tied to one operation.

Operation states: `planned` → `paid` → `started` → `reported` → `accepted`, with side exits `abandoned` and `failed_to_start`. The attempts of a started operation are listed in the campaign save (F); each is `live` (the one being played or resumable), `ended` (it wrote a proposal) or `abandoned`.
  **Closing the game is not abandoning the attempt** (Owner, CE-0 task): the player may save, close the game and continue tomorrow; that attempt stays `live`. An attempt becomes `abandoned` only by an **explicit refusal** of the player or by a **full restart** (7.6 C).
- **One preparation charge**: the cost is taken once at the `planned → paid` transition, recorded in a ledger line keyed by `operation_id`. A load, a restart and every further attempt of the same `operation_id` never charge again; only a new operation (7.6 D) can.
- **Start failure**: the plan, snapshot and charge stay; a failed build / launch leaves the operation `paid` (not started). A retry uses the stored plan. The paid order is not lost. Whether the Owner may cancel before `started` and get the preparation cost back is **[OPEN - Owner decision]**.
- **Started operation**: plan, settings and build are frozen as the immutable operation set (7.8); a changed profile, catalog or order does not change a started operation.
- **Issue of troops and kits - corrected.** An earlier version said that a saved Galaxy flag and the record `started` stop a second issue "after a loaded game or a restart of the same operation". That joined two different cases, and a saved flag does **not** by itself keep the state after a full restart:
  (a) after a **load** the world is the save's world; the flags and counters of what was issued are part of the saved state and come back with it, so nothing is issued again beyond that state (7.6 B);
  (b) after a **full restart** nothing of the old game exists, a Galaxy flag included; the new attempt is issued the **original paid composition once** (7.6 C), and it is the launcher's list of attempts, not a flag in the map, that says which attempt is live.
  The map's own flag (the `GhostOps_ClaimStart` / `go_sceneDone` pattern, **[IMPL]**) only stops a double issue inside the timeline of one attempt.
- **One acceptance**: see 7.7.

### 7.2 Two stocks, no copies **[DESIGN]**
The campaign stock (the ship) and the map's resources are kept apart and linked by a conservation rule: what is handed to the surface for the operation is **removed** from the campaign stock **once**; what remains in the accepted result is **returned** as the passed remainder; a resource cannot be both left on the ship and given to the map. The handed stock belongs to the **operation**, not to an attempt: a restart (7.6 C) gives the new attempt the same handed stock again and removes nothing a second time; what the abandoned attempt held or mined is discarded and is never added to the new attempt, to the campaign stock or to the remainder. Mission report lines: starting stock, mined, found, spent, passed remainder (the report is built from the accepted result proposal). What happens to the handed stock when the operation itself is abandoned is part of the refund question (**[OPEN - Owner decision]**, 7.1, section 12).

### 7.3 Replay and rollback of an accepted operation **[OPEN - Owner decision]**
This open policy is about **one case only**: loading or replaying a mission **after its result has been accepted**, or after later missions have been played. It does **not** touch ordinary saving and loading inside an unfinished operation, which stay free (7.5).
Proposed (not decided): the reward of an operation is accepted **once**; a replay of an accepted operation is allowed as practice with no campaign income. Rolling the campaign back means restoring a copy of the campaign save kept at operation start (one copy per active operation, not a copy per attempt). An irreversible (ironman) mode is **not** introduced without a separate Owner decision. The replay rule is part of the campaign rules (B), so it is changeable without touching the map.
Until the policy exists: a result proposal for an already accepted operation is simply **not accepted** (no income, no change of stock), and **nothing mixes an old map automatically with the new campaign stock**. A practice / rollback policy has to be written before an old save can be used with the current campaign state.

### 7.4 Surviving units **[DESIGN]**
Surviving units are **not** transferred into the campaign automatically. Until the personnel rules exist (section 10) the result proposal carries only resources and counters. When personnel exists, per-soldier records are changed only when an **accepted** result is applied (7.7), never from events during play, so a death of a cancelled future cannot be stored.

### 7.5 The right to make a mistake: free save and load inside an operation **[AGREED]**
Owner decision, 2026-10-20. The binding statements:
1. The player may save by hand at any time the game allows, and it costs nothing.
2. There are several return points: several manual saves of the same attempt by the game's own means; the player chooses which one to load. The design does not promise which concrete ways of saving work together with it (see item 8 below).
3. Loading is not punished: no money, no campaign losses, no smaller reward, no extra equipment spent.
4. The losses of the future that a load cancels are not kept anywhere (7.6 B, 7.7).
5. There is no mandatory ironman, no irreversible accounting of deaths and no limit on the number of attempts.
6. Autosaves may be provided later as a **configurable** option. They are **not implemented now** and never replace manual saves. Note: `GameSaveCreate` is "Blizzard maps only" (RESEARCH), so a script-made save is not available to our maps through that call; whether the game offers maps an autosave of its own and how it behaves is **[OPEN - technical check]**.
7. The mandatory scenario: fighters are lost → the player loads a save made two minutes before the loss → tries another tactic. The `operation_id` and the `attempt_id` stay the same, nothing is charged, the campaign stock does not change, the fighters, ammunition and kits are those of the save, and the losses of the earlier timeline do not exist any more.
8. **[OPEN - technical check]** What is verified is saving through the game menu (F10 → Save) in specific cases (section 2). Not verified, not promised: quick save, several named slots, autosave, and whether a loaded save needs the same map file name, path or content (7.8).

### 7.6 Save, load, restart and a new operation are four different things **[AGREED]** (principle), **[REQUIREMENT]** (rules)

| Action | `operation_id` | `attempt_id` | Charge | Campaign stock | State of the map |
|---|---|---|---|---|---|
| **A. Save** | same | same | none | unchanged | the state of the current attempt is recorded in a game save |
| **B. Load a save** | same | the attempt that made the save (continued) | none | unchanged | exactly the state of the save |
| **C. Full restart of the same paid operation** | same | **new**; the old one becomes `abandoned` | none (not a new purchase) | unchanged; the same handed stock is used again (7.2) | the operation's original paid baseline |
| **D. New operation with a new order** | **new** | new | its own, once | changed by that charge | a new baseline from a new immutable set |

**A. Save** records the state of the current attempt. It does not change the campaign and writes no result.

**B. Load** returns the state **at the moment of the save**, including: living fighters and their health; resources on the map; ammunition and kits; built and under-construction objects; the state of the missile and the aiming; transport and passengers; stages of dialogues and of the landing; timers, objectives and other states the mission needs. Nothing is issued again beyond what the save contains. **[REQUIREMENT]** Irreversible events of the cancelled future must not leak into the loaded game through an external journal or a Bank: gameplay state comes only from the save; nothing the map wrote outside the save (a Bank, a file) is ever read back to restore or change gameplay state; kit counters, issue flags and the like are saved globals only; what the map writes outside the save is limited to result proposals (7.7) and development logs. Which of the listed states really survive a load has been checked for specific cases only (TRaynor02 aiming, flight and stage 8; THanson01 convoy; section 2); the complete list is **[OPEN - technical check]**, not a claim.

**C. Full restart** of the same paid operation creates a **new attempt** with the **original paid composition, ammunition and resources of this operation**. It is not a new purchase and not an additional batch of equipment; the resources of the abandoned attempt are not added to the new one (7.2). It needs the immutable operation set (7.8).

**D. A new operation with a new order** is a separate action. A load or a restart never turns into one, and changing the order of a started operation is not a way to restart it.

### 7.7 The result is a proposal; acceptance; what the architecture prevents **[REQUIREMENT]**
What the map writes at the end is a **result proposal** (section 5): `operation_id`, `attempt_id`, `result_id`, `data_hash`, outcome, end-of-mission resources, counters. It is **not** an immediate, irreversible change of the campaign; the campaign changes only when the launcher accepts the proposal. Loading an ordinary save inside an unfinished operation stays free throughout.

The launcher accepts a proposal only when **all** of these hold: the operation exists and is `started` or `reported` and not yet `accepted`; the `attempt_id` is an attempt of that operation **and is not `abandoned`** (membership in the operation's attempt list is necessary but **not sufficient**; the result of an abandoned attempt is never accepted automatically); the `data_hash` equals the one of the immutable set (7.8); the `result_id` has not been accepted before; and the proposal is **fresh**, i.e. it is not a leftover of an earlier launch. The existence of a Bank file is **not** evidence that this very proposal is the one to accept: the record may remain from a previous launch. How freshness is proven is open and none is chosen (**[OPEN - technical check]**): a launch token that the launcher gives the map and the map copies into the proposal; or the launcher clears or archives the proposal slot before each launch and treats a pre-existing record as stale; or an `attempt_id` made by the launcher. **Resuming an old attempt by loading its save** before the result of the operation is accepted must stay possible and must not charge again: the attempt is `live` again as long as the operation is not `accepted` (an `abandoned` attempt stays abandoned by the Owner's rule above, unless the player explicitly resumes it - **[OPEN - Owner decision]**). How the launcher learns that a loaded save belongs to a particular attempt (a saved attempt identity carried by the save, logged by the map when the load completes) is checked in CE-0 and is **not** declared working in advance; until it is solved a proposal that cannot be tied to the launched run is held, not accepted automatically.

**One consistent operation.** The change of the campaign stock and the mark "this `result_id` is accepted" must be saved as **one** operation: one atomic write of one file (temporary file, flush, replace) or one transaction; if the storage cannot do that, an idempotent journal keyed by `result_id` that is applied again on recovery. A failure between the two steps must give neither a second reward nor a lost reward.

| Threat | How the architecture prevents it |
|---|---|
| Acceptance of a stale result of an abandoned attempt | the proposal carries `operation_id`, `attempt_id`, `result_id`, `data_hash`; the launcher checks them against the operation's attempt list and the immutable set and requires a fresh proposal; a Bank record found on disk proves nothing |
| A second reward for one result | `result_id` and the operation's `accepted` mark; one acceptance per operation; the stock change and the mark are one atomic operation |
| A second payment on load | the charge exists only on the launcher side at `planned → paid`, keyed by `operation_id`; the map has no way to pay; a load and a restart do not touch it |
| Saving the deaths of a cancelled future | no journal of deaths is written during play; the campaign changes only by an accepted proposal; the map never reads outside data to restore gameplay (7.6 B); personnel records, when they exist, change only at acceptance (7.4) |

Still open: which proposal counts when **one** attempt produced several (for example a victory, then a load of an earlier save and a second victory in the same game session) is **[OPEN - Owner decision]**; the requirement is that at most one proposal per operation is accepted and the second never adds to the first. Loading an **old mission after its result was accepted** or after later missions is a separate case with its own open policy (7.3) and does not block anything above.
These are architecture requirements. None of them describes code that exists.

### 7.8 The immutable operation set for saves **[REQUIREMENT]**, storage **[DESIGN]**
A single map file under the shared name "mission + profile" with the snapshot kept in the manifest is **not enough**: the next build or the next change of an order or of settings would overwrite the map that a started operation still needs to be continued from its saves. For a started operation the launcher keeps an **immutable set**:
- the built map;
- the snapshot of the settings (the resolved configuration) and the order (plan);
- the dependencies, or at least the information about their versions (catalog version, Core / source version, the identity and hash of the user's original map, the game version the set was built and checked with);
- the identifiers and checksums: `operation_id`, the set's own identifier and hash, `data_hash`.
A changed order or changed settings never overwrite the set of a started operation: a different order is a new operation (7.6 D), a different build is a different set.
One hash is **not** a promise that a game save will load: whether a save made with one build loads with another, and whether the game checks the map's name, path or content, must be checked in the installed version (**[OPEN - technical check]**). The set is not deleted because the player closed the game or started another test, while any save that is meant to stay supported depends on it. The rules of keeping and cleaning are to be defined separately (**[OPEN - Owner decision]**); no archive manager is designed now and no file is deleted by this document.

## 8. Abilities **[DESIGN]** unless marked

Separate two things: (1) **parameters of a standard ability** and (2) **adding a new ability**.

(1) Parameters: availability and button visibility; energy cost; cooldown; preparation and sustain time; range; damage; target filters; number of charges and their recovery; conditions by role, zone and mission phase. Today **[IMPL]** for the Ghost only: availability (`disabled_abilities`), energy / cloak numbers, Snipe cost, cast time, cooldown, damage, `exclude_friendly` target filter (`ghost_tuning`). Charges, role / zone / phase conditions, and button visibility on conditions are **[DESIGN]**; whether the installed 3.1.4 data supports catalog charges for these abilities is **[OPEN - technical check]**, otherwise they are a script counter in a handler.

(2) Adding an ability: adding an existing campaign ability to a unit type through the catalog with explicit indices is proven (Nova hold fire, **[IMPL]**). A truly new ability needs its own data and effects and is a mission handler, not a parameter. **Arbitrary dynamic granting of abilities during play is not promised**: only enable / disable / show of abilities already in the unit's data (`UnitAbilityEnable`, `TechTreeAbilityAllow` as in the TRaynor02 strike chain, **[IMPL]**) is known to work; anything beyond is **[OPEN - technical check]**.

## 9. Agreed scope of the first version (Owner, 2026-10-20) **[AGREED-V1]**

The TRaynor02 → THanson01 pair is the **first economy experiment**. It does not set the final order of the campaign and does not cancel the earlier agreed **TRaynor03** (ROADMAP: planned order TRaynor02, TTychus01, TRaynor01, TRaynor03, the rest).

### 9.1 TRaynor02 «Вне закона»
- No purchases before the mission.
- The current combat variant (`tactical`) is kept.
- After the virus message (the Adjutant transmission of the story scene), Raynor adds: «Ресурсы всё равно собирайте. Нам ещё корабль чинить и людей снаряжать. Пригодятся для следующих операций». A portrait and text are enough; **no new audio work** is needed. (Connecting point: the stage machine in `adapters/traynor02/adapter.galaxy`; the Raynor portrait model has to be found / verified when it is built - **[OPEN - technical check]**.)
- On victory the remaining minerals and gas are kept for the campaign (passed remainder, section 7.2). On defeat or abandonment nothing is handed over **[OPEN - Owner decision: confirm]**.
- The final report separates: starting stock, mined, found, spent, passed remainder. How "found" (resource containers / rewards) is told from "mined" is **[OPEN - technical check]**.
- Which stock the mission starts with (the original map's own, or a part of the campaign stock) is **[OPEN - Owner decision]**; the minimal reading consistent with "no purchases" is: the original start, and only the remainder passes out.
- The remainder is carried by an **accepted result proposal** (7.7), not by an entry the map makes in the campaign by itself.
- **The agreed minimal scope of this design is exactly:** the current combat variant, no purchases before the mission, Raynor's explanation about collecting resources for the future, the carry-over of the remainder on victory, and the final report. Nothing else is added here.
- **Discussed, NOT approved by the Owner:** a complete ban on training new soldiers in «Вне закона». It was a proposal in discussion; it is **not** an agreed balance change and is not recorded as one. No other new goals, restrictions, automatic rewards or changes of the nuclear strike are added by this document. (**[OPEN - Owner decision]**)

### 9.2 THanson01 «Эвакуация»
- **Preparation costs 1000 minerals and 500 gas.**
- Before the mission the player can buy **turret kits** (Missile Turret) and **mercenaries**.
- Turret rule: **N kits ordered → the workers may build exactly N turrets for free.**
  - A kit is **reserved when construction starts**.
  - **Cancelling returns the kit; completing spends it.**
  - **The death of a built turret does not return the kit.**
  - No second payment inside the map (the purchase is only in the plan).
  - The kit counters (reserved / spent) are saved globals and part of the state of a save (7.6 B). A load returns them to the saved values, so a turret that died, or a kit reserved, in a future cancelled by a load does not count; a full restart (7.6 C) gives the new attempt the original ordered number of kits.
- Number and availability of mercenaries are first oriented on the original; exact correspondences **must be checked before implementation** **[OPEN - technical check]**.
- Original troops and the Ghosts that the current variant already provides stay; **no additional free armies**.
- The price of **a turret kit** and the **final prices of mercenaries are NOT agreed**. No price in this document or in any config is a decision of the Owner. The only agreed numbers are the preparation cost above.
- **Delivery of mercenaries - method and moment: OPEN QUESTION** (no existing document defines it). Candidate moments for discussion only: at mission start with the starting squad; when the intro ends (`intro` hook, `GhostOps_ClaimStart`); by a transport / drop pod during play.
- Compatibility with the existing `sniper` profile (**[OPEN - Owner decision]**): the profile locks development (`hanson.lock_development`, every producible type and upgrade is forbidden) and pre-places 15 turrets. Free turret construction needs a profile in which building turrets (only turrets) is allowed and the pre-placed ones are reconsidered. A new profile, not a change of `sniper`, is the proposed route; its name is not chosen.
- Kit accounting needs a hook on construction start / cancel / completion for the turret type. How these events are read is **[OPEN - technical check]** (the TRaynor02 module already works with unit-created events, **[IMPL]**; construction-progress events are not used anywhere yet).

### 9.2.1 THanson01 «Эвакуация»: газ карты и взрывные контейнеры (2026-10-22, **[СОГЛАСОВАНО]** механика, **[ЭКСПЕРИМЕНТ]** цены)

Дополняет 9.2, ничего в нём не отменяя. Подробности механики: `docs/MISSION_ROADMAP.md` 8.1.
- **Газ на карте - расходуемый ресурс самой операции:** отправка колонны 100 газа (списывается один раз при принятой команде), один взрывной контейнер 25 газа (списывается при успешной установке, вместе с единицей общего предела 12). Отмена, невозможная установка, повторный клик, подрыв, загрузка ничего не списывают. Все числа в `hanson` (`convoy_fuel.gas_cost`, `containers.gas_cost`, `containers.limit`) и в таблице профиля; **это экспериментальные числа, не решение Owner.**
- **Карта и кампания разделены:** газ карты - обычный газ игрока на карте (добыча существующими добытчиками). Запасы кампании и ранее согласованная плата за подготовку **1000 минералов / 500 газа** этим не выдаются на карту и не заменяются ею; отдельный запуск карты не трогает кошелёк Owner.
- **Закупки THanson01 не подключены** (9.2: цены комплектов и доставка наёмников не согласованы): профиль `sniper_next` использует явно обозначенный **тестовый комплект** (15 готовых турелей прототипа, «закупки не подключены»), старый и новый заказ не складываются.
- **Состояние и сохранение [REQUIREMENT]:** газ, факт оплаты рейса, состояние колонны (собирается / ждёт приказа / в пути), общий предел и список поставленных контейнеров, факт подрыва - часть состояния сохранённой игры; загрузка не списывает и не выдаёт повторно, перезапуск оплаченной операции не требует повторной оплаты.

### 9.3 TRaynor03 «Час икс»: the paid kit in the NEW design **[AGREED]** (Owner, 2026-10-21; built 2026-10-21 as the experimental preset `defence`, see `docs/MISSION_ROADMAP.md` 7.8: first six marines are part of the paid order, minimum 6 marines, same prices / limits / total 1640 as experiment numbers, kits spent at construction finish)

The prepared order of the existing economy (section 7: paid once, immutable operation set, accepted-result carry-over) is applied to the new version of the mission as follows. Details of the mission itself: `docs/MISSION_ROADMAP.md` 7.7. Nothing here is implemented; the implemented TRaynor03 (order ready at the start of control, `zerohour`) is the previous build and keeps working as it is.
- **What is bought (unchanged principle):** a limited number of bunkers, anti-air missile turrets, marines and repair SCVs. No barracks at the start, training new soldiers is closed, nothing is bought on the map.
- **Bunkers and turrets are built by the player** (any place he chooses) **[AGREED]**. The paid kit is applied like the THanson01 turret rule (9.2) **[REQUIREMENT]**: N bunkers / M turrets ordered = exactly N / M free constructions; a kit is reserved when construction starts, cancelling returns it, completion spends it; **the loss of a finished building does not return a kit**; there is no second payment inside the map. Counters (reserved / spent) are saved globals and part of the state of a save (7.6 B): a load returns them to the saved values and never grants an additional kit.
- **Technical check [OPEN - technical check]:** construction start / cancel / completion events for bunkers and turrets in the installed game (the same check as list item 3 of section 12, extended to bunkers); how the kit is enforced (disabled build buttons at zero, removal of an over-limit construction without a refund). Implementation is the next technical stage.
- **Marines:** the landing (about 15 game seconds after control starts, a first group of six, then the main group, existing pod animation, no automatic boarding of bunkers) delivers the ordered marines. **[OPEN - Owner decision]** whether the first six are part of the paid order or a base squad of the mission; no hidden free six is created.
- **Surviving units / remainder (7.4, 7.7):** unchanged: the remaining stock of the operation is carried by an accepted result proposal; no new reward is invented. Unspent kits are not converted into stock unless the Owner decides so **[OPEN - Owner decision]**.
- **Prices and limits:** the experimental numbers of the implemented build (`zerohour.prices`, `limits`, `recommended`; marine 40, bunker 75, turret 75, SCV; recommended 16/4/4/8 = 1640) are NOT approved for the new version; new prices, the turret kit price and the limits are decided with the balance **[OPEN - Owner decision]**.
- **Ability to fire at the ground (manual turret salvo)** costs no resources per shot; it is a rule of the mission, not an economy item.
- **Saves / versions [REQUIREMENT]:** a load restores the remaining kits, buildings under construction, finished buildings, the landing stages and the fact that fighters were delivered; it never repeats the landing and never grants a kit. The new version is a separate build (7.8); maps of started operations are never rebuilt in place.

## 10. Future directions **[DESIGN]** (none is current implementation, no empty subsystem is created now)

| Direction | Where it plugs in | Data it needs |
|---|---|---|
| Finite personnel | campaign save (F) + accepted result proposal (7.4, 7.7) | per-soldier record: id, type, status; plan picks from it |
| Wounds and repair | F + catalog prices | per-soldier status, repair price |
| Intelligence | B + C | an item that unlocks mission information (zones, spawn knowledge) |
| Transport fuel | B + E | fuel stock, cost per operation |
| Ammunition and supply | C (consumable counters, a handler) + B | stock per operation, ability charges (section 8) |
| Rescue and evacuation of property | adapter events + result proposal | list of property ids |
| Time-of-day and zone conditions | rule `condition` field (zone id, phase) | zones and phases defined by the adapter |
| Different abilities / compositions per mission | C (section 4, 8) | already part of the format |
| Settings panel for modders | launcher, reads the provenance view (6.3) | the settings format and its validator |

## 11. Design example (NOT a working config)

> **Illustrative only.** The keys `squad_rules`, `replace`, `protected`, `price` and the profile name below **do not exist** in `tools/build.py`; the build would refuse them as unknown (section 6.4). It shows how a future profile "first mission with flamethrowers" (a TRaynor01 variant: ordinary squad fighters are Firebats) would read. Whether the data (Firebat model, abilities) exists in the Liberation Day map is not checked. The role `garrison` used in the example is **not** present in TRaynor01 today: roles are assigned by an adapter (section 4), and only the TRaynor02 module assigns them; the example presupposes a TRaynor01 adapter that does. Raynor is `protected` by identity; a modder may still set his life, weapons or abilities explicitly (section 4).

```jsonc
// DESIGN EXAMPLE - not implemented, not accepted by the build
{
  "presets": {
    "flamethrowers": {
      "extends": "hard",                                   // existing mechanism
      "label": "Огнемётчики",
      "message": "Рядовые бойцы отряда - огнемётчики.",
      "overrides": {
        "squad_rules": {                                   // DESIGN key
          "replace": [
            { "id": "line_infantry",
              "match": { "role": "garrison", "source": "scenario", "original_type": "unit.marine" },
              "with":  { "type": "unit.firebat", "role": "garrison" } }
          ],
          "protected": ["story.raynor"],                   // never matched by a rule
          "handler": null                                  // a mission handler id when the scenario needs one
        }
      }
    }
  }
}
```

## 12. Open questions and checks (collected)

Decided by the Owner (no longer open): the **right to make a mistake** (1, 7.5): free manual save and load inside an operation, loading never punished, no mandatory ironman, no limit on attempts. This is not a question and nothing below reopens it.

Owner decisions **[OPEN - Owner decision]**:
0. (2026-10-21) TRaynor03 new design (9.3): whether the first six landing marines belong to the paid order; new prices / limits; fate of unspent kits. Other open points of the new design: `docs/MISSION_ROADMAP.md` 7.7.8.
1. Price of a turret kit; final prices and number of mercenaries (not agreed, none invented).
2. Method and moment of mercenary delivery.
3. Preparation cost refund when the operation is cancelled before it starts, treatment of defeat / abandonment, and what happens to the handed stock when an operation is abandoned (7.1, 7.2).
4. Replay and rollback policy **after a result was accepted or after later missions** (section 7.3). It does not concern ordinary saves and loads inside an unfinished operation; no irreversible mode without a decision.
5. What the TRaynor02 start stock is (original start or part of the campaign stock).
6. Profile name and form for the THanson01 economy variant (lock lifted for turrets; fate of the 15 pre-placed turrets).
7. Which proposal counts when one attempt produced several (victory, then a load of an earlier save and a second victory in one session); requirement: at most one is accepted per operation (7.7).
8. Keeping and cleaning of immutable operation sets and the saves that depend on them (7.8).
9. A complete ban on training new soldiers in «Вне закона» was discussed and is **not** approved (9.1).

Technical checks **[OPEN - technical check]** (nothing assumed compatible; each is a technical step of its stage and needs no separate permission once the stage is assigned):
1. Map → launcher result channel (Bank from a production map, path, abnormal exit, no duplicates) - section 5, 7.7.
2. Reading player resources at the victory moment; distinguishing mined / found / spent.
3. Construction start / cancel / completion events for turrets and free construction without refunds in the way the rule needs.
4. Raynor portrait model for the TRaynor02 message.
5. Mercenary correspondences with the original; delivery options.
6. Catalog charges in 3.1.4; dynamic ability granting beyond enable / disable / show.
7. Operation set and file naming (7.8): the old proposal "the plan lives in the manifest, the map file stays keyed by mission + profile" is **withdrawn** as insufficient for saves. To check: how the immutable set is stored, how its map is named in `Maps\GhostOps`, whether a game save needs the same map file name, path or content, what the game does when that file is replaced or missing, and that the set leaves no unmanaged trail of files.
8. Saving methods (7.5): quick save, several named slots, autosave; compatibility of each with this design; whether the game gives maps an autosave of its own (`GameSaveCreate` is not authorized for our maps).
9. Completeness of the state restored by a load (7.6 B): every listed state (fighters and health, map resources, ammunition and kits, built and under-construction objects, missile and aiming, transport and passengers, stages of dialogues and landing, timers and objectives) is verified only for the cases named in section 2.
10. Attempt identity and freshness (5, 7.1, 7.7): where `attempt_id` is created, how a launch token or a cleared proposal slot proves that a proposal is not a leftover, how a load of a save of another attempt of the same operation becomes known to the launcher.
11. Atomic commit of the campaign save (7.7): the storage that gives the stock change and the "accepted" mark as one operation, and the recovery after a crash.

## 13. Next implementation stage (proposed; stages are assigned by the Owner)

The stages below are not started. A stage is launched by the Owner's assignment; the technical steps inside an assigned stage (checks, builds, tests) do not need a separate permission each. Documentation tasks do not start a stage.
1. **CE-0 technical verification** (no gameplay balance change): checks 1-3 above on TRaynor02 with a dev preset; add the save / load checks 7-9 and 10-11 (7.5 - 7.8); report only.
2. **CE-1 TRaynor02 remainder**: Raynor message, result proposal, launcher-side campaign save with attempts, the one-time atomic acceptance and the report; no purchases, no catalog.
3. **CE-2 THanson01**: only after the Owner's decisions 1-3 and 6: catalog entries for the turret kit and mercenaries, plan + validator, kit accounting, the new profile.
Config schema moves to the next `schema_version` only when CE-1 adds its first key.

## 14. CE-0 results and the decisions they force (2026-10-20)

Evidence: RESEARCH.md section "CE-0". Everything marked **[CE0-VERIFIED]** was measured by the dev probe (`core/GhostOpsCe0.galaxy`, presets `ce0_dev`), not by a playable profile.

### 14.1 What the real game showed
- **[CE0-VERIFIED] Load = the saved state, nothing else.** Ghost life / energy, Marines, resources, ammunition (nukes), scene stage, transport, kit counters, a pure game-state counter all return to the save; the aiming / flight / blast of TRaynor02 happen once after loads of three named saves of one attempt, no second missile, no new Ghosts, no false defeat; the Swann wait replays exactly one transport; THanson01 convoy command / trip states come back without a second convoy.
- **[CE0-VERIFIED] The Bank is part of the save.** A load restores the Bank to its saved state (rows written in the cancelled future disappear; the Bank's own counter repeats). Therefore: no Bank sequence number is an id or an order; a Bank record is evidence only of the timeline that is in the file now. This realises 7.6 B ("nothing outside the save restores gameplay") and 7.7 ("deaths of a cancelled future are not kept") for the Bank channel.
- **[CE0-VERIFIED] The Bank file must only be READ by the launcher** (an external edit makes the game's bank empty). The launcher -> map direction through a Bank is not usable (signature). The plan therefore reaches the map only by build-time embedding (5, step 1).
- **[CE0-VERIFIED] Normal exit and a killed process keep the last written record.** A fresh process / in-game restart starts with an empty bank (the old file is replaced at the first write, about 2 s after the start).
- **[CE0-VERIFIED] Identity.** The attempt id is a saved global made by `RandomInt` at a fresh start (different on every launch); a load brings back the SAVED id also in a new process (the new process's own START row disappears with the restored bank); a full restart makes a new id. `RandomInt` after a load is deterministic.
- **[CE0-VERIFIED] A save names the map by its relative path under `Maps`** (and the Liberty mods). File present: loads; same path with different content: loads and keeps the save's own script; file missing / other file name / other folder: "cannot open map". `-run <save>` does not open a save; loading from the SC2 main menu needs the Owner's login and was **not** tried **[OPEN - technical check]**.
- **[CE0-VERIFIED] Resources.** `c_playerPropMineralsCollected` / `...VespeneCollected` = mined only; script grants are not counted; spending has no native counter; the victory hook reads the resources before the standard victory sequence. TRaynor02's own resource pallets (`PickupMinerals100` / `PickupGas100`) are the "found" source and can be counted by an ability event.
- **[CE0-VERIFIED] Kits (THanson01 probe).** Construction events: `Created` (creator `TerranBuild`) at placement, progress `Start` / `Complete` / `Cancel` (event unit = SCV, `EventUnitProgressUnit` = structure); the player's own cancel gives `Cancel` first, destroying an unfinished structure gives the death first; killing a finished turret returns nothing; catalog cost can be set to 0 at run time and `TechTreeUnitAllow` refuses the next order when no kit is free.

### 14.2 Decisions (requirements for CE-1, replacing the open items they answer)
1. **Attempt id** is created by the MAP at a fresh start (saved global). The launcher records its own **launch intent** (`fresh` or `continue`) per launch; the active attempt of a run is the attempt in the LAST journal rows of the final bank file; a fresh run whose bank shows a new attempt while an older attempt of the operation was live = a full restart (the older one becomes `abandoned`), unless the launch intent was `continue`. Closing the game never abandons.
2. **Freshness.** The launcher reads the result Bank only after the game process exited (or read-only while it runs). A proposal is fresh when the Bank file's modification time is not older than the launch of that process and its journal belongs to a known attempt of the operation. Stale files of earlier launches are replaced by the new process at its first write; the launcher archives (moves) the old file before every launch it starts. A Bank sequence number is never used.
3. **`result_id`** = attempt id + a random number made when the proposal is written (deterministic after a load, so the same result of the same state gets the same id and is accepted at most once).
4. **Immutable operation set** (7.8): a map file with its own UNIQUE name `GhostOps_<Mission>_<operation_id>.SC2Map` under `Maps\GhostOps`, never overwritten by a later build, plus a manifest with sha256 of the map, the resolved settings and the order. Keeping / cleaning: an Owner decision; nothing is deleted automatically. Standalone tests of a mission use the normal `mission + profile` file and a separate test budget that is never written into the campaign.
5. **Resource report**: start stock, mined (native), found (counted at the pallet pickup hook), net of other changes (start + mined + found - remainder; it contains spending and any grant that is not counted; the exact spending is not measured), remainder. Nothing is invented.

### 14.3 First sequence (Owner, 2026-10-20)
TRaynor02 -> accepted remainder -> TRaynor03 preparation -> launch. THanson01 stays the following, separate stage; its preparation cost 1000 minerals / 500 gas belongs to THanson01 and is NOT transferred to TRaynor03. TRaynor03 has no separate preparation fee in the first prototype: the cost of the chosen order is charged once. Its prices and limits are EXPERIMENTAL numbers in the config (MISSION_ROADMAP.md section 7.3 and the report), not Owner-approved values.

### 14.4 Implementation status after CE-1 (2026-10-20; updated at the end of the work)
| piece | status |
|---|---|
| Map journal `core/GhostOpsCampaign.galaxy` (attempt id, START / LOADED / RESULT proposal, found pallets, resources read before the victory sequence) | **[IMPL]** in TRaynor02 `tactical` and TRaynor03 `standard`; **[CE0-VERIFIED]** in real runs through the dev presets: START row, RESULT row with start / mined / remainder, written once |
| Launcher state `tools/campaign.py` (one atomic commit of stock + accepted mark, pay once, accept once, abandoned attempts, stale Bank file) | **[IMPL]**; proven by fault-injection unit tests (crash before write / half written / before replace / after replace) |
| Flow `tools/campaign_flow.py` + window `tools/gui_campaign.py` (order form, quote with shortage, unique operation set, result confirmation) | **[IMPL]**; flow by unit tests with a fake backend; the window was rendered with a fake backend (screenshots); the real chain (dev preset, same modules) was run in the real game with the real flow: TRaynor02 victory proposal 325 minerals accepted once, a second acceptance refused, a TRaynor03 order of 320 charged once, its unique map built and started, `continue` kept the set and charged nothing (`tools/ce0_campaign_e2e.py`); a click on the real window was NOT done |
| Unique map file per operation, immutable (`build.py --plan`, `prepare_existing`) | **[IMPL]**; built and started in the real game (plan with a changed order: the order was applied) |
| Loading a save of a paid operation continues the same attempt without a second charge | design **[CE0-VERIFIED]** for the attempt identity (saved global); the launcher side (`intent continue`) by unit tests |
| Loading from the SC2 main menu, `Maps` path of a deleted set, quick save / autosave | **[OPEN - technical check]** (needs the Owner's login / not tried) |
| Result of an operation accepted twice, replay income, rollback of the campaign | **[OPEN - Owner decision]** (7.3); the code refuses a second acceptance and gives no replay income |
| An unconfirmed victory proposal blocks every new launch (the Bank file is never archived with a pending result) | **[IMPL]** `CampaignFlow._launch`; unit test |
