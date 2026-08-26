"""Parse and handle labels from draw.io diagrams."""

from __future__ import annotations

import base64
import binascii
import re
import urllib.parse
import xml.etree.ElementTree as ET  # nosec B405
import zlib
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from defusedxml import ElementTree as DefusedET

# The standard module supplies XML types only; untrusted parsing uses defusedxml.

if TYPE_CHECKING:
    from pathlib import Path

DRAWIO_PX_TO_TEX_PT = 0.75
MAX_DECOMPRESSED_DIAGRAM_BYTES = 20 * 1024 * 1024
BOLD_FONT_WEIGHT_MIN = 600
FONT_SIZE_RE = re.compile(r"font-size:\s*([0-9.]+)px", re.IGNORECASE)
CSS_COLOR_RE = re.compile(r"color:\s*([^;]+)", re.IGNORECASE)
RGB_COLOR_RE = re.compile(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[^)]+)?\)", re.IGNORECASE)
HEX_COLOR_RE = re.compile(r"#([0-9a-fA-F]{6})")
FONT_WEIGHT_RE = re.compile(r"font-weight:\s*([^;]+)", re.IGNORECASE)
DRAWIO_STYLE_FONT_SIZE_RE = re.compile(r"(?:^|;)fontSize=([0-9.]+)(?:;|$)")
TEX_MATH_SPAN_RE = re.compile(
    r"(\\\(.*?\\\)|\\\[.*?\\\]|\$\$.*?\$\$|(?<!\\)\$(?:\\.|[^$\\])+(?<!\\)\$)",
    re.DOTALL,
)
TEX_COMMAND_RE = re.compile(r"\\[a-zA-Z]+")

TEX_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
}


@dataclass(frozen=True)
class LabelLine:
    """A single line of text in a label."""

    text: str
    font_size: float | None


@dataclass(frozen=True)
class Label:
    """A label extracted from a draw.io cell."""

    lines: list[LabelLine]
    font_size: float | None


@dataclass
class TextStyle:
    """Text styling attributes."""

    bold: bool = False
    color: str | None = None
    font_size: float | None = None


@dataclass
class TextRun:
    """A run of text with associated styling."""

    text: str
    bold: bool = False
    color: str | None = None
    font_size: float | None = None


