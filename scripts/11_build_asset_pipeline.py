# -*- coding: utf-8 -*-
"""
Этап 11: конвейер ассетов под Topaz Gigapixel (PPTX утерян — PDF единственный источник).

Строит:
  assets/master-from-pdf/heroes/hero-XXX/{photos,letters,drawings,mixed,title}
  assets/derived-upscaled/... (зеркало, пустое — заполняет владелец)
  assets/review/{approved,needs-redo,rejected}
  assets/master-from-pdf/common/
  assets/test-batch-gigapixel/
Копирует нативные мастера под канонические имена hero-XXX_<type>_NN_master.png.
Генерирует content/manifests/upscale-manifest.json (+ .csv).
Дописывает в content/prototypes/*/content.json поля резолюции ассетов.

Идентичность каждого нативного потока сверена визуально по контакт-листам
workspace/reports/native-hero-00X.jpg (см. mapping ниже). Лица по фото не
распознавались — фото помечены только по типу «на фото есть человек».
"""
import csv
import json
import os
import shutil

import pypdfium2 as pdfium

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- ПРОВЕРЕННЫЙ МЭППИНГ: (asset_id, type, group, priority, scale, native_png, web_file, flags) ---
# native_png — путь внутри content/prototypes/<hero>/
# web_file   — существующий файл в design/prototypes/web/assets/img/<hero>/ (для резолвера)
G_FACE, G_DOC, G_LET, G_DRAW, G_ME = ("photo_face","photo_documentary","letter_handwriting","drawing_child_art","map_or_emblem")

ASSETS = {
  "hero-001": [
    ("hero-001_photo_01","photo",G_FACE,"high","4x_or_auto","assets/native/p013_Image106.png","p013_img01.jpg",{"face_sensitive":True}),
    ("hero-001_photo_02","photo",G_FACE,"high","4x_or_auto","assets/native/p013_Image107.png","p013_img03.jpg",{"face_sensitive":True,"note":"Двое в форме на мероприятии"}),
    ("hero-001_photo_03","photo",G_FACE,"high","4x_or_auto","assets/native/p013_Image108.png","p013_img04.jpg",{"face_sensitive":True,"note":"Подросток держит портрет и награду"}),
    ("hero-001_drawing_01","drawing",G_DRAW,"medium","4x_or_auto","assets/native/p013_Image109.png","p013_img02.jpg",{"drawing_sensitive":True}),
    ("hero-001_letter_01","letter",G_LET,"high","4x_or_auto","assets/native/p014_Image112.png","p014_img01.jpg",{"handwriting_sensitive":True}),
    ("hero-001_title_award","title",G_ME,"low","skip_prefer_vector","assets/native/p012_Image96.png",None,{"note":"Изображение награды — атрибуция FACT_LOCKED; предпочтительно вектор, не апскейлить агрессивно"}),
    ("hero-001_title_map","title",G_ME,"low","skip_prefer_vector","assets/native/p012_Image100.png",None,{"note":"Карта России с меткой — будет пересоздана вектором (map-and-emblems-plan)"}),
  ],
  "hero-002": [
    ("hero-002_photo_01","photo",G_FACE,"high","4x_or_auto","assets/native/p016_Image123.png","p016_img01.jpg",{"face_sensitive":True,"note":"Девочка на фоне флага с рисунком"}),
    ("hero-002_photo_02","photo",G_FACE,"high","4x_or_auto","assets/native/p016_Image121.png","p016_img02.jpg",{"face_sensitive":True,"note":"Мальчик держит рисунок-сердце"}),
    ("hero-002_photo_03","photo",G_FACE,"high","4x_or_auto","assets/native/p016_Image125.png","p016_img03.jpg",{"face_sensitive":True,"note":"Двое детей на фоне флага с портретом и наградами"}),
    ("hero-002_photo_04","photo",G_FACE,"high","4x_or_auto","assets/native/p017_Image129.png","p017_img01.jpg",{"face_sensitive":True,"note":"Военнослужащий в лесу (герой)"}),
    ("hero-002_drawing_01","drawing",G_DRAW,"medium","4x_or_auto","assets/native/p017_Image131.png","p017_img03.jpg",{"drawing_sensitive":True}),
    ("hero-002_letter_01","letter",G_LET,"high","4x_or_auto","assets/native/p017_Image132.png","p017_img05.jpg",{"handwriting_sensitive":True,"publish_blocked":True,"note":"eq-009: письмо про отца «Ильшат», подпись «Максим» — не публиковать в hero-002 до решения. Апскейлить можно (читаемость), но принадлежность спорна."}),
    ("hero-002_letter_02","letter",G_LET,"high","4x_or_auto","assets/native/p018_Image136.png","p018_img01.jpg",{"handwriting_sensitive":True}),
    ("hero-002_letter_03","letter",G_LET,"high","4x_or_auto","assets/native/p018_Image138.png","p018_img02.jpg",{"handwriting_sensitive":True}),
    ("hero-002_title_award","title",G_ME,"low","skip_prefer_vector","assets/native/p015_Image96.png",None,{"note":"Награда — FACT_LOCKED; вектор"}),
    ("hero-002_title_map","title",G_ME,"low","skip_prefer_vector","assets/native/p015_Image115.png",None,{"note":"Карта России с меткой — вектор"}),
    ("hero-002_title_map2","title",G_ME,"low","skip_prefer_vector","assets/native/p015_Image118.png",None,{"note":"Вторая карта/эмблема — вектор"}),
  ],
}

