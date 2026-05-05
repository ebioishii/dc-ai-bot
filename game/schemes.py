from __future__ import annotations

from game.mechanics import companion_network_power
from game.npc import get_npc_stats, _hidden_state_for, _is_high_rank_npc, _npc_by_name
from game.state import clamp_int

ACTIVE_STAGES = {"seeded", "developing", "exposed"}
TERMINAL_STAGES = {"resolved", "failed"}
VALID_STAGES = ACTIVE_STAGES | TERMINAL_STAGES

RESOLVE_WORDS = ("揭穿", "告發", "查證", "反制", "設局", "將計就計", "呈報")
SOFTEN_WORDS = ("示好", "安撫", "結盟", "送禮", "賠罪", "請罪")
PROBE_ACTIONS = {"observe", "ask", "social"}


def ensure_scheme_state(relations: dict | None) -> dict:
    relations = relations if isinstance(relations, dict) else {"npcs": {}, "companions": {}}
    relations.setdefault("npcs", {})
    relations.setdefault("companions", {})
    relations.setdefault("social_graph", {})
    raw_schemes = relations.get("schemes", [])
    if not isinstance(raw_schemes, list):
        raw_schemes = []

    normalized = []
    seen_ids = set()
    for index, scheme in enumerate(raw_schemes, 1):
        if not isinstance(scheme, dict):
            continue
        scheme_id = str(scheme.get("id") or f"scheme_{index}").strip()
        if not scheme_id or scheme_id in seen_ids:
            scheme_id = f"scheme_{index}"
        seen_ids.add(scheme_id)
        stage = str(scheme.get("stage") or "seeded")
        if stage not in VALID_STAGES:
            stage = "seeded"
        normalized.append({
            "id": scheme_id,
            "owner": str(scheme.get("owner") or "").strip(),
            "target": str(scheme.get("target") or "玩家").strip(),
            "strategy_id": str(scheme.get("strategy_id") or "yin_she_chu_dong").strip(),
            "goal": str(scheme.get("goal") or "試探玩家的真實意圖").strip(),
            "stage": stage,
            "progress": clamp_int(scheme.get("progress", 0), 0, 100),
            "risk": clamp_int(scheme.get("risk", 0), 0, 100),
            "clues": _unique_strings(scheme.get("clues", []), 8),
            "known_by_player": bool(scheme.get("known_by_player", False)),
            "created_turn": _safe_int(scheme.get("created_turn", 0)),
            "last_advanced_turn": _safe_int(scheme.get("last_advanced_turn", 0)),
        })
    relations["schemes"] = normalized
    return relations


