from __future__ import annotations
import os
import json

_GAMEDATA_CACHE: dict = {}


def _cached_json(key: str, path: str, extract=None):
    if key not in _GAMEDATA_CACHE:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _GAMEDATA_CACHE[key] = extract(data) if extract else data
    return _GAMEDATA_CACHE[key]


def default_hidden_state_for_npc(npc_name: str, npc: dict | None = None, relation: dict | None = None) -> dict:
    from game.npc import default_hidden_state_for_npc as _impl
    return _impl(npc_name, npc, relation)

def get_script(category, key):
    data = _cached_json("scripts", "gamedata/scripts.json")
    return data[category][key]


def get_player_folder(user_id):
    folder = f'players/{user_id}'
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder


def save_player_data(user_id, data_type, data):
    folder = get_player_folder(user_id)
    with open(f'{folder}/{data_type}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_player_data(user_id, data_type):
    path = f'players/{user_id}/{data_type}.json'
    return json.load(open(path, 'r', encoding='utf-8')) if os.path.exists(path) else None


def player_exists(user_id):
    return os.path.exists(f'players/{user_id}/profile.json')


def load_player_profile(user_id):
    return load_player_data(user_id, 'profile')


def load_player_status(user_id):
    return load_player_data(user_id, 'status')


def load_player_memory(user_id):
    return load_player_data(user_id, 'memory')


def load_player_inventory(user_id):
    return load_player_data(user_id, 'inventory')


def load_player_relations(user_id):
    return load_player_data(user_id, 'relations')


PLAYER_FILE_META = {
    "profile": {
        "schema_version": 2,
        "role": "static_player_identity",
        "authority": "出生與角色基礎設定；不記錄當前場景、目標、物品或 NPC 關係",
    },
    "status": {
        "schema_version": 2,
        "role": "authoritative_player_state",
        "authority": "玩家當前狀態、位置、目標、旗標與每回合推進；memory 只能摘要，不可覆蓋本檔",
    },
    "relations": {
        "schema_version": 2,
        "role": "authoritative_npc_relations",
        "authority": "NPC 關係、hidden_state、social_graph、schemes 與正式 companions；未實際接觸的 NPC 不應產生 scheme",
    },
    "inventory": {
        "schema_version": 2,
        "role": "authoritative_inventory",
        "authority": "玩家持有物品的唯一權威來源；Story Writer 敘事贈物必須由 rule/state update 寫入本檔才算成立",
    },
    "memory": {
        "schema_version": 2,
        "role": "non_authoritative_ai_memory",
        "authority": "只提供 Story Writer/Judge 的摘要上下文；不得作為位置、目標、物品、關係或 hidden_state 的最終來源",
        "authoritative_sources": {
            "scene_state": "status.json",
            "current_objectives": "status.json",
            "npc_relations": "relations.json",
            "inventory": "inventory.json",
        },
    },
}


def ensure_record_meta(data: dict | None, data_type: str) -> dict:
    data = dict(data or {})
    meta = dict(data.get("_meta") or {})
    meta.update(PLAYER_FILE_META.get(data_type, {}))
    if meta:
        data["_meta"] = meta
    return data


def objective_summary_from_status(status: dict | None) -> list[str]:
    objectives = (status or {}).get("current_objectives", [])
    if not isinstance(objectives, list):
        return []
    lines = []
    for item in objectives:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "completed":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(text[:160])
    return lines[:6]


def normalize_memory_record(memory: dict | None, status: dict | None = None) -> dict:
    memory = ensure_record_meta(memory or {}, "memory")
    memory.setdefault("long_term_summary", "")
    memory.setdefault("short_term", [])
    memory.setdefault("fact_sheet", "")
    memory.setdefault("fact_sheet_items", [])
    memory.setdefault("scene_summary", "")
    memory.setdefault("summary_turns_since_update", 0)
    if not isinstance(memory.get("short_term"), list):
        memory["short_term"] = []
    if not isinstance(memory.get("fact_sheet_items"), list):
        memory["fact_sheet_items"] = []
    if isinstance(status, dict):
        summary = objective_summary_from_status(status)
        if summary:
            memory["objective_summary"] = summary
    memory.pop("scene_state", None)
    memory.pop("current_objectives", None)
    memory.pop("last_choices", None)
    memory.pop("last_hints", None)
    return memory


def normalize_inventory_record(inventory: dict | None) -> dict:
    inventory = ensure_record_meta(inventory or {}, "inventory")
    items = inventory.setdefault("items", [])
    if not isinstance(items, list):
        items = []
    clean_items = []
    for item in items:
        text = str(item).strip()
        if text and text not in clean_items:
            clean_items.append(text)
    inventory["items"] = clean_items
    details = inventory.setdefault("item_details", {})
    if not isinstance(details, dict):
        details = {}
    for item in clean_items:
        details.setdefault(item, {"source": "unknown", "category": "item", "known_by": ["玩家"]})
    inventory["item_details"] = details
    return inventory


def normalize_relations_record(relations: dict | None) -> dict:
    relations = ensure_record_meta(relations or {}, "relations")
    relations.setdefault("npcs", {})
    relations.setdefault("hidden_state", {})
    relations.setdefault("social_graph", {})
    relations.setdefault("companions", {})
    relations.setdefault("schemes", [])
    if not isinstance(relations.get("companions"), dict):
        relations["companions"] = {}
    if not isinstance(relations.get("schemes"), list):
        relations["schemes"] = []
    return relations


def normalize_status_record(status: dict | None) -> dict:
    status = ensure_record_meta(status or {}, "status")
    status.setdefault("alive", True)
    status.setdefault("flags", [])
    status.setdefault("blocked_choices", [])
    status.setdefault("last_hints", [])
    status.pop("last_choices", None)
    if not isinstance(status.get("last_hints"), list):
        status["last_hints"] = []
    status.setdefault("turn_count", 0)
    ensure_current_objectives(status, None)
    if isinstance(status.get("scene_state"), dict):
        scene_state = dict(status["scene_state"])
        scene_state["_authority"] = "status.scene_state 是目前場景唯一權威副本；memory 若有場景文字只能視為摘要"
        status["scene_state"] = scene_state
    return status


def normalize_profile_record(profile: dict | None) -> dict:
    return ensure_record_meta(profile or {}, "profile")


def normalize_player_records(user_id) -> dict:
    profile = normalize_profile_record(load_player_profile(user_id) or {})
    status = normalize_status_record(load_player_status(user_id) or {})
    relations = normalize_relations_record(load_player_relations(user_id) or {})
    inventory = normalize_inventory_record(load_player_inventory(user_id) or {})
    memory = normalize_memory_record(load_player_memory(user_id) or {}, status)
    if profile:
        save_player_data(user_id, "profile", profile)
    save_player_data(user_id, "status", status)
    save_player_data(user_id, "relations", relations)
    save_player_data(user_id, "inventory", inventory)
    save_player_data(user_id, "memory", memory)
    return {
        "profile": profile,
        "status": status,
        "relations": relations,
        "inventory": inventory,
        "memory": memory,
    }


def get_families():
    return _cached_json("families", "gamedata/families.json", lambda d: d["families"])


def get_ranks():
    return _cached_json("ranks", "gamedata/ranks.json", lambda d: d["ranks"])


def get_rules():
    return _cached_json("rules", "gamedata/rules.json")


def get_punishments():
    return _cached_json("punishments", "gamedata/punishments.json", lambda d: d["punishments"])


def get_rewards():
    return _cached_json("rewards", "gamedata/rewards.json", lambda d: d["rewards"])


def get_locations():
    return _cached_json("locations", "gamedata/locations.json", lambda d: d["locations"])


def get_npcs():
    return _cached_json("npcs", "gamedata/npcs.json", lambda d: d["npcs"])


def get_strategies():
    return _cached_json("strategies", "gamedata/strategies.json", lambda d: d.get("strategies", []))


def _load_gamedata_bundle() -> dict:
    return {
        "npcs": get_npcs(),
        "ranks": get_ranks(),
        "rules": get_rules(),
        "locations": get_locations(),
        "strategies": get_strategies()
    }


def _active_summons(game_state: dict) -> list:
    status = game_state.get("status", {}) if isinstance(game_state, dict) else {}
    summons = status.get("summons") or status.get("summon") or game_state.get("summons")
    if isinstance(summons, dict):
        if summons.get("active") is True:
            return [summons]
        return [value for value in summons.values() if isinstance(value, dict) and value.get("active") is True]
    if isinstance(summons, list):
        return [item for item in summons if isinstance(item, dict) and item.get("active") is True]
    return []


def default_state_update() -> dict:
    return {
        "location": None,
        "alive": None,
        "attributes_delta": {},
        "inventory_add": [],
        "inventory_remove": [],
        "relations_delta": {},
        "hidden_state_delta": {},
        "flags_add": [],
        "flags_remove": [],
        "reputation_delta": 0,
        "blocked_choices_add": [],
        "blocked_choices_remove": [],
        "facts_add": [],
        "status_set": {},
        "objective_updates": [],
        "turn_count_delta": 0
    }


DEFAULT_CURRENT_OBJECTIVES = [
    {
        "id": "understand_chengqian_palace",
        "text": "了解承乾宮內權力結構",
        "status": "active",
        "progress": 0,
    },
    {
        "id": "judge_lu_changzai",
        "text": "判斷陸常在是否可信",
        "status": "active",
        "progress": 0,
    },
]


def default_current_objectives() -> list[dict]:
    return [dict(item) for item in DEFAULT_CURRENT_OBJECTIVES]


def ensure_current_objectives(status: dict | None = None, memory: dict | None = None) -> list[dict]:
    carrier = status if isinstance(status, dict) else memory if isinstance(memory, dict) else {}
    objectives = carrier.get("current_objectives")
    if not isinstance(objectives, list) or not objectives:
        objectives = default_current_objectives()
        if isinstance(status, dict):
            status["current_objectives"] = [dict(item) for item in objectives]
        if isinstance(memory, dict):
            memory["objective_summary"] = objective_summary_from_status({"current_objectives": objectives})
        return objectives
    cleaned = []
    for item in objectives:
        if not isinstance(item, dict):
            continue
        objective = {
            "id": str(item.get("id") or "").strip()[:80],
            "text": str(item.get("text") or "").strip()[:160],
            "status": str(item.get("status") or "active"),
            "progress": clamp_int(item.get("progress", 0), 0, 100),
        }
        if objective["id"] and objective["text"]:
            cleaned.append(objective)
    if not cleaned:
        cleaned = default_current_objectives()
    if isinstance(status, dict):
        status["current_objectives"] = [dict(item) for item in cleaned]
    if isinstance(memory, dict):
        memory["objective_summary"] = objective_summary_from_status({"current_objectives": cleaned})
        memory.pop("current_objectives", None)
    return cleaned


def apply_objective_updates(objectives: list[dict], updates: list) -> list[dict]:
    objectives = [dict(item) for item in objectives if isinstance(item, dict)]
    by_id = {item.get("id"): item for item in objectives if item.get("id")}
    for update in updates or []:
        if not isinstance(update, dict):
            continue
        oid = str(update.get("id") or "").strip()
        if not oid:
            continue
        objective = by_id.get(oid)
        if objective is None:
            text = str(update.get("text") or "").strip()
            if not text:
                continue
            objective = {"id": oid[:80], "text": text[:160], "status": "active", "progress": 0}
            objectives.append(objective)
            by_id[oid] = objective
        if update.get("text"):
            objective["text"] = str(update["text"])[:160]
        if update.get("status"):
            objective["status"] = str(update["status"])
        if "progress" in update:
            objective["progress"] = clamp_int(update.get("progress"), 0, 100, objective.get("progress", 0))
        if "progress_delta" in update:
            objective["progress"] = clamp_int(
                objective.get("progress", 0) + int(update.get("progress_delta", 0) or 0),
                0,
                100,
                objective.get("progress", 0),
            )
        if objective.get("progress", 0) >= 100 and objective.get("status") == "active":
            objective["status"] = "completed"
    return objectives


def normalize_ai_payload(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    reply = data.get('reply') or data.get('narration') or data.get('text')
    if not isinstance(reply, str) or not reply.strip():
        return None
    update = data.get('state_update') if isinstance(data.get('state_update'), dict) else {}
    base = default_state_update()
    base.update(update)
    data['reply'] = reply.strip()
    data['state_update'] = base
    return data


def clamp_int(value, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(value)))
    except Exception:
        return default


def clamp_attribute(attr: str, value, current: int = 0) -> int:
    try:
        from game.mechanics import attribute_bounds
        low, high = attribute_bounds(attr, current)
    except Exception:
        low, high = (0, 100)
    return clamp_int(value, low, high, current)


def apply_state_update(user_id, update: dict):
    """把模型輸出的 state_update 寫回玩家 JSON 檔。"""
    if not isinstance(update, dict):
        return
    status = normalize_status_record(load_player_status(user_id) or {})
    inventory = normalize_inventory_record(load_player_inventory(user_id) or {"items": []})
    relations = normalize_relations_record(load_player_relations(user_id) or {"npcs": {}, "companions": {}})
    memory = normalize_memory_record(load_player_memory(user_id) or {
        "long_term_summary": "",
        "short_term": [],
        "fact_sheet": "",
        "fact_sheet_items": [],
        "scene_summary": "",
        "summary_turns_since_update": 0,
    }, status)
    objectives = ensure_current_objectives(status, memory)
    try:
        from game.schemes import ensure_scheme_state
        relations = ensure_scheme_state(relations)
    except Exception:
        relations.setdefault("schemes", [])

    if update.get("location"):
        status["location"] = str(update["location"])
    if update.get("alive") is not None:
        status["alive"] = bool(update["alive"])
    for key, value in (update.get("status_set") or {}).items():
        if isinstance(key, str) and key:
            status[key] = value
    if update.get("turn_count_delta"):
        try:
            status["turn_count"] = max(0, int(status.get("turn_count", 0) or 0) + int(update.get("turn_count_delta", 0)))
        except Exception:
            pass

    attrs = status.setdefault("attributes", {})
    for attr, delta in (update.get("attributes_delta") or {}).items():
        try:
            current = attrs.get(attr, 0)
            attrs[attr] = clamp_attribute(attr, current + int(delta), current)
        except Exception:
            pass
    if update.get("reputation_delta"):
        try:
            current = attrs.get("聲望", 0)
            attrs["聲望"] = clamp_attribute("聲望", current + int(update.get("reputation_delta", 0)), current)
        except Exception:
            pass

    flags = status.setdefault("flags", [])
    for flag in update.get("flags_add") or []:
        flag = str(flag).strip()
        if flag and flag not in flags:
            flags.append(flag)
    for flag in update.get("flags_remove") or []:
        flag = str(flag).strip()
        if flag in flags:
            flags.remove(flag)

    blocked = status.setdefault("blocked_choices", [])
    for choice_key in update.get("blocked_choices_add") or []:
        choice_key = str(choice_key).strip()
        if choice_key and choice_key not in blocked:
            blocked.append(choice_key)
    for choice_key in update.get("blocked_choices_remove") or []:
        choice_key = str(choice_key).strip()
        if choice_key in blocked:
            blocked.remove(choice_key)

    if update.get("last_turn_type"):
        last_turn_types = status.setdefault("last_turn_types", [])
        if isinstance(last_turn_types, list):
            last_turn_types.append(str(update.get("last_turn_type")))
            status["last_turn_types"] = last_turn_types[-3:]

    if isinstance(update.get("turn_progress"), dict):
        status["last_turn_progress"] = update["turn_progress"]

    items = inventory.setdefault("items", [])
    for item in update.get("inventory_add") or []:
        item = str(item).strip()
        if item and item not in items:
            items.append(item)
    for item in update.get("inventory_remove") or []:
        item = str(item).strip()
        if item in items:
            items.remove(item)

    rel_npcs = relations.setdefault("npcs", {})
    for npc, delta_data in (update.get("relations_delta") or {}).items():
        if not isinstance(delta_data, dict):
            continue
        npc_data = rel_npcs.setdefault(npc, {"好感度": 0, "恩怨": "無", "emotion_state": {"anger": 0, "fear": 0}, "alive": True})
        if "好感度" not in npc_data and "憟賣?摨?" in npc_data:
            npc_data["好感度"] = npc_data.pop("憟賣?摨?", 0)
        if "恩怨" not in npc_data and "?拇?" in npc_data:
            npc_data["恩怨"] = npc_data.pop("?拇?", "無")
        if "好感度" not in delta_data and "憟賣?摨?" in delta_data:
            delta_data["好感度"] = delta_data.get("憟賣?摨?", 0)
        if "恩怨" not in delta_data and "?拇?" in delta_data:
            delta_data["恩怨"] = delta_data.get("?拇?")
        if "好感度" in delta_data:
            try:
                npc_data["好感度"] = clamp_int(npc_data.get("好感度", 0) + int(delta_data["好感度"]), -100, 100)
            except Exception:
                pass
        if "恩怨" in delta_data and delta_data["恩怨"]:
            npc_data["恩怨"] = str(delta_data["恩怨"])[:120]
        emotion = npc_data.setdefault("emotion_state", {"anger": 0, "fear": 0})
        if "anger" in delta_data:
            try:
                emotion["anger"] = clamp_int(emotion.get("anger", 0) + int(delta_data["anger"]), 0, 100)
            except Exception:
                pass
        if "fear" in delta_data:
            try:
                emotion["fear"] = clamp_int(emotion.get("fear", 0) + int(delta_data["fear"]), 0, 100)
            except Exception:
                pass
        if "alive" in delta_data:
            npc_data["alive"] = bool(delta_data["alive"])
            if npc_data["alive"] is False and npc_data.get("恩怨", "無") == "無":
                npc_data["恩怨"] = "已死亡"
        if "contact_count" in delta_data:
            try:
                npc_data["contact_count"] = max(0, int(npc_data.get("contact_count", 0) or 0) + int(delta_data["contact_count"]))
            except Exception:
                pass
        if "last_interaction_turn" in delta_data:
            try:
                npc_data["last_interaction_turn"] = max(int(npc_data.get("last_interaction_turn", 0) or 0), int(delta_data["last_interaction_turn"]))
            except Exception:
                pass

    hidden_state = relations.setdefault("hidden_state", {})
    for npc, delta_data in (update.get("hidden_state_delta") or {}).items():
        if not isinstance(delta_data, dict):
            continue
        npc_hidden = hidden_state.setdefault(npc, default_hidden_state_for_npc(npc, None, rel_npcs.get(npc, {})))
        for key in ("suspicion", "interest", "anger", "threat"):
            if key in delta_data:
                try:
                    npc_hidden[key] = clamp_int(npc_hidden.get(key, 0) + int(delta_data[key]), 0, 100)
                except Exception:
                    pass
        if "trust" in delta_data:
            try:
                npc_hidden["trust"] = clamp_int(npc_hidden.get("trust", 0) + int(delta_data["trust"]), -100, 100)
            except Exception:
                pass
        if "test_intent" in delta_data:
            npc_hidden["test_intent"] = bool(delta_data["test_intent"])
        if isinstance(delta_data.get("intel_known_add"), list):
            intel = npc_hidden.setdefault("intel_known", [])
            for item in delta_data.get("intel_known_add") or []:
                text = str(item).strip()
                if text and text not in intel:
                    intel.append(text[:120])
            npc_hidden["intel_known"] = intel[-20:]

    if isinstance(update.get("objective_updates"), list):
        objectives = apply_objective_updates(objectives, update.get("objective_updates"))
        status["current_objectives"] = [dict(item) for item in objectives]
        memory["objective_summary"] = objective_summary_from_status(status)
        memory.pop("current_objectives", None)

    if isinstance(update.get("schemes"), list):
        relations["schemes"] = update["schemes"]
        try:
            from game.schemes import ensure_scheme_state
            relations = ensure_scheme_state(relations)
        except Exception:
            pass
    if isinstance(update.get("social_graph"), dict):
        relations["social_graph"] = update["social_graph"]

    facts = update.get("facts_add") or []
    if facts:
        fact_items = memory.setdefault("fact_sheet_items", [])
        for fact in facts:
            fact = str(fact).strip()
            if fact:
                fact_items.append(f"[劇情事實] {fact[:120]}")
        memory["fact_sheet_items"] = fact_items[-10:]
        memory["fact_sheet"] = "\n".join(memory["fact_sheet_items"])

    save_player_data(user_id, "status", normalize_status_record(status))
    save_player_data(user_id, "inventory", normalize_inventory_record(inventory))
    save_player_data(user_id, "relations", normalize_relations_record(relations))
    save_player_data(user_id, "memory", normalize_memory_record(memory, status))


