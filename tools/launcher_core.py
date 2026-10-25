"""Logic of the Ghost Ops graphical launcher (no GUI code here, so it can be tested).

The launcher is a thin shell over tools/build.py: the same build / verify / install / start functions that the CLI
(`python tools/build.py launch --mission ... --preset ...`) and the console menu use. Nothing here builds or starts the
game by itself.
"""
import argparse
import contextlib
import importlib
import io
import json
import os
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

import sys  # noqa: E402
sys.path.insert(0, HERE)
import build  # noqa: E402

APP_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'GhostOps')
SETTINGS_PATH = os.path.join(APP_DIR, 'launcher_settings.json')
LOG_PATH = os.path.join(APP_DIR, 'launcher.log')
DEFAULT_GAME_DIR = os.environ.get('GHOSTOPS_SC2_DIR', r'E:\Games\StarCraft II')

STAGES = {
    'check': 'Проверка окружения',
    'build': 'Подготовка карты',
    'verify': 'Проверка',
    'install': 'Установка',
    'start': 'Запуск',
}

# User facing texts of the missions the launcher can start. Profiles of TRaynor01 come from config/traynor01.json.
MISSIONS = [
    {'id': 'traynor01', 'title': 'День освобождения', 'subtitle': 'Liberation Day', 'status': 'Играбельно',
     'description': 'Расчистите путь через Риксвилл и сопроводите Рейнора к штабу Доминиона. '
                    'Призраки поддерживают отряд точными выстрелами; их число зависит от выбранной сложности. '
                    'Противники — оригинальная сложность Blizzard Hard.'},
    {'id': 'traynor02', 'title': 'Вне закона', 'subtitle': 'The Outlaws', 'status': 'Эксперимент',
     'description': 'Спасите повстанцев и уничтожьте базу Доминиона малым отрядом: гарнизон держит оборону базы, '
                    'два призрака проникают к врагу, а единственный ядерный удар наводит Наводчик. Противники — Blizzard Hard.'},
    {'id': 'thanson01', 'title': 'Эвакуация', 'subtitle': 'Evacuation', 'status': 'Эксперимент',
     'description': 'Конечный отряд призраков. Конвои колонистов уходят только по вашей команде, а Snipe призрака снимает '
                    'опасных врагов по одному выстрелу. Профиль «Подготовленные подрывы»: два призрака, взрывные контейнеры огнемётчиков и газ за рейс. Производство и строительство запрещены, поселение прикрыто ПВО. Противники — Blizzard Hard.'},
    {'id': 'thanson02', 'title': 'Эпидемия', 'subtitle': 'Outbreak', 'status': 'Эксперимент',
     'description': 'Оригинальная «Эпидемия»: заражённые структуры нужно уничтожить днём и ночью. Геллионы Свонна едут на топливе, местный газ плохой: брошенный газовоз с хорошим '
                    'топливом нужно найти, захватить пехотой и довезти. Днём часть зданий защищена, ночью работает один транспорт. Свободный тест: бесплатный отряд, без кампании.'},
    {'id': 'traynor03', 'title': 'Час икс', 'subtitle': 'Zero Hour', 'status': 'Эксперимент',
     'description': 'Предварительно заказанный гарнизон базы, два призрака с постоянной маскировкой и две ядерные ракеты. Победа: прошло 20 минут до прибытия корабля '
                    'И уничтожены все отмеченные инкубаторы; если цели остались, корабль ждёт. Отдельный запуск использует рекомендуемый заказ и тестовый бюджет, '
                    'в кампанию ничего не пишет. Противники — Blizzard Hard.'},
    {'id': 'ttychus01', 'title': 'Smash and Grab', 'subtitle': 'TTychus01', 'status': 'Прототип',
     'description': 'Скрытная операция среди протоссов и зергов с настоящими детекторами. Ранний прототип без выбора сложности.'},
]
DEFAULT_MISSION = 'traynor01'


def mission_info(mission_id):
    return next((m for m in MISSIONS if m['id'] == mission_id), None)


