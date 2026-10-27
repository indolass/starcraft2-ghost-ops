"""Campaign window of the Ghost Ops launcher (CustomTkinter). The logic is tools/campaign_flow.py; this file only draws it.

Window: the campaign stock, step 1 "Вне закона" (start / continue / restart / refuse, the result of the map as a PROPOSAL to confirm), step 2 "Час икс"
(the order form with prices, limits, total and shortage; pay once and start). Nothing here closes or moves a running game.
"""
import os
import queue
import threading

import campaign
import campaign_flow as cf

RES_NAMES = {'minerals': 'минералов', 'gas': 'газа'}
VARIANT_TEXT = {
    'defence_r6': '«Оборона и диверсии», версия 6 — ТЕКУЩАЯ, экспериментальная (версия 5 + сворачивание и повторная установка бункеров и турелей [Z]: комплект возвращается, деньги нет; остальное как в версии 5)',
    'defence_r5': '«Оборона и диверсии», версия 5 — прежняя (одна ядерная ракета на отряд, гарнизон ×0,85, повстанцы ×1,2, завод на гейзере, заключительный натиск, ранний анализ детекторов)',
    'defence_r4': '«Оборона и диверсии», версия 4 — прежняя (две ядерные ракеты, ядерный удар без подхода к цели; для новой операции не рекомендуется)',
    'defence_r3': '«Оборона и диверсии», версия 3 — прежняя (ядерное наведение подводило призрака к цели; для новой операции не рекомендуется)',
    'defence_next': '«Оборона и диверсии», версия 2 — прежняя (усиленный гарнизон ×8, залп турелей по области; для новой операции не рекомендуется)',
    'defence': '«Оборона и диверсии», версия 1 — прежняя (карта, которую вы проходили раньше; без залпа по области)',
    'standard': 'прежний «Час икс» (заказ готов к старту)'}
PROFILE_TEXT = {'tactical_next': 'Вне закона, версия 2', 'tactical': 'Вне закона, версия 1', 'defence_r6': 'Оборона и диверсии, версия 6', 'defence_r5': 'Оборона и диверсии, версия 5 (прежняя)', 'defence_r4': 'Оборона и диверсии, версия 4 (прежняя)', 'defence_r3': 'Оборона и диверсии, версия 3 (прежняя)', 'defence_next': 'Оборона и диверсии, версия 2 (прежняя)',
                'defence': 'Оборона и диверсии, версия 1 (прежняя)', 'standard': 'Час икс (прежний)', 'sniper_next_r6': 'Эвакуация, ревизия 6', 'sniper_next_r5': 'Эвакуация, ревизия 5 (прежняя)', 'sniper_next_r4': 'Эвакуация, ревизия 4 (прежняя)', 'sniper_next_r3': 'Эвакуация, ревизия 3 (прежняя)', 'sniper_next_r2': 'Эвакуация, ревизия 2 (прежняя)'}


def stock_text(stock):
    return 'Запас кампании: %d минералов, %d газа' % (stock['minerals'], stock['gas'])


def op_status(op):
    return {'paid': 'оплачена, карта ещё не запускалась', 'started': 'идёт (попытка запущена)', 'reported': 'завершена без победы, можно продолжить сохранение или перезапустить',
            'accepted': 'завершена, результат принят', 'abandoned': 'отменена игроком'}.get(op['state'], op['state'])


