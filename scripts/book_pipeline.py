#!/usr/bin/env python3
"""Shared deterministic pipeline for the V21 full-book draft.

The module deliberately reuses the approved V20 CSS and the normalized V21
data readers.  It adds production pagination, one cached HTML/PDF unit per
family, complete placement accounting, and physical-page/spread assembly.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from pypdf import PageObject, PdfReader, PdfWriter, Transformation


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_v21_pilot as v21  # noqa: E402


OUTPUT = ROOT / "output"
FAMILY_CACHE = OUTPUT / "families"
CHECKPOINT_DIR = OUTPUT / "checkpoints"
INTRO_HTML = ROOT / "design/prototypes/print-v23/interior-compact-v23.html"
INTRO_PLAN = ROOT / "design/prototypes/print-v23/compact-intro-page-plan.json"
INTRO_PDF = ROOT / "design/prototypes/print-v23/PRINT_V23_COMPACT_INTRO_TEST.pdf"
BACK_MATTER_HTML = ROOT / "design/prototypes/print-v23-back-matter/back-matter-v23.html"
BACK_MATTER_PDF = ROOT / "output/pdf/PRINT_V23_BACK_MATTER_PROPOSAL.pdf"
BACK_MATTER_DATA = ROOT / "content/production/back-matter.json"

MM_TO_PT = 72.0 / 25.4
MEDIA_MM = (266.0, 206.0)
TRIM_MM = (260.0, 200.0)
BLEED_MM = 3.0
INNER_SAFE_MM = 22.0
FIRST_FAMILY_PAGE = 14
FRONTMATTER_PAGES = 13
BACK_MATTER_PAGES = 2
MAX_STANDARD_MEDIA = 4
MAX_EXTENDED_MEDIA = 9
MAX_STANDARD_TEXT_CHARS = 1350
MAX_DOCUMENT_TEXT_CHARS = 1550

FORBIDDEN_PUBLIC_MARKERS = (
    "V4",
    "V5",
    "SKELETON",
    "NOT FOR PRODUCTION",
    "PDF_REFERENCE",
    "FACT_LOCKED",
    "REVIEW_REQUIRED",
    "[край обрезан]",
    "[подпись",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def repo_path(value: str | Path) -> str:
    return v21.repo_path(value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def paragraphs_markup(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return "".join(
        f"<p>{esc(paragraph).replace(chr(10), '<br>')}</p>"
        for paragraph in paragraphs
    )


def intro_plan() -> dict[str, Any]:
    if not INTRO_PLAN.is_file():
        raise FileNotFoundError(f"Locked compact intro plan is missing: {INTRO_PLAN}")
    plan = read_json(INTRO_PLAN)
    production = plan.get("production_interior", {})
    if production.get("frontmatter_pages") != FRONTMATTER_PAGES:
        raise RuntimeError(
            f"V23 frontmatter must contain {FRONTMATTER_PAGES} pages, got "
            f"{production.get('frontmatter_pages')}"
        )
    if production.get("first_family_page") != FIRST_FAMILY_PAGE:
        raise RuntimeError("V23 parity lock was lost: first family is not page 14")
    return plan


def intro_sections_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    pages = {
        int(item["production_interior_page"]): item
        for item in plan.get("pages", [])
        if item.get("production_interior_page") is not None
    }
    expected = set(range(1, FRONTMATTER_PAGES + 1))
    if set(pages) != expected:
        raise RuntimeError("V23 compact intro does not cover interior pages 1-13")
    return [
        {
            "section_id": "partners",
            "title": "Выходные данные и партнёры",
            "type": "front_matter",
            "start_page": 1,
            "end_page": 1,
            "spread_count": 1,
        },
        {
            "section_id": "geography",
            "title": "География памяти",
            "type": "front_matter",
            "start_page": 2,
            "end_page": 2,
            "spread_count": 1,
        },
        {
            "section_id": "official-decree",
            "title": "Указ Президента Российской Федерации № 962",
            "type": "front_matter",
            "start_page": 3,
            "end_page": 3,
            "spread_count": 1,
        },
        {
            "section_id": "welcome-words",
            "title": "Приветственные слова",
            "type": "front_matter",
            "start_page": 4,
            "end_page": 10,
            "spread_count": 4,
        },
        {
            "section_id": "chronicle",
            "title": "Диалог поколений — хроника",
            "type": "front_matter",
            "start_page": 5,
            "end_page": 11,
            "spread_count": 4,
        },
        {
            "section_id": "contents",
            "title": "Содержание",
            "type": "front_matter",
            "start_page": 12,
            "end_page": 13,
            "spread_count": 1,
        },
        {
            "section_id": "family-section",
            "title": "Письма семей",
            "type": "front_matter",
            "start_page": 14,
            "end_page": 14,
            "spread_count": 0,
        },
    ]


def split_text_chunks(text: str, max_chars: int) -> list[str]:
    """Split a transcription without dropping or rewriting its words.

    The split prefers paragraph, sentence and word boundaries in that order.
    It is a pagination operation only: the public text stays verbatim.
    """
    remaining = str(text or "").strip()
    if not remaining:
        return []
    chunks: list[str] = []
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]
        candidates = [
            window.rfind("\n\n"),
            window.rfind(". "),
            window.rfind("! "),
            window.rfind("? "),
            window.rfind(" "),
        ]
        cut = max(candidates)
        if cut < max_chars // 2:
            cut = max_chars
        elif window[cut : cut + 2] in {". ", "! ", "? "}:
            cut += 1
        chunk = remaining[:cut].strip()
        if not chunk:
            cut = max_chars
            chunk = remaining[:cut]
        chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def split_text_in_two(text: str) -> tuple[str, str]:
    """Return two non-empty, boundary-aware pieces for spread parity."""
    value = str(text or "").strip()
    if len(value) < 2:
        return value, ""
    midpoint = len(value) // 2
    radius = max(24, len(value) // 5)
    left = max(1, midpoint - radius)
    right = min(len(value) - 1, midpoint + radius)
    window = value[left:right]
    candidates = [
        window.rfind("\n\n", 0, midpoint - left + 1),
        window.rfind(". ", 0, midpoint - left + 1),
        window.rfind("! ", 0, midpoint - left + 1),
        window.rfind("? ", 0, midpoint - left + 1),
        window.rfind(" ", 0, midpoint - left + 1),
    ]
    relative = max(candidates)
    cut = left + relative if relative >= 0 else midpoint
    if value[cut : cut + 2] in {". ", "! ", "? "}:
        cut += 1
    return value[:cut].strip(), value[cut:].strip()


def family_document_units(
    family: dict[str, Any], max_chars: int
) -> list[dict[str, Any]]:
    """Create one lossless render unit per readable transcription segment."""
    texts = v21.family_texts(family)
    letters = [str(item) for item in family.get("letters", [])]
    pair_count = max(len(letters), len(texts))
    units: list[dict[str, Any]] = []
    for pair_index in range(pair_count):
        letter = letters[pair_index] if pair_index < len(letters) else ""
        text = (
            dict(texts[pair_index])
            if pair_index < len(texts)
            else {"text": "", "source_file": "", "manifest_file": ""}
        )
        chunks = split_text_chunks(str(text.get("text") or ""), max_chars) or [""]
        for segment_index, chunk in enumerate(chunks):
            segment = dict(text)
            segment["text"] = chunk
            units.append(
                {
                    "kind": "document",
                    "text": segment,
                    # Show the physical scan once, but retain it as the quiet
                    # paper background on every continuation segment.
                    "letter": letter if segment_index == 0 else "",
                    "letter_background": letter,
                    "pair_index": pair_index,
                    "segment_index": segment_index,
                    "segment_count": len(chunks),
                    "media": [],
                }
            )
    return units


def distribute_media(
    media: list[tuple[str, bool]], bucket_count: int
) -> list[list[tuple[str, bool]]]:
    if bucket_count <= 0:
        return []
    buckets: list[list[tuple[str, bool]]] = [[] for _ in range(bucket_count)]
    for index, item in enumerate(media):
        buckets[index % bucket_count].append(item)
    return buckets


def ensure_odd_content_page_count(
    units: list[dict[str, Any]], family: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep each family on complete spreads without a technical blank page."""
    if len(units) % 2 == 1:
        return units

    # Prefer splitting a real gallery so both pages retain unique materials.
    for index in range(len(units) - 1, -1, -1):
        unit = units[index]
        items = list(unit.get("media") or [])
        if unit.get("kind") == "gallery" and len(items) >= 2:
            cut = math.ceil(len(items) / 2)
            units[index : index + 1] = [
                {**unit, "media": items[:cut]},
                {**unit, "media": items[cut:]},
            ]
            return units

    # If only one overflow image remains, move (not duplicate) one supporting
    # image from a document page to the companion gallery.
    single_gallery = next(
        (
            index
            for index, unit in enumerate(units)
            if unit.get("kind") == "gallery" and len(unit.get("media") or []) == 1
        ),
        None,
    )
    donor = next(
        (
            index
            for index, unit in enumerate(units)
            if unit.get("kind") == "document" and len(unit.get("media") or []) >= 1
        ),
        None,
    )
    if single_gallery is not None and donor is not None:
        moved = units[donor]["media"].pop()
        units.insert(single_gallery + 1, {"kind": "gallery", "media": [moved]})
        return units

    # A transcription may use the second page of the spread at a larger,
    # calmer size. This remains a verbatim pagination split, not an edit.
    document_indexes = [
        index
        for index, unit in enumerate(units)
        if unit.get("kind") == "document"
        and len(str((unit.get("text") or {}).get("text") or "")) >= 80
    ]
    if document_indexes:
        index = max(
            document_indexes,
            key=lambda item: len(str((units[item].get("text") or {}).get("text") or "")),
        )
        unit = units[index]
        first, second = split_text_in_two(str(unit["text"].get("text") or ""))
        if first and second:
            first_text = dict(unit["text"])
            second_text = dict(unit["text"])
            first_text["text"] = first
            second_text["text"] = second
            first_unit = {**unit, "text": first_text}
            second_unit = {
                **unit,
                "text": second_text,
                "letter": "",
                "media": [],
                "segment_index": int(unit.get("segment_index", 0)) + 1,
                "segment_count": int(unit.get("segment_count", 1)) + 1,
            }
            units[index : index + 1] = [first_unit, second_unit]
            return units

    # Last-resort companion is still an original source: a readable
    # facsimile, never a service message or an invented text block.
    letters = [str(item) for item in family.get("letters", []) if item]
    if letters:
        units.append({"kind": "facsimile", "letter": letters[-1], "media": []})
    else:
        units.append({"kind": "gallery", "media": []})
    return units


def family_content_units(family: dict[str, Any]) -> list[dict[str, Any]]:
    """Allocate every canonical family material to a concrete page."""
    template = str(family.get("template") or "standard")
    media: list[tuple[str, bool]] = [
        (str(item), False) for item in family.get("archive_photos", [])
    ] + [(str(item), True) for item in family.get("drawings", [])]
    max_chars = (
        MAX_STANDARD_TEXT_CHARS if template == "standard" else MAX_DOCUMENT_TEXT_CHARS
    )
    documents = family_document_units(family, max_chars)
    minimum_pages = 1 if template == "standard" else 3
    units: list[dict[str, Any]] = []

    if template == "standard":
        if documents:
            first = documents.pop(0)
        else:
            first = {
                "kind": "document",
                "text": {"text": "", "source_file": "", "manifest_file": ""},
                "letter": "",
                "letter_background": "",
                "media": [],
                "segment_index": 0,
                "segment_count": 1,
            }
        first["layout"] = "standard"
        first["media"] = media[:MAX_STANDARD_MEDIA]
        del media[:MAX_STANDARD_MEDIA]
        units.append(first)
        for document in documents:
            document["layout"] = "extended"
            if media:
                document["media"] = [media.pop(0)]
            units.append(document)
    else:
        for document in documents:
            document["layout"] = "extended"
        units.extend(documents)
        # With three or more document pages, keep one supporting image beside
        # each transcription where possible. Otherwise reserve the remaining
        # locked pages for documentary galleries, as in V20.
        if len(documents) >= minimum_pages:
            for document in documents:
                if media:
                    document["media"] = [media.pop(0)]

    minimum_gallery_pages = max(0, minimum_pages - len(units))
    gallery_pages = max(minimum_gallery_pages, math.ceil(len(media) / 6))
    for bucket in distribute_media(media, gallery_pages):
        units.append({"kind": "gallery", "media": bucket})
    while len(units) < minimum_pages:
        units.append({"kind": "gallery", "media": []})

    return ensure_odd_content_page_count(units, family)


