#!/usr/bin/env python3
"""Structural, content, DOM and print-geometry preflight for the full book."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from audit_pdf_preflight import collect_colour_and_transparency, collect_fonts
from book_pipeline import (
    BLEED_MM,
    FORBIDDEN_PUBLIC_MARKERS,
    MEDIA_MM,
    OUTPUT,
    ROOT,
    TRIM_MM,
    read_json,
    repo_path,
    v21,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--profile", choices=("draft", "production-proof"), default="draft")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--dom-report", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


class Audit:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.review: list[dict[str, Any]] = []
        self.dpi_warning: list[dict[str, Any]] = []
        self.dpi_blocking: list[dict[str, Any]] = []
        self.pdf: dict[str, Any] = {}

    def queue_review(
        self,
        message: str,
        hero_id: str = "",
        category: str = "review",
        severity: str = "warning",
        item: dict[str, Any] | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "hero_id": hero_id,
            "category": category,
            "severity": severity,
            "message": message,
            "source_id": "",
            "source_file": "",
            "output_pages": "",
            "effective_dpi": "",
            "width_mm": "",
            "height_mm": "",
        }
        if item:
            placement = item.get("placement") or {}
            row.update(
                {
                    "source_id": str(item.get("source_id") or ""),
                    "source_file": str(item.get("source_file") or ""),
                    "output_pages": ",".join(str(value) for value in item.get("output_pages", [])),
                    "effective_dpi": item.get("effective_dpi", ""),
                    "width_mm": placement.get("width_mm", ""),
                    "height_mm": placement.get("height_mm", ""),
                }
            )
        self.review.append(row)

    def error(self, message: str, hero_id: str = "", category: str = "error", *, queue: bool = True) -> None:
        self.errors.append(message)
        if queue:
            self.queue_review(message, hero_id, category, "blocking")

    def warn(self, message: str, hero_id: str = "", category: str = "warning", *, queue: bool = True) -> None:
        self.warnings.append(message)
        if queue:
            self.queue_review(message, hero_id, category, "warning")


def registry_relations(families: list[dict[str, Any]], audit: Audit) -> None:
    registry = v21.registries()
    for family in families:
        hero = family["hero_id"]
        flags = set(str(value) for value in family.get("review_flags", []))
        region_id = str(family.get("region_id") or "")
        city_id = str(family.get("city_id") or "")
        emblem_id = str(family.get("emblem_id") or "")
        award_id = family.get("award_id")
        region = registry["regions"].get(region_id)
        city = registry["cities"].get(city_id)
        emblem = registry["emblems"].get(emblem_id)
        if not region:
            audit.error(f"{hero}: unknown region_id {region_id!r}", hero, "region")
        if not city:
            message = f"{hero}: city_id is missing or unregistered ({city_id!r})"
            (audit.warn if any("CITY" in flag for flag in flags) else audit.error)(message, hero, "city")
        elif city.get("region_id") and city.get("region_id") != region_id:
            audit.error(f"{hero}: city {city_id} belongs to {city.get('region_id')}, not {region_id}", hero, "city-region")
        elif city.get("region_ids") and region_id not in city.get("region_ids", []):
            audit.error(f"{hero}: city {city_id} does not list region {region_id}", hero, "city-region")
        if not emblem:
            audit.error(f"{hero}: unknown emblem_id {emblem_id!r}", hero, "emblem")
        elif emblem.get("region_id") != region_id:
            audit.error(f"{hero}: emblem {emblem_id} belongs to {emblem.get('region_id')}, not {region_id}", hero, "emblem-region")
        elif not emblem.get("asset_file"):
            message = f"{hero}: verified emblem image is not registered"
            (audit.warn if any("EMBLEM" in flag for flag in flags) else audit.error)(message, hero, "emblem")
        if award_id is None:
            award_provenance = str((family.get("canonical_reference") or {}).get("award_provenance") or "")
            if "no award shown" not in award_provenance.casefold():
                message = f"{hero}: award remains unverified in the canonical reference mapping"
                (audit.warn if any("AWARD" in flag for flag in flags) else audit.error)(message, hero, "award")
        elif str(award_id) not in registry["awards"]:
            audit.error(f"{hero}: unknown award_id {award_id!r}", hero, "award")


def validate_plan(plan: dict[str, Any], toc: dict[str, Any], families: list[dict[str, Any]], audit: Audit) -> None:
    geometry = plan.get("geometry", {})
    if geometry.get("trim_mm") != list(TRIM_MM) or geometry.get("media_box_mm") != list(MEDIA_MM) or geometry.get("bleed_mm") != BLEED_MM:
        audit.error("Page plan lost the 260×200 trim / 266×206 media / 3 mm bleed lock", category="geometry")
    pagination = plan.get("pagination", {})
    if pagination.get("frontmatter_pages") != 13 or pagination.get("first_family_page") != 14:
        audit.error("Compact intro parity lock must remain pages 1–13 with first family on page 14", category="pagination")
    if pagination.get("toc_pages") != [12, 13]:
        audit.error("TOC must remain a two-page spread on pages 12–13", category="pagination")
    if not pagination.get("stable"):
        audit.error("Pagination did not stabilize", category="pagination")
    canonical_ids = [item["hero_id"] for item in families]
    planned = plan.get("families", [])
    if len(planned) != 74 or [item.get("hero_id") for item in planned] != canonical_ids:
        audit.error("Family order/count differs from the 74-family canonical order", category="family-order")
    for item in planned:
        start = int(item.get("start_page", 0))
        end = int(item.get("end_page", 0))
        if start % 2 or item.get("start_side") != "left":
            audit.error(f"{item.get('hero_id')}: starts on page {start}, not an even/left page", str(item.get("hero_id")), "parity")
        if end - start + 1 != int(item.get("page_count", 0)):
            audit.error(f"{item.get('hero_id')}: page span/count mismatch", str(item.get("hero_id")), "pagination")
    toc_items = toc.get("families", [])
    if len(toc_items) != 74:
        audit.error("Dynamic TOC does not contain all 74 families", category="toc")
    else:
        for planned_item, toc_item in zip(planned, toc_items, strict=True):
            if planned_item.get("hero_id") != toc_item.get("hero_id") or planned_item.get("start_page") != toc_item.get("start_page"):
                audit.error(f"TOC mismatch at {planned_item.get('hero_id')}", str(planned_item.get("hero_id")), "toc")
                break


def validate_ledger(ledger: dict[str, Any], families: list[dict[str, Any]], audit: Audit) -> None:
    items = list(ledger.get("items", []))
    by_hero: dict[str, list[dict[str, Any]]] = defaultdict(list)
    used_by_file: dict[str, set[str]] = defaultdict(set)
    for item in items:
        hero = str(item.get("hero_id") or "")
        if hero:
            by_hero[hero].append(item)
        source = str(item.get("source_file") or "")
        if source:
            path = ROOT / source
            if not path.is_file():
                audit.error(f"Ledger source is missing: {source}", hero, "broken-path")
            if hero and item.get("source_type") in {"flagship", "photo", "drawing", "letter", "transcription"}:
                used_by_file[repo_path(source).casefold()].add(hero)
        status = item.get("status")
        if status == "missing":
            audit.error(f"{hero or 'book'}: source {item.get('source_id')} is missing without a review waiver", hero, "missing-material")
        elif status == "review_required":
            audit.warn(f"{hero or 'book'}: {item.get('source_id')} requires review — {item.get('notes', '')}", hero, "review-required")
        dpi = item.get("effective_dpi")
        placement = item.get("placement") or {}
        large = max(float(placement.get("width_mm") or 0), float(placement.get("height_mm") or 0)) >= 80
        if isinstance(dpi, (int, float)) and dpi < 250:
            audit.dpi_warning.append(item)
            critical = dpi < 180 and large
            dpi_message = (
                f"{hero or 'book'}: {item.get('source_id')} is {dpi} ppi at "
                f"{placement.get('width_mm', 0)}x{placement.get('height_mm', 0)} mm"
            )
            audit.queue_review(
                dpi_message,
                hero,
                "dpi",
                "critical" if critical else "warning",
                item,
            )
            if critical:
                audit.dpi_blocking.append(item)
                message = f"{hero or 'book'}: {item.get('source_id')} is {dpi} ppi at a large placement"
                if audit.profile == "production-proof" and item.get("source_quality_policy") != "OWNER_ACCEPTED_SOURCE_LIMIT":
                    audit.error(message, hero, "dpi", queue=False)
                else:
                    audit.warn(message + "; accepted only for the documentary draft", hero, "dpi", queue=False)
    for source, heroes in used_by_file.items():
        if len(heroes) > 1:
            audit.error(f"Asset is assigned to multiple families: {source} → {sorted(heroes)}", category="duplicate-cross-family")

    for family in families:
        hero = family["hero_id"]
        family_items = by_hero.get(hero, [])
        placed = {
            (str(item.get("source_type")), repo_path(str(item.get("source_file") or "")).casefold())
            for item in family_items
            if item.get("status") == "placed"
        }
        explicit = {
            (str(item.get("source_type")), repo_path(str(item.get("source_file") or "")).casefold())
            for item in family_items
            if item.get("status") in {"placed", "review_required", "missing"}
        }
        expected = []
        if family.get("flagship"):
            expected.append(("flagship", repo_path(family["flagship"]).casefold()))
        for key, source_type in (("archive_photos", "photo"), ("drawings", "drawing"), ("letters", "letter"), ("transcriptions", "transcription")):
            expected.extend((source_type, repo_path(value).casefold()) for value in family.get(key, []))
        for token in expected:
            if token not in explicit:
                audit.error(f"{hero}: canonical source disappeared from the placement ledger: {token[1]}", hero, "ledger-completeness")
        if family.get("letters") and not any(item.get("source_type") == "letter" and item.get("status") == "placed" for item in family_items):
            audit.error(f"{hero}: no physical manuscript is placed", hero, "letter")
        if family.get("transcriptions") and not any(item.get("source_type") == "transcription" and item.get("status") == "placed" for item in family_items):
            audit.error(f"{hero}: no reader transcription is placed", hero, "transcription")


def validate_dom(dom_path: Path | None, audit: Audit) -> None:
    if not dom_path or not dom_path.is_file():
        audit.warn("DOM report is not available yet", category="dom")
        return
    payload = read_json(dom_path)
    for result in payload.get("results", []):
        hero = Path(str(result.get("input", ""))).parent.name
        for key, category in (("overflow", "overflow"), ("brokenImages", "broken-image"), ("forbiddenVisible", "technical-marker"), ("tooSmallText", "minimum-type"), ("unsafeFold", "fold-safe-zone"), ("invalidParity", "parity"), ("extendedContinuityIssues", "extended-family-continuity")):
            issues = result.get(key, [])
            for issue in issues:
                audit.error(f"{hero}: DOM {category}: {issue}", hero, category)


def validate_pdf(pdf_path: Path | None, expected_pages: int, audit: Audit) -> None:
    if not pdf_path or not pdf_path.is_file():
        audit.warn("Rendered production proof is not available yet", category="pdf")
        return
    reader = PdfReader(pdf_path)
    if len(reader.pages) != expected_pages:
        audit.error(f"Production proof has {len(reader.pages)} pages; expected {expected_pages}", category="pdf-page-count")
    box_errors = []
    expected_w = MEDIA_MM[0] * 72 / 25.4
    expected_h = MEDIA_MM[1] * 72 / 25.4
    trim = BLEED_MM * 72 / 25.4
    for number, page in enumerate(reader.pages, start=1):
        if abs(float(page.mediabox.width) - expected_w) > .5 or abs(float(page.mediabox.height) - expected_h) > .5:
            box_errors.append(f"p{number}: MediaBox")
        if abs(float(page.trimbox.left) - trim) > .5 or abs(float(page.trimbox.bottom) - trim) > .5:
            box_errors.append(f"p{number}: TrimBox origin")
    if box_errors:
        audit.error("Incorrect production page boxes: " + ", ".join(box_errors[:20]), category="pdf-boxes")
    fonts = collect_fonts(reader)
    unembedded = [item for item in fonts if item.get("program_status") == "font_program_not_found"]
    type3 = [item for item in fonts if item.get("subtype") == "Type3"]
    if unembedded:
        audit.error(f"PDF contains {len(unembedded)} font resources without embedded programs", category="fonts")
    if type3:
        audit.error(f"PDF contains {len(type3)} Type 3 font resources", category="fonts")
    colour = collect_colour_and_transparency(reader)
    audit.pdf = {
        "page_count": len(reader.pages),
        "pdf_version": reader.pdf_header,
        "fonts": fonts,
        "type3_count": len(type3),
        "unembedded_count": len(unembedded),
        "colour_and_transparency": colour,
        "pdf_x4": "not_exported_pending_printer_requirements",
    }


def write_report(output_dir: Path, plan: dict[str, Any], ledger: dict[str, Any], audit: Audit) -> None:
    templates = Counter(item.get("template") for item in plan.get("families", []))
    continuations = sum(int(item.get("continuation_spreads", 0)) for item in plan.get("families", []))
    lines = [
        "# Full-book preflight report",
        "",
        f"Profile: `{audit.profile}`",
        f"Result: **{'FAIL' if audit.errors else 'PASS WITH REVIEW QUEUE' if audit.warnings else 'PASS'}**",
        "",
        "## Pagination",
        "",
        f"- Interior pages: {plan.get('pagination', {}).get('total_interior_pages')}",
        f"- Front matter: {plan.get('pagination', {}).get('frontmatter_pages')} pages",
        f"- TOC: {len(plan.get('pagination', {}).get('toc_pages', []))} pages",
        f"- Standard families: {templates.get('standard', 0)}",
        f"- Extended families: {templates.get('extended', 0)}",
        f"- Continuation spreads: {continuations}",
        "",
        "## Placement completeness",
        "",
        f"- Total ledger records: {ledger.get('counts', {}).get('total', 0)}",
        f"- Placed: {ledger.get('counts', {}).get('placed', 0)}",
        f"- Review required: {ledger.get('counts', {}).get('review_required', 0)}",
        f"- Missing/blocking: {ledger.get('counts', {}).get('missing', 0)}",
        "",
        "## Effective DPI",
        "",
        f"- Below 250 ppi: {len(audit.dpi_warning)}",
        f"- Below 180 ppi at a large placement: {len(audit.dpi_blocking)}",
        "- Documentary source limitations are warnings in `draft`; they remain blocking in `production-proof` unless individually owner-waived.",
        "",
        "## PDF technical status",
        "",
        f"- Pages audited: {audit.pdf.get('page_count', 'not rendered')}",
        f"- Type 3 fonts: {audit.pdf.get('type3_count', 'not audited')}",
        f"- Unembedded fonts: {audit.pdf.get('unembedded_count', 'not audited')}",
        "- PDF/X-4: deliberately not exported until printer requirements are received.",
        "",
        f"## Blocking errors ({len(audit.errors)})",
        "",
    ]
    if audit.errors:
        lines.extend(f"- {message}" for message in audit.errors)
    else:
        lines.append("- None.")
    lines.extend(["", f"## Warnings and review items ({len(audit.warnings)})", ""])
    if audit.warnings:
        lines.extend(f"- {message}" for message in audit.warnings)
    else:
        lines.append("- None.")
    lines.extend(["", "## Manual transcription queue", "", "All prepared reader transcriptions remain provisional and require line-by-line comparison with the physical manuscript before final production.", ""])
    (output_dir / "preflight-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "pilot-preflight-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (output_dir / "review-queue.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "hero_id",
                "category",
                "severity",
                "message",
                "source_id",
                "source_file",
                "output_pages",
                "effective_dpi",
                "width_mm",
                "height_mm",
            ),
        )
        writer.writeheader()
        writer.writerows(audit.review)
    write_json(output_dir / "pdf-technical-audit.json", audit.pdf)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    plan = read_json(output_dir / "page-plan.json")
    toc = read_json(output_dir / "generated-toc.json")
    ledger = read_json(output_dir / "placement-ledger.json")
    families = v21.load_families()
    audit = Audit(args.profile)
    validate_plan(plan, toc, families, audit)
    registry_relations(families, audit)
    validate_ledger(ledger, families, audit)
    validate_dom(args.dom_report.resolve() if args.dom_report else None, audit)
    validate_pdf(args.pdf.resolve() if args.pdf else None, int(plan["pagination"]["total_interior_pages"]), audit)
    write_report(output_dir, plan, ledger, audit)
    print(f"errors={len(audit.errors)} warnings={len(audit.warnings)}")
    if args.strict and audit.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
