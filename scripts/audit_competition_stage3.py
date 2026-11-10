"""Reconstruct every stage-3 session and replay fixed sessions from its snapshot."""
import argparse
from dataclasses import asdict
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys

from research.competition_audit_20261028.audit_sessions import reconstruct, canonical_trace
from scripts.competition_experiment import check_artifact, job_name
from scripts.competition_stage3 import load, jobs


def audit(root, replay=True):
    plan, digest = load(root)
    snapshot = root / 'source/pokerfight'
    alias = '_stage3_replay_snapshot'
    spec = importlib.util.spec_from_file_location(alias, snapshot / '__init__.py',
                                                submodule_search_locations=[str(snapshot)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[alias] = package
    spec.loader.exec_module(package)
    arena = importlib.import_module(alias + '.arena')
    config_type = importlib.import_module(alias + '.strategy').BotConfig
    totals = {'hand_executions_reconstructed': 0, 'tables_reconstructed': 0,
              'replay_tables': 0, 'replay_hands_excluded_from_new_evidence': 0,
              'public_trace_decisions_checked': 0}
    sealed, replay_rows = {}, []
    for job in jobs(plan):
        name = job_name(job)
        report_path, trace_path = root / (name + '.json'), root / (name + '.jsonl')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        check_artifact(root, plan, digest, job, report)
        records = [json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines()]
        expected = reconstruct(plan, job, records)
        actual = {(s['variant'], s['rotation']): s for s in report['sessions']}
        if expected != actual or len(records) != report['executions']:
            raise ValueError('Session reconstruction mismatch: ' + name)
        corrupt = json.loads(json.dumps(report['sessions']))
        corrupt[0]['last_stacks']['hero'] += 1
        if expected == {(s['variant'], s['rotation']): s for s in corrupt}:
            raise AssertionError('Corrupt-summary probe failed')
        for row in records:
            for entry in row['trace']:
                obs = entry['observation']
                h = obs['history']
                if row['history'][:len(h)] != h or len(h) >= len(row['history']):
                    raise ValueError('Incomplete public history prefix')
                event = row['history'][len(h)]
                action = entry['decision']['action']
                if event['player_id'] != obs['hero_id'] or event['kind'] != action['kind']:
                    raise ValueError('Logged action differs from public history')
                if action['kind'] == 'raise_to' and event['amount'] != action['amount']:
                    raise ValueError('Logged raise amount differs')
                totals['public_trace_decisions_checked'] += 1
        totals['hand_executions_reconstructed'] += len(records)
        totals['tables_reconstructed'] += len(expected)
        for path in (report_path, trace_path):
            sealed[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if replay and job[1] == 'external_diverse' and job[3] == 0:
            n, rotation = job[2], 0
            ids = ('hero',) + tuple(f'opponent_{i}' for i in range(1, n))
            kinds = {pid: plan['scenarios'][job[1]][(i - 1) % len(plan['scenarios'][job[1]])]
                     for i, pid in enumerate(ids) if i}
            base = arena.seed_for(plan['experiment_id'], 'crossplay-session-01', job[1], n, 0)
            table_id = f"cp-{arena.seed_for('public-table-token', base, rotation, 'session'):016x}"
            for variant in plan['arms']:
                original = sorted((r for r in records if r['variant'] == variant and r['rotation'] == rotation),
                                  key=lambda r: r['hand'])
                seeds = original[0]['policy_seeds']
                policies = {pid: arena.make_policy(variant if pid == 'hero' else kinds[pid],
                    config_type(**(plan['configs'][variant] if pid == 'hero' else plan['rival_config'])),
                    seeds[pid]) for pid in ids}
                stacks = dict.fromkeys(ids, 800)
                for row in original:
                    cfg = plan['session']
                    result = arena.play_hand(policies, tuple(row['seats']), stacks, row['deck_seed'],
                        str(row['hand']), table_id, cfg['small_blind'], cfg['big_blind'], cfg['ante'], trace_player_id='hero')
                    if (result.payoffs != row['payoffs'] or result.stacks != row['stacks']
                        or list(result.board) != row['board']
                        or [asdict(e) for e in result.history] != row['history']
                        or canonical_trace(result.trace) != canonical_trace(row['trace'])):
                        raise ValueError(f'Exact replay mismatch {name}/{variant}/{row["hand"]}')
                    stacks.update(result.stacks)
                    totals['replay_hands_excluded_from_new_evidence'] += 1
                totals['replay_tables'] += 1
                replay_rows.append({'players': n, 'variant': variant, 'rotation': 0,
                                    'group': 0, 'matched_hands': len(original), 'matched': True})
        (root / 'audit_progress.json').write_text(json.dumps({**totals, 'last_job': name}) + '\n')
    result = {'passed': True, 'protocol_sha256': digest, **totals,
        'corrupt_summary_rejected': True, 'replay_uses': 'registered immutable policy package alias',
        'replay_selection': 'external_diverse group 0, rotation 0, all arms, both formats; fixed rule, no payoff selection',
        'replays': replay_rows, 'artifact_sha256': sealed,
        'auditor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reconstruction_dependency_sha256': hashlib.sha256(Path('research/competition_audit_20261028/audit_sessions.py').read_bytes()).hexdigest()}
    (root / 'independent_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'artifact_sha256'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('results/competition_stage3_2026-10-28'))
    parser.add_argument('--no-replay', action='store_true')
    args = parser.parse_args()
    audit(args.root.resolve(), not args.no_replay)
