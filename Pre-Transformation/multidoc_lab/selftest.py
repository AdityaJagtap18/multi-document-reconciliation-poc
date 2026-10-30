"""
selftest.py — prove the machinery, offline, before you spend anything.

    python3 run_lab.py --selftest

No network. No key. No cost. It builds a synthetic Document Intelligence
response for each of the 32 documents, pushes it through the REAL azure
adapter, and asserts that what comes out the other side is what the mock
provider produces.

WHY THIS EXISTS
---------------
The azure path has exactly one place it can silently go wrong: `adapt()`. A
mistake there does not raise. It returns fewer fields, or subtly different
values, and the pipeline downstream carries on and writes a report. You would
find out when a number in a client presentation did not match.

So the adapter is tested against the mock, which is the only ground truth
available, and the test runs for free. Run it after you change anything at the
vendor boundary and before you spend a penny on a re-run.

WHAT IT CHECKS, AND WHY EACH ONE IS HERE
----------------------------------------
  1. ADAPTER FIDELITY   a synthetic service response for every one of the 32
                        documents survives `adapt()` with the same fields, the
                        same values and the same confidences as the mock.
  2. THE THREE STATES   a field that is absent, a field returned with
                        confidence 0 and no value, and a field returned with a
                        value are three different things. The first two must
                        never become fields; the third must.
  3. IDENTITY BOUNDARY  no run of the pipeline, on any package, under any
                        strategy, may leave a licence number in the record.
  4. TOLERANCE          an account number differing by one digit must be a
                        conflict, not a match. This is PKG-005 and it is the
                        one that nearly got through.
  5. DETERMINISM        the mock provider's headline numbers are pinned. If
                        they move, something changed that you did not mean to
                        change.
"""

from __future__ import annotations

import azure_multidoc
import packages as pk
from pipeline import STRATEGIES, stitch, verify_identity

PASS, FAIL = "  ok  ", "  FAIL"
_results: list[tuple[bool, str, str]] = []


def check(cond: bool, name: str, detail: str = "") -> bool:
    _results.append((bool(cond), name, detail))
    return bool(cond)


# --------------------------------------------------------------------------
# A synthetic service response, in the shape the real API returns.
#
# This is the contract the adapter is written against, transcribed from a live
# response. If Microsoft changes the shape, this file is where the lab finds
# out — and it finds out for free rather than mid-run.
# --------------------------------------------------------------------------
def fake_response(fields: list[dict], pages: int = 1) -> dict:
    return {
        "status": "succeeded",
        "analyzeResult": {
            "apiVersion": "2024-11-30",
            "modelId": "prebuilt-layout",
            "pages": [{"pageNumber": n + 1} for n in range(pages)],
            "documents": [{
                "docType": "prebuilt-layout",
                "fields": {
                    f["field"]: {
                        "type": "string",
                        "valueString": str(f["value"]),
                        "content": str(f["value"]),
                        "confidence": f["confidence"],
                        "boundingRegions": [{"pageNumber": f.get("page", 1),
                                             "polygon": [0, 0, 1, 0, 1, 1, 0, 1]}],
                    } for f in fields
                },
            }],
        },
    }


# ==========================================================================
# 1. ADAPTER FIDELITY
# ==========================================================================
def test_adapter_round_trip() -> None:
    for pkg_id, doc_type in pk.all_docs():
        mock_fields = pk.fields_for(pkg_id, doc_type)
        asked = pk.query_fields_for(doc_type)
        payload = fake_response(mock_fields)
        got, meta = azure_multidoc.adapt(payload, asked)

        want = {f["field"]: str(f["value"]) for f in mock_fields}
        have = {f["field"]: f["value"] for f in got}
        check(have == want, f"adapt {pkg_id}/{doc_type}",
              f"{len(have)} fields, expected {len(want)}")

        conf_ok = all(
            abs(f["confidence"] - next(m["confidence"] for m in mock_fields
                                       if m["field"] == f["field"])) < 1e-9
            for f in got)
        check(conf_ok, f"confidence {pkg_id}/{doc_type}")
        check(meta["empty"] == [], f"nothing empty {pkg_id}/{doc_type}",
              str(meta["empty"]))


