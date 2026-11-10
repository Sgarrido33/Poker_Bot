"""Frozen exploratory cross-play with the newly trained NoRegrets opponent.

This is separate from the registered stage-3 field. One independent group per
format is a pipeline/transfer diagnostic, not a strategy confirmation.
"""
from dataclasses import asdict
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from time import perf_counter

from pokerfight.arena import make_policy, play_hand, seed_for
from pokerfight.domain import Action, Observation
from pokerfight.noregrets_opponent import NoRegretsTableOpponent
from pokerfight.strategy import BotConfig
from scripts.competition_experiment import record

BASE = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = BASE / 'results/noregrets_crossplay_2026-10-28'
INDEX = BASE / 'research/noregrets_training_20261028/profiles_index_validated.json'
EXE = BASE / 'research/noregrets_integration_20261028/artifacts/noregrets-pokerfight-adapter.exe'
IDENTIFIER = 'noregrets-observation-crossplay-20261028-01'
ARMS = ('v2', 'v4rb', 'v6')
OPPONENTS = ('fullhouse', 'noregrets', 'v2_4000', 'pressure', 'fullhouse')


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class RecordedOpponent:
    def __init__(self, seed, failure_root):
        self.policy = NoRegretsTableOpponent(seed, INDEX, executable=EXE, timeout_s=4.25)
        self.calls = []
        self.failure_root = failure_root

    def decide(self, obs):
        try:
            decision = self.policy.decide(obs)
        except Exception as error:
            save(self.failure_root / 'failed_observation.json',
                 {'observation': asdict(obs), 'error': type(error).__name__ + ': ' + str(error)})
            raise
        self.calls.append({'observation': asdict(obs), 'decision': decision.to_dict()})
        return decision

    def close(self):
        self.policy.close()


def registered_files():
    files = [Path(__file__), INDEX, EXE, EXE.with_suffix('.runtime.json'),
             BASE / 'scripts/competition_experiment.py']
    files += list((BASE / 'pokerfight').rglob('*.py'))
    files += list((BASE / 'pokerfight/external').rglob('*.npz'))
    files += list((BASE / 'pokerfight/external').rglob('SOURCE.json'))
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    for value in index['profiles'].values():
        meta = (INDEX.parent / value).resolve()
        files.append(meta)
        profile = json.loads(meta.read_text(encoding='utf-8'))
        value = profile['artifact_path']
        artifact = Path(value) if Path(value).is_absolute() else meta.parent / value
        files.append(artifact.resolve())
    return {str(p.resolve()): sha(p) for p in sorted(set(files))}


def register(root, identifier=IDENTIFIER):
    if root.exists() and any(root.iterdir()):
        raise ValueError('Use a new empty root; never overwrite registered evidence')
    files = registered_files()
    planned = {seed_for(identifier, 'deck', n, h) for n in (5, 6) for h in range(128)}
    historical = set()
    # A concurrently running campaign is represented by its entire reserved
    # seed set; do not read its partially appended JSONL files.
    active = BASE / 'results/competition_stage3_2026-10-28'
    if (active / 'protocol.json').exists():
        other = json.loads((active / 'protocol.json').read_text())
        for s in other['scenarios']:
            count = other['groups_per_format'] if s == 'external_diverse' else other['control_groups_per_format']
            for n in other['players']:
                for g in range(count):
                    b = seed_for(other['experiment_id'], 'crossplay-session-01', s, n, g)
                    historical.update(seed_for(b, 'deck', h) for h in range(other['session']['hand_limit']))
    for path in (BASE / 'results').rglob('*.jsonl'):
        if active in path.parents or root in path.parents:
            continue
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if 'deck_seed' in row:
                    historical.add(row['deck_seed'])
    if planned & historical:
        raise ValueError('New challenge shares deck seeds with existing or reserved data')
    root.mkdir(parents=True, exist_ok=True)
    protocol = {'experiment_id': identifier, 'registered_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Separate exploratory second-learned-family cross-play; no confirmatory inference.',
        'arms': ARMS, 'players': [5, 6], 'groups_per_format': 1, 'horizon': 128,
        'starting_stack': 800, 'blinds': [50, 100], 'ante': 0, 'rebuys': False,
        'opponents': OPPONENTS, 'files': files, 'tables': 33, 'hands_maximum': 4224,
        'independent_groups': 2, 'all_cyclic_rotations': True,
        'hero_configs': {'v2': [4000, 1600], 'v4rb': [4096, 3500], 'v6': [4096, 3500]},
        'rival_config': [512, 1600], 'noregrets_timeout_s': 4.25,
        'profile_selection': 'Fixed largest completed resource-admissible 1M profile per player count; no selection by wins.',
        'native_fallback': 'Record unseen/menu/zero-mass separately from infrastructure failures; no hidden substitution.',
        'seed_check': {'new_unique_decks': len(planned), 'historical_or_reserved_decks': len(historical), 'overlap': 0},
        'stopping': 'Complete fixed allocation; infrastructure error stops and preserves partial evidence; never change for profits.'}
    save(root / 'protocol.json', protocol)
    (root / 'protocol.sha256').write_text(sha(root / 'protocol.json'), encoding='ascii')
    return protocol


