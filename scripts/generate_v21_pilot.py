#!/usr/bin/env python3
"""Build the V21 two-pass, data-driven pilot without changing Design Lock V20.

Pass 1 plans the complete 74-family book. Pass 2 injects the stable page
numbers into the locked V20 frontmatter and emits only the first five family
blocks. The approved cover is deliberately excluded from the interior.
"""

from __future__ import annotations

import argparse
import copy
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from pypdf import PageObject, PdfReader, PdfWriter, Transformation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "design/prototypes/print-v21"
V20_PDF = ROOT / "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf"
V20_HTML = ROOT / "design/prototypes/print-v12/interior-combined-v18.html"
ORDER_FILE = ROOT / "content/manifests/reference-family-order-reset.json"
CLASSIFICATION_FILE = ROOT / "assets/families/family-template-classification.json"
PRODUCTION_DIR = ROOT / "content/production"
MM_TO_PT = 72.0 / 25.4
MEDIA_MM = (266.0, 206.0)
TRIM_MM = (260.0, 200.0)
BLEED_MM = 3.0
FRONTMATTER_PAGES = 19
PILOT_FAMILY_IDS = ("hero-001", "hero-003", "hero-004", "hero-005", "hero-006")
FORBIDDEN_PUBLIC_MARKERS = (
    "V4",
    "V5",
    "SKELETON",
    "NOT FOR PRODUCTION",
    "PDF_REFERENCE",
    "FACT_LOCKED",
    "REVIEW_REQUIRED",
    "ПРОТОТИП",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repo_path(path: Path | str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(ROOT)
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def asset_url(path: str, html_dir: Path) -> str:
    if not path:
        return ""
    absolute = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    return Path(os.path.relpath(absolute, html_dir)).as_posix()


def collection(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(isinstance(value, dict) for value in payload.values()):
            return [dict(value, _registry_key=key) for key, value in payload.items()]
    return []


def registry_index(filename: str, keys: Iterable[str], id_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    path = PRODUCTION_DIR / filename
    if not path.is_file():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in collection(read_json(path), keys):
        stable_id = next((item.get(key) for key in id_keys if item.get(key)), item.get("_registry_key"))
        if stable_id:
            result[str(stable_id)] = item
    return result


def text_value(item: dict[str, Any] | None, *keys: str) -> str:
    if not item:
        return ""
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def file_value(item: dict[str, Any] | None, *keys: str) -> str:
    return text_value(item, *keys)


def family_order() -> list[dict[str, Any]]:
    payload = read_json(ORDER_FILE)
    families = payload.get("families", payload) if isinstance(payload, dict) else payload
    return sorted(families, key=lambda item: int(item["reference_order"]))


def classification_index() -> dict[str, dict[str, Any]]:
    payload = read_json(CLASSIFICATION_FILE)
    items = payload.get("families", payload) if isinstance(payload, dict) else payload
    return {str(item["hero_id"]): item for item in items}


def manifest_assets(hero_id: str) -> list[dict[str, Any]]:
    path = ROOT / f"assets/families/{hero_id}/manifest/family-assets.json"
    if not path.is_file():
        return []
    return list(read_json(path).get("assets", []))


def preferred_file(asset: dict[str, Any]) -> str:
    for key in ("print_file", "file", "source_file"):
        value = asset.get(key)
        if value and (ROOT / str(value)).is_file():
            return repo_path(value)
    return repo_path(asset.get("print_file") or asset.get("file") or "")


def dedupe_files(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = repo_path(value)
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def fallback_family(order_item: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    hero_id = str(order_item["hero_id"])
    assets = manifest_assets(hero_id)
    categories: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        categories.setdefault(str(asset.get("category", "")), []).append(asset)

    flagship_assets = categories.get("flagship", [])
    flagship_assets.sort(
        key=lambda item: (
            item.get("layout_role") != "hero_flagship",
            item.get("selection_confidence") != "high",
            item.get("print_qa_status") != "ready_for_layout",
        )
    )
    flagship = preferred_file(flagship_assets[0]) if flagship_assets else ""

    # A confirmed cutout takes precedence without changing the canonical master.
    processed = ROOT / f"assets/processed-flagships/{hero_id}"
    if processed.is_dir():
        cutouts = sorted(processed.glob("*_nobg.png"))
        if cutouts:
            flagship = repo_path(cutouts[0])

    def category_files(name: str) -> list[str]:
        return dedupe_files(preferred_file(asset) for asset in categories.get(name, []))

    transcription_dir = ROOT / f"assets/families/{hero_id}/transcriptions"
    transcriptions = [repo_path(path) for path in sorted(transcription_dir.glob("*_print.txt"))]
    if not transcriptions:
        transcriptions = [repo_path(path) for path in sorted(transcription_dir.glob("*.json"))]

    known_region_ids = {
        "Волгоградская область": "volgograd-oblast",
        "Новосибирская область": "novosibirsk-oblast",
        "Республика Хакасия": "republic-of-khakassia",
    }
    known_city_ids = {
        "г. Волгоград": "city-volgograd",
        "г. Новосибирск": "city-novosibirsk",
        "г. Абакан": "city-abakan",
    }
    known_emblem_ids = {
        "volgograd-oblast": "emblem-volgograd-oblast",
        "novosibirsk-oblast": "emblem-novosibirsk-oblast",
        "republic-of-khakassia": "emblem-republic-of-khakassia",
    }
    region_id = known_region_ids.get(order_item.get("region", ""), "")
    return {
        "schema_version": 1,
        "hero_id": hero_id,
        "order": int(order_item["reference_order"]),
        "hero_name": str(order_item.get("hero_name") or ""),
        "children": list(order_item.get("children") or []),
        "region_id": region_id,
        "city_id": known_city_ids.get(order_item.get("city", ""), ""),
        "emblem_id": known_emblem_ids.get(region_id, ""),
        "award_id": None,
        "template": classification.get("template_variant", "standard"),
        "flagship": flagship,
        "archive_photos": category_files("archive-photos"),
        "drawings": category_files("drawings"),
        "letters": category_files("letters"),
        "transcriptions": transcriptions,
        "review_flags": [classification.get("status")] if str(classification.get("status", "")).startswith("REVIEW") else [],
        "canonical_reference": {
            "reference_pages": order_item.get("reference_pages", []),
            "identity_status": order_item.get("identity_status"),
        },
        "status": "fallback_from_reset_manifest",
        "_fallback_region_name": order_item.get("region"),
        "_fallback_city_name": order_item.get("city"),
    }


def load_families() -> list[dict[str, Any]]:
    order = family_order()
    classifications = classification_index()
    result: list[dict[str, Any]] = []
    for order_item in order:
        hero_id = str(order_item["hero_id"])
        production_path = PRODUCTION_DIR / "families" / f"{hero_id}.json"
        if production_path.is_file():
            family = read_json(production_path)
        else:
            family = fallback_family(order_item, classifications.get(hero_id, {}))
        family["order"] = int(family.get("order", order_item["reference_order"]))
        family["hero_id"] = hero_id
        family.setdefault("hero_name", order_item.get("hero_name", ""))
        family.setdefault("children", order_item.get("children", []))
        family.setdefault("template", classifications.get(hero_id, {}).get("template_variant", "standard"))
        for key in ("archive_photos", "drawings", "letters", "transcriptions", "review_flags"):
            family[key] = list(family.get(key) or [])
        result.append(family)
    return sorted(result, key=lambda item: int(item["order"]))


def read_transcription(path: str) -> str:
    if not path:
        return ""
    source = ROOT / path
    if not source.is_file():
        return ""
    if source.suffix.lower() == ".txt":
        return source.read_text(encoding="utf-8").strip()
    if source.suffix.lower() == ".json":
        payload = read_json(source)
        direct = payload.get("reader_friendly_transcription") or payload.get("print_transcription")
        if direct:
            return str(direct).strip()
        linked = payload.get("print_transcription_file")
        if linked and (ROOT / linked).is_file():
            return (ROOT / linked).read_text(encoding="utf-8").strip()
    return ""


EDITORIAL_BRACKET = re.compile(
    r"\[(?:[^\]]*(?:сверк|неразбор|обрез|утрачен|край|строк|подпис|review|required)[^\]]*)\]",
    re.IGNORECASE,
)


def public_transcription(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    replaced = EDITORIAL_BRACKET.sub("…", clean)
    if replaced != clean:
        changes.append("editorial_bracket_replaced_with_neutral_ellipsis")
    clean = re.sub(r"\n{3,}", "\n\n", replaced).strip()
    return clean, changes


def family_texts(family: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in family.get("transcriptions", []):
        manifest_file = repo_path(path)
        content_source_file = manifest_file
        source_path = ROOT / str(path)
        if source_path.suffix.lower() == ".json" and source_path.is_file():
            payload = read_json(source_path)
            linked = payload.get("print_transcription_file")
            if linked and (ROOT / str(linked)).is_file():
                content_source_file = repo_path(str(linked))
        source_text = read_transcription(str(path))
        public_text, changes = public_transcription(source_text)
        result.append(
            {
                "source_file": content_source_file,
                "manifest_file": manifest_file,
                "text": public_text,
                "public_transformations": changes,
            }
        )
    return result


def quote_from_text(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("\"«»")
        if not line or line == "…":
            continue
        if len(line) <= 145:
            return line
        match = re.match(r"(.{20,145}?[.!?])(?:\s|$)", line)
        if match:
            return match.group(1).strip()
    return ""


def effective_template(family: dict[str, Any]) -> str:
    documented = str(family.get("template") or "standard")
    texts = family_texts(family)
    transcription_chars = sum(len(item["text"]) for item in texts)
    visual_count = (1 if family.get("flagship") else 0) + len(family.get("archive_photos", [])) + len(family.get("drawings", []))
    overflow = len(family.get("letters", [])) >= 2 or transcription_chars > 1200 or visual_count > 4
    return "extended" if documented == "extended" or overflow else "standard"


def build_page_plan(families: list[dict[str, Any]]) -> dict[str, Any]:
    intro_sections = [
        {"section_id": "partners", "title": "Выходные данные и партнёры", "start_page": 1, "end_page": 1},
        {"section_id": "geography", "title": "География проекта", "start_page": 2, "end_page": 3},
        {"section_id": "welcome-words-i", "title": "Приветственные слова", "start_page": 4, "end_page": 9},
        {"section_id": "chronicle", "title": "Диалог поколений — хроника", "start_page": 10, "end_page": 11},
        {"section_id": "welcome-words-ii", "title": "Приветственные слова — продолжение", "start_page": 12, "end_page": 15},
        {"section_id": "contents", "title": "Содержание", "start_page": 16, "end_page": 19},
    ]
    previous_signature = None
    stable_iteration = 0
    family_entries: list[dict[str, Any]] = []
    total_pages = FRONTMATTER_PAGES
    for iteration in range(1, 6):
        page = FRONTMATTER_PAGES + 1
        family_entries = []
        for family in families:
            if page % 2 != 0:
                page += 1
            template = effective_template(family)
            count = 4 if template == "extended" else 2
            family_entries.append(
                {
                    "hero_id": family["hero_id"],
                    "order": int(family["order"]),
                    "hero_name": family.get("hero_name", ""),
                    "template": template,
                    "start_page": page,
                    "end_page": page + count - 1,
                    "page_count": count,
                    "start_side": "left",
                    "rendered_in_pilot": family["hero_id"] in PILOT_FAMILY_IDS,
                    "review_flags": list(family.get("review_flags") or []),
                }
            )
            page += count
        total_pages = page - 1
        signature = tuple((item["hero_id"], item["template"], item["start_page"], item["end_page"]) for item in family_entries)
        if signature == previous_signature:
            stable_iteration = iteration
            break
        previous_signature = signature
    else:
        raise RuntimeError("Pagination did not stabilize after five passes")

    pilot_entries = [entry for entry in family_entries if entry["hero_id"] in PILOT_FAMILY_IDS]
    pilot_end = max(entry["end_page"] for entry in pilot_entries)
    return {
        "schema_version": 1,
        "generator": "scripts/generate_v21_pilot.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design_lock": "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf",
        "cover_included": False,
        "geometry": {
            "trim_mm": [260, 200],
            "bleed_mm": 3,
            "media_box_mm": [266, 206],
            "safe_zone_inner_mm": 22,
        },
        "pagination": {
            "frontmatter_pages": FRONTMATTER_PAGES,
            "first_family_page": 20,
            "full_planned_pages": total_pages,
            "pilot_rendered_pages": pilot_end,
            "stable": stable_iteration > 0,
            "stable_after_iteration": stable_iteration,
            "toc_pages": [16, 17, 18, 19],
        },
        "intro_sections": intro_sections,
        "families": family_entries,
        "pilot_scope": {
            "hero_ids": list(PILOT_FAMILY_IDS),
            "start_page": 20,
            "end_page": pilot_end,
        },
    }


def build_toc(page_plan: dict[str, Any], families: list[dict[str, Any]]) -> dict[str, Any]:
    family_by_id = {family["hero_id"]: family for family in families}
    entries = []
    for planned in page_plan["families"]:
        family = family_by_id[planned["hero_id"]]
        entries.append(
            {
                "kind": "family",
                "order": planned["order"],
                "hero_id": planned["hero_id"],
                "title": family.get("hero_name", ""),
                "region_id": family.get("region_id"),
                "start_page": planned["start_page"],
                "end_page": planned["end_page"],
                "page_label": str(planned["start_page"]),
                "rendered_in_pilot": bool(planned.get("rendered_in_pilot")),
            }
        )
    return {
        "schema_version": 1,
        "source_page_plan": "page-plan.json",
        "stable": bool(page_plan["pagination"]["stable"]),
        "intro_sections": [dict(item, kind="intro") for item in page_plan["intro_sections"]],
        "families": entries,
    }


@dataclass
class Placement:
    hero_id: str | None
    asset_type: str
    source_file: str
    output_pages: list[int]
    role: str
    box_mm: list[float] | None = None
    fit_mode: str | None = None
    clip: bool = False
    public_transformations: list[str] | None = None
    clip_region: str | None = None
    face_safe: bool = False
    source_quality_policy: str | None = None

    def as_dict(self) -> dict[str, Any]:
        effective_dpi: float | str | None = None
        dimensions_px: list[int] | None = None
        if self.source_file and self.box_mm:
            path = ROOT / self.source_file
            if path.is_file() and path.suffix.lower() not in {".svg", ".pdf", ".txt", ".json"}:
                try:
                    with Image.open(path) as image:
                        dimensions_px = [int(image.width), int(image.height)]
                    ppi_x = dimensions_px[0] / (self.box_mm[0] / 25.4)
                    ppi_y = dimensions_px[1] / (self.box_mm[1] / 25.4)
                    # With contain, the image touches only one axis of the
                    # bounding box. The other axis is unused whitespace.
                    effective_dpi = round(max(ppi_x, ppi_y) if self.fit_mode == "contain" else min(ppi_x, ppi_y), 1)
                except OSError:
                    effective_dpi = None
            elif path.suffix.lower() == ".svg":
                effective_dpi = "vector"
        return {
            "hero_id": self.hero_id,
            "asset_id": Path(self.source_file).stem if self.source_file else self.role,
            "asset_type": self.asset_type,
            "source_file": self.source_file,
            "output_pages": self.output_pages,
            "placement_role": self.role,
            "box_mm": self.box_mm,
            "fit_mode": self.fit_mode,
            "clip": self.clip,
            "clip_region": self.clip_region,
            "face_safe": self.face_safe,
            "dimensions_px": dimensions_px,
            "effective_dpi": effective_dpi,
            "source_quality_policy": self.source_quality_policy,
            "public_transformations": self.public_transformations or [],
            "status": "placed" if self.output_pages else "unplaced",
        }


def resolve_reference(relative_src: str, base_dir: Path) -> str:
    if not relative_src or relative_src.startswith(("data:", "http://", "https://")):
        return relative_src
    return repo_path((base_dir / relative_src).resolve())


def intro_placements() -> list[Placement]:
    soup = BeautifulSoup(V20_HTML.read_text(encoding="utf-8"), "html.parser")
    sheets = soup.select("section.sheet")[:8]
    pages: list[Any] = []
    pages.append(sheets[0].select_one(".page.right"))
    for sheet in sheets[1:]:
        pages.extend(sheet.select(":scope > .page"))
    placements: list[Placement] = []
    for page_number, page in enumerate(pages, start=1):
        if page is None:
            continue
        for image in page.select("img[src]"):
            src = resolve_reference(str(image.get("src")), V20_HTML.parent)
            placements.append(
                Placement(
                    hero_id=None,
                    asset_type="intro_image",
                    source_file=src,
                    output_pages=[page_number],
                    role="design_lock_intro",
                    box_mm=None,
                    fit_mode="locked_v20",
                )
            )
    return placements


def registries() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "regions": registry_index("regions.json", ("regions", "items"), ("region_id", "id")),
        "cities": registry_index("cities.json", ("cities", "items"), ("city_id", "id")),
        "emblems": registry_index("emblems.json", ("emblems", "items"), ("emblem_id", "id")),
        "awards": registry_index("awards.json", ("awards", "items"), ("award_id", "id")),
    }


def materialize_pilot_maps(
    families: list[dict[str, Any]],
    registry: dict[str, dict[str, dict[str, Any]]],
    output_dir: Path,
) -> None:
    """Create self-contained vector maps for the rendered pilot families.

    The verified V11 region wrappers reference ``map-ru.svg`` through an
    external ``<use>`` element. Chromium does not reliably preserve that
    external fragment when printing to PDF. The production copy therefore
    keeps only the base map's region paths and applies the canonical
    ``map_feature_id`` directly. No geographic geometry is redrawn.
    """
    source_map = ROOT / "design/prototypes/print-v11/assets/maps/map-ru.svg"
    if not source_map.is_file():
        raise FileNotFoundError(f"Verified base region map is missing: {source_map}")
    map_dir = output_dir / "generated-assets/maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    pilot_by_id = {family["hero_id"]: family for family in families if family.get("hero_id") in PILOT_FAMILY_IDS}
    region_ids = {str(family.get("region_id") or "") for family in pilot_by_id.values()}
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    for region_id in sorted(region_ids):
        region = registry["regions"].get(region_id)
        if not region:
            raise RuntimeError(f"Pilot region is absent from the canonical registry: {region_id}")
        feature_id = text_value(region, "map_feature_id", "feature_id")
        if not feature_id:
            raise RuntimeError(f"Canonical map feature is missing for {region_id}")
        root = ET.parse(source_map).getroot()
        view_box = root.attrib.pop("viewbox", root.attrib.get("viewBox", "0 0 1000 666"))
        root.set("viewBox", view_box)
        root.set("width", "1000")
        root.set("height", "666")
        root.set("role", "img")
        root.set("aria-label", text_value(region, "official_name", "name") or region_id)
        root.set("fill", "#d9dde1")
        root.set("stroke", "#f8f8f5")
        root.set("stroke-width", "1.15")
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
            raise RuntimeError(f"Feature {feature_id} for {region_id} is absent from the verified vector map")
        destination = map_dir / f"{region_id}.svg"
        ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
        region["generated_print_map_file"] = repo_path(destination)


def family_display(family: dict[str, Any], registry: dict[str, dict[str, dict[str, Any]]]) -> dict[str, str]:
    region = registry["regions"].get(str(family.get("region_id") or ""))
    city = registry["cities"].get(str(family.get("city_id") or ""))
    emblem = registry["emblems"].get(str(family.get("emblem_id") or ""))
    award = registry["awards"].get(str(family.get("award_id") or ""))
    region_name = text_value(region, "official_name", "name", "display_name") or str(family.get("_fallback_region_name") or "")
    city_name = text_value(city, "official_name", "name", "display_name") or str(family.get("_fallback_city_name") or "")
    return {
        "region_name": region_name,
        "city_name": city_name,
        "map_file": file_value(
            region,
            "generated_print_map_file",
            "reference_fallback_map_file",
            "map_file",
            "map_asset",
            "map_path",
        ),
        "emblem_file": file_value(
            emblem,
            "file",
            "emblem_file",
            "asset_file",
            "reference_fallback_file",
        ),
        "award_file": file_value(award, "file", "award_file", "asset_file")
        or str(family.get("reference_award_file") or ""),
        "award_name": text_value(award, "official_name", "name", "display_name"),
    }


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def paragraphs_markup(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return "".join(f"<p>{esc(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs)


def image_tag(css_class: str, path: str, alt: str) -> str:
    if not path:
        return ""
    return f'<img class="{css_class}" src="{esc(path)}" alt="{esc(alt)}">'


def layout_number(layout: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(layout.get(key, default))
    except (TypeError, ValueError):
        return default


def flagship_markup(family: dict[str, Any], path: str, alt: str) -> str:
    if not path:
        return ""
    layout = family.get("flagship_layout")
    if not isinstance(layout, dict) or not layout:
        return image_tag("hero-cutout", path, alt)
    height = layout_number(layout, "display_height_mm", 193.0)
    bottom = layout_number(layout, "bottom_mm", -1.0)
    right = layout_number(layout, "right_mm", 0.0)
    blend = "normal" if layout.get("blend_mode") == "normal" else "multiply"
    pose = re.sub(r"[^a-z0-9-]+", "-", str(layout.get("source_pose") or "manual"))
    style = (
        f"--flagship-height:{height:g}mm;"
        f"--flagship-bottom:{bottom:g}mm;"
        f"--flagship-right:{right:g}mm;"
        f"--flagship-blend:{blend}"
    )
    return (
        f'<img class="hero-cutout manual-flagship pose-{esc(pose)}" '
        f'style="{style}" src="{esc(path)}" alt="{esc(alt)}">'
    )


def flagship_box_mm(family: dict[str, Any]) -> list[float]:
    layout = family.get("flagship_layout")
    if isinstance(layout, dict) and layout:
        height = layout_number(layout, "display_height_mm", 193.0)
        source = ROOT / repo_path(str(family.get("flagship") or ""))
        try:
            with Image.open(source) as image:
                width = height * image.width / image.height
        except (OSError, ZeroDivisionError):
            width = 152.0
        return [round(width, 2), round(height, 2)]
    return {
        "hero-001": [152, 193],
        "hero-003": [81, 132],
        "hero-004": [81, 132],
        "hero-005": [152, 116],
        "hero-006": [152, 116],
    }.get(str(family.get("hero_id") or ""), [152, 193])


def family_open_page(
    family: dict[str, Any],
    display: dict[str, str],
    page_number: int,
    html_dir: Path,
    quote: str,
) -> str:
    children = ", ".join(str(item).title() for item in family.get("children", []))
    author_label = "Автор письма" if len(family.get("children", [])) == 1 else "Авторы писем"
    location = " · ".join(part for part in (display["region_name"], display["city_name"]) if part)
    flagship = asset_url(str(family.get("flagship") or ""), html_dir)
    map_file = asset_url(display["map_file"], html_dir)
    emblem_file = asset_url(display["emblem_file"], html_dir)
    award_file = asset_url(display["award_file"], html_dir)
    symbols = "".join(
        part
        for part in (
            image_tag("medal", award_file, display["award_name"] or "Награда из канонического референса"),
            image_tag("emblem", emblem_file, f"Герб: {display['region_name']}"),
        )
        if part
    )
    quote_markup = ""
    if quote:
        quote_markup = (
            '<blockquote class="hero-quote"><p class="label">Из письма</p>'
            f'<p class="quote">«{esc(quote)}»</p></blockquote>'
        )
    return f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} hero-open generated-family-open {esc(family['hero_id'])}" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  {image_tag('hero-map', map_file, f"Карта региона: {display['region_name']}")}
  <div class="hero-meta"><p class="kicker">{esc(location)}</p><h1>{esc(str(family.get('hero_name') or '').title())}</h1><p class="who">{esc(author_label)}: {esc(children)}</p></div>
  <div class="hero-symbols">{symbols}</div>
  {flagship_markup(family, flagship, str(family.get('hero_name') or '').title())}
  {quote_markup}
  <span class="folio">{page_number}</span><span class="run">Знакомство с героем</span>
</div>"""


def standard_document_page(
    family: dict[str, Any], page_number: int, html_dir: Path, texts: list[dict[str, Any]]
) -> tuple[str, list[Placement]]:
    archives = list(family.get("archive_photos", []))
    drawings = list(family.get("drawings", []))
    letters = list(family.get("letters", []))
    transcription = texts[0] if texts else {"text": "", "source_file": "", "public_transformations": []}
    letter = str(letters[0]) if letters else ""
    placements: list[Placement] = []
    media_markup: list[str] = []
    for index, source in enumerate(archives[:2]):
        css_class = "lp-group" if index == 0 else "lp-igor"
        media_markup.append(
            f'<figure class="lp-photo {css_class}"><img src="{esc(asset_url(str(source), html_dir))}" alt="Семейный архив"><figcaption>Семейный архив</figcaption></figure>'
        )
        placements.append(Placement(family["hero_id"], "archive_photo", repo_path(source), [page_number], css_class, [51, 82], "contain"))
    if drawings:
        source = str(drawings[0])
        media_markup.append(
            f'<figure class="lp-drawing"><img src="{esc(asset_url(source, html_dir))}" alt="Детский рисунок"></figure>'
        )
        placements.append(Placement(family["hero_id"], "drawing", repo_path(source), [page_number], "supporting_drawing", [42, 68], "contain"))
    if letter:
        placements.append(Placement(family["hero_id"], "handwriting", repo_path(letter), [page_number], "physical_letter_evidence", [38, 62], "contain"))
    if transcription.get("source_file"):
        placements.append(
            Placement(
                family["hero_id"],
                "transcription",
                repo_path(transcription["source_file"]),
                [page_number],
                "full_transcription",
                public_transformations=list(transcription.get("public_transformations") or []),
            )
        )
    if transcription.get("manifest_file") and transcription.get("manifest_file") != transcription.get("source_file"):
        placements.append(
            Placement(
                family["hero_id"],
                "transcription_manifest",
                repo_path(transcription["manifest_file"]),
                [page_number],
                "transcription_provenance",
            )
        )
    style = f"--letter-bg:url('{esc(asset_url(letter, html_dir))}')" if letter else "--letter-bg:none"
    return (
        f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} letter-page generated-letter" data-page="{page_number}" data-hero="{esc(family['hero_id'])}" style="{style}">
  <p class="letter-heading">Письмо и семейный архив</p>
  {image_tag('letter-evidence', asset_url(letter, html_dir), 'Подлинная рукопись')}
  {''.join(media_markup)}
  <article class="transcript-card"><p class="tc-label">Расшифровка письма</p><hr><div class="transcript">{paragraphs_markup(str(transcription.get('text') or ''))}</div></article>
  <span class="folio">{page_number}</span><span class="run">Полный текст письма</span>
</div>""",
        placements,
    )


def archive_page(family: dict[str, Any], page_number: int, html_dir: Path) -> tuple[str, list[Placement]]:
    media = list(family.get("archive_photos", [])) + list(family.get("drawings", []))
    placements: list[Placement] = []
    figures = []
    classes = ("archive-a", "archive-b", "archive-c", "archive-d")
    for index, source in enumerate(media[:4]):
        source = str(source)
        is_drawing = source in family.get("drawings", [])
        figures.append(
            f'<figure class="generated-photo {classes[index]}"><img src="{esc(asset_url(source, html_dir))}" alt="{esc("Детский рисунок" if is_drawing else "Семейный архив")}"><figcaption>{"Детский рисунок" if is_drawing else "Семейный архив"}</figcaption></figure>'
        )
        placements.append(
            Placement(
                family["hero_id"],
                "drawing" if is_drawing else "archive_photo",
                repo_path(source),
                [page_number],
                classes[index],
                [68, 130],
                "contain",
            )
        )
    return (
        f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} generated-archive" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="archive-title"><p class="kicker">Семейная история</p><h2>Семейный архив</h2></div>{''.join(figures)}
  <span class="folio">{page_number}</span><span class="run">Семейный архив</span>
</div>""",
        placements,
    )


def extended_document_pages(
    family: dict[str, Any], start_page: int, html_dir: Path, texts: list[dict[str, Any]]
) -> tuple[list[str], list[Placement]]:
    letters = [str(item) for item in family.get("letters", [])]
    placements: list[Placement] = []
    pages_markup: list[str] = []
    # Preserve the letter/transcription pairing by index; distribute pairs 1 + 2.
    pairs = []
    for index in range(max(len(letters), len(texts))):
        pairs.append(
            {
                "letter": letters[index] if index < len(letters) else "",
                "transcription": texts[index] if index < len(texts) else {"text": "", "source_file": "", "public_transformations": []},
            }
        )
    buckets = [pairs[:1], pairs[1:]] if len(pairs) > 1 else [pairs, []]
    for offset, bucket in enumerate(buckets):
        page_number = start_page + offset
        modules: list[str] = []
        multi = len(bucket) > 1
        for index, pair in enumerate(bucket):
            letter = pair["letter"]
            transcription = pair["transcription"]
            css_class = f"document-module document-module--{'stack' if multi else 'single'} document-module--{index + 1}"
            modules.append(
                f"""<article class="{css_class}" style="--module-letter:url('{esc(asset_url(letter, html_dir))}')">
  <p class="document-label">Рукопись и полная расшифровка</p>
  <img class="document-scan" src="{esc(asset_url(letter, html_dir))}" alt="Подлинная рукопись">
  <div class="document-copy">{paragraphs_markup(str(transcription.get('text') or ''))}</div>
</article>"""
            )
            if letter:
                placements.append(Placement(family["hero_id"], "handwriting", repo_path(letter), [page_number], "physical_letter", [38, 62] if multi else [40, 65], "contain"))
            if transcription.get("source_file"):
                placements.append(
                    Placement(
                        family["hero_id"],
                        "transcription",
                        repo_path(transcription["source_file"]),
                        [page_number],
                        "full_transcription",
                        public_transformations=list(transcription.get("public_transformations") or []),
                    )
                )
            if transcription.get("manifest_file") and transcription.get("manifest_file") != transcription.get("source_file"):
                placements.append(
                    Placement(
                        family["hero_id"],
                        "transcription_manifest",
                        repo_path(transcription["manifest_file"]),
                        [page_number],
                        "transcription_provenance",
                    )
                )
        pages_markup.append(
            f"""
<div class="page {'left' if page_number % 2 == 0 else 'right'} generated-documents" data-page="{page_number}" data-hero="{esc(family['hero_id'])}">
  <div class="document-title"><p class="kicker">Голос семьи</p><h2>Рукописи и расшифровки</h2></div>{''.join(modules)}
  <span class="folio">{page_number}</span><span class="run">Документальный комплект</span>
</div>"""
        )
    return pages_markup, placements


def base_css() -> str:
    source = V20_HTML.read_text(encoding="utf-8")
    match = re.search(r"<style>([\s\S]*?)</style>", source)
    if not match:
        raise RuntimeError("V20 source CSS was not found")
    return match.group(1)


GENERATED_CSS = r"""
@page{size:266mm 206mm;margin:0}
html,body{margin:0;padding:0;background:#8b8e92}
.print-sheet{position:relative;width:266mm;height:206mm;overflow:hidden;page-break-after:always;background:var(--page_background)}
.print-sheet:last-child{page-break-after:auto}
.print-sheet>.page{left:3mm!important;top:3mm!important;width:260mm;height:200mm}
.print-sheet>.page.left .safe{right:22mm!important}
.print-sheet>.page.right .safe{left:22mm!important}
.print-sheet>.page.left .run{right:22mm!important}
.print-sheet>.page.right .run{left:22mm!important}
.print-sheet>.imprint .safe{left:22mm!important}
.generated-family-open .hero-cutout{mix-blend-mode:multiply}
.generated-family-open .hero-cutout.manual-flagship{left:auto!important;right:var(--flagship-right,0mm)!important;bottom:var(--flagship-bottom,-1mm)!important;width:auto!important;height:var(--flagship-height,193mm)!important;max-width:none;object-fit:contain;object-position:center bottom;mix-blend-mode:var(--flagship-blend,normal)}
.generated-family-open .hero-symbols .emblem{width:18mm;height:22mm}
.generated-family-open .hero-symbols .medal{width:17mm}
.generated-family-open.hero-003 .hero-cutout:not(.manual-flagship),.generated-family-open.hero-004 .hero-cutout:not(.manual-flagship){left:154mm;width:81mm;height:132mm}
.generated-family-open.hero-005 .hero-cutout:not(.manual-flagship),.generated-family-open.hero-006 .hero-cutout:not(.manual-flagship){left:91mm;width:152mm;height:116mm}
.generated-letter::before{display:none!important}
.generated-letter .letter-heading{left:22mm}
.generated-letter .lp-group,.generated-letter .lp-igor{left:22mm}
.letter-evidence{position:absolute;left:73mm;top:23mm;z-index:4;width:38mm;height:62mm;object-fit:contain;background:rgba(251,251,249,.94);border:.35mm solid #fff;box-shadow:0 .9mm 1.9mm rgba(38,43,48,.12)}
.generated-letter .transcript-card{max-height:164mm;overflow:hidden}
.generated-letter .transcript-card .transcript{font-size:12.5pt;line-height:1.42}
.generated-archive,.generated-documents{background:linear-gradient(112deg,#f4f3ef,#ebe9e3)}
.archive-title,.document-title{position:absolute;left:22mm;top:15mm;z-index:8}
.archive-title h2,.document-title h2{margin-top:2mm;font:800 19pt/1.05 var(--head);color:var(--primary_navy)}
.generated-photo{position:absolute;margin:0;overflow:hidden;background:#eceae4;border:.35mm solid #fff;box-shadow:0 .9mm 1.9mm rgba(38,43,48,.12)}
.generated-photo img{display:block;width:100%;height:100%;object-fit:contain;background:#eceae4}
.generated-photo figcaption{position:absolute;left:0;right:0;bottom:0;padding:2mm 3mm;background:rgba(251,251,249,.94);border-left:.8mm solid var(--accent_burgundy);font:650 5.4pt/1.2 var(--head);letter-spacing:.07em;text-transform:uppercase;color:var(--primary_navy)}
.archive-a{left:22mm;top:44mm;width:68mm;height:130mm}.archive-b{left:92mm;top:44mm;width:68mm;height:130mm}
.archive-c{left:166mm;top:44mm;width:68mm;height:130mm}.archive-d{left:166mm;top:44mm;width:68mm;height:130mm}
.document-module{position:absolute;overflow:hidden;background:radial-gradient(circle at 15% 9%,rgba(118,89,46,.045),transparent 33%),repeating-linear-gradient(0deg,rgba(38,59,83,.022) 0,rgba(38,59,83,.022) .15mm,transparent .15mm,transparent 1.45mm),#f8f6ef;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .65mm 1.8mm rgba(25,36,48,.10)}
.document-module::before{content:"";position:absolute;inset:0;background-image:var(--module-letter);background-position:78% 50%;background-size:62% auto;background-repeat:no-repeat;opacity:.06;filter:grayscale(1) contrast(.85)}
.document-module--single{left:18mm;right:18mm;top:39mm;height:143mm;padding:7mm 8mm 7mm 55mm}
.document-module--stack{left:18mm;right:18mm;height:70mm;padding:5mm 7mm 5mm 51mm}
.document-module--stack.document-module--1{top:39mm}.document-module--stack.document-module--2{top:112mm}
.document-label{position:relative;z-index:2;font:700 5.6pt/1 var(--head);letter-spacing:.12em;text-transform:uppercase;color:var(--primary_navy)}
.document-scan{position:absolute;left:5mm;top:5mm;width:40mm;height:65mm;object-fit:contain;background:#fbfbf9}
.document-module--stack .document-scan{width:38mm;height:57mm}
.document-copy{position:relative;z-index:2;margin-top:3mm;columns:2;column-gap:7mm;font:400 12.3pt/1.28 var(--script);color:#2b2a28}
.document-module--stack .document-copy{columns:2;font-size:10.8pt;line-height:1.2}
.document-copy p{margin:0 0 2.4mm;break-inside:avoid}
.print-sheet>.page.left .run{right:22mm}
.print-sheet>.page.right .run{left:22mm}
.generated-letter.right .letter-heading{left:22mm}
.generated-letter.right .lp-group,.generated-letter.right .lp-igor{left:22mm}
.generated-letter.right .lp-drawing{left:78mm}
.generated-archive.right .archive-title,.generated-documents.right .document-title{left:22mm}
.generated-archive.right .archive-a{left:22mm}
.generated-archive.right .archive-b{left:96mm}
.generated-archive.right .archive-c,.generated-archive.right .archive-d{left:170mm}
.contents-page--with-intro .contents-head{margin-bottom:2.8mm}
.toc-intro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.4mm 4mm;margin:0 0 3mm;padding:0 0 3mm;border-bottom:.2mm solid var(--line)}
.toc-intro-item{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:1.5mm;min-height:7mm}
.toc-intro-title{font:600 6.2pt/1.14 var(--head);color:var(--primary_navy)}
.toc-intro-pg{font:700 7.8pt/1 var(--head);color:var(--accent_burgundy)}
.contents-page--with-intro .toc-row{padding:1.18mm 0}
.wm{display:none!important}
"""


def intro_toc_block(toc: dict[str, Any]) -> str:
    items = []
    for section in toc.get("intro_sections", []):
        items.append(
            f'<div class="toc-intro-item" data-section="{esc(section.get("section_id"))}">'
            f'<span class="toc-intro-title">{esc(section.get("title"))}</span>'
            f'<span class="toc-intro-pg">{int(section.get("start_page", 0))}</span></div>'
        )
    return '<nav class="toc-intro-grid" aria-label="Вводные разделы">' + "".join(items) + "</nav>"


def add_intro_toc_to_page(page: Any, toc: dict[str, Any]) -> None:
    classes = list(page.get("class", []))
    if "contents-page--with-intro" not in classes:
        classes.append("contents-page--with-intro")
    page["class"] = classes
    heading = page.select_one(".contents-head")
    if heading is None:
        raise RuntimeError("First contents page has no .contents-head")
    block = BeautifulSoup(intro_toc_block(toc), "html.parser").select_one(".toc-intro-grid")
    heading.insert_after(block)


def render_family_html(
    output_path: Path,
    page_plan: dict[str, Any],
    families: list[dict[str, Any]],
    registry: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[Placement], list[str]]:
    html_dir = output_path.parent
    family_by_id = {family["hero_id"]: family for family in families}
    planned_by_id = {item["hero_id"]: item for item in page_plan["families"]}
    pages: list[str] = []
    placements: list[Placement] = []
    public_notes: list[str] = []
    for hero_id in PILOT_FAMILY_IDS:
        family = family_by_id[hero_id]
        plan = planned_by_id[hero_id]
        display = family_display(family, registry)
        texts = family_texts(family)
        quote = quote_from_text(texts[0]["text"] if texts else "")
        start = int(plan["start_page"])
        open_markup = family_open_page(family, display, start, html_dir, quote)
        pages.append(f'<section class="print-sheet">{open_markup}</section>')
        if family.get("flagship"):
            flagship_box = flagship_box_mm(family)
            layout = family.get("flagship_layout") if isinstance(family.get("flagship_layout"), dict) else {}
            processing = family.get("flagship_processing") if isinstance(family.get("flagship_processing"), dict) else {}
            clips_bottom = layout.get("source_pose") == "full_body"
            placements.append(
                Placement(
                    hero_id,
                    "flagship",
                    repo_path(family["flagship"]),
                    [start],
                    "hero_flagship",
                    flagship_box,
                    "contain",
                    clips_bottom,
                    clip_region="bottom_only" if clips_bottom else None,
                    face_safe=True,
                    source_quality_policy=processing.get("source_quality_policy"),
                )
            )
        for asset_type, source, role, box in (
            ("map", display["map_file"], "region_map", [244, 150]),
            ("emblem", display["emblem_file"], "official_emblem", [18, 22]),
            ("award", display["award_file"], "official_award", [17, 31]),
        ):
            if source:
                placements.append(Placement(hero_id, asset_type, repo_path(source), [start], role, box, "contain", False))
        if quote and texts:
            public_notes.append(f"{hero_id}: quote extracted verbatim from {texts[0]['source_file']}")

        if plan["template"] == "standard":
            document_markup, document_placements = standard_document_page(family, start + 1, html_dir, texts)
            pages.append(f'<section class="print-sheet">{document_markup}</section>')
            placements.extend(document_placements)
        else:
            archive_markup, archive_placements = archive_page(family, start + 1, html_dir)
            pages.append(f'<section class="print-sheet">{archive_markup}</section>')
            placements.extend(archive_placements)
            document_pages, document_placements = extended_document_pages(family, start + 2, html_dir, texts)
            pages.extend(f'<section class="print-sheet">{markup}</section>' for markup in document_pages)
            placements.extend(document_placements)

    document = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Письма памяти — V21 pilot families</title><style>{base_css()}\n{GENERATED_CSS}</style></head><body>{''.join(pages)}</body></html>"""
    output_path.write_text(document, encoding="utf-8")
    return placements, public_notes


def render_toc_html(output_path: Path, toc: dict[str, Any], registry: dict[str, dict[str, dict[str, Any]]]) -> None:
    source = V20_HTML.read_text(encoding="utf-8")
    soup = BeautifulSoup(source, "html.parser")
    style = soup.style.string if soup.style and soup.style.string else base_css()
    sheets = soup.select("section.sheet")
    toc_pages = []
    for sheet in sheets[8:10]:
        toc_pages.extend(sheet.select(":scope > .page"))
    if len(toc_pages) != 4:
        raise RuntimeError(f"Expected four V20 TOC pages, found {len(toc_pages)}")
    rows = [row for page in toc_pages for row in page.select(".toc-row")]
    if len(rows) != len(toc["families"]):
        raise RuntimeError(f"V20 has {len(rows)} TOC rows, canonical data has {len(toc['families'])}")
    for row, item in zip(rows, toc["families"], strict=True):
        region = registry["regions"].get(str(item.get("region_id") or ""))
        row.select_one(".toc-num").string = f"{int(item['order']):02d}"
        row.select_one(".toc-name").string = str(item["title"]).title()
        row.select_one(".toc-reg").string = text_value(region, "official_name", "name", "display_name")
        row.select_one(".toc-pg").string = str(item["start_page"])
    wrappers: list[str] = []
    for page_number, page in enumerate(toc_pages, start=16):
        cloned = BeautifulSoup(str(page), "html.parser").select_one(".page")
        classes = [name for name in cloned.get("class", []) if name not in {"left", "right"}]
        classes.append("left" if page_number % 2 == 0 else "right")
        cloned["class"] = classes
        folio = cloned.select_one(".folio")
        if folio:
            folio.string = str(page_number)
        if page_number == 16:
            add_intro_toc_to_page(cloned, toc)
        wrappers.append(f'<section class="print-sheet">{str(cloned)}</section>')
    override = GENERATED_CSS + "\n.print-sheet>.contents-page{left:3mm!important;top:3mm!important}"
    document = f"<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><title>Динамическое содержание V21</title><style>{style}\n{override}</style></head><body>{''.join(wrappers)}</body></html>"
    output_path.write_text(document, encoding="utf-8")


def render_frontmatter_html(
    output_path: Path, toc: dict[str, Any], registry: dict[str, dict[str, dict[str, Any]]]
) -> None:
    """Clone V20 interior pages 1-19, changing only folios and TOC data."""
    soup = BeautifulSoup(V20_HTML.read_text(encoding="utf-8"), "html.parser")
    sheets = soup.select("section.sheet")[:10]
    if len(sheets) != 10:
        raise RuntimeError(f"Expected ten locked frontmatter spreads, found {len(sheets)}")
    rows = [row for sheet in sheets for row in sheet.select(".toc-row")]
    if len(rows) != len(toc["families"]):
        raise RuntimeError(f"V20 has {len(rows)} TOC rows, canonical data has {len(toc['families'])}")
    for row, item in zip(rows, toc["families"], strict=True):
        region = registry["regions"].get(str(item.get("region_id") or ""))
        row.select_one(".toc-num").string = f"{int(item['order']):02d}"
        row.select_one(".toc-name").string = str(item["title"]).title()
        row.select_one(".toc-reg").string = text_value(region, "official_name", "name", "display_name")
        row.select_one(".toc-pg").string = str(item["start_page"])
    # Cover was counted as page 1 in V20. It is a separate wrap in V21, so
    # every visible interior folio moves down by one.
    for folio in [node for sheet in sheets for node in sheet.select(".folio")]:
        value = folio.get_text(strip=True)
        if value.isdigit():
            folio.string = str(int(value) - 1)
    for watermark in [node for sheet in sheets for node in sheet.select(".wm")]:
        watermark.decompose()
    first_contents_page = sheets[8].select_one(":scope > .page.left.contents-page")
    if first_contents_page is None:
        raise RuntimeError("Locked frontmatter has no first contents page")
    add_intro_toc_to_page(first_contents_page, toc)
    head = soup.head
    if head is None:
        raise RuntimeError("V20 source has no head element")
    base = soup.new_tag("base", href="../print-v12/")
    head.insert(1, base)
    technical_override = soup.new_tag("style")
    technical_override.string = GENERATED_CSS + "\n.sponsor-card--known img{width:16mm!important;height:18mm!important}"
    head.append(technical_override)
    physical_pages = [sheets[0].select_one(":scope > .page.right")]
    for sheet in sheets[1:]:
        physical_pages.extend(sheet.select(":scope > .page"))
    if len(physical_pages) != 19 or any(page is None for page in physical_pages):
        raise RuntimeError(f"Expected 19 cover-free V20 pages, found {len(physical_pages)}")
    page_fragments = [f'<section class="print-sheet">{str(page)}</section>' for page in physical_pages]
    body = soup.body
    body.clear()
    for fragment in page_fragments:
        body.append(BeautifulSoup(fragment, "html.parser"))
    title = soup.title
    if title:
        title.string = "Письма памяти — V21 locked frontmatter with dynamic TOC"
    output_path.write_text(str(soup), encoding="utf-8")


def placement_ledger(
    page_plan: dict[str, Any], placements: list[Placement], public_notes: list[str]
) -> dict[str, Any]:
    items = [placement.as_dict() for placement in [*intro_placements(), *placements]]
    return {
        "schema_version": 1,
        "scope": "V21 pilot: immutable intro plus first five families",
        "source_page_plan": "page-plan.json",
        "pilot_pages": page_plan["pagination"]["pilot_rendered_pages"],
        "items": items,
        "notes": public_notes,
    }


def playwright_render(html_path: Path, pdf_path: Path) -> None:
    command = [
        "node",
        str(ROOT / "scripts/render_print_prototype.mjs"),
        "--input",
        str(html_path),
        "--output",
        str(pdf_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def normalize_boxes(source_pdf: Path, output_pdf: Path) -> None:
    reader = PdfReader(source_pdf)
    writer = PdfWriter()
    writer.pdf_header = "%PDF-1.7"
    width_pt = MEDIA_MM[0] * MM_TO_PT
    height_pt = MEDIA_MM[1] * MM_TO_PT
    inset = BLEED_MM * MM_TO_PT
    for source_page in reader.pages:
        page = PageObject.create_blank_page(width=width_pt, height=height_pt)
        source_width = float(source_page.mediabox.width)
        source_height = float(source_page.mediabox.height)
        page.merge_transformed_page(
            source_page,
            Transformation().scale(width_pt / source_width, height_pt / source_height),
        )
        page.mediabox.lower_left = (0, 0)
        page.mediabox.upper_right = (width_pt, height_pt)
        page.bleedbox.lower_left = (0, 0)
        page.bleedbox.upper_right = (width_pt, height_pt)
        page.trimbox.lower_left = (inset, inset)
        page.trimbox.upper_right = (width_pt - inset, height_pt - inset)
        writer.add_page(page)
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def crop_generated_frontmatter(source_pdf: Path, output_pdf: Path) -> None:
    reader = PdfReader(source_pdf)
    if len(reader.pages) < 10:
        raise RuntimeError("Generated frontmatter does not contain ten locked spreads")
    writer = PdfWriter()
    writer.pdf_header = "%PDF-1.7"
    target_width = MEDIA_MM[0] * MM_TO_PT
    target_height = MEDIA_MM[1] * MM_TO_PT
    trim_inset = BLEED_MM * MM_TO_PT
    physical_pages: list[tuple[Any, float]] = [(reader.pages[0], 260.0 * MM_TO_PT)]
    for spread in reader.pages[1:10]:
        physical_pages.append((spread, 0.0))
        physical_pages.append((spread, 260.0 * MM_TO_PT))
    if len(physical_pages) != 19:
        raise RuntimeError(f"Expected 19 frontmatter pages, got {len(physical_pages)}")
    for spread, x_offset in physical_pages:
        page = PageObject.create_blank_page(width=target_width, height=target_height)
        page.merge_transformed_page(spread, Transformation().translate(-x_offset, 0))
        page.bleedbox.lower_left = (0, 0)
        page.bleedbox.upper_right = (target_width, target_height)
        page.trimbox.lower_left = (trim_inset, trim_inset)
        page.trimbox.upper_right = (target_width - trim_inset, target_height - trim_inset)
        writer.add_page(page)
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def merge_pilot(frontmatter_pdf: Path, family_pdf: Path, output_pdf: Path) -> None:
    writer = PdfWriter()
    writer.pdf_header = "%PDF-1.7"
    for source in (frontmatter_pdf, family_pdf):
        for page in PdfReader(source).pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "Письма памяти — V21 generator pilot",
            "/Subject": "Первые пять семей; Design Lock V20",
            "/Creator": "scripts/generate_v21_pilot.py",
        }
    )
    with output_pdf.open("wb") as handle:
        writer.write(handle)


def poppler_binary(name: str) -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin" / f"{name}.exe"
    if bundled.is_file():
        return str(bundled)
    available = shutil.which(name)
    if available:
        return available
    raise FileNotFoundError(f"Poppler executable not found: {name}")


def make_contact_sheet(pdf_path: Path, output_path: Path, temp_dir: Path) -> None:
    render_dir = temp_dir / "contact-pages"
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / "page"
    subprocess.run(
        [poppler_binary("pdftoppm"), "-png", "-r", "55", str(pdf_path), str(prefix)],
        check=True,
        cwd=ROOT,
    )
    images = [Image.open(path).convert("RGB") for path in sorted(render_dir.glob("page-*.png"))]
    if not images:
        raise RuntimeError("Contact sheet rendering produced no images")
    thumb_w = 520
    thumb_h = round(images[0].height * thumb_w / images[0].width)
    cols = 3
    rows = math.ceil(len(images) / cols)
    gutter = 24
    label_h = 30
    canvas = Image.new("RGB", (cols * thumb_w + (cols + 1) * gutter, rows * (thumb_h + label_h) + (rows + 1) * gutter), "#e5e7e9")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(str(ROOT / "design/fonts/Onest.ttf"), 20)
    except OSError:
        font = ImageFont.load_default()
    for index, image in enumerate(images):
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = index % cols
        row = index // cols
        x = gutter + col * (thumb_w + gutter)
        y = gutter + row * (thumb_h + label_h + gutter)
        canvas.paste(image, (x, y + label_h))
        draw.text((x, y + 2), f"{index + 1}", fill="#223b5e", font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    for image in images:
        image.close()


def run_validator(output_dir: Path, minimum_dpi: float, pdf: Path | None = None) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/validate_v21_pilot.py"),
        "--output-dir",
        str(output_dir),
        "--minimum-dpi",
        str(minimum_dpi),
        "--strict",
    ]
    if pdf:
        command.extend(["--pdf", str(pdf)])
    subprocess.run(command, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--render", action="store_true", help="Render and merge the 31-page pilot PDF after strict data validation.")
    parser.add_argument("--minimum-dpi", type=float, default=180.0, help="Absolute blocking floor; assets below 250 ppi remain queued for improvement.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    families = load_families()
    if len(families) != 74:
        raise RuntimeError(f"Expected 74 canonical families, found {len(families)}")
    registry = registries()
    materialize_pilot_maps(families, registry, output_dir)
    page_plan = build_page_plan(families)
    toc = build_toc(page_plan, families)
    write_json(output_dir / "page-plan.json", page_plan)
    write_json(output_dir / "generated-toc.json", toc)

    toc_html = output_dir / "generated-toc.html"
    frontmatter_html = output_dir / "generated-frontmatter.html"
    family_html = output_dir / "pilot-families.html"
    render_toc_html(toc_html, toc, registry)
    render_frontmatter_html(frontmatter_html, toc, registry)
    family_placement_items, public_notes = render_family_html(family_html, page_plan, families, registry)
    ledger = placement_ledger(page_plan, family_placement_items, public_notes)
    write_json(output_dir / "placement-ledger.json", ledger)

    run_validator(output_dir, args.minimum_dpi)
    if not args.render:
        print(f"PASS 1: {output_dir / 'page-plan.json'}")
        print(f"PASS 2: {output_dir / 'generated-toc.json'}")
        print(f"HTML: {family_html}")
        print("Render skipped; pass --render after reviewing the plan.")
        return 0

    frontmatter_spreads = temp_dir / "frontmatter-pages-raw.pdf"
    frontmatter_pdf = temp_dir / "frontmatter-pages-01-19.pdf"
    family_raw = temp_dir / "families-raw.pdf"
    family_pdf = temp_dir / "families-boxed.pdf"
    final_pdf = output_dir / "PRINT_V21_GENERATOR_PILOT.pdf"
    playwright_render(frontmatter_html, frontmatter_spreads)
    normalize_boxes(frontmatter_spreads, frontmatter_pdf)
    playwright_render(family_html, family_raw)
    normalize_boxes(family_raw, family_pdf)
    merge_pilot(frontmatter_pdf, family_pdf, output_pdf=final_pdf)
    run_validator(output_dir, args.minimum_dpi, final_pdf)
    make_contact_sheet(final_pdf, output_dir / "contact-sheet.png", temp_dir)
    print(f"PDF: {final_pdf}")
    print(f"CONTACT: {output_dir / 'contact-sheet.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
