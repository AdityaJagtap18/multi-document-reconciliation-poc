"""
selftest_game.py — every test for The Reconciliation Game.

Standard library only, no network, no cost. Mirrors the harness in
multidoc_lab/selftest.py so that a learner who has read one can read the other.

    python3 reconciliation_game/selftest_game.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reconciliation_game.corpus as corpus            # noqa: E402

PASS = FAIL = 0


def check(cond: bool, name: str, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))
    return bool(cond)


# --------------------------------------------------------------------------
# 1. The corpus is complete.
#
# The lab scored two fields per package. The game scores six, so every package
# needs a truth value for every field. A missing key here is not a crash later
# — it is a field silently dropped from scoring, which is worse.
# --------------------------------------------------------------------------
def test_truth_covers_every_field() -> None:
    for pid in corpus.all_ids():
        t = corpus.truth(pid)
        for f in corpus.FIELDS:
            check(f in t, f"truth {pid}.{f}", "no truth value for this field")


def test_every_package_has_a_hint() -> None:
    for pid in corpus.all_ids():
        check(pid in corpus.HINTS and bool(corpus.HINTS[pid]),
              f"hint {pid}", "no hint text")


import reconciliation_game.game as game                # noqa: E402
from pipeline import stitch                            # noqa: E402


# --------------------------------------------------------------------------
# 2. THE PIN.
#
# The game reimplements reconciliation because pipeline.stitch() is reference
# code learners read in Step 1 of the lab, and bolting six knobs onto it would
# destroy the thing that makes it readable. Two implementations of the same
# rules drift. This is what stops them.
#
# The game's "lab" preset must reproduce stitch(..., "reconcile") exactly, on
# every package, for the unified record AND the provenance.
# --------------------------------------------------------------------------
def test_pinned_to_the_lab() -> None:
    policy = game.PRESETS["lab"]()
    for pid in corpus.all_ids():
        pkg = corpus.get(pid)
        res = game.apply_policy(pkg, policy)
        want = stitch(pkg["docs"], "reconcile")

        check(res["unified"] == want["unified"], f"pin unified {pid}",
              f"game {res['unified']} != lab {want['unified']}")

        for f in corpus.FIELDS:
            g = res["provenance"].get(f, {})
            w = want["provenance"].get(f, {})
            check(g.get("source") == w.get("source"),
                  f"pin provenance.source {pid}.{f}",
                  f"game {g.get('source')} != lab {w.get('source')}")
            check(g.get("agreement") == w.get("agreement"),
                  f"pin provenance.agreement {pid}.{f}",
                  f"game {g.get('agreement')} != lab {w.get('agreement')}")


def test_identity_evidence_stays_out_by_default() -> None:
    """The lab's own invariant. It must not weaken because a game wraps it."""
    banned = ("document_number", "expiry_date", "issuing_country")
    for name, make in game.PRESETS.items():
        policy = make()
        if policy.keep_identity_evidence:
            continue
        for pid in corpus.all_ids():
            res = game.apply_policy(corpus.get(pid), policy)
            leaked = [k for k in res["unified"] if k in banned]
            check(not leaked, f"no leak {name}/{pid}", f"leaked {leaked}")


# --------------------------------------------------------------------------
# 3. Every check catches the package it claims to catch, and none of them
#    fires on PKG-001. A check that fires on the clean package is a check
#    that costs flags for nothing, and a player is entitled to switch it off.
# --------------------------------------------------------------------------
CATCHES = {
    "identity_match":    "PKG-002",
    "identity_validity": "PKG-003",
    "cross_doc_name":    "PKG-008",
    "evidence_required": "PKG-006",
    "period_coherence":  "PKG-007",
}


def _only(check_name: str) -> "game.Policy":
    p = game.PRESETS["brief"]()
    p.checks = {c: (c == check_name) for c in game.CHECKS}
    p.keep_identity_evidence = False
    return p


def test_each_check_catches_its_package() -> None:
    for cname, pid in CATCHES.items():
        res = game.apply_policy(corpus.get(pid), _only(cname))
        fired = [f for f in res["flags"] if f["check"] == cname]
        check(bool(fired), f"{cname} catches {pid}", "check did not fire")


def test_no_check_fires_on_the_clean_package() -> None:
    for cname in game.CHECKS:
        res = game.apply_policy(corpus.get("PKG-001"), _only(cname))
        fired = [f for f in res["flags"] if f["check"] == cname]
        check(not fired, f"{cname} silent on PKG-001",
              f"fired: {[f['why'] for f in fired]}")


def test_tolerance_guard_protects_the_account_number() -> None:
    """
    PKG-005's account numbers differ by 5 in twenty million. Slide the
    tolerance to 10% and a numeric comparison calls them equal.
    """
    loose = game.PRESETS["brief"]()
    loose.tolerance = 0.10
    loose.identifiers = set()
    loose.keep_identity_evidence = False

    off = game.apply_policy(corpus.get("PKG-005"), loose)
    check(not off["conflicts"] or
          all(c["field"] != "account_number" for c in off["conflicts"]),
          "tolerance_guard off: the wrong account slips through",
          "expected the loose tolerance to hide the conflict")

    loose.checks["tolerance_guard"] = True
    on = game.apply_policy(corpus.get("PKG-005"), loose)
    check(any(c["field"] == "account_number" for c in on["conflicts"]),
          "tolerance_guard on: the conflict is visible",
          "the guard did not force an exact comparison")


