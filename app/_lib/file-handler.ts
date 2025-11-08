export interface ConversionResult {
  tikz: string;
  elementCount: number;
  codeSize: number;
  status: "success" | "error";
  error?: string;
}

export async function convertDrawioFile(file: File): Promise<ConversionResult> {
  try {
    // Validate file type
    if (!file.name.endsWith(".drawio") && !file.name.endsWith(".xml")) {
      return {
        codeSize: 0,
        elementCount: 0,
        error: "Invalid file type. Please upload a .drawio or .xml file",
        status: "error",
        tikz: "",
      };
    }

    // Validate file size
    if (file.size > 10 * 1024 * 1024) {
      return {
        codeSize: 0,
        elementCount: 0,
        error: "File size exceeds 10MB limit",
        status: "error",
        tikz: "",
      };
    }

    // Read file content
    const content = await file.text();

    // Send to API
    const response = await fetch("/api/convert", {
      body: JSON.stringify({ xml: content }),
      headers: {
        "Content-Type": "application/json",
      },
      method: "POST",
    });

    if (!response.ok) {
      const error = await response.json();
      return {
        codeSize: 0,
        elementCount: 0,
        error: error.error || "Conversion failed",
        status: "error",
        tikz: "",
      };
    }

    const result = await response.json();
    return result as ConversionResult;
  } catch (error) {
    return {
      codeSize: 0,
      elementCount: 0,
      error: error instanceof Error ? error.message : "Unknown error",
      status: "error",
      tikz: "",
    };
  }
}

export function downloadTikzFile(
  tikzCode: string,
  filename = "diagram.tikz",
): void {
  const element = document.createElement("a");
  const file = new Blob([tikzCode], { type: "text/plain" });
  element.href = URL.createObjectURL(file);
  element.download = filename;
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
  URL.revokeObjectURL(element.href);
}

export function downloadLatexDocument(
  tikzCode: string,
  filename = "document.tex",
): void {
  const latexDocument = `\\documentclass{article}
\\usepackage{tikz}
\\usepackage{xcolor}
\\usetikzlibrary{arrows,shapes,positioning}

\\title{Diagram from Draw.io}
\\author{}
\\date{\\today}

\\begin{document}

\\maketitle

${tikzCode}

\\end{document}
`;
  const element = document.createElement("a");
  const file = new Blob([latexDocument], { type: "text/plain" });
  element.href = URL.createObjectURL(file);
  element.download = filename;
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
  URL.revokeObjectURL(element.href);
}
