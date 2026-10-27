"""Mission Workshop (core, no GUI code, so it is testable): variants of an existing mission, their settings, validation, saving and the build of a FREE test.

A variant belongs to ONE mission and starts as a copy of a free profile of it (the base). The player changes the settings the mission really supports (a field exists only when
its path is present in the resolved configuration of the base: the mechanic is in the mission), saves the variant, builds it and starts a free test. Nothing here touches the
campaign: a free test never spends and never credits the stock of the real campaign, its result is never offered for crediting.

Storage (data of the Owner, NOT in the repository): %APPDATA%\\GhostOps\\workshop\\<mission>\\<id>.json (env GHOSTOPS_WORKSHOP_DIR overrides the folder; tests use their own).
A variant file holds the name, the source (base profile, its label, the hash of its resolved configuration at the time of creation), the changed fields (path -> value), the revision
counter and, once built, the COMPLETE resolved configuration of that build (the snapshot), the revision, the plan file and the settings hash. A built revision never changes: the base
profile may change later, the old map and the old snapshot stay as they were; a change of the settings makes a new revision with its own map file name.

The plan of a build is the existing operation-plan mechanism of tools/build.py with a `snapshot` (the full configuration is used as it is; nothing is inherited at build time).
"""
import copy
import hashlib
import json
import os
import time

import build

SECTIONS = [('squad', 'Отряд и снабжение'), ('ghosts', 'Призраки и способности'), ('defence', 'Оборона и союзники'), ('special', 'Особенности миссии'),
            ('enemy', 'Противник и темп'), ('economy', 'Экономика подготовки')]
MISSIONS = ('traynor03', 'thanson01', 'thanson02')


def workshop_dir():
    d = os.environ.get('GHOSTOPS_WORKSHOP_DIR')
    if d:
        return d
    return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'GhostOps', 'workshop')


class Field:
    """One setting. `path` is a tuple of keys / list indexes in the resolved configuration; `scale` turns the stored value into the displayed one (x100 for percent)."""

    def __init__(self, fid, section, label, path, kind='float', unit='', lo=None, hi=None, step=1.0, scale=1.0, hint='', warn=None, missions=None, choices=None, visible_if=None, digits=None):
        self.id, self.section, self.label, self.path, self.kind, self.unit = fid, section, label, tuple(path), kind, unit
        self.lo, self.hi, self.step, self.scale, self.hint, self.warn = lo, hi, step, scale, hint, warn
        self.missions, self.choices, self.visible_if, self.digits = missions, choices, visible_if, digits

    def display(self, raw):
        if self.kind == 'bool':
            return bool(raw)
        if self.kind == 'choice':
            return raw
        v = raw * self.scale
        if self.kind == 'int':
            return int(round(v))
        return round(v, self.digits if self.digits is not None else 3)

    def store(self, shown):
        if self.kind in ('bool', 'choice'):
            return shown
        v = shown / self.scale
        return int(round(v)) if self.kind == 'int' else round(v, 6)


def _get(cfg, path):
    cur = cfg
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and isinstance(k, int) and 0 <= k < len(cur):
            cur = cur[k]
        else:
            raise KeyError(path)
    return cur


def _set(cfg, path, value):
    cur = cfg
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value


def _has(cfg, path):
    try:
        _get(cfg, path)
        return True
    except KeyError:
        return False


def _f(*a, **k):
    return Field(*a, **k)


