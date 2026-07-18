# -*- coding: utf-8 -*-
"""
Этап 2: предварительная классификация страниц и построение:
  - content/manifests/book-manifest.pdf-stage.json  (постраничный манифест)
  - content/entities/heroes.pdf-stage.json          (реестр героев, черновой)
  - content/sections/sections.pdf-stage.json        (разделы книги, черновые)
  - workspace/reports/review-required.md            (список неоднозначных мест)

Правила:
  - тексты сохраняются ДОСЛОВНО (включая опечатки) — исправления запрещены;
  - всё неоднозначное помечается REVIEW_REQUIRED;
  - source_quality всегда "pdf_reference".
"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.join(BASE, "workspace", "reports", "pdf-analysis.json")
TEXT_DIR = os.path.join(BASE, "workspace", "extracted-text", "pages")

with open(ANALYSIS, encoding="utf-8") as f:
    analysis = json.load(f)
pages = analysis["pages"]
N = analysis["total_pages"]

def page_text(i):
    with open(os.path.join(TEXT_DIR, f"page_{i:03d}.txt"), encoding="utf-8") as f:
        return f.read().strip()

# --- ручная классификация вводного блока (страницы 1-11) ---
FRONT = {
    1: ("cover_title", "Титульный лист: ПИСЬМА ПАМЯТИ ТОМ I"),
    2: ("imprint", "Титул с выходными данными (издано по инициативе АНО)"),
    3: ("participants_list", "Список участников акции: субъекты РФ"),
    4: ("official_document", "Указ Президента РФ о Годе народного единства"),
    5: ("greeting_letter", "Обращение к юным авторам (вводное письмо)"),
    6: ("greeting_letter", "Обращение к юным авторам (вводное письмо)"),
    7: ("greeting_letter", "Обращение от Ассамблеи Народов Мира"),
    8: ("news_block", "Награждение в Министерстве обороны РФ, 9 июня 2025"),
    9: ("dialogue_intro", "Диалог Героя Соцтруда А. А. Макарычева с сыном Героя СВО"),
    10: ("greeting_letter", "Обращение от движения «Сенежский форум»"),
    11: ("greeting_letter", "Обращение к юным авторам, о Годе народного единства"),
}

RELATION_RE = re.compile(
    r"^(МО[ЙЯ]|НАШ[АИ]?)\s+(ОТЕЦ|ПАПА|МАМА|БРАТ|ДЯДЯ|ДЕД|ДЕДУШКА|СЫН|МУЖ)\b", re.U
)
UPPER_TOKEN = re.compile(r"^[А-ЯЁA-Z][А-ЯЁA-Z\-\?]*[,]?$", re.U)

def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"-\s*‹#›\s*-", "", t)          # плейсхолдер номера страницы PowerPoint
    t = re.sub(r"-\s*\d+\s*-\s*$", "", t)      # видимый номер страницы
    t = re.sub(r"-\s*\d+\s*-\s*", " ", t)
    return t.strip()

def parse_hero_title(raw):
    """Осторожный разбор титула героя. Возвращает dict + флаги проверки."""
    t = clean_title(raw)
    flags = []
    m = RELATION_RE.match(t)
    relation, hero_name, authors, rest = None, None, [], t
    if m:
        relation = m.group(0)
        tokens = t[m.end():].strip().split(" ")
        # первый токен в ВЕРХНЕМ регистре — имя героя
        idx = 0
        if tokens and UPPER_TOKEN.match(tokens[0]):
            hero_name = tokens[0].rstrip(",")
            idx = 1
        # последующие ВЕРХНИЙ-регистр токены — имена детей-авторов
        while idx < len(tokens) and UPPER_TOKEN.match(tokens[idx]):
            authors.append(tokens[idx].rstrip(","))
            idx += 1
        rest = " ".join(tokens[idx:]).strip()
    else:
        flags.append("relation_not_parsed")
    cities = re.findall(r"г\.\s*[А-ЯЁ][\w\- ]*", rest)
    city = cities[-1].strip() if cities else None
    region = rest
    for c in cities:
        region = region.replace(c, "")
    region = re.sub(r"\s+", " ", region).strip() or None
    if "?" in t:
        flags.append("suspicious_characters_in_title")
    if not city:
        flags.append("city_missing")
    if not authors:
        flags.append("authors_not_parsed")
    return {
        "raw_title": raw.strip(),
        "title_clean": t,
        "relation_phrase": relation,
        "hero_first_name": hero_name,
        "author_names": authors,
        "region_raw": region,
        "city_raw": city,
        "parse_flags": flags,
    }

# --- проход по страницам ---
manifest_pages = []
heroes = []
current_hero = None
title_texts_seen = {}

for p in pages:
    i = p["page"]
    txt = page_text(i)
    entry = {
        "page": i,
        "pdf_page_size_mm": [p["width_mm"], p["height_mm"]],
        "orientation": p["orientation"],
        "has_text_layer": p["has_text_layer"],
        "image_count": p["image_count"],
        "source_quality": "pdf_reference",
        "text_file": p["text_file"],
    }
    if i in FRONT:
        ptype, note = FRONT[i]
        entry.update({
            "page_type": ptype,
            "section": "front-matter",
            "hero_id": None,
            "has_hero": False,
            "has_letter": ptype == "greeting_letter",
            "has_drawing": False,
            "has_photo": p["image_count"] > 0,
            "needs_ocr": False,
            "needs_review": False,
            "review_reasons": [],
            "likely_entities": {
                "greeting_letter": ["DocumentFragment", "Quote"],
                "official_document": ["DocumentFragment"],
                "participants_list": ["DocumentFragment"],
                "cover_title": ["Section"],
                "imprint": ["DocumentFragment"],
                "news_block": ["DocumentFragment", "Photo"],
                "dialogue_intro": ["DocumentFragment", "Photo"],
            }.get(ptype, ["DocumentFragment"]),
            "note": note,
        })
        manifest_pages.append(entry)
        continue

    is_hero_title = bool(txt) and bool(RELATION_RE.match(clean_title(txt)))
    if is_hero_title:
        parsed = parse_hero_title(txt)
        hero_id = f"hero-{len(heroes)+1:03d}"
        review_reasons = list(parsed["parse_flags"])
        # дубликаты / плейсхолдеры: тот же титульный текст уже встречался
        key = parsed["title_clean"]
        if key in title_texts_seen:
            review_reasons.append(
                f"duplicate_title_text_of_page_{title_texts_seen[key]} (возможен дубль страницы или неисправленный шаблон)"
            )
        else:
            title_texts_seen[key] = i
        hero = {
            "id": hero_id,
            "source_quality": "pdf_reference",
            "title_page": i,
            "pages": [i],
            **parsed,
            "review_required": bool(review_reasons),
            "review_reasons": review_reasons,
        }
        heroes.append(hero)
        current_hero = hero
        entry.update({
            "page_type": "hero_title",
            "section": "heroes",
            "hero_id": hero_id,
            "has_hero": True,
            "has_letter": False,
            "has_drawing": False,
            "has_photo": p["image_count"] > 0,
            "needs_ocr": False,
            "needs_review": bool(review_reasons),
            "review_reasons": review_reasons,
            "likely_entities": ["Person", "Section"],
            "note": parsed["title_clean"],
        })
    elif not txt:
        # страница-скан внутри блока героя
        layout_hint = "collage" if p["image_count"] >= 3 else (
            "single_scan" if p["image_count"] >= 1 else "empty_or_vector_only"
        )
        if current_hero:
            current_hero["pages"].append(i)
        entry.update({
            "page_type": "hero_scan_page",
            "section": "heroes" if current_hero else "front-matter",
            "hero_id": current_hero["id"] if current_hero else None,
            "has_hero": current_hero is not None,
            # содержимое скана (письмо/фото/рисунок) без визуальной проверки не определить:
            "has_letter": None,
            "has_drawing": None,
            "has_photo": p["image_count"] > 0,
            "needs_ocr": None,  # да — если на странице рукописное письмо; определяется визуальной проверкой
            "needs_review": True,
            "review_reasons": ["scan_content_not_classified (письмо/фото/рисунок — нужна визуальная разметка)"],
            "layout_hint": layout_hint,
            "likely_entities": ["Letter", "Photo", "Drawing", "PageUnit"],
            "note": "Страница без текстового слоя: сканы (рукописное письмо / фото / детский рисунок)",
        })
    else:
        entry.update({
            "page_type": "unclassified_text_page",
            "section": "heroes" if current_hero else "front-matter",
            "hero_id": current_hero["id"] if current_hero else None,
            "has_hero": current_hero is not None,
            "has_letter": None,
            "has_drawing": None,
            "has_photo": p["image_count"] > 0,
            "needs_ocr": False,
            "needs_review": True,
            "review_reasons": ["text_page_did_not_match_hero_title_pattern"],
            "likely_entities": ["DocumentFragment"],
            "note": clean_title(txt)[:120],
        })
    manifest_pages.append(entry)

manifest = {
    "manifest_version": "0.1.0-pdf-stage",
    "source": "source/reference.pdf",
    "source_quality": "pdf_reference",
    "generated_note": "Черновой манифест по контрольному PDF. После получения PPTX данные подлежат замене (см. docs/pptx-ingestion-plan.md).",
    "total_pages": N,
    "sections": ["front-matter", "heroes"],
    "pages": manifest_pages,
}

os.makedirs(os.path.join(BASE, "content", "manifests"), exist_ok=True)
with open(os.path.join(BASE, "content", "manifests", "book-manifest.pdf-stage.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

with open(os.path.join(BASE, "content", "entities", "heroes.pdf-stage.json"), "w", encoding="utf-8") as f:
    json.dump({
        "source_quality": "pdf_reference",
        "note": "Черновой реестр героев, извлечён из титульных страниц. Имена и регионы — ДОСЛОВНО из PDF, включая возможные опечатки. Не сопоставлять фотографии с людьми без ручной проверки.",
        "count": len(heroes),
        "heroes": heroes,
    }, f, ensure_ascii=False, indent=2)

sections = {
    "source_quality": "pdf_reference",
    "sections": [
        {
            "id": "front-matter",
            "title_working": "Вводный блок",
            "pages": [1, 11],
            "description": "Титул, выходные данные, список участников, Указ Президента РФ, приветственные обращения, новостной блок, диалог поколений.",
        },
        {
            "id": "heroes",
            "title_working": "Истории героев (письма, фото, рисунки)",
            "pages": [12, N],
            "description": "Последовательность блоков героев: титульная страница героя + 1-5 страниц сканов (рукописные письма, фотографии, детские рисунки).",
            "hero_count_draft": len(heroes),
        },
    ],
}
with open(os.path.join(BASE, "content", "sections", "sections.pdf-stage.json"), "w", encoding="utf-8") as f:
    json.dump(sections, f, ensure_ascii=False, indent=2)

# --- отчёт REVIEW_REQUIRED ---
lines = ["# REVIEW_REQUIRED — неоднозначные места (pdf-stage)", ""]
lines.append("## Титульные страницы героев с проблемами\n")
for h in heroes:
    if h["review_required"]:
        lines.append(f"- Стр. {h['title_page']} ({h['id']}): `{h['title_clean']}` — {', '.join(h['review_reasons'])}")
n_scans = sum(1 for e in manifest_pages if e["page_type"] == "hero_scan_page")
lines.append("")
lines.append("## Массовые пометки")
lines.append(f"- Все {n_scans} страниц-сканов помечены `scan_content_not_classified`: нужна визуальная разметка (письмо/фото/рисунок) — вручную или отдельным визуальным проходом.")
lines.append("- OCR рукописных писем на этом этапе НЕ выполнялся (запрещено правилами итерации).")
with open(os.path.join(BASE, "workspace", "reports", "review-required.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("heroes:", len(heroes))
print("hero_title pages:", sum(1 for e in manifest_pages if e["page_type"] == "hero_title"))
print("hero_scan pages:", n_scans)
print("unclassified:", [e["page"] for e in manifest_pages if e["page_type"] == "unclassified_text_page"])
print("review heroes:", sum(1 for h in heroes if h["review_required"]))
