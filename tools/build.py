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
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc2mpq  # noqa: E402
import isolation  # noqa: E402
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
HOTKEY_PREFIX = 'Button/Hotkey/'
CRLF = chr(13) + chr(10)
UTF8_BOM = bytes([0xef, 0xbb, 0xbf])
TXT_BEGIN = '// GHOSTOPS BEGIN'
TXT_END = '// GHOSTOPS END'
# Index of each ability in the standard Ghost's AbilArray (Liberty mod data of client 3.1.4):
# stop 0, attack 1, move 2, GhostCloak 3, Snipe 4, TacNukeStrike 5, GhostHoldFire 6, EMP 7, GhostWeaponsFree 8
GHOST_ABIL_INDEX = {'TacNukeStrike': 5, 'EMP': 7}
TAC_TEXT_PREFIX = 'Param/Value/GhostOpsTac_'
TAC_TEXT_KEYS = ('ZoneLeft', 'RoleSpotter', 'RoleOperative', 'InfoSpotter', 'InfoOperative', 'NukeReady', 'Aiming', 'AimCancelled', 'Launched',
                 'SpotterLost', 'SpotterLostAfter', 'AcademyLost', 'AlertTitle', 'AlertText', 'SwannName', 'SwannText', 'GhostName', 'GhostText', 'ArrivalText',
                 'ObjectiveTitle', 'ObjectiveText', 'Tip1Title', 'Tip1Text', 'Tip2Title', 'Tip2Text', 'Tip3Title', 'Tip3Text', 'Tip4Title', 'Tip4Text', 'AlertClip', 'RaynorName', 'RaynorText', 'SwannExplain', 'GhostExplain', 'RoleGhost', 'InfoGhost')
# Optional texts of the added features (grenade, rebel hints, Raynor's clip subtitle); only written when present in the config
# texts of optional features: a profile that does not define them still gets these (the code that reads them is inert there)
TAC_DEFAULT_TEXTS = {
    'RebelTag': {'ru': 'Повстанец', 'en': 'Rebel'},
    'RebelMedicTag': {'ru': 'Медик повстанцев', 'en': 'Rebel medic'},
    'RebelInfo': {'ru': 'Повстанец', 'en': 'Rebel'},
    'GrenadeEmpty': {'ru': 'Заряды закончились.', 'en': 'No charges left.'},
    'VictoryTitle': {'ru': 'Победа', 'en': 'Victory'},
    'VictoryText': {'ru': 'Уничтожьте вражеское производство.', 'en': 'Destroy the enemy production.'},
    'VictoryLeft': {'ru': 'Осталось: ', 'en': 'Left: '},
}
TAC_EXTRA_TEXT_KEYS = ('RaynorClip', 'GrenadeName', 'GrenadeTip', 'RebelHint1', 'RebelHint2', 'RebelClip', 'FindObjectiveTitle', 'FindObjectiveText',
                       'VictoryTitle', 'VictoryText', 'VictoryLeft', 'RebelTag', 'RebelMedicTag', 'RebelInfo', 'GrenadeEmpty')
# Explanations are shown in a larger style (about +30% over the subtitle area font): <s val="AlertDisplay"> (measured in the game)
EXPLAIN_STYLE = ('<s val=' + chr(34) + 'AlertDisplay' + chr(34) + '>', '</s>')
TAC_EXPLAIN_KEYS = ('AlertText', 'RaynorText', 'SwannExplain', 'GhostExplain', 'RebelHint1', 'RebelHint2')
# With tactical.lines the story texts below live in the line table (tactical.lines[].text) and are no longer required as separate keys
TAC_LINE_REPLACED_KEYS = ('AlertClip', 'AlertText', 'SwannText', 'GhostText', 'RaynorText', 'SwannExplain', 'GhostExplain')
LINE_SPEAKERS = ('raynor', 'swann', 'adjutant', 'ghost')
LINE_TEXT_PREFIX = 'Param/Value/GhostOpsTac_L_'
LINE_MAX = 48
SCENE_EXPLAIN_KEYS = ('Explain', 'Closing')
# AbilArray indexes of the Ghost Academy in the merged campaign data (Liberty mod + Liberty campaign):
# BuildInProgress 0, que5 1, ArmSiloWithNuke 2, GhostAcademyResearch 3, MercCompoundResearch 4, HeroArmNuke 5, SpectreNukeSiloArmMagazine 6
ACADEMY_REMOVED_ABILS = (3, 4, 5, 6)
# Voice clips imported into the map (config key "audio.clips"): the WAV goes to Assets\Sounds\GhostOps\<file name> inside the map archive,
# a CSound entry with the clip id makes it playable with SoundLink("<id>", 0).
AUDIO_DIR = 'Assets' + chr(92) + 'Sounds' + chr(92) + 'GhostOps' + chr(92)
AUDIO_ID = re.compile(r'GhostOps[A-Za-z0-9]{3,40}')
TALK_GROUPS = ('raynor', 'swann', 'horner', 'marine', 'adjutant', 'ghost')  # index = group number of GhostOps_Talk() in core/GhostOpsCore.galaxy
SCENE_TEXT_PREFIX = 'Param/Value/GhostOpsScene_'
HANSON_TEXT_PREFIX = 'Param/Value/GhostOpsH_'
HANSON_TEXT_KEYS = ('BtnPreparing', 'BtnReady', 'BtnActive', 'ReadyMsg', 'SentMsg')
HANSON_ROLES = ('base', 'houses', 'air')
# optional texts of the prepared-detonation variant (containers, gas, HUD, messages); a profile may define any of them, the module reads only what its options need
HANSON_EXTRA_TEXT_KEYS = ('PlaceFarMsg', 'GasSourceLost', 'ContainerTag', 'GasUnit', 'NeedGas', 'FuelPaidMsg', 'FuelShortMsg', 'HudGas', 'HudContainers', 'HudLeft', 'HudOf', 'HudPrice', 'HudFuelPrice', 'HudNoGasForBox', 'HudShort',
                          'KitsTitle', 'KitsOut', 'KitsHint', 'KitsReservedMsg', 'KitsFreedMsg', 'ContainerName', 'ContainerTip', 'ContainerUnitName', 'ContainerInfo', 'PlaceFailGas', 'PlaceFailLimit', 'PlaceFailSpot', 'RaynorName', 'SwannName')
HANSON_TEXT_DEFAULTS = {
    'GasUnit': {'ru': '\u0433\u0430\u0437\u0430', 'en': 'gas'},
    'NeedGas': {'ru': '\u041a\u043e\u043b\u043e\u043d\u043d\u0430 \u0433\u043e\u0442\u043e\u0432\u0430. \u041d\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442 \u0433\u0430\u0437\u0430:', 'en': 'The convoy is ready. Gas missing:'},
}
ZH_TEXT_PREFIX = 'Param/Value/GhostOpsZH_'
ZH_TEXT_KEYS = ('ObjTitle', 'ObjText', 'AllDestroyed', 'RaynorName', 'RaynorText', 'HornerName', 'HornerText', 'HornerWaitText', 'RebelName', 'RebelText', 'RescueText',
                'RaynorClip', 'HornerClip', 'HornerWaitClip', 'RebelClip', 'RebelClipAlt', 'RescueClip', 'RescueClipAlt',
                'Tip1Title', 'Tip1Text', 'Tip2Title', 'Tip2Text', 'Tip3Title', 'Tip3Text')
ZH_ORDER_ITEMS = ('marines', 'bunkers', 'turrets', 'scvs')
# The "defence" variant of TRaynor03 (config key "defence", core/GhostOpsDefence.galaxy)
DEF_TEXT_PREFIX = 'Param/Value/GhostOpsDef_'
DEF_TEXT_KEYS = ('KitsTitle', 'KitsText', 'KitsBunkers', 'KitsTurrets', 'KitsOut', 'LandedFirst', 'LandedRest', 'LandedGhosts', 'SwannName', 'SwannText', 'SalvoHint', 'SalvoName',
                 'SalvoTip', 'RaynorText', 'MattText', 'MattEarly', 'Tip1Title', 'Tip1Text', 'Tip2Title', 'Tip2Text', 'Tip3Title', 'Tip3Text')
DEF_OPTIONAL_TEXT_KEYS = ('ScannerSwann', 'IntroHold')  # texts of optional scenes (the profile that has them lists them; a profile without them is valid)
DEF_EXPLAIN_KEYS = ('SwannText', 'RaynorText', 'MattText', 'MattEarly', 'ScannerSwann', 'IntroHold')
TAIL_BEGIN = '// ==== GHOSTOPS TAIL BEGIN (generated, do not edit) ===='
TAIL_END = '// ==== GHOSTOPS TAIL END ===='
PANEL_TEXT_KEYS = ('Dead', 'Infinite', 'Cloak', 'Seconds', 'Regen', 'Hold', 'Ready', 'Grenades', 'Footer')  # plus Name0 .. Name<squad - 1>
PANEL_TEXT_PREFIX = 'Param/Value/GhostOpsPanel_'
ZH_VOICE_KEYS = ('raynor', 'horner', 'horner_wait', 'rebel', 'rebel_alt', 'rescue', 'rescue_alt')  # index order of go_zhVoiceId
SCENE_TEXT_KEYS = ('RaynorName', 'RaynorLine', 'MarineName', 'MarineBLine', 'MarineALine', 'Explain', 'Closing')


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
    if cfg.get('panel') is not None:
        errs += validate_panel(cfg)
    if cfg.get('audio') is not None:
        errs += validate_audio(cfg['audio'])
    if cfg.get('scene') is not None:
        errs += validate_scene(cfg)
    if cfg.get('hanson') is not None:
        errs += validate_hanson(cfg)
    if cfg.get('ce0') is not None:
        errs += validate_ce0(cfg)
    if cfg.get('campaign') is not None:
        errs += validate_campaign(cfg)
    if cfg.get('zerohour') is not None:
        errs += validate_zerohour(cfg)
    if cfg.get('defence') is not None:
        errs += validate_defence(cfg)
    if cfg.get('detector_analysis'):
        errs += validate_detector_analysis(cfg)
    return errs


def validate_zerohour(cfg):
    """TRaynor03 "Zero Hour" (config key "zerohour", see config/traynor03.json). Every number of the mission is a setting; unknown keys are errors."""
    z = cfg['zerohour']
    errs = []
    if not isinstance(z, dict):
        return ['zerohour must be an object']
    known = {'order', 'limits', 'prices', 'recommended', 'test_budget', 'arrival_minutes', 'targets', 'ping_every', 'ghost_spawn', 'post_arrival', 'scene', 'texts', 'debug_log', 'lock_production', 'voice', 'min'}
    for k in z:
        if k not in known:
            errs.append('zerohour.%s is not supported' % k)
    isint = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    lim = z.get('limits', {})
    mn = z.get('min', {})
    if not isinstance(mn, dict) or set(mn) - set(ZH_ORDER_ITEMS) or any(not isint(v) or v < 0 or v > lim.get(k, -1) for k, v in mn.items()):
        errs.append('zerohour.min must map order items to integers 0..zerohour.limits.<item>')
        mn = {}
    for grp in ('order', 'recommended'):
        o = z.get(grp, {})
        for k in ZH_ORDER_ITEMS:
            if not isint(o.get(k)) or not 0 <= o[k] <= lim.get(k, -1):
                errs.append('zerohour.%s.%s must be an integer 0..zerohour.limits.%s' % (grp, k, k))
            elif o[k] < mn.get(k, 0):
                errs.append('zerohour.%s.%s must be at least zerohour.min.%s (%d)' % (grp, k, k, mn[k]))
        extra = set(o) - set(ZH_ORDER_ITEMS)
        if extra:
            errs.append('zerohour.%s has unsupported items %s' % (grp, sorted(extra)))
    for k in ZH_ORDER_ITEMS:
        if not isint(lim.get(k)) or not 0 <= lim[k] <= 40:
            errs.append('zerohour.limits.%s must be an integer 0..40' % k)
        pr = z.get('prices', {}).get(k, {})
        if not isint(pr.get('minerals')) or not isint(pr.get('gas')) or pr['minerals'] < 0 or pr['gas'] < 0:
            errs.append('zerohour.prices.%s needs non-negative integer minerals and gas' % k)
    tb = z.get('test_budget', {})
    if not isint(tb.get('minerals')) or not isint(tb.get('gas')) or tb['minerals'] < 0 or tb['gas'] < 0:
        errs.append('zerohour.test_budget needs non-negative integer minerals and gas (a budget of standalone tests only, never written into a campaign)')
    if not isinstance(z.get('lock_production'), bool):
        errs.append('zerohour.lock_production must be boolean (no production, building or research during the mission)')
    if z.get('arrival_minutes') != 20:
        errs.append('zerohour.arrival_minutes must be 20 (the constant of the original map; other values are not supported yet)')
    t = z.get('targets')
    if not isinstance(t, list) or not 1 <= len(t) <= 12 or any(not isint(x) or not 0 < x < 100000 for x in t) or len(set(t)) != len(t):
        errs.append('zerohour.targets must be 1..12 distinct object ids of the map')
    if not _num(z.get('ping_every')) or not 10 <= z['ping_every'] <= 600:
        errs.append('zerohour.ping_every must be 10..600 (game seconds)')
    gs = z.get('ghost_spawn')
    if not (isinstance(gs, list) and len(gs) == 2 and all(_num(v) and 0 <= v <= 255 for v in gs)):
        errs.append('zerohour.ghost_spawn must be [x, y]')
    pa = z.get('post_arrival', {})
    if not _num(pa.get('interval')) or not 20 <= pa.get('interval', 0) <= 1200:
        errs.append('zerohour.post_arrival.interval must be 20..1200 (game seconds)')
    if not isint(pa.get('max_active_units')) or not 0 <= pa.get('max_active_units', -1) <= 400:
        errs.append('zerohour.post_arrival.max_active_units must be an integer 0..400')
    for k in ('zerglings', 'hydralisks', 'roaches'):
        if not isint(pa.get(k)) or not 0 <= pa[k] <= 40:
            errs.append('zerohour.post_arrival.%s must be an integer 0..40' % k)
    sc = z.get('scene', {})
    for k, (lo, hi) in {'intro_delay': (1, 120), 'horner_delay': (0, 120), 'raynor_seconds': (3, 40), 'horner_seconds': (3, 40), 'rebel_seconds': (3, 40)}.items():
        if not _num(sc.get(k)) or not lo <= sc[k] <= hi:
            errs.append('zerohour.scene.%s must be a number in %s..%s' % (k, lo, hi))
    vo = z.get('voice', {})
    if not isinstance(vo, dict) or set(vo) != set(ZH_VOICE_KEYS):
        errs.append('zerohour.voice must have exactly the keys %s' % (ZH_VOICE_KEYS,))
    else:
        ids = {c['id'] for c in (cfg.get('audio') or {}).get('clips', [])}
        for k in ZH_VOICE_KEYS:
            v = vo[k]
            if not isinstance(v, dict) or not _num(v.get('seconds')) or not 0.5 <= v['seconds'] <= 20:
                errs.append('zerohour.voice.%s.seconds must be a number 0.5..20 (the length of the subtitle step)' % k)
            if not isinstance(v, dict) or (v.get('clip') not in ids and not cfg.get('_no_voice')):
                errs.append('zerohour.voice.%s.clip must name a clip from audio.clips' % k)
    texts = z.get('texts', {})
    if set(texts) != set(ZH_TEXT_KEYS):
        errs.append('zerohour.texts must have exactly the keys %s' % (ZH_TEXT_KEYS,))
    for k in ZH_TEXT_KEYS:
        v = texts.get(k)
        if not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and chr(10) not in v[l] for l in ('ru', 'en')):
            errs.append('zerohour.texts.%s needs non-empty single-line ru and en texts' % k)
    return errs