def profiles_of(mission_id):
    """[{name, label, card, details, experimental}] for a mission; [] means: no profiles (prototype, one way to start)."""
    adapter = build.load_adapter(mission_id)
    raw = build.load_json(adapter['config'])
    presets = raw.get('presets')
    if not presets:
        return []
    for n, p in presets.items():  # the composition of a free test squad is shown on the card BEFORE the start (the numbers live in the config)
        if '{' in p.get('card', ''):
            p = dict(p, card=fill_card(p['card'], build.resolve_config(adapter, n)[0]))
            presets = dict(presets, **{n: p})
    return [{'name': n, 'label': p['label'], 'card': p.get('card', ''), 'details': p.get('details', []),
             'experimental': bool(p.get('experimental')), 'badge': p.get('badge', '')} for n, p in presets.items() if not p.get('hidden')]


def fill_card(card, rc):
    """The numbers of a card from the RESOLVED configuration (one source for the card, the order, the plan and the test): marines, kits, SCVs, bunkers, hellions, salvo."""
    hh, ee = rc.get('hanson') or {}, rc.get('epidemic') or {}
    fsq = hh.get('free_squad') or {}
    nm = fsq.get('marines', 0)
    tk = hh.get('turret_kits') or {}
    scv = tk.get('scv') or {}
    bk = hh.get('bunker_kits') or {}
    ex_scv = (tk.get('order') or {}).get('scvs', 0) + fsq.get('scvs', 0)
    stock_scv = scv.get('stock', ee.get('stock_scvs', 0))
    sv = ee.get('salvo') or hh.get('salvo') or {}
    rep = {'{marines_total}': str(nm + ee.get('stock_marines', 0)), '{marines_stock}': str(ee.get('stock_marines', 0)), '{marines}': str(nm),
           '{salvo_cd}': ('%g' % sv['cooldown']) if sv else '', '{kits}': str((tk.get('order') or {}).get('turret_kits', 0)),
           '{hellions}': str((ee.get('hellions') or {}).get('extra', 0)),
           '{scvs_total}': str(stock_scv + ex_scv), '{scvs_stock}': str(stock_scv), '{scvs_extra}': str(ex_scv),
           '{bunkers}': str((bk.get('order') or {}).get('bunker_kits', 0)), '{bunker_places}': str(4 * (bk.get('order') or {}).get('bunker_kits', 0))}
    zh = rc.get('zerohour') or {}
    zo = zh.get('order') or {}
    rep.update({'{marines_t}': str(zo.get('marines', 0)), '{bunkers_t}': str(zo.get('bunkers', 0)), '{turrets_t}': str(zo.get('turrets', 0)), '{scvs_t}': str(zo.get('scvs', 0))})
    for k, v in rep.items():
        card = card.replace(k, v)
    return card


def installed_map_info(mission_id, preset, game_dir=None, no_voice=False):
    """(path, installed?) of the map a start of this mission / profile uses (Maps\\GhostOps of the game folder)."""
    adapter = build.load_adapter(mission_id)
    if no_voice:
        adapter = dict(adapter, _novoice=True)
    root = game_dir or DEFAULT_GAME_DIR
    path = os.path.join(root, 'Maps', 'GhostOps', build.output_name(adapter, preset))
    return path, os.path.isfile(path)


def default_profile(mission_id):
    adapter = build.load_adapter(mission_id)
    raw = build.load_json(adapter['config'])
    return raw.get('default_preset') if raw.get('presets') else None


def detail_lines(mission_id, preset):
    """Exact characteristics of a profile (shown behind "Подробнее"), taken from the resolved configuration."""
    adapter = build.load_adapter(mission_id)
    cfg, _ = build.resolve_config(adapter, preset)
    gt = cfg.get('ghost_tuning')
    if not gt:
        return []
    if cfg.get('zerohour'):
        return zerohour_lines(cfg)
    if cfg.get('tactical'):
        return tactical_lines(cfg)
    if cfg.get('epidemic'):
        return epidemic_lines(cfg)
    if cfg.get('hanson'):
        return hanson_lines(cfg)
    life = gt.get('ghost_life', 100)
    sn = gt['snipe']
    cd = sn.get('cooldown', 0)
    ghosts = sum(1 for u in cfg['operatives']['squad'] if u == 'Ghost')
    return [
        'Призраки: %d, здоровье %s/%s' % (ghosts, life, life),
        'Энергия %g/%g, +%g в секунду вне маскировки' % (gt['energy_start'], gt['energy_max'], gt['regen_per_second']),
        'Маскировка: включение бесплатно, расход %g в секунду' % -gt['cloak_net_per_second'],
        'Snipe: %g энергии, урон %g (игнорирует броню), подготовка %g с, дальность 10' % (sn['cost'], sn['damage'], sn['cast_time']),
        'Перезарядка Snipe: %s' % ('нет' if not cd else ('%g с' % cd) + (' у каждого призрака отдельно' if ghosts > 1 else '')),
        'Рейнор 45/45, свои морпехи 1/1, медика нет',
        'EMP и ядерный удар отключены. Противники: Blizzard Hard',
        'Время — в игровых секундах',
    ]


