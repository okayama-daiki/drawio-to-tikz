"""Convert sanitized draw.io SVG into standalone TikZ paths."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from defusedxml import ElementTree as DefusedET

if TYPE_CHECKING:
    from collections.abc import Iterable
    from xml.etree.ElementTree import Element

type Point = tuple[float, float]

NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
PATH_TOKEN_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
TRANSFORM_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
KAPPA = 4 * (math.sqrt(2) - 1) / 3
MIN_POLY_POINTS = 2
RGB_CHANNEL_COUNT = 3
RGB_HEX_LENGTH = 6
SHORT_RGB_HEX_LENGTH = 3
SVG_MATRIX_VALUE_COUNT = 6
SVG_ROTATE_CENTER_VALUE_COUNT = 3
SVG_VIEWBOX_VALUE_COUNT = 4
UNIT_FACTORS = {
    "px": 1.0,
    "pt": 72.0 / 96.0,
    "in": 1.0 / 96.0,
    "cm": 2.54 / 96.0,
    "mm": 25.4 / 96.0,
}
STANDARD_COLORS = {
    "black",
    "blue",
    "brown",
    "cyan",
    "darkgray",
    "gray",
    "green",
    "lightgray",
    "lime",
    "magenta",
    "olive",
    "orange",
    "pink",
    "purple",
    "red",
    "teal",
    "violet",
    "white",
    "yellow",
}
STANDARD_RGB_COLORS = {
    (0, 0, 0): "black",
    (0, 0, 255): "blue",
    (0, 128, 0): "green",
    (0, 255, 255): "cyan",
    (128, 128, 128): "gray",
    (255, 0, 0): "red",
    (255, 0, 255): "magenta",
    (255, 255, 0): "yellow",
    (255, 255, 255): "white",
}
STYLE_ATTRIBUTES = {
    "fill",
    "fill-opacity",
    "fill-rule",
    "font-size",
    "font-style",
    "font-weight",
    "opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "stroke-width",
    "visibility",
}
SKIPPED_CONTAINERS = {"defs", "metadata", "style", "switch", "title", "desc"}


@dataclass(frozen=True)
class Matrix:
    """SVG affine transformation matrix."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, point: Point) -> Point:
        """Transform a point."""
        x, y = point
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def then(self, local: Matrix) -> Matrix:
        """Compose this parent transform with a local transform."""
        return Matrix(
            a=self.a * local.a + self.c * local.b,
            b=self.b * local.a + self.d * local.b,
            c=self.a * local.c + self.c * local.d,
            d=self.b * local.c + self.d * local.d,
            e=self.a * local.e + self.c * local.f + self.e,
            f=self.b * local.e + self.d * local.f + self.f,
        )

    @property
    def stroke_scale(self) -> float:
        """Return a stable scalar approximation for transformed stroke widths."""
        return math.sqrt(abs(self.a * self.d - self.b * self.c))


@dataclass(frozen=True)
class Style:
    """Inherited SVG presentation properties."""

    fill: str = "black"
    stroke: str = "none"
    stroke_width: float = 1.0
    fill_opacity: float = 1.0
    stroke_opacity: float = 1.0
    opacity: float = 1.0
    dasharray: str = "none"
    linecap: str = "butt"
    linejoin: str = "miter"
    miterlimit: float = 4.0
    fill_rule: str = "nonzero"
    visibility: str = "visible"
    font_size: float | None = None
    font_style: str = "normal"
    font_weight: str = "normal"


@dataclass(frozen=True)
class Canvas:
    """SVG viewport mapped to a TikZ unit."""

    min_x: float
    min_y: float
    width: float
    height: float
    unit: str
    factor: float
    digits: int

    def map(self, point: Point) -> Point:
        """Convert SVG coordinates to TikZ coordinates and invert the Y axis."""
        x, y = point
        return (
            (x - self.min_x) * self.factor,
            (self.min_y + self.height - y) * self.factor,
        )

    def number(self, value: float) -> str:
        """Format a finite TikZ number deterministically."""
        rounded = round(value, self.digits)
        if math.isclose(rounded, 0.0, abs_tol=10 ** (-(self.digits + 1))):
            rounded = 0.0
        rendered = f"{rounded:.{self.digits}f}".rstrip("0").rstrip(".")
        return rendered or "0"

    def point(self, point: Point) -> str:
        """Format a mapped coordinate."""
        x, y = self.map(point)
        return f"({self.number(x)}, {self.number(y)})"


