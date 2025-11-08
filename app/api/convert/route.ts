import { type NextRequest, NextResponse } from "next/server";

import { generateTikzCode, parseDrawioXml } from "@/app/_lib/converter";

export async function POST(request: NextRequest) {
  try {
    // Validate request format
    const contentType = request.headers.get("content-type");
    if (!contentType?.includes("application/json")) {
      return NextResponse.json(
        { error: "Content-Type must be application/json" },
        { status: 400 },
      );
    }

    const body = await request.json();
    const { xml } = body;

    // Validate XML input
    if (!xml || typeof xml !== "string") {
      return NextResponse.json(
        { error: "XML content is required and must be a string" },
        { status: 400 },
      );
    }

    if (xml.length > 10 * 1024 * 1024) {
      // 10MB limit
      return NextResponse.json(
        { error: "File size exceeds maximum limit of 10MB" },
        { status: 413 },
      );
    }

    // Check if it looks like Draw.io XML
    if (!xml.includes("mxCell") && !xml.includes("mxGraphModel")) {
      return NextResponse.json(
        { error: "Invalid Draw.io XML format" },
        { status: 400 },
      );
    }

    // Parse Draw.io XML
    const elements = parseDrawioXml(xml);

    // Validate parsing results
    if (!elements || elements.length === 0) {
      return NextResponse.json(
        { error: "No drawable elements found in the XML" },
        { status: 400 },
      );
    }

    // Generate TikZ code
    const tikzCode = generateTikzCode(elements);

    // Validate generated code
    if (!tikzCode || tikzCode.length === 0) {
      return NextResponse.json(
        { error: "Failed to generate TikZ code" },
        { status: 500 },
      );
    }

    return NextResponse.json(
      {
        codeSize: tikzCode.length,
        elementCount: elements.length,
        status: "success",
        tikz: tikzCode,
      },
      { status: 200 },
    );
  } catch (error) {
    console.error("[API] Conversion error:", error);

    // Distinguish between different error types
    if (error instanceof SyntaxError) {
      return NextResponse.json(
        { error: "Invalid JSON format in request body" },
        { status: 400 },
      );
    }

    return NextResponse.json(
      {
        details: error instanceof Error ? error.message : "Unknown error",
        error: "Internal server error during conversion",
      },
      { status: 500 },
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    headers: {
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
    },
    status: 200,
  });
}
