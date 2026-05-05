from __future__ import annotations
import os
import json

def default_hidden_state_for_npc(npc_name: str, npc: dict | None = None, relation: dict | None = None) -> dict:
    from game.npc import default_hidden_state_for_npc as _impl
    return _impl(npc_name, npc, relation)

def get_script(category, key):
    with open('gamedata/scripts.json', 'r', encoding='utf-8') as f:
        return json.load(f)[category][key]


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


def get_families():
    with open('gamedata/families.json', 'r', encoding='utf-8') as f:
        return json.load(f)['families']


def get_ranks():
    with open('gamedata/ranks.json', 'r', encoding='utf-8') as f:
        return json.load(f)['ranks']


def get_rules():
    with open('gamedata/rules.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def get_punishments():
    with open('gamedata/punishments.json', 'r', encoding='utf-8') as f:
        return json.load(f)['punishments']


def get_rewards():
    with open('gamedata/rewards.json', 'r', encoding='utf-8') as f:
        return json.load(f)['rewards']


def get_locations():
    with open('gamedata/locations.json', 'r', encoding='utf-8') as f:
        return json.load(f)['locations']


def get_npcs():
    with open('gamedata/npcs.json', 'r', encoding='utf-8') as f:
        return json.load(f)['npcs']


def get_strategies():
    with open('gamedata/strategies.json', 'r', encoding='utf-8') as f:
        return json.load(f).get('strategies', [])


def _load_gamedata_bundle() -> dict:
    return {
        "npcs": get_npcs(),
        "ranks": get_ranks(),
        "rules": get_rules(),
        "locations": get_locations()
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
        "facts_add": [],
        "status_set": {},
        "turn_count_delta": 0
    }


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


def apply_state_update(user_id, update: dict):
    """把模型輸出的 state_update 寫回玩家 JSON 檔。"""
    if not isinstance(update, dict):
        return
    status = load_player_status(user_id) or {}
    inventory = load_player_inventory(user_id) or {"items": []}
    relations = load_player_relations(user_id) or {"npcs": {}, "companions": {}}
    memory = load_player_memory(user_id) or {"long_term_summary": "", "short_term": [], "fact_sheet": "", "fact_sheet_items": []}

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
            attrs[attr] = clamp_int(attrs.get(attr, 0) + int(delta), 0, 100, attrs.get(attr, 0))
        except Exception:
            pass
    if update.get("reputation_delta"):
        try:
            attrs["聲望"] = clamp_int(attrs.get("聲望", 0) + int(update.get("reputation_delta", 0)), -100, 100, attrs.get("聲望", 0))
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

    hidden_state = relations.setdefault("hidden_state", {})
    for npc, delta_data in (update.get("hidden_state_delta") or {}).items():
        if not isinstance(delta_data, dict):
            continue
        npc_hidden = hidden_state.setdefault(npc, default_hidden_state_for_npc(npc, None, rel_npcs.get(npc, {})))
        for key in ("suspicion", "interest", "anger"):
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

    facts = update.get("facts_add") or []
    if facts:
        fact_items = memory.setdefault("fact_sheet_items", [])
        for fact in facts:
            fact = str(fact).strip()
            if fact:
                fact_items.append(f"[劇情事實] {fact[:120]}")
        memory["fact_sheet_items"] = fact_items[-10:]
        memory["fact_sheet"] = "\n".join(memory["fact_sheet_items"])

    save_player_data(user_id, "status", status)
    save_player_data(user_id, "inventory", inventory)
    save_player_data(user_id, "relations", relations)
    save_player_data(user_id, "memory", memory)


