#!/usr/bin/env python3
"""Fetch Taskmarket public stats for both chains and write site/data.json.

Runs server-side (GitHub Actions, hourly). The Taskmarket API refuses
cross-origin browser calls, so this is the only way the page can be live.

Every number in the output is either copied verbatim from an API response or
derived by arithmetic on those responses; nothing is estimated or invented.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.taskmarket.dev"
CHAINS = {4217: "Tempo", 8453: "Base"}
TIMEOUT = 45
OUT = pathlib.Path(__file__).resolve().parent.parent / "site" / "data.json"

# frozen once per process so every row is judged against the same instant
NOW_ISO = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

ENDPOINTS = {
    "stats": "/api/market/stats?chainId={cid}",
    "breakdowns": "/api/stats/breakdowns?chainId={cid}",
    "series": "/api/stats/platform-time-series?chainId={cid}&range={rng}&bucket={bucket}",
    "heatmap": "/api/stats/activity-heatmap?chainId={cid}&range={rng}&dimension={dim}",
    "feed": "/api/stats/activity-feed?chainId={cid}&limit={limit}",
}


def get(path: str, attempts: int = 4):
    """GET JSON with backoff. The API rate-limits aggressively (HTTP 429) when a
    full snapshot is pulled: ~30 requests in a burst. Retrying with jittered
    sleeps is what makes an hourly run survive; dropping the chain is not."""
    url = BASE + path
    delay = 3.0
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0 (+taskmarket-visualizer)"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < attempts:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                time.sleep(min(wait, 30))
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise last  # type: ignore[misc]


def fetch_tasks(cid: int, limit: int = 100, max_pages: int = 12):
    """Walk the task list for one chain; returns (tasks, pages, truncated)."""
    out, cursor, pages = [], None, 0
    while pages < max_pages:
        path = f"/api/tasks?chainId={cid}&sort=newest&limit={limit}"
        if cursor:
            path += f"&cursor={cursor}"
        page = get(path)
        batch = page.get("tasks") or []
        out.extend(batch)
        pages += 1
        cursor = page.get("nextCursor")
        if not page.get("hasMore") or not cursor or not batch:
            return out, pages, False
    return out, pages, True


def iso_week(ts: str) -> str:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def summarise_tasks(tasks):
    posters_by_week: dict[str, set] = {}
    open_by_week: dict[str, int] = {}
    status_by_week: dict[str, dict[str, int]] = {}
    open_points = []
    for t in tasks:
        created = t.get("createdAt")
        if not created:
            continue
        wk = iso_week(created)
        posters_by_week.setdefault(wk, set()).add((t.get("requester") or "").lower())
        open_by_week[wk] = open_by_week.get(wk, 0) + (1 if t.get("status") == "open" else 0)
        bucket = status_by_week.setdefault(wk, {})
        st = t.get("status") or "unknown"
        bucket[st] = bucket.get(st, 0) + 1
        if t.get("status") == "open":
            try:
                reward = int(t.get("reward") or 0) / 1e6
            except (TypeError, ValueError):
                reward = 0.0
            expiry = t.get("expiryTime") or ""
            open_points.append({
                "id": t.get("referenceCode"),
                "reward": round(reward, 6),
                "subs": int(t.get("submissionCount") or 0),
                "mode": t.get("mode"),
                "created": created,
                "expiry": expiry,
                "stale": bool(expiry and expiry < NOW_ISO),
            })
    open_points.sort(key=lambda p: p["reward"], reverse=True)
    return {
        "tasks_seen": len(tasks),
        "distinct_posters_total": len({(t.get("requester") or "").lower() for t in tasks}),
        "posters_per_week": [{"week": k, "distinctPosters": len(v)} for k, v in sorted(posters_by_week.items())],
        "open_per_week": [{"week": k, "open": v} for k, v in sorted(open_by_week.items())],
        "status_by_week": [{"week": k, **v} for k, v in sorted(status_by_week.items())],
        "open_points": open_points[:400],
    }


def main() -> int:
    read_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    doc = {
        "read_at": read_at,
        "source_base": BASE,
        "partial": False,
        "endpoints_used": [
            "/api/market/stats?chainId={4217,8453}",
            "/api/stats/breakdowns?chainId={4217,8453}",
            "/api/stats/platform-time-series?chainId={4217,8453}&range=7d|30d|90d|all&bucket=day|week",
            "/api/stats/activity-heatmap?chainId={4217,8453}&range=7d|30d&dimension=mode|hourOfWeek",
            "/api/stats/activity-feed?chainId={4217,8453}&limit=40",
            "/api/tasks?chainId={4217,8453}&sort=newest&limit=100",
        ],
        "chains": {},
        "errors": [],
    }

    previous = {}
    if OUT.exists():
        try:
            prev_doc = json.loads(OUT.read_text())
            if isinstance(prev_doc.get("chains"), dict):
                previous = prev_doc["chains"]
        except (json.JSONDecodeError, OSError):
            previous = {}

    for cid, name in CHAINS.items():
        block = {"chainId": cid, "name": name}
        try:
            block["stats"] = get(ENDPOINTS["stats"].format(cid=cid))
            block["breakdowns"] = get(ENDPOINTS["breakdowns"].format(cid=cid))
            block["series"] = {
                rng: get(ENDPOINTS["series"].format(cid=cid, rng=rng, bucket="day" if rng in ("7d", "30d") else "week"))
                for rng in ("7d", "30d", "90d", "all")
            }
            block["heatmap_mode"] = get(ENDPOINTS["heatmap"].format(cid=cid, rng="30d", dim="mode"))
            block["heatmap_hour"] = get(ENDPOINTS["heatmap"].format(cid=cid, rng="30d", dim="hourOfWeek"))
            block["feed"] = get(ENDPOINTS["feed"].format(cid=cid, limit=40))
            tasks, pages, truncated = fetch_tasks(cid)
            block["tasks"] = summarise_tasks(tasks)
            block["tasks"]["pages_walked"] = pages
            block["tasks"]["truncated"] = truncated
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            # Carry the previous good block forward rather than publishing a hole.
            # A stale-but-labelled block beats a half-empty dashboard, and the
            # error is recorded so the next run (and the reader) can see it.
            prior = previous.get(str(cid)) or previous.get(cid)
            if prior and prior.get("stats"):
                block = dict(prior)
                block["stale"] = True
                block["stale_reason"] = f"{type(exc).__name__}: {exc}"
                doc["partial"] = True
                doc["errors"].append(f"chain {cid}: carried forward previous snapshot ({type(exc).__name__}: {exc})")
            else:
                doc["errors"].append(f"chain {cid}: {type(exc).__name__}: {exc}")
                block["failed"] = True
        doc["chains"][str(cid)] = block
        time.sleep(1.5)  # be a polite client; the API 429s on bursts

    if all(b.get("failed") for b in doc["chains"].values()):
        print("FATAL: every chain failed; refusing to write an empty data.json", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size} bytes) at {read_at}; errors={len(doc['errors'])}")
    for e in doc["errors"]:
        print("  ERR", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
