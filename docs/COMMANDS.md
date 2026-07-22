# Команды проекта после reset

Все команды запускаются из корня `book-project` в PowerShell.

## Базовые переменные

```powershell
$Project = (Resolve-Path '.').Path
$Python = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$Node = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$Poppler = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
```

## Проверка и нормализация семей

Сначала всегда dry-run:

```powershell
& $Python scripts\normalize_family_assets.py `
  --classifications project-reset\clean-structure-plan\verified-flagship-classifications.json `
  --dry-run
```

Применение только после просмотра плана:

```powershell
& $Python scripts\normalize_family_assets.py `
  --classifications project-reset\clean-structure-plan\verified-flagship-classifications.json `
  --refresh-manifest `
  --apply
```

## Подготовка Gigapixel

```powershell
& $Python scripts\export_for_gigapixel.py --dry-run
& $Python scripts\export_for_gigapixel.py --apply
```

Экспортёр читает `assets/families/family-processing-plan.json` и копирует только материалы с `needs_gigapixel: true`. Master-файлы не перемещаются и не перезаписываются.

Приём завершённой партии сначала проверяется без изменений:

```powershell
& $Python scripts\ingest_gigapixel_results.py --dry-run
& $Python scripts\ingest_gigapixel_results.py --apply
```

Текущая партия уже принята: 281 производный файл находится в `assets/production-ready/`, а завершённый staging сохранён в архиве.

## Восстановление и нормализация production-данных

Все четыре команды по умолчанию работают как dry-run. `--apply` использовать
только после просмотра вывода и сверки с `source/reference.pdf`.

Регистрация двух восстановленных рукописей (`hero-058` и `hero-069`) и связанных
с ними расшифровок:

```powershell
& $Python scripts\register_recovered_letters.py
& $Python scripts\register_recovered_letters.py --apply
```

Построение документальных фрагментов карт из канонического референса:

```powershell
& $Python scripts\build_reference_map_fallbacks.py
& $Python scripts\build_reference_map_fallbacks.py --apply --force
```

Построение документальных fallback-фрагментов гербов и наград:

```powershell
& $Python scripts\build_reference_symbol_fallbacks.py
& $Python scripts\build_reference_symbol_fallbacks.py --apply --force
```

Нормализация обязательных полей production family manifests (`relationship` и
`source_pages`) без изменения содержания:

```powershell
& $Python scripts\normalize_production_manifest_schema.py
& $Python scripts\normalize_production_manifest_schema.py --apply
```

Fallback-файлы — это документальные вырезки из референса для черновой вёрстки,
а не автоматическая верификация официальных названий, наград или гербов.
Текущее состояние: восстановлены `hero-058` и `hero-069`; подготовлены 30
региональных карт, 30 гербов и 74 семейных фрагмента наград. Повторный запуск с
`--apply --force` нужен только при осознанном обновлении этих производных файлов.

## Выбор флагманов и план разворотов

```powershell
& $Python scripts\apply_flagship_selections.py
& $Python scripts\apply_flagship_selections.py --apply
& $Python scripts\build_family_layout_plan.py
& $Python scripts\build_family_layout_plan.py --apply
```

`apply_flagship_selections.py` не продвигает записи со статусом `REVIEW_REQUIRED`. `build_family_layout_plan.py` фиксирует блокеры расшифровок и правило «основной разворот + максимум один автоматический разворот-продолжение».

## Очередь флагманов и CutItOut

```powershell
& $Python scripts\build_flagship_queue.py --dry-run
& $Python scripts\build_flagship_queue.py --apply --force
```

CutItOut запускается отдельно и только для подтверждённых флагманов:

```powershell
Set-Location '..\tools\cut-it-out'
npm run dev -- --host 127.0.0.1
```

Результаты сохраняются в `assets/processed-flagships/<hero_id>/`, журнал — `assets/processed-flagships/flagship-cutout-log.json`.

Безопасный автоматизированный запуск через неизменённый локальный интерфейс:

```powershell
& $Python scripts\batch_cutitout.py `
  --queue assets\processed-flagships\flagship-processing-queue.json `
  --limit 1

& $Python scripts\batch_cutitout.py `
  --queue assets\processed-flagships\flagship-processing-queue.json `
  --limit 1 `
  --apply
```

Без `--apply` выполняется только проверка. Автоматический PNG всегда получает статус `needs_manual_mask_review`; он не считается утверждённым без проверки волос, рук, оружия, ремней, формы и предметов.

Проверка размеров/alpha и пересборка светлых/тёмных контактных листов:

```powershell
& $Python scripts\validate_flagship_cutouts.py
& $Python scripts\validate_flagship_cutouts.py --apply
```

Регистрация 13 подготовленных владельцем титульных изображений выполняется
повторяемо и без перезаписи master-файлов:

