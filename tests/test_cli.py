"""Tests for the drawio2tikz command-line interface."""

from importlib.metadata import version as package_version

from typer.testing import CliRunner

from drawio2tikz.cli import app


def test_version_option() -> None:
    """Show the installed package version without requiring an input file."""
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"drawio2tikz {package_version('drawio2tikz')}\n"


def test_help_option_resolves_command_signature() -> None:
    """Regression test: `Path` must be importable at runtime for Typer's signature inspection.

    A prior version imported `Path` only under `TYPE_CHECKING`, which raised
    `NameError: name 'Path' is not defined` as soon as Typer built the command
    (e.g. `inspect.signature(..., eval_str=True)`), since `from __future__ import
    annotations` makes all annotations strings evaluated at runtime.
    """
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert result.exception is None
