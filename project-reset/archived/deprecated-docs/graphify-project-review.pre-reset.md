# Проверка полезности Graphify для проекта

Дата: 2026-07-18. Граф построен локально, без LLM/API и без анализа PDF/изображений. Источник: `graphify-out/graph.json`.

## Краткий вывод

Финальная локальная сборка: 127 текстовых файлов, 903 узла, 2386 связей, 84 community; token/API cost — 0. Graphify полезен как навигатор по hero ID, манифестам, скриптам и прямым ссылкам между документами. Он особенно хорошо отвечает на `explain <hero-id>` и `path <конкретный файл> <конкретный файл>`. Свободные широкие `query` по словам `manifest`, `map` или `assets` сейчас шумные: старые документы и крупные постраничные манифесты образуют hubs.

Использовать постоянно стоит, но как первый индекс, а не как источник фактов. Для точной редакционной проверки ответ графа всегда сверяется с манифестом и оригинальным референсом.

## Ответы на контрольные вопросы

### Какие файлы описывают `hero-001`

`graphify explain "hero-001"` нашёл десятки прямых `EXTRACTED`-связей. Основные группы:

- реестр и пагинация: `content/entities/heroes.pdf-stage.json`, `content/manifests/book-manifest.pdf-stage.json`, `.csv`;
- принадлежность материалов: `content/manifests/web-assets.pdf-stage.json`, `mixed-material-decomposition.pdf-stage.json`, `reference-first-20-map.json`;
- image pipeline: `content/manifests/upscale-manifest.json`, `.csv`, `asset-resolution.json`, `image-jobs.json`;
- производственный выбор: `assets/production-input/flagship-images.json`, `jobs.json`, `jobs.csv`;
- пакет семьи: `content/prototypes/hero-001/content.json`, `web-package.json`;
- печатный consumer: `design/prototypes/print-v11/interior.html` и исторические print HTML;
- правила: `docs/AI_HANDOFF.md`, `asset-resolution-policy.md`, `map-and-emblems-plan.md`, `prototype-10-pages-plan.md`;
- генераторы: `scripts/10_build_prototype_packages.py`, `11_build_asset_pipeline.py`, `12_resolve_assets.py`, `13_build_print_v3_data.py`, `15_build_production_input.py`.

Полезность: высокая для поиска всех consumers по одному `hero_id`. Ограничение: наличие связи означает упоминание ID, а не подтверждение корректности материала.

### Какие скрипты изменяют книжные манифесты

Граф показал script/manifest hubs; локальная сверка write-sites уточнила роли:

| Скрипт | Что пишет/изменяет |
|---|---|
| `02_build_manifest.py` | book manifest, heroes registry, sections |
| `04_merge_visual_classification.py` | book manifest JSON/CSV |
| `05_update_hero_boundaries.py` | heroes registry |
| `06_add_visual_verdicts.py` | editorial issues |
| `07_build_web_assets_registry.py` | web-assets manifest |
| `08_decompose_mixed_pages.py` | mixed-material decomposition и book manifest |
| `09_extract_prototype_assets.py` | prototype assets index |
| `10_build_prototype_packages.py` | `content/prototypes/<hero>/content.json` |
| `11_build_asset_pipeline.py` | upscale manifest JSON/CSV и hero content packages |
| `12_resolve_assets.py` | upscale manifest, asset-resolution и resolved hero packages |
| `13_build_print_v3_data.py` | contents и web packages |
| `15_build_production_input.py` | production-input manifests/jobs |

Перед запуском любого из них нужно считать его mutating-командой; это не smoke tests.

### Как связаны исходный PDF, извлечённые ассеты и печатные прототипы

Рабочая цепочка, подтверждённая ссылками в docs/scripts/manifests:

```text
source/reference.pdf
  -> scripts/01_analyze_pdf.py
  -> workspace/extracted-text + workspace/reports/pdf-analysis.json
  -> scripts/02_build_manifest.py
  -> content/manifests + content/entities + content/sections
  -> scripts/09_extract_prototype_assets.py / 11_build_asset_pipeline.py
  -> assets/master-from-pdf + content/prototypes + upscale-manifest
  -> scripts/12_resolve_assets.py
  -> asset-resolution.json / resolved packages
  -> design/prototypes/print-*/interior.html
  -> scripts/render_print_prototype.mjs
  -> PDF prototype
```

Сам PDF исключён из графа намеренно; Graphify видит его как ссылочную тему из документов, но не читает содержимое. `graphify path "reference pdf" "design/prototypes/print-v11/interior.html"` строит косвенный путь через документацию и map-topic. Это полезно для навигации, но не доказывает полную lineage каждого изображения.

### Где зафиксированы правила карт, гербов и порядка семей

