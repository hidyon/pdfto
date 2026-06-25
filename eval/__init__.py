"""Quality-measurement foundation for PDFto (dev/eval only).

This package is **not** imported by the application at runtime; it is a tool for
measuring conversion quality and A/B-comparing knob settings (spec 0030).  The
dependency direction is ``eval -> app`` (the evaluator depends on the app), so
the app's core stays independent of it.
"""
