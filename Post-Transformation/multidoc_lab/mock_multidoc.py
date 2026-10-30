"""
mock_multidoc.py — the offline backend. Free, deterministic, instant.

It answers the same two questions the azure backend answers:

    start(pkg_id, doc_type)   ->  a handle. Does not block.
    poll(handle)              ->  running | succeeded | failed

and nothing else. `pipeline.AsyncAnalyzer` drives both through that pair, which
is why the async lesson is the same lesson on either provider.

WHAT IS SIMULATED, AND WHAT IS NOT
----------------------------------
The FIELDS are not simulated in any interesting sense: they are the eight
packages from `packages.py`, handed back verbatim. The mock is not pretending
to read a document. It is pretending to be a service that already read one.

What IS simulated is the SHAPE of an asynchronous call — that a submission
returns immediately, that the answer is not ready yet, and that a bigger
document takes more polls to resolve. A 12-page bank statement needs more
rounds than a one-page payslip, which is the entire reason the real API is
asynchronous and the entire reason your orchestration has to cope.

Get the async design right here, where a mistake costs nothing, and the azure
backend is a change of transport rather than a change of plan.
"""

from __future__ import annotations

import packages as pk

name = "mock"
poll_gap = 0.0          # nothing to wait for


# How many polls each document takes to resolve. Bigger documents take longer;
# that is the whole reason for async, so the mock has to show it or the lesson
# is invisible. The bank statement is deliberately the slow one — it is also
# the document PKG-008 gets wrong, so the package that needs the most care is
# the one that finishes last.
POLL_COST = {"case_form": 2, "identity": 1, "payslip": 1, "bank_statement": 6}


def start(pkg_id: str, doc_type: str) -> dict:
    """Submit. Returns immediately — there is no result yet, by design."""
    return {
        "pkg_id": pkg_id,
        "doc_type": doc_type,
        "polls": 0,
        "ready_after": POLL_COST.get(pk.base_type(doc_type), 2),
    }


def poll(handle: dict) -> tuple[str, list | None, str | None]:
    handle["polls"] += 1
    if handle["polls"] < handle["ready_after"]:
        return "running", None, None
    return "succeeded", pk.fields_for(handle["pkg_id"], handle["doc_type"]), None


def pages(handle: dict) -> int | None:
    """Pages the service reported reading. The mock reads everything."""
    return pk.DOC_LAYOUT[pk.base_type(handle["doc_type"])]["pages"]


def describe() -> str:
    return "provider: mock  (offline, free, deterministic)"
