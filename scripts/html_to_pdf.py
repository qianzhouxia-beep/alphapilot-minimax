# -*- coding: utf-8 -*-
"""Export a local HTML report to PDF via Chromium (Playwright).

Usage:
  python scripts/html_to_pdf.py output/foo_report.html
  python scripts/html_to_pdf.py output/foo_report.html -o output/foo_report.pdf

Charts (Chart.js) need a short settle wait after load.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def html_to_pdf(html_path: Path, pdf_path: Path, wait_ms: int = 1200) -> Path:
    html_path = html_path.resolve()
    pdf_path = pdf_path.resolve()
    if not html_path.is_file():
        raise FileNotFoundError(html_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    uri = html_path.as_uri()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SystemExit(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from e

    with sync_playwright() as p:
        # Prefer system Chrome/Edge so we do not require `playwright install`.
        browser = None
        last_err: Exception | None = None
        for channel in ("chrome", "msedge", None):
            try:
                if channel:
                    browser = p.chromium.launch(channel=channel)
                else:
                    browser = p.chromium.launch()
                break
            except Exception as e:  # noqa: BLE001 — try next channel
                last_err = e
                browser = None
        if browser is None:
            raise SystemExit(
                f"failed to launch browser ({last_err}). "
                "Install Chrome/Edge, or run: playwright install chromium"
            )

        page = browser.new_page()
        page.goto(uri, wait_until="networkidle")
        page.wait_for_timeout(wait_ms)
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
        )
        browser.close()
    return pdf_path


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML report -> PDF")
    ap.add_argument("html", type=Path, help="Path to .html report")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output .pdf path")
    ap.add_argument("--wait-ms", type=int, default=1200, help="Settle wait after load")
    args = ap.parse_args()
    out = args.output or args.html.with_suffix(".pdf")
    path = html_to_pdf(args.html, out, wait_ms=args.wait_ms)
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
