#!/usr/bin/env python3
"""Build a lightweight raster client preview from an existing spreads PDF.

The source PDF is never modified. Each selected page is rendered with Poppler,
encoded as JPEG, and placed on an exact 526 x 206 mm PDF page. ReportLab is
used when it is installed; the project-standard Pillow + pypdf fallback keeps
the command usable in the bundled Codex Python environment.

Examples (PowerShell):

    python scripts/build_client_preview_pdf.py `
      output/PRINT_V22_LAYOUT_CORRECTIONS_SPREADS.pdf `
      output/PRINT_V22_LAYOUT_CORRECTIONS_CLIENT.pdf

    # Quick two-page smoke test; --force permits replacing an earlier test.
    python scripts/build_client_preview_pdf.py input.pdf tmp/preview-test.pdf `
      --first-page 1 --last-page 2 --force
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject


MM_TO_PT = 72.0 / 25.4
PAGE_WIDTH_MM = 526.0
PAGE_HEIGHT_MM = 206.0
DEFAULT_DPI = 144
DEFAULT_JPEG_QUALITY = 84


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _quality(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a compact 526 x 206 mm client-preview PDF from a spreads "
            "PDF. Default rendering: 144 dpi, JPEG quality 84."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "PowerShell example:\n"
            "  python scripts/build_client_preview_pdf.py "
            "output/PRINT_V21_FULL_DRAFT_SPREADS.pdf "
            "tmp/PRINT_V21_CLIENT_TEST.pdf --first-page 1 --last-page 2\n\n"
            "For the full book, omit --first-page and --last-page. "
            "Use --force only when the output is intentionally replaceable."
        ),
    )
    parser.add_argument("input_pdf", type=Path, help="existing spreads PDF")
    parser.add_argument("output_pdf", type=Path, help="new client-preview PDF")
    parser.add_argument("--dpi", type=_positive_int, default=DEFAULT_DPI)
    parser.add_argument(
        "--quality",
        type=_quality,
        default=DEFAULT_JPEG_QUALITY,
        help="JPEG quality, 1-100 (default: 84)",
    )
    parser.add_argument(
        "--first-page",
        type=_positive_int,
        default=1,
        help="first 1-based source page to include (default: 1)",
    )
    parser.add_argument(
        "--last-page",
        type=_positive_int,
        help="last 1-based source page to include (default: final page)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace output_pdf if it already exists",
    )
    return parser.parse_args()


def _candidate_poppler_names(executable: str) -> tuple[str, ...]:
    if os.name == "nt":
        return (f"{executable}.exe", f"{executable}.cmd", executable)
    return (executable,)


def find_poppler_executable(executable: str) -> Path:
    """Find Poppler on PATH or in the bundled Codex runtime."""

    user_profile = Path.home()
    fixed_roots = (
        user_profile
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin",
        user_profile / ".cache/codex-runtimes",
    )
    for root in fixed_roots:
        if not root.exists():
            continue
        for name in _candidate_poppler_names(executable):
            direct = root / name
            if direct.is_file():
                return direct.resolve()
        matches = sorted(root.glob(f"**/{executable}.exe"))
        if matches:
            return matches[0].resolve()

    # PATH wrappers in the desktop runtime can outlive the runtime directory
    # they point at, so prefer the real bundled executable above when present.
    for name in _candidate_poppler_names(executable):
        discovered = shutil.which(name)
        if discovered:
            return Path(discovered).resolve()

    raise FileNotFoundError(
        f"Poppler executable '{executable}' was not found on PATH or in the "
        "bundled Codex runtime."
    )


def _human_size(byte_count: int) -> str:
    size = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{byte_count} B"


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)$", path.stem)
    if not match:
        raise ValueError(f"Unexpected Poppler output name: {path.name}")
    return int(match.group(1))


def _render_pages(
    pdftoppm: Path,
    input_pdf: Path,
    output_prefix: Path,
    *,
    dpi: int,
    quality: int,
    first_page: int,
    last_page: int,
) -> list[Path]:
    command = [
        str(pdftoppm),
        "-f",
        str(first_page),
        "-l",
        str(last_page),
        "-r",
        str(dpi),
        "-jpeg",
        "-jpegopt",
        f"quality={quality},progressive=y,optimize=y",
        str(input_pdf),
        str(output_prefix),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"pdftoppm failed ({completed.returncode}): {detail}")

    pages = sorted(output_prefix.parent.glob(f"{output_prefix.name}-*.jpg"), key=_page_number)
    expected = last_page - first_page + 1
    if len(pages) != expected:
        raise RuntimeError(f"Poppler rendered {len(pages)} pages; expected {expected}.")
    return pages


def _fit_box(image_width: int, image_height: int) -> tuple[float, float, float, float]:
    page_width = PAGE_WIDTH_MM * MM_TO_PT
    page_height = PAGE_HEIGHT_MM * MM_TO_PT
    scale = min(page_width / image_width, page_height / image_height)
    width = image_width * scale
    height = image_height * scale
    return ((page_width - width) / 2.0, (page_height - height) / 2.0, width, height)


def _build_with_reportlab(jpeg_pages: Iterable[Path], output_pdf: Path) -> str:
    from reportlab.lib.utils import ImageReader  # type: ignore[import-not-found]
    from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

    page_size = (PAGE_WIDTH_MM * MM_TO_PT, PAGE_HEIGHT_MM * MM_TO_PT)
    pdf = canvas.Canvas(str(output_pdf), pagesize=page_size, pageCompression=1)
    pdf.setTitle("Письма памяти — клиентское превью")
    pdf.setCreator("book-project build_client_preview_pdf.py")
    for image_path in jpeg_pages:
        with Image.open(image_path) as image:
            x, y, width, height = _fit_box(*image.size)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(0, 0, page_size[0], page_size[1], stroke=0, fill=1)
        pdf.drawImage(
            ImageReader(str(image_path)),
            x,
            y,
            width=width,
            height=height,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        pdf.showPage()
    pdf.save()
    return "reportlab"


def _normalised_image(image_path: Path, dpi: int) -> Image.Image:
    """Return an RGB image fitted into the exact target raster without distortion."""

    target_size = (
        round(PAGE_WIDTH_MM / 25.4 * dpi),
        round(PAGE_HEIGHT_MM / 25.4 * dpi),
    )
    with Image.open(image_path) as source:
        rgb = source.convert("RGB")
        try:
            return ImageOps.pad(
                rgb,
                target_size,
                method=Image.Resampling.LANCZOS,
                color="white",
                centering=(0.5, 0.5),
            )
        finally:
            rgb.close()


def _build_with_pillow(jpeg_pages: Iterable[Path], output_pdf: Path, dpi: int, quality: int) -> str:
    """Memory-bounded fallback: one Pillow PDF page at a time, merged by pypdf."""

    target_width = PAGE_WIDTH_MM * MM_TO_PT
    target_height = PAGE_HEIGHT_MM * MM_TO_PT
    writer = PdfWriter()

    for image_path in jpeg_pages:
        image = _normalised_image(image_path, dpi)
        one_page_pdf = io.BytesIO()
        try:
            image.save(
                one_page_pdf,
                format="PDF",
                resolution=float(dpi),
                quality=quality,
                optimize=True,
            )
        finally:
            image.close()
        one_page_pdf.seek(0)
        page = PdfReader(one_page_pdf).pages[0]

        current_width = float(page.mediabox.width)
        current_height = float(page.mediabox.height)
        page.add_transformation(
            Transformation().scale(target_width / current_width, target_height / current_height)
        )
        exact_box = RectangleObject((0, 0, target_width, target_height))
        page.mediabox = exact_box
        page.cropbox = RectangleObject((0, 0, target_width, target_height))
        writer.add_page(page)

    writer.add_metadata(
        {
            "/Title": "Письма памяти — клиентское превью",
            "/Creator": "book-project build_client_preview_pdf.py (Pillow fallback)",
        }
    )
    with output_pdf.open("wb") as handle:
        writer.write(handle)
    return "pillow+pypdf"


def _write_preview(
    jpeg_pages: list[Path], output_pdf: Path, *, dpi: int, quality: int
) -> str:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return _build_with_pillow(jpeg_pages, output_pdf, dpi, quality)
    return _build_with_reportlab(jpeg_pages, output_pdf)


def main() -> int:
    args = parse_args()
    input_pdf = args.input_pdf.expanduser().resolve()
    output_pdf = args.output_pdf.expanduser().resolve()

    if not input_pdf.is_file():
        raise FileNotFoundError(input_pdf)
    if input_pdf.suffix.lower() != ".pdf" or output_pdf.suffix.lower() != ".pdf":
        raise ValueError("Both input and output paths must end in .pdf")
    if input_pdf == output_pdf:
        raise ValueError("Input and output must be different files.")
    if output_pdf.exists() and not args.force:
        raise FileExistsError(f"Output already exists (use --force): {output_pdf}")

    input_reader = PdfReader(str(input_pdf))
    source_count = len(input_reader.pages)
    if source_count == 0:
        raise ValueError(f"Input PDF has no pages: {input_pdf}")
    last_page = args.last_page or source_count
    if args.first_page > source_count:
        raise ValueError(
            f"--first-page {args.first_page} exceeds source page count {source_count}."
        )
    if last_page > source_count:
        raise ValueError(f"--last-page {last_page} exceeds source page count {source_count}.")
    if last_page < args.first_page:
        raise ValueError("--last-page must be greater than or equal to --first-page.")

    pdftoppm = find_poppler_executable("pdftoppm")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    staged_output = output_pdf.with_name(
        f".{output_pdf.stem}.{uuid.uuid4().hex}.partial.pdf"
    )
    expected_count = last_page - args.first_page + 1
    try:
        with tempfile.TemporaryDirectory(prefix="letters-memory-client-preview-") as temp_name:
            temp_dir = Path(temp_name)
            jpeg_pages = _render_pages(
                pdftoppm,
                input_pdf,
                temp_dir / "page",
                dpi=args.dpi,
                quality=args.quality,
                first_page=args.first_page,
                last_page=last_page,
            )
            backend = _write_preview(
                jpeg_pages,
                staged_output,
                dpi=args.dpi,
                quality=args.quality,
            )

        output_reader = PdfReader(str(staged_output))
        if len(output_reader.pages) != expected_count:
            raise RuntimeError(
                f"Preview verification failed: {len(output_reader.pages)} pages, "
                f"expected {expected_count}."
            )
        first_box = output_reader.pages[0].mediabox
        actual_width_mm = float(first_box.width) / MM_TO_PT
        actual_height_mm = float(first_box.height) / MM_TO_PT
        if abs(actual_width_mm - PAGE_WIDTH_MM) > 0.01 or abs(actual_height_mm - PAGE_HEIGHT_MM) > 0.01:
            raise RuntimeError(
                "Preview verification failed: page size is "
                f"{actual_width_mm:.3f} x {actual_height_mm:.3f} mm."
            )
        # Replace only after a complete, verified build; an older preview stays
        # intact if Poppler or PDF writing fails midway.
        os.replace(staged_output, output_pdf)
    finally:
        staged_output.unlink(missing_ok=True)

    print(f"SOURCE: {input_pdf}")
    print(f"OUTPUT: {output_pdf}")
    print(f"PAGES: {expected_count} (source pages {args.first_page}-{last_page} of {source_count})")
    print(f"PAGE_SIZE: {actual_width_mm:.3f} x {actual_height_mm:.3f} mm")
    print(f"RENDER: {args.dpi} dpi, JPEG quality {args.quality}, backend {backend}")
    print(
        f"SIZE: {_human_size(input_pdf.stat().st_size)} -> "
        f"{_human_size(output_pdf.stat().st_size)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
