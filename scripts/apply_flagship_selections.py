#!/usr/bin/env python3
"""Promote visually reviewed family assets into the flagship layer.

Selection files are deliberately separate from the manifests while reviewers
work.  This command validates the complete reference-ordered selection set,
moves selected masters/print derivatives into their semantic ``flagship``
folders, and updates every affected manifest in one operation.

Dry-run is the default.  No ambiguous (``REVIEW_REQUIRED``) selection is
promoted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_FAMILIES = 74
SELECTION_GLOB = "flagship-selections-*.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_asset(items: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    source_path = Path(source)
    exact = [item for item in items if item.get("file") == source]
    if len(exact) == 1:
        return exact[0]
    by_name = [
        item
        for item in items
        if item.get("file") and Path(item["file"]).name == source_path.name
    ]
    return by_name[0] if len(by_name) == 1 else None


def plan_asset(
    family: dict[str, Any], source: str
) -> tuple[str, dict[str, Any] | None]:
    current_flagship = family.get("flagship_asset") or ""
    if current_flagship == source or (
        current_flagship and Path(current_flagship).name == Path(source).name
    ):
        return "flagship", family.get("flagship_processing") or {}
    for collection in ("archive_assets", "drawings"):
        for item in family.get(collection, []):
            if item.get("file") == source or (
                item.get("file")
                and Path(item["file"]).name == Path(source).name
            ):
                return collection, item
    return "", None


def check_move(source: Path, destination: Path) -> None:
    if not source.is_file() and not destination.is_file():
        raise ValueError(f"Missing move source: {source}")
    if source.is_file() and destination.is_file():
        if sha256(source) != sha256(destination):
            raise ValueError(f"Destination collision: {destination}")


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"

    selection_dir = root / "project-reset/clean-structure-plan"
    selection_files = sorted(selection_dir.glob(SELECTION_GLOB))
    selections: list[dict[str, Any]] = []
    for path in selection_files:
        payload = load_json(path)
        for selection in payload.get("selections", []):
            # Review files created in parallel used both field spellings.
            # Normalize them before any validation or manifest update.
            if "status" not in selection and "selection_status" in selection:
                selection["status"] = selection["selection_status"]
            selections.append(selection)

    plan_path = root / "assets/families/family-processing-plan.json"
    plan = load_json(plan_path)
    families = plan.get("families", [])
    family_by_id = {item["hero_id"]: item for item in families}

    errors: list[str] = []
    if len(selections) != EXPECTED_FAMILIES:
        errors.append(
            f"Expected {EXPECTED_FAMILIES} selections, found {len(selections)}"
        )
    if len({item.get("hero_id") for item in selections}) != len(selections):
        errors.append("Selection set contains duplicate hero_id values")
    if [item.get("hero_id") for item in selections] != [
        item.get("hero_id") for item in families
    ]:
        errors.append("Selection order differs from family-processing-plan")

    production_manifest_path = root / "assets/production-ready/manifest.json"
    production_manifest = load_json(production_manifest_path)
    production_entries = production_manifest.get("assets", [])
    family_manifests: dict[str, tuple[Path, dict[str, Any]]] = {}
    moves: list[tuple[Path, Path]] = []
    promoted = review_required = 0

    for selection in selections:
        hero_id = selection.get("hero_id", "")
        family = family_by_id.get(hero_id)
        if family is None:
            errors.append(f"Unknown hero_id: {hero_id}")
            continue

        family["flagship_selection"] = {
            key: selection.get(key)
            for key in (
                "status",
                "confidence",
                "reason",
                "print_size_warning",
            )
        }
        if selection.get("status") != "selected":
            review_required += 1
            family["flagship_status"] = "REVIEW_REQUIRED"
            family["flagship_processing"]["notes"] = selection.get(
                "reason", "Flagship requires manual review."
            )
            continue

        source_value = selection.get("source_file")
        if not source_value:
            errors.append(f"Selected flagship has no source_file: {hero_id}")
            continue
        source = root / source_value
        collection, record = plan_asset(family, source_value)
        if record is None:
            errors.append(f"No processing-plan asset for {hero_id}: {source_value}")
            continue

        family_manifest_path = (
            root / f"assets/families/{hero_id}/manifest/family-assets.json"
        )
        family_manifest = load_json(family_manifest_path)
        family_manifests[hero_id] = (family_manifest_path, family_manifest)
        family_asset = find_asset(family_manifest.get("assets", []), source_value)
        if family_asset is None:
            errors.append(f"No family manifest asset for {hero_id}: {source_value}")
            continue

        flagship_source = (
            root / f"assets/families/{hero_id}/flagship/{source.name}"
        )
        if source.resolve() != flagship_source.resolve():
            try:
                check_move(source, flagship_source)
                moves.append((source, flagship_source))
            except ValueError as exc:
                errors.append(str(exc))
                continue
        else:
            flagship_source = source
        selection["source_file"] = rel(flagship_source, root)

        print_value = record.get("print_file") or family_asset.get("print_file")
        flagship_print_value = ""
        if print_value:
            print_source = root / print_value
            print_destination = (
                root
                / f"assets/production-ready/flagship/{hero_id}/{print_source.name}"
            )
            if print_source.resolve() != print_destination.resolve():
                try:
                    check_move(print_source, print_destination)
                    moves.append((print_source, print_destination))
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
            else:
                print_destination = print_source
            flagship_print_value = rel(print_destination, root)

            production_match = next(
                (
                    item
                    for item in production_entries
                    if item.get("print_file") == print_value
                    or (
                        Path(item.get("print_file", "")).name
                        == print_source.name
                        and item.get("hero_id") == hero_id
                    )
                ),
                None,
            )
            if production_match is None:
                errors.append(f"No production manifest entry for {print_value}")
                continue
            production_match["asset_role"] = "flagship"
            production_match["source_file"] = rel(flagship_source, root)
            production_match["print_file"] = flagship_print_value
            production_match["flagship_selection_confidence"] = selection.get(
                "confidence"
            )

        new_processing = dict(record)
        new_processing.pop("file", None)
        new_processing["asset_id"] = family_asset.get("asset_id")
        new_processing["needs_gigapixel"] = (
            False
            if flagship_print_value
            else bool(record.get("needs_gigapixel", True))
        )
        new_processing["needs_cutout"] = bool(selection.get("needs_cutout"))
        new_processing["needs_waist_crop"] = bool(selection.get("needs_cutout"))
        new_processing["preferred_processing_source"] = (
            flagship_print_value or rel(flagship_source, root)
        )
        if flagship_print_value:
            new_processing["print_file"] = flagship_print_value
            new_processing["gigapixel_status"] = "completed"
        new_processing["selection_confidence"] = selection.get("confidence")
        new_processing["selection_reason"] = selection.get("reason")
        new_processing["print_size_warning"] = selection.get(
            "print_size_warning"
        )
        new_processing["notes"] = selection.get("reason", "")

        family["flagship_asset"] = rel(flagship_source, root)
        family["flagship_status"] = "selected_by_reference_visual_review"
        family["flagship_processing"] = new_processing
        if collection in {"archive_assets", "drawings"}:
            family[collection].remove(record)

        family_asset["file"] = rel(flagship_source, root)
        family_asset["category"] = "flagship"
        family_asset["layout_role"] = "hero_flagship"
        family_asset["selection_confidence"] = selection.get("confidence")
        if flagship_print_value:
            family_asset["print_file"] = flagship_print_value

        promoted += 1

    # Preflight every filesystem operation before moving anything.
    seen_destinations: set[Path] = set()
    for source, destination in moves:
        if destination in seen_destinations:
            errors.append(f"Duplicate move destination: {destination}")
        seen_destinations.add(destination)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(
            f"[{mode}] files={len(selection_files)} selections={len(selections)} "
            f"promoted={promoted} review_required={review_required} "
            f"moves={len(moves)} errors={len(errors)}"
        )
        return 1

    if apply:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file() and not destination.is_file():
                shutil.move(str(source), str(destination))

        timestamp = datetime.now(timezone.utc).isoformat()
        plan["layout_policy"] = {
            "main_spreads_per_family": 1,
            "max_automatic_continuation_spreads": 1,
            "continuation_trigger": "documentary_set_does_not_fit_readably",
            "prohibition": "never shrink photographs or text below readable size",
        }
        plan["flagship_selection_completed_at"] = timestamp
        write_json(plan_path, plan)
        for path, manifest in family_manifests.values():
            write_json(path, manifest)

        production_manifest["counts"]["roles"] = dict(
            Counter(item.get("asset_role", "unknown") for item in production_entries)
        )
        production_manifest["flagship_selection_completed_at"] = timestamp
        write_json(production_manifest_path, production_manifest)
        write_json(
            root / "assets/production-ready/flagship-selections.json",
            {
                "schema_version": 1,
                "generated_at": timestamp,
                "selection_basis": "final reference PDF and family-owned assets",
                "counts": {
                    "total": len(selections),
                    "selected": promoted,
                    "review_required": review_required,
                    "needs_cutout": sum(
                        1
                        for item in selections
                        if item.get("status") == "selected"
                        and item.get("needs_cutout")
                    ),
                },
                "selections": selections,
            },
        )

    print(
        f"[{mode}] files={len(selection_files)} selections={len(selections)} "
        f"promoted={promoted} review_required={review_required} "
        f"moves={len(moves)} errors=0"
    )
    if not apply:
        print("No files changed. Re-run with --apply after reviewing all selections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
