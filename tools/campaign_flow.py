"""The campaign flow of the launcher (no GUI code, so it is testable): order -> pay once -> unique map set -> launch -> result proposal -> acceptance.

Contract: docs/MISSION_SETTINGS_AND_CAMPAIGN_ECONOMY.md sections 7 and 14. State: tools/campaign.py (atomic file). Nothing here writes the Owner's
campaign unless the launcher is used for a real campaign run; tests always give their own file (env GHOSTOPS_CAMPAIGN_FILE or the `path` argument).

First sequence (Owner, 2026-10-20): TRaynor02 (no purchases) -> accepted remainder -> TRaynor03 preparation -> launch.
"""
import argparse
import json
import os
import time

import build
import campaign

# missions that take part in the campaign sequence, in the order of the first economy experiment
SEQUENCE = [
    {'mission': 'traynor02', 'preset': 'tactical', 'title': 'Вне закона', 'order': False},
    {'mission': 'traynor03', 'preset': 'standard', 'title': 'Час икс', 'order': True},
]
ORDER_LABELS = {'marines': 'Морпехи гарнизона', 'bunkers': 'Бункеры', 'turrets': 'Ракетные турели', 'scvs': 'КСМ для ремонта'}
PREP_TEXT = 'Закупайтесь сейчас. После высадки новых бойцов нам взять негде. Оставьте достаточно людей для обороны — призракам предстоит работа за периметром.'


def plans_dir():
    return os.path.join(campaign.APP_DIR, 'plans')


def step_of(mission):
    return next((s for s in SEQUENCE if s['mission'] == mission), None)


def _args(mission, preset, plan=None):
    return argparse.Namespace(mission=mission, preset=preset, source=None, multiplier=None, diag=False, print_only=False, start=True, plan=plan)


class BuildCampaignBackend:
    """The real backend: tools/build.py (the same functions the CLI and the launcher use). Tests give the flow a fake."""

    def sc2_running(self):
        return build.sc2_running()

    def prepare(self, args, mode, progress):
        return build.prepare_existing(args, progress) if mode == 'existing' else build.prepare(args, progress)

    def manifest(self, args):
        return build.read_build_manifest(args)

    def start(self, args):
        adapter, cfg, name = build.context(args)
        command, dest = build.launch_command(adapter, cfg, name)
        if not os.path.isfile(dest):
            print('expected installed map is missing: %s' % dest)
            return 8
        return build.start_detached(command)


