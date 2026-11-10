"""Chip-EV push/fold equilibrium for the 6-max blind structure (v8).

One game covers every table size: a first-in shover with k players behind faces
the same blinds whatever folded before. Positions 0..5 are UTG, HJ, CO, BTN, SB,
BB; heads-up maps to SB (button) and BB. Approximations, stated explicitly:
equal effective stacks, no ante, card removal only between the two hands in a
confrontation, and a single caller (players after the first caller fold).
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data"
POSTED = (0.0, 0.0, 0.0, 0.0, 0.5, 1.0)


@lru_cache(maxsize=1)
def matrices() -> tuple[list[str], np.ndarray, np.ndarray]:
    with open(DATA / "preflop_equity.json", encoding="utf-8") as f:
        data = json.load(f)
    pairs = np.array(data["pairs"], dtype=float)
    own = np.array([6.0 if len(c) == 2 else 4.0 if c[2] == "s" else 12.0 for c in data["classes"]])
    # W[i, j]: compatible combos of class j given one combo of class i.
    return data["classes"], np.array(data["equity"]), pairs / own[:, None]


def solve(stack_bb: float, iterations: int = 400) -> dict:
    """Averaged best-response iteration; returns shove/call frequencies."""
    classes, eq, w = matrices()
    n = len(classes)
    shove = {p: np.full(n, 0.5) for p in range(5)}
    call = {(p, q): np.full(n, 0.5) for p in range(5) for q in range(p + 1, 6)}
    combos = w.sum(1)
    for t in range(1, iterations + 1):
        rate = 1.0 / (t + 1)
        new_call = {}
        for (p, q), _ in call.items():
            weight = w * shove[p][None, :]
            mass = weight.sum(1)
            e = np.divide((weight * eq).sum(1), mass, out=np.full(n, 0.5), where=mass > 0)
            pot = 2 * stack_bb + 1.5 - POSTED[p] - POSTED[q]
            new_call[(p, q)] = (e * pot - stack_bb > -POSTED[q]).astype(float)
        new_shove = {}
        for p in range(5):
            alive = np.ones(n)  # P(all callers so far folded | hero hand)
            ev = np.zeros(n)
            for q in range(p + 1, 6):
                weight = w * call[(p, q)][None, :]
                mass = weight.sum(1)
                prob = mass / combos
                e = np.divide((weight * eq).sum(1), mass, out=np.zeros(n), where=mass > 0)
                pot = 2 * stack_bb + 1.5 - POSTED[p] - POSTED[q]
                ev += alive * prob * (e * pot - stack_bb)
                alive = alive * (1 - prob)
            ev += alive * (1.5 - POSTED[p])
            new_shove[p] = (ev > -POSTED[p]).astype(float)
        for key in call:
            call[key] += rate * (new_call[key] - call[key])
        for p in shove:
            shove[p] += rate * (new_shove[p] - shove[p])
    return {"shove": {str(p): [round(x, 3) for x in v] for p, v in shove.items()},
            "call": {f"{p},{q}": [round(x, 3) for x in v] for (p, q), v in call.items()}}


@lru_cache(maxsize=1)
def charts() -> dict:
    with open(DATA / "pushfold_charts.json", encoding="utf-8") as f:
        return json.load(f)


def _nearest(stack_bb: float) -> dict:
    data = charts()
    stacks = data["stacks"]
    best = min(range(len(stacks)), key=lambda i: abs(stacks[i] - stack_bb))
    return data["solutions"][best]


def shove_freq(hand: str, position: int, stack_bb: float) -> float:
    return _nearest(stack_bb)["shove"][str(position)][charts()["classes"].index(hand)]


def call_freq(hand: str, shover: int, caller: int, stack_bb: float) -> float:
    return _nearest(stack_bb)["call"][f"{shover},{caller}"][charts()["classes"].index(hand)]


def range_percent(freqs: list[float]) -> float:
    classes = charts()["classes"]
    combos = [6 if len(c) == 2 else 4 if c[2] == "s" else 12 for c in classes]
    return sum(f * c for f, c in zip(freqs, combos)) / 1326
