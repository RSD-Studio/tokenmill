"""Tests for widgetlib.core."""

from widgetlib import Widget


def test_render() -> None:
    assert Widget("demo").render() == "<demo size=1>"


def test_scaled() -> None:
    assert Widget("demo", 2).scaled(3).size == 6
