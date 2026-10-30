"""
make_pdfs.py — render the 32 documents of the eight case packages as PDFs.

WHY THIS EXISTS
---------------
`packages.py` holds the eight packages as the SHAPE Query Fields returns. That
is enough to learn the pipeline, and it is all the mock provider needs.

The moment you point the lab at the real service you need something to point it
AT. Azure will not accept a Python dictionary. So this module renders the same
32 documents — the same values, the same conflicts between them — as real PDFs
on disk, and the azure provider posts those.

    packages.PACKAGES  --render-->  docs/PKG-001/case_form.pdf  --POST-->  Azure DI

One source of truth, two providers. Edit a package in `packages.py`, re-run
`--make-pdfs`, and the real path picks the change up too.

THE ONE THING THAT MAKES THIS A REAL TEST
-----------------------------------------
The pages do NOT print our field names. `annual_income` is printed as
"Declared Annual Income (GBP)", `document_number` as "Licence Number" — the
labels in `packages.LABELS`, which are the form designer's words, not ours.

That gap is the whole proposition of Query Fields. We ask for `annual_income`
and the service has to work out that the line beginning "Declared Annual
Income" is the one we meant. A mock whose keys already match ours cannot test
that, and it is the part most likely to behave differently on the client's
actual forms.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
These are DIGITAL PDFs — the text is embedded, not scanned. State that before
you show anyone the azure run. Confidence measured against digitally generated
text is a CEILING, not an estimate. Handwriting is not simulated; you cannot
fake it with an embedded font, and pretending otherwise in front of a client is
how you lose the room.

What DOES survive the round trip is every conflict this lab is built on. The
one-digit account number difference in PKG-005 is rendered as printed digits
and comes back as printed digits. PKG-008's bank statement really does carry a
different person's name. The service reads all of it correctly and stitches it
into the wrong record anyway — because the defect was never in the reading.

NO DEPENDENCIES
---------------
Standard library only — this writes the PDF bytes directly. A PDF is a handful
of objects, a cross-reference table of byte offsets, and a trailer. Worth
reading once, because "the file format is just a format" is a useful thing to
have felt at least once in your career.
"""

from __future__ import annotations

from pathlib import Path

import packages as pk

PAGE_W, PAGE_H = 595, 842          # A4 in points
MARGIN = 64


# ==========================================================================
# 1. A MINIMAL PDF WRITER
# ==========================================================================
def _esc(s: str) -> str:
    """Escape a string for a PDF literal. Backslash first, or you escape
    your own escapes."""
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class _Text:
    """One run of text to place on a page."""

    def __init__(self, x, y, s, size=11, bold=False, gray=0.0):
        self.x, self.y, self.s = x, y, s
        self.size, self.bold, self.gray = size, bold, gray

    def ops(self) -> str:
        font = "/F2" if self.bold else "/F1"
        return (
            f"BT {self.gray:.2f} g {font} {self.size} Tf "
            f"1 0 0 1 {self.x:.1f} {self.y:.1f} Tm "
            f"({_esc(self.s)}) Tj ET\n"
        )


def _build_pdf(pages: list[list[_Text]]) -> bytes:
    """pages[i] is the list of text runs on page i. Returns the PDF bytes."""
    objects: list[bytes] = []          # 1-indexed on write

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)            # this object's number

    # Reserve 1 = catalog, 2 = page tree; we know their numbers up front but
    # cannot write them until the kids exist.
    objects.append(b"")                # 1 catalog placeholder
    objects.append(b"")                # 2 pages placeholder

    f_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                    b"/Encoding /WinAnsiEncoding >>")
    f_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                 b"/Encoding /WinAnsiEncoding >>")

    kids = []
    for runs in pages:
        stream = "".join(r.ops() for r in runs).encode("latin-1", "replace")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream)
                      + stream + b"\nendstream")
        page = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
            b"/Contents %d 0 R >>"
            % (PAGE_W, PAGE_H, f_regular, f_bold, content)
        )
        kids.append(page)

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (b"<< /Type /Pages /Kids [%s] /Count %d >>"
                  % (b" ".join(b"%d 0 R" % k for k in kids), len(kids)))

    # Serialise, recording the byte offset of every object for the xref table.
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_at))
    return bytes(out)


