#!/usr/bin/env python3
"""Build an isolated single-column greeting proof for the two generals.

The approved V23 intro and all family templates remain untouched.  This proof
only tests the client's reference principle: a restrained portrait rail, one
continuous readable text column and the authentic signature beside the full
address.
"""

from __future__ import annotations

import copy
from pathlib import Path

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/prototypes/print-v23/interior-compact-v23.html"
OUT_DIR = ROOT / "design/prototypes/print-v24-general-single-column-test"
OUT_HTML = OUT_DIR / "general-single-column-test.html"


TEST_CSS = r"""

/* V24 isolated greeting experiment. V23 and the family templates are not changed. */
.general-ref-page{
  isolation:isolate;
  overflow:hidden;
  background:
    radial-gradient(circle at 82% 24%,rgba(64,92,123,.07),transparent 31%),
    linear-gradient(135deg,#f7f6f2 0%,#f0f1ef 100%);
}
.general-ref-page::before{
  content:"";
  position:absolute;
  right:-11mm;
  bottom:5mm;
  width:126mm;
  height:93mm;
  background:url('../print-v12/assets/maps/russia-action-participants-schematic-commons.svg') center/contain no-repeat;
  opacity:.035;
  filter:grayscale(1);
  z-index:0;
}
.general-letter{
  position:absolute;
  left:20mm;
  right:84mm;
  top:12mm;
  bottom:14mm;
  z-index:5;
  display:grid;
  grid-template-rows:auto auto minmax(0,1fr) auto auto;
  align-content:stretch;
  gap:2mm;
}
.right .general-letter{left:22mm;right:78mm}
.general-eyebrow{
  font:750 6.2pt/1.2 var(--head);
  letter-spacing:.16em;
  text-transform:uppercase;
  color:var(--accent_burgundy);
}
.general-eyebrow::after{
  content:"";
  display:block;
  width:12mm;
  height:.55mm;
  margin-top:3mm;
  background:var(--accent_burgundy);
}
.general-salutation{
  max-width:156mm;
  font:400 19pt/1.04 var(--script);
  color:var(--primary_navy);
}
.general-copy{
  min-height:0;
  overflow:hidden;
  padding-top:1mm;
  font:450 10.1pt/1.38 var(--body);
  color:#2f343b;
  hyphens:auto;
  text-wrap:pretty;
}
.general-copy p{margin:0 0 2.35mm;orphans:2;widows:2}
.general-copy p:first-child::first-letter{
  float:left;
  margin:.7mm 1.8mm 0 0;
  font:800 21pt/.78 var(--head);
  color:var(--accent_burgundy);
}
.general-ending{
  padding-top:1mm;
  font:400 14.2pt/1.05 var(--script);
  color:var(--accent_burgundy);
}
.general-attribution{
  display:grid;
  grid-template-columns:30mm minmax(0,1fr);
  align-items:center;
  gap:4mm;
  min-height:18mm;
  padding-top:3mm;
  border-top:.25mm solid rgba(34,59,94,.17);
}
.general-attribution .signature-proof{
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  justify-content:center;
  gap:.8mm;
}
.general-attribution .signature-ink{
  display:block;
  width:29mm;
  height:11mm;
  object-fit:contain;
  object-position:left center;
}
.general-attribution .signature-proof span{
  font:650 4.1pt/1 var(--head);
  letter-spacing:.09em;
  text-transform:uppercase;
  color:var(--secondary_text);
}
.general-attribution>p{
  font:500 6.25pt/1.3 var(--body);
  color:var(--secondary_text);
}
.general-profile{
  position:absolute;
  right:23mm;
  top:17mm;
  width:50mm;
  z-index:7;
}
.right .general-profile{right:17mm}
.general-portrait-frame{
  position:relative;
  width:50mm;
  height:68mm;
  overflow:hidden;
  background:
    radial-gradient(circle at 52% 28%,rgba(255,255,255,.94),rgba(225,231,234,.92) 62%,rgba(207,216,221,.92));
  border:.25mm solid rgba(34,59,94,.18);
  box-shadow:0 .8mm 2.4mm rgba(38,43,48,.12);
}
.general-portrait-frame::after{
  content:"";
  position:absolute;
  left:0;
  right:0;
  bottom:0;
  height:.9mm;
  background:var(--accent_burgundy);
  z-index:3;
}
.general-portrait-frame img{
  position:absolute;
  left:-4mm;
  bottom:-1mm;
  width:58mm;
  height:70mm;
  display:block;
  object-fit:contain;
  object-position:center bottom;
}
.general-profile h1{
  margin-top:5mm;
  font:750 14.8pt/1.08 var(--head);
  letter-spacing:-.015em;
  color:var(--primary_navy);
}
.general-profile .organization{
  margin-top:2mm;
  font:700 5.1pt/1.28 var(--head);
  letter-spacing:.1em;
  text-transform:uppercase;
  color:var(--accent_burgundy);
}
.general-profile .role{
  margin-top:2.6mm;
  font:500 6.8pt/1.36 var(--body);
  color:var(--secondary_text);
}
.general-profile .profile-rule{
  width:11mm;
  height:.5mm;
  margin-top:4mm;
  background:var(--gold_accent);
}
.general-ref-page .folio{bottom:8mm}
.general-ref-page .run{bottom:8mm}
.general-ref-page .run{color:rgba(70,78,88,.72)}
"""