class CampaignFlow:
    """`backend` needs: sc2_running(), prepare(args, mode, progress) -> rc, manifest(args), start(args) -> rc."""

    def __init__(self, backend, path=None, clock=time.time):
        self.backend = backend
        self.path = path or campaign.campaign_path()
        self.clock = clock
        campaign.load_or_create(self.path)

    # ---- reading ------------------------------------------------------------------------------------------------------------------------
    def state(self):
        return campaign.load(self.path)

    def stock(self):
        return self.state()['stock']

    def open_operation(self, mission):
        """The operation of the mission that is paid / started and not finished (or None)."""
        for op_id, op in self.state()['operations'].items():
            if op['mission'] == mission and op['state'] in ('paid', 'started', 'reported'):
                return op_id, op
        return None

    def accepted_operation(self, mission):
        for op_id, op in self.state()['operations'].items():
            if op['mission'] == mission and op['state'] == 'accepted':
                return op_id, op
        return None

    # ---- orders -------------------------------------------------------------------------------------------------------------------------
    def order_info(self, mission, preset):
        """Limits, prices, the recommended order and its cost, from the resolved configuration (the plan can never change them)."""
        adapter = build.load_adapter(mission)
        cfg, _ = build.resolve_config(adapter, preset)
        z = cfg.get('zerohour')
        if not z:
            return None
        return {'limits': z['limits'], 'prices': z['prices'], 'recommended': z['recommended'], 'default': z['order'], 'items': build.ZH_ORDER_ITEMS,
                'recommended_cost': build.zerohour_cost(cfg, z['recommended']), 'test_budget': z['test_budget']}

    def quote(self, mission, preset, order):
        """Validates an order against the resolved limits and prices and against the campaign stock. Returns
        {'ok', 'errors', 'cost', 'stock', 'short'}; a shortage is SHOWN, never papered over (no credit, no hidden surcharge)."""
        errors = []
        cost = {'minerals': 0, 'gas': 0}
        step = step_of(mission)
        if step and step['order']:
            info = self.order_info(mission, preset)
            if not isinstance(order, dict) or set(order) != set(info['items']):
                errors.append('заказ должен содержать ровно позиции: %s' % ', '.join(info['items']))
            else:
                for k in info['items']:
                    v = order[k]
                    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= info['limits'][k]:
                        errors.append('%s: допустимо 0..%d' % (ORDER_LABELS[k], info['limits'][k]))
                if not errors:
                    adapter = build.load_adapter(mission)
                    cfg, _ = build.resolve_config(adapter, preset)
                    cost = build.zerohour_cost(cfg, order)
        elif order:
            errors.append('у этой миссии нет закупок')
        stock = self.stock()
        short = {k: cost[k] - stock[k] for k in ('minerals', 'gas') if cost[k] > stock[k]}
        return {'ok': not errors and not short, 'errors': errors, 'cost': cost, 'stock': dict(stock), 'short': short}

    # ---- operations ---------------------------------------------------------------------------------------------------------------------
    def _next_operation_id(self):
        s = self.state()
        n = max([int(k[2:]) for k in s['operations'] if k.startswith('OP') and k[2:].isdigit()] or [0]) + 1
        return 'OP%04d' % n

    def _write_plan(self, op_id, mission, preset, order):
        os.makedirs(plans_dir(), exist_ok=True)
        path = os.path.join(plans_dir(), op_id + '.json')
        plan = {'operation_id': op_id, 'mission': mission, 'preset': preset}
        if order is not None:
            plan['order'] = order
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, indent=1, ensure_ascii=False)
        return path

    def start_new(self, mission, preset, order=None, progress=None):
        """A NEW operation (a new order): validate -> pay ONCE -> build the unique set -> start. Returns (ok, message, op_id)."""
        step = step_of(mission)
        if not step:
            return False, 'эта миссия не входит в кампанию', None
        if self.open_operation(mission):
            return False, 'операция этой миссии уже начата: продолжите её или перезапустите', None
        q = self.quote(mission, preset, order if step['order'] else None)
        if not q['ok']:
            if q['short']:
                return False, 'не хватает: %s' % ', '.join('%d %s' % (v, {'minerals': 'минералов', 'gas': 'газа'}[k]) for k, v in q['short'].items()), None
            return False, '; '.join(q['errors']), None
        op_id = self._next_operation_id()
        plan_path = self._write_plan(op_id, mission, preset, order if step['order'] else None)
        try:
            campaign.plan_and_pay(self.path, op_id, mission, preset, q['cost'], {}, None, order=order)
        except campaign.Rejected as e:
            return False, str(e), None
        return self._launch(op_id, mission, preset, plan_path, 'fresh', progress)

    def continue_operation(self, op_id, progress=None):
        """The player continues a saved attempt: the same set is started, intent `continue` (the save is loaded inside the game). No charge."""
        op = self.state()['operations'][op_id]
        return self._launch(op_id, op['mission'], op['profile'], os.path.join(plans_dir(), op_id + '.json'), 'continue', progress)

    def restart_operation(self, op_id, progress=None):
        """A full restart of the same paid operation: the same set, a new attempt, no second payment."""
        op = self.state()['operations'][op_id]
        return self._launch(op_id, op['mission'], op['profile'], os.path.join(plans_dir(), op_id + '.json'), 'fresh', progress)

    def abandon(self, op_id):
        campaign.abandon_operation(self.path, op_id)

    def _launch(self, op_id, mission, preset, plan_path, intent, progress):
        args = _args(mission, preset, plan_path)
        if self.backend.sc2_running():
            return False, 'StarCraft II уже запущена. Закройте игру самостоятельно и повторите: запускатель её не закрывает.', op_id
        # the journal of the PREVIOUS launch is read first: a victory proposal that was not confirmed yet must never be lost with the archived Bank file
        pending = self.after_exit()
        if pending['proposals']:
            return False, 'есть результат карты, ожидающий подтверждения: сначала примите его (окно «Кампания»)', op_id
        rc = self.backend.prepare(args, 'existing', progress)
        if rc != 0:
            return False, 'не удалось подготовить карту операции (код %s); заказ остался оплаченным, повтор не спишет его снова' % rc, op_id
        manifest = self.backend.manifest(args)
        if manifest and manifest.get('data_hash'):
            campaign.set_data_hash(self.path, op_id, manifest['data_hash'])
        campaign.archive_bank()
        campaign.begin_launch(self.path, op_id, intent)
        rc = self.backend.start(args)
        if rc != 0:
            return False, 'не удалось запустить игру (код %s); оплаченный заказ сохранён' % rc, op_id
        return True, 'игра запускается', op_id

    # ---- after the game --------------------------------------------------------------------------------------------------------------------
    def after_exit(self):
        """Call when the game process is gone: reads the fresh journal of the last launch and returns what the player has to decide.
        {'op', 'proposals': [..victory proposals not yet accepted..], 'held': [...]}"""
        s = self.state()
        launch = s.get('launch')
        if not launch:
            return {'op': None, 'proposals': [], 'held': []}
        got = campaign.collect(self.path, launch['op'], launch['at'], launch['intent'])
        op = self.state()['operations'].get(launch['op'])
        props = [p for p in got['proposals'] if p['outcome'] == 'victory' and op and op['state'] != 'accepted' and p['result_id'] not in s['accepted_results']]
        return {'op': launch['op'], 'proposals': props, 'held': got['held'], 'fresh': got['fresh']}

    def accept(self, proposal):
        """The player confirmed THIS proposal: stock change and the accepted mark are one atomic write."""
        s = campaign.accept(self.path, proposal)
        return s['operations'][proposal['op']].get('report')