class ColorRegistry:
    """Collect non-standard SVG colors for xcolor declarations."""

    def __init__(self) -> None:
        """Initialize an empty color map."""
        self._colors: dict[str, tuple[int, int, int]] = {}

    def resolve(self, raw_color: str) -> str:
        """Return a TikZ color name and register custom RGB colors."""
        color = raw_color.strip().lower()
        if color in STANDARD_COLORS:
            return color
        if color == "grey":
            return "gray"
        rgb = _parse_color(color)
        if rgb is None:
            return "black"
        if standard_name := STANDARD_RGB_COLORS.get(rgb):
            return standard_name
        red, green, blue = rgb
        name = f"c{red:02x}{green:02x}{blue:02x}"
        self._colors[name] = rgb
        return name

    def declarations(self) -> str:
        """Render deterministic xcolor definitions."""
        return "\n".join(
            f"\\definecolor{{{name}}}{{RGB}}{{{red},{green},{blue}}}"
            for name, (red, green, blue) in sorted(self._colors.items())
        )


class TikzRenderer:
    """Render a sanitized SVG element tree as TikZ."""

    def __init__(
        self,
        canvas: Canvas,
        *,
        scale: float,
        texmode: str,
    ) -> None:
        """Initialize a renderer for one SVG viewport."""
        self.canvas = canvas
        self.scale = scale
        self.texmode = texmode
        self.colors = ColorRegistry()
        self.lines: list[str] = []
        self._text_serial = 0
        self._unsupported: set[str] = set()

    def render(self, root: Element) -> str:
        """Render the complete TikZ picture."""
        self._visit(root, Matrix(), Style())
        colors = self.colors.declarations()
        color_block = f"{colors}\n\n" if colors else ""
        unsupported = "".join(
            f"  % Unsupported SVG element <{name}> omitted.\n" for name in sorted(self._unsupported)
        )
        body = "\n\n".join(f"  {line}" for line in self.lines)
        if body:
            body = f"{body}\n"
        return (
            f"{color_block}"
            f"\\def \\globalscale {{{self.scale:.6f}}}\n"
            f"\\begin{{tikzpicture}}[y=1{self.canvas.unit}, x=1{self.canvas.unit}, "
            "yscale=\\globalscale, xscale=\\globalscale, "
            "every node/.append style={scale=\\globalscale}, "
            "inner sep=0pt, outer sep=0pt]\n"
            f"{unsupported}{body}"
            "\\end{tikzpicture}\n"
        )

    def _visit(self, element: Element, transform: Matrix, inherited: Style) -> None:
        tag = _local_name(element.tag)
        if tag in SKIPPED_CONTAINERS:
            return
        if element.get("display", "").strip().lower() == "none":
            return

        local_transform = transform.then(_parse_transform(element.get("transform", "")))
        style = _merge_style(inherited, element)
        if style.visibility in {"hidden", "collapse"}:
            return

        if tag in {"svg", "g", "a"}:
            for child in element:
                self._visit(child, local_transform, style)
            return

        renderer = getattr(self, f"_render_{tag}", None)
        if renderer is None:
            self._unsupported.add(tag)
            return
        renderer(element, local_transform, style)

    def _render_path(self, element: Element, transform: Matrix, style: Style) -> None:
        data = element.get("d", "").strip()
        if not data:
            return
        path = _render_path_data(data, transform, self.canvas)
        self._append_path(path, style, transform)

    def _render_rect(self, element: Element, transform: Matrix, style: Style) -> None:
        x = _float_attr(element, "x", 0.0)
        y = _float_attr(element, "y", 0.0)
        width = _float_attr(element, "width", 0.0)
        height = _float_attr(element, "height", 0.0)
        if width <= 0 or height <= 0:
            return
        rx = min(abs(_float_attr(element, "rx", 0.0)), width / 2)
        ry_raw = _float_attr(element, "ry", rx)
        ry = min(abs(ry_raw), height / 2)
        commands = _rounded_rect_commands(x, y, width, height, rx=rx, ry=ry)
        self._append_path(_render_commands(commands, transform, self.canvas), style, transform)

    def _render_circle(self, element: Element, transform: Matrix, style: Style) -> None:
        radius = _float_attr(element, "r", 0.0)
        self._render_ellipse_values(
            _float_attr(element, "cx", 0.0),
            _float_attr(element, "cy", 0.0),
            radius,
            radius,
            transform=transform,
            style=style,
        )

    def _render_ellipse(self, element: Element, transform: Matrix, style: Style) -> None:
        self._render_ellipse_values(
            _float_attr(element, "cx", 0.0),
            _float_attr(element, "cy", 0.0),
            _float_attr(element, "rx", 0.0),
            _float_attr(element, "ry", 0.0),
            transform=transform,
            style=style,
        )

    def _render_ellipse_values(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        *,
        transform: Matrix,
        style: Style,
    ) -> None:
        if rx <= 0 or ry <= 0:
            return
        commands = _ellipse_commands(cx, cy, rx, ry)
        self._append_path(_render_commands(commands, transform, self.canvas), style, transform)

    def _render_line(self, element: Element, transform: Matrix, style: Style) -> None:
        start = (_float_attr(element, "x1", 0.0), _float_attr(element, "y1", 0.0))
        end = (_float_attr(element, "x2", 0.0), _float_attr(element, "y2", 0.0))
        path = _render_commands([("M", (start,)), ("L", (end,))], transform, self.canvas)
        self._append_path(path, replace(style, fill="none"), transform)

    def _render_polyline(self, element: Element, transform: Matrix, style: Style) -> None:
        self._render_points(element, transform, style, close=False)

    def _render_polygon(self, element: Element, transform: Matrix, style: Style) -> None:
        self._render_points(element, transform, style, close=True)

    def _render_points(
        self,
        element: Element,
        transform: Matrix,
        style: Style,
        *,
        close: bool,
    ) -> None:
        values = [float(value) for value in NUMBER_RE.findall(element.get("points", ""))]
        points = list(zip(values[::2], values[1::2], strict=False))
        if len(points) < MIN_POLY_POINTS:
            return
        commands: list[tuple[str, tuple[Point, ...]]] = [("M", (points[0],))]
        commands.extend(("L", (point,)) for point in points[1:])
        if close:
            commands.append(("Z", ()))
        self._append_path(_render_commands(commands, transform, self.canvas), style, transform)

    def _render_text(self, element: Element, transform: Matrix, style: Style) -> None:
        content = "".join(element.itertext())
        if not content:
            return
        x_values = NUMBER_RE.findall(element.get("x", "0"))
        y_values = NUMBER_RE.findall(element.get("y", "0"))
        point = (float(x_values[0]), float(y_values[0]))
        mapped = self.canvas.map(transform.apply(point))
        anchor = _text_anchor(element)
        node_id = _safe_node_id(element.get("id"), self._text_serial)
        self._text_serial += 1
        text = _text_content(content, self.texmode)
        angle = math.degrees(math.atan2(-transform.b, transform.a))
        options = [f"anchor={anchor}"]
        if style.fill.lower() != "none":
            text_color = self.colors.resolve(style.fill)
            text_opacity = max(0.0, min(1.0, style.fill_opacity * style.opacity))
            if text_color != "black" or not math.isclose(text_opacity, 1.0):
                options.append(f"text={text_color}")
            if not math.isclose(text_opacity, 1.0):
                options.append(f"text opacity={self.canvas.number(text_opacity)}")
        font_commands: list[str] = []
        if style.font_size is not None and r"\fontsize" not in content:
            font_size = style.font_size * transform.stroke_scale * UNIT_FACTORS["pt"]
            leading = font_size * 1.2
            font_commands.append(
                f"\\fontsize{{{self.canvas.number(font_size)}pt}}"
                f"{{{self.canvas.number(leading)}pt}}\\selectfont"
            )
        if style.font_weight.lower() in {"bold", "bolder", "500", "600", "700", "800", "900"}:
            font_commands.append(r"\bfseries")
        if style.font_style.lower() in {"italic", "oblique"}:
            font_commands.append(r"\itshape")
        if font_commands:
            options.append(f"font={{{''.join(font_commands)}}}")
        if not math.isclose(angle, 0.0, abs_tol=1e-9):
            options.append(f"rotate={self.canvas.number(angle)}")
        location = f"({self.canvas.number(mapped[0])}, {self.canvas.number(mapped[1])})"
        self.lines.append(
            f"\\node[{','.join(options)}] ({node_id}) at {location}{{{text}}};",
        )

    def _append_path(self, path: str, style: Style, transform: Matrix) -> None:
        options = _style_options(style, transform, self.canvas, self.colors)
        if not options:
            return
        self.lines.append(f"\\path[{','.join(options)}] {path};")