def maybe_create_scheme(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> list[dict]:
    relations = ensure_scheme_state(relations)
    if _active_schemes(relations):
        return []

    owner = _best_scheme_owner(judge_result, game_state, relations, gamedata)
    if not owner:
        return []
    npcs_by_name = _npc_by_name(gamedata)
    npc = npcs_by_name.get(owner, {})
    stats = get_npc_stats(npc)
    if max(_stat(stats, "心機"), _stat(stats, "權謀")) < 60:
        return []

    player_attrs = _player_attrs(game_state)
    hidden = _hidden_state_for(relations, owner)
    rel = (relations.get("npcs", {}) or {}).get(owner, {})
    risk_level = judge_result.get("risk_level", "medium")
    social_tone = judge_result.get("social_tone", "neutral")
    trigger_score = (
        clamp_int(hidden.get("suspicion", 0), 0, 100)
        + clamp_int(hidden.get("anger", 0), 0, 100) // 2
        + clamp_int(hidden.get("interest", 0), 0, 100) // 3
        + max(0, 20 - _stat(player_attrs, "聲望"))
        + max(0, -clamp_int(rel.get("好感度", 0), -100, 100)) // 2
        + _social_grudge(relations, owner) // 2
        + (18 if risk_level == "high" else 0)
        + (14 if social_tone in {"rude", "probing"} else 0)
    )
    if trigger_score < 45:
        return []

    strategy = _select_strategy(stats, player_attrs, hidden, rel, gamedata.get("strategies", []))
    if not strategy:
        return []

    turn = _turn(game_state)
    scheme = {
        "id": _new_scheme_id(relations, turn),
        "owner": owner,
        "target": "玩家",
        "strategy_id": strategy.get("id", "yin_she_chu_dong"),
        "goal": _goal_for_strategy(strategy.get("id", ""), owner),
        "stage": "seeded",
        "progress": 10,
        "risk": max(0, 35 - _stat(player_attrs, "權謀") // 3),
        "clues": [],
        "known_by_player": False,
        "created_turn": turn,
        "last_advanced_turn": turn,
    }
    relations["schemes"].append(scheme)
    return [{
        "type": "scheme_created",
        "npc": owner,
        "visible_effect": f"{owner}沒有立刻表態，卻開始讓旁人留意玩家的一舉一動。"
    }]


def advance_schemes(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> list[dict]:
    relations = ensure_scheme_state(relations)
    notes = []
    turn = _turn(game_state)
    npcs_by_name = _npc_by_name(gamedata)
    player_scheme_resistance = _stat(_player_attrs(game_state), "權謀") + companion_network_power(relations)

    for scheme in _active_schemes(relations):
        owner = scheme["owner"]
        if _is_dead(owner, relations):
            scheme["stage"] = "failed"
            notes.append({"type": "scheme_failed", "npc": owner, "visible_effect": "原本暗中的壓力忽然斷了線。"})
            continue
        if scheme.get("last_advanced_turn") == turn:
            continue
        npc = npcs_by_name.get(owner, {})
        stats = get_npc_stats(npc)
        life_drag = 2 if _stat(stats, "生命") < 80 else 0
        scheme["progress"] = clamp_int(
            scheme.get("progress", 0)
            + 6
            + _stat(stats, "心機") // 20
            + _stat(stats, "聲望") // 30
            - life_drag
            - player_scheme_resistance // 35,
            0,
            100,
        )
        if player_scheme_resistance >= _stat(stats, "心機"):
            scheme["risk"] = clamp_int(scheme.get("risk", 0) + 6, 0, 100)
        if scheme["stage"] == "seeded" and scheme["progress"] >= 25:
            scheme["stage"] = "developing"
        if scheme["risk"] >= 65 and scheme["stage"] != "exposed":
            scheme["stage"] = "exposed"
            scheme["known_by_player"] = True
        scheme["last_advanced_turn"] = turn
        notes.append({
            "type": "scheme_advanced",
            "npc": owner,
            "visible_effect": _pressure_line(scheme)
        })
    return notes


def expose_scheme_clues(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> list[dict]:
    relations = ensure_scheme_state(relations)
    visible = []
    action_type = judge_result.get("action_type", "unknown")
    intent = str(judge_result.get("player_intent") or judge_result.get("intent") or "")
    player_attrs = _player_attrs(game_state)
    player_intrigue = _stat(player_attrs, "權謀") + companion_network_power(relations)
    npcs_by_name = _npc_by_name(gamedata)

    for scheme in _active_schemes(relations):
        owner = scheme["owner"]
        npc_stats = get_npc_stats(npcs_by_name.get(owner, {}))
        exposure_score = player_intrigue + len(scheme.get("clues", [])) * 8
        if action_type in PROBE_ACTIONS or any(word in intent for word in RESOLVE_WORDS):
            exposure_score += 18
        if exposure_score < _stat(npc_stats, "心機") + 15 and scheme["stage"] != "exposed":
            continue
        clue = _clue_for_scheme(scheme)
        if clue not in scheme["clues"]:
            scheme["clues"].append(clue)
        if exposure_score >= _stat(npc_stats, "心機") + 35:
            scheme["known_by_player"] = True
            scheme["stage"] = "exposed"
        visible.append({"npc": owner if scheme.get("known_by_player") else "", "clue": clue})
    return visible


def resolve_scheme_by_player_action(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> list[dict]:
    relations = ensure_scheme_state(relations)
    intent = str(judge_result.get("player_intent") or judge_result.get("intent") or "")
    if not intent:
        return []

    notes = []
    player_attrs = _player_attrs(game_state)
    player_intrigue = _stat(player_attrs, "權謀") + companion_network_power(relations)
    player_wealth = _stat(player_attrs, "財產")
    npcs_by_name = _npc_by_name(gamedata)
    mentioned = {str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()}
    wants_counter = any(word in intent for word in RESOLVE_WORDS)
    wants_soften = any(word in intent for word in SOFTEN_WORDS)
    if not wants_counter and not wants_soften:
        return []

    for scheme in _active_schemes(relations):
        owner = scheme["owner"]
        if mentioned and owner not in mentioned:
            continue
        owner_intrigue = _stat(get_npc_stats(npcs_by_name.get(owner, {})), "心機")
        if wants_counter:
            if scheme.get("known_by_player") or player_intrigue + 20 >= owner_intrigue:
                scheme["stage"] = "failed"
                scheme["known_by_player"] = True
                clue = f"{owner}先前布下的局露出破綻，已難照原意推進。"
                scheme["clues"] = _unique_strings(scheme.get("clues", []) + [clue], 8)
                notes.append({"type": "scheme_failed", "npc": owner, "visible_effect": clue})
            else:
                scheme["stage"] = "exposed"
                scheme["known_by_player"] = True
                clue = f"你察覺有人借旁人的口風試探你，但尚未完全抓住證據。"
                scheme["clues"] = _unique_strings(scheme.get("clues", []) + [clue], 8)
                notes.append({"type": "scheme_exposed", "npc": owner, "visible_effect": clue})
        elif wants_soften:
            scheme["risk"] = clamp_int(scheme.get("risk", 0) + 12 + min(10, player_wealth // 200), 0, 100)
            if scheme.get("known_by_player") and player_intrigue >= owner_intrigue - 10:
                scheme["stage"] = "resolved"
                clue = f"{owner}暫且收住暗線，局勢被你壓回桌面之上。"
                scheme["clues"] = _unique_strings(scheme.get("clues", []) + [clue], 8)
                notes.append({"type": "scheme_resolved", "npc": owner, "visible_effect": clue})
    return notes


def scheme_pressure(relations: dict | None) -> list[dict]:
    relations = ensure_scheme_state(relations)
    pressure = []
    for scheme in _active_schemes(relations):
        visible_clues = scheme.get("clues", [])[-2:] if scheme.get("known_by_player") or scheme.get("stage") == "exposed" else []
        pressure.append({
            "npc": scheme["owner"] if scheme.get("known_by_player") else "",
            "stage": scheme["stage"],
            "visible_clues": visible_clues,
            "pressure": _pressure_line(scheme),
        })
    return pressure


def _active_schemes(relations: dict) -> list[dict]:
    return [scheme for scheme in relations.get("schemes", []) if scheme.get("stage") in ACTIVE_STAGES]


def _best_scheme_owner(judge_result: dict, game_state: dict, relations: dict, gamedata: dict) -> str | None:
    npcs_by_name = _npc_by_name(gamedata)
    candidates = []
    seen = set()
    mentioned = [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]
    scene = [str(x) for x in (game_state or {}).get("scene_npcs", []) if str(x).strip()]
    for name in mentioned + scene + list(npcs_by_name.keys()):
        if name in npcs_by_name and name not in seen and not _is_dead(name, relations):
            seen.add(name)
            npc = npcs_by_name[name]
            stats = get_npc_stats(npc)
            hidden = _hidden_state_for(relations, name)
            score = _stat(stats, "心機") + _stat(stats, "權謀") + clamp_int(hidden.get("suspicion", 0), 0, 100)
            if _is_high_rank_npc(npc, gamedata):
                score += 20
            candidates.append((score, name))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def _select_strategy(npc_stats: dict, player_attrs: dict, hidden: dict, rel: dict, strategies: list[dict]) -> dict | None:
    available = [s for s in strategies if _meets_requirements(npc_stats, s.get("stat_requirement", {}))]
    by_id = {s.get("id"): s for s in available}
    affection = clamp_int(rel.get("好感度", 0), -100, 100)
    suspicion = clamp_int(hidden.get("suspicion", 0), 0, 100)
    player_reputation = _stat(player_attrs, "聲望")
    interest = clamp_int(hidden.get("interest", 0), 0, 100)
    if affection < -20 and "jie_dao_sha_ren" in by_id:
        return by_id["jie_dao_sha_ren"]
    if suspicion >= 65 and "yin_she_chu_dong" in by_id:
        return by_id["yin_she_chu_dong"]
    if player_reputation < 20 and "li_jian_ji" in by_id:
        return by_id["li_jian_ji"]
    if interest >= 60 and affection >= 0 and "tong_meng" in by_id:
        return by_id["tong_meng"]
    if _stat(player_attrs, "財產") > 200 and "tao_ren_xin" in by_id:
        return by_id["tao_ren_xin"]
    if "yin_she_chu_dong" in by_id:
        return by_id["yin_she_chu_dong"]
    return available[0] if available else None


def _meets_requirements(stats: dict, requirements: dict) -> bool:
    if not isinstance(requirements, dict):
        return True
    return all(_stat(stats, key) >= clamp_int(value, 0, 1000) for key, value in requirements.items())


def _goal_for_strategy(strategy_id: str, owner: str) -> str:
    goals = {
        "li_jian_ji": f"{owner}想削弱玩家在後宮中的信任與依附",
        "yin_she_chu_dong": f"{owner}想試探玩家是否藏有野心或把柄",
        "jie_dao_sha_ren": f"{owner}想借他人之手壓制玩家",
        "xia_ma_wei": f"{owner}想壓低玩家聲勢，使其不敢越位",
        "tao_ren_xin": f"{owner}想收買玩家身邊的人取得消息",
        "tong_meng": f"{owner}想判斷玩家是否能成為可用棋子",
    }
    return goals.get(strategy_id, f"{owner}正在暗中試探玩家的立場")


def _clue_for_scheme(scheme: dict) -> str:
    strategy_id = scheme.get("strategy_id")
    if strategy_id == "li_jian_ji":
        return "兩名宮人說起同一件事時，細節竟像被人刻意改過。"
    if strategy_id == "jie_dao_sha_ren":
        return "有人把責任推向你身邊的人，卻避開了真正下令者。"
    if strategy_id == "tao_ren_xin":
        return "你身邊的小人物忽然得了不合身分的好處。"
    if strategy_id == "xia_ma_wei":
        return "原本中立的下人忽然變得畏縮，像是被提前敲打過。"
    return "一段看似偶然的問話前後呼應，像是在試你的口風。"


def _social_grudge(relations: dict, owner: str) -> int:
    edge = ((relations.get("social_graph", {}) or {}).get(owner, {}) or {}).get("玩家", {})
    return clamp_int(edge.get("grudge", 0), 0, 100) if isinstance(edge, dict) else 0


def _pressure_line(scheme: dict) -> str:
    if scheme.get("stage") == "exposed":
        return "暗處的佈置露出邊角，玩家可從異常口風中追查。"
    if scheme.get("stage") == "developing":
        return "宮中人際壓力正在累積，某些話開始繞著玩家流動。"
    return "有人已在暗處落下第一枚棋子，但表面仍風平浪靜。"


def _new_scheme_id(relations: dict, turn: int) -> str:
    used = {scheme.get("id") for scheme in relations.get("schemes", [])}
    index = len(used) + 1
    scheme_id = f"scheme_{turn}_{index}"
    while scheme_id in used:
        index += 1
        scheme_id = f"scheme_{turn}_{index}"
    return scheme_id


def _player_attrs(game_state: dict | None) -> dict:
    status = (game_state or {}).get("status", {}) if isinstance(game_state, dict) else {}
    attrs = status.get("attributes", {}) if isinstance(status, dict) else {}
    return attrs if isinstance(attrs, dict) else {}


def _stat(stats: dict, key: str) -> int:
    return clamp_int((stats or {}).get(key, 0), -1000, 1000)


def _turn(game_state: dict | None) -> int:
    status = (game_state or {}).get("status", {}) if isinstance(game_state, dict) else {}
    return _safe_int((status or {}).get("turn_count", 0))


def _safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _is_dead(name: str, relations: dict) -> bool:
    return (relations.get("npcs", {}) or {}).get(name, {}).get("alive") is False


def _unique_strings(values, limit: int) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        text = str(value).strip()
        if text and text not in result:
            result.append(text[:160])
    return result[-limit:]
