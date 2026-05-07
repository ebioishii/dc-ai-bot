from __future__ import annotations

HINT_FIELDS = ("id", "text", "style", "risk", "reward", "effect_hint", "mechanical_effect")
STYLE_LABELS = {
    "observe": "觀察",
    "probe": "試探",
    "alliance": "示好",
    "pressure": "施壓",
    "deception": "設局",
    "retreat": "退讓",
    "safe": "穩妥",
}
RISK_LABELS = {"low": "低", "medium": "中", "high": "高"}
REWARD_LABELS = {"low": "低", "medium": "中", "high": "高"}


def compact_hints_for_status(choices) -> list[dict]:
    if not isinstance(choices, list):
        return []
    hints: list[dict] = []
    for choice in choices[:4]:
        if not isinstance(choice, dict):
            continue
        text = str(choice.get("text", "")).strip()
        if not text:
            continue
        hints.append({
            "id": str(choice.get("id", ""))[:40],
            "text": text[:160],
            "style": str(choice.get("style", ""))[:30],
            "risk": str(choice.get("risk", ""))[:20],
            "reward": str(choice.get("reward", ""))[:20],
            "effect_hint": str(choice.get("effect_hint", ""))[:160],
            "mechanical_effect": choice.get("mechanical_effect", {}) if isinstance(choice.get("mechanical_effect"), dict) else {},
        })
    return hints


def format_hint_reply(status: dict | None, memory: dict | None = None, *, include_hints: bool = True) -> str:
    status = status if isinstance(status, dict) else {}
    memory = memory if isinstance(memory, dict) else {}
    scene_state = status.get("scene_state") if isinstance(status.get("scene_state"), dict) else {}

    lines = ["【目前提示】"]
    location = scene_state.get("location") or status.get("location_name") or status.get("location") or "未知"
    lines.append(f"位置：{location}")

    present = [str(name) for name in scene_state.get("present_npcs", []) if str(name).strip()]
    if present:
        lines.append(f"在場 NPC：{'、'.join(present)}")

    objectives = status.get("current_objectives", [])
    if not isinstance(objectives, list):
        objectives = []
    active = [
        item for item in objectives
        if isinstance(item, dict) and item.get("status", "active") == "active" and str(item.get("text", "")).strip()
    ][:5]
    if not active and isinstance(memory.get("objective_summary"), list):
        active = [{"text": text, "progress": 0} for text in memory["objective_summary"] if str(text).strip()][:5]

    lines.append("")
    lines.append("短期目標：")
    if active:
        for item in active:
            progress = item.get("progress")
            progress_text = f"（{progress}%）" if isinstance(progress, int) else ""
            lines.append(f"- {str(item.get('text', '')).strip()}{progress_text}")
    else:
        lines.append("- 目前沒有明確短期目標。")

    if not include_hints:
        return "\n".join(lines)

    hints = compact_hints_for_status(status.get("last_hints", []))
    lines.append("")
    lines.append("建議行動：")
    if not hints:
        lines.append("- 目前沒有建議行動。先描述你想觀察、詢問或採取的做法即可。")
        return "\n".join(lines)

    for index, hint in enumerate(hints, 1):
        meta = " / ".join(
            part for part in (
                f"風格：{STYLE_LABELS.get(hint.get('style'), hint.get('style'))}" if hint.get("style") else "",
                f"風險：{RISK_LABELS.get(hint.get('risk'), hint.get('risk'))}" if hint.get("risk") else "",
                f"收益：{REWARD_LABELS.get(hint.get('reward'), hint.get('reward'))}" if hint.get("reward") else "",
            )
            if part
        )
        lines.append(f"{index}. {hint['text']}")
        if meta:
            lines.append(f"   {meta}")
        if hint.get("effect_hint"):
            lines.append(f"   提示：{hint['effect_hint']}")
    return "\n".join(lines)
