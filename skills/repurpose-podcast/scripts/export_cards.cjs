#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { spawnSync } = require('child_process');

function fail(message) { console.error(message); process.exit(2); }
const input = process.argv[2];
if (!input || input === '--help' || input === '-h') {
  console.log('Usage: node export_cards.cjs <index.html> --output-dir <directory>');
  process.exit(input ? 0 : 2);
}
const flag = process.argv.indexOf('--output-dir');
if (flag < 0 || !process.argv[flag + 1]) fail('--output-dir is required');
let playwright;
try { playwright = require('playwright'); } catch { fail('Playwright is required. Install it with: npm install playwright && npx playwright install chromium'); }

(async () => {
  const html = path.resolve(input);
  const output = path.resolve(process.argv[flag + 1]);
  fs.mkdirSync(output, { recursive: true });
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 1600 }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(html).href, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.locator('[data-view="xhs"]').click();
  await page.locator('[data-xhs-tab="cards"]').click();
  await page.evaluate(() => { document.body.style.paddingBottom = '800px'; });
  const cards = page.locator('.xhs-card');
  const count = await cards.count();
  if (count < 4 || count > 8) fail(`Xiaohongshu requires 4–8 cards; found ${count}`);
  const selectedTheme = await page.locator('#theme').evaluate(node => node.value);
  const themes = await page.locator('#theme option').evaluateAll(nodes => nodes.map(node => node.value));
  for (const theme of themes) {
    await page.locator('#theme').selectOption(theme);
    const overflow = await cards.evaluateAll(nodes => nodes.map((node, index) => ({ index, overflow: node.scrollHeight > node.clientHeight || node.scrollWidth > node.clientWidth + 64 })).filter(x => x.overflow));
    if (overflow.length) fail(`Card text overflow detected in ${theme}: ${overflow.map(x => x.index + 1).join(', ')}`);
  }
  await page.locator('#theme').selectOption(selectedTheme);
  const browserExportBytes = await page.evaluate(async () => {
    if (typeof cardPng !== 'function') return 0;
    const blob = await cardPng(0, false);
    return blob?.size || 0;
  });
  if (browserExportBytes < 1000) fail('In-page PNG export did not produce a usable image');
  for (let index = 0; index < count; index += 1) {
    const card = cards.nth(index);
    await card.scrollIntoViewIfNeeded();
    const name = String(index + 1).padStart(2, '0');
    const raw = path.join(output, `.${name}.raw.png`);
    const target = path.join(output, `${name}.png`);
    await card.screenshot({ path: raw });
    const converted = spawnSync('ffmpeg', ['-y', '-v', 'error', '-i', raw, '-vf', 'scale=1080:1440:flags=lanczos', target], { encoding: 'utf8' });
    fs.unlinkSync(raw);
    if (converted.status !== 0) fail(`ffmpeg failed for card ${index + 1}: ${converted.stderr.trim()}`);
  }
  await browser.close();
  console.log(JSON.stringify({ output, count }));
})().catch(error => fail(error.stack || String(error)));
