"""Command-line interface for drawio2tikz."""

from __future__ import annotations

from importlib.metadata import version as package_version
from pathlib import (
    Path,  # noqa: TC003 (Typer does search `Path` in global namespaces at runtime)
)
from typing import Annotated

import typer
from rich.console import Console

from .converter import DEFAULT_DRAWIO_BIN, ConvertOptions, convert

app = typer.Typer(
    add_completion=False,
    help="Convert diagrams.net/draw.io diagrams to TikZ via sanitized SVG.",
)
console = Console()


def _version_callback(value: object) -> None:
    if value is True:
        console.print(f"drawio2tikz {package_version('drawio2tikz')}")
        raise typer.Exit


@app.command()
def main(
    input_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Input .drawio file."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output .tex file or output directory."),
    ] = None,
    page_index: Annotated[
        int,
        typer.Option("--page-index", min=1, help="1-based draw.io page index."),
    ] = 1,
    *,
    all_pages: Annotated[
        bool,
        typer.Option("--all-pages", help="Export every page found in a .drawio file."),
    ] = False,
    keep_svg: Annotated[
        bool,
        typer.Option("--keep-svg", help="Keep the sanitized intermediate SVG."),
    ] = False,
    svg_dir: Annotated[
        Path | None,
        typer.Option("--svg-dir", help="Directory for kept SVG files. Requires --keep-svg."),
    ] = None,
    drawio_bin: Annotated[
        str,
        typer.Option("--drawio-bin", help="draw.io CLI executable."),
    ] = DEFAULT_DRAWIO_BIN,
    output_unit: Annotated[
        str,
        typer.Option("--output-unit", help="Output unit passed to svg2tikz."),
    ] = "pt",
    scale: Annotated[
        float,
        typer.Option("--scale", help="Scale passed to svg2tikz."),
    ] = 1.0,
    round_number: Annotated[
        int,
        typer.Option("--round-number", min=0, help="Coordinate precision for svg2tikz."),
    ] = 3,
    texmode: Annotated[
        str,
        typer.Option("--texmode", help="svg2tikz text mode. raw preserves injected TeX labels."),
    ] = "raw",
    markings: Annotated[
        str,
        typer.Option("--markings", help="svg2tikz marker handling."),
    ] = "interpret",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress external command echoing."),
    ] = False,
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Convert draw.io diagrams to TikZ LaTeX code."""
    if svg_dir and not keep_svg:
        msg = "--svg-dir requires --keep-svg"
        raise typer.BadParameter(msg)

    options = ConvertOptions(
        input_path=input_path,
        output=output,
        page_index=page_index,
        all_pages=all_pages,
        keep_svg=keep_svg,
        svg_dir=svg_dir,
        drawio_bin=drawio_bin,
        output_unit=output_unit,
        scale=scale,
        round_number=round_number,
        texmode=texmode,
        markings=markings,
        quiet=quiet,
    )

    try:
        results = convert(options)
    except Exception as exc:
        console.print(f"[red]drawio2tikz:[/red] {exc}")
        raise typer.Exit(1) from exc

    for result in results:
        svg_note = f", svg: {result.svg_path}" if result.svg_path else ""
        console.print(f"wrote: [green]{result.tex_path}[/green]{svg_note}")
        if result.remaining_foreign_objects:
            console.print(
                "[yellow]warning:[/yellow] sanitized SVG still contains "
                f"{result.remaining_foreign_objects} foreignObject node(s); "
                "some draw.io HTML text may be omitted.",
            )
        if result.text_nodes:
            console.print(f"note: sanitized SVG contains {result.text_nodes} SVG text node(s).")

    console.print(f"converted {len(results)} page(s)")
