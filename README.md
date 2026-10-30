# Multi-Document Reconciliation POC

> A Forward Deployed Engineering (FDE) proof of concept. This repository contains both the **pre-transformation** (before) and **post-transformation** (after) states of the solution, so the impact of the work can be seen side by side.

---

## 1. Overview

| Item | Details |
|------|---------|
| **POC Name** | Multi-Document Reconciliation POC |
| **Scenario / Customer** | Illustrative insurance claims-intake scenario: eight case packages, 32 documents (application form, identity document, payslip, bank statement) |
| **Owner** | Aditya Jagtap |
| **Status** | Completed |
| **Program** | FDE Program |

**One-line summary:** Extracting every document correctly is not enough. Wrong records are built *between* documents, so a reconciliation step that flags conflicts instead of guessing is what stops them.

---

## 2. Problem Statement

Each claim arrives with several supporting documents that must be combined into one applicant record before the claim can proceed. Every document can be read with high confidence and the combined record can still be wrong.

- A bank statement can belong to a different person (PKG-008) and still look perfect on its own.
- An account number can differ by a single digit (PKG-005), and a numeric tolerance would call it equal.
- A missing, expired or contradictory document (PKG-003, PKG-006, PKG-007) removes the check it was meant to support.
- Pipelines that always return a complete record hide these problems, because a record with no gaps looks finished.

---

## 3. Pre-Transformation (Before)

The starting point is a pipeline that stitches documents together by trusting one source and silently overwriting the rest.

| Aspect | Current State |
|--------|---------------|
| Process | Documents are extracted and merged. `trust_form` believes the applicant; `trust_evidence` believes the paperwork |
| Model / Tooling | Mock provider (synthetic Query Fields responses), standard-library Python |
| Cost | None (offline, deterministic) |
| Latency / Performance | Instant |
| Accuracy / Quality | `trust_form`: **4 wrong values accepted**. `trust_evidence`: **2 wrong values accepted**. 0 refusals either way |
| Pain points | Complete-looking records that are wrong with nothing attached to say so; no handler is alerted |

**Location in repo:** [Pre-Transformation/](Pre-Transformation/)

---

## 4. Post-Transformation (After)

The end state adds explicit reconciliation, an identity verdict boundary, provenance on every field, and a run against the real Azure service.

| Aspect | New State |
|--------|-----------|
| Process | `reconcile` surfaces both values on any disagreement and refuses to guess. Identity is verified and only the verdict is kept, never the evidence |
| Model / Tooling | Azure AI Document Intelligence (`prebuilt-layout`, Query Fields, api-version `2024-11-30`), behind a two-function provider seam so the backend can be swapped |
| Cost | 32 billed analyses, 152 query-field requests. Raw responses are cached, so re-runs are free |
| Latency / Performance | About 2 min 54 s for the first billed run; seconds afterwards. Five HTTP 429 rate-limit waits (94 s) on the free tier |
| Accuracy / Quality | **0 wrong values accepted**, 4 packages refused for handler review, 8/8 identity verdicts correct |
| Benefits | Every field carries provenance and an agreement status; conflicts are visible; a field-source whitelist stopped invented vendor values from reaching the record |

**Location in repo:** [Post-Transformation/](Post-Transformation/)

---

## 5. Before vs. After

| Metric | Pre-Transformation (`trust_form`) | Post-Transformation (`reconcile`) | Change |
|--------|-----------------------------------|-----------------------------------|--------|
| Wrong values accepted | 4 | 0 | -4 (100% reduction) |
| Conflicts surfaced | 6 | 6 | Same conflicts found, but now acted on |
| Packages refused for review | 0 | 4 | +4 (visible handler cost) |
| Identity verdicts correct | 8/8 | 8/8 | No change |

The same totals held on the real Azure run as on the mock run (4 / 2 / 0 wrong accepted for the three strategies). The service read all 32 documents essentially perfectly, so the improvement comes from the reconciliation logic, not the extraction.

Detailed results: [Post-Transformation/out/mock/multidoc_report.md](Post-Transformation/out/mock/multidoc_report.md), [Post-Transformation/out/azure/multidoc_report.md](Post-Transformation/out/azure/multidoc_report.md) and the per-field [stitch_results.csv](Post-Transformation/out/azure/stitch_results.csv).

