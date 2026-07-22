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
    throw new Error("Usage: node scripts/check_v21_dom.mjs --input <html>");
  }
  return path.resolve(argv[index + 1]);
}

async function main() {
  const input = inputFromArgs(process.argv.slice(2));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage();
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
      const allPages = [...document.querySelectorAll(".page")];
      const pageNumber = (element) => {
        const pageElement = element.closest(".page");
        if (!pageElement) return null;
        return Number(pageElement.dataset.page || allPages.indexOf(pageElement) + 1);
      };
      const overflow = [...document.querySelectorAll(".transcript-card,.document-module,.contents-page .safe")]
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
      const unsafeFlagships = [...document.querySelectorAll("img.hero-cutout")]
        .map((image) => ({
          page: pageNumber(image),
          src: image.currentSrc || image.src,
          objectFit: getComputedStyle(image).objectFit,
        }))
        .filter((item) => item.objectFit !== "contain");
      return {
        input: document.location.pathname,
        pageCount: allPages.length,
        checkedOverflowModules: document.querySelectorAll(
          ".transcript-card,.document-module,.contents-page .safe",
        ).length,
        flagshipCount: document.querySelectorAll("img.hero-cutout").length,
        overflow,
        brokenImages,
        unsafeFlagships,
      };
    });
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
