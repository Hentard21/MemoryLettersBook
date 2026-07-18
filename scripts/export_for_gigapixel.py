#!/usr/bin/env python3
"""Copy classified family assets into a reviewable Gigapixel queue.

Sources are never moved or modified. Existing output files are never overwritten.
The default mode is a dry run; pass --apply to perform copies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".bmp",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

SOURCE_TO_OUTPUT = {
    "flagship": "flagship",
    "archive-photos": "archive",
    "drawings": "drawings",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy family flagship, archive and drawing assets into "
            "assets/for-gigapixel/. Defaults to a safe dry run."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--families-root",
        type=Path,
        help="Family source root (default: assets/families).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Gigapixel output root (default: assets/for-gigapixel).",
    )
    parser.add_argument(
        "--hero",
        action="append",
        default=[],
        help="Export only this hero ID; repeat for several heroes.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help=(
            "Processing plan (default: assets/families/family-processing-plan.json). "
            "Only assets explicitly marked needs_gigapixel are exported."
        ),
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Ignore the processing plan and export every source image category.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply", action="store_true", help="Create folders and copy files."
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned copies without writing (default).",
    )
    return parser.parse_args()


def resolve_path(project_root: Path, value: Path | None, default: Path) -> Path:
    if value is None:
        return default.resolve()
    return value.resolve() if value.is_absolute() else (project_root / value).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_label(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def existing_hashes(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            result.setdefault(sha256(path), path)
    return result


def choose_collision_free_destination(destination: Path, file_hash: str) -> Path:
    if not destination.exists():
        return destination
    return destination.with_name(
        f"{destination.stem}__{file_hash[:8]}{destination.suffix.lower()}"
    )


def load_allowed_assets(plan_path: Path, project_root: Path) -> set[Path]:
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"Processing plan does not exist: {plan_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid processing plan: {exc}") from exc

    families = data.get("families") if isinstance(data, dict) else data
    if not isinstance(families, list):
        raise ValueError("Processing plan must contain a families list.")

    allowed: set[Path] = set()
    for family in families:
        if not isinstance(family, dict):
            continue
        processing = family.get("flagship_processing") or {}
        flagship = family.get("flagship_asset")
        if flagship and bool(processing.get("needs_gigapixel", False)):
            allowed.add((project_root / str(flagship)).resolve())
        for key in ("archive_assets", "drawings"):
            for asset in family.get(key) or []:
                if isinstance(asset, dict) and asset.get("file") and bool(
                    asset.get("needs_gigapixel", False)
                ):
                    allowed.add((project_root / str(asset["file"])).resolve())
    return allowed


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    families_root = resolve_path(
        project_root,
        args.families_root,
        project_root / "assets" / "families",
    )
    output_root = resolve_path(
        project_root,
        args.output,
        project_root / "assets" / "for-gigapixel",
    )
    plan_path = resolve_path(
        project_root,
        args.plan,
        project_root / "assets" / "families" / "family-processing-plan.json",
    )
    try:
        allowed_assets = None if args.include_all else load_allowed_assets(
            plan_path, project_root
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    selected_heroes = set(args.hero)
    if not families_root.is_dir():
        print(f"ERROR: families root does not exist: {families_root}", file=sys.stderr)
        return 2

    family_dirs = [
        path
        for path in sorted(families_root.iterdir())
        if path.is_dir()
        and path.name.startswith("hero-")
        and (not selected_heroes or path.name in selected_heroes)
    ]
    found_names = {path.name for path in family_dirs}
    missing_heroes = sorted(selected_heroes - found_names)
    if missing_heroes:
        print(
            f"ERROR: unknown hero IDs: {', '.join(missing_heroes)}", file=sys.stderr
        )
        return 2

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] source: {families_root}")
    print(f"[{mode}] output: {output_root}")

    copied = duplicates = unsupported = collisions = 0
    for family_root in family_dirs:
        hero_id = family_root.name
        for source_category, output_category in SOURCE_TO_OUTPUT.items():
            source_root = family_root / source_category
            target_root = output_root / output_category / hero_id
            known_hashes = existing_hashes(target_root)
            planned_hashes: set[str] = set()
            if not source_root.is_dir():
                continue
            for source in sorted(source_root.rglob("*")):
                if not source.is_file() or source.name.startswith("."):
                    continue
                if source.stat().st_size == 0 or source.suffix.lower() not in IMAGE_EXTENSIONS:
                    unsupported += 1
                    print(f"SKIP    unsupported/empty {relative_label(source, project_root)}")
                    continue
                if allowed_assets is not None and source.resolve() not in allowed_assets:
                    print(f"SKIP    not queued {relative_label(source, project_root)}")
                    continue

                file_hash = sha256(source)
                if file_hash in known_hashes or file_hash in planned_hashes:
                    duplicates += 1
                    print(
                        f"SKIP    duplicate content {relative_label(source, project_root)}"
                    )
                    continue

                destination = target_root / source.name
                if destination.exists():
                    destination = choose_collision_free_destination(destination, file_hash)
                    collisions += 1
                    if destination.exists():
                        print(
                            "ERROR: unresolved destination collision: "
                            f"{destination}",
                            file=sys.stderr,
                        )
                        continue

                print(
                    f"COPY    {relative_label(source, project_root)} -> "
                    f"{relative_label(destination, project_root)}"
                )
                if args.apply:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                planned_hashes.add(file_hash)
                copied += 1

    print(
        "Summary: "
        f"heroes={len(family_dirs)}, copies={copied}, duplicates={duplicates}, "
        f"unsupported={unsupported}, renamed_collisions={collisions}"
    )
    if not args.apply:
        print("No files changed. Re-run with --apply after reviewing the plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
