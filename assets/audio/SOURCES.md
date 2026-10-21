# Audio clips of the maps (copies from the voice lab, read only source)

The clips are whole original lines (or one cut sentence) of the ruRU client, no TTS, no cloning. Their recipes (path in the game's storage, interval, fades, ASR text, hash of the file
the author used) are in **`clips.json`** next to this file; `python tools/prepare_audio.py` recreates the files from the installed game (see README, "Voice"). Texts are **ASR (Whisper large-v3), not checked by a human**; nobody has listened to
the files yet (quality, tone and volume are for the Owner). The WAV files are Blizzard voice lines, so they are kept LOCALLY ONLY and are git-ignored (`assets/audio/**/*.wav`); the build imports them into the
modified map (`Assets\Sounds\GhostOps\<name>.wav`) and defines a `CSound` for each (config key `audio.clips`). The originals are not published. The "lab package" column below is the author's private working copy and is NOT needed to reproduce anything.

| our file | lab package / file | text (ASR) | length | sha256 (= lab manifest) | original |
|---|---|---|---|---|---|
| `traynor02/adjutant_alert.wav` | `exports/traynor02_intro_short_01/adjutant_alert.wav` | «Тревога.» | 0.70 s | 4b84f844…de7b16680 | start of `ttychus01adjutant00010` (Adjutant) |
| `traynor02/swann_B.wav` | `exports/traynor02_intro_short_01/swann_B.wav` | «Я решил, что помощь тебе не помешает.» | 2.46 s | c8589754…fc7a4ab | first sentence of `thanson03abriefingswann00003` (Swann), 0 joins |
| `traynor02/ghost_ready00.wav` | `exports/ghost_short_bank_01/01_ghost_ready00.wav` | «Призрак явился.» | 2.07 s | 90ee4733…025cb0 (full hash in the manifest) | `ghost_ready00` (ordinary Ghost) |
| `traynor01/raynor_A.wav` | `exports/traynor01_wounded_squad_01/raynor_A.wav` | «Войска готовы к бою?» | 1.45 s | 5706edf7…f7eb | second half of `tscene01raynor016` (Raynor) |
| `traynor01/marine_B.wav` | `exports/traynor01_wounded_squad_01/marine_B.wav` | «Высылайте подмогу!» | 1.95 s | a9aa48fe…d4fe2 | `marine_help00` (Marine unit) |
| `traynor01/marine_A.wav` | `exports/traynor01_wounded_squad_01/marine_A.wav` | «Доктора! Доктора!» | 1.00 s | afb49916…9a5 | `charambientmarine400004` (Marine, mission Char) |

Not used on purpose: the other Swann candidates (`swann_A`, `swann_C` has a join), the other 11 Ghost lines (the nuclear-strike line "Обозначаю цель" in particular),
the lab's `preview_*` files. Replacing a clip later = replace the file here (same name) or change its entry in `audio.clips` of the config; nothing else.

## TRaynor03 (added 2026-10-21): short whole lines before the explanatory texts

Rule: the short original sound with its own exact subtitle first, THEN the separate explanatory text of the scenario (the explanations are not rewritten to the clips). Portraits stay and use the talking animation.
No line is repeated right after the same line of the original conversation: the original plays one cut-off call and one rescued line per group; the scene uses the other clip of the pair.

| our file | recipe (`clips.json`) | text (ASR) | length | used in |
|---|---|---|---|---|
| `traynor03/raynor_hold.wav` | `traynor03briefingraynor00007` | «Дьявол. Нужно продержаться до прибытия наших.» | 3.62 s | Raynor after the intro |
| `traynor03/horner_intro.wav` | `traynor03horner00006` | «Командир, это Мэтт Хорнер. Держитесь, корабль на подходе.» | 4.12 s | Matt explains the two tasks |
| `traynor03/horner_wait.wav` | `traynor03horner00012` | «Карета подана. Есть кто живой?» | 2.44 s | Matt, the ship waits (after the timer) |
| `traynor03/marine_mayday.wav` | `traynor03marine500005` | «Срочно нужна помощь! Мы окружены! Кто-нибудь нас слышит?» | 4.51 s | the cut-off group's appeal (groups 1, 2) |
| `traynor03/marine_mayday_alt.wav` | `traynor03marine800001` | «На помощь! На помощь! Нас окружили зерги! Если можете, помогите!» | 5.43 s | the appeal (group 3, whose own line is the one above) |
| `traynor03/marine_rescue.wav` | `traynor03marine500016` | «Рады тебя видеть, Рейнар! Ждем приказаний!» | 2.69 s | the first rescue (groups 1, 2) |
| `traynor03/marine_rescue_alt.wav` | `traynor03marine700004` | «Я уже думал, нам конец.» | 1.88 s | the first rescue (group 3) |
| `traynor02/raynor_damn.wav` | - | «Какого...» (Raynor after the alarm; ASR, unchecked) | see `clips.json` | `ttychus01raynor00012`, recipe in `clips.json` | TRaynor02, Raynor scene after the Adjutant alarm |
| `traynor02/raynor_onward.wav` | - | «Идем дальше, парни.» (ASR, unchecked) | see `clips.json` | `ttychus03raynor00011`, recipe in `clips.json` | TRaynor02, rebel-rescue hint scene |

Hashes: see `clips.json` (the files produced by `prepare_audio.py` in a clean checkout were compared: byte-identical except `adjutant_alert.wav`, which differs in a few bits).

Seventh task: `clips.json` entries may carry `facial` (the original sound id inside the portrait's `.fxa`) and the config `audio.talk` lists silent lip-sync drivers (generated silent WAV, FacialAnim of an original line); no new Blizzard audio beyond the two rows above.
