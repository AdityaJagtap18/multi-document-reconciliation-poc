#!/usr/bin/env /usr/bin/python3
"""
Builds "Interpreting Your Results" — the learner-facing companion to the Day 15
multi-document processing lab.

    /usr/bin/python3 build/build_interpretation_guide.py

python-docx lives on /usr/bin/python3 (3.9.6) on this machine, NOT on 3.12.
House style: navy #1D3557 header rows with white text, #EDF1F7 zebra banding,
Consolas for code, red #C8102E for the things that cost money.

Every number in the generated document is a measured figure from a real run:
the mock totals are deterministic, and the azure totals are from the live run
against doc-int-forge0fde-1 on 2026-08-17 (prebuilt-layout + queryFields,
api-version 2024-11-30, F0 tier).
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

NAVY = RGBColor(0x1D, 0x35, 0x57)
RED = RGBColor(0xC8, 0x10, 0x2E)
TEAL = RGBColor(0x1B, 0x6C, 0x6F)
GREY = RGBColor(0x55, 0x5F, 0x6B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

NAVY_HEX = "1D3557"
ZEBRA_HEX = "EDF1F7"
CODE_HEX = "F4F6F8"
AMBER_HEX = "FDF3E3"
TEAL_HEX = "EAF2F5"

OUT = (Path(__file__).resolve().parent.parent
       / "Day15_MultiDoc_Interpreting_Your_Results.docx")


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------
def shade(el, hex_fill):
    """Paint a cell or paragraph background."""
    pr = el.get_or_add_tcPr() if el.tag.endswith("tc") else el.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    pr.append(shd)


def cell_text(cell, text, bold=False, color=None, size=9.5):
    """Write into a cell WITHOUT going through cell.text.

    Setting `cell.text` leaves an empty run at index 0, so anything that later
    styles or asserts on runs[0] silently misses the real text. Write the run
    ourselves and there is exactly one run holding exactly the text.
    """
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    if color is not None:
        run.font.color.rgb = color
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    return run


def h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(22)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(17)
    r.font.color.rgb = NAVY
    r.font.name = "Calibri"
    pPr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:color"), NAVY_HEX)
    borders.append(bottom)
    pPr.append(borders)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(12.5)
    r.font.color.rgb = NAVY
    r.font.name = "Calibri"
    return p


def h3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = TEAL
    r.font.name = "Calibri"
    return p


def para(doc, text, italic=False, color=None, size=10.5, space_after=7):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    r = p.add_run(text)
    r.italic = italic
    r.font.size = Pt(size)
    r.font.name = "Calibri"
    if color is not None:
        r.font.color.rgb = color
    return p


def rich(doc, chunks, size=10.5, space_after=7):
    """chunks = [(text, {bold/italic/color/font}), ...] in one paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    for text, opts in chunks:
        r = p.add_run(text)
        r.bold = opts.get("bold", False)
        r.italic = opts.get("italic", False)
        r.font.size = Pt(opts.get("size", size))
        r.font.name = opts.get("font", "Calibri")
        if opts.get("color") is not None:
            r.font.color.rgb = opts["color"]
    return p


def bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    if bold_prefix:
        r = p.add_run(bold_prefix)
        r.bold = True
        r.font.size = Pt(10.5)
        r.font.name = "Calibri"
    r = p.add_run(text)
    r.font.size = Pt(10.5)
    r.font.name = "Calibri"
    return p


def code(doc, text, fill=CODE_HEX, size=9):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(9)
    p.paragraph_format.left_indent = Inches(0.18)
    r = p.add_run(text)
    r.font.name = "Consolas"
    r.font.size = Pt(size)
    shade(p._p, fill)
    return p