def hanson_lines(cfg):
    """Exact characteristics of the sniper cover variant of THanson01 (taken from the resolved configuration)."""
    h, gt = cfg['hanson'], cfg['ghost_tuning']
    sn = gt['snipe']
    num = lambda v: ('%g' % v).replace('.', ',')  # noqa: E731
    roles = {r: sum(1 for t in h['turrets']['list'] if t['role'] == r) for r in ('base', 'houses', 'air')}
    fs = h.get('free_squad') or {}
    free = ['Тест — бесплатный отряд: 2 призрака, %d морпехов, огнемётчики и медики миссии; конечный отряд без пополнения; запас кампании не тратится, результат в кампанию не зачисляется' % fs['marines']] if fs.get('enabled') else []
    tk = h.get('turret_kits') or {}
    scv = tk.get('scv') or {}
    extra_scv = (tk.get('order') or {}).get('scvs', 0) + (fs.get('scvs', 0) if fs.get('enabled') else 0)
    kits = ['Ракетные турели: готовых на карте нет; комплектов %d (рекомендуется %d), строите сами бесплатно, строго по числу комплектов; отмена возвращает комплект, достроенная турель его тратит, гибель достроенной не возвращает, гибель недостроенной сжигает. Участки: %s' % (
        tk['order']['turret_kits'], tk['recommended'], '; '.join('%s - %d' % (x['ru'], x['count']) for x in tk['sectors']))] if tk.get('enabled') else []
    scv_line = ['КСМ: всего %d (штатных %d + дополнительных %d: заказ / рекомендация; они появляются при передаче базы); обучение КСМ в миссии не открывается' % (
        scv.get('stock', 0) + extra_scv, scv.get('stock', 0), extra_scv)] if scv else []
    salvo_line = ['Наземный залп турелей (кнопка и клавиша %s, круг прицела %s): %d ракет по %g урона наземным врагам, дальность %g, перезарядка %g с у каждой турели; Esc / правая кнопка отменяют без выстрела' % (
        h['salvo'].get('hotkey', 'G'), num(h['salvo']['radius'] + h['salvo'].get('spread', 0)), h['salvo']['missiles'], h['salvo']['damage'], h['salvo']['range'], h['salvo']['cooldown'])] if h.get('salvo') else []
    rs = sn.get('rifle_shot')
    cont_line = []
    ct = h.get('containers') or {}
    if ct.get('enabled'):
        cont_line = ['Взрывные контейнеры (C): %d газа за контейнер, %s; взрыв от первого прямого попадания бойца игрока (призрак не нужен): %g урона по наземным врагам в радиусе %s' % (
            ct['gas_cost'], ('общий запас %d' % ct['limit']) if ct['limit'] else 'общего лимита нет, число ограничено газом', ct['damage'], num(ct['radius']))]
    det_line = ['Анализ детекторов: круги зон обнаружения видимых вражеских детекторов показываются всё время, пока призрак жив (не зависят от выделения)'] if (cfg.get('detector_analysis') or {}).get('always') else []
    shot_line = (['Снайперский выстрел (R): клик по врагу, рядом (помощь прицеливанию в радиусе %s, один ближайший видимый враг) или в пустую точку (выстрел в землю без урона); дальность %g, '
                  'урон %g одной цели, перезарядка %s с, энергия не тратится; промах тоже перезаряжается' % (num(rs['assist_radius']), rs['range'], sn['damage'], num(sn['cooldown']))]) if rs else []
    return free + scv_line + kits + salvo_line + cont_line + det_line + shot_line + [
        'Призраки: %d, здоровье %s/%s, не восполняется; появляются рядом со стартовым отрядом' % (sum(1 for u in cfg['operatives']['squad'] if u == 'Ghost'), gt['ghost_life'], gt['ghost_life']),
        'Маскировка постоянная, энергию не тратит; детекторы раскрывают штатно; EMP и ядерный удар отключены',
        ('Snipe: %s энергии, урон %g (убивает любую вражескую боевую цель, здания и союзники исключены), подготовка %s с, перезарядка %s с' % (
            num(sn['cost']), sn['damage'], num(sn['cast_time']), num(sn['cooldown']))) if not rs else 'Снайперский выстрел заменяет Snipe: см. выше',
        'Производство, строительство, найм и исследования запрещены; существующие SCV добывают и чинят',
        'Конвой уходит по кнопке «Отправить конвой» (по команде игрока), только когда колонисты собраны',
        ('Ракетные турели (ПВО): %d — база %d, дома колонистов %d, воздушные подходы %d; чинятся SCV, новые строить нельзя' % (
            len(h['turrets']['list']), roles['base'], roles['houses'], roles['air'])) if h['turrets']['list'] else 'Готовых ракетных турелей на карте нет (см. комплекты выше)',
        'Колонисты, союзная охрана и её пополнение, налёты и условия победы / поражения — штатные. Противники: Blizzard Hard',
        'Время — в игровых секундах',
    ]


