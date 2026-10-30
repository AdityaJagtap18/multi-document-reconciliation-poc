"""
corpus.py — the eight lab packages, and what the game needs to score them.

THIS IS THE ONLY FILE THAT KNOWS WHERE THE LAB IS.

The game does not carry its own copy of the documents. It imports the lab's,
so that a change to a package changes the lab and the game together and there
is no second corpus to fall out of date. Day 14's game kept its own DOCUMENTS
list; that was fine because it had no lab to agree with. This one does.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

# Reconciliation_Game/reconciliation_game/corpus.py
#   .parent        -> reconciliation_game/
#   .parent.parent -> Reconciliation_Game/
#   .parent.parent.parent -> the lab root
LAB = Path(__file__).resolve().parent.parent.parent / "multidoc_lab"
if not LAB.is_dir():                       # a clear failure beats an ImportError
    raise RuntimeError(
        f"cannot find the lab at {LAB}. The Reconciliation_Game folder must "
        f"stay inside the Day 15 lab — it imports multidoc_lab/packages.py "
        f"rather than carrying its own copy of the eight packages."
    )
sys.path.insert(0, str(LAB))

import packages as pk                                              # noqa: E402
from packages import (PRECEDENCE, INCIDENT_DATE, QUERY_FIELDS,     # noqa: E402
                      base_type)

# The six fields the pipeline unifies, in the order a reader wants them:
# who, when, how much, from whom, to which account, under which claim.
FIELDS = ["applicant_name", "date_of_birth", "annual_income",
          "employer_name", "account_number", "claim_reference"]


def packages() -> list[dict]:
    """Deep copies. The engine mutates what it is given."""
    return [copy.deepcopy(p) for p in pk.PACKAGES]


def get(pkg_id: str) -> dict:
    return pk.get(pkg_id)


def all_ids() -> list[str]:
    return pk.all_ids()


def truth(pkg_id: str) -> dict:
    return pk.get(pkg_id)["truth"]


# What each package is testing. The lab says this in prose in its README;
# the game needs it as data so `--hint` and the board can print it.
HINTS = {
    "PKG-001": "Clean. Everything agrees. This is what a good package looks "
               "like, and it is the control — no check should ever fire here.",
    "PKG-002": "The name on the licence is not the name on the form. Could be "
               "a married name. Could be the wrong person. You cannot tell "
               "from the documents, which is the point.",
    "PKG-003": "The identity document expired before the incident. The four "
               "documents agree with each other perfectly. The problem is not "
               "a conflict — it is the verdict.",
    "PKG-004": "Declared income is 42% above the payslip. One of these two "
               "numbers is evidence and the other is a claim about income.",
    "PKG-005": "The account number differs by one digit. A 2% numeric "
               "tolerance calls 20558193 and 20558198 equal. They are "
               "different accounts and the payment goes somewhere else.",
    "PKG-006": "No payslip. The income is right and it is unevidenced. A "
               "record that cannot tell those two apart is the actual defect.",
    "PKG-007": "Two payslips, two months, two very different amounts. Bonus? "
               "Overtime? Which month represents this person's income?",
    "PKG-008": "The bank statement belongs to somebody else. Every field on "
               "it is high confidence and internally consistent, the sort "
               "code is valid and the period is right. The identity check "
               "PASSES. Nothing about the document is wrong — what is wrong "
               "is its relationship to the other three.",
}
