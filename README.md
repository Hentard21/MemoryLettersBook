# book-project — «Письма памяти», том I

Проект прошёл инфраструктурный reset. Сейчас он не создаёт новую книгу, а последовательно адаптирует исходный PDF-референс без потери и подмены контента.

Начинать работу нужно с:

1. [PROJECT_RULES_RESET.md](docs/PROJECT_RULES_RESET.md)
2. [REFERENCE_LOCK.md](docs/REFERENCE_LOCK.md)
3. [SEQUENTIAL_WORKFLOW.md](docs/SEQUENTIAL_WORKFLOW.md)
4. [AI_HANDOFF.md](docs/AI_HANDOFF.md)
5. [FOR_MACBOOK.md](docs/FOR_MACBOOK.md) — перенос ветки на другой компьютер

Основные каталоги:

```text
source/                     неизменяемые исходники и PDF-референс
assets/families/            нормализованные пакеты семей
assets/production-ready/    принятые печатные производные и их manifest
assets/for-gigapixel/       staging следующей ручной партии апскейла
assets/processed-flagships/ результаты CutItOut только для флагманов
design/prototypes/print-v12 текущий визуальный checkpoint
project-reset/archived/     старые прототипы, документы и эксперименты
```

Канонический PDF содержит 246 страниц. Активный порядок 74 семей зафиксирован в `content/manifests/reference-family-order-reset.json`; ID из прежнего draft не перенумеровываются и хранятся в архиве.

Обложка утверждена и не меняется. Серийная сборка страниц начинается только после ручного утверждения семейного шаблона и идёт строго по порядку оригинального референса.

Одна семья получает один основной разворот. Если весь документальный комплект не помещается читаемо, сразу после него добавляется максимум один разворот-продолжение — фотографии и текст не ужимаются до нечитаемого размера.
