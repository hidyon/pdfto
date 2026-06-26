"""Tests for the optional LLM post-processing (anthropic mocked)."""

from __future__ import annotations

import sys
import types

import pytest

from app import llm
from app.config import settings


def test_transform_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(llm.LLMError):
        llm.transform("hello", "summarize")


def _install_fake_anthropic(monkeypatch, captured):
    """Install a fake `anthropic` module that records the request."""

    class _Msg:
        def __init__(self, text):
            self.content = [types.SimpleNamespace(type="text", text=text)]

    class _Stream:
        def __init__(self, text):
            self._text = text
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get_final_message(self):
            return _Msg(self._text)

    class _Messages:
        def stream(self, **kwargs):
            captured.update(kwargs)
            return _Stream("TRANSFORMED")

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.messages = _Messages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def test_transform_calls_anthropic_and_returns_text(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(settings, "anthropic_api_key", "key-xyz")
    monkeypatch.setattr(settings, "llm_model", "claude-opus-4-8")
    _install_fake_anthropic(monkeypatch, captured)

    out = llm.transform("# Doc\nbody", "translate to English")
    assert out == "TRANSFORMED"
    assert captured["model"] == "claude-opus-4-8"
    # The instruction and document both go into the user message.
    user = captured["messages"][0]["content"]
    assert "translate to English" in user
    assert "# Doc" in user
    # No sampling params are passed (removed on current models).
    assert "temperature" not in captured


def test_resolve_instruction_combinations():
    from app.models import LLMPreset

    # Preset only -> its curated instruction.
    only_preset = llm.resolve_instruction(LLMPreset.ocr_fix, None)
    assert only_preset == llm.PRESET_INSTRUCTIONS["ocr_fix"]
    # Free instruction only.
    assert llm.resolve_instruction(None, "summarize") == "summarize"
    # Both -> preset text then the free instruction.
    both = llm.resolve_instruction(LLMPreset.cleanup, "translate to English")
    assert both.startswith(llm.PRESET_INSTRUCTIONS["cleanup"])
    assert both.endswith("translate to English")
    # Neither / blanks -> None.
    assert llm.resolve_instruction(None, None) is None
    assert llm.resolve_instruction(None, "   ") is None
    # A bare string preset value works; unknown values are ignored.
    assert llm.resolve_instruction("tables", None) == llm.PRESET_INSTRUCTIONS["tables"]
    assert llm.resolve_instruction("bogus", None) is None


def test_apply_llm_uses_resolved_instruction(monkeypatch):
    """_apply_llm runs transform with the resolved preset+instruction."""
    from app import main
    from app.models import ConversionOptions, LLMPreset, OutputFormat

    seen: dict = {}
    monkeypatch.setattr(main.settings, "anthropic_api_key", "key-xyz")  # llm_enabled
    monkeypatch.setattr(main.llm, "transform",
                        lambda content, instruction: seen.update(
                            content=content, instruction=instruction) or "FIXED")

    out = main._apply_llm("body", ConversionOptions(
        output_format=OutputFormat.markdown, llm_preset=LLMPreset.ocr_fix))
    assert out == "FIXED"
    assert seen["instruction"] == llm.PRESET_INSTRUCTIONS["ocr_fix"]


def test_apply_llm_noop_without_preset_or_instruction(monkeypatch):
    from app import main
    from app.models import ConversionOptions, OutputFormat

    monkeypatch.setattr(main.settings, "anthropic_api_key", "key-xyz")
    monkeypatch.setattr(main.llm, "transform",
                        lambda *a, **k: pytest.fail("transform must not be called"))
    out = main._apply_llm("body", ConversionOptions(output_format=OutputFormat.markdown))
    assert out == "body"


def test_transform_wraps_sdk_errors(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "key-xyz")

    class _Boom:
        def __init__(self, **kwargs):
            self.messages = self
        def stream(self, **kwargs):
            raise RuntimeError("network down")

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _Boom
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    with pytest.raises(llm.LLMError):
        llm.transform("x", "y")