TYPE_DIR = {"photo":"photos","letter":"letters","drawing":"drawings","title":"title","mixed":"mixed"}

def canon_name(asset_id, kind):
    return f"{asset_id}_master.png"

# --- структура папок ---
for hid in ASSETS:
    for sub in ("photos","letters","drawings","mixed","title"):
        os.makedirs(f"{BASE}/assets/master-from-pdf/heroes/{hid}/{sub}", exist_ok=True)
        os.makedirs(f"{BASE}/assets/derived-upscaled/heroes/{hid}/{sub}", exist_ok=True)
os.makedirs(f"{BASE}/assets/master-from-pdf/common", exist_ok=True)
os.makedirs(f"{BASE}/assets/derived-upscaled/common", exist_ok=True)
for r in ("approved","needs-redo","rejected"):
    os.makedirs(f"{BASE}/assets/review/{r}", exist_ok=True)
os.makedirs(f"{BASE}/assets/test-batch-gigapixel", exist_ok=True)

from PIL import Image
manifest_rows = []
for hid, items in ASSETS.items():
    for (aid, typ, group, prio, scale, native, webfile, flags) in items:
        src = f"{BASE}/content/prototypes/{hid}/{native}"
        im = Image.open(src)
        w, h = im.size
        subdir = TYPE_DIR[typ]
        master_rel = f"assets/master-from-pdf/heroes/{hid}/{subdir}/{canon_name(aid,typ)}"
        im.save(f"{BASE}/{master_rel}")
        derived_rel = f"assets/derived-upscaled/heroes/{hid}/{subdir}/{aid}_upscaled.png"
        row = {
            "entity_id": hid,
            "asset_id": aid,
            "asset_type": typ,
            "source_file": master_rel,
            "source_origin": "pdf_master",
            "source_dimensions": {"width": w, "height": h},
            "recommended_upscale_group": group,
            "priority": prio,
            "recommended_scale": scale,
            "recommended_output_format": "png",
            "face_sensitive": bool(flags.get("face_sensitive", False)),
            "handwriting_sensitive": bool(flags.get("handwriting_sensitive", False)),
            "drawing_sensitive": bool(flags.get("drawing_sensitive", False)),
            "expected_derived_file": derived_rel,
            "web_prototype_file": (f"design/prototypes/web/assets/img/{hid}/{webfile}" if webfile else None),
            "gigapixel_status": "pending",
            "review_status": "not_reviewed",
            "publish_blocked": bool(flags.get("publish_blocked", False)),
            "notes": ([flags["note"]] if flags.get("note") else []),
        }
        manifest_rows.append(row)

