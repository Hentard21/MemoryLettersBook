# -*- coding: utf-8 -*-
"""
Этап 13 (данные для print-v3): нормализация регионов, порядок книги, номера
страниц, содержание (JSON + HTML-фрагменты для двух разворотов), QR-коды,
веб-пакеты семей (schema под будущую веб-книгу), таблица эффективного DPI.

Ничего не верстает — только готовит данные, которые вставляются в book.html.
"""
import json
import os
import re

import qrcode

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PV3 = f"{BASE}/design/prototypes/print-v3"
os.makedirs(f"{PV3}/assets/qr", exist_ok=True)
os.makedirs(f"{PV3}/_fragments", exist_ok=True)

heroes = json.load(open(f"{BASE}/content/entities/heroes.pdf-stage.json", encoding="utf-8"))["heroes"]

# --- нормализация регионов (артефакты извлечения текста) ---
def norm_region(raw, city):
    r = (raw or "").strip()
    fixes = {
        "Назар и Элина Донецкая Народная Республика": "Донецкая Народная Республика",
        ". Санкт-Петербург": "г. Санкт-Петербург",
        ". Москва": "г. Москва",
        "Карачаево - Черкесская республика": "Карачаево-Черкесская Республика",
    }
    r = fixes.get(r, r)
    if not r:
        r = (city or "—")
    return r

def norm_city(c):
    c = (c or "").strip()
    return c.replace("г. Санкт- Петербур", "г. Санкт-Петербург")

# --- сборка списка семей в книжном порядке (регион -> имя героя) ---
fams = []
for h in heroes:
    fams.append({
        "hero_id": h["id"],
        "hero_name": (h.get("hero_first_name") or "—").strip(),
        "authors": h.get("author_names") or [],
        "region": norm_region(h.get("region_raw"), h.get("city_raw")),
        "city": norm_city(h.get("city_raw")),
        "identity_status": h.get("identity_status", "confirmed"),
    })
# сортировка: регион (рус.), затем имя героя
fams.sort(key=lambda f: (f["region"].lower(), f["hero_name"].lower()))

# --- пагинация (см. docs/pagination-plan-v3.md) ---
FAMILY_START = 16  # первый разворот семьи начинается с verso p16
for i, f in enumerate(fams):
    f["page"] = FAMILY_START + i * 2  # левая (verso) страница разворота семьи

FAMILY_END = FAMILY_START + len(fams) * 2 - 1
PARTNERS = FAMILY_END + 1                       # partners spread (verso)
FINAL = PARTNERS + 2                            # final/colophon spread
last_content = FINAL + 1
total = last_content
while total % 16 != 0:
    total += 1

def hero_slug(f):
    return f["hero_id"]  # стабильный slug для веб-пути

def child_phrase(f):
    a = f["authors"]
    if not a:
        return "письмо ребёнка"
    if len(a) == 1:
        return f"письмо · {a[0]}"
    return f"письма · {', '.join(a)}"

# --- содержание: группировка по регионам, разбивка на 2 разворота ---
from collections import OrderedDict
groups = OrderedDict()
for f in fams:
    groups.setdefault(f["region"], []).append(f)

# оценка «строк» для равномерной разбивки (заголовок региона = 1.6 строки)
def group_lines(entries):
    return 1.6 + len(entries)
all_groups = list(groups.items())
total_lines = sum(group_lines(e) for _, e in all_groups)
half = total_lines / 2
acc, split_idx = 0, len(all_groups)
for idx, (_, e) in enumerate(all_groups):
    acc += group_lines(e)
    if acc >= half:
        split_idx = idx + 1
        break
part1 = all_groups[:split_idx]
part2 = all_groups[split_idx:]

def render_contents(part):
    html = ['<div class="toc-cols">']
    for region, entries in part:
        html.append('<div class="toc-group">')
        html.append(f'<h3 class="toc-region">{region}</h3>')
        for f in entries:
            dots = '<span class="toc-dots"></span>'
            html.append(
                f'<p class="toc-row"><span class="toc-hero">{f["hero_name"]}</span>'
                f'<span class="toc-auth">{child_phrase(f)}</span>{dots}'
                f'<span class="toc-pg">{f["page"]}</span></p>'
            )
        html.append('</div>')
    html.append('</div>')
    return "\n".join(html)

open(f"{PV3}/_fragments/contents_p1.html", "w", encoding="utf-8").write(render_contents(part1))
open(f"{PV3}/_fragments/contents_p2.html", "w", encoding="utf-8").write(render_contents(part2))

