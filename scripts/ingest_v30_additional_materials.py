#!/usr/bin/env python3
"""Ingest owner-supplied V30 Adina and provisional-family materials.

The script copies files byte-for-byte into stable project locations, records
technical metadata and provenance, and deliberately keeps the unidentified
family outside the canonical family list, TOC, and generated book.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageCms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(r"C:\Users\MarkII\Desktop\Доп материалы")
ADINA_SOURCE = SOURCE_ROOT / "Адина доп фото"
PENDING_SOURCE = SOURCE_ROOT / "Кто он"

ADINA_ROOT = PROJECT_ROOT / "assets" / "intro-people" / "adina-gallery"
PENDING_ROOT = PROJECT_ROOT / "assets" / "pending-families" / "pending-family-001"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        icc_bytes = image.info.get("icc_profile")
        profile_name = None
        profile_description = None
        if icc_bytes:
            try:
                profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
                profile_name = ImageCms.getProfileName(profile).strip() or None
                profile_description = ImageCms.getProfileDescription(profile).strip() or None
            except Exception:
                profile_name = "embedded_profile_unreadable"

        exif = image.getexif()
        return {
            "width_px": image.width,
            "height_px": image.height,
            "mode": image.mode,
            "format": image.format,
            "icc_profile_present": bool(icc_bytes),
            "icc_profile_name": profile_name,
            "icc_profile_description": profile_description,
            "icc_profile_sha256": hashlib.sha256(icc_bytes).hexdigest() if icc_bytes else None,
            "exif_camera_make": exif.get(271),
            "exif_camera_model": exif.get(272),
            "exif_color_space": exif.get(40961),
        }


def copy_asset(
    source: Path,
    destination: Path,
    *,
    asset_id: str,
    role: str,
    tier: str,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(source)
    if destination.exists() and sha256(destination) != source_hash:
        destination.unlink()
    if not destination.exists():
        shutil.copy2(source, destination)

    destination_hash = sha256(destination)
    if destination_hash != source_hash:
        raise RuntimeError(f"Byte verification failed for {destination}")

    return {
        "asset_id": asset_id,
        "role": role,
        "tier": tier,
        "source_file": str(source),
        "project_file": project_path(destination),
        "byte_copy_verified": True,
        "sha256": destination_hash,
        "file_size_bytes": destination.stat().st_size,
        "image": image_metadata(destination),
        "notes": notes or [],
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ingest_adina() -> dict[str, Any]:
    mappings = [
        {
            "stem": "DSC_0092",
            "asset_id": "adina-dsc-0092",
            "role": "primary_large_group_photo",
            "notes": [
                "Recommended as the large image in the three-slot Adina gallery.",
                "Original Nikon file is the documentary master; Topaz output is the print-placement candidate.",
            ],
        },
        {
            "stem": "DSC_0189",
            "asset_id": "adina-dsc-0189",
            "role": "supporting_project_event_photo",
            "notes": [
                "Project backdrop is visible; recommended as the upper supporting image.",
                "Original Nikon file is the documentary master; Topaz output is the print-placement candidate.",
            ],
        },
        {
            "stem": "DSC_4846",
            "asset_id": "adina-dsc-4846",
            "role": "supporting_live_conversation_photo",
            "notes": [
                "Recommended as the lower supporting image.",
                "Preserve the embedded colour profile; do not silently discard it during production conversion.",
            ],
        },
    ]

    assets: list[dict[str, Any]] = []
    for item in mappings:
        stem = item["stem"]
        assets.append(
            copy_asset(
                ADINA_SOURCE / f"{stem}.jpg",
                ADINA_ROOT / "originals" / f"adina_{stem.lower()}_master.jpg",
                asset_id=f"{item['asset_id']}-master",
                role=item["role"],
                tier="documentary_master",
                notes=item["notes"],
            )
        )
        assets.append(
            copy_asset(
                ADINA_SOURCE / f"{stem}-Hi-res-recover v2-2x-faceai v2.jpeg",
                ADINA_ROOT / "print" / f"adina_{stem.lower()}_topaz_2x.jpg",
                asset_id=f"{item['asset_id']}-print",
                role=item["role"],
                tier="topaz_print_candidate",
                notes=item["notes"],
            )
        )

    manifest = {
        "manifest_version": 1,
        "collection_id": "adina-gallery-v30",
        "subject": "Адина Арыковна",
        "status": "ready_for_intro_gallery_layout",
        "source_collection": str(ADINA_SOURCE),
        "copy_policy": "byte_for_byte_no_recompression",
        "layout_recommendation": {
            "large": "adina-dsc-0092-print",
            "supporting_upper": "adina-dsc-0189-print",
            "supporting_lower": "adina-dsc-4846-print",
        },
        "assets": assets,
        "warnings": [
            "No identity or event claims beyond visible/source-supported context were added.",
            "DSC_4846 carries an embedded colour profile that must be preserved or deliberately converted at print preflight.",
        ],
    }
    write_json(ADINA_ROOT / "manifest.json", manifest)
    return manifest


def ingest_pending_family() -> dict[str, Any]:
    source_files = {
        "letter_master": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43 (1).jpeg",
        "letter_print": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43 (1)-Hi-res-recover v2-2x.jpeg",
        "family_master": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43 (2).jpeg",
        "family_print": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43 (2)-Hi-res-recover v2-2x-faceai v2.jpeg",
        "award_master": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43.jpeg",
        "award_print": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.43-Hi-res-recover v2-2x-faceai v2.jpeg",
        "hero_master": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.44.jpeg",
        "hero_print": PENDING_SOURCE / "WhatsApp Image 2026-07-22 at 10.14.44-Hi-res-recover v2-2x-faceai v2.jpeg",
    }

    assets = [
        copy_asset(
            source_files["hero_master"],
            PENDING_ROOT / "flagship" / "pending-family-001_hero_portrait_master.jpg",
            asset_id="pending-family-001-hero-portrait-master",
            role="provisional_hero_flagship",
            tier="documentary_master",
            notes=["Identity is not yet confirmed; do not publish under an inferred name."],
        ),
        copy_asset(
            source_files["hero_print"],
            PENDING_ROOT / "flagship" / "pending-family-001_hero_portrait_topaz_2x.jpg",
            asset_id="pending-family-001-hero-portrait-print",
            role="provisional_hero_flagship",
            tier="topaz_print_candidate",
            notes=["Identity is not yet confirmed; do not publish under an inferred name."],
        ),
        copy_asset(
            source_files["family_master"],
            PENDING_ROOT / "archive-photos" / "pending-family-001_family_photo_master.jpg",
            asset_id="pending-family-001-family-photo-master",
            role="family_archive_photo",
            tier="documentary_master",
        ),
        copy_asset(
            source_files["family_print"],
            PENDING_ROOT / "archive-photos" / "pending-family-001_family_photo_topaz_2x.jpg",
            asset_id="pending-family-001-family-photo-print",
            role="family_archive_photo",
            tier="topaz_print_candidate",
        ),
        copy_asset(
            source_files["award_master"],
            PENDING_ROOT / "archive-photos" / "pending-family-001_evelina_award_portrait_master.jpg",
            asset_id="pending-family-001-evelina-award-master",
            role="child_with_award_and_framed_portrait",
            tier="documentary_master",
            notes=["Preferred for documentary details and inscriptions."],
        ),
        copy_asset(
            source_files["award_print"],
            PENDING_ROOT / "archive-photos" / "pending-family-001_evelina_award_portrait_topaz_2x.jpg",
            asset_id="pending-family-001-evelina-award-print",
            role="child_with_award_and_framed_portrait",
            tier="topaz_print_candidate",
            notes=["Inspect certificate/inscription details against the master before publication; enhancement may alter tiny text."],
        ),
        copy_asset(
            source_files["letter_master"],
            PENDING_ROOT / "letters" / "pending-family-001_letter_evelina_2024-09-08_master.jpg",
            asset_id="pending-family-001-letter-master",
            role="physical_handwritten_letter",
            tier="documentary_master",
        ),
        copy_asset(
            source_files["letter_print"],
            PENDING_ROOT / "letters" / "pending-family-001_letter_evelina_2024-09-08_topaz_2x.jpg",
            asset_id="pending-family-001-letter-print",
            role="physical_handwritten_letter",
            tier="topaz_print_candidate",
        ),
    ]

    transcription = (
        "Мой папа-герой!\n"
        "Мой папа-герой, потому что он\n"
        "отдал свою жизнь за нашу Родину.\n"
        "Папа был командиром, при выполнении\n"
        "боевой задачи был смертельно ранен.\n"
        "Он награждён орденом мужества\n"
        "посмертно. Папа всегда мечтал\n"
        "получить орден мужества, так же у\n"
        "него есть и другие награды.\n"
        "Мой папа сильный, добрый, справедливый,\n"
        "Честный.\n"
        "Мы с мамой скучаем по папе и нам его\n"
        "очень нехватает.\n"
        "\n"
        "Эвелина 7 лет.\n"
        "8.09.2024 г.\n"
    )
    transcript_path = PENDING_ROOT / "transcriptions" / "pending-family-001_letter_evelina_2024-09-08.txt"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcription, encoding="utf-8")

    transcript_record = {
        "transcription_id": "pending-family-001-letter-evelina-2024-09-08",
        "letter_file": "assets/pending-families/pending-family-001/letters/pending-family-001_letter_evelina_2024-09-08_master.jpg",
        "transcription_file": project_path(transcript_path),
        "status": "manual_visual_transcription_complete_review_required",
        "author_spelling_preserved": True,
        "silent_corrections_applied": False,
        "uncertain_tokens": [],
        "notes": [
            "Line breaks follow the visible manuscript.",
            "Author forms such as 'так же' and 'нехватает' are preserved.",
            "A second human comparison against the physical scan is required before publication.",
        ],
        "text": transcription,
        "sha256": sha256(transcript_path),
    }
    write_json(PENDING_ROOT / "transcriptions" / "pending-family-001_letter_evelina_2024-09-08.json", transcript_record)

    manifest = {
        "manifest_version": 1,
        "provisional_family_id": "pending-family-001",
        "display_nickname": "Безымянный",
        "hero_name": None,
        "children": ["Эвелина"],
        "child_age_from_letter": 7,
        "letter_date_as_written": "8.09.2024",
        "region_id": None,
        "city_id": None,
        "award_id": None,
        "canonical_order": None,
        "canonical_family_match": None,
        "status": "REVIEW_REQUIRED",
        "review_flags": [
            "REVIEW_REQUIRED_IDENTITY",
            "REVIEW_REQUIRED_REGION",
            "REVIEW_REQUIRED_CITY",
            "REVIEW_REQUIRED_CANONICAL_ORDER",
            "REVIEW_REQUIRED_TRANSCRIPTION_PROOFREAD",
        ],
        "publication_policy": {
            "include_in_canonical_toc": False,
            "include_in_generated_pdf": False,
            "include_in_canonical_family_count": False,
            "reason": "The packet is coherent but has not been matched to the owner-approved canonical order.",
        },
        "provenance": {
            "source_collection": str(PENDING_SOURCE),
            "ingested_as_new_packet": True,
            "attached_to_existing_hero": False,
            "borrowing_materials_from_other_families_allowed": False,
        },
        "evidence_notes": [
            "The packet contains its own physical handwritten letter signed 'Эвелина 7 лет' and dated '8.09.2024 г.'.",
            "The packet contains a hero portrait, a family photograph, and a photograph of the child holding an award case and framed portrait.",
            "The letter states that the father was a commander, was mortally wounded during a combat mission, and was awarded the Order of Courage posthumously; these statements remain letter-source claims until owner verification.",
            "No person name, region, city, or canonical position was inferred.",
        ],
        "assets": assets,
        "letters": [
            {
                "letter_id": "pending-family-001-letter-evelina-2024-09-08",
                "master_asset_id": "pending-family-001-letter-master",
                "print_asset_id": "pending-family-001-letter-print",
                "transcription_id": transcript_record["transcription_id"],
                "master_file": "assets/pending-families/pending-family-001/letters/pending-family-001_letter_evelina_2024-09-08_master.jpg",
                "print_file": "assets/pending-families/pending-family-001/letters/pending-family-001_letter_evelina_2024-09-08_topaz_2x.jpg",
                "transcription_file": transcript_record["transcription_file"],
            }
        ],
    }
    write_json(PENDING_ROOT / "manifest" / "pending-family-001.json", manifest)
    return manifest


def validate(adina: dict[str, Any], pending: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    all_records = list(adina["assets"]) + list(pending["assets"])
    for asset in all_records:
        destination = PROJECT_ROOT / asset["project_file"]
        if not destination.is_file():
            errors.append(f"Missing copied asset: {asset['project_file']}")
        elif sha256(destination) != asset["sha256"]:
            errors.append(f"Hash mismatch: {asset['project_file']}")

    if pending["publication_policy"]["include_in_generated_pdf"]:
        errors.append("Pending family must not be included in generated PDF")
    if pending["provenance"]["attached_to_existing_hero"]:
        errors.append("Pending family must not be attached to an existing hero")
    if not pending["letters"]:
        errors.append("Pending family letter unexpectedly missing")

    report = {
        "status": "passed" if not errors else "failed",
        "copied_asset_count": len(all_records),
        "adina_asset_count": len(adina["assets"]),
        "pending_family_asset_count": len(pending["assets"]),
        "pending_family_in_canonical_output": False,
        "errors": errors,
    }
    write_json(PENDING_ROOT / "manifest" / "ingestion-validation.json", report)
    if errors:
        raise RuntimeError("; ".join(errors))
    return report


def main() -> None:
    if not ADINA_SOURCE.is_dir() or not PENDING_SOURCE.is_dir():
        raise FileNotFoundError(f"Expected owner material below {SOURCE_ROOT}")
    adina = ingest_adina()
    pending = ingest_pending_family()
    report = validate(adina, pending)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
