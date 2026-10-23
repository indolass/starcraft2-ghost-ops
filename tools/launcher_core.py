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
    for n, p in presets.items():  # the composition of a free test squad is shown on the card BEFORE the start (the number lives in the config)
        if '{marines}' in p.get('card', ''):
            fs = (build.resolve_config(adapter, n)[0].get('hanson') or {}).get('free_squad') or {}
            p = dict(p, card=p['card'].replace('{marines}', str(fs.get('marines', 0))))
            presets = dict(presets, **{n: p})
    return [{'name': n, 'label': p['label'], 'card': p.get('card', ''), 'details': p.get('details', []),
             'experimental': bool(p.get('experimental')), 'badge': p.get('badge', '')} for n, p in presets.items() if not p.get('hidden')]


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
    return free + [
        'Призраки: %d, здоровье %s/%s, не восполняется; появляются рядом со стартовым отрядом' % (sum(1 for u in cfg['operatives']['squad'] if u == 'Ghost'), gt['ghost_life'], gt['ghost_life']),
        'Маскировка постоянная, энергию не тратит; детекторы раскрывают штатно; EMP и ядерный удар отключены',
        'Snipe: %s энергии, урон %g (убивает любую вражескую боевую цель, здания и союзники исключены), подготовка %s с, перезарядка %s с' % (
            num(sn['cost']), sn['damage'], num(sn['cast_time']), num(sn['cooldown'])),
        'Производство, строительство, найм и исследования запрещены; существующие SCV добывают и чинят',
        'Конвой уходит по кнопке «Отправить конвой» (по команде игрока), только когда колонисты собраны',
        'Ракетные турели (ПВО): %d — база %d, дома колонистов %d, воздушные подходы %d; чинятся SCV, новые строить нельзя' % (
            len(h['turrets']['list']), roles['base'], roles['houses'], roles['air']),
        'Колонисты, союзная охрана и её пополнение, налёты и условия победы / поражения — штатные. Противники: Blizzard Hard',
        'Время — в игровых секундах',
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
