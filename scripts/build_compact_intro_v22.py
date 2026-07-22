#!/usr/bin/env python3
"""Build the compact V22 intro without touching the locked family templates.

The script deliberately reuses complete DOM fragments from V18.  It does not
rewrite greetings, biographies, captions, names, or the family order.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/prototypes/print-v12/interior-combined-v18.html"
V21_TOC = ROOT / "design/prototypes/print-v21/generated-toc.json"
OUT_DIR = ROOT / "design/prototypes/print-v22"
OUT_HTML = OUT_DIR / "interior-compact-v22.html"
OUT_PLAN = OUT_DIR / "compact-intro-page-plan.json"


COMPACT_CSS = r"""

/* V22: compact introductory pages. Family pages remain under the V20 lock. */
.compact-welcome{isolation:isolate;background:linear-gradient(122deg,#f5f4f0,#ebe9e3)}
.compact-welcome .vip-map{left:-20mm;top:25mm;width:247mm;height:168mm;opacity:.11}
.compact-welcome .vip-vignette{background:radial-gradient(115% 95% at 45% 48%,rgba(243,242,238,0) 34%,rgba(243,242,238,.74) 78%,#f3f2ee 100%)}
.compact-welcome .vip-meta{left:17mm;top:14mm;width:68mm;z-index:12}
.compact-welcome .vip-meta h1{margin-top:2.5mm;font-size:20.5pt;line-height:1.02}
.compact-welcome .vip-meta .role{margin-top:3mm;max-width:66mm;font-size:6.6pt;line-height:1.33;color:#606975}
.compact-welcome .vip-meta hr{width:16mm;margin-top:3.7mm}
.compact-welcome .vip-cutout{left:-6mm;right:auto;bottom:-1mm;width:102mm;height:160mm;object-fit:contain;object-position:left bottom;z-index:5}
.compact-welcome.compact--shumilov .vip-cutout{left:-9mm;width:108mm;height:165mm}
.compact-welcome.compact--makarychev .vip-cutout{left:-7mm;width:104mm;height:161mm}
.compact-welcome.compact--belyaninov .vip-cutout{left:-4mm;width:99mm;height:159mm}
.compact-welcome.compact--smirnova .vip-cutout{left:-5mm;width:102mm;height:160mm}
.compact-welcome.compact--tengebaeva .vip-cutout{left:-6mm;width:104mm;height:161mm}
.compact--makarychev .vip-meta h1,.compact--belyaninov .vip-meta h1,.compact--tengebaeva .vip-meta h1{font-size:18.4pt}
.compact-quote{--compact-quote-size:11.3pt;position:absolute;left:78mm;right:22mm;top:11mm;bottom:13mm;z-index:9;overflow:hidden;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:2mm;padding:6.5mm 7mm 5.5mm 9mm;background:
  radial-gradient(circle at 12% 8%,rgba(72,112,153,.075),transparent 38%),
  radial-gradient(circle at 84% 74%,rgba(169,134,60,.055),transparent 33%),
  repeating-linear-gradient(0deg,rgba(34,59,94,.016) 0,rgba(34,59,94,.016) .15mm,transparent .15mm,transparent 1.2mm),
  rgba(250,249,245,.965);border-left:1mm solid var(--accent_burgundy);box-shadow:0 .8mm 2.2mm rgba(38,43,48,.11)}
.compact-quote::before,.compact-quote::after{position:absolute;font:400 25pt/1 var(--script);color:rgba(135,63,70,.22)}
.compact-quote::before{content:"\201c";left:2.5mm;top:2.5mm}.compact-quote::after{content:"\201d";right:3mm;bottom:1mm}
.compact-quote>.quote-label{position:static;padding-left:1mm;font-size:5.25pt}
.compact-quote-flow{height:100%;min-height:0;overflow:hidden;columns:2;column-gap:7mm;column-rule:.18mm solid var(--line);column-fill:balance;font:400 var(--compact-quote-size)/1.18 var(--script);color:var(--body_text);hyphens:auto}
.compact-quote-flow p{margin:0 0 1.35mm;orphans:2;widows:2}
.compact-quote-flow .salutation{font-size:calc(var(--compact-quote-size) + .35pt);line-height:1.16;color:var(--primary_navy)}
.compact-quote-flow .quote-ending{margin-top:1.5mm;font-size:calc(var(--compact-quote-size) + .45pt);line-height:1.15;color:var(--accent_burgundy)}
.compact-attribution{position:relative;z-index:2;padding-top:1.7mm;border-top:.2mm solid var(--line);font:500 5.2pt/1.22 var(--body);color:var(--secondary_text);text-align:right}
.compact-attribution.quote-attribution--signed{display:grid;grid-template-columns:27mm 1fr;align-items:center;gap:3.5mm;text-align:left}
.compact-attribution .signature-proof{height:13mm;gap:.3mm}.compact-attribution .signature-proof span{font-size:3.9pt}
.compact-attribution .signature-ink{max-width:26mm}.compact-attribution .signature-ink--shumilov{height:11mm}.compact-attribution .signature-ink--makarychev{height:10mm}
.compact--shumilov .compact-quote{--compact-quote-size:11.8pt}
.compact--makarychev .compact-quote{--compact-quote-size:11.9pt}
.compact--belyaninov .compact-quote{--compact-quote-size:12.5pt}
.compact--smirnova .compact-quote{--compact-quote-size:12.1pt}
.compact--tengebaeva .compact-quote{--compact-quote-size:11.4pt}
.right.compact-welcome .vip-cutout{left:auto;right:-5mm;object-position:right bottom}
.right.compact-welcome .vip-meta{left:auto;right:17mm;width:62mm}
.right.compact-welcome .vip-meta h1{font-size:18.4pt}
.right.compact-welcome .vip-meta .role{max-width:61mm}
.right.compact-welcome .compact-quote{left:22mm;right:77mm}

/* A reserved editorial page for the additional Adina Arykovna photographs. */
.adina-photos{background:linear-gradient(135deg,#f7f7f4,#edf0f1)}
.adina-photos .safe{top:14mm;bottom:15mm}
.adina-photos h2{margin-top:2mm;font:800 22pt/1.06 var(--head);color:var(--primary_navy)}
.adina-photos .photo-note{margin-top:3mm;max-width:165mm;font:500 8.2pt/1.4 var(--body);color:var(--secondary_text)}
.adina-photo-grid{position:absolute;left:21mm;right:17mm;top:54mm;bottom:22mm;display:grid;grid-template-columns:1.18fr .82fr;grid-template-rows:1fr 1fr;gap:4mm}
.adina-photo-slot{position:relative;overflow:hidden;background:rgba(255,255,255,.62);border:.25mm solid rgba(34,59,94,.13);box-shadow:0 .6mm 1.8mm rgba(38,43,48,.07)}
.adina-photo-slot:first-child{grid-row:1/-1}
.adina-photo-slot::before{content:"";position:absolute;inset:7mm;border:.3mm dashed rgba(34,59,94,.16)}
.adina-photo-slot span{position:absolute;left:0;right:0;bottom:0;padding:3mm 4mm;background:rgba(251,251,249,.9);font:600 5.7pt/1.25 var(--head);letter-spacing:.08em;text-transform:uppercase;color:var(--secondary_text)}

/* 74 families in two columns over two pages; no entries are dropped. */
.contents-compact .safe{top:12mm;bottom:14mm}
.contents-compact .contents-head{margin-bottom:3.5mm}
.contents-compact .contents-head h2{font-size:15pt}
.toc-columns{display:grid;grid-template-columns:1fr 1fr;gap:0 7mm}
.toc-columns .toc-list{min-width:0}
.contents-compact .toc-row{display:grid;grid-template-columns:6.5mm minmax(0,1fr) auto;grid-template-rows:auto auto;column-gap:1.5mm;row-gap:.3mm;align-items:center;min-height:8.05mm;padding:1mm 0}
.contents-compact .toc-num{grid-column:1;grid-row:1/-1;align-self:center;font-size:6.7pt}
.contents-compact .toc-name{grid-column:2;grid-row:1;font-size:8.1pt;line-height:1.02;white-space:nowrap}
.contents-compact .toc-reg{grid-column:2;grid-row:2;min-width:0;font-size:5.55pt;line-height:1.05;white-space:normal}
.contents-compact .toc-pg{grid-column:3;grid-row:1/-1;align-self:center;font-size:6.8pt}
.contents-compact .toc-dots{display:none}
"""


PROFILE_SPECS = [
    (5, 6, "shumilov", "shumilov_compact_nobg.png"),
    (7, 8, "makarychev", "makarychev_compact_nobg.png"),
    (9, 10, "belyaninov", "belyaninov_compact_nobg.png"),
    (13, 14, "smirnova", "smirnova_compact_nobg.png"),
    (15, 16, "tengebaeva", "tengebaeva_compact_nobg.png"),
]


def direct_pages(soup: BeautifulSoup) -> list[Tag]:
    pages: list[Tag] = []
    for sheet in soup.select("section.sheet"):
        pages.extend(sheet.select(":scope > .page"))
    return pages


def reset_side(page: Tag, page_number: int) -> None:
    classes = [c for c in page.get("class", []) if c not in {"left", "right"}]
    classes.insert(1, "left" if page_number % 2 else "right")
    page["class"] = classes
    folio = page.select_one(".folio")
    if folio:
        folio.string = str(page_number)


def combined_profile(pages: list[Tag], spec: tuple[int, int, str, str], soup: BeautifulSoup) -> Tag:
    profile_page, quote_page, slug, cutout_name = spec
    page = copy.deepcopy(pages[profile_page - 1])
    quote_source = pages[quote_page - 1]
    page["class"] = [c for c in page.get("class", []) if c != "left"]
    page["class"].extend(["compact-welcome", f"compact--{slug}"])
    page["data-source-pages"] = f"{profile_page},{quote_page}"

    excerpt = page.select_one(".vip-excerpt")
    if excerpt:
        excerpt.decompose()

    portrait = page.select_one(".vip-cutout")
    if portrait:
        portrait["src"] = f"../../../assets/intro-people/cutouts-pro/{cutout_name}"

    card = soup.new_tag("blockquote")
    card["class"] = ["compact-quote"]
    label = soup.new_tag("span")
    label["class"] = ["quote-label"]
    label.string = "Полный текст приветствия"
    card.append(label)

    flow = soup.new_tag("div")
    flow["class"] = ["compact-quote-flow"]
    source_flow = quote_source.select_one(".quote-flow")
    if source_flow is None:
        raise RuntimeError(f"Missing quote flow on source page {quote_page}")
    for child in source_flow.find_all(recursive=False):
        flow.append(copy.deepcopy(child))
    card.append(flow)

    source_footer = quote_source.select_one(".quote-attribution")
    if source_footer is None:
        raise RuntimeError(f"Missing attribution on source page {quote_page}")
    footer = copy.deepcopy(source_footer)
    footer["class"] = [
        "compact-attribution",
        *(["quote-attribution--signed"] if "quote-attribution--signed" in source_footer.get("class", []) else []),
    ]
    card.append(footer)

    run = page.select_one(".run")
    if run:
        run.string = "Приветственное слово · полный текст"
    folio = page.select_one(".folio")
    if folio:
        folio.insert_before(card)
    else:
        page.append(card)
    return page


def make_adina_photo_page(soup: BeautifulSoup) -> Tag:
    fragment = BeautifulSoup(
        """
        <div class="page adina-photos" data-status="awaiting-owner-photos">
          <div class="safe">
            <p class="kicker">Диалог поколений</p>
            <h2>Фотохроника встречи</h2>
            <p class="photo-note">Страница сохранена для дополнительных фотографий Адины Арыковны. Композиция будет заполнена без изменения соседней страницы приветствия.</p>
          </div>
          <div class="adina-photo-grid" aria-label="Зарезервированные места для фотографий">
            <figure class="adina-photo-slot"><span>Основная фотография</span></figure>
            <figure class="adina-photo-slot"><span>Фотография встречи</span></figure>
            <figure class="adina-photo-slot"><span>Архивный материал</span></figure>
          </div>
          <span class="folio">12</span><span class="run">Фотохроника · материалы ожидаются</span>
        </div>
        """,
        "html.parser",
    )
    return fragment.div


def make_toc_pages(soup: BeautifulSoup, source_pages: list[Tag]) -> list[Tag]:
    source_rows = []
    for page_number in (17, 18, 19, 20):
        source_rows.extend(source_pages[page_number - 1].select(".toc-row"))
    if len(source_rows) != 74:
        raise RuntimeError(f"Expected 74 source TOC rows, got {len(source_rows)}")

    toc_data = json.loads(V21_TOC.read_text(encoding="utf-8"))["families"]
    if len(toc_data) != 74:
        raise RuntimeError(f"Expected 74 generated TOC records, got {len(toc_data)}")

    # V21 has 19 frontmatter pages. Compact V22 has 13 interior pages before
    # the first family, so every family page shifts by six.
    rows: list[Tag] = []
    for source_row, record in zip(source_rows, toc_data, strict=True):
        row = copy.deepcopy(source_row)
        page_cell = row.select_one(".toc-pg")
        if page_cell is None:
            raise RuntimeError("TOC row is missing its page cell")
        page_cell.string = str(int(record["start_page"]) - 6)
        row["data-hero-id"] = record["hero_id"]
        row["data-production-interior-page"] = str(int(record["start_page"]) - 6)
        rows.append(row)

    pages: list[Tag] = []
    for page_index, chunk in enumerate((rows[:37], rows[37:]), start=1):
        # Balanced columns of 19/18 entries.
        split_at = 19
        left_col, right_col = chunk[:split_at], chunk[split_at:]
        page = soup.new_tag("div")
        page["class"] = ["page", "contents-page", "contents-compact"]
        safe = soup.new_tag("div")
        safe["class"] = ["safe"]
        head = BeautifulSoup(
            f'<div class="contents-head"><h2>Наши герои</h2><span class="cont-note">{"74 семьи" if page_index == 1 else "продолжение"}</span></div>',
            "html.parser",
        ).div
        safe.append(head)
        columns = soup.new_tag("div")
        columns["class"] = ["toc-columns"]
        for column_rows in (left_col, right_col):
            listing = soup.new_tag("ol")
            listing["class"] = ["toc-list"]
            for row in column_rows:
                listing.append(row)
            columns.append(listing)
        safe.append(columns)
        page.append(safe)
        folio = soup.new_tag("span")
        folio["class"] = ["folio"]
        page.append(folio)
        run = soup.new_tag("span")
        run["class"] = ["run"]
        run.string = "Содержание · страницы внутреннего блока"
        page.append(run)
        pages.append(page)
    return pages


def add_sheet(soup: BeautifulSoup, body: Tag, left_page: Tag, right_page: Tag, sheet_class: str | None = None) -> None:
    sheet = soup.new_tag("section")
    classes = ["sheet"]
    if sheet_class:
        classes.append(sheet_class)
    sheet["class"] = classes
    sheet.append(left_page)
    sheet.append(right_page)
    watermark = soup.new_tag("span")
    watermark["class"] = ["wm"]
    watermark.string = "ПРОТОТИП"
    sheet.append(watermark)
    body.append(sheet)


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
    source_pages = direct_pages(soup)
    if len(source_pages) < 20:
        raise RuntimeError(f"Expected at least 20 source pages, got {len(source_pages)}")

    title = soup.select_one("title")
    if title:
        title.string = "Письма памяти — V22, компактное вступление"
    style = soup.select_one("style")
    if style is None:
        raise RuntimeError("Source document has no style element")
    style.append(COMPACT_CSS)

    compact_by_slug = {
        slug: combined_profile(source_pages, spec, soup)
        for spec in PROFILE_SPECS
        for slug in [spec[2]]
    }
    toc_pages = make_toc_pages(soup, source_pages)

    ordered_pages = [
        copy.deepcopy(source_pages[0]),  # cover
        copy.deepcopy(source_pages[1]),  # partners
        copy.deepcopy(source_pages[2]),  # geography lead
        copy.deepcopy(source_pages[3]),  # map
        compact_by_slug["shumilov"],
        copy.deepcopy(source_pages[10]),  # old page 11
        compact_by_slug["makarychev"],
        copy.deepcopy(source_pages[11]),  # old page 12
        compact_by_slug["belyaninov"],
        compact_by_slug["smirnova"],
        compact_by_slug["tengebaeva"],
        make_adina_photo_page(soup),
        toc_pages[0],
        toc_pages[1],
    ]

    body = soup.body
    if body is None:
        raise RuntimeError("Source document has no body")
    body.clear()
    for page_number, page in enumerate(ordered_pages, start=1):
        reset_side(page, page_number)
        # Only the V18-local map paths need rebasing when the derivative HTML
        # moves from print-v12 to print-v22. Shared project assets already use
        # stable ../../../assets paths.
        for image in page.select('img[src^="assets/"]'):
            image["src"] = f'../print-v12/{image["src"]}'

    for index in range(0, len(ordered_pages), 2):
        sheet_class = "map-spread" if index == 2 else None
        add_sheet(soup, body, ordered_pages[index], ordered_pages[index + 1], sheet_class)

    OUT_HTML.write_text(str(soup), encoding="utf-8")

    v21_families = json.loads(V21_TOC.read_text(encoding="utf-8"))["families"]
    page_plan = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/build_compact_intro_v22.py",
        "source_html": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "scope": "intro_only_families_untouched",
        "design_lock": "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf",
        "preview": {
            "cover_included": True,
            "page_count": 14,
            "spread_count": 7,
            "first_family_preview_page": 15,
        },
        "production_interior": {
            "cover_included": False,
            "frontmatter_pages": 13,
            "first_family_page": 14,
            "page_saving_vs_v21": 6,
            "toc_pages": [12, 13],
        },
        "pages": [
            {"preview_page": 1, "production_interior_page": None, "role": "approved_cover", "source_pages": [1]},
            {"preview_page": 2, "production_interior_page": 1, "role": "partners", "source_pages": [2]},
            {"preview_page": 3, "production_interior_page": 2, "role": "geography_lead", "source_pages": [3]},
            {"preview_page": 4, "production_interior_page": 3, "role": "project_map", "source_pages": [4]},
            {"preview_page": 5, "production_interior_page": 4, "role": "welcome_shumilov_complete", "source_pages": [5, 6]},
            {"preview_page": 6, "production_interior_page": 5, "role": "chronicle_i", "source_pages": [11]},
            {"preview_page": 7, "production_interior_page": 6, "role": "welcome_makarychev_complete", "source_pages": [7, 8]},
            {"preview_page": 8, "production_interior_page": 7, "role": "chronicle_ii", "source_pages": [12]},
            {"preview_page": 9, "production_interior_page": 8, "role": "welcome_belyaninov_complete", "source_pages": [9, 10]},
            {"preview_page": 10, "production_interior_page": 9, "role": "welcome_smirnova_complete", "source_pages": [13, 14]},
            {"preview_page": 11, "production_interior_page": 10, "role": "welcome_tengebaeva_complete", "source_pages": [15, 16]},
            {"preview_page": 12, "production_interior_page": 11, "role": "adina_photos_pending", "source_pages": []},
            {"preview_page": 13, "production_interior_page": 12, "role": "toc_i", "source_pages": [17, 18]},
            {"preview_page": 14, "production_interior_page": 13, "role": "toc_ii", "source_pages": [19, 20]},
        ],
        "family_page_shift": {
            "from_v21": -6,
            "families": [
                {
                    "hero_id": row["hero_id"],
                    "order": row["order"],
                    "start_page": int(row["start_page"]) - 6,
                    "end_page": int(row["end_page"]) - 6,
                }
                for row in v21_families
            ],
        },
        "review_flags": [
            "AWAITING_ADINA_ADDITIONAL_PHOTOS",
            "AUTHORED_GREETING_TERMINOLOGY_REQUIRES_OWNER_REVIEW_BEFORE_FINAL_PRINT",
        ],
    }
    OUT_PLAN.write_text(json.dumps(page_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT_HTML)
    print(OUT_PLAN)


if __name__ == "__main__":
    build()
