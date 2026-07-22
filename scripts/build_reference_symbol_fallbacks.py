#!/usr/bin/env python3
"""Extract award and emblem fallbacks from canonical family title pages.

These images are documentary crops, not generated or inferred symbols. A
verified registry asset always has priority; the crops only keep the draft
visually complete while official files are being registered.
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
FAMILIES_DIR = ROOT / "content/production/families"
EMBLEMS_FILE = ROOT / "content/production/emblems.json"
OUTPUT_DIR = ROOT / "content/production/symbols/reference-fallback"


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
    raise FileNotFoundError(name)


def trim_near_white(image: Image.Image, padding: int = 24) -> Image.Image:
    rgb = image.convert("RGB")
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert("L")
    mask = difference.point(lambda value: 255 if value > 5 else 0)
    box = mask.getbbox()
    if box is None:
        return rgb
    left, top, right, bottom = box
    return rgb.crop(
        (
            max(0, left - padding),
            max(0, top - padding),
            min(rgb.width, right + padding),
            min(rgb.height, bottom + padding),
        )
    )


def save_crop(page: Image.Image, ratios: tuple[float, float, float, float], destination: Path) -> None:
    width, height = page.size
    left, top, right, bottom = ratios
    crop = page.crop((int(width * left), int(height * top), int(width * right), int(height * bottom)))
    crop = ImageOps.expand(trim_near_white(crop), border=20, fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True)
    crop.save(destination, "PNG", optimize=True)


def has_visible_content(path: Path) -> bool:
    """Return False for a crop that contains only the white page background."""
    if not path.is_file():
        return False
    with Image.open(path) as source:
        rgb = source.convert("RGB")
        difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert("L")
        mask = difference.point(lambda value: 255 if value > 5 else 0)
        return mask.getbbox() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    family_paths = sorted(FAMILIES_DIR.glob("hero-*.json"))
    families = [read_json(path) for path in family_paths]
    emblems = read_json(EMBLEMS_FILE)
    emblem_by_id = {item["emblem_id"]: item for item in emblems["emblems"]}
    first_region_hero: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    updated: dict[str, dict[str, Any]] = {}

    with tempfile.TemporaryDirectory(prefix="letters-memory-symbols-") as temp_name:
        temp = Path(temp_name)
        for family in families:
            hero_id = str(family["hero_id"])
            title_page = int(family.get("canonical_reference", {}).get("title_page") or 0)
            if title_page <= 0:
                records.append({"hero_id": hero_id, "status": "review_required", "reason": "no title page"})
                continue
            rendered = temp / f"{hero_id}.png"
            subprocess.run(
                [
                    poppler_binary("pdftoppm"),
                    "-f", str(title_page), "-l", str(title_page),
                    "-r", "200", "-png", "-singlefile",
                    str(REFERENCE), str(rendered.with_suffix("")),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
            award_file = OUTPUT_DIR / "awards" / f"{hero_id}.png"
            if args.apply and (args.force or not award_file.is_file()):
                with Image.open(rendered) as page:
                    save_crop(page, (0.27, 0.015, 0.73, 0.29), award_file)
            award_is_visible = has_visible_content(award_file)
            if award_is_visible:
                family["reference_award_file"] = award_file.relative_to(ROOT).as_posix()
                family["reference_award_provenance"] = {
                    "source_file": "source/reference.pdf",
                    "source_pdf_page": title_page,
                    "method": "documentary crop; no award inference",
                    "status": "visible_reference_fallback",
                }
            else:
                family["reference_award_file"] = None
                family["reference_award_provenance"] = {
                    "source_file": "source/reference.pdf",
                    "source_pdf_page": title_page,
                    "method": "reference title page checked; no visible award found",
                    "status": "not_visible_in_reference",
                }

            region_id = str(family.get("region_id") or "")
            emblem_id = str(family.get("emblem_id") or "")
            if region_id and region_id not in first_region_hero and emblem_id in emblem_by_id:
                first_region_hero[region_id] = hero_id
                emblem_file = OUTPUT_DIR / "emblems" / f"{region_id}.png"
                if args.apply and (args.force or not emblem_file.is_file()):
                    with Image.open(rendered) as page:
                        save_crop(page, (0.23, 0.43, 0.77, 0.62), emblem_file)
                emblem = emblem_by_id[emblem_id]
                emblem["reference_fallback_file"] = emblem_file.relative_to(ROOT).as_posix()
                emblem["reference_fallback_provenance"] = {
                    "source_file": "source/reference.pdf",
                    "source_pdf_page": title_page,
                    "hero_id": hero_id,
                    "method": "documentary crop; no emblem inference",
                    "status": "visible_reference_fallback",
                }
            updated[hero_id] = family
            records.append(
                {
                    "hero_id": hero_id,
                    "reference_title_page": title_page,
                    "award_file": award_file.relative_to(ROOT).as_posix() if award_is_visible else None,
                    "region_id": region_id,
                    "status": "ready" if award_is_visible else "review_required",
                }
            )

    if args.apply:
        for path in family_paths:
            write_json(path, updated[path.stem])
        write_json(EMBLEMS_FILE, emblems)
        write_json(
            OUTPUT_DIR / "manifest.json",
            {
                "schema_version": 1,
                "source": "source/reference.pdf",
                "policy": "Documentary draft fallback; verified official assets remain preferred.",
                "families": records,
            },
        )
    print(f"families={len(records)} regions={len(first_region_hero)} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
