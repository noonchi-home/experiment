// 보고서 markdown → PDF: 작은 변환기(제목·표·목록·인용·코드·굵게·코드 글·그림·가로줄)로 HTML을 만들고 헤드리스 크롬 Page.printToPDF로 찍는다.
//   npx tsx scripts/md-to-pdf.ts <보고서.md> [<보고서.pdf>]
// 그림 경로는 md 파일 자리 기준이다. 글꼴은 ui/node_modules의 Noto Sans KR이 있으면 쓰고, 없으면 시스템 글꼴(맑은 고딕).
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromePath, closeChrome, devtoolsPort, launchChrome, openPage } from "./twin3d/cdp.js";

const [src, outArg] = process.argv.slice(2);
if (!src) throw new Error("npx tsx scripts/md-to-pdf.ts <보고서.md> [<보고서.pdf>]");
const mdPath = resolve(src);
const pdfPath = resolve(outArg ?? mdPath.replace(/\.md$/, ".pdf"));
const md = readFileSync(mdPath, "utf8").replace(/\r\n/g, "\n");

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const inline = (s: string) => esc(s)
  .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_m, alt: string, p: string) => `<img alt="${alt}" src="${pathToFileURL(resolve(dirname(mdPath), p)).href}">`)
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
  .replace(/`([^`]+)`/g, "<code>$1</code>")
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

const lines = md.split("\n");
const html: string[] = [];
for (let i = 0; i < lines.length;) {
  const l = lines[i]!;
  if (/^```/.test(l)) {
    const body: string[] = [];
    for (i++; i < lines.length && !/^```/.test(lines[i]!); i++) body.push(lines[i]!);
    i++;
    html.push(`<pre>${esc(body.join("\n"))}</pre>`);
  } else if (/^#{1,4} /.test(l)) {
    const n = l.match(/^#+/)![0].length;
    html.push(`<h${n}>${inline(l.slice(n + 1))}</h${n}>`);
    i++;
  } else if (/^\|/.test(l)) {
    const rows: string[][] = [];
    for (; i < lines.length && /^\|/.test(lines[i]!); i++) {
      const cells = lines[i]!.replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
      if (cells.every((c) => /^:?-{3,}:?$/.test(c))) continue;
      rows.push(cells);
    }
    const [head, ...body] = rows;
    html.push(`<table><thead><tr>${head!.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
  } else if (/^\s*([-*]|\d+\.) /.test(l)) {
    const ordered = /^\s*\d+\./.test(l);
    const items: string[] = [];
    for (; i < lines.length && /^\s*([-*]|\d+\.) /.test(lines[i]!); i++) {
      const sub = /^\s{2,}/.test(lines[i]!);
      const text = inline(lines[i]!.replace(/^\s*([-*]|\d+\.) /, ""));
      items.push(sub ? `<li class="sub">${text}</li>` : `<li>${text}</li>`);
    }
    html.push(`<${ordered ? "ol" : "ul"}>${items.join("")}</${ordered ? "ol" : "ul"}>`);
  } else if (/^> /.test(l)) {
    const q: string[] = [];
    for (; i < lines.length && /^> /.test(lines[i]!); i++) q.push(inline(lines[i]!.slice(2)));
    html.push(`<blockquote>${q.join("<br>")}</blockquote>`);
  } else if (/^---+$/.test(l)) {
    html.push("<hr>");
    i++;
  } else if (l.trim() === "") {
    i++;
  } else {
    const p: string[] = [];
    for (; i < lines.length && lines[i]!.trim() !== "" && !/^(#|\||```|> |---|\s*([-*]|\d+\.) )/.test(lines[i]!); i++) p.push(inline(lines[i]!));
    html.push(`<p>${p.join("<br>")}</p>`);
  }
}

const font = join(dirname(import.meta.dirname), "ui", "node_modules", "@fontsource-variable", "noto-sans-kr", "index.css");
const fontLink = existsSync(font) ? `<link rel="stylesheet" href="${pathToFileURL(font).href}">` : "";
const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8">${fontLink}<style>
  @page { size: A4; margin: 16mm 14mm; }
  body { font-family: "Noto Sans KR Variable", "Malgun Gothic", sans-serif; font-size: 10pt; line-height: 1.55; color: #1b1b1f; }
  h1 { font-size: 19pt; margin: 0 0 6pt; } h2 { font-size: 14pt; margin: 16pt 0 6pt; border-bottom: 1px solid #d0d0d8; padding-bottom: 3pt; }
  h3 { font-size: 11.5pt; margin: 12pt 0 4pt; } h4 { font-size: 10.5pt; margin: 10pt 0 3pt; }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.8pt; page-break-inside: auto; }
  th, td { border: 1px solid #c9c9d2; padding: 3pt 5pt; vertical-align: top; text-align: left; } th { background: #eef0f5; }
  tr { page-break-inside: avoid; }
  code { font-family: Consolas, monospace; font-size: 8.8pt; background: #f1f2f6; padding: 0 2pt; border-radius: 2pt; }
  pre { font-family: Consolas, monospace; font-size: 8.5pt; background: #f4f5f8; padding: 6pt 8pt; white-space: pre-wrap; border-radius: 3pt; }
  blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #8a8fa3; background: #f6f7fa; color: #33343a; }
  img { max-width: 100%; margin: 4pt 0; border: 1px solid #ddd; } li.sub { margin-left: 16pt; list-style: circle; }
  ul, ol { margin: 4pt 0 8pt; padding-left: 18pt; } hr { border: 0; border-top: 1px solid #ccc; margin: 12pt 0; }
</style></head><body>${html.join("\n")}</body></html>`;
const htmlPath = pdfPath.replace(/\.pdf$/, ".print.html");
writeFileSync(htmlPath, page);

const chrome = launchChrome({ path: chromePath(), size: [1200, 1600] });
try {
  const p = await openPage(await devtoolsPort(chrome), (m) => console.error(m));
  await p.send("Page.navigate", { url: pathToFileURL(htmlPath).href });
  for (let i = 0; i < 50 && (await p.evaluate("document.readyState", 5000)) !== "complete"; i++) await new Promise((r) => setTimeout(r, 200));
  await p.evaluate("document.fonts.ready.then(() => Promise.all([...document.images].map((im) => im.complete ? 0 : new Promise((r) => { im.onload = im.onerror = r; })))).then(() => true)", 30_000);
  const r = await p.send("Page.printToPDF", { printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true, headerTemplate: "<span></span>",
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#777"><span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
  const data = r.result?.data;
  if (!data) throw new Error(`PDF를 만들지 못함: ${r.error?.message ?? "답 없음"}`);
  writeFileSync(pdfPath, Buffer.from(data, "base64"));
  p.close();
  console.log(pdfPath);
} finally {
  await closeChrome(chrome);
  rmSync(htmlPath, { force: true });
}
