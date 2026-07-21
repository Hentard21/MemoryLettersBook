#!/usr/bin/env python3
"""Crop approved raster logos without changing their pixels or source files."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "assets" / "branding" / "source"
OUTPUT_ROOT = PROJECT_ROOT / "assets" / "branding" / "processed"
LOGOS = {
    "dialog-pokoleniy-full-white.png": "dialog-pokoleniy-full-cropped-white.png",
    "center-support-full-white.png": "center-support-full-cropped-white.png",
}


def content_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    rgb = image.convert("RGB")
    white = Image.new("RGB", rgb.size, "white")
    difference = ImageChops.difference(rgb, white).convert("L")
    mask = difference.point(lambda value: 255 if value > 8 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("Logo image contains no pixels distinct from white")
    return bbox


def padded_bbox(
    bbox: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    pad_x = max(12, round(width * 0.035))
    pad_y = max(12, round(height * 0.06))
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(size[0], right + pad_x),
        min(size[1], bottom + pad_y),
    )


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for source_name, output_name in LOGOS.items():
        source = SOURCE_ROOT / source_name
        output = OUTPUT_ROOT / output_name
        with Image.open(source) as image:
            crop_box = padded_bbox(content_bbox(image), image.size)
            cropped = image.crop(crop_box)
            cropped.save(output, format="PNG", optimize=False)
            print(f"{source.name}: {image.size} -> {cropped.size}; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