def validate_defence(cfg):
    """TRaynor03 "defence" variant (config key "defence"). Every number of the variant is a setting; unknown keys are errors."""
    d = cfg['defence']
    errs = []
    if not isinstance(d, dict):
        return ['defence must be an object']
    for k in d:
        if k not in ('landing', 'salvo', 'waves', 'scenes', 'texts', 'debug_log'):
            errs.append('defence.%s is not supported' % k)
    if cfg.get('zerohour') is None or not cfg['zerohour'].get('lock_production'):
        errs.append('defence needs zerohour with lock_production true')
    if cfg['zerohour'].get('min', {}).get('marines', 0) < 6:
        errs.append('defence needs zerohour.min.marines >= 6 (the first six marines belong to the paid order)')
    ln = d.get('landing', {})
    if not (isinstance(ln.get('point'), list) and len(ln['point']) == 2 and all(_num(v) and 0 <= v <= 255 for v in ln['point'])):
        errs.append('defence.landing.point must be [x, y]')
    for k, (lo, hi) in {'first_at': (1, 600), 'rest_at': (1, 900), 'ghosts_at': (1, 900)}.items():
        if not _num(ln.get(k)) or not lo <= ln[k] <= hi:
            errs.append('defence.landing.%s must be a number %s..%s (game seconds after the start of control)' % (k, lo, hi))
    sv = d.get('salvo', {})
    for k, (lo, hi) in {'range': (3, 20), 'interval': (0.1, 3), 'radius': (0.5, 6), 'damage': (1, 400), 'cooldown': (1, 300)}.items():
        if not _num(sv.get(k)) or not lo <= sv[k] <= hi:
            errs.append('defence.salvo.%s must be a number %s..%s' % (k, lo, hi))
    if not isinstance(sv.get('missiles'), int) or isinstance(sv.get('missiles'), bool) or not 1 <= sv['missiles'] <= 12:
        errs.append('defence.salvo.missiles must be an integer 1..12')
    if 'hotkey' in sv and not (isinstance(sv['hotkey'], str) and len(sv['hotkey']) == 1 and sv['hotkey'].isalpha() and sv['hotkey'].isupper()):
        errs.append('defence.salvo.hotkey must be one capital letter (the standard-layout hotkey of the button)')
    if 'spread' in sv and (not _num(sv['spread']) or not 0 <= sv['spread'] <= 6):
        errs.append('defence.salvo.spread must be a number 0..6 (radius of the circle of impact points; 0 = every missile hits the centre)')
    if _num(sv.get('radius')) and _num(sv.get('spread', 0)) and sv.get('radius', 0) + sv.get('spread', 0) > 8:
        errs.append('defence.salvo.radius + spread (the whole area the pointer shows) must not exceed 8')
    wv = d.get('waves', {})
    if not _num(wv.get('power')) or not 1 <= wv['power'] <= 2:
        errs.append('defence.waves.power must be 1 (share) or 2 (share squared)')
    if wv.get('rounding') not in ('down', 'nearest', 'up'):
        errs.append('defence.waves.rounding must be down, nearest or up')
    sc = d.get('scenes', {})
    for k, (lo, hi) in {'raynor_at': (0, 600), 'raynor_seconds': (3, 30), 'matt_at': (0, 1200), 'matt_seconds': (3, 30), 'swann_delay': (0, 120), 'swann_seconds': (3, 30), 'reveal_seconds': (1, 30), 'reveal_radius': (2, 12)}.items():
        if not _num(sc.get(k)) or not lo <= sc[k] <= hi:
            errs.append('defence.scenes.%s must be a number %s..%s' % (k, lo, hi))
    for k, (lo, hi) in {'scanner_delay': (0, 120), 'scanner_seconds': (3, 30), 'intro_seconds': (3, 30), 'raynor_wait_timers': (0, 1)}.items():
        if k in sc and (not _num(sc[k]) or not lo <= sc[k] <= hi):
            errs.append('defence.scenes.%s must be a number %s..%s' % (k, lo, hi))
    texts = d.get('texts', {})
    if set(texts) - set(DEF_OPTIONAL_TEXT_KEYS) != set(DEF_TEXT_KEYS):
        errs.append('defence.texts must have exactly the keys %s (and may add %s)' % (DEF_TEXT_KEYS, DEF_OPTIONAL_TEXT_KEYS))
    for k in DEF_TEXT_KEYS + tuple(k for k in DEF_OPTIONAL_TEXT_KEYS if k in texts):
        v = texts.get(k)
        if not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and chr(10) not in v[l] for l in ('ru', 'en')):
            errs.append('defence.texts.%s needs non-empty single-line ru and en texts' % k)
    return errs


def validate_detector_analysis(cfg):
    """The passive Ghost ability "Detector analysis" (config key "detector_analysis"): the circles of the detection range of the VISIBLE enemy detectors while a Ghost is selected.
    Reuses the Hero Detector Radar of the Liberty campaign data (the Nova / Tosh / Zeratul mechanic): behavior HeroDetectorRadar on the Ghost."""
    d = cfg['detector_analysis']
    errs = []
    if not isinstance(d, dict):
        return ['detector_analysis must be an object']
    for k in d:
        if k not in ('enabled', 'texts', 'column', 'row', 'debug_ring'):
            errs.append('detector_analysis.%s is not supported' % k)
    if not isinstance(d.get('enabled'), bool):
        errs.append('detector_analysis.enabled must be true or false')
    for k, hi in (('row', 2), ('column', 4)):
        if k in d and not (isinstance(d[k], int) and not isinstance(d[k], bool) and 0 <= d[k] <= hi):
            errs.append('detector_analysis.%s must be an integer 0..%d (the place of the passive icon on the Ghost card)' % (k, hi))
    texts = d.get('texts', {})
    if set(texts) != {'Name', 'Tip'}:
        errs.append('detector_analysis.texts must have exactly Name and Tip')
    for k in ('Name', 'Tip'):
        v = texts.get(k)
        if not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and chr(10) not in v[l] for l in ('ru', 'en')):
            errs.append('detector_analysis.texts.%s needs non-empty single-line ru and en texts' % k)
    if d.get('enabled') and not cfg.get('ghost_tuning'):
        errs.append('detector_analysis needs ghost_tuning (the Ghost override of this mission)')
    return errs


def detector_analysis_fragments(d):
    """Catalog overrides (map local): a passive icon on the Ghost card and the range actors GhostOpsDetRange10/11/12 that draw the circle of the behavior Detector1x on the units that
    carry the stock buff HeroDetectorRadarDetected (applied by core/GhostOpsDetector.galaxy while a Ghost is selected, to VISIBLE enemy detectors only)."""
    nl = chr(10)
    row, col = d.get('row', 1), d.get('column', 4)
    return {
        'UnitData.xml': nl.join(['    <CUnit id="Ghost">', '        <CardLayouts index="0">',
                                  '            <LayoutButtons Face="GhostOpsDetectorAnalysis" Type="Passive" Row="%d" Column="%d"/>' % (row, col), '        </CardLayouts>', '    </CUnit>', '']),
        'ActorData.xml': nl.join(sum([['    <CActorRange id="GhostOpsDetRange%d">' % n, '        <Behavior value="Detector%d"/>' % n, '        <Terms value="Cap 1"/>', '        <IconArcLength value="0.450000"/>',  # dense: the stock value 1.25 draws a sparse, hardly visible dotted circle
                                         '        <IconTint value="255,60,30,255"/>',
                                         '        <On Terms="Behavior.HeroDetectorRadarDetected.On; ValidateUnit HasDetector%d" Send="Create"/>' % n,
                                         '        <On Terms="Behavior.HeroDetectorRadarDetected.Off" Send="Destroy"/>', '    </CActorRange>'] for n in (10, 11, 12)], [])
                              + (['    <CActorRange id="GhostOpsDetTestRing">', '        <Range value="5"/>', '        <On Terms="Behavior.HeroDetectorRadar.On" Send="Create"/>', '        <On Terms="Behavior.HeroDetectorRadar.Off" Send="Destroy"/>', '    </CActorRange>'] if d.get('debug_ring') else []) + ['']),
        'ButtonData.xml': nl.join(['    <CButton id="GhostOpsDetectorAnalysis">', '        <Icon value="Assets' + chr(92) + 'Textures' + chr(92) + 'btn-status-radar.dds"/>',
                                    '        <EditorCategories value="Race:Terran"/>', '    </CButton>', '']),
    }


def gen_defence(cfg, adapter=None):
    """GhostOps_ApplyDefenceConfig() and, in a build without the "defence" key, the stubs the zerohour module calls."""
    d = cfg.get('defence')
    nl = chr(10)
    if not d:
        return nl.join(['// no defence variant in this build (stubs)', 'void GhostOps_ApplyDefenceConfig () {', '    go_defEnabled = false;', '}', '', 'void GhostOps_DEF_Start () {', '}', '',
                        'void GhostOps_DEF_ApplyStock () {', '}', '', 'int GhostOps_DEF_Scale (int lp_player, int lp_qty) {', '    return lp_qty;', '}', '',
                        'int GhostOps_DEF_PostSide (int lp_start) {', '    return 2 + (lp_start % 3);', '}', ''])
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    ln, sc, wv = d['landing'], d['scenes'], d['waves']
    lines = ['// Generated defence configuration', 'void GhostOps_ApplyDefenceConfig () {', '    go_defEnabled = true;', '    go_defDebug = %s;' % b(d.get('debug_log')),
             '    go_defLandX = %.4f;' % ln['point'][0], '    go_defLandY = %.4f;' % ln['point'][1],
             '    go_defLandAt[0] = %.1f;' % ln['first_at'], '    go_defLandAt[1] = %.1f;' % ln['rest_at'], '    go_defLandAt[2] = %.1f;' % ln['ghosts_at'],
             '    go_defRaynorAt = %.1f;' % sc['raynor_at'], '    go_defRaynorLen = %.1f;' % sc['raynor_seconds'], '    go_defMattAt = %.1f;' % sc['matt_at'],
             '    go_defMattLen = %.1f;' % sc['matt_seconds'], '    go_defRevealSec = %.1f;' % sc['reveal_seconds'], '    go_defRevealRadius = %.1f;' % sc['reveal_radius'], '    go_defSwannDelay = %.1f;' % sc['swann_delay'], '    go_defSwannLen = %.1f;' % sc['swann_seconds'],
             '    go_defPower = %.1f;' % wv['power'], '    go_defRound = %d;' % {'down': 0, 'nearest': 1, 'up': 2}[wv['rounding']], '}', '']
    lines.insert(lines.index('}'), '    go_defScannerOn = %s;' % b('ScannerSwann' in d['texts']))
    lines.insert(lines.index('}'), '    go_defScannerDelay = %.1f;' % sc.get('scanner_delay', 2))
    lines.insert(lines.index('}'), '    go_defScannerLen = %.1f;' % sc.get('scanner_seconds', 8))
    lines.insert(lines.index('}'), '    go_defIntroOn = %s;' % b('IntroHold' in d['texts']))
    if sc.get('raynor_wait_timers'):  # the intro takes the trigger queue only after the original has started its timers (hook on gt_StartTimers)
        lines.insert(lines.index('}'), '    go_defRaynorAt = 9999.0;')
    lines.insert(lines.index('}'), '    go_defIntroLen = %.1f;' % sc.get('intro_seconds', 7))
    for w in (adapter or {}).get('defence_waves', []):
        lines.append('bool GhostOps_DEF_%s (bool testConds, bool runActions);' % w['function'][3:-5])
    return nl.join(lines)


def defence_wave_tail(text, adapter):
    """The generated copies of the original attack functions (script tail): every number of units of a Zerg base is scaled by the share of its living marked
    Hatcheries (GhostOps_DEF_Scale), the waves are buffered and sent only when something is left (GhostOps_DEF_Send). Nothing else of the original changes."""
    nl = '\r\n' if '\r\n' in text else '\n'
    out = []
    for w in adapter.get('defence_waves', []):
        name, group = w['function'], w['group']
        head = 'bool %s (bool testConds, bool runActions) {' % name
        a = text.find(head)
        if a < 0:
            raise ValueError('defence wave function not found: %s' % name)
        e = text.find(nl + '}', a)
        body = text[a:e + len(nl) + 1]
        short = name[3:-5]
        body = body.replace(head, 'bool GhostOps_DEF_%s (bool testConds, bool runActions) {' % short, 1)
        body = re.sub(r'AIAttackWaveAddUnits4\(', 'GhostOps_DEF_Add4(%d, ' % group, body)
        body = re.sub(r'AIAttackWaveAddWaypoint\(gv_pLAYER0\d_ZERG, ', 'GhostOps_DEF_Wp(%d, ' % group, body)
        body = re.sub(r'AIAttackWaveSend\(gv_pLAYER0(\d)_ZERG, ', r'GhostOps_DEF_Send(\1, ', body)
        for call, grp in (('libNtve_gf_CreateUnitsAtPoint2(', None), ('gf_SpawnNydusUnitsP02West(', 2), ('gf_SpawnNydusUnitsP04East(', 4), ('gf_FirstZergWaveAttackP03(', 3),
                          ('gf_DropPodExpansionZergling(', 0)):
            body = _wrap_first_arg(body, call, grp, group)
        if not w.get('prelude'):
            marker0 = '    if (!runActions) {' + nl + '        return true;' + nl + '    }' + nl
            if body.count(marker0) == 1:
                body = body.replace(marker0, marker0 + nl + '    GhostOps_DEF_Log("attack source runs: %s");' % short + nl)
        if w.get('prelude'):
            marker = '    if (!runActions) {' + nl + '        return true;' + nl + '    }' + nl
            if body.count(marker) != 1:
                raise ValueError('prelude anchor not found in %s' % name)
            body = body.replace(marker, marker + nl + '    ' + w['prelude'] + nl)
        out.append(body.rstrip() + nl)
    return nl.join(out)


def _wrap_first_arg(body, call, grp, default_group):
    """Wraps the first argument of every `call(` into GhostOps_DEF_Scale(group, arg). For libNtve_gf_CreateUnitsAtPoint2 only calls whose owner (4th argument) is a Zerg AI player."""
    res = []
    i = 0
    while True:
        j = body.find(call, i)
        if j < 0:
            res.append(body[i:])
            break
        k = j + len(call)
        depth = 1
        args = []
        start = k
        m = k
        while depth > 0:
            c = body[m]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    args.append(body[start:m])
            elif c == ',' and depth == 1:
                args.append(body[start:m])
                start = m + 1
            m += 1
        g = grp
        ok = True
        if call.startswith('libNtve_gf_CreateUnitsAtPoint2'):
            mo = re.search(r'gv_pLAYER0([234])_ZERG', args[3]) if len(args) > 3 else None
            if mo:
                g = int(mo.group(1))
            elif len(args) > 3 and 'gv_pLAYER05_ZERG_NOAI' in args[3]:
                g = 0
            else:
                ok = False
        if ok:
            first = args[0].strip()
            rest = body[k + len(args[0]):m]
            res.append(body[i:k] + 'GhostOps_DEF_Scale(%d, %s)' % (g, first) + rest)
        else:
            res.append(body[i:m])
        i = m
    return ''.join(res)


