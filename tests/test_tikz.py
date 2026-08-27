"""Tests for the native sanitized-SVG to TikZ renderer."""

from __future__ import annotations

import pytest
from defusedxml.common import DefusedXmlException

from drawio2tikz.tikz import convert_svg_to_tikz

ARC_CUBIC_SEGMENTS = 2
TRANSFORMED_SHAPES = 3


def _svg(body: str, *, width: int = 100, height: int = 80) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">{body}</svg>'


def test_paths_colors_and_coordinate_mapping() -> None:
    """Convert SVG path commands, colors, widths, and the inverted Y axis."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<path d="M 10 10 L 20 20 H 30 V 40 Z" '
            'fill="#123456" stroke="#abcdef" stroke-width="2"/>',
        )
    )

    assert r"\definecolor{c123456}{RGB}{18,52,86}" in tikz
    assert r"\definecolor{cabcdef}{RGB}{171,205,239}" in tikz
    assert "draw=cabcdef,line width=1.5pt" in tikz
    assert "(7.5, 52.5) -- (15, 45) -- (22.5, 45) -- (22.5, 30) -- cycle" in tikz


def test_curves_relative_commands_and_smooth_controls() -> None:
    """Preserve cubic, smooth, quadratic, and relative path geometry."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<path d="m10 10 c10 0 10 10 20 10 s10 10 20 0 '
            'q10 -10 20 0 t20 0" fill="none" stroke="black"/>',
        )
    )

    assert "controls (15, 52.5) and (15, 45) .. (22.5, 45)" in tikz
    assert "controls (30, 45) and (30, 37.5) .. (37.5, 45)" in tikz
    assert "controls (42.5, 50) and (47.5, 50) .. (52.5, 45)" in tikz
    assert "controls (57.5, 40) and (62.5, 40) .. (67.5, 45)" in tikz


def test_arc_is_approximated_with_cubic_curves() -> None:
    """Convert elliptical arcs without an external SVG library."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<path d="M 10 50 A 40 20 30 0 1 90 50" fill="none" stroke="black"/>',
            height=100,
        )
    )

    assert tikz.count(".. controls") == ARC_CUBIC_SEGMENTS
    assert "(7.5, 37.5)" in tikz
    assert "(67.5, 37.5)" in tikz


def test_shapes_inherited_style_and_transform() -> None:
    """Apply group styles and transforms to primitive SVG shapes."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<g transform="translate(10,20) rotate(30)" stroke="#000" '
            'stroke-width="4" stroke-opacity="0.5" fill="none">'
            '<rect x="0" y="0" width="20" height="10"/>'
            '<ellipse cx="30" cy="10" rx="5" ry="8"/>'
            '<polyline points="0,0 5,5 10,0" stroke-dasharray="2 3"/>'
            "</g>",
        )
    )

    assert "draw=black,line width=3pt,draw opacity=0.5" in tikz
    assert "dash pattern=on 1.5pt off 2.25pt" in tikz
    assert tikz.count(r"\path[") == TRANSFORMED_SHAPES


def test_text_anchor_rotation_and_raw_tex() -> None:
    """Keep raw TeX labels and mark true visual centers explicitly."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<g transform="rotate(30,50,40)">'
            '<text id="drawio2tikzcenter0line0" x="50" y="40" '
            'text-anchor="middle">\\textbf{vertex}</text>'
            "</g>",
        )
    )

    assert r"\node[anchor=center,rotate=-30] (drawio2tikzcenter0line0)" in tikz
    assert r"{\textbf{vertex}};" in tikz


def test_text_presentation_style() -> None:
    """Preserve ordinary SVG text size, color, opacity, weight, and style."""
    tikz = convert_svg_to_tikz(
        _svg(
            '<g fill="#123456" fill-opacity="0.5" font-size="20px" '
            'font-weight="700" font-style="italic">'
            '<text x="10" y="20">label</text>'
            "</g>",
        )
    )

    assert r"\definecolor{c123456}{RGB}{18,52,86}" in tikz
    assert "text=c123456,text opacity=0.5" in tikz
    assert r"font={\fontsize{15pt}{18pt}\selectfont\bfseries\itshape}" in tikz


def test_output_units_scale_and_precision() -> None:
    """Honor the public unit, scale, and rounding options."""
    tikz = convert_svg_to_tikz(
        _svg('<line x1="0" y1="0" x2="10" y2="20" stroke="black"/>'),
        output_unit="mm",
        scale=2,
        round_number=2,
    )

    assert r"\def \globalscale {2.000000}" in tikz
    assert "y=1mm, x=1mm" in tikz
    assert "(0, 21.17) -- (2.65, 15.88)" in tikz


def test_rejects_unsafe_xml() -> None:
    """Reject entity declarations before native SVG traversal."""
    unsafe = '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg>&xxe;</svg>'

    with pytest.raises(DefusedXmlException):
        convert_svg_to_tikz(unsafe)


@pytest.mark.parametrize("unit", ["em", "pc", "invalid"])
def test_rejects_unknown_output_unit(unit: str) -> None:
    """Fail clearly instead of emitting invalid TikZ dimensions."""
    with pytest.raises(ValueError, match="Unsupported output unit"):
        convert_svg_to_tikz(_svg(""), output_unit=unit)
