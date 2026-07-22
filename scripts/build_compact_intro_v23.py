#!/usr/bin/env python3
"""Build the isolated V23 compact intro without touching V20/V22/families.

V23 keeps the five complete authored greetings verbatim and combines the two
geography pages into one.  The official decree occupies the former welcome
section-divider page, so the map, page count, contents and family parity are
all preserved.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

import build_compact_intro_v22 as v22


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/prototypes/print-v12/interior-combined-v18.html"
V21_TOC = ROOT / "design/prototypes/print-v21/generated-toc.json"
OUT_DIR = ROOT / "design/prototypes/print-v23"
OUT_HTML = OUT_DIR / "interior-compact-v23.html"
OUT_PLAN = OUT_DIR / "compact-intro-page-plan.json"


DECREE_TITLE = (
    "Указ Президента Российской Федерации от 25 декабря 2025 года № 962 "
    "«О проведении в Российской Федерации Года единства народов России»"
)

DECREE_COLUMNS = (
    (
        "В целях укрепления национального единства, мира и согласия между народами "
        "Российской Федерации постановляю:",
        "1. Провести в 2026 году в Российской Федерации Год единства народов России.",
        "2. Правительству Российской Федерации:",
        "а) образовать организационный комитет по проведению в Российской Федерации "
        "Года единства народов России и утвердить его состав;",
        "б) обеспечить разработку и реализацию при участии Совета при Президенте "
        "Российской Федерации по межнациональным отношениям плана основных мероприятий "
        "по проведению в Российской Федерации Года единства народов России;",
        "в) определить источники финансирования основных мероприятий по проведению "
        "в Российской Федерации Года единства народов России.",
    ),
    (
        "3. Назначить сопредседателями организационного комитета по проведению в "
        "Российской Федерации Года единства народов России первого заместителя "
        "Руководителя Администрации Президента Российской Федерации Кириенко С. В. "
        "и Заместителя Председателя Правительства Российской Федерации Голикову Т. А.",
        "4. Рекомендовать исполнительным органам субъектов Российской Федерации "
        "осуществлять необходимые мероприятия в рамках проводимого в Российской "
        "Федерации Года единства народов России.",
        "5. Настоящий Указ вступает в силу со дня его подписания.",
    ),
)


V23_CSS = r"""

/* V23: isolated intro corrections. V20, V22 and family templates are untouched. */

