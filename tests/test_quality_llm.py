"""Opt-in real LLM post-processing check (calls the Anthropic API).

This makes a real, billed Claude request, so it is skipped unless BOTH
``PDFTO_RUN_LLM_TESTS=1`` is set AND an Anthropic API key is configured
(``ANTHROPIC_API_KEY`` / ``PDFTO_ANTHROPIC_API_KEY``).  The default ``pytest``
run never touches the network (the LLM unit tests in ``test_llm.py`` mock the
SDK).  Keep the input tiny to minimise cost.
"""

from __future__ import annotations

import os

import pytest

RUN_LLM = os.environ.get("PDFTO_RUN_LLM_TESTS") == "1"
HAS_KEY = bool(
    os.environ.get("ANTHROPIC_API_KEY")
    or os.environ.get("PDFTO_ANTHROPIC_API_KEY")
)

pytestmark = pytest.mark.skipif(
    not (RUN_LLM and HAS_KEY),
    reason="set PDFTO_RUN_LLM_TESTS=1 and an Anthropic API key to run real LLM tests",
)


def test_transform_real_call_returns_text():
    """A real Claude transform returns non-empty text (no strict match)."""
    from app import llm

    out = llm.transform("Hello, world.", "Reply with only the word OK.")
    assert isinstance(out, str)
    assert out.strip() != ""


def test_ocr_fix_preset_corrects_a_garbled_token():
    """The ocr_fix preset should repair an obvious OCR misread from context."""
    from app import llm
    from app.models import LLMPreset

    instruction = llm.resolve_instruction(LLMPreset.ocr_fix, None)
    # "lnvoice" / "T0TAL" are classic OCR confusions (l->I, O->0).
    garbled = "lnvoice number 12345\nT0TAL due: 9.00 USD"
    out = llm.transform(garbled, instruction)
    assert isinstance(out, str) and out.strip() != ""
    low = out.lower()
    assert "invoice" in low and "total" in low      # corrected
    assert "12345" in out and "9.00" in out         # facts preserved
