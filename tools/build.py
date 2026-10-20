"""Ghost Ops build tool.

  python tools/build.py build     [--mission traynor02|ttychus01] [--multiplier 1|2|3] [--source MAP]
  python tools/build.py verify    [--mission ...]   re-check the built map against its source
  python tools/build.py install   [--mission ...]   copy the built map to <SC2>/Maps/GhostOps
  python tools/build.py uninstall [--mission ...]   roll back exactly what install created
  python tools/build.py launch    [--mission ...]   print the direct launch command (missions with profiles: build, install
                                    and start the chosen profile; --print-only only prints)

The source map is only ever read. Everything written stays inside this project, except the
install step, which writes one file (and, if needed, one folder) under <SC2>/Maps/GhostOps.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
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
GAMEDATA = 'Base.SC2Data' + chr(92) + 'GameData' + chr(92)
UNITDATA = GAMEDATA + 'UnitData.xml'
SQUAD_TYPES = ('Nova', 'Ghost', 'Medic')
ABILITIES = ('Snipe', 'EMP', 'TacNukeStrike')
MAX_FRAGILE = 4
PROFILE_KEY = 'Param/Value/GhostOpsProfile'
TXT_BEGIN = '// GHOSTOPS BEGIN'
TXT_END = '// GHOSTOPS END'
# Index of each ability in the standard Ghost's AbilArray (Liberty mod data of client 3.1.4):
# stop 0, attack 1, move 2, GhostCloak 3, Snipe 4, TacNukeStrike 5, GhostHoldFire 6, EMP 7, GhostWeaponsFree 8
GHOST_ABIL_INDEX = {'TacNukeStrike': 5, 'EMP': 7}
TAC_TEXT_PREFIX = 'Param/Value/GhostOpsTac_'
TAC_TEXT_KEYS = ('ZoneLeft', 'RoleSpotter', 'RoleOperative', 'InfoSpotter', 'InfoOperative', 'NukeReady', 'Aiming', 'AimCancelled', 'Launched',
                 'SpotterLost', 'SpotterLostAfter', 'AcademyLost', 'AlertTitle', 'AlertText', 'SwannName', 'SwannText', 'GhostName', 'GhostText', 'ArrivalText',
                 'ObjectiveTitle', 'ObjectiveText', 'Tip1Title', 'Tip1Text', 'Tip2Title', 'Tip2Text', 'Tip3Title', 'Tip3Text', 'Tip4Title', 'Tip4Text')
# AbilArray indexes of the Ghost Academy in the merged campaign data (Liberty mod + Liberty campaign):
# BuildInProgress 0, que5 1, ArmSiloWithNuke 2, GhostAcademyResearch 3, MercCompoundResearch 4, HeroArmNuke 5, SpectreNukeSiloArmMagazine 6
ACADEMY_REMOVED_ABILS = (3, 4, 5, 6)
# Voice clips imported into the map (config key "audio.clips"): the WAV goes to Assets\Sounds\GhostOps\<file name> inside the map archive,
# a CSound entry with the clip id makes it playable with SoundLink("<id>", 0).
AUDIO_DIR = 'Assets' + chr(92) + 'Sounds' + chr(92) + 'GhostOps' + chr(92)
AUDIO_ID = re.compile(r'GhostOps[A-Za-z0-9]{3,40}')
SCENE_TEXT_PREFIX = 'Param/Value/GhostOpsScene_'
HANSON_TEXT_PREFIX = 'Param/Value/GhostOpsH_'
HANSON_TEXT_KEYS = ('BtnPreparing', 'BtnReady', 'BtnActive', 'ReadyMsg', 'SentMsg')
HANSON_ROLES = ('base', 'houses', 'air')
SCENE_TEXT_KEYS = ('RaynorName', 'RaynorLine', 'MarineName', 'MarineBLine', 'MarineALine', 'Explain')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read(path, mode='rb'):
    with open(path, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()


def load_json(rel):
    return json.loads(read(os.path.join(ROOT, rel), 'r').lstrip('\ufeff'))


def effective_fragile_units(cfg):
    """army.fragile_units plus our own Ghosts when ghost_tuning.ghost_life is set (covered players only)."""
    fus = list(cfg.get('army', {}).get('fragile_units', []))
    gl = (cfg.get('ghost_tuning') or {}).get('ghost_life')
    if gl is not None and 'Ghost' in cfg['operatives']['squad']:
        fus.append({'type': 'Ghost', 'max_life': gl})
    return fus


def validate_config(cfg):
    errs = []
    if cfg.get('schema_version') != 4:
        errs.append('schema_version must be 4')
    op = cfg.get('operatives', {})
    squad = op.get('squad')
    if not isinstance(squad, list) or not 1 <= len(squad) <= 6:
        errs.append('operatives.squad must be a list of 1..6 unit types')
    elif any(t not in SQUAD_TYPES for t in squad):
        errs.append('operatives.squad entries must be one of %s' % (SQUAD_TYPES,))
    for k in ('start_hold_fire', 'ghost_permanent_cloak', 'ghost_start_cloaked'):
        if not isinstance(op.get(k), bool):
            errs.append('operatives.%s must be boolean' % k)
    dg = cfg.get('difficulty', {})
    if dg.get('expected') not in (1, 2, 3, 4) or isinstance(dg.get('expected'), bool):
        errs.append('difficulty.expected must be 1..4 (campaign difficulty, 3 = Hard)')
    if not isinstance(dg.get('show_message'), bool):
        errs.append('difficulty.show_message must be boolean')
    da = op.get('disabled_abilities', [])
    if not isinstance(da, list) or any(x not in ABILITIES for x in da) or len(set(da)) != len(da):
        errs.append('operatives.disabled_abilities must be a list of distinct abilities from %s' % (ABILITIES,))
    fus = cfg.get('army', {}).get('fragile_units', [])
    if not isinstance(fus, list) or len(fus) + (1 if (cfg.get('ghost_tuning') or {}).get('ghost_life') is not None else 0) > MAX_FRAGILE:
        errs.append('army.fragile_units must be a list of at most %d entries' % MAX_FRAGILE)
    else:
        for fu in fus:
            if not isinstance(fu, dict) or not re.fullmatch(r'[A-Za-z0-9_]+', str(fu.get('type', ''))) \
                    or not isinstance(fu.get('max_life'), int) or isinstance(fu.get('max_life'), bool) or not 1 <= fu['max_life'] <= 1000:
                errs.append('army.fragile_units entries must be {"type": id, "max_life": 1..1000}')
        if len({fu.get('type') for fu in fus if isinstance(fu, dict)}) != len(fus):
            errs.append('army.fragile_units types must be distinct')
    gt = cfg.get('ghost_tuning')
    if gt is not None:
        errs += validate_ghost_tuning(gt)
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
    if cfg.get('tactical') is not None:
        errs += validate_tactical(cfg)
    if cfg.get('audio') is not None:
        errs += validate_audio(cfg['audio'])
    if cfg.get('scene') is not None:
        errs += validate_scene(cfg)
    if cfg.get('hanson') is not None:
        errs += validate_hanson(cfg)
    if cfg.get('ce0') is not None:
        errs += validate_ce0(cfg)
    return errs


def validate_ce0(cfg):
    """CE-0 technical probe (config key "ce0"; development only: the profile name must end with _dev)."""
    errs = []
    c = cfg['ce0']
    name = (cfg.get('profile') or {}).get('name', '')
    if not str(name).endswith('_dev'):
        errs.append('ce0 is development only: the profile name must end with _dev (got %r)' % name)
    if not isinstance(c.get('operation_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', c.get('operation_id', '')):
        errs.append('ce0.operation_id must be 1..32 characters of [A-Za-z0-9_-]')
    types = c.get('census_types')
    if not isinstance(types, list) or not 1 <= len(types) <= 8 or any(not re.fullmatch(r'[A-Za-z0-9_]+', str(t)) for t in types):
        errs.append('ce0.census_types must be a list of 1..8 unit type ids')
    for k in c:
        if k not in ('operation_id', 'census_types'):
            errs.append('ce0.%s is not supported' % k)
    return errs


def gen_ce0(cfg):
    """GhostOps_Ce0_Apply(): constants of the development probe."""
    c = cfg['ce0']
    snapshot = json.dumps({k: v for k, v in cfg.items() if k != 'profile'}, sort_keys=True)
    lines = ['// Generated CE-0 probe configuration (development only)', 'void GhostOps_Ce0_Apply () {',
             '    go_c0Enabled = true;', '    go_c0Op = "%s";' % c['operation_id'], '    go_c0Hash = "%s";' % hashlib.sha256(snapshot.encode('utf-8')).hexdigest()[:16],
             '    go_c0TypeCount = %d;' % len(c['census_types'])]
    for i, t in enumerate(c['census_types']):
        lines.append('    go_c0Types[%d] = "%s";' % (i, t))
    lines += ['}', '']
    return chr(10).join(lines)


def validate_hanson(cfg):
    """THanson01 sniper cover (config key "hanson", see config/thanson01.json)."""
    h = cfg['hanson']
    errs = []
    if not isinstance(h, dict):
        return ['hanson must be an object']
    for k in ('debug_log', 'lock_development', 'convoy_command'):
        if not isinstance(h.get(k), bool):
            errs.append('hanson.%s must be boolean' % k)
    gs = h.get('ghost_spawn')
    if not (isinstance(gs, list) and len(gs) == 2 and all(_num(v) and 0 <= v <= 400 for v in gs)):
        errs.append('hanson.ghost_spawn must be [x, y]')
    tur = h.get('turrets')
    if not isinstance(tur, dict) or tur.get('owner') not in (1, 4) or not isinstance(tur.get('list'), list) or len(tur['list']) > 24:
        errs.append('hanson.turrets needs owner 1 or 4 and a list of at most 24 entries')
    else:
        for t in tur['list']:
            if not (isinstance(t, dict) and _num(t.get('x')) and _num(t.get('y')) and 0 <= t['x'] <= 400 and 0 <= t['y'] <= 400 and t.get('role') in HANSON_ROLES):
                errs.append('every turret needs x, y and a role of %s' % (HANSON_ROLES,))
                break
    b = h.get('button', {})
    for k, (lo, hi) in {'width': (80, 800), 'height': (24, 200), 'offset_x': (0, 800), 'offset_y': (0, 600)}.items():
        if not isinstance(b.get(k), int) or isinstance(b.get(k), bool) or not lo <= b[k] <= hi:
            errs.append('hanson.button.%s must be an integer %d..%d' % (k, lo, hi))
    texts = h.get('texts')
    if not isinstance(texts, dict) or set(texts) != set(HANSON_TEXT_KEYS):
        errs.append('hanson.texts must have exactly the keys %s' % (HANSON_TEXT_KEYS,))
    else:
        for k, v in texts.items():
            if not isinstance(v, dict) or not v.get('ru') or not v.get('en'):
                errs.append('hanson.texts.%s needs "ru" and "en"' % k)
    at = h.get('autotest')
    if at is not None and (not isinstance(at, dict) or at.get('mode') not in (1, 2, 3, 4, 5, 6, 7)):
        errs.append('hanson.autotest.mode must be 1..7')
    if 'Ghost' not in cfg['operatives']['squad'] or len(cfg['operatives']['squad']) != 1:
        errs.append('hanson variant: the squad is exactly one Ghost')
    return errs


def audio_clips(cfg):
    """[(clip id, source path, member name in the map archive)]"""
    return [(c['id'], os.path.join(ROOT, *c['source'].split('/')), AUDIO_DIR + os.path.basename(c['source']))
            for c in (cfg.get('audio') or {}).get('clips', [])]


def validate_audio(a):
    errs = []
    clips = a.get('clips') if isinstance(a, dict) else None
    if not isinstance(clips, list) or not clips:
        return ['audio.clips must be a non-empty list of {"id", "source"}']
    ids, names = set(), set()
    for c in clips:
        if not isinstance(c, dict) or not AUDIO_ID.fullmatch(str(c.get('id', ''))):
            errs.append('audio clip id must match %s (got %r)' % (AUDIO_ID.pattern, c.get('id') if isinstance(c, dict) else c))
            continue
        src = str(c.get('source', ''))
        if not re.fullmatch(r'assets/audio/[A-Za-z0-9_]+/[A-Za-z0-9_]+\.wav', src):
            errs.append('audio clip %s: source must look like assets/audio/<dir>/<name>.wav (got %r)' % (c['id'], src))
            continue
        if not os.path.isfile(os.path.join(ROOT, *src.split('/'))):
            errs.append('audio clip %s: file not found: %s' % (c['id'], src))
        elif read(os.path.join(ROOT, *src.split('/')))[:4] != b'RIFF':
            errs.append('audio clip %s: %s is not a WAV file' % (c['id'], src))
        if c['id'] in ids or os.path.basename(src).lower() in names:
            errs.append('audio clip %s: id or file name used twice' % c['id'])
        ids.add(c['id'])
        names.add(os.path.basename(src).lower())
    return errs


def validate_scene(cfg):
    """The wounded squad scene of TRaynor01 (config key "scene")."""
    s = cfg['scene']
    errs = []
    if not isinstance(s, dict) or not isinstance(s.get('enabled'), bool):
        return ['scene.enabled must be boolean']
    for k, lo, hi in (('pause', 0.0, 3.0), ('raynor_seconds', 1.0, 20.0), ('marine_b_seconds', 1.0, 20.0), ('marine_a_seconds', 1.0, 20.0)):
        v = s.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            errs.append('scene.%s must be a number %g..%g' % (k, lo, hi))
    ids = {c['id'] for c in (cfg.get('audio') or {}).get('clips', [])}
    for k in ('raynor_clip', 'marine_b_clip', 'marine_a_clip'):
        if s.get(k) not in ids:
            errs.append('scene.%s must name a clip from audio.clips' % k)
    texts = s.get('texts')
    if not isinstance(texts, dict) or set(texts) != set(SCENE_TEXT_KEYS):
        errs.append('scene.texts must have exactly the keys %s' % (SCENE_TEXT_KEYS,))
    else:
        for k, v in texts.items():
            if not isinstance(v, dict) or not v.get('ru') or not v.get('en'):
                errs.append('scene.texts.%s needs "ru" and "en"' % k)
    return errs


def validate_tactical(cfg):
    """The tactical variant of TRaynor02 (see config/traynor02.poc.json, presets.tactical)."""
    t = cfg['tactical']
    errs = []
    if not isinstance(t, dict):
        return ['tactical must be an object']
    if cfg['operatives'].get('squad') != ['Ghost', 'Ghost']:
        errs.append('tactical: operatives.squad must be exactly two Ghosts')
    if cfg.get('base_support', {}).get('damage_multiplier') != 1:
        errs.append('tactical: no global army bonus (base_support.damage_multiplier 1)')
    if cfg.get('experimental', {}).get('invulnerable_allies'):
        errs.append('tactical: no invulnerability')
    if cfg.get('army', {}).get('fragile_units'):
        errs.append('tactical: army.fragile_units must stay empty (the module owns the Marine rules)')
    gt = cfg.get('ghost_tuning') or {}
    if 'EMP' not in gt.get('remove_abilities', []) or 'TacNukeStrike' in gt.get('remove_abilities', []):
        errs.append('tactical: ghost_tuning must remove EMP and keep TacNukeStrike (the Spotter needs it)')
    num = lambda v, lo, hi: _num(v) and lo <= v <= hi  # noqa: E731
    pair = lambda v: isinstance(v, list) and len(v) == 2 and all(_num(x) and 0 <= x <= 255 for x in v)  # noqa: E731
    g = t.get('garrison', {})
    if not num(g.get('damage_multiplier'), 1, 100):
        errs.append('tactical.garrison.damage_multiplier must be 1..100')
    z = g.get('zone', {})
    if not pair(z.get('center')) or not num(z.get('radius'), 1, 60):
        errs.append('tactical.garrison.zone needs center [x, y] and radius 1..60')
    if not isinstance(g.get('show_border'), bool):
        errs.append('tactical.garrison.show_border must be boolean')
    tm = t.get('trained_marine', {})
    if not isinstance(tm.get('life'), int) or isinstance(tm.get('life'), bool) or not 1 <= tm['life'] <= 45:
        errs.append('tactical.trained_marine.life must be an integer 1..45')
    if tm.get('can_attack') is not False:
        errs.append('tactical.trained_marine.can_attack must be false (new Marines have no weapon)')
    st = t.get('story', {})
    for k, (lo, hi) in {'first_delay': (1, 120), 'second_delay': (1, 300), 'alert_seconds': (3, 40), 'swann_seconds': (2, 30), 'arrival_seconds': (3, 40), 'ghost_seconds': (2, 20)}.items():
        if not num(st.get(k), lo, hi):
            errs.append('tactical.story.%s must be a number in %s..%s' % (k, lo, hi))
    a = t.get('academy', {})
    if not pair(a.get('position')) or not num(a.get('arm_time'), 0.5, 60):
        errs.append('tactical.academy needs position [x, y] and arm_time 0.5..60')
    n = t.get('nuke', {})
    if not num(n.get('aim_time'), 2, 60) or round(n.get('aim_time', 0) / 0.2, 6) != int(round(n.get('aim_time', 0) / 0.2)):
        errs.append('tactical.nuke.aim_time must be 2..60 and a multiple of 0.2')
    if not num(n.get('flight_time'), 1, 60):
        errs.append('tactical.nuke.flight_time must be 1..60')
    if not num(n.get('range'), 1, 30):
        errs.append('tactical.nuke.range must be 1..30')
    texts = t.get('texts', {})
    for k in TAC_TEXT_KEYS:
        v = texts.get(k)
        if not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and '\n' not in v[l] for l in ('ru', 'en')):
            errs.append('tactical.texts.%s needs non-empty single-line ru and en texts' % k)
    return errs


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_ghost_tuning(gt):
    errs = []
    if not isinstance(gt, dict):
        return ['ghost_tuning must be an object']
    sn = gt.get('snipe', {})
    ranges = {
        'energy_start': (0, 500), 'energy_max': (1, 500), 'regen_per_second': (0, 100),
        'cloak_activation_cost': (0, 200), 'cloak_net_per_second': (-100, 0),
    }
    for k, (lo, hi) in ranges.items():
        if not _num(gt.get(k)) or not lo <= gt[k] <= hi:
            errs.append('ghost_tuning.%s must be a number in %s..%s' % (k, lo, hi))
    if 'cooldown' in sn and (not _num(sn['cooldown']) or not 0 <= sn['cooldown'] <= 60):
        errs.append('ghost_tuning.snipe.cooldown must be a number in 0..60')
    if 'exclude_friendly' in sn and not isinstance(sn['exclude_friendly'], bool):
        errs.append('ghost_tuning.snipe.exclude_friendly must be boolean')
    for k, (lo, hi) in {'cost': (0, 200), 'damage': (1, 1000), 'cast_time': (0, 5)}.items():
        if not _num(sn.get(k)) or not lo <= sn[k] <= hi:
            errs.append('ghost_tuning.snipe.%s must be a number in %s..%s' % (k, lo, hi))
    if 'ghost_life' in gt and (not isinstance(gt['ghost_life'], int) or isinstance(gt['ghost_life'], bool) or not 1 <= gt['ghost_life'] <= 1000):
        errs.append('ghost_tuning.ghost_life must be an integer 1..1000')
    ra = gt.get('remove_abilities', [])
    if not isinstance(ra, list) or any(x not in GHOST_ABIL_INDEX for x in ra) or len(set(ra)) != len(ra):
        errs.append('ghost_tuning.remove_abilities must be distinct entries of %s' % sorted(GHOST_ABIL_INDEX))
    if not errs and gt['energy_start'] > gt['energy_max']:
        errs.append('ghost_tuning.energy_start must not exceed energy_max')
    return errs


def ghost_tuning_fragments(gt):
    """Catalog overrides for the standard Ghost (map local, so only this mission is affected).

    Net energy change under cloak = regen (unit) + cloak modification, so the cloak modification
    is (net - regen): regen +20 and net -10 gives -30."""
    g = lambda v: '%g' % v  # noqa: E731
    drain = gt['cloak_net_per_second'] - gt['regen_per_second']
    sn = gt['snipe']
    nl = chr(10)
    return {
        'UnitData.xml': nl.join([
            '    <CUnit id="Ghost">',
            '        <EnergyStart value="%s"/>' % g(gt['energy_start']),
            '        <EnergyMax value="%s"/>' % g(gt['energy_max']),
            '        <EnergyRegenRate value="%s"/>' % g(gt['regen_per_second']),
        ] + ['        <AbilArray index="%d" removed="1"/>' % GHOST_ABIL_INDEX[x] for x in gt.get('remove_abilities', [])]
        + ['    </CUnit>', '']),
        'BehaviorData.xml': nl.join([
            '    <CBehaviorBuff id="GhostCloak">',
            '        <Modification>',
            '            <VitalRegenArray index="Energy" value="%s"/>' % g(drain),
            '        </Modification>',
            '    </CBehaviorBuff>', '']),
        'AbilData.xml': nl.join([
            '    <CAbilBehavior id="GhostCloak">',
            '        <Cost index="0">',
            '            <Vital index="Energy" value="%s"/>' % g(gt['cloak_activation_cost']),
            '        </Cost>',
            '    </CAbilBehavior>',
            '    <CAbilEffectTarget id="Snipe">',
            '        <CastIntroTime value="%s"/>' % g(sn['cast_time']),
        ] + (['        <TargetFilters index="0" value="Biological,Visible;Self,Player,Ally,Neutral,Structure,Destructible,Stasis,Dead,Hidden,Invulnerable"/>'] if sn.get('exclude_friendly') else []) + [
            '        <Cost index="0">',
            '            <Vital index="Energy" value="%s"/>' % g(sn['cost']),
        ] + (['            <Cooldown TimeUse="%s"/>' % g(sn['cooldown'])] if sn.get('cooldown', 0) > 0 else []) + [
            '        </Cost>',
            '    </CAbilEffectTarget>', '']),
        'EffectData.xml': nl.join([
            '    <CEffectDamage id="SnipeDamage">',
            '        <Amount value="%s"/>' % g(sn['damage']),
            '    </CEffectDamage>', '']),
    }


def tactical_fragments(t):
    """Catalog overrides of the tactical variant (map local): two weapon behaviors, the Ghost Academy and
    the missile, and the changed chain of the nuclear strike. Times are game seconds."""
    g = lambda v: '%g' % v  # noqa: E731
    nl = chr(10)
    gm = t['garrison']['damage_multiplier']
    n = t['nuke']

    def behavior(bid, mult):
        # DamageDealtFraction is ADDITIVE (measured in the game: value 0.1 gave x1.1, value 20 gave x21): factor = 1 + value
        mult = round(mult - 1.0, 6)
        return [
            '    <CBehaviorBuff id="%s">' % bid,
            '        <InfoFlags index="Hidden" value="1"/>',
            '        <Modification>',
        ] + ['            <DamageDealtFraction index="%s" value="%s"/>' % (k, g(mult)) for k in ('Spell', 'Melee', 'Ranged', 'Splash')] + [
            '        </Modification>',
            '    </CBehaviorBuff>',
        ]

    return {
        'UnitData.xml': nl.join(
            ['    <CUnit id="GhostAcademy">']
            + ['        <AbilArray index="%d" removed="1"/>' % i for i in ACADEMY_REMOVED_ABILS]
            + ['    </CUnit>',
               '    <CUnit id="Nuke">',
               '        <CostResource index="Minerals" value="0"/>',
               '        <CostResource index="Vespene" value="0"/>',
               '    </CUnit>', '']),
        'BehaviorData.xml': nl.join(behavior('GhostOpsGarrisonDamage', gm) + ['']),
        'RequirementData.xml': nl.join([
            '    <CRequirement id="TrainNuke">',
            '        <NodeArray index="Use" Link="Not866976074CountUnitNukeQueuedOrBetterAtUnit"/>',
            '        <NodeArray index="Show" Link="Not866976074CountUnitNukeQueuedOrBetterAtUnit"/>',
            '    </CRequirement>', '']),
        'AbilData.xml': nl.join([
            '    <CAbilArmMagazine id="ArmSiloWithNuke">',
            '        <InfoArray index="Ammo1" Time="%s"/>' % g(t['academy']['arm_time']),
            '    </CAbilArmMagazine>',
            '    <CAbilEffectTarget id="TacNukeStrike">',
            '        <Range value="%s"/>' % g(n['range']),
            '        <FinishTime value="0"/>',
            '    </CAbilEffectTarget>', '']),
        'EffectData.xml': nl.join([
            '    <CEffectCreatePersistent id="NukePersistent">',
            '        <InitialDelay value="0"/>',
            '        <PeriodCount value="%d"/>' % int(round(n['aim_time'] / 0.2)),
            '        <ExpireEffect value="GhostOpsNukeFlight"/>',
            '    </CEffectCreatePersistent>',
            '    <CEffectCreatePersistent id="GhostOpsNukeFlight">',
            '        <EditorCategories value="Race:Terran"/>',
            '        <ExpireDelay value="%s"/>' % g(n['flight_time']),
            '        <ExpireEffect value="NukeDetonate"/>',
            '    </CEffectCreatePersistent>',
            '    <CEffectCreatePersistent id="NukeDetonate">',
            '        <InitialDelay value="0"/>',
            '    </CEffectCreatePersistent>',
        ]),
    }


def catalog_fragments(cfg):
    """{file name in Base.SC2Data/GameData: xml fragment} that this configuration needs."""
    frags = {}
    if needs_nova_patch(cfg):
        frags['UnitData.xml'] = read(os.path.join(ROOT, 'core', 'data', 'NovaFireControl.xml'), 'r')
    if cfg.get('ghost_tuning'):
        for name, frag in ghost_tuning_fragments(cfg['ghost_tuning']).items():
            frags[name] = frags.get(name, '') + frag
    if cfg.get('tactical'):
        for name, frag in tactical_fragments(cfg['tactical']).items():
            frags[name] = frags.get(name, '') + frag
    clips = audio_clips(cfg)
    if clips:
        frags['SoundData.xml'] = frags.get('SoundData.xml', '') + chr(10).join(
            '    <CSound id="%s" parent="SM_Old">%s        <Mode value="2D"/>%s        <AssetArray File="%s"/>%s    </CSound>' % (cid, chr(10), chr(10), member, chr(10)) for cid, _, member in clips) + chr(10)
    return frags


def gen_config(cfg):
    op = cfg['operatives']
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    fus = effective_fragile_units(cfg)
    lines = ['// Generated from %s' % cfg['mission'],
             'void GhostOps_ApplyConfig () {',
             '    go_cfgSquadSize = %d;' % len(op['squad'])]
    for i, t in enumerate(op['squad']):
        lines.append('    go_cfgSquadType[%d] = "%s";' % (i, t))
    lines += ['    go_cfgStartHoldFire = %s;' % b(op['start_hold_fire']),
              '    go_cfgGhostPermanentCloak = %s;' % b(op['ghost_permanent_cloak']),
              '    go_cfgGhostStartCloaked = %s;' % b(op['ghost_start_cloaked']),
              '    go_cfgShowDifficulty = %s;' % b(cfg['difficulty']['show_message']),
              '    go_cfgExpectedDifficulty = %d;' % cfg['difficulty']['expected'],
              '    go_cfgShowTuning = %s;' % b(bool(cfg.get('ghost_tuning'))),
              '    go_cfgHasProfile = %s;' % b(bool(cfg.get('profile'))),
              '    go_cfgFragileCount = %d;' % len(fus),
              '    go_cfgDamageMultiplier = %d;' % cfg['base_support']['damage_multiplier'],
              '    go_cfgInvulnerableAllies = %s;' % b(cfg['experimental']['invulnerable_allies']),
              ] + ['    go_cfgFragileType[%d] = "%s";' % (i, fu['type']) for i, fu in enumerate(fus)] \
              + ['    go_cfgFragileLife[%d] = %d.0;' % (i, fu['max_life']) for i, fu in enumerate(fus)] \
              + (['    go_cfgPresetText = StringExternal("%s");' % PROFILE_KEY] if cfg.get('profile') else []) \
              + ['}', '',
              'void GhostOps_ApplyAbilityRestrictions (int lp_player) {']
    for ab in op.get('disabled_abilities', []):
        lines.append('    TechTreeAbilityAllow(lp_player, AbilityCommand("%s", 0), false);' % ab)
    lines += ['}', '']
    return chr(10).join(lines)


def gen_tactical(cfg):
    """GhostOps_ApplyTacticalConfig(): the module is inert (go_tacEnabled false) unless the config has a tactical section."""
    t = cfg.get('tactical')
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    lines = ['// Generated tactical configuration', 'void GhostOps_ApplyTacticalConfig () {']
    if not t:
        lines += ['    go_tacEnabled = false;', '}', '']
        return chr(10).join(lines)
    z = t['garrison']['zone']
    a = t['academy']['position']
    lines += [
        '    go_tacEnabled = true;',
        '    go_tacDebug = %s;' % b(t.get('debug_log')),
        '    go_tacZoneX = %.4f;' % z['center'][0],
        '    go_tacZoneY = %.4f;' % z['center'][1],
        '    go_tacZoneR = %.4f;' % z['radius'],
        '    go_tacMarkers = %s;' % b(t['garrison']['show_border']),
        '    go_tacAcademyX = %.4f;' % a[0],
        '    go_tacAcademyY = %.4f;' % a[1],
        '    go_tacTrainedLife = %d.0;' % t['trained_marine']['life'],
        '    go_tacStoryFirst = %.1f;' % t['story']['first_delay'],
        '    go_tacStorySecond = %.1f;' % t['story']['second_delay'],
        '    go_tacStoryAlertLen = %.1f;' % t['story']['alert_seconds'],
        '    go_tacStorySwannLen = %.1f;' % t['story']['swann_seconds'],
        '    go_tacStoryArrivalLen = %.1f;' % t['story']['arrival_seconds'],
        '    go_tacStoryGhostLen = %.1f;' % t['story']['ghost_seconds'],
        '}', '']
    return chr(10).join(lines)


def gen_scene(cfg):
    """GhostOps_ApplySceneConfig(): constants of the wounded squad scene (TRaynor01); empty when the config has no scene."""
    s = cfg.get('scene')
    if not s:
        return ''
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    return chr(10).join([
        '// Generated scene configuration',
        'bool go_sceneEnabled;',
        'bool go_sceneDebug;',
        'bool go_sceneDone;                 // the scene is played once (saved with the game)',
        'fixed go_scenePause;',
        'fixed go_sceneRaynorLen;',
        'fixed go_sceneMarineBLen;',
        'fixed go_sceneMarineALen;',
        'soundlink go_sceneRaynorClip;',
        'soundlink go_sceneMarineBClip;',
        'soundlink go_sceneMarineAClip;',
        'unit go_sceneRaynor;',
        'bank go_sceneBank;',
        'int go_sceneLogN;',
        '',
        'void GhostOps_ApplySceneConfig () {',
        '    go_sceneEnabled = %s;' % b(s['enabled']),
        '    go_scenePause = %.2f;' % s['pause'],
        '    go_sceneRaynorLen = %.1f;' % s['raynor_seconds'],
        '    go_sceneMarineBLen = %.1f;' % s['marine_b_seconds'],
        '    go_sceneMarineALen = %.1f;' % s['marine_a_seconds'],
        '    go_sceneRaynorClip = SoundLink("%s", 0);' % s['raynor_clip'],
        '    go_sceneMarineBClip = SoundLink("%s", 0);' % s['marine_b_clip'],
        '    go_sceneMarineAClip = SoundLink("%s", 0);' % s['marine_a_clip'],
        '    go_sceneDebug = %s;' % b(s.get('debug_log')),
        '}', ''])


def gen_hanson(cfg):
    """GhostOps_ApplyHansonConfig(): constants of the THanson01 module."""
    h = cfg['hanson']
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    lines = ['// Generated THanson01 configuration', 'void GhostOps_ApplyHansonConfig () {',
             '    go_hEnabled = true;',
             '    go_hDebug = %s;' % b(h['debug_log']),
             '    go_hLock = %s;' % b(h['lock_development']),
             '    go_hCommand = %s;' % b(h['convoy_command']),
             '    go_hGhostX = %.4f;' % h['ghost_spawn'][0],
             '    go_hGhostY = %.4f;' % h['ghost_spawn'][1],
             '    go_hTurretOwner = %d;' % h['turrets']['owner'],
             '    go_hTurretCount = %d;' % len(h['turrets']['list']),
             '    go_hBtnW = %d;' % h['button']['width'],
             '    go_hBtnH = %d;' % h['button']['height'],
             '    go_hBtnOffX = %d;' % h['button']['offset_x'],
             '    go_hBtnOffY = %d;' % h['button']['offset_y']]
    for i, t in enumerate(h['turrets']['list']):
        lines.append('    go_hTurretX[%d] = %.4f;' % (i, t['x']))
        lines.append('    go_hTurretY[%d] = %.4f;' % (i, t['y']))
    if h.get('autotest'):
        lines.append('    GhostOps_ApplyHansonTestConfig();')
    lines += ['}', '']
    return chr(10).join(lines)


def gen_hanson_test(cfg):
    """Development only: scripted checks (hidden preset sniper_dev). Production builds get empty stubs."""
    t = cfg['hanson'].get('autotest')
    if not t:
        return chr(10).join(['// no scripted test in this build', 'void GhostOps_HansonTest_Start () {', '}', '',
                             'void GhostOps_HansonTest_Probe () {', '}', ''])
    src = read(os.path.join(ROOT, 'core', 'GhostOpsHansonTest.galaxy'), 'r').rstrip()
    fn = ['void GhostOps_ApplyHansonTestConfig () {', '    go_htMode = %d;' % t['mode'], '    go_htScale = %.2f;' % t.get('time_scale', 1.0), '}', '']
    return src + chr(10) + chr(10) + chr(10).join(fn)


def gen_tactical_test(cfg):
    """Development only: the scripted nuclear strike test (hidden dev presets). Production builds get an empty stub."""
    t = (cfg.get('tactical') or {}).get('autotest')
    if not t:
        return chr(10).join(['// no scripted test in this build', 'void GhostOps_TacTest_Start () {', '}', '', 'void GhostOps_TacTest_Delivered () {', '}', ''])
    src = read(os.path.join(ROOT, 'core', 'GhostOpsTacticalTest.galaxy'), 'r').rstrip()
    cfg_fn = [
        'void GhostOps_ApplyTacticalTestConfig () {',
        '    go_tacTestMode = %d;' % t['mode'],
        '    go_tacTestTargetX = %.4f;' % t['target'][0], '    go_tacTestTargetY = %.4f;' % t['target'][1],
        '    go_tacTestSpotX = %.4f;' % t['spotter'][0], '    go_tacTestSpotY = %.4f;' % t['spotter'][1],
        '    go_tacTestRetreatX = %.4f;' % t['retreat'][0], '    go_tacTestRetreatY = %.4f;' % t['retreat'][1],
        '}', '']
    return src + chr(10) + chr(10) + chr(10).join(cfg_fn)


def hook_list(adapter):
    """Normalised hooks: [{'function', 'anchor', 'where': 'after'|'before', 'call'}]."""
    hooks = []
    for h in adapter.get('start_hooks') or ([adapter['start_hook']] if 'start_hook' in adapter else []):
        hooks.append({'function': h['function'], 'anchor': h['after'], 'where': 'after', 'call': h['call']})
    for h in adapter.get('extra_hooks', []):
        if 'before' in h:
            hooks.append({'function': h['function'], 'anchor': h['before'], 'where': 'before', 'call': h['call']})
        else:
            hooks.append({'function': h['function'], 'anchor': h['after'], 'where': 'after', 'call': h['call']})
    if adapter.get('init_hook'):
        h = adapter['init_hook']
        hooks.append({'function': h['function'], 'anchor': h['before'], 'where': 'before', 'call': h['call']})
    return hooks


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
    edits = []  # (position, inserted text)
    for hook in hook_list(adapter):
        fstart = text.find('bool %s' % hook['function'])
        if fstart < 0:
            raise ValueError('hook function not found: %s' % hook['function'])
        fend = text.find(nl + '}', fstart)
        body = text[fstart:fend]
        if body.count(hook['anchor']) != 1:
            raise ValueError('hook anchor must occur exactly once in %s (found %d)' % (hook['function'], body.count(hook['anchor'])))
        apos = fstart + body.index(hook['anchor'])
        if hook['where'] == 'after':
            apos += len(hook['anchor'])
        else:
            line_start = text.rfind(nl, 0, apos) + len(nl)
            if text[line_start:apos].strip():
                raise ValueError('"before" anchor must start its line')
            apos = line_start - len(nl)  # end of the previous line
        if apos < ins:
            raise ValueError('hook precedes includes')
        edits.append((apos, nl + '    ' + hook['call'] + HOOK_TAG))
    block_nl = nl.join(block.replace('\r\n', '\n').split('\n'))
    edits.append((ins, nl + BEGIN + nl + block_nl.rstrip() + nl + END))
    out = text
    for pos, ins_text in sorted(edits, key=lambda e: -e[0]):
        out = out[:pos] + ins_text + out[pos:]
    return out


NEW_CATALOG = '<?xml version="1.0" encoding="us-ascii"?>' + chr(13) + chr(10) + '<Catalog>' + chr(13) + chr(10) + '</Catalog>' + chr(13) + chr(10)


def patch_unitdata(text, fragment):
    """Insert a catalog override before </Catalog>. Pure; raises ValueError.

    Refuses when the map already defines any entry the fragment defines (indices could clash)."""
    if XML_BEGIN in text:
        raise ValueError('catalog file already patched')
    for entry_id in re.findall(r'<C\w+ id="(\w+)"', fragment):
        if re.search(r'<C\w+ id="%s"' % entry_id, text):
            raise ValueError('map already overrides %s; refusing to guess' % entry_id)
    if text.count('</Catalog>') != 1:
        raise ValueError('unit data must contain exactly one </Catalog>')
    nl = '\r\n' if '\r\n' in text else '\n'
    frag = nl.join(fragment.replace('\r\n', '\n').rstrip('\n').split('\n'))
    return text.replace('</Catalog>', XML_BEGIN + nl + frag + nl + XML_END + nl + '</Catalog>')


def unpatch_unitdata(text):
    return re.sub(re.escape(XML_BEGIN) + r'.*?' + re.escape(XML_END) + r'\r?\n', '', text, flags=re.S)


def patch_strings(text, key, value=None):
    """Append key=value lines (marked) to a GameStrings.txt: either one key and value, or a list of
    (key, value) pairs as `key`. Pure; raises ValueError."""
    entries = key if isinstance(key, list) else [(key, value)]
    if TXT_BEGIN in text:
        raise ValueError('string table already patched')
    for k, _ in entries:
        if re.search(r'^' + re.escape(k) + '=', text, re.M):
            raise ValueError('string key %s already exists' % k)
    nl = '\r\n' if '\r\n' in text else '\n'
    if not text.endswith(nl):
        raise ValueError('string table does not end with a line break; refusing to guess')
    return text + TXT_BEGIN + nl + ''.join('%s=%s%s' % (k, v, nl) for k, v in entries) + TXT_END + nl


def unpatch_strings(text):
    return re.sub(re.escape(TXT_BEGIN) + r'.*?' + re.escape(TXT_END) + r'\r?\n', '', text, flags=re.S)


def profile_texts(cfg):
    """{locale: text} shown at the mission start; Russian for ruRU, English for everything else."""
    p = cfg.get('profile')
    if not p:
        return {}
    return {'ruRU': p['message'], 'enUS': p.get('message_en', p['message'])}


def text_entries(cfg):
    """{locale: [(key, value)]}: the profile message plus the texts of the tactical module."""
    out = {loc: [(PROFILE_KEY, v)] for loc, v in profile_texts(cfg).items()}
    t = cfg.get('tactical')
    if t:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in TAC_TEXT_KEYS:
                v = t['texts'][k][lang].replace('{aim_time}', '%g' % t['nuke']['aim_time']).replace('{flight_time}', '%g' % t['nuke']['flight_time'])
                out.setdefault(loc, []).append((TAC_TEXT_PREFIX + k, v))
    hs = cfg.get('hanson')
    if hs:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in HANSON_TEXT_KEYS:
                out.setdefault(loc, []).append((HANSON_TEXT_PREFIX + k, hs['texts'][k][lang]))
    sc = cfg.get('scene')
    if sc:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in SCENE_TEXT_KEYS:
                out.setdefault(loc, []).append((SCENE_TEXT_PREFIX + k, sc['texts'][k][lang]))
    return out


def build_block(adapter, cfg):
    core = read(os.path.join(ROOT, 'core', 'GhostOpsCore.galaxy'), 'r')
    ad = read(os.path.join(ROOT, adapter['adapter_source']), 'r')
    mods = adapter.get('modules') or []
    gens = adapter.get('generators', ['tactical'] if adapter.get('modules') and not adapter.get('ce0') else [])
    extra = ''
    if mods:
        extra = '\n'.join(read(os.path.join(ROOT, m), 'r').rstrip() + '\n' for m in mods) + '\n'
    if 'tactical' in gens:
        extra += gen_tactical_test(cfg) + '\n' + gen_tactical(cfg) + '\n'
    if 'hanson' in gens:
        extra += gen_hanson_test(cfg) + '\n' + gen_hanson(cfg) + '\n'
    if cfg.get('scene'):
        extra += gen_scene(cfg) + '\n'
    if cfg.get('ce0'):
        extra += gen_ce0(cfg) + '\n'
    return core.rstrip() + '\n\n' + gen_config(cfg) + '\n' + extra + ad


def needs_nova_patch(cfg):
    return 'Nova' in cfg['operatives']['squad']


def load_adapter(mission):
    return load_json('adapters/%s/adapter.json' % mission)


class ConfigError(ValueError):
    pass


def deep_merge(base, over):
    out = json.loads(json.dumps(base))
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def preset_names(raw):
    return list(raw.get('presets', {}))


def resolve_config(adapter, preset=None, diag=False):
    """Returns (merged config, preset name or None). Missions without presets ignore nothing: an explicit
    preset for them is an error, an unknown preset name is an error (never a silent fallback)."""
    raw = load_json(adapter['config'])
    presets = raw.get('presets')
    if presets is None:
        if preset:
            raise ConfigError('mission %s has no presets (got --preset %s)' % (adapter['mission'], preset))
        cfg, name = raw, None
    else:
        name = preset or raw.get('default_preset')
        if name not in presets:
            raise ConfigError('unknown preset "%s" for %s; available: %s' % (name, adapter['mission'], ', '.join(presets)))
        base = {k: v for k, v in raw.items() if k not in ('presets', 'default_preset')}
        parent = presets[name].get('extends')
        if parent is not None and parent not in presets:
            raise ConfigError('preset "%s" extends unknown preset "%s"' % (name, parent))
        cfg = deep_merge(base, presets[parent].get('overrides', {})) if parent else base
        cfg = deep_merge(cfg, presets[name].get('overrides', {}))
        cfg['profile'] = {'name': name, 'label': presets[name]['label'], 'message': presets[name]['message'],
                          'message_en': presets[name].get('message_en', presets[name]['message'])}
    if diag:
        cfg = deep_merge(cfg, {'difficulty': {'show_message': True}})
    return cfg, name


def apply_ce0(adapter, cfg):
    """Development only: a resolved config with the key "ce0" adds the probe module, the mission's probe extras and the probe hooks to a
    COPY of the adapter. Without the key the adapter is returned untouched, so no playable build can contain any of it."""
    if not cfg.get('ce0'):
        return adapter
    a = json.loads(json.dumps(adapter))
    a['generators'] = adapter.get('generators', ['tactical'] if adapter.get('modules') else [])
    a['modules'] = list(adapter.get('modules') or []) + ['core/GhostOpsCe0.galaxy', adapter['ce0_extra']]
    a['extra_hooks'] = list(adapter.get('extra_hooks', [])) + list(adapter.get('ce0_hooks', []))
    a['ce0'] = True
    return a


def context(args):
    adapter = load_adapter(args.mission)
    cfg, preset = resolve_config(adapter, getattr(args, 'preset', None), getattr(args, 'diag', False))
    return apply_ce0(adapter, cfg), cfg, preset


def key_for(adapter, preset):
    return adapter['mission'] + ('_' + preset if preset else '')


def output_name(adapter, preset):
    name = adapter['output_map_file']
    if not preset:
        return name
    stem, ext = os.path.splitext(name)
    return '%s_%s%s' % (stem, preset, ext)


def paths(adapter, source=None, preset=None):
    src = source or os.path.join(ROOT, 'tmp', 'source', adapter['source_map_file'])
    out = os.path.join(ROOT, 'dist', output_name(adapter, preset))
    return src, out


def build_manifest_path(key):
    return os.path.join(ROOT, 'build', 'last_build_%s.json' % key)


def install_manifest_path(key):
    return os.path.join(ROOT, 'build', 'install_%s.json' % key)


def cmd_build(args):
    adapter, cfg, preset = context(args)
    if args.multiplier is not None:
        cfg['base_support']['damage_multiplier'] = args.multiplier
    errs = validate_config(cfg)
    if errs:
        print('CONFIG INVALID:\n  ' + '\n  '.join(errs))
        return 2
    src, out = paths(adapter, args.source, preset)
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
    if not block.isascii():
        print('GALAXY SOURCE MUST BE ASCII (a non-ASCII literal breaks the compile): put texts into the string table')
        return 3
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
        'preset': preset,
        'label': cfg.get('profile', {}).get('label'),
        'diag': bool(args.diag) if hasattr(args, 'diag') else False,
        'snipe_cooldown': cfg.get('ghost_tuning', {}).get('snipe', {}).get('cooldown', 0) if cfg.get('ghost_tuning') else None,
        'squad': cfg['operatives']['squad'],
        'tactical': bool(cfg.get('tactical')),
        'damage_multiplier': cfg['base_support']['damage_multiplier'],
        'invulnerable_allies': cfg['experimental']['invulnerable_allies'],
    }
    manifest['catalog_patches'] = []
    new_members = []
    for fname, fragment in catalog_fragments(cfg).items():
        member = GAMEDATA + fname
        old = arc.read(member)
        created = old is None
        old_text = NEW_CATALOG if created else old.decode('utf-8-sig')
        new_text = patch_unitdata(old_text, fragment)
        ET.fromstring(new_text.encode('utf-8'))  # must stay well-formed
        bom = b'\xef\xbb\xbf' if (not created and old.startswith(b'\xef\xbb\xbf')) else b''
        arc.set_file(member, bom + new_text.encode('utf-8'))
        if created:
            new_members.append(member)
        manifest['catalog_patches'].append({'member': member, 'created': created,
                                            'original_sha256': None if created else sha256(old)})
    manifest['audio'] = []
    for cid, srcfile, member in audio_clips(cfg):
        wav = read(srcfile)
        arc.set_file(member, wav)
        new_members.append(member)
        manifest['audio'].append({'id': cid, 'member': member, 'source': os.path.relpath(srcfile, ROOT).replace(chr(92), '/'), 'sha256': sha256(wav)})
    if new_members:
        arc.update_listfile(new_members)
    manifest['text_patches'] = []
    for loc, entries in text_entries(cfg).items():
        member = loc + '.SC2Data' + chr(92) + 'LocalizedData' + chr(92) + 'GameStrings.txt'
        old = arc.read(member)
        if old is None:
            continue
        new_text = patch_strings(old.decode('utf-8-sig'), entries)
        bom = b'\xef\xbb\xbf' if old.startswith(b'\xef\xbb\xbf') else b''
        arc.set_file(member, bom + new_text.encode('utf-8'))
        manifest['text_patches'].append({'member': member, 'locale': loc, 'keys': [k for k, _ in entries]})
    if (cfg.get('profile') or cfg.get('tactical')) and not manifest['text_patches']:
        print('the map has no GameStrings.txt for the profile text')
        return 2
    arc.drop_attributes()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    built = arc.tobytes()
    with open(out, 'wb') as f:
        f.write(built)
    manifest['output_sha256'] = sha256(built)
    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    with open(build_manifest_path(key_for(adapter, preset)), 'w') as f:
        json.dump(manifest, f, indent=2)
    if sha256(read(src)) != src_hash:
        print('SOURCE MAP CHANGED DURING BUILD - this must never happen')
        return 4
    print('built %s (%d bytes)\n  profile: %s | sha256 %s\n  source unchanged: %s' % (out, len(built), manifest['label'] or 'none', manifest['output_sha256'], src_hash))
    if cfg.get('ghost_tuning'):
        gt = cfg['ghost_tuning']
        print('  ghost: energy %g/%g, regen +%g/s, cloak start %g, net under cloak %g/s | Snipe cost %g, damage %g, cast %g s, cooldown %g s (per unit)' % (
            gt['energy_start'], gt['energy_max'], gt['regen_per_second'], gt['cloak_activation_cost'], gt['cloak_net_per_second'],
            gt['snipe']['cost'], gt['snipe']['damage'], gt['snipe']['cast_time'], gt['snipe'].get('cooldown', 0)))
    return cmd_verify(args)


def cmd_verify(args):
    adapter, cfg, preset = context(args)
    src, out = paths(adapter, args.source, preset)
    man_path = build_manifest_path(key_for(adapter, preset))
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
    patches = man.get('catalog_patches')
    if patches is None:  # manifests written before generic catalog patches
        patches = [{'member': UNITDATA, 'created': False}] if man.get('nova_fire_control_patch') else []
    existing = [p_['member'].lower() for p_ in patches if not p_['created']]
    tpatches = man.get('text_patches', [])
    expected = [man['script_member'].lower()] + existing + [t_['member'].lower() for t_ in tpatches]
    check('only %s differ from source (differs: %s)' % (expected, changed), changed == sorted(expected))
    created = sorted([p_['member'].lower() for p_ in patches if p_['created']] + [x['member'].lower() for x in man.get('audio', [])])
    added = sorted(n.lower() for n in a_out.names() if not n.startswith('(') and n.lower() not in [x.lower() for x in a_src.names()])
    check('files added to the map: %s' % created, added == created)
    for x in man.get('audio', []):
        got = a_out.read(x['member'])
        check('audio %s: %s is the project file (sha256 %s...)' % (x['id'], x['member'], x['sha256'][:8]), got is not None and sha256(got) == x['sha256'] and got[:4] == b'RIFF')
    new = a_out.read(man['script_member']).decode('utf-8-sig')
    n_hooks = len(hook_list(adapter))
    check('%d hook call(s) present, once each' % n_hooks, new.count(HOOK_TAG) == n_hooks)
    check('tactical module state matches manifest (%s)' % man.get('tactical', False),
          ('go_tacEnabled = true;' in new) == bool(man.get('tactical', False)) or 'GhostOps_ApplyTacticalConfig' not in new)
    check('config in script matches manifest (multiplier %s, invulnerable %s, squad %s)' % (man['damage_multiplier'], man['invulnerable_allies'], man['squad']),
          ('go_cfgDamageMultiplier = %d;' % man['damage_multiplier']) in new
          and ('go_cfgInvulnerableAllies = %s;' % ('true' if man['invulnerable_allies'] else 'false')) in new
          and ('go_cfgSquadSize = %d;' % len(man['squad'])) in new)
    check('Ghost Ops block present exactly once', new.count(BEGIN) == 1 and new.count(END) == 1)
    orig = a_src.read(man['script_member']).decode('utf-8-sig')
    stripped = re.sub(r'\r?\n' + re.escape(BEGIN) + r'.*?' + re.escape(END), '', new, flags=re.S)
    stripped = re.sub(r'\r?\n    [^\n]*' + re.escape(HOOK_TAG), '', stripped)
    check('removing our additions restores the original script text exactly', stripped == orig)
    check('all scenario functions of the original are kept', all(f in new for f in re.findall(r'^bool (gt_\w+_Func)', orig, re.M)))
    for p_ in patches:
        new_t = a_out.read(p_['member']).decode('utf-8-sig')
        root = ET.fromstring(new_t.encode('utf-8'))
        if p_['created']:
            check('%s created, well-formed, holds only our entries' % p_['member'], unpatch_unitdata(new_t) == NEW_CATALOG)
        else:
            old_t = a_src.read(p_['member']).decode('utf-8-sig')
            check('%s well-formed and restores exactly' % p_['member'], unpatch_unitdata(new_t) == old_t)
        if p_['member'] == UNITDATA and any(u.get('id') == 'Nova' for u in root.iter('CUnit')):
            nova = [u for u in root.iter('CUnit') if u.get('id') == 'Nova']
            check('Nova override adds exactly hold fire / weapons free', len(nova) == 1 and sorted(e.get('Link') for e in nova[0].iter('AbilArray')) == ['GhostHoldFire', 'GhostWeaponsFree'])
    if not patches:
        check('no catalog files touched', True)
    for t_ in tpatches:
        new_t = a_out.read(t_['member']).decode('utf-8-sig')
        old_t = a_src.read(t_['member']).decode('utf-8-sig')
        keys = t_.get('keys') or [PROFILE_KEY]
        check('%s: %d text(s) added, restores exactly' % (t_['member'], len(keys)), unpatch_strings(new_t) == old_t and all((k + '=') in new_t for k in keys))
    check('script source is ASCII', new.isascii())
    print('VERIFY ' + ('PASSED' if ok else 'FAILED'))
    return 0 if ok else 5


def sc2_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq SC2_x64.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    return 'SC2_x64.exe' in out


def install_key(adapter, preset, args):
    _, out = paths(adapter, None, preset)
    if cmd_verify(args) != 0:
        print('refusing to install an unverified build')
        return 5
    dest_dir = os.path.join(SC2_DIR, 'Maps', 'GhostOps')
    dest = os.path.join(dest_dir, output_name(adapter, preset))
    mp = install_manifest_path(key_for(adapter, preset))
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


def cmd_install(args):
    adapter, cfg, preset = context(args)
    return install_key(adapter, preset, args)


def uninstall_key(key, label):
    mp = install_manifest_path(key)
    if not os.path.exists(mp):
        print('nothing installed by this project for %s' % label)
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
    print('rolled back %s' % label)
    return 0


def cmd_uninstall(args):
    adapter, cfg, preset = context(args)
    return uninstall_key(key_for(adapter, preset), key_for(adapter, preset))


def launch_command(adapter, cfg, preset):
    dest = os.path.join(SC2_DIR, 'Maps', 'GhostOps', output_name(adapter, preset))
    diff = cfg['difficulty']['expected']
    return '"%s" -run "%s" -difficulty %d -displaymode 2' % (os.path.join(SC2_DIR, 'Support64', 'SC2Switcher_x64.exe'), dest, diff), dest


def ensure_installed(args):
    """Install the built map of the chosen profile if the installed copy is missing or different. Never touches a running game."""
    adapter, cfg, preset = context(args)
    key = key_for(adapter, preset)
    if sc2_running():
        print('StarCraft II is already running: close it first (this launcher never closes your game).')
        return 7
    legacy = install_manifest_path(adapter['mission'])
    if preset and os.path.exists(legacy):  # an unnamed build from before profiles existed must not linger
        uninstall_key(adapter['mission'], adapter['mission'] + ' (old unnamed build)')
    _, out = paths(adapter, None, preset)
    mp = install_manifest_path(key)
    if os.path.exists(mp):
        rec = json.loads(read(mp, 'r'))
        if os.path.exists(rec['file']) and sha256(read(rec['file'])) == sha256(read(out)):
            print('already installed and identical: %s' % rec['file'])
            return 0
        rc = uninstall_key(key, key)
        if rc != 0:
            return rc
    return install_key(adapter, preset, args)


def prepare(args, progress=None):
    """Build the requested profile and make sure exactly that build is installed.
    `progress(stage)` is called with 'check', 'build', 'verify', 'install' as the real steps begin."""
    note = progress or (lambda stage: None)
    note('check')
    if sc2_running():
        print('StarCraft II is already running: close it first (this launcher never closes your game).')
        return 7
    note('build')
    rc = cmd_build(args)
    if rc != 0:
        return rc
    note('verify')
    rc = cmd_verify(args)
    if rc != 0:
        return rc
    note('install')
    return ensure_installed(args)


def start_detached(command):
    """Start SC2 outside this process tree (it survives the launcher closing)."""
    ps = "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = '%s'; CurrentDirectory = '%s' } | Out-Null" % (
        command.replace("'", "''"), os.path.join(SC2_DIR, 'Support64'))
    return subprocess.run(['powershell', '-NoProfile', '-Command', ps]).returncode


def cmd_launch(args):
    adapter, cfg, preset = context(args)
    command, dest = launch_command(adapter, cfg, preset)
    has_presets = 'presets' in load_json(adapter['config'])
    if args.print_only or not (has_presets or args.start):
        print(command)
        return 0
    rc = prepare(args)
    if rc != 0:
        return rc
    if not os.path.isfile(dest):
        print('expected installed map is missing: %s' % dest)
        return 8
    print('starting %s' % (cfg.get('profile', {}).get('label') or adapter['mission']))
    return start_detached(command)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'verify', 'install', 'uninstall', 'launch'])
    p.add_argument('--mission', default='traynor02')
    p.add_argument('--source')
    p.add_argument('--preset', help='balance profile of the mission (TRaynor01: easy, hard); default: the mission default')
    p.add_argument('--diag', action='store_true', help='show the detailed in-game diagnostic message in this build')
    p.add_argument('--print-only', dest='print_only', action='store_true', help='launch: only print the SC2 command')
    p.add_argument('--start', action='store_true', help='launch: prepare and start the game also for missions without profiles')
    p.add_argument('--multiplier', type=int, choices=[1, 2, 3], help='override base_support.damage_multiplier for this build')
    args = p.parse_args(argv)
    try:
        return globals()['cmd_' + args.command](args)
    except ConfigError as e:
        print('error: %s' % e)
        return 2


if __name__ == '__main__':
    sys.exit(main())
