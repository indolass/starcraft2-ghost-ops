"""The shared lines table of the voice lab (tools/lines_table.py = unchanged copy, patch of tools/build.py): the build takes the TEXT from the table, nothing else."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import build  # noqa: E402
import lines_table  # noqa: E402

ADAPTER = build.load_adapter('traynor03')
CONFIG_FILE = ADAPTER['config']
RAYNOR = 'presets.defence.overrides.defence.texts.RaynorText'


def table(lines):
    return {'schema': lines_table.SCHEMA, 'mission_id': 'traynor03', 'variant': 'defence', 'languages': ['ru', 'en'], 'speakers': {}, 'scenes': [], 'lines': lines}


def line(lid, ru, en, path, mode='record'):
    return {'id': lid, 'key': 'traynor03/defence/' + lid, 'speaker': 'raynor', 'scene': 'S1', 'order': 1, 'mode': mode, 'text': {'ru': ru, 'en': en},
            'origin_text': {'ru': ru, 'en': en}, 'binding': {'config': 'traynor03.json', 'path': path}}


class SharedLines(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = os.environ.get('GHOSTOPS_LINES_DIR')
        os.environ['GHOSTOPS_LINES_DIR'] = self.dir

    def tearDown(self):
        if self.saved is None:
            os.environ.pop('GHOSTOPS_LINES_DIR', None)
        else:
            os.environ['GHOSTOPS_LINES_DIR'] = self.saved

    def write(self, lines):
        lines_table.write_new_table(lines_table.table_path(self.dir, 'traynor03', 'defence'), table(lines))

    def test_no_table_changes_nothing(self):
        before, _ = build.resolve_config(ADAPTER, 'defence_next')
        self.assertEqual(before['defence']['texts']['RaynorText']['ru'], build.load_json(CONFIG_FILE)['presets']['defence']['overrides']['defence']['texts']['RaynorText']['ru'])

    def test_text_from_the_table_reaches_the_next_build_and_the_config_file_is_not_written(self):
        raw_before = open(CONFIG_FILE, 'rb').read()
        self.write([line('DEF_RAYNOR', 'Новый текст из студии.', 'New text from the studio.', RAYNOR)])
        cfg, _ = build.resolve_config(ADAPTER, 'defence_next')
        self.assertEqual(cfg['defence']['texts']['RaynorText'], {'ru': 'Новый текст из студии.', 'en': 'New text from the studio.'})
        self.assertEqual(build.validate_config(cfg), [])
        self.assertEqual(open(CONFIG_FILE, 'rb').read(), raw_before)  # the config is never written
        text = build.gen_defence(cfg, ADAPTER)  # events, timings and balance numbers are untouched: only the string table differs
        self.assertIn('go_defMattAt', text)

    def test_a_later_edit_in_the_studio_is_taken_by_the_next_build(self):
        self.write([line('DEF_RAYNOR', 'Первый.', 'First.', RAYNOR)])
        self.assertEqual(build.resolve_config(ADAPTER, 'defence_next')[0]['defence']['texts']['RaynorText']['ru'], 'Первый.')
        lines_table.update_text(lines_table.table_path(self.dir, 'traynor03', 'defence'), 'DEF_RAYNOR', 'ru', 'Второй.')
        self.assertEqual(build.resolve_config(ADAPTER, 'defence_next')[0]['defence']['texts']['RaynorText']['ru'], 'Второй.')

    def test_the_build_marks_the_table_as_read(self):
        self.write([line('DEF_RAYNOR', 'Текст.', 'Text.', RAYNOR)])
        build.resolve_config(ADAPTER, 'defence_next')
        with open(lines_table.table_path(self.dir, 'traynor03', 'defence'), encoding='utf-8') as f:
            self.assertIn('game', json.load(f).get('consumers', {}))

    def test_a_line_without_binding_or_native_does_not_block_and_a_wrong_binding_is_an_error(self):
        native = line('ORIGINAL', 'Оригинальная реплика игры.', 'Original line.', RAYNOR, mode='game_native')
        unbound = dict(line('NEWREC', 'Новая запись без привязки.', 'A new recording.', RAYNOR))
        unbound.pop('binding')
        self.write([native, unbound])
        cfg, _ = build.resolve_config(ADAPTER, 'defence_next')  # no recording / no binding: the text scene is not blocked
        self.assertNotEqual(cfg['defence']['texts']['RaynorText']['ru'], 'Оригинальная реплика игры.')
        self.write([line('BAD', 'x', 'x', 'presets.defence.overrides.defence.texts.NoSuchKey')])
        with self.assertRaises(build.ConfigError):
            build.resolve_config(ADAPTER, 'defence_next')

    def test_other_missions_and_traynor02_bindings_are_kept(self):
        # a table of another mission is not applied to this adapter
        lines_table.write_new_table(lines_table.table_path(self.dir, 'traynor02', 'tactical'), dict(table([line('X', 'a', 'b', RAYNOR)]), mission_id='traynor02', variant='tactical'))
        cfg, _ = build.resolve_config(ADAPTER, 'defence_next')
        self.assertNotEqual(cfg['defence']['texts']['RaynorText']['ru'], 'a')
        a2 = build.load_adapter('traynor02')
        self.assertEqual(build.validate_config(build.resolve_config(a2, 'tactical')[0]), [])


if __name__ == '__main__':
    unittest.main()
