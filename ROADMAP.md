# Ghost Ops roadmap

Status legend: DONE = verified, ACTIVE = being worked on, PLANNED = not started. Nothing marked
PLANNED exists yet. Principle: **game first** - get a controllable operative into an original
mission quickly, with correct code boundaries.

| Stage | Name | Status |
|---|---|---|
| F0 | Foundation | DONE (local commit, not published) |
| P0 | PoC 0.0.1 | OWNER-TESTED on TRaynor02; damage multiplier value, save/load and victory not yet confirmed |
| P0.1 | Operative squad (Nova + 2 Ghosts), hold fire | OWNER-CONFIRMED on TRaynor02 (squad, abilities, cloak incl. Crius Suit, hold fire, garrison works) |
| P1 | Second mission | ACTIVE (Smash and Grab built and installed, awaiting Owner game test) |
| M1 | Playable MVP 0.1 | PLANNED |
| A2 | Tactical Abilities | PLANNED |
| A3 | Multi-Mission Alpha | PLANNED |
| B4 | Custom Operations | PLANNED |
| R1 | Open Platform 1.0 | PLANNED |

## F0 Foundation
Single project folder and one git repository; Core / Adapter / Config / Build layout; MIT code
licence with an explicit Blizzard exclusion; reproducible build tool; research notes.
**Done when:** unit tests pass; the build refuses a source map it cannot patch safely; the
original SC2 install is never written except `Maps/GhostOps`; install is reversible.

## P0 PoC 0.0.1
Mission *The Outlaws* (`TRaynor02`) only. One Nova is created after the intro and **added** to the
existing army (no unit replaced or retyped). Nova is vulnerable and unbuffed. **BaseSupport**
(Owner decision 2026-10-19, replaces the invulnerable-army model): regular non-structure units of
the player deal x1 / x2 / x3 damage (config `base_support.damage_multiplier`, default 3) through
Blizzard's behaviors `DamageDealtDouble` / `DamageDealtMega`; they stay vulnerable and enemies keep
attacking them. Enemies, neutrals and operatives get no bonus. Invulnerability remains only as an
experimental option (`experimental.invulnerable_allies`, off, never combined with a multiplier).
Waves, timers and victory are the original ones. No nukes, no menu, no extra operatives.
**Done when (Owner acceptance):** the map starts directly from `Maps/GhostOps`; Nova appears after
the intro and is controllable; her standard model and abilities work; regular units visibly hit
harder, take damage, and enemy waves keep attacking them; resource pickups work again; the Dominion base can be destroyed; the standard
victory fires; save and load work; x1 restores original damage.

## P0.1 Operative squad
Config `operatives.squad` (1..6 of `Nova`/`Ghost`, default Nova + 2 Ghosts), all registered in the
SquadManager before BaseSupport (no army bonus). Standard Ghosts get Blizzard's upgrades
`PersonalCloaking` (required by `GhostCloak`) and, with `ghost_permanent_cloak`, `PermanentCloakGhost`
(Crius Suit: free cloak); both are player level, so any other Ghost of player 1 is affected too.
`ghost_start_cloaked` cloaks the Ghosts after 0.5 s; `start_hold_fire` issues `GhostHoldFire` to all.
Nova gets `GhostHoldFire` / `GhostWeaponsFree` through a minimal map data override (explicit
`AbilArray` indices 7-8, `LayoutButtons` 12-13 at row 1, columns 2-3), nothing else changed.
**Done when (Owner acceptance):** cloak and hold fire work for all three; Ghosts and Nova take normal damage and deal normal damage; the army still gets x3; Smash and Grab passes the same checks with real detectors (photon cannons).

## P1 Second mission
*Smash and Grab* (`TTychus01`) is the first P1 mission (adapter `adapters/ttychus01`, own config);
Liberation Day and Zero Hour follow. Core must not need mission-specific changes.
**Done when:** each mission passes the same checklist as P0 and the Core diff is only generic.

Possible next `TTychus01` adapter task (not started, needs Owner go-ahead after the playtest): an
optional setting **"no artifact race"**. On high difficulty the Zerg can take the artifact before the
player has explored the map. The setting must remove the forced rush while keeping the chosen
difficulty, the Zerg-Protoss war and the standard detectors, and must not break artifact pickup or
the victory scenario.

## M1 Playable MVP 0.1
Operative count, protection on/off and a minimal menu, all driven by the configuration format.
**Done when:** settings persist between missions and are covered by tests.

## A2 Tactical Abilities
Nova and Zeratul abilities, nuclear arsenal, detector visibility, wave rules, drop/extraction
points. **Done when:** each ability has a documented rule and an in-game check.

## A3 Multi-Mission Alpha
Most Wings of Liberty missions have adapters. **Done when:** the campaign can be played start to finish.

## B4 Custom Operations
New objectives and mission types on top of the original maps. **Done when:** one new operation
type is playable end to end.

## R1 Open Platform 1.0
Documented adapter and configuration API, release packaging, contribution guide.
**Done when:** a third party can add a mission adapter from the documentation alone.
