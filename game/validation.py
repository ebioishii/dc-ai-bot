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


NO_CHOICE_UI_MARKERS = (
    "【可選行動】",
    "【當前目標】",
    "效果提示",
    "接下來，你",
    "接下來你",
    "你需要決定",
    "該如何進一步行動",
    "該如何引導",
    "選擇溫和",
    "還是直接施壓",
    "你可以",
    "也可以",
    "1. ",
    "2. ",
    "3. ",
    "4. ",
)

PLAYER_VISIBLE_META_MARKERS = (
    "玩家行動完成",
    "局勢略有推進",
    "玩家對其",
    "玩家的",
    "這表明",
    "這代表",
    "這份自信與宣告",
    "掌控預期",
    "系統",
    "JSON",
    "authoritative_result",
    "state_update",
)

FORBIDDEN_STOCK_PHRASES = (
    "你沒有立刻得到明白答案",
    "回話順序與侍從動線",
    "話落之後，席間的態度",
    "簾外腳步聲停住",
    "原本平順的話題被迫換了節奏",
    "短期目標",
    "向前推進了一小步",
)

FORBIDDEN_INNER_PHRASES = (
    "你感覺",
    "你知道",
    "你試圖",
    "你決定",
    "你定了定神",
    "你心中",
    "心中的",
    "心裡",
    "心底",
    "暗自思忖",
    "你暗自",
    "你不動聲色地",
)

FORBIDDEN_REACTION_TEMPLATE_PHRASES = (
    "有些事情不是妳想的那樣",
    "有些事情，不是妳想的那樣",
    "有些事情不是你想的那樣",
    "有些事情，不是你想的那樣",
    "這裡面牽涉到的",
    "真正要緊的名字仍被她避開",
    "真正要緊的名字仍被他避開",
    "不甘與隱忍",
)

REPEATED_BODY_LANGUAGE_BUNDLE = (
    "臉色蒼白",
    "眼神閃爍",
    "緊咬下唇",
    "緊咬著下唇",
)

INITIAL_HOSTILITY_MARKERS = (
    "不悅",
    "疏離",
    "距離拉遠",
    "冷淡地",
    "冷冷",
    "戒備地退",
    "敵意",
    "嫌惡",
)


def player_visible_text_problem(reply: str, *, choices_required: bool = False) -> str:
    text = str(reply or "")
    if not choices_required and any(marker in text for marker in NO_CHOICE_UI_MARKERS):
        return "story included choices or objective UI when choices are disabled"
    if any(marker in text for marker in PLAYER_VISIBLE_META_MARKERS):
        return "story included meta/system phrasing"
    if any(phrase in text for phrase in FORBIDDEN_STOCK_PHRASES):
        return "story uses forbidden stock/progress phrasing"
    if any(term in text for term in FORBIDDEN_INNER_PHRASES):
        return "story writes player inner thoughts or intent"
    if _uses_repeated_npc_reaction_template(text):
        return "story uses repeated NPC reaction template"
    return ""


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
    visible_problem = player_visible_text_problem(reply, choices_required=choices_required)
    if visible_problem:
        return False, visible_problem
    action_problem = story_action_resolution_problem(reply, authoritative_result, game_state)
    if action_problem:
        return False, action_problem

    hidden_leak_patterns = (
        r"(suspicion|interest|anger|trust|hidden_state)\s*[:：=]?\s*\d+",
        r"(懷疑|猜疑|興趣|怒氣|憤怒|信任|隱藏狀態)\s*[:：=]?\s*\d+"
    )
    if any(re.search(pattern, output_text, re.IGNORECASE) for pattern in hidden_leak_patterns):
        return False, "story leaks hidden_state numbers"
    forbidden_hidden_terms = ("hidden_state", "suspicion", "trust", "anger", "interest", "threat", "intel_known")
    if any(term in output_text for term in forbidden_hidden_terms):
        return False, "story leaks hidden_state keys"
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result, dict) else {}
    inventory_add = update.get("inventory_add", []) if isinstance(update, dict) else []
    gift_terms = ("給你", "送你", "賞你", "賜你", "遞給你", "交給你", "放在你手中", "塞到你手裡")
    if not inventory_add and any(term in reply for term in gift_terms):
        return False, "story invents an item gift without rule inventory_add"
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


def story_action_resolution_problem(reply: str, authoritative_result: dict | None, game_state: dict | None) -> str:
    reply = str(reply or "")
    authoritative_result = authoritative_result if isinstance(authoritative_result, dict) else {}
    game_state = game_state if isinstance(game_state, dict) else {}
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result.get("state_update"), dict) else {}
    status_set = update.get("status_set", {}) if isinstance(update.get("status_set"), dict) else {}
    scene_state = game_state.get("scene_state", {}) if isinstance(game_state.get("scene_state"), dict) else {}
    player_input = str(scene_state.get("visible_player_action") or "")

    audience_target = str(status_set.get("audience_target") or scene_state.get("audience_target") or "").strip()
    denied = authoritative_result.get("denied_assumptions", [])
    if audience_target and "high-rank audience is automatically granted" in denied:
        if _high_rank_target_appears_to_speak_or_rule(reply, audience_target):
            return "story auto-granted high-rank audience"

    if _story_contradicts_declared_action(reply, player_input):
        return "story contradicts the player's declared action"

    if _missing_social_response(reply, authoritative_result, game_state):
        return "story restates player dialogue without NPC response or consequence"
    if _unjustified_initial_hostility(reply, authoritative_result, game_state):
        return "story invents early NPC hostility without cause"
    return ""


