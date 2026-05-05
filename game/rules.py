from __future__ import annotations
from game.state import default_state_update, get_rules, get_punishments, get_rewards, get_ranks, _active_summons, clamp_int
from game.judge import judge_fallback
from game.npc import (
    ensure_hidden_state, _npc_by_name, _rank_level, _is_high_rank_npc,
    _hidden_state_for, _add_hidden_delta, _add_relation_delta, _primary_npc,
    plan_npc_actions,
)
from game.events import plan_world_event

def classify_player_input(text: str) -> tuple[str, str]:
    """
    回傳 (input_type, cleaned_text)
    input_type: 'SLASH_CMD' | 'KILL_CMD' | 'NARRATIVE'
    """
    t = text.strip()
    # /ooc 與 /op 由 Discord slash command 處理，不會走到這裡
    # 處理玩家在普通訊息中輸入的強制指令關鍵字
    kill_keywords = ['殺死', '殺掉', '處死', '賜死', '斬殺', '砍頭']
    for kw in kill_keywords:
        if kw in t:
            return ('KILL_CMD', t)
    return ('NARRATIVE', t)


def merge_state_update(base: dict, extra: dict | None) -> dict:
    if not isinstance(extra, dict):
        return base
    for key in ("inventory_add", "inventory_remove", "facts_add", "flags_add", "flags_remove", "blocked_choices_add"):
        base.setdefault(key, [])
        for item in extra.get(key) or []:
            if item not in base[key]:
                base[key].append(item)
    for key in ("attributes_delta", "relations_delta", "hidden_state_delta"):
        for name, delta in (extra.get(key) or {}).items():
            if isinstance(delta, dict):
                target = base.setdefault(key, {}).setdefault(name, {})
                for sub_key, value in delta.items():
                    try:
                        target[sub_key] = target.get(sub_key, 0) + int(value)
                    except Exception:
                        target[sub_key] = value
    for key in ("status_set",):
        if isinstance(extra.get(key), dict):
            base.setdefault(key, {}).update(extra[key])
    if extra.get("reputation_delta"):
        base["reputation_delta"] = base.get("reputation_delta", 0) + int(extra.get("reputation_delta", 0))
    return base


