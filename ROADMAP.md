# Ghost Ops roadmap

Status legend: DONE = verified, ACTIVE = being worked on, PLANNED = not started. Nothing marked
PLANNED exists yet. Principle: **game first** - get a controllable operative into an original
mission quickly, with correct code boundaries.

**Main path (Owner decision 2026-10-19): Campaign Adaptation.** We are building an alternative story
playthrough of the whole original *Wings of Liberty* campaign (all 29 missions, including the
alternative branches) by a small tactical squad - not a set of technical demos. Core, P0.x and P1
below are the finished or running foundation of that path; the stages after P1 are re-read through
it. See "Campaign Adaptation" below.

| Stage | Name | Status |
|---|---|---|
| F0 | Foundation | DONE (local commit, not published) |
| P0 | PoC 0.0.1 | OWNER-TESTED on TRaynor02; damage multiplier value, save/load and victory not yet confirmed |
| P0.1 | Operative squad (Nova + 2 Ghosts), hold fire | OWNER-CONFIRMED on TRaynor02 (squad, abilities, cloak incl. Crius Suit, hold fire, garrison works) |
| P0.2 | Squad of 5 (+2 Medics), Hard difficulty check | BUILT and installed, awaiting Owner game test |
| P1 | Second mission | ACTIVE (Smash and Grab: squad confirmed by smoke only; Owner playtest pending; `no_rush` proposed, not implemented) |
| M1 | Playable MVP 0.1 | PLANNED |
| A2 | Tactical Abilities | PLANNED |
| CA | Campaign Adaptation (29 missions, mission by mission) | MAIN PATH; first mission TRaynor01: candidate ready for the Owner's game check |
| A3 | Multi-Mission Alpha | superseded by CA |
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

## P0.2 Squad of five and Hard
`operatives.squad` default is now Nova, 2 Ghosts and 2 Medics (config `schema_version` 4). Medics keep
Blizzard's stats and abilities (`heal` autocast on by default, `Flare`); they get no cloak, no hold
fire and no ghost upgrades, but are registered in the SquadManager (no army bonus). They stand in a
second row 2.5 south of the fighters. `difficulty.expected` (3 = Hard) and `difficulty.show_message`:
at mission start a subtitle prints the real `PlayerDifficulty(1)` (repeated every 10 s for a minute).
`build.py launch` prints `-difficulty 3`; whether the 3.1.4 switcher honours it is **not yet
confirmed** - the in-game message is the proof. Enemy stats are never scaled.
**Done when (Owner acceptance):** medics heal operatives, squad of five works on both maps, the
message shows 3 on Hard.

## P1 Second mission
*Smash and Grab* (`TTychus01`) is the first P1 mission (adapter `adapters/ttychus01`, own config);
Liberation Day and Zero Hour follow. Core must not need mission-specific changes.
**Done when:** each mission passes the same checklist as P0 and the Core diff is only generic.

Possible next `TTychus01` adapter task (not started, needs Owner go-ahead after the playtest): an
optional setting **"no artifact race"**. On high difficulty the Zerg can take the artifact before the
player has explored the map. The setting must remove the forced rush while keeping the chosen
difficulty, the Zerg-Protoss war and the standard detectors, and must not break artifact pickup or
the victory scenario.

## CA Campaign Adaptation (main path)
Goal: a complete alternative story playthrough of the original campaign by a small squad, keeping
Blizzard's maps, dialogues, cinematics, staged events, enemies and atmosphere. The campaign's real
structure and branch points decide the order; we start with `TRaynor01` (Liberation Day) and go on
mission by mission. The current registry below lists the 32 installed map roots; the Owner's count is
29 missions including the alternative branches.

Standing requirements for every adapted mission:
1. Original maps, dialogues, cutscenes, scripted events, enemies and atmosphere are kept.
2. Standard group: Nova + 2 Ghosts + 2 Medics (exceptions for special heroes or a special player side are made in the adapter).
3. Campaign difficulty **Hard**, with really vulnerable operatives; no stat scaling of enemies or operatives.
4. Combat difficulty and time pressure are separate settings. For missions with forced haste there is a
   scenario-level *No Rush* solution (`MissionPressure`: `original` / `relaxed` / `no_rush`) that does not
   stop the enemy AI; every such change is explained to the Owner before it is made.
