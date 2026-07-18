# -*- coding: utf-8 -*-
"""
Этап 10: структурированные пакеты двух прототипных героев.

content/prototypes/hero-001/  и  content/prototypes/hero-002/
  content.json        — полный пакет сущностей (person, letters, photos, drawings)
  source-text/        — копии дословных извлечённых текстов страниц блока
  assets/             — временные вырезки из PDF (созданы этапом 09)

Тексты источника не изменяются. Расшифровка письма hero-001 — ручная
дипломатическая, статус diplomatic_draft, REVIEW_REQUIRED (не сверена вторым
человеком). Массовый OCR не выполнялся.
"""
import json
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEROES_PATH = os.path.join(BASE, "content", "entities", "heroes.pdf-stage.json")

with open(HEROES_PATH, encoding="utf-8") as f:
    heroes = {h["id"]: h for h in json.load(f)["heroes"]}

COMMON_WARNINGS = [
    "Все изображения — временные вырезки из контрольного PDF (source_quality: pdf_reference), рабочее качество ~160 dpi. ДЛЯ ТИРАЖА НЕПРИГОДНЫ.",
    "Награда на титуле визуально похожа на орден Мужества, но атрибуция награды — FACT_LOCKED: не публиковать название награды без подтверждения (PPTX/семья).",
    "Личности на фотографиях не устанавливались; подписи к фото (depicts) заполняются только вручную владельцем/семьёй.",
]

COMMON_PPTX_REPLACEMENTS = [
    "Заменить все assets/*.jpg оригиналами из ppt/media соответствующих слайдов (см. docs/pptx-ingestion-plan.md).",
    "Сверить текст титула героя с текстбоксами слайда; заполнить hero_full_name при наличии.",
    "Подтвердить принадлежность каждого материала блоку героя (material_links).",
    "Уточнить границы кропов по координатам фигур слайда (bbox из XML PPTX).",
]

# --- дипломатическая расшифровка письма hero-001 (стр. 14), ручная, черновик ---
# Правила: орфография и пунктуация автора сохранены («на всегда» — авторское
# написание), обрезанные краем скана места помечены […], нечитаемое — [нрзб].
# Дипломатическая (архивная) версия: авторская орфография/пунктуация сохранены,
# обрыв края скана помечен [край обрезан]. БЕЗ реконструкции букв.
HERO1_TRANSCRIPT_DIPLOMATIC = (
    "Моя мама - Герой.\n"
    "Она самая смелая и добрая мама!\n"
    "Я горжусь своей мамой ведь она отдала жизнь за ро[край обрезан]\n"
    "Она была доброй и отзывчивой, и мужественной.\n"
    "всегда поддерживала меня в сложных ситуациях. Она любила свою работу, "
    "и иногда брала меня с собой.\n"
    "Я навсегда запомню те дни когда был у неё на[край обрезан]\n"
    "\"Она добра, она строга\n"
    "Она справедлива, и нежна\n"
    "И я никогда не забуду её\"\n"
    "[край обрезан], горжусь!\n"
    "19.05.24.\n"
    "[подпись — нрзб]"
)

# Читательская версия для сайта/книги: обрыв края — «…», ёлочки, без служебных
# скобок. Смысл и авторские особенности не тронуты. Статус — proposed (подпись и
# закрывающая строка требуют человеческой сверки).
HERO1_TRANSCRIPT_READER = (
    "Моя мама — Герой.\n"
    "Она самая смелая и добрая мама!\n"
    "Я горжусь своей мамой, ведь она отдала жизнь за Ро…\n"
    "Она была доброй, и отзывчивой, и мужественной. Всегда поддерживала меня "
    "в сложных ситуациях. Она любила свою работу, и иногда брала меня с собой.\n"
    "Я навсегда запомню те дни, когда был у неё на…\n"
    "«Она добра, она строга,\n"
    "Она справедлива, и нежна,\n"
    "И я никогда не забуду её»\n"
    "…горжусь! 19.05.24."
)

