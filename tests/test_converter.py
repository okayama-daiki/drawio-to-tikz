"""Tests for SVG-to-TikZ conversion details."""

from __future__ import annotations

from pathlib import Path

from drawio2tikz.converter import (
    ConvertOptions,
    _convert_svg_source,  # pyright: ignore[reportPrivateUsage]
)


def test_centered_drawio_label_uses_tikz_center_anchor() -> None:
    """Translate marked draw.io center coordinates to TikZ center anchors."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
<text id="drawio2tikzcenter0line0" x="50" y="50" text-anchor="middle">vertex</text>
<text id="ordinary" x="50" y="75" text-anchor="middle">weight</text>
</svg>"""
    options = ConvertOptions(input_path=Path("diagram.drawio"))

    tikz = _convert_svg_source(svg, options)

    assert r"\node[anchor=center] (drawio2tikzcenter0line0)" in tikz
    assert r"\node[anchor=south] (ordinary)" in tikz
