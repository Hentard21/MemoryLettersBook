"""Build a non-destructive owner handoff package for difficult flagship cutouts."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELP_LIST = ROOT / "assets/processed-flagships/manual-cutout-help-list.json"
PRODUCTION_MANIFEST = ROOT / "assets/production-ready/manifest.json"
OUTPUT = ROOT / "assets/manual-cutout-help"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def file_record(role: str, source: Path, packaged: Path) -> dict:
    width, height = image_dimensions(source)
    shutil.copy2(source, packaged)
    return {
        "role": role,
        "original_project_path": source.relative_to(ROOT).as_posix(),
        "packaged_file": packaged.relative_to(ROOT).as_posix(),
        "sha256": sha256(packaged),
        "bytes": packaged.stat().st_size,
        "width_px": width,
        "height_px": height,
    }


def main() -> None:
    help_data = json.loads(HELP_LIST.read_text(encoding="utf-8"))
    production_data = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    by_print_file = {
        asset["print_file"]: asset
        for asset in production_data["assets"]
        if asset.get("print_file")
    }

    if OUTPUT.exists():
        raise SystemExit(
            f"Refusing to overwrite existing handoff package: {OUTPUT}. "
            "Move or archive it first."
        )

    package_entries: list[dict] = []
    resolved_entries: list[dict] = []
    missing_paths: list[str] = []

    for entry in help_data["entries"]:
        if str(entry.get("status", "")).startswith("resolved_"):
            resolved_entries.append(
                {
                    "hero_id": entry["hero_id"],
                    "status": entry["status"],
                    "resolution_file": entry.get("resolution_file"),
                }
            )
            continue

        priority = entry["priority"]
        hero_id = entry["hero_id"]
        best_source_rel = entry["source_file"]
        cutout_rel = entry["current_cutout"]
        provenance = by_print_file.get(best_source_rel)

        if provenance is None:
            raise SystemExit(f"No production provenance for {best_source_rel}")

        master_rel = provenance.get("source_file")
        if not master_rel:
            raise SystemExit(f"No documentary source_file for {best_source_rel}")

        master = ROOT / master_rel
        best_source = ROOT / best_source_rel
        current_cutout = ROOT / cutout_rel

        for path in (master, best_source, current_cutout):
            if not path.is_file():
                missing_paths.append(path.relative_to(ROOT).as_posix())

        if missing_paths:
            continue

        hero_dir = OUTPUT / priority / hero_id
        hero_dir.mkdir(parents=True, exist_ok=True)

        master_target = hero_dir / f"01_{hero_id}_original_master{master.suffix.lower()}"
        best_target = hero_dir / f"02_{hero_id}_best_source_upscaled{best_source.suffix.lower()}"
        cutout_target = hero_dir / f"03_{hero_id}_current_cutout_reference{current_cutout.suffix.lower()}"

        files = [
            file_record("documentary_original_master", master, master_target),
            file_record("best_processing_source", best_source, best_target),
            file_record("current_cutout_for_comparison_only", current_cutout, cutout_target),
        ]

        package_entries.append(
            {
                "reference_order": entry["reference_order"],
                "hero_id": hero_id,
                "hero_name": entry.get("hero_name"),
                "priority": priority,
                "issue": entry.get("issue"),
                "recommended_action": entry.get("recommended_action"),
                "asset_id": provenance.get("asset_id"),
                "provenance_manifest": "assets/production-ready/manifest.json",
                "files": files,
                "status": "ready_for_manual_cutout",
            }
        )

    if missing_paths:
        shutil.rmtree(OUTPUT, ignore_errors=True)
        raise SystemExit("Missing input files:\n" + "\n".join(sorted(set(missing_paths))))

    counts = {
        "families": len(package_entries),
        "critical": sum(e["priority"] == "critical" for e in package_entries),
        "high": sum(e["priority"] == "high" for e in package_entries),
        "files": sum(len(e["files"]) for e in package_entries),
    }
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_list": HELP_LIST.relative_to(ROOT).as_posix(),
        "policy": (
            "This is a copy-only handoff package. Documentary masters, upscaled sources, "
            "and existing cutouts remain unchanged in their original locations."
        ),
        "counts": counts,
        "entries": package_entries,
        "resolved_and_omitted": resolved_entries,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = f"""# Фотографии для ручного удаления фона

В пакете {counts['families']} сложных флагманских фотографий: {counts['critical']} критических и {counts['high']} с высоким приоритетом.

В каждой папке героя:

- `01_*_original_master` — нативный документальный исходник;
- `02_*_best_source_upscaled` — лучшая версия для ручной обработки;
- `03_*_current_cutout_reference` — текущая неудачная/неполная маска только для сравнения.

Работать лучше с файлом `02_*`. Сохранять результат как PNG с прозрачностью, не перезаписывая ни один файл в этом пакете. Рекомендуемое имя: `{hero_id if False else 'hero-XXX'}_flagship_nobg_manual.png`.

Полные пути, SHA-256, размеры и описания проблем зафиксированы в `manifest.json`.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