def epidemic_lines(cfg):
    """Exact characteristics of the free test version of THanson02 "Epidemic" (taken from the resolved configuration; every number is an experimental first value)."""
    e, h, gt = cfg['epidemic'], cfg['hanson'], cfg['ghost_tuning']
    f, t = e['fuel'], e['truck']
    num = lambda v: ('%g' % v).replace('.', ',')  # noqa: E731
    fs = h.get('free_squad') or {}
    tk = h.get('turret_kits') or {}
    ct = h.get('containers') or {}
    nc = e['night_cloak']['net_per_second']
    return [
        'Режим «Свободный тест»: бесплатный конечный отряд, без списаний и переноса в кампанию; результат в кампанию не предлагается',
        'Состав: 2 призрака (%s здоровья); морпехи: всего %d (%d штатных миссии и %d добавленных тестом); штатные огнемётчики (4) и медики (4), КСМ; геллионы: штатные Свонна и %d добавленных. Производства боевых войск нет, пополнения нет' % (
            gt['ghost_life'], fs.get('marines', 0) + e.get('stock_marines', 0), e.get('stock_marines', 0), fs.get('marines', 0), e['hellions']['extra']),
        ('КСМ: всего %d (%d штатных миссии и %d добавленных тестом; они появляются в первую секунду)' % (e.get('stock_scvs', 0) + fs.get('scvs', 0), e.get('stock_scvs', 0), fs.get('scvs', 0))) if fs.get('scvs') else 'КСМ: только штатные',
        ('Комплекты бункеров: %d (по 4 места = %d мест гарнизона); бункеры строит и размещает игрок бесплатно, строго по числу комплектов; отмена возвращает комплект, достройка тратит, гибель достроенного не возвращает' % (
            h['bunker_kits']['order']['bunker_kits'], 4 * h['bunker_kits']['order']['bunker_kits'])) if (h.get('bunker_kits') or {}).get('enabled') else 'Комплектов бункеров в этой ревизии нет',
        'Анализ детекторов: %s' % ('круги видимых вражеских детекторов показываются постоянно, пока призрак жив' if (cfg.get('detector_analysis') or {}).get('always') else 'круги показываются, пока призрак выделен (ревизии 1-2)'),
        'Топливо геллионов: бак %s, расход %s на пройденную клетку; на базе местный газ заполняет только %d%% бака; без топлива машина стоит, но стреляет, чинится и заправляется (запас виден полосой энергии)' % (
            num(f['tank']), num(f['per_cell']), round(100 * f['base_fill_poor'])),
        'Газовоз: брошен, не атакуется до захвата; рядом %d зараженных; пехота (не меньше %d бойцов) захватывает его один раз. Запас %s, скорость %s; заправка геллионов рядом автоматическая, топливо уходит из цистерны' % (
            t['defenders']['infested_terran'] + t['defenders']['civilian'], t['capture_units'], num(t['fuel_max']), num(t['speed'])),
        'После возвращения газовоза на базу геллионы заправляются полностью, газовоз пополняется за газ карты (1 газ = %s топлива)' % num(t['gas_to_fuel']),
        'Днём до %d больших заражённых зданий защищены (неуязвимы, подписаны), ночью уязвимы; все они входят в штатное условие победы' % e['protected']['max'],
        'Ночью (со %d-й) один транспорт: погрузка и высадка штатные, маршрут вы задаёте сами; перед рассветом предупреждение; после рассвета новые рейсы закрыты, текущий можно закончить; погибший транспорт не заменяется' % e['transport']['first_night'],
        ('Наземный залп турелей (кнопка и клавиша %s, наведение кругом): %d ракет по %g урона наземным врагам, область %s, дальность %g, перезарядка %g с у каждой турели отдельно; Esc / правая кнопка отменяют без выстрела' % (
            e['salvo'].get('hotkey', 'G'), e['salvo']['missiles'], e['salvo']['damage'], num(e['salvo']['radius'] + e['salvo'].get('spread', 0)), e['salvo']['range'], e['salvo']['cooldown'])) if e.get('salvo') else 'Наземного залпа у турелей в этой ревизии нет (только автоматический огонь по воздуху и земле)',
        'Призраки: днём маскировка без расхода, ночью net %s энергии в секунду (энергия %g, восстановление %s); Snipe %g урона без расхода энергии, перезаряд %s с' % (
            num(nc), gt['energy_max'], num(gt['regen_per_second']), gt['snipe']['damage'], num(gt['snipe']['cooldown'])),
        'Контейнеры огнемётчиков: клавиша C, %d газа, всего %d; взрыв от первого попадания при прямой атаке бойца игрока (призрак не нужен), радиус %s: %g урона по войскам и %g по зданиям (%g основных и %g дополнительных); комплекты ракетных турелей: %d (строите сами, бесплатно, по числу комплектов)' % (
            ct.get('gas_cost', 0), ct.get('limit', 0), num(ct.get('radius', 0)), ct.get('damage', 0), ct.get('damage', 0) * (1 + ct.get('structure_bonus', 0)), ct.get('damage', 0), ct.get('damage', 0) * ct.get('structure_bonus', 0), (tk.get('order') or {}).get('turret_kits', 0)),
        'Оригинальные вступление, сюжет, день и ночь, противник и победа (уничтожены все заражённые структуры) сохранены. Противники: Blizzard. Время — в игровых секундах',
    ]


