#!/usr/bin/env python3
"""Render site/share/og.png (1200x630) with headless Chrome from share.html.

Using Chrome rather than PIL keeps the card in the same brand fonts (Instrument
Serif / Inter Tight / Departure Mono) and the same CSS as the page, so the card
cannot drift from the site's design language.

Pipeline: inject the live figures into share.html -> screenshot at exactly
1200x630 -> assert non-blank and under the platform size cap.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CHROME = "/usr/bin/google-chrome"
W, H = 1200, 630


def fmt_usd(n: float) -> str:
    if n >= 1e6:
        return f"${n/1e6:.2f}M"
    if n >= 1e3:
        return f"${n/1e3:.1f}k"
    return f"${n:.2f}"


def figures() -> dict[str, str]:
    data = json.loads((SITE / "data.json").read_text())
    cs = data["chains"]
    stats = cs["4217"]["stats"]

    per_bucket: dict[str, float] = {}
    for c in cs.values():
        for row in c.get("series", {}).get("all", []):
            v = float(row.get("paidVolume") or 0) / 1e6
            per_bucket[row["bucket"]] = max(per_bucket.get(row["bucket"], 0.0), v)

    dead = total = 0
    for c in cs.values():
        for row in c["tasks"]["status_by_week"][-16:]:
            for k, v in row.items():
                if k == "week":
                    continue
                total += int(v)
                if k in ("cancelled", "expired"):
                    dead += int(v)

    series = cs["4217"].get("series", {}).get("30d", [])
    up = [float(r.get("rewardVolume") or 0) / 1e6 for r in series]
    paid = [float(r.get("paidVolume") or 0) / 1e6 for r in series]
    mx = max(up + paid + [1e-9])
    poly = lambda vals: " ".join(
        f"{i/max(1,len(vals)-1)*100:.2f},{100-(v/mx*100):.2f}" for i, v in enumerate(vals)
    )
    return {
        "OPEN": f"{stats['openTasks']}",
        "PAID": fmt_usd(sum(per_bucket.values())),
        "LEAK": f"{round(dead/max(1,total)*100)}%",
        "ASOF": data["read_at"].replace("T", " ")[:16],
        "UP": poly(up),
        "PAIDPOLY": poly(paid),
    }


def main() -> int:
    tpl = (ROOT / "share.html").read_text()
    vals = figures()
    html = tpl
    for k, v in vals.items():
        html = html.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[A-Z]+\}\}", html)
    if leftover:
        print("FAIL: unfilled template tokens", leftover, file=sys.stderr)
        return 1

    out = SITE / "share" / "og.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "share.html").write_text(html)
        # share.html references ./fonts/* and must live beside them to resolve
        (tmp / "fonts").symlink_to(SITE / "fonts", target_is_directory=True)
        subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={W},{H}",
            "--virtual-time-budget=4000", f"--user-data-dir={tmp/'ud'}",
            "--allow-file-access-from-files", f"--screenshot={out}",
            (tmp / "share.html").as_uri(),
        ], capture_output=True, text=True, timeout=120, check=False)

    if not out.exists():
        print("FAIL: no screenshot produced", file=sys.stderr)
        return 1
    size = out.stat().st_size
    if size < 15000:
        print(f"FAIL: share card looks blank ({size} bytes)", file=sys.stderr)
        return 1
    if size > 5 * 1024 * 1024:
        print(f"FAIL: share card too large ({size} bytes)", file=sys.stderr)
        return 1
    print(f"wrote {out} ({size} bytes, {W}x{H})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
