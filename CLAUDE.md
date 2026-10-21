# StarCraft II: Ghost Ops - rules for sessions

## Automatic test launches of StarCraft II (Owner rule, 2026-10-19)

Use `python tools/test_launch.py --mission M --preset P --seconds N [--keep] [--shot FILE --shot-at S]`
(helpers: `tools/monitors.py`, `tools/mute_process.ps1`). Do not start the game for tests any other way.

1. The test game runs in a small ordinary window (start size 1024x768, `-displaymode 0 -windowwidth/-windowheight/-windowx/-windowy`)
   on the SECOND monitor. Monitors, work areas and scaling are read from Windows every time (the second monitor may be left of the
   primary one and have negative coordinates; never hard code X=1920). No second monitor: a small window on the available screen,
   and say so in the report.
2. The window is placed by the launch parameters; `SetWindowPos` with `SWP_NOACTIVATE` only corrects it if needed. No Always on Top,
   no repeated focus forcing, no activation of the window without a concrete need.
3. Sound is off: only the audio sessions of OUR process are muted (`mute_process.ps1`, checked: `sessions=1 confirmed=1`). The Windows
   master volume, other applications and the Owner's game settings are never touched. The normal GUI / CLI launch keeps sound and the
   normal window (`launch_command` has no test parameters).
4. Only the process started by the test launch is controlled (new `SC2_x64.exe` PID, window ownership checked). If a game is already
   running, the test launch is refused: the Owner's game is never moved, minimised, muted or closed.
5. The Owner's permanent settings (Variables.txt, graphics, volume) are not changed; everything is a parameter of one launch.
6. Screenshots of the test window: `python tools/sc2_ui.py PID shot FILE` (PrintWindow of OUR window only; works while other windows
   cover it; never grab the screen area, a DPI-unaware process captures the wrong monitor). Keys and clicks into the test game
   (`sc2_ui.py PID key ...`, posted window messages, no focus change) and any size other than 1024x768 must be announced to the Owner before
   such a launch. Saves made by such tests (`GHOSTOPS_TEST_*.SC2Save`) are deleted afterwards; the mute loop must run for the whole life of a
   kept game (`mute_process.ps1 -Seconds N`).
7. Do not claim "no focus stealing" unless a real launch has confirmed it.
8. Developer presets (`*_dev`) put test units (enemy Barracks and the like) on the map: their `.SC2Map` must never stay in
   `Maps\GhostOps` (the Owner saw such Barracks once). `test_launch.py` uninstalls them after the run; with `--keep` do it yourself
   (`python tools/build.py uninstall --mission M --preset P_dev`).

## Project

- One repo, branch `main`; no commit / push / publication without a separate explicit permission of the Owner.
- Galaxy sources stay ASCII; visible texts go through the string table (`StringExternal`, `config/*.json` texts).
- After any real launch read the matching new `Documents\StarCraft II\GameLogs\<time> ScriptError.txt`; the campaign-init
  "not authorized" lines are known noise of launches from the Maps folder, a compile error is not.
- The dev-only preset `tactical_dev` (TRaynor02) writes `Documents\StarCraft II\Banks\GhostOpsDevTac.SC2Bank` and can script the nuclear
  strike test (`tactical.autotest.mode`); it is hidden from the GUI and never part of a playable build.

## Campaign, saves and probes (Owner rules, 2026-10-20)

- The campaign state (`%APPDATA%\GhostOps\campaign.json`) and the Owner's saves / Banks are never filled with test data: tests and probes use their own files (`GHOSTOPS_CAMPAIGN_FILE`, `GHOSTOPS_BANK_DIR`,
  saves named `CE0_*` that are deleted afterwards). A test budget of a standalone map test is never written into the campaign.
