from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from scripts.diagnose_early_eliminations import diagnose, features, response_after
from scripts.diagnose_shortstack import opening


class EarlyDiagnosisTests(unittest.TestCase):
    def test_covering_push_is_terminal_without_literal_all_in(self):
        obs = opening(3, 8, 'BTN', rival_depth=2)
        f = features({'observation': asdict(obs), 'decision': {'action': {'kind': 'raise_to', 'amount': 200}}})
        self.assertTrue(f['effective_push'])
        self.assertFalse(f['literal_all_in'])

    def test_response_stops_at_next_hero_and_deduplicates_opponent(self):
        entry = {'observation': {'history': [], 'hero_id': 'hero'},
                 'decision': {'action': {'kind': 'raise_to', 'amount': 200}}}
        history = [{'player_id': p, 'street': 'preflop', 'kind': k}
                   for p, k in [('hero', 'raise_to'), ('a', 'call'), ('b', 'raise_to'),
                                ('hero', 'fold'), ('a', 'call')]]
        responses = response_after(entry, {'history': history})
        self.assertEqual([e['kind'] for e in responses], ['call', 'raise_to'])

    def test_counts_bust_once_even_when_table_continues_without_hero(self):
        rows = [{'variant': 'v2', 'hand': 0, 'group': 0, 'rotation': 0,
                 'stacks': {'hero': 0, 'a': 1600}, 'payoffs': {'hero': -800, 'a': 800},
                 'trace': [], 'history': []},
                {'variant': 'v2', 'hand': 1, 'group': 0, 'rotation': 0,
                 'stacks': {'a': 1600}, 'payoffs': {'a': 0}, 'trace': [], 'history': []}]
        Path('.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir='.tmp') as tmp:
            root = Path(tmp)
            (root / 'session_test_5p_0.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            result = diagnose(root, root / 'output')
        self.assertEqual(result['counts']['v2']['early_eliminations'], 1)
        self.assertEqual(result['new_hand_executions'], 0)


if __name__ == '__main__':
    unittest.main()
