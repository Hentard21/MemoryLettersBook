# -*- coding: utf-8 -*-
"""
Этап 3: рабочие (не печатные!) рендеры страниц для визуальной классификации.

- Рендерит страницы без текстового слоя (168 шт.) + страницы, фигурирующие в
  editorial-issues.pdf-stage.json (титулы с аномалиями) в
  workspace/visual-renders/pages/page_NNN.jpg — умеренное разрешение, только
  для просмотра, НЕ для печати.
- Собирает их в контактные листы (сетка 4x5 с подписанными номерами страниц)
  в workspace/visual-renders/contact-sheets/sheet_NN.jpg для быстрого
  визуального обзора агентом.

Ничего не меняет в PDF. Рендеры — рабочий материал, не печатный исходник.
"""
import json
import os

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "source", "reference.pdf")
MANIFEST = os.path.join(BASE, "content", "manifests", "book-manifest.pdf-stage.json")
ISSUES = os.path.join(BASE, "content", "manifests", "editorial-issues.pdf-stage.json")
PAGES_DIR = os.path.join(BASE, "workspace", "visual-renders", "pages")
SHEETS_DIR = os.path.join(BASE, "workspace", "visual-renders", "contact-sheets")
os.makedirs(PAGES_DIR, exist_ok=True)
os.makedirs(SHEETS_DIR, exist_ok=True)

with open(MANIFEST, encoding="utf-8") as f:
    manifest = json.load(f)
with open(ISSUES, encoding="utf-8") as f:
    issues = json.load(f)

no_text_pages = sorted(p["page"] for p in manifest["pages"] if not p["has_text_layer"])
issue_pages = sorted({pg for iss in issues["issues"] for pg in iss["pdf_pages"]})
target_pages = sorted(set(no_text_pages) | set(issue_pages))

print(f"no_text_pages: {len(no_text_pages)}")
print(f"issue_pages: {len(issue_pages)}")
print(f"target_pages (union): {len(target_pages)}")

# --- 1. рендер отдельных рабочих изображений ---
SCALE = 1.0  # ~72*1.0 dpi эквивалент для A4 портрет -> ок для визуальной классификации, не для печати
pdf = pdfium.PdfDocument(SRC)
rendered = []
for p in target_pages:
    out_path = os.path.join(PAGES_DIR, f"page_{p:03d}.jpg")
    if not os.path.exists(out_path):
        img = pdf[p - 1].render(scale=SCALE).to_pil().convert("RGB")
        img.save(out_path, quality=72)
    rendered.append(p)
    if len(rendered) % 30 == 0:
        print(f"  rendered {len(rendered)}/{len(target_pages)}")
pdf.close()
print(f"Rendered/verified {len(rendered)} working images -> {PAGES_DIR}")

# --- 2. контактные листы ---
COLS, ROWS = 4, 5
PER_SHEET = COLS * ROWS
CELL_W, CELL_H = 280, 396
LABEL_H = 22
PAD = 6

try:
    font = ImageFont.truetype("arial.ttf", 16)
except Exception:
    font = ImageFont.load_default()

sheet_index = []
for s_i in range(0, len(target_pages), PER_SHEET):
    chunk = target_pages[s_i:s_i + PER_SHEET]
    sheet_num = s_i // PER_SHEET + 1
    sheet_w = COLS * (CELL_W + PAD) + PAD
    sheet_h = ROWS * (CELL_H + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, p in enumerate(chunk):
        col = idx % COLS
        row = idx // COLS
        x = PAD + col * (CELL_W + PAD)
        y = PAD + row * (CELL_H + LABEL_H + PAD)
        thumb = Image.open(os.path.join(PAGES_DIR, f"page_{p:03d}.jpg")).convert("RGB")
        thumb.thumbnail((CELL_W, CELL_H))
        tx = x + (CELL_W - thumb.width) // 2
        ty = y + (CELL_H - thumb.height) // 2
        draw.rectangle([x, y, x + CELL_W, y + CELL_H], outline="lightgray")
        sheet.paste(thumb, (tx, ty))
        label = f"p.{p:03d}"
        draw.text((x + 4, y + CELL_H + 2), label, fill="black", font=font)
    sheet_path = os.path.join(SHEETS_DIR, f"sheet_{sheet_num:02d}.jpg")
    sheet.save(sheet_path, quality=80)
    sheet_index.append({"sheet": sheet_num, "file": f"workspace/visual-renders/contact-sheets/sheet_{sheet_num:02d}.jpg", "pages": chunk})
    print(f"  sheet {sheet_num}: pages {chunk[0]}-{chunk[-1]} ({len(chunk)} pages)")

with open(os.path.join(BASE, "workspace", "visual-renders", "reports", "sheet-index.json"), "w", encoding="utf-8") as f:
    json.dump({"per_sheet": PER_SHEET, "total_pages": len(target_pages), "sheets": sheet_index}, f, ensure_ascii=False, indent=2)

print(f"\nTotal sheets: {len(sheet_index)}")