def convert_svg_to_tikz(
    svg_source: str,
    *,
    output_unit: str = "pt",
    scale: float = 1.0,
    round_number: int = 3,
    texmode: str = "raw",
) -> str:
    """Convert sanitized SVG source into a TikZ picture."""
    if output_unit not in UNIT_FACTORS:
        supported = ", ".join(UNIT_FACTORS)
        msg = f"Unsupported output unit {output_unit!r}; choose one of: {supported}."
        raise ValueError(msg)
    if scale <= 0:
        msg = "Scale must be greater than zero."
        raise ValueError(msg)
    if round_number < 0:
        msg = "Coordinate precision must be non-negative."
        raise ValueError(msg)

    root = DefusedET.fromstring(svg_source)
    if _local_name(root.tag) != "svg":
        msg = "Expected an SVG document root."
        raise ValueError(msg)
    min_x, min_y, width, height = _viewport(root)
    canvas = Canvas(
        min_x=min_x,
        min_y=min_y,
        width=width,
        height=height,
        unit=output_unit,
        factor=UNIT_FACTORS[output_unit],
        digits=round_number,
    )
    return TikzRenderer(canvas, scale=scale, texmode=texmode).render(root)


def _viewport(root: Element) -> tuple[float, float, float, float]:
    view_box = [float(value) for value in NUMBER_RE.findall(root.get("viewBox", ""))]
    if len(view_box) == SVG_VIEWBOX_VALUE_COUNT:
        min_x, min_y, width, height = view_box
    else:
        min_x = min_y = 0.0
        width = _length_px(root.get("width", ""))
        height = _length_px(root.get("height", ""))
    if width <= 0 or height <= 0:
        msg = "SVG width and height must be positive."
        raise ValueError(msg)
    return min_x, min_y, width, height


