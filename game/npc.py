from __future__ import annotations
import re

from game.state import get_npcs, load_player_relations, save_player_data, clamp_int

ANGER_THRESHOLD = 70
FEAR_THRESHOLD = 70
INSULT_KEYWORDS = ['??', '?', '??', '?', '??', '?', '?', '?', '?']
AFFECTION_POSITIVE_KEYWORDS = ['??', '??', '??', '??', '??', '??', '??', '??', '??', '??']
AFFECTION_NEGATIVE_KEYWORDS = ['??', '??', '??', '??', '??', '??', '??', '??', '??']
COMPANION_ROLES = ['??', '??', '??', '??', '??', '??', '??', '??']
HIGH_RANK_NPC_LEVEL = 7

def format_npc_data():
    """將 NPC 資料格式化為 AI 可讀的提示"""
    npcs = get_npcs()
    npc_info = ""
    for npc in npcs:
        npc_info += f"【{npc['name']}】{npc.get('title', '')}\n"
        npc_info += f"  位置：{npc.get('location', '未知')}\n"
        npc_info += f"  性格：{npc.get('personality', '無')}\n"
        stats = npc.get('stats', {})
        if stats:
            stats_str = "、".join(f"{k}:{v}" for k, v in stats.items())
            npc_info += f"  能力值：{stats_str}\n"
        hidden = npc.get('hidden', {})
        if hidden.get('hidden_agenda'):
            agenda = hidden['hidden_agenda'][:80]
            npc_info += f"  潛在意圖：{agenda}...\n"
        npc_info += "\n"
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
        npc_info += f"【{npc['name']}】{npc.get('title', '')}\n"
        npc_info += f"  位置：{npc.get('location', '未知')}\n"
        npc_info += f"  性格：{npc.get('personality', '無')}\n"
        stats = npc.get('stats', {})
        if stats:
            stats_str = "、".join(f"{k}:{v}" for k, v in stats.items())
            npc_info += f"  能力值：{stats_str}\n"
        hidden = npc.get('hidden', {})
        if hidden.get('hidden_agenda'):
            agenda = hidden['hidden_agenda'][:80]
            npc_info += f"  潛在意圖：{agenda}...\n"
        npc_info += "\n"
    return npc_info


def get_scene_npcs(location: str) -> str:
    """取得當前場景中的 NPC 名單"""
    npcs = get_npcs()
    scene = [npc['name'] for npc in npcs if npc.get('location') == location]
    return "、".join(scene) if scene else "無"


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
    """更新單一 NPC 的好感度，上下限 -100 ~ 100"""
    relations = load_player_relations(user_id) or {'npcs': {}, 'companions': {}}
    npcs = relations.setdefault('npcs', {})
    if npc_name not in npcs:
        npcs[npc_name] = {
            '好感度': 10, '恩怨': '初次見面',
            'emotion_state': {'anger': 0, 'fear': 0},
            'alive': True
        }
    current = npcs[npc_name].get('好感度', 10)
    npcs[npc_name]['好感度'] = max(-100, min(100, current + delta))
    save_player_data(user_id, 'relations', relations)


def extract_companion_candidates(text: str) -> list:
    """從文字中抓取潛在隨侍名稱（1~3 字名 + 身份詞）"""
    pattern = r'([一-龥]{1,3})(?:' + '|'.join(COMPANION_ROLES) + ')'
    return re.findall(pattern, text)


def update_companion_tracking(user_id, text: str):
    """累計隨侍出現次數，>= 3 次自動晉升為 companions"""
    relations = load_player_relations(user_id) or {'npcs': {}, 'companions': {}}
    companions = relations.setdefault('companions', {})
    candidates = extract_companion_candidates(text)
    changed = False
    for name in set(candidates):
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
    for name, npc in npcs_by_name.items():
        if _is_high_rank_npc(npc, gamedata):
            names.add(name)
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
    for name, npc in npcs_by_name.items():
        if _is_high_rank_npc(npc, gamedata) and rel_npcs.get(name, {}).get("alive") is not False:
            return name
    return None


def plan_npc_actions(judge_result: dict, game_state: dict, relations: dict | None, gamedata: dict) -> list[dict]:
    rel_npcs = (relations or {}).get("npcs", {})
    npcs_by_name = _npc_by_name(gamedata)
    mentioned = [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()]
    primary = _primary_npc(mentioned, game_state, gamedata, relations)
    if not primary or rel_npcs.get(primary, {}).get("alive") is False:
        return []
    npc = npcs_by_name.get(primary, {})
    hidden = _hidden_state_for(relations, primary)
    if not _is_high_rank_npc(npc, gamedata):
        return []

    suspicion = clamp_int(hidden.get("suspicion", 0), 0, 100)
    anger = clamp_int(hidden.get("anger", 0), 0, 100)
    tone = judge_result.get("social_tone", "neutral")
    risk = judge_result.get("risk_level", "medium")

    if suspicion >= 65 or hidden.get("test_intent") is True:
        return [{
            "npc": primary,
            "action": "test_player",
            "description": f"{primary}刻意拋出一句看似尋常的話，試探玩家是否急於辯解或露出破綻。",
            "mechanical_effect": {"suspicion_delta": 5}
        }]
    if anger >= 55 or tone == "rude":
        return [{
            "npc": primary,
            "action": "pressure_player",
            "description": f"{primary}收緊語氣，讓近旁侍從留意玩家接下來的反應。",
            "mechanical_effect": {"anger_delta": 4, "suspicion_delta": 3}
        }]
    if risk == "high" and tone in {"probing", "evasive", "flattering"}:
        return [{
            "npc": primary,
            "action": "redirect_topic",
            "description": f"{primary}不正面回答，反而把話題轉回玩家身上。",
            "mechanical_effect": {"suspicion_delta": 3}
        }]
    return []


