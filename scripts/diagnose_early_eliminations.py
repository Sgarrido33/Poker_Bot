"""Read-only diagnosis of registered stage-2 traces; no new poker hands.

Search.baseline is the local pre-search action, not a replayed frozen-v2
counterfactual. Shared observations are matched only before inspecting payoffs.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from pokerfight.domain import Action, Observation
from pokerfight.shortstack import context


def bucket(value, cuts):
    for cut in cuts:
        if value <= cut:
            return f"<={cut:g}"
    return f">{cuts[-1]:g}"


def features(entry):
    obs = Observation.from_dict(entry['observation'])
    action = Action(**entry['decision']['action'])
    ctx = context(obs)
    investment = (action.amount - obs.hero.street_bet if action.kind == 'raise_to'
                  else obs.legal.call_amount if action.kind == 'call' else 0)
    effective = ctx.effective_bb * obs.big_blind
    effective_push = (action.kind == 'raise_to' and action.amount >= effective)
    return {'position': obs.position, 'effective_bb': ctx.effective_bb,
        'depth_bin': bucket(ctx.effective_bb, (4, 8, 12)),
        'opponents': len(obs.opponents), 'situation': ctx.situation,
        'call_bb': ctx.call_bb, 'price': ctx.price,
        'price_bin': bucket(ctx.price, (.1, .25, .4)),
        'investment_bb': investment / obs.big_blind,
        'investment_stack_fraction': investment / obs.hero.stack,
        'effective_push': effective_push,
        'literal_all_in': investment == obs.hero.stack,
        'action': action.to_dict()}


def response_after(entry, row):
    """First response by each opponent after a raise, through next hero turn.

    Raises count as continuation as well as model violations. No missing
    response (e.g. an already all-in opponent) is classified as a fold.
    """
    obs = entry['observation']
    if entry['decision']['action']['kind'] != 'raise_to':
        return []
    result, seen = [], set()
    for event in row['history'][len(obs['history']) + 1:]:
        if event['street'] != 'preflop' or event['player_id'] == obs['hero_id']:
            break
        if event['player_id'] in seen:
            continue
        seen.add(event['player_id'])
        result.append(event)
    return result


def state_key(observation):
    # Public physical state only; prior-hand opponent profiles may differ.
    state = {k: v for k, v in observation.items() if k != 'table_id'}
    return json.dumps(state, sort_keys=True, separators=(',', ':'))


def diagnose(root, output, horizon=24):
    paths = sorted(root.glob('session_*.jsonl'))
    if not paths:
        raise FileNotFoundError(f'No session traces in {root}')
    output.mkdir(parents=True, exist_ok=True)
    outcomes = defaultdict(Counter)
    breakdown = defaultdict(Counter)
    records, sources, shared = [], {}, defaultdict(Counter)
    examples = []
    strata = defaultdict(Counter)
    for path in paths:
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        baseline_states = {}
        with path.open(encoding='utf-8') as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        for row in rows:
            if row['variant'] != 'v2' or row['hand'] >= horizon:
                continue
            for entry in row['trace']:
                baseline_states[(row['rotation'], row['hand'], state_key(entry['observation']))] = entry['decision']['action']
        for row in rows:
            variant = row['variant']
            if row['hand'] >= horizon:
                continue
            name = path.stem
            scenario = name[len('session_'):].rsplit('_', 2)[0]
            fmt = int(name.rsplit('_', 2)[1][:-1])
            cohort = outcomes[variant]
            cohort['hands_through_horizon'] += 1
            bust = 'hero' in row['payoffs'] and row['stacks'].get('hero', 0) == 0
            # Rows continue after hero bust; only count the hand that removed
            # positive starting chips, including forced blinds with no action.
            bust = bust and row['stacks'].get('hero', 0) - row['payoffs']['hero'] > 0
            if bust:
                cohort['early_eliminations'] += 1
            stratum = strata[(scenario, fmt, variant)]
            stratum['early_eliminations'] += bust
            changed_in_hand = False
            for decision_index, entry in enumerate(row['trace']):
                if entry['observation']['board']:
                    continue
                f = features(entry)
                search = entry['decision'].get('search')
                changed = bool(search and search['changed'])
                changed_in_hand |= changed
                cohort['preflop_decisions'] += 1
                cohort['searches'] += bool(search)
                cohort['local_search_changes'] += changed
                cohort['effective_pushes'] += f['effective_push']
                if changed:
                    baseline = search['baseline']
                    transition = baseline['kind'] + '->' + f['action']['kind']
                    if f['effective_push']:
                        transition += ':effective_push'
                    breakdown[(variant, 'transition')][transition] += 1
                    for key in ('position', 'depth_bin', 'opponents', 'price_bin', 'situation'):
                        breakdown[(variant, key)][str(f[key])] += 1
                responses = response_after(entry, row)
                reraised = any(e['kind'] == 'raise_to' for e in responses)
                cohort['raises_with_reraise_before_next_hero'] += reraised
                if f['action']['kind'] == 'raise_to' and not f['effective_push']:
                    cohort['nonterminal_raises'] += 1
                    cohort['nonterminal_raises_reraised'] += reraised
                    cohort['changed_nonterminal_raises'] += changed
                    cohort['changed_nonterminal_raises_reraised'] += changed and reraised
                    if reraised and decision_index + 1 < len(row['trace']):
                        following = row['trace'][decision_index + 1]
                        if not following['observation']['board']:
                            cohort['nonterminal_raise_then_fold_to_reraise'] += following['decision']['action']['kind'] == 'fold'
                if f['effective_push']:
                    cohort['effective_pushes_with_observed_response'] += bool(responses)
                    cohort['effective_pushes_with_continuation'] += any(e['kind'] in ('call', 'raise_to') for e in responses)
                key = (row['rotation'], row['hand'], state_key(entry['observation']))
                if variant != 'v2' and key in baseline_states:
                    shared[variant]['same_physical_state_decisions'] += 1
                    shared[variant]['different_action'] += baseline_states[key] != f['action']
                record = {'source': path.name, 'scenario': scenario, 'players': fmt,
                    'group': row['group'], 'rotation': row['rotation'], 'hand': row['hand'],
                    'decision_index': decision_index, 'variant': variant,
                    'bust_this_hand': bust, 'hero_payoff_bb': row['payoffs']['hero'] / 100,
                    'changed_local_baseline': changed,
                    'baseline': json.dumps(search['baseline']) if search else '',
                    **{k: json.dumps(v) if isinstance(v, dict) else v for k, v in f.items()},
                    'responses': json.dumps(responses)}
                records.append(record)
                if bust and changed and len(examples) < 24:
                    examples.append({'record': record, 'observation': entry['observation'],
                        'decision': entry['decision']})
            if bust:
                cohort['early_bust_hands_with_local_search_change'] += changed_in_hand
                if row['trace']:
                    last = row['trace'][-1]
                    breakdown[(variant, 'last_bust_action')][last['decision']['action']['kind']] += 1
                    breakdown[(variant, 'last_bust_street')][Observation.from_dict(last['observation']).street] += 1
                else:
                    cohort['early_bust_no_hero_decision'] += 1
    result = {'source_root': str(root), 'horizon': horizon, 'new_hand_executions': 0,
        'source_sha256': sources, 'counts': dict(outcomes),
        'changed_decision_breakdown': {v: {key: dict(counts) for (arm, key), counts in breakdown.items() if arm == v}
                                       for v in outcomes},
        'matched_physical_states': dict(shared),
        'strata': [{'scenario': s, 'players': n, 'variant': v, **counts}
                   for (s, n, v), counts in sorted(strata.items())],
        'interpretation': ['Descriptive, post-selection diagnosis on development data.',
            'Local search baseline is not an exact frozen-v2 counterfactual.',
            'Same physical state does not ensure identical prior-hand model history.',
            'Bust hand containing a changed decision does not establish causation.',
            'All-in response continuation includes calls and raises; missing responses are excluded.']}
    (output / 'diagnosis.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (output / 'examples.json').write_text(json.dumps(examples, indent=2) + '\n', encoding='utf-8')
    if records:
        with (output / 'decisions.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('results/competition_stage2_2026-10-28'))
    parser.add_argument('--output', type=Path, default=Path('results/early_diagnosis_2026-10-28'))
    parser.add_argument('--horizon', type=int, default=24)
    args = parser.parse_args()
    if args.horizon < 1:
        parser.error('horizon must be positive')
    report = diagnose(args.root, args.output, args.horizon)
    print(json.dumps({k: v for k, v in report.items() if k != 'source_sha256'}, indent=2))
