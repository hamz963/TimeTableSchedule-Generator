"""Optional Gemini hook: polish rule-based replies when configured.

Requires the optional `google-generativeai` package and GEMINI_API_KEY.
Without them this module is a pass-through (offline deterministic mode),
which is what the test suite exercises.
"""
from __future__ import annotations


def polish_reply(text: str) -> str:
    try:
        from app.config import get_settings

        key = (get_settings().gemini_api_key or "").strip()
        if not key:
            return text
        import google.generativeai as genai  # optional dependency

        genai.configure(api_key=key)
        resp = genai.GenerativeModel("gemini-1.5-flash").generate_content(
            "Rephrase briefly for a school administrator. "
            "Keep every fact, number, and view/format name exact. "
            "Plain text, no markdown headers:\n\n" + text
        )
        return (resp.text or "").strip() or text
    except Exception:
        return text
