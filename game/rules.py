from __future__ import annotations
from game.state import default_state_update, get_rules, get_punishments, get_rewards, get_ranks, _active_summons, clamp_int, ensure_current_objectives
from game.judge import judge_fallback
from game.npc import (
    ensure_hidden_state, _npc_by_name, _rank_level, _is_high_rank_npc,
    _hidden_state_for, _add_hidden_delta, _add_relation_delta, _primary_npc,
    plan_npc_actions,
)
from game.events import plan_world_event
from game.mechanics import evaluate_player_action_costs, update_social_graph_from_turn
from game.schemes import (
    advance_schemes, ensure_scheme_state, expose_scheme_clues, maybe_create_scheme,
    resolve_scheme_by_player_action, scheme_pressure,
)

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
    for key in ("inventory_add", "inventory_remove", "facts_add", "flags_add", "flags_remove", "blocked_choices_add", "blocked_choices_remove", "objective_updates"):
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
        "scheme_events": [],
        "visible_clues": [],
        "scheme_pressure": [],
        "strategic_choices": [],
        "turn_progress": {},
        "world_event": {"type": "none", "description": "", "state_update": {}}
    }
    if not isinstance(judge_result, dict):
        judge_result = judge_fallback()

    relations = ensure_hidden_state(relations, gamedata, game_state, str(judge_result.get("player_intent") or judge_result.get("intent") or ""))
    relations = ensure_scheme_state(relations)
    mentioned_npcs = [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]
    mentioned_items = [str(x) for x in judge_result.get("mentioned_items", []) if str(x).strip()]
    assumptions = [str(x) for x in judge_result.get("assumptions", []) if str(x).strip()]
    action_type = judge_result.get("action_type", "unknown")
    intent = str(judge_result.get("player_intent") or judge_result.get("intent", ""))
    social_tone = judge_result.get("social_tone", "neutral")
    risk_level = judge_result.get("risk_level", "medium")

    status = game_state.get("status", {}) if isinstance(game_state, dict) else {}
    objectives = ensure_current_objectives(status, memory if isinstance(memory, dict) else {})

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

    mechanics = evaluate_player_action_costs(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata)
    merge_state_update(result["state_update"], mechanics.get("state_update", {}))
    result["confirmed_events"].extend(mechanics.get("events", []))
    result["constraints"].extend(mechanics.get("constraints", []))
    if mechanics.get("allowed") is False:
        result["allowed"] = False
        if mechanics.get("reason"):
            result["reason"] = mechanics["reason"]

    if assumptions:
        result["denied_assumptions"].extend(assumptions)
        result["constraints"].append("player_assumptions: do not treat player assumptions as confirmed events.")

    primary = _primary_npc(mentioned_npcs, game_state if isinstance(game_state, dict) else {}, gamedata, relations)
    if primary and action_type in {"ask", "social", "use_item", "observe"}:
        rel_delta = result["state_update"].setdefault("relations_delta", {}).setdefault(primary, {})
        rel_delta["contact_count"] = rel_delta.get("contact_count", 0) + 1
        rel_delta["last_interaction_turn"] = (status or {}).get("turn_count", 0)
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

    scheme_notes = []
    scheme_notes.extend(resolve_scheme_by_player_action(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata))
    scheme_notes.extend(maybe_create_scheme(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata))
    scheme_notes.extend(advance_schemes(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata))
    visible_clues = expose_scheme_clues(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata)
    if scheme_notes or visible_clues:
        result["scheme_events"] = scheme_notes
        result["visible_clues"] = visible_clues
        result["constraints"].append(
            "schemes: narrate only the provided visible clues and pressure; do not name hidden schemes or change their owner, target, or goal."
        )

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
        if npc_action.get("action") == "test_player" or npc_action.get("type") == "test":
            result["state_update"].setdefault("hidden_state_delta", {}).setdefault(npc_name, {})["test_intent"] = False
        result["constraints"].append("npc_action: story must include the provided npc_actions and must not invent actions for dead NPCs.")

    result["world_event"] = plan_world_event(judge_result, game_state if isinstance(game_state, dict) else {}, relations, gamedata)
    merge_state_update(result["state_update"], result["world_event"].get("state_update", {}))
    if result["world_event"].get("type") != "none":
        result["constraints"].append("world_event: story may describe only this provided world_event, not invent another major event.")

    result["turn_progress"] = plan_turn_progress(
        judge_result,
        result,
        game_state if isinstance(game_state, dict) else {},
        objectives,
    )
    result["state_update"]["turn_progress"] = result["turn_progress"]
    merge_state_update(result["state_update"], result["turn_progress"].get("state_update", {}))
    result["strategic_choices"] = plan_strategic_choices(
        judge_result,
        result,
        game_state if isinstance(game_state, dict) else {},
        relations,
        gamedata,
        objectives,
    )
    result["state_update"]["last_turn_type"] = str((judge_result or {}).get("action_type") or "other")

    result["scheme_pressure"] = scheme_pressure(relations)
    update_social_graph_from_turn(relations, judge_result, game_state if isinstance(game_state, dict) else {}, gamedata)
    result["state_update"]["schemes"] = relations.get("schemes", [])
    result["state_update"]["social_graph"] = relations.get("social_graph", {})
    result["state_update"]["turn_count_delta"] = result["state_update"].get("turn_count_delta", 0) + 1

    if not result["allowed"] and not result["reason"]:
        result["reason"] = "Player input conflicts with current authoritative state."
    return result


