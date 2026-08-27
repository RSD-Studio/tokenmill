"""Licence isolation, enforced rather than declared.

**This file is Phase 7.** The adapters that follow it exist to be checked by it,
and it was written first for the reason `docs/REVIEW_PHASES_0_6.md` §6 gives: a
licence isolation mechanism that was never seen to catch anything is
indistinguishable from one that does not work.

There are four distinct checks here and they fail in different circumstances,
which is the point of having four:

1. **Declaration.** Every registered backend states a licence and a tier, and a
   non-permissive one states out-of-process isolation. This has existed since
   Phase 1 in `test_protocol.py`; it is restated here because the other three are
   meaningless without it and a reader of this file should see the whole rule.
2. **Environment.** No copyleft distribution is installed and importable at all.
   Catches a copyleft package entering the dependency tree through a transitive
   requirement nobody read.
3. **Static imports.** No in-process adapter module mentions a copyleft module,
   parsed rather than executed. This is the one that works on a machine where the
   copyleft package was never installed — which is every machine this project's
   CI runs on — and it is therefore the one that will actually catch a Phase 9
   adapter written in a hurry.
4. **Runtime.** After a copyleft backend has actually converted a document, its
   module is not in `sys.modules`. The plan's own verification snippet, and the
   only check that observes the isolation rather than inferring it.

`TestTheCheckCatchesAViolation` is the guard on all of it. Each mechanism is fed
a deliberate violation and asserted to reject it, because the failure mode of a
safety net is passing quietly forever.
"""

from __future__ import annotations

import sys
from email.message import Message
from importlib.metadata import Distribution
from pathlib import Path
from typing import Any

import pytest

from tokenmill.core.licensing import (
    KNOWN_COPYLEFT_MODULES,
    audit_installed,
    classify,
    copyleft_violations,
    imported_top_level_modules,
    tier_for_module,
)
from tokenmill.core.models import IsolationMode, LicenseTier
from tokenmill.core.registry import Registry

#: Distributions allowed to classify as copyleft and still be installed.
#:
#: One entry, and each one costs a paragraph in `docs/LICENSES.md` —
#: `test_every_exemption_is_documented` enforces that. An undocumented exemption
#: is a waived rule.
#:
#: **`docutils`** arrives as a direct dependency of `nicegui`, in the `gui`
#: extra. Its metadata carries three licence classifiers and no SPDX
#: expression — Public Domain, BSD, and *GNU General Public License (GPL)* —
#: which `classify()` joins conservatively and reads as copyleft. Reading the
#: installed `COPYING.rst` of 0.23 shows the GPL applies to exactly one file,
#: `tools/editors/emacs/rst.el`, which is Emacs Lisp and **is not in the
#: wheel**: the installed package contains no `.el` file and no GPL text
#: anywhere. Verified here on 2026-08-26, not read from a summary.
#:
#: `tld` is *not* here and must not be. It ships
#: `MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later`, a disjunction the recipient
#: resolves, and tokenmill takes the MPL-1.1 branch. `classify()` reads it as
#: permissive **without** an exemption, which is the correct answer rather than
#: a waived one, and a test asserts the distinction.
ALLOWED_COPYLEFT: frozenset[str] = frozenset({"docutils"})

#: The source tree, for the static scan.
SRC = Path(__file__).resolve().parents[2] / "src" / "tokenmill"


def _fake_distribution(name: str, version: str, **headers: str) -> Distribution:
    """Build a distribution that exists only for this test.

    Args:
        name: The distribution name.
        version: Its version.
        **headers: Metadata headers, such as ``License_Expression``. Underscores
            become hyphens, because a keyword argument cannot carry one.

    Returns:
        Something :func:`~tokenmill.core.licensing.audit_installed` will read.
    """
    message = Message()
    message["Name"] = name
    message["Version"] = version
    for key, value in headers.items():
        message[key.replace("_", "-")] = value

    class _Fake(Distribution):
        @property
        def metadata(self) -> Any:
            return message

        @property
        def version(self) -> str:
            return version

        def read_text(self, _filename: str) -> str | None:
            return None

        def locate_file(self, path: Any) -> Any:
            return Path(path)

    return _Fake()


@pytest.fixture(scope="module")
def registry() -> Registry:
    """The backends the entry points actually expose."""
    return Registry()


