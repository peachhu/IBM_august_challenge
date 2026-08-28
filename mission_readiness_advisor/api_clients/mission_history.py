"""
mission_history.py — Launch Library 2 API Client
==================================================
Fetches historical launch data from https://ll.thespacedevs.com/2.2.0/
to understand past scrub/delay patterns at a given launch site.

Free tier: 15 requests/hour (no key needed).
Rate-limited, so results are cached per session.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Optional

import requests

_LL2_BASE = "https://ll.thespacedevs.com/2.2.0"
_TIMEOUT = 15
_HEADERS = {"User-Agent": "MissionReadinessAdvisor/1.0 (IBM August Challenge)"}


# ─── Data Structures ─────────────────────────────────────────────────────────

def _parse_launch(raw: dict) -> dict:
    """Flatten a Launch Library 2 launch object into a slim dict."""
    pad = (raw.get("pad") or {})
    location = (pad.get("location") or {})
    status = (raw.get("status") or {})
    return {
        "id": raw.get("id"),
        "name": raw.get("name", ""),
        "net": raw.get("net", ""),             # No-Earlier-Than date
        "status_abbrev": status.get("abbrev", ""),  # TBD, GO, SUCCESS, FAILURE, HOLD
        "status_name": status.get("name", ""),
        "hold": status.get("abbrev") in ("TBD", "HOLD", "TBC"),
        "success": status.get("abbrev") == "SUCCESS",
        "pad_name": pad.get("name", ""),
        "location_name": location.get("name", ""),
        "rocket_name": ((raw.get("rocket") or {}).get("configuration") or {}).get("name", ""),
        "mission_type": ((raw.get("mission") or {}) or {}).get("type", ""),
        "mission_desc": ((raw.get("mission") or {}) or {}).get("description", "")[:200],
        "url": raw.get("url", ""),
    }


# ─── API Calls ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _fetch_launches_cached(pad_name_fragment: str,
                            limit: int = 20,
                            mode: str = "previous") -> list[dict]:
    """
    Cached fetch of launches for a pad.  mode = 'previous' | 'upcoming'.
    lru_cache uses the arguments as the cache key.
    """
    try:
        endpoint = "launch/previous" if mode == "previous" else "launch/upcoming"
        resp = requests.get(
            f"{_LL2_BASE}/{endpoint}/",
            params={
                "search": pad_name_fragment,
                "limit": limit,
                "ordering": "-net",
                "mode": "detailed",
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("results", [])
        print(f"[LL2] HTTP {resp.status_code} for pad={pad_name_fragment}")
        return []
    except Exception as exc:
        print(f"[LL2] Request failed: {exc}")
        return []


def get_recent_launches(pad_name: str, limit: int = 20) -> list[dict]:
    """Return last `limit` launches from a pad (parsed)."""
    raw = _fetch_launches_cached(pad_name, limit, mode="previous")
    return [_parse_launch(r) for r in raw]


def get_upcoming_launches(pad_name: str, limit: int = 10) -> list[dict]:
    """Return next `limit` scheduled launches from a pad (parsed)."""
    raw = _fetch_launches_cached(pad_name, limit, mode="upcoming")
    return [_parse_launch(r) for r in raw]


# ─── Historical Risk Analysis ─────────────────────────────────────────────────

def historical_scrub_risk(
    pad_name: str,
    target_month: Optional[int] = None,
    limit: int = 40,
) -> dict:
    """
    Analyse historical launch attempts from a pad and return:
      - scrub_rate        : fraction of attempts that were held/scrubbed
      - seasonal_modifier : extra risk for this month based on history
      - scrub_count / total_count
      - recent_scrubs     : list of recent scrubbed launches (name + date)
      - notes             : human-readable insight string
    """
    launches = get_recent_launches(pad_name, limit)

    if not launches:
        return {
            "scrub_rate": 0.10,         # default 10% if no data
            "seasonal_modifier": 0.0,
            "scrub_count": 0,
            "total_count": 0,
            "recent_scrubs": [],
            "notes": "No historical data available from Launch Library 2 — using 10% default",
            "data_source": "default",
        }

    scrubs = [l for l in launches if l["hold"]]
    successes = [l for l in launches if l["success"]]
    total = len(launches)
    scrub_rate = len(scrubs) / total if total > 0 else 0.10

    # Seasonal: check if target month has more scrubs historically
    seasonal_modifier = 0.0
    if target_month:
        month_launches = [
            l for l in launches
            if l.get("net") and str(l["net"])[5:7].lstrip("0") == str(target_month)
        ]
        month_scrubs = [l for l in month_launches if l["hold"]]
        if len(month_launches) >= 3:
            month_rate = len(month_scrubs) / len(month_launches)
            seasonal_modifier = round(month_rate - scrub_rate, 3)

    recent_scrubs = [
        {"name": s["name"], "date": s["net"][:10], "status": s["status_name"]}
        for s in scrubs[:5]
    ]

    notes = (
        f"Analysed {total} launches from '{pad_name}'. "
        f"Scrub/hold rate: {scrub_rate:.1%}. "
        + (f"This month historically {seasonal_modifier:+.1%} vs average. " if abs(seasonal_modifier) > 0.02 else "")
        + (f"Recent holds: {', '.join(s['name'] for s in recent_scrubs[:3])}" if recent_scrubs else "No recent holds in sample.")
    )

    return {
        "scrub_rate": round(scrub_rate, 3),
        "seasonal_modifier": seasonal_modifier,
        "scrub_count": len(scrubs),
        "total_count": total,
        "recent_scrubs": recent_scrubs,
        "notes": notes,
        "data_source": "launch_library_2",
    }
