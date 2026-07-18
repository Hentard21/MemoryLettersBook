# Production-ready image layer

Печатная вёрстка читает этот слой через `manifest.json`.

- `flagship/<hero_id>/` — выбранные флагманы после Gigapixel, до CutItOut;
- `archive/<hero_id>/` — поддерживающие семейные фотографии с сохранённым фоном;
- `drawings/<hero_id>/` — улучшенные рисунки;
- `manifest.json` — связь master → печатная производная и статус QA;
- `flagship-selections.json` — 74 решения в порядке референса.

Master-файлы остаются в `assets/families/` и никогда не перезаписываются.
Прозрачные PNG после CutItOut находятся отдельно в
`assets/processed-flagships/` и до ручной проверки имеют статус `needs-fix`.