def _length_px(raw_value: str) -> float:
    match = NUMBER_RE.match(raw_value.strip())
    if match is None:
        return 0.0
    value = float(match.group())
    suffix = raw_value[match.end() :].strip().lower()
    factors = {"": 1.0, "px": 1.0, "pt": 96 / 72, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4}
    return value * factors.get(suffix, 1.0)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _float_attr(element: Element, name: str, default: float) -> float:
    raw = element.get(name)
    if raw is None:
        return default
    match = NUMBER_RE.match(raw.strip())
    return float(match.group()) if match else default


def _parse_transform(raw_transform: str) -> Matrix:
    matrix = Matrix()
    for name, raw_values in TRANSFORM_RE.findall(raw_transform):
        values = [float(value) for value in NUMBER_RE.findall(raw_values)]
        operation = _transform_operation(name.lower(), values)
        matrix = matrix.then(operation)
    return matrix


def _transform_operation(name: str, values: list[float]) -> Matrix:  # noqa: PLR0911
    if name == "matrix" and len(values) == SVG_MATRIX_VALUE_COUNT:
        return Matrix(*values)
    if name == "translate" and values:
        return Matrix(e=values[0], f=values[1] if len(values) > 1 else 0.0)
    if name == "scale" and values:
        return Matrix(a=values[0], d=values[1] if len(values) > 1 else values[0])
    if name == "rotate" and values:
        radians = math.radians(values[0])
        rotation = Matrix(
            a=math.cos(radians), b=math.sin(radians), c=-math.sin(radians), d=math.cos(radians)
        )
        if len(values) < SVG_ROTATE_CENTER_VALUE_COUNT:
            return rotation
        cx, cy = values[1:3]
        return Matrix(e=cx, f=cy).then(rotation).then(Matrix(e=-cx, f=-cy))
    if name == "skewx" and values:
        return Matrix(c=math.tan(math.radians(values[0])))
    if name == "skewy" and values:
        return Matrix(b=math.tan(math.radians(values[0])))
    return Matrix()


