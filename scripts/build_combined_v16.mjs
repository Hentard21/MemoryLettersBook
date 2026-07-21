import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const v13Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-v13.html');
const v14Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-intro-v14.html');
const greetingsPath = path.join(root, 'content', 'front-matter', 'welcome-words', 'structured.json');
const outputPath = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-combined-v16.html');

const v13 = fs.readFileSync(v13Path, 'utf8');
const v14 = fs.readFileSync(v14Path, 'utf8');
const greetings = JSON.parse(fs.readFileSync(greetingsPath, 'utf8'));

function sections(html) {
  return [...html.matchAll(/<section class="sheet[^"]*">[\s\S]*?<\/section>/g)].map((match) => match[0]);
}

function style(html) {
  const match = html.match(/<style>([\s\S]*?)<\/style>/);
  if (!match) throw new Error('CSS block not found');
  return match[1];
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function quotePage(person, folio) {
  const item = greetings[person];
  const paragraphs = [
    `<p class="salutation">${escapeHtml(item.lead)}</p>`,
    ...item.paras.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`),
    `<p class="quote-ending">${escapeHtml(item.ending)}</p>`,
  ].join('\n          ');

  return `<div class="page right greet">
    <div class="quote-layout">
      <blockquote class="welcome-quote">
        <span class="quote-label">Приветственное слово</span>
        <div class="quote-flow">
          ${paragraphs}
        </div>
      </blockquote>
      <footer class="quote-attribution">${escapeHtml(item.signature)}</footer>
    </div>
    <span class="folio">${folio}</span><span class="run">Приветственное слово</span>
  </div>`;
}

function replaceGreeting(section, person, folio) {
  const pattern = new RegExp(
    `<div class="page right greet">[\\s\\S]*?<span class="folio">${folio}<\\/span><span class="run">[^<]*<\\/span>\\s*<\\/div>`
  );
  if (!pattern.test(section)) throw new Error(`Greeting page ${person}/${folio} not found`);
  return section.replace(pattern, quotePage(person, folio));
}

const v13Sections = sections(v13);
const v14Sections = sections(v14);
if (v13Sections.length !== 5) throw new Error(`Expected 5 V13 spreads, got ${v13Sections.length}`);
if (v14Sections.length !== 8) throw new Error(`Expected 8 V14 spreads, got ${v14Sections.length}`);

let cover = v13Sections[0]
  .replace(
    /<div class="logo-band">[\s\S]*?<\/div>\s*<p class="init-text">/,
    `<div class="logo-band">
        <img class="lg mark" src="../print-v11/assets/frontmatter/reference-imprint-mark.png" alt="Центр поддержки детей">
        <span class="logo-div"></span>
        <img class="lg dialog" src="assets/logos/dialog-pokoleniy-logo.png" alt="Диалог поколений. Герои и дети">
        <span class="logo-div"></span>
        <img class="lg valor" src="../print-v11/assets/frontmatter/trudovaya-doblest-reference.png" alt="Трудовая доблесть России">
      </div>
      <p class="init-text">`
  )
  .replace('Москва · 2025', 'Москва · 2026')
  .replaceAll('эталон · V13', 'ПРОТОТИП');

let intro = v14Sections.slice(0, 7);
intro[0] = intro[0].replace(
  'assets/maps/russia-action-participants-schematic-commons.svg',
  'assets/maps/russia-action-participants-schematic-commons-multitone.svg'
);
intro[1] = replaceGreeting(intro[1], 'shumilov', 6);
intro[2] = replaceGreeting(intro[2], 'makarychev', 8);
intro[3] = replaceGreeting(intro[3], 'belyaninov', 10);
intro[5] = replaceGreeting(intro[5], 'smirnova', 14);
intro[6] = replaceGreeting(intro[6], 'tengebaeva', 16);

let contents = [v13Sections[2], v13Sections[3]].join('\n');
contents = contents
  .replace('74 семьи · нумерация динамическая', '74 семьи · семейный раздел')
  .replaceAll('эталон · V13', 'ПРОТОТИП');
for (const [oldFolio, newFolio] of [[5, 17], [6, 18], [7, 19], [8, 20]]) {
  contents = contents.replace(`<span class="folio">${oldFolio}</span>`, `<span class="folio">${newFolio}</span>`);
}
let tocIndex = 0;
contents = contents.replace(/<span class="toc-pg">—<\/span>/g, () => {
  const page = 21 + tocIndex * 2;
  tocIndex += 1;
  return `<span class="toc-pg">${page}</span>`;
});
if (tocIndex !== 74) throw new Error(`Expected 74 contents rows, got ${tocIndex}`);

let anastasia = v14Sections[7]
  .replace('<span class="folio">17</span>', '<span class="folio">21</span>')
  .replace('<span class="folio">18</span>', '<span class="folio">22</span>');

const extraCss = String.raw`

/* V16: утверждённая обложка и выходные данные */
.cover{inset:0;width:260mm;height:200mm;object-fit:cover;display:block}
.cover-page{background:#0d2343}
.imprint{background:var(--page_background)}
.imprint .safe{top:18mm;bottom:16mm;display:flex;flex-direction:column;align-items:center;text-align:center}
.imprint .imp-main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;gap:13mm}
.imprint .imp-top,.imprint .imp-mid{display:flex;flex-direction:column;align-items:center;width:100%}
.imprint .kicker{margin-bottom:2mm}
.imprint h1{font:800 30pt/1.02 var(--head);color:var(--primary_navy)}
.imprint .vol{margin-top:3.5mm;font:600 10.5pt/1 var(--head);letter-spacing:.08em;color:var(--secondary_text)}
.imprint .rule-gold{width:22mm;height:.5mm;margin:6mm 0 0;background:var(--gold_accent);border:0;opacity:.85}
.imprint .logo-band{display:flex;align-items:center;justify-content:center;gap:9mm;margin-bottom:6mm}
.imprint .logo-band .lg{height:22mm;width:auto;max-width:62mm;object-fit:contain;display:block}
.imprint .logo-band .mark{width:22mm}.imprint .logo-band .dialog{height:20mm}.imprint .logo-band .valor{height:23mm}
.imprint .logo-band .logo-div{width:.2mm;height:22mm;background:var(--line)}
.imprint .init-text{max-width:180mm;font:600 8.8pt/1.42 var(--body);color:var(--body_text)}
.imprint .support-text{margin-top:3mm;max-width:180mm;font:500 8.1pt/1.4 var(--body);color:var(--secondary_text)}
.imprint .place-year{padding-top:5mm;border-top:.2mm solid var(--line);width:120mm;font:600 9.5pt/1 var(--head);letter-spacing:.1em;color:var(--primary_navy)}

/* V16: полное содержание без пустых строк */
.contents-page{background:var(--paper_background)}
.contents-page .safe{top:15mm;bottom:16mm}
.contents-head{display:flex;align-items:baseline;justify-content:space-between;border-bottom:.4mm solid var(--primary_navy);padding-bottom:2.5mm;margin-bottom:5mm}
.contents-head h2{font:750 16pt/1.12 var(--head);color:var(--primary_navy)}
.contents-head .cont-note{font:600 6.4pt/1.3 var(--head);letter-spacing:.1em;text-transform:uppercase;color:var(--secondary_text)}
.toc-list{list-style:none;padding:0}
.toc-row{display:flex;align-items:baseline;gap:2.5mm;padding:1.75mm 0;border-bottom:.15mm solid var(--line)}
.toc-num{flex:0 0 9mm;font:700 8.2pt/1 var(--head);color:var(--gold_accent);letter-spacing:.03em}
.toc-name{flex:0 0 auto;font:600 10.5pt/1.05 var(--head);color:var(--primary_navy)}
.toc-reg{flex:0 0 auto;font:400 7.9pt/1 var(--body);color:var(--secondary_text)}
.toc-dots{flex:1 1 auto;align-self:center;height:.15mm;margin:0 1mm;border-bottom:.3mm dotted var(--line)}
.toc-pg{flex:0 0 auto;font:600 8.4pt/1 var(--head);color:var(--secondary_text)}

/* V16: весь авторский текст воспринимается как одна большая цитата */
.greet{background:var(--paper_background)}
.quote-layout{position:absolute;top:9mm;bottom:10mm;left:27mm;width:208mm;display:grid;grid-template-rows:164mm minmax(0,1fr);gap:2mm}
.welcome-quote{position:relative;overflow:hidden;margin:0;padding:8mm 8mm 5mm 11mm;background:
  radial-gradient(circle at 12% 8%,rgba(72,112,153,.075),transparent 38%),
  radial-gradient(circle at 84% 74%,rgba(169,134,60,.055),transparent 33%),
  repeating-linear-gradient(0deg,rgba(34,59,94,.018) 0,rgba(34,59,94,.018) .15mm,transparent .15mm,transparent 1.2mm),
  #f8f7f2;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(38,43,48,.10)}
.welcome-quote::before,.welcome-quote::after{position:absolute;font:400 28pt/1 var(--script);color:rgba(135,63,70,.28)}
.welcome-quote::before{content:"“";left:3mm;top:3mm}.welcome-quote::after{content:"”";right:4mm;bottom:1mm}
.quote-label{position:absolute;left:11mm;top:3.2mm;font:700 5.5pt/1 var(--head);letter-spacing:.13em;text-transform:uppercase;color:var(--primary_navy)}
.quote-flow{height:100%;columns:2;column-gap:9mm;column-rule:.2mm solid var(--line);column-fill:balance;font:400 11.2pt/1.24 var(--script);color:var(--body_text);text-align:left;hyphens:auto}
.quote-flow p{margin:0 0 1.8mm;orphans:3;widows:3}
.quote-flow .salutation{font-size:11.7pt;line-height:1.22;color:var(--primary_navy)}
.quote-flow .quote-ending{margin-top:2.2mm;font-size:11.8pt;line-height:1.22;color:var(--accent_burgundy)}
.quote-attribution{padding-top:2mm;border-top:.2mm solid var(--line);text-align:right;font:500 6.2pt/1.25 var(--body);color:var(--secondary_text)}

/* V16: немного больше цвета без легенды ложных категорий */
.map-canvas{background:radial-gradient(circle at 58% 47%,rgba(236,244,250,.95),rgba(232,237,241,.48) 62%,rgba(236,236,230,.98))}
.map-stat:nth-child(1){border-left-color:#2f5279;background:rgba(239,245,249,.97)}
.map-stat:nth-child(2){border-left-color:var(--gold_accent);background:rgba(249,246,237,.97)}
.map-stat.wide{border-left-color:#6989a7;background:rgba(243,247,249,.97)}
.map-badge{border-left-color:var(--gold_accent)}
`;

const output = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Письма памяти — объединённый клиентский прототип</title><style>
${style(v14)}
${extraCss}
</style></head><body>
${cover}
${intro.join('\n')}
${contents}
${anastasia}
</body></html>\n`;

fs.writeFileSync(outputPath, output, 'utf8');
console.log(outputPath);
