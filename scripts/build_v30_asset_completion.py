#!/usr/bin/env python3
"""Build V30 by rerendering only families whose title assets changed.

V30 is an asset-completion build, not a redesign.  It keeps V29 front-matter
pagination and the V28 family PDFs for every untouched family.  The explicitly
listed restored/symbolic title pages are rendered from the current production
manifests, then all pages are assembled in the canonical order and checked by
the normal book preflight.

PowerShell:

    python scripts/build_v30_asset_completion.py --force
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

from pypdf import PdfReader

import book_pipeline as pipeline


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "output-v28-map-restored"
OUTPUT_BUILD = ROOT / "output-v30-asset-completion"
PROTOTYPE = ROOT / "design/prototypes/print-v30-asset-completion"
INTRO_BUILDER = ROOT / "scripts/build_intro_complete_v30.py"
INTRO_HTML = PROTOTYPE / "interior-asset-completion-v30.html"
INTRO_PLAN = PROTOTYPE / "intro-page-plan-v30.json"

PRODUCTION_PROOF = OUTPUT_BUILD / "PRINT_V30_ASSET_COMPLETION_INTERIOR_PAGES_PROOF.pdf"
SPREADS_PDF = OUTPUT_BUILD / "PRINT_V30_ASSET_COMPLETION_SPREADS.pdf"
CLIENT_PDF = ROOT / "output/pdf/PRINT_V30_ASSET_COMPLETION_CLIENT.pdf"

# The first group receives owner-restored title images.  The second group has
# no canonical portrait and receives the explicitly labelled symbolic image.
RESTORED_TITLE_FAMILIES = frozenset(
    {
        "hero-005",
        "hero-006",
        "hero-009",
        "hero-022",
        "hero-023",
        "hero-035",
        "hero-039",
        "hero-050",
        "hero-076",
    }
)
SYMBOLIC_TITLE_FAMILIES = frozenset(
    {
        "hero-038",
        "hero-052",
        "hero-055",
        "hero-062",
        "hero-064",
        "hero-072",
        "hero-074",
    }
)
RERENDER_FAMILIES = RESTORED_TITLE_FAMILIES | SYMBOLIC_TITLE_FAMILIES

EXPECTED_FAMILY_COUNT = 74
EXPECTED_FRONTMATTER_PAGES = 13
EXPECTED_INTERIOR_PAGES = 195
EXPECTED_CLIENT_SPREADS = 98


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace the existing V30 build directory and client PDF",
    )
    parser.add_argument(
        "--skip-client-preview",
        action="store_true",
        help="keep the production/spreads build but skip the raster client PDF",
    )
    return parser.parse_args()


def require(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_pages(path: Path) -> int:
    return len(PdfReader(require(path)).pages)


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
    pipeline.write_json(output_path, payload)
    return payload


def run_preflight(dom_report: Path, pdf: Path | None = None) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/preflight_book.py"),
        "--output-dir",
        str(OUTPUT_BUILD),
        "--profile",
        "draft",
        "--dom-report",
        str(dom_report),
        "--strict",
    ]
    if pdf is not None:
        command.extend(["--pdf", str(pdf)])
    subprocess.run(command, cwd=ROOT, check=True)


@contextlib.contextmanager
def v30_intro_context() -> Iterator[None]:
    """Point shared intro helpers at V30 without mutating shared source code."""
    original_html = pipeline.INTRO_HTML
    original_plan = pipeline.INTRO_PLAN
    try:
        pipeline.INTRO_HTML = INTRO_HTML
        pipeline.INTRO_PLAN = INTRO_PLAN
        yield
    finally:
        pipeline.INTRO_HTML = original_html
        pipeline.INTRO_PLAN = original_plan


def plan_signature(plan: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            item.get("hero_id"),
            int(item.get("start_page", 0)),
            int(item.get("end_page", 0)),
            int(item.get("page_count", 0)),
            item.get("template"),
        )
        for item in plan.get("families", [])
    )


def assert_pagination_lock(current: dict[str, Any], source: dict[str, Any]) -> None:
    if plan_signature(current) != plan_signature(source):
        raise RuntimeError(
            "Current manifests change V28/V29 family pagination; V30 asset "
            "completion must not move a page or TOC entry"
        )
    pagination = current.get("pagination", {})
    if (
        int(pagination.get("frontmatter_pages", 0)) != EXPECTED_FRONTMATTER_PAGES
        or int(pagination.get("total_interior_pages", 0)) != EXPECTED_INTERIOR_PAGES
    ):
        raise RuntimeError(f"Unexpected V30 pagination: {pagination}")


def prepare_output(force: bool, *, build_client: bool) -> None:
    if OUTPUT_BUILD.exists() and not force:
        raise FileExistsError(
            f"{OUTPUT_BUILD} already exists; use --force to replace only V30"
        )
    if build_client and CLIENT_PDF.exists() and not force:
        raise FileExistsError(f"{CLIENT_PDF} already exists; use --force")
    if OUTPUT_BUILD.exists():
        shutil.rmtree(OUTPUT_BUILD)
    OUTPUT_BUILD.mkdir(parents=True)
    for relative in ("families", "checkpoints", "tmp"):
        (OUTPUT_BUILD / relative).mkdir(parents=True, exist_ok=True)
    if build_client and CLIENT_PDF.exists():
        CLIENT_PDF.unlink()


def copy_unchanged_family_metadata(hero_id: str, target_dir: Path) -> None:
    source_dir = SOURCE_BUILD / "families" / hero_id
    for name in ("index.html", "placement.json", "notes.json", "cache.json"):
        shutil.copy2(require(source_dir / name), target_dir / name)
    pipeline.write_json(
        target_dir / "reuse.json",
        {
            "status": "reused_without_rerender",
            "source_build": pipeline.repo_path(SOURCE_BUILD),
            "source_pages_pdf": pipeline.repo_path(source_dir / "pages.pdf"),
            "source_pages_sha256": sha256(require(source_dir / "pages.pdf")),
        },
    )


def render_changed_family(
    family: dict[str, Any],
    plan: dict[str, Any],
    registry: dict[str, dict[str, dict[str, Any]]],
    target_dir: Path,
) -> Path:
    html_path = target_dir / "index.html"
    raw_pdf = target_dir / "raw.pdf"
    pages_pdf = target_dir / "pages.pdf"
    ledger, notes = pipeline.render_family_source(family, plan, registry, html_path)
    pipeline.write_json(target_dir / "placement.json", ledger)
    pipeline.write_json(target_dir / "notes.json", notes)
    pipeline.playwright_render(html_path, raw_pdf)
    pipeline.normalize_family_pdf(raw_pdf, pages_pdf)
    actual = pdf_pages(pages_pdf)
    expected = int(plan["page_count"])
    if actual != expected:
        raise RuntimeError(f"{family['hero_id']}: rendered {actual} pages, expected {expected}")
    pipeline.write_json(
        target_dir / "cache.json",
        {
            "cache_key": pipeline.family_cache_key(family, plan),
            "page_count": expected,
            "v30_selective_rerender": True,
        },
    )
    return pages_pdf


def build() -> dict[str, Any]:
    args = parse_args()
    prepare_output(args.force, build_client=not args.skip_client_preview)
    require(SOURCE_BUILD / "page-plan.json")
    subprocess.run([sys.executable, str(INTRO_BUILDER)], cwd=ROOT, check=True)
    require(INTRO_HTML)
    require(INTRO_PLAN)

    families = pipeline.v21.load_families()
    if len(families) != EXPECTED_FAMILY_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_FAMILY_COUNT} canonical families, found {len(families)}"
        )
    family_ids = {item["hero_id"] for item in families}
    missing_changed = RERENDER_FAMILIES - family_ids
    if missing_changed:
        raise RuntimeError(f"Unknown V30 rerender IDs: {sorted(missing_changed)}")

    registry = pipeline.v21.registries()
    pipeline.materialize_all_maps(families, registry, OUTPUT_BUILD)
    source_plan = pipeline.read_json(SOURCE_BUILD / "page-plan.json")
    with v30_intro_context():
        page_plan = pipeline.build_page_plan_data(families)
        assert_pagination_lock(page_plan, source_plan)
        page_plan["schema_version"] = 3
        page_plan["generator"] = "scripts/build_v30_asset_completion.py"
        page_plan["compact_intro"] = pipeline.repo_path(INTRO_HTML)
        page_plan["source_build"] = pipeline.repo_path(SOURCE_BUILD)
        page_plan["pagination_lock"] = "identical_to_v28_v29"
        toc = pipeline.build_toc_data(page_plan, families)
        toc["schema_version"] = 3
        toc["generator"] = "scripts/build_v30_asset_completion.py"
        generated_intro = OUTPUT_BUILD / "generated-frontmatter.html"
        pipeline.patch_intro_toc(toc, generated_intro, registry)

    pipeline.write_json(OUTPUT_BUILD / "page-plan.json", page_plan)
    pipeline.write_json(OUTPUT_BUILD / "generated-toc.json", toc)

    plan_by_id = {item["hero_id"]: item for item in page_plan["families"]}
    family_pdf_sources: list[Path] = []
    family_ledgers: list[dict[str, Any]] = []
    public_notes: list[str] = []
    changed_hashes: dict[str, str] = {}
    reused_hashes: dict[str, str] = {}

    for family in families:
        hero_id = family["hero_id"]
        family_dir = OUTPUT_BUILD / "families" / hero_id
        family_dir.mkdir(parents=True, exist_ok=True)
        if hero_id in RERENDER_FAMILIES:
            pages_pdf = render_changed_family(
                family, plan_by_id[hero_id], registry, family_dir
            )
            changed_hashes[hero_id] = sha256(pages_pdf)
        else:
            copy_unchanged_family_metadata(hero_id, family_dir)
            pages_pdf = require(SOURCE_BUILD / "families" / hero_id / "pages.pdf")
            expected = int(plan_by_id[hero_id]["page_count"])
            if pdf_pages(pages_pdf) != expected:
                raise RuntimeError(f"{hero_id}: reused PDF page count differs from plan")
            reused_hashes[hero_id] = sha256(pages_pdf)
        family_pdf_sources.append(pages_pdf)
        family_ledgers.extend(pipeline.read_json(family_dir / "placement.json"))
        notes_path = family_dir / "notes.json"
        if notes_path.is_file():
            public_notes.extend(pipeline.read_json(notes_path))

    with v30_intro_context():
        ledger = pipeline.build_placement_ledger(
            page_plan, family_ledgers, families, public_notes
        )
    ledger["schema_version"] = 3
    ledger["scope"] = (
        "74 canonical families; V29 locked intro completed with owner photos; "
        f"{len(RERENDER_FAMILIES)} selectively rerendered family title pages"
    )
    ledger["build"] = "V30_ASSET_COMPLETION"
    pipeline.write_json(OUTPUT_BUILD / "placement-ledger.json", ledger)

    build_summary = {
        "profile": "draft",
        "full_build": True,
        "selected": [item["hero_id"] for item in families],
        "completed": [item["hero_id"] for item in families],
        "failed": {},
        "source_build": pipeline.repo_path(SOURCE_BUILD),
        "intro_source": pipeline.repo_path(INTRO_HTML),
        "rerendered": sorted(RERENDER_FAMILIES),
        "restored_title_families": sorted(RESTORED_TITLE_FAMILIES),
        "symbolic_title_families": sorted(SYMBOLIC_TITLE_FAMILIES),
        "reused": sorted(family_ids - RERENDER_FAMILIES),
        "pagination_changed": False,
    }
    pipeline.write_json(OUTPUT_BUILD / "build-summary.json", build_summary)

    dom_report = OUTPUT_BUILD / "family-dom-report.json"
    dom_payload = run_dom_check(OUTPUT_BUILD / "families", dom_report)
    if int(dom_payload.get("checked", 0)) != EXPECTED_FAMILY_COUNT:
        raise RuntimeError(
            f"DOM check covered {dom_payload.get('checked')} families, expected 74"
        )
    run_preflight(dom_report)

    temp_dir = OUTPUT_BUILD / "tmp"
    intro_spreads = temp_dir / "intro-spreads.pdf"
    intro_pages = temp_dir / "intro-pages.pdf"
    pipeline.playwright_render(OUTPUT_BUILD / "generated-frontmatter.html", intro_spreads)
    pipeline.crop_spread_pdf_to_pages(
        intro_spreads,
        intro_pages,
        skip_first_left=True,
        page_limit=EXPECTED_FRONTMATTER_PAGES,
    )
    if pdf_pages(intro_pages) != EXPECTED_FRONTMATTER_PAGES:
        raise RuntimeError("V30 intro did not produce the locked 13 interior pages")

    family_pages = temp_dir / "family-pages.pdf"
    pipeline.merge_page_pdfs(family_pdf_sources, family_pages)
    back_pages = require(SOURCE_BUILD / "tmp/back-matter-pages.pdf")
    back_spread = require(SOURCE_BUILD / "tmp/back-matter-spread.pdf")
    shutil.copy2(
        require(SOURCE_BUILD / "generated-back-matter.html"),
        OUTPUT_BUILD / "generated-back-matter.html",
    )
    pipeline.merge_page_pdfs((intro_pages, family_pages, back_pages), PRODUCTION_PROOF)
    if pdf_pages(PRODUCTION_PROOF) != EXPECTED_INTERIOR_PAGES:
        raise RuntimeError(
            f"Production proof has {pdf_pages(PRODUCTION_PROOF)} pages, "
            f"expected {EXPECTED_INTERIOR_PAGES}"
        )

    family_spreads = temp_dir / "family-spreads.pdf"
    pipeline.pages_to_spreads(family_pages, family_spreads)
    pipeline.append_pdfs((intro_spreads, family_spreads, back_spread), SPREADS_PDF)
    if pdf_pages(SPREADS_PDF) != EXPECTED_CLIENT_SPREADS:
        raise RuntimeError(
            f"Spread PDF has {pdf_pages(SPREADS_PDF)} pages, "
            f"expected {EXPECTED_CLIENT_SPREADS}"
        )

    run_preflight(dom_report, PRODUCTION_PROOF)
    pipeline.make_contact_sheet_pdf(
        SPREADS_PDF,
        OUTPUT_BUILD / "full-contact-sheet.pdf",
        temp_dir,
    )

    if not args.skip_client_preview:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_client_preview_pdf.py"),
                str(SPREADS_PDF),
                str(CLIENT_PDF),
                "--force",
            ],
            cwd=ROOT,
            check=True,
        )
        if pdf_pages(CLIENT_PDF) != EXPECTED_CLIENT_SPREADS:
            raise RuntimeError("Client preview lost a spread")

    validation = {
        "status": "pass",
        "build": "V30_ASSET_COMPLETION",
        "design_lock": page_plan.get("design_lock"),
        "pagination_changed": False,
        "interior_pages": pdf_pages(PRODUCTION_PROOF),
        "spreads": pdf_pages(SPREADS_PDF),
        "client_spreads": (
            pdf_pages(CLIENT_PDF) if CLIENT_PDF.is_file() else None
        ),
        "rerendered_count": len(changed_hashes),
        "reused_count": len(reused_hashes),
        "rerendered_sha256": changed_hashes,
        "reused_source_sha256": reused_hashes,
        "outputs": {
            "production_proof": pipeline.repo_path(PRODUCTION_PROOF),
            "spreads": pipeline.repo_path(SPREADS_PDF),
            "client": pipeline.repo_path(CLIENT_PDF),
            "contact_sheet": pipeline.repo_path(
                OUTPUT_BUILD / "full-contact-sheet.pdf"
            ),
        },
    }
    pipeline.write_json(OUTPUT_BUILD / "v30-validation.json", validation)
    pipeline.write_json(PROTOTYPE / "v30-validation.json", validation)
    return validation


def main() -> int:
    validation = build()
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
