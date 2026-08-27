"""SVG to TikZ conversion with sanitization for draw.io diagrams."""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING

from .drawio import count_pages, drawio_stem, parse_labels
from .svg import sanitize_svg
from .tikz import convert_svg_to_tikz

# The draw.io CLI is the intended process boundary.

if TYPE_CHECKING:
    from .drawio import Label

XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)
DOCTYPE_RE = re.compile(r"^\s*<!DOCTYPE[^>]*(?:\[[\s\S]*?\]\s*)?>\s*", re.IGNORECASE)
DEFAULT_DRAWIO_BIN = environ.get("DRAWIO_BIN", "drawio")
DRAWIO_EXPORT_TIMEOUT_SECONDS = float(environ.get("DRAWIO_EXPORT_TIMEOUT_SECONDS", "120"))
MAX_PAGE_COUNT = int(environ.get("DRAWIO2TIKZ_MAX_PAGE_COUNT", "50"))


@dataclass(frozen=True)
class ConvertOptions:
    """Options for SVG to TikZ conversion."""

    input_path: Path
    output: Path | None = None
    page_index: int = 1
    all_pages: bool = False
    keep_svg: bool = False
    svg_dir: Path | None = None
    drawio_bin: str = DEFAULT_DRAWIO_BIN
    output_unit: str = "pt"
    scale: float = 1.0
    round_number: int = 3
    texmode: str = "raw"
    markings: str = "interpret"
    quiet: bool = False


@dataclass(frozen=True)
class ConversionResult:
    """Result of a single conversion."""

    tex_path: Path
    svg_path: Path | None
    remaining_foreign_objects: int
    text_nodes: int


def convert(options: ConvertOptions) -> list[ConversionResult]:
    """Convert a draw.io file to TikZ LaTeX code."""
    if not options.input_path.exists():
        raise FileNotFoundError(options.input_path)
    if shutil.which(options.drawio_bin) is None and not Path(options.drawio_bin).exists():
        msg = f"draw.io CLI not found: {options.drawio_bin}"
        raise RuntimeError(msg)

    labels = parse_labels(options.input_path)
    page_indexes = _page_indexes(options)

    return [_convert_one(options, labels, page_index) for page_index in page_indexes]


def _page_indexes(options: ConvertOptions) -> list[int]:
    """Get list of page indexes to convert."""
    if not options.all_pages:
        return [options.page_index]

    page_count = count_pages(options.input_path)
    if page_count == 0:
        msg = "--all-pages needs a plain .drawio XML file with diagram pages."
        raise RuntimeError(msg)
    if page_count > MAX_PAGE_COUNT:
        msg = f"Input contains {page_count} pages; the limit is {MAX_PAGE_COUNT}."
        raise RuntimeError(msg)
    return list(range(1, page_count + 1))


def _convert_one(
    options: ConvertOptions,
    labels: dict[str, Label],
    page_index: int,
) -> ConversionResult:
    """Convert a single page to TikZ."""
    tex_path = _default_output_path(
        options.input_path,
        options.output,
        page_index,
        all_pages=options.all_pages,
    )
    tex_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="drawio2tikz-") as tmp:
        tmp_dir = Path(tmp)
        raw_svg = tmp_dir / f"{tex_path.stem}.raw.svg"
        sanitized_svg = tmp_dir / f"{tex_path.stem}.svg"

        _run_drawio_export(options, page_index, raw_svg)
        stats = sanitize_svg(raw_svg, sanitized_svg, labels)

        kept_svg = None
        if options.keep_svg:
            svg_dir = options.svg_dir or tex_path.parent
            svg_dir.mkdir(parents=True, exist_ok=True)
            kept_svg = svg_dir / f"{tex_path.stem}.svg"
            shutil.copyfile(sanitized_svg, kept_svg)

        tikz = _convert_svg_source(
            sanitized_svg.read_text(encoding="utf-8"),
            options,
        )
        tex_path.write_text(
            _source_comment(options.input_path, page_index) + tikz,
            encoding="utf-8",
        )

    return ConversionResult(
        tex_path=tex_path,
        svg_path=kept_svg,
        remaining_foreign_objects=stats.remaining_foreign_objects,
        text_nodes=stats.text_nodes,
    )


def _run_drawio_export(options: ConvertOptions, page_index: int, raw_svg: Path) -> None:
    """Run draw.io CLI to export SVG."""
    command = [
        options.drawio_bin,
        "--export",
        "--format",
        "svg",
        "--page-index",
        str(page_index),
        "--output",
        str(raw_svg),
        str(options.input_path),
    ]
    if not options.quiet:
        sys.stdout.write(f"+ {' '.join(command)}\n")
        sys.stdout.flush()
    # This is an argument list and is never passed through a shell.
    subprocess.run(  # noqa: S603  # nosec B603
        command,
        check=True,
        timeout=DRAWIO_EXPORT_TIMEOUT_SECONDS,
    )


def _convert_svg_source(svg_source: str, options: ConvertOptions) -> str:
    """Convert SVG source to TikZ code."""
    return convert_svg_to_tikz(
        _strip_xml_prolog(svg_source),
        output_unit=options.output_unit,
        texmode=options.texmode,
        scale=options.scale,
        round_number=options.round_number,
    )


def _strip_xml_prolog(svg_source: str) -> str:
    """Strip XML declaration and DOCTYPE from SVG source."""
    svg_source = XML_DECL_RE.sub("", svg_source, count=1)
    return DOCTYPE_RE.sub("", svg_source, count=1)


def _default_output_path(
    input_path: Path,
    output: Path | None,
    page_index: int,
    *,
    all_pages: bool,
) -> Path:
    """Determine output path for TikZ file."""
    stem = drawio_stem(input_path)
    filename = f"{stem}-{page_index:02d}.tex" if all_pages else f"{stem}.tex"

    if output is None:
        return input_path.parent / "tikz" / filename
    if output.suffix == ".tex" and not all_pages:
        return output
    return output / filename


def _source_comment(input_path: Path, page_index: int) -> str:
    """Generate LaTeX comment with conversion metadata."""
    return (
        f"% Generated from {input_path} page {page_index} via drawio SVG.\n"
        "% The intermediate SVG was sanitized by drawio2tikz.\n"
    )
