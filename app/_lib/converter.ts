import { DOMParser as XmldomParser } from "@xmldom/xmldom";

interface IDomParser {
  parseFromString(xml: string, mimeType: string): Document;
}

interface DrawioElement {
  id?: string;
  type:
    | "rect"
    | "circle"
    | "line"
    | "text"
    | "arrow"
    | "diamond"
    | "parallelogram"
    | "triangle";
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  text?: string;
  label?: string;
  style?: string;
  source?: string;
  target?: string;
  sourcePoint?: { x: number; y: number };
  targetPoint?: { x: number; y: number };
  controlPoints?: Array<{ x: number; y: number }>;
  strokeColor?: string;
  fillColor?: string;
  fontSize?: number;
  fontStyle?: string;
  startArrow?: string; // added arrow properties
  endArrow?: string;
  strokeStyle?: string;
  strokeWidth?: number; // add strokeWidth property
  math?: boolean; // added math flag for LaTeX support
}

export function parseDrawioXml(xml: string): DrawioElement[] {
  const elements: DrawioElement[] = [];
  const edgeMap = new Map<
    string,
    { source: string; target: string; style: string }
  >();

  try {
    const ParserCtor: new () => IDomParser =
      (globalThis as unknown as { DOMParser?: new () => IDomParser })
        .DOMParser ?? (XmldomParser as unknown as new () => IDomParser);
    const parser = new ParserCtor();
    const doc = parser.parseFromString(xml, "text/xml");

    const cells = Array.from(doc.getElementsByTagName("mxCell")) as Element[];

    cells.forEach((cell: Element) => {
      const id = cell.getAttribute("id") || "";
      const parent = cell.getAttribute("parent");
      const edge = cell.getAttribute("edge");
      const geometry = cell.getElementsByTagName("mxGeometry")[0] as
        | Element
        | undefined;

      if (!geometry) return;

      const x = Number.parseFloat(geometry.getAttribute("x") || "0");
      const y = Number.parseFloat(geometry.getAttribute("y") || "0");
      const width = Number.parseFloat(geometry.getAttribute("width") || "0");
      const height = Number.parseFloat(geometry.getAttribute("height") || "0");

      const style = cell.getAttribute("style") || "";
      const label = cell.getAttribute("value") || "";

      const isMath = style.includes("math=1") || label.includes("$");

      let type: DrawioElement["type"] = "rect";
      if (style.includes("ellipse")) type = "circle";
      else if (style.includes("rhombus") || style.includes("diamond"))
        type = "diamond";
      else if (style.includes("triangle")) type = "triangle";
      else if (style.includes("parallelogram")) type = "parallelogram";
      else if (
        style.includes("line") ||
        style.includes("connector") ||
        edge === "1"
      )
        type = "line";

      const strokeMatch = style.match(/strokeColor=([^;]+)/);
      const fillMatch = style.match(/fillColor=([^;]+)/);
      const fontSizeMatch = style.match(/fontSize=(\d+)/);
      const endArrowMatch = style.match(/endArrow=([^;]+)/);
      const startArrowMatch = style.match(/startArrow=([^;]+)/);
      const dashedMatch = style.match(/dashed=1/);
      const dashPatternMatch = style.match(/dashPattern=([^;]+)/);
      const strokeWidthMatch = style.match(/strokeWidth=(\d+(?:\.\d+)?)/); // parse strokeWidth

      const element: DrawioElement = {
        endArrow: endArrowMatch ? endArrowMatch[1] : undefined,
        fillColor: fillMatch ? fillMatch[1] : "#ffffff",
        fontSize: fontSizeMatch ? Number.parseInt(fontSizeMatch[1], 10) : 12,
        height,
        id,
        math: isMath,
        source: cell.getAttribute("source") || undefined,
        startArrow: startArrowMatch ? startArrowMatch[1] : undefined,
        strokeColor: strokeMatch ? strokeMatch[1] : "#000000",
        strokeStyle: dashedMatch
          ? "dashed"
          : dashPatternMatch
            ? dashPatternMatch[1]
            : "solid",
        strokeWidth: strokeWidthMatch
          ? Number.parseFloat(strokeWidthMatch[1])
          : 1, // store strokeWidth
        style,
        target: cell.getAttribute("target") || undefined,
        text: label,
        type,
        width,
        x,
        y,
      };

      if (edge === "1") {
        edgeMap.set(id, {
          source: cell.getAttribute("source") || "",
          style,
          target: cell.getAttribute("target") || "",
        });
      }

      if (parent !== "0") {
        elements.push(element);
      }
    });
  } catch (error) {
    console.error("XML parsing error:", error);
  }

  return elements;
}