def salvo_pattern(n, spread):
    """Impact points of the missiles of one salvo relative to the aimed point: the sunflower pattern (golden angle) inside a circle of radius `spread` - the same points every
    time (no random numbers, nothing to save or to repeat after a load); spread 0 = every missile at the centre."""
    import math
    pts = []
    for k in range(n):
        r = spread * math.sqrt((k + 0.5) / n)
        a = k * 2.399963229728653
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def defence_fragments(d):
    """Catalog overrides of the defence variant (map local): Bunker / Missile Turret are free to build for the kit logic and need only the Command Center, the turret gets
    the manual ground salvo (separate Ghost Ops data; the weapon of every other Missile Turret of the game is not touched)."""
    g = lambda v: '%g' % v  # noqa: E731
    sv = d['salvo']
    nl = chr(10)
    periods = ['            <PeriodicPeriodArray value="0"/>'] + ['            <PeriodicPeriodArray value="%s"/>' % g(sv['interval']) for _ in range(sv['missiles'] - 1)]
    offsets = ['        <PeriodicOffsetArray value="%s,%s"/>' % (g(round(x, 3)), g(round(y, 3))) for x, y in salvo_pattern(sv['missiles'], sv.get('spread', 0))]
    aim = sv['radius'] + sv.get('spread', 0)  # the whole area the pointer shows: the circle of impact points plus the blast radius of one missile
    return {
        'UnitData.xml': nl.join([
            '    <CUnit id="Bunker">', '        <CostResource index="Minerals" value="0"/>', '    </CUnit>',
            '    <CUnit id="MissileTurret">', '        <CostResource index="Minerals" value="0"/>', '        <AbilArray Link="GhostOpsTurretSalvo"/>',
            '        <CardLayouts index="0">',
            # hotkey A: the button takes the place of the stock "Attack" button of the turret card (index 3 of the stock layout of the Liberty data; the `attack` ability stays in the
            # unit, so the automatic fire does not change) and aliases the standard "Attack" hotkey; any other hotkey: an extra button, the stock card stays
            ('            <LayoutButtons index="3" Face="GhostOpsTurretSalvo" Type="AbilCmd" AbilCmd="GhostOpsTurretSalvo,Execute" Row="0" Column="4"/>' if sv.get('hotkey') == 'A'
             else '            <LayoutButtons Face="GhostOpsTurretSalvo" Type="AbilCmd" AbilCmd="GhostOpsTurretSalvo,Execute" Row="1" Column="1"/>'),
            '        </CardLayouts>', '    </CUnit>', '']),
        'AbilData.xml': nl.join([
            '    <CAbilBuild id="TerranBuild">',
            '        <InfoArray index="Build6">', '            <Button Requirements="HaveCommandCenter"/>', '        </InfoArray>',
            '        <InfoArray index="Build7">', '            <Button Requirements="HaveCommandCenter"/>', '        </InfoArray>',
            '    </CAbilBuild>',
            '    <CAbilEffectTarget id="GhostOpsTurretSalvo">', '        <EditorCategories value="Race:Terran,AbilityorEffectType:Units"/>',
            '        <Effect index="0" value="GhostOpsSalvoMain"/>', '        <Range value="%s"/>' % g(sv['range']), '        <Arc value="360"/>', '        <CastIntroTime value="0"/>',
            '        <Flags index="RequireTargetVision" value="1"/>', '        <CursorEffect value="GhostOpsSalvoAim"/>',
            '        <Cost index="0">', '            <Cooldown TimeUse="%s"/>' % g(sv['cooldown']), '        </Cost>',
            '        <CmdButtonArray index="Execute" DefaultButtonFace="GhostOpsTurretSalvo"/>', '    </CAbilEffectTarget>', '']),
        'ActorData.xml': nl.join([
            # the pointer of the ability, the way the Odin's Barrage does it (OdinBarrageCursorModel / CursorSplat / Range): the splat takes its radius from CursorEffect, the range
            # indicator from the ability Range; the explosion model is the stock one of the Odin's Barrage (BarrageModel = the Thor missile impact)
            '    <CActorModel id="GhostOpsSalvoCursorModel" parent="TerranCursorModel" abil="GhostOpsTurretSalvo"/>',
            '    <CActorSplat id="GhostOpsSalvoCursorSplat" parent="TerranCursorSplat" abil="GhostOpsTurretSalvo"/>',
            '    <CActorRange id="GhostOpsSalvoRange" parent="RangeAbil" abil="GhostOpsTurretSalvo"/>',
            '    <CActorModel id="GhostOpsSalvoImpact" parent="ModelAnimationStyleOneShot">', '        <Model value="BarrageModel"/>', '        <HostSiteOps Ops="SOpTargetPoint"/>',
            '        <On Terms="Effect.GhostOpsSalvoSearch.Impact" Send="Create"/>', '    </CActorModel>', '']),
        'ButtonData.xml': nl.join([
            '    <CButton id="GhostOpsTurretSalvo">', '        <Icon value="Assets' + chr(92) + 'Textures' + chr(92) + 'btn-command-attack.dds"/>',
            '        <EditorCategories value="Race:Terran"/>'] + (['        <HotkeyAlias value="Attack"/>'] if sv.get('hotkey') == 'A' else []) + ['    </CButton>', '']),
        'EffectData.xml': nl.join([
            '    <CEffectCreatePersistent id="GhostOpsSalvoMain">', '        <EditorCategories value="Race:Terran"/>', '        <WhichLocation Value="TargetPoint"/>',
            '        <PeriodCount value="%d"/>' % sv['missiles'], '        <PeriodicEffectArray value="GhostOpsSalvoLaunch"/>'] + periods + offsets + ['    </CEffectCreatePersistent>',
            '    <CEffectLaunchMissile id="GhostOpsSalvoLaunch">', '        <EditorCategories value="Race:Terran"/>', '        <ImpactEffect value="GhostOpsSalvoSearch"/>',
            '        <ImpactLocation Value="TargetPoint"/>', '        <AmmoUnit value="LongboltMissileWeapon"/>', '    </CEffectLaunchMissile>',
            '    <CEffectEnumArea id="GhostOpsSalvoSearch">', '        <EditorCategories value="Race:Terran"/>', '        <LaunchLocation Value="TargetPoint"/>', '        <ImpactLocation Value="TargetPoint"/>',
            '        <AreaArray Radius="%s" Effect="GhostOpsSalvoDamage"/>' % g(sv['radius']),
            '        <SearchFilters value="Ground,Visible;Player,Ally,Neutral,Air,Missile,Stasis,Dead,Hidden,Invulnerable"/>', '    </CEffectEnumArea>',
            # only the pointer of the ability reads this effect (CursorEffect): its radius is the whole area of possible damage; it is never executed
            '    <CEffectEnumArea id="GhostOpsSalvoAim">', '        <EditorCategories value="Race:Terran"/>',
            '        <AreaArray Radius="%s" Effect="GhostOpsSalvoDamage"/>' % g(aim),
            '        <SearchFilters value="Ground,Visible;Player,Ally,Neutral,Air,Missile,Stasis,Dead,Hidden,Invulnerable"/>', '    </CEffectEnumArea>',
            '    <CEffectDamage id="GhostOpsSalvoDamage">', '        <EditorCategories value="Race:Terran"/>', '        <Kind value="Splash"/>', '        <Amount value="%s"/>' % g(sv['damage']),
            '        <Flags index="Notification" value="1"/>', '        <ResponseFlags index="Acquire" value="1"/>', '    </CEffectDamage>', '']),
    }


def kits_hint(tk, lang):
    """The text that says which sectors the recommended kits are meant to cover (built from `sectors`, so it never disagrees with the numbers)."""
    parts = ['%s - %d' % (x[lang], x['count']) for x in tk['sectors']]
    head = {'ru': 'Рекомендуется %d комплектов: ', 'en': 'Recommended %d kits: '}[lang] % tk['recommended']
    tail = {'ru': '. Строит СКВ, место выбираете вы.', 'en': '. SCVs build them, you choose the place.'}[lang]
    return head + '; '.join(parts) + tail


def zerohour_cost(cfg, order=None):
    """{'minerals': n, 'gas': n} of an order at the prices of the configuration (a plan can never change a price)."""
    z = cfg['zerohour']
    o = order if order is not None else z['order']
    return {r: sum(int(o[k]) * z['prices'][k][r] for k in ZH_ORDER_ITEMS) for r in ('minerals', 'gas')}