def copy_children(source: Tag, target: Tag) -> None:
    for child in source.find_all(recursive=False):
        target.append(copy.deepcopy(child))


def build_page(soup: BeautifulSoup, slug: str, side: str, folio: str) -> Tag:
    source = soup.select_one(f".compact--{slug}")
    if source is None:
        raise RuntimeError(f"Missing V23 greeting source for {slug}")

    meta = source.select_one(".vip-meta")
    flow = source.select_one(".compact-quote-flow")
    attribution = source.select_one(".compact-attribution")
    portrait = source.select_one(".vip-cutout")
    if None in (meta, flow, attribution, portrait):
        raise RuntimeError(f"Incomplete V23 greeting source for {slug}")

    paragraphs = flow.find_all("p", recursive=False)
    if len(paragraphs) < 3:
        raise RuntimeError(f"Greeting for {slug} is unexpectedly short")

    page = soup.new_tag("div")
    page["class"] = ["page", side, "general-ref-page", f"general-ref--{slug}"]
    page["data-source"] = f"V23:{slug}"
    page["data-layout"] = "single-column-reference-test"

    letter = soup.new_tag("article")
    letter["class"] = ["general-letter"]

    eyebrow = soup.new_tag("p")
    eyebrow["class"] = ["general-eyebrow"]
    eyebrow.string = "Приветствие"
    letter.append(eyebrow)

    salutation = soup.new_tag("h2")
    salutation["class"] = ["general-salutation"]
    salutation.string = paragraphs[0].get_text(" ", strip=True)
    letter.append(salutation)

    body = soup.new_tag("div")
    body["class"] = ["general-copy"]
    for paragraph in paragraphs[1:-1]:
        body.append(copy.deepcopy(paragraph))
    letter.append(body)

    ending = soup.new_tag("p")
    ending["class"] = ["general-ending"]
    ending.string = paragraphs[-1].get_text(" ", strip=True)
    letter.append(ending)

    footer = copy.deepcopy(attribution)
    footer["class"] = ["general-attribution"]
    letter.append(footer)
    page.append(letter)

    profile = soup.new_tag("aside")
    profile["class"] = ["general-profile"]

    frame = soup.new_tag("div")
    frame["class"] = ["general-portrait-frame"]
    profile_portrait = copy.deepcopy(portrait)
    profile_portrait["class"] = ["general-portrait"]
    frame.append(profile_portrait)
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
    page.append(profile)

    folio_tag = soup.new_tag("span")
    folio_tag["class"] = ["folio"]
    folio_tag.string = folio
    run = soup.new_tag("span")
    run["class"] = ["run"]
    run.string = "Одноколоночная проба · полный текст"
    page.extend([folio_tag, run])
    return page


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
    title = soup.select_one("title")
    if title:
        title.string = "Письма памяти — V24, одноколоночная проба приветствий"
    style = soup.select_one("style")
    if style is None:
        raise RuntimeError("Source document has no style element")
    style.append(TEST_CSS)

    # Build the two pages while the V23 source nodes are still present. Clearing
    # the body first would also remove the canonical text and attribution data.
    left_page = build_page(soup, "shumilov", "left", "1")
    right_page = build_page(soup, "makarychev", "right", "2")

    body = soup.body
    if body is None:
        raise RuntimeError("Source document has no body")
    body.clear()

    sheet = soup.new_tag("section")
    sheet["class"] = ["sheet", "general-reference-test"]
    sheet.append(left_page)
    sheet.append(right_page)
    watermark = soup.new_tag("span")
    watermark["class"] = ["wm"]
    watermark.string = "ПРОТОТИП"
    sheet.append(watermark)
    body.append(sheet)

    OUT_HTML.write_text(str(soup), encoding="utf-8")
    print(OUT_HTML)


if __name__ == "__main__":
    build()
