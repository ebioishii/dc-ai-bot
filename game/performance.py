from __future__ import annotations

import json
import time


def now_ms() -> float:
    return time.perf_counter() * 1000


def elapsed_ms(start_ms: float) -> int:
    return int(max(0, now_ms() - start_ms))


def estimate_tokens(value) -> int:
    text = _to_text(value)
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    non_cjk = max(0, len(text) - cjk)
    return max(1, int(cjk / 1.35 + non_cjk / 4))


def log_reply_performance(payload: dict) -> dict:
    normalized = {
        "channel_id": str(payload.get("channel_id", "")),
        "input_tokens_est": int(payload.get("input_tokens_est", 0)),
        "output_tokens_est": int(payload.get("output_tokens_est", 0)),
        "model_duration_ms": int(payload.get("model_duration_ms", 0)),
        "total_duration_ms": int(payload.get("total_duration_ms", 0)),
        "retry_count": int(payload.get("retry_count", 0)),
        "summary_used": bool(payload.get("summary_used", False)),
        "summary_triggered": bool(payload.get("summary_triggered", False)),
        "recent_turns": int(payload.get("recent_turns", 0)),
        "story_validation_error": str(payload.get("story_validation_error", ""))[:160],
    }
    print(json.dumps(normalized, ensure_ascii=False))
    return normalized


def _to_text(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)
