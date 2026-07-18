# -*- coding: utf-8 -*-
"""
Этап 4: слияние визуальной классификации (scripts/visual_classification_data.py)
в book-manifest.pdf-stage.json. Старые поля НЕ удаляются, добавляется только
новый объект "visual_classification" в записи затронутых страниц.
Также экспортирует CSV-представление манифеста.

ВНИМАНИЕ (порядок конвейера): этот скрипт пишет ИСХОДНУЮ классификацию из
visual_classification_data.py. Пересмотры полноразмерных рендеров применяет
scripts/08_decompose_mixed_pages.py — его нужно запускать ПОСЛЕ этого скрипта,
иначе уточнённые типы (стр. 43, 138, 144, 150, 153, 167) будут перезаписаны.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visual_classification_data import VISUAL  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE, "content", "manifests", "book-manifest.pdf-stage.json")
CSV_PATH = os.path.join(BASE, "content", "manifests", "book-manifest.pdf-stage.csv")

with open(MANIFEST_PATH, encoding="utf-8") as f:
    manifest = json.load(f)

updated = 0
for page in manifest["pages"]:
    p = page["page"]
    if p in VISUAL:
        page_type, features, confidence, review_required, notes = VISUAL[p]
        page["visual_classification"] = {
            "page_type": page_type,
            "features": features,
            "confidence": confidence,
            "review_required": review_required,
            "notes": notes,
        }
        updated += 1
    else:
        page.setdefault("visual_classification", None)

manifest["manifest_version"] = "0.2.0-pdf-stage+visual"
manifest["visual_classification_note"] = (
    "Поле visual_classification добавлено на этапе визуальной классификации "
    "(workspace/visual-renders/). Старые поля (page_type, has_letter, has_drawing, "
    "needs_ocr и т.д.) сохранены без изменений — это независимый, дополняющий слой. "
    "visual_classification: null означает, что страница не рендерилась для визуального "
    "обзора (обычно потому что уже надёжно классифицирована по текстовому слою)."
)

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"Updated {updated} pages with visual_classification")

# --- CSV-представление манифеста ---
fields = [
    "page", "section", "hero_id", "page_type", "has_text_layer", "image_count",
    "needs_ocr", "needs_review", "review_reasons",
    "visual_page_type", "visual_features", "visual_confidence",
    "visual_review_required", "visual_notes", "note",
]
with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(fields)
    for page in manifest["pages"]:
        vc = page.get("visual_classification") or {}
        w.writerow([
            page["page"],
            page.get("section"),
            page.get("hero_id"),
            page.get("page_type"),
            page.get("has_text_layer"),
            page.get("image_count"),
            page.get("needs_ocr"),
            page.get("needs_review"),
            " | ".join(page.get("review_reasons") or []),
            vc.get("page_type"),
            " | ".join(vc.get("features") or []),
            vc.get("confidence"),
            vc.get("review_required"),
            " | ".join(vc.get("notes") or []),
            page.get("note"),
        ])
print(f"CSV written -> {CSV_PATH}")