def _merge_style(inherited: Style, element: Element) -> Style:
    raw_style: dict[str, str] = {}
    style_attribute = element.get("style", "")
    for declaration in style_attribute.split(";"):
        if ":" in declaration:
            name, value = declaration.split(":", maxsplit=1)
            raw_style[name.strip().lower()] = value.strip()
    for name in STYLE_ATTRIBUTES:
        if value := element.get(name):
            raw_style[name] = value.strip()

    opacity = inherited.opacity * _number(raw_style.get("opacity"), 1.0)
    return Style(
        fill=raw_style.get("fill", inherited.fill),
        stroke=raw_style.get("stroke", inherited.stroke),
        stroke_width=_number(raw_style.get("stroke-width"), inherited.stroke_width),
        fill_opacity=_number(raw_style.get("fill-opacity"), inherited.fill_opacity),
        stroke_opacity=_number(raw_style.get("stroke-opacity"), inherited.stroke_opacity),
        opacity=opacity,
        dasharray=raw_style.get("stroke-dasharray", inherited.dasharray),
        linecap=raw_style.get("stroke-linecap", inherited.linecap),
        linejoin=raw_style.get("stroke-linejoin", inherited.linejoin),
        miterlimit=_number(raw_style.get("stroke-miterlimit"), inherited.miterlimit),
        fill_rule=raw_style.get("fill-rule", inherited.fill_rule),
        visibility=raw_style.get("visibility", inherited.visibility),
        font_size=(
            _number(raw_style["font-size"], inherited.font_size or 16.0)
            if "font-size" in raw_style
            else inherited.font_size
        ),
        font_style=raw_style.get("font-style", inherited.font_style),
        font_weight=raw_style.get("font-weight", inherited.font_weight),
    )


def _number(raw_value: str | None, default: float) -> float:
    if raw_value is None:
        return default
    match = NUMBER_RE.match(raw_value.strip())
    return float(match.group()) if match else default


def _style_options(  # noqa: C901
    style: Style,
    transform: Matrix,
    canvas: Canvas,
    colors: ColorRegistry,
) -> list[str]:
    options: list[str] = []
    if style.stroke.lower() != "none":
        options.append(f"draw={colors.resolve(style.stroke)}")
        width = style.stroke_width * transform.stroke_scale * canvas.factor
        options.append(f"line width={canvas.number(width)}{canvas.unit}")
        stroke_opacity = max(0.0, min(1.0, style.stroke_opacity * style.opacity))
        if not math.isclose(stroke_opacity, 1.0):
            options.append(f"draw opacity={canvas.number(stroke_opacity)}")
        if style.linecap in {"round", "square"}:
            options.append(f"line cap={style.linecap}")
        if style.linejoin in {"round", "bevel"}:
            options.append(f"line join={style.linejoin}")
        if style.linejoin == "miter":
            options.append(f"miter limit={canvas.number(style.miterlimit)}")
        dash_values = [float(value) for value in NUMBER_RE.findall(style.dasharray)]
        if dash_values:
            scaled = [value * transform.stroke_scale * canvas.factor for value in dash_values]
            pairs: list[str] = []
            for index, value in enumerate(scaled):
                state = "on" if index % 2 == 0 else "off"
                pairs.append(f"{state} {canvas.number(value)}{canvas.unit}")
            options.append(f"dash pattern={' '.join(pairs)}")
    if style.fill.lower() != "none":
        options.append(f"fill={colors.resolve(style.fill)}")
        fill_opacity = max(0.0, min(1.0, style.fill_opacity * style.opacity))
        if not math.isclose(fill_opacity, 1.0):
            options.append(f"fill opacity={canvas.number(fill_opacity)}")
        if style.fill_rule == "evenodd":
            options.append("even odd rule")
    return options


