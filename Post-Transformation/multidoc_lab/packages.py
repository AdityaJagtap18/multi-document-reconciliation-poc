"""
packages.py — eight multi-document case packages, as Document Intelligence
Query Fields would return them.

WHAT A CASE PACKAGE IS
----------------------
Not one PDF. Four:

    case_form        the application itself
    identity         a driving licence or passport scan
    payslip          evidence of income
    bank_statement   evidence of the account

Yesterday you extracted ONE document. Today you have to make four documents
agree with each other — and they will not.

WHY THIS IS HARDER THAN IT LOOKS
--------------------------------
Each document is individually fine. Each extraction is individually confident.
The failure lives BETWEEN them:

  * the name on the licence is not the name on the form
  * the income declared is not the income on the payslip
  * the account number differs by one digit
  * the licence expired last month
  * a payslip was submitted twice for different months
  * a document is missing entirely
  * a document is perfectly valid and belongs to somebody else

That last one is the dangerous case. Nothing about it looks wrong. It stitches
silently into a unified record for the wrong applicant.

QUERY FIELDS
------------
Yesterday's prebuilt-document model returns whatever key-value pairs it finds.
Query Fields lets you ASK for specific fields by name — income, employer,
account number — which cuts the noise considerably.

Two things it does NOT do, and both matter:

  1. Asking for a field does not make it exist. A field you asked for and the
     document does not contain still comes back, with a low confidence and
     sometimes with something plausible in it.
  2. It is a paid add-on. Asking for twelve fields when you need five is a
     line on the bill, repeated on every document, forever.
"""

from __future__ import annotations

import copy


def _f(name, value, conf, page=1):
    return {"field": name, "value": value, "confidence": conf, "page": page}


# --------------------------------------------------------------------------
# The fields we ASK FOR, per document type. This list is the cost.
# --------------------------------------------------------------------------
QUERY_FIELDS = {
    "case_form": ["applicant_name", "date_of_birth", "annual_income",
                  "employer_name", "account_number", "claim_reference"],
    "identity": ["holder_name", "date_of_birth", "document_number",
                 "expiry_date", "issuing_country"],
    "payslip": ["employee_name", "employer_name", "gross_monthly_pay",
                "pay_period"],
    "bank_statement": ["account_holder_name", "account_number", "sort_code",
                       "statement_period"],
}

# --------------------------------------------------------------------------
# What each field is CALLED ON THE PAGE.
#
# The names above are ours. These are the form designer's. `make_pdfs.py`
# prints these, and the real service is asked for our name and has to find the
# designer's label by meaning — which is the entire proposition of Query
# Fields, and the thing you cannot test with a mock whose keys already match.
#
# Nothing downstream reads this map. It exists so that the PDFs the azure
# provider posts look like documents rather than like our data model.
# --------------------------------------------------------------------------
LABELS = {
    "applicant_name":     "Applicant Name",
    "date_of_birth":      "Date of Birth",
    "annual_income":      "Declared Annual Income (GBP)",
    "employer_name":      "Employer",
    "account_number":     "Account Number",
    "claim_reference":    "Claim Reference",
    "holder_name":        "Holder Name",
    "document_number":    "Licence Number",
    "expiry_date":        "Valid Until",
    "issuing_country":    "Issuing Country",
    "employee_name":      "Employee Name",
    "gross_monthly_pay":  "Gross Monthly Pay (GBP)",
    "pay_period":         "Pay Period",
    "account_holder_name": "Account Holder",
    "sort_code":          "Sort Code",
    "statement_period":   "Statement Period",
}

# The title printed at the top of each rendered document, and how many pages it
# runs to. Every QUERY FIELD sits on page 1 by design: a free-tier resource
# reads the first two pages and stops, and this lab is not about that limit —
# Day 14 already taught it. The extra pages carry the prose a real document
# would carry, so the service has something to read besides our fields.
DOC_LAYOUT = {
    "case_form":      {"title": "MOTOR CLAIM APPLICATION FORM", "pages": 2},
    "identity":       {"title": "DRIVING LICENCE", "pages": 1},
    "payslip":        {"title": "PAYSLIP", "pages": 1},
    "bank_statement": {"title": "BANK STATEMENT", "pages": 2},
}

# Which document is AUTHORITATIVE for which field. Written down, because if it
# is not written down it will be decided implicitly by whichever branch of an
# if-statement happens to run first.
PRECEDENCE = {
    "applicant_name":  ["identity", "bank_statement", "case_form"],
    "date_of_birth":   ["identity", "case_form"],
    "annual_income":   ["payslip", "case_form"],
    "employer_name":   ["payslip", "case_form"],
    "account_number":  ["bank_statement", "case_form"],
    "claim_reference": ["case_form"],
}


