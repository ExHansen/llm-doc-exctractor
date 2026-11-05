"""Make a clean PDF look like a scan: rotation, noise, blur, JPEG artifacts, image-only output."""

from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageFilter

from docex.imaging import render_first_page

LEVELS = {
    "scan_light": {"angle": 0.7, "sigma": 6.0, "blur": 0.4, "jpeg": 70},
    "scan_heavy": {"angle": 1.5, "sigma": 14.0, "blur": 1.0, "jpeg": 40},
}


def degrade_pdf(
    src: Path, dst: Path, level: Literal["scan_light", "scan_heavy"], rng: random.Random
) -> None:
    p = LEVELS[level]
    image = render_first_page(src, dpi=150).convert("L")
    image = image.rotate(
        rng.uniform(-p["angle"], p["angle"]), resample=Image.Resampling.BICUBIC, fillcolor=255
    )
    noise = np.random.default_rng(rng.randrange(2**32)).normal(
        0.0, p["sigma"], (image.height, image.width)
    )
    pixels = np.clip(np.asarray(image, dtype=np.float32) + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(pixels).filter(ImageFilter.GaussianBlur(p["blur"]))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=p["jpeg"])
    buffer.seek(0)
    with Image.open(buffer) as jpeg:
        dst.parent.mkdir(parents=True, exist_ok=True)
        jpeg.convert("RGB").save(dst, "PDF", resolution=150)
