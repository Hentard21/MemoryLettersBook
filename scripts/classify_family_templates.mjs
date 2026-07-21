import fs from 'node:fs';
import path from 'node:path';

const projectRoot = path.resolve(import.meta.dirname, '..');
const readJson = (relativePath) =>
  JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), 'utf8'));

const order = readJson('content/manifests/reference-family-order-reset.json');
const processingPlan = readJson('assets/families/family-processing-plan.json');
const planByHero = new Map(processingPlan.families.map((family) => [family.hero_id, family]));

const TRANSCRIPTION_LIMIT = 1200;
const VISUAL_LIMIT = 4;

function normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function canonicalDrawings(drawings = []) {
  const originals = drawings.filter((item) => item.is_processed_derivative !== true);
  return originals.length ? originals : drawings;
}

function transcriptionLoad(heroId) {
  const directory = path.join(projectRoot, 'assets', 'families', heroId, 'transcriptions');
  if (!fs.existsSync(directory)) {
    return { files: 0, characters: null };
  }

  const files = fs.readdirSync(directory);
  const readerTextByLetter = new Map();

  for (const file of files.filter((name) => name.endsWith('_print.txt')).sort()) {
    const letterId = file.replace(/_print\.txt$/, '');
    const text = normalizeText(fs.readFileSync(path.join(directory, file), 'utf8'));
    if (text) readerTextByLetter.set(letterId, text);
  }

  for (const file of files.filter((name) => name.endsWith('.json')).sort()) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(directory, file), 'utf8'));
      const letterId = data.letter_id || file.replace(/_transcription\.json$/, '');
      if (readerTextByLetter.has(letterId)) continue;
      const text = normalizeText(
        data.reader_friendly_transcription || data.print_transcription || data.transcription || '',
      );
      if (text) readerTextByLetter.set(letterId, text);
    } catch {
      // An invalid transcription file is not silently counted as usable text.
    }
  }

  const characters = [...readerTextByLetter.values()].reduce((sum, text) => sum + text.length, 0);
  return {
    files: readerTextByLetter.size,
    characters: readerTextByLetter.size ? characters : null,
  };
}

function plural(number, one, few, many) {
  const mod10 = number % 10;
  const mod100 = number % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return few;
  return many;
}

