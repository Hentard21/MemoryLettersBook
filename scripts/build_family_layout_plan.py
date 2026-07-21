#!/usr/bin/env python3
"""Build a reference-ordered readiness plan for serial family layout.

The plan does not invent transcriptions and does not decide page count from a
file count alone. Draft mode may place linked REVIEW_REQUIRED print layers for
human review; final mode still blocks until approval. The renderer tries one
main spread and adds one continuation spread only when readability fails.
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
    parser.add_argument(
        "--edition",
        choices=("draft", "final"),
        default="draft",
        help="Draft uses linked review text; final requires approval.",
    )
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
    deferred_path = root / "content/manifests/draft-deferred-families.json"
    output_path = root / "assets/families/family-layout-plan.json"
    report_path = root / "project-reset/reports/mass-layout-readiness.md"

    processing = load(processing_path)
    letters = load(letters_path)
    deferred_payload = load(deferred_path) if deferred_path.is_file() else {"families": []}
    deferred_by_hero = {
        item["hero_id"]: item for item in deferred_payload.get("families", [])
    }
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
        deferred = deferred_by_hero.get(hero_id)
        if args.edition == "draft":
            if deferred:
                readiness = "deferred_family_archive_draft"
            elif missing:
                readiness = "blocked_missing_transcription"
            elif review:
                readiness = "ready_for_draft_layout_with_review_text"
            elif not letter_entries:
                readiness = "deferred_family_archive_draft"
            else:
                readiness = "ready_for_typographic_preflight"
        else:
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
                "layout_sequence_group": (
                    "deferred_family_archive"
                    if readiness == "deferred_family_archive_draft"
                    else "main_reference_sequence"
                ),
                "draft_appendix_order": (
                    deferred.get("draft_appendix_order") if deferred else None
                ),
                "draft_deferred_reason": deferred.get("reason") if deferred else None,
                "spread_decision": "pending_readability_preflight",
                "allowed_spreads": {
                    "main": 1,
                    "automatic_continuation": 1,
                },
            }
        )

    counts = Counter(item["readiness"] for item in records)
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edition": args.edition,
        "source_processing_plan": "assets/families/family-processing-plan.json",
        "source_letters_index": "assets/families/letters-transcriptions-index.json",
        "source_draft_deferred": "content/manifests/draft-deferred-families.json",
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
        "transcription_rule": (
            "Draft places linked *_print.txt with review status preserved; "
            "final requires explicit human approval."
        ),
        "counts": {"families": len(records), **dict(counts)},
        "families": records,
    }

    lines = [
        "# Готовность к массовой вёрстке",
        "",
        f"Режим сборки: **{args.edition}**.",
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
        "## Текущий режим текста",
        "",
        (
            "В черновике связанные читательские расшифровки ставятся в макет "
            "с сохранением статуса проверки. Перед финальной печатью они "
            "обязательно сверяются человеком."
            if args.edition == "draft"
            else "Финальная сборка блокируется до ручного утверждения расшифровок."
        ),
        "",
        "## Семьи без зарегистрированной физической рукописи",
        "",
        *[
            f"- {item['reference_order']:02d}. {item['hero_id']} — {item['hero_name']}"
            for item in records
            if item["physical_letter_count"] == 0
        ],
        "",
        "## Временный архивный блок черновика",
        "",
        *[
            f"- {item['draft_appendix_order']:02d}. {item['hero_id']} — {item['hero_name']}"
            for item in records
            if item["layout_sequence_group"] == "deferred_family_archive"
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
