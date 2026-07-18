#!/usr/bin/env python3
"""Ingest completed Gigapixel outputs into the production asset layer.

The command is conservative:

- dry-run by default;
- never overwrites a different destination file;
- keeps canonical family masters separate from print derivatives;
- updates generated manifests only in --apply mode;
- records known classification/QA exceptions explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


RESULT_RE = re.compile(r"^(?P<base>.+)-gigapixel-.+\.jpe?g$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=Path("assets/for-gigapixel"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/production-ready"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_original(result: Path, base: str) -> Path:
    matches = [
        candidate
        for candidate in result.parent.iterdir()
        if candidate.is_file()
        and candidate.stem == base
        and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and candidate != result
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one original for {result}, found {len(matches)}: {matches}"
        )
    return matches[0]


def classify(kind: str, hero_id: str, base: str) -> tuple[str, str, str]:
    """Return production role, QA status, and note."""
    if hero_id == "hero-026" and base == "hero-026_p092_image456":
        return (
            "archive",
            "ready_for_layout",
            "Corrected classification: this is a family photograph, not a drawing.",
        )
    if hero_id == "hero-036" and base == "hero-036_p126_image598":
        return (
            "drawings",
            "REVIEW_REQUIRED",
            "Hybrid handmade drawing/handwriting artifact; keep as documentary artifact.",
        )
    if base in {"hero-001_drawing_01_master", "hero-026_p092_image455"}:
        return (
            "drawings",
            "REVIEW_REQUIRED",
            "FaceAI was used on a real drawing; approve against the source before print.",
        )
    return kind, "ready_for_layout", "Gigapixel 2x result paired with its source."


def record_index(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for family in plan.get("families", []):
        hero_id = family["hero_id"]
        flagship = family.get("flagship_asset")
        if flagship:
            index[(hero_id, Path(flagship).stem)] = family["flagship_processing"]
        for key in ("archive_assets", "drawings"):
            for item in family.get(key, []):
                index[(hero_id, Path(item["file"]).stem)] = item
    return index


def update_family_manifest(
    project_root: Path,
    hero_id: str,
    base: str,
    production_role: str,
    production_file: str,
    result_hash: str,
    width: int,
    height: int,
    qa_status: str,
) -> None:
    path = (
        project_root
        / "assets"
        / "families"
        / hero_id
        / "manifest"
        / "family-assets.json"
    )
    data = load_json(path)
    matches = [
        item
        for item in data.get("assets", [])
        if item.get("file") and Path(item["file"]).stem == base
    ]
    if not matches:
        raise ValueError(f"No family manifest asset for {hero_id}/{base}")
    for item in matches:
        item["print_file"] = production_file
        item["print_sha256"] = result_hash
        item["print_width_px"] = width
        item["print_height_px"] = height
        item["gigapixel_status"] = "completed"
        item["print_qa_status"] = qa_status
        if hero_id == "hero-026" and base == "hero-026_p092_image456":
            item["file"] = (
                "assets/families/hero-026/archive-photos/"
                "hero-026_p092_image456.jpg"
            )
            item["category"] = "archive-photos"
            item["asset_type"] = "group"
            item["classification_override"] = (
                "Corrected after visual review: family photograph."
            )
    write_json(path, data)


def correct_hero_026_source(project_root: Path, apply: bool) -> tuple[Path, Path]:
    source = (
        project_root
        / "assets/families/hero-026/drawings/hero-026_p092_image456.jpg"
    )
    destination = (
        project_root
        / "assets/families/hero-026/archive-photos/hero-026_p092_image456.jpg"
    )
    if not source.exists() and destination.exists():
        return source, destination
    if not source.exists():
        raise ValueError(f"Classification source is missing: {source}")
    if destination.exists() and sha256(destination) != sha256(source):
        raise ValueError(f"Classification destination collision: {destination}")
    if apply and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
    return source, destination


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    staging = resolve(project_root, args.staging)
    output = resolve(project_root, args.output)
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"

    plan_path = project_root / "assets/families/family-processing-plan.json"
    plan = load_json(plan_path)
    index = record_index(plan)
    manifest_entries: list[dict[str, Any]] = []
    errors: list[str] = []
    moved = existing = 0

    try:
        source_before, source_after = correct_hero_026_source(project_root, apply)
        action = "RECLASSIFY" if source_before.exists() else "CLASSIFICATION VERIFIED"
        print(
            f"[{mode}] {action} {rel(source_before, project_root)} -> "
            f"{rel(source_after, project_root)}"
        )
    except ValueError as exc:
        errors.append(str(exc))

    results = sorted(staging.rglob("*.jpeg")) + sorted(staging.rglob("*.jpg"))
    results = [path for path in results if RESULT_RE.match(path.name)]

    # A completed batch is moved out of staging.  Treat a second invocation as
    # a successful verification instead of reporting 281 missing results.
    existing_manifest_path = output / "manifest.json"
    if not results and existing_manifest_path.exists():
        existing_manifest = load_json(existing_manifest_path)
        existing_entries = existing_manifest.get("assets", [])
        missing_print_files = [
            item.get("print_file", "")
            for item in existing_entries
            if not (project_root / item.get("print_file", "")).is_file()
        ]
        if len(existing_entries) == 281 and not missing_print_files:
            print(
                f"[{mode}] already ingested: 281/281 production files "
                f"verified via {rel(existing_manifest_path, project_root)}"
            )
            return 0
        errors.append(
            "Existing production manifest is incomplete: "
            f"entries={len(existing_entries)}, missing={len(missing_print_files)}"
        )

    for result in results:
        match = RESULT_RE.match(result.name)
        assert match is not None
        base = match.group("base")
        try:
            relative_parts = result.relative_to(staging).parts
            if len(relative_parts) < 3:
                raise ValueError(f"Unexpected staging path: {result}")
            staging_kind, hero_id = relative_parts[0], relative_parts[1]
            original = find_original(result, base)
            production_role, qa_status, note = classify(
                staging_kind, hero_id, base
            )
            destination = (
                output / production_role / hero_id / f"{base}_upscaled_2x.jpg"
            )
            result_hash = sha256(result)
            if destination.exists():
                if sha256(destination) != result_hash:
                    raise ValueError(f"Destination collision: {destination}")
                existing += 1
            else:
                print(f"[{mode}] MOVE {rel(result, project_root)} -> {rel(destination, project_root)}")
                if apply:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(result), str(destination))
                moved += 1

            image_path = destination if destination.exists() else result
            with Image.open(image_path) as image:
                width, height = image.size

            plan_record = index.get((hero_id, base))
            if plan_record is None:
                raise ValueError(f"No processing-plan record for {hero_id}/{base}")
            production_file = rel(destination, project_root)
            plan_record["needs_gigapixel"] = False
            plan_record["gigapixel_status"] = "completed"
            plan_record["print_file"] = production_file
            plan_record["print_sha256"] = result_hash
            plan_record["print_width_px"] = width
            plan_record["print_height_px"] = height
            plan_record["print_qa_status"] = qa_status

            source_file = plan_record.get("file")
            if source_file is None:
                family = next(
                    item
                    for item in plan["families"]
                    if item["hero_id"] == hero_id
                )
                source_file = family.get("flagship_asset")
            if hero_id == "hero-026" and base == "hero-026_p092_image456":
                source_file = (
                    "assets/families/hero-026/archive-photos/"
                    "hero-026_p092_image456.jpg"
                )

            manifest_entries.append(
                {
                    "hero_id": hero_id,
                    "asset_id": plan_record.get("asset_id") or base,
                    "asset_role": (
                        "documentary_artifact"
                        if hero_id == "hero-036"
                        and base == "hero-036_p126_image598"
                        else production_role
                    ),
                    "source_file": source_file,
                    "staging_original_file": rel(original, project_root),
                    "print_file": production_file,
                    "sha256": result_hash,
                    "width_px": width,
                    "height_px": height,
                    "scale": "2x",
                    "qa_status": qa_status,
                    "notes": note,
                }
            )

            if apply:
                update_family_manifest(
                    project_root,
                    hero_id,
                    base,
                    production_role,
                    production_file,
                    result_hash,
                    width,
                    height,
                    qa_status,
                )
        except (OSError, ValueError, StopIteration) as exc:
            errors.append(f"{result}: {exc}")

    if len(manifest_entries) != 281:
        errors.append(
            f"Expected 281 Gigapixel results, indexed {len(manifest_entries)}"
        )

    if apply and not errors:
        # Move the corrected item between logical plan collections.
        family_026 = next(
            item for item in plan["families"] if item["hero_id"] == "hero-026"
        )
        corrected = next(
            (
                item
                for item in family_026.get("drawings", [])
                if item.get("asset_id") == "hero-026_p092_image456"
            ),
            None,
        )
        if corrected is not None:
            family_026["drawings"].remove(corrected)
            corrected["file"] = (
                "assets/families/hero-026/archive-photos/"
                "hero-026_p092_image456.jpg"
            )
            corrected["needs_cutout"] = False
            corrected["classification_override"] = (
                "Corrected after visual review: family photograph."
            )
            family_026.setdefault("archive_assets", []).append(corrected)

        plan["gigapixel_ingest"] = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "results": len(manifest_entries),
            "manifest": "assets/production-ready/manifest.json",
            "status": "completed_with_review_flags",
        }
        write_json(plan_path, plan)
        write_json(
            output / "manifest.json",
            {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "assets/for-gigapixel",
                "policy": (
                    "Print layout uses print_file. source_file remains the "
                    "documentary master and is never overwritten."
                ),
                "counts": {
                    "total": len(manifest_entries),
                    "ready_for_layout": sum(
                        1
                        for item in manifest_entries
                        if item["qa_status"] == "ready_for_layout"
                    ),
                    "review_required": sum(
                        1
                        for item in manifest_entries
                        if item["qa_status"] == "REVIEW_REQUIRED"
                    ),
                },
                "assets": manifest_entries,
            },
        )

    for error in errors:
        print(f"ERROR: {error}")
    print(
        f"[{mode}] results={len(results)} indexed={len(manifest_entries)} "
        f"moved={moved} existing={existing} errors={len(errors)}"
    )
    if not apply:
        print("No files changed. Re-run with --apply after reviewing the plan.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
