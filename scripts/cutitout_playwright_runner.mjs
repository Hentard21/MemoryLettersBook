#!/usr/bin/env node

import { existsSync, readdirSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const playwrightModule = path.resolve(
  scriptDirectory,
  '..',
  '.tools',
  'playwright',
  'node_modules',
  'playwright',
  'index.mjs',
);
const { chromium } = await import(`file:///${playwrightModule.replaceAll('\\', '/')}`);

function findInstalledChromium() {
  if (process.platform !== 'win32' || !process.env.LOCALAPPDATA) return undefined;
  const browserRoot = path.join(process.env.LOCALAPPDATA, 'ms-playwright');
  if (!existsSync(browserRoot)) return undefined;
  const candidates = readdirSync(browserRoot)
    .flatMap((directory) => [
      path.join(browserRoot, directory, 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
      path.join(browserRoot, directory, 'chrome-win64', 'chrome.exe'),
    ])
    .filter((candidate) => existsSync(candidate));
  return candidates.at(-1);
}

function parseArguments(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error(`Invalid argument sequence near ${key ?? '<end>'}`);
    }
    values.set(key.slice(2), value);
  }
  return values;
}

const args = parseArguments(process.argv.slice(2));
const url = args.get('url');
const jobsFile = args.get('jobs');
const timeout = Number(args.get('timeout') ?? '300000');

if (!url || !jobsFile) {
  throw new Error('Required arguments: --url, --jobs');
}

const jobs = JSON.parse(await readFile(jobsFile, 'utf8'));
if (!Array.isArray(jobs) || jobs.length === 0) {
  throw new Error('The --jobs file must contain a non-empty JSON array');
}
for (const [index, job] of jobs.entries()) {
  if (!job || typeof job.source !== 'string' || typeof job.output !== 'string') {
    throw new Error(`Invalid job at index ${index}: source and output are required`);
  }
  if (!existsSync(job.source)) {
    throw new Error(`Source does not exist: ${job.source}`);
  }
  await mkdir(path.dirname(job.output), { recursive: true });
}

const executablePath = findInstalledChromium();
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ acceptDownloads: true });
const browserErrors = [];
page.on('pageerror', (error) => browserErrors.push(error.message));

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 });
  const completed = [];
  const failed = [];

  for (const [index, job] of jobs.entries()) {
    const errorOffset = browserErrors.length;
    const startedAt = performance.now();
    try {
      if (index > 0) {
        await page.getByRole('button', { name: 'Start Over' }).click();
      }

      const fileInput = page.locator('input[type="file"]');
      await fileInput.waitFor({ state: 'attached', timeout: 30_000 });
      await fileInput.setInputFiles(job.source);

      const processingOverlay = page.getByText('Removing background...');
      await processingOverlay.waitFor({ state: 'visible', timeout: 30_000 }).catch(() => {});
      await processingOverlay.waitFor({ state: 'hidden', timeout });

      await page.waitForFunction(
        () => {
          const canvas = document.querySelector('canvas.relative.z-10');
          if (!(canvas instanceof HTMLCanvasElement) || canvas.width === 0 || canvas.height === 0) {
            return false;
          }
          const context = canvas.getContext('2d', { willReadFrequently: true });
          if (!context) return false;
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          const pixelCount = canvas.width * canvas.height;
          const stride = Math.max(1, Math.floor(pixelCount / 100_000));
          for (let pixel = 0; pixel < pixelCount; pixel += stride) {
            if (pixels[pixel * 4 + 3] < 250) return true;
          }
          return false;
        },
        undefined,
        { timeout },
      );

      const downloadPromise = page.waitForEvent('download', { timeout: 30_000 });
      await page.getByRole('button', { name: 'Download Image' }).click();
      const download = await downloadPromise;
      await download.saveAs(job.output);

      const canvasMetrics = await page.locator('canvas.relative.z-10').evaluate((canvas) => ({
        width: canvas.width,
        height: canvas.height,
      }));
      completed.push({
        hero_id: job.hero_id,
        source: job.source,
        output: job.output,
        ...canvasMetrics,
        duration_ms: Math.round(performance.now() - startedAt),
        browserErrors: browserErrors.slice(errorOffset),
      });
    } catch (error) {
      failed.push({
        hero_id: job.hero_id,
        source: job.source,
        output: job.output,
        duration_ms: Math.round(performance.now() - startedAt),
        error: error instanceof Error ? error.message : String(error),
        browserErrors: browserErrors.slice(errorOffset),
      });
    }
  }

  process.stdout.write(`${JSON.stringify({ completed, failed })}\n`);
  if (failed.length > 0) process.exitCode = 1;
} finally {
  await browser.close();
}