function classify(referenceFamily) {
  const plan = planByHero.get(referenceFamily.hero_id);
  if (!plan) throw new Error(`Missing processing plan for ${referenceFamily.hero_id}`);

  const physicalLetters = (plan.letters || []).filter(
    (item) => item.physical_scan === true && item.is_processed_derivative !== true,
  ).length;
  const archivePhotos = (plan.archive_assets || []).length;
  const drawings = canonicalDrawings(plan.drawings || []).length;
  const flagshipImages = plan.flagship_asset ? 1 : 0;
  const significantVisuals = flagshipImages + archivePhotos + drawings;
  const referencePages = (referenceFamily.reference_pages || []).length;
  const transcription = transcriptionLoad(referenceFamily.hero_id);

  const triggers = [];
  if (physicalLetters >= 2) triggers.push('multiple_physical_letters');
  if (significantVisuals > VISUAL_LIMIT) triggers.push('visual_documentary_overload');
  if (transcription.characters !== null && transcription.characters > TRANSCRIPTION_LIMIT) {
    triggers.push('long_transcription');
  }
  if (
    transcription.characters === null &&
    physicalLetters === 1 &&
    referencePages >= 4 &&
    !triggers.length
  ) {
    triggers.push('conservative_reference_page_proxy');
  }

  const templateVariant = triggers.length ? 'extended' : 'standard';
  let confidence = 'medium';
  let status = 'PROVISIONAL_STANDARD_TRANSCRIPTION_PENDING';

  if (physicalLetters === 0) {
    confidence = 'low';
    status = 'REVIEW_REQUIRED_NO_PHYSICAL_LETTER_REGISTERED';
  } else if (transcription.characters !== null) {
    confidence = 'high';
    status = 'CLASSIFIED_FROM_DOCUMENTED_LOAD';
  } else if (triggers.includes('conservative_reference_page_proxy')) {
    confidence = 'medium';
    status = 'PROVISIONAL_EXTENDED_TRANSCRIPTION_PENDING';
  } else if (templateVariant === 'extended') {
    confidence = 'high';
    status = 'CLASSIFIED_EXTENDED_TRANSCRIPTION_PENDING';
  }

  const reasons = [];
  if (triggers.includes('multiple_physical_letters')) {
    reasons.push(
      `${physicalLetters} ${plural(physicalLetters, 'физическая рукопись', 'физические рукописи', 'физических рукописей')} требуют отдельных расшифровок`,
    );
  }
  if (triggers.includes('visual_documentary_overload')) {
    reasons.push(
      `${significantVisuals} значимых изображений превышают лимит стандартного разворота (${VISUAL_LIMIT})`,
    );
  }
  if (triggers.includes('long_transcription')) {
    reasons.push(
      `полная читательская расшифровка содержит ${transcription.characters} знаков и превышает лимит ${TRANSCRIPTION_LIMIT}`,
    );
  }
  if (triggers.includes('conservative_reference_page_proxy')) {
    reasons.push(
      `длина расшифровки пока неизвестна, а семейный блок занимает ${referencePages} страницы референса; выбран консервативный кандидат`,
    );
  }

  if (!reasons.length) {
    reasons.push(
      `документальная нагрузка не превышает лимит: ${significantVisuals} ${plural(significantVisuals, 'значимое изображение', 'значимых изображения', 'значимых изображений')} и ${physicalLetters} ${plural(physicalLetters, 'рукопись', 'рукописи', 'рукописей')}`,
    );
    if (transcription.characters === null && physicalLetters > 0) {
      reasons.push(
        'длина расшифровки ещё не зафиксирована; standard остаётся предварительным до текстового preflight',
      );
    }
    if (physicalLetters === 0) {
      reasons.push(
        'в активном манифесте нет физической рукописи; после её нахождения классификацию нужно повторить',
      );
    }
  }

  return {
    reference_order: referenceFamily.reference_order,
    hero_id: referenceFamily.hero_id,
    hero_name: referenceFamily.hero_name,
    template_variant: templateVariant,
    counts: {
      reference_pages: referencePages,
      flagship_images: flagshipImages,
      archive_photos: archivePhotos,
      drawings,
      significant_visuals: significantVisuals,
      physical_letters: physicalLetters,
      transcription_files: transcription.files,
      transcription_characters: transcription.characters,
    },
    reason: reasons.join('; ') + '.',
    confidence,
    status,
    source_identity_status: referenceFamily.identity_status,
    reevaluate_when_transcription_ready: transcription.characters === null && physicalLetters > 0,
  };
}

const families = order.families.map(classify);
const standardCount = families.filter((family) => family.template_variant === 'standard').length;
const extendedCount = families.filter((family) => family.template_variant === 'extended').length;

const output = {
  schema_version: 1,
  generated_at: new Date().toISOString(),
  source_of_truth: {
    reference_pdf: order.source_file,
    reference_sha256: order.source_sha256,
    family_order: 'content/manifests/reference-family-order-reset.json',
    processing_plan: 'assets/families/family-processing-plan.json',
  },
  policy: {
    standard: 'один основной разворот',
    extended: 'основной разворот и один разворот-продолжение',
    maximum_significant_visuals_on_standard: VISUAL_LIMIT,
    maximum_reader_transcription_characters_on_standard: TRANSCRIPTION_LIMIT,
    automatic_extended_triggers: [
      'две или более физических рукописи',
      'более четырёх значимых изображений, включая флагман',
      `читательская расшифровка длиннее ${TRANSCRIPTION_LIMIT} знаков`,
      'консервативный кандидат: длина текста неизвестна, а блок занимает четыре или более страниц референса',
    ],
  },
  summary: {
    families: families.length,
    standard: standardCount,
    extended: extendedCount,
    transcription_length_known: families.filter(
      (family) => family.counts.transcription_characters !== null,
    ).length,
    missing_physical_letter_in_manifest: families.filter(
      (family) => family.counts.physical_letters === 0,
    ).length,
  },
  families,
};

