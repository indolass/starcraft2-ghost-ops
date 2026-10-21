import argparse
import copy
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build  # noqa: E402
import sc2mpq  # noqa: E402

AD1 = build.load_adapter('traynor01')
AD2 = build.load_adapter('traynor02')
SRC1 = os.path.join(ROOT, 'tmp', 'source', 'TRaynor01.SC2Map')


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class AudioImport(unittest.TestCase):
    def test_clip_files_are_listed_in_sources(self):
        src = text('assets', 'audio', 'SOURCES.md')
        for rel in ('traynor02/adjutant_alert.wav', 'traynor02/swann_B.wav', 'traynor02/ghost_ready00.wav',
                    'traynor01/raynor_A.wav', 'traynor01/marine_B.wav', 'traynor01/marine_A.wav'):
            path = os.path.join(ROOT, 'assets', 'audio', *rel.split('/'))
            self.assertTrue(os.path.isfile(path), rel)
            self.assertIn('`' + rel + '`', src)
            self.assertEqual(build.read(path)[:4], b'RIFF')
        # the first characters of the lab manifest hashes are written in SOURCES.md
        self.assertIn(build.sha256(build.read(os.path.join(ROOT, 'assets', 'audio', 'traynor02', 'adjutant_alert.wav')))[:8], src)
        self.assertIn(build.sha256(build.read(os.path.join(ROOT, 'assets', 'audio', 'traynor01', 'marine_A.wav')))[:8], src)

    def test_validation_rejects_bad_clips(self):
        cfg, _ = build.resolve_config(AD1, 'easy')
        self.assertEqual(build.validate_config(cfg), [])
        for mutate in (
            lambda c: c['audio']['clips'].append(dict(c['audio']['clips'][0])),
            lambda c: c['audio']['clips'][0].update(id='bad id'),
            lambda c: c['audio']['clips'][0].update(source='assets/audio/traynor01/nothing_here.wav'),
            lambda c: c['audio']['clips'][0].update(source='../outside.wav'),
            lambda c: c['audio'].update(clips=[]),
        ):
            bad = copy.deepcopy(cfg)
            mutate(bad)
            self.assertTrue(build.validate_config(bad))

    def test_catalog_entry_and_member_name(self):
        cfg, _ = build.resolve_config(AD1, 'easy')
        frag = build.catalog_fragments(cfg)['SoundData.xml']
        # 3 voice clips + 4 silent talk drivers (they only drive the mouth of a portrait; they are no voice)
        self.assertEqual(len(re.findall(r'<CSound id="GhostOps\w+" parent="SM_Old">', frag)), 7)
        self.assertEqual(frag.count('FacialAnim="'), 7)  # every clip carries the lip-sync animation of an original line
        self.assertIn('File="Assets' + chr(92) + 'Sounds' + chr(92) + 'GhostOps' + chr(92) + 'raynor_A.wav"', frag)
        self.assertEqual(build.patch_unitdata(build.NEW_CATALOG, frag).count('<CSound'), 7)
        # only the playable variant carries the clips: the old TRaynor02 prototype stays silent
        proto, _ = build.resolve_config(AD2, 'prototype')
        self.assertNotIn('SoundData.xml', build.catalog_fragments(proto))
        tac, _ = build.resolve_config(AD2, 'tactical')
        self.assertIn('GhostOpsAdjutantAlert', build.catalog_fragments(tac)['SoundData.xml'])
        # new story texts carry NO old clip that speaks other words: only the two lines whose clip says exactly the line keep one
        self.assertEqual(sorted(l['clip'] for l in tac['tactical']['lines'] if l.get('clip')), ['GhostOpsAdjutantAlert', 'GhostOpsGhostReady'])

    @unittest.skipUnless(os.path.isfile(SRC1), 'source map not extracted')
    def test_built_map_holds_the_clips(self):
        ns = argparse.Namespace(mission='traynor01', preset='easy', diag=False, multiplier=None, source=None)
        self.assertEqual(build.cmd_build(ns), 0)
        man = json.loads(build.read(build.build_manifest_path('traynor01_easy'), 'r'))
        self.assertEqual(len(man['audio']), 7)  # 3 voice clips + 4 silent talk drivers
        arc = sc2mpq.Archive(build.read(os.path.join(ROOT, 'dist', 'GhostOps_TRaynor01_r2_easy.SC2Map')))
        for a in man['audio']:
            self.assertEqual(build.sha256(arc.read(a['member'])), a['sha256'])


