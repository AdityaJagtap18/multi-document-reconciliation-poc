"""
azure_multidoc.py — the same 32 documents, through the real service.

This is the ONE module the README promised you would have to change:

    mock_multidoc.start/poll   ->   azure_multidoc.start/poll

Everything downstream is untouched. `pipeline.py` does not import this file,
does not know it exists, and produces the same unified record either way. That
is the test of whether your vendor boundary is in the right place.

WHAT IT ACTUALLY DOES
---------------------
    docs/PKG-005/bank_statement.pdf
      -> POST  {endpoint}/documentintelligence/documentModels/
               prebuilt-layout:analyze?api-version=2024-11-30
               &features=queryFields&queryFields=account_holder_name,...
      -> 202 Accepted, with an Operation-Location header
      -> RETURN. Do not wait.
      -> poll that URL later, alongside the other 31
      -> adapt analyzeResult.documents[0].fields into the lab's shape
      -> cache the raw response so the next run costs nothing

THE ASYNC PART IS NOT A SIMULATION HERE
---------------------------------------
On the mock provider, "submit returns before the answer exists" is something
the mock politely pretends. Here it is simply true: the POST gives you a URL
and no result, and a 12-page statement really is still working when a one-page
payslip has finished. Every orphan, every partial package and every ordering
problem in this lab is a real property of this API, not a teaching device.

That is why the lab is built the way it is. The orchestration in
`pipeline.AsyncAnalyzer` is the deliverable — the extraction is a purchased
service, and the part you own is what happens between submitting 32 jobs and
having one record.

WHY REST AND NOT THE SDK
------------------------
So you can read the request. Everything here is standard library — no
`pip install azure-ai-documentintelligence`, no client class hiding the wire
format. When this 404s in front of a client you will want to know exactly what
was sent, and you will not get that from a stack trace inside an SDK.

Use the SDK in production. Read this once first.

THE THREE THINGS THAT WILL BITE YOU
-----------------------------------
1. THE ROUTE MOVED.  api-version 2024-11-30 and later live under
   `/documentintelligence/`. Earlier versions live under `/formrecognizer/`.
   Mismatch the two and you get a 404 whose message talks about the model,
   which sends people hunting for a deployment problem that does not exist.

2. QUERY FIELDS NEEDS BOTH HALVES.  `features=queryFields` turns the add-on on;
   `queryFields=a,b,c` says which fields. Send the names without the feature
   flag and you get HTTP 200 with no `documents` member at all — successful,
   empty, and entirely misleading. Nothing errors. You just get zero fields.

3. ASKING FOR A FIELD DOES NOT MAKE IT EXIST — AND THE SERVICE WILL STILL
   ANSWER.  Ask a motor claim form for `gross_monthly_pay` and you do not get
   an error and you do not reliably get nothing. You may get a number that is
   on the page for some other reason, at a confidence high enough to look
   fine. Run `--overask` and watch it happen. This is the single most
   important measured fact in the lab, and the mock cannot show it to you.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import make_pdfs
import packages as pk
from config import ConfigError, Settings

name = "azure"


class AzureDocIntError(RuntimeError):
    """Anything that should stop the run: bad config, HTTP error, failed
    analysis. We do not paper over these — a half-processed batch that looks
    complete is worse than a batch that stopped."""


# ==========================================================================
# 1. OVER-ASKING — the demonstration that costs money to learn any other way
#
# Every field name below is one the document genuinely does not contain. A
# payslip has no sort code. A driving licence has no employer. Asking anyway is
# what a team does when it writes one query list and reuses it across document
# types "to keep things simple", and the point of the exercise is that the
# service does not push back. It answers.
# ==========================================================================
OVERASK = {
    "case_form":      ["vehicle_registration", "policy_number", "sort_code"],
    "identity":       ["annual_income", "employer_name"],
    "payslip":        ["account_number", "sort_code"],
    "bank_statement": ["annual_income", "employer_name"],
}


# ==========================================================================
# 2. HTTP
# ==========================================================================
def _raw_request(url: str, settings: Settings, method: str = "GET",
                 body: bytes | None = None, content_type: str | None = None):
    headers = {"Ocp-Apim-Subscription-Key": settings.key}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=settings.timeout) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        return e.code, dict(e.headers or {}), {"_error_body": detail}
    except urllib.error.URLError as e:
        raise AzureDocIntError(
            f"Could not reach {url}\n  {e.reason}\n"
            f"  Check AZURE_DOCINT_ENDPOINT, and check the resource is not "
            f"firewalled to a VNet you are not on."
        ) from e


def _request(url: str, settings: Settings, method: str = "GET",
             body: bytes | None = None, content_type: str | None = None,
             attempts: int = 6):
    """
    As above, but a 429 is retried rather than raised.

    A free-tier resource rate-limits aggressively, and 32 documents is enough
    to hit it. The service tells you how long to wait in `Retry-After`; honour
    it. Backing off on the server's terms is the difference between a run that
    takes a few minutes and a run that fails halfway with a bill attached.
    """
    delay = 2.0
    for attempt in range(attempts):
        status, headers, payload = _raw_request(url, settings, method, body, content_type)
        if status != 429:
            return status, headers, payload
        wait = delay
        try:
            wait = max(wait, float(headers.get("Retry-After", 0)))
        except (TypeError, ValueError):
            pass
        if attempt == attempts - 1:
            break
        RATE_LIMIT_WAITS.append(wait)
        time.sleep(wait)
        delay = min(delay * 2, 60)
    return status, headers, payload


# How long we spent waiting on the service's own rate limit. Reported at the
# end of a run, because "it took eleven minutes" is a fact somebody will need
# when they size this for 4,000 documents a month.
RATE_LIMIT_WAITS: list[float] = []


def _explain(status: int, payload: dict, settings: Settings) -> str:
    body = payload.get("_error_body", json.dumps(payload)[:800])
    hint = ""
    if status == 404:
        hint = (f"\n  404 is almost always the ROUTE, not the model.\n"
                f"  api-version {settings.api_version} resolved to "
                f"/{settings.resolved_route()}/.\n"
                f"  Set AZURE_DOCINT_ROUTE=formrecognizer (older) or "
                f"=documentintelligence (2024-11-30+) to force it.")
    elif status in (401, 403):
        hint = ("\n  401/403 is the key or the region. Confirm AZURE_DOCINT_KEY "
                "belongs to the resource\n  at AZURE_DOCINT_ENDPOINT — a key from "
                "a different Azure AI resource returns exactly this.")
    elif status == 429:
        hint = ("\n  429 after every retry. The resource is rate-limited harder "
                "than the backoff expects.\n  Raise AZURE_DOCINT_SUBMIT_GAP (seconds "
                "between submissions), or move off F0.")
    elif status == 400 and "queryFields" in body:
        hint = ("\n  400 mentioning queryFields is usually the add-on not being "
                "available on this\n  resource's tier or region, or more than 20 "
                "field names in one request.")
    return f"HTTP {status} from Document Intelligence.{hint}\n  body: {body}"


# ==========================================================================
# 3. THE ADAPTER
#
# Where the vendor's response shape becomes the lab's response shape, and the
# only place in the codebase allowed to know about either.
# ==========================================================================
def _page_of(field: dict) -> int:
    regions = field.get("boundingRegions") or []
    if regions and isinstance(regions[0], dict):
        return int(regions[0].get("pageNumber", 1))
    return 1


def adapt(payload: dict, asked: list[str]) -> tuple[list[dict], dict]:
    """
    analyzeResult.documents[0].fields  ->  the lab's [{field, value,
    confidence, page}], plus a note of what asking cost us.

    THREE OUTCOMES PER FIELD, NOT TWO
    ---------------------------------
    A query field you asked for comes back in one of three states, and the
    difference between the last two is the lesson:

      absent    the key is not in the response at all
      empty     the key is there, confidence 0, no value — "I looked, no"
      answered  a value, with a confidence

    Only `answered` becomes a field. The other two are counted, not invented:
    a field the service could not find must not enter the record as an empty
    string, because an empty string is a value and `None` is not.
    """
    result = payload.get("analyzeResult", payload)
    docs = result.get("documents") or []
    raw_fields = (docs[0].get("fields") or {}) if docs else {}

    fields, empty = [], []
    for fname in asked:
        f = raw_fields.get(fname)
        if f is None:
            empty.append(fname)
            continue
        value = f.get("content")
        if value is None:
            value = f.get("valueString")
        if value is None or str(value).strip() == "":
            empty.append(fname)
            continue
        fields.append({
            "field": fname,
            "value": str(value).strip(),
            "confidence": float(f.get("confidence", 0.0)),
            "page": _page_of(f),
        })

    meta = {
        "asked": list(asked),
        "answered": [f["field"] for f in fields],
        "empty": empty,
        "values": {f["field"]: f["value"] for f in fields},
        "confidences": {f["field"]: f["confidence"] for f in fields},
        "pages": len(result.get("pages") or []) or 1,
        "no_documents_member": not docs,
    }
    return fields, meta


# ==========================================================================
# 4. THE BACKEND — same two functions as mock_multidoc
# ==========================================================================
def _cache_path(settings: Settings, pkg_id: str, doc_type: str, overask: bool) -> Path:
    sub = "di_raw_overask" if overask else "di_raw"
    return settings.out_dir / "azure" / sub / pkg_id / f"{doc_type}.json"


def _query_fields(doc_type: str, overask: bool) -> list[str]:
    asked = list(pk.query_fields_for(doc_type))
    if overask:
        asked += OVERASK.get(pk.base_type(doc_type), [])
    return asked


class Backend:
    """
    Bound to one Settings object so `pipeline.AsyncAnalyzer` can drive it with
    the same two calls it uses on the mock.

    Instances are stateful only in the sense that they hold configuration and
    a cache directory. Nothing about a job lives here — the handle carries it,
    which is what lets a job outlive the process that submitted it. In Azure
    that handle is an Operation-Location URL, and putting it somewhere durable
    is the difference between a pipeline that survives a restart and one that
    loses 32 paid analyses.
    """

    poll_gap = 1.5

    def __init__(self, settings: Settings, overask: bool = False):
        self.settings = settings
        self.overask = overask
        self.poll_gap = settings.poll_gap
        self.name = "azure"
        self.metas: dict[tuple[str, str], dict] = {}
        self.submitted = 0

    # -- submit -----------------------------------------------------------
    def start(self, pkg_id: str, doc_type: str) -> dict:
        s = self.settings
        asked = _query_fields(doc_type, self.overask)
        cache = _cache_path(s, pkg_id, doc_type, self.overask)

        if s.use_cache and cache.exists():
            return {"pkg_id": pkg_id, "doc_type": doc_type, "asked": asked,
                    "cached": str(cache)}

        pdf = make_pdfs.pdf_path(s.doc_dir, pkg_id, doc_type)
        if not pdf.exists():
            raise AzureDocIntError(
                f"{pdf} does not exist.\n"
                f"  Render the documents first:  python3 run_lab.py --make-pdfs"
            )

        if self.submitted and s.submit_gap:
            time.sleep(s.submit_gap)

        url = s.analyze_url(asked)
        data = pdf.read_bytes()
        status, headers, payload = _request(url, s, "POST", data, "application/pdf")

        # Some api-versions reject raw binary and want the bytes in a JSON
        # body. Both are documented; which one your version accepts is not
        # obvious, so try the other rather than making the learner debug a 415.
        if status == 415:
            body = json.dumps({"base64Source": base64.b64encode(data).decode()}).encode()
            status, headers, payload = _request(url, s, "POST", body, "application/json")

        if status != 202:
            raise AzureDocIntError(f"{pkg_id}/{doc_type}: {_explain(status, payload, s)}")

        op = headers.get("Operation-Location") or headers.get("operation-location")
        if not op:
            raise AzureDocIntError(
                f"{pkg_id}/{doc_type}: 202 Accepted with no Operation-Location "
                f"header. Nothing to poll."
            )

        self.submitted += 1
        # This URL is the whole job. Everything needed to collect the result
        # later is in the handle — nothing is held in this process.
        return {"pkg_id": pkg_id, "doc_type": doc_type, "asked": asked,
                "op": op, "deadline": time.time() + s.timeout}

    # -- collect ----------------------------------------------------------
    def poll(self, handle: dict) -> tuple[str, list | None, str | None]:
        s = self.settings
        key = (handle["pkg_id"], handle["doc_type"])

        if "cached" in handle:
            payload = json.loads(Path(handle["cached"]).read_text())
            fields, meta = adapt(payload, handle["asked"])
            meta["cached"] = True
            self.metas[key] = meta
            _check_pages(handle, meta["pages"], s)
            return "succeeded", fields, None

        status, _, payload = _request(handle["op"], s)
        if status != 200:
            return "failed", None, _explain(status, payload, s)

        state = str(payload.get("status", "")).lower()
        if state in ("running", "notstarted"):
            if time.time() > handle["deadline"]:
                return "failed", None, (
                    f"still '{state}' after {s.timeout}s — raise AZURE_DOCINT_TIMEOUT")
            return "running", None, None
        if state == "failed":
            return "failed", None, json.dumps(payload.get("error", payload))[:400]

        cache = _cache_path(s, handle["pkg_id"], handle["doc_type"], self.overask)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, indent=2))

        fields, meta = adapt(payload, handle["asked"])
        meta["cached"] = False
        self.metas[key] = meta
        _check_pages(handle, meta["pages"], s)
        return "succeeded", fields, None

    def describe(self) -> str:
        s = self.settings
        return (f"provider: azure  ({s.model} @ api-version {s.api_version}, "
                f"/{s.resolved_route()}/, features=queryFields)\n"
                f"          endpoint: {s.endpoint}\n"
                f"          cache:    "
                + ("on — delete out/azure/di_raw/ to force a fresh read"
                   if s.use_cache else "OFF — every document is billed")
                + ("\n          OVER-ASKING: extra field names added per document"
                   if self.overask else ""))


# ==========================================================================
# 5. PAGES THE SERVICE DECLINED TO READ
#
# A free-tier (F0) resource analyses the FIRST TWO PAGES of a document and
# stops. It does not tell you: HTTP 200, no error, no `warnings` member, and a
# `pages` array that simply ends early.
#
# Every query field in this lab is rendered on page 1 precisely so that limit
# cannot be mistaken for an extraction failure — Day 14 already taught that
# lesson and it does not need teaching twice. The check stays because it costs
# nothing and because the day somebody adds a third page to a document, this is
# the line that tells them why their field went missing.
# ==========================================================================
PAGE_TRUNCATIONS: list[str] = []


def _pdf_page_count(data: bytes) -> int | None:
    import re
    m = re.search(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, re.S)
    if not m:
        return None
    try:
        return int(m.group(1)) or None
    except ValueError:
        return None


def _check_pages(handle: dict, returned: int, settings: Settings) -> None:
    pdf = make_pdfs.pdf_path(settings.doc_dir, handle["pkg_id"], handle["doc_type"])
    if not pdf.exists():
        return
    declared = _pdf_page_count(pdf.read_bytes())
    if not declared or returned >= declared:
        return
    note = (f"{handle['pkg_id']}/{handle['doc_type']}: sent {declared} pages, "
            f"the service analysed {returned}. Fields after page {returned} "
            f"were never read — they are NOT extraction failures.")
    if note not in PAGE_TRUNCATIONS:
        PAGE_TRUNCATIONS.append(note)


# ==========================================================================
# 6. WHAT ASKING COST — the artefact worth the run
#
# The mock's confidences are numbers somebody chose to make a teaching point.
# These are numbers the service produced. Quote these.
# ==========================================================================
def query_field_report(backend: "Backend") -> str:
    metas = backend.metas
    asked = sum(len(m["asked"]) for m in metas.values())
    answered = sum(len(m["answered"]) for m in metas.values())
    empty = sum(len(m["empty"]) for m in metas.values())

    md = [
        "# Query Fields — what you asked for, and what it cost",
        "",
        f"Documents analysed: **{len(metas)}**  ·  "
        f"field requests sent: **{asked}**  ·  "
        f"answered: **{answered}**  ·  "
        f"returned empty: **{empty}**",
        "",
        "Query fields are a **paid add-on, billed per document**. The number "
        "above is not a statistic, it is a line on an invoice — every request "
        "in it recurs on every document, forever. `QUERY_FIELDS` in "
        "`packages.py` is that bill. Justify each entry.",
        "",
        "## Per document",
        "",
        "| Package | Document | Asked | Answered | Empty | Mean confidence |",
        "|---|---|---|---|---|---|",
    ]
    for (pkg_id, doc_type) in sorted(metas):
        m = metas[(pkg_id, doc_type)]
        cs = list(m.get("confidences", {}).values())
        mean = f"{sum(cs)/len(cs):.3f}" if cs else "—"
        md.append(f"| {pkg_id} | {doc_type} | {len(m['asked'])} | "
                  f"{len(m['answered'])} | "
                  f"{', '.join(m['empty']) if m['empty'] else '—'} | {mean} |")

    if backend.overask:
        md += ["", "## Fields the document does not contain", "",
               "These names were added by `--overask`. **Not one of them appears "
               "on the document that was asked for it.** A payslip has no sort "
               "code; a driving licence has no employer. This is what a single "
               "reused query list across document types looks like from the "
               "service's side.", "",
               "| Package | Document | Field asked for | What came back | Confidence |",
               "|---|---|---|---|---|"]
        invented = 0
        for (pkg_id, doc_type) in sorted(metas):
            m = metas[(pkg_id, doc_type)]
            extra = OVERASK.get(pk.base_type(doc_type), [])
            for fname in extra:
                if fname in m["answered"]:
                    val = m.get("values", {}).get(fname, "")
                    conf = m.get("confidences", {}).get(fname, 0.0)
                    invented += 1
                    md.append(f"| {pkg_id} | {doc_type} | `{fname}` | "
                              f"**`{val}`** | {conf:.3f} |")
                else:
                    md.append(f"| {pkg_id} | {doc_type} | `{fname}` | "
                              f"*empty — the honest answer* | — |")
        md += ["", f"**{invented} of the over-asked requests came back with a "
               f"value in them.** Every one of those values is real text that is "
               f"genuinely on the page — it is simply not the thing that was "
               f"asked for. The service was asked a question the document cannot "
               f"answer and it found the closest thing rather than declining.", "",
               "Read the confidence column before you decide how you feel about "
               "that. A field that comes back empty is safe: it lands in "
               "`missing` and somebody sees a gap. A field that comes back "
               "*populated and wrong* is the failure mode this entire lab is "
               "about, and here it is arriving from the vendor rather than from "
               "your stitching.", ""]

    md += ["", "## Read this before you draw a conclusion", "",
           "**An empty query field is not a service failure.** It is the "
           "service declining to invent, which is the behaviour you want. It "
           "lands in `documents_missing` or leaves the field absent, and both "
           "are visible.", "",
           "**These PDFs are digitally generated.** The text is embedded, not "
           "scanned, so the service reads it far more confidently than it would "
           "read the forms this lab is modelling. Confidence measured here is a "
           "**ceiling, not an estimate**. To get a real number, run the client's "
           "own scans through the same pipeline — that is the first thing to "
           "ask for.", "",
           "**The conflicts survive the round trip, and that is the point.** "
           "PKG-005's account number really does differ by one digit on the "
           "rendered documents. PKG-008's bank statement really does carry a "
           "different person's name. The service reads all of it correctly, at "
           "high confidence, and hands you documents that disagree. Nothing "
           "about the extraction is wrong. Everything about the record you "
           "build from it can be.", ""]
    return "\n".join(md)


def preflight(settings: Settings, doc_dir: Path) -> None:
    """Fail before the first billed call, not halfway through the batch."""
    settings.require_azure()
    absent = make_pdfs.missing(doc_dir)
    if absent:
        raise AzureDocIntError(
            f"{len(absent)} of {len(pk.all_docs())} PDFs are missing from "
            f"{doc_dir}.\n"
            f"  Render them:  python3 run_lab.py --make-pdfs"
        )
    if len(pk.all_docs()) > settings.max_documents:
        raise ConfigError(
            f"{len(pk.all_docs())} documents exceeds DOCINT_MAX_DOCUMENTS="
            f"{settings.max_documents}. Raise it deliberately."
        )