FIELDS = [
    # ---- squad and supply ------------------------------------------------------------------------------------------------------------------------------
    _f('zh_marines', 'squad', 'Морпехи (всего)', ('zerohour', 'order', 'marines'), 'int', 'шт.', 6, 40, 1, hint='Общее число морпехов отряда: первые шесть входят в оплаченный заказ'),
    _f('zh_bunkers', 'squad', 'Бункеры (комплекты)', ('zerohour', 'order', 'bunkers'), 'int', 'шт.', 0, 12, 1, hint='Бункеры строит игрок из комплектов'),
    _f('zh_turrets', 'squad', 'Ракетные турели (комплекты)', ('zerohour', 'order', 'turrets'), 'int', 'шт.', 0, 12, 1, hint='Турели строит игрок из комплектов'),
    _f('zh_scvs', 'squad', 'КСМ (добавленные)', ('zerohour', 'order', 'scvs'), 'int', 'шт.', 0, 16, 1, hint='Добавленные рабочие сверх штатных'),
    _f('th1_kits', 'squad', 'Комплекты ракетных турелей', ('hanson', 'turret_kits', 'order', 'turret_kits'), 'int', 'шт.', 0, 30, 1, hint='Турели строит игрок из комплектов', missions=('thanson01',)),
    _f('th1_scvs', 'squad', 'КСМ (добавленные)', ('hanson', 'turret_kits', 'order', 'scvs'), 'int', 'шт.', 0, 16, 1, hint='Рабочих всего = штатные (4) + добавленные', missions=('thanson01',)),
    _f('th1_marines', 'squad', 'Морпехи (добавленные)', ('hanson', 'free_squad', 'marines'), 'int', 'шт.', 0, 40, 1, hint='Морпехи отряда бесплатного теста', missions=('thanson01',)),
    _f('th2_marines', 'squad', 'Морпехи (добавленные)', ('hanson', 'free_squad', 'marines'), 'int', 'шт.', 0, 40, 1, missions=('thanson02',), hint='К штатным шести морпехам миссии'),
    _f('th2_scvs', 'squad', 'КСМ (добавленные)', ('hanson', 'free_squad', 'scvs'), 'int', 'шт.', 0, 16, 1, missions=('thanson02',), hint='К штатным шести КСМ миссии'),
    _f('th2_bunkers', 'squad', 'Комплекты бункеров', ('hanson', 'bunker_kits', 'order', 'bunker_kits'), 'int', 'шт.', 0, 8, 1, hint='Каждый бункер вмещает четверых'),
    _f('th2_kits', 'squad', 'Комплекты ракетных турелей', ('hanson', 'turret_kits', 'order', 'turret_kits'), 'int', 'шт.', 0, 30, 1, missions=('thanson02',)),
    # ---- ghosts and abilities --------------------------------------------------------------------------------------------------------------------------
    _f('perm_cloak', 'ghosts', 'Постоянная маскировка призраков', ('operatives', 'ghost_permanent_cloak'), 'bool', hint='Маскировка включена всегда, днём и ночью, энергия не расходуется'),
    _f('fire_control', 'ghosts', 'Переключатель автоогня призраков', ('ghost_tuning', 'fire_control', 'enabled'), 'bool', hint='Кнопка и клавиша F/G: призраки сами выбирают цели или стреляют только по приказу', missions=('thanson01',), visible_if=lambda c: _get(c, ('ghost_tuning', 'fire_control', 'enabled')) is not None),
    _f('night_net', 'ghosts', 'Расход энергии на маскировку ночью', ('epidemic', 'night_cloak', 'net_per_second'), 'float', 'ед./с', -10, 0, 0.5, hint='Только при ограниченной маскировке; 0 = без расхода', warn=(-5, 0), visible_if=lambda c: not _get(c, ('operatives', 'ghost_permanent_cloak'))),
    _f('det_early', 'ghosts', 'Ранний анализ детекторов', ('detector_analysis', 'early_warning', 'enabled'), 'bool', hint='Круг зоны обнаружения виден заранее и у детектора в тумане'),
    _f('det_margin', 'ghosts', 'Запас раннего предупреждения', ('detector_analysis', 'early_warning', 'margin'), 'float', 'клеток', 1, 13, 1, hint='На сколько клеток раньше границы обнаружения появляется круг (штатный радар ищет на 25 клеток вокруг призрака)', warn=(4, 13), visible_if=lambda c: bool(_get(c, ('detector_analysis', 'early_warning', 'enabled')))),
    _f('grenade_charges', 'ghosts', 'Бронебойные заряды', ('tactical', 'grenade', 'charges'), 'int', 'шт. каждому призраку', 1, 6, 1, hint='Заряд у каждого призрака свой, без пополнения', warn=(2, 6)),
    _f('grenade_damage', 'ghosts', 'Урон бронебойного удара', ('tactical', 'grenade', 'damage'), 'float', 'ед. по зданию', 50, 3000, 50, warn=(300, 1500), digits=0),
    _f('grenade_radius', 'ghosts', 'Радиус бронебойного удара', ('tactical', 'grenade', 'radius'), 'float', 'клеток', 0.5, 8, 0.5, warn=(1.5, 5)),
    _f('grenade_range', 'ghosts', 'Дальность бронебойного удара', ('tactical', 'grenade', 'range'), 'float', 'клеток', 3, 20, 1, warn=(6, 14)),
    _f('nuke_count', 'ghosts', 'Ядерные ракеты', ('tactical', 'nuke', 'count'), 'int', 'шт. на весь отряд', 1, 4, 1, hint='Общий запас на операцию; одновременно взведена одна', warn=(1, 3)),
    _f('nuke_range', 'ghosts', 'Дальность наведения ядерного удара', ('tactical', 'nuke', 'range'), 'float', 'клеток', 12, 60, 2, warn=(24, 56)),
    _f('nuke_damage', 'ghosts', 'Урон ядерного удара (в центре)', ('tactical', 'nuke', 'damage', 'amount'), 'float', 'ед.', 100, 3000, 50, warn=(400, 1200), digits=0),
    _f('nuke_struct', 'ghosts', 'Добавка ядерного удара по зданиям', ('tactical', 'nuke', 'damage', 'structure_bonus'), 'float', 'ед.', 0, 3000, 50, warn=(300, 1500), digits=0),
    _f('nuke_r1', 'ghosts', 'Радиус полного урона ядерки', ('tactical', 'nuke', 'damage', 'areas', 0, 0), 'float', 'клеток (100%)', 2, 16, 0.5, hint='Зоны: полный урон / половина / четверть', warn=(5, 10)),
    _f('nuke_r2', 'ghosts', 'Радиус половинного урона', ('tactical', 'nuke', 'damage', 'areas', 1, 0), 'float', 'клеток (50%)', 3, 24, 0.5, warn=(8, 16)),
    _f('nuke_r3', 'ghosts', 'Радиус четвертного урона', ('tactical', 'nuke', 'damage', 'areas', 2, 0), 'float', 'клеток (25%)', 4, 32, 0.5, warn=(12, 24)),
    _f('snipe_cd', 'ghosts', 'Перезарядка снайперского выстрела', ('ghost_tuning', 'snipe', 'cooldown'), 'float', 'игровых секунд', 0.5, 10, 0.1, hint='Промах тоже запускает перезарядку', warn=(1.0, 4.0), missions=('thanson01',)),
    _f('snipe_dmg', 'ghosts', 'Урон снайперского выстрела', ('ghost_tuning', 'snipe', 'damage'), 'float', 'ед.', 20, 1000, 10, warn=(100, 500), missions=('thanson01',), digits=0),
    _f('shot_range', 'ghosts', 'Боевая дальность выстрела', ('ghost_tuning', 'snipe', 'rifle_shot', 'range'), 'float', 'клеток', 3, 20, 1, warn=(6, 14)),
    _f('shot_assist', 'ghosts', 'Радиус помощи прицеливанию', ('ghost_tuning', 'snipe', 'rifle_shot', 'assist_radius'), 'float', 'клеток', 0, 5, 0.5, warn=(0, 3)),
    # ---- defence and allies ----------------------------------------------------------------------------------------------------------------------------
    _f('garrison_dmg', 'defence', 'Урон гарнизона', ('tactical', 'garrison', 'damage_multiplier'), 'float', '% от обычного', 10, 1000, 5, scale=100, hint='Множитель обычного урона морпехов гарнизона; здоровье, броня, скорость и лечение не меняются', warn=(50, 200), digits=0),
    _f('rebel_dmg', 'defence', 'Урон повстанцев', ('tactical', 'rebels', 'damage_multiplier'), 'float', '% от обычного', 10, 1000, 5, scale=100, hint='Множитель урона спасённых бойцов', warn=(70, 250), digits=0),
    _f('salvo_range', 'defence', 'Дальность залпа турелей', ('defence', 'salvo', 'range'), 'float', 'клеток', 4, 20, 1, warn=(8, 14)),
    _f('salvo_missiles', 'defence', 'Ракет в залпе', ('defence', 'salvo', 'missiles'), 'int', 'шт.', 1, 12, 1, warn=(3, 8)),
    _f('salvo_damage', 'defence', 'Урон одной ракеты залпа', ('defence', 'salvo', 'damage'), 'float', 'ед.', 5, 200, 5, warn=(15, 60), digits=0),
    _f('salvo_cd', 'defence', 'Перезарядка залпа (каждой турели)', ('defence', 'salvo', 'cooldown'), 'float', 'игровых секунд', 2, 60, 1, warn=(4, 20)),
    _f('h_salvo_range', 'defence', 'Дальность залпа турелей', ('hanson', 'salvo', 'range'), 'float', 'клеток', 4, 20, 1, warn=(8, 14)),
    _f('h_salvo_missiles', 'defence', 'Ракет в залпе', ('hanson', 'salvo', 'missiles'), 'int', 'шт.', 1, 12, 1, warn=(3, 8)),
    _f('h_salvo_damage', 'defence', 'Урон одной ракеты залпа', ('hanson', 'salvo', 'damage'), 'float', 'ед.', 5, 200, 5, warn=(15, 60), digits=0),
    _f('h_salvo_cd', 'defence', 'Перезарядка залпа (каждой турели)', ('hanson', 'salvo', 'cooldown'), 'float', 'игровых секунд', 2, 60, 1, warn=(4, 20)),
    _f('e_salvo_range', 'defence', 'Дальность залпа турелей', ('epidemic', 'salvo', 'range'), 'float', 'клеток', 4, 20, 1, warn=(8, 14)),
    _f('e_salvo_cd', 'defence', 'Перезарядка залпа (каждой турели)', ('epidemic', 'salvo', 'cooldown'), 'float', 'игровых секунд', 2, 60, 1, warn=(4, 20)),
    # ---- features of the chosen mission ------------------------------------------------------------------------------------------------------------------
    _f('refinery', 'special', 'Перерабатывающий завод на гейзере', ('zerohour', 'allow_refinery'), 'bool', hint='КСМ строят завод за обычную цену; потерянный можно восстановить'),
    _f('c_gas', 'special', 'Цена контейнера', ('hanson', 'containers', 'gas_cost'), 'int', 'газа', 0, 200, 5, hint='Списывается при успешной установке', warn=(10, 60), missions=('thanson01',)),
    _f('c_damage', 'special', 'Урон контейнера', ('hanson', 'containers', 'damage'), 'float', 'ед.', 20, 1000, 10, warn=(100, 400), missions=('thanson01',), digits=0),
    _f('c_radius', 'special', 'Радиус взрыва контейнера', ('hanson', 'containers', 'radius'), 'float', 'клеток', 1, 8, 0.5, warn=(2, 5), missions=('thanson01',)),
    _f('convoy_gas', 'special', 'Цена отправки колонны', ('hanson', 'convoy_fuel', 'gas_cost'), 'int', 'газа', 0, 500, 10, hint='Списывается при отправке колонны', warn=(50, 200)),
    _f('hell_tank', 'special', 'Запас хода геллиона', ('epidemic', 'fuel', 'tank'), 'float', 'клеток пути', 40, 300, 5, hint='Запас топлива геллиона, 1 единица = 1 клетка', warn=(80, 200), digits=0),
    _f('truck_fuel', 'special', 'Запас топлива газовоза', ('epidemic', 'truck', 'fuel_max'), 'float', 'ед. топлива', 100, 1500, 10, warn=(300, 800), digits=0),
    _f('truck_start', 'special', 'Топлива в газовозе в начале', ('epidemic', 'truck', 'fuel_start'), 'float', 'ед. топлива', 0, 1500, 10, digits=0),
    _f('hell_extra', 'special', 'Добавленные геллионы', ('epidemic', 'hellions', 'extra'), 'int', 'шт.', 0, 12, 1),
    _f('transport', 'special', 'Ночной транспорт', ('epidemic', 'transport', 'unit'), 'choice', choices=[('Medivac', 'Медивак: 8 мест, пассажиры гибнут вместе с ним'), ('Hercules', 'Геркулес: 30 мест, пассажиры спасаются в капсулах')], hint='Один корабль на всю миссию'),
    # ---- enemy and tempo ---------------------------------------------------------------------------------------------------------------------------------
    _f('fp_on', 'enemy', 'Заключительный натиск', ('defence', 'final_push', 'enabled'), 'bool', hint='Атака перед концом таймера, не зависящая от числа уничтоженных инкубаторов'),
    _f('fp_warn', 'enemy', 'Предупреждение о натиске', ('defence', 'final_push', 'warn_remaining'), 'float', 'сек. до конца таймера', 30, 600, 10, warn=(120, 360), digits=0, visible_if=lambda c: bool(_get(c, ('defence', 'final_push', 'enabled')))),
    _f('fp_dist', 'enemy', 'Расстояние появления врагов', ('defence', 'final_push', 'spawn_distance'), 'float', 'клеток от базы', 20, 100, 5, warn=(30, 70), digits=0, visible_if=lambda c: bool(_get(c, ('defence', 'final_push', 'enabled')))),
    _f('fp_w1', 'enemy', 'Первая группа натиска', ('defence', 'final_push', 'waves', 0, 'remaining'), 'float', 'сек. до конца таймера', 20, 900, 10, warn=(100, 300), digits=0, visible_if=lambda c: bool(_get(c, ('defence', 'final_push', 'enabled')))),
    _f('fp_w2', 'enemy', 'Вторая группа натиска', ('defence', 'final_push', 'waves', 1, 'remaining'), 'float', 'сек. до конца таймера', 20, 900, 10, warn=(60, 250), digits=0, visible_if=lambda c: bool(_get(c, ('defence', 'final_push', 'enabled')))),
    _f('fp_w3', 'enemy', 'Третья группа натиска', ('defence', 'final_push', 'waves', 2, 'remaining'), 'float', 'сек. до конца таймера', 20, 900, 10, warn=(40, 200), digits=0, visible_if=lambda c: bool(_get(c, ('defence', 'final_push', 'enabled')))),
    # ---- economy of the preparation ------------------------------------------------------------------------------------------------------------------------
    _f('p_marine', 'economy', 'Цена морпеха', ('zerohour', 'prices', 'marines', 'minerals'), 'int', 'минералов', 0, 500, 5, hint='Учитывается в стоимости подготовки кампании; бесплатный тест не списывает'),
    _f('p_bunker', 'economy', 'Цена комплекта бункера', ('zerohour', 'prices', 'bunkers', 'minerals'), 'int', 'минералов', 0, 500, 5),
    _f('p_turret', 'economy', 'Цена комплекта турели', ('zerohour', 'prices', 'turrets', 'minerals'), 'int', 'минералов', 0, 500, 5),
    _f('p_scv', 'economy', 'Цена КСМ', ('zerohour', 'prices', 'scvs', 'minerals'), 'int', 'минералов', 0, 500, 5),
    _f('p_kit', 'economy', 'Цена комплекта турели', ('hanson', 'turret_kits', 'price', 'minerals'), 'int', 'минералов', 0, 500, 5, missions=('thanson01', 'thanson02')),
    _f('p_th1_scv', 'economy', 'Цена дополнительного КСМ', ('hanson', 'turret_kits', 'scv', 'price', 'minerals'), 'int', 'минералов', 0, 500, 5),
    _f('p_kit_limit', 'economy', 'Предел комплектов турелей', ('hanson', 'turret_kits', 'limit'), 'int', 'шт.', 1, 60, 1),
]
BY_ID = {f.id: f for f in FIELDS}


