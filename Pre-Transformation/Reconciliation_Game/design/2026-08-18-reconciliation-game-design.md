# The Reconciliation Game — design

**Birlasoft FORGE FDE Academy · DecisionStream AI · Sprint 1 Day 15**
**Status:** approved 2026-08-18 · **Supersedes:** nothing · **Companion to:** the Day 15 multi-document lab

---

## 1 · What this is and why it is not a port

Day 14 shipped **The Threshold Game**: ten documents, a confidence slider per
field, seven validators, and a leaderboard that proves threshold tuning cannot
beat validation. It works because Day 14's pipeline *has* confidence
thresholds to tune.

Day 15's pipeline has none. There is no threshold anywhere in
`multidoc_lab/`; confidence is carried and reported, never used as a gate.
What Day 15 has instead is a **reconciliation policy** — a numeric tolerance,
a set of fields compared exactly, and a per-field rule for who wins when four
documents disagree.

So the mechanic is re-derived rather than ported. The *shape* of the lesson is
the same and deliberately so:

> Tuning moves **who looks at** a value.
> Validation changes **whether the value is right**.

Day 14 taught that with thresholds. Day 15 teaches it with reconciliation, and
adds a failure mode Day 14 had no room for: a check that vanishes because the
document carrying it never arrived.

## 2 · Non-goals

- **No confidence thresholds.** Adding them would misrepresent the lab.
- **No new packages.** The eight lab packages are the corpus.
- **No credential panel.** See §9.
- **No JavaScript engine.** Day 14 carried a second implementation inside its
  HTML board and needed `verify.py` to stop the two drifting. We ship Python
  only, so there is nothing to keep in sync.
- **No changes to `pipeline.stitch()`.** See §3.

---

## 3 · Architecture

### 3.1 The coupling decision

The game **imports** the lab. It does not copy it and it does not modify it.

```
multidoc_lab/packages.py     ── corpus + truth ──►  reconciliation_game/corpus.py
multidoc_lab/pipeline.py     ── verify_identity ─►  reconciliation_game/game.py
                             ── stitch() ─────────►  selftest only (as the pin)
```

`pipeline.stitch()` takes one global strategy, a tolerance, and reads
module-level `IDENTIFIER_FIELDS` and `PRECEDENCE`. The game needs per-field
strategy, a mutable identifier set, and seven checks that do not exist in the
lab at all.

Two ways to get there:

| Option | Trade-off |
|---|---|
| Extend `stitch()` with six parameters | One implementation, but `stitch()` is the reference code learners *read* in Step 1 of the lab. Six knobs and seven check hooks would destroy the thing that makes it legible. Rejected. |
| **Game implements `apply_policy()`** | Two implementations of overlapping logic — the drift risk Day 14 had. Mitigated by the pin test in §3.2, which is strictly stronger than Day 14's `verify.py` because both sides are Python. **Chosen.** |

### 3.2 The pin test

`selftest_game.py` asserts that this policy:

```python
Policy(strategy={f: "reconcile" for f in FIELDS},
       tolerance=0.02,
       identifiers={"account_number", "claim_reference"},
       checks={c: False for c in CHECKS},
       keep_identity_evidence=False)
```

produces, for all eight packages, a `unified` dict **equal** to
`pipeline.stitch(doc_fields, "reconcile")["unified"]`, and a `provenance` dict
with the same `source` and `agreement` for every field.

If someone changes `stitch()`, this test fails and the game is corrected. If
someone changes the game's engine, this test fails and they find out before a
room does. The lab remains the source of truth for what reconciliation means.

> `sort_code` is in the lab's `IDENTIFIER_FIELDS` but is not a unified field,
> so it never reaches `stitch()`'s comparison. The game's identifier set covers
> only the six unified fields; the pin test is unaffected.

### 3.3 Module layout

