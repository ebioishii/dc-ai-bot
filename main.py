import os
import re
import json
import discord
import google.generativeai as genai
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# --- 環境設定 ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 設定 Gemini API 金鑰
genai.configure(api_key=GEMINI_API_KEY)
<<<<<<< HEAD
=======

# 模型設定 — 在這裡換模型，全程只改這一行
GM_MODEL = "gemini-2.5-flash-lite"   # 主要 GM 模型
BASE_MODEL = "gemini-2.5-flash-lite"   # 角色背景生成等輔助任務
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

# 模型設定 — 在這裡換模型，全程只改這一行
GM_MODEL = "gemini-2.5-flash-lite"
BASE_MODEL = "gemini-2.5-flash-lite"


# ============================================================
# 工具函式
# ============================================================

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


<<<<<<< HEAD
def get_strategies():
    with open('gamedata/strategies.json', 'r', encoding='utf-8') as f:
        return json.load(f).get('strategies', [])


=======
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
def format_npc_data():
    """將 NPC 資料格式化為 AI 可讀的提示"""
    npcs = get_npcs()
    npc_info = ""
    for npc in npcs:
        npc_info += f"【{npc['name']}】{npc.get('title', '')}\n"
        npc_info += f"  位置：{npc.get('location', '未知')}\n"
        npc_info += f"  性格：{npc.get('personality', '無')}\n"
<<<<<<< HEAD
        stats = npc.get('stats', {})
        if stats:
            stats_str = "、".join(f"{k}:{v}" for k, v in stats.items())
            npc_info += f"  能力值：{stats_str}\n"
=======
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        hidden = npc.get('hidden', {})
        if hidden.get('hidden_agenda'):
            agenda = hidden['hidden_agenda'][:80]
            npc_info += f"  潛在意圖：{agenda}...\n"
        npc_info += "\n"
    return npc_info


<<<<<<< HEAD

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

=======
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
def get_scene_npcs(location: str) -> str:
    """取得當前場景中的 NPC 名單"""
    npcs = get_npcs()
    scene = [npc['name'] for npc in npcs if npc.get('location') == location]
    return "、".join(scene) if scene else "無"


<<<<<<< HEAD
def _affection_tier(v: int) -> str:
    if v > 80: return "盟友"
    if v > 60: return "友善"
    if v > 30: return "中立"
    if v >= 0: return "警惕"
    return "敵意"


def format_player_relations(relations):
    """將玩家與 NPC 的關係格式化"""
    npcs = relations.get('npcs', {}) if relations else {}
    companions = relations.get('companions', {}) if relations else {}
    rel_info = ""

    if npcs:
        for npc_id, data in npcs.items():
            好感度 = data.get('好感度', 0)
            恩怨 = data.get('恩怨', '無')
            tier = _affection_tier(好感度)
            emotion = data.get('emotion_state', {})
            anger = emotion.get('anger', 0)
            fear = emotion.get('fear', 0)
            alive = data.get('alive', True)
            life_state = "已死亡，不得登場、不得說話、不得被其他角色當作仍活著互動" if alive is False else "存活"
            rel_info += f"• {npc_id}：{life_state}，好感度 {好感度}（{tier}），恩怨：{恩怨}，憤怒：{anger}，恐懼：{fear}\n"

    active_companions = {k: v for k, v in companions.items() if v.get('appear_count', 0) >= 3}
    if active_companions:
        rel_info += "\n【玩家身旁已知隨侍】\n"
        for name, data in active_companions.items():
            rel_info += f"• {name}（{data.get('role', '隨侍')}）：{data.get('desc', '無額外描述')}\n"

    return rel_info if rel_info.strip() else "（尚無記錄的 NPC 關係）"


# ============================================================
# 規則格式化
# ============================================================
=======
def format_player_relations(relations):
    """將玩家與 NPC 的關係格式化"""
    npcs = relations.get('npcs', {}) if relations else {}
    if not npcs:
        return "（尚無記錄的 NPC 關係）"
    rel_info = ""
    for npc_id, data in npcs.items():
        好感度 = data.get('好感度', 0)
        恩怨 = data.get('恩怨', '無')
        rel_info += f"• {npc_id}：好感度 {好感度}，恩怨：{恩怨}\n"
    return rel_info


# --- 規則格式化 ---
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

def format_game_rules():
    """將所有規則格式化為 AI 可讀的提示"""
    rules_data = get_rules()
    punishments = get_punishments()
    rewards = get_rewards()
    ranks = get_ranks()

    ranks_info = "【後宮位階】皇后＞皇貴妃＞貴妃＞妃＞嬪＞貴人＞常在＞答應＞宮女\n"
    for rank in ranks[:12]:
        ranks_info += f"• {rank['name']}：{rank['description']}\n"

    court_rules = "【宮廷規矩】\n"
    for rule in rules_data.get('court_rules', []):
        court_rules += f"• {rule}\n"

    forbidden = "【禁忌】不可"
    forbidden += "、".join(rules_data.get('forbidden_actions', []))
    forbidden += "。\n"

<<<<<<< HEAD
    punishments_info = "【責處規制】"
    for p in punishments:
        punishments_info += f"{p['name']}：{p['description']}；"

=======
    # 懲罰詞彙軟化對照表，避免觸發安全過濾
    punishment_softener = {
        "杖責": "責打", "杖斃": "重責", "賜死": "奉旨處置",
        "毒殺": "暗害", "殺": "除去", "死": "離去",
        "懲罰": "責處", "處死": "奉旨離宮", "凌遲": "嚴懲",
    }

    punishments_info = "【責處規制】"
    for p in punishments:
        name = p["name"]
        desc = p["description"]
        for k, v in punishment_softener.items():
            name = name.replace(k, v)
            desc = desc.replace(k, v)
        punishments_info += f"{name}：{desc}；"

>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    rewards_info = "【恩賞規制】"
    for r in rewards:
        rewards_info += f"{r['name']}：{r['description']}；"

    return f"{ranks_info}\n{court_rules}\n{forbidden}\n{punishments_info}\n{rewards_info}"


<<<<<<< HEAD
# ============================================================
# ── 修正1：指令解析優先級 ──
# 辨識玩家輸入是「敘事行動」還是「系統指令」
# ============================================================

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


# ============================================================
# ── 修正2：事實清單 (Fact Sheet) 管理 ──
# 每次 /ooc 修正後寫入 memory['fact_sheet']，覆蓋舊有記憶
# ============================================================

def load_fact_sheet(user_id) -> str:
    memory = load_player_memory(user_id)
    if not memory:
        return ""
    return memory.get('fact_sheet', '')


def update_fact_sheet(user_id, correction: str, result_summary: str):
    """
    將 OOC 修正後的事實加入 fact_sheet。
    fact_sheet 以條目形式儲存，最多保留 10 條。
    """
    memory = load_player_memory(user_id)
    if not memory:
        return
    existing = memory.get('fact_sheet_items', [])
    new_entry = f"[修正] {correction[:60]} → [確認事實] {result_summary[:80]}"
    existing.append(new_entry)
    # 只保留最近 10 條修正事實
    memory['fact_sheet_items'] = existing[-10:]
    memory['fact_sheet'] = "\n".join(memory['fact_sheet_items'])
    save_player_data(user_id, 'memory', memory)


# ============================================================
# ── 修正4：NPC 情緒系統 ──
# 在 relations.json 中追蹤每個 NPC 的 anger / fear 值
# ============================================================

