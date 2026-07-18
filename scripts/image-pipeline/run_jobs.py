# -*- coding: utf-8 -*-
"""
Раннер image-пайплайна (OpenRouter: Riverflow / Recraft).

СЕЙЧАС НИЧЕГО НЕ ГЕНЕРИРУЕТ: по умолчанию dry-run — печатает, что было бы
отправлено. Реальный запуск требует:
  1) .env с OPENROUTER_API_KEY (см. .env.example);
  2) флага --execute (явная команда владельца);
  3) статуса job'а "approved_to_run" в image-jobs.json.

Роли и модели — config/image-models.json (замена модели = правка конфига,
пайплайн не переписывается). Журнал — scripts/image-pipeline/logs/usage-log.jsonl.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.path.join(BASE, "config", "image-models.json")
JOBS = os.path.join(BASE, "content", "manifests", "image-jobs.json")
LOGDIR = os.path.join(BASE, "scripts", "image-pipeline", "logs")


def load_env_key(name):
    # без сторонних зависимостей: читаем .env вручную
    env_path = os.path.join(BASE, ".env")
    if os.environ.get(name):
        return os.environ[name]
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def log(entry):
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "usage-log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="реальный запуск (без флага — dry-run)")
    ap.add_argument("--job", help="запустить только указанный job_id")
    args = ap.parse_args()

    cfg = json.load(open(CONFIG, encoding="utf-8"))
    jobs = json.load(open(JOBS, encoding="utf-8"))["jobs"]
    if args.job:
        jobs = [j for j in jobs if j["job_id"] == args.job]

    key = load_env_key(cfg["api_key_env"])
    dry = not args.execute or cfg["safety"].get("dry_run_default", True) and not args.execute

    if args.execute and not key:
        print("ОСТАНОВ: нет OPENROUTER_API_KEY в .env — реальный запуск невозможен.")
        sys.exit(1)

    for j in jobs:
        role = cfg["roles"][j["role"]]
        plan = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": j["job_id"], "role": j["role"], "model": role["model"],
            "input_files": [j.get("input")], "output_file": j.get("output"),
            "params": role["defaults"], "cost_usd": None,
            "status": "dry_run" if (dry or j.get("status") != "approved_to_run") else "would_execute",
        }
        print(f"[{plan['status']}] {j['job_id']} → {role['model']}: {j['task']} ({j.get('input')} → {j.get('output')})")
        log(plan)

    if not args.execute:
        print("\nDRY-RUN завершён. Ничего не отправлено. Для реального запуска: "
              "--execute + ключ в .env + status=approved_to_run у job'а.")
    else:
        print("\nВНИМАНИЕ: интеграция вызова API намеренно не реализована на этом этапе "
              "(решение проекта: генерацию не запускать). Реализуется отдельным шагом "
              "после утверждения тестовых заданий владельцем.")


if __name__ == "__main__":
    main()