class TestEveryBackendDeclaresItsLicence:
    def test_every_backend_states_a_licence_and_a_tier(self, registry: Registry) -> None:
        for converter in registry:
            info = converter.info
            assert info.license.strip(), f"{info.id} states no licence"
            assert isinstance(info.license_tier, LicenseTier), f"{info.id} states no tier"

    def test_a_non_permissive_backend_runs_out_of_process(self, registry: Registry) -> None:
        """`CONTRIBUTING.md` rule 2, over whatever is registered right now."""
        for converter in registry:
            info = converter.info
            if info.license_tier is LicenseTier.PERMISSIVE:
                continue
            assert info.isolation is not IsolationMode.IN_PROCESS, (
                f"backend {info.id!r} is {info.license_tier.value} and declares "
                f"in-process isolation; AGPL and GPL tools are never imported"
            )

    def test_the_declared_licence_agrees_with_the_installed_metadata(
        self, registry: Registry
    ) -> None:
        """A backend cannot declare itself permissive over a copyleft package.

        Only checked where the module is knowable — either installed here, or in
        `KNOWN_COPYLEFT_MODULES`. A backend whose tool is absent and not in that
        table is skipped rather than guessed at, and the static scan below is
        what covers it instead.
        """
        for converter in registry:
            info = converter.info
            for module in _modules_of(converter):
                actual = tier_for_module(module)
                if actual is None or actual is LicenseTier.PERMISSIVE:
                    continue
                assert info.license_tier is not LicenseTier.PERMISSIVE, (
                    f"backend {info.id!r} declares itself permissive but reaches "
                    f"{module!r}, which is {actual.value}"
                )


class TestNoCopyleftPackageIsInstalled:
    def test_nothing_copyleft_is_importable_in_this_environment(self) -> None:
        records = audit_installed()
        violations = copyleft_violations(records, allowed=ALLOWED_COPYLEFT)

        assert not violations, (
            "copyleft distributions are installed and therefore importable: "
            + ", ".join(f"{r.name} {r.version} ({r.expression})" for r in violations)
            + ". AGPL and GPL tools are invoked as a child process or not wrapped "
            "at all; see CONTRIBUTING.md rule 2 and docs/LICENSES.md"
        )

    def test_the_audit_actually_read_something(self) -> None:
        """Guard the guard: an audit over nothing passes every check above."""
        records = audit_installed()

        assert len(records) > 20, f"only {len(records)} distributions audited"
        assert any(r.name == "tokenmill" for r in records)

    def test_tld_is_permissive_by_disjunction_and_not_by_exemption(self) -> None:
        """The one dependency whose licence string contains "GPL".

        `docs/LICENSES.md` explains it in prose. This asserts the code agrees
        with the prose, and specifically that it agrees for the *right reason* —
        by resolving the disjunction, not by being waived on the allow-list.
        """
        assert "tld" not in {n.lower() for n in ALLOWED_COPYLEFT}
        assert classify("MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later") is LicenseTier.PERMISSIVE

    def test_the_docutils_exemption_is_still_for_the_reason_claimed(self) -> None:
        """Re-checks the exemption's premise against the installed package.

        The claim is that docutils' GPL classifier covers one Emacs Lisp file
        that is not shipped in the wheel. If a future release starts shipping
        GPL Python code, this fails and the exemption has to be revisited rather
        than inherited.

        Skipped where docutils is absent — it arrives with the `gui` extra, and
        a core-only install has nothing to check.
        """
        import importlib.util

        spec = importlib.util.find_spec("docutils")
        if spec is None or spec.origin is None:
            pytest.skip("docutils is not installed here; it comes with the gui extra")

        package = Path(spec.origin).parent

        assert not list(package.rglob("*.el")), (
            "docutils now ships Emacs Lisp in the wheel; the exemption in "
            "ALLOWED_COPYLEFT assumed it did not"
        )
        offenders = [
            path.name
            for path in package.rglob("*.py")
            if "GNU General Public License" in path.read_text(encoding="utf-8", errors="replace")
        ]
        assert not offenders, (
            f"docutils now ships Python files claiming the GPL: {offenders}. The "
            f"exemption in ALLOWED_COPYLEFT is no longer justified"
        )

    def test_every_exemption_is_documented(self) -> None:
        """Adding to the allow-list must cost a paragraph, not a line."""
        licenses_md = (SRC.parents[1] / "docs" / "LICENSES.md").read_text(encoding="utf-8")

        for name in ALLOWED_COPYLEFT:
            assert name in licenses_md, (
                f"{name} is exempted from the copyleft check but docs/LICENSES.md "
                f"does not mention it. An undocumented exemption is a waived rule"
            )


