# -*- coding: utf-8 -*-
"""
Этап 5: уточнение границ блоков героев по итогам визуальной классификации.

Добавляет в heroes.pdf-stage.json (не меняя id и не удаляя существующие поля):
  - material_links[]: для каждой страницы блока — page, link_status, confidence, note
  - boundary_status / boundary_confidence: насколько надёжна граница блока
  - identity_status: насколько надёжно сам титул идентифицирует героя
    (отдельно от вопроса "какие страницы входят в блок")

Допустимые link_status: confirmed_by_sequence, probable_by_sequence, ambiguous, unassigned.
Ничего не удаляется и не переприсваивается автоматически — только фиксируется уровень
уверенности для последующего решения человека.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEROES_PATH = os.path.join(BASE, "content", "entities", "heroes.pdf-stage.json")
ISSUES_PATH = os.path.join(BASE, "content", "manifests", "editorial-issues.pdf-stage.json")

with open(HEROES_PATH, encoding="utf-8") as f:
    data = json.load(f)
with open(ISSUES_PATH, encoding="utf-8") as f:
    issues = json.load(f)

# id героев, чей ТИТУЛ признан визуально неполным/шаблонным (eq-001) -> идентичность
# героя недостоверна, хотя порядок страниц не нарушен
INCOMPLETE_TITLE_HEROES = {"hero-030", "hero-041", "hero-053", "hero-055", "hero-056", "hero-064", "hero-065"}

# пары дублирующихся титулов (eq-003, eq-004) -> кандидаты на объединение/проверку
DUPLICATE_PAIRS = {
    "hero-016": {"duplicate_of_candidate": "hero-017", "note": "Титул без единого материала (pages=[64]); визуально идентичен hero-017 (p.65)"},
    "hero-017": {"duplicate_of_candidate": "hero-016", "note": "Возможный настоящий владелец материалов; титул визуально идентичен hero-016"},
    "hero-051": {"duplicate_of_candidate": "hero-052", "note": "Титул визуально идентичен hero-052; у обоих свой полный комплект материалов"},
    "hero-052": {"duplicate_of_candidate": "hero-051", "note": "Титул визуально идентичен hero-051; у обоих свой полный комплект материалов"},
}

EQ_BY_HERO = {}
for iss in issues["issues"]:
    for ref in iss["entity_refs"]:
        EQ_BY_HERO.setdefault(ref, []).append(iss["issue_id"])

for hero in data["heroes"]:
    hid = hero["id"]
    pages = hero["pages"]
    title_page = hero["title_page"]

    identity_status = "confirmed"
    identity_confidence = 0.9
    identity_notes = []

    if hid in INCOMPLETE_TITLE_HEROES:
        identity_status = "ambiguous"
        identity_confidence = 0.3
        identity_notes.append(
            "Титульная страница визуально неполна (нет герба региона и карты РФ, присутствующих "
            "у всех остальных героев) — реальное имя/регион героя этого блока не подтверждены. "
            "Требуется сверка с PPTX."
        )
    if hid in DUPLICATE_PAIRS:
        identity_status = "ambiguous"
        identity_confidence = min(identity_confidence, 0.5)
        identity_notes.append(DUPLICATE_PAIRS[hid]["note"])

    # boundary: насколько надёжно определены границы блока (от титула до следующего титула)
    if hid == "hero-016":
        # блок без материалов — граница формально корректна, но подозрительна по смыслу
        boundary_status = "probable_by_sequence"
        boundary_confidence = 0.5
    else:
        boundary_status = "confirmed_by_sequence"
        boundary_confidence = 0.85

    material_links = []
    for p in pages:
        if p == title_page:
            link_status = "confirmed_by_sequence"
            confidence = 0.95
            note = "Титульная страница блока"
        elif hid in INCOMPLETE_TITLE_HEROES:
            link_status = "ambiguous"
            confidence = 0.35
            note = "Материал расположен сразу после неполного/шаблонного титула; кому именно принадлежит — не подтверждено"
        elif hid in DUPLICATE_PAIRS:
            link_status = "probable_by_sequence"
            confidence = 0.6
            note = "Материал следует за титулом, дублирующим соседний; принадлежность блоку вероятна, но не окончательна"
        else:
            link_status = "confirmed_by_sequence"
            confidence = 0.85
            note = "Расположен последовательно между этим титулом и следующим"
        material_links.append({"page": p, "link_status": link_status, "confidence": confidence, "note": note})

    hero["boundary_status"] = boundary_status
    hero["boundary_confidence"] = boundary_confidence
    hero["identity_status"] = identity_status
    hero["identity_confidence"] = identity_confidence
    hero["identity_notes"] = identity_notes
    hero["material_links"] = material_links
    hero["editorial_issue_refs"] = EQ_BY_HERO.get(hid, [])

data["boundary_review_note"] = (
    "Границы блоков (material_links) и достоверность самой идентичности героя "
    "(identity_status/identity_confidence) — РАЗНЫЕ вещи. Для 7 героев с неполными титулами "
    "(hero-030, 041, 053, 055, 056, 064, 065) страницы расположены последовательно правильно, "
    "но КТО ИМЕННО этот герой — неизвестно до получения PPTX. Ничего не переприсвоено "
    "автоматически."
)

with open(HEROES_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

n_amb = sum(1 for h in data["heroes"] if h["identity_status"] == "ambiguous")
n_conf = sum(1 for h in data["heroes"] if h["identity_status"] == "confirmed")
print(f"heroes total: {len(data['heroes'])}")
print(f"identity confirmed: {n_conf}")
print(f"identity ambiguous: {n_amb}")