# 觸發「突發狀況」模式的閾值
ANGER_THRESHOLD = 70
FEAR_THRESHOLD = 70

# 粗口 / 侮辱性詞彙（可自行擴充）
INSULT_KEYWORDS = ['賤人', '滾', '廢物', '狗', '混帳', '死', '蠢', '豬', '臭']


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


# ============================================================
# 好感度系統（雙軌制）
# ============================================================

AFFECTION_POSITIVE_KEYWORDS = ['送禮', '問候', '感謝', '幫助', '請安', '致意', '相贈', '拜訪', '獻上', '帶來']
AFFECTION_NEGATIVE_KEYWORDS = ['拒絕', '無視', '羞辱', '背叛', '欺騙', '冷落', '嘲笑', '斥責', '趕走']


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


# ============================================================
# 隨侍追蹤系統
# ============================================================

COMPANION_ROLES = ['宮女', '太監', '嬤嬤', '姑姑', '丫鬟', '內侍', '公公', '嬷嬷']


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


# ============================================================
# 記憶系統
# ============================================================

def build_history_summary(short_term: list) -> str:
    """
    ── 修正3：精簡上下文 ──
    只保留最近 3 輪對話，GM 回應截取前 200 字，避免復讀機效應。
    """
    if not short_term:
        return "無（初次入宮）"
    # 只取最後 3 輪
    recent = short_term[-3:]
    lines = []
    for h in recent:
        bot_preview = h['bot'][:200].rstrip()
=======
# --- 記憶系統 ---

# 傳回模型前的內容軟化對照表
# 目的：避免 history_summary 裡的詞彙觸發 Gemini 安全過濾
# 只影響傳給 AI 的版本，存檔的原始內容不受影響
CONTENT_SOFTENER = {
    "妃子": "宮中女眷",
    "男扮女裝": "喬裝入宮",
    "聖寵": "帝王恩寵",
    "承寵": "蒙受眷顧",
    "侍寢": "隨侍左右",
    "枕邊": "近身服侍",
    "臨幸": "召見",
    "寵幸": "眷顧",
    "床榻": "寢殿",
    "情事": "私情",
    "私情": "往來",
    "勾引": "示好",
    "魅惑": "吸引",
    "誘惑": "吸引",
    "春宵": "夜晚",
    "春情": "情誼",
    "媚態": "姿態",
}


def soften_content(text: str) -> str:
    """將文字中可能觸發安全過濾的詞彙替換為委婉說法"""
    for k, v in CONTENT_SOFTENER.items():
        text = text.replace(k, v)
    return text


def build_history_summary(short_term: list) -> str:
    """將短期記憶格式化為可讀摘要，GM 回應截取前 200 字並軟化敏感詞"""
    if not short_term:
        return "無（初次入宮）"
    lines = []
    for h in short_term:
        bot_preview = soften_content(h['bot'][:200].rstrip())
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        if len(h['bot']) > 200:
            bot_preview += "……"
        lines.append(f"玩家：{h['user']}\nGM：{bot_preview}")
    return "\n\n".join(lines)


def build_gemini_history(short_term: list) -> list:
<<<<<<< HEAD
    """將 short_term 轉換為 Gemini Chat API 所需的 history 格式。"""
=======
    """
    將 short_term 轉換為 Gemini Chat API 所需的 history 格式。
    這讓模型真正「記得」對話，而非靠文字摘要猜測。
    """
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    history = []
    for h in short_term:
        history.append({"role": "user", "parts": [h["user"]]})
        history.append({"role": "model", "parts": [h["bot"]]})
    return history


def extract_key_info(dialogue_pair: dict) -> str:
<<<<<<< HEAD
    user_msg = dialogue_pair.get('user', '')
    user_msg = re.sub(r'^\[.*?\]\s*|^【.*?】\s*', '', user_msg)[:80].strip()
    bot_msg = dialogue_pair.get('bot', '')[:180].strip()
    return f"[玩家：{user_msg}] → [場景：{bot_msg}]"
=======
    """
    將一筆對話壓縮為長期記憶條目。
    使用固定模板而非額外 AI 呼叫，更穩定且省費用。
    """
    user_msg = dialogue_pair.get('user', '')[:60].strip()
    bot_msg = dialogue_pair.get('bot', '')[:120].strip()
    return f"[玩家：{user_msg}] → [結果：{bot_msg}]"
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)


def manage_memory(user_id):
    """
    滾動式記憶管理：
<<<<<<< HEAD
    當短期記憶 >= 10 筆時，壓縮最舊的 2 筆為長期記憶條目。
    長期記憶以帶編號列表儲存（最多 15 條）。
=======
    當短期記憶 >= 11 筆時，壓縮最舊的 2 筆為長期記憶條目。
    長期記憶以條目數量（最多 15 條）而非字元數截斷，避免切在句子中間。
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    """
    memory = load_player_memory(user_id)
    if not memory:
        return

    short_term = memory.get('short_term', [])
    long_term = memory.get('long_term_summary', '')

<<<<<<< HEAD
    if len(short_term) < 10:
=======
    if len(short_term) < 11:
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        return

    old_dialogues = short_term[:2]
    memory['short_term'] = short_term[2:]

    new_items = [extract_key_info(d) for d in old_dialogues]

<<<<<<< HEAD
    # 相容舊版 pipe-separated 格式與新版帶編號格式
    if ' | ' in long_term and not long_term.strip().startswith('1.'):
        existing_items = [i.strip() for i in long_term.split(' | ') if i.strip()]
    else:
        existing_items = [
            re.sub(r'^\d+\.\s*', '', line).strip()
            for line in long_term.splitlines()
            if line.strip()
        ]
    existing_items.extend(new_items)

    if len(existing_items) > 15:
        existing_items = existing_items[-15:]

    memory['long_term_summary'] = "\n".join(
        f"{i + 1}. {item}" for i, item in enumerate(existing_items)
    )
=======
    existing_items = [i.strip() for i in long_term.split(" | ") if i.strip()]
    existing_items.extend(new_items)

    # 只保留最近 15 條
    if len(existing_items) > 15:
        existing_items = existing_items[-15:]

    memory['long_term_summary'] = " | ".join(existing_items)
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    save_player_data(user_id, 'memory', memory)
    print(f"✅ 記憶滾動：已壓縮 2 筆舊對話至長期記憶")


<<<<<<< HEAD
# ============================================================
# 模型工廠
# ============================================================