def validate_campaign(cfg):
    """Campaign journal (config key "campaign": see core/GhostOpsCampaign.galaxy and contract section 14)."""
    errs = []
    c = cfg['campaign']
    if not isinstance(c, dict):
        return ['campaign must be a mapping']
    if not isinstance(c.get('operation_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', c.get('operation_id', '')):
        errs.append('campaign.operation_id must be 1..40 characters of [A-Za-z0-9_-]')
    for k in c:
        if k not in ('operation_id', 'bank_name'):
            errs.append('campaign.%s is not supported' % k)
    if 'bank_name' in c:  # a development profile may write its journal into its OWN Bank, so that a test never touches the Owner's campaign Bank
        name = (cfg.get('profile') or {}).get('name', '')
        if not str(name).endswith('_dev') or not re.fullmatch(r'GhostOpsDev[A-Za-z0-9]{1,16}', str(c['bank_name'])):
            errs.append('campaign.bank_name is development only (profile name ending with _dev, value GhostOpsDev<letters>)')
    return errs


def data_hash(cfg):
    """Hash of the settings snapshot a map is built from (the profile label / message do not count). It is baked into the map and written
    into the build manifest, so a result proposal can be tied to exactly that build."""
    snap = json.dumps({k: v for k, v in cfg.items() if k != 'profile'}, sort_keys=True)
    return hashlib.sha256(snap.encode('utf-8')).hexdigest()[:16]


def gen_campaign(cfg):
    """GhostOps_Camp_Apply(): constants of the campaign journal module."""
    c = cfg['campaign']
    return chr(10).join(['// Generated campaign journal configuration', 'void GhostOps_Camp_Apply () {', '    go_cpEnabled = true;', '    go_cpOp = "%s";' % c['operation_id'], '    go_cpBankName = "%s";' % c.get('bank_name', 'GhostOpsCampaign'),
                         '    go_cpMission = "%s";' % cfg['mission'], '    go_cpHash = "%s";' % data_hash(cfg), '}', ''])


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
        if k not in ('operation_id', 'census_types', 'trace'):
            errs.append('ce0.%s is not supported' % k)
    return errs


def gen_ce0(cfg):
    """GhostOps_Ce0_Apply(): constants of the development probe."""
    c = cfg['ce0']
    lines = ['// Generated CE-0 probe configuration (development only)', 'void GhostOps_Ce0_Apply () {',
             '    go_c0Enabled = true;', '    go_c0Op = "%s";' % c['operation_id'], '    go_c0Hash = "%s";' % data_hash(cfg),
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
    if not isinstance(texts, dict) or not set(HANSON_TEXT_KEYS) <= set(texts) or not set(texts) <= set(HANSON_TEXT_KEYS) | set(HANSON_EXTRA_TEXT_KEYS):
        errs.append('hanson.texts must have the keys %s and may have %s' % (HANSON_TEXT_KEYS, HANSON_EXTRA_TEXT_KEYS))
    else:
        for k, v in texts.items():
            if not isinstance(v, dict) or not v.get('ru') or not v.get('en'):
                errs.append('hanson.texts.%s needs "ru" and "en"' % k)
    at = h.get('autotest')
    if at is not None and (not isinstance(at, dict) or at.get('mode') not in (1, 2, 3, 4, 5, 6, 7)):
        errs.append('hanson.autotest.mode must be 1..7')
    tk = h.get('turret_kits')
    if tk is not None:
        if not isinstance(tk, dict) or not isinstance(tk.get('enabled'), bool):
            errs.append('hanson.turret_kits needs enabled (boolean)')
        elif tk['enabled']:
            lim = tk.get('limit')
            if not isinstance(lim, int) or isinstance(lim, bool) or not 1 <= lim <= 60:
                errs.append('hanson.turret_kits.limit must be an integer 1..60')
            else:
                for k in ('recommended',):
                    if not isinstance(tk.get(k), int) or isinstance(tk.get(k), bool) or not 0 <= tk[k] <= lim:
                        errs.append('hanson.turret_kits.%s must be an integer 0..limit' % k)
                o = tk.get('order')
                if not isinstance(o, dict) or set(o) != {'turret_kits'} or not isinstance(o['turret_kits'], int) or isinstance(o['turret_kits'], bool) or not 0 <= o['turret_kits'] <= lim:
                    errs.append('hanson.turret_kits.order must be {"turret_kits": 0..limit}')
            for k in ('price', 'preparation'):
                v = tk.get(k)
                if not (isinstance(v, dict) and set(v) == {'minerals', 'gas'} and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 5000 for x in v.values())):
                    errs.append('hanson.turret_kits.%s must be {"minerals": n, "gas": n}' % k)
            sc = tk.get('sectors')
            if not isinstance(sc, list) or not sc or not all(isinstance(x, dict) and x.get('role') in HANSON_ROLES and isinstance(x.get('count'), int) and x.get('ru') and x.get('en') for x in sc):
                errs.append('hanson.turret_kits.sectors needs entries with role, count, ru and en')
            if not isinstance(h.get('turrets', {}).get('list'), list) or len(h['turrets']['list']) != 0:
                errs.append('hanson.turret_kits: the ready (pre-placed) turrets are replaced by kits: hanson.turrets.list must be empty')
    fs = h.get('free_squad')
    if fs is not None and (not isinstance(fs, dict) or not isinstance(fs.get('enabled'), bool) or not isinstance(fs.get('marines'), int) or isinstance(fs.get('marines'), bool) or not 0 <= fs['marines'] <= 60):
        errs.append('hanson.free_squad needs enabled (boolean) and marines (integer 0..60)')
    sq = cfg['operatives']['squad']
    if sq not in (['Ghost'], ['Ghost', 'Ghost']):
        errs.append('hanson variant: the squad is one Ghost or two Ghosts')
    ct = h.get('containers')
    if ct is not None:
        if not isinstance(ct, dict) or not isinstance(ct.get('enabled'), bool):
            errs.append('hanson.containers needs enabled (boolean)')
        else:
            for k, (lo, hi) in {'limit': (1, 24), 'gas_cost': (0, 500), 'damage': (1, 2000), 'radius': (0.5, 8), 'life': (1, 500), 'place_range': (0.5, 6), 'min_free': (0, 4)}.items():
                if not _num(ct.get(k)) or not lo <= ct[k] <= hi:
                    errs.append('hanson.containers.%s must be a number %s..%s' % (k, lo, hi))
            if ct.get('owner') not in (0, 15):
                errs.append('hanson.containers.owner must be 0 (neutral)')
            fr = ct.get('friendly')
            if not (isinstance(fr, dict) and all(_num(fr.get(k)) and 0 <= fr[k] <= 1 for k in ('hard', 'other'))):
                errs.append('hanson.containers.friendly needs hard and other multipliers 0..1 (0 = no damage to own units)')
            if not (isinstance(ct.get('hotkey'), str) and len(ct['hotkey']) == 1 and ct['hotkey'].isalpha() and ct['hotkey'].isupper()):
                errs.append('hanson.containers.hotkey must be one capital letter')
            if len(sq) != 2:
                errs.append('hanson.containers need the two-Ghost squad')
            if not (cfg.get('ghost_tuning') or {}).get('snipe', {}).get('container_target'):
                errs.append('hanson.containers need ghost_tuning.snipe.container_target (the Ghost shot is the only detonation)')
    if 'allow_refinery' in h and not isinstance(h['allow_refinery'], bool):
        errs.append('hanson.allow_refinery must be boolean')
    fu = h.get('convoy_fuel')
    if fu is not None and (not isinstance(fu, dict) or not isinstance(fu.get('enabled'), bool) or not _num(fu.get('gas_cost')) or not 0 <= fu['gas_cost'] <= 1000):
        errs.append('hanson.convoy_fuel needs enabled and gas_cost 0..1000')
    if (ct or {}).get('enabled') or (fu or {}).get('enabled'):
        hud = h.get('hud')
        if not (isinstance(hud, dict) and all(isinstance(hud.get(k), int) and not isinstance(hud.get(k), bool) for k in ('offset_x', 'offset_y', 'width', 'height'))):
            errs.append('hanson.hud needs integer offset_x, offset_y, width, height')
    ln = h.get('lines')
    if ln is not None:
        ids = set()
        for x in ln if isinstance(ln, list) and len(ln) <= 16 else [None]:
            if not (isinstance(x, dict) and re.fullmatch(r'[A-Z0-9_]{2,40}', str(x.get('id', ''))) and x.get('id') not in ids and x.get('speaker') in ('raynor', 'swann') and _num(x.get('seconds')) and 0.5 <= x['seconds'] <= 60
                    and isinstance(x.get('text'), dict) and x['text'].get('ru') and x['text'].get('en')):
                errs.append('hanson.lines entries need a unique id (A-Z0-9_), speaker raynor / swann, seconds 0.5..60 and ru / en text')
                break
            ids.add(x['id'])
        st = h.get('story') or {}
        if not (_num(st.get('first_delay')) and _num(st.get('gap')) and 0 <= st['first_delay'] <= 600 and 0 <= st['gap'] <= 60):
            errs.append('hanson.story needs first_delay 0..600 and gap 0..60')
    return errs


def audio_clips(cfg):
    """[(clip id, source path, member name in the map archive)]"""
    return [(c['id'], os.path.join(ROOT, *c['source'].split('/')), AUDIO_DIR + os.path.basename(c['source']))
            for c in (cfg.get('audio') or {}).get('clips', [])]


def talk_clips(cfg):
    """[(id, member, facial animation name, seconds)]: SILENT clips that only drive the mouth of a portrait. A portrait animates its mouth only while a sound with a
    FacialAnim (the lip-sync animation of an original line, kept in the portrait's .fxa) plays; a transmission without a sound shows an almost still face.
    They are no voice: a build without added voice keeps them."""
    return [(c['id'], AUDIO_DIR + c['id'] + '.wav', c['facial'], c['seconds']) for c in (cfg.get('audio') or {}).get('talk', [])]


def silent_wav(seconds, rate=22050):
    n = int(rate * seconds)
    return (b'RIFF' + struct.pack('<I', 36 + n * 2) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', n * 2) + bytes(n * 2))


def validate_audio(a):
    errs = []
    errs += validate_talk(a)
    clips = a.get('clips') if isinstance(a, dict) else None
    if clips is None and a.get('talk'):
        return errs  # a build without added voice keeps only the silent talk drivers
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
            errs.append('audio clip %s: file not found: %s. The voice clips are not part of the repository: prepare them from your installed game (python tools/prepare_audio.py, '
                        'see README "Voice") or build without added voice (--no-voice; launcher: option "Без добавленной озвучки")' % (c['id'], src))
        elif read(os.path.join(ROOT, *src.split('/')))[:4] != b'RIFF':
            errs.append('audio clip %s: %s is not a WAV file' % (c['id'], src))
        if c['id'] in ids or os.path.basename(src).lower() in names:
            errs.append('audio clip %s: id or file name used twice' % c['id'])
        ids.add(c['id'])
        names.add(os.path.basename(src).lower())
        if 'facial' in c and not re.fullmatch(r'[A-Za-z0-9_]{3,60}', str(c['facial'])):
            errs.append('audio clip %s: facial must be the name of a facial animation' % c['id'])
    return errs


def validate_talk(a):
    errs = []
    for c in a.get('talk', []) if isinstance(a, dict) else []:
        if not isinstance(c, dict) or not AUDIO_ID.fullmatch(str(c.get('id', ''))) or not re.fullmatch(r'[A-Za-z0-9_]{3,60}', str(c.get('facial', ''))) or not _num(c.get('seconds')) or not 0.5 <= c['seconds'] <= 30 or c.get('group') not in TALK_GROUPS:
            errs.append('audio.talk entries need id (GhostOps...), facial (animation name), seconds 0.5..30 and group %s (got %r)' % (TALK_GROUPS, c))
    return errs


def validate_scene(cfg):
    """The wounded squad scene of TRaynor01 (config key "scene")."""
    s = cfg['scene']
    errs = []
    if not isinstance(s, dict) or not isinstance(s.get('enabled'), bool):
        return ['scene.enabled must be boolean']
    for k, lo, hi in (('pause', 0.0, 3.0), ('raynor_seconds', 1.0, 20.0), ('marine_b_seconds', 1.0, 20.0), ('marine_a_seconds', 1.0, 20.0), ('closing_seconds', 3.0, 40.0)):
        v = s.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            errs.append('scene.%s must be a number %g..%g' % (k, lo, hi))
    ids = {c['id'] for c in (cfg.get('audio') or {}).get('clips', [])}
    for k in ('raynor_clip', 'marine_b_clip', 'marine_a_clip'):
        if s.get(k) not in ids and not cfg.get('_no_voice'):
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
    for k, (lo, hi) in {'first_delay': (1, 120), 'second_delay': (1, 300), 'alert_seconds': (3, 40), 'swann_seconds': (2, 30), 'arrival_seconds': (3, 40), 'ghost_seconds': (2, 20), 'raynor_delay': (0, 60), 'raynor_seconds': (3, 40)}.items():
        if not num(st.get(k), lo, hi):
            errs.append('tactical.story.%s must be a number in %s..%s' % (k, lo, hi))
    for k, (lo, hi) in {'find_delay': (0, 120), 'plan_min_share': (0, 1), 'plan_calm_seconds': (0, 60), 'plan_max_wait': (30, 1800), 'plan_dead_delay': (0, 120)}.items():
        if k in st and not num(st.get(k), lo, hi):
            errs.append('tactical.story.%s must be a number in %s..%s' % (k, lo, hi))
    errs += validate_lines(cfg)
    a = t.get('academy', {})
    if not pair(a.get('position')) or not num(a.get('arm_time'), 0.5, 60):
        errs.append('tactical.academy needs position [x, y] and arm_time 0.5..60')
    n = t.get('nuke', {})
    if not num(n.get('aim_time'), 2, 60) or round(n.get('aim_time', 0) / 0.2, 6) != int(round(n.get('aim_time', 0) / 0.2)):
        errs.append('tactical.nuke.aim_time must be 2..60 and a multiple of 0.2')
    if not num(n.get('flight_time'), 1, 60):
        errs.append('tactical.nuke.flight_time must be 1..60')
    if not isinstance(n.get('count', 1), int) or isinstance(n.get('count', 1), bool) or not 1 <= n.get('count', 1) <= 6:
        errs.append('tactical.nuke.count must be an integer 1..6')
    if not isinstance(n.get('both_may_aim', False), bool) or not isinstance(t.get('spotter_defeat', True), bool):
        errs.append('tactical.nuke.both_may_aim and tactical.spotter_defeat must be boolean')
    if not num(n.get('range'), 1, 100):
        errs.append('tactical.nuke.range must be 1..100')
    nd = n.get('damage')
    if nd is not None:
        if not isinstance(nd, dict) or not num(nd.get('amount'), 1, 20000) or not num(nd.get('structure_bonus'), 0, 20000):
            errs.append('tactical.nuke.damage needs amount 1..20000 and structure_bonus 0..20000 (the damage profile of this mission only; experimental)')
        ar = (nd or {}).get('areas')
        if not (isinstance(ar, list) and len(ar) == 3 and all(isinstance(x, list) and len(x) == 2 and num(x[0], 0.5, 30) and num(x[1], 0.01, 1) for x in ar)
                and ar[0][0] < ar[1][0] < ar[2][0] and ar[0][1] >= ar[1][1] >= ar[2][1]):
            errs.append('tactical.nuke.damage.areas must be three [radius, fraction] pairs with growing radius and falling fraction')
    if 'aim_cloak_hold' in n and not isinstance(n['aim_cloak_hold'], bool):
        errs.append('tactical.nuke.aim_cloak_hold must be boolean')
    if 'require_vision' in n and not isinstance(n['require_vision'], bool):
        errs.append('tactical.nuke.require_vision must be boolean (the strike point must be visible)')
    if n.get('aim_cloak_hold') and (cfg.get('ghost_tuning') or {}).get('cloak_net_per_second', 0) >= 0:
        errs.append('tactical.nuke.aim_cloak_hold needs a cloak that costs energy (ghost_tuning.cloak_net_per_second < 0)')
    gr = t.get('grenade')
    if gr is not None:
        if not isinstance(gr, dict) or not isinstance(gr.get('enabled'), bool):
            errs.append('tactical.grenade.enabled must be boolean')
        else:
            if not isinstance(gr.get('charges'), int) or isinstance(gr.get('charges'), bool) or not 1 <= gr['charges'] <= 6:
                errs.append('tactical.grenade.charges must be an integer 1..6')
            for k, (lo, hi) in {'damage': (1, 3000), 'radius': (0.5, 8), 'range': (3, 20), 'prep_time': (0, 3)}.items():
                if not num(gr.get(k), lo, hi):
                    errs.append('tactical.grenade.%s must be a number %s..%s' % (k, lo, hi))
            if 'flight_speed' in gr and not num(gr['flight_speed'], 1, 60):
                errs.append('tactical.grenade.flight_speed must be a number 1..60 (cells per second of the projectile)')
            if 'hotkey' in gr and not (isinstance(gr['hotkey'], str) and len(gr['hotkey']) == 1 and gr['hotkey'].isalpha() and gr['hotkey'].isupper()):
                errs.append('tactical.grenade.hotkey must be one capital letter')
            if 'pointer' in gr and not isinstance(gr['pointer'], bool):
                errs.append('tactical.grenade.pointer must be boolean (range circle and area circle under the cursor)')
            if 'effects' in gr and not isinstance(gr['effects'], bool):
                errs.append('tactical.grenade.effects must be boolean (impact flash / explosion model and sound)')
            if gr['enabled'] and cfg['operatives'].get('squad') != ['Ghost', 'Ghost']:
                errs.append('tactical.grenade needs the two-Ghost squad (the second Ghost is the Operative)')
            for k in ('GrenadeName', 'GrenadeTip'):
                if gr['enabled'] and k not in t.get('texts', {}):
                    errs.append('tactical.texts.%s is needed by the grenade' % k)
    vc = t.get('victory')
    if vc is not None:
        if not isinstance(vc, dict) or not isinstance(vc.get('enabled'), bool) or not (isinstance(vc.get('types'), list) and 1 <= len(vc['types']) <= 16 and all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9]+', x) for x in vc['types'])):
            errs.append('tactical.victory needs enabled (boolean) and types: 1..16 unit type ids of the enemy production buildings')
    rl = t.get('rebel_labels')
    if rl is not None and (not isinstance(rl, dict) or not isinstance(rl.get('enabled'), bool)):
        errs.append('tactical.rebel_labels.enabled must be boolean')
    rh = t.get('rebel_hints')
    if rh is not None:
        if not isinstance(rh, dict) or not isinstance(rh.get('enabled'), bool):
            errs.append('tactical.rebel_hints.enabled must be boolean')
        else:
            for k, (lo, hi) in {'delay': (0, 30), 'ping_seconds': (1, 20), 'gap': (0, 30)}.items():
                if not num(rh.get(k), lo, hi):
                    errs.append('tactical.rebel_hints.%s must be a number %s..%s' % (k, lo, hi))
    texts = t.get('texts', {})
    for k in TAC_TEXT_KEYS:
        if t.get('lines') and k in TAC_LINE_REPLACED_KEYS:
            continue
        v = texts.get(k)
        if not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and '\n' not in v[l] for l in ('ru', 'en')):
            errs.append('tactical.texts.%s needs non-empty single-line ru and en texts' % k)
    for k in TAC_EXTRA_TEXT_KEYS:
        v = texts.get(k)
        if v is not None and (not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and '\n' not in v[l] for l in ('ru', 'en'))):
            errs.append('tactical.texts.%s needs non-empty single-line ru and en texts' % k)
    return errs


