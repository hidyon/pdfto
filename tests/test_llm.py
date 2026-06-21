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
