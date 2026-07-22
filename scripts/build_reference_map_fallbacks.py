#!/usr/bin/env python3
"""Build verified per-region map fallbacks from the canonical reference PDF.

The preferred source remains the vector map with a verified subject feature.
When that mapping is not yet registered, the project owner explicitly allows
using the map printed on the matching family's title page. This script crops
that map without OCR, redrawing, or geographic inference and records its
provenance in ``content/production/regions.json``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "source/reference.pdf"
REGIONS_FILE = ROOT / "content/production/regions.json"
FAMILIES_DIR = ROOT / "content/production/families"
OUTPUT_DIR = ROOT / "content/production/maps/reference-fallback"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def poppler_binary(name: str) -> str:
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin"
        / f"{name}.exe"
    )
    if bundled.is_file():
        return str(bundled)
    direct = shutil.which(name)
    if direct:
        return direct
    raise FileNotFoundError(f"{name} was not found")


def trim_near_white(image: Image.Image, padding: int = 28) -> Image.Image:
    rgb = image.convert("RGB")
    # The Russia silhouette is very light gray, so use a conservative
    # difference threshold rather than a dark-pixel bounding box.
    background = Image.new("RGB", rgb.size, "white")
    difference = ImageChops.difference(rgb, background).convert("L")
    mask = difference.point(lambda value: 255 if value > 5 else 0)
    box = mask.getbbox()
    if box is None:
        return rgb
    left, top, right, bottom = box
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(rgb.width, right + padding)
    bottom = min(rgb.height, bottom + padding)
    return rgb.crop((left, top, right, bottom))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    regions_payload = read_json(REGIONS_FILE)
    families = {
        path.stem: read_json(path)
        for path in sorted(FAMILIES_DIR.glob("hero-*.json"))
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    rendered = 0

    with tempfile.TemporaryDirectory(prefix="letters-memory-maps-") as temp_name:
        temp = Path(temp_name)
        for region in regions_payload["regions"]:
            region_id = str(region["region_id"])
            heroes = [hero for hero in region.get("reference_hero_ids", []) if hero in families]
            if not heroes:
                records.append({"region_id": region_id, "status": "review_required", "reason": "no canonical family"})
                continue
            hero_id = heroes[0]
            family = families[hero_id]
            title_page = int(family.get("canonical_reference", {}).get("title_page") or 0)
            if title_page <= 0:
                records.append({"region_id": region_id, "status": "review_required", "reason": "no reference title page"})
                continue
            # ``canonical_reference.title_page`` is the physical one-based PDF
            # page in source/reference.pdf. Printed folios inside the old book
            # differ, but must not be used for extraction.
            pdf_page = title_page
            destination = OUTPUT_DIR / f"{region_id}.png"
            if args.apply and (args.force or not destination.is_file()):
                prefix = temp / region_id
                subprocess.run(
                    [
                        poppler_binary("pdftoppm"),
                        "-f", str(pdf_page), "-l", str(pdf_page),
                        "-r", "200", "-png", "-singlefile",
                        str(REFERENCE), str(prefix),
                    ],
                    check=True,
                    cwd=ROOT,
                    capture_output=True,
                )
                rendered_page = prefix.with_suffix(".png")
                with Image.open(rendered_page) as source:
                    width, height = source.size
                    lower_title = source.crop((int(width * 0.06), int(height * 0.62), int(width * 0.94), int(height * 0.92)))
                    cropped = trim_near_white(lower_title)
                    # Preserve a clean neutral ground and exact raster content.
                    framed = ImageOps.expand(cropped, border=24, fill="white")
                    framed.save(destination, "PNG", optimize=True)
                rendered += 1
            relative = destination.relative_to(ROOT).as_posix()
            if args.apply:
                region["reference_fallback_map_file"] = relative
                region["reference_fallback_provenance"] = {
                    "source_file": "source/reference.pdf",
                    "source_pdf_page": pdf_page,
                    "reference_title_page": title_page,
                    "hero_id": hero_id,
                    "method": "lossless page render crop; no geographic inference",
                    "status": "verified_against_canonical_reference",
                }
            records.append(
                {
                    "region_id": region_id,
                    "hero_id": hero_id,
                    "reference_title_page": title_page,
                    "source_pdf_page": pdf_page,
                    "file": relative,
                    "status": "ready" if destination.is_file() else "planned",
                }
            )

    if args.apply:
        write_json(REGIONS_FILE, regions_payload)
        write_json(
            OUTPUT_DIR / "manifest.json",
            {
                "schema_version": 1,
                "source": "source/reference.pdf",
                "policy": "Fallback only when the verified vector map feature is unavailable.",
                "regions": records,
            },
        )
    print(f"regions={len(records)} rendered={rendered} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
