"""FastAPI web application for drawio2tikz."""

from __future__ import annotations

import os
import re
import tempfile
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .converter import DEFAULT_DRAWIO_BIN, ConversionResult, ConvertOptions, convert
from .drawio import drawio_stem

type UploadedDiagram = tuple[bytes, str]

MAX_UPLOAD_BYTES = int(os.environ.get("DRAWIO2TIKZ_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_SUFFIXES = {".drawio", ".xml"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
UNSAFE_FILENAME_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="16" fill="#111111"/>
<path d="M15 16h16v16H15zM33 32h16v16H33z" fill="#fff7d6"/>
<path d="M31 24h8v15h8" stroke="#f4c542" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M18 48 46 16" stroke="#5ed3c6" stroke-width="5" stroke-linecap="round"/>
</svg>"""

app = FastAPI(
    title="drawio2tikz Web",
    summary="Convert diagrams.net/draw.io files to TikZ via SVG.",
    version=package_version("drawio2tikz"),
)


class ConversionFile(BaseModel):
    """Converted file content."""

    filename: str
    tex: str
    svg_filename: str | None = None
    svg: str | None = None
    remaining_foreign_objects: int
    text_nodes: int


class ConversionResponse(BaseModel):
    """Response returned by the conversion API."""

    files: list[ConversionFile]


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    """Render a small browser UI."""
    return HTML_PAGE


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg() -> Response:
    """Serve the browser favicon."""
    return Response(
        content=FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> RedirectResponse:
    """Handle conventional browser favicon requests."""
    return RedirectResponse(url="/favicon.svg", status_code=status.HTTP_308_PERMANENT_REDIRECT)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/convert", response_model=ConversionResponse)
async def convert_api(
    file: Annotated[
        list[UploadFile],
        File(description="One or more .drawio, .drawio.png, or .xml diagrams.net files."),
    ],
    page_index: Annotated[int, Form(ge=1)] = 1,
    *,
    all_pages: Annotated[bool, Form()] = False,
    keep_svg: Annotated[bool, Form()] = False,
    output_unit: Annotated[str, Form()] = "pt",
    scale: Annotated[float, Form(gt=0)] = 1.0,
    round_number: Annotated[int, Form(ge=0)] = 3,
    texmode: Annotated[str, Form()] = "raw",
    markings: Annotated[str, Form()] = "interpret",
) -> ConversionResponse:
    """Convert uploaded draw.io files to TikZ."""
    uploads: list[UploadedDiagram] = []
    for upload in file:
        filename = _safe_filename(upload.filename)
        payload = await _read_upload(upload)
        _validate_upload_payload(payload, filename)
        uploads.append((payload, filename))

    _validate_unique_upload_filenames(uploads)
    _validate_unique_upload_stems(uploads)

    return await run_in_threadpool(
        _convert_payloads,
        uploads,
        page_index,
        all_pages=all_pages,
        keep_svg=keep_svg,
        output_unit=output_unit,
        scale=scale,
        round_number=round_number,
        texmode=texmode,
        markings=markings,
    )


async def _read_upload(file: UploadFile) -> bytes:
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file must be {MAX_UPLOAD_BYTES} bytes or smaller.",
        )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )
    return payload


def _safe_filename(filename: str | None) -> str:
    original_name = (filename or "diagram.drawio").replace("\\", "/")
    safe_name = Path(original_name).name
    safe_name = CONTROL_CHARS_RE.sub("", safe_name).strip().strip(".")
    suffixes = "".join(Path(safe_name).suffixes).lower()

    if suffixes == ".drawio.png":
        stem = safe_name[: -len(".drawio.png")]
        return f"{_safe_stem(stem)}.drawio.png"

    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a .drawio, .drawio.png, or .xml file.",
        )
    stem = safe_name[: -len(suffix)]
    return f"{_safe_stem(stem)}{suffix}"


def _safe_stem(stem: str) -> str:
    """Normalize an uploaded basename while preserving a deterministic stem."""
    safe_stem = UNSAFE_FILENAME_CHARS_RE.sub("_", stem).strip("._-")
    return safe_stem[:80] or "diagram"


def _validate_upload_payload(payload: bytes, filename: str) -> None:
    """Reject upload payloads that cannot be handled safely by the converter."""
    if filename.endswith(".drawio.png"):
        if not payload.startswith(PNG_SIGNATURE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded .drawio.png file is not a valid PNG file.",
            )
        return

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded XML file must be UTF-8 encoded.",
        ) from exc

    stripped = text.lstrip()
    if not stripped.startswith("<"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded .drawio or .xml file must contain XML.",
        )

    upper = stripped[:4096].upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded XML must not contain DOCTYPE or ENTITY declarations.",
        )


def _validate_unique_upload_filenames(uploads: list[UploadedDiagram]) -> None:
    """Reject uploaded files that would collide in the temporary workspace."""
    seen: set[str] = set()
    for _, filename in uploads:
        if filename in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Upload filenames must be unique after sanitization: {filename}",
            )
        seen.add(filename)


def _validate_unique_upload_stems(uploads: list[UploadedDiagram]) -> None:
    """Reject uploads that would produce ambiguous output filenames."""
    seen: set[str] = set()
    for _, filename in uploads:
        stem = drawio_stem(Path(filename))
        if stem in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded files must have unique output basenames: {stem}",
            )
        seen.add(stem)


def _convert_payloads(
    uploads: list[UploadedDiagram],
    page_index: int,
    *,
    all_pages: bool,
    keep_svg: bool,
    output_unit: str,
    scale: float,
    round_number: int,
    texmode: str,
    markings: str,
) -> ConversionResponse:
    with tempfile.TemporaryDirectory(prefix="drawio2tikz-web-") as tmp:
        work_dir = Path(tmp)
        output_dir = work_dir / "tikz"
        svg_dir = work_dir / "svg"
        results: list[ConversionResult] = []
        for payload, filename in uploads:
            input_path = work_dir / filename
            input_path.write_bytes(payload)
            options = ConvertOptions(
                input_path=input_path,
                output=output_dir,
                page_index=page_index,
                all_pages=all_pages,
                keep_svg=keep_svg,
                svg_dir=svg_dir if keep_svg else None,
                drawio_bin=DEFAULT_DRAWIO_BIN,
                output_unit=output_unit,
                scale=scale,
                round_number=round_number,
                texmode=texmode,
                markings=markings,
                quiet=True,
            )

            try:
                results.extend(convert(options))
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(exc),
                ) from exc

        return ConversionResponse(
            files=[
                ConversionFile(
                    filename=result.tex_path.name,
                    tex=result.tex_path.read_text(encoding="utf-8"),
                    svg_filename=result.svg_path.name if result.svg_path else None,
                    svg=result.svg_path.read_text(encoding="utf-8") if result.svg_path else None,
                    remaining_foreign_objects=result.remaining_foreign_objects,
                    text_nodes=result.text_nodes,
                )
                for result in results
            ],
        )


def run() -> None:
    """Run the web server."""
    uvicorn.run(
        "drawio2tikz.web:app",
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("RELOAD", "").lower() in {"1", "true", "yes"},
    )


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Draw.io to TikZ</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {
      color-scheme: light;
      --ink: #111111;
      --muted: #777777;
      --soft: #f7f7f5;
      --line: #e8e8e3;
      --line-strong: #d8d8d1;
      --card: #ffffff;
      --accent: #111111;
      --success: #1e7b4f;
      --danger: #a33a2c;
      --shadow: 0 14px 34px rgba(18, 18, 18, 0.07), 0 2px 8px rgba(18, 18, 18, 0.05);
      --radius: 18px;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: Avenir Next, Avenir, Helvetica Neue, Segoe UI, sans-serif;
      background:
        radial-gradient(circle at 22% 16%, rgba(0, 0, 0, 0.035), transparent 24rem),
        linear-gradient(180deg, #ffffff 0%, #fbfbf9 60%, #f4f3ee 100%);
    }

    button,
    input,
    select {
      font: inherit;
    }

    .shell {
      width: min(100% - 48px, 1440px);
      margin: 0 auto;
      padding: clamp(68px, 9vh, 112px) 0 54px;
    }

    .hero {
      text-align: center;
      padding: 0 16px clamp(52px, 7vh, 84px);
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(2.45rem, 5vw, 4.25rem);
      line-height: 1;
      letter-spacing: -0.065em;
      font-weight: 800;
    }

    .hero p {
      width: min(760px, 100%);
      margin: 24px auto 0;
      color: var(--muted);
      font-size: clamp(1.1rem, 1.7vw, 1.45rem);
      line-height: 1.45;
    }

    .resource-links {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 24px;
    }

    .resource-link {
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 0 15px;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.72);
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
    }

    .resource-link:hover {
      border-color: var(--ink);
      background: #ffffff;
      transform: translateY(-1px);
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 36px;
      align-items: start;
    }

    .card {
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    .upload-card {
      padding: 34px;
    }

    .card-title {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin: 0 0 24px;
      font-size: 1.45rem;
      line-height: 1.15;
      letter-spacing: -0.04em;
      font-weight: 800;
    }

    .drop-zone {
      display: grid;
      place-items: center;
      min-height: 142px;
      width: 100%;
      padding: 28px;
      cursor: pointer;
      text-align: center;
      color: var(--ink);
      border: 2px dashed var(--line-strong);
      border-radius: 14px;
      background:
        linear-gradient(135deg, rgba(255,255,255,0.82), rgba(250,250,248,0.9)),
        repeating-linear-gradient(-45deg, rgba(0,0,0,0.018) 0 1px, transparent 1px 10px);
      transition: border-color 160ms ease, transform 160ms ease, background 160ms ease;
    }

    .drop-zone:hover,
    .drop-zone.is-dragging {
      border-color: #111111;
      transform: translateY(-1px);
      background-color: #ffffff;
    }

    .drop-overlay {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      place-items: center;
      padding: 24px;
      background: rgba(17, 17, 17, 0.54);
      backdrop-filter: blur(9px);
    }

    .drop-overlay.is-visible {
      display: grid;
    }

    .drop-overlay-inner {
      width: min(620px, 100%);
      border: 2px dashed rgba(255, 255, 255, 0.86);
      border-radius: 28px;
      padding: 48px 28px;
      color: #ffffff;
      background: rgba(17, 17, 17, 0.62);
      text-align: center;
      box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
    }

    .drop-overlay-inner strong {
      display: block;
      font-size: clamp(1.8rem, 4vw, 3rem);
      line-height: 1;
      letter-spacing: -0.06em;
    }

    .drop-overlay-inner span {
      display: block;
      margin-top: 14px;
      color: rgba(255, 255, 255, 0.76);
      font-size: 1rem;
    }

    .drop-zone strong {
      display: block;
      font-size: 1.1rem;
      letter-spacing: -0.02em;
    }

    .drop-zone span {
      display: block;
      margin-top: 12px;
      color: var(--muted);
    }

    .file-note {
      min-height: 20px;
      margin: 16px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .options {
      margin-top: 22px;
      border-top: 1px solid var(--line);
      padding-top: 20px;
    }

    .options summary {
      cursor: pointer;
      color: #333333;
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .option-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }

    .field {
      display: grid;
      gap: 8px;
      color: #3a3a3a;
      font-size: 0.9rem;
      font-weight: 700;
    }

    .field input,
    .field select {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line-strong);
      border-radius: 11px;
      padding: 0 12px;
      color: var(--ink);
      background: #ffffff;
      outline: none;
    }

    .field input:focus,
    .field select:focus {
      border-color: var(--ink);
      box-shadow: 0 0 0 3px rgba(17, 17, 17, 0.08);
    }

    .check-row {
      display: flex;
      align-items: center;
      gap: 9px;
      min-height: 44px;
      color: #3a3a3a;
      font-size: 0.94rem;
      font-weight: 700;
    }

    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 24px;
    }

    .primary,
    .secondary {
      border: 0;
      border-radius: 999px;
      min-height: 46px;
      padding: 0 20px;
      cursor: pointer;
      font-weight: 800;
      letter-spacing: -0.02em;
    }

    .primary {
      color: #ffffff;
      background: var(--accent);
    }

    .primary:disabled {
      cursor: not-allowed;
      opacity: 0.48;
    }

    .secondary {
      color: var(--ink);
      background: #efefeb;
    }

    .status {
      color: var(--muted);
      font-size: 0.95rem;
    }

    .status.error {
      color: var(--danger);
    }

    .status.success {
      color: var(--success);
    }

    .result-card {
      min-height: 88px;
      overflow: hidden;
    }

    .empty-state {
      display: grid;
      min-height: 88px;
      place-items: center;
      padding: 28px;
      color: var(--muted);
      text-align: center;
      font-size: 1.12rem;
    }

    .result-pane {
      display: none;
      padding: 24px;
    }

    .result-pane.is-visible {
      display: block;
    }

    .result-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .result-title {
      min-width: 0;
      font-weight: 800;
      letter-spacing: -0.035em;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .result-actions {
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }

    .mini {
      min-height: 36px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 0 13px;
      cursor: pointer;
      color: var(--ink);
      background: #ffffff;
      font-size: 0.88rem;
      font-weight: 800;
    }

    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }

    .tab {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
      color: var(--muted);
      background: #ffffff;
      font-size: 0.88rem;
      font-weight: 800;
    }

    .tab.is-active {
      color: #ffffff;
      background: var(--ink);
      border-color: var(--ink);
    }

    pre {
      max-height: 520px;
      margin: 0;
      overflow: auto;
      border: 1px solid #202020;
      border-radius: 14px;
      padding: 18px;
      color: #f5f1e8;
      background: #111111;
      font-family: SFMono-Regular, Menlo, Consolas, Liberation Mono, monospace;
      font-size: 0.86rem;
      line-height: 1.55;
      white-space: pre;
    }

    .metrics {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
      color: var(--muted);
      font-size: 0.9rem;
    }

    .metric {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 10px;
      background: #ffffff;
    }

    .svg-box {
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }

    .svg-box summary {
      cursor: pointer;
      color: #333333;
      font-weight: 800;
    }

    .embed-card {
      display: grid;
      grid-template-columns: minmax(0, 0.82fr) minmax(0, 1fr);
      gap: 24px;
      margin-top: 34px;
      padding: 28px;
    }

    .embed-card h2 {
      margin: 0;
      font-size: clamp(1.7rem, 3vw, 2.4rem);
      line-height: 1;
      letter-spacing: -0.055em;
    }

    .embed-card p {
      margin: 14px 0 0;
      color: var(--muted);
      line-height: 1.55;
    }

    .embed-card pre {
      max-height: none;
      font-size: 0.82rem;
    }

    .embed-card mark {
      border-radius: 6px;
      padding: 1px 4px;
      color: #111111;
      background: #d9f99d;
    }

    .steps {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 24px;
      margin-top: 58px;
      text-align: center;
    }

    .step strong {
      display: block;
      margin-bottom: 12px;
      font-size: 1.8rem;
      line-height: 1;
      font-weight: 800;
      letter-spacing: -0.045em;
    }

    .step span {
      color: var(--muted);
      font-size: 1rem;
    }

    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }

    @media (max-width: 880px) {
      .shell {
        width: min(100% - 28px, 720px);
        padding-top: 28px;
      }

      .hero {
        padding-bottom: 32px;
      }

      .workspace,
      .steps,
      .embed-card,
      .option-grid {
        grid-template-columns: 1fr;
      }

      .upload-card,
      .result-pane {
        padding: 22px;
      }

      .actions,
      .result-head {
        align-items: stretch;
        flex-direction: column;
      }

      .primary,
      .secondary,
      .mini {
        width: 100%;
      }

      .result-actions {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class="drop-overlay" id="drop-overlay" aria-hidden="true">
    <div class="drop-overlay-inner">
      <strong>Drop anywhere</strong>
      <span>Release your .drawio, .drawio.png, or .xml files to load them.</span>
    </div>
  </div>

  <main class="shell">
    <section class="hero" aria-labelledby="page-title">
      <h1 id="page-title">Draw.io to TikZ</h1>
      <p>Convert your Draw.io diagrams into professional LaTeX TikZ code.</p>
      <nav class="resource-links" aria-label="Project links">
        <a class="resource-link" href="https://github.com/okayama-daiki/drawio2tikz" rel="noreferrer" target="_blank">GitHub</a>
        <a class="resource-link" href="https://github.com/okayama-daiki/drawio2tikz/issues/new" rel="noreferrer" target="_blank">Report a problem</a>
        <a class="resource-link" href="https://buymeacoffee.com/daikiokayama" rel="noreferrer" target="_blank">Buy me a coffee</a>
      </nav>
    </section>

    <section class="workspace" aria-label="Converter">
      <form class="card upload-card" id="convert-form">
        <h2 class="card-title">1. Upload Files</h2>

        <label class="drop-zone" id="drop-zone" for="file-input">
          <span>
            <strong>Drop your files here or click to upload</strong>
            <span>Supports .drawio, .drawio.png, and .xml files</span>
          </span>
          <input class="visually-hidden" id="file-input" name="file" type="file" accept=".drawio,.drawio.png,.xml" multiple required>
        </label>
        <p class="file-note" id="file-note">Supports .drawio, .drawio.png, and .xml files exported from Draw.io</p>

        <details class="options">
          <summary>Conversion options</summary>
          <div class="option-grid">
            <label class="field">
              Page
              <input name="page_index" type="number" min="1" value="1">
            </label>
            <label class="field">
              Unit
              <input name="output_unit" type="text" value="pt">
            </label>
            <label class="field">
              Scale
              <input name="scale" type="number" min="0.01" step="0.01" value="1">
            </label>
            <label class="field">
              Precision
              <input name="round_number" type="number" min="0" value="3">
            </label>
            <label class="field">
              TeX mode
              <input name="texmode" type="text" value="raw">
            </label>
            <label class="field">
              Markings
              <input name="markings" type="text" value="interpret">
            </label>
          </div>
          <label class="check-row">
            <input id="all-pages" name="all_pages" type="checkbox" value="true">
            Convert all pages
          </label>
          <label class="check-row">
            <input id="keep-svg" name="keep_svg" type="checkbox" value="true">
            Include sanitized SVG
          </label>
        </details>

        <div class="actions">
          <button class="primary" id="submit-button" type="submit">Convert to TikZ</button>
          <button class="secondary" id="clear-button" type="button">Clear</button>
          <span class="status" id="status-text" role="status" aria-live="polite"></span>
        </div>
      </form>

      <section class="card result-card" aria-label="Conversion result">
        <div class="empty-state" id="empty-state">Upload a Draw.io file to get started</div>
        <div class="result-pane" id="result-pane">
          <div class="tabs" id="tabs" aria-label="Converted files"></div>
          <div class="result-head">
            <div class="result-title" id="result-title"></div>
            <div class="result-actions">
              <button class="mini" id="copy-button" type="button">Copy</button>
              <button class="mini" id="download-button" type="button">Download .tex</button>
            </div>
          </div>
          <pre id="tex-output"></pre>
          <div class="metrics" id="metrics"></div>
          <details class="svg-box" id="svg-box">
            <summary>Sanitized SVG</summary>
            <pre id="svg-output"></pre>
          </details>
        </div>
      </section>
    </section>

    <section class="steps" aria-label="How it works">
      <div class="step">
        <strong>1</strong>
        <span>Upload your Draw.io files</span>
      </div>
      <div class="step">
        <strong>2</strong>
        <span>Get instant TikZ code</span>
      </div>
      <div class="step">
        <strong>3</strong>
        <span>Use in your LaTeX documents</span>
      </div>
    </section>

    <section class="card embed-card" aria-labelledby="embed-title">
      <div>
        <h2 id="embed-title">Embed the generated TikZ</h2>
        <p>Add the required packages to your preamble, save the generated `.tex` file with your figures, then include it from the document body.</p>
      </div>
      <pre>\\usepackage{xcolor}
\\usepackage{tikz}

\\begin{figure}
  \\centering
  \\input{<mark>path/to/your/figure.tex</mark>}
  \\caption{Diagram exported from draw.io}
\\end{figure}</pre>
    </section>
  </main>

  <script>
    const form = document.querySelector("#convert-form");
    const fileInput = document.querySelector("#file-input");
    const dropZone = document.querySelector("#drop-zone");
    const fileNote = document.querySelector("#file-note");
    const statusText = document.querySelector("#status-text");
    const submitButton = document.querySelector("#submit-button");
    const clearButton = document.querySelector("#clear-button");
    const emptyState = document.querySelector("#empty-state");
    const resultPane = document.querySelector("#result-pane");
    const resultTitle = document.querySelector("#result-title");
    const texOutput = document.querySelector("#tex-output");
    const svgOutput = document.querySelector("#svg-output");
    const svgBox = document.querySelector("#svg-box");
    const dropOverlay = document.querySelector("#drop-overlay");
    const metrics = document.querySelector("#metrics");
    const tabs = document.querySelector("#tabs");
    const copyButton = document.querySelector("#copy-button");
    const downloadButton = document.querySelector("#download-button");
    const allPages = document.querySelector("#all-pages");
    const keepSvg = document.querySelector("#keep-svg");

    const defaultFileNote = "Supports .drawio, .drawio.png, and .xml files exported from Draw.io";

    let files = [];
    let selectedUploads = [];
    let activeIndex = 0;
    let dragDepth = 0;
    let copyResetTimer = 0;
    let crcTable = null;

    function isAllowedFile(file) {
      const name = file.name.toLowerCase();
      return name.endsWith(".drawio") || name.endsWith(".drawio.png") || name.endsWith(".xml");
    }

    function setStatus(message, kind = "") {
      statusText.textContent = message;
      statusText.className = kind ? `status ${kind}` : "status";
    }

    function formatFileList(selectedFiles) {
      if (selectedFiles.length === 1) {
        const file = selectedFiles[0];
        return `${file.name} - ${formatBytes(file.size)}`;
      }

      const totalBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
      return `${selectedFiles.length} files - ${formatBytes(totalBytes)} total`;
    }

    function fileKey(file) {
      return `${file.name}:${file.size}:${file.lastModified}`;
    }

    function syncSelectedUploads() {
      const transfer = new DataTransfer();
      selectedUploads.forEach((file) => transfer.items.add(file));
      fileInput.files = transfer.files;
      fileNote.textContent = selectedUploads.length ? formatFileList(selectedUploads) : defaultFileNote;
    }

    function addSelectedFiles(fileList) {
      const newFiles = Array.from(fileList || []);
      if (!newFiles.length) {
        syncSelectedUploads();
        return;
      }

      if (newFiles.some((file) => !isAllowedFile(file))) {
        setStatus("Upload a .drawio, .drawio.png, or .xml file.", "error");
        syncSelectedUploads();
        return;
      }

      const selectedKeys = new Set(selectedUploads.map(fileKey));
      newFiles.forEach((file) => {
        const key = fileKey(file);
        if (!selectedKeys.has(key)) {
          selectedKeys.add(key);
          selectedUploads.push(file);
        }
      });
      syncSelectedUploads();
      setStatus("");
    }

    function clearSelectedFiles() {
      selectedUploads = [];
      fileInput.value = "";
      syncSelectedUploads();
    }

    function hasDragFiles(event) {
      return Array.from(event.dataTransfer?.types || []).includes("Files");
    }

    function showDropOverlay() {
      dropZone.classList.add("is-dragging");
      dropOverlay.classList.add("is-visible");
      dropOverlay.setAttribute("aria-hidden", "false");
    }

    function hideDropOverlay() {
      dropZone.classList.remove("is-dragging");
      dropOverlay.classList.remove("is-visible");
      dropOverlay.setAttribute("aria-hidden", "true");
    }

    function resetCopyButton() {
      window.clearTimeout(copyResetTimer);
      copyButton.textContent = "Copy";
    }

    function markCopied() {
      window.clearTimeout(copyResetTimer);
      copyButton.textContent = "Copied";
      copyResetTimer = window.setTimeout(resetCopyButton, 1600);
    }

    function formatBytes(bytes) {
      if (bytes < 1024) {
        return `${bytes} B`;
      }
      if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
      }
      return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
    }

    function resetResult() {
      files = [];
      activeIndex = 0;
      tabs.replaceChildren();
      texOutput.textContent = "";
      svgOutput.textContent = "";
      metrics.replaceChildren();
      resultPane.classList.remove("is-visible");
      emptyState.style.display = "grid";
      downloadButton.textContent = "Download .tex";
      resetCopyButton();
    }

    function renderTabs() {
      tabs.replaceChildren();
      if (files.length < 2) {
        return;
      }

      files.forEach((file, index) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = index === activeIndex ? "tab is-active" : "tab";
        tab.textContent = file.filename;
        tab.addEventListener("click", () => renderFile(index));
        tabs.appendChild(tab);
      });
    }

    function renderFile(index) {
      activeIndex = index;
      const file = files[index];
      emptyState.style.display = "none";
      resultPane.classList.add("is-visible");
      resultTitle.textContent = file.filename;
      texOutput.textContent = file.tex || "";
      downloadButton.textContent = files.length > 1 ? "Download ZIP" : "Download .tex";
      resetCopyButton();

      metrics.replaceChildren();
      addMetric(`${file.remaining_foreign_objects} foreignObject nodes left`);
      addMetric(`${file.text_nodes} SVG text nodes`);

      if (file.svg) {
        svgBox.hidden = false;
        svgOutput.textContent = file.svg;
      } else {
        svgBox.hidden = true;
        svgOutput.textContent = "";
      }

      renderTabs();
    }

    function addMetric(text) {
      const item = document.createElement("span");
      item.className = "metric";
      item.textContent = text;
      metrics.appendChild(item);
    }

    async function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }

      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }

    function downloadBlob(filename, blob) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
        link.remove();
      }, 0);
    }

    function downloadText(filename, text) {
      downloadBlob(filename, new Blob([text], { type: "text/x-tex;charset=utf-8" }));
    }

    function crc32(bytes) {
      if (!crcTable) {
        crcTable = [];
        for (let n = 0; n < 256; n += 1) {
          let c = n;
          for (let k = 0; k < 8; k += 1) {
            c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
          }
          crcTable[n] = c >>> 0;
        }
      }

      let crc = 0xffffffff;
      bytes.forEach((byte) => {
        crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
      });
      return (crc ^ 0xffffffff) >>> 0;
    }

    function zipDateParts(date) {
      return {
        time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
        date: ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
      };
    }

    function concatBytes(parts) {
      const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
      const output = new Uint8Array(totalLength);
      let offset = 0;
      parts.forEach((part) => {
        output.set(part, offset);
        offset += part.length;
      });
      return output;
    }

    function writeZip16(view, offset, value) {
      view.setUint16(offset, value, true);
    }

    function writeZip32(view, offset, value) {
      view.setUint32(offset, value, true);
    }

    function createZipBlob(convertedFiles) {
      const encoder = new TextEncoder();
      const { time, date } = zipDateParts(new Date());
      const localParts = [];
      const centralParts = [];
      let offset = 0;

      convertedFiles.forEach((file) => {
        const nameBytes = encoder.encode(file.filename);
        const dataBytes = encoder.encode(file.tex || "");
        const checksum = crc32(dataBytes);
        const localHeader = new Uint8Array(30 + nameBytes.length);
        const localView = new DataView(localHeader.buffer);
        writeZip32(localView, 0, 0x04034b50);
        writeZip16(localView, 4, 20);
        writeZip16(localView, 6, 0x0800);
        writeZip16(localView, 8, 0);
        writeZip16(localView, 10, time);
        writeZip16(localView, 12, date);
        writeZip32(localView, 14, checksum);
        writeZip32(localView, 18, dataBytes.length);
        writeZip32(localView, 22, dataBytes.length);
        writeZip16(localView, 26, nameBytes.length);
        writeZip16(localView, 28, 0);
        localHeader.set(nameBytes, 30);
        localParts.push(localHeader, dataBytes);

        const centralHeader = new Uint8Array(46 + nameBytes.length);
        const centralView = new DataView(centralHeader.buffer);
        writeZip32(centralView, 0, 0x02014b50);
        writeZip16(centralView, 4, 20);
        writeZip16(centralView, 6, 20);
        writeZip16(centralView, 8, 0x0800);
        writeZip16(centralView, 10, 0);
        writeZip16(centralView, 12, time);
        writeZip16(centralView, 14, date);
        writeZip32(centralView, 16, checksum);
        writeZip32(centralView, 20, dataBytes.length);
        writeZip32(centralView, 24, dataBytes.length);
        writeZip16(centralView, 28, nameBytes.length);
        writeZip16(centralView, 30, 0);
        writeZip16(centralView, 32, 0);
        writeZip16(centralView, 34, 0);
        writeZip16(centralView, 36, 0);
        writeZip32(centralView, 38, 0);
        writeZip32(centralView, 42, offset);
        centralHeader.set(nameBytes, 46);
        centralParts.push(centralHeader);

        offset += localHeader.length + dataBytes.length;
      });

      const centralOffset = offset;
      const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
      const endHeader = new Uint8Array(22);
      const endView = new DataView(endHeader.buffer);
      writeZip32(endView, 0, 0x06054b50);
      writeZip16(endView, 4, 0);
      writeZip16(endView, 6, 0);
      writeZip16(endView, 8, convertedFiles.length);
      writeZip16(endView, 10, convertedFiles.length);
      writeZip32(endView, 12, centralSize);
      writeZip32(endView, 16, centralOffset);
      writeZip16(endView, 20, 0);

      return new Blob([concatBytes([...localParts, ...centralParts, endHeader])], {
        type: "application/zip",
      });
    }

    function downloadConvertedFiles() {
      if (files.length === 1) {
        const file = files[0];
        downloadText(file.filename, file.tex || "");
        return;
      }

      if (files.length > 1) {
        downloadBlob("drawio2tikz-output.zip", createZipBlob(files));
      }
    }

    async function readError(response) {
      try {
        const data = await response.json();
        return data.detail || `Conversion failed with HTTP ${response.status}.`;
      } catch {
        return `Conversion failed with HTTP ${response.status}.`;
      }
    }

    fileInput.addEventListener("change", () => {
      addSelectedFiles(fileInput.files);
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragging");
      });
    });

    dropZone.addEventListener("drop", (event) => {
      addSelectedFiles(event.dataTransfer.files);
    });

    window.addEventListener("dragenter", (event) => {
      if (!hasDragFiles(event)) {
        return;
      }
      event.preventDefault();
      dragDepth += 1;
      showDropOverlay();
    });

    window.addEventListener("dragover", (event) => {
      if (!hasDragFiles(event)) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      showDropOverlay();
    });

    window.addEventListener("dragleave", (event) => {
      if (!hasDragFiles(event)) {
        return;
      }
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {
        hideDropOverlay();
      }
    });

    window.addEventListener("drop", (event) => {
      if (!hasDragFiles(event)) {
        return;
      }
      event.preventDefault();
      dragDepth = 0;
      hideDropOverlay();
      addSelectedFiles(event.dataTransfer.files);
    });

    clearButton.addEventListener("click", () => {
      form.reset();
      clearSelectedFiles();
      setStatus("");
      resetResult();
    });

    copyButton.addEventListener("click", async () => {
      const file = files[activeIndex];
      if (!file) {
        return;
      }
      try {
        await copyText(file.tex || "");
        markCopied();
      } catch {
        setStatus("Copy failed. Select the output manually.", "error");
      }
    });

    downloadButton.addEventListener("click", () => {
      downloadConvertedFiles();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      if (!fileInput.files.length) {
        setStatus("Choose at least one file first.", "error");
        return;
      }

      submitButton.disabled = true;
      submitButton.textContent = "Converting...";
      setStatus("Running draw.io export and svg2tikz...");
      resetResult();

      const body = new FormData(form);
      body.set("all_pages", allPages.checked ? "true" : "false");
      body.set("keep_svg", keepSvg.checked ? "true" : "false");

      try {
        const response = await fetch("/api/convert", {
          method: "POST",
          body,
        });

        if (!response.ok) {
          throw new Error(await readError(response));
        }

        const data = await response.json();
        files = data.files || [];
        if (!files.length) {
          throw new Error("No TikZ output was returned.");
        }

        renderFile(0);
        setStatus(`Converted ${files.length} output file${files.length === 1 ? "" : "s"}.`, "success");
      } catch (error) {
        setStatus(error.message || "Conversion failed.", "error");
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Convert to TikZ";
      }
    });
  </script>
</body>
</html>
"""
