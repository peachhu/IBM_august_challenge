"""
llm_advisor.py — IBM Granite / watsonx.ai LLM Integration
===========================================================
Generates human-readable mission readiness explanations using IBM Granite
via watsonx.ai.  Falls back to a rule-based template when credentials are
not configured (so the app always works, even without an API key).

Usage:
    from llm_advisor import generate_advisory
    text = generate_advisory(report)   # MissionRiskReport → str
"""

from __future__ import annotations

import json
from typing import Optional

try:
    from config import WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL
    from core.risk_engine import MissionRiskReport
except ImportError:
    from mission_readiness_advisor.config import WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL
    from mission_readiness_advisor.core.risk_engine import MissionRiskReport

# ── Optional watsonx SDK import (graceful fallback) ──────────────────────────
try:
    from ibm_watsonx_ai import APIClient, Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    _WATSONX_AVAILABLE = True
except ImportError:
    _WATSONX_AVAILABLE = False


# ─── Prompt Builder ───────────────────────────────────────────────────────────

def _build_prompt(report: MissionRiskReport) -> str:
    """
    Construct a concise, factual prompt for Granite to generate a mission advisory.
    Uses a structured JSON context block so the model has all the data it needs.
    """
    dims = {d.name: {"score": f"{d.score:.0%}", "level": d.level, "factors": d.factors}
            for d in report.dimensions}

    context = {
        "mission_date": report.mission_date,
        "launch_site": report.site_name,
        "recommendation": report.recommendation,
        "delay_probability": f"{report.delay_probability_pct}%",
        "confidence": report.confidence,
        "weather": dims.get("Weather", {}),
        "space_weather": dims.get("Space Weather", {}),
        "historical": dims.get("Historical", {}),
        "key_risk_factors": report.key_factors,
    }

    prompt = f"""You are an expert Mission Launch Advisor AI for a space agency.
Analyze the following mission readiness assessment and write a clear, concise advisory briefing.

MISSION ASSESSMENT DATA:
{json.dumps(context, indent=2)}

INSTRUCTIONS:
1. Start with a one-sentence RECOMMENDATION headline (GO / CAUTION / NO-GO and why).
2. Explain the top 1-3 risk factors in plain language that a mission director would understand.
3. If recommendation is CAUTION or NO-GO, suggest what conditions need to change for GO.
4. Keep total response under 200 words. Be direct and professional.
5. Do NOT repeat all the numbers — synthesize them into actionable insight.

ADVISORY:"""
    return prompt


# ─── watsonx.ai Call ──────────────────────────────────────────────────────────

def _call_watsonx(prompt: str,
                  model_id: str = "ibm/granite-13b-instruct-v2",
                  max_new_tokens: int = 300) -> Optional[str]:
    """Call watsonx.ai Granite model. Returns generated text or None on failure."""
    if not _WATSONX_AVAILABLE:
        return None
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return None
    try:
        credentials = Credentials(url=WATSONX_URL, api_key=WATSONX_API_KEY)
        client = APIClient(credentials)
        model = ModelInference(
            model_id=model_id,
            api_client=client,
            project_id=WATSONX_PROJECT_ID,
            params={
                GenParams.MAX_NEW_TOKENS: max_new_tokens,
                GenParams.MIN_NEW_TOKENS: 40,
                GenParams.TEMPERATURE: 0.3,
                GenParams.TOP_P: 0.85,
                GenParams.REPETITION_PENALTY: 1.1,
                GenParams.STOP_SEQUENCES: ["MISSION ASSESSMENT DATA:", "INSTRUCTIONS:"],
            },
        )
        result = model.generate_text(prompt=prompt)
        return result.strip() if result else None
    except Exception as exc:
        print(f"[LLM] watsonx call failed: {exc}")
        return None


# ─── Rule-Based Fallback ──────────────────────────────────────────────────────

