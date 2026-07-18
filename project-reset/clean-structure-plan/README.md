# Чистая структура после reset

## Активные источники

1. `source/reference.pdf` — порядок и содержание.
2. `docs/PROJECT_RULES_RESET.md` — правила.
3. `docs/REFERENCE_LOCK.md` — принадлежность материалов.
4. `assets/families/` — рабочие семейные пакеты.
5. `assets/families/family-processing-plan.json` — план обработки.
6. `assets/families/letters-transcriptions-index.json` — контроль писем.

Точный порядок 74 семей хранится в `content/manifests/reference-family-order-reset.json`. `hero-002` и `hero-016` относятся к прежнему 255-страничному draft и не входят в активную последовательность.

## Переходный источник

Прежний `assets/production-input/` после сверки и нормализации перемещён без удаления в `project-reset/archived/duplicate-assets/production-input-pre-reset/`. Новая работа ссылается на `assets/families/` и `assets/production-ready/`; архив используется только как provenance и для отката.

Прежний PDF-stage конвейер, старые manifests и прототипные пакеты находятся в `project-reset/archived/abandoned-experiments/legacy-pdf-stage-pipeline/`. В активном `scripts/` оставлены только три reset-утилиты и текущий рендерер.

## Визуальный checkpoint

`design/prototypes/print-v12/` остаётся текущим клиентским прототипом. Композиция Анастасии — ориентир для роли флагмана. Дизайн на этапе reset не меняется.

## Стоп-условие

До начала серийной сборки должны быть вручную подтверждены:

- следующий флагман по порядку референса;
- принадлежность всех материалов семьи;
- физические рукописи;
- отдельные расшифровки либо честный статус `missing`;
- регион, карта, герб и награда.