class TestNoInProcessAdapterImportsCopyleft:
    """The check that works without the copyleft package being installed."""

    def test_no_module_in_the_package_imports_a_known_copyleft_module(self) -> None:
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            for module in imported_top_level_modules(path):
                if module in KNOWN_COPYLEFT_MODULES:
                    offenders.append(f"{path.relative_to(SRC.parents[1])} imports {module!r}")

        assert not offenders, (
            "copyleft modules are imported into the tokenmill process:\n  "
            + "\n  ".join(offenders)
            + "\nInvoke the tool as a child process through "
            "tokenmill.backends.isolated instead"
        )

    def test_no_in_process_backend_reaches_a_copyleft_distribution(
        self, registry: Registry
    ) -> None:
        """Per backend rather than per file, so the message names the backend."""
        for converter in registry:
            info = converter.info
            if info.isolation is not IsolationMode.IN_PROCESS:
                continue
            for module in _modules_of(converter):
                assert tier_for_module(module) is not LicenseTier.COPYLEFT, (
                    f"backend {info.id!r} runs in-process and imports {module!r}, which is copyleft"
                )

    def test_the_scanner_sees_imports_inside_functions(self, tmp_path: Path) -> None:
        """The property the whole static check rests on.

        `CONTRIBUTING.md` rule 3 puts every heavy import *inside* `_convert()`.
        A scanner that only read the top of a file would find nothing in any
        adapter in this project and would pass forever.
        """
        module = tmp_path / "sneaky.py"
        module.write_text(
            "def convert():\n"
            "    import fitz\n"
            "    from pymupdf4llm import to_markdown\n"
            "    return fitz, to_markdown\n",
            encoding="utf-8",
        )

        found = imported_top_level_modules(module)

        assert "fitz" in found
        assert "pymupdf4llm" in found


class TestNothingCopyleftIsLoaded:
    def test_no_copyleft_module_is_in_sys_modules(self) -> None:
        """The plan's own verification, as an assertion.

        `uv run python -c "import sys, tokenmill; assert 'fitz' not in sys.modules"`.
        By the time this runs, the whole test suite has imported tokenmill and
        exercised every available backend.
        """
        loaded = sorted(set(sys.modules) & set(KNOWN_COPYLEFT_MODULES))

        assert not loaded, f"copyleft modules are loaded in this process: {loaded}"