PACKAGES = {
    "hero-001": {
        "person": {
            "id": "hero-001",
            "display_title_source": "МОЯ МАМА АНАСТАСИЯ",
            "relation_phrase": "МОЯ МАМА",
            "hero_first_name": "АНАСТАСИЯ",
            "author_names": ["ИГОРЬ"],
            "region_raw": "Волгоградская область",
            "city_raw": "г. Волгоград",
            "pages": [12, 13, 14],
            "identity_status": "confirmed",
        },
        "letters": [{
            "id": "hero-001-letter-01",
            "source_page": 14,
            "scan_asset": "assets/p014_img01.jpg",
            "author_name_raw": "[подпись частично нечитаема: «Сави…»]",
            "date_raw": "19.05.24.",
            "diplomatic_transcription": HERO1_TRANSCRIPT_DIPLOMATIC,
            "reader_friendly_transcription": HERO1_TRANSCRIPT_READER,
            "transcription_status": "reader_version_proposed",
            "preserve_author_spelling": True,
            "reader_version_approved": False,
            "review_required": True,
            "review_reasons": ["Черновая ручная расшифровка, не сверена вторым человеком; закрывающая строка и подпись не читаются уверенно; два места обрезаны краем скана", "Исправлено: убрана ложная реконструкция буквы в «ситуациях» (было ситуац[и]ях)"],
        }],
        "photos": [
            {"id": "hero-001-photo-01", "source_page": 13, "asset": "assets/p013_img01.jpg",
             "alt": "Портретная фотография из семейного архива (стр. 13 PDF)", "depicts": None},
            {"id": "hero-001-photo-02", "source_page": 13, "asset": "assets/p013_img03.jpg",
             "alt": "Фотография из семейного архива: двое в форме на торжественном мероприятии (стр. 13 PDF)", "depicts": None},
            {"id": "hero-001-photo-03", "source_page": 13, "asset": "assets/p013_img04.jpg",
             "alt": "Фотография: подросток держит портрет в рамке и наградную коробку (стр. 13 PDF)", "depicts": None},
        ],
        "drawings": [
            {"id": "hero-001-drawing-01", "source_page": 13, "asset": "assets/p013_img02.jpg",
             "alt": "Детский рисунок цветными карандашами: женский портрет (стр. 13 PDF)", "author_name": None},
        ],
        "title_graphics": [
            {"asset": "assets/p012_img01.jpg", "note": "Изображение награды с титула — атрибуция не подтверждена (FACT_LOCKED)"},
            {"asset": "assets/p012_img02.jpg", "note": "Герб Волгоградской области"},
            {"asset": "assets/p012_img03.jpg", "note": "Карта РФ с меткой г. Волгоград"},
        ],
        "warnings": COMMON_WARNINGS,
        "pptx_replacements": COMMON_PPTX_REPLACEMENTS,
    },
    "hero-002": {
        "person": {
            "id": "hero-002",
            "display_title_source": "НАШ ОТЕЦ ИГОРЬ",
            "relation_phrase": "НАШ ОТЕЦ",
            "hero_first_name": "ИГОРЬ",
            "author_names_raw": "Назар и Элина",
            "author_names": ["Назар", "Элина"],
            "author_names_note": "Смешанный регистр в исходнике (editorial issue eq-008); имена дословно",
            "region_raw": "Донецкая Народная Республика",
            "city_raw": "г. Новосибирск",
            "region_city_note": "Регион происхождения — ДНР, город на карте титула — Новосибирск (см. eq-008): подтвердить трактовку",
            "pages": [15, 16, 17, 18],
            "identity_status": "confirmed",
        },
        "letters": [
            {"id": "hero-002-letter-01", "source_page": 17, "scan_asset": "assets/p017_img05.jpg",
             "author_name_raw": "Сын Максим (читается со скана)", "date_raw": "28.09.2024 (читается со скана)",
             "diplomatic_transcription": None, "reader_friendly_transcription": None,
             "transcription_status": "not_started", "preserve_author_spelling": True, "reader_version_approved": False,
             "review_required": True,
             "review_reasons": ["editorial issue eq-009: в письме читается имя отца «Ильшат» и подпись «сын Максим» — не совпадает с титулом блока (ИГОРЬ; Назар и Элина). Возможно, письмо другой семьи. НЕ ПУБЛИКОВАТЬ до решения."],
             "publish_blocked": True},
            {"id": "hero-002-letter-02", "source_page": 18, "scan_asset": "assets/p018_img01.jpg",
             "author_name_raw": None, "date_raw": None,
             "diplomatic_transcription": None, "reader_friendly_transcription": None,
             "transcription_status": "not_started", "preserve_author_spelling": True, "reader_version_approved": False,
             "review_required": False, "review_reasons": [], "publish_blocked": False},
            {"id": "hero-002-letter-03", "source_page": 18, "scan_asset": "assets/p018_img02.jpg",
             "author_name_raw": None, "date_raw": None,
             "diplomatic_transcription": None, "reader_friendly_transcription": None,
             "transcription_status": "not_started", "preserve_author_spelling": True, "reader_version_approved": False,
             "review_required": False, "review_reasons": [], "publish_blocked": False},
        ],
        "photos": [
            {"id": "hero-002-photo-01", "source_page": 16, "asset": "assets/p016_img01.jpg",
             "alt": "Фотография: девочка на фоне флага России держит рисунок с танком и гвоздикой (стр. 16 PDF)", "depicts": None},
            {"id": "hero-002-photo-02", "source_page": 16, "asset": "assets/p016_img02.jpg",
             "alt": "Фотография: мальчик держит рисунок-сердце (стр. 16 PDF)", "depicts": None},
            {"id": "hero-002-photo-03", "source_page": 16, "asset": "assets/p016_img03.jpg",
             "alt": "Фотография: двое детей на фоне флага с портретом в рамке и планшетом наград (стр. 16 PDF)", "depicts": None},
            {"id": "hero-002-photo-04", "source_page": 17, "asset": "assets/p017_img01.jpg",
             "alt": "Фотография из архива: военнослужащий в экипировке в лесу (стр. 17 PDF)", "depicts": None},
        ],
        "drawings": [
            {"id": "hero-002-drawing-01", "source_page": 17, "asset": "assets/p017_img03.jpg",
             "alt": "Детский рисунок: человек в синей форме и бронежилете под флагом России (стр. 17 PDF)", "author_name": None},
        ],
        "title_graphics": [
            {"asset": "assets/p015_img01.jpg", "note": "Изображение награды с титула — атрибуция не подтверждена (FACT_LOCKED)"},
            {"asset": "assets/p015_img02.jpg", "note": "Герб/эмблема с титула (ДНР)"},
            {"asset": "assets/p015_img03.jpg", "note": "Карта РФ с меткой города"},
        ],
        "warnings": COMMON_WARNINGS + [
            "eq-009: письмо стр. 17 предположительно другой семьи (папа Ильшат, сын Максим) — в веб-прототипе показано только с предупреждением, публикация заблокирована.",
            "eq-008: регион ДНР при городе Новосибирск — трактовку (переезд семьи?) подтвердить у владельца проекта.",
        ],
        "pptx_replacements": COMMON_PPTX_REPLACEMENTS + [
            "Выяснить по PPTX принадлежность письма стр. 17 (eq-009).",
        ],
    },
}

for hero_id, pkg in PACKAGES.items():
    hero_dir = os.path.join(BASE, "content", "prototypes", hero_id)
    os.makedirs(os.path.join(hero_dir, "source-text"), exist_ok=True)
    # копии дословных текстов страниц блока
    for p in pkg["person"]["pages"]:
        src = os.path.join(BASE, "workspace", "extracted-text", "pages", f"page_{p:03d}.txt")
        shutil.copy2(src, os.path.join(hero_dir, "source-text", f"page_{p:03d}.txt"))

    content = {
        "package_version": "0.1.0",
        "source_quality": "pdf_reference",
        "generated_for": "первый дизайн-прототип (веб + печать)",
        "source_pages_pdf": pkg["person"]["pages"],
        "source_text_files": [f"source-text/page_{p:03d}.txt" for p in pkg["person"]["pages"]],
        **pkg,
    }
    with open(os.path.join(hero_dir, "content.json"), "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    print(f"{hero_id}: content.json + source-text ({len(pkg['person']['pages'])} pages)")

print("done")
