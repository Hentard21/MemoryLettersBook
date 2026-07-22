#!/usr/bin/env python3
"""Build the complete data-driven draft of *Letters of Memory*.

Primary command:

    python scripts/build_book.py --families all --profile draft

The command writes one cached HTML/PDF unit per family, checkpoints every ten
families, keeps failures isolated, then performs strict structural preflight
before assembling the client spreads and production-page proof.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from book_pipeline import (
    BACK_MATTER_PDF,
    CHECKPOINT_DIR,
    FAMILY_CACHE,
    FRONTMATTER_PAGES,
    INTRO_PDF,
    OUTPUT,
    ROOT,
    append_pdfs,
    build_page_plan_data,
    build_placement_ledger,
    build_toc_data,
    crop_spread_pdf_to_pages,
    family_cache_key,
    make_contact_sheet_pdf,
    make_review_batches,
    materialize_all_maps,
    merge_page_pdfs,
    normalize_family_pdf,
    pages_to_spreads,
    patch_back_matter,
    patch_intro_toc,
    playwright_render,
    read_checkpoint,
    read_json,
    render_family_source,
    select_families,
    v21,
    write_checkpoint,
    write_json,
    write_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", default="all", help="Use 'all' or a comma-separated list of hero IDs.")
    parser.add_argument("--start-family", help="Canonical order number or hero ID.")
    parser.add_argument("--count", type=int)
    parser.add_argument("--profile", choices=("draft", "production-proof"), default="draft")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--skip-render", action="store_true", help="Build data/HTML/preflight only.")
    return parser.parse_args()


def run_dom_check(family_dir: Path, output_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["node", str(ROOT / "scripts/check_book_dom.mjs"), "--input", str(family_dir)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)
    write_json(output_path, payload)
    return payload


def run_preflight(
    output_dir: Path, profile: str, dom_report: Path, pdf: Path | None = None,
    strict: bool = True,
) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/preflight_book.py"),
        "--output-dir",
        str(output_dir),
        "--profile",
        profile,
        "--dom-report",
        str(dom_report),
    ]
    if pdf:
        command.extend(["--pdf", str(pdf)])
    if strict:
        command.append("--strict")
    subprocess.run(command, cwd=ROOT, check=True)


def chosen_families(all_families: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = select_families(all_families, args.start_family, args.count)
    if args.families != "all":
        requested = {token.strip() for token in args.families.split(",") if token.strip()}
        selected = [family for family in selected if family["hero_id"] in requested]
        unknown = requested - {family["hero_id"] for family in all_families}
        if unknown:
            raise ValueError(f"Unknown family IDs: {sorted(unknown)}")
    return selected


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    family_cache = output_dir / "families"
    checkpoint_dir = output_dir / "checkpoints"
    temp_dir = output_dir / "tmp"
    for directory in (family_cache, checkpoint_dir, temp_dir):
        directory.mkdir(parents=True, exist_ok=True)

    families = v21.load_families()
    if len(families) != 74:
        raise RuntimeError(f"Expected 74 canonical families, found {len(families)}")
    selected = chosen_families(families, args)
    if not selected:
        raise RuntimeError("Family selection is empty")
    if args.families == "all" and len(selected) != 74:
        print(f"Partial canonical build: {len(selected)} families", file=sys.stderr)

    registry = v21.registries()
    materialize_all_maps(families, registry, output_dir)

    # Pass 1 / Pass 2: TOC injection is content-only and must not alter the
    # stable page signature. We still execute the second pagination pass and
    # compare it explicitly.
    page_plan = build_page_plan_data(families)
    signature_1 = [
        (item["hero_id"], item["start_page"], item["end_page"])
        for item in page_plan["families"]
    ]
    toc = build_toc_data(page_plan, families)
    page_plan_2 = build_page_plan_data(families)
    signature_2 = [
        (item["hero_id"], item["start_page"], item["end_page"])
        for item in page_plan_2["families"]
    ]
    if signature_1 != signature_2:
        raise RuntimeError("Pagination changed after TOC generation")
    write_json(output_dir / "page-plan.json", page_plan)
    write_json(output_dir / "generated-toc.json", toc)
    generated_intro_html = output_dir / "generated-frontmatter.html"
    patch_intro_toc(toc, generated_intro_html, registry)

    plan_by_id = {item["hero_id"]: item for item in page_plan["families"]}
    checkpoint = read_checkpoint() if args.resume else {"completed": [], "failed": {}, "cache_keys": {}}
    completed_ids: list[str] = []
    failed: dict[str, str] = {}
    cache_keys: dict[str, str] = {}
    family_ledgers: list[dict[str, Any]] = []
    public_notes: list[str] = []

    for index, family in enumerate(selected, start=1):
        hero_id = family["hero_id"]
        family_dir = family_cache / hero_id
        family_dir.mkdir(parents=True, exist_ok=True)
        html_path = family_dir / "index.html"
        raw_pdf = family_dir / "raw.pdf"
        boxed_pdf = family_dir / "pages.pdf"
        ledger_path = family_dir / "placement.json"
        notes_path = family_dir / "notes.json"
        meta_path = family_dir / "cache.json"
        plan = plan_by_id[hero_id]
        key = family_cache_key(family, plan)
        cache_keys[hero_id] = key
        cached = False
        if not args.force and html_path.is_file() and boxed_pdf.is_file() and ledger_path.is_file() and meta_path.is_file():
            try:
                cached = read_json(meta_path).get("cache_key") == key
            except (OSError, ValueError):
                cached = False
        if args.resume and hero_id in checkpoint.get("completed", []) and checkpoint.get("cache_keys", {}).get(hero_id) == key:
            cached = cached or boxed_pdf.is_file()
        try:
            if not cached:
                ledger, notes = render_family_source(family, plan, registry, html_path)
                write_json(ledger_path, ledger)
                write_json(notes_path, notes)
                if not args.skip_render:
                    playwright_render(html_path, raw_pdf)
                    normalize_family_pdf(raw_pdf, boxed_pdf)
                write_json(meta_path, {"cache_key": key, "page_count": plan["page_count"]})
            ledger = read_json(ledger_path)
            notes = read_json(notes_path) if notes_path.is_file() else []
            family_ledgers.extend(ledger)
            public_notes.extend(notes)
            completed_ids.append(hero_id)
        except Exception as exc:  # keep later families moving
            failed[hero_id] = f"{type(exc).__name__}: {exc}"
            print(f"FAILED {hero_id}: {failed[hero_id]}", file=sys.stderr)
        if index % 10 == 0 or index == len(selected):
            write_checkpoint(completed_ids, failed, cache_keys)
            print(f"checkpoint {index}/{len(selected)} completed={len(completed_ids)} failed={len(failed)}")

    full_build = len(selected) == 74 and args.families == "all" and not args.start_family and args.count is None
    if full_build:
        ledger = build_placement_ledger(page_plan, family_ledgers, families, public_notes)
    else:
        # Partial commands are for rapid layout review. They do not claim full
        # placement completeness, but keep the same page numbering.
        selected_ids = {item["hero_id"] for item in selected}
        ledger = build_placement_ledger(
            page_plan,
            family_ledgers,
            [item for item in families if item["hero_id"] in selected_ids],
            public_notes,
        )
        ledger["scope"] = f"partial build: {len(selected)} families"
    write_json(output_dir / "placement-ledger.json", ledger)
    write_json(
        output_dir / "build-summary.json",
        {
            "profile": args.profile,
            "selected": [item["hero_id"] for item in selected],
            "completed": completed_ids,
            "failed": failed,
            "full_build": full_build,
        },
    )

    dom_report = output_dir / "family-dom-report.json"
    run_dom_check(family_cache, dom_report)
    # A family failure is represented by unplaced/missing entries and must
    # block the full export; draft-quality source warnings do not.
    run_preflight(output_dir, args.profile, dom_report, strict=full_build)

    if args.skip_render:
        print("Render skipped after data/HTML preflight.")
        return 0
    if failed:
        raise RuntimeError(f"Family rendering failures prevent final assembly: {failed}")
    if not full_build:
        print("Partial family PDFs rendered; full-book assembly intentionally skipped.")
        return 0

    intro_spreads = temp_dir / "intro-spreads.pdf"
    intro_pages = temp_dir / "intro-pages.pdf"
    playwright_render(generated_intro_html, intro_spreads)
    crop_spread_pdf_to_pages(
        intro_spreads,
        intro_pages,
        skip_first_left=True,
        page_limit=FRONTMATTER_PAGES,
    )

    generated_back_html = output_dir / "generated-back-matter.html"
    back_spread = temp_dir / "back-matter-spread.pdf"
    patch_back_matter(generated_back_html)
    playwright_render(generated_back_html, back_spread)
    back_pages = temp_dir / "back-matter-pages.pdf"
    crop_spread_pdf_to_pages(back_spread, back_pages, page_limit=2)
    family_pages = temp_dir / "family-pages.pdf"
    family_sources = [family_cache / item["hero_id"] / "pages.pdf" for item in page_plan["families"]]
    merge_page_pdfs(family_sources, family_pages)

    production_proof = output_dir / "PRINT_V21_INTERIOR_PAGES_PROOF.pdf"
    merge_page_pdfs((intro_pages, family_pages, back_pages), production_proof)

    family_spreads = temp_dir / "family-spreads.pdf"
    pages_to_spreads(family_pages, family_spreads)
    client_spreads = output_dir / "PRINT_V21_FULL_DRAFT_SPREADS.pdf"
    append_pdfs((intro_spreads, family_spreads, back_spread), client_spreads)

    run_preflight(
        output_dir,
        args.profile,
        dom_report,
        pdf=production_proof,
        strict=True,
    )
    make_contact_sheet_pdf(
        client_spreads,
        output_dir / "full-contact-sheet.pdf",
        temp_dir,
    )
    batches = make_review_batches(
        family_spreads,
        page_plan,
        output_dir / "review-batches",
    )
    print(f"SPREADS: {client_spreads}")
    print(f"PROOF: {production_proof}")
    print(f"CONTACT: {output_dir / 'full-contact-sheet.pdf'}")
    print(f"BATCHES: {len(batches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
