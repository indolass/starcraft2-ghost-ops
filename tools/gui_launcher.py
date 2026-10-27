"""Ghost Ops graphical launcher (CustomTkinter). A shell over tools/launcher_core.py -> tools/build.py.

Start it with GhostOps_Launcher.pyw (double click, no console window). Errors go to %APPDATA%\\GhostOps\\launcher.log.
"""
import io
import os
import queue
import subprocess
import threading
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
CTK_DIR = os.path.join(ROOT, 'tmp', 'thirdparty', 'ctk')
REQUIREMENTS = os.path.join(ROOT, 'requirements-gui.txt')

import launcher_core as core  # noqa: E402


def ensure_dependencies():
    """CustomTkinter is installed next to the project (pinned in requirements-gui.txt), not into the system Python."""
    if os.path.isdir(CTK_DIR) and CTK_DIR not in sys.path:
        sys.path.insert(0, CTK_DIR)
    try:
        import customtkinter  # noqa: F401
        return True
    except ImportError:
        pass
    python = sys.executable
    if python.lower().endswith('pythonw.exe'):
        python = python[:-len('pythonw.exe')] + 'python.exe'
    core.log('customtkinter missing: installing from %s into %s' % (REQUIREMENTS, CTK_DIR))
    flags = 0x08000000 if os.name == 'nt' else 0  # CREATE_NO_WINDOW
    done = subprocess.run([python, '-m', 'pip', 'install', '-r', REQUIREMENTS, '--target', CTK_DIR],
                          capture_output=True, text=True, creationflags=flags)
    core.log(done.stdout + done.stderr)
    if CTK_DIR not in sys.path:
        sys.path.insert(0, CTK_DIR)
    try:
        import customtkinter  # noqa: F401
        return True
    except ImportError:
        return False


# palette: graphite background, cold blue accents
BG = '#12151a'
PANEL = '#1a1f26'
CARD = '#222934'
CARD_HOVER = '#293241'
LINE = '#313a49'
ACCENT = '#3f8cff'
ACCENT_DARK = '#25508f'
ACCENT_HOVER = '#2f6fd1'
TEXT = '#e8edf4'
MUTED = '#9aa6b8'
AMBER = '#e0a94a'
RED = '#e0636f'
GREEN = '#58c28b'
FONT = 'Segoe UI'


