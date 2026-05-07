from __future__ import annotations
import re

from game.state import _active_summons, default_state_update

CHOICE_STYLES = {"safe", "probe", "observe", "flatter", "pressure", "retreat", "wait", "use_item", "alliance", "deception", "other"}
CHOICE_RISKS = {"low", "medium", "high"}
CHOICE_REWARDS = {"low", "medium", "high"}
MECHANICAL_EFFECT_KEYS = {
    "target",
    "trust_delta",
    "suspicion_delta",
    "anger_delta",
    "intel_gain",
    "reputation_delta",
    "objective_progress_delta",
}

def validate_story_output_reason(story_result, authoritative_result, game_state, choices_required: bool = True):
    if not isinstance(story_result, dict):
        return False, "story_result is not an object"
    reply = story_result.get("reply", "")
    if not isinstance(reply, str) or not reply.strip():
        return False, "missing reply"
    choices = story_result.get("choices")
    if choices_required:
        if not isinstance(choices, list) or not (2 <= len(choices) <= 4):
            return False, "choices must contain 2-4 items"
        for choice in choices:
            if not isinstance(choice, dict) or not str(choice.get("id", "")).strip() or not str(choice.get("text", "")).strip():
                return False, "each choice must have id and text"
            if choice.get("style") not in CHOICE_STYLES:
                return False, "each choice must include a valid style"
            if choice.get("risk") not in CHOICE_RISKS:
                return False, "each choice must include a valid risk"
            if choice.get("reward") not in CHOICE_REWARDS:
                return False, "each choice must include a valid reward"
            if not str(choice.get("effect_hint", "")).strip():
                return False, "each choice must include effect_hint"
            mech = choice.get("mechanical_effect")
            if not isinstance(mech, dict):
                return False, "each choice must include mechanical_effect"
            if not MECHANICAL_EFFECT_KEYS.issubset(set(mech.keys())):
                return False, "each choice mechanical_effect is missing required keys"
        styles = {choice.get("style") for choice in choices if isinstance(choice, dict)}
        risks = {choice.get("risk") for choice in choices if isinstance(choice, dict)}
        rewards = {choice.get("reward") for choice in choices if isinstance(choice, dict)}
        if len(styles) < 2:
            return False, "choices must include at least two different styles"
        if "low" not in risks:
            return False, "choices must include at least one low risk option"
        if not ({"medium", "high"} & risks):
            return False, "choices must include a higher-risk option"
        if not any(choice.get("risk") in {"medium", "high"} and choice.get("reward") in {"medium", "high"} for choice in choices if isinstance(choice, dict)):
            return False, "choices must include a higher reward option with medium/high risk"
    elif not isinstance(choices, list):
        choices = []
    elif choices:
        return False, "choices must be empty when choices are disabled"
    output_text = reply + "\n" + "\n".join(str(choice.get("text", "")) for choice in choices if isinstance(choice, dict))
    if not choices_required:
        option_markers = ("【可選行動】", "【當前目標】", "效果提示", "1. ", "2. ", "3. ", "4. ", "你可以", "也可以")
        if any(marker in reply for marker in option_markers):
            return False, "story included choices or objective UI when choices are disabled"

    hidden_leak_patterns = (
        r"(suspicion|interest|anger|trust|hidden_state)\s*[:：=]?\s*\d+",
        r"(懷疑|猜疑|興趣|怒氣|憤怒|信任|隱藏狀態)\s*[:：=]?\s*\d+"
    )
    if any(re.search(pattern, output_text, re.IGNORECASE) for pattern in hidden_leak_patterns):
        return False, "story leaks hidden_state numbers"
    forbidden_hidden_terms = ("hidden_state", "suspicion", "trust", "anger", "interest", "threat", "intel_known")
    if any(term in output_text for term in forbidden_hidden_terms):
        return False, "story leaks hidden_state keys"
    forbidden_stock_phrases = (
        "你沒有立刻得到明白答案",
        "回話順序與侍從動線",
        "話落之後，席間的態度",
        "簾外腳步聲停住",
        "原本平順的話題被迫換了節奏",
        "短期目標",
        "向前推進了一小步",
    )
    if any(phrase in output_text for phrase in forbidden_stock_phrases):
        return False, "story uses forbidden stock/progress phrasing"
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result, dict) else {}
    inventory_add = update.get("inventory_add", []) if isinstance(update, dict) else []
    gift_terms = ("給你", "送你", "賞你", "賜你", "遞給你", "交給你", "放在你手中", "塞到你手裡")
    if not inventory_add and any(term in reply for term in gift_terms):
        return False, "story invents an item gift without rule inventory_add"
    forbidden_inner_phrases = ("你感覺", "你知道", "你試圖")
    forbidden_inner_phrases += ("你定了定神", "你心中", "心中的", "心裡", "你暗自", "你不動聲色地")
    if any(term in reply for term in forbidden_inner_phrases):
        return False, "story writes player inner thoughts or intent"

    if _active_summons(game_state):
        forbidden = ("未曾傳召", "沒有傳召", "無人傳召", "並未傳召")
        if any(text in output_text for text in forbidden):
            return False, "story violates active summons ruling"

    relations = game_state.get("relations", {}) if isinstance(game_state, dict) else {}
    for dead_name in get_dead_npc_names(relations):
        if dead_name and dead_name in output_text:
            return False, f"dead NPC appears: {dead_name}"

    denied = authoritative_result.get("denied_assumptions", []) if isinstance(authoritative_result, dict) else []
    negations = ("沒有", "未", "不曾", "尚未", "不能確認", "未確認", "並未")
    for assumption in denied:
        token = str(assumption).strip()[:24]
        if token and token in output_text:
            token_index = output_text.find(token)
            window_start = max(0, token_index - 12)
            window = output_text[window_start:token_index + len(token) + 12]
            if not any(neg in window for neg in negations):
                return False, f"denied assumption written as fact: {token}"
    world_event = authoritative_result.get("world_event", {}) if isinstance(authoritative_result, dict) else {}
    if world_event.get("type") == "none":
        major_event_terms = ("皇上駕到", "皇帝駕到", "聖上駕到", "太監急報", "忽然傳召", "突然傳召", "殿外急促腳步", "闖入", "拾到", "撿到")
        if any(term in reply for term in major_event_terms):
            return False, "story appears to invent a major world_event"
    else:
        desc = str(world_event.get("description", "")).strip()
        if desc:
            anchors = [part[:4] for part in re.split(r"[，。；、\s]+", desc) if len(part) >= 2]
            if anchors and not any(anchor in reply for anchor in anchors[:4]) and world_event.get("type") not in reply:
                return False, "story did not include provided world_event"
    for action in authoritative_result.get("npc_actions", []) if isinstance(authoritative_result, dict) else []:
        npc_name = action.get("npc") if isinstance(action, dict) else ""
        if npc_name and npc_name not in output_text:
            return False, f"story did not include npc_action actor: {npc_name}"
    return True, ""


def validate_story_output(story_result, authoritative_result, game_state, choices_required: bool = True):
    ok, _ = validate_story_output_reason(story_result, authoritative_result, game_state, choices_required=choices_required)
    return ok


def validate_state_update(update: dict, authoritative_result: dict, game_state: dict) -> bool:
    if not isinstance(update, dict):
        return False
    # Story AI suggestions cannot contradict the program ruling.
    allowed_keys = set(default_state_update().keys())
    if any(key not in allowed_keys for key in update.keys()):
        return False
    if authoritative_result.get("allowed") is False and update:
        return False
    return True


def get_dead_npc_names(relations: dict | None) -> list[str]:
    if not relations:
        return []
    return [name for name, data in relations.get('npcs', {}).items() if data.get('alive') is False]
