"""Predeclared small technical probe of v6; no strategic promotion decision."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.domain import Action, Observation
from pokerfight.evaluation import environment
from pokerfight.strategy import BotConfig
from pokerfight.terminal_search import terminal_alternatives


def main():
    root = Path('results/v6_technical_2026-10-28')
    root.mkdir(parents=True, exist_ok=True)
    protocol_path = root / 'protocol.json'
    if protocol_path.exists():
        raise ValueError('Use a new output directory for another probe.')
    protocol = {'experiment_id': 'v6-terminal-probe-20261028-01',
        'purpose': 'Technical probe only; all results development; no winner selection.',
        'arms': ['v2', 'v4rb', 'v6'], 'players': [5, 6], 'deals_per_format': 3,
        'hero_config': {'samples': 4096, 'budget_ms': 3500},
        'v2_config': {'samples': 4000, 'budget_ms': 1600},
        'opponents': ['fullhouse', 'honest', 'v2_4000', 'pressure', 'fullhouse'],
        'starting_stack': 800, 'small_blind': 50, 'big_blind': 100,
        'ante': 0, 'environment': environment(),
        'fixture_rule': 'First 16 changed nonterminal raise observations in source order; no outcome selection.',
        'fixture_samples': 4096}
    source = Path('results/early_diagnosis_2026-10-28/diagnosis.json')
    protocol['diagnosis_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    jobs = []
    for n in protocol['players']:
        ids = ('hero',) + tuple(f'opponent_{i}' for i in range(1, n))
        for deal in range(3):
            jobs.append({'players': n, 'deal': deal,
                'deck_seed': seed_for(protocol['experiment_id'], n, deal, 'deck'),
                'policy_seeds': {pid: seed_for(protocol['experiment_id'], n, deal, pid) for pid in ids}})
    historical = set()
    for path in Path('results').rglob('*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                historical.add(json.loads(line).get('deck_seed'))
    assert all(j['deck_seed'] not in historical for j in jobs)
    protocol['jobs'] = jobs
    protocol['new_deck_seeds_checked_against_history'] = True
    rendered = json.dumps(protocol, indent=2) + '\n'
    protocol_path.write_text(rendered, encoding='utf-8')
    (root / 'protocol.sha256').write_text(hashlib.sha256(rendered.encode()).hexdigest() + '\n')
    fixture_results = []
    for path in sorted(Path('results/competition_stage2_2026-10-28').glob('session_*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row['variant'] != 'v4rb' or row['hand'] >= 24:
                    continue
                for entry in row['trace']:
                    info = entry['decision'].get('search')
                    if not info or not info['changed']:
                        continue
                    obs = Observation.from_dict(entry['observation'])
                    old = Action(**entry['decision']['action'])
                    baseline = Action(**info['baseline'])
                    if old in terminal_alternatives(obs, baseline):
                        continue
                    # Fresh, identical model history in both fixture arms.
                    decisions = {kind: make_policy(kind, BotConfig(4096, 3500),
                        seed_for(protocol['experiment_id'], len(fixture_results))).decide(obs).to_dict()
                                 for kind in ('v4rb', 'v6')}
                    fixture_results.append({'source': path.name, 'rotation': row['rotation'],
                        'hand': row['hand'], 'observation': entry['observation'],
                        'decisions': decisions})
                    if len(fixture_results) == 16:
                        break
                if len(fixture_results) == 16:
                    break
        if len(fixture_results) == 16:
            break
    (root / 'fixtures.json').write_text(json.dumps(fixture_results, indent=2) + '\n')
    hands = []
    for job in jobs:
        n = job['players']
        ids = tuple(job['policy_seeds'])
        # Rotate seats across three technical deals; this is not a full group
        # or a strategy estimate and is not counted as independent rotations.
        seats = ids[job['deal']:] + ids[:job['deal']]
        for kind in protocol['arms']:
            policies = {pid: make_policy(kind if pid == 'hero' else protocol['opponents'][i - 1],
                BotConfig(4000, 1600) if pid != 'hero' or kind == 'v2' else BotConfig(4096, 3500),
                job['policy_seeds'][pid]) for i, pid in enumerate(ids)}
            hand = play_hand(policies, seats, dict.fromkeys(ids, 800), job['deck_seed'],
                f"v6-probe-{n}-{job['deal']}", '0', trace_player_id='hero')
            assert sum(hand.payoffs.values()) == 0
            assert not any(d.fallback for _, d in hand.decisions)
            hands.append({**job, 'variant': kind, 'seats': seats, 'payoffs': hand.payoffs,
                'stacks': hand.stacks, 'history': [asdict(e) for e in hand.history], 'trace': hand.trace})
    with (root / 'hands.jsonl').open('w', encoding='utf-8') as stream:
        for hand in hands:
            stream.write(json.dumps(hand) + '\n')
    fixture_decisions = [d for f in fixture_results for d in f['decisions'].values()]
    actual_decisions = [e['decision'] for h in hands for e in h['trace']]
    decisions = fixture_decisions + actual_decisions
    report = {'new_hand_executions': len(hands), 'unique_new_decks': len(jobs),
        'fixture_decisions': len(fixture_decisions), 'all_payoffs_zero_sum': True,
        'fallbacks': sum(d['fallback'] for d in decisions),
        'equity_timeouts': sum(d.get('equity', {}).get('timed_out', False) for d in decisions),
        'search_deadlines': sum(d.get('search', {}).get('stop') == 'deadline_keep_v2' for d in decisions),
        'max_elapsed_ms': max(d['elapsed_ms'] for d in decisions),
        'fixture_action_changes_v6_vs_v4rb': sum(f['decisions']['v6']['action'] != f['decisions']['v4rb']['action'] for f in fixture_results),
        'interpretation': 'Technical legality/scope probe. Fixtures are cold-model redecisions, not historical replays. No session survival or playing-strength conclusion.'}
    (root / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