def validate_lines(cfg):
    """tactical.lines: the story lines (stable id, speaker, seconds, optional voice clip id, ru/en text)."""
    import re
    t = cfg['tactical']
    ls = t.get('lines')
    if ls is None:
        return []
    errs = []
    if not isinstance(ls, list) or not 1 <= len(ls) <= LINE_MAX:
        return ['tactical.lines must be a list of 1..%d lines' % LINE_MAX]
    clips = {c['id'] for c in (cfg.get('audio') or {}).get('clips', [])}
    seen = set()
    for ln in ls:
        i = ln.get('id') if isinstance(ln, dict) else None
        if not isinstance(i, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{1,40}', i) or i in seen:
            errs.append('tactical.lines: bad or repeated id %r' % (i,))
            continue
        seen.add(i)
        if ln.get('speaker') not in LINE_SPEAKERS:
            errs.append('tactical.lines.%s.speaker must be one of %s' % (i, LINE_SPEAKERS))
        if not _num(ln.get('seconds')) or not 0.5 <= ln['seconds'] <= 40:
            errs.append('tactical.lines.%s.seconds must be 0.5..40' % i)
        c = ln.get('clip', '')
        if not isinstance(c, str) or (c and c not in clips):
            errs.append('tactical.lines.%s.clip must be empty or an id of audio.clips' % i)
        if 'large' in ln and not isinstance(ln['large'], bool):
            errs.append('tactical.lines.%s.large must be boolean' % i)
        tx = ln.get('text')
        if not isinstance(tx, dict) or not all(isinstance(tx.get(l), str) and tx[l] and chr(10) not in tx[l] for l in ('ru', 'en')):
            errs.append('tactical.lines.%s.text needs single-line ru and en texts' % i)
    return errs


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_panel(cfg):
    """The status panel of the specialists (config key "panel", core/GhostOpsCore.galaxy)."""
    p = cfg['panel']
    if not isinstance(p, dict) or not isinstance(p.get('enabled'), bool):
        return ['panel.enabled must be boolean']
    errs = []
    texts = p.get('texts', {})
    need = list(PANEL_TEXT_KEYS) + ['Name%d' % i for i in range(len(cfg['operatives']['squad']))]
    if p['enabled'] and not set(need) <= set(texts):
        errs.append('panel.texts must have at least the keys %s' % (need,))
    for k in need:
        v = texts.get(k)
        if p['enabled'] and (not isinstance(v, dict) or not all(isinstance(v.get(l), str) and v[l] and chr(10) not in v[l] for l in ('ru', 'en'))):
            errs.append('panel.texts.%s needs non-empty single-line ru and en texts' % k)
    return errs


def validate_ghost_tuning(gt):
    errs = []
    if not isinstance(gt, dict):
        return ['ghost_tuning must be an object']
    sn = gt.get('snipe', {})
    ranges = {
        'energy_start': (0, 500), 'energy_max': (1, 500), 'regen_per_second': (0, 100),
        'cloak_activation_cost': (0, 200), 'cloak_net_per_second': (-100, 100),
    }
    for k, (lo, hi) in ranges.items():
        if not _num(gt.get(k)) or not lo <= gt[k] <= hi:
            errs.append('ghost_tuning.%s must be a number in %s..%s' % (k, lo, hi))
    if 'cooldown' in sn and (not _num(sn['cooldown']) or not 0 <= sn['cooldown'] <= 60):
        errs.append('ghost_tuning.snipe.cooldown must be a number in 0..60')
    if 'exclude_friendly' in sn and not isinstance(sn['exclude_friendly'], bool):
        errs.append('ghost_tuning.snipe.exclude_friendly must be boolean')
    if 'container_target' in sn and (not isinstance(sn['container_target'], bool) or not sn.get('exclude_friendly')):
        errs.append('ghost_tuning.snipe.container_target must be boolean and needs exclude_friendly (the neutral class is opened for the special containers only, own units stay excluded)')
    for k, (lo, hi) in {'cost': (0, 200), 'damage': (1, 1000), 'cast_time': (0, 5)}.items():
        if not _num(sn.get(k)) or not lo <= sn[k] <= hi:
            errs.append('ghost_tuning.snipe.%s must be a number in %s..%s' % (k, lo, hi))
    if 'ghost_life' in gt and (not isinstance(gt['ghost_life'], int) or isinstance(gt['ghost_life'], bool) or not 1 <= gt['ghost_life'] <= 1000):
        errs.append('ghost_tuning.ghost_life must be an integer 1..1000')
    ra = gt.get('remove_abilities', [])
    if not isinstance(ra, list) or any(x not in GHOST_ABIL_INDEX for x in ra) or len(set(ra)) != len(ra):
        errs.append('ghost_tuning.remove_abilities must be distinct entries of %s' % sorted(GHOST_ABIL_INDEX))
    if not errs and gt['cloak_net_per_second'] > gt['regen_per_second']:
        errs.append('ghost_tuning.cloak_net_per_second must not exceed regen_per_second (the cloak can only cost energy; equal = a free cloak)')
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
        ] + (['        <TargetFilters index="0" value="Biological,Visible;Self,Player,Ally,%sStructure,Destructible,Stasis,Dead,Hidden,Invulnerable"/>' % ('' if sn.get('container_target') else 'Neutral,')] if sn.get('exclude_friendly') else []) + [
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


def hanson_fragments(h, cfg):
    """Catalog overrides of the prepared-detonation variant (map local). The container is a neutral, biological, non-colliding unit (the neutral class is what the Ghost's
    Snipe of this profile may target, container_target); placing it is an ability of the Firebat; the explosion is two search effects (enemies / own side) that the module
    creates at the place where a container died by a Ghost shot; the radius circles and the explosion visuals are actors (they draw only)."""
    g = lambda v: '%g' % v  # noqa: E731
    nl = chr(10)
    ct = h.get('containers') or {}
    kit = {}
    if (h.get('turret_kits') or {}).get('enabled'):
        # the turret kits: the Missile Turret costs nothing to build (the kit was ordered, no second payment) and needs only the Command Center (the stock requirement is an Engineering Bay)
        kit = {'UnitData.xml': nl.join(['    <CUnit id="MissileTurret">', '        <CostResource index="Minerals" value="0"/>', '    </CUnit>', '']),
               'AbilData.xml': nl.join(['    <CAbilBuild id="TerranBuild">', '        <InfoArray index="Build6">', '            <Button Requirements="HaveCommandCenter"/>', '        </InfoArray>', '    </CAbilBuild>', ''])}
    if not ct.get('enabled'):
        return kit
    bs = chr(92)
    icon = 'Assets' + bs + 'Textures' + bs + 'btn-upgrade-terran-infernalpreigniter.dds'
    unit = ['    <CUnit id="GhostOpsFuelContainer" parent="ExplodingBarrelLarge">',
            '        <LifeStart value="%s"/>' % g(ct['life']), '        <LifeMax value="%s"/>' % g(ct['life']), '        <LifeArmor value="0"/>',
            '        <Attributes index="Biological" value="1"/>', '        <FlagArray index="Destructible" value="0"/>',
            '        <BehaviorArray index="0" removed="1"/>',
            # no collision and no footprint: the container can neither block a road nor a convoy
            ] + (['        <Collide index="Ground" value="0"/>', '        <Collide index="Structure" value="0"/>', '        <Collide index="Burrow" value="0"/>', '        <Footprint value=""/>'] if ct.get('blank_footprint') else []) + [
            '        <Radius value="0.4"/>', '        <InnerRadius value="0.3"/>',
            '        <BehaviorArray Link="GhostOpsContainerRadius"/>',
            '    </CUnit>',
            '    <CUnit id="Firebat">', '        <AbilArray Link="GhostOpsPlaceContainer"/>', '        <CardLayouts index="0">',
            '            <LayoutButtons Face="GhostOpsPlaceContainer" Type="AbilCmd" AbilCmd="GhostOpsPlaceContainer,Execute" Row="2" Column="1"/>', '        </CardLayouts>', '    </CUnit>', '']
    abil = ['    <CAbilEffectTarget id="GhostOpsPlaceContainer">', '        <EditorCategories value="Race:Terran,AbilityorEffectType:Units"/>', '        <Effect index="0" value="GhostOpsContainerArea"/>',
            '        <ErrorAlert value="Error"/>', '        <Range value="%s"/>' % g(ct['place_range']), '        <CastIntroTime value="0.3"/>', '        <CursorEffect value="GhostOpsContainerArea"/>',
            # like a building: the model of the container under the cursor and the footprint colours (green = placeable, red = not); the container itself is made by the module
            '        <PlaceUnit value="GhostOpsFuelContainer"/>', '        <Placeholder value="GhostOpsFuelContainer"/>', '        <ProducedUnitArray value="GhostOpsFuelContainer"/>',
            '        <CmdButtonArray index="Execute" DefaultButtonFace="GhostOpsPlaceContainer"/>', '    </CAbilEffectTarget>', '']
    # the Firebat's own Snipe-free card: the new button only; the radius circle of a SELECTED container is a hidden buff shown by the module (UnitIsSelected, like the detector circles)
    beh = ['    <CBehaviorBuff id="GhostOpsContainerRadius">', '        <InfoFlags index="Hidden" value="1"/>', '    </CBehaviorBuff>',
           '    <CBehaviorBuff id="GhostOpsContainerShow">', '        <InfoFlags index="Hidden" value="1"/>', '    </CBehaviorBuff>', '']
    area = lambda eid, filters, dmg: ['    <CEffectEnumArea id="%s">' % eid, '        <EditorCategories value="Race:Terran"/>', '        <LaunchLocation Value="TargetPoint"/>', '        <ImpactLocation Value="TargetPoint"/>',
                                      '        <AreaArray Radius="%s" Effect="%sDamage"/>' % (g(ct['radius']), eid), '        <SearchFilters value="%s"/>' % filters, '    </CEffectEnumArea>',
                                      '    <CEffectDamage id="%sDamage">' % eid, '        <EditorCategories value="Race:Terran"/>', '        <Kind value="Splash"/>', '        <Amount value="%s"/>' % g(dmg),
                                      '        <Flags index="Notification" value="1"/>', '        <ResponseFlags index="Acquire" value="1"/>', '    </CEffectDamage>']
    # the ability's effect is only this harmless search (no damage, nothing created): the MODULE validates the place and creates / pays for the container itself when the cast executes
    eff = [
           '    <CEffectEnumArea id="GhostOpsContainerArea">', '        <EditorCategories value="Race:Terran"/>', '        <AreaArray Radius="%s"/>' % g(ct['radius']), '        <SearchFilters value="Ground;Missile,Dead,Hidden"/>', '    </CEffectEnumArea>']
    # enemies: ground, no air, no neutral (the other containers: no chain detonation), no missiles; own side: the same without enemies, damage = damage x the multiplier
    eff += area('GhostOpsCBlast', 'Ground;Player,Ally,Neutral,Air,Missile,Stasis,Dead,Hidden,Invulnerable', ct['damage'])
    for key, mult in (('Hard', ct['friendly']['hard']), ('Other', ct['friendly']['other'])):
        if mult > 0:
            eff += area('GhostOpsCBlastOwn' + key, 'Ground;Enemy,Neutral,Air,Missile,Stasis,Dead,Hidden,Invulnerable', ct['damage'] * mult)
    eff.append('')
    # same shape as the stock canister actor (parent generic unit, own unitName: the ##unitName## tokens of the generic actor then resolve to OUR model id)
    act = ['    <CActorUnit id="GhostOpsFuelContainer" parent="GenericUnitStandardNoAutoSoundLinks" unitName="GhostOpsFuelContainer">', '        <On Terms="ActorCreation" Send="Create GasCanisterGlow"/>', '        <StatusBarFlags index="Life" value="0"/>', '    </CActorUnit>',
           '    <CActorModel id="GhostOpsCPointerModel" parent="TerranCursorModel" abil="GhostOpsPlaceContainer"/>', '    <CActorSplat id="GhostOpsCPointerSplat" parent="TerranCursorSplat" abil="GhostOpsPlaceContainer"/>',
           '    <CActorRange id="GhostOpsCPlaceRange" parent="RangeAbil" abil="GhostOpsPlaceContainer"/>']
    if ct.get('show_radius'):
        act += ['    <CActorRange id="GhostOpsCRadius">', '        <Range value="%s"/>' % g(ct['radius']), '        <On Terms="Behavior.GhostOpsContainerShow.On" Send="Create"/>', '        <On Terms="Behavior.GhostOpsContainerShow.Off" Send="Destroy"/>', '    </CActorRange>']
    # visuals only (the damage is the search effects above): the explosion model / flash and the sound at the real place, one short smoke after it
    act += ['    <CActorModel id="GhostOpsCBlastModel" parent="ModelAnimationStyleOneShot">', '        <Model value="BarrageModel"/>', '        <HostSiteOps Ops="SOpTargetPoint"/>', '        <On Terms="Effect.GhostOpsCBlast.Impact" Send="Create"/>', '    </CActorModel>',
            '    <CActorModel id="GhostOpsCBlastModel2" parent="ModelAnimationStyleOneShot">', '        <Model value="ExplodingBarrelDeath"/>', '        <HostSiteOps Ops="SOpTargetPoint"/>', '        <On Terms="Effect.GhostOpsCBlast.Impact" Send="Create"/>', '    </CActorModel>',
            '    <CActorSound id="GhostOpsCBlastSound" parent="SoundOneShot">', '        <Sound value="Terran_ExplosionLarge"/>', '        <On Terms="Effect.GhostOpsCBlast.Impact" Send="Create"/>', '    </CActorSound>', '']
    btn = ['    <CButton id="GhostOpsPlaceContainer">', '        <Icon value="%s"/>' % icon, '        <AlertIcon value="%s"/>' % icon, '        <Hotkey value="Button/Hotkey/GhostOpsPlaceContainer"/>', '        <EditorCategories value="Race:Terran"/>', '    </CButton>', '']
    # an inherited model path was NOT resolved by the engine (the unit showed the grey placeholder dome): the path of the stock gas canister model is written out
    model = ['    <CModel id="GhostOpsFuelContainer" parent="GasCanister">', '        <Model value="Assets\\Buildings\\Resources\\GasCanister\\GasCanister.m3"/>', '    </CModel>', '']
    out = {'ModelData.xml': nl.join(model), 'UnitData.xml': nl.join(unit), 'AbilData.xml': nl.join(abil), 'BehaviorData.xml': nl.join(beh), 'EffectData.xml': nl.join(eff), 'ActorData.xml': nl.join(act), 'ButtonData.xml': nl.join(btn)}
    for fname, frag in kit.items():
        out[fname] = out[fname] + nl + frag
    return out


def tactical_fragments(t, gt=None):
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

    gr = t.get('grenade') or {}
    gr = dict(gr, dev_flight_speed=gr.get('dev_flight_speed') or gr.get('flight_speed'))  # projectile speed of this mission; the probe builds may override it (dev_flight_speed)
    hold = ((-gt['cloak_net_per_second']) if gt and t['nuke'].get('aim_cloak_hold') else 0)
    extra_beh = []
    if hold > 0:
        # while the strike channel runs the cloak drain is cancelled: net change under the cloak = cloak_net, so +(-cloak_net) makes it exactly 0 (the energy neither drains nor recovers)
        extra_beh = ['    <CBehaviorBuff id="GhostOpsAimHold">', '        <InfoFlags index="Hidden" value="1"/>', '        <Modification>',
                     '            <VitalRegenArray index="Energy" value="%s"/>' % g(hold), '        </Modification>', '    </CBehaviorBuff>']
    abil_extra, button, effects = [], [], []
    if gr.get('enabled'):
        abil_extra = ['    <CAbilEffectTarget id="GhostOpsArmorPiercing">', '        <EditorCategories value="Race:Terran,AbilityorEffectType:Units"/>',
                      '        <Effect index="0" value="GhostOpsAPLaunch"/>', '        <Range value="%s"/>' % g(gr['range']), '        <CastIntroTime value="%s"/>' % g(gr['prep_time']),
                      '        <CursorEffect value="GhostOpsAPSearch"/>', '        <CmdButtonArray index="Execute" DefaultButtonFace="GhostOpsArmorPiercing"/>',
                      '    </CAbilEffectTarget>']
        button = ['    <CButton id="GhostOpsArmorPiercing">', '        <Icon value="Assets' + chr(92) + 'Textures' + chr(92) + 'btn-ability-terran-punishergrenade-color.dds"/>',
                  '        <AlertIcon value="Assets' + chr(92) + 'Textures' + chr(92) + 'btn-ability-terran-punishergrenade-color.dds"/>', '        <EditorCategories value="Race:Terran"/>', '    </CButton>']
        effects = ['    <CEffectLaunchMissile id="GhostOpsAPLaunch">', '        <EditorCategories value="Race:Terran"/>', '        <ImpactEffect value="GhostOpsAPSearch"/>',
                   '        <ImpactLocation Value="TargetPoint"/>', '        <AmmoUnit value="%s"/>' % ('GhostOpsAPMissile' if gr.get('dev_flight_speed') else 'PunisherGrenadesLMWeapon'), '    </CEffectLaunchMissile>',
                   '    <CEffectEnumArea id="GhostOpsAPSearch">', '        <EditorCategories value="Race:Terran"/>', '        <LaunchLocation Value="TargetPoint"/>', '        <ImpactLocation Value="TargetPoint"/>',
                   '        <AreaArray Radius="%s" Effect="GhostOpsAPDamage"/>' % g(gr['radius']),
                   # ground enemy MACHINES and STRUCTURES only: Mechanical and not Biological (an SCV is both and stays out), no air, no own / allied / neutral units, no missiles
                   '        <SearchFilters value="Ground,Mechanical,Visible;Player,Ally,Neutral,Biological,Air,Missile,Stasis,Dead,Hidden,Invulnerable"/>', '    </CEffectEnumArea>',
                   '    <CEffectDamage id="GhostOpsAPDamage">', '        <EditorCategories value="Race:Terran"/>', '        <Kind value="Splash"/>', '        <Amount value="%s"/>' % g(gr['damage']), '        <Flags index="Notification" value="1"/>',
                   '        <ResponseFlags index="Acquire" value="1"/>', '    </CEffectDamage>']
    nuke_damage = []
    if n.get('damage'):
        # the damage profile of THIS mission only (map local override of the stock NukeDamage: 300 + 200 vs structures, radii 4 / 6 / 8 with 100 / 50 / 25 %): experimental, from the config
        nd = n['damage']
        nuke_damage = ['    <CEffectDamage id="NukeDamage">', '        <Amount value="%s"/>' % g(nd['amount']), '        <AttributeBonus index="Structure" value="%s"/>' % g(nd['structure_bonus'])] + [
            '        <AreaArray index="%d" Radius="%s" Fraction="%s"/>' % (i, g(r), g(f)) for i, (r, f) in enumerate(nd['areas'])] + ['    </CEffectDamage>']
    grenade_actors = []
    if gr.get('enabled') and (gr.get('pointer') or gr.get('effects')):
        # the pointer of the ability like the Odin's Barrage / the EMP: cursor splat (radius = the CursorEffect area = the real damage radius), cursor model and the range indicator
        grenade_actors = ['    <CActorModel id="GhostOpsAPCursorModel" parent="TerranCursorModel" abil="GhostOpsArmorPiercing"/>', '    <CActorSplat id="GhostOpsAPCursorSplat" parent="TerranCursorSplat" abil="GhostOpsArmorPiercing"/>',
                          '    <CActorRange id="GhostOpsAPRange" parent="RangeAbil" abil="GhostOpsArmorPiercing"/>']
        if gr.get('effects'):
            # flash / explosion at the REAL hit (the impact of the search effect; the visual does no damage) with the stock explosion model and sound of the campaign data
            grenade_actors += ['    <CActorModel id="GhostOpsAPImpact" parent="ModelAnimationStyleOneShot">', '        <Model value="BarrageModel"/>', '        <HostSiteOps Ops="SOpTargetPoint"/>',
                               '        <On Terms="Effect.GhostOpsAPSearch.Impact" Send="Create"/>', '    </CActorModel>',
                               '    <CActorSound id="GhostOpsAPSound" parent="SoundOneShot">', '        <Sound value="Terran_ExplosionLarge"/>', '        <On Terms="Effect.GhostOpsAPSearch.Impact" Send="Create"/>', '    </CActorSound>']
    # development only (dev_flight_speed): a slow copy of the grenade projectile, so that a game can be saved while it is in flight
    mover = []
    speed = gr.get('dev_flight_speed')  # = flight_speed unless a probe build overrides it with a slow copy (so that a game can be saved while the projectile is in flight)
    if gr.get('enabled') and speed:
        mover = ['    <CMoverMissile id="GhostOpsAPMover" parent="PunisherGrenadesWeapon">', '        <MotionPhases index="0" Acceleration="%s" MaxSpeed="%s"/>' % (g(max(40, speed * 2)), g(speed)), '    </CMoverMissile>']
    ghost_unit = (['    <CUnit id="Ghost">', '        <AbilArray Link="GhostOpsArmorPiercing"/>', '        <CardLayouts index="0">',
                   '            <LayoutButtons Face="GhostOpsArmorPiercing" Type="AbilCmd" AbilCmd="GhostOpsArmorPiercing,Execute" Row="1" Column="1"/>', '        </CardLayouts>', '    </CUnit>']
                  if gr.get('enabled') else [])
    return {
        'UnitData.xml': nl.join(
            ['    <CUnit id="GhostAcademy">']
            + ['        <AbilArray index="%d" removed="1"/>' % i for i in ACADEMY_REMOVED_ABILS]
            + ['    </CUnit>',
               '    <CUnit id="Nuke">',
               '        <CostResource index="Minerals" value="0"/>',
               '        <CostResource index="Vespene" value="0"/>',
               '    </CUnit>'] + ghost_unit + (['    <CUnit id="GhostOpsAPMissile" parent="PunisherGrenadesLMWeapon">', '        <Mover value="GhostOpsAPMover"/>', '    </CUnit>'] if mover else []) + ['']),
        'MoverData.xml': nl.join(mover + ['']) if mover else '',
        # the projectile unit has no model of its own and showed as a white dome: the stock pod missile of the Odin barrage (smoke trail is part of the model)
        'ModelData.xml': nl.join(['    <CModel id="GhostOpsAPMissile" parent="MissileBarragePod">', '        <Model value="Assets\\Effects\\Terran\\PodMissile\\PodMissile.m3"/>', '    </CModel>', '']) if (mover and gr.get('effects')) else '',
        'BehaviorData.xml': nl.join(behavior('GhostOpsGarrisonDamage', gm) + extra_beh + ['']),
        'ButtonData.xml': nl.join(button + ['']) if button else '',
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
            '        <Range index="0" value="%s"/>' % g(n['range']),
            '        <FinishTime value="0"/>',
        ] + (['        <Flags index="RequireTargetVision" value="1"/>'] if n.get('require_vision') else []) + [
            '    </CAbilEffectTarget>'] + abil_extra + ['']),
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
        ] + nuke_damage + effects),
        'ActorData.xml': nl.join(grenade_actors + (['    <CActorMissile id="GhostOpsAPMissile" parent="GenericAttackMissile" unitName="GhostOpsAPMissile"/>'] if mover else []) + ['']) if grenade_actors else '',
    }


