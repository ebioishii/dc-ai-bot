from __future__ import annotations

import re
from difflib import SequenceMatcher

DEBUG_LINE_PATTERNS = (
    r"劇情修正",
    r"修正意見",
    r"已使用\s*OOC",
    r"\bDEBUG\b",
    r"\[DEBUG\]",
    r"debug\s*[:：]",
)

PLAYER_INNER_CONTROL_PATTERNS = (
    r"你心(?:中|裡|底)[^。！？\n]{0,40}(?:恐懼|害怕|慌亂|絕望|後悔|明白)[^。！？\n]*[。！？]?",
    r"你不由得[^。！？\n]{0,40}(?:恐懼|害怕|心驚|發抖|後悔)[^。！？\n]*[。！？]?",
    r"你感到[^。！？\n]{0,40}(?:恐懼|害怕|絕望|羞愧|後悔)[^。！？\n]*[。！？]?",
    r"你知道自己[^。！？\n]{0,40}(?:完了|害怕|輸了|錯了)[^。！？\n]*[。！？]?",
)


def sanitize_player_visible_text(text: str) -> str:
    text = str(text or "")
    kept_lines = []
    for line in text.splitlines():
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in DEBUG_LINE_PATTERNS):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines).strip()
    cleaned = remove_player_inner_control(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def remove_player_inner_control(text: str) -> str:
    cleaned = str(text or "")
    for pattern in PLAYER_INNER_CONTROL_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def chinese_char_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", str(text or "")))


def truncate_chinese_text(text: str, max_chars: int) -> tuple[str, bool]:
    text = str(text or "").strip()
    if chinese_char_count(text) <= max_chars:
        return text, False
    cjk_seen = 0
    cut_at = len(text)
    for index, char in enumerate(text):
        if "\u4e00" <= char <= "\u9fff":
            cjk_seen += 1
        if cjk_seen >= max_chars:
            cut_at = index + 1
            break
    soft_end = cut_at
    for index in range(cut_at, min(len(text), cut_at + 32)):
        if text[index] in "。！？；":
            soft_end = index + 1
            break
    return text[:soft_end].rstrip("，、； ") + "……", True


def normalized_similarity(left: str, right: str) -> float:
    left_norm = _normalize_for_similarity(left)
    right_norm = _normalize_for_similarity(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def inspect_story_quality(reply: str, *, previous_reply: str = "", max_chars: int = 600, min_chars: int = 0) -> dict:
    raw = str(reply or "")
    sanitized = sanitize_player_visible_text(raw)
    char_count = chinese_char_count(sanitized)
    similarity = normalized_similarity(sanitized, previous_reply)
    too_long = char_count > max_chars
    too_short = min_chars > 0 and char_count < min_chars
    had_debug = sanitized != raw.strip() and any(
        re.search(pattern, raw, re.IGNORECASE) for pattern in DEBUG_LINE_PATTERNS
    )
    player_control = any(re.search(pattern, raw) for pattern in PLAYER_INNER_CONTROL_PATTERNS)
    duplicate = similarity >= 0.86
    unusable = not sanitized.strip()
    retry_recommended = unusable or duplicate or player_control or too_short
    return {
        "sanitized": sanitized,
        "too_long": too_long,
        "too_short": too_short,
        "had_debug": had_debug,
        "player_control": player_control,
        "duplicate": duplicate,
        "similarity": similarity,
        "retry_recommended": retry_recommended,
    }


def finalize_story_result(
    story_result: dict,
    *,
    previous_reply: str = "",
    length_policy: dict | None = None,
) -> tuple[dict, dict]:
    policy = length_policy or {"max_chars": 600}
    max_chars = int(policy.get("max_chars", 600))
    result = dict(story_result or {})
    quality = inspect_story_quality(result.get("reply", ""), previous_reply=previous_reply, max_chars=max_chars)
    reply = quality["sanitized"]
    reply, truncated = truncate_chinese_text(reply, max_chars)
    result["reply"] = reply
    result["choices"] = _sanitize_choices(result.get("choices", []))
    quality["truncated"] = truncated
    quality["output_chars"] = chinese_char_count(reply)
    return result, quality


def natural_next_step_hint(story_result: dict | None = None) -> str:
    choices = (story_result or {}).get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        text = str(first.get("text", "")).strip()
        if text:
            return f"你可以順勢{text[:36]}，也可以先觀察對方反應。"
    return "你可以順勢回應，也可以先觀察周遭反應。"


def _sanitize_choices(choices) -> list[dict]:
    if not isinstance(choices, list):
        return []
    cleaned = []
    for choice in choices[:4]:
        if not isinstance(choice, dict):
            continue
        text = sanitize_player_visible_text(choice.get("text", ""))
        if not text:
            continue
        cleaned.append({
            **choice,
            "text": text[:120],
            "effect_hint": sanitize_player_visible_text(choice.get("effect_hint", ""))[:120],
        })
    return cleaned


def _normalize_for_similarity(text: str) -> str:
    text = re.sub(r"【可選行動】.*", "", str(text or ""), flags=re.S)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)
    return text.lower()
