# Политика разрешения ассетов (master ↔ upscaled)

Как сайт и печать выбирают, какую версию картинки показывать, по мере того как владелец заполняет `assets/derived-upscaled/`.

## Правило

Для каждого ассета:

```
preferred = derived_upscaled   ЕСЛИ  upscaled-файл существует  И  прошёл приёмку (approved)
preferred = master_from_pdf    во всех остальных случаях
```

- Пока апскейла нет — везде используется `master_from_pdf` (нативный из PDF). Прототип работает сразу, без ожидания.
- Появился одобренный upscaled — он подхватывается автоматически при следующем прогоне резолвера.
- Не одобренный (или не проверенный) upscaled **не** используется, даже если файл лежит рядом.

## Поля в данных

В `content/prototypes/*/content.json` у каждого ассета:

```json
{
  "master_asset": "assets/master-from-pdf/heroes/hero-001/photos/hero-001_photo_01_master.png",
  "expected_upscaled_asset": "assets/derived-upscaled/heroes/hero-001/photos/hero-001_photo_01_upscaled.png",
  "preferred_web_asset": "…",
  "preferred_print_asset": "…",
  "upscaled_available": false
}
```

`preferred_web_asset` и `preferred_print_asset` заполняет резолвер. Сейчас они разделены на случай, если для веба и печати позже понадобятся разные версии (напр. для печати — только `approved`, для веба допустим и более мягкий вариант). Пока правило для обоих одинаковое.

## Кто и когда это делает

- Скрипт: `scripts/12_resolve_assets.py`. Идемпотентен, ничего не удаляет, master не трогает.
- Запуск: после каждого пополнения `assets/derived-upscaled/` или `assets/review/approved/`.
- Что делает:
  1. ищет upscaled-файл по зеркальному пути (`<asset_id>_upscaled.*`);
  2. проверяет одобрение (по `review_status` в `upscale-manifest.json` или по копии в `assets/review/approved/`);
  3. выбирает master или upscaled;
  4. обновляет `content.json` прототипов и перезаписывает файлы веб-прототипа (печать берёт те же файлы);
  5. пишет отчёт `content/manifests/asset-resolution.json` — что и почему выбрано.

## Прозрачность и обратимость

- `asset-resolution.json` фиксирует по каждому ассету: выбран master или upscaled, доступен ли upscaled, одобрен ли, `publish_blocked`.
- Master-версии неизменны — в любой момент можно откатиться, удалив/забраковав upscaled и перезапустив резолвер.
- Печать: в тираж идёт `preferred_print_asset` только если это `approved` upscaled **или** сознательно принятый master (для графики, которую не апскейлят).
