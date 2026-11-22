// 영상 한눈에 보기: 영상마다 고르게 12장을 뽑아 4×3 사진 한 장(runtime/test-logs/frames/<영상>.png)으로 남긴다. 장마다 영상 시각을 적는다.
//   npx tsx scripts/clip-contact.ts <영상.mp4> ...   (runtime/videos 안 이름)
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromePath, closeChrome, devtoolsPort, launchChrome, openPage } from "./twin3d/cdp.js";

const ROOT = resolve(import.meta.dirname, "..");
const out = join(ROOT, "runtime", "test-logs", "frames");
mkdirSync(out, { recursive: true });
const W = 1600, H = 1000;
const chrome = launchChrome({ path: chromePath(), size: [W, H] });
try {
  const page = await openPage(await devtoolsPort(chrome), (m) => console.error(m));
  await page.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  for (const clip of process.argv.slice(2)) {
    const src = pathToFileURL(join(ROOT, "runtime", "videos", clip)).href;
    const html = `<body style="margin:0;background:#111"><canvas id=c width=${W} height=${H}></canvas><video id=v muted src="${src}"></video></body>`;
    const sheet = join(out, `_sheet-${clip}.html`);
    writeFileSync(sheet, html);
    await page.send("Page.navigate", { url: pathToFileURL(sheet).href });
    for (let i = 0; i < 50 && !(await page.evaluate("!!document.getElementById('c')", 5000)); i++) await new Promise((r) => setTimeout(r, 200));
    const dur = await page.evaluate(`(async () => {
      const v = document.getElementById('v'), c = document.getElementById('c'), g = c.getContext('2d');
      if (!(v.readyState >= 1)) await new Promise((r, j) => { v.onloadedmetadata = r; v.onerror = () => j(new Error('영상 못 읽음')); });
      const n = 12, cw = ${W} / 4, ch = ${H} / 3;
      for (let i = 0; i < n; i++) {
        const t = v.duration * (i + 0.5) / n;
        v.currentTime = t;
        await new Promise((r) => { v.onseeked = r; });
        const s = Math.min(cw / v.videoWidth, ch / v.videoHeight), w = v.videoWidth * s, h = v.videoHeight * s;
        const x = (i % 4) * cw + (cw - w) / 2, y = Math.floor(i / 4) * ch + (ch - h) / 2;
        g.drawImage(v, x, y, w, h);
        g.fillStyle = 'rgba(0,0,0,.7)'; g.fillRect(x, y, 90, 30); g.fillStyle = '#fff'; g.font = '20px sans-serif'; g.fillText(t.toFixed(1) + 's', x + 8, y + 22);
      }
      return v.duration;
    })()`, 60_000);
    writeFileSync(join(out, clip.replace(/\.[^.]+$/, ".png")), await page.screenshot({ format: "png" }, 20_000));
    console.log(`${clip} ${Number(dur).toFixed(1)}초`);
  }
  page.close();
} finally {
  await closeChrome(chrome);
}
