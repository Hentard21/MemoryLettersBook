# -*- coding: utf-8 -*-
"""
Этап 7: предварительный реестр материалов для сайта.
Строится из heroes.pdf-stage.json (material_links) + визуальной классификации
в book-manifest.pdf-stage.json. Никаких финальных webp/avif не создаётся —
только список того, что потребуется, и предварительное действие для каждого
элемента.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEROES_PATH = os.path.join(BASE, "content", "entities", "heroes.pdf-stage.json")
MANIFEST_PATH = os.path.join(BASE, "content", "manifests", "book-manifest.pdf-stage.json")
OUT_PATH = os.path.join(BASE, "content", "manifests", "web-assets.pdf-stage.json")

with open(HEROES_PATH, encoding="utf-8") as f:
    heroes = json.load(f)["heroes"]
with open(MANIFEST_PATH, encoding="utf-8") as f:
    manifest = json.load(f)

pages_by_num = {p["page"]: p for p in manifest["pages"]}

ALLOWED_ACTIONS = {
    "extract_after_pptx", "replace_with_original_after_pptx", "needs_transcription",
    "needs_manual_crop", "needs_caption_review", "not_for_web", "undetermined",
}


def assets_for_page(page_num, is_title):
    page = pages_by_num.get(page_num, {})
    vc = page.get("visual_classification")
    if is_title:
        return [{
            "type": "title_slide",
            "source_page": page_num,
            "web_action": "not_for_web",
            "note": "Графика титула (герб/карта/значок ордена) — сайт строит собственную шапку страницы героя из структурированных данных, не из скана слайда.",
        }]
    if not vc:
        return [{
            "type": "unknown",
            "source_page": page_num,
            "web_action": "undetermined",
            "note": "Страница не прошла визуальную классификацию в этом проходе.",
        }]

    page_type = vc["page_type"]
    features = set(vc["features"])
    assets = []

    if page_type in ("handwritten_letter", "typed_letter") or "has_handwriting" in features:
        assets.append({
            "type": "letter_scan",
            "source_page": page_num,
            "web_action": "extract_after_pptx",
            "needs_transcription": True,
            "note": "Массовый OCR не выполняется; расшифровка — ручная/выборочная (diplomatic_transcription).",
        })
    if page_type == "child_drawing" or "has_child_art" in features:
        assets.append({
            "type": "drawing",
            "source_page": page_num,
            "web_action": "replace_with_original_after_pptx",
            "needs_manual_crop": page_type in ("photo_collage", "mixed_material"),
            "needs_caption_review": True,
        })
    if page_type in ("photo_collage", "portrait", "mixed_material") or features & {
        "has_family_photo", "has_portrait", "has_multiple_photos", "has_medal_or_award", "has_official_symbols",
    }:
        assets.append({
            "type": "photo",
            "source_page": page_num,
            "web_action": "replace_with_original_after_pptx",
            "needs_manual_crop": page_type in ("photo_collage", "mixed_material"),
            "needs_caption_review": True,
            "note": "Если страница — коллаж/смешанная, один скан описывает НЕСКОЛЬКО будущих Photo/Drawing сущностей; на сайт разбирать по одному изображению, а не сеткой страницы.",
        })
    if page_type == "document_scan":
        assets.append({
            "type": "document_scan",
            "source_page": page_num,
            "web_action": "undetermined",
            "needs_caption_review": True,
            "note": "Нетиповая композиция (похоже на мемориальную карточку/буклет) — решение по подаче принять отдельно.",
        })
    if page_type == "quotation":
        assets.append({
            "type": "quote_text",
            "source_page": page_num,
            "web_action": "needs_transcription",
            "note": "Похоже на печатный текст (стих/посвящение); транскрипция проще, чем для рукописи, но требует сверки.",
        })
    if not assets:
        assets.append({
            "type": "unclassified",
            "source_page": page_num,
            "web_action": "undetermined",
        })
    return assets


registry = []
for hero in heroes:
    hid = hero["id"]
    title_page = hero["title_page"]
    pages = hero["pages"]
    assets = []
    for p in pages:
        assets.extend(assets_for_page(p, is_title=(p == title_page)))
    registry.append({
        "entity_id": hid,
        "pdf_pages": pages,
        "identity_status": hero.get("identity_status"),
        "assets": assets,
    })

# sanity: только допустимые web_action
bad = [a["web_action"] for h in registry for a in h["assets"] if a["web_action"] not in ALLOWED_ACTIONS]
assert not bad, f"Недопустимые web_action: {bad}"

out = {
    "version": "0.1.0",
    "source_quality": "pdf_reference",
    "description": (
        "Предварительный реестр материалов для сайта. Действия только подготовительные — "
        "финальные webp/avif не создаются на этом этапе. Для героев с identity_status="
        "\"ambiguous\" (см. heroes.pdf-stage.json) публикация материалов на сайт должна "
        "дожидаться подтверждения личности героя."
    ),
    "allowed_web_actions": sorted(ALLOWED_ACTIONS),
    "heroes": registry,
}
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

n_letters = sum(1 for h in registry for a in h["assets"] if a["type"] == "letter_scan")
n_photos = sum(1 for h in registry for a in h["assets"] if a["type"] == "photo")
n_drawings = sum(1 for h in registry for a in h["assets"] if a["type"] == "drawing")
print(f"heroes: {len(registry)}, letter_scan assets: {n_letters}, photo assets: {n_photos}, drawing assets: {n_drawings}")
