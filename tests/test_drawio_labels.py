"""Tests for draw.io label parsing."""

from __future__ import annotations

import base64
import urllib.parse
import zlib
from typing import TYPE_CHECKING

from drawio2tikz.drawio import parse_label, parse_labels

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


def _compress_diagram(xml_text: str) -> str:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    payload = urllib.parse.quote(xml_text, safe="").encode()
    compressed = compressor.compress(payload) + compressor.flush()
    return base64.b64encode(compressed).decode()