def resolve_rules(judge_result, game_state, memory, relations, inventory, gamedata):
    result = {
        "allowed": True,
        "reason": "",
        "confirmed_events": [],
        "denied_assumptions": [],
        "state_update": default_state_update(),
        "required_lore_keys": [],
        "relevant_npcs": [],
        "constraints": [],
        "npc_actions": [],
        "world_event": {"type": "none", "description": "", "state_update": {}}
    }
    if not isinstance(judge_result, dict):
        judge_result = judge_fallback()

    relations = ensure_hidden_state(relations, gamedata, game_state, str(judge_result.get("player_intent") or judge_result.get("intent") or ""))
    mentioned_npcs = [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]
    mentioned_items = [str(x) for x in judge_result.get("mentioned_items", []) if str(x).strip()]
    assumptions = [str(x) for x in judge_result.get("assumptions", []) if str(x).strip()]
    action_type = judge_result.get("action_type", "unknown")
    intent = str(judge_result.get("player_intent") or judge_result.get("intent", ""))
    social_tone = judge_result.get("social_tone", "neutral")
    risk_level = judge_result.get("risk_level", "medium")

    inventory_items = set((inventory or {}).get("items", []))
    rel_npcs = (relations or {}).get("npcs", {})
    npcs_by_name = _npc_by_name(gamedata)

    for summons in _active_summons(game_state):
        result["confirmed_events"].append({"type": "summons_active", "data": summons})
        result["constraints"].append("summons_active: story must not say the player was never summoned.")

    for npc_name in mentioned_npcs:
        npc_state = rel_npcs.get(npc_name, {})
        if npc_state.get("alive") is False:
            result["allowed"] = False
            result["denied_assumptions"].append(f"{npc_name} can appear, act, or speak")
            result["constraints"].append(f"dead_npc: {npc_name} is dead and must not appear.")
            continue
        if npc_name in npcs_by_name:
            result["relevant_npcs"].append(npc_name)

    input_type = game_state.get("input_type") if isinstance(game_state, dict) else ""
    kill_words = ("殺死", "賜死", "處決", "斬", "殺了")
    if input_type == "KILL_CMD" or any(word in intent for word in kill_words):
        live_targets = [
            name for name in mentioned_npcs
            if name in npcs_by_name and (rel_npcs.get(name, {}).get("alive") is not False)
        ]
        if live_targets:
            rel_delta = result["state_update"].setdefault("relations_delta", {})
            for npc_name in live_targets:
                rel_delta[npc_name] = {"alive": False, "恩怨": "已死亡"}
            result["confirmed_events"].append({"type": "npc_death", "targets": live_targets})
            result["constraints"].append(f"npc_death: {', '.join(live_targets)} are dead after this ruling.")

    missing_items = [item for item in mentioned_items if item not in inventory_items]
    if action_type == "use_item" and missing_items:
        result["allowed"] = False
        result["denied_assumptions"].extend([f"player has item: {item}" for item in missing_items])
        result["constraints"].append(f"missing_items: player does not have {', '.join(missing_items)}.")

    if assumptions:
        result["denied_assumptions"].extend(assumptions)
        result["constraints"].append("player_assumptions: do not treat player assumptions as confirmed events.")

    primary = _primary_npc(mentioned_npcs, game_state if isinstance(game_state, dict) else {}, gamedata, relations)
    mechanical_tags = {str(x) for x in judge_result.get("mechanical_tags", [])}
    high_risk_social = risk_level == "high" or social_tone in {"rude", "probing"} or bool({"provocation", "information_probe", "high_rank_target"} & mechanical_tags)
    if primary and high_risk_social:
        npc = npcs_by_name.get(primary, {})
        hidden = _hidden_state_for(relations, primary)
        suspicion = clamp_int(hidden.get("suspicion", 0), 0, 100)
        anger = clamp_int(hidden.get("anger", 0), 0, 100)
        if _is_high_rank_npc(npc, gamedata) and (suspicion >= 45 or social_tone in {"rude", "probing"}):
            suspicion_cost = 8 if social_tone == "rude" else 5
            anger_cost = 6 if social_tone == "rude" else 3
            _add_hidden_delta(result["state_update"], primary, suspicion=suspicion_cost, anger=anger_cost)
            _add_relation_delta(result["state_update"], primary, 好感度=-4 if social_tone == "rude" else -2, anger=anger_cost)
            result["state_update"]["reputation_delta"] = result["state_update"].get("reputation_delta", 0) - 1
            result["state_update"].setdefault("flags_add", []).append(f"{primary}起疑")
            result["state_update"].setdefault("blocked_choices_add", []).append(f"reckless_probe:{primary}")
            result["confirmed_events"].append({
                "type": "failure_cost",
                "target": primary,
                "reason": "high_risk_social_misread",
                "visible_effect": f"{primary}對玩家的試探或冒犯有所警覺。"
            })
            result["constraints"].append("failure_cost: narrate the social consequence indirectly; do not expose numeric hidden_state.")

    profile = game_state.get("profile", {}) if isinstance(game_state, dict) else {}
    player_rank_level = _rank_level(profile.get("rank"), gamedata)
    command_words = ("命令", "吩咐", "叫", "讓", "要求", "下令")
    if any(word in intent for word in command_words):
        for npc_name in mentioned_npcs:
            npc = npcs_by_name.get(npc_name, {})
            npc_rank_level = _rank_level(npc.get("rank"), gamedata)
            if player_rank_level is not None and npc_rank_level is not None and player_rank_level > npc_rank_level:
                result["allowed"] = False
                result["denied_assumptions"].append(f"player can command higher-rank NPC: {npc_name}")
                result["constraints"].append(f"rank_limit: player rank cannot command higher-rank NPC {npc_name}.")

    emperor_terms = ("皇上", "皇帝", "聖上", "陛下")
    passage_terms = ("經過", "路過", "來過", "到場", "出現")
    combined_claims = " ".join([intent] + assumptions)
    if any(term in combined_claims for term in emperor_terms) and any(term in combined_claims for term in passage_terms):
        if not (game_state.get("status", {}) or {}).get("emperor_passed"):
            result["denied_assumptions"].append("皇上已經經過或到場")
            result["constraints"].append("emperor_passage: whether the emperor passed by must be decided by rules, not player wording.")

    result["npc_actions"] = plan_npc_actions(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata)
    for npc_action in result["npc_actions"]:
        effect = npc_action.get("mechanical_effect", {}) if isinstance(npc_action, dict) else {}
        npc_name = npc_action.get("npc") if isinstance(npc_action, dict) else ""
        if npc_name:
            _add_hidden_delta(
                result["state_update"],
                npc_name,
                suspicion=effect.get("suspicion_delta", 0),
                anger=effect.get("anger_delta", 0),
                interest=effect.get("interest_delta", 0),
                trust=effect.get("trust_delta", 0)
            )
            if npc_action.get("action") == "test_player":
                result["state_update"].setdefault("hidden_state_delta", {}).setdefault(npc_name, {})["test_intent"] = False
        result["constraints"].append("npc_action: story must include the provided npc_actions and must not invent actions for dead NPCs.")

    result["world_event"] = plan_world_event(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata)
    merge_state_update(result["state_update"], result["world_event"].get("state_update", {}))
    if result["world_event"].get("type") != "none":
        result["constraints"].append("world_event: story may describe only this provided world_event, not invent another major event.")

    result["state_update"]["turn_count_delta"] = result["state_update"].get("turn_count_delta", 0) + 1

    if not result["allowed"] and not result["reason"]:
        result["reason"] = "Player input conflicts with current authoritative state."
    return result


