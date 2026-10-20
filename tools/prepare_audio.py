r"""Prepare the voice clips of the maps from YOUR installed StarCraft II (no clip is published with the repository).

  python tools/prepare_audio.py                 # every clip of assets/audio/clips.json that is missing
  python tools/prepare_audio.py --check         # only report which files are present / missing / different from the recorded hash
  python tools/prepare_audio.py --only traynor03/horner_intro [--force]
  python tools/prepare_audio.py --game-dir "D:\Games\StarCraft II" --casc tmp\thirdparty\casc.dll

What it does for each recipe: reads the original Russian .ogg line from the game's CASC storage (read only), cuts the listed interval, applies a 3 ms fade-in and a 15 ms fade-out
(click guard), keeps the original level (no normalisation, no denoise, no synthesis) and writes a 16-bit WAV to assets/audio/<dir>/<name>.wav. The recipes (source path, interval,
ASR text, hash of the file the author used) are in assets/audio/clips.json. A different decoder may give a file that differs in a few bits: that is reported as "hash differs" and is not an error.

Needs: the game (ruRU speech installed), the CascLib DLL (the same one tools/extract_map.py uses, see docs/EXTRACT_MAP.md) and the packages of requirements-audio.txt
(pip install -r requirements-audio.txt --target tmp\thirdparty\audio). Nothing of the author's private lab is needed. Without the clips build with --no-voice (maps without added voice).
"""
import argparse
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tmp', 'thirdparty', 'audio'))
MANIFEST = os.path.join(ROOT, 'assets', 'audio', 'clips.json')


def load_manifest():
    with open(MANIFEST, encoding='utf-8') as f:
        return json.load(f)['clips']


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def status(clip):
    path = os.path.join(ROOT, *clip['file'].split('/'))
    if not os.path.isfile(path):
        return 'missing', path
    if clip.get('sha256') and sha(path) != clip['sha256']:
        return 'hash differs', path
    return 'ok', path


def missing_files(paths):
    """For build.py: which of these project-relative WAV paths are absent (used to explain how to prepare them)."""
    return [p for p in paths if not os.path.isfile(os.path.join(ROOT, *p.split('/')))]


def make_clip(clip, api, store):
    import numpy as np
    import soundfile as sf
    import casc_read
    data = casc_read.read_file(api, store, clip['casc_path'])
    audio, rate = sf.read(io.BytesIO(data), dtype='float32', always_2d=True)
    iv = clip.get('interval_s')
    a, b = (0, len(audio)) if not iv else (int(round(iv[0] * rate)), min(len(audio), int(round(iv[1] * rate))))
    cut = audio[a:b].copy()
    fi, fo = int(rate * clip.get('fade_in_ms', 3) / 1000), int(rate * clip.get('fade_out_ms', 15) / 1000)
    if fi:
        cut[:fi] *= np.linspace(0.0, 1.0, fi, dtype='float32')[:, None]
    if fo:
        cut[-fo:] *= np.linspace(1.0, 0.0, fo, dtype='float32')[:, None]
    path = os.path.join(ROOT, *clip['file'].split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, cut if cut.shape[1] > 1 else cut[:, 0], rate, subtype='PCM_16')
    return path, len(cut) / rate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game-dir', default=os.environ.get('GHOSTOPS_SC2_DIR', r'E:\Games\StarCraft II'), help='the StarCraft II folder (default: GHOSTOPS_SC2_DIR or E:\\Games\\StarCraft II)')
    ap.add_argument('--casc', default=os.path.join(ROOT, 'tmp', 'thirdparty', 'casc.dll'))
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--force', action='store_true', help='rewrite files that already exist')
    ap.add_argument('--only', action='append', help='a clip file stem such as traynor03/horner_intro (repeatable)')
    a = ap.parse_args(argv)
    clips = load_manifest()
    if a.only:
        clips = [c for c in clips if any(c['file'].endswith('/%s.wav' % o) or c['file'] == o for o in a.only)]
        if not clips:
            print('no clip matches --only')
            return 2
    todo = []
    for c in clips:
        st, path = status(c)
        print('%-14s %s' % (st, c['file']))
        if a.force or st == 'missing':
            todo.append(c)
    if a.check or not todo:
        return 0 if not [c for c in clips if status(c)[0] == 'missing'] else 1
    try:
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        print('\nMissing Python packages. Install them with:\n  pip install -r requirements-audio.txt --target tmp\\thirdparty\\audio')
        return 3
    if not os.path.isfile(a.casc):
        print('\nCascLib DLL not found: %s\nBuild it once as described in docs/EXTRACT_MAP.md (the same DLL is used to extract the original maps), or pass --casc.' % a.casc)
        return 3
    import casc_read
    try:
        api, store = casc_read.open_lib(a.casc, a.game_dir)
    except SystemExit as e:
        print('\nCannot open the game storage %s (%s). Pass --game-dir with your StarCraft II folder.' % (a.game_dir, e))
        return 3
    rc = 0
    try:
        for c in todo:
            try:
                path, dur = make_clip(c, api, store)
            except Exception as e:  # noqa: BLE001 - report every clip, keep going
                print('FAILED %s: %s' % (c['file'], e))
                rc = 4
                continue
            same = (not c.get('sha256')) or sha(path) == c['sha256']
            print('wrote %s (%.2f s)%s' % (c['file'], dur, '' if same else '  [hash differs from the author file: decoder / rounding, not an error]'))
    finally:
        api['close_store'](store)
    return rc


if __name__ == '__main__':
    sys.exit(main())
