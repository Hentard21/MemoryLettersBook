#!/usr/bin/env python3
"""Extract verified intro signatures and event photos from the owner PDF.

The PDF is treated as the source of truth for asset ownership and order.  The
script keeps each embedded image in its native encoded form and also creates a
lossless PNG working copy for layout/Gigapixel.  It is a dry run unless
``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets" / "intro-people"

SIGNATURE_JOBS = (
    {
        "asset_id": "shumilov_signature",
        "reference_page": 5,
        "image_index": 1,
        "person_id": "shumilov",
    },
    {
        "asset_id": "makarychev_signature",
        "reference_page": 6,
        "image_index": 1,
        "person_id": "makarychev",
    },
)

SHARED_PHOTO_JOBS = (
    {
        "asset_id": "intro_shared_p008_image01",
        "reference_page": 8,
        "image_index": 0,
        "event_date": "9 июня 2025 года",
        "caption": "9 июня 2025 года в зале торжественных мероприятий Министерства обороны Российской Федерации министр обороны РФ Андрей Белоусов наградил Сопредседателя Президиума Межгосударственного Союза Городов-Героев генерал-полковника Л. В. Шумилова орденом Александра Невского.",
    },
    {
        "asset_id": "intro_shared_p008_image02",
        "reference_page": 8,
        "image_index": 1,
        "event_date": "25 июля 2025 года",
        "caption": "«Диалог поколений. Герои и дети»: полковник В. Л. Быков из Санкт-Петербурга, Артемий из Улан-Удэ, генерал-полковник Л. В. из Москвы, Кирилл из города Североморск Мурманской области, генерал-лейтенант А. А. Макарычев из Москвы. Музей ВМФ России.",
    },
    {
        "asset_id": "intro_shared_p008_image03",
        "reference_page": 8,
        "image_index": 2,
        "event_date": "7 мая 2025 года",
        "caption": "«Диалог поколений. Герои и дети». ГБУ «Московский дом национальностей».",
    },
    {
        "asset_id": "intro_shared_p009_image01",
        "reference_page": 9,
        "image_index": 0,
        "event_date": "24 декабря 2025 года",
        "caption": "Всероссийская общественно-патриотическая акция «Диалог поколений. Герои и дети» в Культурном центре Главного управления Дипломатического корпуса Министерства иностранных дел Российской Федерации.",
    },
    {
        "asset_id": "intro_shared_p009_image02",
        "reference_page": 9,
        "image_index": 1,
        "event_date": "24 декабря 2025 года",
        "caption": "Диалог между Героем Социалистического Труда, генерал-лейтенантом А. А. Макарычевым и сыном Героя СВО из Ханты-Мансийского автономного округа Тимуром Мухаметгалиным.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Owner-supplied книга0707 PDF")
    parser.add_argument("--apply", action="store_true", help="Write extracted assets")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def extension_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix if suffix else ".bin"


def extract_job(
    reader: PdfReader,
    job: dict[str, Any],
    native_dir: Path,
    working_dir: Path,
    apply: bool,
) -> dict[str, Any]:
    page_number = int(job["reference_page"])
    image_index = int(job["image_index"])
    images = list(reader.pages[page_number - 1].images)
    if image_index >= len(images):
        raise IndexError(
            f"Page {page_number} has {len(images)} images; index {image_index} is unavailable"
        )
    source_image = images[image_index]
    native_extension = extension_for(source_image.name)
    native_file = native_dir / f"{job['asset_id']}_native{native_extension}"
    working_file = working_dir / f"{job['asset_id']}_source.png"
    image = Image.open(BytesIO(source_image.data))
    image.load()

    if apply:
        native_dir.mkdir(parents=True, exist_ok=True)
        working_dir.mkdir(parents=True, exist_ok=True)
        native_file.write_bytes(source_image.data)
        if image.mode not in {"RGB", "RGBA", "L", "LA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(working_file, format="PNG", optimize=False)

    return {
        **job,
        "embedded_name": source_image.name,
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "native_file": native_file.relative_to(PROJECT_ROOT).as_posix(),
        "working_file": working_file.relative_to(PROJECT_ROOT).as_posix(),
        "status": "extracted_from_reference" if apply else "planned",
    }


def build_signature_display(record: dict[str, Any], apply: bool) -> dict[str, Any]:
    """Create a tightly cropped transparent derivative without touching source files."""
    source = PROJECT_ROOT / record["working_file"]
    display = ASSET_ROOT / "signatures" / f"{record['asset_id']}_display.png"
    record = {**record, "display_file": display.relative_to(PROJECT_ROOT).as_posix()}
    if not apply:
        return record

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        ink = ImageOps.invert(rgb.convert("L")).point(lambda value: min(255, value * 3))
        bbox = ink.getbbox()
        if bbox is None:
            raise ValueError(f"No signature ink found in {source}")
        margin = max(4, round(max(image.size) * 0.025))
        left = max(0, bbox[0] - margin)
        top = max(0, bbox[1] - margin)
        right = min(image.width, bbox[2] + margin)
        bottom = min(image.height, bbox[3] + margin)
        cropped_rgb = rgb.crop((left, top, right, bottom))
        cropped_alpha = ink.crop((left, top, right, bottom))
        rgba = cropped_rgb.convert("RGBA")
        rgba.putalpha(cropped_alpha)
        rgba.save(display, format="PNG", optimize=False)
        record.update(
            {
                "display_width": rgba.width,
                "display_height": rgba.height,
                "display_status": "transparent_derivative_from_verified_signature",
            }
        )
    return record


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    reader = PdfReader(source)
    signature_native = ASSET_ROOT / "signatures" / "source-native"
    signature_working = ASSET_ROOT / "signatures"
    shared_native = ASSET_ROOT / "shared-events" / "source-native"
    shared_working = ASSET_ROOT / "shared-events" / "for-gigapixel"

    signatures = [
        build_signature_display(
            extract_job(reader, job, signature_native, signature_working, args.apply),
            args.apply,
        )
        for job in SIGNATURE_JOBS
    ]
    shared_photos = [
        extract_job(reader, job, shared_native, shared_working, args.apply)
        for job in SHARED_PHOTO_JOBS
    ]
    manifest = {
        "schema_version": 1,
        "source_file": str(source),
        "source_sha256": sha256(source),
        "extraction_mode": "native embedded bytes plus lossless PNG working copy",
        "signatures": signatures,
        "shared_photos": shared_photos,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.apply:
        manifest_file = ASSET_ROOT / "intro-reference-assets.json"
        manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {manifest_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