def make_gm_system_instruction(game_rules: str) -> str:
    """
    產生 GM 的 system instruction。
    ── 修正1 & 修正2 & 修正3：在 system prompt 加入強化約束 ──
    """
    gm_rule = get_script("system_prompts", "game_master")
    base = gm_rule.replace("{game_rules}", game_rules)

    # 附加核心強制規則
    extra = """

══════════════════════════════════════════
【核心強制規則 — 凌駕一切敘事氛圍，違反即為失敗】
══════════════════════════════════════════

▌指令優先級（修正1）
一、玩家行動中若包含明確的「殺死 / 賜死 / 處決」等指令，必須在本輪劇情中落實世界狀態改變——目標 NPC 必須真正死亡，且在後續所有輪次中維持已死狀態，不得復活、不得假死、不得以任何方式返場。
二、若玩家行動中包含具體詢問（「問某人」、「查詢」、「打探」），必須直接給出資訊或 NPC 的實際回應，不得以情境台詞代替答案。

▌禁止代寫玩家（修正2 — 反 Godmoding）
三、嚴禁替玩家預設心理活動（如：「你心中暗喜」「你決定忍耐」）。
四、嚴禁替玩家描述主動行為（如：「你起身請安」「你跪下謝恩」）——除非玩家行動指令中已明確說明此動作。
五、敘事只能描述：① NPC 的行動與語言、② 環境變化、③ 對玩家行動的直接後果。

▌禁止重複（修正3 — 反復讀）
六、嚴禁重複任何上一輪已出現過的台詞、場景描述、或 NPC 的反應模式。
七、每一輪必須向前推進：必須有新的事件、新的 NPC 行動、或新的資訊被揭露。
七之一、已登場的 NPC 不需要重新「出場介紹」，直接接續其正在進行的行為或對話。

▌事實清單約束（修正2）
八、若提示中出現「已確認事實」清單，其中的內容具有最高事實優先級，不得在後續劇情中矛盾或推翻。

▌NPC 說話與位階規範
九、每個 NPC 的自稱、他稱必須嚴格符合其位階，不得越位或降格：
   皇帝：自稱「朕」；
   皇太后：自稱「哀家」；
   皇后、皇貴妃、貴妃、妃：對下自稱「本宮」，對皇帝或太后自稱「臣妾」；
   嬪：不可自稱「本宮」，對上自稱「臣妾」；
   貴人、常在、答應：對上只能自稱「奴婢」；
   宮女：自稱「奴婢」；
   太監：自稱「奴才」；
   王公：自稱「臣」或「本王」；外臣：自稱「微臣」——禁止任何人自稱「在下」對後宮女眷說話。
十、NPC 的語氣必須符合其性格描述，不可千篇一律。

▌NPC 行動規範
十一、心機值 > 70 的 NPC：行事迂迴，不直說目的，偏好試探、暗示、借力打力。
十二、聲望值 > 70 的 NPC：言談間自帶威儀，情緒穩定，即使憤怒也是冷然壓迫感而非失控。
十三、每個 NPC 的行動必須服務其「潛在意圖」，非利益相關事務不主動介入。
十四、NPC 有記憶——玩家上一輪的行動（尤其涉及該 NPC）會影響本輪的態度與反應。

▌屬性系統對劇情的影響
十五、玩家屬性值須影響敘事走向：
   體力 < 30：高強度行動有代價（體力不支、動作遲緩）；
   體力 > 70：可承擔耗體力的行動而不失態；
   權謀 < 20：難以察覺他人政治意圖；
   權謀 > 60：能識破較明顯的計謀，NPC 陰謀需更高明才能欺騙；
   聲望 < 20：存在感低，低階 NPC 態度可能怠慢；
   聲望 > 60：受宮中認可，舉動更容易得到下人配合；
   財產 < 20：無法進行需要大量金錢的行動（送禮、收買）；
   財產 > 60：可運作財務手段影響人心。

▌好感度系統
十六、player_relations 中記載了各 NPC 的好感度，NPC 的態度必須反映此數值：
   好感度 > 80（盟友）：主動幫助、可能透露機密；
   好感度 60~80（友善）：樂意配合，態度友善；
   好感度 30~60（中立）：禮節性應對；
   好感度 0~30（警惕）：冷淡，不主動幫助，可能試探；
   好感度 < 0（敵意）：可能刁難、陷害或舉報。

▌懲處與恩賞
十七、當玩家觸犯宮廷規矩，相關 NPC 必須依照「責處規制」做出反應；懲處手段（如板子、掌嘴、禁足、賜死）應出現在敘事中，不可忽視違規行為。
十八、當玩家的行動符合受賞條件，可由上位 NPC 主動給予相應的恩賞。

▌NPC 計策運用"""

    strategies = get_strategies()
    strategy_names = "、".join(s['name'] for s in strategies)
    extra += f"""
十九、NPC 在主動出手時，可從以下計策中選擇符合其性格與情境的手段：{strategy_names}。
二十、高心機（>70）NPC 偏好迂迴計謀，不直接對抗；低心機 NPC 可能魯莽直衝。

══════════════════════════════════════════
"""
    return base + extra
=======
# --- 模型工廠 ---

def make_gm_system_instruction(game_rules: str) -> str:
    """產生 GM 的 system instruction 字串（供每次 API 呼叫使用）"""
    gm_rule = get_script("system_prompts", "game_master")
    return gm_rule.replace("{game_rules}", game_rules)
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)


async def call_gemini(system: str, user: str, model: str = None,
                      temperature: float = 0.75, max_tokens: int = 600) -> str | None:
<<<<<<< HEAD
    """統一的 Gemini 呼叫函式。回傳文字內容，失敗或被擋時回傳 None。"""
=======
    """
    統一的 Gemini 呼叫函式。
    回傳文字內容，失敗或被擋時回傳 None。
    """
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    try:
        model_name = model or GM_MODEL
        gemini_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature
            )
        )
        resp = await gemini_model.generate_content_async(user)

        if resp.prompt_feedback.block_reason:
            print(f"⚠️ Gemini 安全過濾：{resp.prompt_feedback.block_reason.name}")
            return None

        text = resp.text
        if not text or not text.strip():
            print("⚠️ Gemini 回傳空內容")
            return None
        return text.strip()
    except Exception as e:
        print(f"⚠️ Gemini 呼叫失敗：{e}")
        return None


<<<<<<< HEAD

