# AI handoff после reset

Перед любым изменением проекта обязательно прочитать:

1. `docs/PROJECT_RULES_RESET.md` — главный регламент и единый источник рабочих правил;
2. `docs/REFERENCE_LOCK.md` — порядок и принадлежность материалов;
3. `docs/SEQUENTIAL_WORKFLOW.md` — разрешённая последовательность действий;
4. `assets/families/family-processing-plan.json` — текущий план обработки семей;
5. `assets/families/letters-transcriptions-index.json` — связка рукописей и расшифровок.
6. `docs/FAMILY_TEMPLATE_RULES.md` — правило выбора стандартного и расширенного режима.
7. `assets/families/family-template-classification.json` — предварительный режим каждой из 74 семей в референсном порядке.
8. `docs/DRAFT_ASSEMBLY_POLICY.md` — разрешённый режим полного чернового издания до редакторской проверки.
9. `content/manifests/draft-deferred-families.json` — актуальные спорные семьи и причины, которые нельзя заменять догадками.

## Неподвижные условия

- `source/reference.pdf` — структурный и содержательный эталон.
- Текущий эталон содержит 246 страниц; его SHA-256 зафиксирован в `source/reference.sha256`.
- Активный порядок 74 семей хранится в `content/manifests/reference-family-order-reset.json`; ID `hero-002` и `hero-016` не входят в финальный референс и не должны возвращаться в очередь.
- Утверждённая обложка `design/cover-v1/artwork/cover-art.png` не меняется.
- Порядок семей и материалов не меняется.
- Контент не сокращается и не переписывается. Единственное исключение: в отдельной читательской версии расшифровки можно исправить очевидную опечатку или восстановить одно однозначное слово по правилам `docs/TRANSCRIPTION_POLICY.md`; дипломатическая версия при этом остаётся неизменной.
- Каждая рукопись должна физически присутствовать и иметь отдельную расшифровку либо честный статус `missing`/`REVIEW_REQUIRED`.
- Материалы разных семей не смешиваются.
- Новая работа выполняется только последовательно от начала референса.
- Одна семья получает один основной разворот. Если полный документальный комплект не проходит реальную проверку читаемости, непосредственно следом автоматически добавляется максимум один разворот-продолжение; уменьшать текст и фотографии до нечитаемого размера запрещено.

Для полного чернового издания действует одно явно согласованное рабочее исключение:
текущие расшифровки разрешено ставить в макет со статусом `REVIEW_REQUIRED`.
В `content/manifests/draft-deferred-families.json` сейчас остаются только
`hero-030` (конфликт принадлежности письма) и `hero-065` (не зарегистрированы
физическая рукопись и расшифровка). Никакой из этих статусов не разрешает
догадывать содержание или менять канонический `reference_order` в финальной книге.

## Текущий визуальный ориентир

`design/prototypes/print-v20/PRINT_V20_CLIENT_TEMPLATE_APPROVAL.pdf` — утверждённый **Design Lock** перед массовой вёрсткой: Анастасия задаёт `standard`, Евгений задаёт `extended`. В нём используется исправленная владельцем фигура Анастасии и белофоновая групповая фотография Евгения с детьми. Обложка, визуальная концепция, типографика и композиционные принципы не меняются без блокирующей технической причины печатного preflight. Заморозка не даёт права менять факты или механически копировать содержание.

`design/prototypes/print-v21/PRINT_V21_GENERATOR_PILOT.pdf` — сохранённый ранний
пилот первых пяти семей. Он больше не является блокировкой массовой сборки.
Актуальный полный черновик строится через `scripts/build_book.py`; канонические
справочники и family manifests находятся в `content/production/`.

`design/prototypes/print-v23/PRINT_V23_COMPACT_INTRO_TEST.pdf` — актуальный
компактный вводный блок. В нём карта и статистика сведены на одну страницу,
приветствия занимают по одной странице, содержание остаётся двухстраничным, а
первая семья начинается на чётной левой странице 14. Визуальная система V20 при
этом остаётся Design Lock.

Текущая полная draft-сборка находится в `output/`:

- `PRINT_V21_FULL_DRAFT_SPREADS.pdf` — клиентский просмотр разворотами, с
  утверждённой обложкой;
- `PRINT_V21_INTERIOR_PAGES_PROOF.pdf` — интерьер отдельными страницами с
  MediaBox/BleedBox 266 × 206 мм и TrimBox 260 × 200 мм;