- `tools/ce0_session.py stop` uninstalls the preset's map: use `--keep-map` for any map that is not a hidden dev map. The CE-0 probe (`ce0` key) exists only in hidden `*_dev` presets.
- A started operation's map file is immutable (unique name per operation); do not rebuild over it and do not delete it while a save may depend on it.
- Game voice WAVs stay local (git-ignored); only the manifest `assets/audio/SOURCES.md` and the recipes `assets/audio/clips.json` are published (`python tools/prepare_audio.py` recreates the clips from the installed game; `--no-voice` builds without added voice, the map file gets `_novoice`; a test copy of it is never left in `Maps\GhostOps`). No commit of the voice lab tree, installs, CASC data, original maps, saves or Banks.
- Documentation separates: implemented and confirmed / agreed / architectural requirement / open question / technical check. Experimental numbers (prices, limits, waves) are never called Owner-approved.
- Seventh task: maps changed after a started playthrough get a new file name (`GhostOps_<Mission>_r2_<profile>.SC2Map`, `output_map_file` in the adapter); the old-named maps are never overwritten (a save is bound to the map path). Rebuild old ones from the commit that built them if they were touched by mistake.
- Test-launch guard (Owner, 2026-10-21, after a full screen test game): `build.start_detached` is the ONLY function that starts a game process; without `owner=True` (or with the env var `GHOSTOPS_TEST`, which every test tool sets by importing `test_launch`, also when it drives the GUI) it calls `test_launch.launch_test_game`: window 1024x768 (`-displaymode 0`), second monitor if present (primary otherwise), our process muted, never raised / topmost, and the real window (not maximised, not full screen, size, inside the work area) is verified - a non-compliant test window is closed (our pid only). Ad-hoc scripts must not call `build._raw_start` or `SC2Switcher` themselves (`tests/test_launcher.py::TestGameLaunchGuard`). The Owner's normal GUI / CLI launch (`owner=True`, no test env) stays unchanged.

## Galaxy / build traps found with the defence profile (2026-10-21)

- A very long single-statement string concatenation or a huge command function gives an unlocatable "Script load failed: syntax error": split the statement / the function (`tools/last_script_error.py` prints the compile and load lines).
- An ability that targets a structure (turret) needs `<Arc value="360"/>`, otherwise the order is invalid.
- `AIAttackWaveSend(..., wait=true)` BLOCKS the thread until the wave is over; the attack sources run as parallel threads: shared buffers must be emptied before the send.
- The original starts the AI in the intro, before the mission start hooks: a mode flag the wave hooks test must be set by a hook before `TriggerExecute(gt_StartAI` (see `build.apply_ce0`).
- A destroyed unfinished construction and a cancelled one look the same to the script after the unit is gone; the defence kit rule tells them apart by a drop of life (4 s) or an enemy within 6.

## Owner versions, development and waiting for a free game (2026-10-21)

- The Owner plays the INSTALLED map files. A protected map (`build/owner_maps.json`: `python tools/isolation.py status`; every map the Owner's normal launch started is registered automatically) is never rebuilt, replaced, uninstalled or renamed - `build.py` refuses (CLI, launcher and campaign window all go through it), and `prepare()` starts it as it is. Development goes under its OWN hidden preset name (`defence_next`, `defence_next_dev`, ... ending in `_dev` when it has the probe) and gets its own map file; `python tools/isolation.py protect-all` registers the installed maps once. Do not edit the config of a preset the Owner plays (`defence`): copy the change into the `*_next` preset. No second worktree is needed for this.
- In-game tests never wait inside the conversation: put a prepared, bounded scenario into the queue (`python tools/test_queue.py enqueue --label L --mission M --preset P_dev -- python tools/ce0_steps.py tests/scenarios/X.json`), then do the work that needs no game. The detached runner waits while ANY SC2 process exists (5 s checks, nothing closed or changed), waits 10 s after it disappears, re-checks before the launch and runs the jobs one by one through the test-launch guard. `status`, `cancel [JOB|--all]`, `stop` / `go`, `resume JOB` (an interrupted job is never restarted automatically). The queue closes only a test game whose pid AND creation time it recorded; never kill an SC2 process by name. Pending checks are reported as pending, never as done.
- A test must not touch the Owner's data: jobs use their own campaign file / bank directory / session state (`GHOSTOPS_*` variables set by the runner); probes write only the `GhostOpsDev*` Banks; saves are `CE0_*` and are deleted afterwards.
