# Query Fields — what you asked for, and what it cost

Documents analysed: **32**  ·  field requests sent: **152**  ·  answered: **152**  ·  returned empty: **0**

Query fields are a **paid add-on, billed per document**. The number above is not a statistic, it is a line on an invoice — every request in it recurs on every document, forever. `QUERY_FIELDS` in `packages.py` is that bill. Justify each entry.

## Per document

| Package | Document | Asked | Answered | Empty | Mean confidence |
|---|---|---|---|---|---|
| PKG-001 | bank_statement | 4 | 4 | — | 0.995 |
| PKG-001 | case_form | 6 | 6 | — | 0.985 |
| PKG-001 | identity | 5 | 5 | — | 0.986 |
| PKG-001 | payslip | 4 | 4 | — | 0.993 |
| PKG-002 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-002 | case_form | 6 | 6 | — | 0.985 |
| PKG-002 | identity | 5 | 5 | — | 0.991 |
| PKG-002 | payslip | 4 | 4 | — | 0.993 |
| PKG-003 | bank_statement | 4 | 4 | — | 0.993 |
| PKG-003 | case_form | 6 | 6 | — | 0.989 |
| PKG-003 | identity | 5 | 5 | — | 0.987 |
| PKG-003 | payslip | 4 | 4 | — | 0.994 |
| PKG-004 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-004 | case_form | 6 | 6 | — | 0.989 |
| PKG-004 | identity | 5 | 5 | — | 0.919 |
| PKG-004 | payslip | 4 | 4 | — | 0.994 |
| PKG-005 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-005 | case_form | 6 | 6 | — | 0.989 |
| PKG-005 | identity | 5 | 5 | — | 0.991 |
| PKG-005 | payslip | 4 | 4 | — | 0.994 |
| PKG-006 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-006 | case_form | 6 | 6 | — | 0.988 |
| PKG-006 | identity | 5 | 5 | — | 0.903 |
| PKG-007 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-007 | case_form | 6 | 6 | — | 0.988 |
| PKG-007 | identity | 5 | 5 | — | 0.984 |
| PKG-007 | payslip | 4 | 4 | — | 0.994 |
| PKG-007 | payslip_2 | 4 | 4 | — | 0.994 |
| PKG-008 | bank_statement | 4 | 4 | — | 0.994 |
| PKG-008 | case_form | 6 | 6 | — | 0.988 |
| PKG-008 | identity | 5 | 5 | — | 0.953 |
| PKG-008 | payslip | 4 | 4 | — | 0.992 |

## Read this before you draw a conclusion

**An empty query field is not a service failure.** It is the service declining to invent, which is the behaviour you want. It lands in `documents_missing` or leaves the field absent, and both are visible.

**These PDFs are digitally generated.** The text is embedded, not scanned, so the service reads it far more confidently than it would read the forms this lab is modelling. Confidence measured here is a **ceiling, not an estimate**. To get a real number, run the client's own scans through the same pipeline — that is the first thing to ask for.

**The conflicts survive the round trip, and that is the point.** PKG-005's account number really does differ by one digit on the rendered documents. PKG-008's bank statement really does carry a different person's name. The service reads all of it correctly, at high confidence, and hands you documents that disagree. Nothing about the extraction is wrong. Everything about the record you build from it can be.