class DrawioLabelParser(HTMLParser):
    """Parse HTML labels from draw.io cells into TeX-compatible text."""

    def __init__(self) -> None:
        """Initialize the parser."""
        super().__init__(convert_charrefs=True)
        self.lines: list[list[TextRun]] = [[]]
        self.stack: list[TextStyle] = [TextStyle()]
        self.pushed_tags: list[str] = []

    @property
    def current_style(self) -> TextStyle:
        """Get the current text style."""
        return self.stack[-1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle start of HTML tags."""
        tag = tag.lower()
        if tag in {"div", "p"}:
            self._newline()
            self._push_style(tag, attrs)
        elif tag == "br":
            self._newline()
        elif tag in {"b", "strong"}:
            self._push_style(tag, attrs, force_bold=True)
        elif tag in {"font", "span", "i", "em", "u"}:
            self._push_style(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        """Handle end of HTML tags."""
        tag = tag.lower()
        if tag in {"div", "p", "b", "strong", "font", "span", "i", "em", "u"}:
            self._pop_style(tag)

    def handle_data(self, data: str) -> None:
        """Handle text data."""
        text = data.replace("\xa0", " ")
        if not text:
            return
        style = self.current_style
        self.lines[-1].append(
            TextRun(
                text=text,
                bold=style.bold,
                color=style.color,
                font_size=style.font_size,
            ),
        )

    def _newline(self) -> None:
        if self.lines[-1]:
            self.lines.append([])

    def _push_style(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        force_bold: bool = False,
    ) -> None:
        style = TextStyle(**self.current_style.__dict__)
        parsed = _style_from_attrs(attrs)
        style.color = parsed.color or style.color
        style.font_size = parsed.font_size or style.font_size
        style.bold = style.bold or parsed.bold or force_bold
        self.stack.append(style)
        self.pushed_tags.append(tag)

    def _pop_style(self, tag: str) -> None:
        if tag not in self.pushed_tags:
            return
        index = len(self.pushed_tags) - 1 - self.pushed_tags[::-1].index(tag)
        del self.pushed_tags[index]
        del self.stack[index + 1]


def parse_labels(path: Path) -> dict[str, Label]:
    """Parse all labels from a draw.io file."""
    root = DefusedET.parse(path).getroot()
    if root is None:
        msg = "XML document has no root element"
        raise ET.ParseError(msg)
    labels: dict[str, Label] = {}

    _collect_labels(root, labels)
    for diagram_root in _diagram_roots(root):
        _collect_labels(diagram_root, labels)

    return labels


def _collect_labels(root: ET.Element, labels: dict[str, Label]) -> None:
    for cell in root.findall(".//mxCell"):
        _add_label(labels, cell.get("id"), cell.get("value"), cell.get("style"))

    for obj in root.findall(".//object"):
        _add_label(labels, obj.get("id"), obj.get("label"), _object_style(obj))


def _add_label(
    labels: dict[str, Label],
    cell_id: str | None,
    value: str | None,
    style: str | None,
) -> None:
    if not cell_id or not value:
        return

    label = parse_label(value, default_font_size=_drawio_style_font_size(style))
    if label.lines:
        labels[cell_id] = label


def _object_style(obj: ET.Element) -> str | None:
    cell = obj.find("mxCell")
    return cell.get("style") if cell is not None else None


def _drawio_style_font_size(style: str | None) -> float | None:
    if not style:
        return None
    if match := DRAWIO_STYLE_FONT_SIZE_RE.search(style):
        return float(match.group(1))
    return None


def _diagram_roots(root: ET.Element) -> list[ET.Element]:
    roots: list[ET.Element] = []
    for diagram in root.findall("diagram"):
        text = (diagram.text or "").strip()
        if not text:
            continue
        diagram_root = _diagram_root_from_text(text)
        if diagram_root is not None:
            roots.append(diagram_root)
    return roots


def _diagram_root_from_text(text: str) -> ET.Element | None:
    xml_text = _decompress_diagram_text(text) if not text.startswith("<") else text
    if not xml_text:
        return None
    try:
        return DefusedET.fromstring(xml_text)
    except ET.ParseError:
        return None


def _decompress_diagram_text(text: str) -> str | None:
    encoded = "".join(text.split())
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except binascii.Error, ValueError:
        return None

    for window_bits in (-zlib.MAX_WBITS, zlib.MAX_WBITS):
        try:
            decompressor = zlib.decompressobj(window_bits)
            inflated = decompressor.decompress(
                compressed,
                MAX_DECOMPRESSED_DIAGRAM_BYTES + 1,
            )
            if len(inflated) > MAX_DECOMPRESSED_DIAGRAM_BYTES or decompressor.unconsumed_tail:
                return None
            inflated += decompressor.flush(
                MAX_DECOMPRESSED_DIAGRAM_BYTES + 1 - len(inflated),
            )
        except zlib.error:
            continue
        if len(inflated) > MAX_DECOMPRESSED_DIAGRAM_BYTES or not decompressor.eof:
            return None
        try:
            return urllib.parse.unquote(inflated.decode("utf-8"))
        except UnicodeDecodeError:
            return None
    return None


def count_pages(path: Path) -> int:
    """Count the number of pages in a draw.io file."""
    root = DefusedET.parse(path).getroot()
    if root is None:
        msg = "XML document has no root element"
        raise ET.ParseError(msg)
    return len(root.findall("diagram"))


def drawio_stem(path: Path) -> str:
    """Extract the stem of a draw.io file name."""
    name = path.name
    if name.endswith(".drawio.png"):
        return name[: -len(".drawio.png")]
    if name.endswith(".drawio"):
        return name[: -len(".drawio")]
    return path.stem


def parse_label(value: str, default_font_size: float | None = None) -> Label:
    """Parse a single label from HTML string."""
    parser = DrawioLabelParser()
    if default_font_size:
        parser.current_style.font_size = default_font_size
    parser.feed(value)

    lines: list[LabelLine] = []
    font_sizes: list[float] = []

    for raw_runs in parser.lines:
        runs = _trim_edge_whitespace(raw_runs)
        line_font_sizes = [run.font_size for run in runs if run.font_size]
        font_sizes.extend(line_font_sizes)
        line_text = _text_from_runs(runs)
        if line_text:
            first_font = line_font_sizes[0] if line_font_sizes else None
            if first_font:
                line_text = with_tex_font_size(line_text, first_font)
            lines.append(LabelLine(text=line_text, font_size=first_font))

    if not lines:
        return Label(lines=[], font_size=None)

    label_font_size = font_sizes[0] if font_sizes else None
    return Label(lines=lines, font_size=label_font_size)


def _text_from_runs(runs: list[TextRun]) -> str:
    common_style = _common_style(runs)
    parts: list[str] = []
    for run in runs:
        text = _escape_tex_text(run.text)
        if run.bold and not common_style.bold:
            text = rf"\textbf{{{text}}}"
        if run.color and run.color != common_style.color:
            text = rf"\textcolor[HTML]{{{run.color}}}{{{text}}}"
        parts.append(text)

    text = "".join(parts)
    if common_style.bold:
        text = rf"\textbf{{{text}}}"
    if common_style.color:
        text = rf"\textcolor[HTML]{{{common_style.color}}}{{{text}}}"
    return text


def _escape_tex_text(text: str) -> str:
    """Escape TeX text while preserving raw TeX syntax (math spans and macro calls)."""
    parts: list[str] = []
    offset = 0
    for start, end in _raw_tex_spans(text):
        parts.append(_escape_tex_plain_text(text[offset:start]))
        parts.append(_normalize_tex_math_span(text[start:end]))
        offset = end
    parts.append(_escape_tex_plain_text(text[offset:]))
    return "".join(parts)


def _raw_tex_spans(text: str) -> list[tuple[int, int]]:
    r"""Find spans of literal TeX syntax (math spans, `\command{...}` calls) to leave untouched."""
    spans: list[tuple[int, int]] = []
    pos = 0
    length = len(text)
    while pos < length:
        math_match = TEX_MATH_SPAN_RE.search(text, pos)
        command_match = TEX_COMMAND_RE.search(text, pos)
        candidates = [match for match in (math_match, command_match) if match is not None]
        if not candidates:
            break
        match = min(
            candidates, key=lambda candidate: (candidate.start(), candidate is command_match)
        )
        end = match.end()
        if match is command_match:
            end = _tex_command_args_end(text, end)
        spans.append((match.start(), end))
        pos = end
    return spans


def _tex_command_args_end(text: str, pos: int) -> int:
    """Extend past any brace-delimited argument groups immediately following a TeX command."""
    length = len(text)
    while pos < length and text[pos] == "{":
        depth = 0
        index = pos
        while index < length:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    index += 1
                    break
            index += 1
        else:
            break  # unbalanced braces; stop extending
        pos = index
    return pos


def _normalize_tex_math_span(text: str) -> str:
    """Normalize dollar-delimited math for safe use inside TikZ text nodes."""
    if text.startswith("$$") and text.endswith("$$"):
        return rf"\({text[2:-2]}\)"
    if text.startswith("$") and text.endswith("$"):
        return rf"\({text[1:-1]}\)"
    return text


def _escape_tex_plain_text(text: str) -> str:
    for char, replacement in TEX_SPECIALS.items():
        text = text.replace(char, replacement)
    return text


def _common_style(runs: list[TextRun]) -> TextStyle:
    if not runs:
        return TextStyle()

    color = runs[0].color
    return TextStyle(
        bold=all(run.bold for run in runs),
        color=color if color and all(run.color == color for run in runs) else None,
    )


def _trim_edge_whitespace(runs: list[TextRun]) -> list[TextRun]:
    trimmed = [run for run in runs if run.text]
    if not trimmed:
        return []

    first = trimmed[0]
    last = trimmed[-1]
    trimmed[0] = replace(first, text=first.text.lstrip())
    trimmed[-1] = replace(last, text=last.text.rstrip())
    return [run for run in trimmed if run.text]


def with_tex_font_size(text: str, font_size_px: float) -> str:
    """Wrap TeX text in a font-size command converted from draw.io pixels."""
    size_pt = font_size_px * DRAWIO_PX_TO_TEX_PT
    leading_pt = size_pt * 1.2
    return rf"\fontsize{{{size_pt:.1f}pt}}{{{leading_pt:.1f}pt}}\selectfont {text}"


def _style_from_attrs(attrs: list[tuple[str, str | None]]) -> TextStyle:
    style = TextStyle()
    attrs_dict = dict(attrs)
    if "style" in attrs_dict:
        css = attrs_dict["style"] or ""
        if match := FONT_SIZE_RE.search(css):
            style.font_size = float(match.group(1))
        if match := CSS_COLOR_RE.search(css):
            color_str = match.group(1).strip()
            if color_match := RGB_COLOR_RE.search(color_str):
                r, g, b = color_match.groups()
                style.color = f"{int(r):02X}{int(g):02X}{int(b):02X}"
            elif hex_match := HEX_COLOR_RE.search(color_str):
                style.color = hex_match.group(1).upper()
        if match := FONT_WEIGHT_RE.search(css):
            style.bold = _is_bold_weight(match.group(1).strip())
    if "color" in attrs_dict and (hex_match := HEX_COLOR_RE.search(attrs_dict["color"] or "")):
        style.color = hex_match.group(1).upper()
    if "weight" in attrs_dict and _is_bold_weight(attrs_dict["weight"] or ""):
        style.bold = True
    return style


def _is_bold_weight(value: str) -> bool:
    value = value.lower()
    if value in {"bold", "bolder"}:
        return True
    try:
        return int(value) >= BOLD_FONT_WEIGHT_MIN
    except ValueError:
        return False