def base_profiles(mission):
    """[(preset name, label)] of the FREE profiles a variant can start from (campaign-free, not hidden, experimental or not)."""
    adapter = build.load_adapter(mission)
    raw = build.load_json(adapter['config'])
    out = []
    for name, p in (raw.get('presets') or {}).items():
        if p.get('hidden'):
            continue
        cfg, _ = build.resolve_config(adapter, name)
        if cfg.get('campaign'):
            continue
        out.append((name, p.get('label', name)))
    return out


def default_base(mission):
    cands = base_profiles(mission)
    raw = build.load_json(build.load_adapter(mission)['config'])
    want = raw.get('default_preset')
    free = [n for n, _ in cands]
    if want in free:
        return want
    # the default is a campaign profile: its free twin (same name + _free) or the last free profile
    if want and (want + '_free') in free:
        return want + '_free'
    return free[-1] if free else None


def _hash_cfg(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str, ensure_ascii=True).encode('utf-8')).hexdigest()


def resolved_base(mission, base_preset):
    adapter = build.load_adapter(mission)
    cfg, _ = build.resolve_config(adapter, base_preset)
    return cfg


def supported_fields(mission, base_cfg):
    return [f for f in FIELDS if (f.missions is None or mission in f.missions) and _has(base_cfg, f.path)]


