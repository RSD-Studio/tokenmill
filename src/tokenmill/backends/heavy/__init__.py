"""The GPU tier: high-quality ML converters that are never a dependency.

``pyproject.toml``'s ``heavy = []`` group is empty and stays empty. Every
backend in this package is invoked **out of process** — a child process in an
environment of its own, or an HTTP service in a container — and none of them
appears in ``tokenmill``'s dependency tree at any tier. That is
``CONTRIBUTING.md`` rule 1 and it is not negotiable: these tools resolve to
multi-gigabyte installs with PyTorch, CUDA and model weights, and a document
converter that pulls those in by default is not a light install with an extra.

**What "unavailable" means here, and why it is the important path.** Almost
nobody running tokenmill has a GPU. So the behaviour that matters, and the one
this phase actually verifies, is what a CPU-only machine sees: every adapter
reports itself unavailable with the exact commands that would install it, and no
conversion is ever attempted. ``tokenmill doctor`` is the same information
gathered in one place.

**What was verified and what was not**, stated here as well as in
``PROGRESS.md`` because it is the honest headline of the phase:

* The absent-runtime path, the licence classification, the ``doctor`` output and
  the service adapters' HTTP behaviour are all verified — the last against a
  real local server, not a mock.
* **No heavy backend has ever converted a document.** This sandbox has no GPU
  and cannot reach ``huggingface.co``, so no model has been downloaded and no
  conversion has been run. Every claim about output quality in
  ``docs/BACKENDS.md`` is attributed to its source and marked unverified.

**The licences are not what the plan said**, and each was read from the
published artefact rather than from ``docs/research/RESEARCH.md``:

============  =====================================  ==========================
Backend       Verified licence                       The plan said
============  =====================================  ==========================
Marker        Apache-2.0 (``marker-pdf`` 2.0.0)      GPL-3.0
Surya         Apache-2.0 (``surya-ocr`` 0.22.1)      GPL-3.0
MinerU        ``LicenseRef-MinerU-Open-Source-       AGPL (true of its
              License`` — Apache-2.0 plus a          predecessor ``magic-pdf``)
              revenue/MAU threshold and an
              online-service attribution obligation
olmOCR        Apache-2.0 (``olmocr`` 0.4.27)         Apache-2.0
============  =====================================  ==========================

Two of the plan's GPL backends are now permissive, which means **their code
could legally be imported**. They still are not, and the reason is rule 1 rather
than rule 2: importing them would put PyTorch in our dependency tree. The
distinction is kept visible, exactly as ``backends/external/`` keeps it for
LibreOffice.

**Weights are licensed separately from code, and that is the trap.** An
Apache-2.0 repository routinely ships weights under something else — a RAIL
licence with use restrictions, a non-commercial clause, or a bespoke agreement.
This sandbox cannot reach ``huggingface.co``, so **no weight licence here has
been verified**, and ``docs/LICENSES.md`` says so per backend rather than
guessing. The rule the adapters enforce meanwhile is the conservative one: a
backend whose weights are *reported* to be non-commercial is excluded by
default and needs an explicit opt-in.
"""

from __future__ import annotations

__all__: list[str] = []
