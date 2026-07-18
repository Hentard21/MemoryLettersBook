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

## Рендер текущего прототипа

Не запускать во время reset. После отдельного согласования:

```powershell
& $Node scripts\render_print_prototype.mjs `
  --input design\prototypes\print-v12\interior.html `
  --output design\prototypes\print-v12\PRINT_V12_FIRST_FAMILY_CLIENT_EXAMPLE.pdf `
  --channel msedge
```

## Проверка PDF

```powershell
$Pdf = 'design\prototypes\print-v12\PRINT_V12_FIRST_FAMILY_CLIENT_EXAMPLE.pdf'
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
