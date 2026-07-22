#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

function inputFromArgs(argv) {
  const index = argv.indexOf("--input");
  if (index < 0 || !argv[index + 1]) {
    throw new Error("Usage: node scripts/check_compact_intro_v22.mjs --input <html>");
  }
  return path.resolve(argv[index + 1]);
}

async function main() {
  const input = inputFromArgs(process.argv.slice(2));
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
      const overflow = [...document.querySelectorAll(".compact-quote-flow,.compact-quote,.contents-compact .safe")]
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
      const parityErrors = pages
        .map((element, index) => ({
          page: index + 1,
          actual: element.classList.contains("left") ? "left" : element.classList.contains("right") ? "right" : "none",
          expected: (index + 1) % 2 ? "left" : "right",
        }))
        .filter((item) => item.actual !== item.expected);
      const quotePages = [...document.querySelectorAll(".compact-welcome")].map((element) => ({
        page: pageNumber(element),
        sourcePages: element.dataset.sourcePages,
        paragraphs: element.querySelectorAll(".compact-quote-flow > p").length,
        textLength: element.querySelector(".compact-quote-flow")?.innerText.trim().length ?? 0,
      }));
      return {
        input: document.location.pathname,
        sheets: document.querySelectorAll(".sheet").length,
        pages: pages.length,
        compactProfiles: quotePages.length,
        quotePages,
        signatureImages: document.querySelectorAll(".compact-attribution .signature-ink").length,
        shortExcerptCards: document.querySelectorAll(".vip-excerpt").length,
        tocRows: document.querySelectorAll(".contents-compact .toc-row").length,
        adinaPendingPages: document.querySelectorAll(".adina-photos[data-status='awaiting-owner-photos']").length,
        overflow,
        brokenImages,
        parityErrors,
      };
    });

    const blockers = [];
    if (result.sheets !== 7 || result.pages !== 14) blockers.push("EXPECTED_7_SPREADS_14_PAGES");
    if (result.compactProfiles !== 5) blockers.push("EXPECTED_5_COMPACT_PROFILES");
    if (result.signatureImages !== 2) blockers.push("EXPECTED_2_VERIFIED_SIGNATURES");
    if (result.shortExcerptCards !== 0) blockers.push("SHORT_EXCERPTS_NOT_REMOVED");
    if (result.tocRows !== 74) blockers.push("TOC_NOT_74_ROWS");
    if (result.adinaPendingPages !== 1) blockers.push("ADINA_PENDING_PAGE_MISSING");
    if (result.overflow.length) blockers.push("DOM_OVERFLOW");
    if (result.brokenImages.length) blockers.push("BROKEN_IMAGES");
    if (result.parityErrors.length) blockers.push("PAGE_PARITY_ERROR");
    result.blockers = blockers;
    result.status = blockers.length ? "blocked" : "pass";
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    if (blockers.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
