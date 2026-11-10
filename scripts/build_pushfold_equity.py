"""Precompute the 169x169 preflop all-in equity matrix used by v8.

Each cell averages over every compatible combo pair (card removal included) and
Monte Carlo boards. Output: pokerfight/data/preflop_equity.json.
Usage: python -m scripts.build_pushfold_equity [--boards 600] [--workers 12]
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import random

import eval7

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def classes() -> list[str]:
    out = []
    for i in range(12, -1, -1):
        for j in range(12, -1, -1):
            a, b = RANKS[i], RANKS[j]
            if i == j:
                out.append(a + b)
            elif i > j:
                out.append(a + b + "s")
                out.append(a + b + "o")
    return out


def combos(cls: str) -> list[tuple[str, str]]:
    a, b = cls[0], cls[1]
    if a == b:
        return [(a + s1, a + s2) for k, s1 in enumerate(SUITS) for s2 in SUITS[k + 1:]]
    if cls[2] == "s":
        return [(a + s, b + s) for s in SUITS]
    return [(a + s1, b + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]


def row(args: tuple[int, int, int]) -> list[tuple[int, float, int]]:
    i, boards, seed = args
    names = classes()
    rng = random.Random(seed * 1000 + i)
    deck = [eval7.Card(r + s) for r in RANKS for s in SUITS]
    out = []
    for j in range(i, len(names)):
        pairs = [(h, v) for h in combos(names[i]) for v in combos(names[j]) if not set(h) & set(v)]
        if not pairs:
            out.append((j, 0.5, 0))
            continue
        total = 0.0
        per = max(1, boards // len(pairs))
        n = 0
        for h, v in pairs:
            hc = [eval7.Card(c) for c in h]
            vc = [eval7.Card(c) for c in v]
            dead = set(h) | set(v)
            rest = [c for c in deck if str(c) not in dead]
            for _ in range(per):
                board = rng.sample(rest, 5)
                a = eval7.evaluate(hc + board)
                b = eval7.evaluate(vc + board)
                total += 1.0 if a > b else 0.5 if a == b else 0.0
                n += 1
        out.append((j, total / n, len(pairs)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boards", type=int, default=600)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--output", default="pokerfight/data/preflop_equity.json")
    args = parser.parse_args()
    names = classes()
    n = len(names)
    eq = [[0.5] * n for _ in range(n)]
    pairs = [[0] * n for _ in range(n)]
    with ProcessPoolExecutor(args.workers) as pool:
        for i, result in enumerate(pool.map(row, [(i, args.boards, args.seed) for i in range(n)])):
            for j, value, count in result:
                eq[i][j], eq[j][i] = value, 1.0 - value
                pairs[i][j] = pairs[j][i] = count
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump({"classes": names, "boards_per_cell": args.boards, "seed": args.seed,
                   "equity": [[round(x, 4) for x in r] for r in eq], "pairs": pairs}, f)


if __name__ == "__main__":
    main()
