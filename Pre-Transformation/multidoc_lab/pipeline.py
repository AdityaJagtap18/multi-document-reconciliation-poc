"""
pipeline.py — async processing, identity verification, stitching, storage.

FOUR THINGS IN HERE
-------------------
1. ASYNC          submit -> poll -> assemble. What you now own by choosing it.
2. VERIFICATION   process the identity document, keep the VERDICT, drop the rest.
3. STITCHING      four documents, one record, and the conflicts between them.
4. STORAGE        a Blob path is a policy decision, not a filename.

THE IDENTITY QUESTION — READ THIS BEFORE YOU WRITE ANY CODE
------------------------------------------------------------
Day 14 built a scope gate that DROPS identity fields. Today's brief says
"identity verification document processing: ID fields extraction".

Those look contradictory. They are not, and the distinction is the most
important thing in this session:

    You PROCESS the identity document.
    You KEEP the verdict.
    You DISCARD the evidence.

Concretely: you need to know whether the name on the licence matches the
applicant, and whether it had expired at the incident date. Answering those
two questions requires reading the document. It does not require STORING the
licence number, the address, or the document image in your decision profile.

So `verify_identity()` below returns a verdict object with no identity data
in it. The raw fields exist inside the function and never leave it. That is
the Sprint 0 Day 3 decision — consume the verdict, not the evidence —
implemented as a function boundary.

If a reviewer asks "where is the licence number stored", the answer is
"nowhere", and you can point at the code.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass, field as dc_field
from datetime import date

from packages import PRECEDENCE, INCIDENT_DATE, base_type


# ==========================================================================
# 1. ASYNC — submit, poll, assemble
# ==========================================================================
@dataclass
class Job:
    job_id: str
    pkg_id: str
    doc_type: str
    status: str = "running"        # running | succeeded | failed
    polls: int = 0
    result: list | None = None
    error: str | None = None
    handle: dict | None = None


class AsyncAnalyzer:
    """
    The orchestrator. It does NOT know how a document gets analysed — that is
    the backend's job — and it does not care which backend it was given.

    On the azure backend, `backend.start` really is:

        POST .../prebuilt-layout:analyze?...&features=queryFields
        -> 202 Accepted, Operation-Location: https://.../analyzeResults/{id}

    and it returns that URL without waiting. What this class replaces is:

        poller = client.begin_analyze_document(model, body=pdf, features=[...])
        result = poller.result()        # blocks

    We do NOT block. A large document can take minutes, and a Function that
    blocks for minutes is a Function that times out and costs you money while
    it waits. Thirty-two documents processed that way, one after another, is
    thirty-two sequential waits; submitted first and collected afterwards, it
    is one wait as long as the slowest document.

    WHAT CHOOSING ASYNC MEANS YOU NOW OWN
      * job state, somewhere durable — the handle IS the job, and on Azure it
        is a URL that outlives this process. Keep it in memory and a restart
        loses 32 analyses you have already paid for.
      * a retry policy, with a limit
      * partial failure — three documents finished, one did not
      * ORPHAN DETECTION — a job nobody is waiting for any more
      * ordering — the record cannot be assembled until every job resolves

    None of that is bought from the vendor. All of it is yours.
    """

    def __init__(self, backend, failure_rate: float = 0.0, seed: int = 7):
        self.backend = backend
        self.jobs: dict[str, Job] = {}
        self.failure_rate = failure_rate
        self.rng = random.Random(seed)

    def submit(self, pkg_id: str, doc_type: str) -> Job:
        jid = hashlib.sha256(f"{pkg_id}:{doc_type}".encode()).hexdigest()[:12]
        j = Job(jid, pkg_id, doc_type)
        j.handle = self.backend.start(pkg_id, doc_type)
        # Chaos injection, decided once at submission so a run is reproducible.
        # On the azure backend the analysis still happens and is still billed —
        # what this simulates is losing the RESULT, which is the failure mode
        # that actually happens in production and the one people forget to
        # design for.
        j._will_fail = self.rng.random() < self.failure_rate   # type: ignore[attr-defined]
        self.jobs[jid] = j
        return j

    def poll(self, job_id: str) -> Job:
        j = self.jobs[job_id]
        if j.status != "running":
            return j
        j.polls += 1
        state, fields, error = self.backend.poll(j.handle)
        if state == "running":
            return j
        if state == "failed":
            j.status, j.error = "failed", error or "analysis_failed_after_retries"
            return j
        if j._will_fail:                             # type: ignore[attr-defined]
            j.status, j.error = "failed", "result_lost_after_analysis"
            return j
        j.status, j.result = "succeeded", fields
        return j

    def await_all(self, jobs: list[Job], max_polls: int = 200) -> dict:
        """
        Poll until every job resolves or we give up. Returns a summary
        including anything still running, which is your orphan list.

        Note the shape of the loop: one pass over ALL jobs, then a pause, then
        another pass. Not `for job: wait until this one finishes`. The second
        version is the one people write first and it serialises the whole
        batch — every document waits for the one in front of it, and the
        asynchronous API you chose buys you nothing at all.
        """
        rounds = 0
        gap = getattr(self.backend, "poll_gap", 0.0)
        while rounds < max_polls and any(j.status == "running" for j in jobs):
            for j in jobs:
                self.poll(j.job_id)
            rounds += 1
            if gap and any(j.status == "running" for j in jobs):
                time.sleep(gap)
        return {
            "rounds": rounds,
            "succeeded": [j for j in jobs if j.status == "succeeded"],
            "failed": [j for j in jobs if j.status == "failed"],
            "orphaned": [j for j in jobs if j.status == "running"],
        }


# ==========================================================================
# 2. IDENTITY VERIFICATION — verdict out, evidence stays in
# ==========================================================================
@dataclass
class IdentityVerdict:
    """
    Note what is NOT in this object: no document number, no address, no image
    reference. Only what a decision actually needs.
    """
    name_matches: bool | None
    dob_matches: bool | None
    valid_at_incident: bool | None
    issuing_country: str | None
    checks_run: list[str] = dc_field(default_factory=list)
    notes: list[str] = dc_field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.name_matches and self.dob_matches and self.valid_at_incident)


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def verify_identity(id_fields: list, claimed_name: str, claimed_dob: str,
                    incident_date: str) -> IdentityVerdict:
    """
    Reads the identity document. Returns a verdict. Keeps nothing.

    Everything in `raw` below is in scope INSIDE this function and leaves no
    trace outside it. That is deliberate and it is the point of the function.
    """
    raw = {f["field"]: f["value"] for f in id_fields}
    v = IdentityVerdict(None, None, None, raw.get("issuing_country"))

    if "holder_name" in raw and claimed_name:
        v.checks_run.append("name_match")
        v.name_matches = _norm_name(raw["holder_name"]) == _norm_name(claimed_name)
        if not v.name_matches:
            v.notes.append("name on identity document does not match the applicant name")

    if "date_of_birth" in raw and claimed_dob:
        v.checks_run.append("dob_match")
        v.dob_matches = str(raw["date_of_birth"]) == str(claimed_dob)
        if not v.dob_matches:
            v.notes.append("date of birth on identity document does not match the form")

    if "expiry_date" in raw:
        v.checks_run.append("validity")
        try:
            v.valid_at_incident = date.fromisoformat(raw["expiry_date"]) >= date.fromisoformat(incident_date)
            if not v.valid_at_incident:
                v.notes.append(f"identity document expired {raw['expiry_date']}, "
                               f"before the incident on {incident_date}")
        except ValueError:
            v.notes.append("expiry date unreadable")

    # raw goes out of scope here. Nothing downstream can reach it.
    return v


# ==========================================================================
# 3. STITCHING — four documents, one record
# ==========================================================================
# Which source, for a given field, in which document.
FIELD_SOURCES = {
    "applicant_name":  {"case_form": "applicant_name", "identity": "holder_name",
                        "bank_statement": "account_holder_name", "payslip": "employee_name"},
    "date_of_birth":   {"case_form": "date_of_birth", "identity": "date_of_birth"},
    "annual_income":   {"case_form": "annual_income", "payslip": "gross_monthly_pay"},
    "employer_name":   {"case_form": "employer_name", "payslip": "employer_name"},
    "account_number":  {"case_form": "account_number", "bank_statement": "account_number"},
    "claim_reference": {"case_form": "claim_reference"},
}

STRATEGIES = ("trust_form", "trust_evidence", "reconcile")

# Fields where an exact match is required. No tolerance, ever.
IDENTIFIER_FIELDS = {"account_number", "claim_reference", "sort_code"}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def stitch(doc_fields: dict[str, list], strategy: str,
           tolerance: float = 0.02) -> dict:
    """
    doc_fields: {doc_type: [field dicts]}
    Returns the unified record plus every conflict it found.

    THE THREE STRATEGIES
      trust_form      the application form wins. Simple. Believes the applicant.
      trust_evidence  the supporting document wins. Believes the paperwork.
      reconcile       neither. Surface the disagreement and flag it.

    Only one of these is honest when the two sources disagree materially,
    and the lab measures which.
    """
    unified: dict = {}
    conflicts: list[dict] = []
    provenance: dict = {}

    # Payslip gross monthly pay becomes annual income. A derivation, and it
    # gets recorded as one — a derived value is not the same as a read value.
    derived: dict[str, tuple[float, str]] = {}
    for dt, flds in doc_fields.items():
        if base_type(dt) == "payslip":
            for f in flds:
                if f["field"] == "gross_monthly_pay":
                    m = _num(f["value"])
                    if m is not None:
                        derived.setdefault("annual_income", (round(m * 12, 2), dt))

    for target, sources in FIELD_SOURCES.items():
        found: list[tuple[str, object, float]] = []
        for dt, flds in doc_fields.items():
            base = base_type(dt)
            key = sources.get(base if base in sources else dt)
            if not key:
                continue
            for f in flds:
                if f["field"] == key:
                    val = f["value"]
                    if target == "annual_income" and base == "payslip":
                        m = _num(val)
                        val = round(m * 12, 2) if m is not None else val
                    found.append((dt, val, f["confidence"]))

        if not found:
            continue

        # Are they the same?
        #
        # CRITICAL: tolerance applies to QUANTITIES, never to IDENTIFIERS.
        # An account number that differs by 5 is not "within 2%" — it is a
        # different account, and the payment goes somewhere else. Getting
        # this wrong is how PKG-005 passes silently.
        vals = [v for _, v, _ in found]
        nums = [_num(v) for v in vals]
        if target in IDENTIFIER_FIELDS:
            same = len({str(v).strip() for v in vals}) == 1
        elif all(n is not None for n in nums):
            hi, lo = max(nums), min(nums)
            same = (hi - lo) <= tolerance * max(1.0, abs(hi))
        else:
            same = len({_norm_name(v) for v in vals}) == 1

        if same:
            dt, val, conf = max(found, key=lambda x: x[2])
            unified[target] = val
            provenance[target] = {"source": dt, "confidence": conf, "agreement": "all_agree",
                                  "derived": target in derived and dt.startswith("payslip")}
            continue

        # They disagree.
        conflicts.append({
            "field": target,
            "values": [{"source": dt, "value": v, "confidence": c} for dt, v, c in found],
        })

        order = PRECEDENCE.get(target, [])

        def rank(item):
            base = base_type(item[0])
            return order.index(base) if base in order else 99

        if strategy == "trust_form":
            pick = next((f for f in found if f[0] == "case_form"), found[0])
            unified[target] = pick[1]
            provenance[target] = {"source": pick[0], "confidence": pick[2],
                                  "agreement": "CONFLICT_resolved_to_form"}
        elif strategy == "trust_evidence":
            pick = sorted(found, key=rank)[0]
            unified[target] = pick[1]
            provenance[target] = {"source": pick[0], "confidence": pick[2],
                                  "agreement": "CONFLICT_resolved_by_precedence"}
        else:  # reconcile
            unified[target] = None
            provenance[target] = {"source": None, "confidence": None,
                                  "agreement": "CONFLICT_unresolved"}

    return {"unified": unified, "conflicts": conflicts, "provenance": provenance}


# ==========================================================================
# 4. STORAGE — a Blob path is a policy decision
# ==========================================================================
def blob_path(*, region: str, tenant: str, retention_class: str,
              claim_ref: str, doc_type: str, run_id: str) -> str:
    """
    A path that encodes the things somebody will one day have to act on:

        region           where the data physically sits
        tenant           whose data it is
        retention_class  how long it lives, and what deletes it
        claim_ref        what it belongs to
        doc_type         what kind of thing it is
        run_id           which processing run produced it

    Why it matters: a lifecycle rule, a legal hold, a subject access request
    and a residency audit are all PATH PREFIX operations. If retention is not
    in the path, "delete everything older than six years for tenant X" becomes
    a full scan and a per-object decision.

    Design this before you write your first blob. Moving objects later means
    rewriting every reference to them.
    """
    safe = re.sub(r"[^A-Za-z0-9\-_]", "-", claim_ref)
    return (f"{region}/{tenant}/{retention_class}/"
            f"{safe}/{run_id}/{doc_type}.json")
