#!/usr/bin/env python3
"""Safely run the local CutItOut UI for confirmed flagship images.

The script is a thin project wrapper. It does not alter the CutItOut checkout and
does not update family manifests. A run is a dry run unless ``--apply`` is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_TOOL_DIR = WORKSPACE_ROOT / "tools" / "cut-it-out"
OUTPUT_ROOT = PROJECT_ROOT / "assets" / "processed-flagships"
RUNNER = PROJECT_ROOT / "scripts" / "cutitout_playwright_runner.mjs"
ALLOWED_SOURCE_ROOTS = (
    PROJECT_ROOT / "assets" / "production-ready" / "flagship",
    PROJECT_ROOT / "assets" / "families",
)
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
HERO_PATTERN = re.compile(r"hero-\d{3}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove backgrounds through the installed local CutItOut UI."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--source", type=Path, help="One confirmed flagship image")
    selection.add_argument("--queue", type=Path, help="JSON queue with flagship jobs")
    parser.add_argument("--hero-id", help="Required when it cannot be derived from --source")
    parser.add_argument(
        "--only-hero",
        action="append",
        default=[],
        help="For --queue, include only this hero_id; may be repeated",
    )
    parser.add_argument("--output", type=Path, help="Optional output for a single source")
    parser.add_argument("--limit", type=int, default=1, help="Maximum jobs (default: 1)")
    parser.add_argument("--tool-dir", type=Path, default=DEFAULT_TOOL_DIR)
    parser.add_argument("--port", type=int, default=4175)
    parser.add_argument("--timeout", type=int, default=300, help="Per-image timeout in seconds")
    parser.add_argument("--apply", action="store_true", help="Run CutItOut; otherwise dry run")
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    return parser.parse_args()


def resolve_project_path(value: Path) -> Path:
    path = value if value.is_absolute() else PROJECT_ROOT / value
    return path.resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_hero_id(hero_id: str) -> str:
    if not HERO_PATTERN.fullmatch(hero_id):
        raise ValueError(f"Invalid hero_id: {hero_id!r}")
    return hero_id


def derive_hero_id(path: Path, explicit: str | None) -> str:
    if explicit:
        return validate_hero_id(explicit)
    match = HERO_PATTERN.search(path.as_posix())
    if not match:
        raise ValueError(f"Cannot derive hero_id from {path}; pass --hero-id")
    return validate_hero_id(match.group(0))


def validate_source(path: Path, hero_id: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {path.suffix}")
    if not any(is_relative_to(path, root) for root in ALLOWED_SOURCE_ROOTS):
        raise ValueError(f"Source is outside approved flagship roots: {path}")
    if "flagship" not in {part.lower() for part in path.parts}:
        raise ValueError(f"Source is not in a flagship directory: {path}")
    if hero_id not in path.parts:
        raise ValueError(f"Source path does not belong to {hero_id}: {path}")


def default_output(source: Path, hero_id: str) -> Path:
    stem = re.sub(r"_upscaled(?:_\d+x)?$", "", source.stem, flags=re.IGNORECASE)
    return OUTPUT_ROOT / hero_id / f"{stem}_nobg.png"


def validate_output(path: Path, hero_id: str) -> None:
    expected_root = OUTPUT_ROOT / hero_id
    if not is_relative_to(path, expected_root):
        raise ValueError(f"Output must stay under {expected_root}: {path}")
    if path.suffix.lower() != ".png":
        raise ValueError("CutItOut output must be a PNG")


def queue_entries(queue_path: Path) -> list[dict[str, Any]]:
    data = json.loads(queue_path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("queue") or data.get("jobs") or data.get("entries") or []
    else:
        raise ValueError("Queue JSON must contain an array or queue/jobs/entries array")
    if not isinstance(entries, list):
        raise ValueError("Queue entries are not an array")
    return [entry for entry in entries if isinstance(entry, dict)]


def source_from_entry(entry: dict[str, Any]) -> Path | None:
    for key in (
        "processing_source",
        "print_file",
        "production_file",
        "source_file",
        "flagship_asset",
    ):
        value = entry.get(key)
        if value:
            return resolve_project_path(Path(value))
    return None


def build_jobs(args: argparse.Namespace) -> list[dict[str, Path | str]]:
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if args.source:
        source = resolve_project_path(args.source)
        hero_id = derive_hero_id(source, args.hero_id)
        output = resolve_project_path(args.output) if args.output else default_output(source, hero_id)
        validate_source(source, hero_id)
        validate_output(output, hero_id)
        return [{"hero_id": hero_id, "source": source, "output": output}]

    queue_path = resolve_project_path(args.queue)
    selected_heroes = {validate_hero_id(value) for value in args.only_hero}
    jobs: list[dict[str, Path | str]] = []
    for entry in queue_entries(queue_path):
        if entry.get("needs_cutout") is False or entry.get("status") in {
            "missing_asset",
            "cutout-not-required",
        }:
            continue
        if (
            entry.get("status") == "cutout_generated_needs_review"
            and not args.force
        ):
            continue
        source = source_from_entry(entry)
        hero_id = entry.get("hero_id")
        if not source or not hero_id:
            continue
        hero_id = validate_hero_id(str(hero_id))
        if selected_heroes and hero_id not in selected_heroes:
            continue
        output_value = entry.get("output_file") or entry.get("expected_output")
        output = resolve_project_path(Path(output_value)) if output_value else default_output(source, hero_id)
        validate_source(source, hero_id)
        validate_output(output, hero_id)
        jobs.append({"hero_id": hero_id, "source": source, "output": output})
        if len(jobs) >= args.limit:
            break
    return jobs


def wait_for_server(url: str, process: subprocess.Popen[str], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("CutItOut dev server stopped before it became ready")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.4)
    raise TimeoutError(f"CutItOut dev server did not become ready at {url}")


def start_server(tool_dir: Path, port: int) -> subprocess.Popen[str]:
    vite = tool_dir / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.is_file():
        raise FileNotFoundError(f"Vite entry point is missing: {vite}")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        ["node", str(vite), "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=tool_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )


def validate_png(output: Path, source: Path) -> dict[str, Any]:
    with Image.open(source) as original, Image.open(output) as result:
        if result.format != "PNG":
            raise ValueError(f"Unexpected result format: {result.format}")
        if result.size != original.size:
            raise ValueError(f"Dimensions changed: {original.size} -> {result.size}")
        if "A" not in result.getbands():
            raise ValueError("Result PNG does not have an alpha channel")
        alpha = result.getchannel("A")
        extrema = alpha.getextrema()
        if extrema[0] >= 255:
            raise ValueError("Result alpha channel is fully opaque")
        transparent_pixels = sum(alpha.histogram()[:250])
        return {
            "width": result.width,
            "height": result.height,
            "alpha_extrema": list(extrema),
            "transparent_pixels": transparent_pixels,
            "status": "needs_manual_mask_review",
        }


def parse_runner_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "completed" in value and "failed" in value:
            return value
    raise ValueError(f"CutItOut runner did not return a JSON result:\n{stdout}")


def main() -> int:
    args = parse_args()
    jobs = build_jobs(args)
    if not jobs:
        print("No eligible confirmed flagship jobs found.", file=sys.stderr)
        return 2

    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "jobs": jobs}, ensure_ascii=False, default=str, indent=2))
    if not args.apply:
        return 0

    tool_dir = resolve_project_path(args.tool_dir) if not args.tool_dir.is_absolute() else args.tool_dir.resolve()
    if not (tool_dir / "package.json").is_file() or not (tool_dir / "node_modules").is_dir():
        raise FileNotFoundError(f"CutItOut is not installed at {tool_dir}")
    if not RUNNER.is_file():
        raise FileNotFoundError(RUNNER)

    for job in jobs:
        output = Path(job["output"])
        if output.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {output}; use --force")

    url = f"http://127.0.0.1:{args.port}"
    server = start_server(tool_dir, args.port)
    try:
        wait_for_server(url, server)
        for job in jobs:
            Path(job["output"]).parent.mkdir(parents=True, exist_ok=True)

        batch_file: Path | None = None
        started_at = time.monotonic()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                prefix="cutitout-batch-",
                encoding="utf-8",
                delete=False,
            ) as handle:
                json.dump(jobs, handle, ensure_ascii=False, default=str)
                batch_file = Path(handle.name)

            command = [
                "node",
                str(RUNNER),
                "--url",
                url,
                "--jobs",
                str(batch_file),
                "--timeout",
                str(args.timeout * 1000),
            ]
            completed = subprocess.run(
                command,
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
                if isinstance(item, dict) and item.get("output")
            }
            results = []
            for job in jobs:
                source = Path(job["source"])
                output = Path(job["output"])
                runner_job = completed_by_output.get(str(output.resolve()))
                if runner_job is None:
                    continue
                validation = validate_png(output, source)
                results.append({**job, **runner_job, **validation})

            summary = {
                "completed": results,
                "failed": runner_result.get("failed", []),
                "batch_duration_seconds": round(time.monotonic() - started_at, 3),
                "vite_processes": 1,
                "chromium_processes": 1,
                "pages": 1,
            }
            print(json.dumps(summary, ensure_ascii=False, default=str, indent=2))
            if completed.returncode != 0 or len(results) != len(jobs):
                raise RuntimeError(
                    "CutItOut batch did not complete every job"
                    f"\nSTDERR:\n{completed.stderr}"
                )
        finally:
            if batch_file and batch_file.exists():
                batch_file.unlink()
    finally:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(server.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
