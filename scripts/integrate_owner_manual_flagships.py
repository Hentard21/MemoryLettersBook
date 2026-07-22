#!/usr/bin/env python3
"""Register owner-prepared title portraits after local CutItOut processing.

The command is a dry run unless ``--apply`` is provided.  It never replaces the
documentary master, the owner's returned white-background PNG, or an older mask.
It only selects the distinct ``*_manual_nobg.png`` derivative for draft layout
and records its provenance in the existing family registries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
INGEST_QUEUE = ROOT / "assets/processed-flagships/manual-owner-ingest-queue.json"
PROCESSING_PLAN = ROOT / "assets/families/family-processing-plan.json"
PROCESSING_QUEUE = ROOT / "assets/processed-flagships/flagship-processing-queue.json"
CUTOUT_LOG = ROOT / "assets/processed-flagships/flagship-cutout-log.json"
PACKAGE_MANIFEST = ROOT / "assets/manual-cutout-help/manifest.json"
VALIDATION = ROOT / "assets/processed-flagships/manual-owner-cutout-validation.json"
CONTACT_SHEET = (
    ROOT
    / "workspace/reports/manual-flagship-cutouts/manual-cutout-contact-sheet.png"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def repo_path(path: Path | str) -> str:
    value = Path(path)
    if not value.is_absolute():
        value = ROOT / value
    return value.resolve().relative_to(ROOT).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cutout(source: Path, output: Path) -> dict[str, Any]:
    if not source.is_file() or not output.is_file():
        raise FileNotFoundError(f"Missing source/output: {source} -> {output}")
    with Image.open(source) as before, Image.open(output) as after:
        if before.size != after.size:
            raise ValueError(
                f"CutItOut changed dimensions: {before.size} -> {after.size}"
            )
        if after.format != "PNG" or "A" not in after.getbands():
            raise ValueError(f"Not a transparent PNG: {output}")
        alpha = after.getchannel("A")
        histogram = alpha.histogram()
        extrema = alpha.getextrema()
        if extrema[0] >= 255 or sum(histogram[:250]) == 0:
            raise ValueError(f"No usable transparency in {output}")
        if sum(histogram[1:]) == 0:
            raise ValueError(f"Cutout is fully transparent: {output}")
        return {
            "width_px": after.width,
            "height_px": after.height,
            "alpha_extrema": list(extrema),
            "transparent_or_soft_pixels": sum(histogram[:250]),
            "source_sha256": sha256(source),
            "output_sha256": sha256(output),
        }


def owner_return_for(hero_id: str) -> str:
    candidates = []
    for path in (ROOT / "assets/manual-cutout-help").rglob("*.png"):
        if hero_id not in path.parts:
            continue
        if path.name.startswith(("01_", "02_", "03_")):
            continue
        candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(
            f"Expected one owner-returned PNG for {hero_id}, found {len(candidates)}"
        )
    return repo_path(candidates[0])


def layout_policy(hero_id: str | None = None) -> dict[str, Any]:
    full_body_sources = {
        "hero-003",
        "hero-011",
        "hero-015",
        "hero-024",
        "hero-029",
        "hero-047",
        "hero-051",
    }
    needs_layout_crop = hero_id in full_body_sources if hero_id else True
    return {
        "preset": "v20-grounded-right",
        "reference_hero_id": "hero-014",
        "composition": "manual_title_page",
        "crop_mode": "waist",
        "source_pose": "full_body" if needs_layout_crop else "waist_or_bust",
        "display_height_mm": 250 if needs_layout_crop else 193,
        "bottom_mm": -65 if needs_layout_crop else -1,
        "right_mm": 3 if needs_layout_crop else 0,
        "grounding": "bottom",
        "object_fit": "intrinsic_height",
        "object_position": "center bottom",
        "blend_mode": "normal",
        "protect": [
            "face",
            "hair",
            "hands",
            "weapons",
            "straps",
            "uniform",
            "insignia",
            "awards",
            "held_objects",
        ],
        "status": "manual_title_layout_required",
    }


def main() -> int:
    args = parse_args()
    ingest = read_json(INGEST_QUEUE)
    jobs = list(ingest.get("queue", []))
    if len(jobs) != 13:
        raise ValueError(f"Expected 13 owner-returned jobs, found {len(jobs)}")
    if not CONTACT_SHEET.is_file():
        raise FileNotFoundError(CONTACT_SHEET)

    timestamp = datetime.now(timezone.utc).isoformat()
    validations: list[dict[str, Any]] = []
    by_hero: dict[str, dict[str, Any]] = {}
    for job in jobs:
        hero_id = str(job["hero_id"])
        source = ROOT / str(job["processing_source"])
        output = ROOT / str(job["output_file"])
        validation = validate_cutout(source, output)
        record = {
            "hero_id": hero_id,
            "owner_return_file": owner_return_for(hero_id),
            "processing_source": repo_path(source),
            "output_file": repo_path(output),
            **validation,
            "tool": "local CutItOut via Playwright",
            "technical_qa": "passed",
            "visual_qa": "passed_on_light_and_dark_contact_sheet",
            "owner_final_approval": "pending",
            "source_quality_policy": "OWNER_ACCEPTED_SOURCE_LIMIT",
        }
        validations.append(record)
        by_hero[hero_id] = record

    processing_plan = read_json(PROCESSING_PLAN)
    plan_families = {item["hero_id"]: item for item in processing_plan["families"]}
    processing_queue = read_json(PROCESSING_QUEUE)
    queue_by_hero = {item["hero_id"]: item for item in processing_queue["queue"]}
    cutout_log = read_json(CUTOUT_LOG)
    package = read_json(PACKAGE_MANIFEST)
    package_by_hero = {item["hero_id"]: item for item in package["entries"]}

    changed_paths: set[Path] = set()
    for hero_id, record in by_hero.items():
        production_path = ROOT / f"content/production/families/{hero_id}.json"
        family_manifest_path = (
            ROOT / f"assets/families/{hero_id}/manifest/family-assets.json"
        )
        production = read_json(production_path)
        family_manifest = read_json(family_manifest_path)

        production["flagship"] = record["output_file"]
        production["flagship_processing_source"] = record["processing_source"]
        production["flagship_processing"] = {
            "owner_return_file": record["owner_return_file"],
            "cutout_file": record["output_file"],
            "cutout_sha256": record["output_sha256"],
            "tool": record["tool"],
            "status": "ready_for_draft_layout",
            "owner_final_approval": "pending",
            "source_quality_policy": "OWNER_ACCEPTED_SOURCE_LIMIT",
        }
        production["flagship_layout"] = layout_policy(hero_id)

        plan = plan_families[hero_id]["flagship_processing"]
        plan["manual_owner_source"] = record["owner_return_file"]
        plan["preferred_processing_source"] = record["processing_source"]
        plan["cutout_file"] = record["output_file"]
        plan["cutout_sha256"] = record["output_sha256"]
        plan["cutout_status"] = "ready_for_draft_layout"
        plan["cutout_visual_qa"] = record["visual_qa"]
        plan["needs_cutout"] = False
        plan["needs_waist_crop"] = True
        plan["waist_crop_strategy"] = "manual_non_destructive_layout"
        plan["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"
        plan["layout"] = layout_policy(hero_id)

        queue_entry = queue_by_hero[hero_id]
        queue_entry.setdefault(
            "automatic_output_superseded", queue_entry.get("expected_output")
        )
        queue_entry["processing_source"] = record["processing_source"]
        queue_entry["expected_output"] = record["output_file"]
        queue_entry["output_exists"] = True
        queue_entry["route"] = "owner_clean_source_then_local_cutitout"
        queue_entry["needs_cutout"] = False
        queue_entry["needs_waist_crop"] = True
        queue_entry["status"] = "ready_for_manual_title_layout"
        queue_entry["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"

        flagship_assets = [
            item
            for item in family_manifest.get("assets", [])
            if item.get("category") == "flagship"
            and item.get("layout_role") == "hero_flagship"
        ]
        if not flagship_assets:
            flagship_assets = [
                item
                for item in family_manifest.get("assets", [])
                if item.get("category") == "flagship"
            ]
        if len(flagship_assets) != 1:
            raise ValueError(
                f"Expected one canonical flagship manifest record for {hero_id}, "
                f"found {len(flagship_assets)}"
            )
        asset = flagship_assets[0]
        asset["owner_return_file"] = record["owner_return_file"]
        asset["cutout_source_file"] = record["processing_source"]
        asset["cutout_file"] = record["output_file"]
        asset["cutout_sha256"] = record["output_sha256"]
        asset["cutout_width_px"] = record["width_px"]
        asset["cutout_height_px"] = record["height_px"]
        asset["cutout_tool"] = record["tool"]
        asset["cutout_status"] = "ready_for_draft_layout"
        asset["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"
        asset["flagship_layout"] = layout_policy(hero_id)

        package_entry = package_by_hero[hero_id]
        package_entry["owner_return_file"] = record["owner_return_file"]
        package_entry["local_cutitout_output"] = record["output_file"]
        package_entry["local_cutitout_sha256"] = record["output_sha256"]
        package_entry["status"] = "returned_and_ready_for_draft_layout"

        if args.apply:
            write_json(production_path, production)
            write_json(family_manifest_path, family_manifest)
        changed_paths.update((production_path, family_manifest_path))

    log_entries = list(cutout_log.get("entries", []))
    new_outputs = {item["output_file"] for item in validations}
    log_entries = [
        item for item in log_entries if item.get("output_file") not in new_outputs
    ]
    log_entries.extend(
        {
            "hero_id": item["hero_id"],
            "source_file": item["processing_source"],
            "owner_return_file": item["owner_return_file"],
            "output_file": item["output_file"],
            "tool": item["tool"],
            "status": "ready-for-draft-layout",
            "alpha_channel": True,
            "width_px": item["width_px"],
            "height_px": item["height_px"],
            "sha256": item["output_sha256"],
            "visual_qa": item["visual_qa"],
            "owner_final_approval": "pending",
            "notes": (
                "Owner-prepared clean white-background source; background removed "
                "locally. Final waist crop and placement are manual title-page work."
            ),
        }
        for item in validations
    )
    cutout_log["schema_version"] = max(int(cutout_log.get("schema_version", 1)), 3)
    cutout_log["generated_at"] = timestamp
    cutout_log["entries"] = sorted(
        log_entries,
        key=lambda item: (str(item.get("hero_id", "")), str(item.get("output_file", ""))),
    )
    cutout_log["counts"] = {
        "entries": len(cutout_log["entries"]),
        "ready_for_draft_layout": sum(
            item.get("status") == "ready-for-draft-layout"
            for item in cutout_log["entries"]
        ),
        "needs_fix": sum(
            item.get("status") == "needs-fix" for item in cutout_log["entries"]
        ),
        "approved_final": sum(
            item.get("status") == "approved" for item in cutout_log["entries"]
        ),
    }

    processing_plan.setdefault("layout_policy", {})[
        "title_flagship_manual_rule"
    ] = layout_policy()
    processing_plan["layout_policy"]["source_quality_policy"] = (
        "OWNER_ACCEPTED_SOURCE_LIMIT: report real effective DPI; do not invent detail."
    )
    processing_queue["generated_at"] = timestamp
    processing_queue["counts"] = {
        "families": len(processing_queue["queue"]),
        "ready_for_manual_title_layout": sum(
            item.get("status") == "ready_for_manual_title_layout"
            for item in processing_queue["queue"]
        ),
        "pending_or_review": sum(
            item.get("status") != "ready_for_manual_title_layout"
            for item in processing_queue["queue"]
        ),
    }
    package["generated_at"] = timestamp
    package["counts"]["owner_returned_files"] = 13
    package["counts"]["local_cutitout_ready_for_draft_layout"] = 13
    package["policy"] = (
        "Original package files and owner returns are immutable. The owner returns "
        "were staged by copy and processed locally into distinct transparent PNGs."
    )

    validation_document = {
        "schema_version": 1,
        "generated_at": timestamp,
        "policy": (
            "Technical alpha and agent contact-sheet QA allow draft placement only. "
            "Owner final approval remains pending."
        ),
        "contact_sheet": repo_path(CONTACT_SHEET),
        "counts": {
            "expected": len(jobs),
            "technical_qa_passed": len(validations),
            "visual_contact_sheet_passed": len(validations),
            "owner_final_approval": 0,
        },
        "entries": sorted(validations, key=lambda item: item["hero_id"]),
    }

    shared_outputs = (
        (PROCESSING_PLAN, processing_plan),
        (PROCESSING_QUEUE, processing_queue),
        (CUTOUT_LOG, cutout_log),
        (PACKAGE_MANIFEST, package),
        (VALIDATION, validation_document),
    )
    changed_paths.update(path for path, _ in shared_outputs)
    if args.apply:
        for path, value in shared_outputs:
            write_json(path, value)

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "families": len(validations),
                "changed_files": len(changed_paths),
                "outputs": [item["output_file"] for item in validations],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