def _parse_color(color: str) -> tuple[int, int, int] | None:
    if color.startswith("#"):
        value = color[1:]
        if len(value) == SHORT_RGB_HEX_LENGTH:
            value = "".join(character * 2 for character in value)
        if len(value) == RGB_HEX_LENGTH and all(
            character in "0123456789abcdef" for character in value
        ):
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    if color.startswith("rgb"):
        values = NUMBER_RE.findall(color)
        if len(values) >= RGB_CHANNEL_COUNT:
            red, green, blue = (
                max(0, min(255, round(float(value)))) for value in values[:RGB_CHANNEL_COUNT]
            )
            return red, green, blue
    return None


def _rounded_rect_commands(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    rx: float,
    ry: float,
) -> list[tuple[str, tuple[Point, ...]]]:
    if rx == 0 or ry == 0:
        return [
            ("M", ((x, y),)),
            ("L", ((x + width, y),)),
            ("L", ((x + width, y + height),)),
            ("L", ((x, y + height),)),
            ("Z", ()),
        ]
    return [
        ("M", ((x + rx, y),)),
        ("L", ((x + width - rx, y),)),
        (
            "C",
            (
                (x + width - rx + KAPPA * rx, y),
                (x + width, y + ry - KAPPA * ry),
                (x + width, y + ry),
            ),
        ),
        ("L", ((x + width, y + height - ry),)),
        (
            "C",
            (
                (x + width, y + height - ry + KAPPA * ry),
                (x + width - rx + KAPPA * rx, y + height),
                (x + width - rx, y + height),
            ),
        ),
        ("L", ((x + rx, y + height),)),
        (
            "C",
            (
                (x + rx - KAPPA * rx, y + height),
                (x, y + height - ry + KAPPA * ry),
                (x, y + height - ry),
            ),
        ),
        ("L", ((x, y + ry),)),
        ("C", ((x, y + ry - KAPPA * ry), (x + rx - KAPPA * rx, y), (x + rx, y))),
        ("Z", ()),
    ]


def _ellipse_commands(
    cx: float, cy: float, rx: float, ry: float
) -> list[tuple[str, tuple[Point, ...]]]:
    return [
        ("M", ((cx + rx, cy),)),
        ("C", ((cx + rx, cy + KAPPA * ry), (cx + KAPPA * rx, cy + ry), (cx, cy + ry))),
        ("C", ((cx - KAPPA * rx, cy + ry), (cx - rx, cy + KAPPA * ry), (cx - rx, cy))),
        ("C", ((cx - rx, cy - KAPPA * ry), (cx - KAPPA * rx, cy - ry), (cx, cy - ry))),
        ("C", ((cx + KAPPA * rx, cy - ry), (cx + rx, cy - KAPPA * ry), (cx + rx, cy))),
        ("Z", ()),
    ]


def _render_commands(
    commands: Iterable[tuple[str, tuple[Point, ...]]],
    transform: Matrix,
    canvas: Canvas,
) -> str:
    pieces: list[str] = []
    for command, points in commands:
        mapped = [canvas.point(transform.apply(point)) for point in points]
        if command == "M":
            pieces.append(mapped[0])
        elif command == "L":
            pieces.append(f"-- {mapped[0]}")
        elif command == "C":
            pieces.append(f".. controls {mapped[0]} and {mapped[1]} .. {mapped[2]}")
        elif command == "Z":
            pieces.append("-- cycle")
    return " ".join(pieces)


def _render_path_data(data: str, transform: Matrix, canvas: Canvas) -> str:
    commands = _parse_path(data)
    return _render_commands(commands, transform, canvas)


