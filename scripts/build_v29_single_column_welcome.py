#!/usr/bin/env python3
"""Assemble the V29 alternate intro without rebuilding family material.

V29 changes only the five authored welcome pages.  The family and finale
spreads are reused byte-for-byte from the checked V28 build cache, which keeps
the approved family templates outside this experiment's scope.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

import book_pipeline as pipeline


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "output-v28-map-restored"
OUTPUT_BUILD = ROOT / "output-v29-single-column-welcome"
PROTOTYPE = ROOT / "design/prototypes/print-v29-single-column-welcome"
INTRO_HTML = PROTOTYPE / "interior-single-column-welcome-v29.html"
INTRO_PLAN = PROTOTYPE / "intro-page-plan-v29.json"
SPREADS_PDF = OUTPUT_BUILD / "PRINT_V29_SINGLE_COLUMN_WELCOME_SPREADS.pdf"
CLIENT_PDF = ROOT / "output/pdf/PRINT_V29_SINGLE_COLUMN_WELCOME_CLIENT.pdf"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def copy_build_data() -> None:
    for name in (
        "page-plan.json",
        "generated-toc.json",
        "placement-ledger.json",
        "build-summary.json",
        "family-dom-report.json",
        "review-queue.csv",
        "pdf-technical-audit.json",
    ):
        source = require(SOURCE_BUILD / name)
        shutil.copy2(source, OUTPUT_BUILD / name)


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_intro_single_column_v29.py")],
        cwd=ROOT,
        check=True,
    )
    require(INTRO_HTML)
    require(INTRO_PLAN)
    OUTPUT_BUILD.mkdir(parents=True, exist_ok=True)
    (OUTPUT_BUILD / "tmp").mkdir(parents=True, exist_ok=True)
    copy_build_data()

    toc = pipeline.read_json(OUTPUT_BUILD / "generated-toc.json")
    registry = pipeline.v21.registries()
    generated_intro = OUTPUT_BUILD / "generated-frontmatter.html"
    original_intro = pipeline.INTRO_HTML
    try:
        pipeline.INTRO_HTML = INTRO_HTML
        pipeline.patch_intro_toc(toc, generated_intro, registry)
    finally:
        pipeline.INTRO_HTML = original_intro

    dom_source = run_json(
        ["node", str(ROOT / "scripts/check_intro_single_column_v29.mjs"), str(INTRO_HTML)]
    )
    dom_generated = run_json(
        ["node", str(ROOT / "scripts/check_intro_single_column_v29.mjs"), str(generated_intro)]
    )
    if dom_source.get("status") != "pass" or dom_generated.get("status") != "pass":
        raise RuntimeError("V29 intro DOM verification failed")

    intro_spreads = OUTPUT_BUILD / "tmp/intro-spreads.pdf"
    pipeline.playwright_render(generated_intro, intro_spreads)
    family_spreads = require(SOURCE_BUILD / "tmp/family-spreads.pdf")
    back_spread = require(SOURCE_BUILD / "tmp/back-matter-spread.pdf")
    family_hash_before = sha256(family_spreads)
    back_hash_before = sha256(back_spread)
    pipeline.append_pdfs((intro_spreads, family_spreads, back_spread), SPREADS_PDF)
    family_hash_after = sha256(family_spreads)
    back_hash_after = sha256(back_spread)
    if family_hash_before != family_hash_after or back_hash_before != back_hash_after:
        raise RuntimeError("Reused V28 source PDFs changed during V29 assembly")

    intro_count = len(PdfReader(intro_spreads).pages)
    family_count = len(PdfReader(family_spreads).pages)
    back_count = len(PdfReader(back_spread).pages)
    spread_count = len(PdfReader(SPREADS_PDF).pages)
    expected = intro_count + family_count + back_count
    if (intro_count, spread_count, expected) != (7, 98, 98):
        raise RuntimeError(
            f"Unexpected pagination: intro={intro_count}, family={family_count}, "
            f"back={back_count}, total={spread_count}"
        )

    CLIENT_PDF.parent.mkdir(parents=True, exist_ok=True)
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

    client_count = len(PdfReader(CLIENT_PDF).pages)
    if client_count != 98:
        raise RuntimeError(f"Client PDF has {client_count} pages, expected 98")

    validation = {
        "status": "pass",
        "scope": "five authored intro greeting pages only",
        "intro_source": INTRO_HTML.relative_to(ROOT).as_posix(),
        "source_build": SOURCE_BUILD.relative_to(ROOT).as_posix(),
        "intro_spreads": intro_count,
        "reused_family_spreads": family_count,
        "reused_back_matter_spreads": back_count,
        "total_spreads": spread_count,
        "client_spreads": client_count,
        "first_family_spread_index_1_based": intro_count + 1,
        "family_pages_rerendered": False,
        "family_source_sha256": family_hash_before,
        "back_matter_source_sha256": back_hash_before,
        "dom_source": dom_source,
        "dom_generated": dom_generated,
        "output_spreads": SPREADS_PDF.relative_to(ROOT).as_posix(),
        "output_client": CLIENT_PDF.relative_to(ROOT).as_posix(),
    }
    serialized = json.dumps(validation, ensure_ascii=False, indent=2) + "\n"
    (OUTPUT_BUILD / "v29-validation.json").write_text(serialized, encoding="utf-8")
    (PROTOTYPE / "v29-validation.json").write_text(serialized, encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
