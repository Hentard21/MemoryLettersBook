#!/usr/bin/env python3
"""Fill required production manifest fields from canonical reference data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "content/production/families"


def relationship_from_title(title: str) -> str:
    upper = title.upper()
    if "МАМА" in upper:
        return "мама"
    if "ОТЕЦ" in upper or "ПАПА" in upper:
        return "отец"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changed = 0
    unresolved = []
    for path in sorted(FAMILIES.glob("hero-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        reference = data.get("canonical_reference") or {}
        relationship = str(data.get("relationship") or "")
        if not relationship:
            relationship = relationship_from_title(str(reference.get("title_text") or ""))
        source_pages = list(data.get("source_pages") or reference.get("pages") or [])
        if not relationship:
            unresolved.append(str(data.get("hero_id") or path.stem))
        if data.get("relationship") != relationship or data.get("source_pages") != source_pages:
            data["relationship"] = relationship
            data["source_pages"] = source_pages
            changed += 1
            if args.apply:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"families=74 changed={changed} unresolved_relationship={len(unresolved)} mode={'apply' if args.apply else 'dry-run'}")
    if unresolved:
        print("unresolved:", ", ".join(unresolved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
