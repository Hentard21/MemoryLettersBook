#!/usr/bin/env python3
"""Link family transcription candidates into the global physical-letter index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "assets/families/letters-transcriptions-index.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def candidate_for(entry: dict[str, Any]) -> Path | None:
    hero_id = entry["hero_id"]
    letter_id = entry["letter_id"]
    directory = ROOT / "assets/families" / hero_id / "transcriptions"
    exact = directory / f"{letter_id}_transcription.json"
    if exact.is_file():
        return exact
    matches = sorted(directory.glob(f"{letter_id}*.json")) if directory.is_dir() else []
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    args = parse_args()
    payload = load(INDEX)
    linked = 0
    missing = 0

    for entry in payload.get("entries", []):
        candidate = candidate_for(entry)
        if candidate is None:
            entry["transcription_file"] = None
            entry["status"] = "missing"
            entry["notes"] = "No transcription candidate is linked; do not reconstruct by guess."
            missing += 1
            continue

        metadata = load(candidate)
        relative = candidate.relative_to(ROOT).as_posix()
        source_file = metadata.get("source_transcription_file")
        print_file = metadata.get("print_transcription_file")
        for label, value in (("source", source_file), ("print", print_file)):
            if value and not (ROOT / value).is_file():
                raise FileNotFoundError(f"Missing {label} layer for {relative}: {value}")

        approved = metadata.get("approved_for_print") is True
        entry["transcription_file"] = relative
        entry["status"] = "approved" if approved else "REVIEW_REQUIRED"
        entry["notes"] = (
            "Two-layer transcription linked and approved."
            if approved
            else "Two-layer candidate linked; manual comparison with the physical scan is required."
        )
        linked += 1

    payload["transcriptions_present"] = linked
    payload["missing_transcriptions"] = missing
    print(json.dumps({"linked": linked, "missing": missing}, ensure_ascii=False, indent=2))
    if args.apply:
        INDEX.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {INDEX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