# ==========================================================================
# 2. THE DOCUMENT LAYOUTS
#
# "Label: Value" on one line is the shape both key-value extraction and query
# field extraction read most reliably. The label is the FORM DESIGNER'S wording
# from packages.LABELS, never our field name.
# ==========================================================================
FILLER = {
    "case_form": [
        "DECLARATION",
        "I declare that the information given on this form is true and complete",
        "to the best of my knowledge. I understand that giving false information",
        "may invalidate my policy and may be reported to the relevant authorities.",
        "",
        "Supporting evidence supplied with this application:",
        "  - photographic identification",
        "  - evidence of income for the most recent pay period",
        "  - a bank statement showing the account for settlement",
        "",
        "Signature: ______________________     Date: ______________________",
    ],
    "bank_statement": [
        "TRANSACTIONS",
        "",
        "01 Mar   Card payment    GROCERIES                        -64.20",
        "03 Mar   Direct debit    UTILITIES                       -118.00",
        "07 Mar   Faster payment  SALARY                         +2,847.15",
        "12 Mar   Card payment    FUEL                             -71.44",
        "19 Mar   Direct debit    INSURANCE                        -46.90",
        "26 Mar   Card payment    GROCERIES                        -58.10",
        "",
        "This statement is issued for information only and does not constitute",
        "a certified record of account activity.",
    ],
    "identity": [
        "This licence is the property of the issuing authority and must be",
        "produced on request. Categories: B, BE. Restrictions: none recorded.",
    ],
    "payslip": [
        "Payments and deductions are calculated in accordance with current",
        "HMRC guidance. Retain this document for your records.",
    ],
}


def _render(pkg_id: str, doc_type: str, fields: list[dict]) -> bytes:
    base = pk.base_type(doc_type)
    layout = pk.DOC_LAYOUT[base]
    n_pages = layout["pages"]
    pages: list[list[_Text]] = [[] for _ in range(n_pages)]

    for i, runs in enumerate(pages, start=1):
        y = PAGE_H - MARGIN
        runs.append(_Text(MARGIN, y, layout["title"], 16, bold=True))
        y -= 18
        runs.append(_Text(MARGIN, y, "DecisionStream AI  -  Claims Intake", 10, gray=0.35))
        y -= 14
        runs.append(_Text(MARGIN, y, f"Case package {pkg_id}          Page {i} of {n_pages}",
                          10, gray=0.35))
        runs.append(_Text(MARGIN, y - 12, "_" * 74, 10, gray=0.45))

    # Every query field on page 1, under the form designer's label.
    y = PAGE_H - MARGIN - 82
    for f in fields:
        label = pk.LABELS.get(f["field"], f["field"].replace("_", " ").title())
        pages[0].append(_Text(MARGIN, y, f"{label}: {f['value']}", 11))
        y -= 24

    # Prose on the last page, so the service reads something other than pairs.
    last = pages[-1]
    fy = min(y - 34, PAGE_H - MARGIN - 100) if n_pages == 1 else PAGE_H - MARGIN - 100
    for n, line in enumerate(FILLER.get(base, [])):
        bold = n == 0 and line.isupper()
        last.append(_Text(MARGIN, fy, line, 10.5 if bold else 9, bold=bold, gray=0.0 if bold else 0.25))
        fy -= 16

    return _build_pdf(pages)


# ==========================================================================
# 3. ENTRY POINT
# ==========================================================================
def pdf_path(doc_dir: Path, pkg_id: str, doc_type: str) -> Path:
    """docs/PKG-001/case_form.pdf — a directory per package, because that is
    how they arrive and how a human looks for them."""
    return doc_dir / pkg_id / f"{doc_type}.pdf"


def make_all(doc_dir: Path, quiet: bool = False) -> list[Path]:
    written = []
    for pkg in pk.PACKAGES:
        (doc_dir / pkg["id"]).mkdir(parents=True, exist_ok=True)
        for doc_type, fields in pkg["docs"].items():
            path = pdf_path(doc_dir, pkg["id"], doc_type)
            path.write_bytes(_render(pkg["id"], doc_type, fields))
            written.append(path)
        if not quiet:
            print(f"  {pkg['id']}  {len(pkg['docs'])} documents  "
                  f"({', '.join(pkg['docs'])})")
    return written


def missing(doc_dir: Path) -> list[tuple[str, str]]:
    return [(p, d) for p, d in pk.all_docs() if not pdf_path(doc_dir, p, d).exists()]
