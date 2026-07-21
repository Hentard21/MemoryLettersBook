import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const v13Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-v13.html');
const v14Path = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-intro-v14.html');
const greetingsPath = path.join(root, 'content', 'front-matter', 'welcome-words', 'structured.json');
const outputPath = path.join(root, 'design', 'prototypes', 'print-v12', 'interior-combined-v18.html');

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

      <p class="partners-eyebrow">Совместная инициатива</p>
      <div class="organizer-grid">
        <figure class="organizer-card organizer-card--center">
          <img class="organizer-mark organizer-mark--center" src="../../../assets/branding/production/center-mark-tight.svg" alt="">
          <figcaption class="organizer-name organizer-name--center"><strong>Центр поддержки детей</strong><span>погибших военнослужащих</span></figcaption>
        </figure>
        <figure class="organizer-card organizer-card--dialog">
          <img class="organizer-mark organizer-mark--dialog" src="../../../assets/branding/production/dialog-generations-mark.svg" alt="">
          <figcaption class="organizer-name organizer-name--dialog"><strong>Диалог поколений</strong><span>Герои и дети</span></figcaption>
        </figure>
      </div>
      <p class="init-text">Издана по совместной инициативе <strong>АНО «Центр поддержки детей погибших военнослужащих»</strong> и проекта <strong>«Диалог поколений. Герои и дети»</strong>.</p>

      <section class="support-panel">
        <p class="support-title">Проект состоялся в том числе благодаря поддержке</p>
        <div class="sponsor-grid">
          <article class="sponsor-card sponsor-card--known">
            <img src="../print-v11/assets/frontmatter/trudovaya-doblest-reference.png" alt="Трудовая доблесть России">
            <span>ВОО «Трудовая доблесть России»</span>
          </article>
          <article class="sponsor-card sponsor-card--placeholder"><span class="sponsor-slot-mark" aria-hidden="true"></span><span>Партнёр проекта</span></article>
          <article class="sponsor-card sponsor-card--placeholder"><span class="sponsor-slot-mark" aria-hidden="true"></span><span>Партнёр проекта</span></article>
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
  .replace(
    '../../../assets/processed-flagships/hero-001/anastasia_portrait_hero-001_nobg.png',
    '../../../assets/families/hero-001/flagship/anastasia_portrait_repaired_white.png'
  )
  .replace('<span class="folio">17</span>', '<span class="folio">21</span>')
  .replace('<span class="folio">18</span>', '<span class="folio">22</span>');