def base_cfg_of(variant):
    """The base of a variant: the resolved configuration of the base profile AS IT WAS when the variant was created (frozen inside the variant: a later change of the profile never
    changes the variant silently; `refresh_base` takes the current profile on purpose)."""
    if variant.get('base_cfg') is None:
        variant['base_cfg'] = resolved_base(variant['mission'], variant['base_preset'])
    return variant['base_cfg']


def effective_cfg(variant):
    """The configuration of the variant: its frozen base with the fields changed by the player applied, then the dependent settings."""
    base = copy.deepcopy(base_cfg_of(variant))
    for fid, shown in variant['changes'].items():
        f = BY_ID.get(fid)
        if f is None or not _has(base, f.path):
            continue
        _set(base, f.path, f.store(shown) if f.kind not in ('bool', 'choice') else shown)
    # dependent settings: a permanent cloak means no energy cost at night
    if _has(base, ('epidemic', 'night_cloak', 'net_per_second')) and _has(base, ('operatives', 'ghost_permanent_cloak')) and base['operatives']['ghost_permanent_cloak']:
        base['epidemic']['night_cloak']['net_per_second'] = 0
    # Hellion start fuel never above the tank; truck start never above the stock
    if _has(base, ('epidemic', 'truck', 'fuel_start')) and base['epidemic']['truck']['fuel_start'] > base['epidemic']['truck']['fuel_max']:
        base['epidemic']['truck']['fuel_start'] = base['epidemic']['truck']['fuel_max']
    # the recommended order is the order of the test composition: one source for the card, the plan and the test
    if _has(base, ('zerohour', 'recommended')) and _has(base, ('zerohour', 'order')):
        base['zerohour']['recommended'] = dict(base['zerohour']['order'])
    if _has(base, ('hanson', 'turret_kits', 'recommended')) and _has(base, ('hanson', 'turret_kits', 'order', 'turret_kits')):
        base['hanson']['turret_kits']['recommended'] = base['hanson']['turret_kits']['order']['turret_kits']
    base['campaign'] = None
    return base