manifest = {
    "version": "1.0.0",
    "generated": "2026-07-16",
    "source_of_truth": "source/reference.pdf (PPTX утерян)",
    "description": "Манифест апскейла через Topaz Gigapixel. master → assets/master-from-pdf; результат владелец кладёт в assets/derived-upscaled с именем <asset_id>_upscaled.<ext>. Порядок и правила — docs/gigapixel-batch-guide.md.",
    "groups": ["photo_face","photo_documentary","letter_handwriting","drawing_child_art","mixed_manual","cover_material","map_or_emblem"],
    "gigapixel_status_values": ["pending","done","skipped"],
    "review_status_values": ["not_reviewed","approved","needs_redo","rejected"],
    "assets": manifest_rows,
}
os.makedirs(f"{BASE}/content/manifests", exist_ok=True)
json.dump(manifest, open(f"{BASE}/content/manifests/upscale-manifest.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

with open(f"{BASE}/content/manifests/upscale-manifest.csv","w",encoding="utf-8-sig",newline="") as f:
    w = csv.writer(f, delimiter=";")
    cols = ["asset_id","entity_id","asset_type","recommended_upscale_group","priority","recommended_scale",
            "source_width","source_height","face_sensitive","handwriting_sensitive","drawing_sensitive",
            "source_file","expected_derived_file","gigapixel_status","review_status","publish_blocked","notes"]
    w.writerow(cols)
    for r in manifest_rows:
        w.writerow([r["asset_id"],r["entity_id"],r["asset_type"],r["recommended_upscale_group"],r["priority"],
                    r["recommended_scale"],r["source_dimensions"]["width"],r["source_dimensions"]["height"],
                    r["face_sensitive"],r["handwriting_sensitive"],r["drawing_sensitive"],r["source_file"],
                    r["expected_derived_file"],r["gigapixel_status"],r["review_status"],r["publish_blocked"],
                    " | ".join(r["notes"])])

# --- тест-батч: 2 фото-лица, 2 письма, 1 рисунок, 1 mixed ---
test_pick = ["hero-001_photo_01","hero-002_photo_04","hero-001_letter_01","hero-002_letter_02","hero-002_drawing_01"]
by_id = {r["asset_id"]: r for r in manifest_rows}
tb = f"{BASE}/assets/test-batch-gigapixel"
for aid in test_pick:
    shutil.copy2(f"{BASE}/{by_id[aid]['source_file']}", f"{tb}/{aid}_master.png")
# mixed sample — целая стр.17 (фото+рисунок+письмо на одном развороте) в высоком качестве
pdf = pdfium.PdfDocument(f"{BASE}/source/reference.pdf")
pdf[16].render(scale=3.2).to_pil().convert("RGB").save(f"{tb}/mixed_sample_p017_master.png")
pdf.close()

# --- поля резолюции ассетов в content.json прототипов ---
for hid, items in ASSETS.items():
    cj_path = f"{BASE}/content/prototypes/{hid}/content.json"
    cj = json.load(open(cj_path, encoding="utf-8"))
    res = {}
    for (aid, typ, group, prio, scale, native, webfile, flags) in items:
        subdir = TYPE_DIR[typ]
        res[aid] = {
            "master_asset": f"assets/master-from-pdf/heroes/{hid}/{subdir}/{aid}_master.png",
            "expected_upscaled_asset": f"assets/derived-upscaled/heroes/{hid}/{subdir}/{aid}_upscaled.png",
            "preferred_web_asset": f"assets/master-from-pdf/heroes/{hid}/{subdir}/{aid}_master.png",
            "preferred_print_asset": f"assets/master-from-pdf/heroes/{hid}/{subdir}/{aid}_master.png",
            "upscaled_available": False,
            "web_prototype_file": (f"design/prototypes/web/assets/img/{hid}/{webfile}" if webfile else None),
        }
    cj["asset_resolution"] = {
        "policy": "docs/asset-resolution-policy.md",
        "rule": "preferred_* = upscaled если upscaled_available и прошёл review; иначе master_from_pdf",
        "assets": res,
    }
    json.dump(cj, open(cj_path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

print("assets:", len(manifest_rows))
print("test-batch files:", len(test_pick)+1)
print("manifest + csv + content.json resolution — записаны")
