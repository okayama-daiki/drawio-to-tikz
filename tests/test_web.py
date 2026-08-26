"""Tests for the FastAPI web helpers."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException, UploadFile, status

import drawio2tikz.web
from drawio2tikz.converter import ConversionResult
from drawio2tikz.web import (
    FAVICON_SVG,
    HTML_PAGE,
    _convert_payloads,
    _safe_filename,
    _validate_unique_upload_filenames,
    _validate_unique_upload_stems,
    _validate_upload_payload,
    convert_api,
    favicon_ico,
    favicon_svg,
)

if TYPE_CHECKING:
    from drawio2tikz.converter import ConvertOptions


def _fake_convert(options: ConvertOptions) -> list[ConversionResult]:
    output_dir = options.output
    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / f"{options.input_path.stem}.tex"
    tex_path.write_text(f"% {options.input_path.name}\n", encoding="utf-8")
    return [
        ConversionResult(
            tex_path=tex_path,
            svg_path=None,
            remaining_foreign_objects=0,
            text_nodes=0,
        ),
    ]


def test_safe_filename_strips_paths_and_unsafe_characters() -> None:
    """Upload filenames are converted to safe temp-file basenames."""
    assert _safe_filename(r"..\bad path/<figure 1>.drawio") == "figure_1.drawio"


def test_safe_filename_preserves_drawio_png_suffix() -> None:
    """Embedded draw.io PNGs keep the compound suffix."""
    assert _safe_filename("my diagram.drawio.png") == "my_diagram.drawio.png"


def test_html_page_includes_svg_favicon() -> None:
    """The browser UI advertises a favicon route."""
    assert '<link rel="icon" type="image/svg+xml"' in HTML_PAGE
    assert 'href="/favicon.svg"' in HTML_PAGE


def test_favicon_svg_endpoint_serves_svg() -> None:
    """The favicon route returns SVG content."""
    response = favicon_svg()

    assert response.media_type == "image/svg+xml"
    assert response.body == FAVICON_SVG.encode()


def test_favicon_ico_redirects_to_svg() -> None:
    """Conventional favicon.ico requests resolve to the SVG favicon."""
    response = favicon_ico()

    assert response.status_code == status.HTTP_308_PERMANENT_REDIRECT
    assert response.headers["location"] == "/favicon.svg"


def test_validate_upload_payload_rejects_xml_doctype() -> None:
    """XML uploads with entity declarations are rejected before parsing."""
    payload = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><mxfile />'

    with pytest.raises(HTTPException):
        _validate_upload_payload(payload, "diagram.drawio")


def test_validate_upload_payload_rejects_fake_drawio_png() -> None:
    """Compound PNG uploads must actually have a PNG signature."""
    with pytest.raises(HTTPException):
        _validate_upload_payload(b"<mxfile />", "diagram.drawio.png")


def test_validate_unique_upload_filenames_rejects_duplicates() -> None:
    """Multiple uploads cannot share the same sanitized temporary filename."""
    uploads = [(b"<mxfile />", "diagram.drawio"), (b"<mxfile />", "diagram.drawio")]

    with pytest.raises(HTTPException):
        _validate_unique_upload_filenames(uploads)


def test_validate_unique_upload_stems_rejects_duplicate_outputs() -> None:
    """Different upload suffixes cannot produce the same output filename."""
    uploads = [(b"<mxfile />", "diagram.drawio"), (b"<mxfile />", "diagram.xml")]

    with pytest.raises(HTTPException):
        _validate_unique_upload_stems(uploads)


def test_convert_payloads_converts_multiple_uploaded_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple uploads are converted as one batch."""
    monkeypatch.setattr(drawio2tikz.web, "convert", _fake_convert)

    response = _convert_payloads(
        [(b"<mxfile />", "one.drawio"), (b"<mxfile />", "two.drawio")],
        1,
        all_pages=False,
        keep_svg=False,
        output_unit="pt",
        scale=1.0,
        round_number=3,
        texmode="raw",
        markings="interpret",
    )

    assert [file.filename for file in response.files] == ["one.tex", "two.tex"]


def test_convert_api_accepts_multiple_upload_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """The web API accepts multiple uploaded files."""
    monkeypatch.setattr(drawio2tikz.web, "convert", _fake_convert)

    response = asyncio.run(
        convert_api(
            [
                UploadFile(filename="one.drawio", file=BytesIO(b"<mxfile />")),
                UploadFile(filename="two.drawio", file=BytesIO(b"<mxfile />")),
            ],
            1,
            all_pages=False,
            keep_svg=False,
            output_unit="pt",
            scale=1.0,
            round_number=3,
            texmode="raw",
            markings="interpret",
        ),
    )

    assert [file.filename for file in response.files] == ["one.tex", "two.tex"]