```
Reconciliation_Game/
  README.md                       trainer + learner doc
  app.py                          Streamlit board
  play.py                         terminal, --watch, stdlib only
  policy.json                     what players edit (created on first run)
  requirements.txt                streamlit only
  reconciliation_game/
    __init__.py
    corpus.py                     adapter: packages + extended truth + hints
    game.py                       Policy, apply_policy, score, presets
    search.py                     measures the tuning ceiling
    selftest_game.py              incl. the §3.2 pin test
  design/
    2026-08-18-reconciliation-game-design.md
  .vscode/tasks.json              Ctrl+Shift+B runs the watcher
```

`game.py` and `play.py` are standard library only. `app.py` is the only file
that imports Streamlit. That matters: a learner on a locked-down VM with no
`pip` still gets the whole game through `play.py`.

---

## 4 · The policy — what players tune

### 4.1 Knobs

| Knob | Type | Default (the brief) | Effect |
|---|---|---|---|
| `tolerance` | float 0.00 – 0.25 | 0.02 | Numeric agreement band. Two quantities within this fraction are "the same value". |
| `identifiers` | set of fields | `{account_number}` | Fields compared **exactly**, ignoring `tolerance`. |
| `strategy[field]` | one of three, ×6 | `trust_form` | Who wins the conflict: the applicant's form, the documentary evidence (by `PRECEDENCE`), or nobody. |
| `keep_identity_evidence` | bool | **true** | Attach `document_number` and `expiry_date` to the record "so a reviewer can re-check it later". |

`PRECEDENCE` itself is **not** tunable. It is already written down in
`packages.py` with a comment explaining why it is written down, and exposing it
as a fourth knob triples the search space for no additional lesson. Deliberate
YAGNI.

### 4.2 Checks

| Check | Rule | Catches |
|---|---|---|
| `identity_match` | Name and DOB on the identity document must match the form. Failure flags the package. | PKG-002 |
| `identity_validity` | Identity document must not have expired before `INCIDENT_DATE`. | PKG-003 |
| `cross_doc_name` | The same person must appear on **every** document carrying a name — form, identity, payslip, bank statement. | **PKG-008** |
| `evidence_required` | `annual_income` and `account_number` may not be sourced from `case_form` alone. | PKG-006 |
| `period_coherence` | Two payslips covering different periods cannot both feed `annual_income`. | PKG-007 |
| `completeness_gate` | Every expected document type must have arrived. A missing document means a missing **check**, not just missing data. | §7 |
| `tolerance_guard` | `tolerance` may never apply to a field in `identifiers`, and identifier-shaped fields are auto-added to `identifiers`. | nothing, on this corpus — see below |

`tolerance_guard` deserves a note, and the note has been **corrected against
the measurement**. This design originally claimed the guard catches PKG-005.
It does not, and the built game proves it does not. Read
[`README.md` §5](../README.md) before touching this check.

It is the check that makes a *knob* safe, which is unusual — the other six add
information, this one removes a foot-gun. It forces an exact comparison on
identifier-shaped fields so that a player who slides `tolerance` to 0.10 to
stop the income conflicts cannot silently start comparing account numbers
numerically. That is the point of including a tolerance slider at all.

**What it is worth, measured, is nothing — and less than nothing when it acts.**
`account_number` is already in `identifiers` in every preset, so the guard is a
no-op against all six and scores **+0**. It only does anything once a player
empties that set, and on this corpus doing so *lowers* the score: a tolerant
merge of PKG-005's `20558193` and `20558198` happens to land on `20558198`,
which is the correct value, so the guard converts a lucky-correct accept into a
refusal, or under `trust_form` into a wrong accept. Across a large random sweep
it never improves a score and never removes a wrong accept.

**This is not a defect and it must not be "repaired".** The guard is right and
unrewarded: without it the record was correct *by accident*, and the accident
is a property of this eight-package corpus rather than of the rule. The
scoreboard cannot see the difference between a policy that is correct and a
policy that got the right answer, and §5 of the README teaches that gap
deliberately rather than hiding it.