class TestTheCheckCatchesAViolation:
    """Each mechanism, fed a deliberate violation, asserted to reject it.

    Without these, every assertion above could be vacuously true and nobody would
    know. `PROGRESS.md` also records a violation introduced by hand into the real
    tree, the suite failing, and the revert — because a synthetic violation
    proves the function works and only a real one proves it is wired in.
    """

    def test_an_agpl_distribution_in_the_environment_is_caught(self) -> None:
        installed = [
            _fake_distribution("pymupdf4llm", "0.0.31", License_Expression="AGPL-3.0-only"),
            _fake_distribution("trafilatura", "2.2.0", License_Expression="Apache-2.0"),
        ]

        violations = copyleft_violations(audit_installed(installed), allowed=ALLOWED_COPYLEFT)

        assert [r.name for r in violations] == ["pymupdf4llm"]

    def test_a_gpl_classifier_is_caught_even_without_an_spdx_expression(self) -> None:
        """Older packages state their licence as a trove classifier."""
        installed = [
            _fake_distribution(
                "pandocfilters",
                "1.5.1",
                Classifier="License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
            )
        ]

        violations = copyleft_violations(audit_installed(installed))

        assert [r.name for r in violations] == ["pandocfilters"]

    def test_a_dual_agpl_or_commercial_licence_is_copyleft_not_permissive(self) -> None:
        """The defect writing this phase found, in the tool the phase is about.

        PyMuPDF4LLM's installed metadata (1.28.2, read 2026-08-26) states::

            Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License

        `classify()` resolves a disjunction to its most permissive branch, which
        is right for `tld` and wrong here: the second branch has to be *bought*,
        so the only branch tokenmill holds is the AGPL one. Both spellings are
        asserted because the first version of the rule split on a case-sensitive
        `OR` and therefore got the free-text form right by luck while getting the
        SPDX form of the identical licence wrong — classifying the flagship
        copyleft tool this phase exists to isolate as importable.
        """
        assert classify("AGPL-3.0-only OR LicenseRef-Artifex-Commercial") is LicenseTier.COPYLEFT
        assert (
            classify("Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License")
            is LicenseTier.COPYLEFT
        )
        assert classify("GPL-3.0-only OR Proprietary") is LicenseTier.COPYLEFT

    def test_a_purchasable_only_licence_is_not_permissive_either(self) -> None:
        """`CONTRIBUTING.md` rule 1 excludes it before rule 2 is reached."""
        assert classify("Commercial") is LicenseTier.NON_COMMERCIAL
        assert classify("Proprietary") is LicenseTier.NON_COMMERCIAL

    def test_the_purchasable_rule_does_not_break_the_disjunction_it_must_not(self) -> None:
        """`tld` has three branches and all three are genuinely on offer.

        Taking MPL-1.1 is a real choice, not an unbought one, so the fix for
        PyMuPDF4LLM must not turn this into a violation. Asserted beside it
        because the two cases look identical and are not.
        """
        assert classify("MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later") is LicenseTier.PERMISSIVE

    def test_lgpl_is_not_treated_as_a_violation(self) -> None:
        """Deliberate, and the module docstring says why.

        LGPL exists to permit use as a library without relicensing the caller,
        and this project's rule names AGPL and GPL. Asserted so that tightening
        it later is a decision somebody makes rather than a regex drifting.
        """
        installed = [_fake_distribution("chardet", "5.2.0", License_Expression="LGPL-2.1-or-later")]

        assert copyleft_violations(audit_installed(installed)) == ()

    def test_a_non_commercial_licence_is_classified_and_not_silently_permitted(self) -> None:
        record = audit_installed(
            [_fake_distribution("readerlm", "1.0", License_Expression="CC-BY-NC-4.0")]
        )[0]

        assert record.tier is LicenseTier.NON_COMMERCIAL

    def test_an_adapter_that_imports_a_copyleft_module_is_caught(self, tmp_path: Path) -> None:
        """The static scan, against a file shaped exactly like a real adapter.

        Lazy import inside `_convert`, which is what `CONTRIBUTING.md` rule 3
        requires and what a naive scanner would miss.
        """
        adapter = tmp_path / "pymupdf_pdf.py"
        adapter.write_text(
            '"""A plausible-looking adapter that breaks rule 2."""\n'
            "\n"
            "from tokenmill.core.protocol import BaseConverter\n"
            "\n"
            "\n"
            "class PyMuPDFConverter(BaseConverter):\n"
            "    def _convert(self, source, options, context):\n"
            "        import pymupdf4llm\n"
            "\n"
            "        return pymupdf4llm.to_markdown(str(source.path))\n",
            encoding="utf-8",
        )

        found = imported_top_level_modules(adapter)
        offending = found & set(KNOWN_COPYLEFT_MODULES)

        assert offending == {"pymupdf4llm"}, (
            "the static scan did not see a lazily imported copyleft module; "
            "every real adapter imports lazily, so this is the case that matters"
        )

    def test_a_backend_declaring_copyleft_and_in_process_cannot_be_constructed(self) -> None:
        """The Phase 1 half of the rule, still holding.

        Restated here rather than only in `test_models.py` because this file is
        where somebody looks to find out what enforces the licence policy, and
        "the dataclass refuses to exist" is the strongest link in the chain.
        """
        from tokenmill.core.models import BackendInfo, Domain

        with pytest.raises(ValueError, match="out of process"):
            BackendInfo(
                id="sneaky",
                name="Sneaky",
                description="An AGPL tool imported into our process.",
                domains=(Domain.DOCUMENTS,),
                input_formats=("pdf",),
                license="AGPL-3.0",
                license_tier=LicenseTier.COPYLEFT,
                upstream_url="https://example.invalid",
                isolation=IsolationMode.IN_PROCESS,
            )


def _modules_of(converter: object) -> frozenset[str]:
    """Return the top-level modules the converter's own module imports.

    Args:
        converter: A registered backend instance.

    Returns:
        The imported top-level names, or an empty set when the source cannot be
        located — a namespace-package plugin, say.
    """
    module_name = type(converter).__module__
    module = sys.modules.get(module_name)
    origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if origin is None or not origin.endswith(".py"):
        return frozenset()
    try:
        return imported_top_level_modules(Path(origin))
    except (OSError, SyntaxError):  # a plugin we cannot read is not ours to judge
        return frozenset()
