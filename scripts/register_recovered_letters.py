#!/usr/bin/env python3
"""Register two handwriting scans that were misclassified as archive photos.

The migration is deliberately narrow and idempotent. It never deletes or
rewrites the extracted masters: the native files are copied into each family's
``letters`` directory and the former archive copies remain available for
provenance. Run without ``--apply`` for a dry-run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


RECOVERED = (
    {
        "hero_id": "hero-058",
        "reference_order": 56,
        "asset_id": "hero-058_p197_image882",
        "archive_master": "assets/families/hero-058/archive-photos/hero-058_p197_image882.jpg",
        "letter_master": "assets/families/hero-058/letters/hero-058_p197_image882.jpg",
        "print_file": "assets/production-ready/archive/hero-058/hero-058_p197_image882_upscaled_2x.jpg",
        "author": "ЮЛИАННА",
        "source_text": """Мой папа — герой! Он смелый и отважный,
Он защитник нашей Родины. Спасает наше
мирное небо, он отдал свою жизнь.
Я горжусь своим папой!

04.06.2024 г. Юлианна.
""",
        "print_text": """Мой папа — герой! Он смелый и отважный,
он защитник нашей Родины. Спасает наше мирное небо, он отдал свою жизнь.

Я горжусь своим папой!

04.06.2024 г. Юлианна.
""",
    },
    {
        "hero_id": "hero-069",
        "reference_order": 67,
        "asset_id": "hero-069_p233_image1020",
        "archive_master": "assets/families/hero-069/archive-photos/hero-069_p233_image1020.jpg",
        "letter_master": "assets/families/hero-069/letters/hero-069_p233_image1020.jpg",
        "print_file": "assets/production-ready/archive/hero-069/hero-069_p233_image1020_upscaled_2x.jpg",
        "author": "ДМИТРИЙ",
        "source_text": """Мой папа Герой.
Моего папу зовут Башкиров Антон Александро-
вич. Он военный, ветеран боевых действий. Дважды
кавалер Ордена Мужества. Он участвовал в бое-
вых действиях в Чеченской Республике и Сирии.
В 2022 году ушел на СВО среди первых. Чтобы
спасти своих товарищей он вызвал огонь
на себя — так рассказывали его боевые товарищи.
В мирное время, между его командировка-
ми, мы любили гулять, рыбачить, проводить
время на природе. Он самый лучший, самый
добрый, мне его очень нехватает.

Дмитрий 14 лет
""",
        "print_text": """Мой папа — Герой.

Моего папу зовут Башкиров Антон Александрович. Он военный, ветеран боевых действий. Дважды кавалер Ордена Мужества. Он участвовал в боевых действиях в Чеченской Республике и Сирии.

В 2022 году ушел на СВО среди первых. Чтобы спасти своих товарищей, он вызвал огонь на себя — так рассказывали его боевые товарищи.

В мирное время, между его командировками, мы любили гулять, рыбачить, проводить время на природе. Он самый лучший, самый добрый, мне его очень не хватает.