If the guard is ever to be worth positive points, the fix is a **second
tolerance-sensitive package** whose tolerated merge lands on the *wrong* value.
That is a corpus change, not a check change and not a scoring change.

### 4.3 The `keep_identity_evidence` inversion

In Day 14, `scope_gate` was the most valuable single check at **+300** — the
most valuable validator in the set was not an accuracy control at all.

That cannot be reproduced here, because Day 15's `stitch()` already never emits
identity fields: `FIELD_SOURCES` has no mapping for `document_number`,
`expiry_date` or `issuing_country`, so a scope *check* would be worth exactly
zero and would teach nothing.

So the lesson is inverted into a **knob that sounds like diligence**:

> `keep_identity_evidence` — *attach the licence number and expiry to the
> record so a reviewer can re-check it later.*

It costs **−300 per package**, the single most expensive setting on the board,
and it is **on by default in the brief preset**. It is the only knob that
cannot be recovered by tuning anything else.

This makes README §2 of the lab — *"you process the identity document, you keep
the verdict, you discard the evidence"* — a thing the room loses points to
rather than a thing a slide asserts. Nobody argues with a scoreboard.

---

## 5 · Scoring

```
 +10   correct value accepted into the unified record
-150   WRONG value accepted (a conflict resolved to the wrong side)
  -2   a field refused / sent to a human
 -20   required field absent and not flagged
 -60   a value accepted that REQUIRES evidence and was sourced from the form alone
-200   record accepted although the identity verdict did not pass
 -40   identity verdict impossible (no identity document) and not flagged
-300   identity evidence retained, per package
```

Two of those need their wording defended, because an earlier draft got both
wrong in a way that would have made two checks worthless.

**`-200` is for ignoring the verdict, not for computing it wrongly.**
`verify_identity()` already returns the correct verdict for all eight packages
with no checks switched on at all — it is unconditional in `run_lab.process()`.
What the lab does *not* do is act on it: a failed verdict never stops the
record being assembled. So the penalty attaches to accepting a record whose
verdict did not pass, which is what `identity_match` and `identity_validity`
exist to prevent. Scored the other way round, both checks would be worth zero.

**`-60` for an unevidenced accept, not `-150`.** PKG-006's income is *correct* —
47,000 really is the number. Charging a wrong-accept penalty for a right answer
would be dishonest scoring. The defect is that the record cannot tell
`declared` from `evidenced`, which is worth real money and is not worth a
broken case. Without this line `evidence_required` could only ever cost flags,
and would be a check nobody rationally switches on.

The asymmetry is inherited from Day 14 and is the whole design: one wrong
acceptance costs more than seventy flags. A flag costs a handler half a minute
and somebody knows it happened. A wrongly accepted account number sends the
payment to a stranger and nobody finds out until they complain.

**Scored surface:** 8 packages × 6 fields = 48 field decisions, plus 8 identity
verdicts, plus 8 scope decisions. Day 14 had 90 field decisions; this is
comparable, and materially wider than the lab's current 16.

**The constants are provisional.** They are tuned after the engine exists, not
before, against the requirement in §6.

---

## 6 · The property the game must have

The game only teaches the right thing while **validation strictly dominates
tuning**. Concretely, after the constants are tuned, all four must hold:

1. `all checks on, knobs left at the brief's defaults` scores **higher** than
   the best policy `search.py` finds with every check off.
2. That all-checks-on policy reaches **zero wrong accepts**.
3. `flag everything` (all `reconcile`, tolerance 0) scores **worse** than
   all-checks-on — refusing everything is not the answer either.
4. `all checks on + tightened knobs` scores **no better** than all-checks-on
   alone, reproducing Day 14's second finding: tightening on top of working
   validation buys flags and prevents nothing.

If tuning the constants cannot satisfy all four, the check set or the corpus is
wrong and gets revisited — **not** the requirement.

### 6.1 The tuning ceiling is measured, not asserted

