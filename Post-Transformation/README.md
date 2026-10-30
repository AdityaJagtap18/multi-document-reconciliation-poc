# Sprint 1 · Day 15 Lab — Multi-Document Processing

**Birlasoft FORGE FDE Academy · DecisionStream AI · Confidential — For Learner Use Only**

Eight case packages, up to five documents each, one unified record — and the
question of what to do when four documents disagree with each other.

The lab runs two ways from the same code:

| Provider | What it is | Cost | Speed |
|---|---|---|---|
| `mock` *(default)* | Synthetic Query Fields responses | Free | Instant |
| `azure` | 32 rendered PDFs through **Azure AI Document Intelligence** | Billed | ~3 min |

**Run `mock` first. It is the lab.** Run `azure` afterwards to find out how much
of what you concluded survives contact with the real service.

---

## Table of contents

1. [Quick start](#1--quick-start)
2. [Read this before you write any code](#2--read-this-before-you-write-any-code)
3. [The result](#3--the-result)
4. [The eight packages](#4--the-eight-packages)
5. [What to do — the lab, step by step](#5--what-to-do--the-lab-step-by-step)
6. [Switching to real Azure Document Intelligence](#6--switching-to-real-azure-document-intelligence)
7. [What the real run measured](#7--what-the-real-run-measured)
8. [Every command and flag](#8--every-command-and-flag)
9. [Every output file](#9--every-output-file)
10. [Troubleshooting](#10--troubleshooting)
11. [How the code is laid out](#11--how-the-code-is-laid-out)
12. [Before you present](#12--before-you-present)

---

## 1 · Quick start

### The lab, offline, right now

```bash
python run_lab.py
```

Standard library only. No Azure, no key, no `pip install`, no network. That is
the whole setup.

**Python 3.9 or newer is recommended**; the lab is written to run on 3.7+ and is
tested on 3.7.2 and 3.12. On the Techademy Azure VM, `python3` is 3.12 and you
need nothing else.

You should see three tables and this summary:

```
  trust_form        4 wrong accepted,  0 refused,  6 conflicts surfaced, 8/8 verdicts correct
  trust_evidence    2 wrong accepted,  0 refused,  6 conflicts surfaced, 8/8 verdicts correct
  reconcile         0 wrong accepted,  4 refused,  6 conflicts surfaced, 8/8 verdicts correct
```

If those numbers differ, something is wrong with your setup rather than your
reasoning — the mock provider is deterministic and always produces exactly
these. Run `python3 run_lab.py --selftest` to find out what.

### Check everything works before you spend anything

```bash
python3 run_lab.py --selftest
```

108 checks, no network, no cost. It proves the Azure adapter reproduces the
mock pipeline exactly, so that when the two runs later disagree you know the
disagreement is real.

---

## 2 · Read this before you write any code

Day 14 built a scope gate that **drops** identity fields. Today's brief says
*"identity verification document processing: ID fields extraction"*.

Those look contradictory. They are not, and the distinction is the most
important thing in this session:

> **You process the identity document. You keep the verdict. You discard the
> evidence.**

You need to know whether the name on the licence matches the applicant and
whether it had expired at the incident date. Answering those questions requires
reading the document. It does not require **storing** the licence number, the
address, or the image in your decision profile.

Look at `verify_identity()` in [`multidoc_lab/pipeline.py`](multidoc_lab/pipeline.py).
Everything it reads is local to the function. What it returns is an
`IdentityVerdict` with no identity data in it at all. When a reviewer asks
*"where is the licence number stored"*, the answer is *"nowhere"*, and you can
point at the function boundary.

That is the Sprint 0 Day 3 decision — consume the verdict, not the evidence —
implemented as code rather than asserted in a document. The self-test enforces
it on every package under every strategy, so it cannot rot.

---

## 3 · The result

```bash
python3 run_lab.py
```

| Strategy | Wrong accepted | Refused (flagged) |
|---|---|---|
| `trust_form` — the applicant wins | **4** | 0 |
| `trust_evidence` — the paperwork wins | **2** | 0 |
| `reconcile` — neither, surface both | **0** | 4 |

All three find the same six conflicts. What differs is what they **do** about
them, and only one declines to guess.

`trust_form` and `trust_evidence` both produce a complete record every time.
That is exactly what makes them dangerous: a complete record with no gaps looks
finished, and four of those values are wrong with nothing attached to say so.

`reconcile` costs a handler time on four packages. That is a real cost and it
should be quoted at your actual volume — but it is a **visible** cost, paid by
someone who knows they are paying it.

---

## 4 · The eight packages

| Package | What makes it hard |
|---|---|
| PKG-001 | Clean — everything agrees |
| PKG-002 | Name on the licence is not the name on the form |
| PKG-003 | Identity document expired before the incident |
| PKG-004 | Declared income is 42% above the payslip |
| PKG-005 | Account number differs by **one digit** |
| PKG-006 | Payslip missing — income is declared, not evidenced |
| PKG-007 | Two payslips, two months, two very different amounts |
| **PKG-008** | **Bank statement belongs to a different person** |

### PKG-005 is the one that nearly got through

The account number on the form is `20558193`. On the bank statement it is
`20558198`. A numeric comparison with a 2% tolerance calls those equal — they
differ by 5 out of twenty million.

They are not equal. They are different accounts, and the payment goes somewhere
else.

Look at `IDENTIFIER_FIELDS` in `pipeline.py`. **Tolerance applies to
quantities, never to identifiers.** An account number is not a number in any
sense that matters; it is a name made of digits.

### PKG-008 is the one that should worry you

Every field on that bank statement is high confidence and internally
consistent. The sort code is valid. The period is right. It is simply the wrong
person's statement, attached to the package by mistake.

Nothing about the **document** is wrong. What is wrong is the relationship
between it and the other three. Run `--show PKG-008` and see which check
catches it — then ask whether that check would catch a subtler version, where
the name is similar rather than different.

---

## 5 · What to do — the lab, step by step

### Step 1 · Run the three strategies (10 min)

```bash
python3 run_lab.py
```

Read the `WRONG` column first and nothing else. It is the only column that can
hurt a customer.

### Step 2 · Look at the dangerous packages (15 min)

```bash
python3 run_lab.py --show PKG-005
python3 run_lab.py --show PKG-008
```

`--show` prints one package under **all three** strategies, with every conflict,
the identity verdict and the checks that ran.

### Step 3 · Break the async pipeline (10 min)

```bash
python3 run_lab.py --strategy reconcile --failures 0.2
```

One document in five fails to process. Watch what happens to the identity
verdicts.

**They do not become wrong. They become impossible.** The verdict column shows
`n/a`, because the document that would have performed the check never arrived.

> Losing a document does not just lose data. It loses the **check** that
> document was there to perform.

Note that `reconcile` — which accepted **zero** wrong values on a healthy run —
now accepts **three**. Not because the stitching got worse, but because a lost
document removes the second opinion that made a conflict visible in the first
place. One value cannot disagree with anything.

> **Why the same documents fail every time.** The failure injection is seeded
> (`seed=7`, re-seeded per package), so a given `--failures` rate fails the
> same document type in every package and every learner sees an identical
> table. That is deliberate — the lesson is legible instead of noisy. It is not
> a model of how real failures distribute.

### Step 4 · Look at the storage design (5 min)

```bash
python3 run_lab.py --paths
```

```
uksouth/acme-insurance/claims-6y/CLM-2026-4471/run-20260814-0931/case_form.json
```

Region, tenant, retention class, claim, run, document. Every one of those is a
**prefix operation**: delete after six years, prove nothing left the region,
place a legal hold, find everything from one run.

Leave retention out of the path and the first of those becomes a full scan with
a per-object decision. Design this before you write the first blob — moving
objects later means rewriting every reference to them.

### Step 5 · Answer the six questions in `out/mock/multidoc_report.md`

They are the deliverable. The tables are just the evidence.

---

## 6 · Switching to real Azure Document Intelligence

Everything above runs offline. This section points the same pipeline at the
real service. **Nothing downstream of the vendor boundary changes** — that is
the point of the exercise.

### 6.1 · What you need

- An **Azure AI Document Intelligence** resource (or an Azure AI Services
  multi-service resource), any region.
- Its **endpoint** and one of its **keys**: Portal → your resource → *Keys and
  Endpoint*.
- Nothing else. No SDK, no `pip install` — the lab calls the REST API with the
  standard library so you can read the request.

> **If you did Day 14, you already have this.** It is the same service, the same
> resource and the same variable names. Copy your Day 14 `.env` into this folder
> unchanged and skip to 6.3.

### 6.2 · Configure

```bash
cp .env.example .env
```

Then edit `.env` and set two values:

```bash
AZURE_DOCINT_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DOCINT_KEY=<your-key>
```

`.env` is git-ignored. **Never commit it, never paste a key into chat, never
put one in a screenshot.**

Leave `DOCINT_PROVIDER=mock` in the file. Switch per-run with `--provider azure`
so that the offline default stays the thing that happens by accident.

### 6.3 · Render the documents

```bash
python3 run_lab.py --make-pdfs
```

Azure will not accept a Python dictionary. This renders the eight packages —
all 32 documents — as real PDFs under `docs/PKG-XXX/`, from exactly the same
data the mock provider serves. One source of truth, two providers.

```
docs/PKG-007/
  case_form.pdf      identity.pdf      payslip.pdf
  payslip_2.pdf      bank_statement.pdf
```

Open one. The page says **"Declared Annual Income (GBP): 62000.00"** — not
`annual_income`. That gap is deliberate and it is the whole proposition of
Query Fields: we ask for `annual_income` and the service has to work out which
line we meant. A mock whose keys already match ours cannot test that.

### 6.4 · Prove the adapter before you spend

```bash
python3 run_lab.py --selftest
```

### 6.5 · Run it

```bash
python3 run_lab.py --provider azure
```

Expect **about three minutes** and 32 billed analyses on the first run.
Raw responses are cached under `out/azure/di_raw/`, so every run after the
first is free and takes seconds. Delete that directory, or set
`DOCINT_USE_CACHE=false`, to force a fresh read.

Results land in `out/azure/` — a **different directory** from `out/mock/`, so
the two runs never overwrite each other and you can diff them.

### 6.6 · The one call that matters

```
POST {endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze
     ?api-version=2024-11-30
     &features=queryFields
     &queryFields=applicant_name,date_of_birth,annual_income,employer_name,account_number,claim_reference

-> 202 Accepted
   Operation-Location: https://.../analyzeResults/{id}
```

Then poll that URL until `status` is `succeeded`. **Three things about this
request will bite you**, and all three are silent failures rather than errors:

1. **The route moved.** api-version `2024-11-30` and later live under
   `/documentintelligence/`. Earlier versions live under `/formrecognizer/`.
   Mismatch them and you get a 404 whose message talks about *the model*, which
   sends people hunting for a deployment problem that does not exist. Check the
   route before you check the model name.

2. **Query Fields needs both halves.** `features=queryFields` turns the add-on
   on; `queryFields=a,b,c` says which fields. Send the names without the
   feature flag and you get **HTTP 200 with no `documents` member at all** —
   successful, empty, and entirely misleading. Nothing errors. You just get
   zero fields. (Day 14's equivalent trap was `features=keyValuePairs`.)

3. **Asking for a field does not make it exist — and the service will still
   answer.** See §7.3. This is the measured headline of the azure run.

---

## 7 · What the real run measured

> Figures below are from a live run on **2026-08-17** against a free-tier (F0)
> Document Intelligence resource, `prebuilt-layout`, api-version `2024-11-30`.
> Your numbers will differ slightly; the conclusions should not.

### 7.1 · The headline: nothing changed

| Strategy | Mock — wrong / refused / conflicts | Azure — wrong / refused / conflicts |
|---|---|---|
| `trust_form` | 4 / 0 / 6 | **4 / 0 / 6** |
| `trust_evidence` | 2 / 0 / 6 | **2 / 0 / 6** |
| `reconcile` | 0 / 4 / 6 | **0 / 4 / 6** |

Identical. Every conflict, every refusal, every verdict — 8/8 correct on both.

**That is the finding, not a disappointment.** Day 14's azure run diverged from
its mock sharply, because Day 14 was measuring *extraction*: whether the model
read the characters correctly. This lab is measuring something else. Every
defect here lives **between** documents — a name that does not match another
name, an account number that differs from another account number, a statement
belonging to somebody else. The service read all 32 documents essentially
perfectly and handed back a set of documents that still disagree.

> Extraction is a purchased service. **Verification and stitching are yours** —
> and they are where a wrong record gets built out of individually correct
> documents. The real service changed nothing because the failure was never in
> the reading.

That sentence is the one to take to a client. It is also the argument for why
the two rows in §11 that say *"your own code"* are the two that carry the risk.

### 7.2 · What the extraction actually cost

| Measure | Value |
|---|---|
| Documents analysed | 32 |
| Query-field requests sent | 152 |
| Answered | 152 (100%) |
| Returned empty | 0 |
| Mean confidence, per document | 0.903 – 0.995 |
| Wall-clock, first (billed) run | ~2 min 54 s |
| Rate-limited (HTTP 429) | 5 times, 94 s spent waiting on `Retry-After` |

The rate-limit line is a **throughput number, not an error**. Quote it when
somebody asks what 4,000 documents a month looks like on this tier.

**You are not entitled to quote that confidence range as an accuracy estimate.**
These PDFs are digitally generated — the text is embedded, not scanned. The
service reads them far more confidently than it would read the forms this lab
models. That range is a **ceiling**. To get a real number, run the client's own
scans through the same pipeline; asking for them is the first thing to do.

### 7.3 · The measured headline: over-asking

```bash
python3 run_lab.py --provider azure --overask
```

This adds field names to each request that the document **genuinely does not
contain** — a sort code on a payslip, an employer on a driving licence. It is
what happens when a team writes one query list and reuses it across document
types "to keep things simple".

The service does not push back. It answers.

| Measure | Value |
|---|---|
| Extra requests sent | 72 |
| Came back **empty** — the honest answer | 64 |
| Came back **with a value in them** | **8** |

All eight are the same failure, and it is systematic rather than random:

| Asked | Of | Got back | Confidence |
|---|---|---|---|
| `annual_income` | each bank statement | **`-58.10`** | 0.584 – 0.657 |

`-58.10` is a grocery card payment in the transaction list. Asked a bank
statement for annual income, the service found the closest number on the page
and returned it, at a confidence high enough to look like an answer rather than
a shrug.

> A field that comes back **empty** is safe — it lands in `missing` and somebody
> sees a gap. A field that comes back **populated and wrong** is the exact
> failure mode this lab is about, arriving from the vendor rather than from your
> stitching.

**Why it did no damage here, and what that teaches.** None of those eight values
reached the unified record, and the totals were unchanged. The reason is
`FIELD_SOURCES` in `pipeline.py`: it declares that `annual_income` may be
sourced from a **case form or a payslip**, and from nowhere else. A bank
statement is not an allowed source, so the invented value had no route in.

That is a whitelist doing exactly the job a whitelist is for. If your stitching
merges "whatever fields came back" instead of "the fields this document type is
allowed to supply", the vendor's guess becomes your record's income figure and
nothing anywhere reports an error.

*(A second data point, from Day 14's motor claim form: asked for
`gross_monthly_pay`, which no motor claim form has, it returned `9000.00` at
confidence **0.75**. Same behaviour, higher confidence, on a different form.)*

### 7.4 · What did not happen

The **PAGES THE SERVICE DID NOT READ** warning never fired. A free-tier resource
analyses the first two pages of a document and stops — silently — and Day 14 lost
three teaching points to it. Here, every query field is rendered on **page 1 by
design**, so the limit cannot be mistaken for an extraction failure. The check
is still in the code; if you add a third page to a document, it will tell you.

---

## 8 · Every command and flag

### Commands

| Command | What it does |
|---|---|
| `python3 run_lab.py` | All three strategies over all eight packages. **Start here.** |
| `python3 run_lab.py --selftest` | 108 offline checks. No network, no cost. |
| `python3 run_lab.py --paths` | The Blob path design demo. |
| `python3 run_lab.py --make-pdfs` | Render the 32 documents to `docs/`. Needed once before any azure run. |

### Flags

| Flag | Values | Default | What it does |
|---|---|---|---|
| `--strategy` | `trust_form` · `trust_evidence` · `reconcile` | all three | Run one strategy instead of all three. |
| `--show` | a package id, e.g. `PKG-008` | — | One package under all three strategies, in full detail. |
| `--failures` | a rate, e.g. `0.2` | `0.0` | Fail that proportion of documents. Seeded, so it is reproducible. |
| `--provider` | `mock` · `azure` | from `.env` | Override the provider for one run. |
| `--overask` | — | off | **azure only.** Also ask each document for fields it does not contain. |
| `-v`, `--verbose` | — | off | With `--selftest`, print every passing check too. |

Flags combine. `--provider azure --strategy reconcile --failures 0.2` is a valid
and interesting run.

### Environment variables

Set in `.env`, or as real environment variables — **a real environment variable
always wins**, so CI and the Azure VM can override without editing files.

| Variable | Default | What it does |
|---|---|---|
| `DOCINT_PROVIDER` | `mock` | `mock` or `azure`. Same variable as Day 14. |
| `AZURE_DOCINT_ENDPOINT` | — | Resource endpoint. **Required for azure.** |
| `AZURE_DOCINT_KEY` | — | Resource key. **Required for azure.** |
| `AZURE_DOCINT_MODEL` | `prebuilt-layout` | The model Query Fields attaches to. |
| `AZURE_DOCINT_API_VERSION` | `2024-11-30` | API version. Drives the route. |
| `AZURE_DOCINT_ROUTE` | `auto` | `auto`, `documentintelligence`, or `formrecognizer`. Force only when debugging a 404. |
| `AZURE_DOCINT_TIMEOUT` | `180` | Seconds to wait for **one** document. |
| `AZURE_DOCINT_POLL_GAP` | `1.5` | Seconds between polls of the whole batch. |
| `AZURE_DOCINT_SUBMIT_GAP` | `0` | Seconds between submissions. Raise if F0 429s faster than the backoff recovers. |
| `DOCINT_USE_CACHE` | `true` | Reuse `out/azure/di_raw/`. Set `false` to re-bill every run. |
| `DOCINT_MAX_DOCUMENTS` | `60` | Guard against pointing this at 4,000 documents by accident. |

---

## 9 · Every output file

Everything lands under `out/<provider>/`, so a mock run and an azure run never
overwrite each other.

| File | What is in it |
|---|---|
| `multidoc_report.md` | The report for your ADR — strategy comparison, the packages, **and the six questions you have to answer.** |
| `stitch_results.csv` | Every field, every package, every strategy: `strategy, package, field, value, source, agreement`. Sort by `agreement` to find every conflict at once. |
| `unified/PKG-XXX.json` | What your pipeline would actually return for one package: the unified record, provenance per field, conflicts, the identity verdict, the async summary. |
| `query_field_report.md` | **azure only.** What asking cost — per document, answered vs empty, measured confidences, and the over-ask table. |
| `di_raw/PKG-XXX/*.json` | **azure only.** The untouched service responses. This is the cache; it is also your evidence. |
| `di_raw_overask/` | **azure only.** Same, for `--overask` runs — kept separate so one cannot pollute the other. |

### The field to look at first in a unified record

```json
"provenance": {
  "account_number": { "source": null, "confidence": null, "agreement": "CONFLICT_unresolved" }
}
```

`agreement` is the field that tells you whether a value was agreed, resolved by
a rule, or refused. A value with no provenance is a value nobody can defend.

---

## 10 · Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: unsupported operand type(s) for \|` | Python older than 3.9 on an older copy of this lab | Pull the current version, or use `python3.12` |
| Numbers are not 4 / 2 / 0 on mock | Something changed in the pipeline | `python3 run_lab.py --selftest` — it will name the check that broke |
| `DOCINT_PROVIDER=azure needs AZURE_DOCINT_ENDPOINT` | No `.env`, or the values are still placeholders | `cp .env.example .env` and fill in both values |
| `... does not exist. Render the documents first` | The PDFs have not been made | `python3 run_lab.py --make-pdfs` |
| **HTTP 404** talking about the model | The **route**, not the model | api-version ≥ `2024-11-30` needs `/documentintelligence/`. Set `AZURE_DOCINT_ROUTE` to force it |
| **HTTP 401 / 403** | Key does not belong to that endpoint | A key from a *different* Azure AI resource returns exactly this. Re-copy both from the same resource blade |
| **HTTP 429**, run eventually fails | Rate limit harder than the backoff | Raise `AZURE_DOCINT_SUBMIT_GAP` to `2`–`5`, or move off F0. Occasional 429s are normal and handled |
| **HTTP 400** mentioning `queryFields` | Add-on unavailable on that tier/region, or >20 field names | Check the resource tier; keep query lists short |
| HTTP 200 but **zero fields** | `features=queryFields` missing | The lab adds it for you — if you are hand-rolling the call, this is why |
| Run is slow the first time | Expected — 32 billed analyses | Every later run reads `out/azure/di_raw/` and is instant |
| Want to re-bill deliberately | Cache is on | `rm -rf out/azure/di_raw/`, or set `DOCINT_USE_CACHE=false` |

---

## 11 · How the code is laid out

```
run_lab.py                    the command you run — CLI, scoring, reports
multidoc_lab/
  packages.py                 8 case packages, query field lists, precedence,
                              form labels. THE SINGLE SOURCE OF TRUTH.
  pipeline.py                 async orchestration, identity verification,
                              stitching, blob paths.  Provider-agnostic.
  config.py                   the provider switch and every setting
  provider.py                 the seam — picks a backend, returns it
  mock_multidoc.py            backend 1: offline, free, deterministic
  azure_multidoc.py           backend 2: real REST calls to Document Intelligence
  make_pdfs.py                renders the 32 documents as PDFs (stdlib only)
  selftest.py                 108 offline checks
docs/PKG-XXX/*.pdf            generated — what the azure provider posts
out/<provider>/               generated — reports, CSV, unified records
.env.example                  copy to .env and fill in
```

### The seam

Both backends expose exactly two functions:

```python
start(pkg_id, doc_type) -> handle     # submit. does not block.
poll(handle)            -> (state, fields, error)
```

`pipeline.AsyncAnalyzer` drives both through that pair and never asks which one
it got. `pipeline.py` does not import `config.py`, `provider.py` or
`azure_multidoc.py` at all.

Keep the seam this narrow and *"can we swap Document Intelligence for
Textract"* is a one-file question with an honest answer. Let vendor types leak
past it and the same question needs a project.

### The async part is not a simulation on the azure path

On the mock, "submit returns before the answer exists" is something the mock
politely pretends. On azure it is simply true: the POST gives you a URL and no
result, and a bank statement really is still working when a payslip has
finished. Every orphan, every partial package and every ordering problem in
this lab is a real property of this API.

Note the shape of `await_all`: one pass over **all** jobs, then a pause, then
another pass. Not `for job: wait until this one finishes` — that version is the
one people write first, and it serialises the whole batch so the asynchronous
API you chose buys you nothing.

**The handle is the job.** On Azure it is an `Operation-Location` URL that
outlives this process. Keep it only in memory and a restart loses 32 analyses
you have already paid for. That is the durable-state requirement, made concrete.

### Moving this to production

| In this lab | In Azure |
|---|---|
| `AsyncAnalyzer.submit` | `begin_analyze_document(...)` — returns a poller |
| `await_all` | An orchestrator (Durable Functions), or Event Grid on completion |
| `QUERY_FIELDS` | The `queryFields` add-on parameter — **already real here** |
| `verify_identity` | **Your own code.** There is no service for your rules |
| `stitch` | **Your own code.** This is the part nobody sells you |
| `blob_path` | Blob naming plus lifecycle management rules |

**The two rows that say "your own code" are the two that carry the risk** — and
§7.1 is the measurement that proves it.

**Verify current SDK, model names and API versions before you build.** This lab
pins `prebuilt-layout` + `2024-11-30` because that is what was current and
tested; Microsoft has already moved this route once.

---

## 12 · Before you present

- [ ] You can explain the identity verdict boundary and point at the code
- [ ] You can say why PKG-005 nearly passed, in one sentence about tolerance
- [ ] You know what caught PKG-008, and whether it would catch a subtler version
- [ ] You ran `--failures` and can describe what happened to the verdicts
- [ ] You have a policy for a package that arrives incomplete
- [ ] You can name what is in your Blob path and what it makes possible
- [ ] You can say which of `trust_form` / `trust_evidence` / `reconcile` you are
      recommending, and what it costs at the client's real monthly volume
- [ ] **If you ran azure:** you can explain why the results were *identical* to
      the mock, and why that is the finding rather than an anticlimax
- [ ] **If you ran `--overask`:** you can say what came back for a field the
      document did not have, and which line of your own code stopped it
- [ ] You know which numbers from the azure run you are **not** entitled to
      quote, and why

---

### A note on Query Fields and the bill

Day 14's `prebuilt-layout` + `keyValuePairs` returns whatever pairs it finds.
Query Fields lets you **ask** for specific fields by name, which cuts the noise
considerably.

Two things it does not do, and this lab measured both:

1. **Asking for a field does not make it exist.** Measured in §7.3: 8 of 72
   over-asked requests came back with a plausible, confident, wrong value in
   them.
2. **It is a paid add-on, billed per document.** Asking for twelve fields when
   you need five is a line on the bill, on every document, forever.
   `QUERY_FIELDS` in `packages.py` is that bill — 152 requests across 32
   documents in this lab. Justify each entry.

---

*Companion document: `Day15_MultiDoc_Interpreting_Your_Results.docx` — what each
command prints, what every parameter does, and how to read the output.*
