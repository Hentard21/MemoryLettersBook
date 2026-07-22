#!/usr/bin/env python3
"""Instantiate static Onest/Golos weights for press-safe Chromium PDFs.

Chromium on Windows emits variable TrueType fonts as self-contained Type 3
outlines. The approved typography remains unchanged; this script merely
materializes the exact weights used by the locked CSS so Chromium can embed
CID/Type 0 font programs.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "design/fonts"
OUTPUT_DIR = FONT_DIR / "static-print"
WEIGHTS = (400, 500, 600, 650, 700, 750, 800)


def build(source: Path, family: str) -> None:
    for weight in WEIGHTS:
        font = TTFont(source)
        instance = instantiateVariableFont(font, {"wght": weight}, inplace=False)
        target = OUTPUT_DIR / f"{family}-{weight}.ttf"
        instance.save(target)
        print(target)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build(FONT_DIR / "Onest.ttf", "Onest")
    build(FONT_DIR / "GolosText.ttf", "GolosText")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
