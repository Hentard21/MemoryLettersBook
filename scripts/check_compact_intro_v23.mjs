#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

function inputFromArgs(argv) {
  const index = argv.indexOf("--input");
  if (index < 0 || !argv[index + 1]) {
    throw new Error("Usage: node scripts/check_compact_intro_v23.mjs --input <html>");
  }
  return path.resolve(argv[index + 1]);
}

function outputFromArgs(argv) {
  const index = argv.indexOf("--output");
  return index >= 0 && argv[index + 1] ? path.resolve(argv[index + 1]) : null;
}

function rectData(rect) {
  return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
}

async function main() {
  const input = inputFromArgs(process.argv.slice(2));
  const output = outputFromArgs(process.argv.slice(2));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 2200, height: 900 } });
    await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
    await page.emulateMedia({ media: "print" });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(
        [...document.images].map((image) =>
          image.complete ? Promise.resolve() : image.decode().catch(() => undefined),
        ),
      );
    });

    const result = await page.evaluate(() => {
      const pages = [...document.querySelectorAll(".page")];
      const pageNumber = (element) => pages.indexOf(element.closest(".page")) + 1;
      const rect = (element) => {
        const value = element.getBoundingClientRect();
        return { left: value.left, right: value.right, top: value.top, bottom: value.bottom };
      };
      const overlaps = (a, b, gap = 0) =>
        a.left < b.right + gap && a.right + gap > b.left && a.top < b.bottom && a.bottom > b.top;

      const overflow = [...document.querySelectorAll(
        ".compact-quote-flow,.compact-quote,.contents-compact .safe,.decree-panel,.decree-column,.welcome-divider",
      )]
        .map((element) => ({
          page: pageNumber(element),
          selector: element.className,
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          clientHeight: element.clientHeight,
          scrollHeight: element.scrollHeight,
        }))
        .filter(
          (item) =>
            item.scrollWidth > item.clientWidth + 2 || item.scrollHeight > item.clientHeight + 2,
        );

      const brokenImages = [...document.images]
        .filter((image) => !image.complete || image.naturalWidth === 0 || image.naturalHeight === 0)
        .map((image) => ({ page: pageNumber(image), src: image.currentSrc || image.src }));

      const previewParityErrors = pages
        .map((element, index) => ({
          previewPage: index + 1,
          actual: element.classList.contains("left")
            ? "left"
            : element.classList.contains("right")
              ? "right"
              : "none",
          expected: (index + 1) % 2 ? "left" : "right",
        }))
        .filter((item) => item.actual !== item.expected);

      const productionParityErrors = pages.slice(1)
        .map((element, index) => ({
          interiorPage: index + 1,
          actual: element.classList.contains("left")
            ? "left"
            : element.classList.contains("right")
              ? "right"
              : "none",
          expected: (index + 1) % 2 ? "right" : "left",
        }))
        .filter((item) => item.actual !== item.expected);

      const moduleCollisions = [...document.querySelectorAll(".compact-welcome")].flatMap((profile) => {
        const quote = profile.querySelector(".compact-quote");
        const meta = profile.querySelector(".vip-meta");
        if (!quote || !meta) return [{ page: pageNumber(profile), type: "missing_module" }];
        const quoteRect = rect(quote);
        const metaRect = rect(meta);
        return overlaps(metaRect, quoteRect, 4)
          ? [{ page: pageNumber(profile), type: "metadata_quote", meta: metaRect, quote: quoteRect }]
          : [];
      });

      const portraitQuoteCuts = [...document.querySelectorAll(
        ".compact-welcome[data-portrait-direction='toward-address']",
      )].flatMap((profile) => {
        const quote = profile.querySelector(".compact-quote");
        const portrait = profile.querySelector(".vip-cutout");
        if (!quote || !portrait) return [{ page: pageNumber(profile), type: "missing_portrait" }];
        const quoteRect = rect(quote);
        const portraitRect = rect(portrait);
        const horizontalOverlap =
          portraitRect.left < quoteRect.right + 2 && portraitRect.right + 2 > quoteRect.left;
        return horizontalOverlap
          ? [{ page: pageNumber(profile), portrait: portraitRect, quote: quoteRect }]
          : [];
      });

      const portraitDirectionErrors = ["shumilov", "makarychev", "tengebaeva"].flatMap((slug) => {
        const profile = document.querySelector(`.compact--${slug}`);
        if (!profile || profile.dataset.portraitDirection !== "toward-address") {
          return [{ slug, type: "missing_direction_lock" }];
        }
        const portrait = profile.querySelector(".vip-cutout");
        const quote = profile.querySelector(".compact-quote");
        if (!portrait || !quote) return [{ slug, type: "missing_module" }];
        return rect(portrait).left > rect(quote).right
          ? []
          : [{ slug, type: "portrait_not_on_address-facing_side" }];
      });

      const ungroundedPortraits = [...document.querySelectorAll(".compact-welcome .vip-cutout")]
        .map((portrait) => {
          const pageRect = rect(portrait.closest(".page"));
          const portraitRect = rect(portrait);
          return { page: pageNumber(portrait), delta: Math.abs(pageRect.bottom - portraitRect.bottom) };
        })
        .filter((item) => item.delta > 8);

      const decreeText = document.querySelector(".decree-geography")?.innerText ?? "";
      const legacyHeadlineCount = [...document.querySelectorAll("h1,h2")].filter((heading) =>
        heading.innerText.replace(/\s+/g, " ").trim().toLowerCase().includes("вся россия — одна память"),
      ).length;
      const requiredDecreePhrases = [
        "74",
        "78",
        "Указ Президента Российской Федерации от 25 декабря 2025 года № 962",
        "О проведении в Российской Федерации Года единства народов России",
        "Провести в 2026 году в Российской Федерации Год единства народов России.",
        "Настоящий Указ вступает в силу со дня его подписания.",
      ];
      const missingDecreePhrases = requiredDecreePhrases.filter((phrase) => !decreeText.includes(phrase));

      const quotePages = [...document.querySelectorAll(".compact-welcome")].map((element) => ({
        page: pageNumber(element),
        sourcePages: element.dataset.sourcePages,
        paragraphs: element.querySelectorAll(".compact-quote-flow > p").length,
        textLength: element.querySelector(".compact-quote-flow")?.innerText.trim().length ?? 0,
      }));

      return {
        sheets: document.querySelectorAll(".sheet").length,
        pages: pages.length,
        compactProfiles: quotePages.length,
        quotePages,
        signatureImages: document.querySelectorAll(".compact-attribution .signature-ink").length,
        shortExcerptCards: document.querySelectorAll(".vip-excerpt").length,
        decreeGeographyPages: document.querySelectorAll(
          ".decree-geography[data-document-status='verified-official-facsimile']",
        ).length,
        decreeMapImages: document.querySelectorAll(".decree-geography .decree-map").length,
        decreeFacsimiles: document.querySelectorAll(".decree-geography .decree-facsimiles img").length,
        generatedDecreeTextImages: document.querySelectorAll(".decree-geography img[data-generated-text]").length,
        missingDecreePhrases,
        geographyPages: document.querySelectorAll(".geography-combined").length,
        geographyMaps: document.querySelectorAll(".geography-combined .map-big").length,
        geographyStats: document.querySelectorAll(".geography-combined .map-stat").length,
        welcomeDividers: document.querySelectorAll(".welcome-divider[data-role='welcome-section-parity-divider']").length,
        legacyHeadlineCount,
        welcomeIndexItems: document.querySelectorAll(".welcome-divider .welcome-index article").length,
        tocRows: document.querySelectorAll(".contents-compact .toc-row").length,
        tocPages: [...document.querySelectorAll(".contents-compact")].map(pageNumber),
        firstFamilyInteriorPage: pages.length,
        firstFamilySide: pages.length % 2 ? "right" : "left",
        overflow,
        brokenImages,
        previewParityErrors,
        productionParityErrors,
        moduleCollisions,
        portraitQuoteCuts,
        portraitDirectionErrors,
        ungroundedPortraits,
      };
    });

    const blockers = [];
    if (result.sheets !== 7 || result.pages !== 14) blockers.push("EXPECTED_7_SPREADS_14_PREVIEW_PAGES");
    if (result.compactProfiles !== 5) blockers.push("EXPECTED_5_COMPACT_PROFILES");
    if (result.signatureImages !== 2) blockers.push("EXPECTED_2_VERIFIED_SIGNATURES");
    if (result.shortExcerptCards !== 0) blockers.push("SHORT_EXCERPTS_NOT_REMOVED");
    if (result.decreeGeographyPages !== 1 || result.decreeMapImages !== 1) blockers.push("DECREE_GEOGRAPHY_PAGE_MISSING");
    if (result.decreeFacsimiles !== 2) blockers.push("OFFICIAL_DECREE_FACSIMILES_MISSING");
    if (result.generatedDecreeTextImages !== 0) blockers.push("GENERATED_OFFICIAL_TEXT_FORBIDDEN");
    if (result.missingDecreePhrases.length) blockers.push("OFFICIAL_DECREE_TEXT_MISSING");
    if (result.geographyPages !== 1 || result.geographyMaps !== 1 || result.geographyStats !== 3) blockers.push("PROJECT_GEOGRAPHY_MAP_MISSING");
    if (result.welcomeDividers !== 0 || result.welcomeIndexItems !== 0) blockers.push("OBSOLETE_WELCOME_DIVIDER_PRESENT");
    if (result.legacyHeadlineCount !== 0) blockers.push("LEGACY_TRAGIC_HEADLINE_PRESENT");
    if (result.tocRows !== 74 || result.tocPages.join(",") !== "13,14") blockers.push("TOC_NOT_TWO_PAGE_SPREAD");
    if (result.firstFamilyInteriorPage !== 14 || result.firstFamilySide !== "left") blockers.push("FIRST_FAMILY_PARITY_ERROR");
    if (result.overflow.length) blockers.push("DOM_OVERFLOW");
    if (result.brokenImages.length) blockers.push("BROKEN_IMAGES");
    if (result.previewParityErrors.length || result.productionParityErrors.length) blockers.push("PAGE_PARITY_ERROR");
    if (result.moduleCollisions.length) blockers.push("METADATA_QUOTE_COLLISION");
    if (result.portraitQuoteCuts.length) blockers.push("PORTRAIT_QUOTE_HARD_CUT");
    if (result.portraitDirectionErrors.length) blockers.push("PORTRAIT_DIRECTION_ERROR");
    if (result.ungroundedPortraits.length) blockers.push("UNGROUNDED_PORTRAIT");

    result.blockers = blockers;
    result.status = blockers.length ? "blocked" : "pass";
    const serialized = `${JSON.stringify(result, null, 2)}\n`;
    if (output) fs.writeFileSync(output, serialized, "utf8");
    process.stdout.write(serialized);
    if (blockers.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