def _progress_objective_id(objectives: list[dict]) -> str:
    for objective in objectives or []:
        if isinstance(objective, dict) and objective.get("status") == "active":
            return str(objective.get("id") or "")
    return "understand_chengqian_palace"


def _primary_target_name(judge_result: dict, game_state: dict, gamedata: dict, relations: dict | None) -> str:
    return _primary_npc(
        [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()],
        game_state,
        gamedata,
        relations,
    ) or "scene"


def plan_turn_progress(
    judge_result: dict,
    result: dict,
    game_state: dict,
    objectives: list[dict],
) -> dict:
    update = result.get("state_update", {}) if isinstance(result, dict) else {}
    last_types = (game_state.get("status", {}) or {}).get("last_turn_types", [])
    forced = isinstance(last_types, list) and len(last_types) >= 2 and last_types[-2:] == ["observe", "observe"]
    world_event = result.get("world_event", {}) if isinstance(result, dict) else {}
    if isinstance(world_event, dict) and world_event.get("type") not in (None, "", "none"):
        return {"type": "event_trigger", "description": str(world_event.get("description", "小事件推進局勢")), "state_update": {}}
    if result.get("npc_actions"):
        action = result["npc_actions"][0]
        return {"type": "risk_change", "description": str(action.get("description", "NPC主動施壓，局勢變得更緊。")), "state_update": {}}
    if update.get("hidden_state_delta") or update.get("relations_delta"):
        return {"type": "relation_shift", "description": "對話後，場上人物對玩家的態度出現細微變化。", "state_update": {}}
    if update.get("facts_add") or forced:
        return {
            "type": "new_info",
            "description": "玩家得到一條可供後續利用的線索。",
            "state_update": {"facts_add": ["本回合取得一條可供後續利用的線索。"]},
        }
    objective_id = _progress_objective_id(objectives)
    return {
        "type": "objective_update",
        "description": "玩家行動完成，局勢略有推進。",
        "state_update": {"objective_updates": [{"id": objective_id, "progress_delta": 5}]},
    }