def zerohour_lines(cfg):
    """Exact characteristics of TRaynor03 "Zero Hour" (taken from the resolved configuration; the numbers marked experimental are not approved values)."""
    z, t, gt = cfg['zerohour'], cfg['tactical'], cfg['ghost_tuning']
    g, zone, n = t['garrison'], t['garrison']['zone'], t['nuke']
    num = lambda v: ('%g' % v).replace('.', ',')  # noqa: E731
    o, pr, lim = z['recommended'], z['prices'], z['limits']
    cost = build.zerohour_cost(cfg, o)
    return [
        'Заказ (рекомендуемый, экспериментальный): морпехи %d, бункеры %d, ракетные турели %d, КСМ %d' % (o['marines'], o['bunkers'], o['turrets'], o['scvs']),
        'Цены (экспериментальные): морпех %d, бункер %d, турель %d, КСМ %d минералов; итог %d минералов, %d газа. Пределы: %d / %d / %d / %d' % (
            pr['marines']['minerals'], pr['bunkers']['minerals'], pr['turrets']['minerals'], pr['scvs']['minerals'], cost['minerals'], cost['gas'],
            lim['marines'], lim['bunkers'], lim['turrets'], lim['scvs']),
        'Гарнизон: обычное здоровье, урон ×%s, оружие только внутри круга базы (радиус %s); спасённые повстанцы не ограничены' % (num(g['damage_multiplier']), num(zone['radius'])),
        'Производство и строительство запрещены; бойцов и укрепления после гибели заново не выдают',
        'Призраки: 2, здоровье %s/%s, постоянная маскировка бесплатно, энергия %g/%g (+%g в секунду), Snipe %g энергии, урон %g, подготовка %s с, перезарядка %g с; EMP отключён' % (
            gt['ghost_life'], gt['ghost_life'], gt['energy_start'], gt['energy_max'], gt['regen_per_second'], gt['snipe']['cost'], gt['snipe']['damage'],
            num(gt['snipe']['cast_time']), gt['snipe']['cooldown']),
        'Ядерные ракеты: %d на всю операцию, наведение %g с, полёт %g с; наводить может любой призрак; замена призрака невозможна' % (n['count'], n['aim_time'], n['flight_time']),
        'Победа: прошло %d игровых минут до прибытия корабля И уничтожены все отмеченные инкубаторы (%d); после нуля корабль ждёт, миссия продолжается' % (z['arrival_minutes'], len(z['targets'])),
        'После нуля каждые %g с небольшая волна (не более %d активных вражеских юнитов). Противники: Blizzard Hard. Время — в игровых секундах' % (z['post_arrival']['interval'], z['post_arrival']['max_active_units']),
    ]


