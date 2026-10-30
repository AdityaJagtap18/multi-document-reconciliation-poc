"""
game.py — The Reconciliation Game.

THE POINT OF THE GAME
---------------------
You are given eight case packages, up to five documents each, as Query Fields
returned them. One job: decide what goes into the unified record, and what
goes to a human.

Day 14 gave you a confidence slider. There is no slider here, because there is
no threshold anywhere in this pipeline — confidence is reported and never
gated on. What you have instead is a RECONCILIATION POLICY:

    TOLERANCE     how close two numbers have to be to count as the same number
    IDENTIFIERS   which fields are compared exactly, ignoring tolerance
    STRATEGY      per field: when four documents disagree, who wins
    CHECKS        cross-document validators that can refuse a value outright

and one more, which looks like diligence and is the most expensive setting on
the board:

    KEEP_IDENTITY_EVIDENCE   attach the licence number and expiry to the
                             record "so a reviewer can re-check it later"

WHAT YOU WILL DISCOVER
----------------------
The knobs have a ceiling and it is well below what the checks are worth. That
is the same finding as Day 14, reached through a different mechanism, and the
leaderboard is what proves it rather than a slide asserting it.

    Tuning moves WHO LOOKS AT a value.
    Validation changes WHETHER THE VALUE IS RIGHT.

And one finding Day 14 could not teach, because it only had one document per
case: at a non-zero failure rate a check can disappear. Not fail — disappear,
because the document it needed never arrived. One value cannot disagree with
anything.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field as dc_field
from datetime import date

import reconciliation_game.corpus as corpus
from reconciliation_game.corpus import FIELDS, PRECEDENCE, INCIDENT_DATE, base_type

import mock_multidoc                                              # noqa: E402
from pipeline import AsyncAnalyzer, verify_identity               # noqa: E402


# ==========================================================================
# SCORING
#
# The asymmetry is the whole design and it is inherited from Day 14. One wrong
# acceptance costs more than seventy flags, because a flag costs a handler
# half a minute and somebody knows it happened, whereas a wrongly accepted
# account number sends the payment to a stranger and nobody finds out until
# they complain.
# ==========================================================================
POINTS = {
    "correct_accept": 10,
    "wrong_accept": -150,
    "flag": -2,
    "missing_unflagged": -20,
    # The value is RIGHT and it is unevidenced. Charging a wrong-accept
    # penalty for a right answer would be dishonest scoring; charging nothing
    # would make `evidence_required` a check nobody rationally switches on.
    "unevidenced_accept": -60,
    # NOT "the verdict was computed wrongly". verify_identity() gets the
    # verdict right on all eight packages with no checks on at all. What the
    # lab does not do is ACT on it, and this is the cost of not acting.
    "verdict_ignored": -200,
    "verdict_impossible_unflagged": -40,
    "evidence_retained": -300,
}

STRATEGIES = ("trust_form", "trust_evidence", "reconcile")

CHECKS = {
    "identity_match":    "The name and date of birth on the identity document "
                         "must match the form",
    "identity_validity": "The identity document must not have expired before "
                         "the incident",
    "cross_doc_name":    "The same person must appear on every document that "
                         "carries a name",
    "evidence_required": "Income and account number may not come from the "
                         "applicant's own form alone",
    "period_coherence":  "Two payslips covering different periods cannot both "
                         "feed one income figure",
    "completeness_gate": "Every expected document must have arrived — a "
                         "missing document is a missing check",
    "tolerance_guard":   "Numeric tolerance must never be applied to an "
                         "identifier",
}

# Fields that are names made of digits rather than quantities. `tolerance_guard`
# forces these into the identifier set; without it a player can slide tolerance
# up and start accepting an account number that is off by one.
IDENTIFIER_SHAPED = {"account_number", "claim_reference"}

IDENTITY_EVIDENCE = ("document_number", "expiry_date", "issuing_country")


@dataclass
class Policy:
    strategy: dict = dc_field(default_factory=lambda: {f: "trust_form" for f in FIELDS})
    tolerance: float = 0.02
    identifiers: set = dc_field(default_factory=lambda: {"account_number"})
    checks: dict = dc_field(default_factory=lambda: {c: False for c in CHECKS})
    keep_identity_evidence: bool = True

    def copy(self) -> "Policy":
        return Policy(strategy=dict(self.strategy), tolerance=self.tolerance,
                      identifiers=set(self.identifiers), checks=dict(self.checks),
                      keep_identity_evidence=self.keep_identity_evidence)

    def to_dict(self) -> dict:
        return {"tolerance": self.tolerance,
                "identifiers": sorted(self.identifiers),
                "strategy": dict(self.strategy),
                "checks": dict(self.checks),
                "keep_identity_evidence": self.keep_identity_evidence}

    @staticmethod
    def from_dict(d: dict) -> "Policy":
        p = Policy()
        p.tolerance = float(d.get("tolerance", p.tolerance))
        p.identifiers = set(d.get("identifiers", p.identifiers))
        p.strategy = {f: d.get("strategy", {}).get(f, "trust_form") for f in FIELDS}
        p.checks = {c: bool(d.get("checks", {}).get(c, False)) for c in CHECKS}
        p.keep_identity_evidence = bool(d.get("keep_identity_evidence", True))
        return p


# Which document supplies which field, under which of its own names. This is
# the lab's FIELD_SOURCES, restated here rather than imported, because the
# game's copy is the one the pin test holds to account.
FIELD_SOURCES = {
    "applicant_name":  {"case_form": "applicant_name", "identity": "holder_name",
                        "bank_statement": "account_holder_name", "payslip": "employee_name"},
    "date_of_birth":   {"case_form": "date_of_birth", "identity": "date_of_birth"},
    "annual_income":   {"case_form": "annual_income", "payslip": "gross_monthly_pay"},
    "employer_name":   {"case_form": "employer_name", "payslip": "employer_name"},
    "account_number":  {"case_form": "account_number", "bank_statement": "account_number"},
    "claim_reference": {"case_form": "claim_reference"},
}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _collect(doc_fields: dict, target: str) -> list:
    """Every (doc_type, value, confidence) this package offers for one field.

    A payslip's monthly figure is multiplied to an annual one HERE rather than
    at comparison time, so that what gets compared is two annual incomes
    rather than an annual and a monthly one.
    """
    found = []
    sources = FIELD_SOURCES[target]
    for dt, flds in doc_fields.items():
        base = base_type(dt)
        key = sources.get(base if base in sources else dt)
        if not key:
            continue
        for f in flds:
            if f["field"] != key:
                continue
            val = f["value"]
            if target == "annual_income" and base == "payslip":
                m = _num(val)
                val = round(m * 12, 2) if m is not None else val
            found.append((dt, val, f["confidence"]))
    return found


def _agree(target: str, found: list, policy: Policy) -> bool:
    """
    Do these documents agree?

    CRITICAL: tolerance applies to QUANTITIES, never to IDENTIFIERS. An
    account number that differs by 5 is not "within 2%" — it is a different
    account, and the payment goes somewhere else. This is the line PKG-005
    walks through when a player slides the tolerance up.
    """
    vals = [v for _, v, _ in found]
    idents = set(policy.identifiers)
    if policy.checks.get("tolerance_guard"):
        idents |= IDENTIFIER_SHAPED
    if target in idents:
        return len({str(v).strip() for v in vals}) == 1
    nums = [_num(v) for v in vals]
    if all(n is not None for n in nums):
        hi, lo = max(nums), min(nums)
        return (hi - lo) <= policy.tolerance * max(1.0, abs(hi))
    return len({_norm_name(v) for v in vals}) == 1


def _resolve(target: str, found: list, policy: Policy) -> tuple:
    """A conflict, and what the policy does about it. Returns (value, source, agreement)."""
    strat = policy.strategy.get(target, "trust_form")
    order = PRECEDENCE.get(target, [])

    if strat == "trust_form":
        pick = next((f for f in found if f[0] == "case_form"), found[0])
        return pick[1], pick[0], "CONFLICT_resolved_to_form"
    if strat == "trust_evidence":
        def rank(item):
            b = base_type(item[0])
            return order.index(b) if b in order else 99
        pick = sorted(found, key=rank)[0]
        return pick[1], pick[0], "CONFLICT_resolved_by_precedence"
    return None, None, "CONFLICT_unresolved"


def apply_policy(pkg: dict, policy: Policy, failure_rate: float = 0.0) -> dict:
    az = AsyncAnalyzer(mock_multidoc, failure_rate=failure_rate)
    jobs = [az.submit(pkg["id"], dt) for dt in pkg["docs"]]
    summary = az.await_all(jobs)

    doc_fields = {j.doc_type: j.result for j in summary["succeeded"]}
    expected = set(corpus.QUERY_FIELDS)
    present = {base_type(d) for d in doc_fields}
    documents_missing = sorted(expected - present)

    # Identity: verify, keep the verdict, discard the evidence.
    verdict = None
    claimed = {f["field"]: f["value"] for f in doc_fields.get("case_form", [])}
    if "identity" in doc_fields:
        verdict = verify_identity(doc_fields["identity"],
                                  claimed.get("applicant_name"),
                                  claimed.get("date_of_birth"),
                                  INCIDENT_DATE)

    unified, provenance, conflicts, sources = {}, {}, [], {}
    for target in FIELDS:
        found = _collect(doc_fields, target)
        if not found:
            continue
        sources[target] = [dt for dt, _, _ in found]
        if _agree(target, found, policy):
            dt, val, conf = max(found, key=lambda x: x[2])
            unified[target] = val
            provenance[target] = {"source": dt, "confidence": conf,
                                  "agreement": "all_agree"}
            continue
        conflicts.append({"field": target,
                          "values": [{"source": dt, "value": v, "confidence": c}
                                     for dt, v, c in found]})
        val, src, agreement = _resolve(target, found, policy)
        unified[target] = val
        provenance[target] = {"source": src,
                              "confidence": next((c for d, v, c in found if d == src), None),
                              "agreement": agreement}

    res = {
        "package_id": pkg["id"],
        "unified": unified,
        "provenance": provenance,
        "conflicts": conflicts,
        "sources": sources,
        "identity_verdict": (dict(verdict.__dict__, passed=verdict.passed)
                             if verdict else None),
        "retained_evidence": {},
        "documents_missing": documents_missing,
        "flags": [],
        "package_flagged": False,
    }

    # The knob that looks like diligence. Note where it happens: AFTER
    # verify_identity has returned and gone out of scope, by deliberately
    # reaching back into the document for data the verdict did not need.
    # That is exactly how this goes wrong in a real codebase.
    if policy.keep_identity_evidence and "identity" in doc_fields:
        raw = {f["field"]: f["value"] for f in doc_fields["identity"]}
        res["retained_evidence"] = {k: raw[k] for k in IDENTITY_EVIDENCE if k in raw}

    run_checks(res, doc_fields, policy)
    return res


def _flag(res: dict, check_name: str, why: str, field: str = None) -> None:
    res["flags"].append({"scope": "field" if field else "package",
                         "field": field, "check": check_name, "why": why})
    if field is None:
        res["package_flagged"] = True


def run_checks(res: dict, doc_fields: dict, policy: Policy) -> None:
    """
    Seven cross-document validators. Six of them add information the
    reconciliation policy cannot get from any single document; `tolerance_guard`
    is the odd one out and removes a foot-gun from a knob instead.

    A check flags either ONE FIELD (that value goes to a human) or the WHOLE
    PACKAGE (all of it does). Identity and cross-document-identity failures are
    package-scoped, because if you cannot establish who this is, nothing else
    in the record means anything.
    """
    on = policy.checks
    verdict = res["identity_verdict"]

    if on.get("identity_match") and verdict is not None:
        if verdict["name_matches"] is False:
            _flag(res, "identity_match",
                  "the name on the identity document is not the name on the form")
        if verdict["dob_matches"] is False:
            _flag(res, "identity_match",
                  "the date of birth on the identity document is not the one on the form")

    if on.get("identity_validity") and verdict is not None:
        if verdict["valid_at_incident"] is False:
            _flag(res, "identity_validity",
                  f"the identity document had expired before the incident on {INCIDENT_DATE}")

    # PKG-008. Every name-bearing document must name the same person. The
    # identity check cannot see this, because the identity document is one of
    # the ones that agrees.
    if on.get("cross_doc_name"):
        names = {}
        for dt, flds in doc_fields.items():
            key = FIELD_SOURCES["applicant_name"].get(base_type(dt))
            for f in flds:
                if f["field"] == key:
                    names.setdefault(_norm_name(f["value"]), []).append(dt)
        if len(names) > 1:
            who = "; ".join(f"{', '.join(v)}" for v in names.values())
            _flag(res, "cross_doc_name",
                  f"the documents in this package do not name the same person ({who})")

    # PKG-006, and PKG-004/005 under trust_form. A value the applicant asserted
    # about themselves is not evidence of itself.
    if on.get("evidence_required"):
        for fname in ("annual_income", "account_number"):
            if res["unified"].get(fname) is None:
                continue
            if res["provenance"].get(fname, {}).get("source") == "case_form":
                corroborated = (res["provenance"][fname].get("agreement") == "all_agree"
                                and len(res["sources"].get(fname, [])) > 1)
                if not corroborated:
                    _flag(res, "evidence_required",
                          f"{fname} came from the applicant's own form and nothing corroborates it",
                          field=fname)

    # PKG-007. Two payslips for two months is not one income figure.
    if on.get("period_coherence"):
        periods = {}
        for dt, flds in doc_fields.items():
            if base_type(dt) != "payslip":
                continue
            for f in flds:
                if f["field"] == "pay_period":
                    periods.setdefault(str(f["value"]), []).append(dt)
        if len(periods) > 1:
            _flag(res, "period_coherence",
                  f"payslips cover {len(periods)} different periods "
                  f"({', '.join(sorted(periods))}) and cannot be one income",
                  field="annual_income")

    # The Day-15 lesson. A document that never arrived took its check with it.
    if on.get("completeness_gate") and res["documents_missing"]:
        _flag(res, "completeness_gate",
              f"expected documents never arrived: {', '.join(res['documents_missing'])} "
              f"— the checks they would have performed did not run")

    if on.get("tolerance_guard"):
        loose = [f for f in IDENTIFIER_SHAPED
                 if f not in policy.identifiers
                 and f in res["unified"]
                 and len(res["sources"].get(f, [])) > 1]
        if loose and policy.tolerance > 0:
            res["flags"].append(
                {"scope": "note", "field": None, "check": "tolerance_guard",
                 "why": f"compared {', '.join(sorted(loose))} exactly — "
                        f"a {policy.tolerance:.0%} tolerance would have called "
                        f"different identifiers equal"})

    # A package flag sends everything to a human.
    if res["package_flagged"]:
        for f in list(res["unified"]):
            res["unified"][f] = None
    else:
        for fl in res["flags"]:
            if fl["scope"] == "field" and fl["field"] in res["unified"]:
                res["unified"][fl["field"]] = None


# ==========================================================================
# SCORING
# ==========================================================================
NO_CORRECT_ANSWER = ("CONFLICT", "AMBIGUOUS")


def _matches(got, want) -> bool:
    if isinstance(want, float):
        n = _num(got)
        return n is not None and abs(n - want) < 0.05
    return str(got) == str(want)


def score_package(res: dict, truth: dict, policy: Policy) -> dict:
    """
    One package, one policy, one number.

    Read the `wrong` count before the score. It is the only column that can
    hurt a customer; the score is a way of comparing policies, not a target in
    itself.
    """
    total, detail, wrong, correct, flags = 0, [], 0, 0, 0
    flagged_fields = {f["field"] for f in res["flags"] if f["scope"] == "field"}
    requires_evidence = set(truth.get("requires_evidence", []))

    for fname in FIELDS:
        want = truth.get(fname)
        got = res["unified"].get(fname, "__absent__")

        if got == "__absent__":
            # No document in this package offered the field at all.
            if res["package_flagged"] or fname in flagged_fields:
                outcome, pts = "refused", POINTS["flag"]
                flags += 1
            else:
                outcome, pts = "absent", POINTS["missing_unflagged"]
        elif got is None:
            # Refused: either reconcile declined, or a check took it away.
            if want in NO_CORRECT_ANSWER:
                outcome, pts = "correct", POINTS["correct_accept"]
                correct += 1
            else:
                outcome, pts = "refused", POINTS["flag"]
                flags += 1
        elif want in NO_CORRECT_ANSWER:
            outcome, pts = "wrong", POINTS["wrong_accept"]
            wrong += 1
        elif _matches(got, want):
            if (fname in requires_evidence
                    and res["provenance"].get(fname, {}).get("source") == "case_form"):
                # Right answer, no evidence behind it.
                outcome, pts = "unevidenced", POINTS["unevidenced_accept"]
            else:
                outcome, pts = "correct", POINTS["correct_accept"]
                correct += 1
        else:
            outcome, pts = "wrong", POINTS["wrong_accept"]
            wrong += 1

        total += pts
        detail.append({"field": fname, "got": got if got != "__absent__" else None,
                       "want": want, "outcome": outcome, "points": pts})

    # The identity verdict. Not "was it computed correctly" — verify_identity
    # gets it right every time. "Did the pipeline act on it."
    verdict = res["identity_verdict"]
    if verdict is None:
        if not res["package_flagged"]:
            total += POINTS["verdict_impossible_unflagged"]
    elif not verdict["passed"] and not res["package_flagged"]:
        total += POINTS["verdict_ignored"]

    if res["retained_evidence"]:
        total += POINTS["evidence_retained"]

    return {"score": total, "wrong_accepts": wrong, "correct": correct,
            "flags": flags, "detail": detail}


def play(policy: Policy, failure_rate: float = 0.0) -> dict:
    rows = []
    for pkg in corpus.packages():
        res = apply_policy(pkg, policy, failure_rate=failure_rate)
        sc = score_package(res, pkg["truth"], policy)
        rows.append({"package_id": pkg["id"], "result": res, **sc})
    total = {k: sum(r[k] for r in rows)
             for k in ("score", "wrong_accepts", "correct", "flags")}
    return {"rows": rows, "total": total}


def _preset_lab() -> Policy:
    return Policy(strategy={f: "reconcile" for f in FIELDS},
                  tolerance=0.02,
                  identifiers={"account_number", "claim_reference"},
                  checks={c: False for c in CHECKS},
                  keep_identity_evidence=False)


def _preset_brief() -> Policy:
    """What the curriculum literally specifies, and it scores badly."""
    return Policy(strategy={f: "trust_form" for f in FIELDS},
                  tolerance=0.02,
                  identifiers={"account_number"},
                  checks={c: False for c in CHECKS},
                  keep_identity_evidence=True)


def _preset_evidence() -> Policy:
    p = _preset_brief()
    p.strategy = {f: "trust_evidence" for f in FIELDS}
    return p


def _preset_flag_everything() -> Policy:
    p = _preset_brief()
    p.strategy = {f: "reconcile" for f in FIELDS}
    p.tolerance = 0.0
    return p


def _preset_all_checks() -> Policy:
    """The brief's knobs, untouched. Only the checks change."""
    p = _preset_brief()
    p.checks = {c: True for c in CHECKS}
    p.keep_identity_evidence = False
    return p


def _preset_all_checks_tight() -> Policy:
    p = _preset_all_checks()
    p.strategy = {f: "reconcile" for f in FIELDS}
    p.tolerance = 0.0
    return p


PRESETS = {
    "brief":             _preset_brief,
    "lab":               _preset_lab,
    "trust_evidence":    _preset_evidence,
    "flag_everything":   _preset_flag_everything,
    "all_checks":        _preset_all_checks,
    "all_checks_tight":  _preset_all_checks_tight,
}

PRESET_LABELS = {
    "brief":            "The brief — trust the applicant, no checks, keep the evidence",
    "lab":              "The lab — reconcile everywhere, no checks",
    "trust_evidence":   "Trust the paperwork — precedence decides, no checks",
    "flag_everything":  "Flag everything — reconcile, zero tolerance",
    "all_checks":       "All checks on — the brief's knobs, untouched",
    "all_checks_tight": "All checks on, plus tight knobs",
}
