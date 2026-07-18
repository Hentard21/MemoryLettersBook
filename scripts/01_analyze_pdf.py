# -*- coding: utf-8 -*-
"""
Этап 1: анализ контрольного PDF (source/reference.pdf).

Собирает по каждой странице:
  - физический размер (pt и мм), ориентацию;
  - наличие и объём текстового слоя;
  - количество растровых изображений;
  - дословный текст (без нормализации) -> workspace/extracted-text/pages/page_NNN.txt
Итог: workspace/reports/pdf-analysis.json

Ничего не меняет в исходном PDF. source_quality: "pdf_reference".
"""
import json
import os
import sys

import pdfplumber

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "source", "reference.pdf")
TEXT_DIR = os.path.join(BASE, "workspace", "extracted-text", "pages")
REPORTS = os.path.join(BASE, "workspace", "reports")
os.makedirs(TEXT_DIR, exist_ok=True)
os.makedirs(REPORTS, exist_ok=True)

PT_TO_MM = 25.4 / 72.0

pages_info = []
with pdfplumber.open(SRC) as pdf:
    total = len(pdf.pages)
    for i, page in enumerate(pdf.pages, start=1):
        w_pt, h_pt = float(page.width), float(page.height)
        text = page.extract_text() or ""
        chars = len(page.chars)
        n_images = len(page.images)

        fname = f"page_{i:03d}.txt"
        with open(os.path.join(TEXT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(text)

        pages_info.append({
            "page": i,
            "width_pt": round(w_pt, 2),
            "height_pt": round(h_pt, 2),
            "width_mm": round(w_pt * PT_TO_MM, 1),
            "height_mm": round(h_pt * PT_TO_MM, 1),
            "orientation": "landscape" if w_pt > h_pt else ("portrait" if h_pt > w_pt else "square"),
            "has_text_layer": chars > 0,
            "char_count": chars,
            "text_len": len(text),
            "image_count": n_images,
            "text_file": f"workspace/extracted-text/pages/{fname}",
            "source_quality": "pdf_reference",
        })
        if i % 25 == 0:
            print(f"  ... {i}/{total}", flush=True)

report = {
    "source": "source/reference.pdf",
    "source_quality": "pdf_reference",
    "total_pages": len(pages_info),
    "pages": pages_info,
}
with open(os.path.join(REPORTS, "pdf-analysis.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# Краткая сводка в stdout
sizes = {}
no_text = [p["page"] for p in pages_info if not p["has_text_layer"]]
for p in pages_info:
    key = f'{p["width_mm"]}x{p["height_mm"]}mm ({p["orientation"]})'
    sizes[key] = sizes.get(key, 0) + 1
print("PAGES:", len(pages_info))
print("SIZES:", json.dumps(sizes, ensure_ascii=False))
print("PAGES_WITHOUT_TEXT_LAYER:", len(no_text), no_text[:50])
print("AVG_IMAGES_PER_PAGE:", round(sum(p["image_count"] for p in pages_info) / len(pages_info), 2))
