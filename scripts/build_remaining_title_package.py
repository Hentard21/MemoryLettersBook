#!/usr/bin/env python3
"""Build the copy-only package for unresolved family title images.

The package is derived from the latest placement ledger and the active manual
cutout queues.  It never changes production manifests, layout files, or source
assets.  Existing output is not overwritten; use ``--verify-existing`` to
validate a previously built package.
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

from PIL import Image


MASK_FIX_ID = "hero-076"
EXPECTED_PLACEHOLDER_IDS = {
    "hero-038",
    "hero-052",
    "hero-055",
    "hero-062",
    "hero-064",
    "hero-072",
    "hero-074",
}
EXPECTED_INTEGRATED_TRANSPARENT_COUNT = 57

README_TEXT = r"""# Оставшиеся задачи по титульным изображениям

Это динамически собранный copy-only пакет после текущего ingest.
Исходники, production-манифесты и макет не изменены.

## Категории

- `needs-source-confirmation/` — семь семей, для которых последняя
  сборка показывает нейтральный плейсхолдер. Внутри лежат все
  допустимые кандидаты, их Gigapixel-версии, указатель страниц
  референса и снимок production-манифеста. Ни один кандидат не
  помечен как утверждённый флагман.
- `documentary-layout-review/` — пять ещё не утверждённых групповых
  или документальных титульников. Их нельзя автоматически вырезать:
  сначала нужно утвердить подачу целого кадра.
- `needs-mask-fix/hero-076/` — оригинал, чистый белофон и текущая
  неудачная маска. Нужно вручную сохранить шлем, балаклаву,
  броню и края экипировки.

`canonical-reference.pdf` — одна байт-в-байт копия эталонного PDF.
Нужные номера страниц указаны в `reference-pages.json` каждой семьи.

Уже интегрированные 57 прозрачных флагманов в пакет не копируются.

## Проверка

```powershell
python scripts\build_remaining_title_package.py --verify-existing
```