# --- машиночитаемое содержание ---
contents = {
    "note": "Содержание в книжном порядке (регион → имя героя). Номер — левая (verso) страница разворота семьи. Пагинация — docs/pagination-plan-v3.md. Перегенерируется scripts/13.",
    "family_start_page": FAMILY_START,
    "families": [{"hero_id": f["hero_id"], "hero_name": f["hero_name"], "authors": f["authors"],
                  "region": f["region"], "city": f["city"], "page": f["page"],
                  "web_path": f"/letters/{hero_slug(f)}"} for f in fams],
    "regions": [{"region": r, "count": len(e), "first_page": e[0]["page"]} for r, e in all_groups],
}
json.dump(contents, open(f"{BASE}/content/front-matter/contents.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# --- QR-коды для прототипных семей ---
QR_BASE = "https://pisma-pamyati.ru"  # ПЛЕЙСХОЛДЕР стабильного адреса
for hid in ("hero-001", "hero-002"):
    url = f"{QR_BASE}/letters/{hid}"
    qr = qrcode.QRCode(border=1, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url); qr.make(fit=True)
    qr.make_image(fill_color="#1E2732", back_color="white").save(f"{PV3}/assets/qr/{hid}.png")

# --- веб-пакеты семей (schema под веб-книгу; печать и веб — раздельные кропы) ---
web_pkgs = {
  "hero-001": {
    "heroSlug": "hero-001",
    "featuredPhoto": "assets/master-from-pdf/heroes/hero-001/photos/hero-001_photo_01_master.png",
    "featuredLetter": "assets/master-from-pdf/heroes/hero-001/letters/hero-001_letter_01_master.png",
    "featuredQuote": "«Она добра, она строга, она справедлива, и нежна, и я никогда не забуду её»",
    "supportingAssets": [
      "assets/master-from-pdf/heroes/hero-001/photos/hero-001_photo_02_master.png",
      "assets/master-from-pdf/heroes/hero-001/photos/hero-001_photo_03_master.png",
      "assets/master-from-pdf/heroes/hero-001/drawings/hero-001_drawing_01_master.png"
    ],
    "printCrop": {"asset": "hero-001_photo_01", "focus": "center", "aspect": "3x4", "note": "рамочная композиция, не full-bleed"},
    "webFocalPoint": {"asset": "hero-001_photo_01", "x": 0.5, "y": 0.38},
    "fullTranscription": "content/prototypes/hero-001/content.json#letters[0].diplomatic_transcription",
    "printExcerpt": "Моя мама — Герой. Она самая смелая и добрая мама!",
    "webPath": "/letters/hero-001"
  },
  "hero-002": {
    "heroSlug": "hero-002",
    "featuredPhoto": "assets/master-from-pdf/heroes/hero-002/photos/hero-002_photo_04_master.png",
    "featuredLetter": "assets/master-from-pdf/heroes/hero-002/letters/hero-002_letter_02_master.png",
    "featuredQuote": "«Мой папа — мой Герой!!! Я очень горжусь им, и сильно его люблю»",
    "supportingAssets": [
      "assets/master-from-pdf/heroes/hero-002/photos/hero-002_photo_01_master.png",
      "assets/master-from-pdf/heroes/hero-002/photos/hero-002_photo_03_master.png",
      "assets/master-from-pdf/heroes/hero-002/drawings/hero-002_drawing_01_master.png"
    ],
    "printCrop": {"asset": "hero-002_photo_04", "focus": "upper-center", "aspect": "3x4", "note": "рамочная композиция"},
    "webFocalPoint": {"asset": "hero-002_photo_04", "x": 0.5, "y": 0.30},
    "fullTranscription": "content/prototypes/hero-002/content.json#letters",
    "printExcerpt": "Мой папа — мой Герой!!! Я очень горжусь им, и сильно его люблю.",
    "webPath": "/letters/hero-002"
  }
}
for hid, pkg in web_pkgs.items():
    json.dump(pkg, open(f"{BASE}/content/prototypes/{hid}/web-package.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

# --- эффективный DPI размещённых изображений (по запланированным мм) ---
def eff_dpi(px, mm):
    return round(px / (mm / 25.4), 0)
def dpi_status(dpi):
    if dpi >= 220: return "acceptable"
    if dpi >= 150: return "borderline"
    return "too_low_for_size"

placements = [
    # (label, native_px_w, native_px_h, disp_mm_w, disp_mm_h, template)
    ("A hero-001 главное фото", 291, 469, 46, 74, "A"),
    ("A hero-001 письмо",        615, 625, 92, 94, "A"),
    ("B hero-001 письмо (крупно)",615, 625, 120,122,"B"),
    ("B hero-001 портрет малый", 291, 469, 34, 55, "B"),
    ("C hero-002 главное фото",  722, 940, 60, 78, "C"),
    ("C hero-002 доп.фото 1",    723, 949, 40, 52, "C"),
    ("C hero-002 доп.фото 2",    749, 986, 40, 53, "C"),
    ("C hero-002 рисунок",       616, 839, 44, 60, "C"),
    ("C hero-002 письмо фрагм.", 1367,944, 96, 66, "C"),
]
dpi_rows = []
for (label, pw, ph, mw, mh, tpl) in placements:
    d = min(eff_dpi(pw, mw), eff_dpi(ph, mh))
    st = dpi_status(d)
    dpi_rows.append({"placement": label, "template": tpl, "native_px": [pw, ph],
                     "display_mm": [mw, mh], "effective_dpi": d, "status": st,
                     "after_4x_upscale_dpi": d * 4, "after_4x_status": dpi_status(d * 4)})
json.dump({"note":"Эффективный DPI размещённых master-изображений. После апскейла ×4 DPI кратно растёт. Слабые master помечены; в тираж — только derived approved.",
           "target_thresholds":{"acceptable":">=220","borderline":"150-220","too_low_for_size":"<150"},
           "placements": dpi_rows},
          open(f"{BASE}/workspace/reports/print-v3-dpi.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

# --- карта: копия базового силуэта России из нативных мастеров ---
import shutil
src_map = f"{BASE}/content/prototypes/hero-002/assets/native/p015_Image118.png"
if os.path.exists(src_map):
    shutil.copy2(src_map, f"{PV3}/assets/map-base.png")

print(f"families: {len(fams)}  regions: {len(all_groups)}")
print(f"PAGINATION: front 1-15 | families {FAMILY_START}-{FAMILY_END} | partners {PARTNERS}-{PARTNERS+1} | final {FINAL}-{FINAL+1} | ИТОГО(кратно16): {total}")
print(f"contents split: часть1 {len(part1)} регионов, часть2 {len(part2)} регионов")
print("QR, web-package, contents.json, dpi.json, map-base — записаны")