class WoundedSquadScene(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = build.resolve_config(AD1, 'easy')
        self.ad = text('adapters', 'traynor01', 'adapter.galaxy')

    def test_config_values(self):
        s = self.cfg['scene']
        self.assertEqual(build.validate_config(self.cfg), [])
        self.assertEqual(s['pause'], 0.5)
        self.assertEqual(s['texts']['RaynorLine']['ru'], 'Войска готовы к бою?')
        self.assertEqual(s['texts']['MarineBLine']['ru'], 'Высылайте подмогу!')
        self.assertEqual(s['texts']['MarineALine']['ru'], 'Доктора! Доктора!')
        self.assertEqual(s['texts']['Explain']['ru'], 'Отряд серьёзно пострадал при высадке. Морпехи ещё могут сражаться, но любое ранение станет последним.')
        for k in ('raynor_seconds', 'marine_b_seconds', 'marine_a_seconds'):
            self.assertGreaterEqual(s[k], 2.5)  # readable even when the clip is a second long
        bad = copy.deepcopy(self.cfg)
        bad['scene']['marine_a_clip'] = 'GhostOpsNothing'
        self.assertTrue(build.validate_config(bad))

    def test_balance_and_profiles_are_untouched(self):
        for name, squad in (('easy', 2), ('hard', 2), ('extreme', 1)):
            cfg, _ = build.resolve_config(AD1, name)
            self.assertEqual(len(cfg['operatives']['squad']), squad)
            self.assertTrue(cfg['scene']['enabled'])
            self.assertEqual(build.validate_config(cfg), [])
        self.assertEqual(self.cfg['ghost_tuning']['snipe']['cooldown'], 0)

    def test_order_pause_and_once(self):
        a = self.ad
        body = a.split('bool GhostOps_T1_SceneMsg')[1].split('// Called from the hook')[0]
        order = [body.index(x) for x in ('go_sceneRaynorClip, ', 'go_sceneMarineBClip, ', 'go_sceneMarineAClip, ')]
        self.assertEqual(order, sorted(order))
        self.assertEqual(body.count('Wait(go_scenePause, c_timeReal);'), 2)
        self.assertEqual(body.count('GhostOps_ClipStepLink('), 3)  # the three clips; every step waits for its transmission: nothing overlaps
        self.assertEqual(body.count('GhostOps_Talk('), 1)  # Raynor's closing words: the portrait talks (silent lip-sync drivers)
        self.assertEqual(body.count('TriggerQueueEnter();'), body.count('TriggerQueueExit();'))
        self.assertIn('RaynorMarinePortrait', body)
        self.assertEqual(body.count('"MarinePortrait"'), 2)  # the portrait whose lip-sync animations hold the marine lines (Marine_Help00)
        hook = a.split('void GhostOps_T1_OnOpeningLine')[1].split('void GhostOps_OnMissionStart')[0]
        self.assertLess(hook.index('go_sceneDone) {'), hook.index('go_sceneDone = true;'))
        self.assertEqual(a.count('TriggerCreate("GhostOps_T1_SceneMsg")'), 1)
        for forbidden in ('CameraPan(1, ', 'CinematicMode', 'CameraLock', 'UnitSelect'):
            self.assertNotIn(forbidden, body + hook)

    def test_hook_is_in_the_standard_opening_line_only(self):
        hooks = [h for h in build.hook_list(AD1) if h['function'] == 'gt_OpeningLineQ_Func']
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]['call'], 'GhostOps_T1_OnOpeningLine(gv_raynor);')

    def test_block_is_ascii_and_texts_exist(self):
        for preset in ('easy', 'hard', 'extreme', 'easy_dev'):
            cfg, _ = build.resolve_config(AD1, preset)
            block = build.build_block(AD1, cfg)
            self.assertTrue(block.isascii(), preset)
            used = set(re.findall(r'Param/Value/GhostOpsScene_(\w+)', block))
            self.assertTrue(used <= set(build.SCENE_TEXT_KEYS), used)
            ent = dict(build.text_entries(cfg)['ruRU'])
            for k in used:
                self.assertIn(build.SCENE_TEXT_PREFIX + k, ent)
        dev, _ = build.resolve_config(AD1, 'easy_dev')
        self.assertTrue(dev['scene']['debug_log'])
        self.assertFalse(self.cfg['scene']['debug_log'])


if __name__ == '__main__':
    unittest.main()