/* The complete geography story now occupies one page. */
.geography-combined{isolation:isolate;background:linear-gradient(128deg,#f7f6f2 0%,#eef2f4 100%)}
.geography-combined .map-title{left:17mm;top:16mm;width:71mm;z-index:8}
.geography-combined .map-title h1{font-size:25pt;line-height:1.01}
.geography-combined .map-title .sub{max-width:70mm;margin-top:4mm;font-size:8.1pt;line-height:1.38}
.geography-combined .map-canvas{inset:auto;right:8mm;top:10mm;width:164mm;height:134mm;background:none;z-index:3}
.geography-combined .map-big{left:0;right:auto;top:0;width:164mm;height:107mm;object-fit:contain;object-position:center;opacity:1}
.geography-combined .map-badge{left:9mm;right:5mm;bottom:1mm;width:auto;padding:3.5mm 4.5mm;border-left-width:.8mm;box-shadow:0 .6mm 1.8mm rgba(38,43,48,.09)}
.geography-combined .map-badge strong{font-size:9.6pt;line-height:1.08}
.geography-combined .map-badge span{margin-top:1mm;font-size:5.8pt;line-height:1.25}
.geography-combined .map-stats{left:17mm;right:17mm;bottom:15mm;display:grid;grid-template-columns:43mm 49mm minmax(0,1fr);gap:3mm;z-index:8}
.geography-combined .map-stat{min-height:24mm;padding:4mm 5mm}
.geography-combined .map-stat.wide{grid-column:auto}
.geography-combined .map-stat strong{font-size:11.2pt;line-height:1.08}
.geography-combined .map-stat span{font-size:5.6pt;line-height:1.25}

/* Page 4: the old 0707 hierarchy is retained, but the wording comes only
   from the verified official two-page facsimile. */
.decree-geography{isolation:isolate;overflow:hidden;background:#f2f3f2}
.decree-geography .decree-art{position:absolute;left:0;top:0;width:88mm;height:200mm;object-fit:cover;object-position:45% center;filter:saturate(.8) contrast(.96);z-index:1}
.decree-geography .decree-art-wash{position:absolute;left:0;top:0;width:101mm;height:200mm;background:linear-gradient(90deg,rgba(246,247,246,.02) 0%,rgba(246,247,246,.16) 58%,#f2f3f2 91%,#f2f3f2 100%);z-index:2}
.decree-geography .decree-map{position:absolute;left:4mm;top:53mm;width:78mm;height:59mm;object-fit:contain;opacity:.13;filter:grayscale(1);z-index:3}
.decree-context{position:absolute;left:12mm;top:15mm;width:62mm;padding:4.5mm 5mm;background:rgba(250,250,248,.9);border-top:.7mm solid var(--primary_navy);box-shadow:0 .6mm 2mm rgba(26,42,62,.09);z-index:5}
.decree-context .kicker{font:700 5.4pt/1.2 var(--head);letter-spacing:.15em;text-transform:uppercase;color:var(--primary_navy)}
.decree-context strong{display:block;margin-top:2.2mm;font:800 12.2pt/1.05 var(--head);color:var(--primary_navy)}
.decree-context span{display:block;margin-top:1mm;font:600 6pt/1.35 var(--body);color:var(--secondary_text)}
.decree-facsimiles{position:absolute;left:8mm;bottom:15mm;width:73mm;height:80mm;z-index:6}
.decree-facsimiles img{position:absolute;display:block;object-fit:contain;background:#fff;box-shadow:0 1.2mm 3.2mm rgba(30,40,52,.2);border:.35mm solid rgba(255,255,255,.8)}
.decree-facsimiles .facsimile-one{left:1mm;bottom:0;width:48mm;height:68mm;transform:rotate(-1.7deg)}
.decree-facsimiles .facsimile-two{right:0;bottom:3mm;width:43mm;height:61mm;transform:rotate(2.2deg)}
.decree-panel{position:absolute;left:80mm;right:14mm;top:11mm;bottom:13mm;padding:8mm 9mm 7mm;background:rgba(252,251,248,.97);border-left:.85mm solid var(--accent_burgundy);box-shadow:0 1mm 3.2mm rgba(25,39,55,.1);z-index:7}
.decree-panel .decree-kicker{font:700 5.8pt/1.2 var(--head);letter-spacing:.16em;text-transform:uppercase;color:var(--accent_burgundy)}
.decree-panel h1{margin-top:2.5mm;max-width:144mm;font:800 15.4pt/1.06 var(--head);letter-spacing:-.012em;color:var(--primary_navy)}
.decree-panel .decree-meta{display:flex;align-items:center;gap:3mm;margin-top:3mm;padding-bottom:3mm;border-bottom:.35mm solid rgba(34,59,94,.22);font:700 6pt/1.2 var(--head);letter-spacing:.08em;text-transform:uppercase;color:var(--secondary_text)}
.decree-panel .decree-meta b{color:var(--gold_accent)}
.decree-columns{display:grid;grid-template-columns:1fr 1fr;gap:7mm;margin-top:4mm}
.decree-column{min-width:0}
.decree-column p{margin:0 0 2.35mm;font:500 7.85pt/1.34 var(--body);color:#303943;text-wrap:pretty}
.decree-column p:first-child{font-weight:650;color:#202d3b}
.decree-signature{position:absolute;left:9mm;right:9mm;bottom:12mm;display:grid;grid-template-columns:1fr auto;align-items:end;gap:5mm;padding-top:2.8mm;border-top:.35mm solid rgba(34,59,94,.18);font:600 6.15pt/1.35 var(--body);color:var(--primary_navy)}
.decree-signature strong{font:700 7.3pt/1.2 var(--head)}
.decree-source{position:absolute;left:9mm;right:9mm;bottom:3.7mm;font:600 4.7pt/1.2 var(--body);color:var(--secondary_text)}

/* The freed geography page is a parity-preserving section divider. */
.welcome-divider{isolation:isolate;background:linear-gradient(135deg,#f4f4f0 0%,#eaf0f3 100%)}
.welcome-divider .divider-map{position:absolute;right:0;top:9mm;width:205mm;height:174mm;object-fit:contain;opacity:.09;z-index:1}
.welcome-divider .safe{top:16mm;bottom:17mm;z-index:4}
.welcome-divider .divider-kicker{font:700 6.2pt/1.2 var(--head);letter-spacing:.17em;text-transform:uppercase;color:var(--primary_navy)}
.welcome-divider h2{margin-top:3mm;max-width:206mm;font:800 28pt/1.02 var(--head);color:var(--primary_navy)}
.welcome-divider h2 span{display:block;margin-top:1.2mm;font-size:20pt;font-weight:650;line-height:1.08;letter-spacing:-.012em}
.welcome-divider .divider-sub{margin-top:4mm;font:600 9pt/1.3 var(--body);color:var(--accent_burgundy)}
.welcome-index{position:absolute;left:18mm;right:18mm;top:74mm;bottom:21mm;display:grid;grid-template-columns:repeat(6,1fr);grid-template-rows:1fr 1fr;gap:3.5mm;z-index:5}
.welcome-index article{display:grid;grid-template-columns:9mm minmax(0,1fr);align-content:center;gap:0 3mm;padding:4mm 5mm;background:rgba(251,251,249,.87);border-top:.6mm solid rgba(34,59,94,.76);box-shadow:0 .5mm 1.5mm rgba(38,43,48,.06)}
.welcome-index article:nth-child(-n+3){grid-column:span 2}
.welcome-index article:nth-child(4){grid-column:2/span 2}
.welcome-index article:nth-child(5){grid-column:4/span 2}
.welcome-index .welcome-index-num{grid-row:1/3;font:700 7pt/1 var(--head);color:var(--gold_accent)}
.welcome-index h3{font:800 10.5pt/1.08 var(--head);color:var(--primary_navy)}
.welcome-index p{margin-top:1mm;font:600 5.3pt/1.25 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--secondary_text)}

/* Left-hand portraits no longer terminate under the hard paper edge.  Their
   complete source canvas is scaled down to fit before the quote module. */
.compact-welcome::after{content:"";position:absolute;left:-14mm;bottom:0;width:108mm;height:142mm;border-radius:0 72mm 0 0;background:radial-gradient(ellipse at 48% 79%,rgba(69,99,132,.16),rgba(69,99,132,.045) 47%,transparent 72%);z-index:3;pointer-events:none}
.compact-welcome .vip-meta{width:68mm}
.compact-welcome .compact-quote{left:90mm;right:20mm}
.compact-welcome.compact--shumilov .vip-cutout{left:-5mm;width:92mm;height:156mm}
.compact-welcome.compact--makarychev .vip-cutout{left:-4mm;width:92mm;height:154mm}
.compact-welcome.compact--tengebaeva .vip-cutout{left:-3mm;width:92mm;height:154mm}
.compact--shumilov .vip-meta h1{font-size:19.2pt}
.compact--makarychev .vip-meta h1{font-size:17.2pt;letter-spacing:-.015em}
.compact--tengebaeva .vip-meta h1{font-size:17.2pt;letter-spacing:-.012em}
.compact--shumilov .compact-quote{--compact-quote-size:11.25pt}
.compact--makarychev .compact-quote{--compact-quote-size:11.25pt}
.compact--tengebaeva .compact-quote{--compact-quote-size:10.85pt}

/* Belyaninov was already successful; retain its composition. */
.compact--belyaninov .compact-quote{left:78mm;right:22mm}
.compact--belyaninov .vip-meta{width:57mm}
.compact--belyaninov .vip-meta h1{font-size:16.4pt;letter-spacing:-.014em}
.compact--belyaninov .vip-meta .role{max-width:57mm;font-size:6.15pt}

/* Smirnova's initials and role now have a real gap from the paper module. */
.right.compact--smirnova .vip-meta{right:15mm;width:58mm}
.right.compact--smirnova .vip-meta h1{font-size:17.2pt;letter-spacing:-.01em}
.right.compact--smirnova .vip-meta .role{max-width:58mm;font-size:6.35pt}
.right.compact--smirnova .compact-quote{left:22mm;right:77mm}

/* Shumilov, Makarychev and Tengebaeva look to camera-left in the approved
   source portraits. Put them on the right of their page so that the gaze is
   directed into the authored address. Do not mirror the raster: that would
   reverse name tapes, insignia, medals and other documentary details. */
.compact-welcome.compact--portrait-right::after{left:auto;right:-14mm;border-radius:72mm 0 0 0;background:radial-gradient(ellipse at 52% 79%,rgba(69,99,132,.16),rgba(69,99,132,.045) 47%,transparent 72%)}
.compact-welcome.compact--portrait-right .vip-cutout{left:auto;right:-5mm;object-position:right bottom}
.compact-welcome.compact--portrait-right .vip-meta{left:auto;right:17mm}
.compact-welcome.compact--portrait-right .compact-quote{left:20mm;right:90mm}
"""


def make_geography_combined(source_pages: list[Tag], soup: BeautifulSoup) -> Tag:
    """Combine the source geography lead and Russia map on one readable page."""
    page = copy.deepcopy(source_pages[3])
    page["class"] = ["page", "geography-combined"]
    page["data-source-pages"] = "книга0707:3-4"

    title = copy.deepcopy(source_pages[2].select_one(".map-title"))
    stats = copy.deepcopy(source_pages[2].select_one(".map-stats"))
    if title is None or stats is None or page.select_one(".map-canvas") is None:
        raise RuntimeError("Source geography pages are missing title, statistics, or map")
    page.insert(0, stats)
    page.insert(0, title)

    run = page.select_one(".run")
    if run is not None:
        run.string = "Первый том · география семей"
    return page


def make_decree_geography(source_pages: list[Tag], soup: BeautifulSoup) -> Tag:
    page = soup.new_tag("div")
    page["class"] = ["page", "decree-geography"]
    page["data-source-pages"] = "книга0707:4; official-decree:1-2"
    page["data-document-status"] = "verified-official-facsimile"

    artwork = soup.new_tag("img")
    artwork["class"] = ["decree-art"]
    artwork["src"] = "../../../assets/intro-decree/artwork/decree-editorial-stilllife-v1.png"
    artwork["alt"] = "Документальный натюрморт с бумагой и пером"
    page.append(artwork)

    wash = soup.new_tag("div")
    wash["class"] = ["decree-art-wash"]
    page.append(wash)

    map_image = copy.deepcopy(source_pages[3].select_one(".map-big"))
    if map_image is None:
        raise RuntimeError("Source page 4 is missing the map image")
    map_image["class"] = ["decree-map"]
    page.append(map_image)

    context = soup.new_tag("div")
    context["class"] = ["decree-context"]
    context.append(BeautifulSoup(
        '<p class="kicker">География памяти</p>'
        '<strong>74 семьи · 78 писем</strong>'
        '<span>Голоса детей героев из разных регионов России</span>',
        "html.parser",
    ))
    page.append(context)

    facsimiles = soup.new_tag("div")
    facsimiles["class"] = ["decree-facsimiles"]
    for number, css_class in ((1, "facsimile-one"), (2, "facsimile-two")):
        image = soup.new_tag("img")
        image["class"] = [css_class]
        image["src"] = f"../../../assets/intro-decree/official/decree-962-page-{number}.png"
        image["alt"] = f"Официальное факсимиле указа № 962, лист {number}"
        facsimiles.append(image)
    page.append(facsimiles)

    panel = soup.new_tag("article")
    panel["class"] = ["decree-panel"]
    kicker = soup.new_tag("p")
    kicker["class"] = ["decree-kicker"]
    kicker.string = "Официальная основа"
    heading = soup.new_tag("h1")
    heading.string = DECREE_TITLE
    meta = soup.new_tag("div")
    meta["class"] = ["decree-meta"]
    meta.append(BeautifulSoup("<b>№ 962</b><span>25 декабря 2025 года</span>", "html.parser"))
    panel.extend([kicker, heading, meta])

    columns = soup.new_tag("div")
    columns["class"] = ["decree-columns"]
    for paragraphs in DECREE_COLUMNS:
        column = soup.new_tag("div")
        column["class"] = ["decree-column"]
        for paragraph in paragraphs:
            text = soup.new_tag("p")
            text.string = paragraph
            column.append(text)
        columns.append(column)
    panel.append(columns)

    signature = soup.new_tag("div")
    signature["class"] = ["decree-signature"]
    signature.append(BeautifulSoup(
        "<span>Москва, Кремль<br/>25 декабря 2025 года</span>"
        "<strong>Президент Российской Федерации В. Путин</strong>",
        "html.parser",
    ))
    panel.append(signature)
    source = soup.new_tag("p")
    source["class"] = ["decree-source"]
    source.string = "Текст и факсимиле сверены с официальной публикацией Указа Президента Российской Федерации № 962."
    panel.append(source)
    page.append(panel)

    folio = soup.new_tag("span")
    folio["class"] = ["folio"]
    run = soup.new_tag("span")
    run["class"] = ["run"]
    run.string = "Официальная основа · география памяти"
    page.extend([folio, run])
    return page


def make_welcome_divider(source_pages: list[Tag], soup: BeautifulSoup) -> Tag:
    page = soup.new_tag("div")
    page["class"] = ["page", "welcome-divider"]
    page["data-role"] = "welcome-section-parity-divider"

    map_image = copy.deepcopy(source_pages[3].select_one(".map-big"))
    if map_image is None:
        raise RuntimeError("Source page 4 is missing the map image")
    map_image["class"] = ["divider-map"]
    page.append(map_image)

    safe = soup.new_tag("div")
    safe["class"] = ["safe"]
    kicker = soup.new_tag("p")
    kicker["class"] = ["divider-kicker"]
    kicker.string = "Приветственные слова"
    heading = soup.new_tag("h2")
    heading.append("Дети героев.")
    heading.append(soup.new_tag("br"))
    heading_subtitle = soup.new_tag("span")
    heading_subtitle.string = "Письма, которые объединяют"
    heading.append(heading_subtitle)
    sub = soup.new_tag("p")
    sub["class"] = ["divider-sub"]
    sub.string = "«Диалог поколений. Герои и дети»"
    safe.extend([kicker, heading, sub])
    page.append(safe)

    listing = soup.new_tag("div")
    listing["class"] = ["welcome-index"]
    for number, source_number in enumerate((5, 7, 9, 13, 15), start=1):
        meta = source_pages[source_number - 1].select_one(".vip-meta")
        if meta is None:
            raise RuntimeError(f"Source page {source_number} is missing VIP metadata")
        article = soup.new_tag("article")
        index = soup.new_tag("span")
        index["class"] = ["welcome-index-num"]
        index.string = f"{number:02d}"
        name = soup.new_tag("h3")
        name.string = meta.select_one("h1").get_text(" ", strip=True)
        organization = soup.new_tag("p")
        organization.string = meta.select_one(".kicker").get_text(" ", strip=True)
        article.extend([index, name, organization])
        listing.append(article)
    page.append(listing)

    folio = soup.new_tag("span")
    folio["class"] = ["folio"]
    run = soup.new_tag("span")
    run["class"] = ["run"]
    run.string = "Приветственные слова · раздел"
    page.extend([folio, run])
    return page


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
    source_pages = v22.direct_pages(soup)
    if len(source_pages) < 20:
        raise RuntimeError(f"Expected at least 20 source pages, got {len(source_pages)}")

    title = soup.select_one("title")
    if title:
        title.string = "Письма памяти — V23, компактное вступление"
    style = soup.select_one("style")
    if style is None:
        raise RuntimeError("Source document has no style element")
    style.append(v22.COMPACT_CSS)
    style.append(V23_CSS)

    compact_by_slug = {
        slug: v22.combined_profile(source_pages, spec, soup)
        for spec in v22.PROFILE_SPECS
        for slug in [spec[2]]
    }
    # Preserve the documentary pixels and turn the composition, not the
    # people: all three source portraits naturally face camera-left.
    for slug in ("shumilov", "makarychev", "tengebaeva"):
        compact_by_slug[slug]["class"].append("compact--portrait-right")
        compact_by_slug[slug]["data-portrait-direction"] = "toward-address"
    toc_pages = v22.make_toc_pages(soup, source_pages)

    ordered_pages = [
        copy.deepcopy(source_pages[0]),
        copy.deepcopy(source_pages[1]),
        make_geography_combined(source_pages, soup),
        make_decree_geography(source_pages, soup),
        compact_by_slug["shumilov"],
        copy.deepcopy(source_pages[10]),
        compact_by_slug["makarychev"],
        copy.deepcopy(source_pages[11]),
        compact_by_slug["belyaninov"],
        compact_by_slug["smirnova"],
        compact_by_slug["tengebaeva"],
        v22.make_adina_photo_page(soup),
        toc_pages[0],
        toc_pages[1],
    ]

    body = soup.body
    if body is None:
        raise RuntimeError("Source document has no body")
    body.clear()
    for preview_page, page in enumerate(ordered_pages, start=1):
        v22.reset_side(page, preview_page)
        for image in page.select('img[src^="assets/"]'):
            image["src"] = f'../print-v12/{image["src"]}'

    for index in range(0, len(ordered_pages), 2):
        sheet_class = "map-spread" if index == 2 else None
        v22.add_sheet(soup, body, ordered_pages[index], ordered_pages[index + 1], sheet_class)

    OUT_HTML.write_text(str(soup), encoding="utf-8")

    v21_families = json.loads(V21_TOC.read_text(encoding="utf-8"))["families"]
    page_plan = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/build_compact_intro_v23.py",
        "source_html": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "scope": "intro_only_families_untouched",
        "design_lock": "design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf",
        "preview": {"cover_included": True, "page_count": 14, "spread_count": 7},
        "production_interior": {
            "cover_included": False,
            "frontmatter_pages": 13,
            "first_family_page": 14,
            "first_family_side": "left",
            "page_saving_vs_v21": 6,
            "toc_pages": [12, 13],
            "parity_note": "The cover is external. Interior odd pages are right; even pages are left.",
        },
        "pages": [
            {"preview_page": 1, "production_interior_page": None, "role": "approved_cover", "source_pages": [1]},
            {"preview_page": 2, "production_interior_page": 1, "role": "partners", "source_pages": [2]},
            {
                "preview_page": 3,
                "production_interior_page": 2,
                "role": "project_geography_map",
                "source_pages": [3, 4],
            },
            {
                "preview_page": 4,
                "production_interior_page": 3,
                "role": "official_decree",
                "source_pages": [4],
                "document": "assets/intro-decree/official/decree-962-official.pdf",
            },
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