def _parse_path(  # noqa: C901, PLR0912, PLR0915
    data: str,
) -> list[tuple[str, tuple[Point, ...]]]:
    tokens = PATH_TOKEN_RE.findall(data.replace(",", " "))
    commands: list[tuple[str, tuple[Point, ...]]] = []
    index = 0
    active = ""
    current = (0.0, 0.0)
    subpath_start = current
    last_cubic: Point | None = None
    last_quadratic: Point | None = None

    parameter_counts = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            active = token
            index += 1
            if active.upper() == "Z":
                commands.append(("Z", ()))
                current = subpath_start
                last_cubic = last_quadratic = None
                active = ""
            continue
        if not active:
            msg = "SVG path data starts without a command."
            raise ValueError(msg)
        upper = active.upper()
        count = parameter_counts[upper]
        if index + count > len(tokens):
            msg = f"SVG path command {active} has incomplete parameters."
            raise ValueError(msg)
        values = [float(value) for value in tokens[index : index + count]]
        index += count
        relative = active.islower()

        if upper == "M":
            current = _path_point(values, 0, current, relative=relative)
            subpath_start = current
            commands.append(("M", (current,)))
            active = "l" if relative else "L"
        elif upper == "L":
            current = _path_point(values, 0, current, relative=relative)
            commands.append(("L", (current,)))
        elif upper == "H":
            x = current[0] + values[0] if relative else values[0]
            current = (x, current[1])
            commands.append(("L", (current,)))
        elif upper == "V":
            y = current[1] + values[0] if relative else values[0]
            current = (current[0], y)
            commands.append(("L", (current,)))
        elif upper == "C":
            first = _path_point(values, 0, current, relative=relative)
            second = _path_point(values, 2, current, relative=relative)
            current = _path_point(values, 4, current, relative=relative)
            commands.append(("C", (first, second, current)))
            last_cubic = second
        elif upper == "S":
            first = _reflect(last_cubic, current) if last_cubic is not None else current
            second = _path_point(values, 0, current, relative=relative)
            current = _path_point(values, 2, current, relative=relative)
            commands.append(("C", (first, second, current)))
            last_cubic = second
        elif upper == "Q":
            control = _path_point(values, 0, current, relative=relative)
            end = _path_point(values, 2, current, relative=relative)
            commands.append(("C", _quadratic_to_cubic(current, control, end)))
            current = end
            last_quadratic = control
        elif upper == "T":
            control = _reflect(last_quadratic, current) if last_quadratic is not None else current
            end = _path_point(values, 0, current, relative=relative)
            commands.append(("C", _quadratic_to_cubic(current, control, end)))
            current = end
            last_quadratic = control
        elif upper == "A":
            end = _path_point(values, 5, current, relative=relative)
            commands.extend(
                ("C", points)
                for points in _arc_to_cubics(
                    current,
                    end,
                    rx=abs(values[0]),
                    ry=abs(values[1]),
                    rotation=values[2],
                    large_arc=bool(values[3]),
                    sweep=bool(values[4]),
                )
            )
            current = end

        if upper not in {"C", "S"}:
            last_cubic = None
        if upper not in {"Q", "T"}:
            last_quadratic = None
    return commands


