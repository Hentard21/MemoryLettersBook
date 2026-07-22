#!/usr/bin/env python3
"""Register the owner-approved symbolic title image without faking identity.

The seven affected family manifests intentionally keep ``flagship`` set to
``null``.  The separate ``symbolic_flagship`` field is a draft-only layout
fallback and never becomes biographical evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FAMILY_IDS = (
    "hero-038",
    "hero-052",
    "hero-055",
    "hero-062",
    "hero-064",
    "hero-072",
    "hero-074",
)
SYMBOLIC_ASSET = (
    "assets/placeholders/generic-serviceman/"
    "generic-russian-serviceman-masked-nobg-v2.png"
)
PUBLIC_LABEL = "Символический образ"
LAYOUT = {
    "display_height_mm": 188,
    "bottom_mm": -1,
    "right_mm": 1,
    "blend_mode": "normal",
    "source_pose": "symbolic-masked-waist",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_family_manifests() -> None:
    family_dir = ROOT / "content/production/families"
    for hero_id in FAMILY_IDS:
        path = family_dir / f"{hero_id}.json"
        family = read_json(path)
        if family.get("flagship"):
            raise RuntimeError(
                f"{hero_id} now has a real flagship; refusing symbolic substitution"
            )
        flags = list(family.get("review_flags") or [])
        if "REVIEW_REQUIRED_FLAGSHIP_MISSING" not in flags:
            raise RuntimeError(
                f"{hero_id} is not explicitly flagged as missing a real flagship"
            )
        family["symbolic_flagship"] = SYMBOLIC_ASSET
        family["symbolic_flagship_public_label"] = PUBLIC_LABEL
        family["symbolic_flagship_status"] = "approved_for_draft_by_owner"
        family["symbolic_flagship_layout"] = dict(LAYOUT)
        write_json(path, family)


def update_processing_plan() -> None:
    path = ROOT / "assets/families/family-processing-plan.json"
    payload = read_json(path)
    families = payload.get("families")
    if not isinstance(families, list):
        raise RuntimeError("family-processing-plan.json has no families list")
    indexed = {str(item.get("hero_id")): item for item in families}
    missing = [hero_id for hero_id in FAMILY_IDS if hero_id not in indexed]
    if missing:
        raise RuntimeError(f"processing plan is missing: {', '.join(missing)}")
    for hero_id in FAMILY_IDS:
        item = indexed[hero_id]
        if item.get("flagship_asset"):
            raise RuntimeError(
                f"{hero_id} now has a real flagship in the processing plan"
            )
        item["symbolic_flagship_asset"] = SYMBOLIC_ASSET
        item["symbolic_flagship_status"] = "approved_for_draft_by_owner"
        item["symbolic_flagship_public_label"] = PUBLIC_LABEL
        item["symbolic_flagship_layout"] = dict(LAYOUT)
        item["symbolic_flagship_notes"] = (
            "Только для честно подписанного чернового титульника; "
            "не заменяет реальный портрет и не является фактом о герое."
        )
    write_json(path, payload)


def update_placeholder_manifest() -> None:
    path = ROOT / "assets/placeholders/generic-serviceman/manifest.json"
    payload = read_json(path)
    policy = payload.setdefault("usage_policy", {})
    policy["required_public_label"] = PUBLIC_LABEL
    policy["placement_status"] = "approved_for_draft_by_owner"
    policy["applied_families"] = list(FAMILY_IDS)
    policy["replacement_rule"] = (
        "Use only for the seven registered families while their canonical real "
        "flagship remains unavailable. Keep flagship null, retain the missing-"
        "flagship review flag, and show the required public label."
    )
    write_json(path, payload)


def validate() -> None:
    source = ROOT / SYMBOLIC_ASSET
    if not source.is_file():
        raise RuntimeError(f"symbolic asset is missing: {source}")
    for hero_id in FAMILY_IDS:
        family = read_json(ROOT / "content/production/families" / f"{hero_id}.json")
        assert family.get("flagship") is None
        assert family.get("symbolic_flagship") == SYMBOLIC_ASSET
        assert family.get("symbolic_flagship_public_label") == PUBLIC_LABEL
        assert "REVIEW_REQUIRED_FLAGSHIP_MISSING" in family.get("review_flags", [])


def main() -> None:
    update_family_manifests()
    update_processing_plan()
    update_placeholder_manifest()
    validate()
    print(f"Applied symbolic draft title image to {len(FAMILY_IDS)} families.")


if __name__ == "__main__":
    main()