def make_window_class(ctk, pal):
    BG, PANEL, CARD, LINE, ACCENT, ACCENT_HOVER, TEXT, MUTED, AMBER, RED, GREEN, FONT = [pal[k] for k in (
        'BG', 'PANEL', 'CARD', 'LINE', 'ACCENT', 'ACCENT_HOVER', 'TEXT', 'MUTED', 'AMBER', 'RED', 'GREEN', 'FONT')]

    class CampaignWindow(ctk.CTkToplevel):
        def __init__(self, app, flow=None):
            super().__init__(app, fg_color=BG)
            self.app = app
            self.flow = flow or cf.CampaignFlow(cf.BuildCampaignBackend())
            self.title('Кампания — Вне закона → Час икс → Эвакуация')
            self.geometry('820x800')
            self.minsize(700, 640)
            self.transient(app)
            self.q = queue.Queue()
            self.busy = False
            self.watching = False
            self.pending = []
            self.t3 = cf.step_of('traynor03')['preset']  # the variant of the second step: 'defence_r5' (current), 'defence_r4', 'defence_r3' and 'defence_next' (earlier), 'defence' (version 1, the Owner's earlier map) or 'standard' (the previous Zero Hour)
            self.show_details = False
            self.order = dict(self.flow.order_info('traynor03', self.t3)['recommended'])
            self.e_preset = cf.step_of('thanson01')['preset']  # the third step: Evacuation, revision 2 (turret kits)
            self.order3 = dict(self.flow.order_info('thanson01', self.e_preset)['recommended'])
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(0, weight=1)
            self.body = ctk.CTkScrollableFrame(self, fg_color='transparent')
            self.body.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
            self.body.grid_columnconfigure(0, weight=1)
            self.msg = ctk.CTkLabel(self, text='', font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=760)
            self.msg.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 10))
            self.refresh()
            self._check_after_exit()
            self.after(1500, self._tick)

        # ---------------------------------------------------------------- helpers
        def say(self, text, color=MUTED):
            self.msg.configure(text=text, text_color=color)

        def card(self, row, title):
            f = ctk.CTkFrame(self.body, fg_color=PANEL, corner_radius=12, border_width=1, border_color=LINE)
            f.grid(row=row, column=0, sticky='ew', padx=6, pady=8)
            f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(f, text=title, font=(FONT, 18, 'bold'), text_color=TEXT, anchor='w').grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 2))
            return f

        def button(self, parent, text, cmd, primary=False, state='normal', width=200):
            return ctk.CTkButton(parent, text=text, command=cmd, width=width, height=36, font=(FONT, 13, 'bold' if primary else 'normal'), state=state,
                                 fg_color=ACCENT if primary else 'transparent', hover_color=ACCENT_HOVER if primary else CARD,
                                 border_width=0 if primary else 1, border_color=LINE, text_color='#ffffff' if primary else TEXT)

        # ---------------------------------------------------------------- drawing
        def refresh(self):
            for w in self.body.winfo_children():
                w.destroy()
            st = self.flow.state()
            ctk.CTkLabel(self.body, text=stock_text(st['stock']), font=(FONT, 16, 'bold'), text_color=GREEN, anchor='w').grid(row=0, column=0, sticky='ew', padx=14, pady=(4, 0))
            ctk.CTkLabel(self.body, text='Запас кампании меняют только подтверждённый результат карты и оплата заказа. Закрытие игры не отменяет операцию: сохраните, закройте и продолжите позже.',
                         font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=1, column=0, sticky='ew', padx=14, pady=(0, 6))
            self._draw_pending(2)
            self._draw_standalone(5)
            self._draw_step1(3)
            self._draw_step2(4)
            self._draw_step3(6)

        def _draw_pending(self, row):
            if not self.pending:
                return
            f = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=12, border_width=2, border_color=AMBER)
            f.grid(row=row, column=0, sticky='ew', padx=6, pady=8)
            f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(f, text='Карта предложила результат — подтвердите его', font=(FONT, 16, 'bold'), text_color=AMBER, anchor='w').grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 2))
            for i, p in enumerate(self.pending):
                lines = campaign.report_lines(campaign.report(p))
                ctk.CTkLabel(f, text='Победа (попытка %s, %s с игрового времени)' % (p['attempt'], p['mission_time'].split('.')[0]), font=(FONT, 13, 'bold'), text_color=TEXT,
                             anchor='w').grid(row=1 + i * 4, column=0, sticky='ew', padx=16, pady=(8, 0))
                ctk.CTkLabel(f, text='\n'.join(lines), font=(FONT, 12), text_color=TEXT, anchor='w', justify='left', wraplength=730).grid(row=2 + i * 4, column=0, sticky='ew', padx=16)
                self.button(f, 'Принять этот результат', lambda pp=p: self.accept(pp), primary=True).grid(row=3 + i * 4, column=0, sticky='w', padx=16, pady=(6, 4))
            ctk.CTkLabel(f, text='Остаток в кампанию попадает один раз. Пока результат не принят, новые запуски операций недоступны (журнал карты не теряется).',
                         font=(FONT, 11), text_color=MUTED, anchor='w', justify='left', wraplength=730).grid(row=2 + len(self.pending) * 4, column=0, sticky='ew', padx=16, pady=(0, 10))

        def _draw_standalone(self, row):
            """The result of a run that was started from the launcher card (outside the campaign): found / already counted / not connected / not found + the reason."""
            info = self.flow.standalone_status('traynor02')
            color = {'found': AMBER, 'accepted': GREEN, 'not_connected': MUTED, 'not_found': MUTED}[info['state']]
            f = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=12, border_width=2 if info['state'] == 'found' else 1, border_color=AMBER if info['state'] == 'found' else LINE)
            f.grid(row=row, column=0, sticky='ew', padx=6, pady=8)
            f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(f, text='Самостоятельное прохождение «Вне закона» (запуск с карточки, вне кампании)', font=(FONT, 15, 'bold'), text_color=TEXT, anchor='w').grid(
                row=0, column=0, sticky='ew', padx=16, pady=(10, 2))
            ctk.CTkLabel(f, text=info['text'], font=(FONT, 13, 'bold'), text_color=color, anchor='w', justify='left', wraplength=740).grid(row=1, column=0, sticky='ew', padx=16)
            r = 2
            for p in info['results']:
                rep = campaign.report(p)
                src = 'Источник: ваше прохождение «%s», запущенное с карточки запускателя (не из окна кампании); карта записала результат в конце миссии, игровое время %s с.' % (
                    PROFILE_TEXT.get(p.get('profile'), 'профиль не определён'), p['mission_time'].split('.')[0])
                tech = 'Технические данные: файл %s (Documents\\StarCraft II\\Banks), результат %s, операция журнала %s, профиль %s, хэш данных %s.' % (
                    os.path.basename(p['source']), p['result_id'], p['op'], p.get('profile') or 'не определён', p.get('data_hash'))
                ctk.CTkLabel(f, text='Победа. В запас кампании будет зачислено ровно: %d минералов, %d газа.' % (p['minerals'], p['gas']), font=(FONT, 14, 'bold'), text_color=TEXT,
                             anchor='w').grid(row=r, column=0, sticky='ew', padx=16, pady=(6, 0))
                ctk.CTkLabel(f, text='\n'.join(campaign.report_lines(rep)) + '\n' + src + (('\n' + tech) if self.show_details else ''), font=(FONT, 11), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(
                    row=r + 1, column=0, sticky='ew', padx=16)
                self.button(f, 'Скрыть подробности' if self.show_details else 'Подробнее', self.toggle_details, width=140).grid(row=r + 2, column=0, sticky='e', padx=16)
                if info['state'] == 'found':
                    self.button(f, 'Зачислить в кампанию (один раз)', lambda pp=p: self.adopt(pp), primary=True, state='disabled' if info['blocked'] else 'normal', width=260).grid(
                        row=r + 2, column=0, sticky='w', padx=16, pady=(6, 4))
                r += 3
            ctk.CTkLabel(f, text='Самостоятельный запуск карты с карточки в кампанию не записывается сам: остаток попадает в запас только после вашего подтверждения здесь или как результат операции кампании.',
                         font=(FONT, 11), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=r, column=0, sticky='ew', padx=16, pady=(0, 10))

        def toggle_details(self):
            self.show_details = not self.show_details
            self.refresh()

        def adopt(self, proposal):
            try:
                self.flow.adopt_standalone(proposal)
            except campaign.Rejected as e:
                self.say('Результат не зачислен: %s' % e, RED)
                self.refresh()
                return
            self.say('Результат зачислен: %d минералов и %d газа добавлены в запас кампании одной записью.' % (proposal['minerals'], proposal['gas']), GREEN)
            self.refresh()

        def _op_buttons(self, f, row, mission, preset):
            opn = self.flow.open_operation(mission)
            bar = ctk.CTkFrame(f, fg_color='transparent')
            bar.grid(row=row, column=0, sticky='w', padx=12, pady=(4, 12))
            if opn:
                op_id, op = opn
                self.button(bar, 'Продолжить сохранение', lambda: self.run_async(lambda: self.flow.continue_operation(op_id)), primary=True).grid(row=0, column=0, padx=4)
                self.button(bar, 'Перезапустить (бесплатно)', lambda: self.run_async(lambda: self.flow.restart_operation(op_id))).grid(row=0, column=1, padx=4)
                self.button(bar, 'Отказаться от операции', lambda: self.refuse(op_id), width=190).grid(row=0, column=2, padx=4)
                return op_id, op
            return None, None

        def _draw_step1(self, row):
            f = self.card(row, '1. «Вне закона» — без закупок')
            acc = self.flow.accepted_operation('traynor02')
            opn = self.flow.open_operation('traynor02')
            text = 'Не начата. Текущий боевой вариант миссии; в конце остаток минералов и газа может перейти в кампанию.'
            if opn:
                text = 'Операция %s: %s.' % (opn[0], op_status(opn[1]))
            elif acc:
                text = 'Операция %s: %s.' % (acc[0], op_status(acc[1]))
            ctk.CTkLabel(f, text=text, font=(FONT, 13), text_color=TEXT, anchor='w', justify='left', wraplength=740).grid(row=1, column=0, sticky='ew', padx=16, pady=(2, 4))
            if acc and acc[1].get('report'):
                ctk.CTkLabel(f, text='\n'.join(campaign.report_lines(acc[1]['report'])), font=(FONT, 12), text_color=MUTED, anchor='w', justify='left',
                             wraplength=740).grid(row=2, column=0, sticky='ew', padx=16, pady=(0, 4))
            if not self._op_buttons(f, 3, 'traynor02', cf.step_of('traynor02')['preset'])[0]:
                if not acc:
                    self.button(f, 'Начать «Вне закона»', lambda: self.run_async(lambda: self.flow.start_new('traynor02', cf.step_of('traynor02')['preset'])), primary=True).grid(row=3, column=0, sticky='w', padx=16, pady=(4, 12))
                else:
                    ctk.CTkLabel(f, text='Операция завершена. Повтор принятой операции доход не даёт (правила практики и отката ещё не определены).', font=(FONT, 11), text_color=MUTED,
                                 anchor='w', justify='left', wraplength=740).grid(row=3, column=0, sticky='ew', padx=16, pady=(0, 12))

        def _draw_step2(self, row):
            f = self.card(row, '2. «Час икс» — подготовка заказа')
            info = self.flow.order_info('traynor03', self.t3)
            opn = self.flow.open_operation('traynor03')
            ctk.CTkLabel(f, text=('Вариант: %s. ' % (VARIANT_TEXT[self.t3])) + 'Рейнор: «%s»' % cf.PREP_TEXT, font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 6))
            if opn:
                ctk.CTkLabel(f, text='Операция %s: %s. Заказ зафиксирован и оплачен. Карта операции: %s (она и продолжится; новая версия на неё не подменяется).' % (opn[0], op_status(opn[1]), PROFILE_TEXT.get(opn[1].get('profile'), opn[1].get('profile'))),
                             font=(FONT, 13), text_color=TEXT, anchor='w', wraplength=740).grid(row=2, column=0, sticky='ew', padx=16, pady=(2, 4))
                self._op_buttons(f, 3, 'traynor03', self.t3)
                return
            vb = ctk.CTkFrame(f, fg_color='transparent')
            vb.grid(row=6, column=0, sticky='w', padx=12, pady=(0, 10))
            self.button(vb, 'Версия 6 (текущая)', lambda: self.set_variant('defence_r6'), primary=(self.t3 == 'defence_r6'), width=170).grid(row=0, column=0, padx=4)
            self.button(vb, 'Версия 5 (прежняя)', lambda: self.set_variant('defence_r5'), primary=(self.t3 == 'defence_r5'), width=150).grid(row=0, column=1, padx=4)
            self.button(vb, 'Версия 4 (прежняя)', lambda: self.set_variant('defence_r4'), primary=(self.t3 == 'defence_r4'), width=150).grid(row=0, column=2, padx=4)
            self.button(vb, 'Версия 3 (прежняя)', lambda: self.set_variant('defence_r3'), primary=(self.t3 == 'defence_r3'), width=150).grid(row=1, column=0, padx=4, pady=3)
            self.button(vb, 'Версия 2 (прежняя)', lambda: self.set_variant('defence_next'), primary=(self.t3 == 'defence_next'), width=150).grid(row=1, column=1, padx=4, pady=3)
            self.button(vb, 'Версия 1 (прежняя)', lambda: self.set_variant('defence'), primary=(self.t3 == 'defence'), width=150).grid(row=1, column=2, padx=4, pady=3)
            self.button(vb, 'Прежний «Час икс»', lambda: self.set_variant('standard'), primary=(self.t3 == 'standard'), width=150).grid(row=2, column=0, padx=4, pady=3)
            grid = ctk.CTkFrame(f, fg_color='transparent')
            grid.grid(row=2, column=0, sticky='ew', padx=16)
            grid.grid_columnconfigure(0, weight=1)
            for i, k in enumerate(info['items']):
                pr = info['prices'][k]
                price = '%d мин.' % pr['minerals'] + (' + %d газа' % pr['gas'] if pr['gas'] else '')
                ctk.CTkLabel(grid, text='%s (по %s, %sне более %d)' % (cf.ORDER_LABELS[k], price, ('не менее %d, ' % info['min'][k]) if info['min'].get(k) else '', info['limits'][k]), font=(FONT, 13), text_color=TEXT,
                             anchor='w').grid(row=i, column=0, sticky='ew', pady=3)
                self.button(grid, '−', lambda kk=k: self.change(kk, -1), width=36).grid(row=i, column=1, padx=4)
                ctk.CTkLabel(grid, text=str(self.order[k]), font=(FONT, 15, 'bold'), text_color=TEXT, width=36).grid(row=i, column=2)
                self.button(grid, '+', lambda kk=k: self.change(kk, 1), width=36).grid(row=i, column=3, padx=4)
            q = self.flow.quote('traynor03', self.t3, self.order)
            cost = q['cost']
            short = q['short']
            line = 'Стоимость заказа: %d минералов, %d газа. В запасе: %d / %d.' % (cost['minerals'], cost['gas'], q['stock']['minerals'], q['stock']['gas'])
            if short:
                line += '  НЕ ХВАТАЕТ: ' + ', '.join('%d %s' % (v, RES_NAMES[kk]) for kk, v in short.items()) + '. Доплат, кредита и автоматической выдачи нет.'
            ctk.CTkLabel(f, text=line, font=(FONT, 13, 'bold'), text_color=RED if short else GREEN, anchor='w', justify='left', wraplength=740).grid(row=3, column=0, sticky='ew', padx=16, pady=(8, 2))
            ctk.CTkLabel(f, text='Два призрака с постоянной маскировкой и две ядерные ракеты входят в операцию без закупки (заменить их нельзя). Цены и пределы — экспериментальные настройки '
                                 'config/traynor03.json, не утверждены Owner. Стоимость подготовки отдельно не взимается: оплачивается только выбранный заказ, один раз.',
                         font=(FONT, 11), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=4, column=0, sticky='ew', padx=16)
            bar = ctk.CTkFrame(f, fg_color='transparent')
            bar.grid(row=5, column=0, sticky='w', padx=12, pady=(6, 12))
            self.button(bar, 'Рекомендуемый заказ', self.use_recommended).grid(row=0, column=0, padx=4)
            self.button(bar, 'Оплатить и начать', lambda: self.run_async(lambda: self.flow.start_new('traynor03', self.t3, dict(self.order))), primary=True,
                        state='normal' if q['ok'] and not self.busy else 'disabled').grid(row=0, column=1, padx=4)

        def _draw_step3(self, row):
            """3. Evacuation (THanson01, revision 3): the pre-order of turret kits and extra SCVs. There are no ready turrets on the map: the player builds the ordered number himself."""
            f = self.card(row, '3. «Эвакуация» (ревизия 5) — комплекты турелей и дополнительные КСМ')
            info = self.flow.order_info('thanson01', self.e_preset)
            opn = self.flow.open_operation('thanson01')
            if opn:
                ctk.CTkLabel(f, text='Операция %s: %s. Заказ зафиксирован и оплачен. Карта операции: %s (она и продолжится).' % (opn[0], op_status(opn[1]), PROFILE_TEXT.get(opn[1].get('profile'), opn[1].get('profile'))),
                             font=(FONT, 13), text_color=TEXT, anchor='w', wraplength=740).grid(row=2, column=0, sticky='ew', padx=16, pady=(2, 4))
                self._op_buttons(f, 3, 'thanson01', self.e_preset)
                return
            ctk.CTkLabel(f, text='Готовых турелей на карте нет. Закажите комплекты ракетных турелей: на карте СКВ строят ровно столько турелей бесплатно, место выбираете вы. '
                                 'Отмена стройки возвращает комплект, достройка тратит, гибель достроенной не возвращает, гибель недостроенной сжигает комплект. '
                                 'Неиспользованные комплекты деньгами не возвращаются и в следующий заказ не переходят; при победе в запас можно зачислить остаток минералов и газа на карте (один раз).',
                         font=(FONT, 12), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 4))
            grid = ctk.CTkFrame(f, fg_color='transparent')
            grid.grid(row=2, column=0, sticky='ew', padx=16)
            grid.grid_columnconfigure(0, weight=1)
            for r, k in enumerate(info['items']):
                pr = info['prices'][k]
                price = '%d мин.' % pr['minerals'] + (' + %d газа' % pr['gas'] if pr['gas'] else '')
                if k == 'scvs':
                    sv = info['scv']
                    label = 'Дополнительные КСМ (по %s, не более %d; штатных %d; рекомендуется всего %d, то есть %d дополнительных). Всего будет: %d' % (
                        price, info['limits'][k], sv['stock'], sv['recommended_total'], info['recommended'][k], sv['stock'] + self.order3.get(k, 0))
                else:
                    label = '%s (по %s, не более %d; рекомендуется %d)' % (cf.ORDER_LABELS[k], price, info['limits'][k], info['recommended'][k])
                ctk.CTkLabel(grid, text=label, font=(FONT, 13), text_color=TEXT, anchor='w', wraplength=520, justify='left').grid(row=r, column=0, sticky='ew', pady=3)
                self.button(grid, '−', lambda kk=k: self.change3(-1, kk), width=36).grid(row=r, column=1, padx=4)
                ctk.CTkLabel(grid, text=str(self.order3.get(k, 0)), font=(FONT, 15, 'bold'), text_color=TEXT, width=36).grid(row=r, column=2)
                self.button(grid, '+', lambda kk=k: self.change3(1, kk), width=36).grid(row=r, column=3, padx=4)
            ctk.CTkLabel(f, text=info['hint'], font=(FONT, 12, 'bold'), text_color=AMBER, anchor='w', justify='left', wraplength=740).grid(row=3, column=0, sticky='ew', padx=16, pady=(6, 2))
            q = self.flow.quote('thanson01', self.e_preset, self.order3)
            cost, short = q['cost'], q['short']
            prep = info['preparation']
            line = 'Стоимость: %d минералов, %d газа (комплекты + подготовка %d / %d). В запасе: %d / %d.' % (cost['minerals'], cost['gas'], prep['minerals'], prep['gas'], q['stock']['minerals'], q['stock']['gas'])
            if short:
                line += '  НЕ ХВАТАЕТ: ' + ', '.join('%d %s' % (v, RES_NAMES[kk]) for kk, v in short.items()) + '. Доплат, кредита и автоматической выдачи нет.'
            ctk.CTkLabel(f, text=line, font=(FONT, 13, 'bold'), text_color=RED if short else GREEN, anchor='w', justify='left', wraplength=740).grid(row=4, column=0, sticky='ew', padx=16, pady=(4, 2))
            ctk.CTkLabel(f, text='Цена комплекта и число комплектов экспериментальные, не утверждены Owner (config/thanson01.json, hanson.turret_kits); подготовка 1000 / 500 — ранее согласованная сумма. '
                                 'При победе предлагается зачислить остаток минералов и газа на карте (один раз); неиспользованные комплекты и КСМ деньгами не возвращаются.',
                         font=(FONT, 11), text_color=MUTED, anchor='w', justify='left', wraplength=740).grid(row=5, column=0, sticky='ew', padx=16)
            bar = ctk.CTkFrame(f, fg_color='transparent')
            bar.grid(row=6, column=0, sticky='w', padx=12, pady=(6, 12))
            self.button(bar, 'Рекомендуемый заказ', self.use_recommended3).grid(row=0, column=0, padx=4)
            self.button(bar, 'Оплатить и начать', lambda: self.run_async(lambda: self.flow.start_new('thanson01', self.e_preset, dict(self.order3))), primary=True,
                        state='normal' if q['ok'] and not self.busy else 'disabled').grid(row=0, column=1, padx=4)

        # ---------------------------------------------------------------- actions
        def change3(self, delta, key='turret_kits'):
            info = self.flow.order_info('thanson01', self.e_preset)
            self.order3[key] = max(0, min(info['limits'][key], self.order3.get(key, 0) + delta))
            self.refresh()

        def use_recommended3(self):
            self.order3 = dict(self.flow.order_info('thanson01', self.e_preset)['recommended'])
            self.refresh()

        def change(self, key, delta):
            info = self.flow.order_info('traynor03', self.t3)
            self.order[key] = max(info['min'].get(key, 0), min(info['limits'][key], self.order[key] + delta))
            self.refresh()

        def set_variant(self, name):
            self.t3 = name
            self.order = dict(self.flow.order_info('traynor03', name)['recommended'])
            self.refresh()

        def use_recommended(self):
            self.order = dict(self.flow.order_info('traynor03', self.t3)['recommended'])
            self.refresh()

        def refuse(self, op_id):
            self.flow.abandon(op_id)
            self.say('Операция %s отменена игроком. Возврат стоимости — открытый вопрос, сейчас ничего не возвращается.' % op_id, AMBER)
            self.refresh()

        def run_async(self, fn):
            if self.busy:
                return
            self.busy = True
            self.say('Подготовка карты и запуск игры…', TEXT)

            def work():
                try:
                    self.q.put(('done', fn()))
                except Exception as e:  # noqa: BLE001 - the window must never stay locked
                    self.q.put(('done', (False, 'ошибка: %s' % e, None)))
            threading.Thread(target=work, daemon=True).start()

        def accept(self, proposal):
            try:
                self.flow.accept(proposal)
            except campaign.Rejected as e:
                self.say('Результат не принят: %s' % e, RED)
                self.pending = []
                self.refresh()
                return
            self.pending = []
            self.say('Результат принят: остаток добавлен в запас кампании одной записью.', GREEN)
            self.refresh()

        def _check_after_exit(self):
            if self.flow.backend.sc2_running():
                return
            got = self.flow.after_exit()
            self.pending = got['proposals']
            if got['op'] and not got['proposals'] and got.get('fresh') and not self.watching:
                pass
            if self.pending:
                self.refresh()

        def _tick(self):
            try:
                while True:
                    kind, value = self.q.get_nowait()
                    if kind == 'done':
                        ok, message, op_id = value
                        self.busy = False
                        self.watching = ok
                        self.say(('✓ ' if ok else '') + message + ('' if ok else ' Оплаченный заказ сохранён.'), GREEN if ok else RED)
                        self.refresh()
            except queue.Empty:
                pass
            if self.watching and not self.flow.backend.sc2_running():
                self.watching = False
                self._check_after_exit()
                if not self.pending:
                    self.say('Игра закрыта. Победного результата карты нет: операция остаётся открытой, можно продолжить сохранение.', MUTED)
                self.refresh()
            self.after(1500, self._tick)

    return CampaignWindow