# ==========================================================================
# 2. THE THREE STATES OF A QUERY FIELD
# ==========================================================================
def test_three_states() -> None:
    payload = {
        "analyzeResult": {
            "pages": [{"pageNumber": 1}],
            "documents": [{"fields": {
                # answered — a value and a confidence
                "account_number": {"type": "string", "valueString": "44182903",
                                   "content": "44182903", "confidence": 0.96},
                # empty — the key is present, the service found nothing.
                # This is the shape the live service returns, verified against
                # it: type and a zero confidence, and no valueString at all.
                "sort_code": {"type": "string", "confidence": 0},
                # "statement_period" is simply absent from the response.
            }}],
        }
    }
    asked = ["account_number", "sort_code", "statement_period"]
    fields, meta = azure_multidoc.adapt(payload, asked)

    check([f["field"] for f in fields] == ["account_number"],
          "only answered fields become fields", str([f["field"] for f in fields]))
    check(sorted(meta["empty"]) == ["sort_code", "statement_period"],
          "absent and value-less both count as empty", str(meta["empty"]))
    check(all(f["value"] != "" for f in fields),
          "no empty string ever enters the record")


# ==========================================================================
# 3. THE IDENTITY BOUNDARY
# ==========================================================================
def test_identity_never_leaks() -> None:
    forbidden = {"document_number", "expiry_date", "issuing_country"}
    leaked_anywhere = []
    for pkg_id in pk.all_ids():
        pkg = pk.get(pkg_id)
        for strategy in STRATEGIES:
            st = stitch(pkg["docs"], strategy)
            leaked_anywhere += [f"{pkg_id}/{strategy}/{k}"
                                for k in st["unified"] if k in forbidden]
    check(not leaked_anywhere, "no identity evidence in any unified record",
          ", ".join(leaked_anywhere))

    # And the verdict object itself carries none of it.
    pkg = pk.get("PKG-001")
    v = verify_identity(pkg["docs"]["identity"], "[PERSON_01]", "1987-04-12",
                        pk.INCIDENT_DATE)
    body = repr(v.__dict__)
    check("SMITH8704127AB9CD" not in body, "licence number absent from verdict")
    check(v.passed, "PKG-001 identity verifies")


# ==========================================================================
# 4. TOLERANCE NEVER APPLIES TO AN IDENTIFIER
# ==========================================================================
def test_identifier_tolerance() -> None:
    docs = {
        "case_form": [{"field": "account_number", "value": "20558193",
                       "confidence": 0.88, "page": 1}],
        "bank_statement": [{"field": "account_number", "value": "20558198",
                            "confidence": 0.96, "page": 1}],
    }
    st = stitch(docs, "reconcile")
    check(any(c["field"] == "account_number" for c in st["conflicts"]),
          "one-digit account difference is a CONFLICT",
          "a 2% numeric tolerance would call these equal")
    check(st["unified"].get("account_number") is None,
          "reconcile refuses rather than picking one")


# ==========================================================================
# 5. THE MOCK'S HEADLINE NUMBERS ARE PINNED
# ==========================================================================
EXPECTED = {"trust_form": 4, "trust_evidence": 2, "reconcile": 0}


def test_pinned_totals() -> None:
    import tempfile
    from pathlib import Path

    import provider as provider_mod
    import run_lab

    run_lab.backend, _ = provider_mod.get("mock")
    # Scored, not published. The self-test must not overwrite the out/ that a
    # learner is reading, and must not create one if they have not run yet.
    run_lab.OUT = Path(tempfile.mkdtemp(prefix="multidoc-selftest-"))
    (run_lab.OUT / "unified").mkdir(parents=True, exist_ok=True)
    for strategy, want in EXPECTED.items():
        rows, tot = run_lab.run(strategy, 0.0, quiet=True)
        check(tot["wrong_accepted"] == want,
              f"{strategy} accepts {want} wrong values",
              f"got {tot['wrong_accepted']}")
    check(tot["conflicts_found"] == 6, "six conflicts surfaced",
          f"got {tot['conflicts_found']}")


# ==========================================================================
def run(verbose: bool = False) -> int:
    _results.clear()
    for fn in (test_adapter_round_trip, test_three_states,
               test_identity_never_leaks, test_identifier_tolerance,
               test_pinned_totals):
        fn()

    failed = [r for r in _results if not r[0]]
    for ok, name, detail in _results:
        if verbose or not ok:
            print(f"{PASS if ok else FAIL}  {name}" + (f"   {detail}" if detail else ""))

    print(f"\n  {len(_results) - len(failed)}/{len(_results)} checks passed.")
    if failed:
        print("\n  The adapter does not reproduce the mock. Fix that before you "
              "run against\n  the service — a billed run will not tell you which "
              "of the two is wrong.")
        return 1
    print("  The azure adapter reproduces the mock pipeline exactly. Safe to spend.")
    return 0