def callout(doc, title, text, fill=AMBER_HEX, accent=RED):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    shade(c._tc, fill)
    p = c.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    r = p.add_run(title + "  ")
    r.bold = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = accent
    r.font.name = "Calibri"
    r = p.add_run(text)
    r.font.size = Pt(10.5)
    r.font.name = "Calibri"
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def table(doc, headers, rows, widths=None, mono_cols=(), size=9.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, htext in enumerate(headers):
        c = t.rows[0].cells[i]
        shade(c._tc, NAVY_HEX)
        cell_text(c, htext, bold=True, color=WHITE, size=size)
    for n, row in enumerate(rows):
        cells = t.add_row().cells
        for i, val in enumerate(row):
            if n % 2 == 1:
                shade(cells[i]._tc, ZEBRA_HEX)
            run = cell_text(cells[i], str(val), size=size)
            if i in mono_cols:
                run.font.name = "Consolas"
                run.font.size = Pt(size - 0.5)
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------
def build():
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(0.85)
        s.top_margin = s.bottom_margin = Inches(0.8)

    # ---- title ----------------------------------------------------------
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("Interpreting Your Results")
    r.bold = True
    r.font.size = Pt(26)
    r.font.color.rgb = NAVY
    r.font.name = "Calibri"

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("Sprint 1 · Day 15 — Multi-Document Processing & Query Fields")
    r.font.size = Pt(13)
    r.font.color.rgb = RED
    r.font.name = "Calibri"

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(16)
    r = p.add_run("Birlasoft FORGE FDE Academy  ·  DecisionStream AI  ·  "
                  "Confidential — for learner use only")
    r.font.size = Pt(9)
    r.font.color.rgb = GREY
    r.italic = True
    r.font.name = "Calibri"

    # =====================================================================
    h1(doc, "0 · What this lab is, and what it is for")
    # =====================================================================
    h2(doc, "The situation")
    para(doc,
         "DecisionStream AI processes motor insurance claims. A claim does not "
         "arrive as one document. It arrives as a CASE PACKAGE: an application "
         "form, a photograph of a driving licence, a payslip proving income, "
         "and a bank statement showing the account the settlement will be paid "
         "into. Four documents, sometimes five, sometimes three.",
         size=11)
    para(doc,
         "Your job is to turn each package into ONE unified record that a "
         "claims handler or a downstream system can act on.")

    h2(doc, "Why that is harder than it sounds")
    para(doc, "Yesterday, on Day 14, you extracted fields from a single "
              "document, and the hard part was whether the model read the "
              "characters correctly. Today every individual document is read "
              "perfectly and the pipeline still produces wrong records.")
    para(doc, "That is because the failures in a multi-document workflow do not "
              "live inside any document. They live BETWEEN them:")
    for t in [
        "the name on the licence is not the name on the form",
        "the income declared is not the income on the payslip",
        "the account number differs by one digit",
        "the licence expired before the incident",
        "a payslip was submitted twice, for two different months",
        "a document is missing entirely",
        "a document is perfectly valid and belongs to somebody else",
    ]:
        bullet(doc, t)
    para(doc, "Each document is individually fine. Each extraction is "
              "individually confident. Nothing errors. And the record you build "
              "out of them can still be wrong in a way that reaches a customer.",
         italic=True)

    h2(doc, "The four things this lab makes you build")
    table(doc,
          ["#", "Capability", "What it decides", "Who owns it"],
          [
              ["1", "Asynchronous orchestration",
               "How 32 documents get submitted, polled and assembled without "
               "blocking — and what happens when one never comes back",
               "You"],
              ["2", "Identity verification",
               "Whether the licence matches the applicant and was valid — while "
               "storing none of it",
               "You"],
              ["3", "Stitching / reconciliation",
               "Which document wins when two documents disagree",
               "You"],
              ["4", "Storage path design",
               "What retention, residency and legal hold will be possible later",
               "You"],
          ],
          widths=[0.35, 1.7, 3.2, 0.85], size=9.5)
    callout(doc, "The sentence the whole lab exists to earn.",
            "Extraction is a purchased service. Verification and stitching are "
            "YOUR code — and they are where a wrong record gets built out of "
            "individually correct documents. Section 8 is the measurement that "
            "proves it.")

    h2(doc, "The two ways it runs")
    table(doc,
          ["Provider", "What it is", "Cost", "When to use it"],
          [
              ["mock", "Synthetic Query Fields responses, served straight from "
               "packages.py", "Free, instant, deterministic",
               "Always first. This is the lab."],
              ["azure", "The same 32 documents, rendered as PDFs and sent to a "
               "real Azure AI Document Intelligence resource",
               "Billed, ~3 min first run",
               "Afterwards — to find out how much of what you concluded "
               "survives contact with the service."],
          ],
          widths=[0.85, 2.6, 1.5, 1.9], mono_cols=(0,))
    rich(doc, [
        ("Both go through the same pipeline. ", {}),
        ("pipeline.py", {"font": "Consolas", "size": 10}),
        (" never learns which one ran — it receives the same list of field "
         "dictionaries either way. That is the adapter pattern from Day 11, and "
         "if pointing your pipeline at a real service means editing your "
         "business logic, your vendor boundary is in the wrong place.", {}),
    ])

    # =====================================================================
    h1(doc, "1 · Before you run anything")
    # =====================================================================
    h2(doc, "What you need")
    para(doc, "For the mock provider: Python. That is the entire list — standard "
              "library only, no pip install, no network, no key.")
    rich(doc, [
        ("Python 3.9 or newer is recommended. The lab is written to run on 3.7+ "
         "and is tested on both 3.7.2 and 3.12. On the Techademy Azure VM, ", {}),
        ("python3", {"font": "Consolas", "size": 10}),
        (" is 3.12 and you need nothing else.", {}),
    ])
    para(doc, "For the azure provider you also need an Azure AI Document "
              "Intelligence resource, its endpoint and one of its keys. Section "
              "7 covers that.")

    h2(doc, "The first thing to run")
    code(doc, "python3 run_lab.py --selftest")
    para(doc, "108 checks, no network, no cost, about a second. It builds a "
              "synthetic service response for each of the 32 documents, pushes "
              "it through the REAL Azure adapter, and asserts the result matches "
              "what the mock produces.")
    para(doc, "Run it before you spend anything, and again after you change "
              "anything at the vendor boundary. If the mock and the service "
              "later disagree, this is what tells you the disagreement is real "
              "rather than a bug in your adapter.")
    code(doc, "  108/108 checks passed.\n"
              "  The azure adapter reproduces the mock pipeline exactly. "
              "Safe to spend.")

    # =====================================================================
    h1(doc, "2 · Every command, every parameter")
    # =====================================================================
    para(doc, "There is one script. Everything is a flag on it.")

    h2(doc, "The commands")
    table(doc,
          ["Command", "What it does", "Cost"],
          [
              ["python3 run_lab.py", "All three stitching strategies over all "
               "eight packages. START HERE.", "Free"],
              ["python3 run_lab.py --selftest", "108 offline checks on the "
               "adapter, the identity boundary and the pinned totals.", "Free"],
              ["python3 run_lab.py --paths", "The Blob path design "
               "demonstration.", "Free"],
              ["python3 run_lab.py --make-pdfs", "Renders the 32 documents to "
               "docs/. Required once before any azure run.", "Free"],
          ],
          widths=[2.3, 3.6, 0.75], mono_cols=(0,))

    h2(doc, "The parameters")
    table(doc,
          ["Flag", "Accepts", "Default", "What it does"],
          [
              ["--strategy", "trust_form | trust_evidence | reconcile",
               "all three", "Run one stitching strategy instead of all three."],
              ["--show", "a package id, e.g. PKG-008", "—",
               "One package under all three strategies, in full detail — every "
               "conflict, the identity verdict, the checks that ran."],
              ["--failures", "a rate, 0.0 to 1.0", "0.0",
               "Fail that proportion of documents during processing. Seeded, so "
               "it is reproducible."],
              ["--provider", "mock | azure", "from .env",
               "Override the provider for this run only. The safest way to work "
               "— leave .env on mock so offline is what happens by accident."],
              ["--overask", "—", "off",
               "AZURE ONLY. Also ask each document for fields it does not "
               "contain, and record what comes back. See section 8.3."],
              ["-v, --verbose", "—", "off",
               "With --selftest, print every passing check as well as the "
               "failures."],
          ],
          widths=[1.15, 1.9, 0.85, 2.7], mono_cols=(0, 1), size=9)
    para(doc, "Flags combine. --provider azure --strategy reconcile --failures "
              "0.2 is a valid and interesting run.", italic=True)

    h2(doc, "The environment variables")
    rich(doc, [
        ("Set these in ", {}),
        (".env", {"font": "Consolas", "size": 10}),
        (", or as real environment variables — ", {}),
        ("a real environment variable always wins", {"bold": True}),
        (", so CI and the Azure VM can override without editing a file.", {}),
    ])
    table(doc,
          ["Variable", "Default", "What it does"],
          [
              ["DOCINT_PROVIDER", "mock", "mock or azure. Same variable name as "
               "Day 14 — one .env works for both days."],
              ["AZURE_DOCINT_ENDPOINT", "—", "Resource endpoint. REQUIRED for "
               "azure."],
              ["AZURE_DOCINT_KEY", "—", "Resource key. REQUIRED for azure. Never "
               "commit it."],
              ["AZURE_DOCINT_MODEL", "prebuilt-layout", "The model the Query "
               "Fields add-on attaches to."],
              ["AZURE_DOCINT_API_VERSION", "2024-11-30", "API version. This also "
               "determines the URL route."],
              ["AZURE_DOCINT_ROUTE", "auto", "auto, documentintelligence, or "
               "formrecognizer. Force it only when debugging a 404."],
              ["AZURE_DOCINT_TIMEOUT", "180", "Seconds to wait for ONE document "
               "to finish."],
              ["AZURE_DOCINT_POLL_GAP", "1.5", "Seconds between polls of the "
               "whole batch."],
              ["AZURE_DOCINT_SUBMIT_GAP", "0", "Seconds between submissions. "
               "Raise if a free-tier resource 429s faster than the backoff "
               "recovers."],
              ["DOCINT_USE_CACHE", "true", "Reuse out/azure/di_raw/. Set false "
               "to re-bill every document on every run."],
              ["DOCINT_MAX_DOCUMENTS", "60", "A guard against pointing this at "
               "4,000 documents by accident. This lab needs 32."],
          ],
          widths=[1.9, 1.1, 3.6], mono_cols=(0, 1), size=9)

    # =====================================================================
    h1(doc, "3 · python3 run_lab.py — the main run")
    # =====================================================================
    h2(doc, "What it does")
    para(doc, "For each of the eight packages, under each of the three "
              "strategies: submits every document asynchronously, waits for them "
              "all, verifies identity, stitches the survivors into one record, "
              "and scores it against ground truth.")

    h2(doc, "What it prints")
    code(doc,
         "Strategy: trust_form\n"
         "package     WRONG  refused  conflicts  verdict  note\n"
         "-------------------------------------------------------------------\n"
         "PKG-001         0        0    0/0           ok  clean package, ever\n"
         "PKG-004         1        0    1/1           ok  declared income doe"
         "  <-- annual_income=62000.00\n"
         "PKG-006         0        0    0/0           ok  payslip missing fro"
         "  <-- declared, not evidenced: annual_income\n"
         "-------------------------------------------------------------------\n"
         "TOTAL           4        0          6      8/8",
         size=8)

    h2(doc, "The five columns")
    table(doc,
          ["Column", "What it counts", "How to treat it"],
          [
              ["WRONG", "Values stitched into the unified record that are not "
               "correct, with no flag attached",
               "THE ONLY COLUMN THAT CAN HURT A CUSTOMER. Judge every strategy "
               "on this first and everything else second."],
              ["refused", "Values the strategy declined to pick, because the "
               "sources disagreed",
               "A cost, not a failure. It buys a handler decision. Roughly "
               "thirty seconds each."],
              ["conflicts", "Disagreements found / disagreements expected",
               "All three strategies find the SAME conflicts. Finding them is "
               "not the differentiator — what you do about them is."],
              ["verdict", "ok / WRONG / n/a for the identity check",
               "Three states, not two. n/a means the check could not run at "
               "all, which is different from running and being wrong."],
              ["note", "What makes this package hard, plus an arrow naming the "
               "first wrong value",
               "The arrow means you never have to hunt for which field broke."],
          ],
          widths=[0.85, 2.6, 3.1], mono_cols=(0,), size=9)

    h3(doc, "A worked line")
    code(doc, "PKG-004         1        0    1/1           ok  declared income "
              "doe  <-- annual_income=62000.00")
    para(doc, "One wrong value was accepted. Nothing was refused. One conflict "
              "was expected and one was found. The identity verdict was correct. "
              "And the arrow tells you exactly which field went wrong and what "
              "was written: annual_income, stitched as 62,000.")
    para(doc, "The form declared £62,000. The payslip says £3,625 a month, which "
              "is £43,500 a year — a 42% difference. trust_form believed the "
              "applicant, wrote 62,000 into the record, attached no flag, and "
              "produced a complete-looking record that is wrong by eighteen and "
              "a half thousand pounds.")

    h3(doc, "The second kind of arrow")
    code(doc, "PKG-006         0        0    0/0           ok  payslip missing "
              "fro  <-- declared, not evidenced: annual_income")
    para(doc, "Zero wrong. Zero conflicts. And still flagged — because PKG-006's "
              "payslip never arrived, so the £47,000 income figure came only "
              "from the form. The value is CORRECT. It is just not EVIDENCED.")
    callout(doc, "PKG-006 is the subtle one.",
            "A record that cannot tell 'the applicant told us' apart from 'a "
            "document proved it' is defective even when every value in it is "
            "right. That distinction is what the provenance block exists for, "
            "and it is the one most pipelines never build.",
            fill=TEAL_HEX, accent=TEAL)

    h2(doc, "The summary you should see")
    code(doc,
         "  trust_form        4 wrong accepted,  0 refused,  6 conflicts "
         "surfaced, 8/8 verdicts correct\n"
         "  trust_evidence    2 wrong accepted,  0 refused,  6 conflicts "
         "surfaced, 8/8 verdicts correct\n"
         "  reconcile         0 wrong accepted,  4 refused,  6 conflicts "
         "surfaced, 8/8 verdicts correct", size=8)
    para(doc, "The mock provider is deterministic. If your numbers are not "
              "exactly 4 / 2 / 0, something is wrong with your setup rather than "
              "your reasoning — run --selftest and it will name the check that "
              "broke.")

    h2(doc, "How to read the three strategies")
    table(doc,
          ["Strategy", "What it believes", "What it produces", "The problem with it"],
          [
              ["trust_form", "The applicant. The application form wins every "
               "disagreement.", "A complete record, every time. 4 wrong values.",
               "It treats a claimant's own declaration as authoritative over the "
               "evidence submitted to support it."],
              ["trust_evidence", "The paperwork. A precedence table decides which "
               "document wins.", "A complete record, every time. 2 wrong values.",
               "Better — but it still GUESSES. It is confidently wrong on "
               "PKG-007 and PKG-008, where precedence has no way of knowing the "
               "document is the wrong one."],
              ["reconcile", "Neither. It surfaces the disagreement and refuses "
               "to pick.", "An INCOMPLETE record on 4 packages. 0 wrong values.",
               "It costs a handler time on every conflict, including the trivial "
               "ones. That is a real cost and you should quote it at the "
               "client's real volume."],
          ],
          widths=[1.1, 1.85, 1.75, 2.0], mono_cols=(0,), size=8.5)
    callout(doc, "The uncomfortable result.",
            "trust_form and trust_evidence both produce a complete record every "
            "single time. That is exactly what makes them dangerous — a record "
            "with no gaps looks finished, and several of its values are wrong "
            "with nothing attached to say so. reconcile's incompleteness is a "
            "VISIBLE cost, paid by somebody who knows they are paying it.")

    # =====================================================================
    h1(doc, "4 · python3 run_lab.py --show PKG-XXX")
    # =====================================================================
    para(doc, "One package, all three strategies, everything the pipeline knows. "
              "This is where you go when a line in the main table surprises you.")
    code(doc, "python3 run_lab.py --show PKG-008")
    h2(doc, "Actual output")
    code(doc,
         "PKG-008 - bank statement belongs to a different person\n"
         "  why it matters: bank statement is a different person entirely.\n"
         "                  Nothing about the document looks wrong.\n"
         "\n"
         "  STRATEGY: trust_form\n"
         "    wrong accepted: 1    conflicts: 2    needs_human: True\n"
         "      WRONG  account_number: stitched '55710284'  should be 'CONFLICT'\n"
         "      CONFLICT applicant_name: case_form=[PERSON_08]  vs  "
         "identity=[PERSON_08]\n"
         "                               vs  payslip=[PERSON_08]  vs  "
         "bank_statement=[PERSON_12]\n"
         "      CONFLICT account_number: case_form=55710284  vs  "
         "bank_statement=31860492\n"
         "      identity: passed=True  checks=['name_match', 'dob_match', "
         "'validity']",
         size=8)

    h2(doc, "How to read it")
    table(doc,
          ["Line", "What it means"],
          [
              ["wrong accepted", "How many values this strategy wrote into the "
               "record that are not correct."],
              ["conflicts", "How many fields had two or more sources that "
               "disagreed."],
              ["needs_human", "Whether the package would be routed for review. "
               "Note that it is True here for ALL THREE strategies — the "
               "difference is whether a wrong value was also written."],
              ["WRONG <field>", "The field, what was stitched, and what it "
               "should have been. 'CONFLICT' as the truth means the correct "
               "answer was to refuse."],
              ["CONFLICT <field>", "Every source and its value, side by side. "
               "This is the evidence a handler needs."],
              ["identity: passed=", "The verdict, and which checks actually ran. "
               "An empty checks list means the document was never available."],
          ],
          widths=[1.5, 5.0], mono_cols=(0,), size=9)

    h2(doc, "What PKG-008 is actually teaching you")
    rich(doc, [
        ("Look at the identity line: ", {}),
        ("passed=True", {"font": "Consolas", "size": 10}),
        (". The identity check ", {}),
        ("succeeded", {"bold": True}),
        (". The licence genuinely does match the applicant, and it was genuinely "
         "valid. Your identity verification — the thing you built to catch the "
         "wrong person — was completely useless here, because the wrong person "
         "is not on the licence. They are on the bank statement.", {}),
    ])
    para(doc, "What caught PKG-008 is the applicant_name conflict: three "
              "documents say [PERSON_08] and the fourth says [PERSON_12]. Not a "
              "confidence score, not a validator, not the identity check — a "
              "cross-document comparison of a field nobody thinks of as a "
              "security control.")
    callout(doc, "The question to take away.",
            "That check worked because the two names are completely different. "
            "Would it have caught a statement belonging to the applicant's "
            "spouse, at the same address, with a similar surname? Be ready to "
            "answer that, because it is the version that actually happens.")

    # =====================================================================
    h1(doc, "5 · python3 run_lab.py --failures 0.2")
    # =====================================================================
    para(doc, "Fails one document in five during processing, so you can see what "
              "your pipeline does when a package arrives incomplete.")
    code(doc, "python3 run_lab.py --strategy reconcile --failures 0.2")

    h2(doc, "Actual output")
    code(doc,
         "package     WRONG  refused  conflicts  verdict  note\n"
         "-------------------------------------------------------------------\n"
         "PKG-005         1        0    0/1          n/a  account number diff"
         "  <-- account_number=20558193\n"
         "PKG-008         1        0    0/1          n/a  bank statement belo"
         "  <-- account_number=55710284\n"
         "-------------------------------------------------------------------\n"
         "TOTAL           3        1          1      0/8\n"
         "\n"
         "  8 package(s) could not be verified at all because a\n"
         "  document never arrived.",
         size=8)

    h2(doc, "The two things that just happened")
    bullet(doc, "Every verdict became n/a — not WRONG, n/a. The identity "
                "document never arrived, so the check could not run. The "
                "verdicts did not become incorrect; they became IMPOSSIBLE.",
           bold_prefix="0/8 verdicts. ")
    bullet(doc, "The strategy that accepted ZERO wrong values on a healthy run "
                "now accepts three, and surfaces one conflict instead of six.",
           bold_prefix="reconcile went from 0 wrong to 3. ")
    callout(doc, "Why reconcile broke.",
            "reconcile is safe because it notices two sources disagreeing. Lose "
            "one of the two and there is nothing left to disagree with — a "
            "single value looks unanimous. The conflicts did not get resolved; "
            "they became invisible. A missing document does not just remove "
            "data, it removes the CHECK that document was there to perform.")
    para(doc, "That is why a partial package needs a POLICY — process it, hold "
              "it, or request the missing document — and why 'retry the failed "
              "job' is not that policy. The pipeline above did not error. It "
              "produced eight confident, complete-looking, less-trustworthy "
              "records and told nobody.")

    h3(doc, "Why the same documents fail every time")
    rich(doc, [
        ("The injection is seeded (", {}),
        ("seed=7", {"font": "Consolas", "size": 10}),
        (", re-seeded per package), so a given ", {}),
        ("--failures", {"font": "Consolas", "size": 10}),
        (" rate fails the same document type in every package and every learner "
         "sees an identical table. That is deliberate — it makes the lesson "
         "legible instead of noisy. It is ", {}),
        ("not", {"italic": True}),
        (" a model of how real failures distribute, and you should not present "
         "it as one.", {}),
    ])

    # =====================================================================
    h1(doc, "6 · python3 run_lab.py --paths")
    # =====================================================================
    para(doc, "No processing. It prints the Blob storage path design and the "
              "operations that design makes possible.")
    code(doc,
         "uksouth/acme-insurance/claims-6y/CLM-2026-4471/run-20260814-0931/"
         "case_form.json\n"
         "  ^region  ^tenant       ^retention  ^claim      ^run          ^doc",
         size=8)
    table(doc,
          ["Segment", "Why it is in the path"],
          [
              ["region", "Prove nothing left the UK. A residency audit becomes a "
               "prefix listing."],
              ["tenant", "Whose data it is. Multi-tenant separation, and tenant "
               "offboarding."],
              ["retention_class", "How long it lives. 'Delete everything older "
               "than six years for tenant X' is a lifecycle rule on a prefix."],
              ["claim_ref", "What it belongs to. A legal hold, or a subject "
               "access request, on one claim."],
              ["run_id", "Which processing run produced it. Reprocessing, and "
               "debugging one bad batch."],
              ["doc_type", "What kind of thing it is."],
          ],
          widths=[1.5, 5.0], mono_cols=(0,), size=9.5)
    para(doc, "Every one of those is a PREFIX operation. Leave retention out of "
              "the path and 'delete everything older than six years' becomes a "
              "full scan with a per-object decision — at which point somebody "
              "has to write, test and defend a script that deletes customer "
              "data one object at a time.")
    callout(doc, "Design this before you write the first blob.",
            "Moving objects later means rewriting every reference to them. This "
            "is a fifteen-minute decision now and a migration project in "
            "eighteen months.", fill=TEAL_HEX, accent=TEAL)

    # =====================================================================
    h1(doc, "7 · Switching to real Azure Document Intelligence")
    # =====================================================================
    h2(doc, "Step 1 — credentials")
    code(doc, "cp .env.example .env")
    rich(doc, [
        ("Then set ", {}),
        ("AZURE_DOCINT_ENDPOINT", {"font": "Consolas", "size": 10}),
        (" and ", {}),
        ("AZURE_DOCINT_KEY", {"font": "Consolas", "size": 10}),
        (" from Portal → your Document Intelligence resource → ", {}),
        ("Keys and Endpoint", {"italic": True}),
        (". ", {}),
        (".env is git-ignored. Never commit it, never paste a key into chat, "
         "never put one in a screenshot.", {"bold": True}),
    ])
    para(doc, "If you did Day 14, this is the same service, the same resource "
              "and the same variable names. Copy that .env here unchanged.",
         italic=True)

    h2(doc, "Step 2 — render the documents")
    code(doc, "python3 run_lab.py --make-pdfs")
    para(doc, "Azure will not accept a Python dictionary. This renders all 32 "
              "documents as real PDFs under docs/PKG-XXX/, from exactly the same "
              "data the mock serves. One source of truth, two providers.")
    rich(doc, [
        ("Open one. The page says ", {}),
        ("\"Declared Annual Income (GBP): 62000.00\"", {"font": "Consolas",
                                                        "size": 9.5}),
        (" — not ", {}),
        ("annual_income", {"font": "Consolas", "size": 10}),
        (". That gap is deliberate and it is the whole proposition of Query "
         "Fields: we ask for our field name and the service has to work out "
         "which line on the page we meant. A mock whose keys already match ours "
         "cannot test that.", {}),
    ])

    h2(doc, "Step 3 — prove the adapter, then run")
    code(doc, "python3 run_lab.py --selftest\n"
              "python3 run_lab.py --provider azure")
    para(doc, "Expect about three minutes and 32 billed analyses on the first "
              "run. Raw responses are cached under out/azure/di_raw/, so every "
              "run after the first is free and takes seconds. Results land in "
              "out/azure/ — a different directory from out/mock/, so the two "
              "never overwrite each other.")

    h2(doc, "The one call that matters")
    code(doc,
         "POST {endpoint}/documentintelligence/documentModels/"
         "prebuilt-layout:analyze\n"
         "     ?api-version=2024-11-30\n"
         "     &features=queryFields\n"
         "     &queryFields=applicant_name,date_of_birth,annual_income,...\n"
         "\n"
         "-> 202 Accepted\n"
         "   Operation-Location: https://.../analyzeResults/{id}",
         size=8.5)
    para(doc, "Then poll that URL until status is succeeded. Three things about "
              "this request will bite you, and all three are silent failures "
              "rather than errors:")
    bullet(doc, "api-version 2024-11-30 and later live under "
                "/documentintelligence/; earlier versions under "
                "/formrecognizer/. Mismatch them and you get a 404 whose message "
                "talks about the MODEL, which sends people hunting for a "
                "deployment problem that does not exist.",
           bold_prefix="The route moved. ")
    bullet(doc, "features=queryFields turns the add-on on; queryFields=a,b,c "
                "says which. Send the names without the feature flag and you get "
                "HTTP 200 with no documents member at all — successful, empty "
                "and entirely misleading. Nothing errors; you just get zero "
                "fields.", bold_prefix="Query Fields needs both halves. ")
    bullet(doc, "See section 8.3. This is the measured headline of the whole "
                "azure run.",
           bold_prefix="Asking for a field does not make it exist — and the "
                       "service will still answer. ")

    # =====================================================================
    h1(doc, "8 · What the real run measured")
    # =====================================================================
    para(doc, "Figures below are from a live run on 2026-08-17 against a "
              "free-tier (F0) Document Intelligence resource, prebuilt-layout, "
              "api-version 2024-11-30. Your numbers will differ slightly; the "
              "conclusions should not.", italic=True)

    h2(doc, "8.1 — The headline: nothing changed")
    table(doc,
          ["Strategy", "Mock (wrong / refused / conflicts)",
           "Azure (wrong / refused / conflicts)"],
          [
              ["trust_form", "4 / 0 / 6", "4 / 0 / 6"],
              ["trust_evidence", "2 / 0 / 6", "2 / 0 / 6"],
              ["reconcile", "0 / 4 / 6", "0 / 4 / 6"],
          ],
          widths=[1.6, 2.45, 2.45], mono_cols=(0, 1, 2))
    para(doc, "Identical. Every conflict, every refusal, every verdict — 8/8 "
              "correct on both providers.")
    callout(doc, "That is the finding, not a disappointment.",
            "Day 14's azure run diverged from its mock sharply, because Day 14 "
            "was measuring EXTRACTION — whether the model read the characters "
            "correctly. This lab measures something else. Every defect here "
            "lives BETWEEN documents. The service read all 32 documents "
            "essentially perfectly and handed back a set of documents that still "
            "disagree with each other. The real service changed nothing because "
            "the failure was never in the reading.")
    para(doc, "That is the sentence to take to a client, and it is the argument "
              "for why 'verification' and 'stitching' are the two rows in the "
              "production-mapping table that say YOUR OWN CODE.")

    h2(doc, "8.2 — What the extraction actually cost")
    table(doc,
          ["Measure", "Value"],
          [
              ["Documents analysed", "32"],
              ["Query-field requests sent", "152"],
              ["Answered", "152 (100%)"],
              ["Returned empty", "0"],
              ["Mean confidence, per document", "0.903 – 0.995"],
              ["Wall-clock, first (billed) run", "about 2 min 54 s"],
              ["Rate-limited (HTTP 429)", "5 times, 94 s waiting on Retry-After"],
          ],
          widths=[2.9, 3.6], mono_cols=(1,))
    para(doc, "The rate-limit line is a THROUGHPUT number, not an error. Quote "
              "it when somebody asks what 4,000 documents a month looks like on "
              "this tier.")
    callout(doc, "What you are NOT entitled to quote.",
            "These PDFs are digitally generated — the text is embedded, not "
            "scanned. The service reads them far more confidently than it would "
            "read the forms this lab models. That 0.903–0.995 range is a "
            "CEILING, not an estimate. To get a real number, run the client's "
            "own scans through the same pipeline; asking for them is the first "
            "thing to do.")

    h2(doc, "8.3 — The measured headline: over-asking")
    code(doc, "python3 run_lab.py --provider azure --overask")
    para(doc, "This adds field names to each request that the document genuinely "
              "does not contain — a sort code on a payslip, an employer on a "
              "driving licence. It is what happens when a team writes one query "
              "list and reuses it across document types 'to keep things "
              "simple'.")
    para(doc, "The service does not push back. It answers.")
    table(doc,
          ["Measure", "Value"],
          [
              ["Extra requests sent", "72"],
              ["Came back EMPTY — the honest answer", "64"],
              ["Came back WITH A VALUE IN THEM", "8"],
          ],
          widths=[3.4, 3.1], mono_cols=(1,))
    para(doc, "All eight are the same failure, and it is systematic rather than "
              "random:")
    table(doc,
          ["Asked for", "On", "What came back", "Confidence"],
          [
              ["annual_income", "each bank statement", "-58.10", "0.584 – 0.657"],
          ],
          widths=[1.6, 1.9, 1.6, 1.4], mono_cols=(0, 2, 3))
    para(doc, "-58.10 is a grocery card payment in the transaction list. Asked a "
              "bank statement for annual income, the service found the closest "
              "number on the page and returned it, at a confidence high enough "
              "to look like an answer rather than a shrug.")
    callout(doc, "Empty is safe. Populated and wrong is not.",
            "A field that comes back empty lands in 'missing' and somebody sees "
            "a gap. A field that comes back populated and wrong is the exact "
            "failure mode this entire lab is about — arriving from the vendor "
            "rather than from your stitching.")

    h3(doc, "Why it did no damage here, and what that teaches")
    rich(doc, [
        ("None of those eight values reached the unified record, and the totals "
         "were unchanged. The reason is ", {}),
        ("FIELD_SOURCES", {"font": "Consolas", "size": 10}),
        (" in ", {}),
        ("pipeline.py", {"font": "Consolas", "size": 10}),
        (": it declares that ", {}),
        ("annual_income", {"font": "Consolas", "size": 10}),
        (" may be sourced from a case form or a payslip, and from nowhere else. "
         "A bank statement is not an allowed source, so the invented value had "
         "no route in.", {}),
    ])
    para(doc, "That is a whitelist doing exactly the job a whitelist is for. If "
              "your stitching merges 'whatever fields came back' instead of 'the "
              "fields this document type is allowed to supply', the vendor's "
              "guess becomes your record's income figure and nothing anywhere "
              "reports an error.")
    para(doc, "A second data point, from Day 14's motor claim form: asked for "
              "gross_monthly_pay, which no motor claim form has, it returned "
              "9000.00 at confidence 0.75. Same behaviour, higher confidence, on "
              "a different form.", italic=True)

    h2(doc, "8.4 — What did not happen")
    para(doc, "The PAGES THE SERVICE DID NOT READ warning never fired. A "
              "free-tier resource analyses the first two pages of a document and "
              "stops — silently — and Day 14 lost three teaching points to it. "
              "Here, every query field is rendered on page 1 BY DESIGN, so the "
              "limit cannot be mistaken for an extraction failure. The check is "
              "still in the code; add a third page to a document and it will "
              "tell you.")

    # =====================================================================
    h1(doc, "9 · The output files, and what to look for in each")
    # =====================================================================
    para(doc, "Everything lands under out/<provider>/, so a mock run and an "
              "azure run never overwrite each other and you can diff them.")
    table(doc,
          ["File", "What is in it", "What to look for"],
          [
              ["multidoc_report.md", "Strategy comparison, the package list, and "
               "the six questions.", "THE SIX QUESTIONS. They are the "
               "deliverable; the tables are just evidence."],
              ["stitch_results.csv", "Every field, every package, every "
               "strategy: strategy, package, field, value, source, agreement.",
               "Sort by 'agreement' to see every conflict in the corpus at "
               "once."],
              ["unified/PKG-XXX.json", "What your pipeline would actually return "
               "for one package.", "The provenance block — see below."],
              ["query_field_report.md", "AZURE ONLY. What asking cost, per "
               "document, with measured confidences and the over-ask table.",
               "The over-ask section, if you ran --overask."],
              ["di_raw/PKG-XXX/*.json", "AZURE ONLY. The untouched service "
               "responses.", "This is the cache; it is also your evidence when "
               "somebody disputes a number."],
              ["di_raw_overask/", "AZURE ONLY. The same, for --overask runs.",
               "Kept separate so one run cannot pollute the other."],
          ],
          widths=[1.6, 2.6, 2.3], mono_cols=(0,), size=8.5)

    h2(doc, "The field to read first in a unified record")
    code(doc,
         '"provenance": {\n'
         '  "account_number": {\n'
         '    "source": null,\n'
         '    "confidence": null,\n'
         '    "agreement": "CONFLICT_unresolved"\n'
         '  }\n'
         '}', size=8.5)
    table(doc,
          ["agreement value", "What it means"],
          [
              ["all_agree", "Every document that carried this field said the "
               "same thing. The safest kind of value."],
              ["CONFLICT_resolved_to_form", "Sources disagreed; trust_form "
               "picked the application form."],
              ["CONFLICT_resolved_by_precedence", "Sources disagreed; "
               "trust_evidence picked by the precedence table."],
              ["CONFLICT_unresolved", "Sources disagreed and reconcile refused "
               "to pick. The value is null and a human has to decide."],
          ],
          widths=[2.4, 4.1], mono_cols=(0,), size=9)
    para(doc, "A value with no provenance is a value nobody can defend. When a "
              "reviewer asks 'where did this income figure come from and did "
              "anything corroborate it', this block is the answer — not a "
              "paragraph in a design document.")

    # =====================================================================
    h1(doc, "10 · Troubleshooting")
    # =====================================================================
    table(doc,
          ["Symptom", "Cause", "Fix"],
          [
              ["Numbers are not 4 / 2 / 0 on mock", "Something changed in the "
               "pipeline", "python3 run_lab.py --selftest — it names the check "
               "that broke"],
              ["DOCINT_PROVIDER=azure needs AZURE_DOCINT_ENDPOINT", "No .env, or "
               "the values are still placeholders", "cp .env.example .env and "
               "fill in both values"],
              ["'... does not exist. Render the documents first'", "The PDFs "
               "have not been made", "python3 run_lab.py --make-pdfs"],
              ["HTTP 404 talking about the model", "The ROUTE, not the model",
               "api-version 2024-11-30+ needs /documentintelligence/. Set "
               "AZURE_DOCINT_ROUTE to force it"],
              ["HTTP 401 / 403", "The key does not belong to that endpoint",
               "A key from a different Azure AI resource returns exactly this. "
               "Re-copy both from the same blade"],
              ["HTTP 429, run eventually fails", "Rate limit harder than the "
               "backoff", "Raise AZURE_DOCINT_SUBMIT_GAP to 2–5, or move off F0. "
               "Occasional 429s are normal and handled"],
              ["HTTP 400 mentioning queryFields", "Add-on unavailable on that "
               "tier or region, or more than 20 field names", "Check the "
               "resource tier; keep query lists short"],
              ["HTTP 200 but zero fields", "features=queryFields missing", "The "
               "lab adds it for you — this is why, if you hand-roll the call"],
              ["First azure run is slow", "Expected — 32 billed analyses",
               "Every later run reads out/azure/di_raw/ and is instant"],
              ["Want to re-bill deliberately", "The cache is on", "rm -rf "
               "out/azure/di_raw/, or set DOCINT_USE_CACHE=false"],
          ],
          widths=[2.0, 1.9, 2.6], size=8.5)

    # =====================================================================
    h1(doc, "11 · Five conclusions people draw that are wrong")
    # =====================================================================
    table(doc,
          ["The tempting reading", "Why it is wrong", "What to say instead"],
          [
              ["\"Azure gave the same answers as the mock, so running it was a "
               "waste.\"",
               "The identical result IS the finding. It demonstrates that the "
               "defects are relational, not extractive — which is the whole "
               "thesis of the session.",
               "\"The service read all 32 documents perfectly and the records "
               "were still wrong. That is why stitching is our problem, not the "
               "vendor's.\""],
              ["\"reconcile is obviously right, so we recommend reconcile.\"",
               "reconcile refuses on 4 of 8 packages. At real volume that is a "
               "queue somebody has to staff, and nobody has costed it.",
               "Recommend it WITH the flag rate and its cost at the client's "
               "actual monthly volume."],
              ["\"The identity check protects us against the wrong person.\"",
               "PKG-008 passed identity verification. The wrong person was on "
               "the bank statement, which identity verification never looks at.",
               "\"Identity verification checks one document. Cross-document name "
               "agreement is what caught the impostor.\""],
              ["\"Confidence was 0.99, so extraction is 99% reliable.\"",
               "The PDFs are digitally generated. That number measures embedded "
               "text, not scans.",
               "\"That is a ceiling measured on clean digital text. I need your "
               "real scans before I quote an accuracy figure.\""],
              ["\"--failures shows the pipeline degrades gracefully.\"",
               "It does not degrade gracefully. reconcile went from 0 wrong to 3 "
               "and every identity verdict became impossible — silently, with no "
               "error anywhere.",
               "\"A missing document removes the check that document performed. "
               "Partial packages need a policy, not a retry.\""],
          ],
          widths=[1.9, 2.35, 2.25], size=8.5)

    # =====================================================================
    h1(doc, "12 · Before you present")
    # =====================================================================
    for text in [
        "You can explain the identity verdict boundary and point at the code.",
        "You can say why PKG-005 nearly passed, in one sentence about tolerance.",
        "You know what caught PKG-008 — and it is not the identity check.",
        "You ran --failures and can describe what happened to the verdicts, and "
        "why reconcile got worse.",
        "You have a policy for a package that arrives incomplete.",
        "You can name what is in your Blob path and what it makes possible.",
        "You can say which strategy you are recommending, and what it costs at "
        "the client's real monthly volume.",
        "If you ran azure: you can explain why the results were IDENTICAL to the "
        "mock, and why that is the finding rather than an anticlimax.",
        "If you ran --overask: you can say what came back for a field the "
        "document did not have, and which line of your own code stopped it.",
        "You know which numbers from the azure run you are NOT entitled to "
        "quote, and why.",
    ]:
        bullet(doc, text, bold_prefix="☐  ")

    para(doc, "")
    callout(doc, "The sentence your client needs to hear.",
            "Every one of these documents was read correctly. The record built "
            "from them was still wrong. Buying a better extraction service would "
            "not have changed a single number in this report — because the "
            "failure was never in the reading, it was in what we did with what "
            "we read.",
            fill=TEAL_HEX, accent=TEAL)

    # ---- glossary --------------------------------------------------------
    h1(doc, "Glossary")
    table(doc,
          ["Term", "Meaning here"],
          [
              ["Case package", "The set of documents that arrive together for "
               "one claim — form, identity, payslip, bank statement."],
              ["Wrong accepted", "A value stitched into the unified record that "
               "is not correct, with no flag attached. The only outcome that can "
               "reach a customer unnoticed."],
              ["Refused", "A value the strategy declined to pick because sources "
               "disagreed. A visible cost, roughly 30 seconds of handler time."],
              ["Conflict", "Two or more documents supplying different values for "
               "the same field."],
              ["Stitching", "Merging several documents into one record, "
               "including deciding what to do when they disagree. Your code — "
               "nobody sells this."],
              ["Precedence", "The written-down table of which document is "
               "authoritative for which field. If it is not written down it gets "
               "decided by whichever if-branch happens to run first."],
              ["Provenance", "Per field: which document it came from, its "
               "confidence, and whether the sources agreed."],
              ["Identity verdict", "The output of verify_identity — booleans and "
               "notes, and deliberately NO licence number, address or image."],
              ["Orphan", "An asynchronous job that never resolved and that "
               "nobody is waiting for any more."],
              ["Query Fields", "The Document Intelligence add-on that lets you "
               "ask for named fields instead of taking whatever key-value pairs "
               "the model finds. Billed per document."],
              ["prebuilt-layout", "The Document Intelligence model that Query "
               "Fields attaches to, from api-version 2024-11-30."],
              ["F0 / S0", "Free and Standard pricing tiers. F0 rate-limits "
               "aggressively and analyses only the first two pages of a "
               "document, without saying so."],
              ["Ground truth", "What the value actually is. Available here "
               "because the packages are synthetic; never available in "
               "production, which is why refusing to guess matters more than "
               "any metric."],
          ],
          widths=[1.6, 4.9], size=9)

    doc.save(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print("wrote %s (%.1f KB)" % (path, path.stat().st_size / 1024))
