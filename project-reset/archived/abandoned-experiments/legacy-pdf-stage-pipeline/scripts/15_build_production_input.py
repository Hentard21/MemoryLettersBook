# -*- coding: utf-8 -*-
"""Build a non-destructive production archive from the reference PDF.

The script extracts native PDF image streams without recompression whenever
possible, copies already verified master assets for hero-001/002, renders
separate low-resolution page references, and prepares five balanced manual
work batches. It never modifies source/reference.pdf or master-from-pdf.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader


BASE = Path(__file__).resolve().parents[1]
SOURCE_PDF = BASE / "source" / "reference.pdf"
OUT = BASE / "assets" / "production-input"
BATCH_ROOT = BASE / "assets" / "production-batches"
HEROES_FILE = BASE / "content" / "entities" / "heroes.pdf-stage.json"
MANIFEST_FILE = BASE / "content" / "manifests" / "book-manifest.pdf-stage.json"
WEB_FILE = BASE / "content" / "manifests" / "web-assets.pdf-stage.json"
MIXED_FILE = BASE / "content" / "manifests" / "mixed-material-decomposition.pdf-stage.json"
UPSCALE_FILE = BASE / "content" / "manifests" / "upscale-manifest.json"

SUBDIRS = ("portraits", "groups", "drawings", "letters-reference", "page-reference")
CSV_FIELDS = [
    "hero_id", "hero_name", "asset_id", "asset_type", "source_file",
    "source_pdf_page", "recommended_action", "priority", "status", "notes",
]
TYPE_TO_DIR = {
    "portrait": "portraits",
    "group": "groups",
    "drawing": "drawings",
    "letter_reference": "letters-reference",
}
ACTION = {
    "portrait": "enhance_person",
    "group": "enhance_group",
    "drawing": "enhance_drawing",
    "letter_reference": "archive_only",
}
PRIORITY = {"portrait": "high", "group": "high", "drawing": "medium", "letter_reference": "low"}
KNOWN_GROUPS = {"hero-001_photo_02", "hero-002_photo_03"}
KNOWN_PORTRAITS = {
    "hero-001_photo_01", "hero-001_photo_03", "hero-002_photo_01",
    "hero-002_photo_02", "hero-002_photo_04",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def rel(path: Path) -> str:
    return path.relative_to(BASE).as_posix()


def ensure_structure(hero_ids):
    OUT.mkdir(parents=True, exist_ok=True)
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    for hero_id in hero_ids:
        for sub in SUBDIRS:
            (OUT / hero_id / sub).mkdir(parents=True, exist_ok=True)
    for i in range(1, 6):
        (BATCH_ROOT / f"batch-{i:02d}").mkdir(parents=True, exist_ok=True)


def face_signal(pil_image: Image.Image):
    rgb = np.asarray(pil_image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    rects, _, weights = cascade.detectMultiScale3(
        gray, scaleFactor=1.08, minNeighbors=4, minSize=(18, 18), outputRejectLevels=True
    )
    kept = [(r, float(w)) for r, w in zip(rects, weights) if float(w) >= 2.8]
    widths = sorted((int(r[2]) for r, _ in kept), reverse=True)
    if len(widths) >= 2 and widths[1] >= widths[0] * 0.65:
        return "group", len(widths), "несколько сопоставимых лиц"
    if widths:
        return "portrait", len(widths), "одно доминирующее лицо"
    return None, 0, "лица автоматически не обнаружены"


def image_metrics(pil_image: Image.Image):
    a = np.asarray(pil_image.convert("RGB").resize((256, 256))).astype(np.float32)
    colorfulness = float(np.mean(np.max(a, axis=2) - np.min(a, axis=2)))
    tonal_std = float(np.mean(np.std(a, axis=(0, 1))))
    w, h = pil_image.size
    return colorfulness, tonal_std, w / max(h, 1)


def mapped_entity_type(page_num, image_info, page_w, page_h, mixed_by_page):
    entities = mixed_by_page.get(page_num, [])
    if not entities:
        return None, None
    cx = ((float(image_info.get("x0", 0)) + float(image_info.get("x1", 0))) / 2) / page_w * 100
    cy = ((float(image_info.get("top", 0)) + float(image_info.get("bottom", 0))) / 2) / page_h * 100
    hits = []
    for e in entities:
        x0, y0, x1, y1 = e["bbox_pct_approx"]
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            hits.append(e)
    if len(hits) == 1:
        return hits[0]["entity_type"].lower(), hits[0]
    return None, None


def classify_asset(page_rec, web_types, image_info, pil_image, mixed_by_page):
    page_num = page_rec["page"]
    visual = (page_rec.get("visual_classification") or {})
    visual_type = visual.get("page_type") or ""
    features = set(visual.get("features") or [])
    mapped, entity = mapped_entity_type(
        page_num, image_info, float(image_info["page_width"]), float(image_info["page_height"]), mixed_by_page
    )
    photo_kind, faces, face_note = face_signal(pil_image)
    colorfulness, tonal_std, aspect = image_metrics(pil_image)
    candidates = set(web_types.get(page_num, []))

    if mapped == "letter":
        return "letter_reference", True, f"смешанная страница; область письма; {face_note}"
    if mapped == "drawing":
        return "drawing", bool(entity and entity.get("needs_manual_review")), "разметка смешанной страницы: рисунок"
    if mapped == "photo":
        kind = photo_kind or ("group" if "has_family_photo" in features else "portrait")
        review = photo_kind is None or bool(entity and entity.get("needs_manual_review"))
        return kind, review, f"разметка смешанной страницы; {face_note}"

    if visual_type in {"handwritten_letter", "quotation", "document_scan"} or candidates == {"letter_scan"}:
        return "letter_reference", False, "страница классифицирована как рукопись"
    if visual_type == "child_drawing" or candidates == {"drawing"}:
        return "drawing", False, "страница классифицирована как детский рисунок"

    if photo_kind and ("photo" in candidates or visual_type in {"photo_collage", "portrait", "mixed_material"}):
        return photo_kind, False, face_note

    if "letter_scan" in candidates and "drawing" in candidates and "photo" not in candidates:
        if aspect > 1.05:
            return "letter_reference", True, "эвристика смешанной страницы: горизонтальный документ"
        return "drawing", True, "эвристика смешанной страницы: вертикальный лист"

    if "letter_scan" in candidates and "photo" in candidates:
        if aspect > 1.08 and tonal_std < 65:
            return "letter_reference", True, "эвристика: широкий документ без уверенного лица"
        kind = "group" if "has_family_photo" in features else "portrait"
        return kind, True, f"фото/письмо требуют визуальной проверки; {face_note}"

    if "drawing" in candidates and "photo" in candidates:
        if tonal_std < 55 and colorfulness > 16:
            return "drawing", True, "эвристика: рисунок на смешанной странице"
        kind = "group" if "has_family_photo" in features else "portrait"
        return kind, True, f"рисунок/фото требуют визуальной проверки; {face_note}"

    if candidates == {"photo"} or visual_type in {"photo_collage", "portrait"}:
        if photo_kind:
            return photo_kind, False, face_note
        kind = "group" if "has_family_photo" in features else "portrait"
        return kind, True, f"фото без уверенно обнаруженного лица; {face_note}"

    # Conservative fallback: preserve the asset and force a human decision.
    if aspect > 1.12 and tonal_std < 62:
        return "letter_reference", True, "неуверенная автоматическая классификация"
    return "portrait", True, "тип изображения требует ручной проверки"


def stream_bytes_and_ext(image_info, pypdf_images):
    stream = image_info["stream"]
    filters = str(stream.attrs.get("Filter", ""))
    raw = stream.get_rawdata()
    if "DCTDecode" in filters:
        return raw, ".jpg"
    if "JPXDecode" in filters:
        return raw, ".jp2"
    stem = str(image_info.get("name", "")).lower()
    for pimg in pypdf_images:
        if Path(pimg.name).stem.lower() == stem:
            return pimg.data, Path(pimg.name).suffix.lower() or ".png"
    raise RuntimeError(f"Cannot extract image {image_info.get('name')}")


def build_row(hero_id, hero_name, asset_id, asset_type, out_file, page_num, notes, review=False):
    note = notes
    if review:
        note += "; REVIEW_REQUIRED: проверить тип и пригодность перед раздачей"
    return {
        "hero_id": hero_id,
        "hero_name": hero_name,
        "asset_id": asset_id,
        "asset_type": asset_type,
        "source_file": rel(out_file),
        "source_pdf_page": page_num,
        "recommended_action": ACTION[asset_type],
        "priority": PRIORITY[asset_type] if not review else "medium",
        "status": "pending",
        "notes": note,
    }


def copy_verified_masters(hero, upscale_assets, rows, review_items):
    hero_id = hero["id"]
    hero_name = hero.get("hero_first_name") or hero_id
    for a in upscale_assets:
        if a["entity_id"] != hero_id or a["asset_type"] not in {"photo", "drawing", "letter"}:
            continue
        aid = a["asset_id"]
        if a["asset_type"] == "drawing":
            atype = "drawing"
        elif a["asset_type"] == "letter":
            atype = "letter_reference"
        elif aid in KNOWN_GROUPS:
            atype = "group"
        else:
            atype = "portrait"
        page_match = re.search(r"p(\d{3})_", a.get("web_prototype_file") or "")
        page_num = int(page_match.group(1)) if page_match else None
        src = BASE / a["source_file"]
        dst = OUT / hero_id / TYPE_TO_DIR[atype] / src.name
        shutil.copy2(src, dst)
        notes = "Проверенный master_from_pdf; скопирован без изменения"
        if a.get("publish_blocked"):
            notes += "; принадлежность материала заблокирована редакционной проверкой"
            review_items.append(f"- {hero_id}, {aid}: принадлежность материала спорна; не передавать как подтверждённый материал героя.")
        rows.append(build_row(hero_id, hero_name, aid, atype, dst, page_num, notes, bool(a.get("publish_blocked"))))


def render_page_reference(pdf_doc, hero_id, page_num):
    dst = OUT / hero_id / "page-reference" / f"page_{page_num:03d}_reference.jpg"
    page = pdf_doc[page_num - 1]
    img = page.render(scale=1.45).to_pil().convert("RGB")
    img.save(dst, format="JPEG", quality=84, optimize=True)


def prepare_batches(task_rows):
    weight = {"portrait": 2.0, "group": 3.0, "drawing": 1.5}
    bins = [{"rows": [], "load": 0.0} for _ in range(5)]
    for row in sorted(task_rows, key=lambda r: (-weight[r["asset_type"]], r["hero_id"], r["asset_id"])):
        target = min(bins, key=lambda b: (b["load"], len(b["rows"])))
        target["rows"].append(row)
        target["load"] += weight[row["asset_type"]]

    for idx, batch in enumerate(bins, start=1):
        batch_dir = BATCH_ROOT / f"batch-{idx:02d}"
        batch_rows = []
        for row in batch["rows"]:
            src = BASE / row["source_file"]
            dst = batch_dir / row["hero_id"] / TYPE_TO_DIR[row["asset_type"]] / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied = dict(row)
            copied["source_file"] = dst.relative_to(batch_dir).as_posix()
            batch_rows.append(copied)
        write_json(batch_dir / "jobs.json", batch_rows)
        write_csv(batch_dir / "jobs.csv", batch_rows)
        counts = Counter(r["asset_type"] for r in batch_rows)
        file_lines = "\n".join(f"- `{r['source_file']}` — {r['recommended_action']}" for r in batch_rows)
        readme = f"""# Batch {idx:02d}