def validate(variant):
    """(errors, warnings): a value outside the technical range or a configuration the generator refuses is an error; an unusual value is a warning."""
    errs, warns = [], []
    base = base_cfg_of(variant)
    fields = {f.id: f for f in supported_fields(variant['mission'], base)}
    for fid, shown in variant['changes'].items():
        f = fields.get(fid)
        if f is None:
            errs.append('Параметр «%s» не поддерживается этой миссией и профилем' % fid)
            continue
        if f.kind in ('int', 'float'):
            if not isinstance(shown, (int, float)) or isinstance(shown, bool):
                errs.append('%s: нужно число' % f.label)
                continue
            if (f.lo is not None and shown < f.lo) or (f.hi is not None and shown > f.hi):
                errs.append('%s: допустимо от %g до %g %s' % (f.label, f.lo, f.hi, f.unit))
                continue
            if f.warn and not (f.warn[0] <= shown <= f.warn[1]):
                warns.append('%s: %g %s — необычное значение (обычно %g–%g)' % (f.label, shown, f.unit, f.warn[0], f.warn[1]))
        elif f.kind == 'choice' and shown not in [c[0] for c in f.choices]:
            errs.append('%s: неизвестный выбор' % f.label)
    if errs:
        return errs, warns
    cfg = effective_cfg(variant)
    # relations between the values
    try:
        areas = cfg['tactical']['nuke']['damage']['areas']
        if not (areas[0][0] < areas[1][0] < areas[2][0]):
            errs.append('Радиусы зон ядерного удара должны возрастать: полный < половинный < четвертной')
    except KeyError:
        pass
    try:
        zo = cfg['zerohour']
        for k, v in zo['order'].items():
            if v > zo['limits'][k]:
                errs.append('Заказ «%s»: %d больше предела подготовки %d' % (k, v, zo['limits'][k]))
            if v < zo.get('min', {}).get(k, 0):
                errs.append('Заказ «%s»: %d меньше обязательного минимума %d' % (k, v, zo['min'][k]))
    except KeyError:
        pass
    try:
        tk = cfg['hanson']['turret_kits']
        if tk['order']['turret_kits'] > tk['limit']:
            errs.append('Комплекты турелей: %d больше предела %d' % (tk['order']['turret_kits'], tk['limit']))
        if tk['order']['scvs'] > tk['scv']['limit_extra']:
            errs.append('Добавленные КСМ: %d больше предела %d' % (tk['order']['scvs'], tk['scv']['limit_extra']))
    except KeyError:
        pass
    try:
        if cfg['epidemic']['truck']['fuel_start'] > cfg['epidemic']['truck']['fuel_max']:
            errs.append('Топлива в газовозе в начале больше его запаса')
    except KeyError:
        pass
    errs += build.validate_config(cfg)
    return errs, warns