def plan_strategic_choices(
    judge_result: dict,
    result: dict,
    game_state: dict,
    relations: dict | None,
    gamedata: dict,
    objectives: list[dict],
) -> list[dict]:
    primary = _primary_target_name(judge_result, game_state, gamedata, relations)
    objective_id = _progress_objective_id(objectives)
    blocked = set((game_state.get("status", {}) or {}).get("blocked_choices", []) or [])
    intent = str(judge_result.get("player_intent") or judge_result.get("intent") or "")
    action_type = str(judge_result.get("action_type") or "other")
    target_label = primary if primary != "scene" else "在場的人"

    def choice(id_: str, text: str, style: str, risk: str, reward: str, hint: str, **effect) -> dict:
        return {
            "id": id_,
            "text": text,
            "style": style,
            "risk": risk,
            "reward": reward,
            "effect_hint": hint,
            "mechanical_effect": {
                "target": primary,
                "trust_delta": effect.get("trust_delta", 0),
                "suspicion_delta": effect.get("suspicion_delta", 0),
                "anger_delta": effect.get("anger_delta", 0),
                "intel_gain": effect.get("intel_gain", 0),
                "reputation_delta": effect.get("reputation_delta", 0),
                "objective_progress_delta": effect.get("objective_progress_delta", 0),
                "objective_id": objective_id,
            },
        }

    if any(word in intent for word in ("紙箋", "字條", "信", "紙條")):
        choices = [
            choice("paper_watch_reaction", f"先不逼問來源，只看{target_label}聽見紙箋二字時的眼神與停頓。", "observe", "low", "low", "安全確認她是否認得紙箋。", suspicion_delta=-1, intel_gain=1, objective_progress_delta=4),
            choice("paper_source_probe", f"把紙箋說成宮人收拾時偶然瞧見，試探{target_label}是否會急著否認。", "probe", "medium", "medium", "可能逼出她是否知情，也可能讓她戒備。", suspicion_delta=2, intel_gain=2, objective_progress_delta=8),
            choice("paper_servant_crosscheck", "轉問旁邊宮人近來誰碰過那類紙箋，不把矛頭直接指向她。", "observe", "medium", "medium", "繞開正面衝突，改查動線。", suspicion_delta=1, intel_gain=2, objective_progress_delta=7),
            choice("paper_direct_pressure", f"直接請{target_label}說明紙箋是否出自她身邊，逼她當場表態。", "pressure", "high", "high", "成功會得到明確立場，失手會傷關係。", trust_delta=-2, suspicion_delta=5, anger_delta=2, intel_gain=3, reputation_delta=-1, objective_progress_delta=12),
        ]
    elif any(word in intent for word in ("點心", "茶", "糕", "吃", "嘗", "招待")):
        choices = [
            choice("food_watch_preference", f"先看{target_label}對點心口味與擺盤的反應，不急著再送話。", "observe", "low", "low", "確認她是真喜歡，還是只給場面話。", suspicion_delta=-1, intel_gain=1, objective_progress_delta=4),
            choice("food_origin_smalltalk", "順著點心來歷閒談一兩句，把話題引到宮中誰愛新鮮物。", "probe", "medium", "medium", "可能問出人脈喜好，也不至於太突兀。", trust_delta=1, suspicion_delta=1, intel_gain=2, objective_progress_delta=8),
            choice("food_offer_favor", f"把剩下的點心留給{target_label}身邊人分用，賣一個不重的人情。", "alliance", "medium", "medium", "有機會增加好感，但會留下示好的痕跡。", trust_delta=2, suspicion_delta=1, anger_delta=-1, intel_gain=1, objective_progress_delta=6),
            choice("food_test_boundary", "故意提到這點心不宜送到主位娘娘面前，觀察誰立刻接話。", "deception", "high", "high", "可能試出承乾宮內忌諱，失手會顯得多心。", suspicion_delta=4, intel_gain=3, reputation_delta=-1, objective_progress_delta=11),
        ]
    elif action_type == "ask":
        choices = [
            choice("ask_narrow_detail", f"把問題縮小到一個細節，請{target_label}只答她親眼見過的部分。", "probe", "medium", "medium", "比大問題更容易得到可判斷答案。", suspicion_delta=1, intel_gain=2, objective_progress_delta=8),
            choice("ask_watch_avoidance", f"暫時不追問，記下{target_label}避開的是人名、時間，還是物件。", "observe", "low", "low", "安全累積線索。", suspicion_delta=-1, intel_gain=1, objective_progress_delta=4),
            choice("ask_trade_minor_truth", "先坦白一件無傷大雅的小事，換對方也說一句實話。", "alliance", "medium", "medium", "可能換到信任，但會暴露一點底牌。", trust_delta=2, suspicion_delta=1, intel_gain=1, objective_progress_delta=6),
            choice("ask_press_contradiction", f"抓住{target_label}前後說法不合處追問，要求她補上缺口。", "pressure", "high", "high", "可能得到明確破口，也可能激怒對方。", trust_delta=-2, suspicion_delta=5, anger_delta=2, intel_gain=3, reputation_delta=-1, objective_progress_delta=12),
        ]
    else:
        choices = [
            choice("scene_read_power", "觀察誰先替誰接話、誰能讓宮人停手，判斷場上話語權。", "observe", "low", "low", "安全補足權力關係線索。", suspicion_delta=-1, intel_gain=1, objective_progress_delta=4),
            choice("soft_probe_relation", f"用一句不指名的家常話試探{target_label}與主位娘娘的距離。", "probe", "medium", "medium", "可能看出她在宮中的站位。", suspicion_delta=2, intel_gain=2, objective_progress_delta=8),
            choice("build_small_favor", f"給{target_label}留一個能接也能退的台階，先換取表面善意。", "alliance", "medium", "medium", "有機會改善關係，但進展較慢。", trust_delta=2, suspicion_delta=1, anger_delta=-1, intel_gain=1, objective_progress_delta=6),
            choice("force_position", f"把問題推到{target_label}必須選邊的位置，逼她露出真實顧忌。", "pressure", "high", "high", "成功會看清立場，失手會讓場面轉冷。", trust_delta=-2, suspicion_delta=5, anger_delta=2, intel_gain=3, reputation_delta=-1, objective_progress_delta=12),
        ]
    return [choice for choice in choices if choice["id"] not in blocked][:4]

