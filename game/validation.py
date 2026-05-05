from __future__ import annotations
import re

from game.state import _active_summons, default_state_update

CHOICE_STYLES = {"humble", "probe", "observe", "flatter", "confront", "retreat", "wait", "use_item", "other"}
CHOICE_RISKS = {"low", "medium", "high"}

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
            if not str(choice.get("effect_hint", "")).strip():
                return False, "each choice must include effect_hint"
            mech = choice.get("mechanical_effect")
            if not isinstance(mech, dict):
                return False, "each choice must include mechanical_effect"
        styles = {choice.get("style") for choice in choices if isinstance(choice, dict)}
        risks = {choice.get("risk") for choice in choices if isinstance(choice, dict)}
        if len(styles) < 2:
            return False, "choices must include at least two different styles"
        if "low" not in risks:
            return False, "choices must include at least one low risk option"
        if not ({"medium", "high"} & risks):
            return False, "choices must include a higher-risk option"
    elif not isinstance(choices, list):
        choices = []
    output_text = reply + "\n" + "\n".join(str(choice.get("text", "")) for choice in choices if isinstance(choice, dict))

    hidden_leak_patterns = (
        r"(suspicion|interest|anger|trust|hidden_state)\s*[:：=]?\s*\d+",
        r"(懷疑|猜疑|興趣|怒氣|憤怒|信任|隱藏狀態)\s*[:：=]?\s*\d+"
    )
    if any(re.search(pattern, output_text, re.IGNORECASE) for pattern in hidden_leak_patterns):
        return False, "story leaks hidden_state numbers"

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


def detect_kill_targets(text: str, known_names: list[str]) -> list[str]:
    return [name for name in known_names if name and name in text]


def validate_ai_output(data: dict, relations: dict | None, input_type: str, kill_targets: list[str]) -> tuple[bool, str]:
    reply = data.get('reply', '')
    update = data.get('state_update', {})
    if not reply.strip():
        return False, "缺少 reply"
    if not isinstance(update, dict):
        return False, "state_update 必須是 object"
    for dead_name in get_dead_npc_names(relations):
        if f"{dead_name}道" in reply or f"{dead_name}說" in reply or f"{dead_name}冷笑" in reply:
            return False, f"已死亡 NPC「{dead_name}」仍在行動或說話"
    if input_type == 'KILL_CMD' and kill_targets:
        rel_delta = update.get('relations_delta', {})
        missing = [name for name in kill_targets if rel_delta.get(name, {}).get('alive') is not False]
        if missing:
            return False, f"殺戮指令未把目標標記為死亡：{'、'.join(missing)}"
    return True, ""


def build_json_output_contract(input_type: str, kill_targets: list[str]) -> str:
    kill_note = ""
    if input_type == 'KILL_CMD':
        if kill_targets:
            target_lines = "\n".join(f'      "{name}": {{"alive": false, "恩怨": "被玩家下令處死"}}' for name in kill_targets)
            kill_note = f"\n殺戮指令已確認目標：{'、'.join(kill_targets)}。relations_delta 必須包含：\n{target_lines}\n"
        else:
            kill_note = "\n玩家使用了殺戮指令；若文本中有明確目標，必須在 relations_delta 中把該 NPC alive 設為 false。\n"
    return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【輸出格式強制要求】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
只輸出合法 JSON。不得輸出 Markdown、不得加 ```、不得在 JSON 外加解釋。
{kill_note}
JSON schema：
{{
  "reply": "給玩家看的劇情文字。必須接續上一幕，回應玩家本輪行動。",
  "state_update": {{
    "location": null,
    "alive": null,
    "attributes_delta": {{"體力": 0, "權謀": 0, "聲望": 0, "財產": 0}},
    "inventory_add": [],
    "inventory_remove": [],
    "relations_delta": {{
      "NPC名稱": {{"好感度": 0, "anger": 0, "fear": 0, "alive": true, "恩怨": ""}}
    }},
    "facts_add": []
  }}
}}
規則：
1. 沒有變動的欄位用 null、空 object 或空 array。
2. attributes_delta 與 relations_delta 只能填「變化量」，不能填總值。
3. facts_add 只放確定已發生、後續不能推翻的關鍵事實，每條 120 字內。
4. reply 不得替玩家決定內心、不得代替玩家做未聲明的主動行為。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


