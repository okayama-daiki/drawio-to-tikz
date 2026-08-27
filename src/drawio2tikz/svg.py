"""SVG sanitization for draw.io diagrams."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .drawio import Label, LabelLine, with_tex_font_size

if TYPE_CHECKING:
    from pathlib import Path

STYLE_ELEMENT_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL)
STYLE_ATTR_RE = re.compile(r'\sstyle="[^"]*"')
SWITCH_FOREIGN_OBJECT_RE = re.compile(
    r"<switch>\s*<foreignObject\b[^>]*>(.*?)</foreignObject>\s*"
    r"<image\s+([^>]*)/>\s*</switch>",
    re.DOTALL,
)
ATTR_RE = re.compile(r'([:\w-]+)="([^"]*)"')
FLEX_CONTAINER_STYLE_RE = re.compile(
    r'<div\b[^>]*\bstyle="([^"]*\bdisplay:\s*flex\b[^"]*)"',
    re.IGNORECASE,
)
CSS_LENGTH_RE_TEMPLATE = r"(?:^|;)\s*{property}:\s*([-+]?[0-9.]+)px(?:;|$)"


@dataclass(frozen=True)
class SVGStats:
    """Statistics about SVG sanitization."""

    remaining_foreign_objects: int
    text_nodes: int


def sanitize_svg(
    raw_svg: Path,
    sanitized_svg: Path,
    labels: dict[str, Label],
) -> SVGStats:
    """Sanitize SVG by converting foreign objects to text nodes."""
    text = raw_svg.read_text(encoding="utf-8")
    text = _restore_foreign_object_text(text, labels)
    text = STYLE_ELEMENT_RE.sub("", text)
    text = STYLE_ATTR_RE.sub("", text)
    sanitized_svg.write_text(text, encoding="utf-8")
    return SVGStats(
        remaining_foreign_objects=text.count("foreignObject"),
        text_nodes=text.count("<text"),
    )


def _restore_foreign_object_text(
    svg_text: str,
    labels: dict[str, Label],
) -> str:
    """Restore text in foreign objects using parsed labels."""
    label_serial = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal label_serial
        cell_id = _nearest_cell_id(svg_text, match.start())
        if not cell_id or cell_id not in labels:
            return match.group(0)
        label_obj = labels[cell_id]
        replacement = _text_svg_for_label(
            label_obj,
            _parse_attrs(match.group(2)),
            match.group(1),
            label_serial,
        )
        label_serial += 1
        return replacement or match.group(0)

    return SWITCH_FOREIGN_OBJECT_RE.sub(replace, svg_text)


def _nearest_cell_id(svg_text: str, offset: int) -> str | None:
    """Find the nearest cell ID before the given offset."""
    marker = 'data-cell-id="'
    start = svg_text.rfind(marker, 0, offset)
    if start == -1:
        return None
    start += len(marker)
    end = svg_text.find('"', start)
    if end == -1:
        return None
    return svg_text[start:end]


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    """Parse attributes from a string."""
    return {name: html.unescape(value) for name, value in ATTR_RE.findall(raw_attrs)}


def _text_svg_for_label(
    label: Label,
    image_attrs: dict[str, str],
    foreign_object_body: str,
    label_serial: int,
) -> str:
    """Generate SVG text nodes for a label."""
    try:
        x = float(image_attrs["x"])
        y = float(image_attrs["y"])
        width = float(image_attrs["width"])
        height = float(image_attrs["height"])
    except KeyError, ValueError:
        return ""

    if not label.lines:
        return ""

    font_size = label.font_size or height / len(label.lines) * 0.8
    font_size = max(8.0, min(font_size, height * 0.95))
    line_height = font_size * 1.2
    cx = x + width / 2
    vertical_center = _flex_vertical_center(foreign_object_body)

    if vertical_center is None:
        first_y = y + height / 2 - (len(label.lines) - 1) * line_height / 2 + font_size * 0.35
        node_id_prefix = f"drawio2tikzlabel{label_serial}line"
    else:
        first_y = vertical_center - (len(label.lines) - 1) * line_height / 2
        # Mark labels whose SVG Y coordinate is a true visual center so the
        # native TikZ renderer can use a center anchor rather than a baseline.
        node_id_prefix = f"drawio2tikzcenter{label_serial}line"

    text_nodes: list[str] = []
    for index, line in enumerate(label.lines):
        line_text = _line_text_with_fallback_size(line, font_size)
        node_id = f' id="{node_id_prefix}{index}"'
        text_nodes.append(
            f'<text{node_id} x="{cx:.3f}" y="{first_y + index * line_height:.3f}" '
            f'text-anchor="middle" font-size="{font_size:.3f}px">'
            f"{html.escape(line_text, quote=False)}</text>",
        )
    return "".join(text_nodes)


def _flex_vertical_center(foreign_object_body: str) -> float | None:
    """Return draw.io's exact vertical center for flex-centered labels."""
    match = FLEX_CONTAINER_STYLE_RE.search(foreign_object_body)
    if not match:
        return None

    style = html.unescape(match.group(1))
    normalized_style = re.sub(r"\s+", " ", style).strip()
    if not re.search(
        r"(?:^|;)\s*align-items:\s*(?:unsafe\s+)?center(?:;|$)",
        normalized_style,
        re.IGNORECASE,
    ):
        return None

    padding_top_re = re.compile(
        CSS_LENGTH_RE_TEMPLATE.format(property="padding-top"),
        re.IGNORECASE,
    )
    if padding_top := padding_top_re.search(normalized_style):
        return float(padding_top.group(1))
    return None


def _line_text_with_fallback_size(line: LabelLine, font_size_px: float) -> str:
    """Generate TeX text for a label line with fallback font size."""
    if line.font_size:
        return line.text
    return with_tex_font_size(line.text, font_size_px)