PACKAGES: list[dict] = [

# 1 — clean
{"id": "PKG-001", "note": "clean package, everything agrees",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_01]", 0.96), _f("date_of_birth", "1987-04-12", 0.95),
                 _f("annual_income", "42000.00", 0.94), _f("employer_name", "Halewood Logistics Ltd", 0.93),
                 _f("account_number", "44182903", 0.95), _f("claim_reference", "CLM-2026-4471", 0.97)],
   "identity": [_f("holder_name", "[PERSON_01]", 0.95), _f("date_of_birth", "1987-04-12", 0.94),
                _f("document_number", "SMITH8704127AB9CD", 0.92), _f("expiry_date", "2029-03-31", 0.93),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_01]", 0.94), _f("employer_name", "Halewood Logistics Ltd", 0.95),
               _f("gross_monthly_pay", "3500.00", 0.93), _f("pay_period", "2026-03", 0.94)],
   "bank_statement": [_f("account_holder_name", "[PERSON_01]", 0.95), _f("account_number", "44182903", 0.96),
                      _f("sort_code", "20-45-118", 0.94), _f("statement_period", "2026-03", 0.95)],
 },
 "truth": {"verified": True, "conflicts": 0, "annual_income": 42000.00, "account_number": "44182903",
           "applicant_name": "[PERSON_01]", "date_of_birth": "1987-04-12",
           "employer_name": "Halewood Logistics Ltd", "claim_reference": "CLM-2026-4471"}},

# 2 — name mismatch: form says one name, licence says another
{"id": "PKG-002", "note": "name on identity does not match the form",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_02]", 0.95), _f("date_of_birth", "1991-09-30", 0.94),
                 _f("annual_income", "38000.00", 0.93), _f("employer_name", "Brightwell Retail plc", 0.94),
                 _f("account_number", "77219044", 0.95), _f("claim_reference", "CLM-2026-4482", 0.96)],
   "identity": [_f("holder_name", "[PERSON_02B]", 0.94), _f("date_of_birth", "1991-09-30", 0.93),
                _f("document_number", "JONES9109302CD1EF", 0.91), _f("expiry_date", "2030-06-30", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_02]", 0.93), _f("employer_name", "Brightwell Retail plc", 0.94),
               _f("gross_monthly_pay", "3166.67", 0.92), _f("pay_period", "2026-03", 0.93)],
   "bank_statement": [_f("account_holder_name", "[PERSON_02]", 0.94), _f("account_number", "77219044", 0.95),
                      _f("sort_code", "30-11-882", 0.93), _f("statement_period", "2026-03", 0.94)],
 },
 "truth": {"verified": False, "conflicts": 1, "annual_income": 38000.04, "account_number": "77219044",
           "applicant_name": "CONFLICT", "date_of_birth": "1991-09-30",
           "employer_name": "Brightwell Retail plc", "claim_reference": "CLM-2026-4482",
           "why": "identity name mismatch - could be a married name, could be the wrong person"}},

# 3 — expired identity document
{"id": "PKG-003", "note": "identity document expired before the incident",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_03]", 0.96), _f("date_of_birth", "1979-11-05", 0.94),
                 _f("annual_income", "51000.00", 0.94), _f("employer_name", "Kestrel Engineering", 0.93),
                 _f("account_number", "10559871", 0.95), _f("claim_reference", "CLM-2026-4503", 0.96)],
   "identity": [_f("holder_name", "[PERSON_03]", 0.95), _f("date_of_birth", "1979-11-05", 0.94),
                _f("document_number", "PATEL7911053GH2IJ", 0.92), _f("expiry_date", "2026-01-31", 0.95),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_03]", 0.94), _f("employer_name", "Kestrel Engineering", 0.94),
               _f("gross_monthly_pay", "4250.00", 0.93), _f("pay_period", "2026-03", 0.94)],
   "bank_statement": [_f("account_holder_name", "[PERSON_03]", 0.95), _f("account_number", "10559871", 0.96),
                      _f("sort_code", "40-22-093", 0.94), _f("statement_period", "2026-03", 0.95)],
 },
 "truth": {"verified": False, "conflicts": 0, "annual_income": 51000.00, "account_number": "10559871",
           "applicant_name": "[PERSON_03]", "date_of_birth": "1979-11-05",
           "employer_name": "Kestrel Engineering", "claim_reference": "CLM-2026-4503",
           "why": "identity expired 2026-01-31, incident 2026-03. No STITCH conflict - "
                  "the documents agree with each other. The problem is the verdict."}},