def summary(variant):
    """The right-hand panel: the composition and the settings that differ from the base (all from the SAME effective configuration the build uses)."""
    cfg = effective_cfg(variant)
    base = base_cfg_of(variant)
    lines = []
    m = variant['mission']
    if m == 'traynor03':
        o = cfg['zerohour']['order']
        lines += ['Морпехи: %d' % o['marines'], 'Бункеры (комплекты): %d' % o['bunkers'], 'Ракетные турели (комплекты): %d' % o['turrets'], 'КСМ добавленных: %d' % o['scvs'], 'Призраки: 2',
                  'Ядерные ракеты: %d на весь отряд' % cfg['tactical']['nuke']['count'], 'Бронебойные заряды: %d каждому призраку' % cfg['tactical']['grenade']['charges']]
        pr = cfg['zerohour']['prices']
        cost = sum(o[k] * pr[k]['minerals'] for k in o)
        lines.append('Стоимость подготовки в кампании (бесплатный тест не списывает): %d минералов' % cost)
    elif m == 'thanson01':
        tk = cfg['hanson']['turret_kits']
        scv = tk['scv']
        lines += ['Призраки: 2', 'Комплекты ракетных турелей: %d' % tk['order']['turret_kits'], 'КСМ: %d всего — %d штатных + %d добавленных' % (scv['stock'] + tk['order']['scvs'], scv['stock'], tk['order']['scvs'])]
        fs = cfg['hanson'].get('free_squad') or {}
        if fs.get('marines') is not None:
            lines.append('Морпехи добавленных: %d' % fs['marines'])
        lines.append('Контейнер: %d газа, отправка колонны: %d газа' % (cfg['hanson']['containers']['gas_cost'], cfg['hanson']['convoy_fuel']['gas_cost']))
        lines.append('Рекомендация = заказ (одно значение): %d комплектов' % tk['recommended'])
        cost = {r: tk['order']['turret_kits'] * tk['price'][r] + tk['order']['scvs'] * scv['price'][r] + tk['preparation'][r] for r in ('minerals', 'gas')}
        lines.append('Стоимость подготовки в кампании (комплекты %d×%d + КСМ %d×%d + плата за подготовку %d): %d минералов, %d газа; бесплатный тест не списывает' % (
            tk['order']['turret_kits'], tk['price']['minerals'], tk['order']['scvs'], scv['price']['minerals'], tk['preparation']['minerals'], cost['minerals'], cost['gas']))
    elif m == 'thanson02':
        fs = cfg['hanson']['free_squad']
        e = cfg['epidemic']
        lines += ['Призраки: 2', 'Морпехи: %d всего — %d штатных + %d добавленных' % (e['stock_marines'] + fs['marines'], e['stock_marines'], fs['marines']),
                  'КСМ: %d всего — %d штатных + %d добавленных' % (e['stock_scvs'] + fs['scvs'], e['stock_scvs'], fs['scvs']),
                  'Комплекты бункеров: %d, комплекты турелей: %d' % (cfg['hanson']['bunker_kits']['order']['bunker_kits'], cfg['hanson']['turret_kits']['order']['turret_kits']),
                  'Закупки кампании для «Эпидемии» не подключены: стоимости подготовки нет, только бесплатный тест']
    lines.append('Режим: бесплатный тест — запас и результаты настоящей кампании не затрагиваются')
    diffs = []
    shown = {f.id: f for f in supported_fields(m, base)}
    for fid, val in variant['changes'].items():
        f = shown.get(fid)
        if f is None:
            continue
        b = f.display(_get(base, f.path))
        if val != b:
            diffs.append('%s: %s → %s %s' % (f.label, _fmt(b), _fmt(val), f.unit))
    return lines, diffs


