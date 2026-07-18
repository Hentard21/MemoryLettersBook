# Handoff `ForMacbook`

Ветка содержит reset проекта, master-файлы семей, 281 принятый апскейл, 65 выбранных флагманов, 58 черновых прозрачных PNG, manifests и QA-отчёты. Дизайн и PDF на этом этапе не пересобирались.

## Скачать и проверить

```bash
git clone --branch ForMacbook --single-branch https://github.com/Hentard21/MemoryLettersBook.git
cd MemoryLettersBook

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-tools.txt

python scripts/validate_production_readiness.py
```

Ожидаемый статус проверки: `ready_with_documented_blockers`, `errors: []`.

## Где продолжать работу

- правила: `docs/PROJECT_RULES_RESET.md`;
- правило количества разворотов: `docs/MASS_LAYOUT_POLICY.md`;
- порядок: `content/manifests/reference-family-order-reset.json`;
- семейные master-файлы: `assets/families/`;
- печатные апскейлы: `assets/production-ready/`;
- прозрачные черновики: `assets/processed-flagships/`;
- QA вырезок: `project-reset/reports/flagship-cutouts/`;
- блокеры массовой вёрстки: `project-reset/reports/mass-layout-readiness.md`.

## CutItOut на новом компьютере

Готовые 58 PNG уже находятся в Git, поэтому повторный запуск не нужен. Для новой маски CutItOut устанавливается рядом с репозиторием, а не внутрь него:

```bash
mkdir -p ../tools
git clone https://github.com/Suvink/cut-it-out.git ../tools/cut-it-out
cd ../tools/cut-it-out
npm install
cd ../../MemoryLettersBook
```

Локальный Playwright — runtime, он намеренно не хранится в Git:

```bash
mkdir -p .tools/playwright
cd .tools/playwright
npm init -y
npm install playwright
npx playwright install chromium
cd ../..
```

После этого доступен точечный повторный прогон:

```bash
python scripts/batch_cutitout.py \
  --queue assets/processed-flagships/flagship-processing-queue.json \
  --only-hero hero-003 \
  --limit 1 \
  --force \
  --apply
```

Без `--apply` команда остаётся dry-run. Автоматический результат никогда не получает `approved` без ручной проверки маски.
