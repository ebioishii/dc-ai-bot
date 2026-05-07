from __future__ import annotations
from game.state import get_rules, get_punishments, get_rewards, get_ranks

def _affection_tier(v: int) -> str:
    if v > 80: return "盟友"
    if v > 60: return "信任"
    if v > 30: return "友善"
    if v > 10: return "中立偏暖"
    if v >= -10: return "初識"
    if v >= -30: return "戒備"
    return "敵意"


def format_player_relations(relations):
    npcs = relations.get('npcs', {}) if isinstance(relations, dict) else {}
    companions = relations.get('companions', {}) if isinstance(relations, dict) else {}
    lines = []
    for npc_id, data in npcs.items():
        if not isinstance(data, dict):
            continue
        affection = data.get('好感度', data.get('憟賣?摨?', 0))
        grudge = data.get('恩怨', data.get('?拇?', '無'))
        emotion = data.get('emotion_state', {}) if isinstance(data.get('emotion_state'), dict) else {}
        alive = data.get('alive', True)
        state = "已死亡" if alive is False else "存活"
        lines.append(f"{npc_id}：{state}，好感度 {affection}（{_affection_tier(int(affection or 0))}），恩怨：{grudge}，怒氣：{emotion.get('anger', 0)}，懼意：{emotion.get('fear', 0)}")
    active_companions = {k: v for k, v in companions.items() if isinstance(v, dict) and v.get('appear_count', 0) >= 3}
    for name, data in active_companions.items():
        lines.append(f"隨侍 {name}：{data.get('role', '隨侍')}")
    return "\n".join(lines) if lines else "目前沒有明確 NPC 關係。"


def format_game_rules():
    """將所有規則格式化為 AI 可讀的提示"""
    rules_data = get_rules()
    punishments = get_punishments()
    rewards = get_rewards()
    ranks = get_ranks()

    ranks_info = "【後宮位階】皇后＞皇貴妃＞貴妃＞妃＞嬪＞貴人＞常在＞答應＞宮女\n"
    for rank in ranks[:12]:
        ranks_info += f"• {rank['name']}：{rank['description']}\n"

    court_rules = "【宮廷規矩】\n"
    for rule in rules_data.get('court_rules', []):
        court_rules += f"• {rule}\n"

    forbidden = "【禁忌】不可"
    forbidden += "、".join(rules_data.get('forbidden_actions', []))
    forbidden += "。\n"

    punishments_info = "【責處規制】"
    for p in punishments:
        punishments_info += f"{p['name']}：{p['description']}；"

    rewards_info = "【恩賞規制】"
    for r in rewards:
        rewards_info += f"{r['name']}：{r['description']}；"

    return f"{ranks_info}\n{court_rules}\n{forbidden}\n{punishments_info}\n{rewards_info}"


def _choice_lines(choices: list) -> str:
    lines = []
    for index, choice in enumerate(choices[:4], 1):
        text = str(choice.get("text", "")).strip() if isinstance(choice, dict) else ""
        hint = str(choice.get("effect_hint", "")).strip() if isinstance(choice, dict) else ""
        if text:
            if hint:
                lines.append(f"{index}. {text}\n   └ {hint}")
            else:
                lines.append(f"{index}. {text}")
    return "\n".join(lines)


def format_story_reply(story_result: dict, show_choices: bool = True, natural_hint: str = "") -> str:
    reply = str(story_result.get("reply", "")).strip()
    choices = story_result.get("choices", []) if show_choices else []
    choice_text = _choice_lines(choices if isinstance(choices, list) else [])
    if show_choices and choice_text:
        return f"{reply}\n\n【可選行動】\n{choice_text}"
    if natural_hint:
        return f"{reply}\n\n{natural_hint.strip()}"
    return reply


