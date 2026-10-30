"""
run_lab.py — process eight multi-document case packages.

    python3 run_lab.py                      # all three stitching strategies
    python3 run_lab.py --strategy reconcile
    python3 run_lab.py --show PKG-008       # one package, in full
    python3 run_lab.py --failures 0.15      # inject async failures
    python3 run_lab.py --paths              # the Blob path design

Where the 32 documents come from is a setting, not an argument:

    DOCINT_PROVIDER=mock     synthetic Query Fields responses, offline, free
    DOCINT_PROVIDER=azure    32 real PDFs through Azure Document Intelligence

Set it in `.env` (see `.env.example`), or override for one run:

    python3 run_lab.py --selftest              # prove the adapter, offline, free
    python3 run_lab.py --make-pdfs             # render docs/PKG-XXX/*.pdf first
    python3 run_lab.py --provider azure
    python3 run_lab.py --provider azure --overask   # ask for fields that do not exist

Writes to out/<provider>/:
    unified/PKG-XXX.json     what the pipeline would return
    multidoc_report.md       the report for your ADR
    stitch_results.csv       every field, every package, every strategy
    di_raw/                  azure only — the untouched service responses
    query_field_report.md    azure only — what asking actually cost
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "multidoc_lab"))

import packages as pk                                            # noqa: E402
import provider as provider_mod                                  # noqa: E402
from config import ConfigError                                   # noqa: E402
from packages import QUERY_FIELDS, INCIDENT_DATE                 # noqa: E402
from pipeline import (AsyncAnalyzer, verify_identity, stitch,    # noqa: E402
                      blob_path, STRATEGIES)

backend = None      # bound to the active provider in main()
OUT = HERE / "out"


def process(pkg: dict, strategy: str, failure_rate: float = 0.0) -> dict:
    az = AsyncAnalyzer(backend, failure_rate=failure_rate)

    # --- submit every document. Nothing blocks. ---
    jobs = [az.submit(pkg["id"], dt) for dt in pkg["docs"]]
    summary = az.await_all(jobs)

    doc_fields = {j.doc_type: j.result for j in summary["succeeded"]}
    missing_types = [j.doc_type for j in summary["failed"] + summary["orphaned"]]

    # --- identity: verify, keep the verdict, drop the evidence ---
    verdict = None
    form = doc_fields.get("case_form", [])
    claimed = {f["field"]: f["value"] for f in form}
    if "identity" in doc_fields:
        verdict = verify_identity(doc_fields["identity"],
                                  claimed.get("applicant_name"),
                                  claimed.get("date_of_birth"),
                                  INCIDENT_DATE)

    # --- stitch what survived ---
    st = stitch(doc_fields, strategy)

    # Identity fields must not survive into the record. Belt and braces:
    # verify_identity already keeps them local, and this asserts it.
    leaked = [k for k in st["unified"] if k in
              ("document_number", "expiry_date", "issuing_country")]

    expected = set(QUERY_FIELDS)
    present = {pk.base_type(d) for d in pkg["docs"]}

    return {
        "package_id": pkg["id"],
        "strategy": strategy,
        "provider": getattr(backend, "name", "mock"),
        "unified": st["unified"],
        "provenance": st["provenance"],
        "conflicts": st["conflicts"],
        # dict(**a, b=...) rather than `a | b`: the merge operator is 3.9+, and
        # the first thing a learner on an older interpreter should hit is the
        # lab, not a TypeError three frames deep.
        "identity_verdict": (dict(verdict.__dict__, passed=verdict.passed)) if verdict else None,
        "documents_expected": sorted(expected),
        "documents_received": sorted(present),
        "documents_missing": sorted(expected - present),
        "async": {"rounds": summary["rounds"],
                  "failed": [j.doc_type for j in summary["failed"]],
                  "orphaned": [j.doc_type for j in summary["orphaned"]]},
        "identity_fields_leaked": leaked,
        "needs_human": bool(st["conflicts"] or missing_types or (verdict and not verdict.passed)
                            or (expected - present)),
    }


def score(res: dict, truth: dict) -> dict:
    """
    The number that matters is WRONG ACCEPTED: values stitched into the
    unified record that are not correct, with no flag attached.
    """
    u = res["unified"]
    wrong, refused, checked = [], 0, 0
    for k in ("annual_income", "account_number"):
        if k not in truth:
            continue
        want, got = truth[k], u.get(k)
        checked += 1
        if got is None:
            # A refusal is not a wrong acceptance. It costs handler time,
            # which is a different and much cheaper kind of cost.
            refused += 1
            continue
        if want in ("CONFLICT", "AMBIGUOUS"):
            wrong.append((k, got, want))
        elif want is None:
            wrong.append((k, got, "should be absent"))
        else:
            ok = (abs(float(got) - float(want)) < 0.05) if isinstance(want, float) and got is not None \
                else (str(got) == str(want))
            if not ok:
                wrong.append((k, got, want))

    ver = res["identity_verdict"]
    # Three states, not two. "Could not verify" is different from "verified
    # wrongly", and a pipeline that reports them the same way is hiding the
    # more dangerous one.
    if ver is None:
        ver_state = "unverified"
    elif ver["passed"] == truth["verified"]:
        ver_state = "ok"
    else:
        ver_state = "wrong"
    ver_ok = ver_state == "ok"
    # Was a value that REQUIRES evidence actually evidenced?
    unevidenced = []
    for k in truth.get("requires_evidence", []):
        pv = res["provenance"].get(k, {})
        if u.get(k) is not None and pv.get("source") == "case_form":
            unevidenced.append(k)

    return {"wrong_accepted": len(wrong), "wrong": wrong, "checked": checked,
            "refused": refused, "unevidenced": unevidenced,
            "verdict_correct": ver_ok, "verdict_state": ver_state,
            "conflicts_found": len(res["conflicts"]),
            "conflicts_expected": truth["conflicts"]}


def run(strategy: str, failure_rate: float, quiet: bool = False):
    rows, tot = [], {"wrong_accepted": 0, "verdict_correct": 0, "conflicts_found": 0,
                     "refused": 0, "unevidenced": 0, "unverified": 0}
    if not quiet:
        print(f"\nStrategy: {strategy}")
        print(f"{'package':<10} {'WRONG':>6} {'refused':>8} {'conflicts':>10} {'verdict':>8}  note")
        print("-" * 78)
    for pid in pk.all_ids():
        p = pk.get(pid)
        res = process(p, strategy, failure_rate)
        sc = score(res, p["truth"])
        res["score"] = sc
        rows.append(res)
        tot["wrong_accepted"] += sc["wrong_accepted"]
        tot["verdict_correct"] += sc["verdict_correct"]
        tot["conflicts_found"] += sc["conflicts_found"]
        tot["refused"] += sc["refused"]
        tot["unevidenced"] += len(sc["unevidenced"])
        tot["unverified"] += (sc["verdict_state"] == "unverified")
        (OUT / "unified" / f"{pid}.json").write_text(json.dumps(res, indent=2, default=str))
        if not quiet:
            flag = "  <-- " + ", ".join(f"{f}={g}" for f, g, _ in sc["wrong"][:1]) if sc["wrong"] else ""
            if not flag and sc["unevidenced"]:
                flag = "  <-- declared, not evidenced: " + ",".join(sc["unevidenced"])
            print(f"{pid:<10} {sc['wrong_accepted']:>6} {sc['refused']:>8} "
                  f"{sc['conflicts_found']:>4}/{sc['conflicts_expected']:<5} "
                  f"{ {'ok':'ok','wrong':'WRONG','unverified':'n/a'}[sc['verdict_state']]:>8}  "
                  f"{p['note'][:24]}{flag}")
    if not quiet:
        print("-" * 78)
        print(f"{'TOTAL':<10} {tot['wrong_accepted']:>6} {tot['refused']:>8} "
              f"{tot['conflicts_found']:>10} {tot['verdict_correct']:>6}/8")
        if tot["unverified"]:
            print(f"\n  {tot['unverified']} package(s) could not be verified at all because a")
            print("  document never arrived. Losing a document does not just lose data —")
            print("  it loses the CHECK that document was there to perform.")
    return rows, tot


def show(pid: str) -> int:
    if pid not in pk.all_ids():
        print(f"No such package. Try: {', '.join(pk.all_ids())}")
        return 1
    p = pk.get(pid)
    print(f"\n{pid} — {p['note']}")
    print(f"  why it matters: {p['truth'].get('why', '-')}")
    print("=" * 76)
    for strat in STRATEGIES:
        res = process(p, strat)
        sc = score(res, p["truth"])
        print(f"\n  STRATEGY: {strat}")
        print(f"    wrong accepted: {sc['wrong_accepted']}    "
              f"conflicts: {sc['conflicts_found']}    "
              f"needs_human: {res['needs_human']}")
        for f, got, want in sc["wrong"]:
            print(f"      WRONG  {f}: stitched '{got}'  should be '{want}'")
        for c in res["conflicts"]:
            vals = "  vs  ".join(f"{v['source']}={v['value']}" for v in c["values"])
            print(f"      CONFLICT {c['field']}: {vals}")
        v = res["identity_verdict"]
        if v:
            print(f"      identity: passed={v['passed']}  checks={v['checks_run']}")
            for n in v["notes"]:
                print(f"                {n}")
        if res["documents_missing"]:
            print(f"      MISSING documents: {res['documents_missing']}")
        if res["identity_fields_leaked"]:
            print(f"      !! IDENTITY FIELDS LEAKED: {res['identity_fields_leaked']}")
    return 0


def paths_demo() -> int:
    print("\nBLOB PATH DESIGN — a path is a policy decision\n")
    for dt in ("case_form", "identity", "payslip", "bank_statement"):
        print("  " + blob_path(region="uksouth", tenant="acme-insurance",
                               retention_class="claims-6y", claim_ref="CLM-2026-4471",
                               doc_type=dt, run_id="run-20260814-0931"))
    print("\n  Every one of these is a prefix operation:")
    print("    delete everything for a tenant after six years  -> prefix")
    print("    prove nothing left the UK region                -> prefix")
    print("    place a legal hold on one claim                 -> prefix")
    print("    find every artefact from one processing run     -> prefix")
    print("\n  Leave retention out of the path and the first one becomes a full")
    print("  scan with a per-object decision. Design this before the first blob.")
    return 0


def write_report(results: dict, failure_rate: float, provider_name: str) -> None:
    with open(OUT / "stitch_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["strategy", "package", "field", "value", "source", "agreement"])
        for strat, (rows, _) in results.items():
            for r in rows:
                for fld, val in r["unified"].items():
                    pv = r["provenance"].get(fld, {})
                    w.writerow([strat, r["package_id"], fld, val,
                                pv.get("source"), pv.get("agreement")])

    md = ["# Multi-document extraction report — DecisionStream AI", "",
          f"Packages: **{len(pk.all_ids())}**   Documents: **{len(pk.all_docs())}**   "
          f"Injected async failure rate: **{failure_rate:.0%}**", "",
          f"Source: **{provider_name}** "
          + ("(synthetic Query Fields responses — the confidences were chosen to "
             "make a teaching point, not measured)" if provider_name == "mock"
             else "(Azure AI Document Intelligence, prebuilt-layout + queryFields "
                  "— measured confidences; see `query_field_report.md`)"), "",
          "## Stitching strategy comparison", "",
          "| Strategy | Wrong accepted | Refused (flagged) | Conflicts surfaced | Verdicts correct |",
          "|---|---|---|---|---|"]
    for strat, (_, t) in results.items():
        md.append(f"| {strat} | **{t['wrong_accepted']}** | {t['refused']} | "
                  f"{t['conflicts_found']} | {t['verdict_correct']}/8 |")

    md += ["", "### How to read this", "",
           "**Wrong accepted** is the only column that can hurt a customer. Those "
           "are values written into the unified record, with no flag, that are "
           "not correct.",
           "",
           "`trust_form` believes the applicant. `trust_evidence` believes the "
           "paperwork. Both produce a complete record and both will be wrong "
           "silently when the two sources disagree for a reason neither strategy "
           "understands. `reconcile` refuses and flags — which costs a handler "
           "time on every conflict, including the trivial ones.", "",
           "## The packages", "", "| Package | What makes it hard |", "|---|---|"]
    for p in pk.PACKAGES:
        md.append(f"| {p['id']} | {p['note']} |")

    md += ["", "## Questions to answer before this goes in the ADR", "",
           "1. Which field is authoritative from which document, and who signed "
           "that precedence table off?",
           "2. PKG-008 contains a bank statement belonging to a different person. "
           "Every field in it is high confidence and internally consistent. What "
           "caught it, and would that check have caught a subtler version?",
           "3. Your identity verification returns a verdict and keeps nothing. "
           "Can you point at the line of code that guarantees that?",
           "4. A package arrives with three of four documents. Do you process it "
           "or hold it, and who decided?",
           "5. An async job never completes. How long before anyone notices, and "
           "what notices?",
           "6. What is in your Blob path, and which retention or residency "
           "operation would be impossible without it?", ""]

    (OUT / "multidoc_report.md").write_text("\n".join(md))


def main() -> int:
    global backend, OUT

    ap = argparse.ArgumentParser(description="Multi-document extraction lab")
    ap.add_argument("--strategy", choices=STRATEGIES)
    ap.add_argument("--show", metavar="PKG_ID")
    ap.add_argument("--failures", type=float, default=0.0,
                    help="async failure rate, e.g. 0.15")
    ap.add_argument("--paths", action="store_true")
    ap.add_argument("--provider", choices=("mock", "azure"),
                    help="override DOCINT_PROVIDER from .env for this run")
    ap.add_argument("--make-pdfs", action="store_true",
                    help="render the 32 documents to docs/ and exit "
                         "(what the azure provider posts)")
    ap.add_argument("--overask", action="store_true",
                    help="azure only — also ask each document for fields it "
                         "does not contain, and see what comes back")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the azure adapter reproduces the mock pipeline, "
                         "offline, before you spend anything")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print("DecisionStream AI — multi-document extraction lab")
    print("=" * 78)

    if args.selftest:
        import selftest
        print("\nAdapter self-test — no network, no cost.\n")
        return selftest.run(args.verbose)

    if args.make_pdfs:
        import make_pdfs
        from config import get_settings
        doc_dir = get_settings(args.provider).doc_dir
        print(f"\nRendering {len(pk.all_docs())} documents to {doc_dir}/\n")
        made = make_pdfs.make_all(doc_dir)
        print(f"\n{len(made)} PDFs written. These are what "
              f"DOCINT_PROVIDER=azure posts to the service.")
        return 0

    if args.paths:
        return paths_demo()

    # ----------------------------------------------------------------------
    # The switch. Everything below this line is provider-agnostic.
    # ----------------------------------------------------------------------
    try:
        backend, settings = provider_mod.get(args.provider, overask=args.overask)
    except ConfigError as e:
        print(f"\nConfiguration error:\n  {e}\n")
        return 2
    except Exception as e:                       # azure preflight failures
        print(f"\n{type(e).__name__}:\n  {e}\n")
        return 2

    print(backend.describe())
    OUT = settings.out_dir / settings.provider
    (OUT / "unified").mkdir(parents=True, exist_ok=True)

    if args.show:
        return show(args.show.upper())

    if settings.provider == "azure":
        print(f"\n  {len(pk.all_docs())} documents to analyse. The first run is "
              f"billed and slow;\n  every run after it reads out/azure/di_raw/ "
              f"and is neither.")
        if args.failures:
            # Say this out loud. The failure injection happens AFTER the
            # service has answered, so the analysis is performed and billed and
            # then thrown away. That is the correct simulation — losing a
            # result you already paid for is the failure mode that actually
            # happens — but nobody should discover the billing part later.
            print(f"\n  --failures {args.failures:.0%} on the azure provider "
                  f"discards results the service\n  already returned. The "
                  f"analysis still happened and was still billed.")

    strats = [args.strategy] if args.strategy else list(STRATEGIES)
    try:
        results = {s: run(s, args.failures) for s in strats}
    except Exception as e:
        # A billed batch that stops loudly beats one that half-succeeds and
        # writes a report nobody knows is incomplete.
        print(f"\n{type(e).__name__}:\n  {e}\n")
        return 1

    write_report(results, args.failures, settings.provider)

    if len(strats) > 1:
        print("\n" + "=" * 78)
        for s in strats:
            t = results[s][1]
            print(f"  {s:<16} {t['wrong_accepted']:>2} wrong accepted, "
                  f"{t['refused']:>2} refused, "
                  f"{t['conflicts_found']:>2} conflicts surfaced, "
                  f"{t['verdict_correct']}/8 verdicts correct")
        print("\n  Every strategy finds the same conflicts. What differs is what")
        print("  they DO about them — and only one of them declines to guess.")

    print(f"\nWritten: {OUT/'multidoc_report.md'}")
    print(f"         {OUT/'stitch_results.csv'}")
    print(f"         {OUT/'unified'}/  ({len(pk.all_ids())} unified records)")

    if settings.provider == "azure":
        import azure_multidoc
        (OUT / "query_field_report.md").write_text(
            azure_multidoc.query_field_report(backend))
        print(f"         {OUT/'query_field_report.md'}   <-- read this one")
        print(f"         {OUT/'di_raw'}/  (untouched service responses)")

        waits = azure_multidoc.RATE_LIMIT_WAITS
        if waits:
            print(f"\n  Rate limited {len(waits)} times, {sum(waits):.0f}s spent "
                  f"waiting on Retry-After.")
            print("  That is a throughput number, not an error. Quote it when "
                  "somebody asks")
            print("  how long 4,000 documents a month takes on this tier.")

        if azure_multidoc.PAGE_TRUNCATIONS:
            print("\n" + "=" * 78)
            print("  PAGES THE SERVICE DID NOT READ")
            for note in azure_multidoc.PAGE_TRUNCATIONS:
                print(f"    {note}")
            print("\n  A free-tier (F0) resource analyses the first two pages and "
                  "stops.")
            print("  Every query field in this lab is on page 1 by design, so if "
                  "you are")
            print("  seeing this, a document grew. Check that before blaming the "
                  "extraction.")

    print("\nNow open multidoc_report.md and answer the six questions at the bottom.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