# 4 — declared income does not match the payslip
{"id": "PKG-004", "note": "declared income does not match the payslip",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_04]", 0.95), _f("date_of_birth", "1984-02-17", 0.94),
                 _f("annual_income", "62000.00", 0.94), _f("employer_name", "Marlow Care Group", 0.93),
                 _f("account_number", "88304127", 0.95), _f("claim_reference", "CLM-2026-4517", 0.96)],
   "identity": [_f("holder_name", "[PERSON_04]", 0.95), _f("date_of_birth", "1984-02-17", 0.94),
                _f("document_number", "AHMED8402174KL3MN", 0.92), _f("expiry_date", "2031-08-14", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_04]", 0.94), _f("employer_name", "Marlow Care Group", 0.94),
               _f("gross_monthly_pay", "3625.00", 0.93), _f("pay_period", "2026-03", 0.94)],
   "bank_statement": [_f("account_holder_name", "[PERSON_04]", 0.95), _f("account_number", "88304127", 0.96),
                      _f("sort_code", "60-18-447", 0.94), _f("statement_period", "2026-03", 0.95)],
 },
 "truth": {"verified": True, "conflicts": 1, "annual_income": 43500.00, "account_number": "88304127",
           "applicant_name": "[PERSON_04]", "date_of_birth": "1984-02-17",
           "employer_name": "Marlow Care Group", "claim_reference": "CLM-2026-4517",
           "why": "form says 62,000; payslip x12 gives 43,500. A 42% difference."}},

# 5 — account number differs by one digit
{"id": "PKG-005", "note": "account number differs by one digit",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_05]", 0.95), _f("date_of_birth", "1996-06-21", 0.94),
                 _f("annual_income", "35000.00", 0.93), _f("employer_name", "Fenwick Foods", 0.94),
                 _f("account_number", "20558193", 0.88), _f("claim_reference", "CLM-2026-4526", 0.96)],
   "identity": [_f("holder_name", "[PERSON_05]", 0.95), _f("date_of_birth", "1996-06-21", 0.93),
                _f("document_number", "OKAFOR9606215OP4QR", 0.91), _f("expiry_date", "2028-11-02", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_05]", 0.93), _f("employer_name", "Fenwick Foods", 0.94),
               _f("gross_monthly_pay", "2916.67", 0.92), _f("pay_period", "2026-03", 0.93)],
   "bank_statement": [_f("account_holder_name", "[PERSON_05]", 0.94), _f("account_number", "20558198", 0.96),
                      _f("sort_code", "05-33-720", 0.93), _f("statement_period", "2026-03", 0.94)],
 },
 "truth": {"verified": True, "conflicts": 1, "annual_income": 35000.04, "account_number": "20558198",
           "applicant_name": "[PERSON_05]", "date_of_birth": "1996-06-21",
           "employer_name": "Fenwick Foods", "claim_reference": "CLM-2026-4526",
           "why": "form 20558193 vs statement 20558198. Payment goes somewhere."}},

# 6 — supporting document missing entirely
{"id": "PKG-006", "note": "payslip missing from the package",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_06]", 0.96), _f("date_of_birth", "1988-12-03", 0.94),
                 _f("annual_income", "47000.00", 0.94), _f("employer_name", "Tarn Valley Motors", 0.93),
                 _f("account_number", "63920174", 0.95), _f("claim_reference", "CLM-2026-4534", 0.96)],
   "identity": [_f("holder_name", "[PERSON_06]", 0.95), _f("date_of_birth", "1988-12-03", 0.94),
                _f("document_number", "REILLY8812035ST5UV", 0.92), _f("expiry_date", "2029-05-19", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "bank_statement": [_f("account_holder_name", "[PERSON_06]", 0.95), _f("account_number", "63920174", 0.96),
                      _f("sort_code", "77-04-215", 0.94), _f("statement_period", "2026-03", 0.95)],
 },
 "truth": {"verified": True, "conflicts": 0, "annual_income": 47000.00, "account_number": "63920174",
           "applicant_name": "[PERSON_06]", "date_of_birth": "1988-12-03",
           "employer_name": "Tarn Valley Motors", "claim_reference": "CLM-2026-4534",
           "requires_evidence": ["annual_income"],
           "why": "no payslip. The value is right, but it is DECLARED not EVIDENCED. "
                  "A record that cannot tell those apart is the actual defect."}},