В батче: {len(batch_rows)} задач — portraits: {counts['portrait']}, groups: {counts['group']}, drawings: {counts['drawing']}.

## Что делать

- Портреты: сохранить лицо, одежду, форму, экипировку, награды и предметы; подготовить прозрачный либо белый фон.
- Группы: сохранить всех людей и их взаимное расположение.
- Рисунки: повысить качество, сохранив детский штрих; очистить фон.

## Что не трогать

- Не менять лица, одежду, форму, награды и предметы.
- Не добавлять и не удалять людей.
- Не превращать рисунок в гладкую цифровую иллюстрацию.
- Письма не генерируются и в рабочие батчи не включены.

## Файлы

{file_lines}
"""
        (batch_dir / "README.md").write_text(readme, encoding="utf-8")
    return bins


def main():
    heroes_data = load_json(HEROES_FILE)["heroes"]
    heroes = {h["id"]: h for h in heroes_data}
    manifest = load_json(MANIFEST_FILE)
    pages = {p["page"]: p for p in manifest["pages"]}
    web = load_json(WEB_FILE)
    mixed = load_json(MIXED_FILE)
    upscale = load_json(UPSCALE_FILE)["assets"]

    web_types = defaultdict(list)
    for hero in web["heroes"]:
        for a in hero["assets"]:
            if a["type"] != "title_slide":
                web_types[int(a["source_page"])].append(a["type"])
    mixed_by_page = defaultdict(list)
    for e in mixed["entities"]:
        mixed_by_page[int(e["source_page"])].append(e)

    ensure_structure(heroes)
    rows = []
    review_items = []
    low_source_heroes = []
    for page_num, entities in sorted(mixed_by_page.items()):
        entity_types = sorted({e["entity_type"] for e in entities if e["entity_type"] in {"Photo", "Drawing", "Letter"}})
        if len(entity_types) > 1 and int(pages[page_num].get("image_count") or 0) <= 1:
            review_items.append(
                f"- {pages[page_num].get('hero_id')}, стр. {page_num}: один физический PDF-ассет смешивает "
                f"{', '.join(entity_types)}; не разделять и не отправлять в генерацию до ручного решения."
            )
        elif any(e.get("needs_manual_review") for e in entities):
            reasons = "; ".join(e.get("note") or e.get("review_reason") or "сомнительное качество/атрибуция" for e in entities if e.get("needs_manual_review"))
            review_items.append(f"- {pages[page_num].get('hero_id')}, стр. {page_num}: {reasons}.")
    for hero_id in ("hero-001", "hero-002"):
        copy_verified_masters(heroes[hero_id], upscale, rows, review_items)

    reader = PdfReader(str(SOURCE_PDF))
    pdf_doc = pdfium.PdfDocument(str(SOURCE_PDF))
    seen_hashes = defaultdict(set)
    for r in rows:
        seen_hashes[r["hero_id"]].add(hashlib.sha256((BASE / r["source_file"]).read_bytes()).hexdigest())

    with pdfplumber.open(SOURCE_PDF) as plumber:
        for hero_id, hero in heroes.items():
            hero_name = hero.get("hero_first_name") or hero_id
            for page_num in hero["pages"]:
                render_page_reference(pdf_doc, hero_id, int(page_num))
            if hero_id in {"hero-001", "hero-002"}:
                continue

            extracted_for_hero = 0
            for page_num in hero["pages"]:
                page_rec = pages[int(page_num)]
                if page_rec.get("page_type") == "hero_title":
                    continue
                ppage = plumber.pages[int(page_num) - 1]
                pypdf_images = list(reader.pages[int(page_num) - 1].images)
                for image_info in ppage.images:
                    image_info = dict(image_info)
                    image_info["page_width"] = float(ppage.width)
                    image_info["page_height"] = float(ppage.height)
                    try:
                        raw, ext = stream_bytes_and_ext(image_info, pypdf_images)
                        digest = hashlib.sha256(raw).hexdigest()
                        if digest in seen_hashes[hero_id]:
                            continue
                        seen_hashes[hero_id].add(digest)
                        pil_image = Image.open(io.BytesIO(raw)).convert("RGB")
                    except Exception as exc:
                        review_items.append(f"- {hero_id}, стр. {page_num}, {image_info.get('name')}: не удалось нативно извлечь ({exc}).")
                        continue

                    atype, review, classify_note = classify_asset(
                        page_rec, web_types, image_info, pil_image, mixed_by_page
                    )
                    image_name = str(image_info.get("name") or f"img{extracted_for_hero + 1}")
                    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", image_name).strip("-").lower()
                    asset_id = f"{hero_id}_p{int(page_num):03d}_{stem}"
                    dst = OUT / hero_id / TYPE_TO_DIR[atype] / f"{asset_id}{ext}"
                    dst.write_bytes(raw)
                    notes = f"Нативный поток из source/reference.pdf без повторного сжатия; {classify_note}"
                    rows.append(build_row(hero_id, hero_name, asset_id, atype, dst, int(page_num), notes, review))
                    extracted_for_hero += 1
                    if review:
                        review_items.append(f"- {hero_id} ({hero_name}), стр. {page_num}, `{dst.name}`: {classify_note}.")
            if extracted_for_hero <= 1:
                low_source_heroes.append((hero_id, hero_name, extracted_for_hero))

    pdf_doc.close()
    rows.sort(key=lambda r: (r["hero_id"], r["source_pdf_page"] or 0, r["asset_type"], r["asset_id"]))
    write_json(OUT / "jobs.json", rows)
    write_csv(OUT / "jobs.csv", rows)

    instructions = """# Короткая памятка ручной обработки

