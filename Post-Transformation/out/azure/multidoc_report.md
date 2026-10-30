# Multi-document extraction report — DecisionStream AI

Packages: **8**   Documents: **32**   Injected async failure rate: **0%**

Source: **azure** (Azure AI Document Intelligence, prebuilt-layout + queryFields — measured confidences; see `query_field_report.md`)

## Stitching strategy comparison

| Strategy | Wrong accepted | Refused (flagged) | Conflicts surfaced | Verdicts correct |
|---|---|---|---|---|
| trust_form | **4** | 0 | 6 | 8/8 |
| trust_evidence | **2** | 0 | 6 | 8/8 |
| reconcile | **0** | 4 | 6 | 8/8 |

### How to read this

**Wrong accepted** is the only column that can hurt a customer. Those are values written into the unified record, with no flag, that are not correct.

`trust_form` believes the applicant. `trust_evidence` believes the paperwork. Both produce a complete record and both will be wrong silently when the two sources disagree for a reason neither strategy understands. `reconcile` refuses and flags — which costs a handler time on every conflict, including the trivial ones.

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

1. Which field is authoritative from which document, and who signed that precedence table off?
2. PKG-008 contains a bank statement belonging to a different person. Every field in it is high confidence and internally consistent. What caught it, and would that check have caught a subtler version?
3. Your identity verification returns a verdict and keeps nothing. Can you point at the line of code that guarantees that?
4. A package arrives with three of four documents. Do you process it or hold it, and who decided?
5. An async job never completes. How long before anyone notices, and what notices?
6. What is in your Blob path, and which retention or residency operation would be impossible without it?
