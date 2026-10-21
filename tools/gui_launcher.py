"""Ghost Ops graphical launcher (CustomTkinter). A shell over tools/launcher_core.py -> tools/build.py.

Start it with GhostOps_Launcher.pyw (double click, no console window). Errors go to %APPDATA%\\GhostOps\\launcher.log.
"""
import io
import os
import queue
import subprocess
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
        def __init__(self, launcher=None):
            super().__init__(fg_color=BG)
            self.launcher = launcher or core.Launcher()
            self.settings = self.launcher.settings
            self.title('Ghost Ops — запускатель')
            self.geometry('1060x700')
            self.minsize(900, 620)
            self.queue = queue.Queue()
            self.mission = self.settings.mission()
            self.preset = self.settings.profile(self.mission)
            self.open_details = None
            self.card_frames = {}
            self.card_texts = []
            self.busy = False
            self.images = {}
            self._build_layout()
            self._refresh()
            self.after(100, self._poll)

        # ------------------------------------------------------------------ layout
        def _build_layout(self):
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            left = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14, width=270)
            left.grid(row=0, column=0, sticky='nsew', padx=(14, 7), pady=(14, 7))
            left.grid_propagate(False)
            left.grid_rowconfigure(3, weight=1)
            ctk.CTkLabel(left, text='GHOST OPS', font=(FONT, 22, 'bold'), text_color=ACCENT).grid(row=0, column=0, sticky='w', padx=18, pady=(18, 0))
            ctk.CTkLabel(left, text='Запускатель миссий', font=(FONT, 13), text_color=MUTED).grid(row=1, column=0, sticky='w', padx=18, pady=(0, 12))
            ctk.CTkLabel(left, text='МИССИИ', font=(FONT, 11, 'bold'), text_color=MUTED).grid(row=2, column=0, sticky='w', padx=18, pady=(6, 4))
            lst = ctk.CTkFrame(left, fg_color='transparent')
            lst.grid(row=3, column=0, sticky='new', padx=10)
            lst.grid_columnconfigure(0, weight=1)
            self.mission_buttons = {}
            for i, m in enumerate(core.MISSIONS):
                b = ctk.CTkButton(lst, text='%s\n%s' % (m['title'], m['status']), anchor='w', height=60, corner_radius=10,
                                  font=(FONT, 14), fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT, border_width=2,
                                  border_color=CARD, command=lambda mid=m['id']: self.select_mission(mid))
                b.grid(row=i, column=0, sticky='ew', pady=4)
                self.mission_buttons[m['id']] = b
            self.settings_button = ctk.CTkButton(left, text='Настройки', height=34, width=120, corner_radius=8, font=(FONT, 13),
                                                 fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED,
                                                 hover_color=CARD, command=self.open_settings)
            self.settings_button.grid(row=5, column=0, sticky='w', padx=14, pady=(0, 14))
            self.campaign_button = ctk.CTkButton(left, text='Кампания: Вне закона → Час икс', height=44, corner_radius=10, font=(FONT, 13, 'bold'),
                                                 fg_color=ACCENT_DARK, hover_color=ACCENT, text_color=TEXT, command=self.open_campaign)
            self.campaign_button.grid(row=4, column=0, sticky='ew', padx=14, pady=(8, 8))

            right = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14)
            right.grid(row=0, column=1, sticky='nsew', padx=(7, 14), pady=(14, 7))
            right.grid_columnconfigure(0, weight=1)
            right.grid_rowconfigure(0, weight=1)
            self.scroll = ctk.CTkScrollableFrame(right, fg_color='transparent', corner_radius=0)
            self.scroll.grid(row=0, column=0, sticky='nsew', padx=6, pady=(6, 0))
            self.scroll.grid_columnconfigure(0, weight=1)

            head = ctk.CTkFrame(self.scroll, fg_color='transparent')
            head.grid(row=0, column=0, sticky='ew', padx=10, pady=(8, 4))
            head.grid_columnconfigure(1, weight=1)
            self.image_label = ctk.CTkLabel(head, text='', width=300, height=170)
            self.image_label.grid(row=0, column=0, sticky='nw', padx=(0, 18))
            info = ctk.CTkFrame(head, fg_color='transparent')
            info.grid(row=0, column=1, sticky='nsew')
            info.grid_columnconfigure(0, weight=1)
            self.title_label = ctk.CTkLabel(info, text='', font=(FONT, 26, 'bold'), text_color=TEXT, anchor='w', justify='left')
            self.title_label.grid(row=0, column=0, sticky='ew')
            self.subtitle_label = ctk.CTkLabel(info, text='', font=(FONT, 14), text_color=MUTED, anchor='w')
            self.subtitle_label.grid(row=1, column=0, sticky='ew')
            self.status_badge = ctk.CTkLabel(info, text='', font=(FONT, 12, 'bold'), corner_radius=8, fg_color=ACCENT_DARK, text_color=TEXT, padx=10, pady=2)
            self.status_badge.grid(row=2, column=0, sticky='w', pady=(8, 8))
            self.description_label = ctk.CTkLabel(info, text='', font=(FONT, 14), text_color=TEXT, anchor='nw', justify='left', wraplength=380)
            self.description_label.grid(row=3, column=0, sticky='ew')

            self.diff_title = ctk.CTkLabel(self.scroll, text='Сложность', font=(FONT, 16, 'bold'), text_color=TEXT, anchor='w')
            self.diff_title.grid(row=1, column=0, sticky='ew', padx=12, pady=(14, 4))
            self.cards = ctk.CTkFrame(self.scroll, fg_color='transparent')
            self.cards.grid(row=2, column=0, sticky='ew', padx=8)
            self.details = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=10, border_width=1, border_color=LINE)
            self.details_title = ctk.CTkLabel(self.details, text='', font=(FONT, 14, 'bold'), text_color=ACCENT, anchor='w')
            self.details_title.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 2))
            self.details_text = ctk.CTkLabel(self.details, text='', font=(FONT, 13), text_color=TEXT, anchor='w', justify='left', wraplength=560)
            self.details_text.grid(row=1, column=0, sticky='ew', padx=14, pady=(0, 10))
            self.details.grid_columnconfigure(0, weight=1)
            self.error_frame = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=10, border_width=2, border_color=RED)
            self.error_label = ctk.CTkLabel(self.error_frame, text='', font=(FONT, 13), text_color=TEXT, anchor='w', justify='left', wraplength=560)
            self.error_label.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 6))
            self.error_frame.grid_columnconfigure(0, weight=1)
            eb = ctk.CTkFrame(self.error_frame, fg_color='transparent')
            eb.grid(row=1, column=0, sticky='w', padx=10, pady=(0, 10))
            ctk.CTkButton(eb, text='Открыть журнал', width=140, height=30, font=(FONT, 13), command=self.open_log).grid(row=0, column=0, padx=4)
            ctk.CTkButton(eb, text='Скрыть', width=90, height=30, font=(FONT, 13), fg_color='transparent', border_width=1,
                          border_color=LINE, text_color=MUTED, hover_color=CARD, command=self.hide_error).grid(row=0, column=1, padx=4)

            bar = ctk.CTkFrame(right, fg_color='transparent')
            bar.grid(row=1, column=0, sticky='ew', padx=16, pady=(8, 16))
            bar.grid_columnconfigure(1, weight=1)
            self.start_button = ctk.CTkButton(bar, text='Начать миссию', height=52, width=230, corner_radius=12, font=(FONT, 18, 'bold'),
                                              fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color='#ffffff', command=self.start)
            self.start_button.grid(row=0, column=0, sticky='w')
            self.stage_label = ctk.CTkLabel(bar, text='', font=(FONT, 13), text_color=MUTED, anchor='w', justify='left', wraplength=420)
            self.stage_label.grid(row=0, column=1, sticky='ew', padx=18)

            self.status = ctk.CTkLabel(self, text='', font=(FONT, 12), text_color=MUTED, anchor='w')
            self.status.grid(row=1, column=0, columnspan=2, sticky='ew', padx=22, pady=(0, 8))
            self.right = right
            self._resize_job = None
            self.bind('<Configure>', self._schedule_resize, add='+')
            self.scroll._parent_canvas.bind('<Configure>', lambda e: self._schedule_resize(), add='+')

        # ------------------------------------------------------------------ rendering
        def _refresh(self):
            m = core.mission_info(self.mission)
            profiles = core.profiles_of(self.mission)
            for mid, b in self.mission_buttons.items():
                sel = mid == self.mission
                b.configure(border_color=ACCENT if sel else CARD, fg_color=ACCENT_DARK if sel else CARD)
            self.title_label.configure(text=m['title'])
            self.subtitle_label.configure(text=m['subtitle'])
            self.status_badge.configure(text=m['status'], fg_color=ACCENT_DARK if m['status'] == 'Играбельно' else '#5a4a1f',
                                        text_color=TEXT if m['status'] == 'Играбельно' else AMBER)
            path, there = core.installed_map_info(self.mission, self.preset, self.settings.game_dir, self.settings.no_voice)
            self.description_label.configure(text=m['description'] + '\n\nКарта: %s%s' % (path, '' if there else '  (будет собрана и установлена при запуске)'))
            if mission_key(self.mission) not in self.images:
                from PIL import Image  # noqa: F401
                img = mission_image(self.mission)
                self.images[mission_key(self.mission)] = ctk.CTkImage(light_image=img, dark_image=img, size=(300, 170))
            self.image_label.configure(image=self.images[mission_key(self.mission)])
            self._build_cards(profiles)
            self._render_details()
            self.status.configure(text='Игра: %s' % self.settings.game_dir)
            self._apply_busy()
            self._last_sw = None
            self.after(30, self._on_resize)

        def _build_cards(self, profiles):
            for w in self.cards.winfo_children():
                w.destroy()
            self.card_frames = {}
            self.card_texts = []
            if not profiles:
                self.diff_title.configure(text='Вариант запуска')
                f = ctk.CTkFrame(self.cards, fg_color=CARD, corner_radius=10, border_width=2, border_color=ACCENT)
                f.grid(row=0, column=0, sticky='ew', padx=4, pady=4)
                f.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(f, text='Прототип', font=(FONT, 15, 'bold'), text_color=TEXT, anchor='w').grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 0))
                t = ctk.CTkLabel(f, text='Запускается в единственном варианте, как и раньше. Выбора сложности у этой миссии нет.',
                                 font=(FONT, 13), text_color=MUTED, anchor='w', justify='left', wraplength=520)
                t.grid(row=1, column=0, sticky='ew', padx=14, pady=(2, 12))
                self.card_texts.append(t)
                self.cards.grid_columnconfigure(0, weight=1)
                return
            self.diff_title.configure(text='Сложность')
            for i in range(3):
                self.cards.grid_columnconfigure(i, weight=1, uniform='cards')
            for i, p in enumerate(profiles):
                sel = p['name'] == self.preset
                f = ctk.CTkFrame(self.cards, fg_color=CARD_HOVER if sel else CARD, corner_radius=10, border_width=2,
                                 border_color=ACCENT if sel else LINE)
                f.grid(row=0, column=i, sticky='nsew', padx=4, pady=4)
                f.grid_columnconfigure(0, weight=1)
                name = ctk.CTkLabel(f, text=p['label'], font=(FONT, 16, 'bold'), text_color=TEXT, anchor='w')
                name.grid(row=0, column=0, sticky='ew', padx=12, pady=(10, 0))
                row = 1
                if p['experimental']:
                    ctk.CTkLabel(f, text='Эксперимент', font=(FONT, 11, 'bold'), text_color=AMBER, fg_color='#4a3b17', corner_radius=6,
                                 padx=8, pady=1).grid(row=row, column=0, sticky='w', padx=12, pady=(4, 0))
                    row += 1
                if p.get('badge'):
                    ctk.CTkLabel(f, text=p['badge'].upper(), font=(FONT, 11, 'bold'), text_color='#0b2a14', fg_color=GREEN, corner_radius=6,
                                 padx=8, pady=1).grid(row=row, column=0, sticky='w', padx=12, pady=(4, 0))
                    row += 1
                t = ctk.CTkLabel(f, text=p['card'], font=(FONT, 13), text_color=MUTED, anchor='nw', justify='left', wraplength=200)
                t.grid(row=row, column=0, sticky='nsew', padx=12, pady=(6, 4))
                f.grid_rowconfigure(row, weight=1)
                self.card_texts.append(t)
                more = ctk.CTkButton(f, text='Скрыть' if self.open_details == p['name'] else 'Подробнее', height=24, width=90, font=(FONT, 12),
                                     fg_color='transparent', text_color=ACCENT, hover_color=CARD, anchor='w',
                                     command=lambda n=p['name']: self.toggle_details(n))
                more.grid(row=row + 1, column=0, sticky='w', padx=6, pady=(0, 8))
                for w in [f, name, t] + [c for c in f.winfo_children() if isinstance(c, ctk.CTkLabel)]:
                    w.bind('<Button-1>', lambda e, n=p['name']: self.select_profile(n))
                self.card_frames[p['name']] = f
            self._relayout_cards()

        def _render_details(self):
            if not self.open_details:
                self.details.grid_remove()
                return
            label = next((p['label'] for p in core.profiles_of(self.mission) if p['name'] == self.open_details), '')
            self.details_title.configure(text='Подробности: %s' % label)
            self.details_text.configure(text='\n'.join('•  ' + ln for ln in core.detail_lines(self.mission, self.open_details)))
            self.details.grid(row=3, column=0, sticky='ew', padx=12, pady=(8, 4))

        def _relayout_cards(self):
            """Three cards in a row; stacked when the window is narrow."""
            if not self.card_frames:
                return
            narrow = self.scroll.winfo_width() / (self._get_window_scaling() or 1.0) < 500
            for i, f in enumerate(self.card_frames.values()):
                if narrow:
                    f.grid_configure(row=i, column=0)
                    self.cards.grid_columnconfigure(0, weight=1)
                else:
                    f.grid_configure(row=0, column=i)

        def _schedule_resize(self, event=None):
            """Window edges move first, the inner frames follow a moment later: measure after the layout settled."""
            if event is not None and event.widget is not self:
                return
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(80, self._on_resize)

        def _on_resize(self, event=None):
            if event is not None and event.widget is not self:
                return
            k = self._get_window_scaling() or 1.0
            sw = self.scroll.winfo_width() / k  # winfo_* report physical pixels, wraplength wants logical ones
            if getattr(self, '_last_sw', None) == int(sw):
                return  # nothing changed: avoids a Configure feedback loop
            self._last_sw = int(sw)
            rw = self.right.winfo_width() / k
            self.description_label.configure(wraplength=int(max(240, sw - 360)))
            self.title_label.configure(wraplength=int(max(240, sw - 360)))
            narrow = sw < 500
            card_w = (sw - 90) if narrow else (sw - 60) / 3 - 34
            for t in self.card_texts:
                t.configure(wraplength=int(max(130, card_w)))
            self.details_text.configure(wraplength=int(max(240, sw - 100)))
            self.error_label.configure(wraplength=int(max(240, sw - 100)))
            self.stage_label.configure(wraplength=int(max(180, rw - 330)))
            self._relayout_cards()

        # ------------------------------------------------------------------ actions
        def select_mission(self, mission_id):
            if self.busy:
                return
            self.mission = mission_id
            self.preset = self.settings.profile(mission_id)
            self.open_details = None
            self.hide_error()
            self.settings.remember(self.mission, self.preset)
            self._refresh()
            self._on_resize()

        def select_profile(self, name):
            if self.busy:
                return
            self.preset = name
            self.settings.remember(self.mission, self.preset)
            self._refresh()
            self._on_resize()

        def toggle_details(self, name):
            self.open_details = None if self.open_details == name else name
            self._refresh()
            self._on_resize()

        def start(self):
            if self.busy:
                return
            self.hide_error()
            if not self.launcher.start_async(self.mission, self.preset, lambda s: self.queue.put(('stage', s)), lambda r: self.queue.put(('done', r))):
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

        def _apply_busy(self):
            state = 'disabled' if self.busy else 'normal'
            self.start_button.configure(state=state, text='Подготовка…' if self.busy else 'Начать миссию')
            for b in self.mission_buttons.values():
                b.configure(state=state)
            self.settings_button.configure(state=state)

        def show_error(self, message, kind='error'):
            self.error_frame.configure(border_color=AMBER if kind == 'busy-game' else RED)
            self.error_label.configure(text=message)
            self.error_frame.grid(row=4, column=0, sticky='ew', padx=12, pady=(10, 6))
            self.status.configure(text=message.split('.')[0])

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

    def mission_key(mission_id):
        return mission_id

    return ctk, App


