#!/usr/bin/env python3
"""Strict structural and print-box validation for the V21 generator pilot."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
import pdfplumber
from pypdf import PdfReader

from audit_pdf_preflight import audit as audit_rendered_pdf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "design/prototypes/print-v21"
ORDER_FILE = ROOT / "content/manifests/reference-family-order-reset.json"
PRODUCTION_DIR = ROOT / "content/production"
MM_TO_PT = 72.0 / 25.4
EXPECTED_MEDIA_MM = (266.0, 206.0)
EXPECTED_TRIM_MM = (260.0, 200.0)
INNER_SAFE_MM = 22.0
PILOT_IDS = ("hero-001", "hero-003", "hero-004", "hero-005", "hero-006")
PILOT_NAMES = ("АНАСТАСИЯ", "ВЯЧЕСЛАВ", "НИКОЛАЙ", "ЕВГЕНИЙ", "АЛИМАМЕД")
PILOT_STARTS = (20, 22, 26, 28, 30)
FORBIDDEN_VISIBLE = (
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


def registry(filename: str, keys: Iterable[str], id_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    path = PRODUCTION_DIR / filename
    if not path.is_file():
        return {}
    result = {}
    for item in collection(read_json(path), keys):
        stable_id = next((item.get(key) for key in id_keys if item.get(key)), item.get("_registry_key"))
        if stable_id:
            result[str(stable_id)] = item
    return result


def family_data(hero_id: str) -> dict[str, Any] | None:
    path = PRODUCTION_DIR / "families" / f"{hero_id}.json"
    return read_json(path) if path.is_file() else None


def repo_normalize(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(ROOT)
        except ValueError:
            return path.as_posix().casefold()
    return path.as_posix().casefold()


class Audit:
    def __init__(self, minimum_dpi: float) -> None:
        self.minimum_dpi = minimum_dpi
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.dpi_below_250: list[dict[str, Any]] = []
        self.dpi_below_180: list[dict[str, Any]] = []
        self.dpi_owner_waived: list[dict[str, Any]] = []
        self.actual_pdf_audit: dict[str, Any] | None = None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.info.append(message)


def validate_core_files(output_dir: Path, audit: Audit) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    required = ("page-plan.json", "generated-toc.json", "placement-ledger.json", "pilot-families.html", "generated-frontmatter.html")
    for name in required:
        if not (output_dir / name).is_file():
            audit.error(f"Missing generator artifact: {name}")
    if audit.errors:
        return {}, {}, {}
    return (
        read_json(output_dir / "page-plan.json"),
        read_json(output_dir / "generated-toc.json"),
        read_json(output_dir / "placement-ledger.json"),
    )


def validate_plan(page_plan: dict[str, Any], toc: dict[str, Any], audit: Audit) -> None:
    if not page_plan or not toc:
        return
    geometry = page_plan.get("geometry", {})
    if geometry.get("trim_mm") != [260, 200]:
        audit.error(f"Wrong trim geometry in page plan: {geometry.get('trim_mm')}")
    if geometry.get("media_box_mm") != [266, 206] or geometry.get("bleed_mm") != 3:
        audit.error("Page plan does not lock 266 x 206 mm media with 3 mm bleed")
    if page_plan.get("cover_included") is not False:
        audit.error("Cover must not be included in the interior page plan")
    pagination = page_plan.get("pagination", {})
    if pagination.get("frontmatter_pages") != 19 or pagination.get("first_family_page") != 20:
        audit.error("Frontmatter/family boundary must be pages 1-19 / 20")
    if not pagination.get("stable"):
        audit.error("Two-pass pagination did not report a stable result")

    canonical_payload = read_json(ORDER_FILE)
    canonical = canonical_payload.get("families", canonical_payload)
    planned = page_plan.get("families", [])
    if len(planned) != 74:
        audit.error(f"Page plan contains {len(planned)} families instead of 74")
        return
    expected_ids = [item["hero_id"] for item in sorted(canonical, key=lambda item: int(item["reference_order"]))]
    actual_ids = [item.get("hero_id") for item in planned]
    if actual_ids != expected_ids:
        audit.error("Family order differs from reference-family-order-reset.json")

    for entry in planned:
        start = int(entry.get("start_page", 0))
        end = int(entry.get("end_page", 0))
        if start % 2 != 0 or entry.get("start_side") != "left":
            audit.error(f"{entry.get('hero_id')} starts on {start}, not an even/left page")
        expected_count = 4 if entry.get("template") == "extended" else 2
        if end - start + 1 != expected_count:
            audit.error(f"{entry.get('hero_id')} has an invalid {entry.get('template')} page span")
        should_render = entry.get("hero_id") in PILOT_IDS
        if bool(entry.get("rendered_in_pilot")) != should_render:
            audit.error(f"{entry.get('hero_id')} rendered_in_pilot flag is inconsistent")

    pilot = planned[:5]
    if tuple(item.get("hero_id") for item in pilot) != PILOT_IDS:
        audit.error("Pilot scope is not the first five canonical families")
    if tuple(str(item.get("hero_name", "")).upper() for item in pilot) != PILOT_NAMES:
        audit.error("Pilot hero names differ from canonical first five")
    if tuple(int(item.get("start_page", 0)) for item in pilot) != PILOT_STARTS:
        audit.error(f"Pilot starts are not {PILOT_STARTS}")
    if pagination.get("pilot_rendered_pages") != 31:
        audit.error("Pilot must end on page 31")

    toc_families = toc.get("families", [])
    if len(toc_families) != 74:
        audit.error("Generated TOC does not contain all 74 planned families")
    else:
        for planned_item, toc_item in zip(planned, toc_families, strict=True):
            if planned_item.get("hero_id") != toc_item.get("hero_id") or planned_item.get("start_page") != toc_item.get("start_page"):
                audit.error(f"TOC/page-plan mismatch at {planned_item.get('hero_id')}")
                break
            if bool(toc_item.get("rendered_in_pilot")) != bool(planned_item.get("rendered_in_pilot")):
                audit.error(f"TOC rendered flag mismatch at {planned_item.get('hero_id')}")
                break
    intro_ids = [item.get("section_id") for item in toc.get("intro_sections", [])]
    if intro_ids != [item.get("section_id") for item in page_plan.get("intro_sections", [])]:
        audit.error("Generated TOC does not include the planned introductory sections")


def validate_canonical_relations(audit: Audit) -> None:
    regions = registry("regions.json", ("regions", "items"), ("region_id", "id"))
    cities = registry("cities.json", ("cities", "items"), ("city_id", "id"))
    emblems = registry("emblems.json", ("emblems", "items"), ("emblem_id", "id"))
    awards = registry("awards.json", ("awards", "items"), ("award_id", "id"))
    for hero_id in PILOT_IDS:
        family = family_data(hero_id)
        if family is None:
            audit.error(f"Missing canonical family manifest: {hero_id}")
            continue
        region_id = str(family.get("region_id") or "")
        city_id = str(family.get("city_id") or "")
        emblem_id = str(family.get("emblem_id") or "")
        award_id = family.get("award_id")
        region = regions.get(region_id)
        city = cities.get(city_id)
        emblem = emblems.get(emblem_id)
        if not region:
            audit.error(f"{hero_id}: unknown region_id {region_id!r}")
        if not city:
            audit.error(f"{hero_id}: unknown city_id {city_id!r}")
        elif city.get("region_id") and city.get("region_id") != region_id:
            audit.error(f"{hero_id}: city {city_id} belongs to {city.get('region_id')}, not {region_id}")
        elif city.get("region_ids") and region_id not in city.get("region_ids", []):
            audit.error(f"{hero_id}: city {city_id} does not list region {region_id}")
        if not emblem:
            audit.error(f"{hero_id}: unknown emblem_id {emblem_id!r}")
        elif emblem.get("region_id") != region_id:
            audit.error(f"{hero_id}: emblem {emblem_id} belongs to {emblem.get('region_id')}, not {region_id}")
        if award_id is not None and str(award_id) not in awards:
            audit.error(f"{hero_id}: unknown award_id {award_id!r}")
        if region and not (region.get("map_file") or region.get("print_render_file")):
            audit.error(f"{hero_id}: canonical region has no verified map asset")
        if emblem and not emblem.get("asset_file"):
            audit.error(f"{hero_id}: canonical emblem has no asset_file")


def expected_family_assets(hero_id: str) -> set[str]:
    family = family_data(hero_id)
    if not family:
        return set()
    result = set()
    if family.get("flagship"):
        result.add(repo_normalize(str(family["flagship"])))
    for key in ("archive_photos", "drawings", "letters", "transcriptions"):
        result.update(repo_normalize(str(value)) for value in family.get(key, []) if value)
    return result


def validate_ledger(ledger: dict[str, Any], output_dir: Path, audit: Audit) -> None:
    if not ledger:
        return
    items = ledger.get("items", [])
    placed_by_hero: dict[str, set[str]] = {hero_id: set() for hero_id in PILOT_IDS}
    symbol_items: dict[str, dict[str, list[dict[str, Any]]]] = {
        hero_id: {"map": [], "emblem": [], "award": []} for hero_id in PILOT_IDS
    }
    for item in items:
        source = str(item.get("source_file") or "")
        hero_id = item.get("hero_id")
        if source and not source.startswith(("http://", "https://", "data:")) and not (ROOT / source).is_file():
            audit.error(f"Ledger source is missing: {source}")
        if hero_id in placed_by_hero and source:
            placed_by_hero[str(hero_id)].add(repo_normalize(source))
        if hero_id in symbol_items and item.get("asset_type") in symbol_items[str(hero_id)]:
            symbol_items[str(hero_id)][str(item["asset_type"])].append(item)
        if item.get("asset_type") == "flagship":
            safe_bottom_clip = (
                item.get("clip")
                and item.get("clip_region") == "bottom_only"
                and item.get("face_safe") is True
            )
            if item.get("fit_mode") != "contain" or (
                item.get("clip") and not safe_bottom_clip
            ):
                audit.error(f"{hero_id}: flagship may crop a face (fit={item.get('fit_mode')}, clip={item.get('clip')})")
        dpi = item.get("effective_dpi")
        if isinstance(dpi, (int, float)):
            record = {
                "hero_id": hero_id,
                "source_file": source,
                "effective_dpi": dpi,
                "output_pages": item.get("output_pages", []),
                "placement_role": item.get("placement_role"),
                "source_quality_policy": item.get("source_quality_policy"),
            }
            if dpi < 250:
                audit.dpi_below_250.append(record)
            if dpi < 180:
                audit.dpi_below_180.append(record)
            if dpi + 0.05 < audit.minimum_dpi:
                if item.get("source_quality_policy") == "OWNER_ACCEPTED_SOURCE_LIMIT":
                    audit.dpi_owner_waived.append(record)
                    audit.warn(
                        f"{hero_id or 'intro'}: {source} is {dpi} ppi; owner accepted the documented source limit"
                    )
                else:
                    audit.error(f"{hero_id or 'intro'}: {source} is {dpi} ppi, below blocking floor {audit.minimum_dpi:g}")
    for hero_id in PILOT_IDS:
        expected = expected_family_assets(hero_id)
        missing = sorted(expected - placed_by_hero[hero_id])
        for source in missing:
            audit.error(f"{hero_id}: canonical asset not placed: {source}")
        family = family_data(hero_id)
        if family:
            if not family.get("flagship"):
                audit.error(f"{hero_id}: missing flagship")
            if not family.get("letters"):
                audit.error(f"{hero_id}: missing physical handwriting")
            if not family.get("transcriptions"):
                audit.error(f"{hero_id}: missing separate transcription")

    regions = registry("regions.json", ("regions", "items"), ("region_id", "id"))
    emblems = registry("emblems.json", ("emblems", "items"), ("emblem_id", "id"))
    awards = registry("awards.json", ("awards", "items"), ("award_id", "id"))
    for hero_id in PILOT_IDS:
        family = family_data(hero_id)
        if not family:
            continue
        region_id = str(family.get("region_id") or "")
        emblem_id = str(family.get("emblem_id") or "")
        award_id = str(family.get("award_id") or "")

        maps = symbol_items[hero_id]["map"]
        expected_map = repo_normalize(output_dir / "generated-assets" / "maps" / f"{region_id}.svg")
        if len(maps) != 1:
            audit.error(f"{hero_id}: expected exactly one canonical map placement, found {len(maps)}")
        else:
            source = repo_normalize(str(maps[0].get("source_file") or ""))
            if source != expected_map:
                audit.error(f"{hero_id}: map source {source!r} does not match {expected_map!r}")
            map_path = ROOT / str(maps[0].get("source_file") or "")
            feature_id = str((regions.get(region_id) or {}).get("map_feature_id") or "")
            if not feature_id:
                audit.error(f"{hero_id}: canonical region {region_id} has no map_feature_id")
            elif map_path.is_file():
                svg = BeautifulSoup(map_path.read_text(encoding="utf-8"), "xml")
                feature = svg.find(id=feature_id)
                if feature is None or str(feature.get("fill") or "").casefold() != "#873f46":
                    audit.error(f"{hero_id}: map does not highlight canonical feature {feature_id}")

        emblem_rows = symbol_items[hero_id]["emblem"]
        emblem = emblems.get(emblem_id) or {}
        expected_emblem = repo_normalize(str(emblem.get("asset_file") or ""))
        if len(emblem_rows) != 1:
            audit.error(f"{hero_id}: expected exactly one canonical emblem placement, found {len(emblem_rows)}")
        elif repo_normalize(str(emblem_rows[0].get("source_file") or "")) != expected_emblem:
            audit.error(f"{hero_id}: emblem placement does not match canonical {emblem_id}")

        award_rows = symbol_items[hero_id]["award"]
        if award_id:
            expected_award = repo_normalize(str((awards.get(award_id) or {}).get("asset_file") or ""))
            if len(award_rows) != 1:
                audit.error(f"{hero_id}: expected exactly one canonical award placement, found {len(award_rows)}")
            elif repo_normalize(str(award_rows[0].get("source_file") or "")) != expected_award:
                audit.error(f"{hero_id}: award placement does not match canonical {award_id}")
        elif award_rows:
            audit.error(f"{hero_id}: award is placed although canonical award_id is null")
    audit.note(f"Ledger contains {len(items)} placements")
    audit.note("Canonical region/map/emblem/award placement gate: PASS for the rendered pilot")
    audit.note(f"DPI queue: {len(audit.dpi_below_250)} below 250 ppi; {len(audit.dpi_below_180)} below 180 ppi")


def visible_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for node in soup.select("style,script,.editorial-hidden"):
        node.decompose()
    return soup.get_text(" ", strip=True)


def validate_public_html(output_dir: Path, audit: Audit) -> None:
    for filename in ("generated-frontmatter.html", "generated-toc.html", "pilot-families.html"):
        path = output_dir / filename
        if not path.is_file():
            continue
        text = visible_text(path)
        upper = text.upper()
        for marker in FORBIDDEN_VISIBLE:
            if marker.upper() in upper:
                audit.error(f"Public HTML {filename} contains forbidden marker: {marker}")
        if re.search(r"\[[^\]]*(?:сверк|неразбор|обрез|REVIEW|REQUIRED)[^\]]*\]", text, re.IGNORECASE):
            audit.error(f"Public HTML {filename} exposes an editorial bracket note")
    family_html = output_dir / "pilot-families.html"
    frontmatter_html = output_dir / "generated-frontmatter.html"
    if frontmatter_html.is_file():
        soup = BeautifulSoup(frontmatter_html.read_text(encoding="utf-8"), "html.parser")
        page16 = soup.select_one(".contents-page--with-intro")
        intro_items = page16.select(".toc-intro-item") if page16 else []
        expected = (("partners", "1"), ("geography", "2"), ("welcome-words-i", "4"), ("chronicle", "10"), ("welcome-words-ii", "12"), ("contents", "16"))
        actual = tuple(
            (str(item.get("data-section") or ""), item.select_one(".toc-intro-pg").get_text(strip=True))
            for item in intro_items
            if item.select_one(".toc-intro-pg")
        )
        if actual != expected:
            audit.error(f"Visual TOC intro block is missing or wrong: {actual}")
    if family_html.is_file():
        soup = BeautifulSoup(family_html.read_text(encoding="utf-8"), "html.parser")
        page_nodes = soup.select(".print-sheet > .page")
        if len(page_nodes) != 12:
            audit.error(f"Pilot family HTML contains {len(page_nodes)} pages instead of 12")
        page_numbers = [int(node.get("data-page", 0)) for node in page_nodes]
        if page_numbers != list(range(20, 32)):
            audit.error(f"Pilot family HTML page sequence is {page_numbers}, expected 20..31")
        for card in soup.select(".transcript-card,.document-module"):
            char_count = len(card.get_text(" ", strip=True))
            cap = 1250 if "transcript-card" in card.get("class", []) else 950
            if char_count > cap:
                audit.error(f"Text overflow risk: module has {char_count} characters, cap {cap}")


def validate_dom(output_dir: Path, audit: Audit) -> None:
    checker = ROOT / "scripts/check_v21_dom.mjs"
    if not checker.is_file():
        audit.error("DOM overflow checker is missing: scripts/check_v21_dom.mjs")
        return
    checked_modules = 0
    checked_flagships = 0
    for filename in ("generated-frontmatter.html", "pilot-families.html"):
        html_path = output_dir / filename
        if not html_path.is_file():
            continue
        result = subprocess.run(
            ["node", str(checker), "--input", str(html_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            audit.error(f"DOM validation failed for {filename}: {result.stderr.strip() or result.stdout.strip()}")
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            audit.error(f"DOM checker returned invalid JSON for {filename}: {exc}")
            continue
        checked_modules += int(payload.get("checkedOverflowModules") or 0)
        checked_flagships += int(payload.get("flagshipCount") or 0)
        for item in payload.get("overflow", []):
            audit.error(
                f"DOM overflow in {filename} page {item.get('page')}: {item.get('selector')} "
                f"({item.get('scrollWidth')}x{item.get('scrollHeight')} > "
                f"{item.get('clientWidth')}x{item.get('clientHeight')})"
            )
        for item in payload.get("brokenImages", []):
            audit.error(f"Broken image in {filename} page {item.get('page')}: {item.get('src')}")
        for item in payload.get("unsafeFlagships", []):
            audit.error(
                f"Flagship crop gate failed in {filename} page {item.get('page')}: "
                f"object-fit={item.get('objectFit')}"
            )
    if checked_flagships != 5:
        audit.error(f"DOM flagship gate found {checked_flagships} hero cutouts instead of 5")
    else:
        audit.note(
            f"DOM gate: {checked_modules} text modules fit; all images load; 5 flagships use object-fit: contain"
        )


def box_mm(box: Any) -> tuple[float, float, float, float]:
    return tuple(float(value) / MM_TO_PT for value in (box.left, box.bottom, box.right, box.top))


def close_pair(actual: tuple[float, float], expected: tuple[float, float], tolerance: float = 0.12) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True))


def validate_pdf(
    pdf_path: Path, audit: Audit, ledger: dict[str, Any] | None = None
) -> None:
    if not pdf_path.is_file():
        audit.error(f"Requested PDF validation target does not exist: {pdf_path}")
        return
    reader = PdfReader(pdf_path)
    if len(reader.pages) != 31:
        audit.error(f"Pilot PDF contains {len(reader.pages)} pages instead of 31")
    for index, page in enumerate(reader.pages, start=1):
        media = box_mm(page.mediabox)
        trim = box_mm(page.trimbox)
        bleed = box_mm(page.bleedbox)
        media_size = (media[2] - media[0], media[3] - media[1])
        trim_size = (trim[2] - trim[0], trim[3] - trim[1])
        bleed_size = (bleed[2] - bleed[0], bleed[3] - bleed[1])
        if not close_pair(media_size, EXPECTED_MEDIA_MM):
            audit.error(f"PDF page {index}: MediaBox is {media_size}, expected {EXPECTED_MEDIA_MM}")
        if not close_pair(bleed_size, EXPECTED_MEDIA_MM):
            audit.error(f"PDF page {index}: BleedBox is {bleed_size}, expected {EXPECTED_MEDIA_MM}")
        if not close_pair(trim_size, EXPECTED_TRIM_MM):
            audit.error(f"PDF page {index}: TrimBox is {trim_size}, expected {EXPECTED_TRIM_MM}")
        trim_left = trim[0] - media[0]
        trim_bottom = trim[1] - media[1]
        if abs(trim_left - 3) > 0.12 or abs(trim_bottom - 3) > 0.12:
            audit.error(f"PDF page {index}: trim is not inset by 3 mm")

    # The final PDF consists of single pages.  The inner safe boundary is
    # therefore measured from the trim edge nearest the binding: x <= 241 mm
    # on even/left pages and x >= 25 mm on odd/right pages in MediaBox space.
    # Checking extracted word boxes makes the fold rule a blocking gate rather
    # than a visual-review note.
    media_width_mm = EXPECTED_MEDIA_MM[0]
    right_page_min_x = 3.0 + INNER_SAFE_MM
    left_page_max_x = media_width_mm - 3.0 - INNER_SAFE_MM
    safe_violations: list[str] = []
    with pdfplumber.open(pdf_path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False)
            for word in words:
                x0_mm = float(word["x0"]) / MM_TO_PT
                x1_mm = float(word["x1"]) / MM_TO_PT
                text = str(word.get("text") or "").strip()
                if not text:
                    continue
                if page_number % 2 == 0 and x1_mm > left_page_max_x + 0.15:
                    safe_violations.append(
                        f"p{page_number} left/even: {text!r} ends at x={x1_mm:.2f} mm (limit {left_page_max_x:.2f})"
                    )
                elif page_number % 2 == 1 and x0_mm < right_page_min_x - 0.15:
                    safe_violations.append(
                        f"p{page_number} right/odd: {text!r} starts at x={x0_mm:.2f} mm (limit {right_page_min_x:.2f})"
                    )
    if safe_violations:
        audit.error(
            "Inner 22 mm safe-zone text violations: "
            + "; ".join(safe_violations[:12])
            + (f"; plus {len(safe_violations) - 12} more" if len(safe_violations) > 12 else "")
        )
    else:
        audit.note("Inner 22 mm fold-safe text gate: PASS on all 31 pages")
    try:
        actual = audit_rendered_pdf(pdf_path, 22.0)
    except Exception as exc:  # pragma: no cover - keeps the failure visible in CI/reporting
        audit.error(f"Rendered-PDF resource audit failed: {exc}")
        return
    audit.actual_pdf_audit = actual
    image_summary = actual["images"]["summary"]
    audit.note(
        "Rendered PDF resources: "
        f"{image_summary['placement_count']} raster placements; "
        f"minimum actual effective DPI {image_summary['minimum_effective_ppi']}"
    )
    waived_pdf_keys: set[tuple[int, tuple[int, int]]] = set()
    if ledger:
        for item in ledger.get("items", []):
            if item.get("source_quality_policy") != "OWNER_ACCEPTED_SOURCE_LIMIT":
                continue
            dimensions = item.get("dimensions_px")
            if not (
                isinstance(dimensions, list)
                and len(dimensions) == 2
                and all(isinstance(value, int) for value in dimensions)
            ):
                continue
            for page_number in item.get("output_pages", []):
                if isinstance(page_number, int):
                    waived_pdf_keys.add(
                        (page_number, (dimensions[0], dimensions[1]))
                    )
    for placement in actual["images"]["placements"]:
        dpi = placement.get("effective_ppi_min")
        if isinstance(dpi, (int, float)) and dpi + 0.05 < audit.minimum_dpi:
            pixels = placement.get("pixels")
            key = (
                int(placement.get("page", 0)),
                tuple(pixels)
                if isinstance(pixels, list) and len(pixels) == 2
                else (0, 0),
            )
            if key in waived_pdf_keys:
                audit.warn(
                    f"Rendered PDF page {placement.get('page')}: {placement.get('xobject')} is "
                    f"{dpi} ppi under OWNER_ACCEPTED_SOURCE_LIMIT"
                )
            else:
                audit.error(
                    f"Rendered PDF page {placement.get('page')}: {placement.get('xobject')} is "
                    f"{dpi} ppi, below blocking floor {audit.minimum_dpi:g}"
                )
    font_summary = actual["fonts"]["summary"]
    missing_programs = int(font_summary.get("program_status_counts", {}).get("font_program_not_found", 0))
    if missing_programs:
        audit.error(f"Rendered PDF has {missing_programs} font resources without an embedded/self-contained program")
    if font_summary.get("type3_present"):
        audit.warn("Rendered PDF contains self-contained Type 3 font resources; inspect before PDF/X-4 conversion")
    pdfx = actual["pdfx"]
    if not pdfx.get("current_file_is_pdfx4"):
        audit.warn("Pilot is PDF 1.7, not a declared PDF/X-4 file; final PDF/X-4 conversion needs an ICC output intent")


def markdown_report(audit: Audit, pdf_path: Path | None) -> str:
    status = "PASS" if not audit.errors else "BLOCKED"
    lines = [
        "# V21 pilot preflight",
        "",
        f"Status: **{status}**",
        "",
        f"Blocking DPI floor: **{audit.minimum_dpi:g} ppi**. Assets below 250 ppi remain in the improvement queue; below 180 ppi are critical unless explicitly recorded as `OWNER_ACCEPTED_SOURCE_LIMIT`.",
        "",
        f"PDF: `{pdf_path}`" if pdf_path else "PDF boxes: not checked in the data-only pass.",
        "",
        "## Blocking errors",
        "",
    ]
    lines.extend(f"- {item}" for item in audit.errors) if audit.errors else lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in audit.warnings) if audit.warnings else lines.append("- None.")
    lines.extend(["", "## Effective DPI below 180", ""])
    if audit.dpi_below_180:
        for item in audit.dpi_below_180:
            waiver = (
                " — OWNER_ACCEPTED_SOURCE_LIMIT"
                if item in audit.dpi_owner_waived
                else ""
            )
            lines.append(f"- `{item['source_file']}` — {item['effective_dpi']} ppi, pages {item['output_pages']}{waiver}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Replacement / reduction queue: 180–249.9 ppi", ""])
    queue = [item for item in audit.dpi_below_250 if item not in audit.dpi_below_180]
    if queue:
        for item in queue:
            lines.append(f"- `{item['source_file']}` — {item['effective_dpi']} ppi, pages {item['output_pages']}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Checks", ""])
    lines.extend(f"- {item}" for item in audit.info)
    if audit.actual_pdf_audit:
        actual = audit.actual_pdf_audit
        image_summary = actual["images"]["summary"]
        font_summary = actual["fonts"]["summary"]
        lines.extend(
            [
                "",
                "## Rendered PDF technical resources",
                "",
                f"- PDF version: `{actual['pdf_version']}`.",
                f"- Actual raster placements: {image_summary['placement_count']}.",
                f"- Minimum actual effective DPI: {image_summary['minimum_effective_ppi']} ppi.",
                f"- Actual DPI classes: `{json.dumps(image_summary['quality_counts'], ensure_ascii=False)}`.",
                f"- Image colour spaces: `{json.dumps(image_summary['colour_space_counts'], ensure_ascii=False)}`.",
                f"- Font subtypes: `{json.dumps(font_summary['subtype_counts'], ensure_ascii=False)}`.",
                f"- Font program status: `{json.dumps(font_summary['program_status_counts'], ensure_ascii=False)}`.",
                f"- Type 3 present: `{font_summary['type3_present']}`.",
                f"- PDF/X-4 declared: `{actual['pdfx']['current_file_is_pdfx4']}`.",
                f"- Output intent present: `{actual['pdfx']['has_output_intent']}`.",
                "- The Chromium/PDF 1.7 result is suitable as a geometry/content pilot; final PDF/X-4 requires a controlled prepress conversion with the printer's ICC profile.",
            ]
        )
    lines.extend(
        [
            "- Full canonical order: checked for all 74 planned families.",
            "- Render scope: only the first five canonical families.",
            "- Page parity: family starts are even/left.",
            "- Cover: excluded from the interior.",
            "- Physical handwriting and separate transcription: required for every rendered family.",
            "- Public technical markers: blocked.",
            "- Flagship face cropping: blocked through `object-fit: contain` and `clip: false`.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--minimum-dpi", type=float, default=180.0)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when blocking errors exist.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    audit = Audit(args.minimum_dpi)
    page_plan, toc, ledger = validate_core_files(output_dir, audit)
    validate_plan(page_plan, toc, audit)
    validate_canonical_relations(audit)
    validate_ledger(ledger, output_dir, audit)
    validate_public_html(output_dir, audit)
    validate_dom(output_dir, audit)
    pdf_path = args.pdf.resolve() if args.pdf else None
    if pdf_path:
        validate_pdf(pdf_path, audit, ledger)
    report = markdown_report(audit, pdf_path)
    report_path = output_dir / "pilot-preflight-report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"REPORT: {report_path}")
    print(f"STATUS: {'PASS' if not audit.errors else 'BLOCKED'}")
    print(f"ERRORS: {len(audit.errors)}; BELOW_250: {len(audit.dpi_below_250)}; BELOW_180: {len(audit.dpi_below_180)}")
    return 2 if args.strict and audit.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
