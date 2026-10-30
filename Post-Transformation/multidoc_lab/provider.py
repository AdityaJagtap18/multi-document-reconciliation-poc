"""
provider.py — the seam.

This is the whole switch. Two modules expose the same two functions, and this
picks one:

                       start(pkg, doc)      poll(handle)
    mock_multidoc            yes                yes
    azure_multidoc.Backend   yes                yes

`pipeline.AsyncAnalyzer` binds to whichever this returns and never asks which
it got. `packages.py` does not import this file at all — the ground truth, the
package list and the notes are properties of the CASE, not of whoever read the
documents, which is what makes the two runs comparable.

Keep the seam this narrow and "can we swap Document Intelligence for Textract"
is a one-file question with an honest answer. Let vendor types leak past it and
the same question needs a project.
"""

from __future__ import annotations

from types import SimpleNamespace

import azure_multidoc
import mock_multidoc
from config import Settings, get_settings


def get(provider_override: str | None = None,
        overask: bool = False) -> tuple[object, Settings]:
    settings = get_settings(provider_override)

    if settings.provider == "mock":
        if overask:
            print("\n  --overask has no effect on the mock provider.\n"
                  "  The mock cannot invent a value for a field that is not in "
                  "the package,\n  which is exactly why this flag exists: only "
                  "the real service can show\n  you what happens when you ask a "
                  "document a question it cannot answer.\n")
        backend = SimpleNamespace(
            name="mock",
            poll_gap=mock_multidoc.poll_gap,
            start=mock_multidoc.start,
            poll=mock_multidoc.poll,
            describe=mock_multidoc.describe,
            metas={},
            overask=False,
        )
        return backend, settings

    azure_multidoc.preflight(settings, settings.doc_dir)
    return azure_multidoc.Backend(settings, overask=overask), settings
