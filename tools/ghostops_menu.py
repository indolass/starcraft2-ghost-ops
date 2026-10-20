"""Console menu that prepares and starts a Ghost Ops variant of Liberation Day (TRaynor01).

Opened by GhostOps_TRaynor01.cmd (double click). It only asks which profile to start, then calls the same
build/install/launch code as `python tools/build.py launch --mission traynor01 --preset <name>`.
The profile applies to the mission that is started now; it cannot be switched inside an existing save.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402

MISSION = 'traynor01'

def menu_items():
    raw = build.load_json('config/%s.json' % MISSION)
    return [(name, p['label'], p.get('card', ''), bool(p.get('experimental'))) for name, p in raw['presets'].items() if not p.get('hidden')]


def choose(input_fn=input, output_fn=print):
    """Shows the menu; returns the chosen preset name, or None for Cancel / end of input."""
    items = menu_items()
    output_fn('')
    output_fn('Ghost Ops — Liberation Day (TRaynor01)')
    output_fn('Сложность противников во всех вариантах: Blizzard Hard.')
    output_fn('')
    for i, (name, label, card, experimental) in enumerate(items, 1):
        output_fn('  %d. %s — %s%s' % (i, label, card, ' [эксперимент]' if experimental else ''))
    output_fn('  0. Отмена')
    output_fn('')
    while True:
        try:
            answer = input_fn('Выберите вариант [0-%d]: ' % len(items)).strip()
        except EOFError:
            return None
        if answer in ('0', ''):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(items):
            return items[int(answer) - 1][0]
        output_fn('Неверный выбор, введите число от 0 до %d.' % len(items))


def run(input_fn=input, output_fn=print, launch_fn=None):
    """Menu -> launch. Returns the process exit code (0 also when the user cancelled)."""
    preset = choose(input_fn, output_fn)
    if preset is None:
        output_fn('Отмена: ничего не запущено.')
        return 0
    launch_fn = launch_fn or (lambda p: build.main(['launch', '--mission', MISSION, '--preset', p]))
    output_fn('Подготовка варианта «%s»...' % preset)
    rc = launch_fn(preset)
    if rc == 0:
        output_fn('Игра запускается. Это окно можно закрыть.')
    else:
        output_fn('Запуск не выполнен (код %s). Сообщение выше.' % rc)
    return rc


if __name__ == '__main__':
    code = run()
    if sys.stdin.isatty():
        input('Нажмите Enter для выхода...')
    sys.exit(code)