def mission_image(mission_id, width=380, height=214):
    """Minimap of the mission from the locally extracted map if present, otherwise a styled placeholder."""
    from PIL import Image, ImageDraw, ImageFont
    info = core.mission_info(mission_id)
    canvas = Image.new('RGB', (width, height), (26, 31, 38))
    try:
        adapter = core.build.load_adapter(mission_id)
        src = os.path.join(ROOT, 'tmp', 'source', adapter['source_map_file'])
        data = core.build.sc2mpq.Archive(open(src, 'rb').read()).read('minimap.tga')
        pic = Image.open(io.BytesIO(data)).convert('RGB')
        pic.thumbnail((width - 16, height - 16))
        canvas.paste(pic, ((width - pic.width) // 2, (height - pic.height) // 2))
        return canvas
    except Exception:  # no extracted map yet, or an unreadable minimap: placeholder below
        pass
    draw = ImageDraw.Draw(canvas)
    for y in range(height):
        k = y / height
        draw.line([(0, y), (width, y)], fill=(int(24 + 18 * k), int(32 + 30 * k), int(48 + 52 * k)))
    draw.rectangle([10, 10, width - 11, height - 11], outline=(63, 140, 255), width=2)
    fonts = [r'C:\Windows\Fonts\segoeuib.ttf', r'C:\Windows\Fonts\arialbd.ttf']
    font = next((ImageFont.truetype(f, 30) for f in fonts if os.path.isfile(f)), ImageFont.load_default())
    small = next((ImageFont.truetype(f, 16) for f in fonts if os.path.isfile(f)), ImageFont.load_default())
    draw.text((width // 2, height // 2 - 14), info['title'] if info else mission_id, fill=(232, 237, 244), font=font, anchor='mm')
    draw.text((width // 2, height // 2 + 22), info['subtitle'] if info else '', fill=(154, 166, 184), font=small, anchor='mm')
    return canvas


def build_app():
    import customtkinter as ctk
    from tkinter import filedialog

    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')

    class App(ctk.CTk):
        """One mission screen: ONE version (the current one for the Owner's check) with its mode, composition, changes, build state and the start button; the earlier versions sit in a
        closed archive. The choice (version / mode / difficulty) lives in this window for the session; a saved choice of an earlier session never puts the Owner back into the archive."""

        def __init__(self, launcher=None):
            super().__init__(fg_color=BG)
            self.launcher = launcher or core.Launcher()
            self.settings = self.launcher.settings
            self.title('Ghost Ops — запускатель')
            self.geometry('1060x700')
            self.minsize(640, 400)
            self.queue = queue.Queue()
            self.mission = self.settings.mission()
            self.choice = {}  # mission -> {'rev', 'mode', 'difficulty'} chosen in this session
            self.archive_open = False
            self.shop_open = False
            self.details_open = False
            self.busy = False
            self.images = {}
            self.build_state = {}  # (mission, preset) -> (state, hash)
            self.wrap_labels = []
            self.notice = ''
            self._build_layout()
            self._refresh()
            self.after(100, self._poll)

        # ------------------------------------------------------------------ the choice of the window
        def _rev(self):
            return core.revision_by_number(self.mission, self._sel()['rev'])

        def _sel(self):
            if self.mission not in self.choice:
                cur = core.current_revision(self.mission)
                rev = core.revision_by_number(self.mission, cur)
                self.choice[self.mission] = {'rev': cur, 'mode': rev['modes'][0], 'difficulty': (core.difficulties_of(rev, rev['modes'][0]) or [None])[0]}
            return self.choice[self.mission]

        def _preset(self):
            s = self._sel()
            return core.preset_for(self._rev(), s['mode'], s['difficulty'])

        def _is_archive(self):
            return not self._rev()['current']

        def start_text(self):
            """The label of the main button: what it really does for the selected version and mode."""
            rev, s = self._rev(), self._sel()
            if s['mode'] == 'campaign':
                return 'Открыть кампанию'
            if not rev['current']:
                return 'Запустить архивную версию %d' % rev['number']
            return 'Запустить тест · версия %d' % rev['number']

        # ------------------------------------------------------------------ layout
        def _wrap(self, label, margin):
            self.wrap_labels.append((label, margin))
            return label

        def _build_layout(self):
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            left = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14, width=230)
            left.grid(row=0, column=0, sticky='nsew', padx=(12, 6), pady=(12, 6))
            left.grid_propagate(False)
            left.grid_rowconfigure(3, weight=1)
            ctk.CTkLabel(left, text='GHOST OPS', font=(FONT, 20, 'bold'), text_color=ACCENT).grid(row=0, column=0, sticky='w', padx=16, pady=(14, 0))
            ctk.CTkLabel(left, text='Запускатель миссий', font=(FONT, 12), text_color=MUTED).grid(row=1, column=0, sticky='w', padx=16, pady=(0, 6))
            ctk.CTkLabel(left, text='МИССИИ', font=(FONT, 11, 'bold'), text_color=MUTED).grid(row=2, column=0, sticky='w', padx=16, pady=(4, 2))
            lst = ctk.CTkScrollableFrame(left, fg_color='transparent', corner_radius=0)
            lst.grid(row=3, column=0, sticky='nsew', padx=4)
            lst.grid_columnconfigure(0, weight=1)
            self.mission_buttons = {}
            for i, m in enumerate(core.MISSIONS):
                b = ctk.CTkButton(lst, text='%s\n%s' % (m['title'], m['status']), anchor='w', height=46, corner_radius=10, font=(FONT, 13), fg_color=CARD, hover_color=CARD_HOVER,
                                  text_color=TEXT, border_width=2, border_color=CARD, command=lambda mid=m['id']: self.select_mission(mid))
                b.grid(row=i, column=0, sticky='ew', pady=3, padx=4)
                self.mission_buttons[m['id']] = b
            self.campaign_button = ctk.CTkButton(left, text='Окно «Кампания»', height=36, corner_radius=10, font=(FONT, 13, 'bold'), fg_color=ACCENT_DARK, hover_color=ACCENT, text_color=TEXT, command=self.open_campaign)
            self.campaign_button.grid(row=4, column=0, sticky='ew', padx=12, pady=(6, 3))
            self.workshop_button = ctk.CTkButton(left, text='Мастерская миссий', height=34, corner_radius=10, font=(FONT, 13, 'bold'), fg_color='transparent', border_width=1, border_color=ACCENT,
                                                 hover_color=CARD, text_color=TEXT, command=self.open_workshop)
            self.workshop_button.grid(row=5, column=0, sticky='ew', padx=12, pady=3)
            self.settings_button = ctk.CTkButton(left, text='Настройки', height=30, corner_radius=8, font=(FONT, 12), fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED,
                                                 hover_color=CARD, command=self.open_settings)
            self.settings_button.grid(row=6, column=0, sticky='ew', padx=12, pady=(3, 12))

            right = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14)
            right.grid(row=0, column=1, sticky='nsew', padx=(6, 12), pady=(12, 6))
            right.grid_columnconfigure(0, weight=1)
            right.grid_rowconfigure(0, weight=1)
            self.scroll = ctk.CTkScrollableFrame(right, fg_color='transparent', corner_radius=0)
            self.scroll.grid(row=0, column=0, sticky='nsew', padx=4, pady=(4, 0))
            self.scroll.grid_columnconfigure(0, weight=1)
            r = 0

            head = ctk.CTkFrame(self.scroll, fg_color='transparent')
            head.grid(row=r, column=0, sticky='ew', padx=8, pady=(4, 2))
            head.grid_columnconfigure(1, weight=1)
            self.image_label = ctk.CTkLabel(head, text='', width=120, height=68)
            self.image_label.grid(row=0, column=0, sticky='nw', padx=(0, 12))
            info = ctk.CTkFrame(head, fg_color='transparent')
            info.grid(row=0, column=1, sticky='nsew')
            info.grid_columnconfigure(0, weight=1)
            self.title_label = self._wrap(ctk.CTkLabel(info, text='', font=(FONT, 22, 'bold'), text_color=TEXT, anchor='w', justify='left'), 200)
            self.title_label.grid(row=0, column=0, sticky='ew')
            sub = ctk.CTkFrame(info, fg_color='transparent')
            sub.grid(row=1, column=0, sticky='w')
            self.subtitle_label = ctk.CTkLabel(sub, text='', font=(FONT, 13), text_color=MUTED, anchor='w')
            self.subtitle_label.grid(row=0, column=0, sticky='w')
            self.status_badge = ctk.CTkLabel(sub, text='', font=(FONT, 11, 'bold'), corner_radius=8, fg_color=ACCENT_DARK, text_color=TEXT, padx=8, pady=1)
            self.status_badge.grid(row=0, column=1, sticky='w', padx=(10, 0))

            # ---- the one summary card: version, mode, difficulty, composition, changes, build state
            r += 1
            self.summary = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=12, border_width=2, border_color=ACCENT)
            self.summary.grid(row=r, column=0, sticky='ew', padx=8, pady=(8, 4))
            self.summary.grid_columnconfigure(0, weight=1)
            vrow = ctk.CTkFrame(self.summary, fg_color='transparent')
            vrow.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 0))
            vrow.grid_columnconfigure(0, weight=1)
            self.version_label = self._wrap(ctk.CTkLabel(vrow, text='', font=(FONT, 19, 'bold'), text_color=TEXT, anchor='w', justify='left'), 250)
            self.version_label.grid(row=0, column=0, sticky='ew')
            self.version_badge = ctk.CTkLabel(vrow, text='', font=(FONT, 11, 'bold'), corner_radius=6, padx=8, pady=1)
            self.version_badge.grid(row=0, column=1, sticky='e', padx=(8, 0))
            self.back_button = ctk.CTkButton(vrow, text='', height=26, font=(FONT, 12), fg_color='transparent', border_width=1, border_color=LINE, text_color=ACCENT, hover_color=CARD_HOVER, command=self.back_to_current)
            self.mode_frame = ctk.CTkFrame(self.summary, fg_color='transparent')
            self.mode_frame.grid(row=3, column=0, sticky='ew', padx=14, pady=(6, 0))
            self.mode_frame.grid_columnconfigure(0, weight=1)
            self.mode_buttons = ctk.CTkSegmentedButton(self.mode_frame, values=['—'], font=(FONT, 13), command=self.set_mode)
            self.mode_line = self._wrap(ctk.CTkLabel(self.mode_frame, text='', font=(FONT, 12, 'bold'), text_color=MUTED, anchor='w', justify='left'), 250)
            self.mode_line.grid(row=1, column=0, sticky='ew', pady=(4, 0))
            self.diff_frame = ctk.CTkFrame(self.summary, fg_color='transparent')
            self.diff_frame.grid(row=4, column=0, sticky='ew', padx=14, pady=(6, 0))
            ctk.CTkLabel(self.diff_frame, text='Сложность', font=(FONT, 12, 'bold'), text_color=MUTED, anchor='w').grid(row=0, column=0, sticky='w')
            self.diff_buttons = ctk.CTkSegmentedButton(self.diff_frame, values=['—'], font=(FONT, 13), command=self.set_difficulty)
            self.comp_label = self._wrap(ctk.CTkLabel(self.summary, text='', font=(FONT, 13), text_color=TEXT, anchor='w', justify='left'), 250)
            self.comp_label.grid(row=5, column=0, sticky='ew', padx=14, pady=(8, 0))
            self.changes_label = self._wrap(ctk.CTkLabel(self.summary, text='', font=(FONT, 13), text_color=TEXT, anchor='w', justify='left'), 250)
            self.changes_label.grid(row=6, column=0, sticky='ew', padx=14, pady=(4, 0))
            self.note_label = self._wrap(ctk.CTkLabel(self.summary, text='', font=(FONT, 12), text_color=AMBER, anchor='w', justify='left'), 250)
            self.note_label.grid(row=7, column=0, sticky='ew', padx=14, pady=(4, 0))
            self.op_label = self._wrap(ctk.CTkLabel(self.summary, text='', font=(FONT, 13), text_color=GREEN, anchor='w', justify='left'), 250)
            self.op_label.grid(row=8, column=0, sticky='ew', padx=14, pady=(4, 10))
            self.build_label = self._wrap(ctk.CTkLabel(self.summary, text='', font=(FONT, 13, 'bold'), text_color=MUTED, anchor='w', justify='left'), 250)
            self.build_label.grid(row=1, column=0, sticky='ew', padx=14, pady=(4, 0))
            arow = ctk.CTkFrame(self.summary, fg_color='transparent')
            arow.grid(row=2, column=0, sticky='w', padx=10, pady=(2, 0))
            self.details_button = ctk.CTkButton(arow, text='Подробнее', height=28, width=110, font=(FONT, 12), fg_color='transparent', text_color=ACCENT, hover_color=CARD_HOVER, command=self.toggle_details)
            self.details_button.grid(row=0, column=0, padx=4)
            self.copy_button = ctk.CTkButton(arow, text='Скопировать сведения о тесте', height=28, font=(FONT, 12), fg_color='transparent', border_width=1, border_color=LINE, text_color=TEXT,
                                             hover_color=CARD_HOVER, command=self.copy_info)
            self.copy_button.grid(row=0, column=1, padx=4)

            # ---- details (closed by default): the long text, the numbers, the technical profile
            r += 1
            self.details = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=10, border_width=1, border_color=LINE)
            self.details.grid_columnconfigure(0, weight=1)
            self.details_title = ctk.CTkLabel(self.details, text='Подробности', font=(FONT, 14, 'bold'), text_color=ACCENT, anchor='w')
            self.details_title.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 2))
            self.details_text = self._wrap(ctk.CTkLabel(self.details, text='', font=(FONT, 12), text_color=TEXT, anchor='w', justify='left'), 120)
            self.details_text.grid(row=1, column=0, sticky='ew', padx=14, pady=(0, 6))
            self.tech_title = ctk.CTkLabel(self.details, text='Технические сведения', font=(FONT, 12, 'bold'), text_color=MUTED, anchor='w')
            self.tech_title.grid(row=2, column=0, sticky='ew', padx=14)
            self.tech_text = self._wrap(ctk.CTkLabel(self.details, text='', font=(FONT, 11), text_color=MUTED, anchor='w', justify='left'), 120)
            self.tech_text.grid(row=3, column=0, sticky='ew', padx=14, pady=(0, 10))
            self.details_row = r

            r += 1
            self.error_frame = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=10, border_width=2, border_color=RED)
            self.error_label = self._wrap(ctk.CTkLabel(self.error_frame, text='', font=(FONT, 13), text_color=TEXT, anchor='w', justify='left'), 120)
            self.error_label.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 6))
            self.error_frame.grid_columnconfigure(0, weight=1)
            eb = ctk.CTkFrame(self.error_frame, fg_color='transparent')
            eb.grid(row=1, column=0, sticky='w', padx=10, pady=(0, 10))
            ctk.CTkButton(eb, text='Открыть журнал', width=140, height=30, font=(FONT, 13), command=self.open_log).grid(row=0, column=0, padx=4)
            ctk.CTkButton(eb, text='Скрыть', width=90, height=30, font=(FONT, 13), fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED, hover_color=CARD, command=self.hide_error).grid(row=0, column=1, padx=4)
            self.error_row = r

            # ---- the archive of versions (closed by default)
            r += 1
            self.archive_button = ctk.CTkButton(self.scroll, text='', anchor='w', height=34, font=(FONT, 14, 'bold'), fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT, command=self.toggle_archive)
            self.archive_button.grid(row=r, column=0, sticky='ew', padx=8, pady=(12, 2))
            r += 1
            self.archive_frame = ctk.CTkFrame(self.scroll, fg_color='transparent')
            self.archive_frame.grid_columnconfigure(0, weight=1)
            self.archive_row = r

            # ---- own variants of the Mission Workshop: a separate compact section
            r += 1
            self.shop_button = ctk.CTkButton(self.scroll, text='', anchor='w', height=34, font=(FONT, 14, 'bold'), fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT, command=self.toggle_shop)
            self.shop_button.grid(row=r, column=0, sticky='ew', padx=8, pady=(8, 2))
            r += 1
            self.shop_frame = ctk.CTkFrame(self.scroll, fg_color='transparent')
            self.shop_frame.grid_columnconfigure(0, weight=1)
            self.shop_row = r

            bar = ctk.CTkFrame(right, fg_color='transparent')
            bar.grid(row=1, column=0, sticky='ew', padx=14, pady=(8, 12))
            bar.grid_columnconfigure(1, weight=1)
            self.start_button = ctk.CTkButton(bar, text='Запустить тест', height=48, width=300, corner_radius=12, font=(FONT, 17, 'bold'), fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color='#ffffff', command=self.start)
            self.start_button.grid(row=0, column=0, sticky='w')
            self.stage_label = self._wrap(ctk.CTkLabel(bar, text='', font=(FONT, 12), text_color=MUTED, anchor='w', justify='left'), 420)
            self.stage_label.grid(row=0, column=1, sticky='ew', padx=14)

            self.status = ctk.CTkLabel(self, text='', font=(FONT, 12), text_color=MUTED, anchor='w')
            self.status.grid(row=1, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 6))
            # compact status of the queue of prepared in-game tests (hidden when there is none)
            self.qframe = ctk.CTkFrame(self, fg_color=CARD, corner_radius=8)
            self.qlabel = ctk.CTkLabel(self.qframe, text='', font=(FONT, 12), text_color=TEXT, anchor='w', justify='left', wraplength=620)
            self.qlabel.grid(row=0, column=0, sticky='ew', padx=10, pady=6)
            self.qframe.grid_columnconfigure(0, weight=1)
            self.qbuttons = ctk.CTkFrame(self.qframe, fg_color='transparent')
            self.qbuttons.grid(row=0, column=1, padx=6)
            self._qsummary = None
            self.after(1500, self._queue_poll)
            self.right = right
            self._resize_job = None
            self._last_sw = None
            self.bind('<Configure>', self._schedule_resize, add='+')
            self.scroll._parent_canvas.bind('<Configure>', lambda e: self._schedule_resize(), add='+')

        # ------------------------------------------------------------------ queue of in-game tests
        def _queue_poll(self):
            try:
                summary = core.queue_summary()
            except Exception:  # noqa: BLE001
                summary = None
            if summary != self._qsummary:
                self._qsummary = summary
                for w in self.qbuttons.winfo_children():
                    w.destroy()
                if summary is None:
                    self.qframe.grid_remove()
                else:
                    self.qlabel.configure(text=summary['text'])
                    labels = {'cancel': 'Отменить', 'resume': 'Возобновить', 'open_log': 'Журнал'}
                    for i, act in enumerate(summary['actions']):
                        ctk.CTkButton(self.qbuttons, text=labels[act], width=100, height=26, font=(FONT, 12), command=lambda a=act, s=summary: self._queue_click(a, s)).grid(row=0, column=i, padx=3)
                    self.qframe.grid(row=2, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 6))
            self.after(3000, self._queue_poll)

        def _queue_click(self, action, summary):
            if action == 'open_log':
                if summary.get('log') and os.path.exists(summary['log']):
                    os.startfile(summary['log'])
                return
            core.queue_action(action, summary['job'])
            self._qsummary = None

        # ------------------------------------------------------------------ rendering
        def _refresh(self):
            m = core.mission_info(self.mission)
            for mid, b in self.mission_buttons.items():
                sel = mid == self.mission
                b.configure(border_color=ACCENT if sel else CARD, fg_color=ACCENT_DARK if sel else CARD)
            self.title_label.configure(text=m['title'])
            self.subtitle_label.configure(text=m['subtitle'])
            self.status_badge.configure(text=m['status'], fg_color=ACCENT_DARK if m['status'] == 'Играбельно' else '#5a4a1f', text_color=TEXT if m['status'] == 'Играбельно' else AMBER)
            if self.mission not in self.images:
                from PIL import Image  # noqa: F401
                img = mission_image(self.mission, 300, 170)
                self.images[self.mission] = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 68))
            self.image_label.configure(image=self.images[self.mission])
            self._render_summary()
            self._render_archive()
            self._render_shop()
            self._apply_busy()
            self._request_map_status()
            self._last_sw = None
            self.after(30, self._on_resize)

        def _render_summary(self):
            rev, s = self._rev(), self._sel()
            cur = rev['current']
            self.summary.configure(border_color=ACCENT if cur else AMBER)
            self.version_label.configure(text=rev['label'] if cur else 'Архив · ' + rev['label'][0].lower() + rev['label'][1:])
            self.version_badge.configure(text='ТЕКУЩАЯ ДЛЯ ПРОВЕРКИ' if cur else 'АРХИВ', fg_color=GREEN if cur else '#4a3b17', text_color='#0b2a14' if cur else AMBER)
            if cur:
                self.back_button.grid_remove()
            else:
                self.back_button.configure(text='К текущей версии %d' % core.current_revision(self.mission))
                self.back_button.grid(row=1, column=0, columnspan=2, sticky='w', pady=(6, 0))
            modes = rev['modes']
            if len(modes) > 1:
                self.mode_buttons.configure(values=[core.MODE_TITLES[x] for x in modes])
                self.mode_buttons.set(core.MODE_TITLES[s['mode']])
                self.mode_buttons.grid(row=0, column=0, sticky='w')
            else:
                self.mode_buttons.grid_remove()
            self.mode_line.configure(text=core.MODE_LINES[s['mode']])
            diffs = core.difficulties_of(rev, s['mode']) if s['mode'] != 'campaign' else []
            if diffs:
                self.diff_buttons.configure(values=diffs)
                self.diff_buttons.set(s['difficulty'] if s['difficulty'] in diffs else diffs[0])
                self.diff_buttons.grid(row=1, column=0, sticky='w', pady=(2, 0))
                self.diff_frame.grid()
            else:
                self.diff_frame.grid_remove()
            preset = self._preset()
            comp = core.composition_line(self.mission, preset) if preset else ''
            if s['mode'] == 'campaign':
                comp = 'Состав и заказ выбираются в окне «Кампания»; новая операция использует текущую рекомендованную версию, оплаченная продолжается на своей карте.'
                self.comp_label.configure(text=comp)
            else:
                self.comp_label.configure(text=('Состав: %s' % comp) if comp else '')
            variant = next((v for v in rev['variants'].get(s['mode'], []) if v['preset'] == preset), None)
            ch = (variant['changes'] if variant and s['mode'] != 'campaign' and variant['changes'] else rev['changes'])
            self.changes_label.configure(text='Изменения:\n' + '\n'.join('•  ' + c for c in ch[:3]))
            self.note_label.configure(text=rev['note'])
            ops = core.open_operations(self.mission)
            if ops:
                o = ops[0]
                self.op_label.configure(text='Идёт операция %s на версии %s: она продолжится на своей карте (новая версия её не подменяет). Продолжить — окно «Кампания».' % (o['id'], o['revision'] if o['revision'] is not None else '?'))
            else:
                self.op_label.configure(text='')
            self.build_label.configure(text=self._build_text(), text_color=self._build_color())
            self.details_button.configure(text='Скрыть подробности' if self.details_open else 'Подробнее')
            self._render_details()
            self.start_button.configure(text=self.start_text() if not self.busy else 'Подготовка…')

        def _build_state(self):
            preset = self._preset()
            if not preset:
                return None
            return self.build_state.get((self.mission, preset))

        def _build_text(self):
            preset = self._preset()
            if not preset:
                return 'Кампания: сборку карты операции готовит окно «Кампания».'
            err = self.settings.last_error_for(self.mission, preset)
            st = self._build_state()
            if err and not (st and st[0] == 'ready'):
                return core.build_state_text(None, err)
            if st is None:
                return 'Проверка сборки…'
            return core.build_state_text(st[0]) + (' · ' + st[1] if st[1] else '')

        def _build_color(self):
            st = self._build_state()
            preset = self._preset()
            if preset and self.settings.last_error_for(self.mission, preset) and not (st and st[0] == 'ready'):
                return RED
            if st and st[0] == 'ready':
                return GREEN
            return AMBER if st else MUTED

        def _render_details(self):
            if not self.details_open:
                self.details.grid_remove()
                return
            rev, s = self._rev(), self._sel()
            preset = self._preset() or (rev['variants'].get('campaign') or [{'preset': None}])[0]['preset']
            lines = []
            p = next((x for x in core.profiles_of(self.mission) if x['name'] == preset), None) if preset else None
            if p:
                lines.append(p['card'])
                lines += ['•  ' + ln for ln in core.detail_lines(self.mission, preset)]
            self.details_text.configure(text='\n'.join(lines) if lines else 'Подробности этой версии показывает окно «Кампания».')
            tech = ['Профиль: %s' % (preset or '—'), 'Версия: %s, режим: %s' % (rev['label'], core.MODE_TITLES[s['mode']])]
            if preset:
                path, there = core.installed_map_info(self.mission, preset, self.settings.game_dir, self.settings.no_voice)
                tech.append('Карта: %s%s' % (path, '' if there else '  (будет собрана и установлена при запуске)'))
                st = self._build_state()
                if st and st[1]:
                    tech.append('Сборка (хеш входных данных): %s' % st[1])
            tech.append('Последний запуск из этого окна: см. «Скопировать сведения о тесте»')
            self.tech_text.configure(text='\n'.join(tech))
            self.details.grid(row=self.details_row, column=0, sticky='ew', padx=8, pady=(4, 4))

        def _render_archive(self):
            arch = core.archive_of(self.mission)
            self.archive_button.configure(text='%s Архив версий — %d' % ('▾' if self.archive_open else '▸', len(arch)))
            for w in self.archive_frame.winfo_children():
                w.destroy()
            if not self.archive_open or not arch:
                self.archive_frame.grid_remove()
                return
            self.archive_frame.grid(row=self.archive_row, column=0, sticky='ew', padx=8)
            for i, rv in enumerate(arch):
                cur_sel = rv['number'] == self._sel()['rev']
                f = ctk.CTkFrame(self.archive_frame, fg_color=CARD_HOVER if cur_sel else CARD, corner_radius=8, border_width=1, border_color=AMBER if cur_sel else LINE)
                f.grid(row=i, column=0, sticky='ew', pady=2)
                f.grid_columnconfigure(0, weight=1)
                head = ctk.CTkLabel(f, text=rv['label'], font=(FONT, 14, 'bold'), text_color=TEXT, anchor='w', justify='left')
                head.grid(row=0, column=0, sticky='ew', padx=10, pady=(6, 0))
                self.wrap_labels.append((head, 190))
                ctk.CTkLabel(f, text='АРХИВ', font=(FONT, 10, 'bold'), text_color=AMBER, fg_color='#4a3b17', corner_radius=5, padx=6, pady=0).grid(row=1, column=0, sticky='w', padx=10, pady=(2, 0))
                modes = ', '.join(core.MODE_TITLES[x].lower() for x in rv['modes'])
                txt = ctk.CTkLabel(f, text='%s\nРежимы: %s' % (rv['changes'][0] if rv['changes'] else '', modes), font=(FONT, 12), text_color=MUTED, anchor='w', justify='left')
                txt.grid(row=2, column=0, sticky='ew', padx=10, pady=(2, 6))
                self.wrap_labels.append((txt, 190))
                ctk.CTkButton(f, text='Выбрать', width=90, height=28, font=(FONT, 12), command=lambda n=rv['number']: self.select_revision(n)).grid(row=0, column=1, rowspan=3, padx=10)
            self._last_sw = None
            self.after(20, self._on_resize)

        def _render_shop(self):
            import workshop
            vs = workshop.list_variants(self.mission) if self.mission in workshop.MISSIONS else []
            if not vs:
                self.shop_button.grid_remove()
                self.shop_frame.grid_remove()
                return
            self.shop_button.grid(row=self.shop_row - 1, column=0, sticky='ew', padx=8, pady=(8, 2))
            self.shop_button.configure(text='%s Свои варианты (Мастерская) — %d' % ('▾' if self.shop_open else '▸', len(vs)))
            for w in self.shop_frame.winfo_children():
                w.destroy()
            if not self.shop_open:
                self.shop_frame.grid_remove()
                return
            self.shop_frame.grid(row=self.shop_row, column=0, sticky='ew', padx=8)
            for i, v in enumerate(vs):
                lb = ctk.CTkLabel(self.shop_frame, text='%s — основа: %s · %s' % (v.get('name', v.get('id')), v.get('base_preset', ''), v.get('state', '')), font=(FONT, 12), text_color=TEXT, anchor='w', justify='left')
                lb.grid(row=i, column=0, sticky='ew', pady=2)
                self.wrap_labels.append((lb, 190))
            ctk.CTkButton(self.shop_frame, text='Открыть Мастерскую', height=28, font=(FONT, 12), command=self.open_workshop).grid(row=len(vs), column=0, sticky='w', pady=4)

        def _schedule_resize(self, event=None):
            """Window edges move first, the inner frames follow a moment later: measure after the layout settled."""
            if event is not None and event.widget is not self:
                return
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(80, self._on_resize)

        def _on_resize(self, event=None):
            k = self._get_window_scaling() or 1.0
            sw = self.scroll.winfo_width() / k  # winfo_* report physical pixels, wraplength wants logical ones
            if self._last_sw == int(sw):
                return  # nothing changed: avoids a Configure feedback loop
            self._last_sw = int(sw)
            rw = self.right.winfo_width() / k
            for lb, margin in self.wrap_labels:
                try:
                    if lb.winfo_exists():
                        lb.configure(wraplength=int(max(160, sw - margin)))
                except Exception:  # noqa: BLE001 - a label destroyed by a redraw
                    pass
            self.stage_label.configure(wraplength=int(max(120, rw - 360)))
            self.start_button.configure(width=int(max(170, min(300, rw - 60))))
            if self.winfo_height() / k < 620:
                self.image_label.grid_remove()
            else:
                self.image_label.grid()

        # ------------------------------------------------------------------ actions
        def select_mission(self, mission_id):
            if self.busy:
                return
            self.mission = mission_id
            self.details_open = False
            self.archive_open = False
            self.hide_error()
            self.settings.remember(self.mission, None)
            self._refresh()

        def select_revision(self, number):
            """The Owner picked a version (current or from the archive); it stays selected in this session until another is chosen."""
            if self.busy:
                return
            rev = core.revision_by_number(self.mission, number)
            s = self._sel()
            s['rev'] = number
            if s['mode'] not in rev['modes']:
                s['mode'] = rev['modes'][0]
            diffs = core.difficulties_of(rev, s['mode'])
            s['difficulty'] = s['difficulty'] if s['difficulty'] in diffs else (diffs[0] if diffs else None)
            self.hide_error()
            self._refresh()

        def back_to_current(self):
            self.select_revision(core.current_revision(self.mission))

        def set_mode(self, title):
            mode = next((k for k, v in core.MODE_TITLES.items() if v == title), None)
            if mode and mode in self._rev()['modes']:
                s = self._sel()
                s['mode'] = mode
                diffs = core.difficulties_of(self._rev(), mode)
                s['difficulty'] = diffs[0] if diffs else None
                self._refresh()

        def set_difficulty(self, value):
            self._sel()['difficulty'] = value
            self._refresh()

        def toggle_details(self):
            self.details_open = not self.details_open
            self._render_summary()
            self._last_sw = None
            self._on_resize()

        def toggle_archive(self):
            self.archive_open = not self.archive_open
            self._render_archive()

        def toggle_shop(self):
            self.shop_open = not self.shop_open
            self._render_shop()

        def info_text(self):
            """What the Owner copies: the current choice of the window, and (separately) what was really launched last."""
            s, rev = self._sel(), self._rev()
            preset = self._preset()
            st = self._build_state()
            return core.test_info(self.mission, rev['number'], s['mode'], preset, s['difficulty'], self.settings.game_dir, self.settings.no_voice, st[1] if st else '') \
                + '\n\n' + core.last_launch_text(self.settings.data.get('last_launch'))

        def copy_info(self):
            text = self.info_text()
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
            self.status.configure(text='Сведения о тесте скопированы в буфер обмена.')
            return text

        def _request_map_status(self):
            """The build state is read off the interface thread (hashing the inputs must never freeze the window); a redraw never starts a build."""
            mission, preset, gdir = self.mission, self._preset(), self.settings.game_dir
            if self.busy or not preset:
                return

            def work():
                try:
                    st = self.launcher.backend.status(mission, preset, gdir)
                    h = self.launcher.backend.build_hash(mission, preset) if hasattr(self.launcher.backend, 'build_hash') else ''
                except Exception:  # noqa: BLE001
                    st, h = 'unknown', ''
                self.queue.put(('mapstatus', (mission, preset, st, h)))
            threading.Thread(target=work, daemon=True).start()

        def start(self):
            if self.busy:
                return
            self.hide_error()
            s, rev = self._sel(), self._rev()
            if s['mode'] == 'campaign':
                self.open_campaign()
                return
            preset = self._preset()
            info = {'mission': self.mission, 'revision': rev['number'], 'revision_label': rev['label'], 'archive': not rev['current'], 'mode': s['mode'], 'difficulty': s['difficulty']}
            if not self.launcher.start_async(self.mission, preset, lambda st: self.queue.put(('stage', st)), lambda r: self.queue.put(('done', r)), info):
                self.status.configure(text='Подготовка уже выполняется.')
                return
            self.busy = True
            self.done_stages = []
            self.current_stage = 'check'
            self._apply_busy()
            self._show_stages()

        def _poll(self):
            try:
                while True:
                    kind, value = self.queue.get_nowait()
                    if kind == 'stage':
                        self.done_stages.append(self.current_stage)
                        self.current_stage = value
                        self._show_stages()
                    elif kind == 'done':
                        self._finish(value)
                    elif kind == 'mapstatus':
                        m, p, st, h = value
                        self.build_state[(m, p)] = (st, h)
                        if not self.busy and m == self.mission and p == self._preset():
                            self.build_label.configure(text=self._build_text(), text_color=self._build_color())
            except queue.Empty:
                pass
            self.after(100, self._poll)

        def _show_stages(self):
            parts = []
            for key, label in core.STAGES.items():
                if key in self.done_stages:
                    parts.append('✓ ' + label)
                elif key == self.current_stage:
                    parts.append('→ ' + label + '…')
            self.stage_label.configure(text='   '.join(parts), text_color=TEXT)

        def _finish(self, result):
            self.busy = False
            self._apply_busy()
            if result.ok:
                self.stage_label.configure(text='✓ ' + result.message, text_color=GREEN)
                self.status.configure(text='Игра: %s' % self.settings.game_dir)
            else:
                self.stage_label.configure(text='', text_color=MUTED)
                self.show_error(result.message, result.kind)
            self._render_summary()
            self._request_map_status()

        def _apply_busy(self):
            state = 'disabled' if self.busy else 'normal'
            self.start_button.configure(state=state, text='Подготовка…' if self.busy else self.start_text())
            for b in self.mission_buttons.values():
                b.configure(state=state)
            self.settings_button.configure(state=state)

        def show_error(self, message, kind='error'):
            self.error_frame.configure(border_color=AMBER if kind == 'busy-game' else RED)
            self.error_label.configure(text=message)
            self.error_frame.grid(row=self.error_row, column=0, sticky='ew', padx=8, pady=(8, 4))
            self.status.configure(text=message.split('.')[0])
            self._last_sw = None
            self.after(20, self._on_resize)

        def hide_error(self):
            self.error_frame.grid_remove()

        def open_campaign(self):
            import gui_campaign
            win = getattr(self, 'campaign_window', None)
            if win is not None and win.winfo_exists():
                win.lift()
                return win
            cls = gui_campaign.make_window_class(ctk, dict(BG=BG, PANEL=PANEL, CARD=CARD, LINE=LINE, ACCENT=ACCENT, ACCENT_HOVER=ACCENT_HOVER, TEXT=TEXT, MUTED=MUTED,
                                                           AMBER=AMBER, RED=RED, GREEN=GREEN, FONT=FONT))
            import campaign_flow
            settings = self.settings

            class LiveBackend(campaign_flow.BuildCampaignBackend):
                @property
                def no_voice(self):  # read at every launch: the setting may be changed while the window is open
                    return settings.no_voice

            self.campaign_window = cls(self, flow=campaign_flow.CampaignFlow(LiveBackend()))
            return self.campaign_window

        def open_workshop(self):
            import gui_workshop
            import workshop
            if self.mission not in workshop.MISSIONS:
                self.status.configure(text='Для этой миссии Мастерской пока нет: выберите «Час икс», «Эвакуацию» или «Эпидемию».')
                return None
            win = getattr(self, 'workshop_window', None)
            if win is not None and win.winfo_exists():
                win.lift()
                return win
            cls = gui_workshop.make_window_class(ctk, dict(BG=BG, PANEL=PANEL, CARD=CARD, LINE=LINE, ACCENT=ACCENT, ACCENT_HOVER=ACCENT_HOVER, TEXT=TEXT, MUTED=MUTED, AMBER=AMBER, RED=RED,
                                                           GREEN=GREEN, FONT=FONT))
            self.workshop_window = cls(self, self.mission)
            return self.workshop_window

        def open_log(self):
            core.log('log opened by the user')
            try:
                os.startfile(core.LOG_PATH)
            except OSError:
                os.startfile(os.path.dirname(core.LOG_PATH))

        def open_settings(self):
            win = ctk.CTkToplevel(self, fg_color=BG)
            win.title('Настройки')
            win.geometry('620x360')
            win.minsize(520, 320)
            win.transient(self)
            win.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(win, text='Путь к установленной игре', font=(FONT, 15, 'bold'), text_color=TEXT, anchor='w').grid(row=0, column=0, columnspan=2, sticky='ew', padx=20, pady=(18, 4))
            var = ctk.StringVar(value=self.settings.game_dir)
            entry = ctk.CTkEntry(win, textvariable=var, height=36, font=(FONT, 13), fg_color=CARD, border_color=LINE)
            entry.grid(row=1, column=0, sticky='ew', padx=(20, 8))
            note = ctk.CTkLabel(win, text='', font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=560)
            note.grid(row=2, column=0, columnspan=2, sticky='ew', padx=20, pady=(6, 0))

            def choose():
                d = filedialog.askdirectory(parent=win, initialdir=var.get() or None, title='Папка StarCraft II')
                if d:
                    var.set(os.path.normpath(d))

            voice_var = ctk.BooleanVar(value=self.settings.no_voice)
            ctk.CTkCheckBox(win, text='Без добавленной озвучки (портреты, тексты и порядок сцен остаются; карта с суффиксом _novoice)', variable=voice_var, font=(FONT, 13),
                            text_color=TEXT).grid(row=5, column=0, columnspan=2, sticky='w', padx=20, pady=(14, 0))

            def save():
                problem = core.game_dir_problem(var.get())
                if problem:
                    note.configure(text=problem, text_color=RED)
                    return
                self.settings.data['game_dir'] = var.get()
                self.settings.data['no_voice'] = bool(voice_var.get())
                self.settings.save()
                self.status.configure(text='Игра: %s' % var.get())
                self.build_state = {}
                self._refresh()
                win.destroy()

            ctk.CTkButton(win, text='Выбрать папку…', width=140, height=36, font=(FONT, 13), command=choose).grid(row=1, column=1, padx=(0, 20))
            row = ctk.CTkFrame(win, fg_color='transparent')
            row.grid(row=3, column=0, columnspan=2, sticky='w', padx=14, pady=20)
            ctk.CTkButton(row, text='Сохранить', width=120, height=36, font=(FONT, 13), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=save).grid(row=0, column=0, padx=6)
            ctk.CTkButton(row, text='Журнал диагностики', width=170, height=36, font=(FONT, 13), fg_color='transparent', border_width=1, border_color=LINE,
                          text_color=TEXT, hover_color=CARD, command=self.open_log).grid(row=0, column=1, padx=6)
            ctk.CTkButton(row, text='Закрыть', width=100, height=36, font=(FONT, 13), fg_color='transparent', border_width=1, border_color=LINE,
                          text_color=MUTED, hover_color=CARD, command=win.destroy).grid(row=0, column=2, padx=6)
            ctk.CTkLabel(win, text='Настройки хранятся отдельно от игровых конфигов: %s' % core.SETTINGS_PATH, font=(FONT, 11), text_color=MUTED,
                         anchor='w', justify='left', wraplength=560).grid(row=4, column=0, columnspan=2, sticky='ew', padx=20)
            self.settings_window = win
            return win

    return ctk, App


