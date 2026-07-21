#!/usr/bin/env python3
"""Build the intro map from the locked 74-family order manifest.

The generated SVG highlights only regions represented by families in the
current book manifest.  It deliberately does not infer participation from the
blanket map in the 255-page draft.  Dry run is the default.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "design"
    / "prototypes"
    / "print-v12"
    / "assets"
    / "maps"
    / "russia-all-participants.svg"
)
DEFAULT_MANIFEST = PROJECT_ROOT / "content" / "manifests" / "reference-family-order-reset.json"
DEFAULT_FAMILY_OUTPUT = DEFAULT_SOURCE.with_name("russia-family-participants.svg")
DEFAULT_ACTION_OUTPUT = DEFAULT_SOURCE.with_name("russia-action-participants-schematic.svg")

REGION_TO_FEATURE = {
    "москва": "RUMOS",
    "санкт-петербург": "RUSPE",
    "амурская область": "RUAMU",
    "астраханская область": "RUAST",
    "волгоградская область": "RUVGG",
    "забайкальский край": "RUZAB",
    "ивановская область": "RUIVA",
    "карачаево-черкесская республика": "RUKC",
    "красноярский край": "RUKYA",
    "курганская область": "RUKGN",
    "липецкая область": "RULIP",
    "нижегородская область": "RUNIZ",
    "новосибирская область": "RUNVS",
    "оренбургская область": "RUORE",
    "приморский край": "RUPRI",
    "псковская область": "RUPSK",
    "республика адыгея": "RUAD",
    "республика башкортостан": "RUBA",
    "республика дагестан": "RUDA",
    "республика ингушетия": "RUIN",
    "республика калмыкия": "RUKL",
    "республика татарстан": "RUTA",
    "республика тыва": "RUTY",
    "республика хакасия": "RUKK",
    "свердловская область": "RUSVE",
    "тюменская область": "RUTYU",
    "ханты-мансийский ао-югра": "RUKHM",
    "челябинская область": "RUCHE",
    "чеченская республика": "RUCE",
    "ярославская область": "RUYAR",
}


def normalize_region(value: str) -> str:
    value = value.strip().lstrip(". ")
    value = re.sub(r"\s*-\s*", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value.casefold()


def clean_chukotka_antimeridian_strips(svg: str) -> str:
    """Remove three wraparound slivers from the legacy Chukotka geometry.

    The Simplemaps source encodes the 180-degree map seam as three long,
    almost-flat subpaths.  With a print stroke they render as a striped
    rectangle at the eastern edge.  All other Chukotka subpaths are retained
    at their original absolute coordinates.
    """

    path_match = re.search(r'(<path\b(?=[^>]*\bid="RUCHU")[^>]*\bd=")([^"]+)(")', svg)
    if not path_match:
        raise ValueError("Chukotka path RUCHU was not found")

    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", path_match.group(2))
    index = 0
    command: str | None = None
    current_x = current_y = 0.0
    start_x = start_y = 0.0
    subpaths: list[list[tuple[float, float]]] = []
    current_points: list[tuple[float, float]] = []

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command in {"M", "m", "l"}:
            first_pair = True
            while index < len(tokens) and not tokens[index].isalpha():
                x_value = float(tokens[index])
                y_value = float(tokens[index + 1])
                index += 2
                if command == "M":
                    current_x, current_y = x_value, y_value
                else:
                    current_x += x_value
                    current_y += y_value
                if command in {"M", "m"} and first_pair:
                    if current_points:
                        subpaths.append(current_points)
                    current_points = []
                    start_x, start_y = current_x, current_y
                current_points.append((current_x, current_y))
                first_pair = False
                if command == "M":
                    command = "L"
                elif command == "m":
                    command = "l"
        elif command in {"z", "Z"}:
            if current_points:
                subpaths.append(current_points)
                current_points = []
            current_x, current_y = start_x, start_y
            command = None
        else:
            raise ValueError(f"Unsupported RUCHU path command: {command}")
    if current_points:
        subpaths.append(current_points)
    if len(subpaths) != 11:
        raise ValueError(f"Expected 11 Chukotka subpaths, found {len(subpaths)}")

    retained = [points for subpath_index, points in enumerate(subpaths) if subpath_index not in {4, 5, 6}]

    def coordinate(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    cleaned_parts = []
    for points in retained:
        first_x, first_y = points[0]
        commands = [f"M{coordinate(first_x)} {coordinate(first_y)}"]
        commands.extend(f"L{coordinate(x_value)} {coordinate(y_value)}" for x_value, y_value in points[1:])
        commands.append("z")
        cleaned_parts.append("".join(commands))
    cleaned_path = " ".join(cleaned_parts)
    return svg[: path_match.start(2)] + cleaned_path + svg[path_match.end(2) :]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scope", choices=("family", "action"), default="family")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    manifest_file = args.manifest.resolve()
    default_output = DEFAULT_FAMILY_OUTPUT if args.scope == "family" else DEFAULT_ACTION_OUTPUT
    output = (args.output or default_output).resolve()
    data = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    regions = sorted({normalize_region(item["region"]) for item in data["families"]})
    missing = [region for region in regions if region not in REGION_TO_FEATURE]
    if missing:
        raise ValueError(f"Unmapped participant regions: {missing}")
    feature_ids = sorted({REGION_TO_FEATURE[region] for region in regions})

    svg = source.read_text(encoding="utf-8-sig")
    svg_ids = set(re.findall(r'\bid="([A-Z0-9]+)"', svg))
    unavailable = [feature_id for feature_id in feature_ids if feature_id not in svg_ids]
    if unavailable:
        raise ValueError(f"Map feature IDs are absent: {unavailable}")

    if args.scope == "family":
        style = (
            "<style>"
            "#features path{fill:#dfe2e5;stroke:#ffffff;stroke-width:.8;opacity:.98}"
            "#features path.participant{fill:#873f46}"
            "#points,#label_points{display:none}"
            "</style>"
        )
    else:
        # The owner reference lists 89 action participants, while this legacy
        # Simplemaps base exposes only 83 path features.  Rendering it as one
        # project silhouette avoids falsely presenting 83 as an exact count.
        style = (
            "<style>"
            "#features path{fill:#223b5e;stroke:#f3f2ee;stroke-width:.55;opacity:.97}"
            "#features #RUCHU{stroke:none}"
            "#points,#label_points{display:none}"
            "</style>"
        )
    svg, replacements = re.subn(r"<style>.*?</style>", style, svg, count=1, flags=re.DOTALL)
    if replacements != 1:
        raise ValueError("Expected one map style element")
    svg = clean_chukotka_antimeridian_strips(svg)
    if args.scope == "family":
        for feature_id in feature_ids:
            pattern = rf'<path(?=[^>]*\bid="{re.escape(feature_id)}")'
            svg, count = re.subn(pattern, '<path class="participant"', svg, count=1)
            if count != 1:
                raise ValueError(f"Could not mark feature {feature_id}")

    summary = {
        "scope": args.scope,
        "family_count": len(data["families"]),
        "participant_region_count": len(regions),
        "participant_feature_ids": feature_ids,
        "source_map_feature_count": len(re.findall(r'<path\b', svg)),
        "action_subject_count_from_owner_reference": 89 if args.scope == "action" else None,
        "map_status": (
            "manifest_driven_family_regions"
            if args.scope == "family"
            else "schematic_only_legacy_base_has_83_features"
        ),
        "output": str(output),
        "mode": "apply" if args.apply else "dry-run",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.apply:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(svg, encoding="utf-8")
        print(f"WROTE: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
