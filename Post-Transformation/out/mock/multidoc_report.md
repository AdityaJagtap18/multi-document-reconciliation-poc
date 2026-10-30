# Multi-document extraction report � DecisionStream AI

Packages: **8**   Documents: **32**   Injected async failure rate: **0%**

Source: **mock** (synthetic Query Fields responses � the confidences were chosen to make a teaching point, not measured)

## Stitching strategy comparison

| Strategy | Wrong accepted | Refused (flagged) | Conflicts surfaced | Verdicts correct |
|---|---|---|---|---|
| trust_form | **4** | 0 | 6 | 8/8 |
| trust_evidence | **2** | 0 | 6 | 8/8 |
| reconcile | **0** | 4 | 6 | 8/8 |

### How to read this

**Wrong accepted** is the only column that can hurt a customer. Those are values written into the unified record, with no flag, that are not correct.

`trust_form` believes the applicant. `trust_evidence` believes the paperwork. Both produce a complete record and both will be wrong silently when the two sources disagree for a reason neither strategy understands. `reconcile` refuses and flags � which costs a handler time on every conflict, including the trivial ones.

## The packages

| Package | What makes it hard |
|---|---|
| PKG-001 | clean package, everything agrees |
| PKG-002 | name on identity does not match the form |
| PKG-003 | identity document expired before the incident |
| PKG-004 | declared income does not match the payslip |
| PKG-005 | account number differs by one digit |
| PKG-006 | payslip missing from the package |
| PKG-007 | two payslips, different months, different amounts |
| PKG-008 | bank statement belongs to a different person |

## Questions to answer before this goes in the ADR

### 1. Which field is authoritative from which document, and who signed that precedence table off?

The precedence is the `PRECEDENCE` table in `multidoc_lab/packages.py:116-123`, applied by `stitch()` in `multidoc_lab/pipeline.py:325-340` only when a `trust_evidence` conflict needs resolving:

| Field | Authoritative document (highest to lowest) |
|---|---|
| `applicant_name` | identity → bank_statement → case_form |
| `date_of_birth` | identity → case_form |
| `annual_income` | payslip → case_form |
| `employer_name` | payslip → case_form |
| `account_number` | bank_statement → case_form |
| `claim_reference` | case_form |

The rule behind the ordering: the applicant's own form is never authoritative for anything a third party also attests to — it loses to the identity document for who someone is, and to the payslip/bank statement for what they earn and where they bank. It only wins when it is the *only* source (`claim_reference`).

**Who signed it off:** nobody, yet — this table is a lab default checked into `packages.py`, not a reviewed business rule. Before this goes into the ADR, it needs a named accountable owner (claims policy / compliance) to approve the ordering, because `trust_evidence` silently overwrites the applicant's stated value with this precedence and someone has to own that decision. **Action item: get this table signed off before it ships, and record who approved it here.**

### 2. PKG-008 contains a bank statement belonging to a different person. Every field in it is high confidence and internally consistent. What caught it, and would that check have caught a subtler version?

What caught it is the cross-document agreement check on `applicant_name` in `stitch()` (`multidoc_lab/pipeline.py:296-317`): `applicant_name` is sourced from four documents (`FIELD_SOURCES`, `pipeline.py:227-228`), and when the bank statement's `account_holder_name` doesn't normalize-match the other three, it becomes a `CONFLICT`, not a silent value. It is **not** `verify_identity()` that catches it — that function only compares the identity document to the case form, and PKG-008's identity document matches the applicant fine (`identity: passed=True`, confirmed by `--show PKG-008` above). The catch happens purely because the same field is asked of a fourth, otherwise-unrelated document and the answers are compared.

**Would it catch a subtler version?** No — not reliably. `_norm_name()` (`pipeline.py:181-182`) does an exact match after stripping punctuation/case. A bank statement in a similar name (a transposed name, a spouse, a shared account, a maiden vs. married name) would normalize to a *different* string and would still conflict — so near-miss typos are actually caught. But the real gap is upstream: the check only exists because `account_holder_name` happens to be in `FIELD_SOURCES["applicant_name"]`. There is no independent identity check *on the bank statement itself* (no sort-code-to-region check, no account-age check, nothing that verifies the statement belongs to this claim other than the name string matching). A subtler attack — the correct person's name on a statement that is nonetheless the wrong account, or a joint account holder whose name legitimately differs — would not be flagged by anything in this pipeline. **Action item: name-string matching is necessary but not sufficient; a stronger cross-document identity check needs design before this scales past a lab.**

### 3. Your identity verification returns a verdict and keeps nothing. Can you point at the line of code that guarantees that?

Two places, belt and braces:

