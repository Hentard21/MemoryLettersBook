#!/usr/bin/env node

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const require = createRequire(new URL("../.tools/playwright/package.json", import.meta.url));
const { chromium } = require("playwright");

const input = path.resolve(
  process.argv[2] ||
    "design/prototypes/print-v29-single-column-welcome/interior-single-column-welcome-v29.html",
);

const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 900 } });
  await page.goto(pathToFileURL(input).href, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "print" });
  await page.evaluate(() => document.fonts.ready);

  const result = await page.evaluate(() => {
    const rect = (node) => {
      const value = node.getBoundingClientRect();
      return {
        left: value.left,
        right: value.right,
        top: value.top,
        bottom: value.bottom,
        width: value.width,
        height: value.height,
      };
    };
    const intersects = (a, b) =>
      a.left < b.right - 0.5 && a.right > b.left + 0.5 &&
      a.top < b.bottom - 0.5 && a.bottom > b.top + 0.5;
    const textRects = (root) => {
      const output = [];
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (!node.nodeValue.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const value of range.getClientRects()) {
          if (value.width > 0 && value.height > 0) {
            output.push({ left: value.left, right: value.right, top: value.top, bottom: value.bottom });
          }
        }
      }
      return output;
    };

    const pages = [...document.querySelectorAll(".welcome-single-column")];
    const overflow = [];
    const textProfileOverlaps = [];
    const metrics = [];
    for (const node of pages) {
      const letter = node.querySelector(".welcome-letter");
      const profile = node.querySelector(".welcome-profile");
      const attribution = node.querySelector(".welcome-attribution");
      const copy = node.querySelector(".welcome-copy");
      const pageRect = rect(node);
      const letterRect = rect(letter);
      const profileRect = rect(profile);
      const attributionRect = rect(attribution);
      for (const candidate of [letter, profile, copy, attribution]) {
        if (candidate.scrollHeight > candidate.clientHeight + 1 || candidate.scrollWidth > candidate.clientWidth + 1) {
          overflow.push({
            page: node.className,
            className: candidate.className,
            clientWidth: candidate.clientWidth,
            scrollWidth: candidate.scrollWidth,
            clientHeight: candidate.clientHeight,
            scrollHeight: candidate.scrollHeight,
          });
        }
      }
      const authored = node.querySelector(".welcome-letter");
      const authoredRects = [
        ...authored.querySelectorAll(
          ".welcome-eyebrow, .welcome-salutation, .welcome-copy, .welcome-ending, .welcome-attribution",
        ),
      ].flatMap(textRects);
      const overlaps = authoredRects.filter((value) => intersects(value, profileRect)).length;
      if (overlaps) textProfileOverlaps.push({ page: node.className, lineRects: overlaps });
      const pxPerMm = pageRect.width / 260;
      const leftInnerMm = (letterRect.left - pageRect.left) / pxPerMm;
      const rightInnerMm = (pageRect.right - profileRect.right) / pxPerMm;
      metrics.push({
        page: node.className,
        copyFontPx: Number.parseFloat(getComputedStyle(copy).fontSize),
        copyLineHeightPx: Number.parseFloat(getComputedStyle(copy).lineHeight),
        contentBottomGapMm: (letterRect.bottom - attributionRect.bottom) / pxPerMm,
        leftInnerMm,
        rightInnerMm,
        textLength: authored.innerText.replace(/\s+/g, " ").trim().length,
      });
    }

    const brokenImages = [...document.images]
      .filter((image) => !image.complete || image.naturalWidth === 0 || image.naturalHeight === 0)
      .map((image) => image.getAttribute("src"));
    return { pages: pages.length, metrics, overflow, textProfileOverlaps, brokenImages };
  });

  const failed =
    result.pages !== 5 ||
    result.overflow.length > 0 ||
    result.textProfileOverlaps.length > 0 ||
    result.brokenImages.length > 0 ||
    result.metrics.some((item) => item.contentBottomGapMm < -0.2);
  console.log(JSON.stringify({ status: failed ? "fail" : "pass", ...result }, null, 2));
  if (failed) process.exitCode = 1;
} finally {
  await browser.close();
}