def merge_same_id(xml, tag, ident):
    """One element per id in a fragment: the inner lines of a second <tag id=ident> block move into the first (the game layers the fragment on the original data; two blocks of one id would be two layers)."""
    start = '<%s id="%s">' % (tag, ident)
    end = '</%s>' % tag
    first = xml.find(start)
    if first < 0:
        return xml
    pos = xml.find(start, first + len(start))
    while pos >= 0:
        stop = xml.index(end, pos)
        inner = xml[pos + len(start):stop]
        line_start = xml.rfind(chr(10), 0, pos) + 1
        line_end = xml.index(chr(10), stop) + 1 if chr(10) in xml[stop:] else len(xml)
        xml = xml[:line_start] + xml[line_end:]
        first_end = xml.index(end, first)
        xml = xml[:first_end] + inner.strip(chr(10)) + chr(10) + '    ' + xml[first_end:]
        pos = xml.find(start, first + len(start))
    return xml


def catalog_fragments(cfg):
    """{file name in Base.SC2Data/GameData: xml fragment} that this configuration needs."""
    frags = {}
    if needs_nova_patch(cfg):
        frags['UnitData.xml'] = read(os.path.join(ROOT, 'core', 'data', 'NovaFireControl.xml'), 'r')
    if cfg.get('ghost_tuning'):
        for name, frag in ghost_tuning_fragments(cfg['ghost_tuning']).items():
            frags[name] = frags.get(name, '') + frag
    if cfg.get('tactical'):
        for name, frag in tactical_fragments(cfg['tactical'], cfg.get('ghost_tuning')).items():
            if frag:
                frags[name] = frags.get(name, '') + frag
    if cfg.get('defence'):
        for name, frag in defence_fragments(cfg['defence']).items():
            frags[name] = frags.get(name, '') + frag
    if cfg.get('hanson'):
        for name, frag in hanson_fragments(cfg['hanson'], cfg).items():
            if frag:
                frags[name] = frags.get(name, '') + frag
    if cfg.get('detector_analysis') and cfg['detector_analysis'].get('enabled'):
        for name, frag in detector_analysis_fragments(cfg['detector_analysis']).items():
            frags[name] = frags.get(name, '') + frag
    if 'UnitData.xml' in frags:
        frags['UnitData.xml'] = merge_same_id(frags['UnitData.xml'], 'CUnit', 'Ghost')
    facial = {c['id']: c['facial'] for c in (cfg.get('audio') or {}).get('clips', []) if c.get('facial')}
    sounds = ['    <CSound id="%s" parent="SM_Old">%s        <Mode value="2D"/>%s        <AssetArray File="%s"%s/>%s    </CSound>' % (
        cid, chr(10), chr(10), member, (' FacialAnim="%s"' % facial[cid]) if cid in facial else '', chr(10)) for cid, _, member in audio_clips(cfg)]
    sounds += ['    <CSound id="%s" parent="SM_Old">%s        <Mode value="2D"/>%s        <AssetArray File="%s" FacialAnim="%s"/>%s    </CSound>' % (
        tid, chr(10), chr(10), member, fa, chr(10)) for tid, member, fa, _ in talk_clips(cfg)]
    if sounds:
        frags['SoundData.xml'] = frags.get('SoundData.xml', '') + chr(10).join(sounds) + chr(10)
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
              '    go_cfgNoVoice = %s;' % b(cfg.get('_no_voice')),
              ] + talk_lines(cfg) + [

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


def talk_lines(cfg):
    """Constants of the talk drivers: silent lip-sync clips per speaker group (GhostOps_Talk chains them while a portrait explains something)."""
    talk = (cfg.get('audio') or {}).get('talk', [])
    lines = []
    idx = 0
    for gi, g in enumerate(TALK_GROUPS):
        members = [t for t in talk if t['group'] == g]
        lines.append('    go_talkFirst[%d] = %d;' % (gi, idx))
        lines.append('    go_talkCount[%d] = %d;' % (gi, len(members)))
        for t in members:
            lines.append('    go_talkId[%d] = "%s";' % (idx, t['id']))
            lines.append('    go_talkLen[%d] = %.1f;' % (idx, t['seconds']))
            idx += 1
    return lines


def gen_panel(cfg):
    """GhostOps_ApplyPanelConfig(): the status panel of the specialists (disabled without the config key "panel")."""
    p = cfg.get('panel') or {}
    gt = cfg.get('ghost_tuning') or {}
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    on = bool(p.get('enabled'))
    return chr(10).join(['// Generated panel configuration', 'void GhostOps_ApplyPanelConfig () {', '    go_pnEnabled = %s;' % b(on),
                         '    go_pnCount = %d;' % len(cfg['operatives']['squad']),
                         '    go_pnNet = %.3f;' % (gt['cloak_net_per_second'] if gt else -0.9),
                         '    go_pnRegen = %.3f;' % (gt['regen_per_second'] if gt else 0.5625),
                         '    go_pnPermanent = %s;' % b(cfg['operatives']['ghost_permanent_cloak']),
                         '    go_pnGrenades = -1;', '    go_pnGrenadeSlot = 1;', '    go_pnHoldSlot = 0;', '}', '']) + chr(10)


def gen_tactical(cfg):
    """GhostOps_ApplyTacticalConfig(): the module is inert (go_tacEnabled false) unless the config has a tactical section."""
    t = cfg.get('tactical')
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    lines = ['// Generated tactical configuration', 'void GhostOps_ApplyTacticalConfig () {']
    if not t:
        lines += ['    go_tacEnabled = false;', '}', '', 'void GhostOps_ApplyLines () {', '    go_lnCount = 0;', '}', '']
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
        '    go_tacNukeCount = %d;' % t['nuke'].get('count', 1),
        '    go_tacBothAim = %s;' % b(t['nuke'].get('both_may_aim', False)),
        '    go_tacSpotterDefeat = %s;' % b(t.get('spotter_defeat', True)),
        '    go_tacStoryRaynorDelay = %.1f;' % t['story']['raynor_delay'],
        '    go_tacStoryRaynorLen = %.1f;' % t['story']['raynor_seconds'],
        '    go_tacAimHold = %s;' % b(t['nuke'].get('aim_cloak_hold')),
        '    go_tacGrenade = %s;' % b((t.get('grenade') or {}).get('enabled')),
        '    go_tacGrenadeMax = %d;' % (t.get('grenade') or {}).get('charges', 0),
        '    go_tacRebelLabels = %s;' % b((t.get('rebel_labels') or {}).get('enabled')),
        '    go_tacMsgEmpty = %s;' % b('GrenadeEmpty' in t.get('texts', {})),
        '    go_tacVictory = %s;' % b((t.get('victory') or {}).get('enabled')),
        '    go_tacVicCount = %d;' % len((t.get('victory') or {}).get('types', [])),
    ] + ['    go_tacVicType[%d] = "%s";' % (i, x) for i, x in enumerate((t.get('victory') or {}).get('types', []))] + [
        '    go_tacHints = %s;' % b((t.get('rebel_hints') or {}).get('enabled')),
        '    go_tacHintDelay = %.1f;' % (t.get('rebel_hints') or {}).get('delay', 0),
        '    go_tacHintFirstLen = %.1f;' % (t.get('rebel_hints') or {}).get('first_seconds', 8),
        '    go_tacHintSecondLen = %.1f;' % (t.get('rebel_hints') or {}).get('second_seconds', 6),
        '    go_tacHintPing = %.1f;' % (t.get('rebel_hints') or {}).get('ping_seconds', 5),
        '    go_tacHintGap = %.1f;' % (t.get('rebel_hints') or {}).get('gap', 6),
        '    go_tacFindDelay = %.1f;' % t['story'].get('find_delay', 3),
        '    go_tacPlanShare = %.2f;' % t['story'].get('plan_min_share', 0.5),
        '    go_tacPlanCalm = %.1f;' % t['story'].get('plan_calm_seconds', 6),
        '    go_tacPlanMaxWait = %.1f;' % t['story'].get('plan_max_wait', 360),
        '    go_tacPlanDeadDelay = %.1f;' % t['story'].get('plan_dead_delay', 6),
        '    GhostOps_ApplyLines();',
        '}', '', 'void GhostOps_ApplyLines () {']
    ls = t.get('lines') or []
    lines.append('    go_lnCount = %d;' % len(ls))
    for i, ln in enumerate(ls):
        lines += ['    go_lnId[%d] = "%s";' % (i, ln['id']), '    go_lnSpk[%d] = "%s";' % (i, ln['speaker']), '    go_lnSec[%d] = %.2f;' % (i, ln['seconds']),
                  '    go_lnClip[%d] = "%s";' % (i, ln.get('clip', ''))]
    lines += ['}', '']
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
        'fixed go_sceneClosingLen;',
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
        '    go_sceneClosingLen = %.1f;' % s['closing_seconds'],
        '    go_sceneRaynorClip = %s;' % ('null' if cfg.get('_no_voice') else 'SoundLink("%s", 0)' % s['raynor_clip']),
        '    go_sceneMarineBClip = %s;' % ('null' if cfg.get('_no_voice') else 'SoundLink("%s", 0)' % s['marine_b_clip']),
        '    go_sceneMarineAClip = %s;' % ('null' if cfg.get('_no_voice') else 'SoundLink("%s", 0)' % s['marine_a_clip']),
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
    ct = h.get('containers') or {}
    fu = h.get('convoy_fuel') or {}
    lines += ['    go_hAllowRefinery = %s;' % b(h.get('allow_refinery')), '    go_hContOn = %s;' % b(ct.get('enabled')), '    go_hFuelOn = %s;' % b(fu.get('enabled'))]
    if ct.get('enabled'):
        lines += ['    go_hContLimit = %d;' % ct['limit'], '    go_hContCost = %d;' % ct['gas_cost'], '    go_hContOwner = %d;' % ct['owner'], '    go_hContMinFree = %.2f;' % ct['min_free'], '    go_hContRange = %.2f;' % ct['place_range'],
                  '    go_hContFriendHard = %.4f;' % ct['friendly']['hard'], '    go_hContFriendOther = %.4f;' % ct['friendly']['other']]
    if fu.get('enabled'):
        lines.append('    go_hFuelCost = %d;' % fu['gas_cost'])
    tkc = h.get('turret_kits') or {}
    if tkc.get('enabled'):
        lines += ['    go_hKitOn = true;', '    go_hKitOrdered = %d;' % tkc['order']['turret_kits']]
    fsq = h.get('free_squad') or {}
    if fsq.get('enabled'):
        lines.append('    go_hFreeMarines = %d;' % fsq['marines'])
    hud = h.get('hud') or {}
    if hud:
        lines += ['    go_hHudX = %d;' % hud['offset_x'], '    go_hHudY = %d;' % hud['offset_y'], '    go_hHudW = %d;' % hud['width'], '    go_hHudH = %d;' % hud['height']]
    lns = h.get('lines') or []
    lines.append('    go_hLnCount = %d;' % len(lns))
    for i, ln in enumerate(lns):
        lines += ['    go_hLnId[%d] = "%s";' % (i, ln['id']), '    go_hLnSpk[%d] = "%s";' % (i, ln['speaker']), '    go_hLnSec[%d] = %.2f;' % (i, ln['seconds'])]
    if lns:
        lines += ['    go_hStoryFirst = %.1f;' % h['story']['first_delay'], '    go_hStoryGap = %.1f;' % h['story']['gap']]
    if h.get('autotest'):
        lines.append('    GhostOps_ApplyHansonTestConfig();')
    lines += ['}', '']
    return chr(10).join(lines)


