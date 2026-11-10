"""Inspect completed quality experiments and replay selected paired outcomes."""
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import statistics

from pokerfight.arena import make_policy, play_hand
from pokerfight.campaign import save
from pokerfight.evaluation import environment
from pokerfight.strategy import BotConfig
from scripts.benchmark_action_compilation import without_timing


ROOT = Path('results/quality_2026-10-28')


def replay(row, report):
    config = BotConfig(**report['original_config' if row['variant'] == 'v2' else 'config'])
    rival_config = BotConfig(**report['rival_config'])
    scenarios = json.loads((ROOT / 'protocol.json').read_text())['scenarios']
    ids = ('hero',) + tuple(f'opponent_{i}' for i in range(1, report['players']))
    kinds = {pid: scenarios[report['scenario']][(i - 1) % len(scenarios[report['scenario']])]
             for i, pid in enumerate(ids) if i}
    policies = {pid: make_policy(row['variant'] if pid == 'hero' else kinds[pid],
        config if pid == 'hero' else rival_config, row['policy_seeds'][pid]) for pid in ids}
    result = play_hand(policies, tuple(row['seats']), dict.fromkeys(ids, report['depth_bb'] * 100),
        row['deck_seed'], str(row['block']), f"quality-{report['base_seed']}-{row['rotation']}", trace_player_id='hero')
    actual = {'payoffs': result.payoffs, 'stacks': result.stacks,
              'history': [asdict(e) for e in result.history], 'trace': result.trace}
    expected = {key: row[key] for key in actual}
    return without_timing(actual) == without_timing(expected)


def diagnostics(rows, variant):
    decisions = [entry for row in rows if row['variant'] == variant for entry in row['trace']]
    searches = [e['decision']['search'] for e in decisions if 'search' in e['decision']]
    actions = Counter()
    nonterminal_raises, reraised, pushes = 0, 0, 0
    for row in rows:
        if row['variant'] != variant:
            continue
        for entry in row['trace']:
            obs, decision = entry['observation'], entry['decision']
            if obs['board']:
                continue
            action = decision['action']
            actions[action['kind']] += 1
            if action['kind'] != 'raise_to':
                continue
            hero = next(p for p in obs['players'] if p['player_id'] == 'hero')
            effective = min(hero['stack'] + hero['street_bet'], max(
                p['stack'] + p['street_bet'] for p in obs['players'] if p['player_id'] != 'hero' and not p['folded']))
            if action['amount'] >= effective:
                pushes += 1
                continue
            nonterminal_raises += 1
            later = row['history'][len(obs['history']) + 1:]
            for event in later:
                if event['street'] != 'preflop' or event['player_id'] == 'hero':
                    break
                if event['kind'] == 'raise_to':
                    reraised += 1
                    break
    return {'hero_decisions': len(decisions), 'preflop_actions': dict(actions),
        'effective_pushes': pushes, 'raises_leaving_effective_chips': nonterminal_raises,
        'opposing_reraises_before_next_decision': reraised,
        'searches': len(searches), 'search_changes': sum(s['changed'] for s in searches),
        'search_stops': dict(Counter(s['stop'] for s in searches)),
        'training_worlds': sum(s.get('training_worlds', 0) for s in searches),
        'evaluation_worlds': sum(s['worlds'] for s in searches),
        'continuation_nodes': sum(s.get('continuation_nodes', 0) for s in searches),
        'continuation_calls': sum(s.get('continuation_calls', 0) for s in searches),
        'max_elapsed_ms': max((e['decision']['elapsed_ms'] for e in decisions), default=0),
        'fallbacks': sum(e['decision']['fallback'] for e in decisions)}


def main():
    plan = json.loads((ROOT / 'protocol.json').read_text())
    if plan['environment']['source_sha256'] != environment()['source_sha256']:
        raise ValueError('Source changed')
    summary = json.loads((ROOT / 'validation/summary.json').read_text())
    if not summary['complete']:
        raise ValueError('Complete validation before analysis')
    rows, reports = [], {}
    for path in sorted((ROOT / 'validation').glob('cell_*.json')):
        reports[path.stem] = json.loads(path.read_text())
        for line in path.with_suffix('.jsonl').read_text().splitlines():
            row = json.loads(line)
            row['cell'] = path.stem
            rows.append(row)
    groups = {}
    for row in rows:
        groups.setdefault((row['cell'], row['block'], row['rotation']), {})[row['variant']] = row
    audits = []
    for key, paired in groups.items():
        assert set(paired) == set(plan['variants'])
        assert len({r['deck_seed'] for r in paired.values()}) == 1
        assert len({json.dumps(r['policy_seeds'], sort_keys=True) for r in paired.values()}) == 1
        assert len({tuple(r['seats']) for r in paired.values()}) == 1
        assert all(sum(r['payoffs'].values()) == 0 for r in paired.values())
    for candidate in ('v4rb', 'v5'):
        changed = [(key, paired) for key, paired in groups.items()
                   if without_timing(paired[candidate]['trace']) != without_timing(paired['v4']['trace'])]
        changed.sort(key=lambda item: item[1][candidate]['payoffs']['hero'] - item[1]['v4']['payoffs']['hero'])
        # Repeated indices when fewer than four differences are deduplicated.
        selected = changed[:2] + changed[-2:]
        selected = {key: pair for key, pair in selected}
        for key, paired in selected.items():
            for variant in (candidate, 'v4'):
                row = paired[variant]
                matched = replay(row, reports[row['cell']])
                audits.append({'cell': key[0], 'block': key[1], 'rotation': key[2], 'variant': variant,
                    'hero_payoff_bb': row['payoffs']['hero'] / 100,
                    'candidate_minus_v4_bb': (paired[candidate]['payoffs']['hero'] - paired['v4']['payoffs']['hero']) / 100,
                    'matched': matched})
    result = {'source_sha256': environment()['source_sha256'], 'paired_deals_audited': len(groups),
        'hand_executions_audited': len(rows), 'same_deck_across_all_five_arms': True,
        'same_policy_seeds_and_seats_across_all_five_arms': True,
        'diagnostics': {v: diagnostics(rows, v) for v in plan['variants']}, 'replays': audits,
        'all_replays_matched': all(r['matched'] for r in audits),
        'interpretation': 'Action/reraise counts are descriptive under each policy; different visited states prevent causal action-quality comparisons.'}
    save(ROOT / 'validation/analysis.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