# 7 — duplicate document, two pay periods
{"id": "PKG-007", "note": "two payslips, different months, different amounts",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_07]", 0.95), _f("date_of_birth", "1972-05-08", 0.94),
                 _f("annual_income", "58000.00", 0.94), _f("employer_name", "Crowther Legal", 0.93),
                 _f("account_number", "91447035", 0.95), _f("claim_reference", "CLM-2026-4548", 0.96)],
   "identity": [_f("holder_name", "[PERSON_07]", 0.95), _f("date_of_birth", "1972-05-08", 0.94),
                _f("document_number", "DUNNE7205084WX6YZ", 0.92), _f("expiry_date", "2027-09-30", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_07]", 0.94), _f("employer_name", "Crowther Legal", 0.94),
               _f("gross_monthly_pay", "4833.33", 0.93), _f("pay_period", "2026-02", 0.94)],
   "payslip_2": [_f("employee_name", "[PERSON_07]", 0.94), _f("employer_name", "Crowther Legal", 0.94),
                 _f("gross_monthly_pay", "6100.00", 0.93), _f("pay_period", "2026-03", 0.94)],
   "bank_statement": [_f("account_holder_name", "[PERSON_07]", 0.95), _f("account_number", "91447035", 0.96),
                      _f("sort_code", "12-88-601", 0.94), _f("statement_period", "2026-03", 0.95)],
 },
 "truth": {"verified": True, "conflicts": 1, "annual_income": "AMBIGUOUS", "account_number": "91447035",
           "applicant_name": "[PERSON_07]", "date_of_birth": "1972-05-08",
           "employer_name": "Crowther Legal", "claim_reference": "CLM-2026-4548",
           "why": "Feb 4,833 vs Mar 6,100. Bonus? Overtime? Which month represents income?"}},

# 8 — THE DANGEROUS ONE. A valid document belonging to somebody else.
{"id": "PKG-008", "note": "bank statement belongs to a different person",
 "docs": {
   "case_form": [_f("applicant_name", "[PERSON_08]", 0.96), _f("date_of_birth", "1990-01-22", 0.95),
                 _f("annual_income", "44000.00", 0.94), _f("employer_name", "Ridgeway Plant Hire", 0.94),
                 _f("account_number", "55710284", 0.95), _f("claim_reference", "CLM-2026-4573", 0.97)],
   "identity": [_f("holder_name", "[PERSON_08]", 0.95), _f("date_of_birth", "1990-01-22", 0.94),
                _f("document_number", "WALSH9001225AB7CD", 0.92), _f("expiry_date", "2030-02-28", 0.94),
                _f("issuing_country", "GB", 0.96)],
   "payslip": [_f("employee_name", "[PERSON_08]", 0.94), _f("employer_name", "Ridgeway Plant Hire", 0.94),
               _f("gross_monthly_pay", "3666.67", 0.93), _f("pay_period", "2026-03", 0.94)],
   # Every field here is high confidence and internally consistent. It is
   # simply the wrong person's statement, attached to this package by mistake.
   "bank_statement": [_f("account_holder_name", "[PERSON_12]", 0.96), _f("account_number", "31860492", 0.97),
                      _f("sort_code", "23-70-114", 0.95), _f("statement_period", "2026-03", 0.96)],
 },
 "truth": {"verified": True, "conflicts": 1, "annual_income": 44000.04, "account_number": "CONFLICT",
           "applicant_name": "CONFLICT", "date_of_birth": "1990-01-22",
           "employer_name": "Ridgeway Plant Hire", "claim_reference": "CLM-2026-4573",
           "why": "bank statement is a different person entirely. Nothing about the document looks wrong."}},
]


def get(pkg_id: str) -> dict:
    for p in PACKAGES:
        if p["id"] == pkg_id:
            return copy.deepcopy(p)
    raise KeyError(pkg_id)


def all_ids() -> list[str]:
    return [p["id"] for p in PACKAGES]


# --------------------------------------------------------------------------
# ONE definition of "what kind of document is this".
#
# `payslip_2` is a payslip. It uses the payslip query fields, the payslip
# layout and the payslip precedence entry, and only its slot in the package is
# different. That rule was written out three times in three files before this
# function existed, and the copy in the renderer disagreed with the other two.
#
# `bank_statement` is why you cannot just split on the underscore.
# --------------------------------------------------------------------------
def base_type(doc_type: str) -> str:
    return "payslip" if doc_type.startswith("payslip") else doc_type


def query_fields_for(doc_type: str) -> list[str]:
    """The fields we ASK the service for, for this document. The bill."""
    return QUERY_FIELDS[base_type(doc_type)]


def fields_for(pkg_id: str, doc_type: str) -> list[dict]:
    """The mock provider's answer: what Query Fields would have returned."""
    return get(pkg_id)["docs"][doc_type]


def all_docs() -> list[tuple[str, str]]:
    """Every (package, document) pair in the corpus — 32 of them."""
    return [(p["id"], dt) for p in PACKAGES for dt in p["docs"]]


# The incident date these packages relate to — used for identity expiry checks.
INCIDENT_DATE = "2026-03-14"