def gen_zerohour(cfg):
    """GhostOps_ApplyZeroHourConfig(): constants of the TRaynor03 module."""
    if not cfg.get('zerohour'):  # the original-like trace profile: the module stays off
        return chr(10).join(['// no TRaynor03 module in this build (stub)', 'void GhostOps_ApplyZeroHourConfig () {', '    go_zhEnabled = false;', '}', ''])
    z = cfg['zerohour']
    b = lambda v: 'true' if v else 'false'  # noqa: E731
    o, pa, sc = z['order'], z['post_arrival'], z['scene']
    lines = ['// Generated TRaynor03 configuration', 'void GhostOps_ApplyZeroHourConfig () {', '    go_zhEnabled = true;',
             '    go_zhDebug = %s;' % b(z.get('debug_log')), '    go_zhLockProduction = %s;' % b(z['lock_production']),
             '    go_zhOrdMarines = %d;' % o['marines'], '    go_zhOrdBunkers = %d;' % o['bunkers'], '    go_zhOrdTurrets = %d;' % o['turrets'], '    go_zhOrdScvs = %d;' % o['scvs'],
             '    go_zhTargetCount = %d;' % len(z['targets']),
             '    go_zhPingEvery = %.1f;' % z['ping_every'], '    go_zhGhostX = %.4f;' % z['ghost_spawn'][0], '    go_zhGhostY = %.4f;' % z['ghost_spawn'][1],
             '    go_zhPostInterval = %.1f;' % pa['interval'], '    go_zhPostMaxActive = %d;' % pa['max_active_units'], '    go_zhPostZerglings = %d;' % pa['zerglings'],
             '    go_zhPostHydras = %d;' % pa['hydralisks'], '    go_zhPostRoaches = %d;' % pa['roaches'],
             '    go_zhIntroDelay = %.1f;' % sc['intro_delay'], '    go_zhHornerDelay = %.1f;' % sc['horner_delay'], '    go_zhRaynorLen = %.1f;' % sc['raynor_seconds'],
             '    go_zhHornerLen = %.1f;' % sc['horner_seconds'], '    go_zhRebelLen = %.1f;' % sc['rebel_seconds']]
    for i, t in enumerate(z['targets']):
        lines.append('    go_zhTargetId[%d] = %d;' % (i, t))
    for i, k in enumerate(ZH_VOICE_KEYS):
        lines.append('    go_zhVoiceId[%d] = "%s";' % (i, '' if cfg.get('_no_voice') else z['voice'][k]['clip']))
        lines.append('    go_zhVoiceLen[%d] = %.1f;' % (i, z['voice'][k]['seconds']))
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


TRACE_RE = re.compile(r'^gt_(Transmission|Tip|Objective|Alert|Rebel|Start|Intro|Briefing|Zerg|AttackWaves|SpineCrawler|Victory|Defeat|TenMinute|FiveMinute|TwoMinute|OneMinute|DropPod|Evacuation|Warning|Nydus)')


def trace_hooks(text, adapter):
    """Development only (profile key ce0.trace): a TRACE journal line at the start of every original scene / transmission / wave function, to compare what plays when."""
    if not adapter.get('trace'):
        return []
    hooks = []
    for m in re.finditer(r'^bool (gt_\w+)_Func \(', text, re.M):
        name = m.group(1)
        if not TRACE_RE.match(name):
            continue
        fend = text.find('\n}', m.start())
        if text[m.start():fend].count('// Actions') != 1:
            continue
        hooks.append({'function': name + '_Func', 'anchor': '// Actions', 'where': 'before', 'call': 'if (runActions) { GhostOps_Ce0_Trace("%s"); }' % name})
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
    for hook in hook_list(adapter) + trace_hooks(text, adapter):
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
    tail = ''
    if adapter.get('defence'):
        tail += defence_wave_tail(text, adapter) + chr(10)
    if adapter.get('tail_source'):
        tail += read(os.path.join(ROOT, adapter['tail_source']), 'r') + chr(10)
    if tail:
        tail_nl = nl.join(tail.replace('\r\n', '\n').split('\n'))
        edits.append((len(text), nl + TAIL_BEGIN + nl + tail_nl.rstrip() + nl + TAIL_END))
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
            for ln in t.get('lines') or []:
                v = ln['text'][lang]
                if ln.get('large', True):
                    v = EXPLAIN_STYLE[0] + v + EXPLAIN_STYLE[1]
                out.setdefault(loc, []).append((LINE_TEXT_PREFIX + ln['id'], v))
            all_texts = dict(TAC_DEFAULT_TEXTS, **t['texts'])
            for k in tuple(k for k in TAC_TEXT_KEYS if k in all_texts) + tuple(k for k in TAC_EXTRA_TEXT_KEYS if k in all_texts):
                v = all_texts[k][lang].replace('{aim_time}', '%g' % t['nuke']['aim_time']).replace('{flight_time}', '%g' % t['nuke']['flight_time'])
                if k in TAC_EXPLAIN_KEYS:
                    v = EXPLAIN_STYLE[0] + v + EXPLAIN_STYLE[1]
                out.setdefault(loc, []).append((TAC_TEXT_PREFIX + k, v))
            if t.get('grenade'):
                g = t['texts']
                out.setdefault(loc, []).append(('Button/Name/GhostOpsArmorPiercing', g['GrenadeName'][lang]))
                out.setdefault(loc, []).append(('Button/Tooltip/GhostOpsArmorPiercing', g['GrenadeTip'][lang]))
                out.setdefault(loc, []).append(('Button/Hotkey/GhostOpsArmorPiercing', (t.get('grenade') or {}).get('hotkey', 'E')))
    df = cfg.get('defence')
    if df:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in DEF_TEXT_KEYS + tuple(k for k in DEF_OPTIONAL_TEXT_KEYS if k in df['texts']):
                v = df['texts'][k][lang]
                if k in DEF_EXPLAIN_KEYS:
                    v = EXPLAIN_STYLE[0] + v + EXPLAIN_STYLE[1]
                out.setdefault(loc, []).append((DEF_TEXT_PREFIX + k, v))
            out.setdefault(loc, []).append(('Button/Name/GhostOpsTurretSalvo', df['texts']['SalvoName'][lang]))
            out.setdefault(loc, []).append(('Button/Tooltip/GhostOpsTurretSalvo', df['texts']['SalvoTip'][lang]))
            out.setdefault(loc, []).append(('Button/Hotkey/GhostOpsTurretSalvo', df['salvo'].get('hotkey', 'G')))
    da = cfg.get('detector_analysis')
    if da and da.get('enabled'):
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            out.setdefault(loc, []).append(('Button/Name/GhostOpsDetectorAnalysis', da['texts']['Name'][lang]))
            out.setdefault(loc, []).append(('Button/Tooltip/GhostOpsDetectorAnalysis', da['texts']['Tip'][lang]))
    pn = cfg.get('panel')
    if pn and pn.get('enabled'):
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k, v in pn['texts'].items():
                out.setdefault(loc, []).append((PANEL_TEXT_PREFIX + k, v[lang]))
    hs = cfg.get('hanson')
    if hs:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            ht = dict(HANSON_TEXT_DEFAULTS, **hs['texts'])
            cts = hs.get('containers') or {}
            fill = lambda v: v if not cts else (v.replace('{gas}', '%g' % cts['gas_cost']).replace('{limit}', '%g' % cts['limit']).replace('{damage}', '%g' % cts['damage']).replace('{radius}', '%g' % cts['radius']).replace('{range}', '%g' % cts['place_range']).replace('{friendly}', '%g' % round(100 * cts['friendly']['hard'], 1)))  # noqa: E731
            for k in HANSON_TEXT_KEYS + tuple(k for k in HANSON_EXTRA_TEXT_KEYS if k in ht):
                out.setdefault(loc, []).append((HANSON_TEXT_PREFIX + k, fill(ht[k][lang])))
            if (hs.get('turret_kits') or {}).get('enabled'):
                out.setdefault(loc, []).append((HANSON_TEXT_PREFIX + 'KitsHint', kits_hint(hs['turret_kits'], lang)))
            for ln in hs.get('lines') or []:
                v = ln['text'][lang]
                out.setdefault(loc, []).append((HANSON_TEXT_PREFIX + 'L_' + ln['id'], EXPLAIN_STYLE[0] + v + EXPLAIN_STYLE[1]))
            if (hs.get('containers') or {}).get('enabled'):
                out.setdefault(loc, []).append(('Button/Name/GhostOpsPlaceContainer', ht['ContainerName'][lang]))
                out.setdefault(loc, []).append(('Button/Tooltip/GhostOpsPlaceContainer', fill(ht['ContainerTip'][lang])))
                out.setdefault(loc, []).append(('Button/Hotkey/GhostOpsPlaceContainer', hs['containers']['hotkey']))
                out.setdefault(loc, []).append(('Unit/Name/GhostOpsFuelContainer', ht['ContainerUnitName'][lang]))
    zh = cfg.get('zerohour')
    if zh:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in ZH_TEXT_KEYS:
                out.setdefault(loc, []).append((ZH_TEXT_PREFIX + k, zh['texts'][k][lang]))
    sc = cfg.get('scene')
    if sc:
        for loc, lang in (('ruRU', 'ru'), ('enUS', 'en')):
            for k in SCENE_TEXT_KEYS:
                v = sc['texts'][k][lang]
                if k == 'Closing':  # the explanation is shown in the larger style (the Explain text is a directive and is large already)
                    v = EXPLAIN_STYLE[0] + v + EXPLAIN_STYLE[1]
                out.setdefault(loc, []).append((SCENE_TEXT_PREFIX + k, v))
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
    if 'zerohour' in gens:
        extra += gen_zerohour(cfg) + '\n' + gen_defence(cfg, adapter) + '\n'
    if 'hanson' in gens:
        extra += gen_hanson_test(cfg) + '\n' + gen_hanson(cfg) + '\n'
    if cfg.get('scene'):
        extra += gen_scene(cfg) + '\n'
    if adapter.get('detector_analysis'):
        extra += chr(10).join(['// Generated detector-analysis configuration', 'void GhostOps_ApplyDetectorAnalysisConfig () {', '    go_daEnabled = true;', '}', '']) + chr(10)
    if cfg.get('ce0'):
        extra += gen_ce0(cfg) + '\n'
    if cfg.get('campaign'):
        extra += gen_campaign(cfg) + '\n'
    return core.rstrip() + '\n\n' + gen_config(cfg) + '\n' + gen_panel(cfg) + '\n' + extra + ad


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


def shared_lines_dir():
    """Folder of the shared lines tables (docs/SHARED_LINES.md of the voice lab): env GHOSTOPS_LINES_DIR, else the one line of build/shared_lines_dir.txt, else none."""
    d = os.environ.get('GHOSTOPS_LINES_DIR')
    if not d:
        p = os.path.join(ROOT, 'build', 'shared_lines_dir.txt')
        if os.path.isfile(p):
            d = read(p, 'r').strip()
    return d or None


def apply_shared_lines(raw, adapter):
    """Put the texts of the shared lines tables (one JSON per mission/profile, edited by Voice Studio and by hand) into the RAW config, BEFORE the presets are merged.
    No folder configured / no table for the mission -> nothing changes and the texts of the config stay the source. The config FILE is never written; a table that
    cannot be read is an error (never a silent fallback to older texts). Afterwards the table is marked 'read by the game build' (the studio shows it)."""
    d = shared_lines_dir()
    if not d:
        return raw
    import lines_table  # tools/lines_table.py = unchanged copy of voice_studio/lines_table.py of the voice lab
    mission = adapter['mission']
    name = os.path.basename(adapter['config'])
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith('.lines.json') or fn.split('.')[0] != mission:
            continue
        table = lines_table.read_table(os.path.join(d, fn))
        res = lines_table.apply_texts_to_config(raw, table, name)
        if res['skipped']:
            raise ConfigError('shared lines table %s: binding not found in %s: %s' % (fn, name, ', '.join('%s (%s)' % s for s in res['skipped'])))
        try:
            lines_table.mark_game_read(os.path.join(d, fn), tool='build.py', info={'config': name})
        except OSError:
            pass  # a read-only table folder: the texts are applied, only the studio's "game reads the table" mark is not written
    return raw


def resolve_config(adapter, preset=None, diag=False, no_voice=False):
    """Returns (merged config, preset name or None). Missions without presets ignore nothing: an explicit
    preset for them is an error, an unknown preset name is an error (never a silent fallback)."""
    raw = apply_shared_lines(load_json(adapter['config']), adapter)
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
        chain, cur = [], name  # the whole chain of "extends" (a hidden development preset may extend another development preset)
        while cur is not None:
            if cur not in presets:
                raise ConfigError('preset "%s" extends unknown preset "%s"' % (chain[-1] if chain else name, cur))
            if cur in chain:
                raise ConfigError('preset "%s" extends itself' % cur)
            chain.append(cur)
            cur = presets[cur].get('extends')
        cfg = base
        for link in reversed(chain):
            cfg = deep_merge(cfg, presets[link].get('overrides', {}))
        cfg = {k: v for k, v in cfg.items() if v is not None}  # an override with null removes a whole module of the base config (the original-like trace profile)
        cfg['profile'] = {'name': name, 'label': presets[name]['label'], 'message': presets[name]['message'],
                          'message_en': presets[name].get('message_en', presets[name]['message'])}
    if diag:
        cfg = deep_merge(cfg, {'difficulty': {'show_message': True}})
    raw_audio = cfg.get('audio')
    if no_voice:  # explicit variant without added voice: no clip is imported or played, portraits / texts / order of the scenes are unchanged
        cfg = {k: v for k, v in cfg.items() if k != 'audio'}
        if (raw_audio or {}).get('talk'):
            cfg['audio'] = {'talk': raw_audio['talk']}  # silent mouth drivers are not voice
        cfg['_no_voice'] = True
        for ln in (cfg.get('tactical') or {}).get('lines') or []:
            ln['clip'] = ''  # the lines keep their text, portrait and talking animation; only the clip is dropped
    return cfg, name