`search.py` runs a random search over knob-space with every check off, and
reports the best score it found. The README quotes that number and says
plainly that a random search finds the best it happened to try, never provably
the best there is. Every number in the README is produced by the same engine
the room plays against.

---

## 7 · Resilience — the Day-15-only mechanic

Day 14 had no equivalent. The lab's Step 3 does:

```bash
python3 run_lab.py --strategy reconcile --failures 0.2
```

`reconcile` accepts **zero** wrong values on a healthy run and **three** at a
20% failure rate. Not because stitching got worse — because a lost document
removes the second opinion that made the conflict visible. One value cannot
disagree with anything.

The game exposes this as a **failure-rate control** (0 / 10 / 20 / 30%) and
scores the player's policy at all four rates side by side, reusing the lab's
seeded injection so every learner sees the same table.

The discovery: a policy that scores well at 0% collapses at 20% **unless**
`completeness_gate` is on. That check is worth nothing on a healthy run and is
the difference between a good policy and a dangerous one on a degraded one.

> Losing a document does not just lose data. It loses the **check** that
> document was there to perform.

---

## 8 · Truth extension

Each package's `truth` dict in `multidoc_lab/packages.py` grows from two scored
fields to all six, derived from the corpus:

| Package | applicant_name | date_of_birth | annual_income | employer_name | account_number | claim_reference | verified |
|---|---|---|---|---|---|---|---|
| PKG-001 | PERSON_01 | 1987-04-12 | 42000.00 | Halewood | 44182903 | CLM-2026-4471 | ✓ |
| PKG-002 | **CONFLICT** | 1991-09-30 | 38000.04 | Brightwell | 77219044 | CLM-2026-4482 | ✗ |
| PKG-003 | PERSON_03 | 1979-11-05 | 51000.00 | Kestrel | 10559871 | CLM-2026-4503 | ✗ |
| PKG-004 | PERSON_04 | 1984-02-17 | **43500.00** | Marlow | 88304127 | CLM-2026-4517 | ✓ |
| PKG-005 | PERSON_05 | 1996-06-21 | 35000.04 | Fenwick | **20558198** | CLM-2026-4526 | ✓ |
| PKG-006 | PERSON_06 | 1988-12-03 | 47000.00 (unevidenced) | Tarn Valley | 63920174 | CLM-2026-4534 | ✓ |
| PKG-007 | PERSON_07 | 1972-05-08 | **AMBIGUOUS** | Crowther | 91447035 | CLM-2026-4548 | ✓ |
| PKG-008 | **CONFLICT** | 1990-01-22 | 44000.04 | Ridgeway | **CONFLICT** | CLM-2026-4573 | ✓ |

Two facts this table makes visible that the two-field version could not:

- **PKG-008 is `verified: True`.** The identity document matches the form
  perfectly. Identity verification passes and the package is still wrong.
  Only `cross_doc_name` catches it. This is the single most important cell in
  the table.
- **`applicant_name` carries two conflicts.** Widening from two fields to six
  is what makes name reconciliation scoreable at all.

**Additivity requirement.** `run_lab.py:score()` reads only `annual_income`,
`account_number`, `verified`, `conflicts` and `requires_evidence`. The
extension adds keys and changes none of those. Proof obligation:
`python3 run_lab.py --selftest` reports **108/108** and `python3 run_lab.py`
reports **4 / 2 / 0** wrong accepted, before and after.

---

## 9 · Surfaces

### 9.1 Streamlit board (`app.py`) — the demo

Tabs, mirroring Day 14's board:

| Tab | Content |
|---|---|
| Per package | Eight cards, score each, red/green on wrong accepts |
| Field detail | Every field × package: sources, what was picked, why, provenance |
| How scoring works | The points table, applied live to the current policy |
| Strategy comparison | Presets vs the player's policy, incl. the measured tuning ceiling |
| The packages | What each package is testing — the hint table |
| **Resilience** | The §7 failure-rate table |
| Mock vs live | **Only if `out/azure/unified/*.json` exists on disk** |

