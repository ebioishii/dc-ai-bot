from __future__ import annotations

import re

from game.quality import normalized_similarity
from game.validation import player_visible_text_problem


OOC_UNSAFE_EVENT_MARKERS = (
    "駕到",
    "闖入",
    "傳您過去",
    "急促的腳步",
    "殿外傳來",
    "忽然傳來",
    "忽然，一陣",
    "新寵",
)

OOC_GENERIC_REWRITE_MARKERS = (
    "沒有描寫劇情",
    "重新生成",
    "重新寫",
    "重寫",
    "以此重新",
    "上一段不對",
)


def extract_ooc_target_action(correction: str, last_exchange: dict | None = None) -> str:
    """Prefer the quoted action inside an OOC correction, then fall back to the stored user action."""
    correction = str(correction or "").strip()
    for pattern in (r"「([^」]{2,500})」", r'"([^"]{2,500})"', r"'([^']{2,500})'"):
        match = re.search(pattern, correction)
        if match:
            return match.group(1).strip()
    last_user = str((last_exchange or {}).get("user", "")).strip()
    return last_user or correction[:500]


def should_record_ooc_fact(correction: str) -> bool:
    """Only durable world/character corrections belong in fact_sheet."""
    text = str(correction or "").strip()
    if not text:
        return False
    if any(marker in text for marker in OOC_GENERIC_REWRITE_MARKERS):
        return False
    return any(marker in text for marker in ("事實", "設定", "記住", "應該是", "不是", "不能"))


def build_ooc_rewrite_prompt(
    *,
    correction: str,
    target_action: str,
    invalid_previous_reply: str,
    profile: dict,
    status: dict,
    present_npcs: list[str],
    npc_database: str,
    history_summary: str,
    fact_sheet: str,
) -> tuple[str, str]:
    location = status.get("location_name") or status.get("location") or "未知"
    scene_state = status.get("scene_state", {}) if isinstance(status.get("scene_state"), dict) else {}
    present = "、".join(name for name in present_npcs if name) or "無"
    system = (
        "You are an OOC rewrite editor for a Discord palace-intrigue text game. "
        "Rewrite only the invalid previous narration for the same player action. "
        "Do not act as a free GM and do not create new state. Output JSON only."
    )
    user = {
        "task": "Rewrite the previous invalid story reply as JSON: {\"reply\": \"...\"}.",
        "player_correction": correction,
        "target_player_action": target_action,
        "invalid_previous_reply_do_not_copy": str(invalid_previous_reply or "")[:500],
        "current_state": {
            "player_name": profile.get("name", ""),
            "background": profile.get("family_description", ""),
            "location": location,
            "scene_state": scene_state,
            "present_npcs": present_npcs,
        },
        "npc_context": npc_database,
        "recent_valid_history": history_summary,
        "fact_sheet": fact_sheet or "",
        "hard_rules": [
            "Return JSON only with reply. No choices, no markdown, no OOC explanation.",
            "This is a rewrite of target_player_action, not a new turn.",
            "Do not repeat earlier setup from recent_valid_history. One short location clause is enough.",
            "Only resolve the target_player_action and show concrete visible response, clue, risk, or relation change.",
            "Do not introduce new arrivals, summons, messengers, footsteps outside, sudden interruptions, new items, or new conflicts.",
            f"Only these NPCs may be physically present, speak, or react: {present}.",
            "NPCs not in present_npcs may only be mentioned as topics of conversation, not as entering or acting.",
            "Do not reveal hidden numbers, system labels, objective progress, or /hint content.",
            "Do not write player thoughts unless the target_player_action explicitly says the player thought/planned it.",
            "Keep the reply between 160 and 320 Chinese characters.",
        ],
    }
    return system, str(user)


def ooc_rewrite_problem(reply: str, *, previous_valid_reply: str = "") -> str:
    text = str(reply or "").strip()
    if not text:
        return "empty reply"
    if any(marker in text for marker in OOC_UNSAFE_EVENT_MARKERS):
        return "rewrite invented a new arrival/interruption/event"
    if previous_valid_reply and normalized_similarity(text, previous_valid_reply) >= 0.72:
        return "rewrite repeated too much previous narration"
    visible_problem = player_visible_text_problem(text, choices_required=False)
    if visible_problem:
        return visible_problem
    return ""
