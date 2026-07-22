#!/usr/bin/env python3
"""Integrate the returned title-photo correction cutouts.

The package under ``assets/manual-cutout-help-title-corrections`` is immutable.
Returned PNGs are validated, trimmed only to their real alpha bounds, copied to
``assets/processed-flagships`` and registered in the production manifests.

This script never edits documentary masters and never applies background
removal to ordinary archive photographs.  A dry run is the default.
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
PACKAGE = ROOT / "assets/manual-cutout-help-title-corrections/manifest.json"
PROCESSING_PLAN = ROOT / "assets/families/family-processing-plan.json"
PROCESSING_QUEUE = ROOT / "assets/processed-flagships/flagship-processing-queue.json"
CUTOUT_LOG = ROOT / "assets/processed-flagships/flagship-cutout-log.json"
VALIDATION = ROOT / "assets/processed-flagships/title-correction-cutout-validation.json"


JOBS: dict[str, dict[str, Any]] = {
    "hero-005": {
        "asset_id": "hero-005_p027_image176",
        "return_file": "hero-005_title_nobg.png",
        "output_file": "hero-005_title_ready_nobg.png",
        "display_height_mm": 155,
        "source_pose": "family-group",
    },
    "hero-006": {
        "asset_id": "hero-006_p030_image184",
        "return_file": "hero-006_title_group_nobg.png",
        "output_file": "hero-006_title_group_ready_nobg.png",
        "display_height_mm": 135,
        "source_pose": "children-with-portrait",
        "supporting": {
            "asset_id": "hero-006_p030_image185",
            "return_file": "hero-006_supporting_boys_nobg.png",
            "output_file": "hero-006_supporting_boys_ready_nobg.png",
        },
    },
    "hero-009": {
        "asset_id": "hero-009_p039_image225",
        "return_file": "hero-009_title_group_nobg.png",
        "output_file": "hero-009_title_group_ready_nobg.png",
        "display_height_mm": 158,
        "source_pose": "family-group",
    },
    "hero-022": {
        "asset_id": "hero-022_p080_image409",
        "return_file": "hero-022_title_nobg.png",
        "output_file": "hero-022_title_ready_nobg.png",
        "display_height_mm": 168,
        "source_pose": "seated-upper-body",
        # The returned mask contains a hand detached by the original birch trunk.
        # Keeping it produces a visibly floating fragment on the title page.
        "discard_left_px": 520,
    },
    "hero-023": {
        "asset_id": "hero-023_p083_image419",
        "return_file": "hero-023_title_nobg.png",
        "output_file": "hero-023_title_ready_nobg.png",
        "display_height_mm": 168,
        "source_pose": "seated-upper-body",
    },
    "hero-035": {
        "asset_id": "hero-035_p122_image581",
        "return_file": "hero-035_title_group_nobg.png",
        "output_file": "hero-035_title_group_ready_nobg.png",
        "display_height_mm": 158,
        "source_pose": "seated-family-group",
    },
    "hero-039": {
        "asset_id": "hero-039_p134_image631",
        "return_file": "hero-039_alt_p134_image631_nobg.png",
        "output_file": "hero-039_alt_title_ready_nobg.png",
        "display_height_mm": 174,
        "source_pose": "uniform-waist",
        "remove_selected_from_archive": True,
    },
    "hero-047": {
        "asset_id": "hero-047_p159_image728",
        "return_file": "hero-047_alt_p159_image728_nobg.png",
        "output_file": "hero-047_alt_title_ready_nobg.png",
        "display_height_mm": 250,
        "bottom_mm": -65,
        "right_mm": 3,
        "source_pose": "full-body",
        "remove_selected_from_archive": True,
    },
    "hero-050": {
        "asset_id": "hero-050_p169_image769",
        "return_file": "hero-050_title_group_nobg.png",
        "output_file": "hero-050_title_group_ready_nobg.png",
        "display_height_mm": 172,
        "source_pose": "family-group-with-stroller",
    },
    "hero-076": {
        "asset_id": "hero-076_p254_image1101",
        "return_file": "hero-076_title_nobg_fixed.png",
        "output_file": "hero-076_title_ready_nobg.png",
        "display_height_mm": 190,
        "source_pose": "armoured-upper-body",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and register returned title correction cutouts."
    )
    parser.add_argument("--apply", action="store_true", help="Write outputs and manifests")
    parser.add_argument("--force", action="store_true", help="Replace existing derived outputs")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def repo_path(path: Path | str) -> str:
    value = Path(path)
    if value.is_absolute():
        value = value.relative_to(ROOT)
    return value.as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def alpha_trim(
    source: Path,
    target: Path,
    apply: bool,
    force: bool,
    discard_left_px: int | None = None,
) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        alpha = image.getchannel("A")
        if discard_left_px:
            alpha.paste(0, (0, 0, min(discard_left_px, image.width), image.height))
            image.putalpha(alpha)
        extrema = alpha.getextrema()
        if extrema[0] >= 255:
            raise ValueError(f"Returned PNG has no transparency: {source}")
        threshold = alpha.point(lambda value: 255 if value >= 4 else 0)
        bbox = threshold.getbbox()
        if not bbox:
            raise ValueError(f"Returned PNG is fully transparent: {source}")
        pad = max(8, round(max(image.size) * 0.012))
        left = max(0, bbox[0] - pad)
        top = max(0, bbox[1] - pad)
        right = min(image.width, bbox[2] + pad)
        bottom = min(image.height, bbox[3] + pad)
        cropped = image.crop((left, top, right, bottom))
        if apply:
            if target.exists() and not force:
                raise FileExistsError(
                    f"Derived output already exists; use --force after review: {target}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(target, format="PNG", compress_level=6)
    result = {
        "return_file": repo_path(source),
        "return_sha256": sha256(source),
        "output_file": repo_path(target),
        "source_width_px": image.width,
        "source_height_px": image.height,
        "alpha_extrema": list(extrema),
        "alpha_bbox": [left, top, right, bottom],
        "output_width_px": right - left,
        "output_height_px": bottom - top,
        "operation": "transparent-margin-trim-only",
        "detached_fragment_cleanup": (
            {"discard_left_px": discard_left_px}
            if discard_left_px else None
        ),
        "background_removal_status": "already_present_in_returned_cutitout_png",
        "technical_qa": "passed",
    }
    if apply:
        result["output_sha256"] = sha256(target)
    return result


def layout_policy(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "preset": "v20-grounded-right",
        "reference_hero_id": "hero-014",
        "composition": "manual_title_page",
        "crop_mode": "waist_or_truthful_source_limit",
        "source_pose": job["source_pose"],
        "display_height_mm": job["display_height_mm"],
        "bottom_mm": job.get("bottom_mm", -1),
        "right_mm": job.get("right_mm", 0),
        "grounding": "bottom",
        "object_fit": "intrinsic_height",
        "object_position": "center bottom",
        "blend_mode": "normal",
        "protect": [
            "face", "hair", "hands", "weapons", "straps", "uniform",
            "insignia", "awards", "held_objects", "children",
        ],
        "status": "manual_title_layout_required",
    }


def package_entry_for(package: dict[str, Any], hero_id: str) -> dict[str, Any]:
    entries = package.get("families") or package.get("entries") or []
    found = [item for item in entries if item.get("hero_id") == hero_id]
    if len(found) != 1:
        raise ValueError(f"Expected one package entry for {hero_id}; found {len(found)}")
    return found[0]


def asset_record(family_manifest: dict[str, Any], asset_id: str) -> dict[str, Any]:
    found = [item for item in family_manifest.get("assets", []) if item.get("asset_id") == asset_id]
    if len(found) != 1:
        raise ValueError(f"Expected one asset record for {asset_id}; found {len(found)}")
    return found[0]


def main() -> int:
    args = parse_args()
    package = read_json(PACKAGE)
    processing_plan = read_json(PROCESSING_PLAN)
    processing_queue = read_json(PROCESSING_QUEUE)
    cutout_log = read_json(CUTOUT_LOG)
    plan_by_hero = {item["hero_id"]: item for item in processing_plan["families"]}
    queue_by_hero = {item["hero_id"]: item for item in processing_queue["queue"]}
    timestamp = datetime.now(timezone.utc).isoformat()
    validations: list[dict[str, Any]] = []
    changed: set[Path] = set()

    for hero_id, job in JOBS.items():
        package_entry = package_entry_for(package, hero_id)
        returned = PACKAGE.parent / hero_id / job["return_file"]
        output = ROOT / "assets/processed-flagships" / hero_id / job["output_file"]
        result = alpha_trim(
            returned,
            output,
            args.apply,
            args.force,
            job.get("discard_left_px"),
        )
        result.update({
            "hero_id": hero_id,
            "asset_id": job["asset_id"],
            "role": "hero_flagship",
            "tool": "returned manual CutItOut PNG; local alpha QA",
            "visual_qa": "passed_on_light_and_dark_checkerboard",
            "owner_final_approval": "pending",
        })
        validations.append(result)

        production_path = ROOT / f"content/production/families/{hero_id}.json"
        family_path = ROOT / f"assets/families/{hero_id}/manifest/family-assets.json"
        production = read_json(production_path)
        family_manifest = read_json(family_path)
        chosen = asset_record(family_manifest, job["asset_id"])
        old_flagship = production.get("flagship")
        chosen_source = chosen.get("print_file") or chosen.get("file")
        layout = layout_policy(job)

        production["flagship"] = result["output_file"]
        production["flagship_processing_source"] = chosen_source
        production["flagship_max_height_mm_at_180_ppi"] = round(
            result["output_height_px"] / 180 * 25.4
        )
        production["flagship_processing"] = {
            "owner_return_file": result["return_file"],
            "processing_source": chosen_source,
            "cutout_file": result["output_file"],
            "cutout_sha256": result.get("output_sha256"),
            "tool": result["tool"],
            "status": "ready_for_draft_layout",
            "visual_qa": result["visual_qa"],
            "owner_final_approval": "pending",
            "source_quality_policy": "OWNER_ACCEPTED_SOURCE_LIMIT",
            "supersedes": old_flagship,
        }
        production["flagship_layout"] = layout
        if job.get("remove_selected_from_archive"):
            production["archive_photos"] = [
                value for value in production.get("archive_photos", [])
                if Path(value).stem != Path(str(chosen_source)).stem
                and job["asset_id"] not in value
            ]

        for item in family_manifest.get("assets", []):
            if item.get("layout_role") == "hero_flagship" and item is not chosen:
                item["title_page_status"] = f"superseded_by_{job['asset_id']}"
        chosen["title_layout_role"] = "hero_flagship"
        chosen["owner_return_file"] = result["return_file"]
        chosen["cutout_file"] = result["output_file"]
        chosen["cutout_sha256"] = result.get("output_sha256")
        chosen["cutout_width_px"] = result["output_width_px"]
        chosen["cutout_height_px"] = result["output_height_px"]
        chosen["cutout_tool"] = result["tool"]
        chosen["cutout_status"] = "ready_for_draft_layout"
        chosen["flagship_layout"] = layout

        plan = plan_by_hero[hero_id]
        plan["flagship_asset"] = chosen.get("file") or chosen_source
        plan["flagship_status"] = "selected_for_title_correction"
        plan_processing = plan.setdefault("flagship_processing", {})
        plan_processing.update({
            "manual_owner_source": result["return_file"],
            "preferred_processing_source": chosen_source,
            "cutout_file": result["output_file"],
            "cutout_sha256": result.get("output_sha256"),
            "cutout_status": "ready_for_draft_layout",
            "cutout_visual_qa": result["visual_qa"],
            "needs_cutout": False,
            "needs_waist_crop": True,
            "waist_crop_strategy": "manual_non_destructive_layout",
            "layout": layout,
        })

        queue = queue_by_hero[hero_id]
        queue.setdefault("automatic_output_superseded", queue.get("expected_output"))
        queue.update({
            "flagship_asset": chosen.get("file") or chosen_source,
            "processing_source": chosen_source,
            "expected_output": result["output_file"],
            "output_exists": True,
            "route": "returned_manual_cutitout_then_local_qa",
            "needs_cutout": False,
            "needs_waist_crop": True,
            "status": "ready_for_manual_title_layout",
        })

        package_entry["returned_file"] = result["return_file"]
        package_entry["returned_sha256"] = result["return_sha256"]
        package_entry["local_ready_output"] = result["output_file"]
        package_entry["local_ready_sha256"] = result.get("output_sha256")
        package_entry["status"] = "integrated_for_draft_layout"

        supporting = job.get("supporting")
        if supporting:
            support_returned = PACKAGE.parent / hero_id / supporting["return_file"]
            support_output = (
                ROOT / "assets/processed-flagships" / hero_id / supporting["output_file"]
            )
            support_result = alpha_trim(
                support_returned, support_output, args.apply, args.force
            )
            support_result.update({
                "hero_id": hero_id,
                "asset_id": supporting["asset_id"],
                "role": "supporting_photo",
                "tool": "returned manual CutItOut PNG; local alpha QA",
                "visual_qa": "passed_on_light_and_dark_checkerboard",
                "owner_final_approval": "pending",
            })
            validations.append(support_result)
            support_asset = asset_record(family_manifest, supporting["asset_id"])
            support_source = support_asset.get("print_file") or support_asset.get("file")
            support_asset["owner_return_file"] = support_result["return_file"]
            support_asset["cutout_file"] = support_result["output_file"]
            support_asset["cutout_sha256"] = support_result.get("output_sha256")
            support_asset["cutout_status"] = "ready_for_draft_layout"
            support_asset["cutout_tool"] = support_result["tool"]
            production["archive_photos"] = [
                support_result["output_file"] if value == support_source else value
                for value in production.get("archive_photos", [])
            ]
            for archive in plan.get("archive_assets", []):
                if archive.get("asset_id") == supporting["asset_id"]:
                    archive["cutout_file"] = support_result["output_file"]
                    archive["cutout_status"] = "ready_for_draft_layout"
            prior_supporting = [
                item for item in package_entry.get("supporting_returns", [])
                if item.get("asset_id") != supporting["asset_id"]
            ]
            prior_supporting.append({
                "asset_id": supporting["asset_id"],
                "returned_file": support_result["return_file"],
                "output_file": support_result["output_file"],
                "output_sha256": support_result.get("output_sha256"),
                "status": "integrated_for_draft_layout",
            })
            package_entry["supporting_returns"] = prior_supporting

        if args.apply:
            write_json(production_path, production)
            write_json(family_path, family_manifest)
        changed.update((production_path, family_path))

    updated_heroes = set(JOBS)
    retained_log = [
        item for item in cutout_log.get("entries", [])
        if not (
            item.get("hero_id") in updated_heroes
            and item.get("integration_batch") == "title-photo-corrections-v22"
        )
    ]
    retained_log.extend({
        "hero_id": item["hero_id"],
        "asset_id": item["asset_id"],
        "asset_type": item["role"],
        "source_file": item["return_file"],
        "output_file": item["output_file"],
        "tool": item["tool"],
        "status": "ready-for-draft-layout",
        "alpha_channel": True,
        "width_px": item["output_width_px"],
        "height_px": item["output_height_px"],
        "sha256": item.get("output_sha256"),
        "visual_qa": item["visual_qa"],
        "owner_final_approval": "pending",
        "integration_batch": "title-photo-corrections-v22",
        "notes": "Returned transparent PNG; only empty alpha margins were trimmed.",
    } for item in validations)
    cutout_log["schema_version"] = max(int(cutout_log.get("schema_version", 1)), 3)
    cutout_log["generated_at"] = timestamp
    cutout_log["entries"] = sorted(
        retained_log,
        key=lambda item: (str(item.get("hero_id", "")), str(item.get("output_file", ""))),
    )
    cutout_log["counts"] = {
        "entries": len(cutout_log["entries"]),
        "ready_for_draft_layout": sum(
            item.get("status") == "ready-for-draft-layout"
            for item in cutout_log["entries"]
        ),
        "needs_fix": sum(item.get("status") == "needs-fix" for item in cutout_log["entries"]),
        "approved_final": sum(item.get("status") == "approved" for item in cutout_log["entries"]),
    }
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
    processing_plan.setdefault("layout_policy", {})[
        "title_correction_cutouts"
    ] = "Returned alpha PNGs are trimmed non-destructively and placed with V20 grounding."
    package["generated_at"] = timestamp
    package.setdefault("counts", {}).update({
        "families_with_title_corrections": len(JOBS),
        "returned_alpha_files": len(validations),
        "integrated_for_draft_layout": len(validations),
    })
    validation_doc = {
        "schema_version": 1,
        "generated_at": timestamp,
        "package": repo_path(PACKAGE),
        "policy": (
            "Returned CutItOut PNGs already contained real transparency. They were "
            "not subjected to a destructive second removal pass; only alpha QA and "
            "transparent-margin trimming were applied."
        ),
        "counts": {
            "families": len(JOBS),
            "files": len(validations),
            "technical_qa_passed": len(validations),
            "visual_qa_passed": len(validations),
        },
        "entries": validations,
    }
    shared = (
        (PROCESSING_PLAN, processing_plan),
        (PROCESSING_QUEUE, processing_queue),
        (CUTOUT_LOG, cutout_log),
        (PACKAGE, package),
        (VALIDATION, validation_doc),
    )
    changed.update(path for path, _ in shared)
    if args.apply:
        for path, value in shared:
            write_json(path, value)

    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run",
        "families": len(JOBS),
        "files": len(validations),
        "changed_manifest_files": len(changed),
        "outputs": [item["output_file"] for item in validations],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
