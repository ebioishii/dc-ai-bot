from __future__ import annotations
import re

from game.state import get_npcs, load_player_relations, save_player_data, clamp_int

ANGER_THRESHOLD = 70
FEAR_THRESHOLD = 70
INSULT_KEYWORDS = ['??', '?', '??', '?', '??', '?', '?', '?', '?']
AFFECTION_POSITIVE_KEYWORDS = ['??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
AFFECTION_NEGATIVE_KEYWORDS = ['??', '??', '??', '??', '??', '??', '??', '??', '??']
COMPANION_ROLES = ['宮女', '太監', '嬤嬤', '姑姑', '侍女', '隨侍', '小太監', '丫鬟']
HIGH_RANK_NPC_LEVEL = 7

def get_npc_stats(npc: dict | None) -> dict:
    """Return the canonical NPC stat block, accepting older `stats` data too."""
    if not isinstance(npc, dict):
        return {}
    stats = npc.get("base_stats")
    if isinstance(stats, dict):
        return stats
    stats = npc.get("stats")
    return stats if isinstance(stats, dict) else {}


def _format_npc_prompt_block(npc: dict) -> str:
    npc_info = f"【{npc['name']}】{npc.get('title', '')}\n"
    npc_info += f"  位置：{npc.get('location', '未知')}\n"
    npc_info += f"  位階：{npc.get('rank', '未知')}\n"
    desc = str(npc.get("description", "")).strip()
    if desc:
        npc_info += f"  描述：{desc[:120]}\n"
    npc_info += f"  性格：{npc.get('personality', '無')}\n"
    stats = get_npc_stats(npc)
    if stats:
        stats_str = "、".join(f"{k}:{v}" for k, v in stats.items())
        npc_info += f"  能力值：{stats_str}\n"
    hidden = npc.get('hidden', {})
    if hidden.get('hidden_agenda'):
        agenda = hidden['hidden_agenda'][:100]
        npc_info += f"  潛在意圖：{agenda}...\n"
    return npc_info + "\n"

def format_npc_data():
    """將 NPC 資料格式化為 AI 可讀的提示"""
    npcs = get_npcs()
    npc_info = ""
    for npc in npcs:
        npc_info += _format_npc_prompt_block(npc)
    return npc_info


def select_relevant_npcs(location: str, player_action: str, relations: dict | None, limit: int = 8) -> list:
    """簡易 RAG：只挑本輪可能相關的 NPC，避免把全 NPC 資料塞進 prompt。"""
    all_npcs = get_npcs()
    rel_npcs = (relations or {}).get('npcs', {})
    selected = []
    seen = set()

    def add(npc):
        name = npc.get('name')
        if name and name not in seen:
            selected.append(npc)
            seen.add(name)

    for npc in all_npcs:
        if npc.get('location') == location:
            add(npc)

    for npc in all_npcs:
        name = npc.get('name', '')
        title = npc.get('title', '')
        if (name and name in player_action) or (title and title in player_action):
            add(npc)

    for npc in all_npcs:
        name = npc.get('name', '')
        rel = rel_npcs.get(name, {})
        if abs(rel.get('好感度', 0)) >= 60 or rel.get('alive') is False:
            add(npc)

    return selected[:limit]


def format_selected_npc_data(npcs: list) -> str:
    """將挑選後的 NPC 資料格式化為 AI 可讀提示。"""
    if not npcs:
        return "（本輪無直接相關 NPC。若需 NPC 介入，必須符合地點、位階與劇情因果。）"
    npc_info = ""
    for npc in npcs:
        npc_info += _format_npc_prompt_block(npc)
    return npc_info


def get_scene_npcs(location: str) -> str:
    """取得當前場景中的 NPC 名單"""
    npcs = get_npcs()
    scene = [npc['name'] for npc in npcs if npc.get('location') == location]
    return "、".join(scene) if scene else "無"

def get_present_scene_npcs(location: str, profile: dict | None = None, status: dict | None = None, player_input: str = "") -> list[str]:
    """Return NPCs physically present by default, not every resident of the palace."""
    profile = profile or {}
    status = status or {}
    family_id = profile.get("family")
    start_host = ""
    start_location = ""
    peer_npcs: list[str] = []
    try:
        from game.state import get_families
        for family in get_families():
            if family.get("id") == family_id:
                start_location = (family.get("start_location") or {}).get("location_id", "")
                contacts = family.get("opening_contacts") or {}
                start_host = str(contacts.get("host_npc") or "").strip()
                peer_npcs = [str(name).strip() for name in contacts.get("peer_npcs", []) if str(name).strip()]
                break
    except Exception:
        pass

    scene_state = status.get("scene_state") if isinstance(status, dict) else {}
    explicit_present = []
    if isinstance(scene_state, dict) and isinstance(scene_state.get("explicit_present_npcs"), list):
        explicit_present = [str(name).strip() for name in scene_state.get("explicit_present_npcs", []) if str(name).strip()]

    present: list[str] = []
    if isinstance(scene_state, dict) and isinstance(scene_state.get("present_npcs"), list):
        present.extend(str(name).strip() for name in scene_state.get("present_npcs", []) if str(name).strip())

    if location == start_location:
        if start_host and start_host not in explicit_present:
            present = [name for name in present if name != start_host]
        present.extend(peer_npcs)

    present.extend(explicit_present)
    return list(dict.fromkeys(present))


def detect_extreme_action(text: str) -> dict:
    """
    偵測玩家的行動是否觸發極端行為標記。
    回傳 {is_insult: bool, is_violence: bool}
    """
    is_insult = any(kw in text for kw in INSULT_KEYWORDS)
    violence_keywords = ['打', '踢', '推', '摔', '攻擊', '扇', '掌摑', '咬']
    is_violence = any(kw in text for kw in violence_keywords)
    return {'is_insult': is_insult, 'is_violence': is_violence}


def update_npc_emotions(user_id, scene_npc_names: list, extreme_flags: dict):
    """
    根據玩家的極端行為，更新場景內所有 NPC 的情緒值。
    回傳更新後的 relations dict 與是否有 NPC 觸發閾值。
    """
    relations = load_player_relations(user_id) or {'npcs': {}}
    triggered_npcs = []

    for npc_name in scene_npc_names:
        if npc_name not in relations['npcs']:
            relations['npcs'][npc_name] = {
                '好感度': 0, '恩怨': '無',
                'emotion_state': {'anger': 0, 'fear': 0},
                'alive': True
            }
        emotion = relations['npcs'][npc_name].setdefault(
            'emotion_state', {'anger': 0, 'fear': 0}
        )
        if extreme_flags['is_insult']:
            emotion['anger'] = min(100, emotion.get('anger', 0) + 25)
        if extreme_flags['is_violence']:
            emotion['anger'] = min(100, emotion.get('anger', 0) + 40)
            emotion['fear'] = min(100, emotion.get('fear', 0) + 20)
        relations['npcs'][npc_name]['emotion_state'] = emotion

        if (emotion['anger'] >= ANGER_THRESHOLD or
                emotion['fear'] >= FEAR_THRESHOLD):
            triggered_npcs.append({
                'name': npc_name,
                'anger': emotion['anger'],
                'fear': emotion['fear']
            })

    save_player_data(user_id, 'relations', relations)
    return relations, triggered_npcs


def build_emotion_override(triggered_npcs: list) -> str:
    """
    若有 NPC 觸發閾值，生成強制覆蓋指令注入 prompt。
    """
    if not triggered_npcs:
        return ""
    lines = ["━━ 情緒突發強制覆蓋 ━━"]
    lines.append("以下 NPC 情緒已突破臨界，必須立即切換至【突發狀況分支】：")
    for npc in triggered_npcs:
        if npc['anger'] >= ANGER_THRESHOLD:
            lines.append(
                f"• {npc['name']}（憤怒值 {npc['anger']}）：必須做出憤怒或激烈的反應，可能失去理智、大聲呵斥、召人行刑，或做出超出劇本的衝動舉動。")
        if npc['fear'] >= FEAR_THRESHOLD:
            lines.append(
                f"• {npc['name']}（恐懼值 {npc['fear']}）：必須表現出恐懼、顫抖或試圖逃離、求饒。")
    lines.append("━━ 此覆蓋優先於所有劇情預設，必須執行 ━━")
    return "\n".join(lines)


def detect_affection_change(text: str) -> int:
    """回傳好感度變化量（正/負/0），依正負關鍵字數量判定"""
    pos = sum(1 for k in AFFECTION_POSITIVE_KEYWORDS if k in text)
    neg = sum(1 for k in AFFECTION_NEGATIVE_KEYWORDS if k in text)
    if pos > neg:
        return 8
    elif neg > pos:
        return -12
    return 0


def update_npc_affection(user_id, npc_name: str, delta: int):
    """Update the canonical public affection field."""
    relations = load_player_relations(user_id) or {'npcs': {}, 'companions': {}}
    npcs = relations.setdefault('npcs', {})
    npc_data = npcs.setdefault(npc_name, {
        '好感度': 0,
        '恩怨': '無',
        'emotion_state': {'anger': 0, 'fear': 0},
        'alive': True,
    })
    current = npc_data.get('好感度', npc_data.get('憟賣?摨?', 0))
    npc_data['好感度'] = max(-100, min(100, int(current or 0) + int(delta or 0)))
    npc_data.pop('憟賣?摨?', None)
    npc_data.setdefault('恩怨', npc_data.pop('?拇?', '無'))
    save_player_data(user_id, 'relations', relations)


INVALID_COMPANION_NAMES = {
    "你命", "身旁", "身旁的", "旁人", "宮人", "宮女", "太監", "侍女", "嬤嬤",
    "對方", "有人", "眾人", "她們", "他們", "自己", "玩家", "娘娘", "小主",
}


def extract_companion_candidates(text: str) -> list:
    roles = [re.escape(role) for role in COMPANION_ROLES if role]
    if not roles:
        return []
    known_npcs = {npc.get("name") for npc in get_npcs() if isinstance(npc, dict)}
    pattern = r"([\u4e00-\u9fff]{2,3})(?:姑姑|宮女|侍女|嬤嬤|太監|隨侍|丫鬟)"
    candidates = []
    for name in re.findall(pattern, str(text or "")):
        name = name.strip("的了著過在向與和")
        if len(name) < 2 or name in INVALID_COMPANION_NAMES or name in known_npcs:
            continue
        if any(bad in name for bad in ("身旁", "你", "她", "他", "自己")):
            continue
        candidates.append(name)
    return list(dict.fromkeys(candidates))[:3]


def update_companion_tracking(user_id, text: str):
    relations = load_player_relations(user_id) or {'npcs': {}, 'companions': {}}
    companions = relations.setdefault('companions', {})
    candidates = extract_companion_candidates(text)
    changed = False
    for name in candidates:
        if name not in companions:
            companions[name] = {'role': '隨侍', 'desc': '', 'appear_count': 1}
            changed = True
        else:
            companions[name]['appear_count'] = companions[name].get('appear_count', 1) + 1
            changed = True
    if changed:
        save_player_data(user_id, 'relations', relations)


def _rank_level(rank_name: str | None, gamedata: dict) -> int | None:
    if not rank_name:
        return None
    for rank in gamedata.get("ranks", []):
        if rank_name in {rank.get("id"), rank.get("name")}:
            return rank.get("level")
    return None


def _npc_by_name(gamedata: dict) -> dict:
    return {npc.get("name"): npc for npc in gamedata.get("npcs", []) if npc.get("name")}


def default_hidden_state_for_npc(npc_name: str, npc: dict | None = None, relation: dict | None = None) -> dict:
    relation = relation or {}
    rank = (npc or {}).get("rank", "")
    base_suspicion = 50 if rank in {"皇帝", "皇太后", "皇后"} or npc_name in {"皇后", "德宣帝"} else 30
    base_interest = 20 if rank in {"皇帝", "皇太后", "皇后", "皇貴妃", "貴妃"} else 10
    emotion = relation.get("emotion_state", {}) if isinstance(relation, dict) else {}
    return {
        "suspicion": base_suspicion,
        "interest": base_interest,
        "anger": clamp_int(emotion.get("anger", 10), 0, 100, 10),
        "trust": clamp_int(relation.get("好感度", 0), -100, 100, 0),
        "threat": 0,
        "intel_known": [],
        "test_intent": False
    }


def _npc_rank_level(npc: dict | None, gamedata: dict) -> int | None:
    return _rank_level((npc or {}).get("rank"), gamedata)


def _is_high_rank_npc(npc: dict | None, gamedata: dict) -> bool:
    level = _npc_rank_level(npc, gamedata)
    return level is not None and level <= HIGH_RANK_NPC_LEVEL


def _mentioned_known_npcs(text: str, gamedata: dict) -> list[str]:
    return [
        npc.get("name") for npc in gamedata.get("npcs", [])
        if npc.get("name") and npc.get("name") in (text or "")
    ]


def ensure_hidden_state(relations: dict | None, gamedata: dict, game_state: dict | None = None, player_input: str = "") -> dict:
    relations = relations or {"npcs": {}, "companions": {}}
    rel_npcs = relations.setdefault("npcs", {})
    hidden_state = relations.setdefault("hidden_state", {})
    npcs_by_name = _npc_by_name(gamedata)
    names = set(_mentioned_known_npcs(player_input, gamedata))
    names.update((game_state or {}).get("scene_npcs", []) or [])
    names.update((relations.get("npcs", {}) or {}).keys())
    for name in names:
        if not name or rel_npcs.get(name, {}).get("alive") is False:
            continue
        current = hidden_state.setdefault(name, {})
        defaults = default_hidden_state_for_npc(name, npcs_by_name.get(name), rel_npcs.get(name, {}))
        for key, value in defaults.items():
            current.setdefault(key, value)
    return relations


def _hidden_state_for(relations: dict | None, npc_name: str) -> dict:
    hidden = (relations or {}).get("hidden_state", {})
    state = hidden.get(npc_name, {}) if isinstance(hidden, dict) else {}
    return state if isinstance(state, dict) else {}


def _hidden_band(value, wary_at: int = 60, sharp_at: int = 80) -> str:
    value = clamp_int(value, 0, 100)
    if value >= sharp_at:
        return "sharp"
    if value >= wary_at:
        return "wary"
    if value >= 35:
        return "watching"
    return "settled"


def hidden_state_cues(relations: dict | None, npc_names: list[str]) -> dict:
    cues = {}
    for name in npc_names:
        state = _hidden_state_for(relations, name)
        if not state:
            continue
        cues[name] = {
            "suspicion_cue": _hidden_band(state.get("suspicion", 0)),
            "anger_cue": _hidden_band(state.get("anger", 0), 45, 70),
            "interest_cue": _hidden_band(state.get("interest", 0), 45, 70),
            "threat_cue": _hidden_band(state.get("threat", 0), 45, 70),
            "trust_cue": "guarded" if clamp_int(state.get("trust", 0), -100, 100) < 0 else "neutral_or_warmer",
            "test_intent": bool(state.get("test_intent", False))
        }
    return cues


def _add_hidden_delta(state_update: dict, npc_name: str, **deltas):
    target = state_update.setdefault("hidden_state_delta", {}).setdefault(npc_name, {})
    for key, value in deltas.items():
        if value:
            target[key] = target.get(key, 0) + int(value)


def _add_relation_delta(state_update: dict, npc_name: str, **deltas):
    target = state_update.setdefault("relations_delta", {}).setdefault(npc_name, {})
    for key, value in deltas.items():
        if value:
            target[key] = target.get(key, 0) + int(value)


def _primary_npc(mentioned_npcs: list[str], game_state: dict, gamedata: dict, relations: dict | None) -> str | None:
    rel_npcs = (relations or {}).get("npcs", {})
    npcs_by_name = _npc_by_name(gamedata)
    has_known_mention = any(name in npcs_by_name for name in mentioned_npcs)
    for name in mentioned_npcs:
        if name in npcs_by_name and rel_npcs.get(name, {}).get("alive") is not False:
            return name
    if has_known_mention:
        return None
    for name in game_state.get("scene_npcs", []) or []:
        if name in npcs_by_name and rel_npcs.get(name, {}).get("alive") is not False:
            return name
    return None


def plan_npc_actions(judge_result: dict, game_state: dict, relations: dict | None, gamedata: dict) -> list[dict]:
    """Final planner: only present NPCs act, and action style follows npcs.json."""
    rel_npcs = (relations or {}).get("npcs", {})
    npcs_by_name = _npc_by_name(gamedata)
    mentioned = [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]
    primary = _primary_npc(mentioned, game_state, gamedata, relations)
    scene_names = {str(name).strip() for name in (game_state or {}).get("scene_npcs", []) if str(name).strip()}
    if not primary or primary not in scene_names or rel_npcs.get(primary, {}).get("alive") is False:
        return []
    npc = npcs_by_name.get(primary, {})
    hidden = _hidden_state_for(relations, primary)
    if not _is_high_rank_npc(npc, gamedata):
        return []

    stats = get_npc_stats(npc)
    personality = str(npc.get("personality", ""))
    hidden_agenda = str((npc.get("hidden") or {}).get("hidden_agenda", ""))
    suspicion = clamp_int(hidden.get("suspicion", 0), 0, 100)
    anger = clamp_int(hidden.get("anger", 0), 0, 100)
    threat = clamp_int(hidden.get("threat", 0), 0, 100)
    tone = judge_result.get("social_tone", "neutral")
    risk = judge_result.get("risk_level", "medium")
    cunning = max(clamp_int(stats.get("心機", 0), 0, 100), clamp_int(stats.get("權謀", 0), 0, 100))

    def action(kind: str, description: str, effect: dict) -> list[dict]:
        return [{
            "npc": primary,
            "type": kind,
            "action": kind if kind != "redirect" else "redirect_topic",
            "description": description,
            "mechanical_effect": effect,
            "personality_basis": personality[:120],
            "hidden_agenda_basis": hidden_agenda[:120],
            "stat_basis": {"cunning": cunning},
        }]

    indirect = any(word in personality + hidden_agenda for word in ("牆頭草", "背後", "依附", "試探", "掌握", "權力"))
    blunt = any(word in personality for word in ("直率", "暴躁", "傲慢", "強勢"))
    if suspicion >= 65 or hidden.get("test_intent") is True:
        if indirect or cunning >= 60:
            return action("test", f"{primary}借一句尋常問候試探玩家來意，話面溫和，卻把可疑處輕輕挑起。", {"suspicion_delta": 5, "interest_delta": 1})
        return action("withhold_info", f"{primary}把話留在規矩裡，不肯把真正意思說透。", {"suspicion_delta": 2})
    if anger >= 55 or tone == "rude" or threat >= 60:
        if blunt:
            return action("pressure", f"{primary}語氣壓低，直接把分寸擺到玩家面前。", {"anger_delta": 4, "suspicion_delta": 3, "trust_delta": -1})
        return action("soft_attack", f"{primary}把不悅藏進一句客氣話裡，讓旁人聽得出提醒，卻挑不出明面錯處。", {"anger_delta": 2, "suspicion_delta": 3, "trust_delta": -1})
    if suspicion >= 50 and tone in {"probing", "evasive", "flattering"}:
        if indirect or cunning >= 60:
            return action("soft_attack", f"{primary}順著話頭笑了一句，像玩笑，實則把玩家過於急切之處點給旁人看。", {"suspicion_delta": 4, "trust_delta": -1, "interest_delta": 1})
        return action("redirect", f"{primary}沒有接住追問，只把話題撥回無害的宮規與日常。", {"suspicion_delta": 3})
    if risk == "high":
        return action("withhold_info", f"{primary}收住原本要說的話，只留下一句可進可退的場面話。", {"suspicion_delta": 2})
    return []
