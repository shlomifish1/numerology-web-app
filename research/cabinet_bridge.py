"""
cabinet_bridge.py — sends a question to the Cabinet (real_agents_bot) and returns a summarized answer.
Requires: real_agents_bot running with HTTP bridge on port 8765.
"""
from __future__ import annotations

import logging

import httpx

CABINET_URL = "http://127.0.0.1:8765/cabinet/ask"
logger = logging.getLogger("cabinet_bridge")


def ask_cabinet(question: str, context_text: str = "", timeout: int = 120) -> str:
    """
    Send a question to the Cabinet and return a summarized answer.
    If the Cabinet is unavailable, returns an empty string (caller decides what to do).
    """
    full_question = f"{context_text}\n\nשאלה: {question}" if context_text else question
    try:
        resp = httpx.post(
            CABINET_URL,
            json={"question": full_question, "timeout": timeout, "use_numerology_sessions": True},
            timeout=timeout + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"Cabinet error: {data.get('error')}")
            return ""
        answers: dict = data.get("answers", {})
        parts = [f"[{agent}]: {text}" for agent, text in answers.items() if text]
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"Cabinet unavailable: {e}")
        return ""
