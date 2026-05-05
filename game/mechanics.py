from __future__ import annotations

from game.npc import get_npc_stats, _npc_by_name
from game.state import clamp_int

PHYSICAL_WORDS = ("跑", "逃", "追", "打", "踢", "推", "摔", "攻擊", "掌摑", "爬", "搬", "跪")
VIOLENCE_WORDS = ("打", "踢", "推", "摔", "攻擊", "掌摑", "刺", "砍")
MONEY_WORDS = ("送禮", "賞", "打點", "收買", "賄賂", "銀子", "財物", "買通")
SOCIAL_REPAIR_WORDS = ("賠罪", "請罪", "示好", "安撫", "送禮")
INTRIGUE_WORDS = ("試探", "套話", "查", "打探", "觀察", "設局", "反制", "揭穿")

ATTRIBUTE_LIMITS = {
    "體力": (0, 200),
    "權謀": (0, 100),
    "聲望": (-100, 100),
    "財產": 0,
}


def attribute_bounds(attr: str, current: int = 0) -> tuple[int, int]:
    bounds = ATTRIBUTE_LIMITS.get(attr)
    if isinstance(bounds, tuple):
        return bounds
    if attr == "財產":
        return 0, max(100000, current)
    return 0, 100


def apply_delta(target: dict, key: str, delta: int):
    if not delta:
        return
    target[key] = target.get(key, 0) + int(delta)