- `page-plan.json`, `generated-toc.json` и `placement-ledger.json` —
  воспроизводимая пагинация и учёт каждого элемента;
- `preflight-report.md` и `review-queue.csv` — техническая проверка и ручная
  очередь;
- `full-contact-sheet.pdf` и `review-batches/` — визуальная проверка.

Это полный V21 draft-проход, а не новый Design Lock. Точное число страниц,
placement-записей, DPI-предупреждений и элементов review queue всегда
пересчитывается текущим запуском и читается из свежих файлов в `output/`;
значения из предыдущих отчётов нельзя переносить в handoff как константы.

Полная команда: `python scripts/build_book.py --families all --profile draft
--resume`. Ошибка одной семьи изолируется, кеш хранится в `output/families/`,
checkpoint — в `output/checkpoints/`. Финальный редакционный разворот подключён
как предложение и требует утверждения владельца; его нельзя считать исходным
фактом референса.

После подготовки читательских расшифровок классификация пересчитана: **58** семей предварительно относятся к `standard`, **16** — к `extended`. Актуальный список всегда брать из `assets/families/family-template-classification.json`, а не из старых отчётов.

`design/prototypes/print-v12/` остаётся источником действующего вступительного блока и стандартного разворота Анастасии. Страница Анастасии — ориентир масштаба и роли флагманского изображения, но не источник фактов.

`design/prototypes/print-v11/` временно остаётся активной зависимостью V12: оттуда используются вводные изображения, награда, герб и карта. Не перемещать V11 до переноса этих зависимостей.

## Рабочие данные

- `assets/families/` — нормализованный каталог семей и новый источник рабочих пакетов.
- `assets/for-gigapixel/` — пустой staging для следующей явно согласованной партии; завершённая партия уже архивирована.
- `assets/production-ready/` — 281 зарегистрированный апскейл и единый print-manifest; вёрстка берёт производный файл из `print_file`, не затирая master.
- `assets/processed-flagships/` — только проверенные или ожидающие проверки флагманские PNG после CutItOut.
- `assets/processed-flagships/manual-cutout-help-list.json` — короткая очередь сложных флагманов, которым нужна ручная кисть; Евгений (`hero-014`) помечен решённым после появления версии с чистым белым фоном.
- `assets/manual-cutout-help/` — готовый пакет 13 оставшихся сложных случаев: для каждого сохранены оригинал, лучший апскейл и текущая маска для ручной обработки.
- `assets/families/letters-transcriptions-index.json` — актуальный индекс физических рукописей и связанных двухслойных кандидатов расшифровки. Рукописи `hero-058` и `hero-069` восстановлены из ошибочно классифицированных архивных изображений и зарегистрированы со статусом `REVIEW_REQUIRED`. Единственная семья, у которой действительно не зарегистрированы физическая рукопись и расшифровка, — `hero-065`. Лист `hero-006` повторно подтверждён в каноническом референсе.
- `assets/families/transcription-batches/batch-a.json` и `batch-b.json` — отчёты визуальной расшифровки и перечни сомнительных мест; их нельзя считать автоматическим утверждением текста для печати.
- `project-reset/archived/duplicate-assets/production-input-pre-reset/` — прежний источник миграции, сохранённый только для provenance и отката; активная работа ведётся из `assets/families/` и `assets/production-ready/`.
- `project-reset/archived/` — сохранённые старые решения. Не возвращать их в работу без явного решения владельца.

Активная техническая прослойка намеренно мала: `normalize_family_assets.py`, `export_for_gigapixel.py`, `ingest_gigapixel_results.py`, `apply_flagship_selections.py`, `build_flagship_queue.py`, `batch_cutitout.py`, `build_family_layout_plan.py`, `register_recovered_letters.py`, `build_reference_map_fallbacks.py`, `build_reference_symbol_fallbacks.py`, `normalize_production_manifest_schema.py`, `book_pipeline.py`, `build_book.py`, `build_page_plan.py`, `build_toc.py`, `preflight_book.py`, `render_review.py`, `generate_v21_pilot.py`, `validate_v21_pilot.py`, `audit_pdf_preflight.py`, `check_v21_dom.mjs` и `render_print_prototype.mjs`. Прежний PDF-stage конвейер `01…15`, его manifests и прототипы перенесены в `project-reset/archived/abandoned-experiments/legacy-pdf-stage-pipeline/`; их нельзя запускать как актуальный pipeline.

