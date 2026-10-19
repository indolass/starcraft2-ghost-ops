# Extracting an original map (automatic, read only)

The 3.1.4 install keeps campaign maps in CASC as loose component files
(`campaigns\liberty.sc2campaign\base.sc2maps\maps\campaign\<mission>.sc2map\*`).
`tools/extract_map.py` reads them with CascLib (MIT) and packs them with `tools/sc2mpq.py`.

CASCConsole (C# CascLib) cannot open this install (no `file-index` in the CDN config); the C++
CascLib can. One-time local build, everything stays in git-ignored `tmp/`:

1. `pip install --target tmp\thirdparty\zig ziglang==0.14.1` (local compiler, nothing global).
2. Download CascLib source at commit 2a280f5a231966dc5d1b534978dd9f9f04a374cd into
   `tmp\thirdparty\casclib-src`, compile the files listed in its `CMakeLists.txt` plus
   `src\DllMain.c` with `zig c++ -target x86_64-windows-gnu -shared -O2
   -DCASCLIB_NO_AUTO_LINK_LIBRARY -DCASCLIB_NODEBUG ... -lwininet -lws2_32 -o tmp\thirdparty\casc.dll`.
3. `python tools\extract_map.py --casc tmp\thirdparty\casc.dll --mission traynor02 --out tmp\source\TRaynor02.SC2Map`

Result for traynor02: 41 components (base, enUS and ruRU localisation kept), ~1.3 MB.

Result for ttychus01: 44 components, ~2 MB. Use `--mission ttychus01 --out tmp\source\TTychus01.SC2Map`.