def _arc_to_cubics(
    start: Point,
    end: Point,
    *,
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
) -> list[tuple[Point, Point, Point]]:
    if rx == 0 or ry == 0 or start == end:
        return [(start, end, end)]
    phi = math.radians(rotation % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    dx = (start[0] - end[0]) / 2
    dy = (start[1] - end[1]) / 2
    x_prime = cos_phi * dx + sin_phi * dy
    y_prime = -sin_phi * dx + cos_phi * dy
    radii_scale = x_prime**2 / rx**2 + y_prime**2 / ry**2
    if radii_scale > 1:
        factor = math.sqrt(radii_scale)
        rx *= factor
        ry *= factor
    numerator = max(0.0, rx**2 * ry**2 - rx**2 * y_prime**2 - ry**2 * x_prime**2)
    denominator = rx**2 * y_prime**2 + ry**2 * x_prime**2
    coefficient = 0.0 if denominator == 0 else math.sqrt(numerator / denominator)
    if large_arc == sweep:
        coefficient = -coefficient
    cx_prime = coefficient * (rx * y_prime / ry)
    cy_prime = coefficient * (-ry * x_prime / rx)
    cx = cos_phi * cx_prime - sin_phi * cy_prime + (start[0] + end[0]) / 2
    cy = sin_phi * cx_prime + cos_phi * cy_prime + (start[1] + end[1]) / 2

    theta = _vector_angle((1.0, 0.0), ((x_prime - cx_prime) / rx, (y_prime - cy_prime) / ry))
    delta = _vector_angle(
        ((x_prime - cx_prime) / rx, (y_prime - cy_prime) / ry),
        ((-x_prime - cx_prime) / rx, (-y_prime - cy_prime) / ry),
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    segments = max(1, math.ceil(abs(delta) / (math.pi / 2)))
    step = delta / segments
    curves: list[tuple[Point, Point, Point]] = []
    for segment in range(segments):
        start_angle = theta + segment * step
        end_angle = start_angle + step
        alpha = 4 / 3 * math.tan(step / 4)
        first_unit = (
            math.cos(start_angle) - alpha * math.sin(start_angle),
            math.sin(start_angle) + alpha * math.cos(start_angle),
        )
        second_unit = (
            math.cos(end_angle) + alpha * math.sin(end_angle),
            math.sin(end_angle) - alpha * math.cos(end_angle),
        )
        end_unit = (math.cos(end_angle), math.sin(end_angle))
        curves.append(
            (
                _ellipse_point(
                    first_unit, center=(cx, cy), radii=(rx, ry), cos_phi=cos_phi, sin_phi=sin_phi
                ),
                _ellipse_point(
                    second_unit, center=(cx, cy), radii=(rx, ry), cos_phi=cos_phi, sin_phi=sin_phi
                ),
                _ellipse_point(
                    end_unit, center=(cx, cy), radii=(rx, ry), cos_phi=cos_phi, sin_phi=sin_phi
                ),
            )
        )
    return curves


def _ellipse_point(
    point: Point,
    *,
    center: Point,
    radii: Point,
    cos_phi: float,
    sin_phi: float,
) -> Point:
    x, y = point
    cx, cy = center
    rx, ry = radii
    return (
        cx + rx * cos_phi * x - ry * sin_phi * y,
        cy + rx * sin_phi * x + ry * cos_phi * y,
    )


def _vector_angle(first: Point, second: Point) -> float:
    dot = first[0] * second[0] + first[1] * second[1]
    determinant = first[0] * second[1] - first[1] * second[0]
    return math.atan2(determinant, dot)


def _quadratic_to_cubic(start: Point, control: Point, end: Point) -> tuple[Point, Point, Point]:
    return (
        (start[0] + 2 / 3 * (control[0] - start[0]), start[1] + 2 / 3 * (control[1] - start[1])),
        (end[0] + 2 / 3 * (control[0] - end[0]), end[1] + 2 / 3 * (control[1] - end[1])),
        end,
    )


def _add_points(first: Point, second: Point) -> Point:
    return first[0] + second[0], first[1] + second[1]


def _path_point(values: list[float], offset: int, current: Point, *, relative: bool) -> Point:
    point = (values[offset], values[offset + 1])
    return _add_points(current, point) if relative else point


def _reflect(control: Point, around: Point) -> Point:
    return 2 * around[0] - control[0], 2 * around[1] - control[1]


def _text_anchor(element: Element) -> str:
    node_id = element.get("id", "")
    if node_id.startswith("drawio2tikzcenter"):
        return "center"
    return {
        "middle": "south",
        "end": "south east",
        "start": "south west",
    }.get(element.get("text-anchor", "start"), "south west")


def _safe_node_id(raw_id: str | None, serial: int) -> str:
    candidate = re.sub(r"[^A-Za-z0-9:_-]+", "-", raw_id or "").strip("-")
    return candidate or f"text{serial}"


def _text_content(content: str, texmode: str) -> str:
    if texmode == "raw":
        return content
    if texmode == "math":
        return f"${content}$"
    if texmode in {"escape", "attribute"}:
        replacements = {
            "\\": r"\textbackslash{}",
            "{": r"\{",
            "}": r"\}",
            "$": r"\$",
            "&": r"\&",
            "#": r"\#",
            "_": r"\_",
            "%": r"\%",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        return "".join(replacements.get(character, character) for character in content)
    msg = f"Unsupported TeX text mode: {texmode}."
    raise ValueError(msg)
