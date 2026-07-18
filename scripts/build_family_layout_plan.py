#!/usr/bin/env python3
"""Build a reference-ordered readiness plan for serial family layout.

The plan does not invent transcriptions and does not decide page count from a
file count alone.  It records the documentary load and blocks typography until
every physical letter has a linked, reviewed transcription.  The renderer then
tries one main spread and adds one continuation spread only when a readability
preflight fails.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    processing_path = root / "assets/families/family-processing-plan.json"
    letters_path = root / "assets/families/letters-transcriptions-index.json"
    output_path = root / "assets/families/family-layout-plan.json"
    report_path = root / "project-reset/reports/mass-layout-readiness.md"

    processing = load(processing_path)
    letters = load(letters_path)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in letters.get("entries", []):
        by_family[entry["hero_id"]].append(entry)

    records: list[dict[str, Any]] = []
    for family in processing.get("families", []):
        hero_id = family["hero_id"]
        letter_entries = by_family.get(hero_id, [])
        missing = sum(item.get("status") == "missing" for item in letter_entries)
        review = sum(
            item.get("status") not in {"missing", "present", "approved"}
            for item in letter_entries
        )
        if missing:
            readiness = "blocked_missing_transcription"
        elif review:
            readiness = "blocked_transcription_review"
        elif not letter_entries:
            readiness = "blocked_missing_physical_letter_index"
        else:
            readiness = "ready_for_typographic_preflight"

        archive_count = len(family.get("archive_assets", []))
        drawing_count = len(family.get("drawings", []))
        documentary_load = archive_count + drawing_count + len(letter_entries)
        if len(letter_entries) > 1 or documentary_load >= 7:
            preflight_priority = "high"
        elif documentary_load >= 5:
            preflight_priority = "medium"
        else:
            preflight_priority = "normal"

        records.append(
            {
                "reference_order": family["reference_order"],
                "hero_id": hero_id,
                "hero_name": family.get("hero_name", ""),
                "authors": family.get("authors", []),
                "reference_pages": family.get("reference_pages", []),
                "flagship_status": family.get("flagship_status"),
                "flagship_asset": family.get("flagship_asset") or None,
                "archive_photo_count": archive_count,
                "drawing_count": drawing_count,
                "physical_letter_count": len(letter_entries),
                "missing_transcription_count": missing,
                "transcription_review_count": review,
                "documentary_load": documentary_load,
                "preflight_priority": preflight_priority,
                "readiness": readiness,
                "spread_decision": "pending_readability_preflight",
                "allowed_spreads": {
                    "main": 1,
                    "automatic_continuation": 1,
                },
            }
        )

    counts = Counter(item["readiness"] for item in records)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_processing_plan": "assets/families/family-processing-plan.json",
        "source_letters_index": "assets/families/letters-transcriptions-index.json",
        "policy": (
            "Одна семья — один основной разворот. Если полный документальный "
            "комплект не помещается читаемо, автоматически добавляется один "
            "разворот-продолжение. Это лучше, чем уменьшать фотографии и текст "
            "до нечитаемого размера."
        ),
        "decision_rule": (
            "File counts only set preflight priority. Final continuation is "
            "created only after a real typography/readability preflight."
        ),
        "counts": {"families": len(records), **dict(counts)},
        "families": records,
    }

    lines = [
        "# Готовность к массовой вёрстке",
        "",
        "Автоматическая проверка не сочиняет текст и не считает число файлов "
        "заменой реальной типографской пробы.",
        "",
        "## Зафиксированное правило",
        "",
        payload["policy"],
        "",
        "## Сводка",
        "",
        f"- Семей в референсном порядке: **{len(records)}**.",
        f"- Флагманы выбраны: **{sum(bool(x['flagship_asset']) for x in records)}**.",
        f"- Флагманы требуют ручного решения: **{sum(x['flagship_status'] == 'REVIEW_REQUIRED' for x in records)}**.",
        f"- Семей с отсутствующими расшифровками: **{sum(x['missing_transcription_count'] > 0 for x in records)}**.",
        f"- Физических рукописей без расшифровки: **{sum(x['missing_transcription_count'] for x in records)}**.",
        "",
        "## Главный блокер",
        "",
        "До серийной финальной вёрстки нужно подготовить и сверить отдельные "
        "расшифровки. Пока они отсутствуют, можно собирать геометрию шаблона и "
        "обрабатывать изображения, но нельзя заполнять письмо догадкой.",
        "",
        "## Семьи без зарегистрированной физической рукописи",
        "",
        *[
            f"- {item['reference_order']:02d}. {item['hero_id']} — {item['hero_name']}"
            for item in records
            if item["readiness"] == "blocked_missing_physical_letter_index"
        ],
        "",
        "## Флагманы, требующие ручного решения",
        "",
        *[
            f"- {item['reference_order']:02d}. {item['hero_id']} — {item['hero_name']}"
            for item in records
            if item["flagship_status"] == "REVIEW_REQUIRED"
        ],
        "",
        "Машиночитаемый план: `assets/families/family-layout-plan.json`.",
    ]

    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    if args.apply:
        write(output_path, payload)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"WROTE: {output_path}")
        print(f"WROTE: {report_path}")
    else:
        print("No files changed. Re-run with --apply after reviewing the summary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
