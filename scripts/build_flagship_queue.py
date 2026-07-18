#!/usr/bin/env python3
"""Build an ordered Gigapixel/CutItOut queue for family flagship assets.

The queue is derived only from family-processing-plan.json; this script does not
infer processing needs from filenames or images. Default mode is a dry run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the ordered flagship processing queue from "
            "assets/families/family-processing-plan.json."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help="Input plan (default: assets/families/family-processing-plan.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Queue JSON output (default: "
            "assets/processed-flagships/flagship-processing-queue.json)."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write the queue JSON.")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview the queue without writing (default).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --apply to replace an existing generated queue file.",
    )
    return parser.parse_args()


def resolve_path(project_root: Path, value: Path | None, default: Path) -> Path:
    if value is None:
        return default.resolve()
    return value.resolve() if value.is_absolute() else (project_root / value).resolve()


def load_families(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"Processing plan does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(data, list):
        families = data
    elif isinstance(data, dict) and isinstance(data.get("families"), list):
        families = data["families"]
    elif isinstance(data, dict) and "hero_id" in data:
        families = [data]
    else:
        raise ValueError("Plan must be a list, a 'families' list, or one family record.")
    if not all(isinstance(item, dict) for item in families):
        raise ValueError("Every family plan record must be an object.")
    return families


def relative_or_absolute(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_asset(asset: str, project_root: Path) -> Path | None:
    if not asset:
        return None
    candidate = Path(asset)
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def expected_output(hero_id: str, source: Path | None, project_root: Path) -> str:
    stem = source.stem if source is not None else f"{hero_id}_flagship"
    output = (
        project_root
        / "assets"
        / "processed-flagships"
        / hero_id
        / f"{stem}_nobg.png"
    )
    return relative_or_absolute(output, project_root)


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    plan_path = resolve_path(
        project_root,
        args.plan,
        project_root / "assets" / "families" / "family-processing-plan.json",
    )
    output_path = resolve_path(
        project_root,
        args.output,
        project_root
        / "assets"
        / "processed-flagships"
        / "flagship-processing-queue.json",
    )

    try:
        families = load_families(plan_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    seen_heroes: set[str] = set()
    queue: list[dict[str, Any]] = []
    errors = 0
    for order, family in enumerate(families, start=1):
        hero_id = str(family.get("hero_id", "")).strip()
        if not hero_id:
            print(f"ERROR: family record #{order} has no hero_id", file=sys.stderr)
            errors += 1
            continue
        if hero_id in seen_heroes:
            print(f"ERROR: duplicate hero_id in plan: {hero_id}", file=sys.stderr)
            errors += 1
            continue
        seen_heroes.add(hero_id)

        processing = family.get("flagship_processing") or {}
        if not isinstance(processing, dict):
            print(
                f"ERROR: {hero_id}.flagship_processing must be an object",
                file=sys.stderr,
            )
            errors += 1
            continue

        needs_gigapixel = bool(processing.get("needs_gigapixel", False))
        needs_cutout = bool(processing.get("needs_cutout", False))
        needs_waist_crop = bool(processing.get("needs_waist_crop", False))
        operations: list[str] = []
        if needs_gigapixel:
            operations.append("gigapixel")
        if needs_cutout:
            operations.append("cutitout")
        if needs_waist_crop:
            operations.append("waist_crop_review")

        raw_asset = str(family.get("flagship_asset") or "").strip()
        processing_asset = str(
            processing.get("preferred_processing_source")
            or processing.get("print_file")
            or raw_asset
        ).strip()
        source = resolve_asset(processing_asset, project_root)
        source_exists = bool(source and source.is_file())
        expected_output_value = expected_output(
            hero_id,
            resolve_asset(raw_asset, project_root) or source,
            project_root,
        )
        output_exists = bool(
            resolve_asset(expected_output_value, project_root)
            and resolve_asset(expected_output_value, project_root).is_file()
        )
        if family.get("flagship_status") == "REVIEW_REQUIRED":
            status = "manual_review_required"
        elif not raw_asset:
            status = "missing_asset"
        elif not source_exists:
            status = "source_not_found"
        elif needs_cutout and output_exists:
            status = "cutout_generated_needs_review"
        elif operations:
            status = "queued"
        else:
            status = "no_processing_required"

        if needs_cutout and needs_gigapixel:
            route = "gigapixel_then_cutitout"
        elif needs_cutout:
            route = "cutitout_only"
        elif needs_gigapixel:
            route = "gigapixel_only"
        elif needs_waist_crop:
            route = "manual_crop_only"
        else:
            route = "none"

        queue.append(
            {
                "order": order,
                "hero_id": hero_id,
                "hero_name": family.get("hero_name", ""),
                "flagship_asset": raw_asset,
                "processing_source": processing_asset,
                "source_exists": source_exists,
                "route": route,
                "operations": operations,
                "needs_gigapixel": needs_gigapixel,
                "needs_cutout": needs_cutout,
                "needs_waist_crop": needs_waist_crop,
                "expected_output": expected_output_value,
                "output_exists": output_exists,
                "notes": processing.get("notes", ""),
                "print_size_warning": processing.get("print_size_warning", ""),
                "status": status,
            }
        )

    counts = {
        "total": len(queue),
        "gigapixel": sum(item["needs_gigapixel"] for item in queue),
        "cutitout": sum(item["needs_cutout"] for item in queue),
        "gigapixel_only": sum(item["route"] == "gigapixel_only" for item in queue),
        "missing_or_unresolved": sum(
            item["status"]
            in {"missing_asset", "source_not_found", "manual_review_required"}
            for item in queue
        ),
        "manual_review_required": sum(
            item["status"] == "manual_review_required" for item in queue
        ),
        "cutout_generated_needs_review": sum(
            item["status"] == "cutout_generated_needs_review" for item in queue
        ),
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_plan": relative_or_absolute(plan_path, project_root),
        "processing_order": "reference_order_from_family-processing-plan",
        "counts": counts,
        "queue": queue,
    }

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] plan: {plan_path}")
    print(f"[{mode}] output: {output_path}")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    for item in queue:
        print(
            f"{item['order']:03d} {item['hero_id']}: "
            f"{item['route']} [{item['status']}]"
        )

    if errors:
        print(f"ERROR: queue has {errors} validation error(s).", file=sys.stderr)
        return 1
    if args.apply:
        if output_path.exists() and not args.force:
            print(
                "ERROR: output exists and was not overwritten. "
                "Use --force only after reviewing it.",
                file=sys.stderr,
            )
            return 3
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {output_path}")
    else:
        print("No files changed. Re-run with --apply after reviewing the queue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