- канонические region data: `content/regions/regions.json` (`region_code`, `map_feature_id`, `emblem_file`);
- порядок первых страниц/семей и принадлежность: `content/manifests/reference-first-20-map.json`;
- карта/гербы/награды: `docs/map-and-emblems-plan.md`, `docs/page-archetypes.md`, `docs/print-adaptation-plan.md`;
- общий handoff: `docs/AI_HANDOFF.md`;
- визуальный consumer: `design/prototypes/print-v11/interior.html`.

Свободный Graphify path от generic `family order` к map JSON не сработал: термин не был единообразно назван. Для графа лучше запрашивать конкретное имя `reference-first-20-map.json` или `hero-001`.

### Что обновлять при замене флагманского портрета

Для `hero-001`:

1. `assets/production-input/flagship-images.json` — роль, source и processed file;
2. соответствующую запись в `assets/production-input/jobs.json`/`.csv`, если обработка меняется;
3. `content/manifests/upscale-manifest.json`/`.csv` и `asset-resolution.json`, если меняется выбранный resolved asset;
4. `content/prototypes/hero-001/content.json` и `web-package.json` (`featuredPhoto`/resolved paths);
5. `design/prototypes/print-v11/interior.html`, пока он использует жёстко прописанные пути;
6. после изменения — Graphify rebuild и Playwright/PDF visual check.

Найдена важная рассинхронизация: `asset-resolution.json` выбирает для `hero-001_photo_01` derived-upscaled файл, `flagship-images.json` знает Nana Banana output, а `print-v11/interior.html` одновременно использует и Nana Banana portrait, и production-input masters. До массовой работы нужен один resolver → consumer contract.

### Какие документы противоречат правилу полного манифеста

Текущему правилу «ознакомительный разворот + отдельный полный манифест целиком» противоречат:

- `docs/family-spread-v3.md` — одна семья/один разворот, printExcerpt и QR;
- `docs/prototype-10-pages-plan.md` — фрагмент письма, полоска почерка и QR;
- `docs/pagination-plan-v3.md` — семья занимает одну пару страниц;
- `docs/print-structure-v2.md` — один разворот вокруг скана/цитаты;
- ранние строки `docs/AI_HANDOFF.md` — одна семья = один разворот, полный оригинал только в web/QR;
- `content/prototypes/*/web-package.json` и старые print HTML содержат `printExcerpt`/QR-era структуру.

В `AI_HANDOFF.md` добавлено приоритетное уточнение текущего правила, но исторические документы пока не переписаны. Также в `design/prototypes/print-v11/interior.html` найден фактический typo: «Анастасия · полный манифест Игоря». Макет в рамках этой задачи не менялся; исправление вынесено в следующий контентный этап.

## Что Graphify нашёл хорошо

- быстро собрал consumers одного `hero_id`;
- показал write-heavy script/manifest узлы;
- связал docs с конкретными JSON и HTML;
- выявил старые правила через общие темы `full manifest`, `map`, `emblems`, `flagship portrait`;
- `diagnose multigraph` подтвердил отсутствие dangling/missing endpoints, self-loops и collapsed edges.

## Ошибочные или шумные связи

- крупные page/hero manifests становятся god nodes и попадают почти в любой широкий query;
- topic nodes (`manifest`, `maps`, `reference pdf`) связывают документы по наличию терминов, а не по причинной зависимости;
- старые v3/v5 HTML и docs индексируются вместе с текущими и создают конфликтующие neighborhoods;
- HTML/CSS и CSV добавляются локальным project adapter, поэтому их связи в основном lexical/file-reference, не семантические;
- изображения и PDF намеренно отсутствуют; граф знает только их пути из manifests/docs;
- community labels оставлены локальными `Community N`, потому что LLM-labeling не запускался.
- штатный structural extractor сообщил о JSON без извлекаемых сущностей; project adapter всё равно добавляет для них file/reference nodes, поэтому operational manifests присутствуют в итоговом графе.

## Рекомендация по постоянному использованию

Да, для навигации и impact analysis. Рекомендуемый порядок:

1. `graphify explain "hero-XXX"`;
2. `graphify path "точный файл A" "точный файл B"`;
3. только затем `query` и `rg` для точных строк;
4. факты сверить с reference manifest/PDF.

Граф пересобирать после:

- изменения структуры `content/` или JSON/CSV manifests;
- добавления/замены hero package или flagship mapping;
- изменения scripts, которые пишут manifests;
- обновления HTML/CSS consumers;
- существенного изменения правил в `docs/`;
- перед началом массовой верстки и после завершения крупного batch.

Не пересобирать после простого добавления рендера, PDF, изображения, апскейла или временного файла: они исключены.