Sidebar carries the knobs, the checks, the preset buttons and the running
score, exactly as Day 14 does.

### 9.2 No credential panel — a deliberate difference from Day 14

Day 14's board asks for an Azure endpoint and key, holds them for the browser
session, and caches responses under `out/azure/`. Its README then spends four
paragraphs explaining that on a hosted deployment that cache is shared between
strangers and that a restart re-bills the next run.

This board does not need any of that. If a trainer has already run

```bash
python3 run_lab.py --provider azure
```

the unified records are on disk, and `app.py` reads them and offers the *Mock
vs live* tab. If they have not, the tab is absent and everything else works.

Nothing to paste, nothing to cache, no key in a hosted app, and no
32-document 3-minute billed call triggered by a button in a room. Strictly
safer and strictly cheaper than the Day 14 arrangement.

### 9.3 Terminal (`play.py`)

Standard library only.

```bash
python3 play.py --watch          # split VS Code: policy.json | watcher
python3 play.py --pkg PKG-008    # one package, field by field
python3 play.py --compare        # the presets
python3 play.py --hint           # what each package is testing
python3 play.py --resilience     # the §7 table
```

The `--watch` loop is the one that feels like engineering: `policy.json` on the
left, watcher on the right, change a number, save, the score moves before you
look back up. Under a second and people experiment; over five and they start
planning instead, which is a slower way to learn the same thing.

---

## 10 · Presets

| Preset | Setting | Intent |
|---|---|---|
| **The brief** | `trust_form` everywhere, tolerance 0.02, identifiers `{account_number}`, no checks, `keep_identity_evidence` **on** | What the curriculum literally specifies. Opens the session. Should score badly. |
| **The lab** | `reconcile` everywhere, lab defaults, no checks | Reproduces `run_lab.py --strategy reconcile` exactly. Also the §3.2 pin. |
| **Trust the paperwork** | `trust_evidence` everywhere, no checks | The obvious second idea. |
| **Flag everything** | `reconcile` everywhere, tolerance 0 | Refuse-everything. Must lose — §6.3. |
| **Best tuning found** | whatever `search.py` measured | The honest ceiling, with its trial count quoted. |
| **All checks on** | brief's knobs, every check on, evidence off | The winner. |

---

## 11 · Testing

`selftest_game.py`, standard library, no network:

1. **Pin to lab** (§3.2) — game's lab preset ≡ `pipeline.stitch(..., "reconcile")`, all eight packages, unified and provenance.
2. **Lab unchanged** — `run_lab.py --selftest` still 108/108; `run_lab.py` still 4 / 2 / 0.
3. **Scoring arithmetic** — hand-computed score for one package under one policy.
4. **Each check earns its place** — every check fires on the package it claims in §4.2, and no check fires on PKG-001.
5. **Scope holds under every policy** — with `keep_identity_evidence` off, no `document_number`, `expiry_date` or `issuing_country` appears in any unified record, under all six presets and a random sample of policies. This is the lab's own invariant and it must not weaken.
6. **Presets score what the README says** — the strategy table is generated, never hand-typed.
7. **Determinism** — same policy and seed produce the same score, at every failure rate.
8. **§6 property holds** — the four orderings, asserted as a test rather than checked once by hand.

Test 8 is the important one. It is the difference between a game that teaches
the lesson and a game that used to.

---

## 12 · Build order

1. `corpus.py` + truth extension, with the additivity proof (§8) as the first test.
2. `game.py`: `Policy`, `apply_policy`, pin test green before any check is written.
3. Checks, one at a time, each with its catching test.
4. Scoring, then `search.py`, then tune the constants until §6 holds.
5. `play.py`.
6. `app.py`.
7. `README.md`, with every number generated by the engine.

Steps 1–4 are the game. Steps 5–6 are two views of it. If the constants cannot
be tuned to satisfy §6, stop at step 4 and revisit the check set — shipping a
board that rewards tuning would teach the opposite of the lab.