def _fmt(v):
    if isinstance(v, bool):
        return 'да' if v else 'нет'
    if isinstance(v, float) and v == int(v):
        return '%d' % v
    return str(v)


# ---------------------------------------------------------------------------------- storage --------------------------------------------------------------------------------
def _path(mission, vid):
    return os.path.join(workshop_dir(), mission, vid + '.json')


def list_variants(mission):
    d = os.path.join(workshop_dir(), mission)
    out = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            if n.endswith('.json') and not n.endswith('.plan.json'):
                try:
                    with open(os.path.join(d, n), encoding='utf-8') as f:
                        out.append(json.load(f))
                except (OSError, ValueError):
                    continue
    return sorted(out, key=lambda v: v.get('created', 0))


def new_variant(mission, name, base_preset=None):
    base_preset = base_preset or default_base(mission)
    if base_preset not in [n for n, _ in base_profiles(mission)]:
        raise ValueError('the base profile must be a free profile of the mission')
    name = (name or '').strip()
    if not name or len(name) > 60:
        raise ValueError('the name of a variant: 1..60 characters')
    raw = build.load_json(build.load_adapter(mission)['config'])
    vid = hashlib.sha1(('%s|%s|%s' % (mission, name, time.time())).encode('utf-8')).hexdigest()[:8]
    v = {'id': vid, 'mission': mission, 'name': name, 'base_preset': base_preset, 'base_label': raw['presets'][base_preset].get('label', base_preset),
         'base_hash': _hash_cfg(resolved_base(mission, base_preset)), 'base_cfg': resolved_base(mission, base_preset), 'changes': {}, 'state': 'draft', 'revision': 0, 'created': time.time(), 'snapshot': None, 'built': None}
    save(v)
    return v


def save(variant):
    os.makedirs(os.path.join(workshop_dir(), variant['mission']), exist_ok=True)
    tmp = _path(variant['mission'], variant['id']) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(variant, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _path(variant['mission'], variant['id']))


def load(mission, vid):
    with open(_path(mission, vid), encoding='utf-8') as f:
        return json.load(f)


