#!/usr/bin/env python3
"""Create contact sheets and ten-family review batches from rendered PDFs."""

from __future__ import annotations

import argparse
from pathlib import Path

from book_pipeline import OUTPUT, make_contact_sheet_pdf, make_review_batches, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--spreads", type=Path, default=OUTPUT / "PRINT_V21_FULL_DRAFT_SPREADS.pdf")
    parser.add_argument("--family-spreads", type=Path, default=OUTPUT / "tmp/family-spreads.pdf")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    page_plan = read_json(output_dir / "page-plan.json")
    make_contact_sheet_pdf(
        args.spreads.resolve(),
        output_dir / "full-contact-sheet.pdf",
        output_dir / "tmp",
    )
    batches = make_review_batches(
        args.family_spreads.resolve(),
        page_plan,
        output_dir / "review-batches",
    )
    print(output_dir / "full-contact-sheet.pdf")
    for path in batches:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