def evaluate_player_action_costs(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> dict:
    intent = str(judge_result.get("player_intent") or judge_result.get("intent") or "")
    action_type = judge_result.get("action_type", "unknown")
    attrs = _player_attrs(game_state)
    updates = {"attributes_delta": {}, "relations_delta": {}, "hidden_state_delta": {}}
    events = []
    constraints = []
    allowed = True
    reason = ""

    stamina = _stat(attrs, "體力")
    wealth = _stat(attrs, "財產")
    intrigue = _stat(attrs, "權謀")
    reputation = _stat(attrs, "聲望")
    primary = _primary_context_npc(judge_result, game_state, gamedata, relations)

    physical_cost = _physical_cost(intent, action_type)
    if physical_cost:
        if stamina < physical_cost:
            allowed = False
            reason = "體力不足，這個高強度行動無法完整完成。"
            constraints.append("stamina_limit: player lacks enough stamina for the attempted physical action.")
        else:
            apply_delta(updates["attributes_delta"], "體力", -physical_cost)
            events.append({"type": "attribute_cost", "attribute": "體力", "visible_effect": "這個行動會消耗體力。"})

    money_cost = _money_cost(intent, action_type)
    if money_cost:
        if wealth < money_cost:
            allowed = False
            reason = reason or "財產不足，無法完成需要打點或送禮的行動。"
            constraints.append("wealth_limit: player lacks enough wealth for the attempted gift or bribe.")
        else:
            apply_delta(updates["attributes_delta"], "財產", -money_cost)
            apply_delta(updates["attributes_delta"], "聲望", 1 if reputation < 60 else 0)
            if primary:
                updates["relations_delta"].setdefault(primary, {})
                apply_delta(updates["relations_delta"][primary], "好感度", 2)
                apply_delta(updates["hidden_state_delta"].setdefault(primary, {}), "trust", 2)
            events.append({"type": "resource_spent", "attribute": "財產", "visible_effect": "銀錢或禮物被用來打點人心。"})

    if action_type in {"observe", "ask"} or any(word in intent for word in INTRIGUE_WORDS):
        if intrigue >= 60:
            events.append({"type": "insight", "visible_effect": "玩家較容易察覺話中破綻。"})
            if primary:
                apply_delta(updates["hidden_state_delta"].setdefault(primary, {}), "interest", 2)
        elif intrigue < 20 and primary:
            apply_delta(updates["hidden_state_delta"].setdefault(primary, {}), "suspicion", 2)
            constraints.append("low_intrigue: probing may reveal the player's inexperience.")

    if any(word in intent for word in SOCIAL_REPAIR_WORDS) and primary:
        rel = (relations.get("npcs", {}) or {}).get(primary, {})
        if str(rel.get("恩怨", "無")) not in {"", "無"}:
            updates["relations_delta"].setdefault(primary, {})
            apply_delta(updates["relations_delta"][primary], "好感度", -1)
            constraints.append("grudge_memory: old grievances make repair attempts less effective.")

    if action_type == "attack" or any(word in intent for word in VIOLENCE_WORDS):
        if primary:
            npc_life = _npc_life(primary, gamedata)
            if npc_life >= 100 and stamina < 40:
                allowed = False
                reason = reason or "對方體魄或護衛條件佔優，玩家體力不足以強行壓制。"
                constraints.append("npc_life_resistance: sturdy or well-protected NPC resists low-stamina violence.")
            updates["relations_delta"].setdefault(primary, {})
            updates["hidden_state_delta"].setdefault(primary, {})
            apply_delta(updates["relations_delta"][primary], "好感度", -8)
            apply_delta(updates["relations_delta"][primary], "anger", 10)
            apply_delta(updates["hidden_state_delta"][primary], "anger", 8)
            apply_delta(updates["hidden_state_delta"][primary], "suspicion", 6)
            updates["relations_delta"][primary]["恩怨"] = "曾遭玩家冒犯或攻擊"

    return {
        "allowed": allowed,
        "reason": reason,
        "state_update": updates,
        "events": events,
        "constraints": constraints,
    }


def update_social_graph_from_turn(relations: dict, judge_result: dict, game_state: dict, gamedata: dict):
    relations.setdefault("social_graph", {})
    primary = _primary_context_npc(judge_result, game_state, gamedata, relations)
    if not primary:
        return
    graph = relations["social_graph"].setdefault(primary, {})
    edge = graph.setdefault("玩家", {"attention": 0, "grudge": 0, "favor": 0})
    hidden = (relations.get("hidden_state", {}) or {}).get(primary, {})
    rel = (relations.get("npcs", {}) or {}).get(primary, {})
    edge["attention"] = clamp_int(edge.get("attention", 0) + max(1, _stat(hidden, "interest") // 25), 0, 100)
    edge["favor"] = clamp_int(_stat(rel, "好感度"), -100, 100)
    if str(rel.get("恩怨", "無")) not in {"", "無"}:
        edge["grudge"] = clamp_int(edge.get("grudge", 0) + 2, 0, 100)


def companion_network_power(relations: dict | None) -> int:
    companions = (relations or {}).get("companions", {})
    if not isinstance(companions, dict):
        return 0
    power = 0
    for data in companions.values():
        if not isinstance(data, dict):
            continue
        count = clamp_int(data.get("appear_count", 0), 0, 100)
        if count >= 3:
            power += min(10, 2 + count // 2)
    return min(power, 30)


def _physical_cost(intent: str, action_type: str) -> int:
    if action_type == "attack":
        return 18
    if any(word in intent for word in VIOLENCE_WORDS):
        return 12
    if any(word in intent for word in PHYSICAL_WORDS):
        return 8
    return 0


def _money_cost(intent: str, action_type: str) -> int:
    if action_type == "use_item" and any(word in intent for word in MONEY_WORDS):
        return 20
    if "收買" in intent or "賄賂" in intent or "買通" in intent:
        return 40
    if "打點" in intent:
        return 25
    if "送禮" in intent or "賞" in intent or "銀子" in intent or "財物" in intent:
        return 15
    return 0


def _primary_context_npc(judge_result: dict, game_state: dict, gamedata: dict, relations: dict) -> str | None:
    npcs_by_name = _npc_by_name(gamedata)
    for name in [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]:
        if name in npcs_by_name and (relations.get("npcs", {}) or {}).get(name, {}).get("alive") is not False:
            return name
    for name in (game_state or {}).get("scene_npcs", []) or []:
        if name in npcs_by_name and (relations.get("npcs", {}) or {}).get(name, {}).get("alive") is not False:
            return name
    return None


def _npc_life(name: str, gamedata: dict) -> int:
    npc = _npc_by_name(gamedata).get(name, {})
    return _stat(get_npc_stats(npc), "生命")


def _player_attrs(game_state: dict | None) -> dict:
    status = (game_state or {}).get("status", {}) if isinstance(game_state, dict) else {}
    attrs = status.get("attributes", {}) if isinstance(status, dict) else {}
    return attrs if isinstance(attrs, dict) else {}


def _stat(stats: dict, key: str) -> int:
    return clamp_int((stats or {}).get(key, 0), -1000, 100000)
