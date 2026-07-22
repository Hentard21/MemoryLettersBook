#!/usr/bin/env python3
"""Build the copy-only manual correction package for selected title photos.

The script copies, hashes and inventories source assets. It never edits the
master images, family manifests, placement data or rendering code. A second
run must use ``--verify-existing`` so an owner's returned work cannot be
overwritten accidentally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


OUTPUT_REL = Path("assets/manual-cutout-help-title-corrections")

GENERAL_REQUIREMENTS = [
    "Use the working/upscaled file for masking; keep the original only for provenance and recovery.",
    "Return a PNG with real transparency. Do not replace transparency with white.",
    "Preserve facial features and recognisability; do not change clothes, insignia, medals, equipment or objects in hands.",
    "Keep hair, ears, fingers, sleeves, straps and all meaningful silhouette details; inspect the mask at 100%.",
    "Prepare a stable lower edge and approximately waist-up composition where the source allows it, following the approved Eugene title-page placement.",
    "Do not invent missing body parts. If a clean waist crop is impossible, keep the truthful available crop and mark it needs-fix.",
]

README_TEXT = """# Title-photo corrections for manual CutItOut work

This is a copy-only correction package. Nothing in `assets/families/`,
`assets/production-ready/` or `assets/processed-flagships/` was modified.

The numbered files in each `hero-*` folder have clear roles:

- `original_master` is the untouched extracted source and is included for
  provenance/recovery;
- `working_upscaled` is the file to load into CutItOut;
- `supporting_*` belongs to the same family but is a separate requested group
  image;
- `existing_*_cutout_reference` is a superseded or faulty mask supplied only
  for comparison. Do not treat it as the source for a new mask.

The required return filename and family-specific masking instructions are in
`manifest.json`. The common rule is: transparent PNG, preserve identity and
documentary details, crop approximately to the waist where the real frame
allows it, and do not generate missing anatomy.

Rebuild from a clean location:

```powershell
python scripts\build_title_rework_package.py
```

Verify this package without overwriting anything:

