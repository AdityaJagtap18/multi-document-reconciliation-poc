"""
search.py — how high can tuning alone get?

Every number the README quotes about the tuning ceiling comes from here, so
that the finding is PRODUCED by the same engine the room plays against rather
than asserted by whoever wrote the README.

    python3 reconciliation_game/search.py
    python3 reconciliation_game/search.py --trials 20000

WHAT THIS DOES AND DOES NOT PROVE
---------------------------------
It is a random search. It finds the best policy it happened to try, never
provably the best there is. Quote it as a LOWER BOUND on what tuning can
reach, and say so when you quote it. A learner who beats it has not broken
anything — they have found a policy the search missed, and the finding still
holds as long as the checks beat them.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reconciliation_game.game as game
from reconciliation_game.corpus import FIELDS

# The tolerances a person would actually try, rather than a continuous range.
TOLERANCES = [0.0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.15, 0.25]

# The 4000-trial result, recorded so the fast property test in
# selftest_game.py can assert against the same number the README quotes
# rather than against a cheaper search that finds a lower ceiling.
# Regenerate with: python3 reconciliation_game/search.py --trials 4000 --seed 11
MEASURED_CEILING = -2


def random_policy(rng: random.Random) -> game.Policy:
    """A policy with every check OFF. Knobs only — that is the point."""
    return game.Policy(
        strategy={f: rng.choice(game.STRATEGIES) for f in FIELDS},
        tolerance=rng.choice(TOLERANCES),
        identifiers={f for f in FIELDS if rng.random() < 0.5},
        checks={c: False for c in game.CHECKS},
        keep_identity_evidence=rng.random() < 0.5,
    )


def tuning_ceiling(trials: int = 4000, seed: int = 11) -> dict:
    rng = random.Random(seed)
    best, best_policy, best_wrong = None, None, None
    for _ in range(trials):
        p = random_policy(rng)
        t = game.play(p)["total"]
        if best is None or t["score"] > best:
            best, best_policy, best_wrong = t["score"], p, t["wrong_accepts"]
    return {"best": best, "wrong_accepts": best_wrong,
            "policy": best_policy, "trials": trials}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    r = tuning_ceiling(a.trials, a.seed)
    print(f"\n  {a.trials} trials, every check off.")
    print(f"  Best score found:  {r['best']}")
    print(f"  Wrong accepts:     {r['wrong_accepts']}")
    print(f"  tolerance          {r['policy'].tolerance}")
    print(f"  identifiers        {sorted(r['policy'].identifiers) or '(none)'}")
    print(f"  keep evidence      {r['policy'].keep_identity_evidence}")
    for f in FIELDS:
        print(f"    {f:18} {r['policy'].strategy[f]}")

    checks = game.play(game.PRESETS["all_checks"]())["total"]
    print(f"\n  For comparison — every check on, knobs left at the brief's "
          f"defaults: {checks['score']}, {checks['wrong_accepts']} wrong.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