def _high_rank_target_appears_to_speak_or_rule(reply: str, target: str) -> bool:
    if target not in reply:
        return False
    negation_terms = ("尚未", "未能", "不能", "沒有", "不得", "等候", "通報", "求見", "候著")
    target_index = reply.find(target)
    window = reply[max(0, target_index - 24):target_index + 80]
    if any(term in window for term in negation_terms):
        return False
    auto_grant_terms = ("說道", "開口", "聽後", "點頭", "應允", "會徹查", "本宮", "在此聽著", "傳見", "召見")
    return any(term in window or term in reply for term in auto_grant_terms)


def _story_contradicts_declared_action(reply: str, player_input: str) -> bool:
    if not player_input:
        return False
    action_terms = ("搭話", "詢問", "問", "請求", "通報", "告發", "等待", "觀察")
    if not any(term in player_input for term in action_terms):
        return False
    contradiction_patterns = (
        "沒有直接與她們搭話",
        "沒有直接與他們搭話",
        "沒有與她們搭話",
        "沒有與他們搭話",
        "沒有直接搭話",
        "沒有再搭話",
        "沒有開口",
        "沒有詢問",
        "沒有通報",
        "沒有告發",
    )
    if any(pattern in reply for pattern in contradiction_patterns):
        return True
    if "等待" in player_input and "回到" in reply and "方才" in reply and "等待" not in reply:
        return True
    return False


def _missing_social_response(reply: str, authoritative_result: dict, game_state: dict) -> bool:
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result.get("state_update"), dict) else {}
    turn_type = str(update.get("last_turn_type") or "")
    if turn_type not in {"ask", "social", "pressure", "threaten", "accuse"}:
        return False
    scene_npcs = [str(name).strip() for name in game_state.get("scene_npcs", []) if str(name).strip()]
    relevant = [str(name).strip() for name in authoritative_result.get("relevant_npcs", []) if str(name).strip()]
    targets = [name for name in list(dict.fromkeys(relevant + scene_npcs)) if name not in {"其他宮人", "通報宮人"}]
    if not targets:
        return False
    if "」" not in reply:
        return False
    first_quote_end = reply.find("」")
    head = reply[:first_quote_end + 1]
    tail = reply[first_quote_end + 1:]
    response_markers = ("聞言", "看", "望", "答", "說", "回", "沉默", "皺", "退", "避開", "低聲", "停", "臉色", "眼神", "宮人")
    if any(target in head and any(marker in head for marker in response_markers) for target in targets):
        return False
    return not any(target in tail and any(marker in tail for marker in response_markers) for target in targets)


def _uses_repeated_npc_reaction_template(text: str) -> bool:
    if any(phrase in text for phrase in FORBIDDEN_REACTION_TEMPLATE_PHRASES):
        return True
    return sum(1 for phrase in REPEATED_BODY_LANGUAGE_BUNDLE if phrase in text) >= 2


def _unjustified_initial_hostility(reply: str, authoritative_result: dict, game_state: dict) -> bool:
    status = game_state.get("status", {}) if isinstance(game_state.get("status"), dict) else {}
    try:
        turn_count = int(status.get("turn_count", 0) or 0)
    except (TypeError, ValueError):
        turn_count = 0
    if turn_count > 2:
        return False

    scene_state = game_state.get("scene_state", {}) if isinstance(game_state.get("scene_state"), dict) else {}
    player_input = str(scene_state.get("visible_player_action") or "")
    gentle_first_contact = ("打招呼", "寒暄", "自我介紹", "請安", "問候", "見禮")
    if not any(term in player_input for term in gentle_first_contact):
        return False
    if not any(marker in reply for marker in INITIAL_HOSTILITY_MARKERS):
        return False
    if _has_authorized_negative_pressure(authoritative_result, game_state):
        return False
    return True


def _has_authorized_negative_pressure(authoritative_result: dict, game_state: dict) -> bool:
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result.get("state_update"), dict) else {}
    turn_type = str(update.get("last_turn_type") or "")
    if turn_type in {"pressure", "threaten", "accuse", "attack"}:
        return True
    for event in authoritative_result.get("confirmed_events", []) if isinstance(authoritative_result, dict) else []:
        if isinstance(event, dict) and event.get("type") in {"public_pressure", "insult", "violence", "failed_check"}:
            return True
    relations = game_state.get("relations", {}) if isinstance(game_state.get("relations"), dict) else {}
    for data in (relations.get("npcs", {}) or {}).values():
        if not isinstance(data, dict):
            continue
        emotion = data.get("emotion_state", {}) if isinstance(data.get("emotion_state"), dict) else {}
        if int(data.get("好感度", 0) or 0) < 0 or int(emotion.get("anger", 0) or 0) > 0:
            return True
    return False


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
