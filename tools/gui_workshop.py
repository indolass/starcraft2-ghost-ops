"""Window "Мастерская миссий" of the launcher (CustomTkinter): variants of an existing mission, their settings, a free test build and start.

Path: mission -> create a variant from a profile -> change the settings -> save -> build and start a free test. The window only shows and edits what tools/workshop.py supports (a field
exists only if its mechanic is in the mission); every number shown, the composition, the differences and the build come from the SAME effective configuration (workshop.effective_cfg).
Free tests never touch the campaign. No game logic here; development tests drive it with a fake backend.
"""
import threading
import tkinter
import queue

import build
import workshop

TITLES = {'traynor03': 'Час икс', 'thanson01': 'Эвакуация', 'thanson02': 'Эпидемия'}


class WorkshopBackend:
    """What the window needs from the outside: the readiness of the game and the start of the test. Tests replace it."""

    def sc2_running(self):
        return build.sc2_running()

    def start(self, variant):
        command, dest = workshop.launch_command(variant)
        import os
        if not os.path.isfile(dest):
            return 8
        return build.start_detached(command, owner=True)


def make_window_class(ctk, pal):
    BG, PANEL, CARD, LINE, ACCENT, ACCENT_HOVER, TEXT, MUTED, AMBER, RED, GREEN, FONT = [pal[k] for k in (
        'BG', 'PANEL', 'CARD', 'LINE', 'ACCENT', 'ACCENT_HOVER', 'TEXT', 'MUTED', 'AMBER', 'RED', 'GREEN', 'FONT')]

    class WorkshopWindow(ctk.CTkToplevel):
        def __init__(self, app, mission, backend=None):
            super().__init__(app, fg_color=BG)
            self.mission = mission
            self.backend = backend or WorkshopBackend()
            self.title('Ghost Ops — Мастерская миссий: %s' % TITLES.get(mission, mission))
            self.geometry('1180x780')
            self.minsize(1040, 600)
            self.transient(app)
            self.variant = None
            self.section = 'squad'
            self.busy = False
            self.stage_text = ''
            self.invalid = {}  # field id -> text that could not be read (blocks the build, nothing is stored)
            self.q = queue.Queue()
            self.rows = {}
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            self._build()
            variants = workshop.list_variants(mission)
            if variants:
                self.variant = variants[-1]
            self.refresh()
            self.after(150, self._poll)

        # ------------------------------------------------------------------------------------------------------------------------ layout
        def _build(self):
            head = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
            head.grid(row=0, column=0, sticky='ew', padx=12, pady=(12, 6))
            head.grid_columnconfigure(3, weight=1)
            ctk.CTkLabel(head, text='Мастерская: %s' % TITLES.get(self.mission, self.mission), font=(FONT, 18, 'bold'), text_color=ACCENT).grid(row=0, column=0, sticky='w', padx=14, pady=(10, 2))
            self.variant_menu = ctk.CTkOptionMenu(head, values=['—'], command=self._pick_variant, width=240, fg_color=CARD, button_color=ACCENT, text_color=TEXT)
            self.variant_menu.grid(row=0, column=1, padx=8, pady=(10, 2))
            ctk.CTkButton(head, text='Создать вариант', width=140, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT, command=self.create_dialog).grid(row=0, column=2, padx=4, pady=(10, 2))
            self.delete_button = ctk.CTkButton(head, text='Удалить вариант', width=130, fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED, hover_color=CARD, command=self.delete_variant)
            self.delete_button.grid(row=0, column=4, padx=(4, 12), pady=(10, 2))
            self.name_var = tkinter.StringVar()
            self.name_entry = ctk.CTkEntry(head, textvariable=self.name_var, width=300, fg_color=CARD, text_color=TEXT, border_color=LINE)
            self.name_entry.grid(row=1, column=0, columnspan=2, sticky='w', padx=14, pady=(2, 4))
            self.name_entry.bind('<FocusOut>', lambda e: self._rename())
            self.name_entry.bind('<Return>', lambda e: self._rename())
            self.base_label = ctk.CTkLabel(head, text='', font=(FONT, 12), text_color=MUTED, anchor='w', justify='left')
            self.base_label.grid(row=1, column=2, columnspan=3, sticky='w', padx=8, pady=(2, 4))
            self.refresh_base_button = ctk.CTkButton(head, text='Взять текущую основу', width=170, height=26, fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED, hover_color=CARD,
                                                     command=self.refresh_base)
            self.refresh_base_button.grid(row=2, column=0, sticky='w', padx=14, pady=(0, 8))
            self.base_note = ctk.CTkLabel(head, text='', font=(FONT, 12), text_color=AMBER, anchor='w', wraplength=700, justify='left')
            self.base_note.grid(row=2, column=1, columnspan=4, sticky='w', padx=8, pady=(0, 8))

            body = ctk.CTkFrame(self, fg_color='transparent')
            body.grid(row=1, column=0, sticky='nsew', padx=12, pady=6)
            body.grid_columnconfigure(1, weight=3, minsize=600)
            body.grid_columnconfigure(2, weight=2, minsize=250)
            body.grid_rowconfigure(0, weight=1)
            left = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=12, width=210)
            left.grid(row=0, column=0, sticky='ns', padx=(0, 6))
            left.grid_propagate(False)
            ctk.CTkLabel(left, text='РАЗДЕЛЫ', font=(FONT, 11, 'bold'), text_color=MUTED).grid(row=0, column=0, sticky='w', padx=14, pady=(12, 4))
            self.section_buttons = {}
            for i, (sid, title) in enumerate(workshop.SECTIONS):
                b = ctk.CTkButton(left, text=title, anchor='w', height=38, corner_radius=8, fg_color=CARD, hover_color=CARD, text_color=TEXT, border_width=2, border_color=CARD, width=186,
                                  command=lambda s=sid: self.pick_section(s))
                b.grid(row=i + 1, column=0, padx=10, pady=3)
                self.section_buttons[sid] = b
            self.center = ctk.CTkScrollableFrame(body, fg_color=PANEL, corner_radius=12)
            self.center.grid(row=0, column=1, sticky='nsew', padx=6)
            self.center.grid_columnconfigure(0, weight=1)
            self.right = ctk.CTkScrollableFrame(body, fg_color=PANEL, corner_radius=12, width=250)
            self.right.grid(row=0, column=2, sticky='nsew', padx=(6, 0))
            self.right.grid_columnconfigure(0, weight=1)

            bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
            bar.grid(row=2, column=0, sticky='ew', padx=12, pady=(6, 12))
            bar.grid_columnconfigure(2, weight=1)
            self.save_button = ctk.CTkButton(bar, text='Сохранить вариант', width=170, fg_color=CARD, hover_color=LINE, text_color=TEXT, border_width=1, border_color=LINE, command=self.save_variant)
            self.save_button.grid(row=0, column=0, padx=(14, 6), pady=12)
            self.run_button = ctk.CTkButton(bar, text='Собрать и запустить бесплатный тест', width=300, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT, command=self.build_and_run)
            self.run_button.grid(row=0, column=1, padx=6, pady=12)
            self.status_label = ctk.CTkLabel(bar, text='', font=(FONT, 13), text_color=MUTED, anchor='w', justify='left', wraplength=520)
            self.status_label.grid(row=0, column=2, sticky='ew', padx=12, pady=12)

        # ------------------------------------------------------------------------------------------------------------------------ data
        def variants(self):
            return workshop.list_variants(self.mission)

        def _pick_variant(self, label):
            for v in self.variants():
                if self._label(v) == label:
                    self.variant = v
                    self.invalid = {}
                    self.refresh()
                    return

        def _label(self, v):
            return '%s  [%s]' % (v['name'], v['id'])

        def create_dialog(self):
            dlg = ctk.CTkToplevel(self, fg_color=BG)
            dlg.title('Новый вариант')
            dlg.geometry('520x250')
            dlg.transient(self)
            dlg.grab_set()
            ctk.CTkLabel(dlg, text='Название варианта', text_color=TEXT, font=(FONT, 13)).pack(anchor='w', padx=16, pady=(16, 2))
            name = tkinter.StringVar(value='Мой вариант')
            entry = ctk.CTkEntry(dlg, textvariable=name, width=480, fg_color=CARD, text_color=TEXT)
            entry.pack(padx=16)
            ctk.CTkLabel(dlg, text='Основа (бесплатный профиль миссии)', text_color=TEXT, font=(FONT, 13)).pack(anchor='w', padx=16, pady=(12, 2))
            profiles = workshop.base_profiles(self.mission)
            labels = {lab: n for n, lab in profiles}
            default = workshop.default_base(self.mission)
            first = next((lab for n, lab in profiles if n == default), profiles[-1][1])
            base = tkinter.StringVar(value=first)
            ctk.CTkOptionMenu(dlg, values=[lab for _, lab in profiles], variable=base, width=480, fg_color=CARD, button_color=ACCENT, text_color=TEXT).pack(padx=16)
            msg = ctk.CTkLabel(dlg, text='', text_color=RED, font=(FONT, 12))
            msg.pack(anchor='w', padx=16, pady=(6, 0))

            def ok():
                try:
                    v = workshop.new_variant(self.mission, name.get(), labels[base.get()])
                except ValueError as e:
                    msg.configure(text=str(e))
                    return
                dlg.destroy()
                self.variant = v
                self.invalid = {}
                self.refresh()
            ctk.CTkButton(dlg, text='Создать', width=140, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT, command=ok).pack(anchor='e', padx=16, pady=14)
            self._dialog = dlg
            return dlg

        def create_variant(self, name, base_preset=None):
            """The same as the dialog (used by tests)."""
            self.variant = workshop.new_variant(self.mission, name, base_preset)
            self.invalid = {}
            self.refresh()
            return self.variant

        def _rename(self):
            if self.variant is None:
                return
            n = self.name_var.get().strip()
            if n and n != self.variant['name'] and len(n) <= 60:
                self.variant['name'] = n
                workshop.save(self.variant)
                self.refresh(rows=False)

        def delete_variant(self):
            if self.variant is None or self.busy:
                return
            workshop.delete_draft(self.variant)
            self.variant = (self.variants() or [None])[-1]
            self.invalid = {}
            self.refresh()

        def refresh_base(self):
            if self.variant is None:
                return
            workshop.refresh_base(self.variant)
            self.say('Взята текущая основа; измененные поля сохранены. Следующая сборка — новая ревизия.', TEXT)
            self.refresh()

        def pick_section(self, sid):
            self.section = sid
            self.refresh()

        def say(self, text, color=None):
            self.status_label.configure(text=text, text_color=color or MUTED)

        # ------------------------------------------------------------------------------------------------------------------------ editing
        def _fields(self):
            if self.variant is None:
                return []
            base = workshop.base_cfg_of(self.variant)
            return workshop.supported_fields(self.mission, base)

        def _visible(self, f, cfg):
            if f.visible_if is None:
                return True
            try:
                return bool(f.visible_if(cfg))
            except KeyError:
                return False

        def set_value(self, fid, text):
            """Reads what the player typed / clicked; a value that cannot be read is kept as an error and blocks the build."""
            f = workshop.BY_ID[fid]
            if f.kind in ('bool', 'choice'):
                shown = text
            else:
                try:
                    shown = int(str(text).strip()) if f.kind == 'int' else float(str(text).strip().replace(',', '.'))
                except ValueError:
                    self.invalid[fid] = str(text)
                    self.refresh()
                    return False
            self.invalid.pop(fid, None)
            workshop.set_field(self.variant, fid, shown)
            workshop.save(self.variant)
            self.refresh()
            return True

        def _arrow(self, fid, sign):
            f = workshop.BY_ID[fid]
            cur = workshop.effective_cfg(self.variant)
            now = f.display(workshop._get(cur, f.path))
            self.set_value(fid, round(now + sign * f.step, 6) if f.kind == 'float' else int(now + sign * f.step))

        def _reset(self, fid):
            self.invalid.pop(fid, None)
            workshop.reset_field(self.variant, fid)
            workshop.save(self.variant)
            self.refresh()

        # ------------------------------------------------------------------------------------------------------------------------ drawing
        def refresh(self, rows=True):
            names = [self._label(v) for v in self.variants()] or ['—']
            self.variant_menu.configure(values=names)
            if self.variant is None:
                self.variant_menu.set('—')
                self.name_var.set('')
                self.base_label.configure(text='Создайте вариант на основе профиля миссии')
                self.base_note.configure(text='')
                self._clear(self.center)
                self._clear(self.right)
                ctk.CTkLabel(self.center, text='Нет варианта. Нажмите «Создать вариант»: он начнётся как копия бесплатного профиля миссии, дальше меняются только поддерживаемые настройки.', font=(FONT, 14), text_color=MUTED,
                             wraplength=520, justify='left').grid(row=0, column=0, sticky='w', padx=20, pady=20)
                self.run_button.configure(state='disabled')
                self.save_button.configure(state='disabled')
                self.delete_button.configure(state='disabled')
                self.refresh_base_button.configure(state='disabled')
                return
            v = self.variant
            self.variant_menu.set(self._label(v))
            self.name_var.set(v['name'])
            self.base_label.configure(text='Основа: %s (%s)  ·  ревизия сборки: %s' % (v['base_label'], v['base_preset'], v['built']['revision'] if v.get('built') else 'нет'))
            self.base_note.configure(text='Основа изменилась после создания варианта: вариант использует свою копию, она не меняется сама.' if workshop.base_changed(v) else '')
            self.refresh_base_button.configure(state='normal' if workshop.base_changed(v) else 'disabled')
            self.delete_button.configure(state='normal' if not self.busy else 'disabled')
            self.save_button.configure(state='normal')
            fields = self._fields()
            avail = {f.section for f in fields}
            for sid, b in self.section_buttons.items():
                sel = sid == self.section
                if sid in avail:
                    b.grid()
                else:
                    b.grid_remove()
                b.configure(border_color=ACCENT if sel else CARD, fg_color=CARD if not sel else LINE)
            if self.section not in avail and avail:
                self.section = next(sid for sid, _ in workshop.SECTIONS if sid in avail)
                for sid, b in self.section_buttons.items():
                    b.configure(border_color=ACCENT if sid == self.section else CARD)
            if rows:
                self._draw_fields(fields)
            self._draw_summary()
            self._update_buttons()

        def _clear(self, frame):
            for w in frame.winfo_children():
                w.destroy()

        def _draw_fields(self, fields):
            self._clear(self.center)
            self.rows = {}
            cfg = workshop.effective_cfg(self.variant)
            base = workshop.base_cfg_of(self.variant)
            r = 0
            for f in fields:
                if f.section != self.section or not self._visible(f, cfg):
                    continue
                now = f.display(workshop._get(cfg, f.path))
                bval = f.display(workshop._get(base, f.path))
                row = ctk.CTkFrame(self.center, fg_color=CARD, corner_radius=10)
                row.grid(row=r, column=0, sticky='ew', padx=8, pady=5)
                row.grid_columnconfigure(1, weight=1)
                changed = f.id in self.variant['changes']
                ctk.CTkLabel(row, text=f.label + ('  •' if changed else ''), font=(FONT, 14, 'bold'), text_color=ACCENT if changed else TEXT, anchor='w').grid(row=0, column=0, columnspan=2, sticky='w', padx=12, pady=(8, 0))
                ctl = ctk.CTkFrame(row, fg_color='transparent')
                ctl.grid(row=1, column=0, sticky='w', padx=12, pady=4)
                if f.kind == 'bool':
                    sw = ctk.CTkSwitch(ctl, text='включено' if now else 'выключено', onvalue=True, offvalue=False, progress_color=ACCENT, text_color=TEXT,
                                       command=lambda fid=f.id: self._switch(fid))
                    sw.select() if now else sw.deselect()
                    sw.grid(row=0, column=0)
                    self.rows[f.id] = sw
                elif f.kind == 'choice':
                    labels = dict(f.choices)
                    var = tkinter.StringVar(value=labels.get(now, now))
                    om = ctk.CTkOptionMenu(ctl, values=[c[1] for c in f.choices], variable=var, width=420, fg_color=PANEL, button_color=ACCENT, text_color=TEXT,
                                           command=lambda text, fid=f.id, f_=f: self.set_value(fid, next(k for k, lab in f_.choices if lab == text)))
                    om.grid(row=0, column=0)
                    self.rows[f.id] = om
                else:
                    var = tkinter.StringVar(value=self.invalid.get(f.id, ('%g' % now) if f.kind == 'float' else str(now)))
                    ctk.CTkButton(ctl, text='−', width=32, fg_color=PANEL, hover_color=LINE, text_color=TEXT, command=lambda fid=f.id: self._arrow(fid, -1)).grid(row=0, column=0, padx=(0, 4))
                    e = ctk.CTkEntry(ctl, textvariable=var, width=96, justify='center', fg_color=PANEL, text_color=TEXT, border_color=RED if f.id in self.invalid else LINE)
                    e.grid(row=0, column=1)
                    e.bind('<Return>', lambda ev, fid=f.id, v_=var: self.set_value(fid, v_.get()))
                    e.bind('<FocusOut>', lambda ev, fid=f.id, v_=var, f_=f, n_=now: (self.set_value(fid, v_.get()) if v_.get().strip() != (('%g' % n_) if f_.kind == 'float' else str(n_)) else None))
                    ctk.CTkButton(ctl, text='+', width=32, fg_color=PANEL, hover_color=LINE, text_color=TEXT, command=lambda fid=f.id: self._arrow(fid, 1)).grid(row=0, column=2, padx=(4, 0))
                    ctk.CTkLabel(ctl, text=f.unit, font=(FONT, 12), text_color=MUTED).grid(row=0, column=3, padx=8)
                    self.rows[f.id] = e
                info = []
                if f.hint:
                    info.append(f.hint)
                if f.kind in ('int', 'float'):
                    info.append('Основа: %g %s · допустимо %g–%g' % (bval, f.unit, f.lo, f.hi))
                elif f.kind == 'bool':
                    info.append('Основа: %s' % ('включено' if bval else 'выключено'))
                else:
                    info.append('Основа: %s' % dict(f.choices).get(bval, bval))
                ctk.CTkLabel(row, text='\n'.join(info), font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=520).grid(row=2, column=0, sticky='w', padx=12, pady=(0, 8))
                if f.id in self.invalid:
                    ctk.CTkLabel(row, text='Не число: «%s». Значение не принято.' % self.invalid[f.id], font=(FONT, 12), text_color=RED).grid(row=3, column=0, sticky='w', padx=12, pady=(0, 8))
                ctk.CTkButton(row, text='↺ к основе', width=100, height=26, fg_color='transparent', border_width=1, border_color=LINE, text_color=MUTED, hover_color=PANEL,
                              state='normal' if changed or f.id in self.invalid else 'disabled', command=lambda fid=f.id: self._reset(fid)).grid(row=1, column=1, sticky='e', padx=12)
                r += 1
            if r == 0:
                ctk.CTkLabel(self.center, text='В этом разделе у выбранной миссии и профиля нет настроек.', font=(FONT, 13), text_color=MUTED).grid(row=0, column=0, padx=20, pady=20)

        def _switch(self, fid):
            sw = self.rows[fid]
            self.set_value(fid, bool(sw.get()))

        def _draw_summary(self):
            self._clear(self.right)
            v = self.variant
            lines, diffs = workshop.summary(v)
            errs, warns = workshop.validate(v)
            r = 0

            def title(t):
                nonlocal r
                ctk.CTkLabel(self.right, text=t, font=(FONT, 11, 'bold'), text_color=MUTED, anchor='w').grid(row=r, column=0, sticky='w', padx=12, pady=(10, 2))
                r += 1

            def text(t, color=TEXT):
                nonlocal r
                ctk.CTkLabel(self.right, text=t, font=(FONT, 12), text_color=color, anchor='w', justify='left', wraplength=290).grid(row=r, column=0, sticky='w', padx=12, pady=1)
                r += 1
            title('ИТОГОВЫЙ СОСТАВ')
            for ln in lines:
                text('•  ' + ln)
            title('ОТЛИЧИЯ ОТ ОСНОВЫ')
            if diffs:
                for d in diffs:
                    text('•  ' + d, ACCENT)
            else:
                text('Нет: вариант совпадает с основой', MUTED)
            cfg = workshop.effective_cfg(v)
            try:
                areas = cfg['tactical']['nuke']['damage']['areas']
                title('ЗОНЫ УРОНА ЯДЕРНОГО УДАРА')
                cv = tkinter.Canvas(self.right, width=290, height=170, bg=CARD, highlightthickness=0)
                cv.grid(row=r, column=0, padx=12, pady=4)
                r += 1
                mx = max(a[0] for a in areas) or 1
                for rad, frac in sorted(areas, key=lambda a: -a[0]):
                    pr = 8 + 76 * rad / mx
                    cv.create_oval(145 - pr, 85 - pr, 145 + pr, 85 + pr, outline=ACCENT, width=2)
                    cv.create_text(145, 85 - pr + 8, text='%g%% до %g' % (frac * 100, rad), fill=TEXT, font=(FONT, 9))
            except KeyError:
                pass
            if self.invalid:
                title('НЕ ПРИНЯТО')
                for fid, t in self.invalid.items():
                    text('•  %s: «%s» не число' % (workshop.BY_ID[fid].label, t), RED)
            if errs:
                title('ОШИБКИ (сборка заблокирована)')
                for e in errs:
                    text('•  ' + e, RED)
            if warns:
                title('ПРЕДУПРЕЖДЕНИЯ')
                for w in warns:
                    text('•  ' + w, AMBER)

        def current_status(self):
            if self.variant is None:
                return 'none'
            if self.busy:
                return 'building'
            if self.invalid:
                return 'invalid'
            return workshop.status(self.variant)

        def _update_buttons(self):
            st = self.current_status()
            names = {'none': 'Нет варианта', 'building': 'Сборка…', 'invalid': 'Исправьте значения', 'draft': 'Нужна сборка (вариант ещё не собирался)', 'needs_build': 'Нужна сборка',
                     'ready': 'Готова к запуску'}
            cols = {'ready': GREEN, 'building': AMBER, 'invalid': RED, 'needs_build': AMBER, 'draft': AMBER}
            base = names.get(st, st)
            self.status_text = base
            if not self.stage_text:
                self.say(base, cols.get(st, MUTED))
            self.run_button.configure(text='Запустить тест' if st == 'ready' else 'Собрать и запустить бесплатный тест',
                                      state='disabled' if st in ('none', 'building', 'invalid') else 'normal')

        # ------------------------------------------------------------------------------------------------------------------------ actions
        def save_variant(self):
            if self.variant is None:
                return
            self._rename()
            workshop.save(self.variant)
            self.say('Вариант сохранён.', GREEN)
            self.stage_text = ''

        def build_and_run(self):
            if self.variant is None or self.busy:
                return
            errs, _ = workshop.validate(self.variant)
            if errs or self.invalid:
                self.say('Сборка заблокирована: ' + '; '.join(errs or ['есть не принятые значения']), RED)
                return
            if self.backend.sc2_running():
                self.say('StarCraft II уже запущена. Закройте игру самостоятельно и повторите: запускатель её не закрывает.', RED)
                return
            self.busy = True
            self.stage_text = 'Сборка…'
            self.say('Сборка…', AMBER)
            self._update_buttons()
            v = self.variant

            def progress(stage):
                self.q.put(('stage', {'check': 'Проверка…', 'build': 'Сборка…', 'verify': 'Проверка сборки…', 'install': 'Установка карты…'}.get(stage, stage)))

            def work():
                try:
                    rc, msg = workshop.prepare(v, progress)
                    if rc != 0:
                        self.q.put(('done', (False, msg)))
                        return
                    rc = self.backend.start(v)
                    self.q.put(('done', (rc == 0, 'Игра запускается: бесплатный тест, ничего не списывается и не зачисляется.' if rc == 0 else 'Не удалось запустить игру (код %s).' % rc)))
                except Exception as e:  # noqa: BLE001 - the window must never stay locked
                    self.q.put(('done', (False, 'Ошибка: %s' % e)))
            threading.Thread(target=work, daemon=True).start()

        def _poll(self):
            try:
                while True:
                    kind, payload = self.q.get_nowait()
                    if kind == 'stage':
                        self.stage_text = payload
                        self.say(payload, AMBER)
                    elif kind == 'done':
                        ok, msg = payload
                        self.busy = False
                        self.stage_text = ''
                        self.variant = workshop.load(self.mission, self.variant['id']) if self.variant else None
                        self.refresh()
                        self.say(msg, GREEN if ok else RED)
            except queue.Empty:
                pass
            if self.winfo_exists():
                self.after(150, self._poll)

    return WorkshopWindow
