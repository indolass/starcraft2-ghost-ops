"""The generated copies of the original attack functions (defence variant) differ from the original ONLY by the wrapped calls: scaling by the share of living marked
incubators, the buffered send, the group prelude. Nothing of the original sequence, waits, waypoints or unit numbers is lost (needs the extracted original map)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
os.environ['GHOSTOPS_LINES_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'no_shared_lines_here')
import build  # noqa: E402
import sc2mpq  # noqa: E402

NL = chr(10)


def function_text(text, name):
    m = re.search(r'bool %s \(bool testConds, bool runActions\) \{.*?\n\}' % re.escape(name), text, re.S)
    return m.group(0) if m else None


class WaveCopies(unittest.TestCase):
    def test_copies_are_the_original_with_wrapped_calls_only(self):
        src = os.path.join(build.ROOT, 'tmp', 'source', 'TRaynor03.SC2Map')
        if not os.path.isfile(src):
            self.skipTest('the extracted original map is not available (docs/EXTRACT_MAP.md)')
        text = sc2mpq.Archive(open(src, 'rb').read()).read('MapScript.galaxy').decode('utf-8-sig').replace(chr(13) + NL, NL)
        adapter = build.load_adapter('traynor03')
        tail = build.defence_wave_tail(text, adapter)
        checked = 0
        for w in adapter['defence_waves']:
            name = w['function']
            short = 'GhostOps_DEF_' + name[3:-5]
            orig, copy_ = function_text(text, name), function_text(tail, short)
            self.assertTrue(orig and copy_, name)
            copy_ = copy_.replace(short, name, 1)
            copy_ = re.sub(r'GhostOps_DEF_Add4\(\d, ', 'AIAttackWaveAddUnits4(', copy_)
            copy_ = re.sub(r'GhostOps_DEF_Wp\((\d), ', lambda mo: 'AIAttackWaveAddWaypoint(gv_pLAYER0%s_ZERG, ' % mo.group(1), copy_)
            copy_ = re.sub(r'GhostOps_DEF_Send\((\d), ', lambda mo: 'AIAttackWaveSend(gv_pLAYER0%s_ZERG, ' % mo.group(1), copy_)
            # GhostOps_DEF_Scale(group, expr) -> expr (one level of parentheses inside the expression is enough for the original calls)
            for _ in range(3):
                copy_ = re.sub(r'GhostOps_DEF_Scale\(\d, ((?:[^()]|\([^()]*\))*)\)', r'\1', copy_)

            def keep(t):
                return [ln.strip() for ln in t.split(NL) if ln.strip() and not ln.strip().startswith('//') and 'GhostOps_DEF_' not in ln]
            self.assertEqual(keep(orig), keep(copy_), name)
            checked += 1
        self.assertEqual(checked, len(adapter['defence_waves']))


if __name__ == '__main__':
    unittest.main()
