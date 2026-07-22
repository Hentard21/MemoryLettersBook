#!/usr/bin/env python3
"""Validate the five compact intro-person cutouts and build QA sheets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "intro-people"
OUTPUT_ROOT = ASSET_ROOT / "cutouts-pro"
REPORT_ROOT = ROOT / "workspace" / "reports" / "intro-compact-cutouts"

PEOPLE = (
    {
        "person_id": "shumilov",
        "source": "for-gigapixel/ProUpscale/Шумилов.png",
        "current": "cutouts-pro/shumilov_nobg.png",
        "compact": "cutouts-pro/shumilov_compact_nobg.png",
    },
    {
        "person_id": "makarychev",
        "source": "for-gigapixel/ProUpscale/Макарычев.png",
        "current": "cutouts-pro/makarychev_nobg.png",
        "compact": "cutouts-pro/makarychev_compact_nobg.png",
    },
    {
        "person_id": "belyaninov",
        "source": "belyaninov-refresh/source/belyaninov_friendlier_white.png",
        "current": "cutouts-pro/belyaninov_v2_nobg.png",
        "compact": "cutouts-pro/belyaninov_compact_nobg.png",
    },
    {
        "person_id": "smirnova",
        "source": "for-gigapixel/ProUpscale/Смирнова.png",
        "current": "cutouts-pro/smirnova_nobg.png",
        "compact": "cutouts-pro/smirnova_compact_nobg.png",
    },
    {
        "person_id": "tengebaeva",
        "source": "for-gigapixel/ProUpscale/Адина.png",
        "current": "cutouts-pro/tengebaeva_nobg.png",
        "compact": "cutouts-pro/tengebaeva_compact_nobg.png",
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_record(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        alpha = image.getchannel("A") if "A" in image.getbands() else None
        return {
            "file": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "alpha_extrema": list(alpha.getextrema()) if alpha else None,
            "alpha_bbox": list(alpha.getbbox()) if alpha and alpha.getbbox() else None,
        }


def build_sheet(records: list[dict[str, object]], background: tuple[int, int, int], name: str) -> Path:
    card_w, card_h = 430, 560
    padding, title_h = 28, 54
    sheet = Image.new("RGB", (padding * 2 + card_w * len(records), card_h + padding * 2), background)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=22)
    subfont = ImageFont.load_default(size=15)
    is_dark = sum(background) < 380
    text_color = (245, 245, 241) if is_dark else (24, 42, 68)
    frame_color = (123, 143, 176) if is_dark else (206, 196, 180)

    for index, record in enumerate(records):
        x = padding + card_w * index
        draw.rounded_rectangle(
            (x + 8, padding, x + card_w - 8, padding + card_h),
            radius=16,
            outline=frame_color,
            width=2,
        )
        path = ROOT / str(record["compact_file"])
        with Image.open(path) as source:
            portrait = source.convert("RGBA")
            portrait = ImageOps.contain(portrait, (card_w - 42, card_h - title_h - 40))
            px = x + (card_w - portrait.width) // 2
            py = padding + title_h + (card_h - title_h - 18 - portrait.height)
            sheet.paste(portrait, (px, py), portrait)
        draw.text((x + 24, padding + 15), str(record["person_id"]), fill=text_color, font=font)
        draw.text((x + 24, padding + 40), "CutItOut / compact", fill=text_color, font=subfont)

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    output = REPORT_ROOT / name
    sheet.save(output, optimize=True)
    return output


def main() -> int:
    records: list[dict[str, object]] = []
    for person in PEOPLE:
        source = ASSET_ROOT / person["source"]
        current = ASSET_ROOT / person["current"]
        compact = ASSET_ROOT / person["compact"]
        for path in (source, current, compact):
            if not path.is_file():
                raise FileNotFoundError(path)

        source_record = image_record(source)
        current_record = image_record(current)
        compact_record = image_record(compact)
        records.append(
            {
                "person_id": person["person_id"],
                "source_file": source_record["file"],
                "source_sha256": source_record["sha256"],
                "current_cutout_file": current_record["file"],
                "current_cutout_sha256": current_record["sha256"],
                "compact_file": compact_record["file"],
                "compact_sha256": compact_record["sha256"],
                "dimensions": [compact_record["width"], compact_record["height"]],
                "alpha_extrema": compact_record["alpha_extrema"],
                "alpha_bbox": compact_record["alpha_bbox"],
                "same_as_current_cutout": compact_record["sha256"] == current_record["sha256"],
                "status": "ready_for_compact_intro_layout_manual_visual_review",
            }
        )

    light = build_sheet(records, (247, 245, 239), "contact-sheet-light.png")
    dark = build_sheet(records, (20, 34, 61), "contact-sheet-dark.png")
    report = {
        "schema_version": 1,
        "scope": "intro_people_only",
        "tool": "local CutItOut via Playwright",
        "layout_intent": "compact one-page welcome composition; scale and crop remain CSS decisions",
        "records": records,
        "contact_sheets": [
            light.relative_to(ROOT).as_posix(),
            dark.relative_to(ROOT).as_posix(),
        ],
        "note": "Sources and existing cutouts were not overwritten. Every mask still requires visual review at print scale.",
    }
    report_path = OUTPUT_ROOT / "compact-cutout-map.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE: {report_path}")
    print(f"WROTE: {light}")
    print(f"WROTE: {dark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
