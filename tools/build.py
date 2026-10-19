"""Ghost Ops build tool.

  python tools/build.py build     [--mission traynor02|ttychus01] [--multiplier 1|2|3] [--source MAP]
  python tools/build.py verify    [--mission ...]   re-check the built map against its source
  python tools/build.py install   [--mission ...]   copy the built map to <SC2>/Maps/GhostOps
  python tools/build.py uninstall [--mission ...]   roll back exactly what install created
  python tools/build.py launch    [--mission ...]   print the direct launch command

The source map is only ever read. Everything written stays inside this project, except the
install step, which writes one file (and, if needed, one folder) under <SC2>/Maps/GhostOps.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc2mpq  # noqa: E402
import galaxy_lint  # noqa: E402

SC2_DIR = os.environ.get('GHOSTOPS_SC2_DIR', r'E:\Games\StarCraft II')
BEGIN = '// ==== GHOSTOPS BEGIN (generated, do not edit) ===='
END = '// ==== GHOSTOPS END ===='
HOOK_TAG = ' // GHOSTOPS HOOK'
XML_BEGIN = '    <!-- GHOSTOPS BEGIN -->'
XML_END = '    <!-- GHOSTOPS END -->'
UNITDATA = 'Base.SC2Data' + chr(92) + 'GameData' + chr(92) + 'UnitData.xml'
SQUAD_TYPES = ('Nova', 'Ghost')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read(path, mode='rb'):
    with open(path, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()


def load_json(rel):
    return json.loads(read(os.path.join(ROOT, rel), 'r').lstrip('\ufeff'))


def validate_config(cfg):
    errs = []
    if cfg.get('schema_version') != 3:
        errs.append('schema_version must be 3')
    op = cfg.get('operatives', {})
    squad = op.get('squad')
    if not isinstance(squad, list) or not 1 <= len(squad) <= 6:
        errs.append('operatives.squad must be a list of 1..6 unit types')
    elif any(t not in SQUAD_TYPES for t in squad):
        errs.append('operatives.squad entries must be one of %s' % (SQUAD_TYPES,))
    for k in ('start_hold_fire', 'ghost_permanent_cloak', 'ghost_start_cloaked'):
        if not isinstance(op.get(k), bool):
            errs.append('operatives.%s must be boolean' % k)
    mult = cfg.get('base_support', {}).get('damage_multiplier')
    if mult not in (1, 2, 3) or isinstance(mult, bool):
        errs.append('base_support.damage_multiplier must be 1, 2 or 3')
    inv = cfg.get('experimental', {}).get('invulnerable_allies')
    if not isinstance(inv, bool):
        errs.append('experimental.invulnerable_allies must be boolean')
    elif inv and mult in (2, 3):
        errs.append('invulnerable_allies cannot be combined with a damage multiplier above 1')
    if cfg.get('nukes_granted', 0) != 0:
        errs.append('nukes_granted must be 0 in this version')
    return errs


def gen_config(cfg):
    op = cfg['operatives']
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    lines = ['// Generated from %s' % cfg['mission'],
             'void GhostOps_ApplyConfig () {',
             '    go_cfgSquadSize = %d;' % len(op['squad'])]
    for i, t in enumerate(op['squad']):
        lines.append('    go_cfgSquadType[%d] = "%s";' % (i, t))
    lines += ['    go_cfgStartHoldFire = %s;' % b(op['start_hold_fire']),
              '    go_cfgGhostPermanentCloak = %s;' % b(op['ghost_permanent_cloak']),
              '    go_cfgGhostStartCloaked = %s;' % b(op['ghost_start_cloaked']),
              '    go_cfgDamageMultiplier = %d;' % cfg['base_support']['damage_multiplier'],
              '    go_cfgInvulnerableAllies = %s;' % b(cfg['experimental']['invulnerable_allies']),
              '}', '']
    return chr(10).join(lines)


def patch_script(text, adapter, block):
    """Pure function: returns patched MapScript text or raises ValueError."""
    if BEGIN in text:
        raise ValueError('source script already contains Ghost Ops code (not an original map)')
    nl = '\r\n' if '\r\n' in text else '\n'
    for m in adapter['required_markers']:
        if m not in text:
            raise ValueError('required marker missing in source script: %s' % m)
    libs = text.find('void InitLibs')
    includes = [m for m in re.finditer(r'^include\s+"[^"]+"[ \t]*\r?$', text, re.M) if m.start() < libs]
    if not includes:
        raise ValueError('no include lines before InitLibs')
    ins = includes[-1].end()
    hook = adapter['start_hook']
    fstart = text.find('bool %s' % hook['function'])
    if fstart < 0:
        raise ValueError('hook function not found: %s' % hook['function'])
    fend = text.find(nl + '}', fstart)
    body = text[fstart:fend]
    if body.count(hook['after']) != 1:
        raise ValueError('hook anchor must occur exactly once in %s (found %d)' % (hook['function'], body.count(hook['after'])))
    apos = fstart + body.index(hook['after']) + len(hook['after'])
    if apos < ins:
        raise ValueError('hook precedes includes')
    block_nl = nl.join(block.replace('\r\n', '\n').split('\n'))
    inject = nl + BEGIN + nl + block_nl.rstrip() + nl + END
    call = nl + '    ' + hook['call'] + HOOK_TAG
    return text[:ins] + inject + text[ins:apos] + call + text[apos:]


def patch_unitdata(text, fragment):
    """Insert the Nova fire-control override before </Catalog>. Pure; raises ValueError."""
    if XML_BEGIN in text:
        raise ValueError('unit data already patched')
    if 'CUnit id="Nova"' in text:
        raise ValueError('map already overrides Nova; refusing to guess indices')
    if text.count('</Catalog>') != 1:
        raise ValueError('unit data must contain exactly one </Catalog>')
    nl = '\r\n' if '\r\n' in text else '\n'
    frag = nl.join(fragment.replace('\r\n', '\n').rstrip('\n').split('\n'))
    return text.replace('</Catalog>', XML_BEGIN + nl + frag + nl + XML_END + nl + '</Catalog>')


def unpatch_unitdata(text):
    return re.sub(re.escape(XML_BEGIN) + r'.*?' + re.escape(XML_END) + r'\r?\n', '', text, flags=re.S)


def build_block(adapter, cfg):
    core = read(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), 'r')
    ad = read(os.path.join(ROOT, adapter['adapter_source']), 'r')
    return core.rstrip() + '\n\n' + gen_config(cfg) + '\n' + ad


def needs_nova_patch(cfg):
    return 'Nova' in cfg['operatives']['squad']


def load_adapter(mission):
    return load_json('adapters/%s/adapter.json' % mission)


def paths(adapter, source=None):
    src = source or os.path.join(ROOT, 'tmp', 'source', adapter['source_map_file'])
    out = os.path.join(ROOT, 'dist', adapter['output_map_file'])
    return src, out


def build_manifest_path(mission):
    return os.path.join(ROOT, 'build', 'last_build_%s.json' % mission)


def install_manifest_path(mission):
    return os.path.join(ROOT, 'build', 'install_%s.json' % mission)


def cmd_build(args):
    adapter = load_adapter(args.mission)
    cfg = load_json(adapter['config'])
    if args.multiplier is not None:
        cfg['base_support']['damage_multiplier'] = args.multiplier
    errs = validate_config(cfg)
    if errs:
        print('CONFIG INVALID:\n  ' + '\n  '.join(errs))
        return 2
    src, out = paths(adapter, args.source)
    if not os.path.isfile(src):
        print('Source map not found: %s\nSee docs/EXTRACT_MAP.md' % src)
        return 2
    src_bytes = read(src)
    src_hash = sha256(src_bytes)
    arc = sc2mpq.Archive(src_bytes)
    script = arc.read(adapter['script_member'])
    if script is None:
        print('Map has no %s' % adapter['script_member'])
        return 2
    text = script.decode('utf-8-sig')
    bom = script.startswith(b'\xef\xbb\xbf')
    block = build_block(adapter, cfg)
    problems = galaxy_lint.lint(block)
    if problems:
        print('GALAXY LINT FAILED:\n  ' + '\n  '.join(problems))
        return 3
    patched = patch_script(text, adapter, block)
    problems = galaxy_lint.lint(patched)
    if problems:
        print('GALAXY LINT FAILED on patched script:\n  ' + '\n  '.join(problems))
        return 3
    data = (b'\xef\xbb\xbf' if bom else b'') + patched.encode('utf-8')
    arc.set_file(adapter['script_member'], data)
    manifest = {
        'mission': adapter['mission'],
        'source_map': src,
        'source_sha256': src_hash,
        'output_map': out,
        'script_member': adapter['script_member'],
        'script_original_sha256': sha256(script),
        'script_patched_sha256': sha256(data),
        'config': adapter['config'],
        'squad': cfg['operatives']['squad'],
        'damage_multiplier': cfg['base_support']['damage_multiplier'],
        'invulnerable_allies': cfg['experimental']['invulnerable_allies'],
        'nova_fire_control_patch': False,
    }
    if needs_nova_patch(cfg):
        ud = arc.read(UNITDATA)
        if ud is None:
            print('map has no %s; cannot add Nova fire control' % UNITDATA)
            return 2
        ud_text = ud.decode('utf-8-sig')
        fragment = read(os.path.join(ROOT, 'core', 'data', 'NovaFireControl.xml'), 'r')
        ud_new = patch_unitdata(ud_text, fragment)
        ET.fromstring(ud_new.encode('utf-8'))  # must stay well-formed
        ud_bytes = (b'\xef\xbb\xbf' if ud.startswith(b'\xef\xbb\xbf') else b'') + ud_new.encode('utf-8')
        arc.set_file(UNITDATA, ud_bytes)
        manifest['nova_fire_control_patch'] = True
        manifest['unitdata_original_sha256'] = sha256(ud)
    arc.drop_attributes()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    built = arc.tobytes()
    with open(out, 'wb') as f:
        f.write(built)
    manifest['output_sha256'] = sha256(built)
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    with open(build_manifest_path(adapter['mission']), 'w') as f:
        json.dump(manifest, f, indent=2)
    if sha256(read(src)) != src_hash:
        print('SOURCE MAP CHANGED DURING BUILD - this must never happen')
        return 4
    print('built %s (%d bytes)\n  sha256 %s\n  source unchanged: %s' % (out, len(built), manifest['output_sha256'], src_hash))
    return cmd_verify(args)


def cmd_verify(args):
    adapter = load_adapter(args.mission)
    src, out = paths(adapter, args.source)
    man_path = build_manifest_path(adapter['mission'])
    if not (os.path.isfile(out) and os.path.isfile(man_path)):
        print('nothing to verify: build first')
        return 2
    man = json.loads(read(man_path, 'r'))
    ok = True

    def check(label, cond):
        nonlocal ok
        print('  [%s] %s' % ('OK' if cond else 'FAIL', label))
        ok = ok and cond

    built = read(out)
    check('built map hash matches manifest', sha256(built) == man['output_sha256'])
    check('source map untouched since build', sha256(read(src)) == man['source_sha256'])
    a_src, a_out = sc2mpq.Archive(read(src)), sc2mpq.Archive(built)
    names = [n for n in a_src.names() if not n.startswith('(')]
    check('listfile has %d files' % len(names), len(names) > 0)
    changed = sorted(n.lower() for n in names if a_src.read(n) != a_out.read(n))
    expected = [man['script_member'].lower()] + ([UNITDATA.lower()] if man['nova_fire_control_patch'] else [])
    check('only %s differ from source (differs: %s)' % (expected, changed), changed == sorted(expected))
    new = a_out.read(man['script_member']).decode('utf-8-sig')
    check('hook present exactly once', new.count(HOOK_TAG) == 1)
    check('config in script matches manifest (multiplier %s, invulnerable %s, squad %s)' % (man['damage_multiplier'], man['invulnerable_allies'], man['squad']),
          ('go_cfgDamageMultiplier = %d;' % man['damage_multiplier']) in new
          and ('go_cfgInvulnerableAllies = %s;' % ('true' if man['invulnerable_allies'] else 'false')) in new
          and ('go_cfgSquadSize = %d;' % len(man['squad'])) in new)
    check('Ghost Ops block present exactly once', new.count(BEGIN) == 1 and new.count(END) == 1)
    orig = a_src.read(man['script_member']).decode('utf-8-sig')
    stripped = re.sub(r'\r?\n' + re.escape(BEGIN) + r'.*?' + re.escape(END), '', new, flags=re.S)
    stripped = re.sub(r'\r?\n    GhostOps_OnMissionStart\(\);' + re.escape(HOOK_TAG), '', stripped)
    check('removing our additions restores the original script text exactly', stripped == orig)
    check('all scenario functions of the original are kept', all(f in new for f in re.findall(r'^bool (gt_\w+_Func)', orig, re.M)))
    ud_new = a_out.read(UNITDATA).decode('utf-8-sig')
    ud_old = a_src.read(UNITDATA).decode('utf-8-sig')
    if man['nova_fire_control_patch']:
        check('unit data well-formed and restores exactly', unpatch_unitdata(ud_new) == ud_old and ET.fromstring(ud_new.encode('utf-8')) is not None)
        root = ET.fromstring(ud_new.encode('utf-8'))
        nova = [u for u in root.iter('CUnit') if u.get('id') == 'Nova']
        check('Nova override adds exactly hold fire / weapons free', len(nova) == 1 and sorted(e.get('Link') for e in nova[0].iter('AbilArray')) == ['GhostHoldFire', 'GhostWeaponsFree'])
    else:
        check('unit data untouched', ud_new == ud_old)
    print('VERIFY ' + ('PASSED' if ok else 'FAILED'))
    return 0 if ok else 5


def cmd_install(args):
    adapter = load_adapter(args.mission)
    _, out = paths(adapter)
    if cmd_verify(args) != 0:
        print('refusing to install an unverified build')
        return 5
    dest_dir = os.path.join(SC2_DIR, 'Maps', 'GhostOps')
    dest = os.path.join(dest_dir, adapter['output_map_file'])
    mp = install_manifest_path(adapter['mission'])
    if os.path.exists(mp):
        print('already installed (see %s); run uninstall first' % mp)
        return 6
    if os.path.exists(dest):
        print('target exists and was not installed by us: %s' % dest)
        return 6
    created_dir = not os.path.isdir(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copyfile(out, dest)
    rec = {'file': dest, 'sha256': sha256(read(dest)), 'created_dir': created_dir, 'dir': dest_dir}
    with open(mp, 'w') as f:
        json.dump(rec, f, indent=2)
    print('installed %s' % dest)
    return 0


def cmd_uninstall(args):
    mp = install_manifest_path(args.mission)
    if not os.path.exists(mp):
        print('nothing installed by this project for %s' % args.mission)
        return 0
    rec = json.loads(read(mp, 'r'))
    if os.path.exists(rec['file']):
        if sha256(read(rec['file'])) != rec['sha256']:
            print('installed file was modified since install; not deleting: %s' % rec['file'])
            return 6
        os.remove(rec['file'])
    if rec['created_dir'] and os.path.isdir(rec['dir']) and not os.listdir(rec['dir']):
        os.rmdir(rec['dir'])
    os.remove(mp)
    print('rolled back')
    return 0


def cmd_launch(args):
    adapter = load_adapter(args.mission)
    dest = os.path.join(SC2_DIR, 'Maps', 'GhostOps', adapter['output_map_file'])
    print('"%s" -run "%s" -displaymode 2' % (os.path.join(SC2_DIR, 'Support64', 'SC2Switcher_x64.exe'), dest))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'verify', 'install', 'uninstall', 'launch'])
    p.add_argument('--mission', default='traynor02')
    p.add_argument('--source')
    p.add_argument('--multiplier', type=int, choices=[1, 2, 3], help='override base_support.damage_multiplier for this build')
    args = p.parse_args(argv)
    return globals()['cmd_' + args.command](args)


if __name__ == '__main__':
    sys.exit(main())
