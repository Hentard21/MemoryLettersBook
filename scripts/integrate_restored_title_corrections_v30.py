#!/usr/bin/env python3
"""Prepare and integrate the owner's restored V30 title photographs.

The owner return package is treated as immutable input. ``--prepare`` copies
the selected white-background restorations into canonical production storage
and writes a CutItOut queue. After the local background remover has produced
the versioned raw PNGs, ``--integrate`` trims only empty alpha margins and
updates the corresponding production manifests. Previous cutouts are retained.
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
PACKAGE_ROOT = ROOT / "assets/manual-cutout-help-title-corrections"
QUEUE = ROOT / "assets/processed-flagships/restored-title-v30-queue.json"
VALIDATION = ROOT / "assets/processed-flagships/restored-title-v30-validation.json"
PLAN = ROOT / "assets/families/family-processing-plan.json"
PROCESSING_QUEUE = ROOT / "assets/processed-flagships/flagship-processing-queue.json"
CUTOUT_LOG = ROOT / "assets/processed-flagships/flagship-cutout-log.json"


JOBS: list[dict[str, Any]] = [
    {
        "hero_id": "hero-005",
        "asset_id": "hero-005_p027_image176",
        "source_name": "hero-005_title_portrait_white.png",
        "canonical_name": "hero-005_title_restored_white_v2.png",
        "raw_name": "hero-005_title_restored_v2_nobg_raw.png",
        "ready_name": "hero-005_title_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-006",
        "asset_id": "hero-006_p030_image184",
        "source_name": "hero-006_title_group_portrait_white.png",
        "canonical_name": "hero-006_title_group_restored_white_v2.png",
        "raw_name": "hero-006_title_group_restored_v2_nobg_raw.png",
        "ready_name": "hero-006_title_group_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-006",
        "asset_id": "hero-006_p030_image185",
        "source_name": "hero-006_supporting_boys_portrait_white.png",
        "canonical_name": "hero-006_supporting_boys_restored_white_v2.png",
        "raw_name": "hero-006_supporting_boys_restored_v2_nobg_raw.png",
        "ready_name": "hero-006_supporting_boys_restored_v2_ready_nobg.png",
        "role": "supporting_photo",
    },
    {
        "hero_id": "hero-009",
        "asset_id": "hero-009_p039_image225",
        "source_name": "hero-009_title_group_portrait_white_arm_fixed_detailed.png",
        "canonical_name": "hero-009_title_group_restored_white_v2.png",
        "raw_name": "hero-009_title_group_restored_v2_nobg_raw.png",
        "ready_name": "hero-009_title_group_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-022",
        "asset_id": "hero-022_p080_image409",
        "source_name": "hero-022_title_portrait_white.png",
        "canonical_name": "hero-022_title_restored_white_v2.png",
        "raw_name": "hero-022_title_restored_v2_nobg_raw.png",
        "ready_name": "hero-022_title_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-023",
        "asset_id": "hero-023_p083_image419",
        "source_name": "hero-023_title_portrait_white.png",
        "canonical_name": "hero-023_title_restored_white_v2.png",
        "raw_name": "hero-023_title_restored_v2_nobg_raw.png",
        "ready_name": "hero-023_title_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-035",
        "asset_id": "hero-035_p122_image581",
        "source_name": "hero-035_title_group_portrait_white_arms_fixed.png",
        "canonical_name": "hero-035_title_group_restored_white_v2.png",
        "raw_name": "hero-035_title_group_restored_v2_nobg_raw.png",
        "ready_name": "hero-035_title_group_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-039",
        "asset_id": "hero-039_p134_image631",
        "source_name": "hero-039_alt_p134_image631_portrait_white.png",
        "canonical_name": "hero-039_alt_title_restored_white_v2.png",
        "raw_name": "hero-039_alt_title_restored_v2_nobg_raw.png",
        "ready_name": "hero-039_alt_title_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
    {
        "hero_id": "hero-050",
        "asset_id": "hero-050_p169_image769",
        "source_name": "hero-050_title_group_portrait_white.png",
        "canonical_name": "hero-050_title_group_restored_white_v2.png",
        "raw_name": "hero-050_title_group_restored_v2_nobg_raw.png",
        "ready_name": "hero-050_title_group_restored_v2_ready_nobg.png",
        "role": "flagship",
        "selection_confidence": "high",
        "owner_approval": "approved_three_figure_restoration_2026-07-22",
        "queue_notes": "Владелец утвердил восстановленную трёхфигурную композицию для титульника; младенец и коляска сознательно не используются. Локальный CutItOut завершён.",
        "print_size_warning": "Owner-restored source is 1023x1537 px; locked placement is 184 mm high at approximately 200 effective ppi.",
    },
    {
        "hero_id": "hero-076",
        "asset_id": "hero-076_p254_image1101",
        "source_name": "hero-076_title_portrait_white.png",
        "canonical_name": "hero-076_title_restored_white_v2.png",
        "raw_name": "hero-076_title_restored_v2_nobg_raw.png",
        "ready_name": "hero-076_title_restored_v2_ready_nobg.png",
        "role": "flagship",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--integrate", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
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
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(job: dict[str, Any]) -> Path:
    return PACKAGE_ROOT / job["hero_id"] / job["source_name"]


def canonical_path(job: dict[str, Any]) -> Path:
    return ROOT / "assets/production-ready/flagship" / job["hero_id"] / job["canonical_name"]


def raw_path(job: dict[str, Any]) -> Path:
    return ROOT / "assets/processed-flagships" / job["hero_id"] / job["raw_name"]


def ready_path(job: dict[str, Any]) -> Path:
    return ROOT / "assets/processed-flagships" / job["hero_id"] / job["ready_name"]


def prepare(force: bool) -> None:
    queue = []
    for job in JOBS:
        source = source_path(job)
        destination = canonical_path(job)
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists() and not force:
            if sha256(destination) != sha256(source):
                raise FileExistsError(destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        queue.append(
            {
                "hero_id": job["hero_id"],
                "asset_id": job["asset_id"],
                "role": job["role"],
                "processing_source": repo_path(destination),
                "output_file": repo_path(raw_path(job)),
                "needs_cutout": True,
                "status": "ready_for_local_cutitout",
            }
        )
    write_json(
        QUEUE,
        {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "policy": "Owner-restored white sources; local CutItOut; versioned outputs.",
            "queue": queue,
        },
    )
    print(json.dumps({"prepared": len(queue), "queue": repo_path(QUEUE)}, indent=2))


def alpha_trim(source: Path, target: Path, force: bool) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        alpha = image.getchannel("A")
        extrema = alpha.getextrema()
        if extrema[0] >= 255:
            raise ValueError(f"CutItOut output is fully opaque: {source}")
        bbox = alpha.point(lambda value: 255 if value >= 4 else 0).getbbox()
        if not bbox:
            raise ValueError(f"CutItOut output is fully transparent: {source}")
        pad = max(8, round(max(image.size) * 0.012))
        crop = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(image.width, bbox[2] + pad),
            min(image.height, bbox[3] + pad),
        )
        output = image.crop(crop)
        if target.exists() and not force:
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        output.save(target, format="PNG", compress_level=6)
    return {
        "raw_file": repo_path(source),
        "raw_sha256": sha256(source),
        "ready_file": repo_path(target),
        "ready_sha256": sha256(target),
        "source_dimensions": [image.width, image.height],
        "ready_dimensions": [output.width, output.height],
        "alpha_extrema": list(extrema),
        "alpha_crop": list(crop),
    }


def find_entry(items: list[dict[str, Any]], hero_id: str) -> dict[str, Any]:
    matches = [item for item in items if item.get("hero_id") == hero_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one entry for {hero_id}; found {len(matches)}")
    return matches[0]


def find_asset(manifest: dict[str, Any], asset_id: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("assets", []) if item.get("asset_id") == asset_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one asset {asset_id}; found {len(matches)}")
    return matches[0]


def integrate(force: bool) -> None:
    plan = read_json(PLAN)
    queue = read_json(PROCESSING_QUEUE)
    cutout_log = read_json(CUTOUT_LOG)
    plan_items = plan["families"]
    queue_items = queue["queue"]
    results = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for job in JOBS:
        hero_id = job["hero_id"]
        result = alpha_trim(raw_path(job), ready_path(job), force)
        result.update(
            {
                "hero_id": hero_id,
                "asset_id": job["asset_id"],
                "role": job["role"],
                "restored_source": repo_path(canonical_path(job)),
                "restored_source_sha256": sha256(canonical_path(job)),
                "tool": "local CutItOut via Playwright; alpha-margin trim only",
                "status": "needs_visual_qa",
            }
        )
        results.append(result)

        production_path = ROOT / "content/production/families" / f"{hero_id}.json"
        assets_path = ROOT / "assets/families" / hero_id / "manifest/family-assets.json"
        production = read_json(production_path)
        assets = read_json(assets_path)
        asset = find_asset(assets, job["asset_id"])
        ready = result["ready_file"]
        canonical = result["restored_source"]

        asset.update(
            {
                "owner_return_file": repo_path(source_path(job)),
                "restored_source_file": canonical,
                "restored_source_sha256": result["restored_source_sha256"],
                "cutout_file": ready,
                "cutout_sha256": result["ready_sha256"],
                "cutout_width_px": result["ready_dimensions"][0],
                "cutout_height_px": result["ready_dimensions"][1],
                "cutout_tool": result["tool"],
                "cutout_status": "ready_for_draft_layout_pending_final_visual_qa",
            }
        )

        if job["role"] == "flagship":
            previous = production.get("flagship")
            production["flagship"] = ready
            production["flagship_processing_source"] = canonical
            production["flagship_max_height_mm_at_180_ppi"] = round(
                result["ready_dimensions"][1] / 180 * 25.4, 2
            )
            processing = production.setdefault("flagship_processing", {})
            processing.update(
                {
                    "owner_return_file": repo_path(source_path(job)),
                    "processing_source": canonical,
                    "restored_source_file": canonical,
                    "restored_source_sha256": result["restored_source_sha256"],
                    "cutout_file": ready,
                    "cutout_sha256": result["ready_sha256"],
                    "tool": result["tool"],
                    "status": "ready_for_draft_layout_pending_final_visual_qa",
                    "source_quality_policy": "OWNER_RESTORED_SOURCE",
                    "supersedes": previous,
                }
            )
            if job.get("owner_approval"):
                processing["owner_final_approval"] = job["owner_approval"]
            plan_entry = find_entry(plan_items, hero_id)
            plan_entry.setdefault("flagship_processing", {}).update(
                {
                    "preferred_processing_source": canonical,
                    "cutout_file": ready,
                    "cutout_sha256": result["ready_sha256"],
                    "cutout_status": "ready_for_draft_layout_pending_final_visual_qa",
                    "needs_cutout": False,
                }
            )
            if job.get("selection_confidence"):
                asset["selection_confidence"] = job["selection_confidence"]
                plan_entry["flagship_processing"]["selection_confidence"] = job[
                    "selection_confidence"
                ]
            queue_entry = find_entry(queue_items, hero_id)
            queue_entry.update(
                {
                    "processing_source": canonical,
                    "source_exists": True,
                    "expected_output": ready,
                    "output_exists": True,
                    "needs_cutout": False,
                    "route": "owner_restoration_then_local_cutitout_v30",
                    "status": "ready_for_manual_title_layout",
                }
            )
            if job.get("queue_notes"):
                queue_entry["notes"] = job["queue_notes"]
            if job.get("print_size_warning"):
                queue_entry["print_size_warning"] = job["print_size_warning"]
            if job.get("owner_approval"):
                queue_entry["status"] = "approved_for_v30_title_layout"
        else:
            prior = list(production.get("archive_photos", []))
            old = asset.get("cutout_file")
            # The asset record has just been updated, so also match the known
            # previous supporting filename used by V28.
            production["archive_photos"] = [
                ready
                if Path(str(value)).name == "hero-006_supporting_boys_ready_nobg.png"
                else value
                for value in prior
            ]
            for archive in find_entry(plan_items, hero_id).get("archive_assets", []):
                if archive.get("asset_id") == job["asset_id"]:
                    archive.update(
                        {
                            "restored_source_file": canonical,
                            "cutout_file": ready,
                            "cutout_status": "ready_for_draft_layout_pending_final_visual_qa",
                        }
                    )

        write_json(production_path, production)
        write_json(assets_path, assets)

    retained = [
        item
        for item in cutout_log.get("entries", [])
        if item.get("integration_batch") != "restored-title-corrections-v30"
    ]
    retained.extend(
        {
            "hero_id": item["hero_id"],
            "asset_id": item["asset_id"],
            "asset_type": item["role"],
            "source_file": item["restored_source"],
            "output_file": item["ready_file"],
            "tool": item["tool"],
            "status": "ready-for-draft-layout",
            "alpha_channel": True,
            "width_px": item["ready_dimensions"][0],
            "height_px": item["ready_dimensions"][1],
            "sha256": item["ready_sha256"],
            "visual_qa": "pending_final_spread_render",
            "integration_batch": "restored-title-corrections-v30",
        }
        for item in results
    )
    cutout_log["generated_at"] = timestamp
    cutout_log["entries"] = sorted(
        retained,
        key=lambda item: (str(item.get("hero_id", "")), str(item.get("output_file", ""))),
    )
    write_json(CUTOUT_LOG, cutout_log)
    plan["generated_at"] = timestamp
    queue["generated_at"] = timestamp
    write_json(PLAN, plan)
    write_json(PROCESSING_QUEUE, queue)
    prepared_queue = read_json(QUEUE)
    for item in prepared_queue.get("queue", []):
        item["needs_cutout"] = False
        item["status"] = "completed_local_cutitout"
    prepared_queue["completed_at"] = timestamp
    write_json(QUEUE, prepared_queue)
    write_json(
        VALIDATION,
        {
            "schema_version": 1,
            "generated_at": timestamp,
            "policy": "Nine owner-approved restorations plus one confirmed supporting photo; previous cutouts retained.",
            "rejected": {
                "hero-047": "No new restored white-background source was supplied.",
            },
            "entries": results,
        },
    )
    print(json.dumps({"integrated": len(results), "validation": repo_path(VALIDATION)}, indent=2))


def main() -> int:
    args = parse_args()
    if args.prepare:
        prepare(args.force)
    else:
        integrate(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