5. New capabilities built from existing WoL mechanics (ammunition, nuclear weapons, Blink and similar)
   are added gradually and only after a separate Owner decision.
6. Every map gets its own confirmation of technical compatibility, story compatibility and playability.
7. For the future: alternative ways to complete objectives without repeating the whole strategic part
   of a mission, while keeping its story events. Not designed yet.
8. Analysis, adaptation, build and in-game acceptance run strictly mission by mission; a mission is not
   started until the Owner has approved its specific adaptation, and the next one starts only after
   the Owner accepts the previous one.

**Done when (per mission):** the Owner has played it with the standard squad on Hard, confirmed the
three checks of requirement 6, saving/loading and the story victory and defeat work, and the mission is
marked ADAPTED in the registry. **Done when (campaign):** the whole campaign can be played start to
finish that way.

## M1 Playable MVP 0.1
Operative count, protection on/off and a minimal menu, all driven by the configuration format.
**Done when:** settings persist between missions and are covered by tests.

## A2 Tactical Abilities
Nova and Zeratul abilities, nuclear arsenal, detector visibility, wave rules, drop/extraction
points. **Done when:** each ability has a documented rule and an in-game check.

## A3 Multi-Mission Alpha (superseded by Campaign Adaptation)
Most Wings of Liberty missions have adapters. **Done when:** the campaign can be played start to finish.

## B4 Custom Operations
New objectives and mission types on top of the original maps. **Done when:** one new operation
type is playable end to end.

## R1 Open Platform 1.0
Documented adapter and configuration API, release packaging, contribution guide.
**Done when:** a third party can add a mission adapter from the documentation alone.

## Mission registry (campaign adaptation)