def delete_draft(variant):
    """Only the variant record (and its plan files) goes; built maps and their saves are never removed here."""
    p = _path(variant['mission'], variant['id'])
    if os.path.exists(p):
        os.remove(p)


def settings_hash(variant):
    return _hash_cfg(effective_cfg(variant))


def base_changed(variant):
    """True when the base profile has changed since the variant was created (the variant keeps its own copy; this only tells the player)."""
    return variant.get('base_hash') != _hash_cfg(resolved_base(variant['mission'], variant['base_preset']))


def refresh_base(variant):
    """Takes the CURRENT base profile on purpose; the changed fields stay. A built revision keeps its map and snapshot; the next build is a new revision."""
    variant['base_cfg'] = resolved_base(variant['mission'], variant['base_preset'])
    variant['base_hash'] = _hash_cfg(variant['base_cfg'])
    save(variant)


def reset_field(variant, fid):
    variant['changes'].pop(fid, None)


def set_field(variant, fid, shown):
    base = base_cfg_of(variant)
    f = BY_ID[fid]
    if _has(base, f.path) and f.display(_get(base, f.path)) == shown:
        variant['changes'].pop(fid, None)  # equal to the base: nothing is recorded
    else:
        variant['changes'][fid] = shown


# ---------------------------------------------------------------------------------- build ----------------------------------------------------------------------------------
def build_args(variant, plan_path):
    import argparse
    return argparse.Namespace(mission=variant['mission'], preset=variant['base_preset'], source=None, multiplier=None, diag=False, print_only=False, start=False, plan=plan_path, no_voice=False)


def plan_path(variant, revision):
    return os.path.join(workshop_dir(), variant['mission'], '%s_r%d.plan.json' % (variant['id'], revision))


def op_id(variant, revision):
    return 'WK%sR%d' % (variant['id'], revision)


def status(variant):
    """'draft' (never built), 'needs_build' (settings changed since the last build, or the map is missing), 'ready' (the built revision is current and installed), 'invalid'."""
    errs, _ = validate(variant)
    if errs:
        return 'invalid'
    b = variant.get('built')
    if not b:
        return 'draft'
    if b['settings_hash'] != settings_hash(variant):
        return 'needs_build'
    args = build_args(variant, b['plan'])
    if not os.path.isfile(b['plan']) or build.build_status(args) != 'ready':
        return 'needs_build'
    return 'ready'


def prepare(variant, progress=None):
    """Builds and installs the current settings as a NEW revision when they differ from the built one (the old revision, its map and its saves stay), else does nothing.
    Returns (rc, message). The map is a free test: a unique file name, no campaign part."""
    errs, _ = validate(variant)
    if errs:
        return 9, 'Настройки неверны: ' + '; '.join(errs)
    h = settings_hash(variant)
    b = variant.get('built')
    if b and b['settings_hash'] == h and os.path.isfile(b['plan']):
        args = build_args(variant, b['plan'])
        rc = build.prepare(args, progress)  # an up-to-date build is not rebuilt (build.prepare checks the inputs); a missing map of the SAME revision is rebuilt from the same snapshot
        return rc, 'Готова к запуску' if rc == 0 else 'Сбой подготовки карты (код %s)' % rc
    revision = (b['revision'] if b else 0) + 1
    cfg = effective_cfg(variant)
    snapshot = json.loads(json.dumps(cfg))
    pp = plan_path(variant, revision)
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    with open(pp, 'w', encoding='utf-8') as f:
        json.dump({'operation_id': op_id(variant, revision), 'mission': variant['mission'], 'preset': variant['base_preset'], 'snapshot': snapshot}, f, indent=1, ensure_ascii=False)
    args = build_args(variant, pp)
    rc = build.prepare(args, progress)
    if rc != 0:
        return rc, 'Сбой подготовки карты (код %s)' % rc
    adapter, cfg2, preset = build.context(args)
    _, dest = build.launch_command(adapter, cfg2, preset)
    variant['snapshot'] = snapshot
    variant['state'] = 'built'
    variant['revision'] = revision
    variant['built'] = {'revision': revision, 'settings_hash': h, 'plan': pp, 'op': op_id(variant, revision), 'map_file': dest, 'base_hash': _hash_cfg(resolved_base(variant['mission'], variant['base_preset'])), 'at': time.time()}
    save(variant)
    return 0, 'Готова к запуску (ревизия %d)' % revision


def launch_command(variant):
    b = variant['built']
    args = build_args(variant, b['plan'])
    adapter, cfg, preset = build.context(args)
    return build.launch_command(adapter, cfg, preset)