def _template_advisory(report: MissionRiskReport) -> str:
    """
    Generate a structured text advisory without an LLM.
    Used when watsonx credentials are unavailable.
    """
    rec = report.recommendation
    prob = report.delay_probability_pct
    icon = report.recommendation_emoji

    lines = [
        f"## {icon} Mission Readiness Advisory",
        f"**{rec}** — Estimated delay risk: **{prob}%**  "
        f"(Confidence: {report.confidence})",
        "",
    ]

    # Weather
    wx_dim = report.dimension_by_name("Weather")
    if wx_dim:
        lines.append(f"### 🌦️ Surface Weather — {wx_dim.level}")
        if wx_dim.factors:
            for f in wx_dim.factors:
                lines.append(f"- {f}")
        else:
            lines.append("- All Launch Commit Criteria satisfied.")
        lines.append("")

    # Space Weather
    sw_dim = report.dimension_by_name("Space Weather")
    if sw_dim and report.space_weather:
        sw = report.space_weather
        lines.append(f"### ☀️ Space Weather — {sw_dim.level}")
        lines.append(f"- Geomagnetic: {sw.geomag_level} (Kp={sw.kp_max:.1f})")
        lines.append(f"- Max solar flare: {sw.flare_class_max}")
        if sw.cme_count:
            lines.append(f"- {sw.cme_count} CME event(s) in window"
                         + (" — geoeffective" if sw.cme_geoeffective else ""))
        if sw.hss_active:
            lines.append("- High-speed solar wind stream active")
        if not sw.risk_factors:
            lines.append("- Space weather conditions nominal.")
        lines.append("")

    # Historical
    hist_dim = report.dimension_by_name("Historical")
    if hist_dim:
        hist = report.historical or {}
        rate = hist.get("scrub_rate", 0)
        lines.append(f"### 📚 Historical Context — {hist_dim.level}")
        lines.append(f"- Historical scrub rate at this site: {rate:.0%}")
        if hist.get("recent_scrubs"):
            names = [s["name"] for s in hist["recent_scrubs"][:2]]
            lines.append(f"- Recent holds: {', '.join(names)}")
        lines.append("")

    # Recommendation
    lines.append("### 📋 Recommendation")
    if rec == "GO":
        lines.append("All systems within acceptable parameters. Proceed with launch sequence.")
    elif rec == "CAUTION":
        caution_items = report.key_factors[:3]
        lines.append("Monitor the following before committing to launch:")
        for item in caution_items:
            lines.append(f"- {item}")
    else:
        scrub_items = report.key_factors[:3]
        lines.append("Launch not recommended. Violations detected:")
        for item in scrub_items:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Reassess when conditions improve.")

    lines.append(f"\n*Generated at {report.generated_at} UTC — "
                 f"Data: {'live API + ' if report.confidence != 'LOW' else ''}historical datasets*")

    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_advisory(
    report: MissionRiskReport,
    use_llm: bool = True,
    model_id: str = "ibm/granite-13b-instruct-v2",
) -> str:
    """
    Generate a human-readable advisory for the mission risk report.

    Tries watsonx.ai first (if credentials configured + use_llm=True).
    Falls back to rule-based template automatically.

    Parameters
    ----------
    report   : MissionRiskReport from risk_engine.evaluate_mission_readiness()
    use_llm  : Set False to always use the template (e.g. for testing)
    model_id : Granite model ID (default: granite-13b-instruct-v2)

    Returns
    -------
    Markdown-formatted advisory string
    """
    if use_llm:
        prompt = _build_prompt(report)
        llm_text = _call_watsonx(prompt, model_id=model_id)
        if llm_text:
            return (
                f"## {report.recommendation_emoji} Mission Readiness Advisory "
                f"*(IBM Granite)*\n\n"
                f"**{report.recommendation}** — Delay Risk: **{report.delay_probability_pct}%**\n\n"
                + llm_text
                + f"\n\n---\n*Generated at {report.generated_at} UTC*"
            )

    return _template_advisory(report)