function coordinatesToTikz(
  x: number,
  y: number,
  scale = 0.015,
  maxY = 0,
): string {
  const invertedY = maxY - y;
  return `(${(x * scale).toFixed(2)},${(invertedY * scale).toFixed(2)})`;
}

function hexToRgb(hex: string): string {
  const clean = hex.replace(/^#/, "").toUpperCase();

  // Handle 6-digit or 3-digit hex codes
  let r: number, g: number, b: number;

  if (clean.length === 6) {
    r = Number.parseInt(clean.substring(0, 2), 16) / 255;
    g = Number.parseInt(clean.substring(2, 4), 16) / 255;
    b = Number.parseInt(clean.substring(4, 6), 16) / 255;
  } else if (clean.length === 3) {
    r = Number.parseInt(clean[0] + clean[0], 16) / 255;
    g = Number.parseInt(clean[1] + clean[1], 16) / 255;
    b = Number.parseInt(clean[2] + clean[2], 16) / 255;
  } else {
    // Default to black if invalid format
    return "{rgb,1:red,0.000;green,0.000;blue,0.000}";
  }

  // xcolor expects the syntax {rgb,1:red,<r>;green,<g>;blue,<b>}
  return `{rgb,1:red,${r.toFixed(3)};green,${g.toFixed(3)};blue,${b.toFixed(3)}}`;
}

/**
 * @deprecated Currently unused; kept for future styling enhancements.
 */
// UNUSED helper retained for future styling; prefixed with _ to silence lint.
function _styleToTikzOptions(element: DrawioElement): string {
  // Deprecated: currently not used; logic retained for potential future styling.
  const options: string[] = [];
  if (element.fillColor && element.fillColor !== "none") {
    options.push(`fill=${hexToRgb(element.fillColor)}`);
  }
  if (element.strokeColor && element.strokeColor !== "none") {
    options.push(`draw=${hexToRgb(element.strokeColor)}`);
  }
  if (element.fontStyle?.includes("italic")) options.push("font=\\itshape");
  if (element.fontStyle?.includes("bold")) options.push("font=\\bfseries");
  return options.length ? `[${options.join(", ")}]` : "";
}

function arrowStyleToTikz(element: DrawioElement): string {
  const arrowOptions: string[] = [];

  // Handle end arrow (target side)
  if (element.endArrow) {
    switch (element.endArrow.toLowerCase()) {
      case "block":
      case "triangle":
        arrowOptions.push("->");
        break;
      case "open":
        arrowOptions.push("-open triangle 45-");
        break;
      case "oval":
        arrowOptions.push("-o");
        break;
      case "diamond":
        arrowOptions.push("-diamond");
        break;
      case "none":
        break;
      default:
        arrowOptions.push("->");
    }
  }

  if (element.startArrow) {
    const startArrow = element.startArrow.toLowerCase();
    let startArrowTikz = "";
    switch (startArrow) {
      case "block":
      case "triangle":
        startArrowTikz = "<";
        break;
      case "open":
        startArrowTikz = "open triangle 45-";
        break;
      case "oval":
        startArrowTikz = "o";
        break;
      case "diamond":
        startArrowTikz = "diamond";
        break;
    }

    if (startArrowTikz) {
      if (arrowOptions.length > 0 && arrowOptions[0].includes("->")) {
        arrowOptions[0] = `${startArrowTikz}${arrowOptions[0]}`;
      } else if (arrowOptions.length > 0) {
        arrowOptions[0] = `${startArrowTikz}${arrowOptions[0]}`;
      } else {
        arrowOptions.push(`${startArrowTikz}-`);
      }
    }
  }

  if (element.strokeStyle === "dashed") {
    arrowOptions.push("dashed");
  } else if (
    element.strokeStyle === "dotted" ||
    element.strokeStyle === "1 2"
  ) {
    arrowOptions.push("dotted");
  } else if (element.strokeStyle && element.strokeStyle !== "solid") {
    arrowOptions.push(`dash pattern=${element.strokeStyle}`);
  }

  if (element.strokeWidth && element.strokeWidth > 1) {
    const scaledWidth = (element.strokeWidth * 0.5).toFixed(2);
    arrowOptions.push(`line width=${scaledWidth}pt`);
  }

  if (element.strokeColor && element.strokeColor !== "#000000") {
    const colorRgb = hexToRgb(element.strokeColor);
    arrowOptions.push(`draw=${colorRgb}`);
  }

  return arrowOptions.length > 0 ? `[${arrowOptions.join(", ")}]` : "";
}

export function generateTikzCode(elements: DrawioElement[]): string {
  const scale = 0.015;

  const maxY = Math.max(
    ...elements.map((e) => (e.y || 0) + (e.height || 0)).filter((y) => y > 0),
    1000,
  );

  let tikz = "\\documentclass{article}\n";
  tikz += "\\usepackage{tikz}\n";
  tikz += "\\usepackage{xcolor}\n";
  tikz += "\\usepackage{amsmath}\n";
  tikz += "\\usetikzlibrary{arrows,shapes,positioning}\n\n";
  tikz += "\\begin{document}\n\n";
  tikz += "\\begin{tikzpicture}[scale=1]\n\n";

  const shapes = elements.filter(
    (e) => e.type !== "line" && e.type !== "arrow",
  );
  const connectors = elements.filter(
    (e) => e.type === "line" || e.type === "arrow",
  );

  const nodeMap = new Map<string, { name: string; x: number; y: number }>();

  shapes.forEach((elem, index) => {
    if (!elem.width || !elem.height) return;

    const nodeId = `node${index}`;
    const cx = (elem.x || 0) + elem.width / 2;
    const cy = (elem.y || 0) + elem.height / 2;

    if (elem.id) {
      nodeMap.set(elem.id, { name: nodeId, x: cx, y: cy });
    }

    const cx_tikz = coordinatesToTikz(cx, cy, scale, maxY);
    const width_tikz = ((elem.width || 0) * scale).toFixed(2);
    const height_tikz = ((elem.height || 0) * scale).toFixed(2);

    let shapeType = "rectangle";
    if (elem.type === "circle") shapeType = "circle";
    else if (elem.type === "diamond") shapeType = "diamond";
    else if (elem.type === "triangle") shapeType = "triangle";

    let fillColor = "white";
    if (elem.fillColor && elem.fillColor !== "none") {
      fillColor = hexToRgb(elem.fillColor);
    }

    let strokeColor = "black";
    if (elem.strokeColor && elem.strokeColor !== "none") {
      strokeColor = hexToRgb(elem.strokeColor);
    }

    // Prepare text
    let cleanText = elem.text || "";
    if (elem.math) {
      if (!cleanText.includes("\\(")) {
        cleanText = `$$${cleanText}$$`;
      }
    } else {
      cleanText = cleanText.replace(/{/g, "\\{").replace(/}/g, "\\}");
    }

    const lineWidth =
      elem.strokeWidth && elem.strokeWidth > 1
        ? `, line width=${(elem.strokeWidth * 0.5).toFixed(2)}pt`
        : "";

    const nodeOptions = [
      `${shapeType}`,
      `minimum width=${width_tikz}cm`,
      `minimum height=${height_tikz}cm`,
      `fill=${fillColor}`,
      `draw=${strokeColor}${lineWidth}`,
      `inner sep=0pt`,
      `outer sep=0pt`,
      `align=center`,
      `text centered`,
    ].join(", ");

    tikz += `  \\node[${nodeOptions}] (${nodeId}) at ${cx_tikz} {${cleanText}};\n`;
  });

  tikz += "\n";

  connectors.forEach((elem) => {
    if (elem.source && elem.target) {
      const sourceNode = nodeMap.get(elem.source);
      const targetNode = nodeMap.get(elem.target);

      if (sourceNode && targetNode) {
        const arrowStyle = arrowStyleToTikz(elem);
        const defaultStyle = !elem.endArrow && !elem.startArrow ? "[draw]" : "";
        tikz += `  \\draw${arrowStyle || defaultStyle} (${sourceNode.name}) -- (${targetNode.name});\n`;
      }
    }
  });

  tikz += "\n\\end{tikzpicture}\n\n";
  tikz += "\\end{document}\n";

  return tikz;
}
