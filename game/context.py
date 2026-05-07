from __future__ import annotations

import re
from copy import deepcopy

RECENT_TURNS_MIN = 3
RECENT_TURNS_MAX = 6
DEFAULT_RECENT_TURNS = 4
SUMMARY_INTERVAL_TURNS = 5
SCENE_SUMMARY_MAX_CHARS = 600


DEFAULT_SCENE_STATE = {
    "location": "",
    "phase": "normal",
    "present_npcs": [],
    "audience_target": "",
    "pending_audience_request": False,
    "player_posture": "",
    "visible_player_action": "",
    "npc_mood": {},
    "suspicion_level": 0,
    "relationship_delta": {},
    "known_information": [],
    "unresolved_hooks": [],
}


def clamp_recent_turns(value: int | None = None) -> int:
    try:
        turns = int(value if value is not None else DEFAULT_RECENT_TURNS)
    except Exception:
        turns = DEFAULT_RECENT_TURNS
    return max(RECENT_TURNS_MIN, min(RECENT_TURNS_MAX, turns))


def compact_turn(turn: dict) -> dict:
    user = str((turn or {}).get("user", "")).strip()
    bot = strip_choice_block(str((turn or {}).get("bot", "")).strip())
    return {
        "user": user[:160],
        "bot": bot[:260] + ("…" if len(bot) > 260 else ""),
    }

