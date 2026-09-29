// og-image.html → static/og-image.png (1200×630). 사용: PW=<playwright 경로> node scripts/og/render.js
const path = require('path');
const { chromium } = require(process.env.PW || 'playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.goto('file://' + path.join(__dirname, 'og-image.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(200);
  await p.screenshot({ path: path.join(__dirname, '..', '..', 'static', 'og-image.png') });
  await b.close();
})();
