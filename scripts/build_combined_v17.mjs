import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const v13Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-v13.html');
const v14Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-intro-v14.html');
const greetingsPath = path.join(root, 'content', 'front-matter', 'welcome-words', 'structured.json');
const outputPath = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-combined-v17.html');

const signatureAssets = {
  shumilov: {
    src: '../../../assets/intro-people/signatures/shumilov_signature_display.png',
    alt: 'Подлинная подпись Л. В. Шумилова',
    cssClass: 'signature-ink--shumilov',
  },
  makarychev: {
    src: '../../../assets/intro-people/signatures/makarychev_signature_display.png',
    alt: 'Подлинная подпись А. А. Макарычева',
    cssClass: 'signature-ink--makarychev',
  },
};

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
  const signatureAsset = signatureAssets[person];
  const paragraphs = [
    `<p class="salutation">${escapeHtml(item.lead)}</p>`,
    ...item.paras.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`),
    `<p class="quote-ending">${escapeHtml(item.ending)}</p>`,
  ].join('\n          ');

  const attribution = signatureAsset
    ? `<footer class="quote-attribution quote-attribution--signed">
        <div class="signature-proof">
          <img class="signature-ink ${signatureAsset.cssClass}" src="${signatureAsset.src}" alt="${escapeHtml(signatureAsset.alt)}">
          <span>Подлинная подпись</span>
        </div>
        <p>${escapeHtml(item.signature)}</p>
      </footer>`
    : `<footer class="quote-attribution"><p>${escapeHtml(item.signature)}</p></footer>`;

  return `<div class="page right greet greet--${person}${signatureAsset ? ' greet--signed' : ''}">
    <div class="quote-layout">
      <blockquote class="welcome-quote">
        <span class="quote-label">Полный текст приветствия</span>
        <div class="quote-flow">
          ${paragraphs}
        </div>
      </blockquote>
      ${attribution}
    </div>
    <span class="folio">${folio}</span><span class="run">Приветственное слово</span>
  </div>`;
}

function decorateVipPage(section, person, leftFolio) {
  const item = greetings[person];
  let decorated = section
    .replace('<div class="page left vip-open">', `<div class="page left vip-open vip-open--${person}">`)
    .replace(
    /\s*<img class="vip-signature[^>]*>\s*<span class="vip-signature-label">[^<]*<\/span>/,
    ''
    );
  const anchor = `<span class="folio">${leftFolio}</span>`;
  if (!decorated.includes(anchor)) throw new Error(`VIP folio ${leftFolio} not found for ${person}`);
  const excerpt = `<blockquote class="vip-excerpt">
      <p class="vip-excerpt-label">Из приветственного слова</p>
      <p class="vip-excerpt-text">${escapeHtml(item.featured_quote)}</p>
    </blockquote>
    `;
  return decorated.replace(anchor, `${excerpt}${anchor}`);
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
    /<div class="page right imprint">[\s\S]*?<span class="folio">2<\/span><span class="run">[^<]*<\/span><\/div>/,
    `<div class="page right imprint"><div class="safe">
      <div class="imp-top">
        <p class="kicker">Всероссийская книга</p>
        <h1>Письма памяти</h1>
        <p class="vol">Том I</p>
        <hr class="rule-gold">
      </div>

      <p class="partners-eyebrow">Инициатор и партнёры издания</p>
      <div class="organizer-grid">
        <figure class="organizer-card organizer-card--center">
          <img src="../../../assets/branding/processed/center-support-full-cropped-white.png" alt="Центр поддержки детей погибших военнослужащих">
        </figure>
        <figure class="organizer-card organizer-card--dialog">
          <img src="../../../assets/branding/processed/dialog-pokoleniy-full-cropped-white.png" alt="Диалог поколений. Герои и дети">
        </figure>
      </div>
      <p class="init-text">Издана по инициативе <strong>АНО «Центр поддержки детей погибших военнослужащих»</strong></p>

      <section class="support-panel">
        <p class="support-title">Проект состоялся в том числе благодаря поддержке</p>
        <div class="sponsor-grid">
          <article class="sponsor-card sponsor-card--known">
            <img src="../print-v11/assets/frontmatter/trudovaya-doblest-reference.png" alt="Трудовая доблесть России">
            <span>ВОО «Трудовая доблесть России»</span>
          </article>
          <article class="sponsor-card sponsor-card--placeholder"><span class="sponsor-plus">+</span><span>Логотип партнёра</span></article>
          <article class="sponsor-card sponsor-card--placeholder"><span class="sponsor-plus">+</span><span>Логотип партнёра</span></article>
        </div>
      </section>

      <p class="place-year">Москва · 2026</p>
    </div>
    <span class="folio">2</span><span class="run">Выходные данные и партнёры</span></div>`
  )
  .replaceAll('эталон · V13', 'ПРОТОТИП');

let intro = v14Sections.slice(0, 7);
intro[0] = intro[0].replace(
  'assets/maps/russia-action-participants-schematic-commons.svg',
  'assets/maps/russia-action-participants-schematic-commons-multitone.svg'
);
intro[1] = replaceGreeting(decorateVipPage(intro[1], 'shumilov', 5), 'shumilov', 6);
intro[2] = replaceGreeting(decorateVipPage(intro[2], 'makarychev', 7), 'makarychev', 8);
intro[3] = replaceGreeting(decorateVipPage(intro[3], 'belyaninov', 9), 'belyaninov', 10);
intro[5] = replaceGreeting(decorateVipPage(intro[5], 'smirnova', 13), 'smirnova', 14);
intro[6] = replaceGreeting(decorateVipPage(intro[6], 'tengebaeva', 15), 'tengebaeva', 16);

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

/* V17: утверждённая обложка и обновлённая страница партнёров */
.cover{inset:0;width:260mm;height:200mm;object-fit:cover;display:block}
.cover-page{background:#0d2343}
.imprint{background:
  radial-gradient(circle at 86% 12%,rgba(86,132,176,.12),transparent 31%),
  linear-gradient(142deg,#f7f7f4 0%,#f0f3f5 100%)}
.imprint::before,.imprint::after{content:"";position:absolute;z-index:0;border-radius:5mm;background:linear-gradient(135deg,rgba(27,98,183,.10),rgba(237,31,39,.065))}
.imprint::before{right:10mm;top:8mm;width:28mm;height:22mm}.imprint::after{right:23mm;top:22mm;width:21mm;height:17mm}
.imprint .safe{top:9mm;bottom:10mm;display:flex;flex-direction:column;align-items:center;text-align:center;z-index:2}
.imprint .imp-top{display:flex;flex-direction:column;align-items:center}
.imprint .kicker{margin-bottom:1.5mm;font-size:6.7pt}
.imprint h1{font:800 26pt/1.02 var(--head);color:var(--primary_navy)}
.imprint .vol{margin-top:2mm;font:600 8.8pt/1 var(--head);letter-spacing:.08em;color:var(--secondary_text)}
.imprint .rule-gold{width:18mm;height:.45mm;margin:3.3mm 0 0;background:var(--gold_accent);border:0;opacity:.85}
.partners-eyebrow{margin-top:5mm;font:700 5.8pt/1 var(--head);letter-spacing:.14em;text-transform:uppercase;color:var(--secondary_text)}
.organizer-grid{width:210mm;margin-top:2.7mm;display:grid;grid-template-columns:1fr 1fr;gap:5mm}
.organizer-card{height:35mm;margin:0;padding:3.4mm 5mm;overflow:hidden;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.78);border:.22mm solid rgba(42,67,94,.15);box-shadow:0 .7mm 2mm rgba(38,43,48,.07)}
.organizer-card img{display:block;width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply}
.organizer-card--center img{max-width:98mm}.organizer-card--dialog img{max-width:96mm}
.imprint .init-text{margin-top:2.7mm;max-width:196mm;font:500 7.2pt/1.3 var(--body);color:var(--body_text)}
.imprint .init-text strong{font-weight:700;color:var(--primary_navy)}
.support-panel{width:210mm;margin-top:4mm;padding-top:3.3mm;border-top:.3mm solid rgba(34,59,94,.22)}
.support-title{font:700 6.2pt/1.2 var(--head);letter-spacing:.09em;text-transform:uppercase;color:var(--primary_navy)}
.sponsor-grid{margin-top:2.6mm;display:grid;grid-template-columns:1fr 1fr 1fr;gap:4mm}
.sponsor-card{height:29mm;padding:2.5mm 3mm;display:flex;align-items:center;justify-content:center;background:rgba(251,251,249,.78);border:.24mm solid rgba(42,67,94,.18)}
.sponsor-card--known{gap:3mm;text-align:left}.sponsor-card--known img{width:15mm;height:20mm;object-fit:contain}.sponsor-card--known span{max-width:42mm;font:600 5.6pt/1.3 var(--body);color:var(--body_text)}
.sponsor-card--placeholder{gap:2.5mm;border-style:dashed;color:#8b96a2}
.sponsor-card--placeholder>span:last-child{font:600 5.5pt/1.2 var(--head);letter-spacing:.08em;text-transform:uppercase}
.sponsor-plus{width:6mm;height:6mm;border:.25mm solid #a6afb8;border-radius:50%;display:flex;align-items:center;justify-content:center;font:500 8pt/1 var(--head)}
.imprint .place-year{margin-top:auto;padding-top:3.5mm;border-top:.2mm solid var(--line);width:100mm;font:600 8.6pt/1 var(--head);letter-spacing:.1em;color:var(--primary_navy)}

/* V17: короткая буквальная цитата на портретной странице */
.vip-open{isolation:isolate;background-color:#f3f2ee}
.vip-excerpt{position:absolute;left:17mm;bottom:25mm;z-index:8;width:94mm;margin:0;padding:4.5mm 6mm 5mm 8mm;background:rgba(251,251,249,.95);border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(38,43,48,.09)}
.vip-excerpt-label{font:700 5.4pt/1 var(--head);letter-spacing:.12em;text-transform:uppercase;color:var(--primary_navy)}
.vip-excerpt-text{margin-top:2mm;font:400 12pt/1.18 var(--script);color:var(--accent_burgundy)}
.vip-open--tengebaeva .vip-excerpt-text{font-size:11.3pt}

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

/* V17: весь авторский текст крупно, без сокращений */
.greet{background:var(--paper_background)}
.quote-layout{position:absolute;top:9mm;bottom:10mm;left:27mm;width:208mm;display:grid;grid-template-rows:164mm minmax(0,1fr);gap:2mm}
.greet--signed .quote-layout{grid-template-rows:154mm 25mm}
.welcome-quote{position:relative;overflow:hidden;margin:0;padding:8mm 8mm 5mm 11mm;background:
  radial-gradient(circle at 12% 8%,rgba(72,112,153,.075),transparent 38%),
  radial-gradient(circle at 84% 74%,rgba(169,134,60,.055),transparent 33%),
  repeating-linear-gradient(0deg,rgba(34,59,94,.018) 0,rgba(34,59,94,.018) .15mm,transparent .15mm,transparent 1.2mm),
  #f8f7f2;border-left:1mm solid var(--accent_burgundy);box-shadow:0 .7mm 2mm rgba(38,43,48,.10)}
.welcome-quote::before,.welcome-quote::after{position:absolute;font:400 28pt/1 var(--script);color:rgba(135,63,70,.28)}
.welcome-quote::before{content:"“";left:3mm;top:3mm}.welcome-quote::after{content:"”";right:4mm;bottom:1mm}
.quote-label{position:absolute;left:11mm;top:3.2mm;font:700 5.5pt/1 var(--head);letter-spacing:.13em;text-transform:uppercase;color:var(--primary_navy)}
.greet--shumilov{--quote-size:13.4pt}.greet--makarychev{--quote-size:13.6pt}.greet--belyaninov{--quote-size:14.6pt}.greet--smirnova{--quote-size:13pt}.greet--tengebaeva{--quote-size:12.5pt}
.quote-flow{height:100%;columns:2;column-gap:9mm;column-rule:.2mm solid var(--line);column-fill:balance;font:400 var(--quote-size)/1.22 var(--script);color:var(--body_text);text-align:left;hyphens:auto}
.quote-flow p{margin:0 0 1.8mm;orphans:3;widows:3}
.quote-flow .salutation{font-size:calc(var(--quote-size) + .5pt);line-height:1.2;color:var(--primary_navy)}
.quote-flow .quote-ending{margin-top:2.2mm;font-size:calc(var(--quote-size) + .6pt);line-height:1.2;color:var(--accent_burgundy)}
.quote-attribution{padding-top:2mm;border-top:.2mm solid var(--line);text-align:right;font:500 6.2pt/1.25 var(--body);color:var(--secondary_text)}
.quote-attribution p{margin:0}
.quote-attribution--signed{display:grid;grid-template-columns:34mm 1fr;align-items:center;gap:5mm;text-align:left}
.signature-proof{height:22mm;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.7mm}
.signature-proof span{font:600 4.7pt/1 var(--head);letter-spacing:.09em;text-transform:uppercase;color:var(--secondary_text)}
.signature-ink{display:block;max-width:32mm;object-fit:contain}.signature-ink--shumilov{height:17mm}.signature-ink--makarychev{height:15mm}

/* V16: немного больше цвета без легенды ложных категорий */
.map-canvas{background:radial-gradient(circle at 58% 47%,rgba(236,244,250,.95),rgba(232,237,241,.48) 62%,rgba(236,236,230,.98))}
.map-stat:nth-child(1){border-left-color:#2f5279;background:rgba(239,245,249,.97)}
.map-stat:nth-child(2){border-left-color:var(--gold_accent);background:rgba(249,246,237,.97)}
.map-stat.wide{border-left-color:#6989a7;background:rgba(243,247,249,.97)}
.map-badge{border-left-color:var(--gold_accent)}
`;

const output = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Письма памяти — V17, единый клиентский прототип</title><style>
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
