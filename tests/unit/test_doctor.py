"""`tokenmill doctor`, and the specific ways it could lie.

The command's whole value is that its answer is true. So these tests are about
the four ways a hardware report goes wrong, each of which sends a user somewhere
different and expensive:

1. **"CUDA is installed" reported as "there is a GPU."** A container started
   without `--gpus` has the driver libraries and no device. Telling that user
   they have a GPU costs them a 5 GB download that fails at model load.
2. **"No `nvidia-smi`" reported as "no GPU."** Telling a user with a working
   card that they have none sends them to buy hardware they own.
3. **A guessed VRAM figure.** `nvidia-smi` prints `[N/A]` for a device that will
   not answer, and "0.0 GiB" is a worse answer than "not reported".
4. **Apple Silicon reported as CUDA.** Marker runs on MPS; vLLM does not.

The GPU probes are driven against **stub `nvidia-smi` scripts** rather than
against this machine, because a test that asserted what this container has would
be the environment-dependent mistake `docs/REVIEW_PHASES_0_8.md` records twice
(N12) — green here, red on a runner with different hardware.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from tokenmill.backends.heavy import gpu as gpu_module
from tokenmill.backends.heavy.doctor import diagnose
from tokenmill.backends.heavy.gpu import Accelerator, GpuDevice, detect_gpu
from tokenmill.core.models import LicenseTier

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the stub driver is a POSIX shell script"
)


def _stub_nvidia_smi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, stdout: str, exit_code: int = 0
) -> None:
    """Install a fake `nvidia-smi` that prints what a test wants it to.

    Two details cost a debugging round each and are worth stating:

    * It uses `printf`, a shell **builtin**, rather than `cat`. The first
      version used `cat` and every test failed with `cat: not found`, because
      the stub's own PATH does not necessarily contain `/bin`.
    * It **prepends** to PATH rather than replacing it, so the stub wins over a
      real `nvidia-smi` while the script can still find whatever it needs.

    Args:
        tmp_path: Where to write it.
        monkeypatch: Used to put it first on PATH.
        stdout: What it should print.
        exit_code: What it should exit with.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "nvidia-smi"
    body = stdout.replace("\\", "\\\\").replace("%", "%%").replace("'", "'\\''")
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{body}'\nexit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")


