"""Tests for the FastAPI web helpers."""

# pyright: reportPrivateUsage=false

import pytest
from fastapi import HTTPException

from drawio2tikz.web import _safe_filename, _validate_upload_payload


def test_safe_filename_strips_paths_and_unsafe_characters() -> None:
    """Upload filenames are converted to safe temp-file basenames."""
    assert _safe_filename(r"..\bad path/<figure 1>.drawio") == "figure_1.drawio"


def test_safe_filename_preserves_drawio_png_suffix() -> None:
    """Embedded draw.io PNGs keep the compound suffix."""
    assert _safe_filename("my diagram.drawio.png") == "my_diagram.drawio.png"


def test_validate_upload_payload_rejects_xml_doctype() -> None:
    """XML uploads with entity declarations are rejected before parsing."""
    payload = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><mxfile />'

    with pytest.raises(HTTPException):
        _validate_upload_payload(payload, "diagram.drawio")


def test_validate_upload_payload_rejects_fake_drawio_png() -> None:
    """Compound PNG uploads must actually have a PNG signature."""
    with pytest.raises(HTTPException):
        _validate_upload_payload(b"<mxfile />", "diagram.drawio.png")