const jsonPath = path.join(projectRoot, 'assets/families/family-template-classification.json');
fs.writeFileSync(jsonPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');

const extendedRows = families
  .filter((family) => family.template_variant === 'extended')
  .map(
    (family) =>
      `| ${family.reference_order} | ${family.hero_id} | ${family.hero_name} | ${family.counts.reference_pages} | ${family.counts.significant_visuals} | ${family.counts.physical_letters} | ${family.counts.transcription_characters ?? '—'} | ${family.confidence} |`,
  )
  .join('\n');

const missingLetterIds = families
  .filter((family) => family.counts.physical_letters === 0)
  .map((family) => `\`${family.hero_id}\``)
  .join(', ');

const markdown = `# Правила выбора семейного шаблона

Дата классификации: 21 июля 2026 года.
Эталон порядка и принадлежности: \`source/reference.pdf\`, SHA-256 \`${order.source_sha256}\`.
Машиночитаемый результат: \`assets/families/family-template-classification.json\`.

## Два замороженных режима

- **standard** — один основной разворот. Визуальный эталон — Анастасия.
- **extended** — основной разворот и ровно один разворот-продолжение. Визуальный эталон — Евгений (\`hero-014\`).

Расширенный режим не служит декоративной паузой. Он разрешён только там, где полный документальный комплект нельзя удержать в одном развороте без уменьшения текста, рукописи или фотографий до нечитаемого размера.

## Объективные триггеры extended

Семья получает \`extended\`, если выполнено хотя бы одно условие:

1. Есть две или более самостоятельных физических рукописи. Каждая должна остаться в книге и иметь свою расшифровку.
2. Более четырёх значимых изображений: флагман + архивные фото + рисунки. Производные апскейлы и вырезки не считаются новыми изображениями.
3. Суммарная длина печатных читательских расшифровок превышает **${TRANSCRIPTION_LIMIT} знаков с пробелами**.
4. Длина расшифровки ещё неизвестна, но блок занимает четыре или более страниц референса. Это консервативный кандидат; после готовности текста решение пересчитывается.

Даже после формальной классификации вёрстка проходит preflight. Если текст или важная деталь не читаются при 100 %, \`standard\` автоматически повышается до \`extended\`. Контент не уменьшается и не выбрасывается.

## Как читать предварительные статусы

- \`CLASSIFIED_FROM_DOCUMENTED_LOAD\` — длина печатной расшифровки уже учтена.
- \`CLASSIFIED_EXTENDED_TRANSCRIPTION_PENDING\` — продолжение уже обосновано числом рукописей или изображений; текст всё равно нужно подготовить.
- \`PROVISIONAL_STANDARD_TRANSCRIPTION_PENDING\` — текущий комплект визуально вмещается, но длина текста ещё неизвестна.
- \`PROVISIONAL_EXTENDED_TRANSCRIPTION_PENDING\` — выбрано продолжение как безопасный кандидат по объёму блока в референсе.
- \`REVIEW_REQUIRED_NO_PHYSICAL_LETTER_REGISTERED\` — в активном манифесте нет физической рукописи; решение нельзя считать окончательным.

## Текущий итог

- Всего семей: **${families.length}**.
- \`standard\`: **${standardCount}**.
- \`extended\`: **${extendedCount}**.
- Длина читательской расшифровки уже доступна для **${output.summary.transcription_length_known}** семей.
- Физическая рукопись не зарегистрирована в активном манифесте у **${output.summary.missing_physical_letter_in_manifest}** семей: ${missingLetterIds || 'нет'}.

### Семьи, заранее помеченные extended

| № | hero_id | Герой | Страниц реф. | Изображений | Рукописей | Знаков | Уверенность |
|---:|---|---|---:|---:|---:|---:|---|
${extendedRows}

## Пересчёт

Классификацию нужно перестроить, когда:

- появилась или изменилась полная печатная расшифровка;
- в манифест добавлена пропущенная рукопись, фотография или рисунок;
- ручной preflight показал переполнение или нечитаемый масштаб.

Команда пересчёта: \`node scripts/classify_family_templates.mjs\`. Скрипт не меняет PDF, HTML или файлы расшифровок.
`;

fs.writeFileSync(path.join(projectRoot, 'docs/FAMILY_TEMPLATE_RULES.md'), markdown, 'utf8');

console.log(
  JSON.stringify(
    {
      families: families.length,
      standard: standardCount,
      extended: extendedCount,
      output: path.relative(projectRoot, jsonPath),
    },
    null,
    2,
  ),
);
