"""Render the first page of a document (PDF or image) as a PIL image."""

from __future__ import annotations

from pathlib import Path

import pypdfium2
from PIL import Image


def render_first_page(path: Path, dpi: int = 150) -> Image.Image:
    if Path(path).suffix.lower() == ".pdf":
        pdf = pypdfium2.PdfDocument(str(path))
        try:
            image = pdf[0].render(scale=dpi / 72).to_pil()
        finally:
            pdf.close()
        return image.convert("RGB")
    with Image.open(path) as img:
        return img.convert("RGB")
