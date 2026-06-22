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
