#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

const input = path.resolve(
  process.argv[2] ?? "design/prototypes/print-v23-back-matter/back-matter-v23.html",
);

const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1988, height: 779 } });
  await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(() => {
    const pages = [...document.querySelectorAll(".page")];
    const required = [
      ".editorial-label",
      ".left-heading",
      ".editorial-paper",
      ".thanks-card",
      ".closing",
    ];
    const missing = required.filter((selector) => !document.querySelector(selector));
    const overflows = pages.flatMap((pageNode, index) => {
      const pageRect = pageNode.getBoundingClientRect();
      return [...pageNode.querySelectorAll("h1,h2,p,li,.closing,.editorial-label")]
        .filter((node) => {
          const rect = node.getBoundingClientRect();
          return (
            rect.left < pageRect.left - 0.5 ||
            rect.right > pageRect.right + 0.5 ||
            rect.top < pageRect.top - 0.5 ||
            rect.bottom > pageRect.bottom + 0.5
          );
        })
        .map((node) => ({ page: index + 1, text: node.textContent.trim().slice(0, 80) }));
    });
    const images = [...document.images].map((image) => ({
      src: image.getAttribute("src"),
      complete: image.complete,
      naturalWidth: image.naturalWidth,
    }));
    return {
      pageCount: pages.length,
      sheetCount: document.querySelectorAll(".sheet").length,
      missing,
      overflows,
      images,
      attributionCount: [...document.querySelectorAll(".editorial-label")].filter(
        (node) => node.textContent.trim() === "От редакции",
      ).length,
      fonts: [...document.fonts].map((font) => ({ family: font.family, status: font.status })),
    };
  });

  console.log(JSON.stringify(result, null, 2));
  const brokenImages = result.images.filter((image) => !image.complete || image.naturalWidth === 0);
  if (
    result.pageCount !== 2 ||
    result.sheetCount !== 1 ||
    result.missing.length ||
    result.overflows.length ||
    brokenImages.length ||
    result.attributionCount !== 2
  ) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
