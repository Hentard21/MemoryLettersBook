#!/usr/bin/env python3
"""Pass 2: build the dynamic TOC from page-plan.json."""

from __future__ import annotations

import argparse
from pathlib import Path

from book_pipeline import OUTPUT, build_toc_data, read_json, v21, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-plan", type=Path, default=OUTPUT / "page-plan.json")
    parser.add_argument("--output", type=Path, default=OUTPUT / "generated-toc.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    page_plan = read_json(args.page_plan.resolve())
    families = v21.load_families()
    toc = build_toc_data(page_plan, families)
    write_json(args.output.resolve(), toc)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
