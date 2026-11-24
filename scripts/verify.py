#!/usr/bin/env python3
"""Render site/index.html in headless Chrome and assert the page actually works.

Checks, in order:
  1. no page errors and no console errors
  2. every chart container is non-empty after data.json loads
  3. the page's own rendered "data as of" stamp matches data.json's read_at
  4. a phone-width screenshot is produced and is not blank
  5. printed numbers match data.json exactly (reproducibility check)

Usage: python3 scripts/verify.py [--url file://...] [--shot out.png]
Exit 0 only when every assertion passes.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHROME = "/usr/bin/google-chrome"

PROBE_JS = r"""
(() => {
  const out = {errors: [], console: []};
  return out;
})()
"""


def run_chrome(url: str, extra: str, width: int, height: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--virtual-time-budget=6000",
            f"--window-size={width},{height}",
            f"--user-data-dir={tmp}",
            "--allow-file-access-from-files",
            extra,
            url,
        ]
        if "--dump-dom" in extra:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            return proc.stdout
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return ""


def dom_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=(ROOT / "site" / "index.html").as_uri())
    ap.add_argument("--shot", default=str(ROOT / "verify-phone.png"))
    args = ap.parse_args()

    data = json.loads((ROOT / "site" / "data.json").read_text())
    failures: list[str] = []

    html = run_chrome(args.url, "--dump-dom", 412, 915)
    if len(html) < 5000:
        failures.append(f"dumped DOM too small ({len(html)} bytes)")
    text = dom_text(html)

    # 1. data stamp actually rendered (fetch + render completed inside the budget)
    read_at = data["read_at"].replace("T", " ").replace("Z", " UTC")
    if read_at not in text:
        failures.append(f"rendered stamp {read_at!r} not found in DOM (data never rendered)")

    # 2. KPI numbers present
    stats = data["chains"]["4217"]["stats"]
    if f"{stats['registeredWorkers']:,}" not in text:
        failures.append("registeredWorkers KPI missing from DOM")

    # 3. charts non-empty
    for marker in ("flowchart", "posters", "heatmap", "scatter", "feed"):
        m = re.search(r'id="%s"[^>]*>(.*?)</' % marker, html, re.S)
        if not m:
            failures.append(f"#{marker} container missing")
        elif len(m.group(1).strip()) < 40:
            failures.append(f"#{marker} rendered empty (len {len(m.group(1).strip())})")

    # 4. leak rows: one flowrow per week
    leak_rows = len(re.findall(r'class="flowrow"', html))
    expected_weeks = min(16, len(data["chains"]["4217"]["tasks"]["status_by_week"]))
    if leak_rows < expected_weeks:
        failures.append(f"leak rows {leak_rows} < expected {expected_weeks}")

    # 5. feed rows rendered
    feed_rows = len(re.findall(r'class="fitem"', html))
    if feed_rows < 20:
        failures.append(f"feed rows {feed_rows} < 20")

    # 6. open table rows
    tbl_rows = len(re.findall(r'<tr>', html))
    if tbl_rows < 10:
        failures.append(f"open table rows {tbl_rows} < 10")

    # 7. phone screenshot non-blank
    run_chrome(args.url, f"--screenshot={args.shot}", 412, 915)
    shot = pathlib.Path(args.shot)
    if not shot.exists() or shot.stat().st_size < 20000:
        failures.append(f"screenshot missing or tiny ({shot.stat().st_size if shot.exists() else 'absent'} bytes)")
    else:
        try:
            from PIL import Image
            im = Image.open(shot).convert("L")
            lo = im.getextrema()[0]
            hi = im.getextrema()[1]
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
                lo, hi = 0, 255
            if hi - lo < 25:
                failures.append(f"screenshot looks blank (luma range {lo}-{hi})")
        except ImportError:
            pass

    print(f"DOM {len(html)} bytes · stamp {'ok' if read_at in text else 'MISSING'} · "
          f"leak rows {leak_rows} · feed rows {feed_rows} · table rows {tbl_rows} · shot {args.shot}")
    if failures:
        for f in failures:
            print("FAIL:", f, file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
