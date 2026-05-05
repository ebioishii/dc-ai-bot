from __future__ import annotations
from game.state import get_rules, get_punishments, get_rewards, get_ranks

def _affection_tier(v: int) -> str:
    if v > 80: return "盟友"
    if v > 60: return "友善"
    if v > 30: return "中立"
    if v >= 0: return "警惕"
    return "敵意"


def format_player_relations(relations):
    """將玩家與 NPC 的關係格式化"""
    npcs = relations.get('npcs', {}) if relations else {}
    companions = relations.get('companions', {}) if relations else {}
    rel_info = ""

    if npcs:
        for npc_id, data in npcs.items():
            好感度 = data.get('好感度', 0)
            恩怨 = data.get('恩怨', '無')
            tier = _affection_tier(好感度)
            emotion = data.get('emotion_state', {})
            anger = emotion.get('anger', 0)
            fear = emotion.get('fear', 0)
            alive = data.get('alive', True)
            life_state = "已死亡，不得登場、不得說話、不得被其他角色當作仍活著互動" if alive is False else "存活"
            rel_info += f"• {npc_id}：{life_state}，好感度 {好感度}（{tier}），恩怨：{恩怨}，憤怒：{anger}，恐懼：{fear}\n"

    active_companions = {k: v for k, v in companions.items() if v.get('appear_count', 0) >= 3}
    if active_companions:
        rel_info += "\n【玩家身旁已知隨侍】\n"
        for name, data in active_companions.items():
            rel_info += f"• {name}（{data.get('role', '隨侍')}）：{data.get('desc', '無額外描述')}\n"

    return rel_info if rel_info.strip() else "（尚無記錄的 NPC 關係）"


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


def format_story_reply(story_result: dict) -> str:
    reply = str(story_result.get("reply", "")).strip()
    choices = story_result.get("choices", [])
    choice_text = _choice_lines(choices if isinstance(choices, list) else [])
    if choice_text:
        return f"{reply}\n\n【可選行動】\n{choice_text}"
    return reply


