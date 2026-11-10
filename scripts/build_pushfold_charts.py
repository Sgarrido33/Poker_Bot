"""Solve the v8 push/fold charts for each stack. Output: pokerfight/data/pushfold_charts.json."""
from __future__ import annotations

import json

from pokerfight.pushfold import DATA, matrices, solve

STACKS = [x / 2 for x in range(2, 41)]  # 1..20 bb in half-bb steps


def main() -> None:
    classes, _, _ = matrices()
    solutions = [solve(s) for s in STACKS]
    with open(DATA / "pushfold_charts.json", "w", encoding="utf-8", newline="") as f:
        json.dump({"classes": classes, "stacks": STACKS, "solutions": solutions,
                   "model": "chip-EV, equal stacks, no ante, single caller, 400 averaged iterations"}, f)


if __name__ == "__main__":
    main()