def tactical_lines(cfg):
    """Exact characteristics of the tactical variant of TRaynor02 (taken from the resolved configuration)."""
    t, gt = cfg['tactical'], cfg['ghost_tuning']
    g, z = t['garrison'], t['garrison']['zone']
    tm, n = t['trained_marine'], t['nuke']
    num = lambda v: ('%g' % v).replace('.', ',')  # noqa: E731
    return [
        'Гарнизон (морпехи исходной базы): урон ×%s, оружие только в зоне обороны (радиус %s)' % (num(g['damage_multiplier']), num(z['radius'])),
        'Обученные морпехи: здоровье %d/%d, атаковать не могут' % (tm['life'], tm['life']),
        'Спасённые повстанцы: обычные морпехи и медики, действуют по всей карте',
        'Призраки: 2 (Наводчик и Оперативник), здоровье %s/%s, не восполняются; прилетают на транспорте через %g с после начала миссии (с сюжетной сценой)' % (
            gt['ghost_life'], gt['ghost_life'], t['story']['first_delay'] + t['story']['second_delay'] + t['story']['alert_seconds']),
        'Энергия %g/%g, +%g в секунду вне маскировки, маскировка %g в секунду' % (gt['energy_start'], gt['energy_max'], gt['regen_per_second'], -gt['cloak_net_per_second']),
        'Snipe: %g энергии, урон %g (игнорирует броню), подготовка %s с, перезарядка %g с у каждого призрака' % (
            gt['snipe']['cost'], gt['snipe']['damage'], num(gt['snipe']['cast_time']), gt['snipe']['cooldown']),
        'Ядерный удар: одна ракета, только у Наводчика; наведение %g с (не двигаться), после запуска %g с до взрыва; дальность наведения %g' % (n['aim_time'], n['flight_time'], n['range']),
        ] + (['Точка удара должна быть видна (второй призрак может её разведать)'] if n.get('require_vision') else []) + (
        ['Во время наведения расход маскировки приостановлен (энергия не тратится и не восстанавливается), детекторы видят Наводчика; подход к точке — не наведение'] if n.get('aim_cloak_hold') else []) + (
        ['Оперативник: «Бронебойная граната» — %d заряда на миссию без пополнения, урон %g по области радиуса %s (наземная техника и здания; не пехота, не воздух, не свои), дальность %g, энергия не тратится' % (
            t['grenade']['charges'], t['grenade']['damage'], num(t['grenade']['radius']), t['grenade']['range'])] if (t.get('grenade') or {}).get('enabled') else []) + (
        ['Панель призраков (энергия, остаток маскировки в игровых секундах), подсказки при спасении повстанцев'] if (cfg.get('panel') or {}).get('enabled') else []) + [
        'Мощность взрыва, радиусы и спад урона — штатные; дружественный огонь сохраняется',
        'Смерть Наводчика до запуска — поражение; после запуска ракета долетает',
        'EMP отключён. Противники: Blizzard Hard. Время — в игровых секундах',
    ]


