"""Verify unchanged v4 results against the complete pre-quality snapshot."""
from dataclasses import asdict
from pathlib import Path

from pokerfight import action_search, arena, domain, equity, evaluation, opponents, strategy
from pokerfight.campaign import save
from pokerfight.shortstack_experiment import verify_control
from scripts.benchmark_action_compilation import reference_package, fixed_search, full_hand
from scripts.diagnose_shortstack import cases


def main():
    root = Path(__file__).resolve().parents[1]
    before, recorded = reference_package(root / 'research/policy_snapshots/pre_quality_20261028')
    after = {key: globals()[key] for key in before}
    verify_control()
    decisions = []
    for name, obs in cases().items():
        if 'all_in' in name:
            continue
        base = arena.make_policy('v2', strategy.BotConfig(samples=512), 27).decide(obs).action
        a, _ = fixed_search(before, asdict(obs), base.to_dict(), 1024, 270928)
        b, _ = fixed_search(after, asdict(obs), base.to_dict(), 1024, 270928)
        assert a == b, name
        decisions.append({'case': name, 'identical': True})
    hands = []
    for n in (2, 3, 4, 5, 6):
        for rotation in range(n):
            seed = arena.seed_for('quality-v4-control-regression', n, rotation)
            a, b = full_hand(before, n, rotation, seed), full_hand(after, n, rotation, seed)
            assert a == b, (n, rotation)
            hands.append({'players': n, 'rotation': rotation, 'identical': True})
    output = root / 'results/quality_2026-10-28/controls.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    save(output, {'environment_before': recorded, 'environment_after': evaluation.environment(),
        'fixed_searches': decisions, 'complete_hands': hands, 'frozen_v2_manifest_unchanged': True})
    print(f'{len(decisions)} fixed searches, {len(hands)} complete paired hands identical; frozen_v2 unchanged')


if __name__ == '__main__':
    main()
