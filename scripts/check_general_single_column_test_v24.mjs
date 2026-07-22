#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

const input = path.resolve(
  process.argv[2] || "design/prototypes/print-v24-general-single-column-test/general-single-column-test.html",
);

const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 900 } });
  await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "print" });
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(() => {
    const pages = [...document.querySelectorAll(".general-ref-page")];
    const overflow = [];
    const brokenImages = [];
    for (const node of document.querySelectorAll(".general-copy, .general-letter, .general-profile")) {
      if (node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1) {
        overflow.push({
          className: node.className,
          clientWidth: node.clientWidth,
          scrollWidth: node.scrollWidth,
          clientHeight: node.clientHeight,
          scrollHeight: node.scrollHeight,
        });
      }
    }
    for (const image of document.images) {
      if (!image.complete || image.naturalWidth === 0 || image.naturalHeight === 0) {
        brokenImages.push(image.getAttribute("src"));
      }
    }
    return {
      pages: pages.length,
      columns: [...document.querySelectorAll(".general-copy")].map((node) => getComputedStyle(node).columns),
      bodyFontSizes: [...document.querySelectorAll(".general-copy")].map((node) => getComputedStyle(node).fontSize),
      overflow,
      brokenImages,
    };
  });

  const failed =
    result.pages !== 2 ||
    result.overflow.length > 0 ||
    result.brokenImages.length > 0 ||
    result.columns.some((value) => value !== "auto");
  console.log(JSON.stringify(result, null, 2));
  if (failed) process.exitCode = 1;
} finally {
  await browser.close();
}
