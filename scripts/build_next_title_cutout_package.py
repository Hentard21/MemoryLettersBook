#!/usr/bin/env python3
"""Build the next copy-only handoff package for title-page flagships.

The package is intentionally independent from the layout generator.  It copies
documentary masters, the best registered processing derivatives, and existing
automatic cutouts for comparison.  It never changes family or production
manifests and refuses to overwrite an existing package.

The three work queues are owner-approved for this handoff.  Their union is
validated against the active 74-family reference order after excluding the two
approved exemplars and the thirteen cutouts already returned by the owner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image


READY_FOR_MANUAL = (
    "hero-004",
    "hero-007",
    "hero-008",
    "hero-010",
    "hero-012",
    "hero-013",
    "hero-017",
    "hero-018",
    "hero-019",
    "hero-020",
    "hero-021",
    "hero-025",
    "hero-026",
    "hero-027",
    "hero-028",
    "hero-030",
    "hero-031",
    "hero-032",
    "hero-033",
    "hero-034",
    "hero-037",
    "hero-039",
    "hero-040",
    "hero-041",
    "hero-042",
    "hero-043",
    "hero-045",
    "hero-046",
    "hero-048",
    "hero-049",
    "hero-053",
    "hero-054",
    "hero-056",
    "hero-057",
    "hero-058",
    "hero-060",
    "hero-063",
    "hero-065",
    "hero-067",
    "hero-068",
    "hero-069",
    "hero-070",
    "hero-073",
    "hero-075",
    "hero-076",
)

DOCUMENTARY_LAYOUT_REVIEW = (
    "hero-005",
    "hero-009",
    "hero-022",
    "hero-023",
    "hero-035",
    "hero-050",
)

REVIEW_REQUIRED = (
    "hero-006",
    "hero-038",
    "hero-052",
    "hero-055",
    "hero-062",
    "hero-064",
    "hero-072",
    "hero-074",
)

APPROVED_OR_OWNER_RETURNED = (
    "hero-001",
    "hero-003",
    "hero-011",
    "hero-014",
    "hero-015",
    "hero-024",
    "hero-029",
    "hero-036",
    "hero-044",
    "hero-047",
    "hero-051",
    "hero-059",
    "hero-061",
    "hero-066",
    "hero-071",
)

EXPECTED_CATEGORY_COUNTS = {
    "ready-for-manual": 45,
    "documentary-layout-review": 6,
    "review-required": 8,
}
EXPECTED_CANONICAL_COUNT = 74


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/manual-cutout-help-next"),
        help="Project-relative output directory unless an absolute path is supplied.",
    )
    parser.add_argument(
        "--verify-existing",
        action="store_true",
        help="Verify an already-built package without writing or copying files.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_metadata(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
            mode = image.mode
            has_alpha = "A" in image.getbands() or "transparency" in image.info
    except Exception as exc:  # pragma: no cover - diagnostic branch
        raise ValueError(f"Cannot read image metadata for {path}: {exc}") from exc
    return {
        "width_px": width,
        "height_px": height,
        "image_format": image_format,
        "color_mode": mode,
        "has_alpha": has_alpha,
    }


def assert_unique(values: Iterable[str], label: str) -> None:
    values = list(values)
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(duplicates)}")


def validate_declared_coverage(canonical_ids: list[str]) -> dict[str, Any]:
    if len(canonical_ids) != EXPECTED_CANONICAL_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_CANONICAL_COUNT} canonical families, "
            f"found {len(canonical_ids)}"
        )
    assert_unique(canonical_ids, "canonical hero_id values")

    categories = {
        "ready-for-manual": list(READY_FOR_MANUAL),
        "documentary-layout-review": list(DOCUMENTARY_LAYOUT_REVIEW),
        "review-required": list(REVIEW_REQUIRED),
    }
    for category, expected in EXPECTED_CATEGORY_COUNTS.items():
        actual = len(categories[category])
        if actual != expected:
            raise ValueError(f"{category}: expected {expected}, declared {actual}")

    packaged_ids = [hero_id for values in categories.values() for hero_id in values]
    resolved_ids = list(APPROVED_OR_OWNER_RETURNED)
    assert_unique(packaged_ids, "packaged hero_id values")
    assert_unique(resolved_ids, "resolved hero_id values")

    overlap = sorted(set(packaged_ids) & set(resolved_ids))
    missing = sorted(set(canonical_ids) - set(packaged_ids) - set(resolved_ids))
    unexpected = sorted((set(packaged_ids) | set(resolved_ids)) - set(canonical_ids))
    misordered_categories = [
        category
        for category, values in categories.items()
        if values != sorted(values, key=canonical_ids.index)
    ]

    if overlap or missing or unexpected or misordered_categories:
        raise ValueError(
            "Coverage validation failed: "
            f"overlap={overlap}, missing={missing}, unexpected={unexpected}, "
            f"misordered_categories={misordered_categories}"
        )

    return {
        "canonical_families": len(canonical_ids),
        "packaged_families": len(packaged_ids),
        "already_resolved_families": len(resolved_ids),
        "category_counts": EXPECTED_CATEGORY_COUNTS,
        "missing_ids": missing,
        "unexpected_ids": unexpected,
        "overlap_ids": overlap,
        "canonical_coverage_complete": True,
    }


def selection_by_id(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "assets/production-ready/flagship-selections.json"
    payload = load_json(path)
    selections = payload.get("selections", [])
    result: dict[str, dict[str, Any]] = {}
    for selection in selections:
        normalized = dict(selection)
        normalized.setdefault("status", normalized.get("selection_status"))
        result[normalized["hero_id"]] = normalized
    return result


def cutout_by_hero(root: Path) -> dict[str, list[dict[str, Any]]]:
    path = root / "assets/processed-flagships/flagship-cutout-log.json"
    payload = load_json(path)
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in payload.get("entries", []):
        output = entry.get("output_file")
        if output and (root / output).is_file():
            result.setdefault(entry["hero_id"], []).append(entry)
    return result


def matching_cutout(
    hero_id: str,
    sources: Iterable[Path],
    cutouts: dict[str, list[dict[str, Any]]],
    root: Path,
) -> tuple[Path | None, dict[str, Any] | None]:
    normalized_sources = {rel(path, root) for path in sources}
    source_stems = {path.stem.removesuffix("_upscaled_2x") for path in sources}
    exact = [
        entry
        for entry in cutouts.get(hero_id, [])
        if entry.get("source_file") in normalized_sources
    ]
    if len(exact) == 1:
        return root / exact[0]["output_file"], exact[0]
    if len(exact) > 1:
        raise ValueError(f"Multiple exact current cutouts for {hero_id}: {exact}")

    by_name = []
    for entry in cutouts.get(hero_id, []):
        output = root / entry["output_file"]
        output_stem = output.stem.removesuffix("_nobg")
        if output_stem in source_stems:
            by_name.append(entry)
    if len(by_name) == 1:
        return root / by_name[0]["output_file"], by_name[0]
    return None, None


def source_pair_from_flagship(
    family: dict[str, Any], root: Path
) -> tuple[Path, Path | None, str | None]:
    master_value = family.get("flagship_asset")
    if not master_value:
        raise ValueError(f"{family['hero_id']} has no selected flagship_asset")
    master = root / master_value
    processing = family.get("flagship_processing") or {}
    best_value = (
        processing.get("preferred_processing_source")
        or processing.get("print_file")
        or master_value
    )
    best = root / best_value if best_value else None
    return master, best, processing.get("asset_id")


def fallback_pairs(
    family: dict[str, Any], root: Path
) -> list[tuple[Path, Path | None, str | None]]:
    pairs: list[tuple[Path, Path | None, str | None]] = []
    for asset in family.get("archive_assets", []):
        source_value = asset.get("file")
        if not source_value:
            continue
        master = root / source_value
        print_value = asset.get("print_file")
        best = root / print_value if print_value else None
        pairs.append((master, best, asset.get("asset_id")))
    if not pairs:
        raise ValueError(f"{family['hero_id']} has no documented fallback photos")
    return pairs


def validate_input(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    image_metadata(path)


def copy_record(
    role: str,
    source: Path,
    target: Path,
    root: Path,
    asset_id: str | None,
    candidate_index: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite package file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    record = {
        "role": role,
        "candidate_index": candidate_index,
        "asset_id": asset_id,
        "original_project_path": rel(source, root),
        "packaged_file": rel(target, root),
        "sha256": sha256(target),
        "bytes": target.stat().st_size,
        **image_metadata(target),
    }
    if extra:
        record.update(extra)
    return record


def add_candidate_files(
    *,
    hero_id: str,
    hero_dir: Path,
    root: Path,
    master: Path,
    best: Path | None,
    asset_id: str | None,
    candidate_index: int,
    target_counter: list[int],
    cutouts: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_input(master, f"documentary master for {hero_id}")
    files: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []

    def next_target(label: str, source: Path) -> Path:
        number = target_counter[0]
        target_counter[0] += 1
        return hero_dir / (
            f"{number:02d}_{hero_id}_candidate-{candidate_index:02d}_{label}"
            f"{source.suffix.lower()}"
        )

    master_target = next_target("original_master", master)
    files.append(
        copy_record(
            "documentary_original_master",
            master,
            master_target,
            root,
            asset_id,
            candidate_index,
        )
    )

    distinct_best: Path | None = None
    if best is not None:
        validate_input(best, f"best processing source for {hero_id}")
        if best.resolve() == master.resolve() or sha256(best) == sha256(master):
            omissions.append(
                {
                    "role": "best_processing_source",
                    "candidate_index": candidate_index,
                    "asset_id": asset_id,
                    "original_project_path": rel(best, root),
                    "reason": "byte-identical-to-documentary-master",
                }
            )
        else:
            distinct_best = best
            best_target = next_target("best_source_upscaled", best)
            files.append(
                copy_record(
                    "best_processing_source",
                    best,
                    best_target,
                    root,
                    asset_id,
                    candidate_index,
                )
            )

    comparison_sources = [master]
    if distinct_best is not None:
        comparison_sources.append(distinct_best)
    current_cutout, cutout_log = matching_cutout(
        hero_id, comparison_sources, cutouts, root
    )
    if current_cutout is not None:
        validate_input(current_cutout, f"current cutout for {hero_id}")
        cutout_target = next_target("current_cutout_reference", current_cutout)
        files.append(
            copy_record(
                "current_cutout_for_comparison_only",
                current_cutout,
                cutout_target,
                root,
                asset_id,
                candidate_index,
                {
                    "cutout_status": cutout_log.get("status") if cutout_log else None,
                    "cutout_tool": cutout_log.get("tool") if cutout_log else None,
                },
            )
        )
    return files, omissions


def build_package(root: Path, output: Path) -> dict[str, Any]:
    canonical_path = root / "content/manifests/reference-family-order-reset.json"
    canonical = load_json(canonical_path)
    canonical_families = canonical.get("families", [])
    canonical_ids = [family["hero_id"] for family in canonical_families]
    coverage = validate_declared_coverage(canonical_ids)
    canonical_by_id = {family["hero_id"]: family for family in canonical_families}

    plan_path = root / "assets/families/family-processing-plan.json"
    plan = load_json(plan_path)
    families = plan.get("families", [])
    family_by_id = {family["hero_id"]: family for family in families}
    if set(family_by_id) != set(canonical_ids):
        raise ValueError("family-processing-plan does not match the canonical 74 IDs")

    selections = selection_by_id(root)
    cutouts = cutout_by_hero(root)
    category_by_id = {
        **{hero_id: "ready-for-manual" for hero_id in READY_FOR_MANUAL},
        **{
            hero_id: "documentary-layout-review"
            for hero_id in DOCUMENTARY_LAYOUT_REVIEW
        },
        **{hero_id: "review-required" for hero_id in REVIEW_REQUIRED},
    }

    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing handoff package: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}-building-",
            dir=output.parent,
        )
    )

    entries: list[dict[str, Any]] = []
    try:
        for canonical_family in canonical_families:
            hero_id = canonical_family["hero_id"]
            category = category_by_id.get(hero_id)
            if category is None:
                continue
            family = family_by_id[hero_id]
            selection = selections.get(hero_id, {})
            hero_dir = stage / category / hero_id
            counter = [1]
            files: list[dict[str, Any]] = []
            omissions: list[dict[str, Any]] = []

            if category == "review-required":
                pairs = fallback_pairs(family, root)
            else:
                pairs = [source_pair_from_flagship(family, root)]

            candidates: list[dict[str, Any]] = []
            for candidate_index, (master, best, asset_id) in enumerate(pairs, start=1):
                candidate_files, candidate_omissions = add_candidate_files(
                    hero_id=hero_id,
                    hero_dir=hero_dir,
                    root=root,
                    master=master,
                    best=best,
                    asset_id=asset_id,
                    candidate_index=candidate_index,
                    target_counter=counter,
                    cutouts=cutouts,
                )
                files.extend(candidate_files)
                omissions.extend(candidate_omissions)
                candidates.append(
                    {
                        "candidate_index": candidate_index,
                        "asset_id": asset_id,
                        "documentary_master": rel(master, root),
                        "best_processing_source": rel(best, root) if best else None,
                    }
                )

            status_by_category = {
                "ready-for-manual": "ready_for_manual_cutout",
                "documentary-layout-review": "documentary_layout_review",
                "review-required": "REVIEW_REQUIRED",
            }
            entries.append(
                {
                    "reference_order": canonical_family["reference_order"],
                    "hero_id": hero_id,
                    "hero_name": canonical_family.get("hero_name"),
                    "category": category,
                    "status": status_by_category[category],
                    "selection_status": selection.get("status"),
                    "selection_reason": selection.get("reason"),
                    "print_size_warning": selection.get("print_size_warning"),
                    "title_layout_target": {
                        "composition_reference": "Evgeny title page in V20 Design Lock",
                        "crop": "approximately waist-up where the source permits",
                        "placement": "bottom-grounded; never leave the figure floating",
                        "preserve": (
                            "face, recognizability, clothing, hands, awards, patches, "
                            "equipment, weapons, straps, and held objects"
                        ),
                    },
                    "candidates": candidates,
                    "files": files,
                    "omitted_duplicate_files": omissions,
                }
            )

        counts = Counter(entry["category"] for entry in entries)
        if dict(counts) != EXPECTED_CATEGORY_COUNTS:
            raise ValueError(
                f"Built category counts {dict(counts)} do not match "
                f"{EXPECTED_CATEGORY_COUNTS}"
            )

        # Files are copied into an unpublished staging directory first.  Store
        # their final package paths in the manifest so verification remains
        # correct after the atomic directory rename below.
        stage_prefix = rel(stage, root) + "/"
        output_prefix = rel(output, root) + "/"
        for entry in entries:
            for record in entry["files"]:
                packaged_file = record["packaged_file"]
                if not packaged_file.startswith(stage_prefix):
                    raise ValueError(
                        f"Unexpected staging path in package record: {packaged_file}"
                    )
                record["packaged_file"] = output_prefix + packaged_file.removeprefix(
                    stage_prefix
                )

        manifest = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "canonical_order_source": rel(canonical_path, root),
            "processing_plan_source": rel(plan_path, root),
            "selection_source": "assets/production-ready/flagship-selections.json",
            "cutout_log_source": "assets/processed-flagships/flagship-cutout-log.json",
            "policy": (
                "Copy-only manual handoff. No documentary master, production derivative, "
                "current cutout, generator file, or existing manifest is modified."
            ),
            "counts": {
                "families": len(entries),
                **EXPECTED_CATEGORY_COUNTS,
                "files": sum(len(entry["files"]) for entry in entries),
                "fallback_candidates": sum(
                    len(entry["candidates"])
                    for entry in entries
                    if entry["category"] == "review-required"
                ),
            },
            "coverage": coverage,
            "already_resolved_and_omitted": [
                {
                    "hero_id": hero_id,
                    "reason": (
                        "approved exemplar"
                        if hero_id in {"hero-001", "hero-014"}
                        else "owner-returned manual cutout"
                    ),
                }
                for hero_id in canonical_ids
                if hero_id in set(APPROVED_OR_OWNER_RETURNED)
            ],
            "entries": entries,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        readme = """# Следующая очередь титульных фотографий

