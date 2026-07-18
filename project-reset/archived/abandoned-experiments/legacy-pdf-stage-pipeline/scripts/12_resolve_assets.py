# -*- coding: utf-8 -*-
"""
Этап 12: резолвер ассетов. Владелец постепенно заполняет
assets/derived-upscaled/ и/или assets/review/approved/. Этот скрипт для каждого
ассета выбирает, что показывать в прототипах, и обновляет их — прозрачно и
воспроизводимо.

Правило (см. docs/asset-resolution-policy.md):
  preferred = upscaled, ЕСЛИ upscaled-файл существует И одобрен
             (review_status=approved в манифесте ИЛИ копия в assets/review/approved/);
  иначе      preferred = master_from_pdf.

Действия:
  - обновляет upscale-manifest.json (gigapixel_status/review_status по факту наличия файлов);
  - проставляет upscaled_available/preferred_* в content.json прототипов;
  - копирует выбранный файл в путь веб-прототипа (печать использует те же файлы);
  - пишет content/manifests/asset-resolution.json (что и почему выбрано).

Запускать после каждого пополнения derived-upscaled/ или review/approved/.
Идемпотентен. Ничего не удаляет; master-версии не трогает.
"""
import glob
import json
import os

from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAN = f"{BASE}/content/manifests/upscale-manifest.json"

def find_upscaled(expected_rel, asset_id):
    """Ищет upscaled-файл: точное имя или любой <asset_id>_upscaled.* в той же папке."""
    exact = f"{BASE}/{expected_rel}"
    if os.path.exists(exact):
        return expected_rel
    folder = os.path.dirname(f"{BASE}/{expected_rel}")
    for p in sorted(glob.glob(f"{folder}/{asset_id}_upscaled.*")):
        return os.path.relpath(p, BASE).replace("\\", "/")
    return None

def is_approved(asset_id, manifest_review):
    if manifest_review == "approved":
        return True
    # копия в review/approved/ (по имени asset_id) — тоже одобрение
    return bool(glob.glob(f"{BASE}/assets/review/approved/{asset_id}*"))

manifest = json.load(open(MAN, encoding="utf-8"))
resolution = {}
web_updates = 0

for a in manifest["assets"]:
    aid = a["asset_id"]
    up_rel = find_upscaled(a["expected_derived_file"], aid)
    if up_rel:
        a["gigapixel_status"] = "done"
    approved = is_approved(aid, a.get("review_status"))
    use_upscaled = bool(up_rel and approved)
    chosen = up_rel if use_upscaled else a["source_file"]
    reason = ("upscaled+approved" if use_upscaled else
              ("upscaled_present_but_not_approved→master" if up_rel else "no_upscaled→master"))
    resolution[aid] = {"chosen": chosen, "reason": reason,
                       "upscaled_available": bool(up_rel), "approved": approved,
                       "publish_blocked": a.get("publish_blocked", False)}
    # обновить веб-прототип (печать берёт те же файлы)
    web = a.get("web_prototype_file")
    if web:
        dst = f"{BASE}/{web}"
        if os.path.exists(dst):
            try:
                Image.open(f"{BASE}/{chosen}").convert("RGB").save(dst, quality=90)
                web_updates += 1
            except Exception as e:
                resolution[aid]["web_update_error"] = str(e)

# обновить content.json прототипов
for hid in {a["entity_id"] for a in manifest["assets"]}:
    cj_path = f"{BASE}/content/prototypes/{hid}/content.json"
    if not os.path.exists(cj_path):
        continue
    cj = json.load(open(cj_path, encoding="utf-8"))
    ar = cj.get("asset_resolution", {}).get("assets", {})
    for aid, meta in ar.items():
        if aid in resolution:
            r = resolution[aid]
            meta["upscaled_available"] = r["upscaled_available"]
            pref = (r["chosen"] if r["reason"] == "upscaled+approved" else meta["master_asset"])
            meta["preferred_web_asset"] = pref
            meta["preferred_print_asset"] = pref
    json.dump(cj, open(cj_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

json.dump(manifest, open(MAN, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"note": "Что выбрано для каждого ассета и почему. Перегенерируется scripts/12_resolve_assets.py.",
           "resolution": resolution},
          open(f"{BASE}/content/manifests/asset-resolution.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

n_up = sum(1 for r in resolution.values() if r["reason"] == "upscaled+approved")
print(f"assets: {len(resolution)} | используют upscaled: {n_up} | обновлено веб-файлов: {web_updates}")
print("Подсказка: сейчас upscaled ещё нет — прототипы используют нативные мастера.")