# ---------------------------------------------------------------------------------------------- settings
class Settings:
    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.data = {'game_dir': DEFAULT_GAME_DIR, 'mission': DEFAULT_MISSION, 'profiles': {}, 'no_voice': False}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.data})
        except (OSError, ValueError):
            pass  # first start or a damaged file: keep the defaults

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @property
    def game_dir(self):
        return self.data['game_dir']

    @property
    def no_voice(self):
        return bool(self.data.get('no_voice'))

    def mission(self):
        m = self.data.get('mission')
        return m if mission_info(m) else DEFAULT_MISSION

    def profile(self, mission_id):
        """Remembered profile of a mission if it still exists, else the mission default (easy for TRaynor01)."""
        names = [p['name'] for p in profiles_of(mission_id)]
        if not names:
            return None
        remembered = self.data.get('profiles', {}).get(mission_id)
        return remembered if remembered in names else default_profile(mission_id)

    def remember(self, mission_id, preset):
        self.data['mission'] = mission_id
        if preset:
            self.data.setdefault('profiles', {})[mission_id] = preset
        self.save()


def game_dir_problem(path):
    if not path or not os.path.isdir(path):
        return 'Папка игры не найдена: %s' % path
    if not os.path.isfile(os.path.join(path, 'Support64', 'SC2Switcher_x64.exe')):
        return 'В папке нет Support64\\SC2Switcher_x64.exe, это не папка StarCraft II.'
    return None


# ---------------------------------------------------------------------------------------------- log
def log(message, path=LOG_PATH):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), message.rstrip()))
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------- backend
class BuildBackend:
    """The real thing: calls tools/build.py. Tests replace it with a fake."""

    no_voice = False  # the explicit variant without added voice (a setting of the launcher)

    def args(self, mission, preset):
        return argparse.Namespace(mission=mission, preset=preset, source=None, multiplier=None, diag=False,
                                  print_only=False, start=True, no_voice=self.no_voice)

    def sc2_running(self):
        return build.sc2_running()

    def configure(self, game_dir):
        # the window may have been open for hours: always run the current build code and configs, not what was loaded at its start
        importlib.reload(build)
        build.SC2_DIR = game_dir

    def prepare(self, mission, preset, progress):
        return build.prepare(self.args(mission, preset), progress)

    def start(self, mission, preset):
        a = self.args(mission, preset)
        adapter, cfg, name = build.context(a)
        command, dest = build.launch_command(adapter, cfg, name)
        if not os.path.isfile(dest):
            print('expected installed map is missing: %s' % dest)
            return 8
        return build.start_detached(command, owner=True)


class Result:
    def __init__(self, ok, message, kind='error', output=''):
        self.ok, self.message, self.kind, self.output = ok, message, kind, output  # kind: ok | busy-game | error