class TestTheGpuReportDoesNotLie:
    def test_a_working_card_is_reported_with_its_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_nvidia_smi(tmp_path, monkeypatch, stdout="NVIDIA GeForce RTX 4090, 24564, 550.54.14")

        report = detect_gpu()

        assert report.accelerator is Accelerator.CUDA
        assert report.usable
        assert report.devices == (GpuDevice(name="NVIDIA GeForce RTX 4090", memory_mb=24564),)
        assert report.driver == "550.54.14"
        assert report.total_memory_mb == 24564

    def test_two_cards_are_both_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_nvidia_smi(
            tmp_path,
            monkeypatch,
            stdout=(
                "NVIDIA A100-SXM4-40GB, 40960, 550.54.14\nNVIDIA A100-SXM4-40GB, 40960, 550.54.14"
            ),
        )

        report = detect_gpu()

        assert len(report.devices) == 2
        assert report.total_memory_mb == 81920

    def test_software_without_a_device_is_not_reported_as_no_gpu(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failure 1, and the one this module exists for.

        A container started without `--gpus` looks exactly like this: the
        driver's own tool runs, and lists nothing. "No GPU" and "GPU software
        present, no device" need different fixes, so they get different answers.
        """
        _stub_nvidia_smi(tmp_path, monkeypatch, stdout="")

        report = detect_gpu()

        assert report.accelerator is Accelerator.CUDA_UNUSABLE
        assert not report.usable
        assert "no usable device" in report.detail

    def test_a_driver_error_is_reported_rather_than_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_nvidia_smi(
            tmp_path,
            monkeypatch,
            stdout="Failed to initialize NVML: Driver/library version mismatch",
            exit_code=9,
        )

        report = detect_gpu()

        assert report.accelerator is Accelerator.CUDA_UNUSABLE
        assert any("NVML" in note or "mismatch" in note for note in report.notes)

    def test_an_unreported_memory_figure_is_none_rather_than_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failure 3. `nvidia-smi` prints `[N/A]` for a device that will not answer.

        "0.0 GiB" would read as a real measurement of a card with no memory,
        which is the figure that makes a model download fail at the very end.
        """
        _stub_nvidia_smi(tmp_path, monkeypatch, stdout="Some Odd Device, [N/A], 550.54.14")

        report = detect_gpu()

        assert report.devices[0].memory_mb is None
        assert report.total_memory_mb is None
        assert "not reported" in report.devices[0].describe()

    def test_no_driver_tooling_at_all_is_reported_as_no_gpu(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        monkeypatch.setattr(gpu_module, "_CUDA_MARKERS", ())

        report = detect_gpu()

        assert report.accelerator is Accelerator.NONE
        assert not report.usable

    def test_cuda_libraries_without_nvidia_smi_are_not_no_gpu_either(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failure 2's mirror: software present, tool missing.

        Reported as "software present, no usable device" rather than "no GPU",
        because the fix is to install the driver package rather than to buy a
        card.
        """
        empty = tmp_path / "empty"
        empty.mkdir()
        marker = tmp_path / "cuda"
        marker.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        monkeypatch.setattr(gpu_module, "_CUDA_MARKERS", (str(marker),))

        report = detect_gpu()

        assert report.accelerator is Accelerator.CUDA_UNUSABLE

    def test_apple_silicon_is_not_reported_as_cuda(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failure 4. Marker runs on MPS; vLLM has no Metal backend at all."""
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        # By string target: `gpu_module.sys` is a re-export mypy will not accept
        # as an attribute, and patching the real ones is what the module reads.
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")

        report = detect_gpu()

        assert report.accelerator is Accelerator.APPLE
        assert report.usable
        assert report.total_memory_mb is None, "shared memory has no VRAM figure to report"
        assert any("vLLM" in note for note in report.notes), (
            "a Mac user needs to be told which heavy backends do not run at all, "
            "not only that they have a GPU"
        )


class TestTheDiagnosis:
    def test_it_covers_every_registered_backend(self) -> None:
        from tokenmill.core.registry import Registry

        diagnosis = diagnose(Registry(), probe_torch=False)

        assert {d.backend_id for d in diagnosis.backends} == {c.info.id for c in Registry()}

    def test_every_unavailable_heavy_backend_carries_an_instruction(self) -> None:
        """The phase's acceptance criterion, at the layer `doctor` reports."""
        diagnosis = diagnose(probe_torch=False)

        for backend in diagnosis.heavy:
            if backend.usable_here:
                continue
            has_steps = bool(backend.install_steps)
            has_hint = bool(backend.availability.hint)
            assert has_steps or has_hint, (
                f"{backend.backend_id} is unavailable and says nothing about how "
                f"to change that, which is the one thing doctor exists to do"
            )

    def test_a_weights_licence_is_never_invented(self) -> None:
        diagnosis = diagnose(probe_torch=False)

        for backend in diagnosis.heavy:
            assert backend.weights_licence is None

    def test_mineru_is_reported_as_restricted(self) -> None:
        diagnosis = diagnose(probe_torch=False)
        mineru = next(b for b in diagnosis.backends if b.backend_id == "mineru")

        assert mineru.tier is LicenseTier.RESTRICTED

    def test_it_does_not_run_a_subprocess_for_an_environment_that_does_not_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`doctor` must be instant on a machine with nothing installed.

        Which is every machine that most needs to run it.
        """
        called: list[object] = []
        monkeypatch.setattr(
            "tokenmill.backends.heavy.doctor.describe_environment_torch",
            lambda interpreter: called.append(interpreter),
        )

        diagnose(probe_torch=True)

        assert called == [], (
            "doctor probed PyTorch in an environment that does not exist; that is "
            "seconds of subprocess for a machine with no backends installed"
        )
