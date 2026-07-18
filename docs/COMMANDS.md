# Команды проекта (Windows PowerShell)

Запускать из корня `book-project/`.

## Graphify

```powershell
$Graphify = 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe'
$GraphifyPython = 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\python.exe'

# Project-scoped skill (идемпотентно)
& $Graphify install --project --platform codex

# Полностью локальный граф проекта, без LLM/API
& $GraphifyPython scripts\build_graphify_project_graph.py .
& $Graphify export html

# Запросы к готовому графу
& $Graphify query 'hero-001 files' --budget 1500
& $Graphify explain 'hero-001' --graph graphify-out\graph.json
& $Graphify path 'flagship portrait' 'design/prototypes/print-v11/interior.html'
& $Graphify diagnose multigraph --graph graphify-out\graph.json --json
```

В Codex project skill вызывается как `/graphify .`. Headless `graphify extract .` без `--code-only` требует настроенного LLM-backend; для штатной массовой навигации проекта используйте локальный адаптер выше.

Открыть интерактивный граф:

```powershell
Start-Process (Resolve-Path 'graphify-out\graph.html')
```

## Рендер печатного прототипа

Команда приведена для ручного запуска. В рамках tools-аудита PDF не пересобирался.

```powershell
node scripts\render_print_prototype.mjs `
  --input design\prototypes\print-v11\interior.html `
  --output design\prototypes\print-v11\interior.pdf `
  --channel msedge
```

Скрипт применяет print media, `printBackground: true`, CSS page size и нулевые дополнительные margins.

## Проверка PDF

```powershell
$Poppler = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
$Pdf = 'design\prototypes\print-v11\interior.pdf'

& "$Poppler\pdfinfo.exe" $Pdf
New-Item -ItemType Directory -Force -Path 'tmp\pdf-check' | Out-Null
& "$Poppler\pdftoppm.exe" -f 1 -l 1 -singlefile -r 144 -png $Pdf 'tmp\pdf-check\page-001'
```

Для визуальной проверки нескольких страниц увеличьте `-l`, но не запускайте массовый рендер без необходимости.

## Скриншот Playwright

```powershell
$Playwright = '.\.tools\playwright\node_modules\.bin\playwright.cmd'
$Html = (New-Object System.Uri((Resolve-Path 'design\prototypes\print-v11\interior.html'))).AbsoluteUri
New-Item -ItemType Directory -Force -Path 'tmp\playwright' | Out-Null
& $Playwright screenshot --channel msedge --full-page --wait-for-timeout 500 $Html 'tmp\playwright\print-v11.png'
```

Для проверки интерактивного HTML внутри Codex также доступен Browser skill; он предпочтителен, когда нужны DOM-снимок, визуальная проверка и точечные действия на странице.

## MarkItDown

```powershell
$MarkItDown = '.\.tools\markitdown\Scripts\python.exe'
& $MarkItDown -m markitdown 'source\reference.pdf' -o 'tmp\reference-structure.md'
& $MarkItDown -m markitdown 'document.docx' -o 'tmp\document.md'
```

MarkItDown применяется для технического извлечения структуры. Его результат не становится источником фактов без сверки с референсом и манифестами.

## Проверка JSON-манифестов

```powershell
$JsonFiles = Get-ChildItem content,config -Recurse -File -Filter *.json
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

## Минимальные тесты проекта

В проекте пока нет единого test runner. Безопасная базовая проверка:

```powershell
$Python = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $Python -m compileall -q scripts
node --check scripts\render_print_prototype.mjs
& '.\.tools\playwright\node_modules\.bin\playwright.cmd' --version
& '.\.tools\markitdown\Scripts\python.exe' -m markitdown --version
```

После этого выполнить JSON-проверку из предыдущего раздела. Скрипты, меняющие манифесты или PDF, не входят в smoke test и запускаются только явно.