def grab(window, path):
    """Screenshot of exactly this window (physical pixels, so Windows scaling does not shift the crop)."""
    import ctypes
    from ctypes import wintypes
    from PIL import ImageGrab
    rect = wintypes.RECT()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(path)


def run_snapshots(app, ctk, outdir):
    """Developer aid: render the window in several states and save PNGs of exactly the window area."""
    from PIL import ImageGrab
    os.makedirs(outdir, exist_ok=True)
    steps = []

    def shot(name):
        app.update_idletasks()
        app.update()
        grab(app, os.path.join(outdir, name + '.png'))

    def wait(ms):
        end = time.time() + ms / 1000
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def plan():
        app.attributes('-topmost', True)
        app.lift()
        app.update()
        shot('01_main_extreme')
        app.toggle_details('extreme')
        shot('02_details_open')
        app.toggle_details('extreme')
        app.select_mission('traynor02')
        shot('03_prototype')
        app.select_mission('traynor01')
        app.select_profile('hard')
        app.geometry('900x620')
        wait(600)
        shot('04_narrow_window')
        app.geometry('1060x700')
        app.busy = True
        app.done_stages = ['check', 'build']
        app.current_stage = 'verify'
        app._apply_busy()
        app._show_stages()
        shot('05_busy_stages')
        app.busy = False
        app._apply_busy()
        app.stage_label.configure(text='')
        app.show_error('StarCraft II уже запущена. Закройте игру самостоятельно и повторите: запускатель никогда не завершает её принудительно.', 'busy-game')
        shot('06_error_game_running')
        app.show_error('Не удалось подготовить карту (код 2). Подробности в журнале.', 'error')
        shot('07_error')
        app.hide_error()
        win = app.open_settings()
        win.update()
        win.attributes('-topmost', True)
        app.update()
        grab(win, os.path.join(outdir, '08_settings.png'))
        win.destroy()
        app.select_profile('extreme')
        shot('09_final')
        app.destroy()

    app.after(600, plan)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    snapshot_dir = None
    if '--snapshots' in argv:
        snapshot_dir = argv[argv.index('--snapshots') + 1]
    try:
        if not ensure_dependencies():
            raise RuntimeError('customtkinter не установлен. Выполните: pip install -r requirements-gui.txt --target tmp\\thirdparty\\ctk')
        if os.name == 'nt' and snapshot_dir is None:
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
        if snapshot_dir:
            run_snapshots(app, ctk, snapshot_dir)
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
