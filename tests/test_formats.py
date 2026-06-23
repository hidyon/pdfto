"""Tests for the input-format allowlist and helpers."""

from __future__ import annotations

from app import formats


def test_extension_of():
    assert formats.extension_of("report.PDF") == ".pdf"
    assert formats.extension_of("slides.pptx") == ".pptx"
    assert formats.extension_of("noext") == ""
    assert formats.extension_of("") == ""


def test_is_supported():
    assert formats.is_supported(".pdf")
    assert formats.is_supported(".DOCX")  # case-insensitive
    assert formats.is_supported(".png")
    assert not formats.is_supported(".exe")
    assert not formats.is_supported("")


def test_is_pdf():
    assert formats.is_pdf(".pdf")
    assert formats.is_pdf(".PDF")
    assert not formats.is_pdf(".docx")
