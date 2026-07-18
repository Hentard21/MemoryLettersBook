# AI handoff после reset

Перед любым изменением проекта обязательно прочитать:

1. `docs/PROJECT_RULES_RESET.md` — главный регламент и единый источник рабочих правил;
2. `docs/REFERENCE_LOCK.md` — порядок и принадлежность материалов;
3. `docs/SEQUENTIAL_WORKFLOW.md` — разрешённая последовательность действий;
4. `assets/families/family-processing-plan.json` — текущий план обработки семей;
5. `assets/families/letters-transcriptions-index.json` — связка рукописей и расшифровок.

## Неподвижные условия

- `source/reference.pdf` — структурный и содержательный эталон.
- Текущий эталон содержит 246 страниц; его SHA-256 зафиксирован в `source/reference.sha256`.
- Активный порядок 74 семей хранится в `content/manifests/reference-family-order-reset.json`; ID `hero-002` и `hero-016` не входят в финальный референс и не должны возвращаться в очередь.
- Утверждённая обложка `design/cover-v1/artwork/cover-art.png` не меняется.
- Порядок семей и материалов не меняется.
- Контент не сокращается, не переписывается и не дополняется догадками.
- Каждая рукопись должна физически присутствовать и иметь отдельную расшифровку либо честный статус `missing`/`REVIEW_REQUIRED`.
- Материалы разных семей не смешиваются.
- Новая работа выполняется только последовательно от начала референса.
- Одна семья получает один основной разворот. Если полный документальный комплект не проходит реальную проверку читаемости, непосредственно следом автоматически добавляется максимум один разворот-продолжение; уменьшать текст и фотографии до нечитаемого размера запрещено.

## Текущий визуальный ориентир

`design/prototypes/print-v12/` сохраняется как действующий прототип. Страница Анастасии — ориентир масштаба и роли флагманского изображения, но не источник фактов и не шаблон для механического копирования контента.

`design/prototypes/print-v11/` временно остаётся активной зависимостью V12: оттуда используются вводные изображения, награда, герб и карта. Не перемещать V11 до переноса этих зависимостей.

## Рабочие данные

- `assets/families/` — нормализованный каталог семей и новый источник рабочих пакетов.
- `assets/for-gigapixel/` — пустой staging для следующей явно согласованной партии; завершённая партия уже архивирована.
- `assets/production-ready/` — 281 зарегистрированный апскейл и единый print-manifest; вёрстка берёт производный файл из `print_file`, не затирая master.
- `assets/processed-flagships/` — только проверенные или ожидающие проверки флагманские PNG после CutItOut.
- `project-reset/archived/duplicate-assets/production-input-pre-reset/` — прежний источник миграции, сохранённый только для provenance и отката; активная работа ведётся из `assets/families/` и `assets/production-ready/`.
- `project-reset/archived/` — сохранённые старые решения. Не возвращать их в работу без явного решения владельца.

Активная техническая прослойка намеренно мала: `normalize_family_assets.py`, `export_for_gigapixel.py`, `ingest_gigapixel_results.py`, `apply_flagship_selections.py`, `build_flagship_queue.py`, `batch_cutitout.py`, `build_family_layout_plan.py` и `render_print_prototype.mjs`. Прежний PDF-stage конвейер `01…15`, его manifests и прототипы перенесены в `project-reset/archived/abandoned-experiments/legacy-pdf-stage-pipeline/`; их нельзя запускать как актуальный pipeline.

## Запрещённые действия

- менять дизайн или пересобирать PDF на этапе reset;
- выбирать неизвестный флагман по внешнему виду;
- запускать CutItOut для семейного архива;
- создавать расшифровку по догадке;
- переходить к следующей семье до проверки предыдущей;
- использовать архивные инструкции как актуальные правила.

## Минимальная проверка перед серийной работой

```powershell
python scripts\normalize_family_assets.py --dry-run
python scripts\export_for_gigapixel.py --dry-run
python scripts\ingest_gigapixel_results.py --dry-run
python scripts\apply_flagship_selections.py
python scripts\build_flagship_queue.py --dry-run
python scripts\build_family_layout_plan.py
```

Точные параметры команд сверять через `--help`: скрипты намеренно не должны молча перезаписывать master-файлы.