def extract_json_object(text: str) -> dict | None:
    """從模型輸出中解析 JSON；容忍 ```json fence 或前後雜訊。"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            return None
    return None


async def call_gemini_json(system: str, user: str, model: str = None,
                           temperature: float = 0.65, max_tokens: int = 1000) -> dict | None:
    """Gemini JSON 呼叫。優先要求 application/json；失敗時回傳 None。"""
    try:
        model_name = model or GM_MODEL
        gemini_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_mime_type="application/json"
            )
        )
        resp = await gemini_model.generate_content_async(user)
        if resp.prompt_feedback.block_reason:
            print(f"⚠️ Gemini 安全過濾：{resp.prompt_feedback.block_reason.name}")
            return None
        return extract_json_object(resp.text)
    except Exception as e:
        print(f"⚠️ Gemini JSON 呼叫失敗：{e}")
        return None


JUDGE_AI_MODEL = "gemini-2.5-flash"


def judge_fallback() -> dict:
    return {
        "intent": "unknown",
        "player_intent": "unknown",
        "action_type": "unknown",
        "social_tone": "neutral",
        "risk_level": "medium",
        "possible_misread": "",
        "mentioned_npcs": [],
        "mentioned_items": [],
        "assumptions": [],
        "risk_flags": ["judge_ai_failed"],
        "mechanical_tags": []
    }


async def call_judge_ai(system, user):
    data = await call_gemini_json(
        system,
        user,
        model=JUDGE_AI_MODEL,
        temperature=0.2,
        max_tokens=1000
    )
    if not isinstance(data, dict):
        return judge_fallback()

    fallback = judge_fallback()
    result = {
        "intent": str(data.get("intent") or fallback["intent"])[:300],
        "player_intent": str(data.get("player_intent") or data.get("intent") or fallback["player_intent"])[:300],
        "action_type": str(data.get("action_type") or fallback["action_type"]),
        "social_tone": str(data.get("social_tone") or fallback["social_tone"]),
        "risk_level": str(data.get("risk_level") or fallback["risk_level"]),
        "possible_misread": str(data.get("possible_misread") or "")[:300],
        "mentioned_npcs": data.get("mentioned_npcs") if isinstance(data.get("mentioned_npcs"), list) else [],
        "mentioned_items": data.get("mentioned_items") if isinstance(data.get("mentioned_items"), list) else [],
        "assumptions": data.get("assumptions") if isinstance(data.get("assumptions"), list) else [],
        "risk_flags": data.get("risk_flags") if isinstance(data.get("risk_flags"), list) else [],
        "mechanical_tags": data.get("mechanical_tags") if isinstance(data.get("mechanical_tags"), list) else []
    }
    allowed_types = {"move", "ask", "attack", "wait", "observe", "social", "use_item", "other", "unknown"}
    if result["action_type"] not in allowed_types:
        result["action_type"] = "other"
    allowed_tones = {"humble", "rude", "probing", "evasive", "flattering", "neutral"}
    if result["social_tone"] not in allowed_tones:
        result["social_tone"] = "neutral"
    allowed_risks = {"low", "medium", "high"}
    if result["risk_level"] not in allowed_risks:
        result["risk_level"] = "medium"
    return result


async def call_story_ai(system, user):
    data = await call_gemini_json(
        system,
        user,
        model=GM_MODEL,
        temperature=0.75,
        max_tokens=1800
    )
    if not isinstance(data, dict):
        return {}
    reply = data.get("reply")
    choices = data.get("choices")
    update = data.get("state_update") if isinstance(data.get("state_update"), dict) else {}
    return {
        "reply": reply.strip() if isinstance(reply, str) else "",
        "choices": choices if isinstance(choices, list) else [],
        "state_update": update
    }


def _json_prompt_payload(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def build_judge_prompt(player_input, game_state, memory, relations, inventory):
    judge_system = (
        "You are AI 1: Intent / Judge AI for a Discord text game. "
        "Only understand player input, identify intent, risks, mentions, and assumptions. "
        "Do not write fiction, narration, dialogue, or player-facing story. "
        "Output JSON only."
    )
    judge_user = {
        "task": "Parse player_input into this exact JSON shape.",
        "schema": {
            "intent": "玩家真正想達成的目的",
            "player_intent": "玩家真正想達成的目的，與 intent 相同或更精準",
            "action_type": "move | ask | attack | wait | observe | social | use_item | other",
            "social_tone": "humble | rude | probing | evasive | flattering | neutral",
            "risk_level": "low | medium | high",
            "possible_misread": "NPC 可能如何誤解玩家行動",
            "mentioned_npcs": [],
            "mentioned_items": [],
            "assumptions": [],
            "risk_flags": [],
            "mechanical_tags": []
        },
        "rules": [
            "assumptions are claims from the player that are not guaranteed by current state.",
            "risk_flags should include possible godmoding, impossible item use, dead NPC mention, rank overreach, or state-changing assumptions.",
            "Do not flatter the player. If the wording could be read as rude, provocative, evasive, or overreaching, mark it clearly.",
            "If the player assumes events such as 'betting the emperor passes by', put that claim in assumptions instead of treating it as fact.",
            "mechanical_tags should be short tags such as high_rank_target, provocation, information_probe, item_claim, emperor_assumption, retreat, wait.",
            "Do not decide world state. Do not confirm events."
        ],
        "player_input": player_input,
        "current_state": game_state,
        "memory_summary": {
            "long_term_summary": (memory or {}).get("long_term_summary", ""),
            "recent_turns": (memory or {}).get("short_term", [])[-3:],
            "fact_sheet": (memory or {}).get("fact_sheet", "")
        },
        "known_relations": relations or {},
        "inventory": inventory or {"items": []}
    }
    return judge_system, _json_prompt_payload(judge_user)


def _load_gamedata_bundle() -> dict:
    return {
        "npcs": get_npcs(),
        "ranks": get_ranks(),
        "rules": get_rules(),
        "locations": get_locations()
    }


def _rank_level(rank_name: str | None, gamedata: dict) -> int | None:
    if not rank_name:
        return None
    for rank in gamedata.get("ranks", []):
        if rank_name in {rank.get("id"), rank.get("name")}:
            return rank.get("level")
    return None


def _npc_by_name(gamedata: dict) -> dict:
    return {npc.get("name"): npc for npc in gamedata.get("npcs", []) if npc.get("name")}


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


CHOICE_STYLES = {"humble", "probe", "observe", "flatter", "confront", "retreat", "wait", "use_item", "other"}
CHOICE_RISKS = {"low", "medium", "high"}
HIGH_RANK_NPC_LEVEL = 7


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


def plan_world_event(judge_result: dict, game_state: dict, relations: dict | None, gamedata: dict) -> dict:
    status = game_state.get("status", {}) if isinstance(game_state, dict) else {}
    next_turn = int(status.get("turn_count", 0) or 0) + 1
    last_event_turn = int(status.get("last_world_event_turn", 0) or 0)
    if _active_summons(game_state) or next_turn - last_event_turn < 4 or next_turn % 4 != 0:
        return {"type": "none", "description": "", "state_update": {}}

    primary = _primary_npc(
        [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()],
        game_state,
        gamedata,
        relations
    )
    if primary and _hidden_state_for(relations, primary).get("suspicion", 0) >= 60:
        return {
            "type": "overheard",
            "description": "簾外有宮人腳步略停，像是聽見了殿內隻字片語。",
            "state_update": {
                "status_set": {"last_world_event_turn": next_turn},
                "hidden_state_delta": {primary: {"suspicion": 2}}
            }
        }
    return {
        "type": "interruption",
        "description": "殿外傳來短促通報聲，打斷了原本過於安靜的氣氛。",
        "state_update": {"status_set": {"last_world_event_turn": next_turn}}
    }


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


def build_story_prompt(player_input, judge_result, authoritative_result, selected_lore, selected_npcs, game_state, memory):
    selected_names = [npc.get("name") for npc in selected_npcs if isinstance(npc, dict) and npc.get("name")]
    selected_names.extend(authoritative_result.get("relevant_npcs", []) if isinstance(authoritative_result, dict) else [])
    sanitized_state = dict(game_state or {})
    sanitized_state["relations"] = {
        "npcs": (game_state or {}).get("relations", {}).get("npcs", {}),
        "companions": (game_state or {}).get("relations", {}).get("companions", {})
    }
    sanitized_state["hidden_state_cues"] = hidden_state_cues(
        (game_state or {}).get("relations", {}),
        list(dict.fromkeys([name for name in selected_names if name]))
    )
    story_system = (
        "You are AI 2: Story Writer AI for a Discord text game. "
        "Only write player-facing narration and choices from the authoritative ruling. "
        "You are not the judge. Do not change state, overrule rulings, or treat player assumptions as facts. "
        "Do not reveal hidden_state numbers or full hidden_state objects. Express them only through indirect cues. "
        "Output JSON only."
    )
    story_user = {
        "task": "Write the next player-facing story beat and 2-4 strategically different choices.",
        "output_schema": {
            "reply": "給玩家看的劇情文字",
            "choices": [
                {
                    "id": "choice_1",
                    "text": "玩家看到的行動描述",
                    "style": "humble | probe | observe | flatter | confront | retreat | wait | use_item | other",
                    "risk": "low | medium | high",
                    "effect_hint": "玩家可理解的策略效果提示",
                    "mechanical_effect": {
                        "target": "NPC 名稱或狀態名稱",
                        "relation_delta": 0,
                        "suspicion_delta": 0,
                        "anger_delta": 0,
                        "info_gain": 0,
                        "reputation_delta": 0
                    }
                }
            ],
            "state_update": {}
        },
        "hard_rules": [
            "You only write story; you do not decide rules.",
            "Do not overrule authoritative_result.",
            "Do not add major events that are absent from authoritative_result.confirmed_events, npc_actions, world_event, or state_update.",
            "Do not turn judge_result.assumptions into happened facts.",
            "If authoritative_result.denied_assumptions includes an event, the reply must say it did not happen or remains unconfirmed.",
            "Do not reveal hidden_state numeric values, labels, or JSON keys in player-facing prose.",
            "Use hidden_state_cues only as indirect body language, pauses, tone, glances, or servant reactions.",
            "You must include all provided npc_actions and world_event if world_event.type is not none.",
            "If world_event.type is none, do not invent interruptions, arrivals, summons, object discoveries, or overheard events.",
            "Provide 2-4 choices every turn.",
            "Choices must be concrete and actionable, not just emotions or tone swaps.",
            "Choices must have real mechanical differences. Include at least one low risk choice and at least one higher-reward but risky choice.",
            "Discord display will show only text and effect_hint, but JSON must include the full choice schema.",
            "state_update is only a suggestion and may be ignored by code."
        ],
        "player_input": player_input,
        "judge_result": judge_result,
        "authoritative_result": authoritative_result,
        "selected_lore": selected_lore,
        "selected_npcs": selected_npcs,
        "current_state": sanitized_state,
        "memory_summary": {
            "long_term_summary": (memory or {}).get("long_term_summary", ""),
            "recent_turns": (memory or {}).get("short_term", [])[-3:],
            "fact_sheet": (memory or {}).get("fact_sheet", "")
        }
    }
    return story_system, _json_prompt_payload(story_user)


def _choice_lines(choices: list) -> str:
    lines = []
    for index, choice in enumerate(choices[:4], 1):
        text = str(choice.get("text", "")).strip() if isinstance(choice, dict) else ""
        hint = str(choice.get("effect_hint", "")).strip() if isinstance(choice, dict) else ""
        if text:
            if hint:
                lines.append(f"{index}. {text}\n   └ {hint}")
            else:
                lines.append(f"{index}. {text}")
    return "\n".join(lines)


def format_story_reply(story_result: dict) -> str:
    reply = str(story_result.get("reply", "")).strip()
    choices = story_result.get("choices", [])
    choice_text = _choice_lines(choices if isinstance(choices, list) else [])
    if choice_text:
        return f"{reply}\n\n【可選行動】\n{choice_text}"
    return reply


def validate_story_output_reason(story_result, authoritative_result, game_state):
    if not isinstance(story_result, dict):
        return False, "story_result is not an object"
    reply = story_result.get("reply", "")
    if not isinstance(reply, str) or not reply.strip():
        return False, "missing reply"
    choices = story_result.get("choices")
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


def validate_story_output(story_result, authoritative_result, game_state):
    ok, _ = validate_story_output_reason(story_result, authoritative_result, game_state)
    return ok


def fallback_story_result(authoritative_result: dict) -> dict:
    if authoritative_result.get("allowed") is False:
        reason = authoritative_result.get("reason") or "這個行動與目前狀態衝突，未能成立。"
        reply = f"{reason} 宮中局勢仍按已確認的狀態推進，未經裁決的假設不會成為事實。"
    else:
        reply = "宮中消息一時混雜，你先按下心緒，確認眼前可行之事。"
    return {
        "reply": reply,
        "choices": [
            {
                "id": "choice_1",
                "text": "先退半步觀察四周，確認目前有哪些人在場",
                "style": "observe",
                "risk": "low",
                "effect_hint": "降低誤判風險，較可能獲得場面線索。",
                "mechanical_effect": {"target": "scene", "relation_delta": 0, "suspicion_delta": -1, "anger_delta": 0, "info_gain": 1, "reputation_delta": 0}
            },
            {
                "id": "choice_2",
                "text": "委婉詢問身邊可信之人，釐清剛才的狀況",
                "style": "humble",
                "risk": "medium",
                "effect_hint": "可能取得情報，但會暴露你在意此事。",
                "mechanical_effect": {"target": "nearest_ally", "relation_delta": 1, "suspicion_delta": 1, "anger_delta": 0, "info_gain": 1, "reputation_delta": 0}
            },
            {
                "id": "choice_3",
                "text": "直接追問對方話中未盡之意",
                "style": "probe",
                "risk": "high",
                "effect_hint": "若對方鬆口可得關鍵訊息，失敗則容易引人起疑。",
                "mechanical_effect": {"target": "primary_npc", "relation_delta": -1, "suspicion_delta": 4, "anger_delta": 1, "info_gain": 2, "reputation_delta": 0}
            }
        ],
        "state_update": {}
    }


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


def update_memory(user_id, player_input, reply):
    memory = load_player_memory(user_id) or {
        "long_term_summary": "",
        "short_term": [],
        "fact_sheet": "",
        "fact_sheet_items": []
    }
    short_term = memory.get("short_term", [])
    short_term.append({"user": player_input, "bot": reply})
    memory["short_term"] = short_term
    save_player_data(user_id, "memory", memory)
    manage_memory(user_id)
    memory = load_player_memory(user_id)
    if memory and len(memory.get("short_term", [])) > 10:
        memory["short_term"] = memory["short_term"][-10:]
        save_player_data(user_id, "memory", memory)


def _run_dual_ai_gameplay_selftest() -> dict:
    gamedata = _load_gamedata_bundle()
    base_state = {
        "profile": {"rank": "貴人"},
        "status": {"turn_count": 1},
        "location": "偏殿",
        "attributes": {"聲望": 30},
        "scene_npcs": ["皇后"],
        "relations": {
            "npcs": {"皇后": {"好感度": 0, "恩怨": "無", "emotion_state": {"anger": 0, "fear": 0}, "alive": True}},
            "companions": {},
            "hidden_state": {"皇后": {"suspicion": 75, "interest": 20, "anger": 10, "trust": 0, "test_intent": False}}
        },
        "history_summary": "",
        "input_type": "NORMAL"
    }
    inventory = {"items": ["家傳玉佩"]}
    judge = {
        "intent": "反問皇后為何試探自己",
        "player_intent": "反問皇后為何試探自己",
        "action_type": "ask",
        "social_tone": "probing",
        "risk_level": "high",
        "possible_misread": "皇后可能認為玩家頂撞",
        "mentioned_npcs": ["皇后"],
        "mentioned_items": [],
        "assumptions": [],
        "risk_flags": [],
        "mechanical_tags": ["high_rank_target", "information_probe"]
    }
    authoritative = resolve_rules(judge, base_state, {}, base_state["relations"], inventory, gamedata)
    valid_story = {
        "reply": "皇后指尖在茶盞旁略停，並未把話說破，只讓身側宮女多看了你一眼。皇上經過一事尚未確認，殿中也沒有因此起新的動靜。",
        "choices": [
            {
                "id": "choice_1",
                "text": "垂首請安，先順著皇后的話應下",
                "style": "humble",
                "risk": "low",
                "effect_hint": "穩住場面，降低被視為頂撞的可能。",
                "mechanical_effect": {"target": "皇后", "relation_delta": 1, "suspicion_delta": -1, "anger_delta": 0, "info_gain": 0, "reputation_delta": 0}
            },
            {
                "id": "choice_2",
                "text": "細問皇后方才所指，試探她真正介意的地方",
                "style": "probe",
                "risk": "high",
                "effect_hint": "有機會逼近關鍵訊息，但容易引起戒心。",
                "mechanical_effect": {"target": "皇后", "relation_delta": -1, "suspicion_delta": 4, "anger_delta": 1, "info_gain": 2, "reputation_delta": 0}
            }
        ],
        "state_update": {}
    }
    dead_state = json.loads(json.dumps(base_state, ensure_ascii=False))
    dead_state["relations"]["npcs"]["皇后"]["alive"] = False
    dead_result = resolve_rules(judge, dead_state, {}, dead_state["relations"], inventory, gamedata)
    old_relations = ensure_hidden_state({"npcs": {}, "companions": {}}, gamedata, base_state, "")
    return {
        "A_high_suspicion_npc_tests": any(a.get("action") == "test_player" for a in authoritative.get("npc_actions", [])),
        "B_high_risk_has_cost": bool(authoritative["state_update"].get("hidden_state_delta", {}).get("皇后")),
        "C_choices_strategy_valid": validate_story_output(valid_story, authoritative, base_state),
        "D_hidden_numbers_rejected": not validate_story_output({**valid_story, "reply": "皇后 suspicion: 75，仍盯著你。"}, authoritative, base_state),
        "E_emperor_assumption_denied": "皇上已經經過或到場" in resolve_rules({**judge, "assumptions": ["皇上經過"]}, base_state, {}, base_state["relations"], inventory, gamedata)["denied_assumptions"],
        "F_dead_npc_has_no_actions": not dead_result.get("npc_actions"),
        "G_old_player_hidden_state_initialized": bool(old_relations.get("hidden_state"))
    }


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

# ============================================================
# UI 組件
# ============================================================
=======
# safe_response_text 已由 call_openrouter() 內建容錯取代


# --- UI 組件 ---
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

class StartModal(discord.ui.Modal):
    def __init__(self, gender, family):
        super().__init__(title=f"🏮 建立身分：{gender}性 🏮")
        self.gender = gender
        self.family = family

    p_name = discord.ui.TextInput(
        label='名諱',
        placeholder='請輸入你在宮中的稱呼...',
        min_length=2,
        max_length=10
    )

    p_appearance = discord.ui.TextInput(
        label='外貌描述',
        placeholder='請簡單描述你的外貌特徵...',
        min_length=5,
        max_length=50,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.p_name.value
        appearance = self.p_appearance.value

        bonus = self.family.get("starting_bonus", {})
        user_id = interaction.user.id

        get_player_folder(user_id)

        # 1. profile.json
        profile = {
            "name": name,
            "gender": self.gender,
            "family": self.family["id"],
            "family_name": self.family["name"],
            "family_description": self.family["description"],
            "appearance": appearance,
            "rank": self.family["rank"]
        }
        save_player_data(user_id, 'profile', profile)

        # 2. status.json
        status = {
            "alive": True,
            "location": "偏殿",
            "location_id": "",
            "attributes": {
                "體力": bonus.get("體力", 100),
                "權謀": bonus.get("權謀", 10),
                "聲望": bonus.get("聲望", 0),
                "財產": bonus.get("財產", 0)
            },
            "core": {
                "world_view": "清宮後宮世界觀：權力鬥爭、位階分明、爾虞我詐",
                "initial_attributes": {
                    "體力": bonus.get("體力", 100),
                    "權謀": bonus.get("權謀", 10),
                    "聲望": bonus.get("聲望", 0),
                    "財產": bonus.get("財產", 0)
                }
            }
        }
        save_player_data(user_id, 'status', status)

<<<<<<< HEAD
        # 3. memory.json — 加入 fact_sheet 欄位
=======
        # 3. memory.json
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        memory = {
            "long_term_summary": "",
            "short_term": [],
            "fact_sheet": "",
            "fact_sheet_items": []
        }
        save_player_data(user_id, 'memory', memory)

        # 4. inventory.json
        inventory = {"items": ["家傳玉佩"]}
        save_player_data(user_id, 'inventory', inventory)

        # 5. relations.json
<<<<<<< HEAD
        relations = {"npcs": {}, "companions": {}}
=======
        relations = {"npcs": {}}
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        save_player_data(user_id, 'relations', relations)

        # 顯示創角 Embed
        embed = discord.Embed(title=f"【 {name} 】之入宮檔案", color=0x800000)
        embed.add_field(name="家世", value=self.family["name"], inline=True)
        embed.add_field(name="位階", value=self.family["rank"], inline=True)
        embed.add_field(name="外貌", value=appearance, inline=False)
        embed.add_field(name="優勢", value="、".join(
            self.family["advantages"]), inline=False)
        embed.add_field(name="劣勢", value="、".join(
            self.family["disadvantages"]), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        # 生成角色背景描述
        bg_system = "你是一位清宮小說家，請根據玩家資料生成一段一百五十字以內、古風、沉浸感強的角色背景描述，以第三人稱敘述，不要有任何 AI 或機器人語氣。"
        bg_user = (
            f"名諱：{name}\n性別：{self.gender}\n"
            f"家世：{self.family['name']}，{self.family['description']}\n外貌：{appearance}"
        )
        char_desc = await call_gemini(bg_system, bg_user, model=BASE_MODEL, max_tokens=300) or "（角色描述生成失敗）"

        await interaction.channel.send(f"**身分背景**\n\n{char_desc}")

        opening = self.family.get("opening", "")
        await interaction.channel.send(content=opening)

<<<<<<< HEAD
        # 將開場存入短期記憶（user 欄使用自然語句，避免 Gemini 困惑）
        initial_scene = f"{char_desc}\n\n{opening}"
=======
        # 將開場存入短期記憶
        initial_scene = f"【創角】{char_desc}\n\n{opening}"
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        memory = load_player_data(user_id, 'memory')
        if memory:
            memory['short_term'].append({
                "user": "【開場】請描述我初入宮廷時的第一幕場景，從此刻起我正式踏入這座深宮。",
                "bot": initial_scene
            })
            save_player_data(user_id, 'memory', memory)


class FamilySelect(discord.ui.Select):
    def __init__(self, families, gender):
        self.families = families
        self.gender = gender
        options = [
            discord.SelectOption(
                label=f["label"],
                description=f["description"][:50],
                value=f["id"]
            ) for f in families
        ]
        super().__init__(placeholder="請選擇你的家世背景...", options=options)

    async def callback(self, interaction: discord.Interaction):
        family_id = self.values[0]
        family = next(f for f in self.families if f["id"] == family_id)
        await interaction.response.send_modal(StartModal(self.gender, family))


class GenderSelect(discord.ui.Select):
    def __init__(self, families):
        self.families = families
        options = [
            discord.SelectOption(label="女"),
            discord.SelectOption(label="男")
        ]
        super().__init__(placeholder="請選擇你的身分...", options=options)

    async def callback(self, interaction: discord.Interaction):
        gender = self.values[0]
        view = FamilySelectView(self.families, gender)
        await interaction.response.send_message("請選擇你的家世背景：", view=view, ephemeral=True)


class FamilySelectView(discord.ui.View):
    def __init__(self, families, gender):
        super().__init__()
        self.add_item(FamilySelect(families, gender))


class GenderView(discord.ui.View):
    def __init__(self, families):
        super().__init__()
        self.add_item(GenderSelect(families))


<<<<<<< HEAD
# ============================================================
# Bot 設定
# ============================================================
=======
# --- Bot 設定 ---
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

class HaremBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()


bot = HaremBot()


# ============================================================
# 指令
# ============================================================

@bot.tree.command(name="start", description="開始遊戲並建立身分")
async def start(interaction: discord.Interaction):
    if player_exists(interaction.user.id):
        await interaction.response.send_message("你已在宮中，不得重新投胎。", ephemeral=True)
    else:
        families = get_families()
        await interaction.response.send_message(
            "「命運之書」已開啟，請先選擇你的身世：",
            view=GenderView(families),
            ephemeral=True
        )


@bot.tree.command(name="help", description="查看操作指南")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🏮 紫禁城生存手冊", color=0x2b2d31)
    embed.add_field(name="`/start`", value="建立身分與開啟故事", inline=False)
    embed.add_field(name="`/profile`", value="查看屬性與裝備", inline=False)
    embed.add_field(name="`/ooc <修正內容>`",
                    value="直接與 AI 溝通，糾正劇情錯誤（自動更新事實清單）", inline=False)
    embed.add_field(name="`/relation <NPC名> <數值>`",
                    value="手動調整與指定 NPC 的好感度（正負皆可）", inline=False)
    embed.set_footer(text="直接在頻道中輸入行動，Bot 會推演劇情。")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="profile", description="查看人物表")
async def profile(interaction: discord.Interaction):
    profile = load_player_profile(interaction.user.id)
    status = load_player_status(interaction.user.id)
    inventory = load_player_inventory(interaction.user.id)

    if not profile:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return

    embed = discord.Embed(title=f"角色資訊：{profile['name']}", color=0xdaa520)
    embed.add_field(name="家世", value=profile['family_name'], inline=True)
    embed.add_field(name="位階", value=profile['rank'], inline=True)

    if status:
        attr_text = "\n".join(
            [f"{k}: {v}" for k, v in status.get('attributes', {}).items()])
        embed.add_field(name="數值", value=attr_text, inline=True)
        embed.add_field(name="位置", value=status.get(
            'location', '未知'), inline=True)
        embed.add_field(name="生死", value="存活" if status.get(
            'alive', True) else "已故", inline=True)

    if inventory:
        items = inventory.get('items', [])
        embed.add_field(name="倉庫", value="、".join(
            items) if items else "空", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ooc", description="直接與 AI 溝通，糾正劇情錯誤")
async def ooc(interaction: discord.Interaction, *, correction: str):
    profile = load_player_profile(interaction.user.id)
    status = load_player_status(interaction.user.id)
    memory = load_player_memory(interaction.user.id)

    if not profile:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return

    short_term = memory.get('short_term', []) if memory else []
    if not short_term:
        await interaction.response.send_message("尚無劇情紀錄，無法撤回。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # 移除最後一筆錯誤紀錄
    last_exchange = short_term.pop()
    if memory:
        memory['short_term'] = short_term
        save_player_data(interaction.user.id, 'memory', memory)

<<<<<<< HEAD
=======
    # 取得遊戲規則並組裝 system instruction
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
    game_rules = format_game_rules()
    gm_system = make_gm_system_instruction(game_rules)

    location = status.get('location', '未知') if status else '未知'
    attributes = status.get('attributes', {}) if status else {}
<<<<<<< HEAD
    # ── 修正3：只保留最近 3 輪 ──
    history_summary = build_history_summary(short_term)
    npc_database = format_selected_npc_data(select_relevant_npcs(location, correction, load_player_relations(interaction.user.id)))
    # ── 修正2：注入事實清單 ──
    fact_sheet = load_fact_sheet(interaction.user.id)
    fact_section = f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n已確認事實清單（最高優先級，不得違背）\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{fact_sheet if fact_sheet else '（尚無修正記錄）'}\n" if fact_sheet else ""
=======
    history_summary = build_history_summary(short_term)
    npc_database = soften_content(format_npc_data())
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

    ooc_template = get_script("templates", "ooc_correction")
    full_prompt = ooc_template.format(
        correction=correction,
<<<<<<< HEAD
        last_scene=last_exchange.get('bot', '[無紀錄]')[:200],
=======
        last_scene=soften_content(last_exchange.get('bot', '[無紀錄]')[:200]),
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        name=profile['name'],
        background=profile['family_description'],
        location=location,
        attributes=attributes,
        npc_database=npc_database,
        history_summary=history_summary,
<<<<<<< HEAD
    ) + fact_section
=======
    )
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

    try:
        text = await call_gemini(gm_system, full_prompt)
        if not text:
            await interaction.channel.send("⚠️ 修正劇情觸動禁忌，無法生成，請換個修正方向。")
            return

        await interaction.channel.send(
            f"🔄 **劇情修正**\n> 修正意見：{correction}\n\n{text}"
        )

<<<<<<< HEAD
        # ── 修正2：更新事實清單 ──
        update_fact_sheet(interaction.user.id, correction, text[:80])

=======
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
        # 儲存修正後的劇情
        short_term.append({"user": f"[OOC修正] {correction}", "bot": text})
        short_term = short_term[-10:]
        if memory:
            memory['short_term'] = short_term
            save_player_data(interaction.user.id, 'memory', memory)

    except Exception as e:
        await interaction.channel.send(f"⚠️ 修正失敗：{e}")


@bot.tree.command(name="op", description="GM 指令 - 直接修改遊戲狀態")
async def op_cmd(interaction: discord.Interaction, *, command: str):
    profile = load_player_profile(interaction.user.id)
    status = load_player_status(interaction.user.id)
    relations = load_player_relations(interaction.user.id)
    inventory = load_player_inventory(interaction.user.id)
    memory = load_player_memory(interaction.user.id)

    if not profile:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    game_rules = format_game_rules()
    gm_system = make_gm_system_instruction(game_rules)

    short_term = memory.get('short_term', []) if memory else []
    history_summary = build_history_summary(short_term)

    op_template = get_script("templates", "op_command")
    full_prompt = op_template.format(
        command=command,
        game_rules=game_rules,
        name=profile['name'],
        background=profile['family_description'],
        rank=profile['rank'],
        location=status.get('location', '未知') if status else '未知',
        attributes=status.get('attributes', {}) if status else {},
        inventory_items=inventory.get('items', []) if inventory else [],
        relations_npcs=relations.get('npcs', {}) if relations else {},
        history_summary=history_summary,
    )

    try:
        text = await call_gemini(gm_system, full_prompt)
        if not text:
            await interaction.channel.send("⚠️ 指令執行被攔截，請調整指令內容後重試。")
            return

        await interaction.channel.send(f"⚡ **GM 指令執行**\n> 指令：{command}\n\n{text}")

        if memory:
            short_term.append({"user": f"[OP] {command}", "bot": text})
            short_term = short_term[-10:]
            memory['short_term'] = short_term
            save_player_data(interaction.user.id, 'memory', memory)

    except Exception as e:
        await interaction.channel.send(f"⚠️ 指令執行失敗：{e}")


<<<<<<< HEAD
@bot.tree.command(name="relation", description="手動調整與 NPC 的好感度（GM 校正用）")
@app_commands.describe(npc="NPC 名稱", delta="好感度變化（正數增加，負數減少）")
async def relation_cmd(interaction: discord.Interaction, npc: str, delta: int):
    if not load_player_profile(interaction.user.id):
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return
    update_npc_affection(interaction.user.id, npc, delta)
    relations = load_player_relations(interaction.user.id)
    new_val = relations['npcs'].get(npc, {}).get('好感度', '未知') if relations else '未知'
    tier = _affection_tier(new_val) if isinstance(new_val, int) else ''
    await interaction.response.send_message(
        f"✅ {npc} 好感度調整 {delta:+d}，目前：{new_val}（{tier}）", ephemeral=True
    )


# ============================================================
# 訊息處理（核心流程）
# ── 修正1：指令分類 → 修正4：情緒偵測 → 組裝 prompt ──
# ============================================================
=======
# --- 訊息處理 ---
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    profile = load_player_profile(message.author.id)
    status = load_player_status(message.author.id)
    memory = load_player_memory(message.author.id)

    if profile and not message.content.startswith('!'):
        async with message.channel.typing():
            try:
<<<<<<< HEAD
=======
                # 取得遊戲規則並組裝 system instruction
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
                game_rules = format_game_rules()
                gm_system = make_gm_system_instruction(game_rules)

<<<<<<< HEAD
                long_term = memory.get('long_term_summary', '') if memory else ''
=======
                # 讀取記憶與狀態
                long_term = memory.get(
                    'long_term_summary', '') if memory else ''
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)
                short_term = memory.get('short_term', []) if memory else []

                location = status.get('location', '未知') if status else '未知'
                attributes = status.get('attributes', {}) if status else {}

                relations = load_player_relations(message.author.id)
                player_relations_str = format_player_relations(relations)

<<<<<<< HEAD
                scene_npcs_str = get_scene_npcs(location)
                scene_npc_list = [n.strip() for n in scene_npcs_str.split('、') if n.strip() and n != '無']

                # ── 修正3：只注入最近 3 輪 ──
                history_summary = build_history_summary(short_term)

                # ── 修正2：注入事實清單 ──
                fact_sheet = load_fact_sheet(message.author.id)

                # ── 修正1：辨識指令類型 ──
                input_type, cleaned_action = classify_player_input(message.content)

                # ── 好感度自動偵測（雙軌制 — 關鍵字軌）──
                affection_delta = detect_affection_change(message.content)
                if affection_delta != 0 and scene_npc_list:
                    for npc_name in scene_npc_list:
                        update_npc_affection(message.author.id, npc_name, affection_delta)
                    relations = load_player_relations(message.author.id)
                    player_relations_str = format_player_relations(relations)

                # ── 修正4：偵測極端行為並更新 NPC 情緒 ──
                extreme_flags = detect_extreme_action(message.content)
                emotion_override = ""
                if (extreme_flags['is_insult'] or extreme_flags['is_violence']) and scene_npc_list:
                    updated_relations, triggered_npcs = update_npc_emotions(
                        message.author.id, scene_npc_list, extreme_flags
                    )
                    relations = updated_relations
                    player_relations_str = format_player_relations(relations)
                    emotion_override = build_emotion_override(triggered_npcs)

                game_state = {
                    "profile": profile,
                    "status": status or {},
                    "location": location,
                    "attributes": attributes,
                    "scene_npcs": scene_npc_list,
                    "relations": relations or {"npcs": {}, "companions": {}},
                    "history_summary": history_summary,
                    "input_type": input_type
                }
                inventory = load_player_inventory(message.author.id) or {"items": []}
                gamedata = _load_gamedata_bundle()
                relations = ensure_hidden_state(relations, gamedata, game_state, cleaned_action)
                save_player_data(message.author.id, "relations", relations)
                game_state["relations"] = relations

                judge_system, judge_prompt = build_judge_prompt(
                    cleaned_action,
                    game_state,
                    memory,
                    relations,
                    inventory
                )
                judge_result = await call_judge_ai(judge_system, judge_prompt)

                authoritative_result = resolve_rules(
                    judge_result,
                    game_state,
                    memory,
                    relations,
                    inventory,
                    gamedata
                )

                selected_npcs = select_relevant_npcs(location, cleaned_action, relations)
                selected_lore = {
                    "game_rules": game_rules,
                    "fact_sheet": fact_sheet,
                    "player_relations": player_relations_str,
                    "emotion_override": emotion_override,
                    "history_summary": history_summary,
                    "long_term_summary": long_term
                }
                story_system, story_prompt = build_story_prompt(
                    cleaned_action,
                    judge_result,
                    authoritative_result,
                    selected_lore,
                    selected_npcs,
                    game_state,
                    memory
                )

                story_result = await call_story_ai(story_system, story_prompt)
                ok, last_error = validate_story_output_reason(story_result, authoritative_result, game_state)
                if not ok:
                    retry_prompt = (
                        story_prompt
                        + f"\n\nPrevious story output failed validation: {last_error}. "
                        + "Return corrected JSON only, preserving authoritative_result."
                    )
                    story_result = await call_story_ai(story_system, retry_prompt)
                    ok, last_error = validate_story_output_reason(story_result, authoritative_result, game_state)

                if not ok:
                    story_result = fallback_story_result(authoritative_result)

                text = format_story_reply(story_result)
                await message.reply(text)

                apply_state_update(message.author.id, authoritative_result["state_update"])

                # 追蹤 AI 回應中出現的隨侍人物
                update_companion_tracking(message.author.id, story_result.get("reply", ""))

                update_memory(message.author.id, message.content, text)
=======
                # 篩選當前場景的 NPC，軟化所有動態內容
                scene_npcs = get_scene_npcs(location)
                npc_database = soften_content(format_npc_data())
                player_relations = soften_content(player_relations)
                long_term_clean = soften_content(long_term)
                history_summary = build_history_summary(short_term)

                # 組裝 action_prompt
                template = get_script("templates", "action_prompt")
                action_prompt = template.format(
                    gm_prompt="",
                    npc_database=npc_database,
                    player_relations=player_relations,
                    name=profile['name'],
                    location=location,
                    scene_npcs=scene_npcs,
                    attributes=attributes,
                    action=message.content,
                    history_summary=history_summary,
                    long_term_summary=long_term_clean,
                    core_settings=""
                )

                text = await call_gemini(gm_system, action_prompt)
                if not text:
                    await message.reply("⚠️ 此段劇情觸動禁忌，宮中傳訊受阻，請換個方向行動。")
                    return

                await message.reply(text)

                # 更新短期記憶（只保留最近 10 筆）
                if memory:
                    short_term.append({"user": message.content, "bot": text})
                    short_term = short_term[-10:]
                    memory['short_term'] = short_term
                    save_player_data(message.author.id, 'memory', memory)

                    # 觸發滾動記憶管理
                    manage_memory(message.author.id)
>>>>>>> acd070b (改進雞同鴨講的問題 重寫prompt)

            except Exception as e:
                print(f"Error: {e}")
                await message.reply("⚠️ 宮中傳訊受阻，請稍後再試。")

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)