## Документальные fallback-ассеты

- `content/production/maps/reference-fallback/` — 30 фрагментов карт для 30 регионов, извлечённых из канонических титульных страниц;
- `content/production/symbols/reference-fallback/emblems/` — 30 фрагментов гербов регионов;
- `content/production/symbols/reference-fallback/awards/` — 74 семейных фрагмента наград;
- ссылки и provenance записаны в `content/production/regions.json`, `content/production/emblems.json` и production family manifests.

Эти файлы разрешены как точные документальные подстановки в черновой макет, но
не переводят спорные официальные данные в статус `verified`. При появлении
проверенного отдельного ассета генератор должен предпочесть его fallback-фрагменту.

## Запрещённые действия

- менять V20 Design Lock без блокирующей технической причины печатного preflight;
- выбирать неизвестный флагман по внешнему виду;
- запускать CutItOut для семейного архива;
- создавать расшифровку по неоднозначной догадке или молча подменять дипломатическую версию редакторским текстом;
- переходить к следующей семье до проверки предыдущей;
- использовать архивные инструкции как актуальные правила.

## Минимальная проверка перед серийной работой

```powershell
python scripts\normalize_family_assets.py --dry-run
python scripts\export_for_gigapixel.py --dry-run
python scripts\ingest_gigapixel_results.py --dry-run
python scripts\apply_flagship_selections.py
python scripts\build_flagship_queue.py --dry-run
python scripts\build_family_layout_plan.py --edition draft --apply
python scripts\register_recovered_letters.py
python scripts\build_reference_map_fallbacks.py
python scripts\build_reference_symbol_fallbacks.py
python scripts\normalize_production_manifest_schema.py
python scripts\build_book.py --start-family hero-001 --count 5 --profile draft
python scripts\build_book.py --families all --profile draft --resume
```

Точные параметры команд сверять через `--help`: скрипты намеренно не должны молча перезаписывать master-файлы.

## Ручные титульные флагманы — актуальный статус

С 21 июля 2026 года все титульные флагманы проходят ручную проверку. CutItOut
используется как локальный технический инструмент, но автоматическая маска не
считается финально утверждённой сама по себе.

- `hero-001` и `hero-014` — действующие визуальные ориентиры;
- 57 прозрачных титульных PNG уже подключены к production family manifests со
  статусом `ready_for_draft_layout`; они не должны повторно попадать в ручную
  очередь;
- `assets/manual-cutout-help-next/` — завершённый пакет предыдущей ручной
  партии; 44 его маски прошли светлую/тёмную проверку, `hero-076` не принят;
- `assets/manual-cutout-help-remaining/` — актуальный короткий пакет: семь
  семей требуют подтверждения источника, пять документальных титульников —
  ручного решения по композиции, `hero-076` — исправления маски;
- `assets/processed-flagships/manual-owner-cutout-validation.json` — альфа,
  SHA-256, размеры и статус проверки новых 13 файлов;
- `scripts/integrate_owner_manual_flagships.py` — безопасная повторяемая
  регистрация этих файлов; dry-run используется по умолчанию;
- `scripts/build_next_title_cutout_package.py --verify-existing` — проверка
  завершённого большого пакета без изменения файлов;
- `scripts/build_remaining_title_package.py --verify-existing` — проверка
  актуального остаточного пакета без изменения файлов.

Для полной V21 draft-сборки семь семей пока получают нейтральный титульный
плейсхолдер вместо неподтверждённого флагмана: `hero-038`, `hero-052`,
`hero-055`, `hero-062`, `hero-064`, `hero-072`, `hero-074`. Это не разрешает
подставлять визуально похожий портрет. `hero-076` остаётся отдельным случаем
`manual mask review`: автоматическая маска не принимается как готовый титульник.

Титульная фигура компонуется вручную по ориентиру Евгения: крупно, с опорой на
нижний край и примерно по пояс. Для полнофигурного исходника допустим только
нижний композиционный crop; лицо, руки и важные предметы защищены. Прозрачный
PNG выводится в режиме `normal`, а не `multiply`.

Если исходное качество физически нельзя улучшить, effective DPI не скрывается.
Исключение оформляется только явным `OWNER_ACCEPTED_SOURCE_LIMIT`; оно не
разрешает дорисовывать фактические детали или указывать фиктивное разрешение.
