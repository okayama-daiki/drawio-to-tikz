"""Tests for draw.io label parsing."""

from __future__ import annotations

import base64
import urllib.parse
import zlib
from typing import TYPE_CHECKING

from drawio2tikz.drawio import Label, LabelLine, parse_label, parse_labels
from drawio2tikz.svg import _restore_foreign_object_text  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_mixed_formatting() -> None:
    """Test parsing labels with mixed formatting."""
    label = parse_label(
        '<div><font style="font-size: 40px;"><b>Assign searchers evenly&nbsp;</b></font></div>'
        '<div><font style="font-size: 40px;"><b>to '
        '<font style="color: rgb(255, 128, 0);">unfinished</font> subtrees.</b></font></div>',
    )

    expected_first = r"\fontsize{30.0pt}{36.0pt}\selectfont \textbf{Assign searchers evenly}"
    assert label.lines[0].text == expected_first

    expected_second = (
        r"\fontsize{30.0pt}{36.0pt}\selectfont \textbf{to "
        r"\textcolor[HTML]{FF8000}{unfinished} subtrees.}"
    )
    assert label.lines[1].text == expected_second


def test_parse_math_label_raw() -> None:
    """Test parsing math labels in raw mode."""
    label = parse_label('<font style="font-size: 28px;">\\(\\times 10\\)</font>')

    expected = r"\fontsize{21.0pt}{25.2pt}\selectfont \(\times 10\)"
    assert label.lines[0].text == expected


def test_parse_math_label_preserves_tex_syntax() -> None:
    """Test parsing draw.io math labels without escaping math syntax."""
    label = parse_label(
        '<span style="font-size: 50px;"><font style="color: rgb(255, 128, 0);">'
        r"\(= D_{T_{\textrm{GTE}}(G)}(s, u_1)\)"
        "</font></span>",
    )

    assert label.lines[0].text == (
        r"\fontsize{37.5pt}{45.0pt}\selectfont "
        r"\textcolor[HTML]{FF8000}{\(= D_{T_{\textrm{GTE}}(G)}(s, u_1)\)}"
    )


def test_parse_math_label_still_escapes_surrounding_text() -> None:
    """Test escaping normal text while preserving inline math spans."""
    label = parse_label(r"a_b \(x_i\) {z}")

    assert label.lines[0].text == r"a\_b \(x_i\) \{z\}"


def test_parse_label_preserves_raw_tex_macro() -> None:
    r"""Test that raw TeX macro calls (e.g. \hyperlink{...}{...}) are not brace-escaped."""
    label = parse_label(r"\hyperlink{par:lower-bound-case-2}{\textit{Case 2}}")

    assert label.lines[0].text == r"\hyperlink{par:lower-bound-case-2}{\textit{Case 2}}"


def test_parse_label_still_escapes_braces_outside_tex_macros() -> None:
    """Test that literal braces unrelated to a TeX macro call are still escaped."""
    label = parse_label("{plain text}")

    assert label.lines[0].text == r"\{plain text\}"


def test_parse_css_font_weight() -> None:
    """Test parsing CSS font-weight declarations."""
    label = parse_label('<span style="font-weight: 700;">heavy</span>')

    assert label.lines[0].text == r"\textbf{heavy}"


def test_parse_object_wrapped_label(tmp_path: Path) -> None:
    """Test parsing labels stored on draw.io object wrappers."""
    drawio_path = tmp_path / "object.drawio"
    drawio_path.write_text(
        """<mxfile>
  <diagram>
    <mxGraphModel>
      <root>
        <object id="obj-1" label="Wrapped label">
          <mxCell vertex="1" parent="1" />
        </object>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
""",
        encoding="utf-8",
    )

    labels = parse_labels(drawio_path)

    assert labels["obj-1"].lines[0].text == "Wrapped label"


def test_parse_mxcell_style_font_size(tmp_path: Path) -> None:
    """Test parsing labels with draw.io fontSize style declarations."""
    drawio_path = tmp_path / "style-font-size.drawio"
    drawio_path.write_text(
        """<mxfile>
  <diagram>
    <mxGraphModel>
      <root>
        <mxCell id="cell-1" value="Sized label" style="text;html=1;fontSize=32;" />
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
""",
        encoding="utf-8",
    )

    labels = parse_labels(drawio_path)

    assert labels["cell-1"].lines[0].text == (
        r"\fontsize{24.0pt}{28.8pt}\selectfont Sized label"
    )


def test_parse_object_wrapped_style_font_size(tmp_path: Path) -> None:
    """Test parsing object labels with fontSize on the wrapped mxCell."""
    drawio_path = tmp_path / "object-style-font-size.drawio"
    drawio_path.write_text(
        """<mxfile>
  <diagram>
    <mxGraphModel>
      <root>
        <object id="obj-1" label="Wrapped sized label">
          <mxCell vertex="1" parent="1" style="text;html=1;fontSize=28;" />
        </object>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
""",
        encoding="utf-8",
    )

    labels = parse_labels(drawio_path)

    assert labels["obj-1"].lines[0].text == (
        r"\fontsize{21.0pt}{25.2pt}\selectfont Wrapped sized label"
    )


def test_parse_compressed_diagram_label(tmp_path: Path) -> None:
    """Test parsing labels from compressed draw.io diagram payloads."""
    drawio_path = tmp_path / "compressed.drawio"
    model = (
        '<mxGraphModel><root><mxCell id="cell-1" value="Compressed label" /></root></mxGraphModel>'
    )
    drawio_path.write_text(
        f"<mxfile><diagram>{_compress_diagram(model)}</diagram></mxfile>",
        encoding="utf-8",
    )

    labels = parse_labels(drawio_path)

    assert labels["cell-1"].lines[0].text == "Compressed label"


def test_restore_centered_label_uses_drawio_shape_center() -> None:
    """Use the flex center, not the fallback PNG bounds, for shape labels."""
    svg = """<g data-cell-id="vertex-s"><switch>
<foreignObject><div xmlns="http://www.w3.org/1999/xhtml"
 style="display: flex; align-items: unsafe center; justify-content: unsafe center;
 width: 52px; height: 1px; padding-top: 70px; margin-left: 294px;">
label</div></foreignObject>
<image x="294" y="53.5" width="52" height="41" />
</switch></g>"""
    label = Label(lines=[LabelLine(text=r"\(s\)", font_size=28.0)], font_size=28.0)

    restored = _restore_foreign_object_text(svg, {"vertex-s": label})

    assert 'id="drawio2tikzcenter0line0"' in restored
    assert 'x="320.000" y="70.000"' in restored


def test_restore_top_aligned_label_keeps_baseline_approximation() -> None:
    """Do not center labels that draw.io explicitly aligns to the top."""
    svg = """<g data-cell-id="weight"><switch>
<foreignObject><div xmlns="http://www.w3.org/1999/xhtml"
 style="display: flex; align-items: unsafe flex-start; justify-content: unsafe center;
 width: 48px; height: 1px; padding-top: 197px; margin-left: 165px;">
label</div></foreignObject>
<image x="165" y="197.5" width="48" height="41" />
</switch></g>"""
    label = Label(lines=[LabelLine(text=r"\(6\)", font_size=28.0)], font_size=28.0)

    restored = _restore_foreign_object_text(svg, {"weight": label})

    assert 'id="drawio2tikzlabel0line0"' in restored
    assert 'x="189.000" y="227.800"' in restored


def _compress_diagram(xml_text: str) -> str:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    payload = urllib.parse.quote(xml_text, safe="").encode()
    compressed = compressor.compress(payload) + compressor.flush()
    return base64.b64encode(compressed).decode()
