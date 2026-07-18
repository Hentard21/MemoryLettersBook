#!/usr/bin/env python3
"""Create/validate family folders and build per-family asset manifests.

The command is deliberately conservative: it never guesses a file category and
never moves source files. Assets are copied only when an explicit classification
record is supplied. The default mode is a dry run; pass --apply to write changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FAMILY_DIRS = (
    "flagship",
    "archive-photos",
    "drawings",
    "letters",
    "transcriptions",
    "references",
    "manifest",
)

CATEGORY_ALIASES = {
    "flagship": "flagship",
    "archive": "archive-photos",
    "archive-photo": "archive-photos",
    "archive-photos": "archive-photos",
    "drawing": "drawings",
    "drawings": "drawings",
    "letter": "letters",
    "letters": "letters",
    "handwriting": "letters",
    "transcription": "transcriptions",
    "transcriptions": "transcriptions",
    "reference": "references",
    "references": "references",
}

# These mappings use explicit metadata or explicit source folders. In
# particular, a production "portrait" is kept in the archive pool: choosing a
# flagship is an editorial decision and is never inferred by this script.
JOB_TYPE_CATEGORIES = {
    "portrait": "archive-photos",
    "group": "archive-photos",
    "drawing": "drawings",
    "letter_reference": "letters",
    "handwriting": "letters",
    "transcription": "transcriptions",
    "reference": "references",
}

PRODUCTION_FOLDER_CATEGORIES = {
    "portraits": "archive-photos",
    "groups": "archive-photos",
    "drawings": "drawings",
    "letters-reference": "letters",
    "transcriptions": "transcriptions",
    "references": "references",
}

HERO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate/create assets/families/<hero-id>/ folders and build "
            "family manifests. Defaults to a safe dry run."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--hero",
        action="append",
        default=[],
        help="Hero ID to normalize; repeat for several heroes.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help=(
            "Optional processing-plan JSON. Relative paths are resolved from "
            "the project root."
        ),
    )
    parser.add_argument(
        "--classifications",
        type=Path,
        help=(
            "Optional JSON list (or {'assets': [...]}) with explicit hero_id, "
            "category and source_file fields. Files are copied, never moved. "
            "Defaults to the reset verified-flagship classifications when present."
        ),
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        help=(
            "Production jobs JSON. If omitted, the archived pre-reset "
            "production-input/jobs.json is used when present. asset_type is "
            "mapped explicitly; portraits are not guessed to be flagships."
        ),
    )
    parser.add_argument(
        "--family-order",
        type=Path,
        help=(
            "Canonical family-order JSON (default: "
            "content/manifests/reference-family-order-reset.json when present)."
        ),
    )
    parser.add_argument(
        "--include-legacy-families",
        action="store_true",
        help="Do not filter draft-only hero IDs excluded from the canonical reference.",
    )
    parser.add_argument(
        "--skip-production-input",
        action="store_true",
        help="Do not import the archived categorized production-input folders.",
    )
    parser.add_argument(
        "--include-legacy-page-references",
        action="store_true",
        help=(
            "Also import archived production-input/page-reference images. These renders "
            "belong to the archived 255-page draft and are excluded by default; "
            "use only for an explicit migration audit."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Create directories, copy classified files and write manifests.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing (default).",
    )
    parser.add_argument(
        "--refresh-manifest",
        action="store_true",
        help=(
            "Replace only generated manifest/family-assets.json files. "
            "Asset files are still never overwritten."
        ),
    )
    return parser.parse_args()


def resolve_from_project(project_root: Path, value: Path | None) -> Path | None:
    if value is None:
        return None
    return value.resolve() if value.is_absolute() else (project_root / value).resolve()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def records_from_json(data: Any, collection_key: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict) and isinstance(data.get(collection_key), list):
        records = data[collection_key]
    elif isinstance(data, dict) and "hero_id" in data:
        records = [data]
    else:
        raise ValueError(
            f"Expected a JSON list, a '{collection_key}' list, or one record."
        )
    if not all(isinstance(item, dict) for item in records):
        raise ValueError("Every JSON record must be an object.")
    return records


def validate_hero_id(hero_id: str) -> str:
    hero_id = hero_id.strip()
    if not HERO_ID_RE.fullmatch(hero_id):
        raise ValueError(f"Unsafe or empty hero_id: {hero_id!r}")
    return hero_id


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_asset_files(family_root: Path) -> Iterable[tuple[str, Path]]:
    for category in FAMILY_DIRS:
        if category == "manifest":
            continue
        category_root = family_root / category
        if not category_root.is_dir():
            continue
        for path in sorted(category_root.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                yield category, path


def safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def build_manifest(
    hero_id: str,
    family_root: Path,
    project_root: Path,
    planned: list[dict[str, Any]],
) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    canonical_reference: dict[str, Any] | None = None
    reference_manifest = family_root / "references" / "reference-pages.json"
    if reference_manifest.is_file():
        try:
            loaded_reference = load_json(reference_manifest)
            if isinstance(loaded_reference, dict):
                canonical_reference = loaded_reference
        except ValueError:
            canonical_reference = None

    for item in planned:
        key = (item["category"], item["sha256"])
        if key in seen:
            continue
        seen.add(key)
        destination = family_root / item["category"] / item["name"]
        entry: dict[str, Any] = {
            "asset_id": item.get("asset_id")
            or (
                f"{hero_id}-{item['category']}-{destination.stem}-"
                f"{item['sha256'][:8]}"
            ),
            "category": item["category"],
            "file": safe_relative(destination, project_root),
            "source_file": item["source_file"],
            "sha256": item["sha256"],
            "status": "present" if destination.is_file() else "planned",
        }
        for field in (
            "asset_type",
            "recommended_action",
            "priority",
            "source_status",
            "notes",
        ):
            if item.get(field) is not None:
                entry[field] = item[field]
        if item.get("source_pdf_page") is not None:
            if canonical_reference is not None:
                entry["legacy_source_pdf_page"] = item["source_pdf_page"]
                entry["source_page_status"] = (
                    "REVIEW_REQUIRED_REMAP_TO_FINAL_REFERENCE"
                )
            else:
                entry["source_pdf_page"] = item["source_pdf_page"]
        assets.append(entry)

    for category, path in iter_asset_files(family_root):
        file_hash = sha256(path)
        key = (category, file_hash)
        if key in seen:
            continue
        seen.add(key)
        assets.append(
            {
                "asset_id": f"{hero_id}-{category}-{path.stem}-{file_hash[:8]}",
                "category": category,
                "file": safe_relative(path, project_root),
                "source_file": None,
                "sha256": file_hash,
                "status": "present",
            }
        )

    manifest = {
        "schema_version": 1,
        "hero_id": hero_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directories": list(FAMILY_DIRS),
        "assets": sorted(assets, key=lambda item: (item["category"], item["file"])),
    }
    if canonical_reference is not None:
        manifest["canonical_reference"] = {
            "source_file": canonical_reference.get("source_file"),
            "source_sha256": canonical_reference.get("source_sha256"),
            "reference_title_page": canonical_reference.get(
                "reference_title_page"
            ),
            "reference_pages": canonical_reference.get("reference_pages", []),
            "status": canonical_reference.get("status", "REVIEW_REQUIRED"),
        }
    return manifest


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    families_root = project_root / "assets" / "families"
    plan_path = resolve_from_project(project_root, args.plan)
    if plan_path is None:
        default_plan = families_root / "family-processing-plan.json"
        plan_path = default_plan if default_plan.exists() else None
    classifications_path = resolve_from_project(project_root, args.classifications)
    if classifications_path is None:
        default_classifications = (
            project_root
            / "project-reset"
            / "clean-structure-plan"
            / "verified-flagship-classifications.json"
        )
        classifications_path = (
            default_classifications if default_classifications.exists() else None
        )
    jobs_path = resolve_from_project(project_root, args.jobs)
    production_root = project_root / "assets" / "production-input"
    if not production_root.exists():
        production_root = (
            project_root
            / "project-reset"
            / "archived"
            / "duplicate-assets"
            / "production-input-pre-reset"
        )
    family_order_path = resolve_from_project(project_root, args.family_order)
    if family_order_path is None:
        default_order = (
            project_root
            / "content"
            / "manifests"
            / "reference-family-order-reset.json"
        )
        family_order_path = default_order if default_order.exists() else None
    if jobs_path is None:
        default_jobs = production_root / "jobs.json"
        jobs_path = default_jobs if default_jobs.exists() else None

    try:
        heroes = {validate_hero_id(value) for value in args.hero}
        canonical_heroes: set[str] | None = None
        if family_order_path is not None:
            canonical_heroes = {
                validate_hero_id(str(record.get("hero_id", "")))
                for record in records_from_json(
                    load_json(family_order_path), "families"
                )
            }
        if families_root.is_dir():
            heroes.update(
                validate_hero_id(path.name)
                for path in families_root.iterdir()
                if path.is_dir() and path.name.startswith("hero-")
            )

        if plan_path is not None:
            for record in records_from_json(load_json(plan_path), "families"):
                if record.get("hero_id"):
                    heroes.add(validate_hero_id(str(record["hero_id"])))

        classifications: list[dict[str, Any]] = []
        if classifications_path is not None:
            classifications = records_from_json(
                load_json(classifications_path), "assets"
            )
            for record in classifications:
                heroes.add(validate_hero_id(str(record.get("hero_id", ""))))

        jobs: list[dict[str, Any]] = []
        if jobs_path is not None:
            jobs = records_from_json(load_json(jobs_path), "jobs")
            for record in jobs:
                heroes.add(validate_hero_id(str(record.get("hero_id", ""))))

        # A family with only a reference page may legitimately have no jobs.
        # Explicit hero-* directories still establish its identity.
        if production_root.is_dir() and not args.skip_production_input:
            heroes.update(
                validate_hero_id(path.name)
                for path in production_root.iterdir()
                if path.is_dir() and path.name.startswith("hero-")
            )
        if canonical_heroes is not None and not args.include_legacy_families:
            heroes.intersection_update(canonical_heroes)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] project: {project_root}")
    print(f"[{mode}] families: {len(heroes)}")

    planned_by_hero: dict[str, list[dict[str, Any]]] = {
        hero_id: [] for hero_id in heroes
    }
    errors = 0

    import_records: list[dict[str, Any]] = []
    for record in classifications:
        raw_category = str(record.get("category", "")).strip().lower()
        category = CATEGORY_ALIASES.get(raw_category)
        enriched = dict(record)
        enriched["_normalized_category"] = category
        enriched["_is_explicit"] = True
        import_records.append(enriched)

    for record in jobs:
        raw_type = str(record.get("asset_type", "")).strip().lower()
        enriched = dict(record)
        enriched["_normalized_category"] = JOB_TYPE_CATEGORIES.get(raw_type)
        enriched["category"] = raw_type
        enriched["source_status"] = record.get("status")
        enriched["_is_explicit"] = False
        import_records.append(enriched)

    if production_root.is_dir() and not args.skip_production_input:
        production_folder_categories = dict(PRODUCTION_FOLDER_CATEGORIES)
        if args.include_legacy_page_references:
            production_folder_categories["page-reference"] = "references"
        for hero_id in sorted(heroes):
            hero_source_root = production_root / hero_id
            if not hero_source_root.is_dir():
                continue
            for folder_name, category in production_folder_categories.items():
                category_root = hero_source_root / folder_name
                if not category_root.is_dir():
                    continue
                for source in sorted(category_root.rglob("*")):
                    if source.is_file() and not source.name.startswith("."):
                        import_records.append(
                            {
                                "hero_id": hero_id,
                                "asset_id": source.stem,
                                "asset_type": folder_name,
                                "source_file": safe_relative(source, project_root),
                                "_normalized_category": category,
                                "_is_explicit": False,
                                "notes": "Imported from explicitly categorized production-input folder.",
                            }
                        )

    scheduled: set[tuple[str, str, str]] = set()
    explicit_categories: dict[tuple[str, str], str] = {}
    for record in import_records:
        try:
            hero_id = validate_hero_id(str(record.get("hero_id", "")))
            if hero_id not in planned_by_hero:
                continue
            raw_category = str(record.get("category", record.get("asset_type", "")))
            category = record.get("_normalized_category")
            if category is None:
                raise ValueError(
                    f"Unsupported category {raw_category!r}; no guessing is allowed."
                )
            raw_source = record.get("source_file")
            if not raw_source:
                raise ValueError("source_file is required")
            source = Path(str(raw_source))
            source = (
                source.resolve()
                if source.is_absolute()
                else (project_root / source).resolve()
            )
            if not source.is_file():
                raise ValueError(f"source_file does not exist: {source}")
            destination_name = str(record.get("destination_name") or source.name)
            if Path(destination_name).name != destination_name:
                raise ValueError(f"Unsafe destination_name: {destination_name!r}")

            file_hash = sha256(source)
            override_key = (hero_id, file_hash)
            if record.get("_is_explicit"):
                explicit_categories[override_key] = str(category)
            elif (
                override_key in explicit_categories
                and explicit_categories[override_key] != category
            ):
                print(
                    "SKIP    explicit category override: "
                    f"{safe_relative(source, project_root)} -> "
                    f"{explicit_categories[override_key]}"
                )
                continue
            schedule_key = (hero_id, str(category), file_hash)
            if schedule_key in scheduled:
                continue
            scheduled.add(schedule_key)
            planned_by_hero[hero_id].append(
                {
                    "category": category,
                    "name": destination_name,
                    "source": str(source),
                    "source_file": safe_relative(source, project_root),
                    "sha256": file_hash,
                    "asset_id": record.get("asset_id"),
                    "asset_type": record.get("asset_type"),
                    "source_pdf_page": record.get("source_pdf_page"),
                    "recommended_action": record.get("recommended_action"),
                    "priority": record.get("priority"),
                    "source_status": record.get("source_status"),
                    "notes": record.get("notes"),
                }
            )
        except ValueError as exc:
            errors += 1
            print(f"ERROR classification: {exc}", file=sys.stderr)

    created_dirs = copied = skipped = manifests = 0
    for hero_id in sorted(heroes):
        family_root = families_root / hero_id
        for directory in FAMILY_DIRS:
            target_dir = family_root / directory
            if not target_dir.exists():
                print(f"CREATE  {safe_relative(target_dir, project_root)}/")
                if args.apply:
                    target_dir.mkdir(parents=True, exist_ok=True)
                created_dirs += 1

        for item in planned_by_hero[hero_id]:
            source = Path(item["source"])
            destination = family_root / item["category"] / item["name"]
            if destination.exists():
                if destination.is_file() and sha256(destination) == item["sha256"]:
                    print(f"SKIP    duplicate {safe_relative(destination, project_root)}")
                else:
                    errors += 1
                    print(
                        f"ERROR collision (not overwritten): {destination}",
                        file=sys.stderr,
                    )
                skipped += 1
                continue
            print(
                f"COPY    {safe_relative(source, project_root)} -> "
                f"{safe_relative(destination, project_root)}"
            )
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            copied += 1

        manifest_path = family_root / "manifest" / "family-assets.json"
        if manifest_path.exists() and not args.refresh_manifest:
            print(
                f"SKIP    existing manifest {safe_relative(manifest_path, project_root)}"
            )
            skipped += 1
        else:
            manifest = build_manifest(
                hero_id,
                family_root,
                project_root,
                planned_by_hero[hero_id],
            )
            print(f"WRITE   {safe_relative(manifest_path, project_root)}")
            if args.apply:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            manifests += 1

    print(
        "Summary: "
        f"directories={created_dirs}, copies={copied}, manifests={manifests}, "
        f"skipped={skipped}, errors={errors}"
    )
    if not args.apply:
        print("No files changed. Re-run with --apply after reviewing the plan.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
