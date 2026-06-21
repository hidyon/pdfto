"""Optional LLM post-processing of converted text via the Anthropic API.

This is an opt-in feature: it only runs when an Anthropic API key is configured
(``PDFTO_ANTHROPIC_API_KEY`` / ``ANTHROPIC_API_KEY``).  The ``anthropic`` SDK is
imported lazily so the app and its default tests never require it.

The converted document text is sent to Claude with the caller's instruction;
only the transformed text is returned.  Errors are normalised to
:class:`LLMError` so the job layer can mark the job failed without leaking
internals or crashing the worker.
"""

from __future__ import annotations

import logging
from typing import Optional

from .config import settings

logger = logging.getLogger("pdfto.llm")


class LLMError(RuntimeError):
    """Raised when an LLM transform cannot be completed."""


_SYSTEM = (
    "You post-process text that was converted from a PDF. Apply the user's "
    "instruction to the document and return ONLY the resulting text, with no "
    "preamble, commentary, or code fences."
)


def transform(content: str, instruction: str, *, model: Optional[str] = None,
              max_tokens: Optional[int] = None, api_key: Optional[str] = None,
              timeout: Optional[float] = None) -> str:
    """Return *content* transformed per *instruction* using Claude.

    Raises :class:`LLMError` (never a raw SDK exception) on any failure.
    """

    api_key = api_key or settings.anthropic_api_key
    if not api_key:
        raise LLMError("LLM is not configured (no Anthropic API key)")
    model = model or settings.llm_model
    max_tokens = max_tokens or settings.llm_max_tokens
    timeout = timeout or settings.llm_timeout

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise LLMError("anthropic SDK not installed; run `pip install anthropic`") from exc

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    user = f"Instruction: {instruction}\n\n---\nDocument:\n{content}"
    try:
        # Stream so large documents don't hit request timeouts; collect the
        # final message once complete.
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001 - normalise to LLMError
        raise LLMError(f"LLM request failed: {exc}") from exc

    text = "".join(
        block.text for block in message.content
        if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise LLMError("LLM returned no text")
    logger.info("llm transform applied", extra={"model": model})
    return text