def load(root):
    if sha(root / 'protocol.json') != (root / 'protocol.sha256').read_text().strip():
        raise ValueError('Protocol hash mismatch')
    protocol = json.loads((root / 'protocol.json').read_text())
    if any(sha(Path(p)) != digest for p, digest in protocol['files'].items()):
        raise ValueError('Frozen source/model/runtime changed')
    return protocol


def run(root):
    protocol = load(root)
    identifier = protocol['experiment_id']
    output = root / 'hands.jsonl'
    if output.exists():
        raise ValueError('Evidence exists already; refuse outcome-dependent reruns')
    sessions, totals, external_counts = [], Counter(), defaultdict(Counter)
    times, hands, started = [], 0, perf_counter()
    with output.open('w', encoding='utf-8') as stream:
        for n in protocol['players']:
            ids = ('hero',) + tuple(f'opponent_{i}' for i in range(1, n))
            for rotation in range(n):
                seeds = {pid: seed_for(identifier, 'policy', n, rotation, pid) for pid in ids}
                shifted = list(ARMS[rotation % 3:] + ARMS[:rotation % 3])
                for variant in shifted:
                    pp = {}
                    for i, pid in enumerate(ids):
                        kind = variant if i == 0 else OPPONENTS[i - 1]
                        pp[pid] = (RecordedOpponent(seeds[pid], root) if kind == 'noregrets' else
                            make_policy(kind, BotConfig(*(protocol['hero_configs'][variant] if i == 0
                                                          else protocol['rival_config'])), seeds[pid]))
                    stacks, eliminated = dict.fromkeys(ids, 800), {}
                    button, played = ids[(rotation - 1) % n], 0
                    try:
                        for hand in range(128):
                            active = tuple(pid for pid in ids if stacks[pid] > 0)
                            if len(active) < 2:
                                break
                            if hand:
                                old = ids.index(button)
                                button = next(ids[(old + k) % n] for k in range(1, n + 1) if ids[(old + k) % n] in active)
                            b = active.index(button)
                            seats = active[b + 1:] + active[:b + 1]
                            for policy in pp.values():
                                if isinstance(policy, RecordedOpponent):
                                    policy.calls.clear()
                            deck = seed_for(identifier, 'deck', n, hand)
                            table = f'nr-{seed_for(identifier, "public", n, rotation):016x}'
                            result = play_hand(pp, seats, stacks, deck, str(hand), table, trace_player_id='hero')
                            calls = [call for policy in pp.values() if isinstance(policy, RecordedOpponent) for call in policy.calls]
                            for call in calls:
                                obs = Observation.from_dict(call['observation'])
                                d = call['decision']
                                assert Action(**d['action']).is_legal(obs)
                                ext = d['external']
                                c = external_counts[(len(obs.players), obs.street)]
                                c['decisions'] += 1
                                c['fallbacks'] += d['fallback']
                                c['stack_transfers'] += ext['profile_transfer']
                                c['menu_mismatches'] += ext['menu_mismatches_delta']
                                if d['fallback']:
                                    c['fallback:' + str(ext.get('fallback_reason', 'unspecified'))] += 1
                                times.append(d['elapsed_ms'])
                            for _, d in result.decisions:
                                totals['decisions'] += 1
                                totals['non_noregrets_fallbacks'] += d.fallback and not d.reason.startswith('external:noregrets')
                                totals['equity_deadlines'] += bool(d.equity and d.equity.timed_out)
                                totals['search_deadlines'] += bool(d.search and 'deadline' in d.search['stop'])
                            row = record(result, players=n, rotation=rotation, variant=variant, hand=hand,
                                deck_seed=deck, policy_seeds=seeds, seats=seats, noregrets_trace=calls)
                            stream.write(json.dumps(row, allow_nan=False) + '\n')
                            stream.flush()
                            assert sum(result.payoffs.values()) == 0
                            stacks.update(result.stacks)
                            assert sum(stacks.values()) == 800 * n
                            for pid in active:
                                if stacks[pid] == 0:
                                    eliminated[pid] = hand
                            played += 1
                            hands += 1
                    finally:
                        for policy in pp.values():
                            if hasattr(policy, 'close'):
                                policy.close()
                    finished = sum(s > 0 for s in stacks.values()) == 1
                    sessions.append({'players': n, 'rotation': rotation, 'variant': variant, 'stacks': stacks,
                        'eliminated_at': eliminated, 'played_hands': played, 'table_finished': finished,
                        'observed_win': finished and stacks['hero'] > 0, 'censored_survivor': not finished and stacks['hero'] > 0})
                    save(root / 'progress.json', {'tables_completed': len(sessions), 'hands': hands,
                        'technical_counts': dict(totals), 'elapsed_wall_seconds': perf_counter() - started})
    load(root)
    save(root / 'sessions.json', sessions)
    summary = {'complete': len(sessions) == 33, 'tables': len(sessions), 'hand_executions': hands,
        'independent_groups': 2, 'hands_sha256': sha(output), 'elapsed_wall_seconds': perf_counter() - started,
        'technical_counts': dict(totals),
        'technical_pass': all(totals[k] == 0 for k in ('non_noregrets_fallbacks', 'equity_deadlines', 'search_deadlines')),
        'noregrets_coverage': [{'players': n, 'street': s, **counts} for (n, s), counts in sorted(external_counts.items())],
        'noregrets_latency_ms': {'decisions': len(times), 'p50': statistics.median(times) if times else 0,
                                'p95': sorted(times)[max(0, int(len(times) * .95) - 1)] if times else 0, 'maximum': max(times, default=0)},
        'outcomes': {arm: {'tables': sum(s['variant'] == arm for s in sessions),
            'mean_final_stack': statistics.mean(s['stacks']['hero'] for s in sessions if s['variant'] == arm),
            'wins': sum(s['variant'] == arm and s['observed_win'] for s in sessions),
            'busts': sum(s['variant'] == arm and 'hero' in s['eliminated_at'] for s in sessions),
            'censored_survivors': sum(s['variant'] == arm and s['censored_survivor'] for s in sessions)} for arm in ARMS},
        'interpretation': 'Exploratory transfer/coverage diagnostic only; two independent groups cannot establish a stronger strategy or representative tournament field.'}
    save(root / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('register', 'run'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--id', default=IDENTIFIER)
    args = parser.parse_args()
    args.root = args.root.resolve()
    if args.command == 'register':
        register(args.root, args.id)
    else:
        run(args.root)
