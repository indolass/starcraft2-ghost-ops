"""Voice: the explicit build without added voice, the explained error for a missing clip, the clip recipes, the permanent free cloak of TRaynor03."""
import argparse
import json
import os
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')  # tests never read (or mark) the voice lab tables
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402
import prepare_audio  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def ns(mission, preset, no_voice=False):
    return argparse.Namespace(mission=mission, preset=preset, source=None, multiplier=None, diag=False, print_only=False, start=False, plan=None, no_voice=no_voice)


def block(mission, preset, no_voice=False):
    adapter, cfg, name = build.context(ns(mission, preset, no_voice))
    return adapter, cfg, name, build.build_block(adapter, cfg)


class NoVoice(unittest.TestCase):
    CASES = (('traynor01', 'easy'), ('traynor02', 'tactical'), ('traynor03', 'standard'))

    def test_no_voice_build_has_no_clips_and_its_own_file_name(self):
        for mission, preset in self.CASES:
            with self.subTest(mission=mission):
                adapter, cfg, name, text = block(mission, preset, True)
                self.assertTrue(text.isascii())
                self.assertEqual(build.audio_clips(cfg), [])
                self.assertIn('go_cfgNoVoice = true;', text)
                self.assertTrue(build.output_name(adapter, name).endswith('_novoice.SC2Map'), build.output_name(adapter, name))
                self.assertEqual(build.validate_config(cfg), [])
                self.assertNotIn('SoundLink("', text)  # clips are only reached through GhostOps_Voice()
                self.assertFalse(build.sound_fragments(cfg) if hasattr(build, 'sound_fragments') else False)

    def test_normal_build_keeps_the_voice(self):
        for mission, preset in (('traynor01', 'easy'), ('traynor02', 'tactical'), ('traynor03', 'standard')):
            with self.subTest(mission=mission):
                adapter, cfg, name, text = block(mission, preset, False)
                self.assertIn('go_cfgNoVoice = false;', text)
                self.assertTrue(build.audio_clips(cfg))
                self.assertFalse(build.output_name(adapter, name).endswith('_novoice.SC2Map'))

    def test_no_voice_keeps_portraits_texts_and_scene_order_of_traynor03(self):
        _, cfg_v, _, text_v = block('traynor03', 'standard', False)
        _, cfg_n, _, text_n = block('traynor03', 'standard', True)
        self.assertEqual(cfg_v['zerohour']['texts'], cfg_n['zerohour']['texts'])
        self.assertEqual(cfg_v['zerohour']['scene'], cfg_n['zerohour']['scene'])
        self.assertEqual(cfg_v['zerohour']['order'], cfg_n['zerohour']['order'])
        self.assertEqual(cfg_v['tactical'], cfg_n['tactical'])
        # the only difference of the two scripts: the voice flag and the clip ids (empty without voice)
        for i in range(7):
            self.assertIn('go_zhVoiceId[%d] = "";' % i, text_n)
            self.assertNotIn('go_zhVoiceId[%d] = "";' % i, text_v)

    def test_missing_clip_is_not_hidden_and_the_message_explains_what_to_do(self):
        real = build.ROOT
        adapter = build.load_adapter('traynor03')
        cfg = json.load(open(adapter['config'], encoding='utf-8'))
        try:
            build.ROOT = tempfile.mkdtemp()
            errs = build.validate_audio(cfg['audio'])
        finally:
            build.ROOT = real
        self.assertTrue(errs)
        self.assertTrue(all('prepare_audio.py' in e and '--no-voice' in e for e in errs), errs)


class Recipes(unittest.TestCase):
    def test_every_clip_used_by_a_config_has_a_recipe(self):
        recipes = {c['file'] for c in prepare_audio.load_manifest()}
        for mission in ('traynor01', 'traynor02', 'traynor03'):
            adapter = build.load_adapter(mission)
            raw = json.load(open(adapter['config'], encoding='utf-8'))
            texts = json.dumps(raw)
            import re
            for src in re.findall(r'assets/audio/[A-Za-z0-9_]+/[A-Za-z0-9_]+\.wav', texts):
                self.assertIn(src, recipes, src)

    def test_recipes_are_complete_and_never_point_at_a_private_path(self):
        for c in prepare_audio.load_manifest():
            self.assertTrue(c['casc_path'].startswith(('campaigns\\', 'mods\\')), c)
            self.assertNotIn('AI-workspaces', json.dumps(c))
            self.assertTrue(c['text'])


class Traynor03Cloak(unittest.TestCase):
    def test_free_permanent_cloak_with_regeneration_and_a_paid_snipe(self):
        adapter, cfg, name, text = block('traynor03', 'standard')
        op, gt = cfg['operatives'], cfg['ghost_tuning']
        self.assertTrue(op['ghost_permanent_cloak'] and op['ghost_start_cloaked'])
        self.assertEqual((gt['regen_per_second'], gt['cloak_net_per_second'], gt['cloak_activation_cost']), (20, 20, 0))
        self.assertEqual(gt['snipe']['cost'], 10)
        self.assertIn('go_cfgGhostPermanentCloak = true;', text)
        self.assertIn('go_cfgGhostStartCloaked = true;', text)
        frag = build.ghost_tuning_fragments(gt)['BehaviorData.xml']
        self.assertIn('value="0"', frag)  # the cloak modifies the energy regeneration by 0: it costs nothing


if __name__ == '__main__':
    unittest.main()