Полный provenance, SHA-256 и размеры файлов хранятся в `manifest.json`.
"""


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
        default=Path("assets/manual-cutout-help-remaining"),
    )
    parser.add_argument("--verify-existing", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def package_rel(path: Path, output: Path, root: Path) -> str:
    return f"{project_rel(output, root)}/{path.resolve().relative_to(output.resolve()).as_posix()}"


def image_metadata(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
        return {}
    with Image.open(path) as image:
        return {
            "width_px": image.width,
            "height_px": image.height,
            "image_format": image.format,
            "color_mode": image.mode,
            "has_alpha": "A" in image.getbands() or "transparency" in image.info,
        }


def add_copy(
    *,
    source: Path,
    destination: Path,
    output: Path,
    root: Path,
    role: str,
    provenance: str,
    asset_id: str | None = None,
) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    source_hash = sha256(source)
    packaged_hash = sha256(destination)
    if source_hash != packaged_hash:
        raise ValueError(f"Copy hash mismatch: {source} -> {destination}")
    entry: dict[str, Any] = {
        "role": role,
        "asset_id": asset_id,
        "source_file": project_rel(source, root),
        "packaged_file": package_rel(destination, output, root),
        "source_sha256": source_hash,
        "packaged_sha256": packaged_hash,
        "bytes": destination.stat().st_size,
        "provenance": provenance,
    }
    entry.update(image_metadata(destination))
    return entry


def placeholder_ids_from_ledger(root: Path) -> list[str]:
    ledger = load_json(root / "output/placement-ledger.json")
    result = {
        item["hero_id"]
        for item in ledger.get("items", [])
        if item.get("source_type") == "flagship"
        and item.get("status") == "review_required"
        and item.get("source_file") == ""
        and "neutral review placeholder" in item.get("notes", "")
    }
    if result != EXPECTED_PLACEHOLDER_IDS:
        raise ValueError(
            "Neutral placeholder set changed; review before packaging: "
            f"expected={sorted(EXPECTED_PLACEHOLDER_IDS)}, actual={sorted(result)}"
        )
    return sorted(result)


def verify_existing(root: Path, output: Path) -> None:
    manifest_path = output / "manifest.json"
    manifest = load_json(manifest_path)
    checked = 0
    for file_entry in manifest.get("shared_files", []):
        source = root / file_entry["source_file"]
        packaged = root / file_entry["packaged_file"]
        if sha256(source) != file_entry["source_sha256"]:
            raise ValueError(f"Source changed: {source}")
        if sha256(packaged) != file_entry["packaged_sha256"]:
            raise ValueError(f"Packaged copy changed: {packaged}")
        checked += 1
    for family in manifest.get("entries", []):
        for file_entry in family.get("files", []):
            source = root / file_entry["source_file"]
            packaged = root / file_entry["packaged_file"]
            if sha256(source) != file_entry["source_sha256"]:
                raise ValueError(f"Source changed: {source}")
            if sha256(packaged) != file_entry["packaged_sha256"]:
                raise ValueError(f"Packaged copy changed: {packaged}")
            checked += 1
    if (output / "README.md").read_text(encoding="utf-8") != README_TEXT:
        raise ValueError("README.md does not match the package builder")
    print(f"verified package files: {checked}")


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output = output.resolve()

    if args.verify_existing:
        verify_existing(root, output)
        return 0
    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing package: {output}. "
            "Use --verify-existing or move the old package first."
        )

    canonical = load_json(root / "content/manifests/reference-family-order-reset.json")
    canonical_by_id = {entry["hero_id"]: entry for entry in canonical["families"]}
    selections = load_json(root / "assets/manual-cutout-help-next/manifest.json")
    selection_by_id = {entry["hero_id"]: entry for entry in selections["entries"]}
    processing_queue = load_json(
        root / "assets/processed-flagships/flagship-processing-queue.json"
    )
    integrated_ids = sorted(
        entry["hero_id"]
        for entry in processing_queue["queue"]
        if entry.get("status") == "ready_for_manual_title_layout"
    )
    if len(integrated_ids) != EXPECTED_INTEGRATED_TRANSPARENT_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_INTEGRATED_TRANSPARENT_COUNT} integrated transparent "
            f"flagships, found {len(integrated_ids)}"
        )

    cutout_log = load_json(root / "assets/processed-flagships/flagship-cutout-log.json")
    approved_documentary_ids = {
        entry["hero_id"]
        for entry in cutout_log.get("entries", [])
        if entry.get("status") == "cutout-not-required"
    }
    documentary_ids = sorted(
        (
            entry["hero_id"]
            for entry in selections["entries"]
            if entry.get("category") == "documentary-layout-review"
            and entry["hero_id"] not in approved_documentary_ids
        ),
        key=lambda hero_id: canonical_by_id[hero_id]["reference_order"],
    )
    placeholder_ids = sorted(
        placeholder_ids_from_ledger(root),
        key=lambda hero_id: canonical_by_id[hero_id]["reference_order"],
    )

    overlap = (set(integrated_ids) & set(placeholder_ids)) | (
        set(integrated_ids) & set(documentary_ids)
    )
    if overlap:
        raise ValueError(f"Integrated flagships leaked into package: {sorted(overlap)}")

    for folder in (
        "needs-source-confirmation",
        "documentary-layout-review",
        "needs-mask-fix",
    ):
        (output / folder).mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, Any]] = []

    for hero_id in placeholder_ids:
        canonical_entry = canonical_by_id[hero_id]
        selection = selection_by_id[hero_id]
        family_dir = output / "needs-source-confirmation" / hero_id
        files: list[dict[str, Any]] = []
        for index, file_info in enumerate(selection.get("files", []), start=1):
            if file_info.get("role") not in {
                "documentary_original_master",
                "best_processing_source",
            }:
                continue
            source = root / file_info["original_project_path"]
            destination = family_dir / f"{index:02d}_{source.name}"
            files.append(
                add_copy(
                    source=source,
                    destination=destination,
                    output=output,
                    root=root,
                    role=file_info["role"],
                    provenance=(
                        "Native family-owned extraction from the canonical reference PDF; "
                        "candidate only, identity/flagship choice is not inferred."
                        if file_info["role"] == "documentary_original_master"
                        else "Registered Gigapixel derivative of the paired documentary master; "
                        "candidate only, not an approved flagship."
                    ),
                    asset_id=file_info.get("asset_id"),
                )
            )
        files.append(
            add_copy(
                source=root / f"assets/families/{hero_id}/references/reference-pages.json",
                destination=family_dir / "reference-pages.json",
                output=output,
                root=root,
                role="canonical_reference_page_pointer",
                provenance="Exact page pointers and SHA-256 for source/reference.pdf.",
            )
        )
        files.append(
            add_copy(
                source=root / f"content/production/families/{hero_id}.json",
                destination=family_dir / "production-family-manifest.json",
                output=output,
                root=root,
                role="production_manifest_snapshot",
                provenance="Read-only copy of the current normalized family manifest.",
            )
        )
        entries.append(
            {
                "reference_order": canonical_entry["reference_order"],
                "hero_id": hero_id,
                "hero_name": canonical_entry["hero_name"],
                "category": "needs-source-confirmation",
                "status": "neutral_placeholder_in_latest_build",
                "reference_pages": canonical_entry["reference_pages"],
                "reason": selection.get("selection_reason", ""),
                "decision_required": (
                    "Owner/source confirmation is required. Do not infer the hero from a "
                    "child, framed portrait, drawing, memorial plate, or group photo."
                ),
                "files": files,
            }
        )

    for hero_id in documentary_ids:
        canonical_entry = canonical_by_id[hero_id]
        selection = selection_by_id[hero_id]
        family_dir = output / "documentary-layout-review" / hero_id
        files = []
        for index, file_info in enumerate(selection.get("files", []), start=1):
            if file_info.get("role") not in {
                "documentary_original_master",
                "best_processing_source",
            }:
                continue
            source = root / file_info["original_project_path"]
            files.append(
                add_copy(
                    source=source,
                    destination=family_dir / f"{index:02d}_{source.name}",
                    output=output,
                    root=root,
                    role=file_info["role"],
                    provenance=(
                        "Native family-owned documentary master. Preserve the whole frame."
                        if file_info["role"] == "documentary_original_master"
                        else "Registered Gigapixel derivative for whole-frame documentary layout."
                    ),
                    asset_id=file_info.get("asset_id"),
                )
            )
        files.append(
            add_copy(
                source=root / f"assets/families/{hero_id}/references/reference-pages.json",
                destination=family_dir / "reference-pages.json",
                output=output,
                root=root,
                role="canonical_reference_page_pointer",
                provenance="Exact page pointers and SHA-256 for source/reference.pdf.",
            )
        )
        files.append(
            add_copy(
                source=root / f"content/production/families/{hero_id}.json",
                destination=family_dir / "production-family-manifest.json",
                output=output,
                root=root,
                role="production_manifest_snapshot",
                provenance="Read-only copy of the current normalized family manifest.",
            )
        )
        entries.append(
            {
                "reference_order": canonical_entry["reference_order"],
                "hero_id": hero_id,
                "hero_name": canonical_entry["hero_name"],
                "category": "documentary-layout-review",
                "status": "whole_frame_layout_not_yet_owner_approved",
                "reference_pages": canonical_entry["reference_pages"],
                "reason": selection.get("selection_reason", ""),
                "decision_required": (
                    "Approve a whole-frame documentary title treatment; do not run automatic "
                    "background removal before approval."
                ),
                "files": files,
            }
        )

    mask_sources = (
        (
            root / "assets/families/hero-076/flagship/hero-076_p254_image1101.jpg",
            "01_original_master.jpg",
            "documentary_original_master",
            "Native family-owned flagship extraction.",
        ),
        (
            root / "assets/production-ready/flagship/hero-076/hero-076_manual_white_v2.png",
            "02_white_background_source.png",
            "owner_clean_white_background_source",
            "Owner-supplied clean white-background source used for the current CutItOut attempt.",
        ),
        (
            root / "assets/processed-flagships/hero-076/hero-076_manual_v2_nobg.png",
            "03_current_mask_needs_fix.png",
            "current_cutitout_mask_needs_fix",
            "Current local CutItOut result; technical alpha passes but visual mask needs repair.",
        ),
    )
    mask_files = [
        add_copy(
            source=source,
            destination=output / "needs-mask-fix" / MASK_FIX_ID / filename,
            output=output,
            root=root,
            role=role,
            provenance=provenance,
            asset_id="hero-076_p254_image1101",
        )
        for source, filename, role, provenance in mask_sources
    ]
    mask_canonical = canonical_by_id[MASK_FIX_ID]
    entries.append(
        {
            "reference_order": mask_canonical["reference_order"],
            "hero_id": MASK_FIX_ID,
            "hero_name": mask_canonical["hero_name"],
            "category": "needs-mask-fix",
            "status": "technical_alpha_passed_visual_mask_failed",
            "reference_pages": mask_canonical["reference_pages"],
            "reason": (
                "The current mask does not preserve a clean usable silhouette around the helmet, "
                "balaclava, body armour, and equipment edges."
            ),
            "decision_required": "Repair the mask manually and return one transparent PNG.",
            "files": mask_files,
        }
    )

    canonical_pdf_source = root / "source/reference.pdf"
    shared_files = [
        add_copy(
            source=canonical_pdf_source,
            destination=output / "canonical-reference.pdf",
            output=output,
            root=root,
            role="canonical_reference_pdf",
            provenance="Byte-for-byte copy of the canonical structural and content reference.",
        )
    ]

    category_counts = Counter(entry["category"] for entry in entries)
    entries.sort(key=lambda entry: (entry["reference_order"], entry["category"]))
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Copy-only unresolved-title handoff. No production manifest, source asset, "
            "processed flagship, or layout file is modified."
        ),
        "derivation": {
            "neutral_placeholders": "output/placement-ledger.json",
            "documentary_review": "assets/manual-cutout-help-next/manifest.json",
            "integrated_transparent_exclusions": (
                "assets/processed-flagships/flagship-processing-queue.json"
            ),
            "approved_documentary_exclusions": (
                "assets/processed-flagships/flagship-cutout-log.json"
            ),
            "canonical_order": "content/manifests/reference-family-order-reset.json",
        },
        "counts": {
            "families": len(entries),
            "files": len(shared_files) + sum(len(entry["files"]) for entry in entries),
            "needs_source_confirmation": category_counts["needs-source-confirmation"],
            "documentary_layout_review": category_counts["documentary-layout-review"],
            "needs_mask_fix": category_counts["needs-mask-fix"],
            "integrated_transparent_flagships_omitted": len(integrated_ids),
        },
        "excluded": {
            "integrated_transparent_flagships": integrated_ids,
            "already_approved_documentary_title_treatments": sorted(
                approved_documentary_ids
            ),
        },
        "shared_files": shared_files,
        "entries": entries,
    }
    (output / "README.md").write_text(README_TEXT, encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    verify_existing(root, output)
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
