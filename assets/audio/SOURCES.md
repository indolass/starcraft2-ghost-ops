# Audio clips of the maps (copies from the voice lab, read only source)

The clips are final results of `D:\AI-workspaces\games\starcraft2-ghost-ops-voice-lab` (a separate project; it is only read). Each is a whole original
Blizzard line of the ruRU client cut at silence, no TTS, no cloning. Texts are **ASR (Whisper large-v3), not checked by a human**; nobody has listened to
the files yet (quality, tone and volume are for the Owner). The WAV files are Blizzard voice lines, so they are kept LOCALLY ONLY and are git-ignored (`assets/audio/**/*.wav`); this file with the hashes is the manifest that
recreates them from the voice lab; the build imports them into the
modified map (`Assets\Sounds\GhostOps\<name>.wav`) and defines a `CSound` for each (config key `audio.clips`). The originals are not published.

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
