#!/usr/bin/env python3
"""Stage and register owner-prepared title portraits from the next manual queue.

The command is deliberately conservative:

* only ``ready-for-manual`` entries already mapped in
  ``assets/manual-cutout-help-next/manifest.json`` are eligible;
* the owner's returned ``cutitout.png`` is copied, never moved or overwritten;
* staged white-background sources and transparent outputs use new ``v2`` names;
* registration is allowed only after a separate light/dark contact sheet exists;
* documentary masters and archive photographs are never modified.

The command is a dry run unless ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "assets/manual-cutout-help-next/manifest.json"
QUEUE = ROOT / "assets/processed-flagships/manual-owner-next-ingest-queue.json"
VALIDATION = ROOT / "assets/processed-flagships/manual-owner-next-cutout-validation.json"
CONTACT_SHEET = (
    ROOT
    / "workspace/reports/manual-flagship-cutouts-next/manual-cutout-light-dark-contact-sheet.png"
)
PROCESSING_PLAN = ROOT / "assets/families/family-processing-plan.json"
PROCESSING_QUEUE = ROOT / "assets/processed-flagships/flagship-processing-queue.json"
CUTOUT_LOG = ROOT / "assets/processed-flagships/flagship-cutout-log.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage", action="store_true")
    mode.add_argument("--register", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--needs-fix",
        action="append",
        default=[],
        help="hero_id whose generated mask must not be selected for layout",
    )
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


def eligible_entries(package: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for entry in package.get("entries", []):
        if entry.get("category") != "ready-for-manual":
            continue
        hero_id = str(entry.get("hero_id", ""))
        returned = (
            ROOT
            / "assets/manual-cutout-help-next/ready-for-manual"
            / hero_id
            / "cutitout.png"
        )
        if returned.is_file():
            result.append(entry)
    return sorted(result, key=lambda item: int(item["reference_order"]))


def paths_for(hero_id: str) -> tuple[Path, Path, Path]:
    owner_return = (
        ROOT
        / "assets/manual-cutout-help-next/ready-for-manual"
        / hero_id
        / "cutitout.png"
    )
    staged = (
        ROOT
        / "assets/production-ready/flagship"
        / hero_id
        / f"{hero_id}_manual_white_v2.png"
    )
    output = (
        ROOT
        / "assets/processed-flagships"
        / hero_id
        / f"{hero_id}_manual_v2_nobg.png"
    )
    return owner_return, staged, output


def copy_without_overwrite(source: Path, target: Path, apply: bool) -> str:
    if target.exists():
        if sha256(source) != sha256(target):
            raise FileExistsError(f"Refusing to replace different staged file: {target}")
        return "already_staged_same_sha256"
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return "staged" if apply else "would_stage"


def validate_white_source(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        corners = [
            rgb.getpixel((0, 0)),
            rgb.getpixel((width - 1, 0)),
            rgb.getpixel((0, height - 1)),
            rgb.getpixel((width - 1, height - 1)),
        ]
        return {
            "width_px": width,
            "height_px": height,
            "color_mode": image.mode,
            "white_corner_count": sum(
                all(channel >= 245 for channel in pixel) for pixel in corners
            ),
            "sha256": sha256(path),
        }


def validate_cutout(source: Path, output: Path) -> dict[str, Any]:
    if not source.is_file() or not output.is_file():
        raise FileNotFoundError(f"Missing source/output: {source} -> {output}")
    with Image.open(source) as before, Image.open(output) as after:
        if before.size != after.size:
            raise ValueError(f"Dimensions changed: {before.size} -> {after.size}")
        if after.format != "PNG" or "A" not in after.getbands():
            raise ValueError(f"Not a transparent PNG: {output}")
        alpha = after.getchannel("A")
        histogram = alpha.histogram()
        extrema = alpha.getextrema()
        if extrema[0] >= 255 or sum(histogram[:250]) == 0:
            raise ValueError(f"No usable transparency: {output}")
        if sum(histogram[1:]) == 0:
            raise ValueError(f"Fully transparent output: {output}")
        return {
            "width_px": after.width,
            "height_px": after.height,
            "alpha_extrema": list(extrema),
            "transparent_or_soft_pixels": sum(histogram[:250]),
            "source_sha256": sha256(source),
            "output_sha256": sha256(output),
        }


def layout_policy() -> dict[str, Any]:
    return {
        "preset": "v20-grounded-right",
        "reference_hero_id": "hero-014",
        "composition": "manual_title_page",
        "crop_mode": "waist",
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


def stage(package: dict[str, Any], apply: bool) -> dict[str, Any]:
    jobs = []
    for entry in eligible_entries(package):
        hero_id = str(entry["hero_id"])
        owner_return, staged, output = paths_for(hero_id)
        white = validate_white_source(owner_return)
        staging_status = copy_without_overwrite(owner_return, staged, apply)
        jobs.append(
            {
                "hero_id": hero_id,
                "reference_order": int(entry["reference_order"]),
                "owner_return_file": repo_path(owner_return),
                "owner_return_sha256": white["sha256"],
                "processing_source": repo_path(staged),
                "output_file": repo_path(output),
                "needs_cutout": True,
                "status": "ready",
                "staging_status": staging_status,
                "source_width_px": white["width_px"],
                "source_height_px": white["height_px"],
                "white_corner_count": white["white_corner_count"],
            }
        )
    queue = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": repo_path(PACKAGE),
        "policy": (
            "Only confirmed ready-for-manual owner returns are copied to distinct "
            "v2 processing sources; owner returns and documentary masters are immutable."
        ),
        "counts": {
            "eligible_owner_returns": len(jobs),
            "missing_ready_for_manual": int(package["counts"]["ready-for-manual"])
            - len(jobs),
        },
        "queue": jobs,
    }
    if apply:
        write_json(QUEUE, queue)
    return queue


def register(
    package: dict[str, Any], apply: bool, needs_fix: set[str]
) -> dict[str, Any]:
    if not QUEUE.is_file():
        raise FileNotFoundError(QUEUE)
    if not CONTACT_SHEET.is_file():
        raise FileNotFoundError(
            f"Light/dark contact sheet is required before registration: {CONTACT_SHEET}"
        )
    queue = read_json(QUEUE)
    jobs = list(queue.get("queue", []))
    known = {str(job["hero_id"]) for job in jobs}
    unknown_flags = needs_fix - known
    if unknown_flags:
        raise ValueError(f"Unknown --needs-fix hero IDs: {sorted(unknown_flags)}")

    timestamp = datetime.now(timezone.utc).isoformat()
    validations = []
    by_hero: dict[str, dict[str, Any]] = {}
    for job in jobs:
        hero_id = str(job["hero_id"])
        owner_return = ROOT / str(job["owner_return_file"])
        source = ROOT / str(job["processing_source"])
        output = ROOT / str(job["output_file"])
        if sha256(owner_return) != str(job["owner_return_sha256"]):
            raise ValueError(f"Owner return changed after staging: {owner_return}")
        validation = validate_cutout(source, output)
        passed = hero_id not in needs_fix
        record = {
            "hero_id": hero_id,
            "reference_order": int(job["reference_order"]),
            "owner_return_file": repo_path(owner_return),
            "processing_source": repo_path(source),
            "output_file": repo_path(output),
            **validation,
            "tool": "local CutItOut via Playwright",
            "technical_qa": "passed",
            "visual_qa": (
                "passed_on_light_and_dark_contact_sheet"
                if passed
                else "needs_manual_mask_fix"
            ),
            "layout_status": (
                "ready_for_draft_layout" if passed else "needs_fix"
            ),
            "owner_final_approval": "pending",
            "source_quality_policy": "OWNER_ACCEPTED_SOURCE_LIMIT",
        }
        validations.append(record)
        by_hero[hero_id] = record

    processing_plan = read_json(PROCESSING_PLAN)
    plan_by_hero = {item["hero_id"]: item for item in processing_plan["families"]}
    processing_queue = read_json(PROCESSING_QUEUE)
    queue_by_hero = {item["hero_id"]: item for item in processing_queue["queue"]}
    cutout_log = read_json(CUTOUT_LOG)
    package_by_hero = {item["hero_id"]: item for item in package["entries"]}
    changed: set[Path] = set()

    for hero_id, record in by_hero.items():
        production_path = ROOT / f"content/production/families/{hero_id}.json"
        family_path = ROOT / f"assets/families/{hero_id}/manifest/family-assets.json"
        production = read_json(production_path)
        family = read_json(family_path)
        ready = record["layout_status"] == "ready_for_draft_layout"

        if ready:
            production["flagship"] = record["output_file"]
            production["flagship_processing_source"] = record["processing_source"]
            production["flagship_max_height_mm_at_180_ppi"] = round(
                record["height_px"] / 180 * 25.4
            )
            production["flagship_processing"] = {
                "owner_return_file": record["owner_return_file"],
                "cutout_file": record["output_file"],
                "cutout_sha256": record["output_sha256"],
                "tool": record["tool"],
                "status": "ready_for_draft_layout",
                "owner_final_approval": "pending",
                "source_quality_policy": "OWNER_ACCEPTED_SOURCE_LIMIT",
            }
            production["flagship_layout"] = layout_policy()

        plan = plan_by_hero[hero_id]["flagship_processing"]
        plan["manual_owner_source"] = record["owner_return_file"]
        plan["preferred_processing_source"] = record["processing_source"]
        plan["cutout_file"] = record["output_file"]
        plan["cutout_sha256"] = record["output_sha256"]
        plan["cutout_status"] = record["layout_status"]
        plan["cutout_visual_qa"] = record["visual_qa"]
        plan["needs_cutout"] = not ready
        plan["needs_waist_crop"] = True
        plan["waist_crop_strategy"] = "manual_non_destructive_layout"
        plan["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"
        plan["layout"] = layout_policy()

        process_entry = queue_by_hero[hero_id]
        process_entry.setdefault(
            "automatic_output_superseded", process_entry.get("expected_output")
        )
        process_entry["processing_source"] = record["processing_source"]
        process_entry["expected_output"] = record["output_file"]
        process_entry["output_exists"] = True
        process_entry["route"] = "owner_clean_source_then_local_cutitout"
        process_entry["needs_cutout"] = not ready
        process_entry["needs_waist_crop"] = True
        process_entry["status"] = (
            "ready_for_manual_title_layout" if ready else "needs_manual_mask_fix"
        )
        process_entry["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"

        flagship_assets = [
            item
            for item in family.get("assets", [])
            if item.get("category") == "flagship"
            and item.get("layout_role") == "hero_flagship"
        ]
        if not flagship_assets:
            flagship_assets = [
                item
                for item in family.get("assets", [])
                if item.get("category") == "flagship"
            ]
        if len(flagship_assets) != 1:
            raise ValueError(
                f"Expected one canonical flagship record for {hero_id}; "
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
        asset["cutout_status"] = record["layout_status"]
        asset["source_quality_policy"] = "OWNER_ACCEPTED_SOURCE_LIMIT"
        asset["flagship_layout"] = layout_policy()

        package_entry = package_by_hero[hero_id]
        package_entry["owner_return_file"] = record["owner_return_file"]
        package_entry["owner_return_sha256"] = record["source_sha256"]
        package_entry["local_cutitout_output"] = record["output_file"]
        package_entry["local_cutitout_sha256"] = record["output_sha256"]
        package_entry["status"] = (
            "returned_and_ready_for_draft_layout" if ready else "returned_needs_fix"
        )

        if apply:
            write_json(production_path, production)
            write_json(family_path, family)
        changed.update((production_path, family_path))

    new_outputs = {item["output_file"] for item in validations}
    log_entries = [
        item
        for item in cutout_log.get("entries", [])
        if item.get("output_file") not in new_outputs
    ]
    log_entries.extend(
        {
            "hero_id": item["hero_id"],
            "source_file": item["processing_source"],
            "owner_return_file": item["owner_return_file"],
            "output_file": item["output_file"],
            "tool": item["tool"],
            "status": (
                "ready-for-draft-layout"
                if item["layout_status"] == "ready_for_draft_layout"
                else "needs-fix"
            ),
            "alpha_channel": True,
            "width_px": item["width_px"],
            "height_px": item["height_px"],
            "sha256": item["output_sha256"],
            "visual_qa": item["visual_qa"],
            "owner_final_approval": "pending",
            "notes": (
                "Confirmed owner-prepared white-background flagship; background "
                "removed locally. Final waist crop and placement remain manual."
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
    ready_count = sum(
        item["layout_status"] == "ready_for_draft_layout" for item in validations
    )
    package["generated_at"] = timestamp
    package["counts"]["owner_returned_files"] = len(validations)
    package["counts"]["local_cutitout_ready_for_draft_layout"] = ready_count
    package["counts"]["local_cutitout_needs_fix"] = len(validations) - ready_count

    validation_doc = {
        "schema_version": 1,
        "generated_at": timestamp,
        "policy": (
            "Technical alpha plus agent light/dark contact-sheet QA allow draft "
            "placement only; final title crop and owner approval remain pending."
        ),
        "contact_sheet": repo_path(CONTACT_SHEET),
        "counts": {
            "expected": len(validations),
            "technical_qa_passed": len(validations),
            "visual_qa_passed": ready_count,
            "needs_fix": len(validations) - ready_count,
            "owner_final_approval": 0,
        },
        "entries": sorted(validations, key=lambda item: item["reference_order"]),
    }
    shared = (
        (PROCESSING_PLAN, processing_plan),
        (PROCESSING_QUEUE, processing_queue),
        (CUTOUT_LOG, cutout_log),
        (PACKAGE, package),
        (VALIDATION, validation_doc),
    )
    changed.update(path for path, _ in shared)
    if apply:
        for path, value in shared:
            write_json(path, value)

    return {
        "schema_version": 1,
        "mode": "apply" if apply else "dry-run",
        "families": len(validations),
        "ready_for_draft_layout": ready_count,
        "needs_fix": len(validations) - ready_count,
        "changed_files": len(changed),
        "outputs": [item["output_file"] for item in validations],
    }


def main() -> int:
    args = parse_args()
    package = read_json(PACKAGE)
    if args.stage:
        result = stage(package, args.apply)
    else:
        result = register(package, args.apply, set(args.needs_fix))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