Owner decision 2026-10-19: adapt all Wings of Liberty missions one by one with a standard squad of
5 (Nova, 2 Ghosts, 2 Medics), campaign difficulty **Hard**, enemy and operatives unmodified, and
"hard combat, no mandatory rush" as two independent settings. The table is generated from a
read-only scan of the installed 3.1.4 campaign scripts (32 map roots: the Owner's 29 missions plus
the story hub, the tutorial and the Lost Viking arcade map; counting is the Owner's). Columns are
text-scan facts, not analysis: mission type, story heroes and AI specials are filled in when a map
is adapted. Planned order: TRaynor02, TTychus01 (done first), then TRaynor01, TRaynor03, the rest.

| Map ID | Mission | Player slots (script consts) | Own base (CommandCenter in script) | TimerStart calls | Detector types in script | Status / blockers |
|---|---|---|---|---|---|---|
| tarcade | Lost Viking | 4 | - | 4 | - | not analysed |
| thanson01 | The Evacuation | 1 | yes | 1 | - | not analysed |
| thanson02 | Outbreak | 7 | yes | 8 | - | not analysed |
| thanson03a | Safe Haven | 7 | - | 5 | cannon | not analysed |
| thanson03b | Haven's Fall | 8 | - | 10 | - | not analysed |
| thorner01 | The Great Train Robbery | 7 | - | 2 | turret | not analysed |
| thorner02 | Cutthroat | 9 | yes | 0 | turret | not analysed |
| thorner03 | Engine of Destruction | 9 | yes | 1 | turret | not analysed |
| thorner04 | Media Blitz | 8 | yes | 6 | turret | not analysed |
| thorner05s | Piercing the Shroud | 13 | - | 0 | - | not analysed |
| traynor01 | Liberation Day | ? | - | 0 | - | CANDIDATE with three Ghost Ops variants (config/traynor01.json; double-click `GhostOps_Launcher.pyw`, console fallback `GhostOps_TRaynor01.cmd`). **easy**: Owner considers it playable at the easy level. **hard**: same as easy plus a 5 s per-Ghost Snipe cooldown; Owner: "сложно, но проходимо" (balance judgement only). **extreme** (experiment): hard with ONE Ghost, HP 45/45 and Snipe cooldown 10 s; built, verified and installed, NOT yet played. Balance tuning of the first mission is closed on this set; the last change still needs an in-game confirmation. Game checks still OPEN from the previous iteration (not confirmed one by one): EMP / nuclear strike removed from the panel, Raynor 45/45 HP, no Medic on normal start and after skipping the intro, standard defeat when Raynor dies, marines 1/1 incl. reinforcements, Hard stays Blizzard Hard. New and OPEN: extreme in game (exactly one Ghost, 45/45, Snipe cooldown 10 s), all three profile builds start from the GUI, profile message at start, Snipe cooldown 5 s on the first Ghost only (second Ghost independent) |
| traynor02 | The Outlaws | 5 | yes | 1 | - | TACTICAL VARIANT built, installed, data/script tests done (see README); NOT yet played by the Owner. Real save/load checked in the game (before aiming, in flight, and during the story scene: waiting and transport on the way). Owner played it: interesting, easy at first then hard, camouflage is not always enough; completion not confirmed. Story scene (Adjutant alert, Swann, transport with the two Ghosts) and Marines without weapon added 2026-10-19. Enemy production is the original's (our stop logic removed 2026-10-19). Previous prototype kept (`--preset prototype`). Open in game: the whole run (zone border feel, garrison defence without camera returns, rescue -> hook, victory scene, save/load of roles and missile state, real-route retreat after the launch) |
| traynor03 | Zero Hour | ? | - | 13 | turret | not analysed |
| tstory01 | Wings of Liberty (story hub, not a mission) | 1 | - | 11 | - | excluded (not a mission) |
| ttosh01 | The Devil's Playground | 6 | yes | 8 | - | not analysed |
| ttosh02 | Welcome to the Jungle | 5 | yes | 1 | cannon | not analysed |
| ttosh03a | Breakout | 11 | - | 3 | turret | not analysed |
| ttosh03b | Ghost of a Chance | 6 | - | 1 | turret | not analysed |
| ttutorial01 | StarCraft II Tutorial (not a mission) | 3 | yes | 2 | turret | excluded (not a mission) |
| ttychus01 | Smash and Grab | 7 | yes | 5 | cannon | ADAPTED, built (5 operatives), Owner test pending |
| ttychus02 | The Dig | 1 | - | 1 | cannon | not analysed |
| ttychus03 | The Moebius Factor | 8 | yes | 6 | - | not analysed |
| ttychus04 | Supernova | 7 | yes | 1 | cannon | not analysed |
| ttychus05 | Maw of the Void | 7 | yes | 6 | cannon | not analysed |
| tvalerian01 | Gates of Hell | 12 | yes | 7 | - | not analysed |
| tvalerian02a | Belly of the Beast | 4 | - | 2 | - | not analysed |
| tvalerian02b | Shatter the Sky | 11 | yes | 8 | - | not analysed |
| tvalerian03 | All In | 5 | yes | 4 | turret | not analysed |
| tzeratul01 | Whispers of Doom | 5 | - | 5 | - | not analysed |
| tzeratul02 | A Sinister Turn | 9 | - | 6 | cannon | not analysed |
| tzeratul03 | Echoes of the Future | 8 | - | 19 | cannon | not analysed |
| tzeratul04 | In Utter Darkness | 8 | - | 1 | cannon | not analysed |


2026-10-20: TRaynor02 pause before Swann is 15 mission seconds after the end of the Adjutant transmission; short voice clips (Adjutant, Swann, one Ghost line)
and the TRaynor01 wounded squad scene (Raynor + two Marines) are connected through the new audio import of the build. In game verified: order, intervals, one-time play,
compile clean, clip length read by the engine (a probe transmission lasted clip length + the usual 1 s). NOT verified: how the clips sound (test runs are muted); a
real save/load of the new stage 8 (Swann queued). Owner listens and decides on each clip.


2026-10-20: **THanson01 «Эвакуация», снайперское прикрытие** (profile `sniper`, experiment) built, installed and checked in the game by scripted runs: one Ghost (cloak
permanent, energy untouched), single-shot Snipe on ground / air / Ultralisk (and refusal of own, allied, mechanical and structure targets), cooldown, development lock,
SCV repair of a turret, allied Marine refill, the convoy command (waits 90+ s, one release per click, a real click on the button, repeated clicks ignored, several trips),
real save / load while waiting and during a trip, 3 late raids on 15 turrets. NOT checked: a full playthrough (50 colonists), the detector revealing the cloaked
Ghost (the Zerg are passive towards the player in the original, so a test could not provoke an attack), balance of the escort without the player's hands on it.
Real save / load of the new TRaynor02 stage 8 (Swann queued) and the transport trip: done, no repeated lines or ships, two Ghosts, one missile.
Future task (not started): portrait mouth animation while a clip plays (talking animation without exact articulation) for the voiced transmissions.


2026-10-22: **TRaynor02 v2 "Outlaws" (`tactical_next`)** pushed (708fb94): armor-piercing area strike (2 charges, G, area circle), nuke range 48 + mission-only damage profile, rebel labels, production-building victory; measured values and open checks in `docs/MISSION_ROADMAP.md` 6.1. **THanson01 "Evacuation" prepared detonations (`sniper_next`)**: design recorded in `docs/MISSION_ROADMAP.md` 8.1 / contract 9.2.1 / `docs/ARCHITECTURE.md` (two Ghosts, Snipe 250 / 2 s, fuel containers placed by Firebats and detonated by a Ghost shot, gas costs 100 per convoy / 25 per container, convoy by command); implementation follows. All numbers experimental, not Owner-approved.

2026-10-20: **CE - Campaign economy (documentation only, PLANNED, nothing built).** Design contract: `docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md`.
First experiment (Owner-agreed scope): TRaynor02 passes the remaining minerals / gas and a report (no purchases; one Raynor line after the virus message, text only);
THanson01 has a 1000 minerals + 500 gas preparation, turret kits (N ordered = N free builds, reserved at construction start) and mercenaries.
NOT agreed: turret kit price, mercenary prices, mercenary delivery. It does not fix the campaign order and does not cancel the agreed TRaynor03.
Also NOT agreed: a complete ban on training new soldiers in TRaynor02 (discussed only; the agreed scope above is unchanged).
Agreed principle (Owner, 2026-10-20), a requirement for the whole economy: **the right to make a mistake** - free manual save and load inside a mission, loading never costs money,
campaign losses, reward or equipment, losses of a cancelled future are not kept, no mandatory ironman, no limit on attempts. Save, load, full restart of the same paid operation and a new operation
are separate actions (contract 7.1, 7.5 - 7.8). Documentation only: nothing of it is built, and only the game-menu save is verified in a few cases. Open and NOT blocking ordinary saves:
the policy for loading an old mission after its result was accepted (practice / rollback).
Proposed queue (stages are assigned by the Owner; technical steps inside an assigned stage need no separate permission): CE-0 technical verification (result channel, resources at victory,
construction events, save / load completeness, saving methods, operation set naming), CE-1 TRaynor02 remainder and report, CE-2 THanson01 purchases after the Owner's price / delivery decisions.

2026-10-20 (later): **CE-0 DONE as a technical probe (NOT closed as a whole: loading a save from the SC2 main menu was never tried - it needs the Owner's login)** (hidden dev presets only; results in docs/RESEARCH.md "CE-0" and contract section 14): real saves / loads of TRaynor02 and THanson01, Bank behaviour, map set for saves, resource counters, turret kit events. The mission plan of the next stages is docs/MISSION_ROADMAP.md (TRaynor02 -> TRaynor03 preparation first; THanson01 later). Nothing of the probe is in a playable profile.

2026-10-21 (later): **TRaynor03 «Оборона и диверсии» (preset `defence`) implemented as an EXPERIMENT** (player-built kit bunkers / turrets, pod landing, manual ground salvo, wave weakening by marked incubator groups, Matt message with a short target reveal); separate map `GhostOps_TRaynor03_defence`, the previous *Zero Hour* untouched. Real-game checks and limits: `docs/MISSION_ROADMAP.md` 7.8. No full playthrough yet; numbers are not Owner-approved.

2026-10-20 (queue of docs/MISSION_ROADMAP.md): CE-0 DONE; **CE-1 implemented** (map journal, launcher-side campaign state with one atomic commit, campaign window of the launcher, unique per-operation
map files); **TRaynor03 «Час икс» built as an EXPERIMENT** (pre-ordered garrison, two Ghosts, two missiles, victory = 20 game minutes AND all marked hatcheries, production lock, post-timer waves); scenes of the first three
missions (portrait + text; clips exist only for the older short lines). Prices / limits / waves of TRaynor03 are experimental numbers, not Owner-approved. THanson01 economy (1000 / 500, turret kits, mercenaries)
stays the following, separate stage. Statuses and checks: docs/MISSION_ROADMAP.md "Фактическое состояние". (Remote: created and pushed on 2026-10-21, see the next entry.)

2026-10-21 (fifth task: remaining checks + publication): public repository https://github.com/indolass/starcraft2-ghost-ops created (no auto README), `main` pushed normally.
**TRaynor03 real defence** tested with a scripted player (marines in bunkers, original SCVs mine, extra SCVs repair, Ghosts away; no healing / invulnerability / removal of enemies / extra money / disabled waves):
the recommended 8/4/4/4 (1120) does NOT hold 20 minutes (the base falls at 12-18.6 min at garrison damage x4 / x8 / x12); 16/4/4/8 (1640) with garrison damage x8 held past the timer (1207.9 s; checked until 1321 s).
EXPERIMENTAL tuning (not Owner-approved): garrison damage 4 -> 8, recommended and default order 8/4/4/4 -> 16/4/4/8, test budget 1500 -> 1700. Waves after zero: created, move, reach the perimeter, no uncontrolled accumulation.
Campaign window passed with the REAL widgets and the REAL backend (shortage, accept once, pay once, continue and full restart without a second charge); TRaynor02 mining measured (~330 minerals per game minute with 8 SCVs, 12379 ore at the base);
TRaynor03 missiles: cancel, load with remaining ammo and a two-Ghost race checked (2 launches in total). Not verified: a full human playthrough of TRaynor03 and TRaynor02, main-menu loading, any sound by ear. TRaynor03 has no clips; candidates listed in docs/MISSION_ROADMAP.md.
Details: docs/MISSION_ROADMAP.md "Итог пятого задания".

2026-10-21 (sixth task: pre-playthrough corrections): TRaynor03 cloak fixed to the agreed permanent free cloak (regeneration 20/s, Snipe 10; measured in the game); seven short original lines of Raynor, Matt and the marines now
precede the explanatory texts of the TRaynor03 scenes (portrait with the talking animation stays; a wrong empty marine portrait was replaced); explicit voice-free build (`--no-voice`, launcher setting, `_novoice` map file), an explained
error for a missing clip and a reproducible local clip preparation (`tools/prepare_audio.py`, `assets/audio/clips.json`) tested on a clean copy of the checkout; README introduction rewritten to the current implementation; TRaynor03 balance fixed
at 16/4/4/8 (1640), garrison x8 until the Owner's review (no more automatic tuning). Full playability of TRaynor03 is NOT confirmed; sound was not heard by ear. Details: docs/MISSION_ROADMAP.md "Итог шестого задания".

2026-10-21 (documentation stage Z1, no code): **TRaynor03 «Час икс» redesign agreed and recorded** (`docs/MISSION_ROADMAP.md` 7.7, contract 9.3, ARCHITECTURE "TRaynor03 redesign"): defence + a small squad behind the enemy lines; limited paid bunkers / anti-air turrets / marines / repair SCVs built and placed by the player (no barracks, no training); landing of six marines about 15 game seconds after control starts, then the main group; two Ghosts (permanent cloak on the easy profile, limited cloak under consideration on the hard one); Snipe as in TRaynor02 r2; no grenade; manual one-shot ground salvo of the turrets (air fire kept, simultaneity to be checked); destroying incubators weakens / stops the waves of their base group (the original wave sources must be analysed first); Matt's message moment and victory (timer AND all marked incubators, no defeat at zero) kept. **Not implemented**; the previous build and its results stay as history and do not confirm the new balance. Open Owner decisions and technical checks are collected in MISSION_ROADMAP 7.7.8. Next stage (technical, not started): analysis of the wave sources and construction events, then a prototype of the salvo and the kit accounting, built as a separate map.