def grab(window, path):
    """PNG of exactly this window by PrintWindow (never a screen area: a DPI-unaware grab captured the Owner's browser once)."""
    import ctypes
    from ctypes import wintypes as wt
    from PIL import Image
    user32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)

    class BI(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                    ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD), ('x', wt.LONG), ('y', wt.LONG), ('c', wt.DWORD), ('i', wt.DWORD)]
    bi = BI()
    bi.biSize, bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = ctypes.sizeof(BI), w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    if ok:
        Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB').save(path)
    return bool(ok)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    snapshot_dir = None  # (the old --snapshots aid is replaced by tools/launcher_window_check.py)
    try:
        if not ensure_dependencies():
            raise RuntimeError('customtkinter не установлен. Выполните: pip install -r requirements-gui.txt --target tmp\\thirdparty\\ctk')
        if os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\GhostOpsLauncherSingleton')
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                core.log('second launcher instance refused')
                return 0
        ctk, App = build_app()
        if '--scale' in argv:  # developer aid: extra scaling on top of Windows scaling
            factor = float(argv[argv.index('--scale') + 1])
            ctk.set_widget_scaling(factor)
            ctk.set_window_scaling(factor)
        app = App()
        if '--mission' in argv:  # open on a given mission (and, as a developer aid, on a given version)
            app.select_mission(argv[argv.index('--mission') + 1])
            if '--revision' in argv:
                app.select_revision(int(argv[argv.index('--revision') + 1]))
        app.mainloop()
        return 0
    except Exception:
        text = traceback.format_exc()
        core.log('launcher crashed:\n' + text)
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror('Ghost Ops', 'Запускатель не смог открыться.\n\nПодробности записаны в журнал:\n%s' % core.LOG_PATH)
            r.destroy()
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())