## Портреты

- Сохранить лицо и узнаваемость.
- Не менять одежду.
- Сохранить предметы в руках, форму, экипировку, награды и нашивки.
- Достраивать только обрезанные части тела и одежды.
- Фон — прозрачный, если возможно, иначе белый.

## Группы

- Сохранить всех людей; никого не удалять.
- Не менять взаимное расположение без необходимости.
- Фон — прозрачный или белый.

## Рисунки

- Улучшить качество и очистить фон.
- Сохранить детский стиль и живой штрих.
- Не превращать в гладкую цифровую иллюстрацию.

## Письма

- Не обрабатывать генеративно.
- Хранить только как референс и архив для расшифровки и дизайна.
"""
    (OUT / "WORK_INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")

    review_header = """# Материалы, требующие ручной проверки

Автоматическая раскладка не распознаёт личности и использует только структуру PDF, существующую редакционную разметку и число визуально сопоставимых лиц. До раздачи людям проверьте перечисленные ниже случаи.

## Мало исходников

"""
    low_lines = "\n".join(f"- {hid} ({name}): извлечено рабочих ассетов — {count}." for hid, name, count in low_source_heroes) or "- Не выявлено."
    mixed_lines = "\n".join(review_items) or "- Не выявлено."
    review_text = review_header + low_lines + "\n\n## Неоднозначная категория, качество или принадлежность\n\n" + mixed_lines + "\n"
    (OUT / "review-needed.md").write_text(review_text, encoding="utf-8")

    task_rows = [r for r in rows if r["asset_type"] != "letter_reference"]
    bins = prepare_batches(task_rows)

    counts = Counter(r["asset_type"] for r in rows)
    summary = {
        "heroes": len(heroes),
        "assets": len(rows),
        "counts": dict(counts),
        "manual_tasks": len(task_rows),
        "review_items": len(review_items) + len(low_source_heroes),
        "batch_loads": [round(b["load"], 1) for b in bins],
    }
    write_json(OUT / "build-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
