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

    # FIXED (root cause of 0.0% scrub rate bug):
    # `holdreason` is populated by LL2 when a launch attempt experienced a
    # hold/scrub during that launch day, even if it eventually succeeded.
    # This is the correct signal for "was this attempt delayed/scrubbed".
    #
    # The previous version checked status.abbrev in ("TBD","HOLD","TBC"),
    # but those abbreviations only ever appear on *upcoming* / unresolved
    # launches. This function processes the `launch/previous` endpoint,
    # where every launch is already finalized as Success or Failure — so
    # that condition could never match, guaranteeing scrub_rate = 0.0%
    # for every site, every time, regardless of real history.
    hold_reason = (raw.get("holdreason") or "").strip()

    return {
        "id": raw.get("id"),
        "name": raw.get("name", ""),
        "net": raw.get("net", ""),             # No-Earlier-Than date
        "status_abbrev": status.get("abbrev", ""),  # Success, Failure, Partial Failure, ...
        "status_name": status.get("name", ""),
        "hold": bool(hold_reason),              # FIXED: based on holdreason, not status_abbrev
        "hold_reason": hold_reason,
        "success": status.get("abbrev", "").lower() == "success",
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

    # NOTE ON DATA QUALITY: Launch Library 2's `holdreason` field exists but
    # is sparsely populated on the free tier — it's typically only filled in
    # for high-profile / heavily-reported missions, not routine launches.
    # A scrub_rate of exactly 0.0% across a real sample almost certainly
    # means "no holds were *recorded*", not "no holds occurred". Showing a
    # bare 0% would overstate confidence, so we apply a conservative floor
    # and flag it explicitly rather than presenting it as a clean measurement.
    data_quality_note = ""
    if len(scrubs) == 0 and total >= 10:
        FLOOR = 0.08  # conservative industry-baseline floor, not a measurement
        scrub_rate = FLOOR
        data_quality_note = (
            f"No hold/scrub records found in {total} sampled launches — "
            f"Launch Library 2's free tier under-reports holds for routine "
            f"missions, so a {FLOOR:.0%} conservative baseline is applied "
            f"instead of an unverified 0%."
        )

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
        {"name": s["name"], "date": s["net"][:10], "status": s["status_name"],
         "reason": s.get("hold_reason", "")}
        for s in scrubs[:5]
    ]

    notes = (
        f"Analysed {total} launches from '{pad_name}'. "
        f"Scrub/hold rate: {scrub_rate:.1%}. "
        + (data_quality_note + " " if data_quality_note else "")
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
        # FIXED: mark as lower-confidence source when we had to apply the
        # floor, so risk_engine's confidence scoring reflects the sparse data
        "data_source": "launch_library_2_sparse" if data_quality_note else "launch_library_2",
    }