def test_completeness_gate_fires_only_when_a_document_is_missing() -> None:
    p = _only("completeness_gate")
    missing = game.apply_policy(corpus.get("PKG-006"), p)   # no payslip
    check(any(f["check"] == "completeness_gate" for f in missing["flags"]),
          "completeness_gate catches the missing payslip")
    whole = game.apply_policy(corpus.get("PKG-001"), p)
    check(not any(f["check"] == "completeness_gate" for f in whole["flags"]),
          "completeness_gate silent on a whole package")


def test_identity_check_does_not_save_pkg_008() -> None:
    """
    The point of PKG-008. Its identity document matches the form perfectly,
    so identity verification PASSES and the package is still wrong. Only a
    cross-document name check catches it.
    """
    res = game.apply_policy(corpus.get("PKG-008"), _only("identity_match"))
    check(res["identity_verdict"]["passed"] is True,
          "PKG-008 identity verdict passes")
    check(not any(f["check"] == "identity_match" for f in res["flags"]),
          "identity_match cannot see PKG-008")


# --------------------------------------------------------------------------
# 4. Scoring.
#
# The hand-computed case is PKG-001 under the lab preset: six fields, all
# agreeing, all correct, no checks, no retained evidence. Six correct accepts
# and nothing else.
# --------------------------------------------------------------------------
def test_clean_package_scores_six_correct_accepts() -> None:
    policy = game.PRESETS["lab"]()
    res = game.apply_policy(corpus.get("PKG-001"), policy)
    sc = game.score_package(res, corpus.truth("PKG-001"), policy)
    check(sc["score"] == 6 * game.POINTS["correct_accept"],
          "PKG-001 scores 6 correct accepts",
          f"got {sc['score']}, expected {6 * game.POINTS['correct_accept']}")
    check(sc["wrong_accepts"] == 0, "PKG-001 has no wrong accepts")


def test_declining_an_unanswerable_field_is_correct() -> None:
    """
    PKG-007's income truth is AMBIGUOUS. There is no right value, so
    returning nothing IS the right answer and must score as one.
    """
    policy = game.PRESETS["lab"]()
    res = game.apply_policy(corpus.get("PKG-007"), policy)
    sc = game.score_package(res, corpus.truth("PKG-007"), policy)
    income = next(d for d in sc["detail"] if d["field"] == "annual_income")
    check(income["outcome"] == "correct",
          "declining AMBIGUOUS income scores as correct",
          f"outcome was {income['outcome']}")


def test_retained_evidence_is_the_most_expensive_setting() -> None:
    keep = game.PRESETS["lab"]()
    keep.keep_identity_evidence = True
    drop = game.PRESETS["lab"]()
    a = game.play(keep)["total"]["score"]
    b = game.play(drop)["total"]["score"]
    check(b - a == 8 * abs(game.POINTS["evidence_retained"]),
          "keeping identity evidence costs 300 a package",
          f"difference was {b - a}")


def test_every_preset_runs() -> None:
    for name, make in game.PRESETS.items():
        out = game.play(make())
        check(isinstance(out["total"]["score"], int), f"preset {name} scores",
              f"got {out['total']}")


def test_scoring_is_deterministic() -> None:
    p = game.PRESETS["brief"]()
    for rate in (0.0, 0.2):
        a = game.play(p, failure_rate=rate)["total"]["score"]
        b = game.play(p, failure_rate=rate)["total"]["score"]
        check(a == b, f"deterministic at failure_rate={rate}", f"{a} != {b}")


# --------------------------------------------------------------------------
# 5. THE PROPERTY THE GAME MUST HAVE.
#
# The game only teaches the right thing while validation strictly dominates
# tuning. This is the test that stops somebody "improving" the scoring
# constants and quietly inverting the lesson. It is the most important test
# in the file.
# --------------------------------------------------------------------------
import reconciliation_game.search as search             # noqa: E402


def test_validation_beats_tuning() -> None:
    ceiling = search.tuning_ceiling(trials=1500, seed=11)
    bar = max(ceiling["best"], search.MEASURED_CEILING)
    all_checks = game.play(game.PRESETS["all_checks"]())["total"]
    flag_all = game.play(game.PRESETS["flag_everything"]())["total"]
    tight = game.play(game.PRESETS["all_checks_tight"]())["total"]

    check(all_checks["score"] > bar,
          "all checks on beats the best tuning found",
          f"checks {all_checks['score']} vs tuning ceiling {bar}")
    check(all_checks["wrong_accepts"] == 0,
          "all checks on reaches zero wrong accepts",
          f"{all_checks['wrong_accepts']} wrong accepts remain")
    check(flag_all["score"] < all_checks["score"],
          "refusing everything is not the answer either",
          f"flag_everything {flag_all['score']} vs {all_checks['score']}")
    check(tight["score"] <= all_checks["score"],
          "tightening on top of working validation buys nothing",
          f"tight {tight['score']} > all_checks {all_checks['score']}")


ALL = [test_truth_covers_every_field, test_every_package_has_a_hint,
       test_pinned_to_the_lab, test_identity_evidence_stays_out_by_default,
       test_each_check_catches_its_package,
       test_no_check_fires_on_the_clean_package,
       test_tolerance_guard_protects_the_account_number,
       test_completeness_gate_fires_only_when_a_document_is_missing,
       test_identity_check_does_not_save_pkg_008,
       test_clean_package_scores_six_correct_accepts,
       test_declining_an_unanswerable_field_is_correct,
       test_retained_evidence_is_the_most_expensive_setting,
       test_every_preset_runs,
       test_scoring_is_deterministic,
       test_validation_beats_tuning]


def main() -> int:
    print("\nThe Reconciliation Game — self-test")
    print("=" * 74 + "\n")
    for t in ALL:
        t()
    print(f"\n  {PASS}/{PASS + FAIL} checks passed.")
    if FAIL:
        print(f"  {FAIL} FAILED.\n")
        return 1
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
