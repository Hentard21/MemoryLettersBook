#!/usr/bin/env python3
"""Pass 1: calculate stable pagination for all canonical families."""

from __future__ import annotations

import argparse
from pathlib import Path

from book_pipeline import OUTPUT, build_page_plan_data, v21, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT / "page-plan.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    families = v21.load_families()
    if len(families) != 74:
        raise RuntimeError(f"Expected 74 canonical families, found {len(families)}")
    plan = build_page_plan_data(families)
    write_json(args.output.resolve(), plan)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
