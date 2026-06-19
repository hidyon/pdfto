"""PDFto — convert PDF documents into Markdown and other formats.

The package is organised so the conversion core (:mod:`app.converter`) and the
content analysis used to drive interactive questions (:mod:`app.questions`) are
independent of the web layer (:mod:`app.main`).  This keeps the project easy to
reuse from other systems: import the functions directly, call the REST API, or
use the bundled web UI.
"""

__version__ = "0.1.0"
