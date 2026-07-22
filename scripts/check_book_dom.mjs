#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

function valueAfter(argv, name) {
  const index = argv.indexOf(name);
  return index >= 0 ? argv[index + 1] : undefined;
}

function inputsFromArgs(argv) {
  const raw = valueAfter(argv, "--input");
  if (!raw) throw new Error("Usage: node scripts/check_book_dom.mjs --input <html-or-directory>");
  const resolved = path.resolve(raw);
  if (fs.statSync(resolved).isFile()) return [resolved];
  const results = [];
  for (const entry of fs.readdirSync(resolved, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const candidate = path.join(resolved, entry.name, "index.html");
    if (fs.existsSync(candidate)) results.push(candidate);
  }
  return results.sort();
}

async function inspect(browser, input) {
  const page = await browser.newPage();
  try {
    await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
    await page.emulateMedia({ media: "print" });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map((image) => image.complete ? Promise.resolve() : image.decode().catch(() => undefined)));
    });
    return await page.evaluate(() => {
      const mm = 96 / 25.4;
      const pages = [...document.querySelectorAll(".page")];
      const pageNumber = (element) => Number(element.closest(".page")?.dataset.page || 0);
      const overflow = [...document.querySelectorAll(".doc-paper,.doc-copy,.paper,.copy,.gallery-grid,.standard-media,.hero-quote,.review-paper,.doc-side-media,.doc-scan-figure")]
        .map((element) => ({
          page: pageNumber(element), selector: element.className,
          clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
          clientHeight: element.clientHeight, scrollHeight: element.scrollHeight,
        }))
        .filter((item) => item.scrollWidth > item.clientWidth + 2 || item.scrollHeight > item.clientHeight + 2);
      const brokenImages = [...document.images]
        .filter((image) => !image.complete || image.naturalWidth === 0 || image.naturalHeight === 0)
        .map((image) => ({ page: pageNumber(image), src: image.currentSrc || image.src }));
      const forbidden = ["V4", "V5", "SKELETON", "NOT FOR PRODUCTION", "PDF_REFERENCE", "FACT_LOCKED", "REVIEW_REQUIRED", "[край обрезан]", "[подпись"];
      const bodyText = document.body.innerText;
      const forbiddenVisible = forbidden.filter((marker) => bodyText.includes(marker));
      const tooSmallText = [...document.querySelectorAll(".doc-copy")]
        .map((element) => ({ page: pageNumber(element), pt: parseFloat(getComputedStyle(element).fontSize) * 0.75 }))
        .filter((item) => item.pt < 10.95);
      const safeSelectors = ".hero-meta,.hero-symbols,.hero-quote,.page-title,.doc-label,.doc-copy,.review-paper";
      const unsafeFold = [...document.querySelectorAll(safeSelectors)].flatMap((element) => {
        const host = element.closest(".page");
        if (!host) return [];
        const hostBox = host.getBoundingClientRect();
        const box = element.getBoundingClientRect();
        const isLeft = host.classList.contains("left");
        const bad = isLeft ? box.right > hostBox.right - 22 * mm + 2 : box.left < hostBox.left + 22 * mm - 2;
        return bad ? [{ page: pageNumber(element), selector: element.className, side: isLeft ? "left" : "right" }] : [];
      });
      const invalidParity = pages.map((element) => ({
        page: Number(element.dataset.page || 0),
        side: element.classList.contains("left") ? "left" : "right",
      })).filter((item) => !item.page || (item.page % 2 === 0 ? item.side !== "left" : item.side !== "right"));
      const titleAuthorIssues = [...document.querySelectorAll(".generated-family-open .hero-meta .who")].flatMap((element) => {
        const host = element.closest(".page");
        if (!host) return [];
        const hostBox = host.getBoundingClientRect();
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        const exceedsProtectedColumn = !host.classList.contains("frozen-eugene-open") && box.right > hostBox.left + 120 * mm;
        const clipped = element.scrollWidth > element.clientWidth + 2 || element.scrollHeight > element.clientHeight + 2;
        const invisible = style.visibility === "hidden" || style.display === "none" || Number(style.opacity) < 0.8;
        return exceedsProtectedColumn || clipped || invisible
          ? [{ page: pageNumber(element), exceedsProtectedColumn, clipped, invisible }]
          : [];
      });
      const ghostLetterBackground = [...document.querySelectorAll(".doc-paper.has-visible-scan")]
        .filter((element) => getComputedStyle(element, "::before").display !== "none")
        .map((element) => ({ page: pageNumber(element), selector: element.className }));
      const nestedSideMedia = [...document.querySelectorAll(".doc-side-media figure")]
        .map((element) => ({ page: pageNumber(element), selector: element.className }));
      const extendedContinuityIssues = pages.flatMap((host) => {
        const thread = host.querySelector(".family-thread-run");
        const isExtended = host.classList.contains("extended-family-page");
        if (!isExtended) {
          return thread ? [{ page: pageNumber(host), reason: "thread-on-standard-page" }] : [];
        }
        if (!thread) return [{ page: pageNumber(host), reason: "missing-thread" }];
        const hero = host.dataset.hero || "";
        const threadHero = thread.dataset.familyThread || "";
        const spread = thread.dataset.familySpread || "";
        const name = thread.querySelector(".thread-name")?.textContent?.trim() || "";
        const region = thread.querySelector(".thread-region")?.textContent?.trim() || "";
        const hostBox = host.getBoundingClientRect();
        const box = thread.getBoundingClientRect();
        const folio = host.querySelector(".folio")?.getBoundingClientRect();
        const outside = box.left < hostBox.left || box.right > hostBox.right || box.bottom > hostBox.bottom;
        const folioOverlap = Boolean(folio && !(box.right < folio.left || box.left > folio.right || box.bottom < folio.top || box.top > folio.bottom));
        return hero !== threadHero || !/^\d+\/\d+$/.test(spread) || !name || !region || outside || folioOverlap
          ? [{ page: pageNumber(host), reason: "invalid-thread", hero, threadHero, spread, name, region, outside, folioOverlap }]
          : [];
      });
      return { input: document.location.pathname, pageCount: pages.length, overflow, brokenImages, forbiddenVisible, tooSmallText, unsafeFold, invalidParity, titleAuthorIssues, ghostLetterBackground, nestedSideMedia, extendedContinuityIssues };
    });
  } finally {
    await page.close();
  }
}

async function main() {
  const inputs = inputsFromArgs(process.argv.slice(2));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const results = [];
    for (const input of inputs) results.push(await inspect(browser, input));
    process.stdout.write(`${JSON.stringify({ checked: results.length, results })}\n`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; });
