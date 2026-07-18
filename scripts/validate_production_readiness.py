#!/usr/bin/env python3
"""Validate the reset asset graph before serial layout or Git handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXCLUDED_PARTS = {".git", ".tools", "node_modules", "graphify-out", "archived"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    errors: list[str] = []

    json_files = [
        path
        for path in root.rglob("*.json")
        if not any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts)
    ]
    for path in json_files:
        try:
            load(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid JSON {path.relative_to(root)}: {exc}")

    reference = root / "source/reference.pdf"
    expected_hash = (root / "source/reference.sha256").read_text(
        encoding="utf-8-sig"
    ).split()[0].upper()
    if not reference.is_file() or sha256(reference) != expected_hash:
        errors.append("source/reference.pdf does not match source/reference.sha256")
    if not (root / "design/cover-v1/artwork/cover-art.png").is_file():
        errors.append("Approved cover art is missing")

    order = load(root / "content/manifests/reference-family-order-reset.json")
    order_families = order.get("families", order)
    order_ids = [item["hero_id"] for item in order_families]
    processing = load(root / "assets/families/family-processing-plan.json")
    families = processing.get("families", [])
    family_ids = [item["hero_id"] for item in families]
    if len(family_ids) != 74 or family_ids != order_ids:
        errors.append("Family processing order does not match the 74-family reference order")

    selected = 0
    for family in families:
        hero_id = family["hero_id"]
        flagship = family.get("flagship_asset")
        if flagship:
            selected += 1
            if not (root / flagship).is_file():
                errors.append(f"Missing flagship: {hero_id} {flagship}")
        elif family.get("flagship_status") != "REVIEW_REQUIRED":
            errors.append(f"Unresolved flagship lacks REVIEW_REQUIRED: {hero_id}")
        for key in ("archive_assets", "drawings", "letters", "transcriptions"):
            for item in family.get(key, []):
                value = item.get("file") or item.get("transcription_file")
                if value and not (root / value).is_file():
                    errors.append(f"Missing {key} file: {hero_id} {value}")
                print_file = item.get("print_file")
                if print_file and not (root / print_file).is_file():
                    errors.append(f"Missing print derivative: {hero_id} {print_file}")

    family_manifest_files = sorted(
        (root / "assets/families").glob("hero-*/manifest/family-assets.json")
    )
    if len(family_manifest_files) != 74:
        errors.append(f"Expected 74 family manifests, found {len(family_manifest_files)}")
    family_asset_records = 0
    for path in family_manifest_files:
        manifest = load(path)
        for item in manifest.get("assets", []):
            family_asset_records += 1
            for key in ("file", "source_file", "print_file"):
                value = item.get(key)
                if value and not (root / value).is_file():
                    errors.append(f"Broken {key} in {path.relative_to(root)}: {value}")

    production = load(root / "assets/production-ready/manifest.json")
    production_entries = production.get("assets", [])
    if len(production_entries) != 281:
        errors.append(
            f"Expected 281 production derivatives, found {len(production_entries)}"
        )
    for item in production_entries:
        for key in ("source_file", "staging_original_file", "print_file"):
            value = item.get(key)
            if value and not (root / value).is_file():
                errors.append(f"Broken production {key}: {value}")

    letters = load(root / "assets/families/letters-transcriptions-index.json")
    letter_entries = letters.get("entries", [])
    for item in letter_entries:
        if not (root / item["letter_file"]).is_file():
            errors.append(f"Missing physical letter: {item['letter_file']}")
        transcription = item.get("transcription_file")
        if transcription and not (root / transcription).is_file():
            errors.append(f"Missing transcription: {transcription}")

    cutouts = load(root / "assets/processed-flagships/cutout-validation.json")
    cutout_entries = cutouts.get("entries", [])
    if len(cutout_entries) != 58:
        errors.append(f"Expected 58 validated cutouts, found {len(cutout_entries)}")
    for item in cutout_entries:
        if not (root / item["output_file"]).is_file():
            errors.append(f"Missing cutout: {item['output_file']}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_with_documented_blockers" if not errors else "failed",
        "json_files_validated": len(json_files),
        "families": len(families),
        "selected_flagships": selected,
        "review_required_flagships": sum(
            item.get("flagship_status") == "REVIEW_REQUIRED" for item in families
        ),
        "family_asset_records": family_asset_records,
        "physical_letters_indexed": len(letter_entries),
        "missing_transcriptions": sum(
            item.get("status") == "missing" for item in letter_entries
        ),
        "production_derivatives": len(production_entries),
        "validated_cutouts": len(cutout_entries),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.apply:
        output = root / "project-reset/reports/production-readiness-validation.json"
        output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {output}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
