#!/usr/bin/env python3
"""Read-only technical audit for a PDF made from book-project spread HTML.

The script never rewrites the inspected PDF.  It records page boxes, placed-image
effective resolution, font resources, colour usage and objects entering the
preliminary inner safe zone.  Coordinates in the JSON output use millimetres.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import ImageCms
from pypdf import PdfReader
from pypdf.generic import ContentStream


PT_PER_MM = 72 / 25.4


def mm(value: float) -> float:
    return round(float(value) / PT_PER_MM, 3)


def dereference(value: Any) -> Any:
    try:
        return value.get_object()
    except (AttributeError, TypeError):
        return value


def indirect_id(value: Any) -> str:
    reference = getattr(value, "indirect_reference", None)
    if reference is None:
        return f"direct-{id(value)}"
    return f"{reference.idnum}-{reference.generation}"


def pdf_name(value: Any) -> str:
    if value is None:
        return ""
    # pypdf names stringify as ``/DeviceRGB`` while pdfminer PSLiteral values
    # stringify as ``/'DeviceRGB'``.  Normalise both without exposing object
    # representations in the audit JSON.
    return str(value).strip().lstrip("/").strip("'\"")


def serialise_colour_space(value: Any) -> str:
    value = dereference(value)
    if isinstance(value, list):
        if not value:
            return "unknown"
        head = pdf_name(value[0])
        if head == "ICCBased" and len(value) > 1:
            profile = dereference(value[1])
            components = profile.get("/N", profile.get("N", "?"))
            return f"ICCBased(N={components})"
        tail = ",".join(pdf_name(item) for item in value[1:])
        return head if not tail else f"{head}[{tail}]"
    return pdf_name(value) or "unknown"


def font_descriptor(font: Any) -> Any | None:
    font = dereference(font)
    if font.get("/Subtype") == "/Type0":
        descendants = dereference(font.get("/DescendantFonts", []))
        if descendants:
            descendant = dereference(descendants[0])
            descriptor = descendant.get("/FontDescriptor")
            return dereference(descriptor) if descriptor else None
        return None
    descriptor = font.get("/FontDescriptor")
    return dereference(descriptor) if descriptor else None


def collect_fonts(reader: PdfReader) -> list[dict[str, Any]]:
    fonts: dict[str, dict[str, Any]] = {}
    visited_forms: set[tuple[str, int]] = set()

    def visit_resources(resources: Any, page_number: int) -> None:
        resources = dereference(resources or {})
        for resource_name, reference in dereference(resources.get("/Font", {})).items():
            font = dereference(reference)
            key = indirect_id(font)
            descriptor = font_descriptor(font)
            font_name = font.get("/BaseFont")
            if not font_name and descriptor:
                font_name = descriptor.get("/FontName")
            embedded_files = [
                name
                for name in ("/FontFile", "/FontFile2", "/FontFile3")
                if descriptor and descriptor.get(name) is not None
            ]
            subtype = pdf_name(font.get("/Subtype"))
            entry = fonts.setdefault(
                key,
                {
                    "object_id": key,
                    "font_name": pdf_name(font_name) or "unnamed",
                    "font_family": pdf_name(descriptor.get("/FontFamily")) if descriptor else "",
                    "subtype": subtype,
                    "resource_names": set(),
                    "pages": set(),
                    "embedded_font_files": embedded_files,
                    "charproc_count": len(dereference(font.get("/CharProcs", {}))),
                },
            )
            entry["resource_names"].add(str(resource_name))
            entry["pages"].add(page_number)

        for _, reference in dereference(resources.get("/XObject", {})).items():
            xobject = dereference(reference)
            if xobject.get("/Subtype") != "/Form" or not xobject.get("/Resources"):
                continue
            form_key = (indirect_id(xobject), page_number)
            if form_key in visited_forms:
                continue
            visited_forms.add(form_key)
            visit_resources(xobject.get("/Resources"), page_number)

    for page_number, page in enumerate(reader.pages, start=1):
        visit_resources(page.get("/Resources"), page_number)

    result: list[dict[str, Any]] = []
    for entry in fonts.values():
        entry["resource_names"] = sorted(entry["resource_names"])
        entry["pages"] = sorted(entry["pages"])
        entry["program_status"] = (
            "embedded_font_file"
            if entry["embedded_font_files"]
            else "self_contained_type3_charprocs"
            if entry["subtype"] == "Type3" and entry["charproc_count"]
            else "font_program_not_found"
        )
        result.append(entry)
    return sorted(result, key=lambda item: (item["font_name"], item["object_id"]))


def collect_colour_and_transparency(reader: PdfReader) -> dict[str, Any]:
    operator_counts: Counter[str] = Counter()
    named_spaces: Counter[str] = Counter()
    extgstates: dict[str, dict[str, Any]] = {}
    soft_mask_images: set[str] = set()
    visited_forms: set[str] = set()

    def scan_stream(stream: Any, resources: Any) -> None:
        if stream is None:
            return
        try:
            content = ContentStream(stream, reader)
        except Exception:
            return
        for operands, operator in content.operations:
            op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)
            if op in {"rg", "RG", "k", "K", "g", "G", "cs", "CS", "sc", "SC", "scn", "SCN"}:
                operator_counts[op] += 1
            if op in {"cs", "CS"} and operands:
                named_spaces[pdf_name(operands[0])] += 1

        resources = dereference(resources or {})
        for _, reference in dereference(resources.get("/ExtGState", {})).items():
            state = dereference(reference)
            key = indirect_id(state)
            if key not in extgstates:
                extgstates[key] = {
                    "ca": float(state.get("/ca", 1)),
                    "CA": float(state.get("/CA", 1)),
                    "has_soft_mask": state.get("/SMask") not in (None, "/None"),
                }

        for _, reference in dereference(resources.get("/XObject", {})).items():
            xobject = dereference(reference)
            key = indirect_id(xobject)
            if xobject.get("/SMask") is not None:
                soft_mask_images.add(key)
            if xobject.get("/Subtype") == "/Form" and key not in visited_forms:
                visited_forms.add(key)
                scan_stream(xobject, xobject.get("/Resources") or resources)

    for page in reader.pages:
        scan_stream(page.get_contents(), page.get("/Resources"))

    translucent = [
        key
        for key, state in extgstates.items()
        if state["ca"] != 1 or state["CA"] != 1 or state["has_soft_mask"]
    ]
    return {
        "paint_operator_counts": dict(sorted(operator_counts.items())),
        "named_colour_space_counts": dict(sorted(named_spaces.items())),
        "unique_extgstate_count": len(extgstates),
        "translucent_extgstate_count": len(translucent),
        "soft_mask_image_count": len(soft_mask_images),
    }


def collect_icc_profiles(reader: PdfReader) -> list[dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    visited_forms: set[str] = set()

    def visit_resources(resources: Any) -> None:
        resources = dereference(resources or {})
        for _, reference in dereference(resources.get("/XObject", {})).items():
            xobject = dereference(reference)
            colour_space = dereference(xobject.get("/ColorSpace"))
            if isinstance(colour_space, list) and colour_space and colour_space[0] == "/ICCBased":
                profile_stream = dereference(colour_space[1])
                data = profile_stream.get_data()
                digest = hashlib.sha256(data).hexdigest()
                if digest not in profiles:
                    try:
                        profile = ImageCms.getOpenProfile(BytesIO(data))
                        description = ImageCms.getProfileDescription(profile).strip()
                    except Exception as exc:  # pragma: no cover - malformed third-party profile
                        description = f"unreadable: {exc}"
                    profiles[digest] = {
                        "sha256": digest,
                        "components": int(profile_stream.get("/N", 0)),
                        "description": description,
                        "bytes": len(data),
                    }
            key = indirect_id(xobject)
            if xobject.get("/Subtype") == "/Form" and key not in visited_forms:
                visited_forms.add(key)
                visit_resources(xobject.get("/Resources"))

    for page in reader.pages:
        visit_resources(page.get("/Resources"))
    return sorted(profiles.values(), key=lambda item: item["description"])


def page_box(page: Any, name: str) -> list[float] | None:
    raw = page.get(name)
    if raw is None:
        return None
    return [mm(float(value)) for value in dereference(raw)]


def audit(pdf_path: Path, safe_inner_mm: float) -> dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
    spread_width_mm = mm(float(reader.pages[0].mediabox.width))
    fold_mm = spread_width_mm / 2
    fold_low_mm = fold_mm - safe_inner_mm
    fold_high_mm = fold_mm + safe_inner_mm
    fold_low_pt = fold_low_mm * PT_PER_MM
    fold_high_pt = fold_high_mm * PT_PER_MM

    image_instances: list[dict[str, Any]] = []
    fold_words: list[dict[str, Any]] = []
    fold_images: list[dict[str, Any]] = []
    image_colour_spaces: Counter[str] = Counter()

    # pdfminer emits noisy FontBBox warnings for Chromium Type3 fonts; these are
    # audited directly below, so keep the read-only image/word pass quiet.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for occurrence, image in enumerate(page.images, start=1):
                pixel_width, pixel_height = image.get("srcsize") or (0, 0)
                placed_width_pt = abs(float(image.get("width", 0)))
                placed_height_pt = abs(float(image.get("height", 0)))
                ppi_x = pixel_width * 72 / placed_width_pt if placed_width_pt else 0
                ppi_y = pixel_height * 72 / placed_height_pt if placed_height_pt else 0
                colour_space = serialise_colour_space(image.get("colorspace"))
                image_colour_spaces[colour_space] += 1
                entry = {
                    "page": page_number,
                    "occurrence": occurrence,
                    "xobject": str(image.get("name", "")),
                    "pixels": [int(pixel_width), int(pixel_height)],
                    "placed_bbox_mm": [
                        mm(image["x0"]),
                        mm(image["top"]),
                        mm(image["x1"]),
                        mm(image["bottom"]),
                    ],
                    "placed_size_mm": [mm(placed_width_pt), mm(placed_height_pt)],
                    "effective_ppi_x": round(ppi_x, 1),
                    "effective_ppi_y": round(ppi_y, 1),
                    "effective_ppi_min": round(min(ppi_x, ppi_y), 1),
                    "colour_space": colour_space,
                    "has_soft_mask": bool(image.get("stream") and dereference(image["stream"]).get("/SMask")),
                }
                if entry["effective_ppi_min"] < 180:
                    entry["quality_class"] = "critical_below_180"
                elif entry["effective_ppi_min"] < 250:
                    entry["quality_class"] = "review_below_250"
                else:
                    entry["quality_class"] = "pass_250"
                image_instances.append(entry)
                if image["x1"] > fold_low_pt and image["x0"] < fold_high_pt:
                    fold_images.append(
                        {
                            "page": page_number,
                            "xobject": entry["xobject"],
                            "x0_mm": entry["placed_bbox_mm"][0],
                            "x1_mm": entry["placed_bbox_mm"][2],
                        }
                    )

            for word in page.extract_words(keep_blank_chars=False):
                if word["x1"] > fold_low_pt and word["x0"] < fold_high_pt:
                    fold_words.append(
                        {
                            "page": page_number,
                            "text": word["text"],
                            "x0_mm": mm(word["x0"]),
                            "x1_mm": mm(word["x1"]),
                            "top_mm": mm(word["top"]),
                            "bottom_mm": mm(word["bottom"]),
                        }
                    )

    fonts = collect_fonts(reader)
    root = dereference(reader.trailer["/Root"])
    info = dereference(reader.trailer.get("/Info", {}))
    pdfx_version = info.get("/GTS_PDFXVersion") or metadata.get("/GTS_PDFXVersion")
    output_intents = dereference(root.get("/OutputIntents", []))
    page_boxes = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_boxes.append(
            {
                "page": page_number,
                "media_box_mm": [mm(float(value)) for value in page.mediabox],
                "crop_box_explicit_mm": page_box(page, "/CropBox"),
                "trim_box_explicit_mm": page_box(page, "/TrimBox"),
                "bleed_box_explicit_mm": page_box(page, "/BleedBox"),
                "art_box_explicit_mm": page_box(page, "/ArtBox"),
                "rotation": int(page.get("/Rotate", 0)),
            }
        )

    type_counts = Counter(font["subtype"] for font in fonts)
    program_counts = Counter(font["program_status"] for font in fonts)
    image_quality_counts = Counter(image["quality_class"] for image in image_instances)
    source_digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return {
        "source_pdf": str(pdf_path.as_posix()),
        "source_sha256": source_digest,
        "source_size_bytes": pdf_path.stat().st_size,
        "pdf_version": reader.pdf_header,
        "encrypted": reader.is_encrypted,
        "metadata": metadata,
        "page_count_spreads": len(reader.pages),
        "page_boxes": page_boxes,
        "target_geometry_mm": {
            "trim_page": [260, 200],
            "bleed": 3,
            "media_and_bleed_page": [266, 206],
            "preview_spread": [526, 206],
            "fold_x_on_spread": fold_mm,
            "inner_safe_distance_from_trim_fold": safe_inner_mm,
            "fold_hazard_band_on_spread": [fold_low_mm, fold_high_mm],
        },
        "images": {
            "summary": {
                "placement_count": len(image_instances),
                "quality_counts": dict(sorted(image_quality_counts.items())),
                "minimum_effective_ppi": min(
                    (image["effective_ppi_min"] for image in image_instances), default=None
                ),
                "colour_space_counts": dict(sorted(image_colour_spaces.items())),
            },
            "placements": image_instances,
        },
        "fonts": {
            "summary": {
                "unique_resource_count": len(fonts),
                "subtype_counts": dict(sorted(type_counts.items())),
                "program_status_counts": dict(sorted(program_counts.items())),
                "type3_present": any(font["subtype"] == "Type3" for font in fonts),
            },
            "resources": fonts,
        },
        "colour_and_transparency": {
            **collect_colour_and_transparency(reader),
            "icc_profiles": collect_icc_profiles(reader),
            "output_intent_count": len(output_intents),
        },
        "safe_zone": {
            "fold_hazard_words": fold_words,
            "fold_hazard_images": fold_images,
        },
        "pdfx": {
            "declared_pdfx_version": str(pdfx_version) if pdfx_version else None,
            "has_output_intent": bool(output_intents),
            "current_file_is_pdfx4": bool(pdfx_version and "PDF/X-4" in str(pdfx_version)),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="PDF to inspect without modifying it")
    parser.add_argument("--json", type=Path, help="optional path for detailed JSON results")
    parser.add_argument("--safe-inner-mm", type=float, default=22.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    result = audit(args.pdf, args.safe_inner_mm)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(encoded, encoding="utf-8")
        print(args.json)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