def family_requirements(family: dict[str, Any]) -> dict[str, Any]:
    texts = v21.family_texts(family)
    text_chars = sum(len(item.get("text", "")) for item in texts)
    media_count = len(family.get("archive_photos", [])) + len(
        family.get("drawings", [])
    )
    pair_count = max(len(family.get("letters", [])), len(texts))
    template = str(family.get("template") or "standard")
    reasons: list[str] = []
    units = family_content_units(family)
    base_content_pages = 1 if template == "standard" else 3
    extra_spreads = max(0, (len(units) - base_content_pages) // 2)
    if template == "standard":
        if media_count > MAX_STANDARD_MEDIA:
            reasons.append(f"media_count={media_count}>{MAX_STANDARD_MEDIA}")
        if pair_count > 1:
            reasons.append(f"document_pairs={pair_count}>1")
        if text_chars > MAX_STANDARD_TEXT_CHARS:
            reasons.append(
                f"transcription_chars={text_chars}>{MAX_STANDARD_TEXT_CHARS}"
            )
    else:
        if media_count > MAX_EXTENDED_MEDIA:
            reasons.append(f"media_count={media_count}>{MAX_EXTENDED_MEDIA}")
        if pair_count > 3:
            reasons.append(f"document_pairs={pair_count}>3")
        if any(len(item.get("text", "")) > MAX_DOCUMENT_TEXT_CHARS for item in texts):
            reasons.append("single_transcription_exceeds_document_capacity")
    if extra_spreads and not reasons:
        reasons.append(f"allocated_content_pages={len(units)}>{base_content_pages}")
    return {
        "documented_template": template,
        "media_count": media_count,
        "document_pair_count": pair_count,
        "transcription_chars": text_chars,
        "continuation_spreads": extra_spreads,
        "continuation_reasons": reasons,
        "allocated_content_pages": len(units),
    }


def build_page_plan_data(families: list[dict[str, Any]]) -> dict[str, Any]:
    compact_plan = intro_plan()
    intro_sections = intro_sections_from_plan(compact_plan)
    previous_signature: tuple[Any, ...] | None = None
    stable_after = 0
    family_entries: list[dict[str, Any]] = []
    back_start = 0
    for iteration in range(1, 6):
        page = FIRST_FAMILY_PAGE
        family_entries = []
        for family in families:
            if page % 2:
                page += 1
            requirements = family_requirements(family)
            base_count = 4 if family.get("template") == "extended" else 2
            page_count = base_count + requirements["continuation_spreads"] * 2
            family_entries.append(
                {
                    "section_id": family["hero_id"],
                    "type": "family",
                    "hero_id": family["hero_id"],
                    "order": int(family["order"]),
                    "hero_name": family.get("hero_name", ""),
                    "template": family.get("template", "standard"),
                    "start_page": page,
                    "end_page": page + page_count - 1,
                    "page_count": page_count,
                    "spread_count": page_count // 2,
                    "start_side": "left",
                    "continuation_spreads": requirements["continuation_spreads"],
                    "continuation_reasons": requirements["continuation_reasons"],
                    "requirements": requirements,
                    "review_flags": list(family.get("review_flags") or []),
                }
            )
            page += page_count
        if page % 2:
            page += 1
        back_start = page
        signature = tuple(
            (
                item["hero_id"],
                item["start_page"],
                item["end_page"],
                item["continuation_spreads"],
            )
            for item in family_entries
        )
        if signature == previous_signature:
            stable_after = iteration
            break
        previous_signature = signature
    if not stable_after:
        raise RuntimeError("Pagination did not stabilize after five passes")
    back_section = {
        "section_id": "editorial-finale",
        "title": "Память продолжается",
        "type": "back_matter",
        "start_page": back_start,
        "end_page": back_start + BACK_MATTER_PAGES - 1,
        "spread_count": 1,
        "review_status": "OWNER_APPROVAL_REQUIRED",
    }
    sections = [*intro_sections, *family_entries, back_section]
    return {
        "schema_version": 2,
        "generator": "scripts/build_book.py",
        "design_lock": "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf",
        "compact_intro": repo_path(INTRO_PDF),
        "cover_included": False,
        "geometry": {
            "trim_mm": list(TRIM_MM),
            "bleed_mm": BLEED_MM,
            "media_box_mm": list(MEDIA_MM),
            "preview_spread_mm": [526, 206],
            "safe_zone_inner_mm": INNER_SAFE_MM,
        },
        "pagination": {
            "frontmatter_pages": FRONTMATTER_PAGES,
            "first_family_page": FIRST_FAMILY_PAGE,
            "family_pages": sum(item["page_count"] for item in family_entries),
            "backmatter_pages": BACK_MATTER_PAGES,
            "total_interior_pages": back_section["end_page"],
            "toc_pages": [12, 13],
            "stable": True,
            "stable_after_iteration": stable_after,
        },
        "intro_sections": intro_sections,
        "families": family_entries,
        "back_matter": [back_section],
        "sections": sections,
    }


def build_toc_data(
    page_plan: dict[str, Any], families: list[dict[str, Any]]
) -> dict[str, Any]:
    family_by_id = {item["hero_id"]: item for item in families}
    family_rows = []
    for planned in page_plan["families"]:
        family = family_by_id[planned["hero_id"]]
        family_rows.append(
            {
                "kind": "family",
                "order": planned["order"],
                "hero_id": planned["hero_id"],
                "title": family.get("hero_name", ""),
                "children": list(family.get("children") or []),
                "region_id": family.get("region_id"),
                "start_page": planned["start_page"],
                "end_page": planned["end_page"],
                "page_label": str(planned["start_page"]),
                "template": planned["template"],
                "continuation_spreads": planned["continuation_spreads"],
            }
        )
    return {
        "schema_version": 2,
        "source_page_plan": "page-plan.json",
        "stable": page_plan["pagination"]["stable"],
        "intro_sections": [dict(item, kind="intro") for item in page_plan["intro_sections"]],
        "families": family_rows,
        "back_matter": [dict(item, kind="back_matter") for item in page_plan["back_matter"]],
    }


def image_dimensions(path: str) -> tuple[int, int] | None:
    source = ROOT / path
    if not source.is_file() or source.suffix.lower() in {".svg", ".pdf", ".txt", ".json"}:
        return None
    try:
        with Image.open(source) as image:
            return int(image.width), int(image.height)
    except OSError:
        return None


def placement_record(
    *,
    source_id: str,
    hero_id: str | None,
    source_type: str,
    source_file: str,
    output_pages: list[int],
    status: str = "placed",
    x_mm: float | None = None,
    y_mm: float | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    fit_mode: str | None = None,
    crop_policy: str = "none",
    notes: str = "",
    source_quality_policy: str | None = None,
) -> dict[str, Any]:
    dimensions = image_dimensions(source_file)
    effective_dpi: float | str | None = None
    if source_file.lower().endswith(".svg"):
        effective_dpi = "vector"
    elif dimensions and width_mm and height_mm:
        ppi_x = dimensions[0] / (width_mm / 25.4)
        ppi_y = dimensions[1] / (height_mm / 25.4)
        effective_dpi = round(
            max(ppi_x, ppi_y) if fit_mode == "contain" else min(ppi_x, ppi_y),
            1,
        )
    return {
        "source_id": source_id,
        "hero_id": hero_id,
        "source_type": source_type,
        "source_file": source_file,
        "output_pages": output_pages,
        "status": status,
        "placement": {
            "x_mm": x_mm,
            "y_mm": y_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "fit_mode": fit_mode,
            "crop_policy": crop_policy,
        },
        "dimensions_px": list(dimensions) if dimensions else None,
        "effective_dpi": effective_dpi,
        "source_quality_policy": source_quality_policy,
        "notes": notes,
    }


def canonical_css() -> str:
    css = v21.base_css()
    css = re.sub(r"@font-face\{font-family:(?:Onest|Golos);[^}]+\}", "", css)
    css = css.replace(
        "../../fonts/MarckScript.ttf",
        (ROOT / "design/fonts/MarckScript.ttf").as_uri(),
    )
    css = static_font_face_css() + css
    return css


def static_font_face_css() -> str:
    static_dir = ROOT / "design/fonts/static-print"
    faces = []
    for family, prefix in (("Onest", "Onest"), ("Golos", "GolosText")):
        for weight in (400, 500, 600, 650, 700, 750, 800):
            path = static_dir / f"{prefix}-{weight}.ttf"
            if not path.is_file():
                raise FileNotFoundError(
                    f"Static print font is missing: {path}. "
                    "Run scripts/build_static_print_fonts.py"
                )
            faces.append(
                f"@font-face{{font-family:{family};src:url('{path.as_uri()}') "
                f"format('truetype');font-weight:{weight};font-style:normal;font-display:block}}"
            )
    faces.append(
        "@font-face{font-family:Marck;src:url('"
        + (ROOT / "design/fonts/MarckScript.ttf").as_uri()
        + "') format('truetype');font-weight:400;font-style:normal;font-display:block}"
    )
    return "".join(faces)


FAMILY_CSS = r"""
@page{size:266mm 206mm;margin:0}
html,body{margin:0;padding:0;background:#8b8e92;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.print-sheet{position:relative;width:266mm;height:206mm;overflow:hidden;page-break-after:always;background:var(--page_background)}
.print-sheet:last-child{page-break-after:auto}
.print-sheet>.page{left:3mm!important;top:3mm!important;width:260mm;height:200mm}
.print-sheet>.page.left .run{right:22mm!important}
.print-sheet>.page.right .run{left:22mm!important}
.generated-family-open .hero-cutout:not(.manual-flagship){left:auto!important;right:0!important;bottom:-1mm!important;width:152mm!important;height:193mm!important;object-fit:contain!important;object-position:center bottom!important;mix-blend-mode:multiply}
.generated-family-open .hero-cutout.manual-flagship{left:auto!important;right:var(--flagship-right,0mm)!important;bottom:var(--flagship-bottom,-1mm)!important;width:auto!important;height:var(--flagship-height,193mm)!important;max-width:none;object-fit:contain;object-position:center bottom;mix-blend-mode:var(--flagship-blend,normal)}
.generated-family-open .hero-meta{width:94mm}.generated-family-open .hero-meta h1{font-size:28pt}
.generated-family-open .hero-meta .who{box-sizing:border-box;width:94mm;max-width:94mm;margin-top:2.6mm;padding:2.2mm 3.2mm 2.4mm 4mm;background:rgba(251,251,249,.91);border-left:.75mm solid rgba(148,77,84,.88);box-shadow:0 .45mm 1.4mm rgba(25,36,48,.07);line-height:1.34}
.generated-family-open .hero-map{
 opacity:.50
}
.generated-family-open .hero-map[src*="reference-fallback"]{
 mix-blend-mode:multiply;
 filter:saturate(.82) contrast(.96)
}
.generated-family-open .hero-quote{width:108mm}
.generated-family-open .hero-symbols .emblem{width:20mm;height:24mm}.generated-family-open .hero-symbols .medal{width:18mm;height:31mm}
.generated-family-open.hero-013 .hero-symbols{top:108mm}
.flagship-placeholder{position:absolute;right:18mm;top:39mm;bottom:20mm;width:118mm;z-index:3;display:flex;flex-direction:column;align-items:center;justify-content:center;border:.35mm dashed rgba(34,59,94,.25);background:rgba(251,251,249,.34);color:var(--secondary_text);text-align:center}.flagship-placeholder strong{font:650 10pt/1.3 var(--head);color:var(--primary_navy)}.flagship-placeholder small{margin-top:3mm;font:600 5.5pt/1 var(--head);letter-spacing:.14em;text-transform:uppercase}
.family-doc,.family-gallery,.family-review{background:linear-gradient(112deg,#f4f3ef,#ebe9e3)}
.page-title{position:absolute;left:22mm;top:14mm;z-index:8}.page-title h2{margin-top:2mm;font:800 19pt/1.05 var(--head);color:var(--primary_navy)}
.doc-paper{position:absolute;z-index:3;background:radial-gradient(circle at 13% 7%,rgba(118,89,46,.04),transparent 34%),repeating-linear-gradient(0deg,rgba(38,59,83,.022) 0,rgba(38,59,83,.022) .15mm,transparent .15mm,transparent 1.45mm),#f8f6ef;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(25,36,48,.10);overflow:hidden}
.doc-paper::before{content:"";position:absolute;inset:0;background-image:var(--letter-bg);background-position:85% 50%;background-size:68% auto;background-repeat:no-repeat;opacity:.07;filter:grayscale(1) contrast(.86)}
.doc-paper.has-visible-scan::before{display:none}
.doc-label{position:relative;z-index:3;font:700 5.8pt/1 var(--head);letter-spacing:.13em;text-transform:uppercase;color:var(--primary_navy)}
.doc-scan{position:absolute;z-index:4;object-fit:contain;background:rgba(251,251,249,.94);border:.35mm solid #fff;box-shadow:0 .7mm 1.6mm rgba(38,43,48,.12)}
.doc-copy{position:relative;z-index:3;font:400 12pt/1.30 var(--script);color:#292827}.doc-copy p{margin:0 0 2.2mm;break-inside:avoid}
.standard-doc .doc-paper{left:104mm;right:18mm;top:26mm;height:156mm;padding:7mm 9mm 7mm 10mm}.standard-doc .doc-copy{margin-top:4mm;columns:1;column-gap:7mm;font-size:14.2pt;line-height:1.32}
.standard-doc .doc-paper.text-micro{top:48mm;height:108mm;padding:9mm 11mm 9mm 12mm}.standard-doc .doc-paper.text-micro .doc-copy{font-size:21pt;line-height:1.34}
.standard-doc .doc-paper.text-short{top:38mm;height:132mm;padding:8mm 10mm 8mm 11mm}.standard-doc .doc-paper.text-short .doc-copy{font-size:18pt;line-height:1.34}
.standard-doc .doc-paper.text-medium .doc-copy{font-size:14.7pt;line-height:1.27}
.standard-doc .doc-paper.text-long .doc-copy{columns:2;column-gap:7mm;font-size:12.4pt;line-height:1.23}
.standard-doc .doc-paper.text-long .doc-copy p,.standard-doc .doc-paper.text-dense .doc-copy p{break-inside:auto}
.standard-doc .doc-paper.text-dense .doc-copy{margin-top:3mm;columns:2;column-gap:7mm;font-size:11.7pt;line-height:1.22}
.standard-doc.wide-media .standard-media{width:100mm}.standard-doc.wide-media .doc-paper{left:128mm}.standard-doc.wide-media .doc-paper.text-short .doc-copy{font-size:16pt;line-height:1.28}
.standard-doc.missing-document .doc-paper{top:54mm;height:auto;min-height:54mm;padding:9mm 10mm}.standard-doc.missing-document .doc-copy{margin-top:5mm;columns:1;font:400 11pt/1.45 var(--body);color:var(--body_text)}
.standard-media{position:absolute;left:20mm;top:30mm;width:76mm;height:150mm}
.standard-media figure,.gallery-grid figure,.doc-side-media,.doc-scan-figure{position:relative;margin:0;min-width:0;min-height:0;overflow:hidden;background:#e9e7e1;border:.35mm solid #fff;box-shadow:0 .7mm 1.7mm rgba(38,43,48,.11)}
.standard-media figure{position:absolute}
.standard-media img,.gallery-grid img,.doc-side-media img,.doc-scan-figure img{display:block;width:100%;height:100%;object-fit:contain;background:#eceae4}
.standard-media .media-letter{background:#f8f6ef;box-shadow:0 .7mm 1.8mm rgba(38,43,48,.13)}
.media-cap{position:absolute;left:0;right:0;bottom:0;padding:1.7mm 2.2mm;background:rgba(251,251,249,.94);border-left:.7mm solid var(--accent_burgundy);font:600 5.2pt/1.2 var(--head);letter-spacing:.05em;text-transform:uppercase;color:var(--primary_navy)}
.extended-doc .doc-paper{left:20mm;right:20mm;top:29mm;height:151mm;padding:7mm 9mm 7mm 78mm}.extended-doc .doc-copy{margin-top:4mm;columns:1;column-gap:8mm;font-size:14.2pt;line-height:1.30}
.extended-doc .doc-paper.text-micro .doc-copy{font-size:20pt;line-height:1.34}.extended-doc .doc-paper.text-short .doc-copy{font-size:17pt;line-height:1.34}.extended-doc .doc-paper.text-medium .doc-copy{font-size:14.8pt;line-height:1.32}.extended-doc .doc-paper.text-long .doc-copy{font-size:13.2pt;line-height:1.27}.extended-doc .doc-paper.text-dense{padding-left:62mm}.extended-doc .doc-paper.text-dense .doc-copy{columns:2;font-size:11.3pt;line-height:1.14}
.extended-doc:not(.with-side-media) .doc-paper.text-micro{top:37mm;height:134mm;padding-top:9mm;padding-bottom:9mm}
.extended-doc.with-side-media .doc-paper{right:82mm;padding-left:66mm}.extended-doc.with-side-media .doc-paper.text-micro .doc-copy{font-size:17pt}.extended-doc.with-side-media .doc-paper.text-short .doc-copy{font-size:15pt}.extended-doc.with-side-media .doc-paper.text-medium .doc-copy{font-size:12.8pt;line-height:1.24}.extended-doc.with-side-media .doc-paper.text-long .doc-copy{font-size:11.5pt;line-height:1.20}.extended-doc.with-side-media .doc-paper.text-dense .doc-copy{columns:1;font-size:10.95pt;line-height:1.17}
.doc-scan-figure{position:absolute;z-index:5}.doc-side-media{position:absolute}
.gallery-grid{position:absolute;left:20mm;right:20mm;top:40mm;bottom:22mm;display:grid;gap:4mm}
.gallery-grid.count-1{grid-template-columns:1fr}.gallery-grid.count-2{grid-template-columns:1fr 1fr}.gallery-grid.count-3{grid-template-columns:1.15fr .85fr;grid-template-rows:1fr 1fr}.gallery-grid.count-3 figure:first-child{grid-row:1/3}.gallery-grid.count-4{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}.gallery-grid.count-5{grid-template-columns:repeat(6,1fr);grid-template-rows:1fr 1fr}.gallery-grid.count-5 figure:nth-child(1){grid-column:1/4}.gallery-grid.count-5 figure:nth-child(2){grid-column:4/7}.gallery-grid.count-5 figure:nth-child(3){grid-column:1/3}.gallery-grid.count-5 figure:nth-child(4){grid-column:3/5}.gallery-grid.count-5 figure:nth-child(5){grid-column:5/7}.gallery-grid.count-6{grid-template-columns:repeat(3,1fr);grid-template-rows:1fr 1fr}
.family-facsimile{background:linear-gradient(112deg,#f4f3ef,#ebe9e3)}.facsimile-stage{position:absolute;left:28mm;right:28mm;top:34mm;bottom:21mm;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 18% 12%,rgba(118,89,46,.045),transparent 35%),#f8f6ef;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(25,36,48,.10)}.facsimile-stage img{display:block;max-width:94%;max-height:94%;object-fit:contain;filter:contrast(.96)}
.family-review .review-paper{position:absolute;left:32mm;right:32mm;top:48mm;padding:12mm 14mm;background:#fbfbf9;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(38,43,48,.10)}.review-paper h2{font:800 20pt/1.1 var(--head);color:var(--primary_navy)}.review-paper p{margin-top:5mm;font:400 12pt/1.5 var(--body);color:var(--body_text)}
.page.right.standard-doc .standard-media{left:22mm}.page.right.extended-doc .doc-paper{left:22mm}.page.right.extended-doc .doc-scan{left:28mm}.page.right.family-gallery .gallery-grid{left:22mm}
.page.left.extended-doc .doc-paper{right:22mm}.page.left.extended-doc.with-side-media .doc-paper{right:84mm}.page.left.family-gallery .gallery-grid{right:22mm}
.frozen-eugene-open .hero-map{
 left:5mm!important;top:auto!important;bottom:9mm!important;
 width:126mm!important;height:72mm!important;
 opacity:.50!important;
 mix-blend-mode:multiply!important;
 filter:saturate(.74) contrast(.90)!important;
 -webkit-mask-image:linear-gradient(90deg,#000 0%,#000 50%,transparent 72%);
 mask-image:linear-gradient(90deg,#000 0%,#000 50%,transparent 72%)
}
.frozen-eugene-open .hero-meta{left:18mm;top:17mm;width:142mm}.frozen-eugene-open .hero-meta h1{margin-top:2.4mm;font-size:31pt}.frozen-eugene-open .hero-meta .who{width:118mm;max-width:118mm;font-size:8.3pt}
.frozen-eugene-open .hero-symbols{left:19mm;top:69mm}.frozen-eugene-open .hero-cutout:not(.manual-flagship){left:auto!important;right:-1mm!important;top:28mm!important;bottom:auto!important;width:188mm!important;height:162mm!important;object-fit:contain!important;object-position:center bottom!important;mix-blend-mode:multiply!important}
.frozen-eugene-open .hero-quote{left:18mm;right:auto;bottom:17mm;width:112mm;padding:4.5mm 6mm 5mm 8mm}.frozen-eugene-open .hero-quote .quote{font-size:14.5pt;line-height:1.18}
.frozen-eugene-gallery{background:#f5f4f0}.frozen-eugene-gallery .archive-head{position:absolute;left:18mm;top:15mm;z-index:8}.frozen-eugene-gallery .archive-head h2{margin:2mm 0 0;font:800 19pt/1.05 var(--head);color:var(--primary_navy)}
.frozen-eugene-gallery .photo{position:absolute;margin:0;overflow:hidden;background:#ecebe7;box-shadow:0 .6mm 1.8mm rgba(25,36,48,.10)}.frozen-eugene-gallery .photo img{display:block;width:100%;height:100%;object-fit:cover}.frozen-eugene-gallery .photo figcaption{position:absolute;left:0;bottom:0;padding:2.1mm 3.2mm 2.3mm 4mm;background:rgba(252,251,248,.94);border-left:.75mm solid var(--accent_burgundy);font:650 5.6pt/1.2 var(--head);letter-spacing:.06em;text-transform:uppercase;color:var(--primary_navy)}
.frozen-eugene-gallery .p307{left:18mm;top:39mm;width:141mm;height:84mm}.frozen-eugene-gallery .p302{left:164mm;top:20mm;width:75mm;height:164mm}.frozen-eugene-gallery .p303{left:18mm;top:128mm;width:67mm;height:56mm}.frozen-eugene-gallery .p308{left:90mm;top:128mm;width:69mm;height:56mm}.frozen-eugene-gallery .p302 img{object-position:center 20%}.frozen-eugene-gallery .p303 img{object-position:center top}.frozen-eugene-gallery .p308 img{object-position:center 38%}
.frozen-eugene-document{background:linear-gradient(115deg,#f4f3ef,#eceae5)}.frozen-eugene-document .doc-head{position:absolute;left:17mm;top:13mm;z-index:9}.frozen-eugene-document .doc-head h2{margin:2mm 0 0;font:800 17pt/1.05 var(--head);color:var(--primary_navy)}
.frozen-eugene-document .drawing{position:absolute;left:17mm;top:38mm;width:109mm;height:146mm;object-fit:contain;background:#fbfbf8;box-shadow:0 .55mm 1.5mm rgba(25,36,48,.09)}.frozen-eugene-document .scan{position:absolute;display:block;object-fit:contain;background:#faf9f5;filter:saturate(.78) contrast(.9);box-shadow:0 .55mm 1.5mm rgba(25,36,48,.09)}.frozen-eugene-document .scan-short{left:134mm;top:21mm;width:107mm;height:79mm}.frozen-eugene-document .scan-long{left:17mm;top:37mm;width:84mm;height:111mm}
.frozen-eugene-document .paper{position:absolute;overflow:hidden;background:radial-gradient(circle at 14% 8%,rgba(118,89,46,.05),transparent 33%),repeating-linear-gradient(0deg,rgba(38,59,83,.022) 0,rgba(38,59,83,.022) .15mm,transparent .15mm,transparent 1.45mm),#f8f6ef;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .65mm 1.8mm rgba(25,36,48,.10)}.frozen-eugene-document .paper::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(90deg,rgba(255,255,255,.18),transparent 15%,transparent 83%,rgba(111,85,50,.035))}.frozen-eugene-document .paper-label{position:relative;z-index:2;font:700 5.8pt/1 var(--head);letter-spacing:.13em;text-transform:uppercase;color:var(--primary_navy)}
.frozen-eugene-document .transcript-short{left:126mm;top:92mm;width:116mm;height:92mm;padding:6mm 7mm 5mm 9mm}.frozen-eugene-document .transcript-short .copy{position:relative;z-index:2;margin:2.4mm 0 0;font:400 12.8pt/1.18 var(--script);color:#2c3034}.frozen-eugene-document .transcript-short .copy p{margin:0 0 1.5mm;break-inside:avoid}
.frozen-eugene-document .transcript-long{left:96mm;top:14mm;width:146mm;height:170mm;padding:8mm 9mm 7mm 11mm}.frozen-eugene-document .transcript-long .copy{position:relative;z-index:2;margin:3.6mm 0 0;font:400 18.5pt/1.34 var(--script);color:#292e33}.frozen-eugene-document .transcript-long .copy p{margin:0 0 4.5mm}.frozen-eugene-document .scan-label{position:absolute;left:18mm;top:153mm;width:83mm;text-align:center;font:650 5.2pt/1.2 var(--head);letter-spacing:.1em;text-transform:uppercase;color:var(--secondary_text)}
.family-thread-run{box-sizing:border-box;width:174mm;max-width:174mm;display:flex;align-items:baseline;gap:2.7mm;padding-top:1.7mm;border-top:.32mm solid rgba(135,63,70,.72);font:600 5.45pt/1 var(--head);letter-spacing:.04em;text-transform:none;color:var(--secondary_text);white-space:nowrap}
.family-thread-run .thread-name{flex:0 0 auto;font-weight:780;letter-spacing:.12em;text-transform:uppercase;color:var(--primary_navy)}
.family-thread-run .thread-region{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.family-thread-run .thread-spread{flex:0 0 auto;margin-left:auto;font-weight:720;letter-spacing:.09em;text-transform:uppercase;color:var(--accent_burgundy)}
.folio,.run{z-index:30}.wm{display:none!important}
"""


def image_url(source: str, html_dir: Path) -> str:
    return v21.asset_url(source, html_dir)


def family_display(
    family: dict[str, Any], registry: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, str]:
    return v21.family_display(family, registry)


def family_continuity_run(
    family: dict[str, Any], display: dict[str, str], page_number: int,
    start_page: int, page_count: int,
) -> str:
    """Return the restrained footer thread used only by extended families.

    The opening and continuation spreads keep their approved page compositions;
    the shared footer repeats the canonical hero and region so the second spread
    cannot be mistaken for a new family.
    """
    total_spreads = max(1, math.ceil(page_count / 2))
    spread_number = min(
        total_spreads,
        max(1, ((int(page_number) - int(start_page)) // 2) + 1),
    )
    hero_name = str(family.get("hero_name") or "").title()
    region_name = str(display.get("region_name") or "")
    return (
        f'<span class="run family-thread-run" '
        f'data-family-thread="{esc(family.get("hero_id"))}" '
        f'data-family-spread="{spread_number}/{total_spreads}">'
        f'<span class="thread-name">{esc(hero_name)}</span>'
        f'<span class="thread-region">{esc(region_name)}</span>'
        f'<span class="thread-spread">Разворот {spread_number} из {total_spreads}</span>'
        '</span>'
    )


def media_figure(
    source: str,
    html_dir: Path,
    drawing: bool = False,
    css_class: str = "",
    style: str = "",
    label: str | None = None,
) -> str:
    display_label = label or ("Детский рисунок" if drawing else "Семейный архив")
    class_attr = f' class="{esc(css_class)}"' if css_class else ""
    style_attr = f' style="{esc(style)}"' if style else ""
    return (
        f'<figure{class_attr}{style_attr}><img src="{esc(image_url(source, html_dir))}" alt="{esc(display_label)}">'
        f'<figcaption class="media-cap">{esc(display_label)}</figcaption></figure>'
    )


def document_scale_class(text: str) -> str:
    """Return a restrained, readable scale for the available source text.

    Most manuscripts in the reference are short.  Treating all of them as a
    dense two-column article produced tiny type and large sterile voids.  The
    classes below preserve every character while allowing short documents to
    read like the primary object on the page.
    """
    length = len(str(text or "").strip())
    if length <= 180:
        return "text-micro"
    if length <= 330:
        return "text-short"
    if length <= 620:
        return "text-medium"
    if length <= 900:
        return "text-long"
    return "text-dense"


def fitted_media_size(
    source: str, max_width_mm: float, max_height_mm: float,
    *, fallback: tuple[float, float]
) -> tuple[float, float]:
    """Fit an image box to the real aspect ratio without creating a grey tail."""
    dims = image_dimensions(repo_path(source)) if source else None
    if not dims or not dims[0] or not dims[1]:
        return fallback
    scale = min(max_width_mm / dims[0], max_height_mm / dims[1])
    return round(dims[0] * scale, 2), round(dims[1] * scale, 2)


def standard_media_boxes(
    count: int, width: float = 76, *, wide_archive: bool = False,
) -> list[tuple[float, float, float, float]]:
    """Boxes inside the 76 x 150 mm standard documentary rail.

    The last item is the manuscript whenever one is present.  It receives a
    full-width row for counts 3-5, matching the approved documentary intent.
    """
    if wide_archive and count == 4:
        column = (width - 3) / 2
        return [
            (0, 0, width, 42),
            (0, 45, column, 43),
            (column + 3, 45, column, 43),
            (0, 91, width, 59),
        ]
    if count <= 1:
        return [(0, 0, width, 150)]
    if count == 2:
        return [(0, 0, width, 73.5), (0, 76.5, width, 73.5)]
    if count == 3:
        column = (width - 3) / 2
        return [(0, 0, column, 72), (column + 3, 0, column, 72), (0, 75, width, 75)]
    if count == 4:
        column = (width - 3) / 2
        return [
            (0, 0, column, 91),
            (column + 3, 0, column, 44),
            (column + 3, 47, column, 44),
            (0, 94, width, 56),
        ]
    column = (width - 3) / 2
    return [
        (0, 0, column, 44),
        (column + 3, 0, column, 44),
        (0, 47, column, 44),
        (column + 3, 47, column, 44),
        (0, 94, width, 56),
    ]


def standard_content_page(
    family: dict[str, Any], page_number: int, html_dir: Path,
    unit: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if unit is None:
        units = family_content_units(family)
        unit = units[0]
    text = dict(unit.get("text") or {"text": "", "source_file": ""})
    letter = str(unit.get("letter") or "")
    letter_background = str(unit.get("letter_background") or letter)
    media = list(unit.get("media") or [])
    is_missing_document = not text.get("text")
    missing_copy = ""
    if is_missing_document:
        missing_copy = (
            f"<p>{esc(family.get('missing_document_message') or 'Рукопись и расшифровка не представлены в переданных материалах.')}</p>"
        )
    document_label = (
        str(family.get("missing_document_label") or "Состав переданных материалов")
        if is_missing_document
        else (
            "Расшифровка письма · продолжение"
            if int(unit.get("segment_index", 0))
            else "Расшифровка письма"
        )
    )
    document_title = "Документальный комплект" if is_missing_document else "Полный голос семьи"
    run_label = "Семейный архив" if is_missing_document else "Полный текст письма"
    letter_url = image_url(letter, html_dir) if letter else ""
    letter_background_url = (
        image_url(letter_background, html_dir) if letter_background else ""
    )
    media_cell_count = len(media) + (1 if letter else 0)
    wide_archive = family.get("hero_id") == "hero-050" and media_cell_count == 4
    media_width = 100.0 if wide_archive else 76.0
    media_items: list[tuple[str, bool, str, str]] = [
        (path, drawing, "", "Детский рисунок" if drawing else "Семейный архив")
        for path, drawing in media
    ]
    if letter:
        media_items.append((letter, False, "media-letter", "Рукопись"))
    boxes = standard_media_boxes(
        max(1, media_cell_count), media_width, wide_archive=wide_archive
    )
    positioned: list[tuple[str, bool, str, str, tuple[float, float, float, float]]] = []
    for index, item in enumerate(media_items):
        source, drawing, css_class, label = item
        cell_x, cell_y, cell_width, cell_height = boxes[min(index, len(boxes) - 1)]
        width, height = fitted_media_size(
            source,
            cell_width,
            cell_height,
            fallback=(cell_width, cell_height),
        )
        x = cell_x + (cell_width - width) / 2
        y = cell_y + (cell_height - height) / 2
        positioned.append((source, drawing, css_class, label, (x, y, width, height)))
    media_markup = "".join(
        media_figure(
            source,
            html_dir,
            drawing,
            css_class=css_class,
            style=f"left:{x:.2f}mm;top:{y:.2f}mm;width:{width:.2f}mm;height:{height:.2f}mm",
            label=label,
        )
        for source, drawing, css_class, label, (x, y, width, height) in positioned
    )
    scale_class = document_scale_class(str(text.get("text") or ""))
    visible_scan_class = " has-visible-scan" if letter else ""
    markup = f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-doc standard-doc{' wide-media' if wide_archive else ''}{' missing-document' if is_missing_document else ''}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Письмо и семейный архив</p><h2>{document_title}</h2></div>
  <div class="standard-media count-{max(1, media_cell_count)}">{media_markup}</div>
  <article class="doc-paper {scale_class}{visible_scan_class}" data-text-chars="{len(str(text.get('text') or ''))}" style="--letter-bg:url('{esc(letter_background_url)}')"><p class="doc-label">{esc(document_label)}</p><div class="doc-copy">{paragraphs_markup(str(text.get('text') or ''))}{missing_copy}</div></article>
  <span class="folio">{page_number}</span><span class="run">{run_label}</span>
</div>"""
    ledger: list[dict[str, Any]] = []
    media_left = 22.0 if page_number % 2 else 20.0
    if letter and positioned:
        _, _, _, _, (x, y, width, height) = positioned[-1]
        ledger.append(
            placement_record(
                source_id=Path(letter).stem,
                hero_id=family["hero_id"],
                source_type="letter",
                source_file=repo_path(letter),
                output_pages=[page_number],
                x_mm=media_left + x,
                y_mm=30 + y,
                width_mm=width,
                height_mm=height,
                fit_mode="contain",
                notes="Visible physical manuscript; background duplication disabled.",
            )
        )
    if text.get("manifest_file") or text.get("source_file"):
        transcription_source = str(text.get("manifest_file") or text.get("source_file"))
        ledger.append(
            placement_record(
                source_id=Path(transcription_source).stem,
                hero_id=family["hero_id"],
                source_type="transcription",
                source_file=repo_path(transcription_source),
                output_pages=[page_number],
                x_mm=125 if wide_archive else 101,
                y_mm=23,
                width_mm=117 if wide_archive else 141,
                height_mm=156,
                fit_mode="text-flow",
                notes="Clean reader transcription; editorial brackets suppressed.",
            )
        )
    if media:
        for index, (source, drawing) in enumerate(media):
            _, _, _, _, (x, y, width, height) = positioned[index]
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id=family["hero_id"],
                    source_type="drawing" if drawing else "photo",
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=media_left + x,
                    y_mm=30 + y,
                    width_mm=width,
                    height_mm=height,
                    fit_mode="contain",
                    notes="Archive background retained; no face crop.",
                )
            )
    return markup, ledger


def distribute_extended(
    family: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[list[tuple[str, bool]]]]:
    texts = v21.family_texts(family)
    letters = [str(item) for item in family.get("letters", [])]
    pairs = []
    for index in range(max(len(letters), len(texts))):
        pairs.append(
            {
                "letter": letters[index] if index < len(letters) else "",
                "text": texts[index] if index < len(texts) else {"text": "", "source_file": ""},
            }
        )
    media: list[tuple[str, bool]] = [
        (str(item), False) for item in family.get("archive_photos", [])
    ] + [(str(item), True) for item in family.get("drawings", [])]
    if not pairs:
        return [], [media[0:3], media[3:6], media[6:9]]
    doc_pages = len(pairs)
    if len(pairs) == 1 and len(str(pairs[0]["text"].get("text") or "")) > 1000:
        # Keep a long transcription on one readable documentary page; the
        # second reserved content page remains available for a large gallery.
        doc_pages = 1
    gallery_pages = max(0, 3 - doc_pages)
    if gallery_pages:
        buckets: list[list[tuple[str, bool]]] = [[] for _ in range(gallery_pages)]
        for index, item in enumerate(media):
            buckets[index % gallery_pages].append(item)
        return pairs, buckets
    for index, item in enumerate(media):
        pairs[index % len(pairs)].setdefault("side_media", []).append(item)
    return pairs, []


def extended_content_pages(
    family: dict[str, Any], start_page: int, html_dir: Path
) -> tuple[list[str], list[dict[str, Any]]]:
    pairs, galleries = distribute_extended(family)
    pages: list[str] = []
    ledger: list[dict[str, Any]] = []
    page_number = start_page
    for pair in pairs:
        text = pair["text"]
        letter = str(pair.get("letter") or "")
        letter_url = image_url(letter, html_dir) if letter else ""
        side_media = list(pair.get("side_media") or [])[:1]
        side_markup = ""
        with_side = " with-side-media" if side_media else ""
        if side_media:
            source, drawing = side_media[0]
            side_markup = (
                f'<figure class="doc-side-media">{media_figure(source, html_dir, drawing)[8:-9]}</figure>'
            )
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id=family["hero_id"],
                    source_type="drawing" if drawing else "photo",
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=185,
                    y_mm=28,
                    width_mm=55,
                    height_mm=149,
                    fit_mode="contain",
                )
            )
        missing_copy = ""
        if not text.get("text"):
            missing_copy = "<p>Рукопись и расшифровка не представлены в переданных материалах.</p>"
        scan_markup = (
            f'<img class="doc-scan" src="{esc(letter_url)}" alt="Подлинная рукопись">'
            if letter
            else ""
        )
        pages.append(
            f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-doc extended-doc{with_side}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Рукопись и расшифровка</p><h2>Полный голос семьи</h2></div>
  <article class="doc-paper{' dense' if len(str(text.get('text') or '')) > 1050 else ''}" style="--letter-bg:url('{esc(letter_url)}')"><p class="doc-label">Полная читательская версия</p><div class="doc-copy">{paragraphs_markup(str(text.get('text') or ''))}{missing_copy}</div></article>
  {scan_markup}{side_markup}<span class="folio">{page_number}</span><span class="run">Документальный комплект</span>
</div>"""
        )
        if letter:
            ledger.append(
                placement_record(
                    source_id=Path(letter).stem,
                    hero_id=family["hero_id"],
                    source_type="letter",
                    source_file=repo_path(letter),
                    output_pages=[page_number],
                    x_mm=23,
                    y_mm=36,
                    width_mm=43,
                    height_mm=67,
                    fit_mode="contain",
                )
            )
        if text.get("manifest_file") or text.get("source_file"):
            transcription_source = str(text.get("manifest_file") or text.get("source_file"))
            ledger.append(
                placement_record(
                    source_id=Path(transcription_source).stem,
                    hero_id=family["hero_id"],
                    source_type="transcription",
                    source_file=repo_path(transcription_source),
                    output_pages=[page_number],
                    x_mm=17,
                    y_mm=26,
                    width_mm=226 if not side_media else 164,
                    height_mm=151,
                    fit_mode="text-flow",
                )
            )
        page_number += 1
    for bucket in galleries:
        figures = "".join(media_figure(source, html_dir, drawing) for source, drawing in bucket)
        pages.append(
            f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-gallery" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Семейная история</p><h2>Семейный архив</h2></div>
  <div class="gallery-grid count-{max(1, len(bucket))}">{figures}</div>
  <span class="folio">{page_number}</span><span class="run">Семейный архив</span>
</div>"""
        )
        count = max(1, len(bucket))
        cols = 1 if count == 1 else (2 if count <= 4 else 3)
        rows = math.ceil(count / cols)
        width = (220 - (cols - 1) * 4) / cols
        height = (138 - (rows - 1) * 4) / rows
        for index, (source, drawing) in enumerate(bucket):
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id=family["hero_id"],
                    source_type="drawing" if drawing else "photo",
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=17 + (index % cols) * (width + 4),
                    y_mm=37 + (index // cols) * (height + 4),
                    width_mm=width,
                    height_mm=height,
                    fit_mode="contain",
                    notes="Archive background retained; no face crop.",
                )
            )
        page_number += 1
    while len(pages) < 3:
        pages.append(
            f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-review" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <article class="review-paper"><h2>Документальный материал</h2><p>Рукопись и расшифровка не представлены в переданных материалах.</p></article>
  <span class="folio">{page_number}</span><span class="run">Семейный архив</span>
</div>"""
        )
        page_number += 1
    return pages, ledger


def extended_document_unit_page(
    family: dict[str, Any], page_number: int, html_dir: Path,
    unit: dict[str, Any], continuation: bool = False,
    continuity_markup: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    text = dict(unit.get("text") or {"text": "", "source_file": ""})
    letter = str(unit.get("letter") or "")
    background_letter = str(unit.get("letter_background") or letter)
    letter_url = image_url(letter, html_dir) if letter else ""
    background_url = image_url(background_letter, html_dir) if background_letter else ""
    side_media = list(unit.get("media") or [])[:1]
    side_markup = ""
    with_side = " with-side-media" if side_media else ""
    ledger: list[dict[str, Any]] = []
    if side_media:
        source, drawing = side_media[0]
        side_width, side_height = fitted_media_size(
            source, 55, 149, fallback=(55, 149)
        )
        side_top = 31 + (149 - side_height) / 2
        side_right = 20 if page_number % 2 else 22
        side_markup = media_figure(
            source,
            html_dir,
            drawing,
            css_class="doc-side-media",
            style=(
                f"right:{side_right:.2f}mm;top:{side_top:.2f}mm;"
                f"width:{side_width:.2f}mm;height:{side_height:.2f}mm"
            ),
        )
        ledger.append(
            placement_record(
                source_id=Path(source).stem,
                hero_id=family["hero_id"],
                source_type="drawing" if drawing else "photo",
                source_file=repo_path(source),
                output_pages=[page_number],
                x_mm=260 - side_right - side_width,
                y_mm=side_top,
                width_mm=side_width,
                height_mm=side_height,
                fit_mode="contain",
                notes="Archive background retained; frame follows native aspect ratio.",
            )
        )
    missing_copy = ""
    if not text.get("text"):
        missing_copy = "<p>Рукопись и расшифровка не представлены в переданных материалах.</p>"
    scale_class = document_scale_class(str(text.get("text") or ""))
    scan_markup = ""
    scan_box: tuple[float, float, float, float] | None = None
    if letter:
        scan_max_width = 48 if scale_class == "text-dense" else (52 if side_media else 64)
        scan_max_height = 100 if scale_class == "text-dense" else 112
        scan_width, scan_height = fitted_media_size(
            letter, scan_max_width, scan_max_height,
            fallback=(scan_max_width, min(78, scan_max_height))
        )
        scan_left = 28 if page_number % 2 else 26
        scan_top = 42 + (scan_max_height - scan_height) / 2
        scan_box = (scan_left, scan_top, scan_width, scan_height)
        scan_markup = media_figure(
            letter,
            html_dir,
            False,
            css_class="doc-scan-figure",
            style=(
                f"left:{scan_left:.2f}mm;top:{scan_top:.2f}mm;"
                f"width:{scan_width:.2f}mm;height:{scan_height:.2f}mm"
            ),
            label="Рукопись",
        )
    continued_segment = int(unit.get("segment_index", 0)) > 0
    title = "Продолжение полного голоса семьи" if continuation or continued_segment else "Полный голос семьи"
    label = "Продолжение расшифровки" if continued_segment else "Полная читательская версия"
    visible_scan_class = " has-visible-scan" if letter else ""
    run_markup = continuity_markup or (
        f'<span class="run">{"Продолжение семейного архива" if continuation else "Документальный комплект"}</span>'
    )
    markup = f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-doc extended-doc{with_side}{' extended-family-page' if continuity_markup else ''}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Рукопись и расшифровка</p><h2>{title}</h2></div>
  <article class="doc-paper {scale_class}{visible_scan_class}" data-text-chars="{len(str(text.get('text') or ''))}" style="--letter-bg:url('{esc(background_url)}')"><p class="doc-label">{label}</p><div class="doc-copy">{paragraphs_markup(str(text.get('text') or ''))}{missing_copy}</div></article>
  {scan_markup}{side_markup}<span class="folio">{page_number}</span>{run_markup}
</div>"""
    if letter and scan_box:
        scan_left, scan_top, scan_width, scan_height = scan_box
        ledger.append(
            placement_record(
                source_id=Path(letter).stem,
                hero_id=family["hero_id"],
                source_type="letter",
                source_file=repo_path(letter),
                output_pages=[page_number],
                x_mm=scan_left,
                y_mm=scan_top,
                width_mm=scan_width,
                height_mm=scan_height,
                fit_mode="contain",
                notes="Visible physical manuscript; background duplication disabled.",
            )
        )
    if text.get("manifest_file") or text.get("source_file"):
        transcription_source = str(text.get("manifest_file") or text.get("source_file"))
        ledger.append(
            placement_record(
                source_id=Path(transcription_source).stem,
                hero_id=family["hero_id"],
                source_type="transcription",
                source_file=repo_path(transcription_source),
                output_pages=[page_number],
                x_mm=17,
                y_mm=26,
                width_mm=226 if not side_media else 164,
                height_mm=151,
                fit_mode="text-flow",
                notes=(
                    f"Verbatim transcription segment {int(unit.get('segment_index', 0)) + 1}/"
                    f"{int(unit.get('segment_count', 1))}."
                ),
            )
        )
    return markup, ledger


def gallery_unit_page(
    family: dict[str, Any], page_number: int, html_dir: Path,
    unit: dict[str, Any], continuation: bool = False,
    continuity_markup: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    bucket = list(unit.get("media") or [])
    figures = "".join(
        media_figure(source, html_dir, drawing) for source, drawing in bucket
    )
    title = "Продолжение семейного архива" if continuation else "Семейный архив"
    run_markup = continuity_markup or (
        f'<span class="run">{"Продолжение" if continuation else "Семейный архив"}</span>'
    )
    markup = f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-gallery{' extended-family-page' if continuity_markup else ''}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Семейная история</p><h2>{title}</h2></div>
  <div class="gallery-grid count-{max(1, len(bucket))}">{figures}</div>
  <span class="folio">{page_number}</span>{run_markup}
</div>"""
    ledger: list[dict[str, Any]] = []
    count = max(1, len(bucket))
    cols = 1 if count == 1 else (2 if count <= 4 else 3)
    rows = math.ceil(count / cols)
    width = (220 - (cols - 1) * 4) / cols
    height = (138 - (rows - 1) * 4) / rows
    for index, (source, drawing) in enumerate(bucket):
        ledger.append(
            placement_record(
                source_id=Path(source).stem,
                hero_id=family["hero_id"],
                source_type="drawing" if drawing else "photo",
                source_file=repo_path(source),
                output_pages=[page_number],
                x_mm=17 + (index % cols) * (width + 4),
                y_mm=37 + (index // cols) * (height + 4),
                width_mm=width,
                height_mm=height,
                fit_mode="contain",
                notes="Archive background retained; no face crop.",
            )
        )
    return markup, ledger


def facsimile_unit_page(
    family: dict[str, Any], page_number: int, html_dir: Path,
    unit: dict[str, Any], continuation: bool = False,
    continuity_markup: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    letter = str(unit.get("letter") or "")
    letter_url = image_url(letter, html_dir) if letter else ""
    run_markup = continuity_markup or (
        f'<span class="run">{"Продолжение" if continuation else "Семейный архив"}</span>'
    )
    markup = f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} family-facsimile{' extended-family-page' if continuity_markup else ''}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="page-title"><p class="kicker">Подлинный документ</p><h2>Рукопись семьи</h2></div>
  <figure class="facsimile-stage"><img src="{esc(letter_url)}" alt="Подлинная рукопись"></figure>
  <span class="folio">{page_number}</span>{run_markup}
</div>"""
    ledger = []
    if letter:
        ledger.append(
            placement_record(
                source_id=Path(letter).stem,
                hero_id=family["hero_id"],
                source_type="letter",
                source_file=repo_path(letter),
                output_pages=[page_number],
                x_mm=25,
                y_mm=31,
                width_mm=210,
                height_mm=141,
                fit_mode="contain",
                notes="Full-size documentary facsimile used as the parity companion page.",
            )
        )
    return markup, ledger


def render_content_unit(
    family: dict[str, Any], page_number: int, html_dir: Path,
    unit: dict[str, Any], continuation: bool,
    continuity_markup: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    kind = str(unit.get("kind") or "")
    if kind == "document" and unit.get("layout") == "standard":
        return standard_content_page(family, page_number, html_dir, unit)
    if kind == "document":
        return extended_document_unit_page(
            family, page_number, html_dir, unit, continuation, continuity_markup
        )
    if kind == "facsimile":
        return facsimile_unit_page(
            family, page_number, html_dir, unit, continuation, continuity_markup
        )
    return gallery_unit_page(
        family, page_number, html_dir, unit, continuation, continuity_markup
    )


def family_open_page(
    family: dict[str, Any], page_number: int, html_dir: Path,
    registry: dict[str, dict[str, dict[str, Any]]]
) -> tuple[str, list[dict[str, Any]], list[str]]:
    display = family_display(family, registry)
    texts = v21.family_texts(family)
    quote = v21.quote_from_text(texts[0]["text"] if texts else "")
    public_family = dict(family)
    public_family["children"] = [
        re.sub(r"\?{2,}", "…", str(value)) for value in family.get("children", [])
    ]
    markup = v21.family_open_page(public_family, display, page_number, html_dir, quote)
    ledger: list[dict[str, Any]] = []
    notes: list[str] = []
    flagship = str(family.get("flagship") or "")
    if flagship:
        layout = family.get("flagship_layout") if isinstance(family.get("flagship_layout"), dict) else {}
        height = float(layout.get("display_height_mm", 193))
        width = 152.0
        if layout:
            dims = image_dimensions(repo_path(flagship))
            if dims and dims[1]:
                width = round(height * dims[0] / dims[1], 2)
        ledger.append(
            placement_record(
                source_id=Path(flagship).stem,
                hero_id=family["hero_id"],
                source_type="flagship",
                source_file=repo_path(flagship),
                output_pages=[page_number],
                x_mm=max(0, 260 - width - float(layout.get("right_mm", 0))),
                y_mm=max(0, 200 - height - float(layout.get("bottom_mm", -1))),
                width_mm=width,
                height_mm=height,
                fit_mode="contain",
                crop_policy="bottom_only_waist_or_source_limited",
                source_quality_policy=(family.get("flagship_processing") or {}).get("source_quality_policy") if isinstance(family.get("flagship_processing"), dict) else None,
            )
        )
    else:
        notes.append(f"{family['hero_id']}: flagship missing; explicit review flag retained")
        placeholder = (
            '<div class="flagship-placeholder"><strong>Портрет семьи — на сверке</strong>'
            f'<small>{esc(family["hero_id"])}</small></div>'
        )
        markup = markup.rsplit("</div>", 1)[0] + placeholder + "</div>"
    for source_type, source, box in (
        ("map", display.get("map_file", ""), (8, 34, 244, 150)),
        ("emblem", display.get("emblem_file", ""), (44, 78, 20, 24)),
        ("award", display.get("award_file", ""), (20, 78, 18, 31)),
    ):
        if source:
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id=family["hero_id"],
                    source_type=source_type,
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=box[0],
                    y_mm=box[1],
                    width_mm=box[2],
                    height_mm=box[3],
                    fit_mode="contain",
                )
            )
        else:
            notes.append(f"{family['hero_id']}: {source_type} asset unavailable; kept in review queue")
    if quote and texts:
        notes.append(
            f"{family['hero_id']}: opening quote copied verbatim from {texts[0]['source_file']}"
        )
    return markup, ledger, notes


def _source_matching(values: list[Any], token: str, fallback_index: int = 0) -> str:
    sources = [str(value) for value in values if value]
    return next((source for source in sources if token in Path(source).stem), sources[fallback_index] if len(sources) > fallback_index else "")


def frozen_eugene_v20_pages(
    family: dict[str, Any], start: int, html_dir: Path,
    registry: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """Restore the two-spread Eugene composition approved in PRINT_V20.

    This is intentionally a frozen exception to the data-driven family grid:
    the owner approved these four pages as the extended-template reference.
    Text and assets still come from the canonical family manifest.
    """
    if int(start) % 2 or str(family.get("hero_id")) != "hero-014":
        raise RuntimeError("frozen-eugene-v20 requires hero-014 on a left/even page")
    _generic_opening, opening_ledger, notes = family_open_page(
        family, start, html_dir, registry
    )
    display = family_display(family, registry)
    texts = v21.family_texts(family)
    quote_source = texts[1]["text"] if len(texts) > 1 else (texts[0]["text"] if texts else "")
    quote = v21.quote_from_text(quote_source)
    public_family = dict(family)
    public_family["children"] = [
        re.sub(r"\?{2,}", "…", str(value)) for value in family.get("children", [])
    ]
    opening = v21.family_open_page(
        public_family, display, start, html_dir, quote
    ).replace(
        "generated-family-open hero-014",
        "generated-family-open frozen-eugene-open hero-014",
        1,
    )

    archives = list(family.get("archive_photos") or [])
    p302 = _source_matching(archives, "image302", 0)
    p303 = _source_matching(archives, "image303", 1)
    p307 = _source_matching(archives, "image307", 2)
    p308 = _source_matching(archives, "image308", 3)
    drawing = _source_matching(list(family.get("drawings") or []), "image311", 0)
    letters = [str(value) for value in family.get("letters") or []]
    short_letter = _source_matching(letters, "image314", 0)
    long_letter = _source_matching(letters, "image317", 1)
    short_text = texts[0] if texts else {"text": "", "source_file": ""}
    long_text = texts[1] if len(texts) > 1 else {"text": "", "source_file": ""}

    gallery_page = start + 1
    gallery_continuity = family_continuity_run(
        family, display, gallery_page, start, 4
    )
    gallery = f"""
<div class="page right frozen-eugene-gallery extended-family-page" data-page="{gallery_page}" data-hero="hero-014">
  <div class="archive-head"><p class="kicker">Евгений и дети</p><h2>Семейный архив</h2></div>
  <figure class="photo p307"><img src="{esc(image_url(p307, html_dir))}" alt="Семейная фотография"><figcaption>Семейный архив</figcaption></figure>
  <figure class="photo p302"><img src="{esc(image_url(p302, html_dir))}" alt="Семейная фотография"></figure>
  <figure class="photo p303"><img src="{esc(image_url(p303, html_dir))}" alt="Дети с портретом и наградными материалами"></figure>
  <figure class="photo p308"><img src="{esc(image_url(p308, html_dir))}" alt="Семейная фотография"></figure>
  <span class="folio">{gallery_page}</span>{gallery_continuity}
</div>"""

    short_page = start + 2
    short_continuity = family_continuity_run(
        family, display, short_page, start, 4
    )
    short_document = f"""
<div class="page left frozen-eugene-document extended-family-page" data-page="{short_page}" data-hero="hero-014">
  <div class="doc-head"><p class="kicker">Голос семьи</p><h2>Рисунок и две рукописи</h2></div>
  <img class="drawing" src="{esc(image_url(drawing, html_dir))}" alt="Детский рисунок">
  <img class="scan scan-short" src="{esc(image_url(short_letter, html_dir))}" alt="Подлинная рукопись">
  <section class="paper transcript-short"><p class="paper-label">Расшифровка · лист 1</p><div class="copy">{paragraphs_markup(str(short_text.get('text') or ''))}</div></section>
  <span class="folio">{short_page}</span>{short_continuity}
</div>"""

    long_page = start + 3
    long_continuity = family_continuity_run(
        family, display, long_page, start, 4
    )
    long_document = f"""
<div class="page right frozen-eugene-document extended-family-page" data-page="{long_page}" data-hero="hero-014">
  <div class="doc-head"><p class="kicker">Подлинная рукопись</p><h2>Письмо Макара</h2></div>
  <img class="scan scan-long" src="{esc(image_url(long_letter, html_dir))}" alt="Подлинная рукопись Макара">
  <span class="scan-label">Физический скан письма</span>
  <section class="paper transcript-long"><p class="paper-label">Расшифровка · полный текст</p><div class="copy">{paragraphs_markup(str(long_text.get('text') or ''))}</div></section>
  <span class="folio">{long_page}</span>{long_continuity}
</div>"""

    ledger = list(opening_ledger)
    for source, page_number, source_type, box in (
        (p307, gallery_page, "photo", (18, 39, 141, 84)),
        (p302, gallery_page, "photo", (164, 20, 75, 164)),
        (p303, gallery_page, "photo", (18, 128, 67, 56)),
        (p308, gallery_page, "photo", (90, 128, 69, 56)),
        (drawing, short_page, "drawing", (17, 38, 109, 146)),
        (short_letter, short_page, "letter", (134, 21, 107, 79)),
        (long_letter, long_page, "letter", (17, 37, 84, 111)),
    ):
        if source:
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id="hero-014",
                    source_type=source_type,
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=box[0], y_mm=box[1], width_mm=box[2], height_mm=box[3],
                    fit_mode="contain" if source_type != "photo" else "cover",
                    notes="Frozen PRINT_V20 extended-template placement.",
                )
            )
    for text_item, page_number, box in (
        (short_text, short_page, (126, 92, 116, 92)),
        (long_text, long_page, (96, 14, 146, 170)),
    ):
        source = str(text_item.get("manifest_file") or text_item.get("source_file") or "")
        if source:
            ledger.append(
                placement_record(
                    source_id=Path(source).stem,
                    hero_id="hero-014",
                    source_type="transcription",
                    source_file=repo_path(source),
                    output_pages=[page_number],
                    x_mm=box[0], y_mm=box[1], width_mm=box[2], height_mm=box[3],
                    fit_mode="text-flow",
                    notes="Frozen PRINT_V20 extended-template placement; verbatim canonical text.",
                )
            )
    notes.append("hero-014: restored frozen PRINT_V20 extended composition")
    return [opening, gallery, short_document, long_document], ledger, notes


def render_family_source(
    family: dict[str, Any], plan: dict[str, Any],
    registry: dict[str, dict[str, dict[str, Any]]], output_path: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    html_dir = output_path.parent
    start = int(plan["start_page"])
    if str(family.get("hero_id")) == "hero-014":
        if int(plan.get("page_count", 0)) != 4:
            raise RuntimeError("hero-014 frozen PRINT_V20 composition requires four pages")
        pages, ledger, public_notes = frozen_eugene_v20_pages(
            family, start, html_dir, registry
        )
        wrappers = "".join(
            f'<section class="print-sheet">{page}</section>' for page in pages
        )
        document = (
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<title>Письма памяти — {esc(family["hero_id"])}</title>'
            f'<style>{canonical_css()}\n{FAMILY_CSS}</style></head><body>{wrappers}</body></html>'
        )
        write_text(output_path, document)
        return ledger, public_notes
    pages: list[str] = []
    ledger: list[dict[str, Any]] = []
    public_notes: list[str] = []
    opening, opening_ledger, notes = family_open_page(
        family, start, html_dir, registry
    )
    display = family_display(family, registry)
    is_extended = str(family.get("template") or "standard") == "extended"
    pages.append(opening)
    ledger.extend(opening_ledger)
    public_notes.extend(notes)
    base_pages = 4 if family.get("template") == "extended" else 2
    base_content_pages = base_pages - 1
    content_units = family_content_units(family)
    planned_content_pages = int(plan.get("page_count", base_pages)) - 1
    if len(content_units) != planned_content_pages:
        raise RuntimeError(
            f"{family['hero_id']}: pagination/render allocation mismatch: "
            f"plan={planned_content_pages}, units={len(content_units)}"
        )
    for index, unit in enumerate(content_units):
        page_number = start + 1 + index
        continuity_markup = (
            family_continuity_run(
                family,
                display,
                page_number,
                start,
                int(plan.get("page_count", base_pages)),
            )
            if is_extended
            else ""
        )
        markup, unit_ledger = render_content_unit(
            family,
            page_number,
            html_dir,
            unit,
            continuation=index >= base_content_pages,
            continuity_markup=continuity_markup,
        )
        pages.append(markup)
        ledger.extend(unit_ledger)
    wrappers = "".join(f'<section class="print-sheet">{page}</section>' for page in pages)
    document = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f'<title>Письма памяти — {esc(family["hero_id"])}</title>'
        f'<style>{canonical_css()}\n{FAMILY_CSS}</style></head><body>{wrappers}</body></html>'
    )
    write_text(output_path, document)
    return ledger, public_notes


def materialize_all_maps(
    families: list[dict[str, Any]],
    registry: dict[str, dict[str, dict[str, Any]]],
    output_dir: Path,
) -> None:
    source_map = ROOT / "design/prototypes/print-v11/assets/maps/map-ru.svg"
    if not source_map.is_file():
        raise FileNotFoundError(source_map)
    map_dir = output_dir / "generated-assets/maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    report: list[dict[str, Any]] = []
    region_ids = sorted({str(item.get("region_id") or "") for item in families})
    for region_id in region_ids:
        region = registry["regions"].get(region_id)
        feature_id = v21.text_value(region, "map_feature_id", "feature_id")
        if not region or not feature_id:
            report.append(
                {
                    "region_id": region_id,
                    "status": "review_required",
                    "reason": "canonical map_feature_id is missing",
                }
            )
            continue
        root = ET.parse(source_map).getroot()
        view_box = root.attrib.pop("viewbox", root.attrib.get("viewBox", "0 0 1000 666"))
        root.set("viewBox", view_box)
        root.set("width", "1000")
        root.set("height", "666")
        root.set("role", "img")
        root.set("aria-label", v21.text_value(region, "official_name", "name") or region_id)
        features = next((child for child in list(root) if child.attrib.get("id") == "features"), None)
        if features is None:
            raise RuntimeError("Verified base map has no #features group")
        for child in list(root):
            if child is not features:
                root.remove(child)
        target_found = False
        features.set("fill", "#d9dde1")
        features.set("stroke", "#f8f8f5")
        features.set("stroke-width", "1.15")
        for feature in features:
            feature.set("fill", "#d9dde1")
            feature.set("stroke", "#f8f8f5")
            feature.set("stroke-width", "1.15")
            if feature.attrib.get("id") == feature_id:
                feature.set("fill", "#873f46")
                feature.set("stroke", "#ffffff")
                feature.set("stroke-width", "2.1")
                target_found = True
        if not target_found:
            report.append(
                {
                    "region_id": region_id,
                    "status": "review_required",
                    "reason": f"feature {feature_id} is absent from verified vector map",
                }
            )
            continue
        destination = map_dir / f"{region_id}.svg"
        ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
        region["generated_print_map_file"] = repo_path(destination)
        report.append(
            {
                "region_id": region_id,
                "map_feature_id": feature_id,
                "status": "generated_from_verified_vector",
                "file": repo_path(destination),
            }
        )
    write_json(map_dir / "map-generation-report.json", {"regions": report})


def family_cache_key(family: dict[str, Any], plan: dict[str, Any]) -> str:
    sources = []
    for value in [family.get("flagship"), *family.get("archive_photos", []), *family.get("drawings", []), *family.get("letters", []), *family.get("transcriptions", [])]:
        if not value:
            continue
        path = ROOT / str(value)
        sources.append(
            {
                "path": repo_path(value),
                "size": path.stat().st_size if path.is_file() else None,
                "mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
            }
        )
    # Family pages also depend on canonical display registries and the render
    # implementation itself.  Keeping those dependencies in the cache key
    # prevents stale region labels, emblems, awards, or CSS/HTML from surviving
    # a resumed full-book build.
    shared_dependencies = [
        v21.PRODUCTION_DIR / "regions.json",
        v21.PRODUCTION_DIR / "cities.json",
        v21.PRODUCTION_DIR / "emblems.json",
        v21.PRODUCTION_DIR / "awards.json",
        Path(__file__),
        Path(v21.__file__),
    ]
    shared_sources = [
        {
            "path": repo_path(path),
            "size": path.stat().st_size if path.is_file() else None,
            "mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
        }
        for path in shared_dependencies
    ]
    return stable_digest(
        {
            "pipeline_version": 10,
            "family": family,
            "plan": plan,
            "sources": sources,
            "shared_sources": shared_sources,
        }
    )


def select_families(
    families: list[dict[str, Any]], start_family: str | None, count: int | None
) -> list[dict[str, Any]]:
    start_index = 0
    if start_family:
        candidate = start_family.strip()
        if candidate.isdigit():
            order = int(candidate)
            start_index = next(
                index for index, item in enumerate(families) if int(item["order"]) == order
            )
        else:
            start_index = next(
                index for index, item in enumerate(families) if item["hero_id"] == candidate
            )
    end = len(families) if count is None else start_index + max(0, count)
    return families[start_index:end]


def patch_intro_toc(
    toc: dict[str, Any], output_html: Path,
    registry: dict[str, dict[str, dict[str, Any]]]
) -> None:
    if not INTRO_HTML.is_file():
        raise FileNotFoundError(f"V23 intro HTML is missing: {INTRO_HTML}")
    soup = BeautifulSoup(INTRO_HTML.read_text(encoding="utf-8"), "html.parser")
    year_name_replacements = {
        "Году народного единства": "Году единства народов России",
        "Года народного единства": "Года единства народов России",
        "Годом народного единства": "Годом единства народов России",
    }
    for node in soup.find_all(
        string=lambda value: value
        and any(source in value for source in year_name_replacements)
    ):
        corrected = str(node)
        for source, target in year_name_replacements.items():
            corrected = corrected.replace(source, target)
        node.replace_with(corrected)

    # Keep the future Adina photo page visually reserved without exposing
    # workflow instructions or technical labels in the client PDF.
    adina_page = soup.select_one(".adina-photos")
    if adina_page is not None:
        note = adina_page.select_one(".photo-note")
        if note is not None:
            note.string = "Продолжение фотохроники проекта."
        for caption in adina_page.select(".adina-photo-slot span"):
            caption.decompose()
        run = adina_page.select_one(".run")
        if run is not None:
            run.string = "Фотохроника встречи"
    rows = soup.select(".toc-row")
    if len(rows) != len(toc["families"]):
        raise RuntimeError(
            f"V23 TOC has {len(rows)} rows; canonical plan has {len(toc['families'])}"
        )
    for row, item in zip(rows, toc["families"], strict=True):
        region = registry["regions"].get(str(item.get("region_id") or ""), {})
        values = {
            ".toc-num": f"{int(item['order']):02d}",
            ".toc-name": str(item["title"]).title(),
            ".toc-reg": v21.text_value(region, "official_name", "name", "display_name"),
            ".toc-pg": str(item["start_page"]),
        }
        for selector, value in values.items():
            node = row.select_one(selector)
            if node is None:
                raise RuntimeError(f"V23 TOC row has no {selector}")
            node.string = value
    first_contents = soup.select_one(".contents-page .contents-head")
    if first_contents is not None:
        heading = first_contents.select_one("h2")
        if heading is not None:
            heading.string = "Наши герои · 74 семьи"
        note = first_contents.select_one(".cont-note")
        if note is not None:
            intro = {item["section_id"]: item for item in toc.get("intro_sections", [])}
            finale = (toc.get("back_matter") or [{}])[0]
            note.string = (
                f"Партнёры {intro.get('partners', {}).get('start_page', 1)} · "
                f"География {intro.get('geography', {}).get('start_page', 2)} · "
                f"Указ {intro.get('official-decree', {}).get('start_page', 3)} · "
                f"Приветствия {intro.get('welcome-words', {}).get('start_page', 4)} · "
                f"Фотохроника {intro.get('chronicle', {}).get('start_page', 5)} · "
                f"Семьи {intro.get('family-section', {}).get('start_page', 14)} · "
                f"Финал {finale.get('start_page', '')}"
            )
    for watermark in soup.select(".wm"):
        watermark.decompose()
    preview_pages = [
        page for sheet in soup.select("section.sheet")
        for page in sheet.select(":scope > .page")
    ]
    if len(preview_pages) != FRONTMATTER_PAGES + 1:
        raise RuntimeError(
            f"V23 preview must contain cover + {FRONTMATTER_PAGES} interior pages"
        )
    for preview_index, page in enumerate(preview_pages):
        if preview_index == 0:
            continue
        folio = page.select_one(".folio")
        if folio is not None:
            folio.string = str(preview_index)
    if soup.head is not None:
        existing_base = soup.head.find("base")
        if existing_base:
            existing_base.decompose()
        base = soup.new_tag("base", href=INTRO_HTML.parent.as_uri() + "/")
        soup.head.insert(1, base)
        font_style = soup.new_tag("style")
        font_style.string = static_font_face_css() + """
.contents-compact .contents-head .cont-note{
  max-width:155mm;text-align:right;font-size:5.5pt;line-height:1.25;
  letter-spacing:.035em;text-transform:none;white-space:nowrap
}
"""
        soup.head.append(font_style)
    write_text(output_html, str(soup))


def patch_back_matter(output_html: Path) -> None:
    if not BACK_MATTER_HTML.is_file():
        raise FileNotFoundError(BACK_MATTER_HTML)
    soup = BeautifulSoup(BACK_MATTER_HTML.read_text(encoding="utf-8"), "html.parser")
    if soup.head is None:
        raise RuntimeError("Back matter HTML has no head")
    base = soup.new_tag("base", href=BACK_MATTER_HTML.parent.as_uri() + "/")
    soup.head.insert(1, base)
    font_style = soup.new_tag("style")
    font_style.string = static_font_face_css()
    soup.head.append(font_style)
    write_text(output_html, str(soup))


def playwright_render(html_path: Path, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "node",
            str(ROOT / "scripts/render_print_prototype.mjs"),
            "--input",
            str(html_path),
            "--output",
            str(pdf_path),
        ],
        cwd=ROOT,
        check=True,
    )


def normalize_family_pdf(source_pdf: Path, output_pdf: Path) -> None:
    reader = PdfReader(source_pdf)
    writer = PdfWriter()
    width_pt = MEDIA_MM[0] * MM_TO_PT
    height_pt = MEDIA_MM[1] * MM_TO_PT
    trim = BLEED_MM * MM_TO_PT
    for source in reader.pages:
        page = PageObject.create_blank_page(width=width_pt, height=height_pt)
        page.merge_transformed_page(
            source,
            Transformation().scale(
                width_pt / float(source.mediabox.width),
                height_pt / float(source.mediabox.height),
            ),
        )
        page.mediabox.lower_left = (0, 0)
        page.mediabox.upper_right = (width_pt, height_pt)
        page.bleedbox.lower_left = (0, 0)
        page.bleedbox.upper_right = (width_pt, height_pt)
        page.trimbox.lower_left = (trim, trim)
        page.trimbox.upper_right = (width_pt - trim, height_pt - trim)
        writer.add_page(page)
    writer.add_metadata({"/Creator": "scripts/build_book.py", "/Producer": "pypdf"})
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def crop_spread_pdf_to_pages(
    spread_pdf: Path, output_pdf: Path, *, skip_first_left: bool = False,
    page_limit: int | None = None
) -> None:
    reader = PdfReader(spread_pdf)
    writer = PdfWriter()
    target_w = MEDIA_MM[0] * MM_TO_PT
    target_h = MEDIA_MM[1] * MM_TO_PT
    trim = BLEED_MM * MM_TO_PT
    pairs: list[tuple[Any, float]] = []
    for index, spread in enumerate(reader.pages):
        if not (skip_first_left and index == 0):
            pairs.append((spread, 0.0))
        pairs.append((spread, 260.0 * MM_TO_PT))
    if page_limit is not None:
        pairs = pairs[:page_limit]
    for spread, offset in pairs:
        page = PageObject.create_blank_page(width=target_w, height=target_h)
        page.merge_transformed_page(spread, Transformation().translate(-offset, 0))
        page.mediabox.lower_left = (0, 0)
        page.mediabox.upper_right = (target_w, target_h)
        page.bleedbox.lower_left = (0, 0)
        page.bleedbox.upper_right = (target_w, target_h)
        page.trimbox.lower_left = (trim, trim)
        page.trimbox.upper_right = (target_w - trim, target_h - trim)
        writer.add_page(page)
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def merge_page_pdfs(sources: Iterable[Path], output_pdf: Path) -> None:
    writer = PdfWriter()
    for source in sources:
        for page in PdfReader(source).pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "Письма памяти — полный черновой том",
            "/Creator": "scripts/build_book.py",
            "/Producer": "pypdf",
        }
    )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def pages_to_spreads(source_pages_pdf: Path, output_pdf: Path) -> None:
    reader = PdfReader(source_pages_pdf)
    if len(reader.pages) % 2:
        raise RuntimeError("Interior page count must be even for spread assembly")
    writer = PdfWriter()
    spread_w = 526.0 * MM_TO_PT
    spread_h = 206.0 * MM_TO_PT
    for index in range(0, len(reader.pages), 2):
        spread = PageObject.create_blank_page(width=spread_w, height=spread_h)
        spread.merge_page(reader.pages[index])
        spread.merge_transformed_page(
            reader.pages[index + 1], Transformation().translate(260.0 * MM_TO_PT, 0)
        )
        writer.add_page(spread)
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def append_pdfs(sources: Iterable[Path], output_pdf: Path) -> None:
    writer = PdfWriter()
    for source in sources:
        for page in PdfReader(source).pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "Письма памяти — клиентский просмотр",
            "/Creator": "scripts/build_book.py",
            "/Producer": "pypdf",
        }
    )
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def poppler_binary(name: str) -> str:
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin"
        / f"{name}.exe"
    )
    if bundled.is_file():
        return str(bundled)
    available = shutil.which(name)
    if available:
        return available
    raise FileNotFoundError(name)


def make_contact_sheet_pdf(source_pdf: Path, output_pdf: Path, temp_dir: Path) -> None:
    render_dir = temp_dir / "contact-render"
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / "spread"
    subprocess.run(
        [poppler_binary("pdftoppm"), "-jpeg", "-r", "42", str(source_pdf), str(prefix)],
        check=True,
        cwd=ROOT,
    )
    images = sorted(render_dir.glob("spread-*.jpg"))
    if not images:
        raise RuntimeError("No spread thumbnails were rendered")
    page_w, page_h = (1754, 1240)  # A4 landscape at 150 dpi
    cols, rows = 2, 3
    margin, gap, label_h = 58, 28, 28
    cell_w = (page_w - 2 * margin - gap) // cols
    cell_h = (page_h - 2 * margin - 2 * gap) // rows
    try:
        font = ImageFont.truetype(str(ROOT / "design/fonts/static-print/Onest-600.ttf"), 18)
    except OSError:
        font = ImageFont.load_default()
    pages: list[Image.Image] = []
    for page_start in range(0, len(images), cols * rows):
        canvas = Image.new("RGB", (page_w, page_h), "#e7e8e9")
        draw = ImageDraw.Draw(canvas)
        for offset, path in enumerate(images[page_start : page_start + cols * rows]):
            index = page_start + offset
            col = offset % cols
            row = offset // cols
            x = margin + col * (cell_w + gap)
            y = margin + row * (cell_h + gap)
            with Image.open(path) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((cell_w, cell_h - label_h), Image.Resampling.LANCZOS)
            draw.text((x, y), f"Spread {index + 1}", fill="#223b5e", font=font)
            canvas.paste(thumb, (x, y + label_h))
        pages.append(canvas)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        output_pdf,
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
    )


def make_review_batches(
    family_spreads_pdf: Path, page_plan: dict[str, Any], output_dir: Path
) -> list[Path]:
    reader = PdfReader(family_spreads_pdf)
    output_dir.mkdir(parents=True, exist_ok=True)
    full_spreads_dir = output_dir / "full-spreads"
    full_spreads_dir.mkdir(parents=True, exist_ok=True)
    render_root = output_dir.parent / "tmp" / "review-batches"
    render_root.mkdir(parents=True, exist_ok=True)
    outputs = []
    families = page_plan["families"]
    spread_cursor = 0
    spans = []
    for item in families:
        count = int(item["spread_count"])
        spans.append((spread_cursor, spread_cursor + count))
        spread_cursor += count
    for start in range(0, len(families), 10):
        end = min(len(families), start + 10)
        writer = PdfWriter()
        first_spread = spans[start][0]
        last_spread = spans[end - 1][1]
        for spread_index in range(first_spread, last_spread):
            writer.add_page(reader.pages[spread_index])
        stem = f"families-{start + 1:02d}-{end:02d}"
        full_spreads_path = full_spreads_dir / f"{stem}-spreads.pdf"
        with full_spreads_path.open("wb") as handle:
            writer.write(handle)
        path = output_dir / f"{stem}.pdf"
        make_contact_sheet_pdf(
            full_spreads_path,
            path,
            render_root / stem,
        )
        outputs.append(path)
    return outputs


def intro_ledger(plan: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(INTRO_HTML.read_text(encoding="utf-8"), "html.parser")
    pages: list[Any] = []
    for sheet in soup.select("section.sheet"):
        pages.extend(sheet.select(":scope > .page"))
    result = []
    # First preview cell is the cover; interior numbering starts at one.
    for preview_index, page in enumerate(pages, start=1):
        interior_page = preview_index - 1
        if interior_page < 1 or interior_page > FRONTMATTER_PAGES:
            continue
        for image in page.select("img[src]"):
            source = str(image.get("src") or "")
            if not source or source.startswith("data:"):
                continue
            resolved = (INTRO_HTML.parent / source).resolve()
            result.append(
                placement_record(
                    source_id=resolved.stem,
                    hero_id=None,
                    source_type="front_matter_image",
                    source_file=repo_path(resolved),
                    output_pages=[interior_page],
                    status="placed",
                    fit_mode="locked-v23",
                )
            )
    return result


def expected_unplaced_records(
    family: dict[str, Any], placed_sources: set[str], planned_pages: list[int]
) -> list[dict[str, Any]]:
    expected: list[tuple[str, str]] = []
    if family.get("flagship"):
        expected.append(("flagship", str(family["flagship"])))
    for key, source_type in (
        ("archive_photos", "photo"),
        ("drawings", "drawing"),
        ("letters", "letter"),
        ("transcriptions", "transcription"),
    ):
        expected.extend((source_type, str(value)) for value in family.get(key, []))
    records = []
    review_flags = list(family.get("review_flags") or [])
    for source_type, source in expected:
        normalized = repo_path(source).casefold()
        if normalized in placed_sources:
            continue
        records.append(
            placement_record(
                source_id=Path(source).stem,
                hero_id=family["hero_id"],
                source_type=source_type,
                source_file=repo_path(source),
                output_pages=[],
                status="review_required" if review_flags else "missing",
                notes=(
                    "Not silently discarded; queued after layout capacity check. "
                    + "; ".join(review_flags)
                ),
            )
        )
    if not family.get("letters"):
        records.append(
            placement_record(
                source_id=f"{family['hero_id']}-physical-letter",
                hero_id=family["hero_id"],
                source_type="letter",
                source_file="",
                output_pages=[],
                status="review_required" if review_flags else "missing",
                notes="No physical manuscript registered in the canonical family manifest.",
            )
        )
    if not family.get("flagship"):
        records.append(
            placement_record(
                source_id=f"{family['hero_id']}-flagship",
                hero_id=family["hero_id"],
                source_type="flagship",
                source_file="",
                output_pages=[],
                status="review_required" if review_flags else "missing",
                notes="No confirmed flagship is registered; the draft page shows a neutral review placeholder.",
            )
        )
    if not family.get("transcriptions"):
        records.append(
            placement_record(
                source_id=f"{family['hero_id']}-transcription",
                hero_id=family["hero_id"],
                source_type="transcription",
                source_file="",
                output_pages=[],
                status="review_required" if review_flags else "missing",
                notes="No reader transcription registered in the canonical family manifest.",
            )
        )
    return records


def build_placement_ledger(
    page_plan: dict[str, Any], family_ledgers: list[dict[str, Any]],
    families: list[dict[str, Any]], notes: list[str]
) -> dict[str, Any]:
    items = [*intro_ledger(page_plan), *family_ledgers]
    by_hero: dict[str, set[str]] = {}
    for item in family_ledgers:
        if item.get("hero_id") and item.get("source_file"):
            by_hero.setdefault(str(item["hero_id"]), set()).add(
                repo_path(str(item["source_file"])).casefold()
            )
    plan_by_id = {item["hero_id"]: item for item in page_plan["families"]}
    for family in families:
        plan = plan_by_id[family["hero_id"]]
        items.extend(
            expected_unplaced_records(
                family,
                by_hero.get(family["hero_id"], set()),
                list(range(plan["start_page"], plan["end_page"] + 1)),
            )
        )
    if BACK_MATTER_DATA.is_file():
        back = page_plan["back_matter"][0]
        items.append(
            placement_record(
                source_id="editorial-finale",
                hero_id=None,
                source_type="text",
                source_file=repo_path(BACK_MATTER_DATA),
                output_pages=list(range(back["start_page"], back["end_page"] + 1)),
                status="review_required",
                notes="Original editorial conclusion; clearly labelled and awaiting owner approval.",
            )
        )
    return {
        "schema_version": 2,
        "scope": "74 canonical families plus locked V23 front matter and editorial finale",
        "source_page_plan": "page-plan.json",
        "items": items,
        "notes": notes,
        "counts": {
            "total": len(items),
            "placed": sum(item["status"] == "placed" for item in items),
            "review_required": sum(item["status"] == "review_required" for item in items),
            "missing": sum(item["status"] == "missing" for item in items),
        },
    }


def write_checkpoint(
    completed: list[str], failed: dict[str, str], cache_keys: dict[str, str]
) -> None:
    write_json(
        CHECKPOINT_DIR / "build-state.json",
        {
            "schema_version": 1,
            "completed": completed,
            "failed": failed,
            "cache_keys": cache_keys,
        },
    )


def read_checkpoint() -> dict[str, Any]:
    path = CHECKPOINT_DIR / "build-state.json"
    return read_json(path) if path.is_file() else {
        "completed": [], "failed": {}, "cache_keys": {}
    }
