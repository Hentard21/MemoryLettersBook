#!/usr/bin/env python3
"""Validate CutItOut drafts and build light/dark QA contact sheets."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def font(size: int) -> ImageFont.ImageFont:
    candidate = Path("C:/Windows/Fonts/arial.ttf")
    if candidate.is_file():
        return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def contain(image: Image.Image, width: int, height: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    return copy


def make_sheets(
    entries: list[dict[str, Any]], root: Path, output_dir: Path
) -> list[str]:
    columns, rows = 4, 4
    tile_width, tile_height = 620, 350
    image_width, image_height = 286, 292
    sheet_paths: list[str] = []
    label_font = font(21)
    note_font = font(15)

    for sheet_index in range(math.ceil(len(entries) / (columns * rows))):
        subset = entries[
            sheet_index * columns * rows : (sheet_index + 1) * columns * rows
        ]
        sheet = Image.new(
            "RGB", (columns * tile_width, rows * tile_height), "#d8d8d8"
        )
        draw = ImageDraw.Draw(sheet)
        for index, entry in enumerate(subset):
            column, row = index % columns, index // columns
            x, y = column * tile_width, row * tile_height
            draw.rectangle(
                (x + 1, y + 1, x + tile_width - 2, y + tile_height - 2),
                fill="#f5f2ec",
                outline="#b7b1a7",
                width=2,
            )
            left = Image.new("RGBA", (image_width, image_height), "white")
            right = Image.new("RGBA", (image_width, image_height), "#0b1f3b")
            with Image.open(root / entry["output_file"]) as raw:
                cutout = contain(raw.convert("RGBA"), image_width, image_height)
            position = (
                (image_width - cutout.width) // 2,
                image_height - cutout.height,
            )
            left.alpha_composite(cutout, position)
            right.alpha_composite(cutout, position)
            sheet.paste(left.convert("RGB"), (x + 12, y + 10))
            sheet.paste(right.convert("RGB"), (x + 322, y + 10))
            draw.text(
                (x + 14, y + 309),
                f"{entry['order']:02d} · {entry['hero_id']}",
                fill="#102b50",
                font=label_font,
            )
            draw.text(
                (x + 322, y + 313),
                "needs manual mask review",
                fill="#8f3542",
                font=note_font,
            )

        path = output_dir / f"cutout-qa-{sheet_index + 1:02d}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(path, "JPEG", quality=90, optimize=True)
        sheet_paths.append(path.resolve().relative_to(root).as_posix())
    return sheet_paths


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    queue_path = root / "assets/processed-flagships/flagship-processing-queue.json"
    log_path = root / "assets/processed-flagships/flagship-cutout-log.json"
    validation_path = root / "assets/processed-flagships/cutout-validation.json"
    report_dir = root / "project-reset/reports/flagship-cutouts"
    report_path = report_dir / "README.md"

    queue = load(queue_path).get("queue", [])
    jobs = [item for item in queue if item.get("needs_cutout")]
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for job in jobs:
        source = root / job["processing_source"]
        output = root / job["expected_output"]
        if not source.is_file() or not output.is_file():
            errors.append(f"Missing source/output for {job['hero_id']}")
            continue
        try:
            with Image.open(source) as original, Image.open(output) as result:
                if result.format != "PNG":
                    raise ValueError(f"not PNG: {result.format}")
                if original.size != result.size:
                    raise ValueError(
                        f"dimensions differ: {original.size} -> {result.size}"
                    )
                if "A" not in result.getbands():
                    raise ValueError("alpha channel is missing")
                alpha = result.getchannel("A")
                extrema = alpha.getextrema()
                if extrema[0] >= 255:
                    raise ValueError("alpha channel is fully opaque")
                histogram = alpha.histogram()
                entries.append(
                    {
                        "order": job["order"],
                        "hero_id": job["hero_id"],
                        "source_file": job["processing_source"],
                        "output_file": job["expected_output"],
                        "width_px": result.width,
                        "height_px": result.height,
                        "alpha_extrema": list(extrema),
                        "transparent_or_soft_pixels": sum(histogram[:250]),
                        "fully_transparent_pixels": histogram[0],
                        "status": "needs_manual_mask_review",
                    }
                )
        except (OSError, ValueError) as exc:
            errors.append(f"{job['hero_id']}: {exc}")

    print(
        f"jobs={len(jobs)} valid={len(entries)} errors={len(errors)} "
        f"mode={'APPLY' if args.apply else 'DRY-RUN'}"
    )
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1

    if args.apply:
        timestamp = datetime.now(timezone.utc).isoformat()
        sheets = make_sheets(entries, root, report_dir)
        write(
            validation_path,
            {
                "schema_version": 1,
                "generated_at": timestamp,
                "policy": (
                    "Technical alpha validation is not visual approval. Every "
                    "result remains needs_manual_mask_review."
                ),
                "counts": {
                    "expected": len(jobs),
                    "valid_png_alpha": len(entries),
                    "approved": 0,
                    "needs_manual_mask_review": len(entries),
                    "errors": 0,
                },
                "contact_sheets": sheets,
                "entries": entries,
            },
        )

        previous = load(log_path) if log_path.exists() else {"entries": []}
        generated_outputs = {item["output_file"] for item in entries}
        preserved = [
            item
            for item in previous.get("entries", [])
            if item.get("output_file") not in generated_outputs
        ]
        generated_log = [
            {
                "hero_id": item["hero_id"],
                "source_file": item["source_file"],
                "output_file": item["output_file"],
                "tool": "CutItOut via Playwright batch",
                "status": "needs-fix",
                "alpha_channel": True,
                "width_px": item["width_px"],
                "height_px": item["height_px"],
                "notes": (
                    "Автоматическая маска технически валидна; проверить волосы, "
                    "руки, оружие, ремни, форму, предметы и цветной ореол."
                ),
            }
            for item in entries
        ]
        write(
            log_path,
            {
                "schema_version": 2,
                "generated_at": timestamp,
                "policy": (
                    "CutItOut is used only for confirmed flagships. Automated "
                    "outputs are never approved without visual mask review."
                ),
                "counts": {
                    "generated_needs_fix": len(generated_log),
                    "preserved_entries": len(preserved),
                    "approved": sum(
                        item.get("status") == "approved" for item in preserved
                    ),
                },
                "entries": sorted(
                    preserved + generated_log,
                    key=lambda item: (item.get("hero_id", ""), item.get("output_file") or ""),
                ),
            },
        )

        report_lines = [
            "# QA вырезанных флагманов",
            "",
            f"Технически проверено: **{len(entries)} из {len(jobs)}** PNG.",
            "",
            "Все результаты сохраняют исходные размеры и имеют реальный alpha-канал. Ни один результат не утверждён автоматически: цветные ореолы, фоновые фрагменты, волосы, руки, оружие, ремни, форма и предметы проверяются вручную на светлом и тёмном фоне.",
            "",
            "## Контактные листы",
            "",
            *[f"- `{path}`" for path in sheets],
            "",
            "Машиночитаемая проверка: `assets/processed-flagships/cutout-validation.json`.",
        ]
        report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        print(f"WROTE: {validation_path}")
        print(f"WROTE: {len(sheets)} contact sheets in {report_dir}")
    else:
        print("No files changed. Re-run with --apply after reviewing validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