# ---------------------------------------------------------------------------------------------- controller
class Launcher:
    """Runs "prepare -> install -> start" for the chosen mission and profile, one run at a time."""

    def __init__(self, settings=None, backend=None, log_fn=log):
        self.settings = settings or Settings()
        self.backend = backend or BuildBackend()
        self.log = log_fn
        self._lock = threading.Lock()
        self.busy = False

    def begin(self):
        """Claims the single run slot; False when a run is already in progress."""
        with self._lock:
            if self.busy:
                return False
            self.busy = True
            return True

    def run(self, mission_id, preset, on_stage=None):
        """Synchronous pipeline (call begin() first). Always releases the slot; never raises."""
        note = on_stage or (lambda stage: None)
        buf = io.StringIO()
        try:
            self.backend.configure(self.settings.game_dir)
            if hasattr(self.backend, 'no_voice'):
                self.backend.no_voice = self.settings.no_voice
            problem = game_dir_problem(self.settings.game_dir) if isinstance(self.backend, BuildBackend) else None
            if problem:
                return self._finish(Result(False, problem, 'error'))
            valid = [p['name'] for p in profiles_of(mission_id)]
            if valid and preset not in valid:
                return self._finish(Result(False, 'Неизвестный вариант сложности: %s' % preset, 'error'))
            if not valid and preset:
                return self._finish(Result(False, 'У этой миссии нет вариантов сложности.', 'error'))
            self.settings.remember(mission_id, preset)
            self.log('start requested: %s / %s' % (mission_id, preset))
            if self.backend.sc2_running():
                return self._finish(Result(False, 'StarCraft II уже запущена. Закройте игру самостоятельно и повторите: '
                                           'запускатель никогда не завершает её принудительно.', 'busy-game'))
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = self.backend.prepare(mission_id, preset, lambda stage: note(stage))
                if rc == 7:
                    return self._finish(Result(False, 'StarCraft II уже запущена. Закройте игру самостоятельно и повторите.', 'busy-game', buf.getvalue()))
                if rc != 0 and 'prepare_audio' in buf.getvalue():
                    return self._finish(Result(False, 'Не найдены файлы озвучки: клипы не входят в репозиторий. Подготовьте их из установленной игры (python tools\\prepare_audio.py, см. README, раздел «Voice») '
                                               'или включите в настройках «Без добавленной озвучки»: портреты, тексты и порядок сцен останутся.', 'error', buf.getvalue()))
                if rc != 0:
                    why = [ln.strip() for ln in buf.getvalue().splitlines() if re.search(r'INVALID|FAIL|error|refus|MUST', ln, re.I) or ln.startswith('  tactical')]
                    return self._finish(Result(False, 'Не удалось подготовить карту (код %s).%s' % (rc, (' ' + ' | '.join(why[:2])) if why else ''), 'error', buf.getvalue()))
                note('start')
                rc = self.backend.start(mission_id, preset)
            if rc != 0:
                return self._finish(Result(False, 'Не удалось запустить игру (код %s).' % rc, 'error', buf.getvalue()))
            return self._finish(Result(True, 'Игра запускается. Окно запускателя можно закрыть.', 'ok', buf.getvalue()))
        except Exception as e:  # noqa: BLE001 - the interface must never stay locked
            return self._finish(Result(False, 'Неожиданная ошибка: %s' % e, 'error', buf.getvalue()))

    def _finish(self, result):
        if result.output:
            self.log(result.output)
        self.log('result: %s %s' % ('OK' if result.ok else 'FAILED', result.message))
        with self._lock:
            self.busy = False
        return result

    def start_async(self, mission_id, preset, on_stage, on_done):
        """Runs in a worker thread; callbacks are called from that thread (the GUI forwards them through a queue)."""
        if not self.begin():
            return False

        def work():
            on_done(self.run(mission_id, preset, on_stage))
        threading.Thread(target=work, daemon=True).start()
        return True


def queue_summary(st=None):
    """Compact status of the queue of in-game tests (tools/test_queue.py) for the launcher: None when there is nothing to show, else
    {'text', 'job', 'state', 'actions': ['cancel', 'resume', 'open_log']}. Read only; an unreadable queue is simply not shown."""
    try:
        if st is None:
            import test_queue
            st = test_queue.status(refresh=False)
    except Exception:  # noqa: BLE001
        return None
    jobs = st.get('jobs') or []
    if not jobs:
        return None
    waiting = [j for j in jobs if j['state'] in ('waiting', 'preparing', 'running', 'interrupted')]
    j = waiting[0] if waiting else jobs[-1]
    names = {'waiting': 'ожидает', 'preparing': 'готовится к запуску', 'running': 'выполняет тест', 'done': 'завершён', 'cancelled': 'отменён', 'error': 'ошибка',
             'interrupted': 'прерван (состояние неизвестно)'}
    text = 'Тест %s «%s» - %s - %s / %s: %s' % (j['id'], j['label'], names.get(j['state'], j['state']), j['mission'], j['preset'], j.get('phase', ''))
    if len(waiting) > 1:
        text += '  (ещё в очереди: %d)' % (len(waiting) - 1)
    if j['state'] in ('done', 'cancelled', 'error'):
        text += '  Итог: %s. Журнал: %s' % (j.get('result', ''), j.get('log', ''))
    if j['state'] in ('waiting', 'preparing', 'running') and not st.get('runner_alive'):
        text += '  [процесс очереди не работает]'
    actions = []
    if j['state'] in ('waiting', 'preparing', 'running', 'interrupted'):
        actions.append('cancel')
    if j['state'] == 'interrupted':
        actions.append('resume')
    if j.get('log'):
        actions.append('open_log')
    return {'text': text, 'job': j['id'], 'state': j['state'], 'actions': actions, 'log': j.get('log', '')}


def queue_action(action, job_id):
    """Cancel or resume of one queued test (the game of the Owner is never touched: the runner closes only its own verified test game)."""
    import test_queue
    if action == 'cancel':
        test_queue.request_cancel(job_id)
    elif action == 'resume':
        test_queue.resume(job_id)
        test_queue.start_detached()