```powershell
python scripts\build_title_rework_package.py --verify-existing
```
"""


FAMILIES: list[dict[str, Any]] = [
    {
        "hero_id": "hero-005",
        "hero_name": "Евгений",
        "output_pages": [22],
        "return_file": "hero-005_title_nobg.png",
        "intended_edit": (
            "Remove the outdoor background from the father-and-child group. "
            "Keep both people together, including the child's hood, gloves and "
            "the hero's sleeves, hands and uniform patch. Use a natural lower "
            "edge; do not make either person look cut off or floating."
        ),
        "files": [
            ("original_master", "assets/families/hero-005/flagship/hero-005_p027_image176.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-005/hero-005_p027_image176_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-006",
        "hero_name": "Алимамед",
        "output_pages": [24],
        "return_file": "hero-006_title_group_nobg.png",
        "additional_return_files": ["hero-006_supporting_boys_nobg.png"],
        "intended_edit": (
            "Create two transparent group cutouts. For image184 retain both boys, "
            "the framed portrait, uniform jacket, cap, medals and every hand. For "
            "image185 retain both boys, the worn uniform jacket, cap, medals and "
            "all hands. Do not separate the children or recreate the portrait."
        ),
        "files": [
            ("original_master", "assets/families/hero-006/archive-photos/hero-006_p030_image184.jpg"),
            ("working_upscaled", "assets/production-ready/archive/hero-006/hero-006_p030_image184_upscaled_2x.jpg"),
            ("supporting_original_master", "assets/families/hero-006/archive-photos/hero-006_p030_image185.jpg"),
            ("supporting_working_upscaled", "assets/production-ready/archive/hero-006/hero-006_p030_image185_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-009",
        "hero_name": "Егор",
        "output_pages": [32],
        "return_file": "hero-009_title_group_nobg.png",
        "intended_edit": (
            "Remove the garden background while preserving the hero and all three "
            "children as one group. Keep the held child, interlocked arms, fingers, "
            "clothing edges and the full family relationship visible."
        ),
        "files": [
            ("original_master", "assets/families/hero-009/flagship/hero-009_p039_image225.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-009/hero-009_p039_image225_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-022",
        "hero_name": "Сергей",
        "output_pages": [62],
        "return_file": "hero-022_title_nobg.png",
        "intended_edit": (
            "Remove the landscape and birch trunk. Restore only a clean silhouette "
            "of the hero that is genuinely present in the frame; keep his visible "
            "hand and jacket edges. Do not reconstruct the hidden side behind the tree."
        ),
        "files": [
            ("original_master", "assets/families/hero-022/flagship/hero-022_p080_image409.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-022/hero-022_p080_image409_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-023",
        "hero_name": "Дмитрий",
        "output_pages": [64],
        "return_file": "hero-023_title_nobg.png",
        "intended_edit": (
            "Preventive title correction requested for the next affected family. "
            "Remove the vehicle cabin and seat while retaining the truthful seated "
            "upper-body silhouette, coat, hands and belt details. Do not extend the body."
        ),
        "files": [
            ("original_master", "assets/families/hero-023/flagship/hero-023_p083_image419.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-023/hero-023_p083_image419_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-035",
        "hero_name": "Илья",
        "output_pages": [94],
        "return_file": "hero-035_title_group_nobg.png",
        "intended_edit": (
            "Remove the room, chair and tree background, preserving the hero and "
            "both children as one family group. Keep overlapping arms, hands and "
            "the truthful seated composition; do not invent legs or hidden anatomy."
        ),
        "files": [
            ("original_master", "assets/families/hero-035/flagship/hero-035_p122_image581.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-035/hero-035_p122_image581_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-039",
        "hero_name": "Василий",
        "output_pages": [102],
        "reference_content_page": 105,
        "return_file": "hero-039_alt_p134_image631_nobg.png",
        "intended_edit": (
            "Replace the current title group with the alternate formal portrait "
            "from reference p134 image631. Isolate only the man on the left half; "
            "exclude the separate medal panel. Preserve uniform collar, shoulder "
            "boards and visible medals, and produce a waist-up transparent figure."
        ),
        "files": [
            ("alternate_original_master", "assets/families/hero-039/archive-photos/hero-039_p134_image631.jpg"),
            ("alternate_working_upscaled", "assets/production-ready/archive/hero-039/hero-039_p134_image631_upscaled_2x.jpg"),
            ("existing_current_cutout_reference", "assets/processed-flagships/hero-039/hero-039_manual_v2_nobg.png"),
            ("existing_automatic_cutout_reference", "assets/processed-flagships/hero-039/hero-039_p134_image629_nobg.png"),
        ],
    },
    {
        "hero_id": "hero-047",
        "hero_name": "Александр",
        "output_pages": [122],
        "reference_content_page": 125,
        "return_file": "hero-047_alt_p159_image728_nobg.png",
        "intended_edit": (
            "Replace the current title image with the alternate full portrait in "
            "blue uniform and peaked cap from reference p159 image728. Remove the "
            "trees and pavement, preserve the cap, insignia and every medal, and "
            "crop cleanly to approximately the waist."
        ),
        "files": [
            ("alternate_original_master", "assets/families/hero-047/archive-photos/hero-047_p159_image728.jpg"),
            ("alternate_working_upscaled", "assets/production-ready/archive/hero-047/hero-047_p159_image728_upscaled_2x.jpg"),
            ("existing_current_cutout_reference", "assets/processed-flagships/hero-047/hero-047_manual_nobg.png"),
            ("existing_automatic_cutout_reference", "assets/processed-flagships/hero-047/hero-047_p159_image727_nobg.png"),
        ],
    },
    {
        "hero_id": "hero-050",
        "hero_name": "Мустафа",
        "output_pages": [130],
        "return_file": "hero-050_title_group_nobg.png",
        "intended_edit": (
            "Remove the shopping-centre background while preserving the hero and "
            "all three children, including the child and stroller, as one truthful "
            "family group. Keep hands, legs and stroller contours; do not merge people."
        ),
        "files": [
            ("original_master", "assets/families/hero-050/flagship/hero-050_p169_image769.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-050/hero-050_p169_image769_upscaled_2x.jpg"),
        ],
    },
    {
        "hero_id": "hero-076",
        "hero_name": "Николай",
        "output_pages": [192],
        "return_file": "hero-076_title_nobg_fixed.png",
        "intended_edit": (
            "Replace the faulty title mask through which the map is visible. Remove "
            "all branches and sky, preserve the helmet, balaclava, face, armour, "
            "straps and equipment edges, and close every accidental transparent hole. "
            "Use the real upper-body crop; do not fabricate a waist."
        ),
        "files": [
            ("original_master", "assets/families/hero-076/flagship/hero-076_p254_image1101.jpg"),
            ("working_upscaled", "assets/production-ready/flagship/hero-076/hero-076_p254_image1101_upscaled_2x.jpg"),
            ("existing_current_cutout_reference", "assets/processed-flagships/hero-076/hero-076_manual_v2_nobg.png"),
            ("existing_faulty_cutout_reference", "assets/processed-flagships/hero-076/hero-076_p254_image1101_nobg.png"),
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_REL)
    parser.add_argument("--verify-existing", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "width_px": image.width,
            "height_px": image.height,
            "format": image.format,
            "color_mode": image.mode,
            "has_alpha": "A" in image.getbands() or "transparency" in image.info,
        }


def destination_name(index: int, hero_id: str, role: str, source: Path) -> str:
    clean_role = role.replace("alternate_", "alt_")
    return f"{index:02d}_{hero_id}_{clean_role}{source.suffix.lower()}"


def copy_entry(
    *, source: Path, destination: Path, root: Path, role: str
) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    source_hash = sha256(source)
    if sha256(destination) != source_hash:
        raise ValueError(f"Copy hash mismatch: {source} -> {destination}")
    return {
        "role": role,
        "source_file": relative(source, root),
        "packaged_file": relative(destination, root),
        "sha256": source_hash,
        "bytes": destination.stat().st_size,
        **metadata(destination),
    }


def verify_existing(root: Path, output: Path) -> int:
    manifest_file = output / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(manifest_file)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    count = 0
    for family in manifest["families"]:
        for item in family["files"]:
            source = root / item["source_file"]
            packaged = root / item["packaged_file"]
            if not source.is_file() or not packaged.is_file():
                raise FileNotFoundError(source if not source.is_file() else packaged)
            if sha256(source) != item["sha256"]:
                raise ValueError(f"Source changed: {source}")
            if sha256(packaged) != item["sha256"]:
                raise ValueError(f"Packaged copy changed: {packaged}")
            count += 1
    if (output / "README.md").read_text(encoding="utf-8") != README_TEXT:
        raise ValueError("README.md differs from the package builder")
    print(f"verified families: {len(manifest['families'])}")
    print(f"verified copied files: {count}")
    return 0


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output = output.resolve()
    expected_output = (root / OUTPUT_REL).resolve()
    if output != expected_output and not args.output.is_absolute():
        raise ValueError(f"Output escaped the requested package path: {output}")

    if args.verify_existing:
        return verify_existing(root, output)
    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing package: {output}. "
            "Use --verify-existing or move the package explicitly."
        )

    output.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "package_id": "title-photo-corrections-v22",
        "generated_by": "scripts/build_title_rework_package.py",
        "copy_only": True,
        "masters_modified": False,
        "general_requirements": GENERAL_REQUIREMENTS,
        "families": [],
    }

    for family in FAMILIES:
        target = output / family["hero_id"]
        copied: list[dict[str, Any]] = []
        for index, (role, source_rel) in enumerate(family["files"], start=1):
            source = root / source_rel
            destination = target / destination_name(index, family["hero_id"], role, source)
            copied.append(
                copy_entry(
                    source=source,
                    destination=destination,
                    root=root,
                    role=role,
                )
            )
        entry = {key: value for key, value in family.items() if key != "files"}
        entry["status"] = "ready_for_manual_cutout"
        entry["files"] = copied
        manifest["families"].append(entry)

    (output / "README.md").write_text(README_TEXT, encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built package: {output}")
    print(f"families: {len(manifest['families'])}")
    print(f"copied files: {sum(len(item['files']) for item in manifest['families'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