def strip_choice_block(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    for pattern in (r"\n\s*【可選行動】", r"\n\s*【當前目標】", r"\n\s*??貉???"):
        text = re.split(pattern, text, maxsplit=1)[0]
    return text.strip()


def recent_turns_for_prompt(memory: dict | None, recent_turns: int | None = None) -> list[dict]:
    memory = memory or {}
    count = clamp_recent_turns(recent_turns)
    turns = memory.get("short_term", [])
    if not isinstance(turns, list):
        return []
    return [compact_turn(turn) for turn in turns[-count:] if isinstance(turn, dict)]


def default_scene_state() -> dict:
    return deepcopy(DEFAULT_SCENE_STATE)


def normalize_scene_state(
    scene_state: dict | None,
    *,
    status: dict | None = None,
    relations: dict | None = None,
    scene_npcs: list[str] | None = None,
    player_input: str = "",
    authoritative_result: dict | None = None,
) -> dict:
    state = default_scene_state()
    if isinstance(scene_state, dict):
        for key in state:
            if key in scene_state:
                state[key] = deepcopy(scene_state[key])

    status = status or {}
    location = status.get("location_name") or status.get("location") or status.get("location_id") or ""
    state["location"] = str(location)

    explicit = set(state.get("explicit_present_npcs", []) or [])
    npcs = [str(name).strip() for name in (scene_npcs or state.get("present_npcs") or []) if str(name).strip()]
    crowd_terms = ("周圍", "眾人", "在場", "大家", "宮人", "宮女太監")
    if any(term in str(player_input or "") for term in crowd_terms) and "其他宮人" not in npcs:
        npcs.append("其他宮人")
    state["present_npcs"] = list(dict.fromkeys(npcs))[:8]
    state["visible_player_action"] = str(player_input).strip()[:160]

    rel_npcs = (relations or {}).get("npcs", {}) if isinstance(relations, dict) else {}
    npc_mood = {}
    for name in state["present_npcs"]:
        data = rel_npcs.get(name, {}) if isinstance(rel_npcs, dict) else {}
        emotion = data.get("emotion_state", {}) if isinstance(data, dict) else {}
        mood_bits = []
        anger = _safe_int(emotion.get("anger", 0))
        fear = _safe_int(emotion.get("fear", 0))
        if anger >= 70:
            mood_bits.append("震怒")
        elif anger >= 40:
            mood_bits.append("不悅")
        if fear >= 70:
            mood_bits.append("畏懼")
        elif fear >= 40:
            mood_bits.append("戒慎")
        if data.get("alive") is False:
            mood_bits.append("已死亡")
        if mood_bits:
            npc_mood[name] = "、".join(mood_bits)
    state["npc_mood"] = npc_mood

    hidden = (relations or {}).get("hidden_state", {}) if isinstance(relations, dict) else {}
    suspicions = []
    for name in state["present_npcs"]:
        npc_hidden = hidden.get(name, {}) if isinstance(hidden, dict) else {}
        if isinstance(npc_hidden, dict):
            suspicions.append(_safe_int(npc_hidden.get("suspicion", 0)))
    state["suspicion_level"] = max(suspicions) if suspicions else _safe_int(state.get("suspicion_level", 0))

    update = (authoritative_result or {}).get("state_update", {}) if isinstance(authoritative_result, dict) else {}
    if isinstance(update, dict):
        status_set = update.get("status_set", {}) if isinstance(update.get("status_set"), dict) else {}
        if status_set.get("pending_audience_request") or status.get("pending_audience_request"):
            target = str(status_set.get("audience_target") or status.get("audience_target") or state.get("audience_target") or "主位娘娘").strip()
            state["phase"] = "audience_request"
            state["pending_audience_request"] = True
            state["audience_target"] = target
            state["present_npcs"] = [name for name in state["present_npcs"] if name != target]
            if "通報宮人" not in state["present_npcs"]:
                state["present_npcs"].append("通報宮人")
            state["unresolved_hooks"] = _dedupe_keep_tail(
                (state.get("unresolved_hooks") or []) + [f"已請求通報{target}，尚未獲准入見。"],
                12,
            )
        state["relationship_delta"] = update.get("relations_delta", {}) if isinstance(update.get("relations_delta"), dict) else {}
        facts = [str(item).strip()[:120] for item in update.get("facts_add", []) if str(item).strip()]
        if facts:
            state["known_information"] = _dedupe_keep_tail((state.get("known_information") or []) + facts, 12)
        hooks = [str(item).strip()[:100] for item in update.get("flags_add", []) if str(item).strip()]
        if hooks:
            state["unresolved_hooks"] = _dedupe_keep_tail((state.get("unresolved_hooks") or []) + hooks, 12)

    return state


def build_model_context(
    memory: dict | None,
    *,
    status: dict | None = None,
    relations: dict | None = None,
    scene_npcs: list[str] | None = None,
    player_input: str = "",
    authoritative_result: dict | None = None,
    recent_turns: int | None = None,
) -> dict:
    memory = memory or {}
    status_scene_state = status.get("scene_state") if isinstance(status, dict) else None
    scene_state = normalize_scene_state(
        status_scene_state if isinstance(status_scene_state, dict) else memory.get("scene_state"),
        status=status,
        relations=relations,
        scene_npcs=scene_npcs,
        player_input=player_input,
        authoritative_result=authoritative_result,
    )
    recent = recent_turns_for_prompt(memory, recent_turns)
    scene_summary = str(memory.get("scene_summary") or memory.get("long_term_summary") or "").strip()
    return {
        "scene_state": scene_state,
        "scene_summary": scene_summary or "（尚無可用場景摘要）",
        "recent_turns": recent,
        "recent_turns_count": len(recent),
        "fact_sheet": memory.get("fact_sheet", ""),
    }


def compact_memory_window(
    memory: dict | None,
    *,
    status: dict | None = None,
    relations: dict | None = None,
    recent_limit: int = DEFAULT_RECENT_TURNS,
    force: bool = False,
) -> tuple[dict, bool]:
    memory = dict(memory or {})
    turns = memory.get("short_term", [])
    if not isinstance(turns, list):
        turns = []
    recent_limit = clamp_recent_turns(recent_limit)
    since_summary = _safe_int(memory.get("summary_turns_since_update", 0))
    should_summarize = force or len(turns) > recent_limit or since_summary >= SUMMARY_INTERVAL_TURNS
    if not should_summarize:
        memory["summary_turns_since_update"] = since_summary
        return memory, False

    keep = min(recent_limit, max(RECENT_TURNS_MIN, 4))
    old_turns = turns[:-keep] if len(turns) > keep else turns
    recent_turns = turns[-keep:] if len(turns) > keep else turns
    if old_turns:
        memory["scene_summary"] = merge_scene_summary(
            memory.get("scene_summary", ""),
            old_turns,
            status=status,
            relations=relations,
        )
        memory["long_term_summary"] = memory["scene_summary"]
        memory["short_term"] = recent_turns
        memory["summary_turns_since_update"] = 0
        return memory, True

    memory["summary_turns_since_update"] = 0
    return memory, False


def merge_scene_summary(
    existing_summary: str,
    old_turns: list[dict],
    *,
    status: dict | None = None,
    relations: dict | None = None,
) -> str:
    facts = []
    existing = str(existing_summary or "").strip()
    if existing:
        facts.extend(_split_summary_items(existing))

    location = (status or {}).get("location_name") or (status or {}).get("location") or ""
    if location:
        facts.append(f"地點：目前場景在{location}。")

    for turn in old_turns:
        if not isinstance(turn, dict):
            continue
        user = _clean_for_summary(turn.get("user", ""), 90)
        bot = _clean_for_summary(strip_choice_block(str(turn.get("bot", ""))), 150)
        if user:
            facts.append(f"玩家重要行動：{user}。")
        consequence = _extract_consequence(bot)
        if consequence:
            facts.append(f"場景結果：{consequence}")

    rel_npcs = (relations or {}).get("npcs", {}) if isinstance(relations, dict) else {}
    for name, data in list(rel_npcs.items())[:8]:
        if not isinstance(data, dict):
            continue
        mood = []
        if data.get("alive") is False:
            mood.append("已死亡")
        affection = data.get("好感度")
        if isinstance(affection, int):
            if affection <= -30:
                mood.append("態度敵意")
            elif affection >= 60:
                mood.append("態度友善")
        emotion = data.get("emotion_state", {})
        if isinstance(emotion, dict) and _safe_int(emotion.get("anger", 0)) >= 50:
            mood.append("怒意升高")
        if mood:
            facts.append(f"NPC態度：{name}{'、'.join(mood)}。")

    return _trim_summary("".join(_dedupe_keep_tail(facts, 24)), SCENE_SUMMARY_MAX_CHARS)


def classify_event_size(judge_result: dict | None, authoritative_result: dict | None) -> str:
    authoritative_result = authoritative_result or {}
    world_event = authoritative_result.get("world_event", {}) if isinstance(authoritative_result, dict) else {}
    confirmed = authoritative_result.get("confirmed_events", []) if isinstance(authoritative_result, dict) else []
    if isinstance(world_event, dict) and world_event.get("type") not in (None, "", "none"):
        return "major"
    if any(isinstance(event, dict) and event.get("type") in {"npc_death", "summons_active"} for event in confirmed):
        return "major"
    if authoritative_result.get("allowed") is False:
        return "small"
    if authoritative_result.get("npc_actions") or authoritative_result.get("scheme_events") or authoritative_result.get("visible_clues"):
        return "small"
    if (judge_result or {}).get("risk_level") == "high":
        return "small"
    return "normal"


def output_length_policy(event_size: str) -> dict:
    if event_size == "major":
        return {"event_size": "major", "min_chars": 450, "max_chars": 700}
    if event_size == "small":
        return {"event_size": "small", "min_chars": 300, "max_chars": 520}
    return {"event_size": "normal", "min_chars": 220, "max_chars": 400}


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _dedupe_keep_tail(items: list, limit: int) -> list:
    result = []
    seen = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result[-limit:]


def _clean_for_summary(text: str, limit: int) -> str:
    text = str(text or "")
    text = re.sub(r"^\[.*?\]\s*", "", text)
    text = re.sub(r"【可選行動】.*", "", text, flags=re.S)
    text = re.sub(r"\s+", " ", text).strip(" 。；，")
    return text[:limit]


def _extract_consequence(text: str) -> str:
    text = _clean_for_summary(text, 180)
    if not text:
        return ""
    sentences = re.split(r"(?<=[。！？；])", text)
    useful = [item.strip() for item in sentences if item.strip()]
    return (useful[-1] if useful else text)[:150]


def _split_summary_items(summary: str) -> list[str]:
    items = re.split(r"(?<=[。！？])", summary)
    return [item.strip() for item in items if item.strip()]


def _trim_summary(summary: str, max_chars: int) -> str:
    summary = re.sub(r"\s+", "", summary).strip()
    if len(summary) <= max_chars:
        return summary
    start = max(0, len(summary) - max_chars)
    trimmed = summary[start:]
    first_stop = min([idx for idx in (trimmed.find("。"), trimmed.find("！"), trimmed.find("？")) if idx >= 0] or [0])
    if first_stop > 0 and first_stop < 80:
        trimmed = trimmed[first_stop + 1:]
    return trimmed[:max_chars].strip()
