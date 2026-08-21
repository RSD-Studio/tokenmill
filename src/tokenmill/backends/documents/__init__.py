"""Document backends: the light, CPU-only, permissively licensed tier.

Five adapters live here, registered through the ``tokenmill.backends`` entry
point group like any other plugin:

============ ============ =============================================
Backend      Install       What it is for
============ ============ =============================================
``pdfplumber``  core       Digital PDFs where the tables matter.
``pypdf``       core       Digital PDFs where the reading order matters.
``markitdown``  documents  Breadth: Office, mail, archives, media.
``kreuzberg``   documents  Fast unified extraction across many formats.
``docling``     docling    Best structure fidelity; pulls PyTorch.
============ ============ =============================================

Nothing in this package is imported at start-up. Each module imports cleanly
with its dependency absent and does the real import inside ``_convert``, which
is ``CONTRIBUTING.md`` rule 3 and what keeps ``tokenmill backends`` cheap.

``docs/BACKENDS.md`` records what each one is good at and — quoted from real
output on our own fixtures — what each one gets wrong.
"""

from __future__ import annotations

__all__: list[str] = []
