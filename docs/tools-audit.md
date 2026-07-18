# Аудит инструментов проекта

Дата проверки: 2026-07-18. Рабочая папка: `book-project/`.

Макет книги и существующие PDF в ходе аудита не изменялись. Диагностические файлы лежат в `tmp/tool-audit/`.

## Итог

| Инструмент | Версия | Статус | Минимальный безопасный тест |
|---|---:|---|---|
| Graphify | 0.9.18 (`graphifyy`) | работает через executable собственного окружения; project-scoped skill установлен | `--version`, `install --help`, локальная сборка и read-only query/diagnose |
| Playwright CLI | 1.61.1 | установлен project-scoped в `.tools/playwright/`; использует системный Microsoft Edge | локальный HTML открыт и сохранён в `tmp/tool-audit/playwright-index.png` |
| Codex Browser skill (Playwright API) | bundle 26.715.21425 | работает | создана фоновая вкладка `about:blank`, проверены title/URL, вкладка закрыта |
| MarkItDown | 0.1.6 | установлен project-scoped в `.tools/markitdown/` | HTML преобразован в `tmp/tool-audit/markitdown-index.md` |
| Context7 | — | не установлен: нет CLI и доступного MCP-инструмента | проверено наличие команды, переменной окружения и callable tool |
| Codex PDF skill | bundle 26.715.12143 | работает; системные Poppler wrappers повреждены, прямые binaries исправны | метаданные существующего PDF прочитаны, одна страница отрендерена в `tmp/tool-audit/pdf-page.png` |

## Graphify

Версия:

```powershell
& 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe' --version
```

Результат: `graphify 0.9.18`.

Глобальный launcher `C:\Users\MarkII\.local\bin\graphify.exe` не работает: `uv trampoline failed to canonicalize script path`. Переустановка не выполнялась, потому что штатный executable внутри уже установленного окружения исправен. Project hook в `.codex/hooks.json` направлен на рабочий executable.

Project-scoped установка выполнена документированной командой версии 0.9.18:

```powershell
& 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe' install --project --platform codex
```

Созданы `.codex/skills/graphify/`, `AGENTS.md` и `.codex/hooks.json`. Синтаксис исключений подтверждён по установленной реализации: `.graphifyignore` использует правила gitignore, включая вложенные ignore-файлы и `!`-исключения.

Для этого проекта используется локальная сборка без LLM-backend:

```powershell
& 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\python.exe' scripts\build_graphify_project_graph.py .
& 'C:\Users\MarkII\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe' export html
```

Она использует штатные Graphify extractors, добавляет CSV/HTML/CSS как проектные file/reference nodes и не отправляет документы наружу. PDF, изображения, рендеры, апскейлы, `workspace/`, `tmp/`, `.tools/`, `.codex/`, `node_modules/` и `graphify-out/` исключены. Текстовые JSON/CSV/MD-манифесты внутри `assets/` включены, сами ассеты — нет.

## Playwright CLI и Browser skill

Версия CLI:

```powershell
& '.\.tools\playwright\node_modules\.bin\playwright.cmd' --version
```

Результат: `Version 1.61.1`.

Безопасный тест с уже установленным Edge:

```powershell
$url = (New-Object System.Uri((Resolve-Path 'design\prototypes\web\index.html'))).AbsoluteUri
& '.\.tools\playwright\node_modules\.bin\playwright.cmd' screenshot --channel msedge --viewport-size '1280,720' --wait-for-timeout 500 $url 'tmp\tool-audit\playwright-index.png'
```

Bundled-копия Playwright в Codex runtime была неполной (`playwright-core` отсутствовал), поэтому рабочий CLI установлен только в `.tools/playwright/`, без скачивания браузеров. Browser skill Codex проверен отдельно и доступен для интерактивной визуальной проверки.

## MarkItDown

Версия:

```powershell
& '.\.tools\markitdown\Scripts\python.exe' -m markitdown --version
```

Результат: `0.1.6`.

Безопасный тест:

```powershell
& '.\.tools\markitdown\Scripts\python.exe' -m markitdown 'design\prototypes\web\index.html' -o 'tmp\tool-audit\markitdown-index.md'
```

Установлены локальные extras для PDF, DOCX, PPTX и XLSX. По умолчанию используется офлайн-конвертация; параметры Azure Document Intelligence/Content Understanding не применять без отдельного решения владельца.

## Context7

Проверка:

```powershell
Get-Command context7 -ErrorAction SilentlyContinue
Test-Path Env:CONTEXT7_API_KEY
```

Команда, ключ и MCP-инструмент отсутствуют. Context7 не устанавливался: запрос требовал проверить его только при наличии.

## PDF skill Codex

Версии компонентов:

- PDF skill bundle: `26.715.12143`;
- Poppler `pdfinfo` / `pdftoppm`: `26.05.0`;
- `pypdf`: `6.10.0`;
- `pdfplumber`: `0.11.9`;
- `reportlab`: `4.4.9`.

Рабочие команды:

```powershell
$Poppler = 'C:\Users\MarkII\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
& "$Poppler\pdfinfo.exe" 'design\prototypes\print-v11\interior.pdf'
& "$Poppler\pdftoppm.exe" -f 1 -l 1 -singlefile -scale-to 200 -png 'design\prototypes\print-v11\interior.pdf' 'tmp\tool-audit\pdf-page'
```

Wrappers `pdfinfo.cmd` и `pdftoppm.cmd` в `dependencies/bin/override/` указывают на несуществующий `native/poppler/bin/`; использовать прямые binaries из `native/poppler/Library/bin/`.
