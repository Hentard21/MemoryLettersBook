#!/usr/bin/env python3
"""Run the installed CutItOut UI for the five verified intro portraits.

This wrapper is separate from the family flagship queue: it accepts only the
five ProUpscale files listed below and writes only to the intro cutout folder.
Dry run is the default.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from batch_cutitout import (
    DEFAULT_TOOL_DIR,
    PROJECT_ROOT,
    RUNNER,
    parse_runner_result,
    start_server,
    validate_png,
    wait_for_server,
)


SOURCE_ROOT = PROJECT_ROOT / "assets" / "intro-people" / "for-gigapixel" / "ProUpscale"
OUTPUT_ROOT = PROJECT_ROOT / "assets" / "intro-people" / "cutouts-pro"
JOBS = (
    ("tengebaeva", "Адина.png"),
    ("belyaninov", "Белянинов (2).png"),
    ("makarychev", "Макарычев.png"),
    ("smirnova", "Смирнова.png"),
    ("shumilov", "Шумилов.png"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--person",
        choices=[person_id for person_id, _ in JOBS],
        help="Process only one named intro portrait.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Versioned source override; requires --person.",
    )
    parser.add_argument(
        "--output-name",
        help="Output PNG filename; requires --person.",
    )
    parser.add_argument(
        "--report-name",
        help="Report filename; defaults to cutout-run.json for the batch.",
    )
    parser.add_argument("--limit", type=int, default=len(JOBS))
    parser.add_argument("--port", type=int, default=4176)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--tool-dir", type=Path, default=DEFAULT_TOOL_DIR)
    return parser.parse_args()


def build_jobs(
    limit: int,
    force: bool,
    person: str | None = None,
    source_override: Path | None = None,
    output_name: str | None = None,
) -> list[dict[str, str]]:
    if not 1 <= limit <= len(JOBS):
        raise ValueError(f"--limit must be between 1 and {len(JOBS)}")
    if source_override and not person:
        raise ValueError("--source requires --person")
    if output_name and not person:
        raise ValueError("--output-name requires --person")
    selected = [job for job in JOBS if person is None or job[0] == person]
    jobs: list[dict[str, str]] = []
    for person_id, filename in selected:
        source = (source_override or SOURCE_ROOT / filename).resolve()
        output = (OUTPUT_ROOT / (output_name or f"{person_id}_nobg.png")).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if output.exists() and not force:
            continue
        jobs.append(
            {
                "hero_id": person_id,
                "person_id": person_id,
                "source": str(source),
                "output": str(output),
            }
        )
        if len(jobs) >= limit:
            break
    return jobs


def main() -> int:
    args = parse_args()
    jobs = build_jobs(
        args.limit,
        args.force,
        person=args.person,
        source_override=args.source,
        output_name=args.output_name,
    )
    print(
        json.dumps(
            {"mode": "apply" if args.apply else "dry-run", "jobs": jobs},
            ensure_ascii=False,
            indent=2,
        )
    )
    if not jobs:
        print("All requested intro cutouts already exist; use --force to rebuild.")
        return 0
    if not args.apply:
        return 0

    tool_dir = args.tool_dir.resolve()
    if not (tool_dir / "package.json").is_file() or not (tool_dir / "node_modules").is_dir():
        raise FileNotFoundError(f"CutItOut is not installed at {tool_dir}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    url = f"http://127.0.0.1:{args.port}"
    server = start_server(tool_dir, args.port)
    batch_file: Path | None = None
    started_at = time.monotonic()
    try:
        wait_for_server(url, server)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="intro-cutitout-",
            encoding="utf-8",
            delete=False,
        ) as handle:
            json.dump(jobs, handle, ensure_ascii=False)
            batch_file = Path(handle.name)

        completed = subprocess.run(
            [
                "node",
                str(RUNNER),
                "--url",
                url,
                "--jobs",
                str(batch_file),
                "--timeout",
                str(args.timeout * 1000),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=args.timeout * len(jobs) + 120,
        )
        runner_result = parse_runner_result(completed.stdout)
        completed_by_output = {
            str(Path(item["output"]).resolve()): item
            for item in runner_result.get("completed", [])
        }
        results = []
        for job in jobs:
            output = Path(job["output"])
            runner_item = completed_by_output.get(str(output.resolve()))
            if not runner_item:
                continue
            validation = validate_png(output, Path(job["source"]))
            results.append({**job, **runner_item, **validation})

        report = {
            "schema_version": 1,
            "tool": "CutItOut via Playwright",
            "source_profile": "intro ProUpscale portraits",
            "completed": results,
            "failed": runner_result.get("failed", []),
            "batch_duration_seconds": round(time.monotonic() - started_at, 3),
            "status_note": "Every mask requires visual review before final print approval.",
        }
        report_file = OUTPUT_ROOT / (
            args.report_name
            or (f"cutout-run-{args.person}.json" if args.person else "cutout-run.json")
        )
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if completed.returncode != 0 or len(results) != len(jobs):
            raise RuntimeError(f"CutItOut failed to complete every intro portrait: {completed.stderr}")
        print(f"WROTE: {report_file}")
    finally:
        if batch_file and batch_file.exists():
            batch_file.unlink()
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(server.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
