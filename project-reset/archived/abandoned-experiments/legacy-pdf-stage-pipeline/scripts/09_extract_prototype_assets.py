# -*- coding: utf-8 -*-
"""
Этап 9: временные ассеты для двух прототипных героев (hero-001: стр. 12-14,
hero-002: стр. 15-18).

Рендерит страницы в рабочем разрешении (~160 dpi) и вырезает каждое встроенное
изображение по bbox из pdfplumber. Все вырезки — source_quality: pdf_reference,
ПОМЕЧЕНЫ КАК ВРЕМЕННЫЕ (заменить оригиналами из PPTX). Пишет индекс ассетов.
"""
import json
import os

import pdfplumber
import pypdfium2 as pdfium

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "source", "reference.pdf")

HEROES = {
    "hero-001": [12, 13, 14],
    "hero-002": [15, 16, 17, 18],
}
SCALE = 2.2  # ~158 dpi для A4 — рабочее качество, НЕ печатное

index = {"source_quality": "pdf_reference", "note": "ВРЕМЕННЫЕ вырезки из контрольного PDF. Не для печати. Заменить оригиналами из PPTX.", "heroes": {}}

pdf_r = pdfium.PdfDocument(SRC)
with pdfplumber.open(SRC) as pdf_p:
    for hero_id, pages in HEROES.items():
        out_dir = os.path.join(BASE, "content", "prototypes", hero_id, "assets")
        os.makedirs(out_dir, exist_ok=True)
        hero_assets = []
        for pnum in pages:
            plumb = pdf_p.pages[pnum - 1]
            W, H = float(plumb.width), float(plumb.height)
            rendered = pdf_r[pnum - 1].render(scale=SCALE).to_pil().convert("RGB")
            rw, rh = rendered.size

            # полный рендер страницы (для контекста/фолбэка)
            page_file = f"page_{pnum:03d}_full.jpg"
            rendered.save(os.path.join(out_dir, page_file), quality=80)
            hero_assets.append({
                "file": f"assets/{page_file}", "kind": "page_render",
                "source_page": pnum, "bbox_pdf": None,
            })

            imgs = sorted(plumb.images, key=lambda im: (im["top"], im["x0"]))
            for i, im in enumerate(imgs, start=1):
                x0 = max(0, im["x0"] / W * rw)
                x1 = min(rw, im["x1"] / W * rw)
                top = max(0, im["top"] / H * rh)
                bottom = min(rh, im["bottom"] / H * rh)
                if x1 - x0 < 40 or bottom - top < 40:
                    continue  # мелкая графика (значки и т.п.)
                crop = rendered.crop((int(x0), int(top), int(x1), int(bottom)))
                fname = f"p{pnum:03d}_img{i:02d}.jpg"
                crop.save(os.path.join(out_dir, fname), quality=82)
                hero_assets.append({
                    "file": f"assets/{fname}", "kind": "embedded_image_crop",
                    "source_page": pnum,
                    "bbox_pdf": [round(im["x0"], 1), round(im["top"], 1), round(im["x1"], 1), round(im["bottom"], 1)],
                    "px": [crop.width, crop.height],
                })
        index["heroes"][hero_id] = hero_assets
        print(f"{hero_id}: {len(hero_assets)} assets")

pdf_r.close()
with open(os.path.join(BASE, "content", "prototypes", "assets-index.pdf-stage.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
print("index written")