---

## 6. Approach

1. **Discover** – Identify the failure modes between documents: name mismatch, expiry, income gap, one-digit account difference, missing and duplicate documents, a statement from the wrong person.
2. **Baseline** – Score `trust_form` and `trust_evidence` on the eight packages by counting wrong values accepted.
3. **Evaluate** – Compare the three stitching strategies against the criteria below.
4. **Build** – Implement `reconcile`, the identity verdict boundary, per-field provenance and the Azure adapter.
5. **Measure** – Run offline, then on real Azure Document Intelligence, including an over-ask test and injected document failures.
6. **Hand off** – Document the commands, outputs, troubleshooting and the open questions for sign-off.

### Decision Criteria

| Criterion | Weight | Why |
|---|---|---|
| Wrong values accepted | Highest | The only measure that can hurt a customer |
| Visibility of conflicts | High | A refused value is a visible cost; a wrong accepted value is an invisible one |
| Handler effort | Medium | Refusals cost time, which must be quoted at real volume |
| Identity data retained | High | Keep the verdict, discard the evidence |

---

## 7. Repository Structure

```
Multi_Document_Reconciliation_POC/
├── README.md
├── Pre-Transformation/      # "Before" state: pipeline, strategies, scoring, game
└── Post-Transformation/     # "After" state: same code plus documents, outputs and analysis
    ├── multidoc_lab/        # packages, pipeline, mock and Azure providers, self-test
    ├── Reconciliation_Game/ # scored tuning exercise on the same cases
    ├── docs/                # 32 generated PDFs
    ├── out/mock/, out/azure/ # reports, CSV, unified records, raw responses
    └── project_analysis.md
```

---

## 8. Getting Started

### Prerequisites

- Python 3.9 or newer (standard library only for the core run)
- For the Azure run: an Azure AI Document Intelligence resource, its endpoint and a key

### Setup

```powershell
cd Post-Transformation
copy .env.example .env
```

Fill in `AZURE_DOCINT_ENDPOINT` and `AZURE_DOCINT_KEY` in `.env` only if running against Azure. `.env` is git-ignored and must never be committed.

### Run

```powershell
python run_lab.py                      # all three strategies, offline
python run_lab.py --selftest           # 108 offline checks
python run_lab.py --show PKG-008       # one package under every strategy
python run_lab.py --strategy reconcile --failures 0.2   # inject document failures
python run_lab.py --make-pdfs          # render the 32 PDFs (needed once for Azure)
python run_lab.py --provider azure     # real Document Intelligence (billed)
```

---

## 9. Results & Learnings

- **Key result:** `reconcile` accepts 0 wrong values against 4 for `trust_form` and 2 for `trust_evidence`, at the cost of refusing 4 packages.
- **What worked:** Applying tolerance to quantities only, never identifiers (this is what catches PKG-005). Cross-checking the same field across four documents (this is what catches PKG-008). The identity function returns a verdict and stores nothing.
- **What didn't:** When documents are lost (`--failures 0.2`), `reconcile` accepts 3 wrong values, because a lost document removes the second opinion that made the conflict visible. Name matching is exact after normalisation, so a joint account or a maiden versus married name is not handled.
- **Over-asking:** Asking Azure for a field a document does not contain returned a populated value 8 times out of 72 (`-58.10` as annual income from a bank statement). A per-document-type field whitelist stopped all eight reaching the record.
- **Recommendations:** Use `reconcile`; keep the field whitelist; get the precedence table signed off by a named owner; quote handler cost at real volume.

> Caveats: The corpus is eight synthetic packages with hand-written ground truth. The PDFs are digitally generated, so the Azure confidence range (0.903 to 0.995) is a ceiling, not an accuracy estimate. The Pre and Post folders share the same code, so the "before" figures come from the `trust_form` and `trust_evidence` strategies rather than from a separate older implementation. Nothing here measures cost savings or production readiness.

---

## 10. Next Steps

- [ ] Run the pipeline on the customer's own scanned documents to get a real accuracy figure
- [ ] Get the field precedence table approved by claims policy or compliance
- [ ] Add a stronger identity check on bank statements (joint accounts, name variants)
- [ ] Replace the polling loop with durable orchestration for production volume

---

## 11. Contact

Aditya Jagtap · adiraj2503@gmail.com