```powershell
& $Python scripts\integrate_owner_manual_flagships.py
& $Python scripts\integrate_owner_manual_flagships.py --apply
```

Проверка завершённой большой ручной очереди:

```powershell
& $Python scripts\build_next_title_cutout_package.py --verify-existing
```

Проверка актуального остаточного пакета титульников:

```powershell
& $Python scripts\build_remaining_title_package.py --verify-existing
```

Повторная регистрация возвращённой большой партии (dry-run по умолчанию):

```powershell
& $Python scripts\integrate_next_owner_flagships.py --register --needs-fix hero-076
& $Python scripts\integrate_next_owner_flagships.py --register --needs-fix hero-076 --apply
```

`batch_cutitout.py` сам временно запускает установленный локальный Vite и один
Chromium; для этого сценария отдельный `npm run dev` не нужен.

## Проверка JSON

```powershell
$Roots = @(
  'content',
  'config',
  'assets\families',
  'assets\processed-flagships',
  'project-reset\clean-structure-plan',
  'project-reset\reports'
)
$JsonFiles = Get-ChildItem -Path $Roots -Recurse -File -Filter *.json
$Errors = foreach ($File in $JsonFiles) {
  try {
    Get-Content -LiteralPath $File.FullName -Raw -Encoding utf8 | ConvertFrom-Json | Out-Null
  } catch {
    "$($File.FullName): $($_.Exception.Message)"
  }
}
if ($Errors) { $Errors | ForEach-Object { Write-Error $_ }; throw 'JSON validation failed' }
"JSON OK: $($JsonFiles.Count) files"
```

## Проверка Python

```powershell
& $Python -m compileall -q scripts
```

## Graphify

```powershell
graphify update .
graphify query "hero-001 family assets"
Start-Process (Resolve-Path 'graphify-out\graph.html')
```

## Сохранённый ранний V21 pilot

V20 остаётся неизменяемым Design Lock. Ранний V21 pilot строится в два прохода
и физически рендерит только первые пять семей. Для текущей полной draft-сборки
использовать `build_book.py` из следующего раздела.

```powershell
& $Python scripts\generate_v21_pilot.py
& $Python scripts\generate_v21_pilot.py --render
```

## Полная data-driven сборка

V20 остаётся визуальным Design Lock, а компактное вступление V23 подключается
как актуальный вводный блок. Полный черновой том из 74 семей собирается одной
командой:

```powershell
& $Python scripts\build_book.py --families all --profile draft --resume
```

Чистая пересборка без семейного кеша:

```powershell
& $Python scripts\build_book.py --families all --profile draft --force
```

Быстрая проверка ограниченного последовательного фрагмента:

```powershell
& $Python scripts\build_book.py --start-family hero-001 --count 5 --profile draft
```

Повторное создание контактного листа и пакетов рецензирования:

```powershell
& $Python scripts\render_review.py
```

Основные результаты находятся в `output\`: клиентские развороты,
постраничный proof, `page-plan.json`, динамическое содержание,
`placement-ledger.json`, preflight и очередь ручной проверки.

Число страниц, записей placement ledger, предупреждений DPI и элементов очереди
не фиксируется в этом документе: оно пересчитывается каждой полной сборкой и
берётся из свежих `output\page-plan.json`, `output\placement-ledger.json` и
`output\preflight-report.md`.

## Проверка PDF

```powershell
$Pdf = 'design\prototypes\print-v21\PRINT_V21_GENERATOR_PILOT.pdf'
& $Python scripts\validate_v21_pilot.py `
  --output-dir design\prototypes\print-v21 `
  --pdf $Pdf `
  --minimum-dpi 180 `
  --strict
& "$Poppler\pdfinfo.exe" $Pdf
New-Item -ItemType Directory -Force -Path 'tmp\pdf-check' | Out-Null
& "$Poppler\pdftoppm.exe" -f 1 -l 5 -r 144 -png $Pdf 'tmp\pdf-check\spread'
```

## Скриншот HTML через Playwright

```powershell
$Playwright = '.\.tools\playwright\node_modules\.bin\playwright.cmd'
$Html = (New-Object System.Uri((Resolve-Path 'design\prototypes\print-v12\interior.html'))).AbsoluteUri
New-Item -ItemType Directory -Force -Path 'tmp\playwright' | Out-Null
& $Playwright screenshot --channel msedge --full-page --wait-for-timeout 500 $Html 'tmp\playwright\print-v12.png'
```

## MarkItDown

```powershell
& '.\.tools\markitdown\Scripts\python.exe' -m markitdown `
  'source\reference.pdf' `
  -o 'tmp\reference-structure.md'
```

MarkItDown, OCR, Graphify и макеты не являются источниками фактов без сверки с `source/reference.pdf` и семейным manifest.
