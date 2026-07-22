#!/usr/bin/env python3
"""Build the V29 alternate intro with five continuous greeting pages.

The V23 compact intro remains the factual source.  Only the five authored
greeting pages are re-composed; geography, decree, chronicle, contents and all
family material keep their existing pagination and assets.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/prototypes/print-v23/interior-compact-v23.html"
SOURCE_PLAN = ROOT / "design/prototypes/print-v23/compact-intro-page-plan.json"
OUT_DIR = ROOT / "design/prototypes/print-v29-single-column-welcome"
OUT_HTML = OUT_DIR / "interior-single-column-welcome-v29.html"
OUT_PLAN = OUT_DIR / "intro-page-plan-v29.json"
SLUGS = ("shumilov", "makarychev", "belyaninov", "smirnova", "tengebaeva")
YEAR_NAME_REPLACEMENTS = {
    "Году народного единства": "Году единства народов России",
    "Года народного единства": "Года единства народов России",
    "Годом народного единства": "Годом единства народов России",
}


V29_CSS = r"""

/* V29 alternate greeting system. Only the five authored intro pages change. */
.welcome-single-column{
  --welcome-copy-size:9.75pt;
  --welcome-copy-leading:1.32;
  isolation:isolate;
  overflow:hidden;
  background:
    radial-gradient(circle at 82% 22%,rgba(62,91,123,.065),transparent 31%),
    linear-gradient(135deg,#f8f7f3 0%,#f1f2ef 100%);
}
.welcome-single-column::before{
  content:"";
  position:absolute;
  right:-10mm;
  bottom:2mm;
  width:132mm;
  height:96mm;
  background:url('../print-v12/assets/maps/russia-action-participants-schematic-commons.svg') center/contain no-repeat;
  opacity:.027;
  filter:grayscale(1);
  z-index:0;
}
.welcome-letter{
  position:absolute;
  left:19mm;
  right:22mm;
  top:11mm;
  bottom:14mm;
  z-index:5;
  overflow:hidden;
  color:#30353b;
}
.welcome-single-column.right .welcome-letter{left:22mm;right:17mm}
.welcome-profile{
  position:relative;
  z-index:7;
  float:right;
  width:50mm;
  margin:2mm 0 5mm 8mm;
}
.welcome-portrait-frame{
  position:relative;
  width:50mm;
  height:67mm;
  overflow:hidden;
  background:
    radial-gradient(circle at 52% 28%,rgba(255,255,255,.96),rgba(226,232,235,.92) 62%,rgba(207,216,221,.91));
  border:.25mm solid rgba(34,59,94,.18);
  box-shadow:0 .8mm 2.4mm rgba(38,43,48,.11);
}
.welcome-portrait-frame::after{
  content:"";
  position:absolute;
  left:0;
  right:0;
  bottom:0;
  height:.9mm;
  background:var(--accent_burgundy);
  z-index:3;
}
.welcome-portrait-frame img{
  position:absolute;
  left:-4mm;
  bottom:-1mm;
  width:58mm;
  height:70mm;
  display:block;
  object-fit:contain;
  object-position:center bottom;
}
.welcome-profile h1{
  margin-top:4mm;
  font:750 14.4pt/1.07 var(--head);
  letter-spacing:-.015em;
  color:var(--primary_navy);
}
.welcome-profile .organization{
  margin-top:2mm;
  font:700 5pt/1.28 var(--head);
  letter-spacing:.095em;
  text-transform:uppercase;
  color:var(--accent_burgundy);
}
.welcome-profile .role{
  margin-top:2.3mm;
  font:500 6.6pt/1.34 var(--body);
  color:var(--secondary_text);
}
.welcome-profile .profile-rule{
  width:11mm;
  height:.5mm;
  margin-top:3.5mm;
  background:var(--gold_accent);
}
.welcome-eyebrow{
  margin:0;
  font:750 6.2pt/1.2 var(--head);
  letter-spacing:.16em;
  text-transform:uppercase;
  color:var(--accent_burgundy);
}
.welcome-eyebrow::after{
  content:"";
  display:block;
  width:12mm;
  height:.55mm;
  margin-top:3mm;
  background:var(--accent_burgundy);
}
.welcome-salutation{
  margin:3mm 0 3mm;
  max-width:170mm;
  font:400 18.5pt/1.05 var(--script);
  color:var(--primary_navy);
}
.welcome-copy{
  font:450 var(--welcome-copy-size)/var(--welcome-copy-leading) var(--body);
  color:#30353b;
  hyphens:auto;
  text-wrap:pretty;
}
.welcome-copy p{margin:0 0 2.15mm;orphans:2;widows:2}
.welcome-copy p:first-child::first-letter{
  float:left;
  margin:.7mm 1.7mm 0 0;
  font:800 21pt/.78 var(--head);
  color:var(--accent_burgundy);
}
.welcome-ending{
  margin:2.4mm 0 0;
  font:400 13.8pt/1.08 var(--script);
  color:var(--accent_burgundy);
}
.welcome-attribution{
  clear:both;
  display:grid;
  grid-template-columns:30mm minmax(0,1fr);
  align-items:center;
  gap:4mm;
  min-height:17mm;
  margin-top:3mm;
  padding-top:2.5mm;
  border-top:.25mm solid rgba(34,59,94,.17);
}
.welcome-attribution:not(:has(.signature-proof)){grid-template-columns:1fr}
.welcome-attribution .signature-proof{
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  justify-content:center;
  gap:.7mm;
}
.welcome-attribution .signature-ink{
  display:block;
  width:29mm;
  height:10.5mm;
  object-fit:contain;
  object-position:left center;
}
.welcome-attribution .signature-proof span{
  font:650 4pt/1 var(--head);
  letter-spacing:.09em;
  text-transform:uppercase;
  color:var(--secondary_text);
}
.welcome-attribution>p{
  margin:0;
  font:500 6.15pt/1.28 var(--body);
  color:var(--secondary_text);
}
.welcome-single--shumilov{--welcome-copy-size:10.7pt;--welcome-copy-leading:1.33}
.welcome-single--makarychev{--welcome-copy-size:10.8pt;--welcome-copy-leading:1.33}
.welcome-single--belyaninov{--welcome-copy-size:11.4pt;--welcome-copy-leading:1.34}
.welcome-single--smirnova{--welcome-copy-size:10.4pt;--welcome-copy-leading:1.32}
.welcome-single--tengebaeva{--welcome-copy-size:10pt;--welcome-copy-leading:1.3}
.welcome-single-column .folio,.welcome-single-column .run{bottom:8mm}
.welcome-single-column .run{color:rgba(70,78,88,.72)}
"""


def text_list(flow: Tag) -> list[str]:
    return [node.get_text(" ", strip=True) for node in flow.find_all("p", recursive=False)]


def build_profile(soup: BeautifulSoup, meta: Tag, portrait: Tag) -> Tag:
    profile = soup.new_tag("aside")
    profile["class"] = ["welcome-profile"]

    frame = soup.new_tag("div")
    frame["class"] = ["welcome-portrait-frame"]
    image = copy.deepcopy(portrait)
    image["class"] = ["welcome-portrait"]
    frame.append(image)
    profile.append(frame)

    name = soup.new_tag("h1")
    name.string = meta.select_one("h1").get_text(" ", strip=True)
    profile.append(name)

    organization = soup.new_tag("p")
    organization["class"] = ["organization"]
    organization.string = meta.select_one(".kicker").get_text(" ", strip=True)
    profile.append(organization)

    role = soup.new_tag("p")
    role["class"] = ["role"]
    role.string = meta.select_one(".role").get_text(" ", strip=True)
    profile.append(role)

    rule = soup.new_tag("div")
    rule["class"] = ["profile-rule"]
    profile.append(rule)
    return profile


def build_page(soup: BeautifulSoup, source: Tag, slug: str) -> tuple[Tag, list[str]]:
    meta = source.select_one(".vip-meta")
    flow = source.select_one(".compact-quote-flow")
    attribution = source.select_one(".compact-attribution")
    portrait = source.select_one(".vip-cutout")
    if None in (meta, flow, attribution, portrait):
        raise RuntimeError(f"Incomplete V23 greeting source for {slug}")
    paragraphs = flow.find_all("p", recursive=False)
    if len(paragraphs) < 3:
        raise RuntimeError(f"Greeting for {slug} is unexpectedly short")
    original_text = text_list(flow)

    side = "right" if "right" in source.get("class", []) else "left"
    page = soup.new_tag("div")
    page["class"] = [
        "page",
        side,
        "welcome-single-column",
        f"welcome-single--{slug}",
    ]
    page["data-source-pages"] = source.get("data-source-pages", "")
    page["data-layout"] = "single-column-continuous-v29"
    page["data-content-lock"] = "full-authored-address-verbatim"

    letter = soup.new_tag("article")
    letter["class"] = ["welcome-letter"]
    letter.append(build_profile(soup, meta, portrait))

    eyebrow = soup.new_tag("p")
    eyebrow["class"] = ["welcome-eyebrow"]
    eyebrow.string = "Приветствие"
    letter.append(eyebrow)

    salutation = soup.new_tag("h2")
    salutation["class"] = ["welcome-salutation"]
    salutation.string = original_text[0]
    letter.append(salutation)

    body = soup.new_tag("div")
    body["class"] = ["welcome-copy"]
    for paragraph in paragraphs[1:-1]:
        body.append(copy.deepcopy(paragraph))
    letter.append(body)

    ending = soup.new_tag("p")
    ending["class"] = ["welcome-ending"]
    ending.string = original_text[-1]
    letter.append(ending)

    footer = copy.deepcopy(attribution)
    footer["class"] = ["welcome-attribution"]
    letter.append(footer)
    page.append(letter)

    folio = copy.deepcopy(source.select_one(".folio"))
    run = copy.deepcopy(source.select_one(".run"))
    if folio is not None:
        page.append(folio)
    if run is None:
        run = soup.new_tag("span")
        run["class"] = ["run"]
    run.string = "Приветственное слово · полный текст"
    page.append(run)
    return page, original_text


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
    # Keep the generated V29 source factually correct on disk instead of
    # relying on the later production patch to repair obsolete wording.
    for node in soup.find_all(
        string=lambda value: value
        and any(source in value for source in YEAR_NAME_REPLACEMENTS)
    ):
        corrected = str(node)
        for source, target in YEAR_NAME_REPLACEMENTS.items():
            corrected = corrected.replace(source, target)
        node.replace_with(corrected)
    style = soup.select_one("style")
    if style is None:
        raise RuntimeError("V23 source has no style element")
    style.append(V29_CSS)
    title = soup.select_one("title")
    if title is not None:
        title.string = "Письма памяти — V29, одноколоночные приветствия"

    expected: dict[str, list[str]] = {}
    for slug in SLUGS:
        source = soup.select_one(f".compact--{slug}")
        if source is None:
            raise RuntimeError(f"Missing V23 greeting source for {slug}")
        replacement, original_text = build_page(soup, source, slug)
        expected[slug] = original_text
        source.replace_with(replacement)

    preview_pages = [
        page
        for sheet in soup.select("section.sheet")
        for page in sheet.select(":scope > .page")
    ]
    if len(preview_pages) != 14:
        raise RuntimeError(f"Expected cover plus 13 intro pages, found {len(preview_pages)}")
    if len(soup.select(".welcome-single-column")) != len(SLUGS):
        raise RuntimeError("Not all greeting pages were converted")
    for slug, original in expected.items():
        page = soup.select_one(f".welcome-single--{slug}")
        rendered = [page.select_one(".welcome-salutation").get_text(" ", strip=True)]
        rendered.extend(
            node.get_text(" ", strip=True)
            for node in page.select(".welcome-copy > p")
        )
        rendered.append(page.select_one(".welcome-ending").get_text(" ", strip=True))
        if rendered != original:
            raise RuntimeError(f"Authored greeting changed while rebuilding {slug}")

    OUT_HTML.write_text(str(soup), encoding="utf-8")
    plan = json.loads(SOURCE_PLAN.read_text(encoding="utf-8-sig"))
    plan["schema_version"] = 2
    plan["generated_at"] = datetime.now(timezone.utc).isoformat()
    plan["generator"] = "scripts/build_intro_single_column_v29.py"
    plan["source_html"] = SOURCE.relative_to(ROOT).as_posix()
    plan["scope"] = "five_intro_greetings_only_families_untouched"
    plan["alternate_design"] = {
        "base": "V24 general single-column proof",
        "converted_slugs": list(SLUGS),
        "content_rule": "full authored address, verbatim, one continuous column",
        "pagination_changed": False,
    }
    OUT_PLAN.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUT_HTML)
    print(OUT_PLAN)


if __name__ == "__main__":
    build()