- `verify_identity()` in `multidoc_lab/pipeline.py:185-219` reads the raw identity fields into a local variable `raw` (line 193) that goes out of scope when the function returns; it returns only an `IdentityVerdict` (`pipeline.py:163-178`), whose fields are `name_matches`, `dob_matches`, `valid_at_incident`, `issuing_country`, `checks_run`, `notes` — no document number, no address, no image reference. That is the function-boundary guarantee: nothing downstream can reach `raw`.
- `run_lab.py:77-79` is the runtime assertion that boundary held: `leaked = [k for k in st["unified"] if k in ("document_number", "expiry_date", "issuing_country")]`, checked on every package under every strategy. If any code path ever let an identity field leak into the unified record, this line — and the self-test that exercises it (`multidoc_lab/selftest.py`, part of the 108 checks that passed above) — catches it.

### 4. A package arrives with three of four documents. Do you process it or hold it, and who decided?

The code **processes it, never holds it**, and flags it. `process()` in `run_lab.py:52-103` always stitches whatever documents arrived (`doc_fields` built only from `summary["succeeded"]`, `run_lab.py:59`) and sets `needs_human = True` whenever `documents_missing` is non-empty or a document failed/orphaned (`run_lab.py:101-102`). There is no branch that halts the pipeline and waits for the fourth document — a partial package produces a partial (and flagged) unified record on the same run.

That is a design decision embedded in code, not a decision anyone explicitly signed off on for this lab (see PKG-006, which is missing its payslip entirely and processes fine with `annual_income` marked `missing` rather than blocking). **Action item: decide, and name an owner, for whether that is the right call in production** — always-process-and-flag trades completeness for speed and puts the burden on the human reviewer catching `needs_human`; a hold-for-completeness policy would be slower but would never let a handler action an incomplete record without noticing it was incomplete. This lab's default is process-and-flag.

### 5. An async job never completes. How long before anyone notices, and what notices?

On the **mock** provider, jobs always resolve in one poll round — nothing hangs. On the **azure** path, two timers apply:

- Per-document: `azure_multidoc.py:337,360` gives a job until `AZURE_DOCINT_TIMEOUT` seconds (default **180s**, `config.py:170`) after submission; past that deadline `poll()` returns `failed` with `"still '<state>' after 180s — raise AZURE_DOCINT_TIMEOUT"`.
- Batch loop: `AsyncAnalyzer.await_all()` (`pipeline.py:133-157`) polls every job once per round, sleeps `poll_gap` (default **1.5s**) between rounds, up to `max_polls=200` rounds — a ~300s ceiling before the batch gives up and reports the job as `orphaned` regardless.

So in practice a stuck job is caught by the per-document 180s timeout well inside the batch's ~300s ceiling — **noticed within about 3 minutes of submission**, not immediately. What "noticing" means today: the job lands in `summary["failed"]` or `summary["orphaned"]`, `documents_missing` and `async.failed`/`async.orphaned` populate that package's `unified/PKG-XXX.json`, and `needs_human` flips to `True` (`run_lab.py:97-102`). **Nothing pushes an alert** — this is entirely passive. Someone has to read the unified record, run `--show`, or read the report to find out. Step 3 of the README demonstrates exactly this: a lost document doesn't make a verdict wrong, it makes it `n/a`, and only a human reading the output learns that. **Action item: this lab has detection but no notification — production needs the `needs_human`/`orphaned` state wired to an actual alert (queue, dashboard, page), not just a field in a JSON file nobody is watching.**

### 6. What is in your Blob path, and which retention or residency operation would be impossible without it?

`blob_path()` (`multidoc_lab/pipeline.py:352-374`) builds:

```
{region}/{tenant}/{retention_class}/{claim_ref}/{run_id}/{doc_type}.json
```

e.g. `uksouth/acme-insurance/claims-6y/CLM-2026-4471/run-20260814-0931/case_form.json`

Each segment is a prefix, in this order — region, tenant, retention class, claim, run, document — and each supports a specific operation that would otherwise require a full-bucket scan with a per-object decision:

| In the path | Operation it makes a prefix delete/list instead of a scan |
|---|---|
| `region` | Prove nothing left the region (residency audit) |
| `tenant` | Delete or export everything for one customer |
| `retention_class` | Delete everything past its retention window (`claims-6y` and older) |
| `claim_ref` | Find or hold every document for one claim (legal hold, subject access request) |
| `run_id` | Find everything one processing run produced (incident investigation, reprocessing) |

Without `retention_class` specifically: "delete everything older than six years for this tenant" degenerates into reading every object's metadata individually to decide whether it qualifies — at scale, that is the difference between a lifecycle rule Azure runs for you and a bespoke, expensive, error-prone batch job someone has to write, run, and re-run correctly forever. That is why the README calls this a design-before-first-blob decision: moving objects later means rewriting every reference to them.