const extraCss = String.raw`

/* V17: утверждённая обложка и обновлённая страница партнёров */
.cover{inset:0;width:260mm;height:200mm;object-fit:cover;display:block}
.cover-page{background:#0d2343}
.imprint{background:
  linear-gradient(90deg,rgba(34,59,94,.045) 0,rgba(34,59,94,0) 42%),
  linear-gradient(142deg,#f8f8f5 0%,#edf2f5 100%)}
.imprint::before,.imprint::after{display:none}
.imprint .safe{top:12mm;bottom:11mm;left:20mm;right:18mm;display:flex;flex-direction:column;align-items:stretch;text-align:left;z-index:2}
.imprint .imp-top{display:flex;flex-direction:column;align-items:flex-start}
.imprint .kicker{margin-bottom:1.5mm;font-size:6.7pt}
.imprint h1{font:800 28pt/1.02 var(--head);color:var(--primary_navy)}
.imprint .vol{margin-top:2mm;font:600 8.8pt/1 var(--head);letter-spacing:.08em;color:var(--secondary_text)}
.imprint .rule-gold{width:21mm;height:.45mm;margin:3.3mm 0 0;background:var(--gold_accent);border:0;opacity:.85}
.partners-eyebrow{margin-top:7mm;font:700 6.4pt/1 var(--head);letter-spacing:.14em;text-transform:uppercase;color:var(--secondary_text)}
.organizer-grid{width:100%;margin-top:3mm;display:grid;grid-template-columns:1fr 1fr;gap:4mm}
.organizer-card{height:38mm;margin:0;padding:4mm 5mm;overflow:hidden;display:grid;grid-template-columns:20mm 1fr;gap:4mm;align-items:center;text-align:left;background:rgba(255,255,255,.84);border:.22mm solid rgba(42,67,94,.14);box-shadow:none}
.organizer-card--center{border-top:.8mm solid #1764c0}.organizer-card--dialog{border-top:.8mm solid #ed1f2b}
.organizer-mark{display:block;width:19mm;height:21mm;object-fit:contain}
.organizer-mark--dialog{width:18mm;height:20mm;justify-self:center}
.organizer-name{display:flex;min-width:0;flex-direction:column;justify-content:center;text-transform:uppercase;color:var(--primary_navy)}
.organizer-name strong{font:800 9.6pt/1.04 var(--head);letter-spacing:.012em}
.organizer-card--center .organizer-name strong{font-size:9.3pt}.organizer-card--dialog .organizer-name strong{font-size:9.8pt}
.organizer-name span{margin-top:1.4mm;font:700 5.7pt/1.1 var(--head);letter-spacing:.06em}
.organizer-name--center span{color:#1764c0}.organizer-name--dialog span{color:#ed1f2b}
.imprint .init-text{margin-top:4mm;max-width:none;padding:3.5mm 5mm;font:500 8.3pt/1.4 var(--body);color:var(--body_text);background:rgba(226,234,241,.66);border-left:.8mm solid var(--primary_navy)}
.imprint .init-text strong{font-weight:700;color:var(--primary_navy)}
.support-panel{width:100%;margin-top:5mm;padding:5mm 5.5mm 5.5mm;border-top:0;background:rgba(219,229,237,.58)}
.support-title{font:700 7pt/1.2 var(--head);letter-spacing:.09em;text-transform:uppercase;color:var(--primary_navy)}
.sponsor-grid{margin-top:3mm;display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:3mm}
.sponsor-card{height:36mm;padding:3mm 4mm;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.9);border:.22mm solid rgba(42,67,94,.14)}
.sponsor-card--known{gap:4mm;text-align:left}.sponsor-card--known img{width:18mm;height:23mm;object-fit:contain}.sponsor-card--known span{max-width:44mm;font:600 6.4pt/1.3 var(--body);color:var(--body_text)}
.sponsor-card--placeholder{flex-direction:column;gap:2.4mm;color:#7d8996}
.sponsor-card--placeholder>span:last-child{font:650 6.2pt/1.2 var(--head);letter-spacing:.08em;text-transform:uppercase}
.sponsor-slot-mark{width:13mm;height:13mm;border:.35mm solid rgba(34,59,94,.22);border-radius:50%;background:radial-gradient(circle,rgba(34,59,94,.08) 0 23%,transparent 24%)}
.imprint .place-year{margin-top:auto;padding-top:3.5mm;border-top:.2mm solid var(--line);width:100%;text-align:center;font:600 8.6pt/1 var(--head);letter-spacing:.1em;color:var(--primary_navy)}

/* Белый фон нового флагмана растворяется в светлом развороте без размытой маски. */
.hero-cutout{mix-blend-mode:multiply}

/* V20: страница 12 хроники — два самостоятельных фотодокументальных модуля. */
.ev-dialog,.ev-december{width:219mm;overflow:hidden;background:rgba(251,251,249,.97);border:.35mm solid #fff;box-shadow:0 .65mm 1.7mm rgba(38,43,48,.10)}
.ev-dialog{left:21mm;top:18mm;height:102mm}.ev-december{left:21mm;top:129mm;height:55mm}
.event-image{box-shadow:none}
.ev-dialog .event-image{left:2.2mm;top:2.2mm;width:137mm;height:97.6mm}.ev-december .event-image{left:2.2mm;top:2.2mm;width:91mm;height:50.6mm}
.ev-dialog .event-image img,.ev-december .event-image img{transform:scale(1.015)}
.ev-dialog figcaption{left:139.2mm;right:0;top:0;bottom:0;width:auto;min-height:0;padding:6mm 5.5mm 6mm 7mm;display:flex;flex-direction:column;justify-content:center;font-size:6.45pt;line-height:1.36;box-shadow:none}
.ev-december figcaption{left:93.2mm;right:0;top:0;bottom:0;width:auto;min-height:0;padding:4.5mm 5.5mm 4.5mm 7mm;display:flex;flex-direction:column;justify-content:center;font-size:6.25pt;line-height:1.34;box-shadow:none}

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

const output = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Письма памяти — V18, единый клиентский прототип</title><style>
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
