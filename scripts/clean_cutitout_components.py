#!/usr/bin/env python3
"""Remove detached mask islands from a CutItOut PNG without changing the main subject."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--alpha-threshold", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    encoded = np.fromfile(source, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(f"Expected an RGBA PNG: {source}")

    alpha = image[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > args.alpha_threshold).astype(np.uint8), connectivity=8
    )
    if count <= 1:
        raise ValueError("No foreground component found")
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    removed_pixels = int(np.count_nonzero((labels != 0) & (labels != largest_label)))
    image[:, :, 3] = np.where(labels == largest_label, alpha, 0).astype(np.uint8)

    output.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded_output = cv2.imencode(".png", image)
    if not ok:
        raise OSError(f"Could not encode {output}")
    encoded_output.tofile(output)
    print(f"WROTE: {output}")
    print(f"COMPONENTS: {count - 1}; REMOVED_PIXELS: {removed_pixels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