Дмитрий, 14 лет
""",
    },
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_append(items: list[Any], value: Any, key: str | None = None) -> None:
    marker = value.get(key) if key and isinstance(value, dict) else value
    for item in items:
        current = item.get(key) if key and isinstance(item, dict) else item
        if current == marker:
            return
    items.append(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print("Mode:", "apply" if args.apply else "dry-run")

    production: dict[str, dict[str, Any]] = {}
    family_assets: dict[str, dict[str, Any]] = {}
    processing_path = ROOT / "assets/families/family-processing-plan.json"
    classification_path = ROOT / "assets/families/family-template-classification.json"
    index_path = ROOT / "assets/families/letters-transcriptions-index.json"
    deferred_path = ROOT / "content/manifests/draft-deferred-families.json"
    processing = read_json(processing_path)
    classification = read_json(classification_path)
    index = read_json(index_path)
    deferred = read_json(deferred_path)

    for item in RECOVERED:
        hero_id = item["hero_id"]
        asset_id = item["asset_id"]
        archive_master = ROOT / item["archive_master"]
        letter_master = ROOT / item["letter_master"]
        if not archive_master.is_file():
            raise FileNotFoundError(archive_master)
        if args.apply:
            letter_master.parent.mkdir(parents=True, exist_ok=True)
            if not letter_master.exists():
                shutil.copy2(archive_master, letter_master)
        if letter_master.exists() and sha256(letter_master) != sha256(archive_master):
            raise RuntimeError(f"Copied master differs: {letter_master}")

        transcription_dir = letter_master.parent.parent / "transcriptions"
        source_txt = transcription_dir / f"{asset_id}_source.txt"
        print_txt = transcription_dir / f"{asset_id}_print.txt"
        transcription_json = transcription_dir / f"{asset_id}_transcription.json"
        transcription_rel = transcription_json.relative_to(ROOT).as_posix()
        source_rel = source_txt.relative_to(ROOT).as_posix()
        print_rel = print_txt.relative_to(ROOT).as_posix()

        if args.apply:
            transcription_dir.mkdir(parents=True, exist_ok=True)
            source_txt.write_text(item["source_text"], encoding="utf-8")
            print_txt.write_text(item["print_text"], encoding="utf-8")
            write_json(
                transcription_json,
                {
                    "schema_version": 1,
                    "hero_id": hero_id,
                    "letter_id": asset_id,
                    "letter_file": item["letter_master"],
                    "source_transcription_file": source_rel,
                    "print_transcription_file": print_rel,
                    "authors": [item["author"]],
                    "authors_status": "CONFIRMED_FROM_VISIBLE_SIGNATURE",
                    "editorial_changes": [
                        "В читательской версии соединены переносы слов и нормализована базовая пунктуация.",
                        "Факты и содержание письма не дополнялись.",
                    ],
                    "doubts": [],
                    "status": "REVIEW_REQUIRED",
                    "approved_for_print": False,
                },
            )

        prod_path = ROOT / f"content/production/families/{hero_id}.json"
        prod = read_json(prod_path)
        prod["archive_photos"] = [p for p in prod["archive_photos"] if p != item["print_file"]]
        unique_append(prod["letters"], item["letter_master"])
        unique_append(prod["transcriptions"], transcription_rel)
        prod["review_flags"] = [
            flag for flag in prod["review_flags"] if flag != "REVIEW_REQUIRED_PHYSICAL_LETTER_MISSING"
        ]
        unique_append(prod["review_flags"], "REVIEW_REQUIRED_TRANSCRIPTION")
        production[hero_id] = prod

        plan = next(row for row in processing["families"] if row["hero_id"] == hero_id)
        plan["archive_assets"] = [row for row in plan["archive_assets"] if row["asset_id"] != asset_id]
        unique_append(
            plan["letters"],
            {
                "asset_id": asset_id,
                "file": item["letter_master"],
                "physical_scan": True,
                "is_processed_derivative": False,
                "notes": "Рукопись повторно распознана среди архивных изображений; master скопирован без изменения.",
            },
            "asset_id",
        )
        unique_append(
            plan["transcriptions"],
            {"asset_id": f"{asset_id}_transcription", "file": transcription_rel, "status": "REVIEW_REQUIRED"},
            "asset_id",
        )

        cls = next(row for row in classification["families"] if row["hero_id"] == hero_id)
        cls["counts"]["archive_photos"] = len(prod["archive_photos"])
        cls["counts"]["significant_visuals"] = (
            (1 if prod.get("flagship") else 0)
            + len(prod["archive_photos"])
            + len(prod.get("drawings", []))
        )
        cls["counts"]["physical_letters"] = 1
        cls["counts"]["transcription_files"] = 1
        cls["counts"]["transcription_characters"] = len(item["print_text"].strip())
        cls["status"] = "REVIEW_REQUIRED_TRANSCRIPTION"
        cls["confidence"] = "medium"
        cls["reason"] = (
            "Физическая рукопись найдена среди ранее ошибочно классифицированных архивных изображений; "
            "читательская расшифровка подготовлена и требует ручной сверки."
        )

        fa_path = ROOT / f"assets/families/{hero_id}/manifest/family-assets.json"
        fa = read_json(fa_path)
        asset = next(row for row in fa["assets"] if row["asset_id"] == asset_id)
        asset.update(
            {
                "category": "letters",
                "file": item["letter_master"],
                "asset_type": "letter_reference",
                "recommended_action": "archive_only",
                "notes": "Нативная рукопись повторно классифицирована по визуальной сверке; master скопирован без изменения.",
            }
        )
        if transcription_json.exists():
            unique_append(
                fa["assets"],
                {
                    "asset_id": f"{asset_id}_transcription",
                    "category": "transcriptions",
                    "file": transcription_rel,
                    "source_file": None,
                    "sha256": sha256(transcription_json),
                    "status": "REVIEW_REQUIRED",
                },
                "asset_id",
            )
        family_assets[hero_id] = fa

        unique_append(
            index["entries"],
            {
                "reference_order": item["reference_order"],
                "hero_id": hero_id,
                "letter_id": asset_id,
                "letter_file": item["letter_master"],
                "transcription_file": transcription_rel,
                "status": "REVIEW_REQUIRED",
                "notes": "Рукопись восстановлена из ошибочно классифицированного архивного изображения; ручная сверка обязательна.",
            },
            "letter_id",
        )
        print(hero_id, asset_id, "registered")

    index["entries"].sort(key=lambda row: (int(row["reference_order"]), row["letter_id"]))
    index["physical_letters"] = len(index["entries"])
    index["transcriptions_present"] = sum(bool(row.get("transcription_file")) for row in index["entries"])
    index["missing_transcriptions"] = index["physical_letters"] - index["transcriptions_present"]
    deferred["families"] = [
        row for row in deferred["families"] if row["hero_id"] not in {item["hero_id"] for item in RECOVERED}
    ]
    for order, row in enumerate(deferred["families"], start=1):
        row["draft_appendix_order"] = order

    if args.apply:
        for hero_id, value in production.items():
            write_json(ROOT / f"content/production/families/{hero_id}.json", value)
        for hero_id, value in family_assets.items():
            write_json(ROOT / f"assets/families/{hero_id}/manifest/family-assets.json", value)
        write_json(processing_path, processing)
        write_json(classification_path, classification)
        write_json(index_path, index)
        write_json(deferred_path, deferred)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
