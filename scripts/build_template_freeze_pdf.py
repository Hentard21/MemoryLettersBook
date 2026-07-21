#!/usr/bin/env python3
"""Combine the approved standard and extended family examples into one review PDF."""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ROOT / "design/prototypes/print-v12/PRINT_V18_REFINED_CLIENT_OVERVIEW.pdf",
    ROOT / "design/prototypes/print-v18/PRINT_V18_HERO_014_TWO_SPREAD_TEST.pdf",
)
OUTPUT = ROOT / "design/prototypes/print-v19/PRINT_V19_FROZEN_TEMPLATES.pdf"
SNAPSHOT = ROOT / "design/prototypes/print-v19/PRINT_V19_TEMPLATE_FREEZE_CANDIDATE.pdf"
CLIENT_APPROVAL = ROOT / "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf"


def main() -> int:
    for source in SOURCES:
        if not source.is_file():
            raise FileNotFoundError(source)

    writer = PdfWriter()
    page_counts: list[int] = []
    for source in SOURCES:
        reader = PdfReader(source)
        page_counts.append(len(reader.pages))
        for page in reader.pages:
            writer.add_page(page)

    writer.add_metadata(
        {
            "/Title": "Письма памяти — замороженные семейные шаблоны",
            "/Subject": "Стандартный шаблон Анастасии и расширенный шаблон Евгения",
            "/Creator": "book-project template freeze builder",
        }
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as handle:
        writer.write(handle)
    copyfile(OUTPUT, SNAPSHOT)
    CLIENT_APPROVAL.parent.mkdir(parents=True, exist_ok=True)
    copyfile(OUTPUT, CLIENT_APPROVAL)

    print(f"WROTE: {OUTPUT}")
    print(f"SNAPSHOT: {SNAPSHOT}")
    print(f"CLIENT_APPROVAL: {CLIENT_APPROVAL}")
    print(f"SOURCE_PAGES: {page_counts}; TOTAL: {sum(page_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