def apply_ce0(adapter, cfg):
    """Optional modules chosen by the RESOLVED config, added to a COPY of the adapter:
    key "ce0" (development probe, only in *_dev profiles) and key "campaign" (the campaign journal of a playable profile that takes part in the
    economy). Without a key the adapter is returned untouched, so a profile without it contains nothing of it."""
    if not cfg.get('ce0') and not cfg.get('campaign') and not cfg.get('defence') and not (cfg.get('detector_analysis') or {}).get('enabled'):
        return adapter
    a = json.loads(json.dumps(adapter))
    a['generators'] = adapter.get('generators', ['tactical'] if adapter.get('modules') else [])
    mods = list(adapter.get('modules') or [])
    hooks = list(adapter.get('extra_hooks', []))
    if cfg.get('defence'):
        mods.append('core/GhostOpsDefence.galaxy')
        for w in adapter.get('defence_waves', []):
            hooks.append({'function': w['function'], 'before': '// Actions', 'call': 'if (go_defEnabled && runActions) { return GhostOps_DEF_%s(testConds, runActions); }' % w['function'][3:-5]})
        # the original starts the AI (and with it the attack waves) in the intro, before the mission start hooks run: the flag must be set first
        hooks.append({'function': 'gt_IntroSequence_Func', 'before': 'TriggerExecute(gt_StartAI, true, false);', 'call': 'GhostOps_ApplyDefenceConfig();'})
        # the original tips ask for a Reactor / Engineering Bay and talk about buildings the player does not have here
        for tip in ('gt_TipBunkerQ_Func', 'gt_TipReactorQ_Func', 'gt_TipEngineeringBayQ_Func', 'gt_TipMissileTurretQ_Func'):
            hooks.append({'function': tip, 'before': '// Actions', 'call': 'if (go_defEnabled && runActions) { return true; }'})
        hooks.append({'function': 'gt_StartTimers_Func', 'after': 'TimerWindowSetColor(gv_evacuationTimerWindow, c_timerWindowColorTime, Color(0.00, 100.00, 0.00), 0.0);', 'call': 'GhostOps_DEF_OnTimersStarted();'})
        a['defence'] = True
    if (cfg.get('detector_analysis') or {}).get('enabled'):
        mods.append('core/GhostOpsDetector.galaxy')
        st = (adapter.get('start_hooks') or [adapter.get('start_hook')])[0]
        hooks.append({'function': st['function'], 'after': st['after'], 'call': 'GhostOps_DA_Start();'})
        a['detector_analysis'] = True
    if cfg.get('campaign'):
        mods.append('core/GhostOpsCampaign.galaxy')
        hooks += list(adapter.get('campaign_hooks', []))
        a['campaign'] = True
    if cfg.get('ce0'):
        if 'ce0_trace' not in adapter:
            mods += ['core/GhostOpsCe0.galaxy', adapter['ce0_extra']]
        elif cfg.get('defence') or cfg.get('zerohour'):
            mods += ['core/GhostOpsCe0.galaxy', adapter['ce0_trace'], adapter['ce0_extra']]
        else:  # the original-like profile: the trace probe alone
            mods += ['core/GhostOpsCe0.galaxy', adapter['ce0_trace'], adapter['ce0_trace_only']]
        hooks += list(adapter.get('ce0_hooks', []))
        a['ce0'] = True
        if cfg['ce0'].get('trace'):
            a['trace'] = True  # every original scene / transmission / wave function writes a TRACE line (patch_script adds the hooks)
    a['modules'] = mods
    a['extra_hooks'] = hooks
    return a


def load_plan(path):
    """An operation plan written by the launcher: {"operation_id", "mission", "preset", "order": {...}}. Only these keys are accepted."""
    plan = load_json_file(path)
    if not isinstance(plan, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', str(plan.get('operation_id', ''))):
        raise ConfigError('plan: operation_id must be 1..40 characters of [A-Za-z0-9_-]')
    for k in plan:
        if k not in ('operation_id', 'mission', 'preset', 'order', 'cost'):
            raise ConfigError('plan: unsupported key "%s"' % k)
    return plan


def load_json_file(path):
    with open(path, encoding='utf-8-sig') as f:
        return json.load(f)


def context(args):
    adapter = load_adapter(args.mission)
    no_voice = bool(getattr(args, 'no_voice', False))
    cfg, preset = resolve_config(adapter, getattr(args, 'preset', None), getattr(args, 'diag', False), no_voice)
    if no_voice:
        adapter = json.loads(json.dumps(adapter))
        adapter['_novoice'] = True
    plan_path = getattr(args, 'plan', None)
    if plan_path:
        plan = load_plan(plan_path)
        if plan.get('mission') not in (None, args.mission):
            raise ConfigError('plan is for mission %s, not %s' % (plan.get('mission'), args.mission))
        if not cfg.get('campaign'):
            raise ConfigError('profile %s has no campaign key: it cannot carry an operation' % preset)
        cfg = deep_merge(cfg, {'campaign': {'operation_id': plan['operation_id']}})
        if plan.get('order') is not None:
            section = adapter.get('order_section')
            if not section:
                raise ConfigError('mission %s takes no order' % args.mission)
            patch = {'order': plan['order']}
            for key in reversed(adapter.get('order_path', [])):  # a mission whose order lives deeper than the section (THanson01: hanson.turret_kits.order)
                patch = {key: patch}
            cfg = deep_merge(cfg, {section: patch})
        adapter = json.loads(json.dumps(adapter))
        adapter['_op'] = plan['operation_id']
    return apply_ce0(adapter, cfg), cfg, preset


def key_for(adapter, preset):
    return adapter['mission'] + ('_' + preset if preset else '') + ('__' + adapter['_op'] if adapter.get('_op') else '') + ('_novoice' if adapter.get('_novoice') else '')


def output_name(adapter, preset):
    name = adapter['output_map_file']
    stem, ext = os.path.splitext(name)
    if preset:
        stem = '%s_%s' % (stem, preset)
    if adapter.get('_op'):  # an operation of the campaign: its own unique file, never overwritten by a later build (contract 14.2, step 4)
        stem = '%s__%s' % (stem, adapter['_op'])
    if adapter.get('_novoice'):
        stem += '_novoice'
    return stem + ext


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
        'operation_id': adapter.get('_op'),
        'data_hash': data_hash(cfg) if cfg.get('campaign') or cfg.get('ce0') else None,
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
    for tid, member, fa, secs in talk_clips(cfg):
        wav = silent_wav(secs)
        arc.set_file(member, wav)
        new_members.append(member)
        manifest['audio'].append({'id': tid, 'member': member, 'source': 'silent:%g' % secs, 'sha256': sha256(wav)})
    if new_members:
        arc.update_listfile(new_members)
    manifest['text_patches'] = []
    manifest['hotkeys'] = []
    for loc, entries in text_entries(cfg).items():
        # the key of a button is read from GameHotkeys.txt (NOT from GameStrings.txt: a key written there is ignored by the game); one line per layout of the hotkey profile
        hk = [(k, v) for k, v in entries if k.startswith(HOTKEY_PREFIX)]
        entries = [(k, v) for k, v in entries if not k.startswith(HOTKEY_PREFIX)]
        if hk:
            hk = [(k + suf, v) for k, v in hk for suf in ('', '_USD', '_NRS', '_USDL')]
            hmember = loc + '.SC2Data' + chr(92) + 'LocalizedData' + chr(92) + 'GameHotkeys.txt'
            hold = arc.read(hmember)
            if hold is None:
                htext = ''.join('%s=%s' % (k, v) + CRLF for k, v in hk)
                arc.set_file(hmember, UTF8_BOM + htext.encode('utf-8'))
                arc.update_listfile([hmember])
                manifest['hotkeys'].append({'member': hmember, 'locale': loc, 'keys': [k for k, _ in hk], 'created': True, 'sha256': sha256(UTF8_BOM + htext.encode('utf-8'))})
            else:
                hnew = patch_strings(hold.decode('utf-8-sig'), hk)
                hbom = UTF8_BOM if hold.startswith(UTF8_BOM) else b''
                arc.set_file(hmember, hbom + hnew.encode('utf-8'))
                manifest['hotkeys'].append({'member': hmember, 'locale': loc, 'keys': [k for k, _ in hk], 'created': False})
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
    hpatches = man.get('hotkeys', [])
    expected = [man['script_member'].lower()] + existing + [t_['member'].lower() for t_ in tpatches] + [h_['member'].lower() for h_ in hpatches if not h_['created']]
    check('only %s differ from source (differs: %s)' % (expected, changed), changed == sorted(expected))
    created = sorted([p_['member'].lower() for p_ in patches if p_['created']] + [x['member'].lower() for x in man.get('audio', [])] + [h_['member'].lower() for h_ in hpatches if h_['created']])
    added = sorted(n.lower() for n in a_out.names() if not n.startswith('(') and n.lower() not in [x.lower() for x in a_src.names()])
    check('files added to the map: %s' % created, added == created)
    for x in man.get('audio', []):
        got = a_out.read(x['member'])
        check('audio %s: %s is the project file (sha256 %s...)' % (x['id'], x['member'], x['sha256'][:8]), got is not None and sha256(got) == x['sha256'] and got[:4] == b'RIFF')
    new = a_out.read(man['script_member']).decode('utf-8-sig')
    n_hooks = len(hook_list(adapter)) + len(trace_hooks(a_src.read(man['script_member']).decode('utf-8-sig'), adapter))
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
    stripped = re.sub(r'\r?\n' + re.escape(TAIL_BEGIN) + r'.*?' + re.escape(TAIL_END), '', stripped, flags=re.S)
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
    for h_ in hpatches:
        got = a_out.read(h_['member'])
        if h_['created']:
            check('%s: %d hotkey line(s), created' % (h_['member'], len(h_['keys'])), got is not None and sha256(got) == h_['sha256'] and all((k + '=') in got.decode('utf-8-sig') for k in h_['keys']))
        else:
            check('%s: %d hotkey line(s) added, restores exactly' % (h_['member'], len(h_['keys'])), unpatch_strings(got.decode('utf-8-sig')) == a_src.read(h_['member']).decode('utf-8-sig') and all((k + '=') in got.decode('utf-8-sig') for k in h_['keys']))
    check('script source is ASCII', new.isascii())
    print('VERIFY ' + ('PASSED' if ok else 'FAILED'))
    return 0 if ok else 5


def sc2_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq SC2_x64.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True, creationflags=0x08000000).stdout
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
    try:
        isolation.check_change(dest, 'overwritten')
    except isolation.Protected as e:
        print('refused: %s' % e)
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
    try:
        isolation.check_change(rec['file'], 'removed')
    except isolation.Protected as e:
        print('refused: %s' % e)
        return 6
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
        if os.path.exists(rec['file']) and isolation.is_protected(rec['file']):
            if sha256(read(rec['file'])) == sha256(read(out)):
                print('already installed and identical: %s' % rec['file'])
                return 0
            print('refused: %s is a protected version of the Owner and differs from this build; it is kept as it is' % rec['file'])
            return 6
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
    adapter0, cfg0, preset0 = context(args)
    kept = os.path.join(SC2_DIR, 'Maps', 'GhostOps', output_name(adapter0, preset0))
    if os.path.isfile(kept) and isolation.is_protected(kept):
        # the Owner's version: started as it is, never rebuilt, never replaced (CLI, launcher and campaign window all come here)
        reg = isolation.load()[isolation.key(kept)]
        if sha256(read(kept)) != reg['sha256']:
            print('refused: the installed %s differs from the registered Owner version; nothing is changed' % os.path.basename(kept))
            return 6
        print('Owner version kept as it is (not rebuilt): %s' % kept)
        return 0
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


def prepare_existing(args, progress=None):
    """The map set of a started operation is IMMUTABLE (contract 14.2): when its unique map file is installed, nothing is built and nothing is replaced;
    only a missing file is rebuilt from the same plan."""
    note = progress or (lambda stage: None)
    adapter, cfg, preset = context(args)
    _, dest = launch_command(adapter, cfg, preset)
    if adapter.get('_op') and os.path.isfile(dest) and os.path.exists(install_manifest_path(key_for(adapter, preset))):
        note('check')
        if sc2_running():
            print('StarCraft II is already running: close it first (this launcher never closes your game).')
            return 7
        print('operation set already installed and kept as it is: %s' % dest)
        return 0
    return prepare(args, progress)


def read_build_manifest(args):
    """The manifest of the last build of the plan / profile in `args` (data_hash, output sha256, ...), or None."""
    adapter, cfg, preset = context(args)
    path = build_manifest_path(key_for(adapter, preset))
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _raw_start(command):
    ps = "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = '%s'; CurrentDirectory = '%s' } | Out-Null" % (
        command.replace("'", "''"), os.path.join(SC2_DIR, 'Support64'))
    return subprocess.run(['powershell', '-NoProfile', '-Command', ps]).returncode


def start_detached(command, owner=False):
    """Start SC2 outside this process tree (it survives the launcher closing).

    The ONLY way a game process is started by this project. owner=True is the Owner's normal launch (launcher / campaign window / `build.py launch`): the
    command is used as it is - unless the environment variable GHOSTOPS_TEST is set (every test tool sets it, also through the GUI): then, like every call
    without owner=True, the game is started as a TEST game by test_launch.launch_test_game: ordinary window 1024x768 on the second monitor (the primary only when
    there is no other), muted (our process only), never full screen, never raised; the actual mode / size / monitor of the window are verified afterwards and a
    window that does not comply is closed (our own pid only)."""
    if owner and not os.environ.get('GHOSTOPS_TEST'):
        m = re.search(r'-run "([^"]+[.]SC2Map)"', command, re.I)
        if m and os.path.isfile(m.group(1)) and os.path.dirname(m.group(1)).lower() == isolation.MAPS_DIR.lower():
            isolation.protect(m.group(1), "started by the Owner's normal launch")  # a save may be bound to it from now on
        return _raw_start(command)
    import test_launch
    return 0 if test_launch.launch_test_game(command) else 8


def cmd_prepare(args):
    """Build + verify + install of the profile exactly as the launcher does (a protected Owner version is kept as it is). Used by the test queue in a fresh process."""
    return prepare(args)


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
    return start_detached(command, owner=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'verify', 'install', 'uninstall', 'launch', 'prepare'])
    p.add_argument('--mission', default='traynor02')
    p.add_argument('--source')
    p.add_argument('--plan', help='an operation plan (JSON written by the launcher): builds the unique map file of that operation')
    p.add_argument('--preset', help='balance profile of the mission (TRaynor01: easy, hard); default: the mission default')
    p.add_argument('--diag', action='store_true', help='show the detailed in-game diagnostic message in this build')
    p.add_argument('--no-voice', dest='no_voice', action='store_true', help='explicit variant WITHOUT added voice: no clip is imported or played (portraits, texts, order of the scenes and mechanics are kept); its own map file name ends with _novoice')
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
