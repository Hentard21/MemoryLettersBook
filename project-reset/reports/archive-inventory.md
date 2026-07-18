# Инвентаризация архива reset

Дата reset: 18 июля 2026 года.

Ничего из перечисленного не удалено: материалы перемещены внутри `project-reset/archived/` и остаются доступны для истории и отката.

## old-prototypes

- `print/`
- `print-v3/`
- `print-v4/`
- `print-v5/`
- `print-v9/`
- `print-v10/`

Всего: 45 файлов, около 103,1 МБ.

Активными оставлены `design/prototypes/print-v12/` и `print-v11/`. V11 пока нужен как зависимость V12 для вводных изображений, награды, герба и карты Волгоградской области.

## deprecated-docs

- прежний `AI_HANDOFF.md`;
- прежний `COMMANDS.md`;
- прежние инструкции Gigapixel и CutItOut;
- `CLIENT_EXAMPLE_SPRINT.md`;
- `custom-skill-plan.md`;
- `family-block-scaling-note.md`;
- `family-spread-v3.md`;
- `pagination-plan-v3.md`;
- `print-structure-v2.md`;
- `prototype-10-pages-plan.md`;
- `source-of-truth-update.md`;
- прежние `PROJECT_BRIEF.md`, `content-model.md` и `editorial-workflow.md`;
- прежние cover/design/print/web планы;
- прежние правила семейного разворота, карты и гербов;
- прежние инструкции тестового batch и проверки upscale;
- исторический отчёт Graphify.

Всего: 27 файлов, около 0,2 МБ. Их правила больше не являются действующими.

## abandoned-experiments

- прежние `derived-upscaled` и review-папки;
- старый `family-block-v2` с тематическим дроблением текста;
- старые moodboards и веб-прототип;
- входы Nana Banana;
- тестовый Gigapixel-пакет;
- промежуточные рендеры V12, кроме утверждённого ориентира;
- прежние экспериментальные результаты обработки;
- прежний PDF-stage конвейер `01…15`, его классификатор, image-pipeline, manifests, front matter и прототипные пакеты;
- прежний 255-страничный `source/reference.pdf`;
- draft-only семейные блоки `hero-002` и `hero-016`;
- page-reference рендеры, созданные по старому 255-страничному PDF.

Полезные улучшенные результаты активных семей перед архивированием продублированы в нормализованные семейные папки. Всего в разделе: 423 файла, около 136,1 МБ.

## duplicate-assets

- `production-batches/` — прежние массовые pending-пакеты;
- `gigapixel-input-pre-reset/` — старая ручная выборка;
- `for-gigapixel-from-255-reference/` — первая reset-очередь, отозванная после сверки канонического PDF;
- `PRINT_V12_FIRST_FAMILY_CLIENT_EXAMPLE_REFRESHED.pdf` — идентичная cache-busting копия основного PDF.
- `production-input-pre-reset/` — прежний 618-файловый слой миграции; все активные семейные master-файлы уже находятся в `assets/families/`, provenance-пути обновлены на архив.
- `for-gigapixel-completed-2026-07-19/` — 281 исходник завершённой партии; 281 апскейл зарегистрирован в `assets/production-ready/manifest.json`.

Всего после приёма Gigapixel и архивации migration-слоя: 1492 файла, около 86,4 МБ.

## Что намеренно не архивировано

- `source/`;
- утверждённая обложка и шрифты;
- `design/prototypes/print-v12/`;
- `design/prototypes/print-v11/` из-за зависимости V12;
- `assets/master-from-pdf/`;
- `assets/nana-banana-output/`;
- текущая вырезка Анастасии;
- контентные manifests, regions, schemas и entities.

## Канонический референс после проверки

`source/reference.pdf` теперь является точной копией повторно предоставленного `refnew.pdf`: 246 страниц, SHA-256 `7D4F63C1E212D69B793DAB8FCC7E2E8216487C7BA06A089BBB767B5BC997B8E5`.

Сопоставление 74 семей зафиксировано в `content/manifests/reference-family-order-reset.json`. Стабильные ID не перенумеровывались, чтобы не разрушить связи с уже извлечёнными материалами.

Архив не используется как источник актуальных правил.
