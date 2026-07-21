#!/usr/bin/env python3
"""Remove the white background from the two approved partner logos via CutItOut."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
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


SOURCE_ROOT = PROJECT_ROOT / "assets" / "branding" / "source"
OUTPUT_ROOT = PROJECT_ROOT / "assets" / "branding" / "processed"
JOBS = (
    (
        "branding-dialog",
        "dialog-pokoleniy-full-white.png",
        "dialog-pokoleniy-full-transparent.png",
    ),
    (
        "branding-center",
        "center-support-full-white.png",
        "center-support-full-transparent.png",
    ),
)


def main() -> int:
    tool_dir = DEFAULT_TOOL_DIR.resolve()
    if not (tool_dir / "package.json").is_file() or not (tool_dir / "node_modules").is_dir():
        raise FileNotFoundError(f"CutItOut is not installed at {tool_dir}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for job_id, source_name, output_name in JOBS:
        source = (SOURCE_ROOT / source_name).resolve()
        output = (OUTPUT_ROOT / output_name).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        jobs.append(
            {
                "hero_id": job_id,
                "source": str(source),
                "output": str(output),
            }
        )

    url = "http://127.0.0.1:4177"
    server = start_server(tool_dir, 4177)
    batch_file: Path | None = None
    try:
        wait_for_server(url, server)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="branding-cutitout-",
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
                "300000",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=720,
        )
        result = parse_runner_result(completed.stdout)
        completed_by_output = {
            str(Path(item["output"]).resolve()): item
            for item in result.get("completed", [])
        }
        validated = []
        for job in jobs:
            output = Path(job["output"])
            if str(output.resolve()) not in completed_by_output:
                continue
            validated.append({**job, **validate_png(output, Path(job["source"]))})
        report = {
            "tool": "CutItOut via Playwright",
            "completed": validated,
            "failed": result.get("failed", []),
            "status_note": "Logo masks require visual review before print use.",
        }
        report_path = OUTPUT_ROOT / "cutout-run.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if completed.returncode != 0 or len(validated) != len(jobs):
            raise RuntimeError(completed.stderr or "CutItOut did not complete every branding job")
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
