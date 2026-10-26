"""Launcher card status: ready / needs a build, from a fast hash check; never raises."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import launcher_core as core  # noqa: E402


class Fake:
    def __init__(self, v):
        self.v = v

    def status(self, mission, preset, game_dir=None):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class Status(unittest.TestCase):
    def test_texts(self):
        self.assertEqual(core.map_status_text(Fake('ready'), 'm', 'p'), 'Готова к запуску')
        self.assertTrue(core.map_status_text(Fake('needs_build'), 'm', 'p').startswith('Нужна сборка'))

    def test_an_unreadable_state_is_not_shown_and_does_not_raise(self):
        self.assertEqual(core.map_status_text(Fake(RuntimeError('x')), 'm', 'p'), '')
        self.assertEqual(core.map_status_text(object(), 'm', 'p'), '')

    def test_real_backend_answers_quickly_for_every_campaign_profile(self):
        import time
        b = core.BuildBackend()
        t = time.time()
        for m, p in (('traynor03', 'defence_r5'), ('thanson01', 'sniper_next_r5'), ('thanson02', 'epidemic_free_r4')):
            self.assertIn(b.status(m, p), ('ready', 'needs_build'))
        self.assertLess(time.time() - t, 5)


if __name__ == '__main__':
    unittest.main()
