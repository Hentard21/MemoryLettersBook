#!/usr/bin/env python3
"""Complete the locked V29 intro with the three approved Adina photographs.

The script deliberately changes only the reserved photo page.  Greeting copy,
the map, decree, contents, pagination and all family pages stay inherited from
V29.  The expected print assets are produced by the additional-materials
ingestion step; missing inputs stop the build instead of restoring a public
placeholder.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
V29_BUILDER = ROOT / "scripts/build_intro_single_column_v29.py"
V29_DIR = ROOT / "design/prototypes/print-v29-single-column-welcome"
V29_HTML = V29_DIR / "interior-single-column-welcome-v29.html"
V29_PLAN = V29_DIR / "intro-page-plan-v29.json"

OUT_DIR = ROOT / "design/prototypes/print-v30-asset-completion"
OUT_HTML = OUT_DIR / "interior-asset-completion-v30.html"
OUT_PLAN = OUT_DIR / "intro-page-plan-v30.json"

PHOTO_ROOT = ROOT / "assets/intro-people/adina-gallery/print"
PHOTO_SPECS = (
    {
        "file": PHOTO_ROOT / "adina_dsc_0092_topaz_2x.jpg",
        "caption": "Участники проекта",
        "alt": "Участники проекта на сцене",
        "class": "adina-photo adina-photo--stage",
    },
    {
        "file": PHOTO_ROOT / "adina_dsc_0189_topaz_2x.jpg",
        "caption": "Диалог поколений",
        "alt": "Встреча участников проекта «Диалог поколений. Герои и дети»",
        "class": "adina-photo adina-photo--meeting",
    },
    {
        "file": PHOTO_ROOT / "adina_dsc_4846_topaz_2x.jpg",
        "caption": "Живая встреча",
        "alt": "Адина Арыковна на встрече с участниками проекта",
        "class": "adina-photo adina-photo--conversation",
    },
)


V30_CSS = r"""

/* V30 fills the already-reserved V29 Adina photo page; geometry is locked. */
.adina-photos .photo-note{max-width:170mm}
.adina-photo-slot::before{display:none}
.adina-photo-slot .adina-photo{
  position:absolute;
  inset:0;
  width:100%;
  height:100%;
  display:block;
  object-fit:cover;
  filter:saturate(.96) contrast(1.015);
}
.adina-photo-slot .adina-photo--stage{object-position:center 46%}
.adina-photo-slot .adina-photo--meeting{object-position:center 45%}
.adina-photo-slot .adina-photo--conversation{object-position:center 47%}
.adina-photo-slot figcaption{
  position:absolute;
  z-index:2;
  left:0;
  right:0;
  bottom:0;
  padding:2.5mm 3.5mm 2.3mm;
  background:linear-gradient(180deg,rgba(249,249,247,.18),rgba(249,249,247,.94));
  font:650 5.3pt/1.25 var(--head);
  letter-spacing:.075em;
  text-transform:uppercase;
  color:var(--primary_navy);
}
"""


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def ensure_v29_source() -> None:
    """Regenerate V29 deterministically so V30 never inherits a stale edit."""
    # V29 is the approved source snapshot. Its generator records the current
    # time, so preserve the tracked plan bytes and avoid dirtying the locked
    # artifact merely because V30 was rebuilt.
    locked_plan = V29_PLAN.read_bytes() if V29_PLAN.is_file() else None
    subprocess.run([sys.executable, str(V29_BUILDER)], cwd=ROOT, check=True)
    for path in (V29_HTML, V29_PLAN):
        if not path.is_file():
            raise FileNotFoundError(path)
    if locked_plan is not None:
        V29_PLAN.write_bytes(locked_plan)


def build() -> None:
    ensure_v29_source()
    missing = [str(item["file"]) for item in PHOTO_SPECS if not item["file"].is_file()]
    if missing:
        raise FileNotFoundError(
            "Adina print assets are not ready; run the additional-materials "
            f"ingestion first: {missing}"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(V29_HTML.read_text(encoding="utf-8"), "html.parser")
    page = soup.select_one(".adina-photos")
    if page is None:
        raise RuntimeError("V29 intro has no reserved .adina-photos page")
    slots = page.select(".adina-photo-grid > .adina-photo-slot")
    if len(slots) != len(PHOTO_SPECS):
        raise RuntimeError(
            f"Expected {len(PHOTO_SPECS)} Adina photo slots, found {len(slots)}"
        )

    page["data-status"] = "complete"
    page["data-content-lock"] = "owner-supplied-photo-chronicle"
    note = page.select_one(".photo-note")
    if note is not None:
        note.string = "Фотохроника проекта «Диалог поколений. Герои и дети»."
    run = page.select_one(".run")
    if run is not None:
        run.string = "Фотохроника проекта"
    grid = page.select_one(".adina-photo-grid")
    if grid is not None:
        grid["aria-label"] = "Фотохроника проекта"

    for slot, spec in zip(slots, PHOTO_SPECS, strict=True):
        slot.clear()
        image = soup.new_tag("img")
        image["src"] = "../../../" + repo_path(spec["file"])
        image["alt"] = spec["alt"]
        image["class"] = str(spec["class"]).split()
        slot.append(image)
        caption = soup.new_tag("figcaption")
        caption.string = spec["caption"]
        slot.append(caption)

    style = soup.select_one("style")
    if style is None:
        raise RuntimeError("V29 intro has no style element")
    style.append(V30_CSS)
    title = soup.select_one("title")
    if title is not None:
        title.string = "Письма памяти — V30, дополнение ассетов"

    if len(page.select(".adina-photo-slot img")) != 3:
        raise RuntimeError("Not all Adina photographs were inserted")
    if page.select_one("[data-status='awaiting-owner-photos']") is not None:
        raise RuntimeError("Technical Adina placeholder survived V30 build")

    OUT_HTML.write_text(str(soup), encoding="utf-8")

    plan = json.loads(V29_PLAN.read_text(encoding="utf-8-sig"))
    plan["schema_version"] = 3
    plan["generated_at"] = datetime.now(timezone.utc).isoformat()
    plan["generator"] = "scripts/build_intro_complete_v30.py"
    plan["source_html"] = repo_path(V29_HTML)
    plan["scope"] = "v29_locked_intro_plus_owner_supplied_adina_photo_chronicle"
    for item in plan.get("pages", []):
        if item.get("production_interior_page") == 11:
            item["role"] = "adina_photo_chronicle_complete"
            item["assets"] = [repo_path(spec["file"]) for spec in PHOTO_SPECS]
    plan["review_flags"] = [
        value
        for value in plan.get("review_flags", [])
        if value != "AWAITING_ADINA_ADDITIONAL_PHOTOS"
    ]
    plan["asset_completion"] = {
        "pagination_changed": False,
        "adina_photo_page": 11,
        "assets": [repo_path(spec["file"]) for spec in PHOTO_SPECS],
    }
    OUT_PLAN.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUT_HTML)
    print(OUT_PLAN)


if __name__ == "__main__":
    build()