Этот пакет создан копированием. Исходники, апскейлы, текущие маски и рабочие
манифесты в проекте не изменены.

## Категории

- `ready-for-manual/` — 45 утверждённых флагманов. Рабочим исходником обычно
  служит файл `best_source_upscaled`; `current_cutout_reference` дан только для
  сравнения и не считается готовым результатом.
- `documentary-layout-review/` — 6 групповых или контекстных кадров. Их нельзя
  автоматически превращать в одиночный портрет: сначала нужно решить, сохранять
  ли документальный фон и группу целиком.
- `review-required/` — 8 семей без утверждённого флагмана. В папке каждой семьи
  лежат все зарегистрированные фото-кандидаты с доступными апскейлами. Выбор по
  догадке запрещён.

## Требования к ручному результату

Сохранить прозрачный PNG, лицо и узнаваемость, одежду, руки, награды, нашивки,
экипировку, оружие, ремни и предметы в руках. Для титульной страницы нужен кадр
примерно по пояс, если исходник это допускает. Фигура в макете ставится на нижнюю
линию страницы, по принципу титульной страницы Евгения, и не должна «висеть».
Не достраивать отсутствующие части тела и не менять документальные детали без
отдельного решения владельца.

Точные исходные и пакетные пути, SHA-256, размеры, режим цвета и наличие
альфа-канала записаны в `manifest.json`.
"""
        (stage / "README.md").write_text(readme, encoding="utf-8")

        # The target did not exist when the build started; an atomic directory
        # rename publishes the complete package without touching any input.
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    return manifest


def verify_existing(root: Path, output: Path) -> dict[str, Any]:
    manifest_path = output / "manifest.json"
    readme_path = output / "README.md"
    if not manifest_path.is_file() or not readme_path.is_file():
        raise FileNotFoundError(f"Incomplete package metadata in {output}")
    manifest = load_json(manifest_path)

    canonical = load_json(
        root / "content/manifests/reference-family-order-reset.json"
    )
    canonical_ids = [family["hero_id"] for family in canonical.get("families", [])]
    coverage = validate_declared_coverage(canonical_ids)
    entries = manifest.get("entries", [])
    actual_ids = [entry.get("hero_id") for entry in entries]
    expected_ids = [
        hero_id
        for hero_id in canonical_ids
        if hero_id not in set(APPROVED_OR_OWNER_RETURNED)
    ]
    if actual_ids != expected_ids:
        raise ValueError("Package entry order/coverage differs from canonical order")

    counts = Counter(entry.get("category") for entry in entries)
    if dict(counts) != EXPECTED_CATEGORY_COUNTS:
        raise ValueError(f"Unexpected category counts: {dict(counts)}")

    files_checked = 0
    source_files_checked = 0
    for entry in entries:
        for record in entry.get("files", []):
            packaged = root / record["packaged_file"]
            source = root / record["original_project_path"]
            if not packaged.is_file() or not source.is_file():
                raise FileNotFoundError(
                    f"Missing packaged/source pair: {packaged} / {source}"
                )
            if sha256(packaged) != record["sha256"]:
                raise ValueError(f"Packaged hash mismatch: {packaged}")
            if sha256(source) != record["sha256"]:
                raise ValueError(f"Copy differs from source: {packaged}")
            metadata = image_metadata(packaged)
            for key in (
                "width_px",
                "height_px",
                "image_format",
                "color_mode",
                "has_alpha",
            ):
                if metadata[key] != record[key]:
                    raise ValueError(f"Metadata mismatch for {packaged}: {key}")
            files_checked += 1
            source_files_checked += 1

    return {
        "status": "PASS",
        "output": rel(output, root),
        "families_checked": len(entries),
        "files_checked": files_checked,
        "source_files_checked": source_files_checked,
        "coverage": coverage,
    }


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise SystemExit("Output must stay inside the project root") from exc

    if args.verify_existing:
        result = verify_existing(root, output)
    else:
        build_package(root, output)
        result = verify_existing(root, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
