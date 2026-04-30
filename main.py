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

genai.configure(api_key=GEMINI_API_KEY)

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


def get_strategies():
    with open('gamedata/strategies.json', 'r', encoding='utf-8') as f:
        return json.load(f).get('strategies', [])


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


def get_scene_npcs(location: str) -> str:
    """取得當前場景中的 NPC 名單"""
    npcs = get_npcs()
    scene = [npc['name'] for npc in npcs if npc.get('location') == location]
    return "、".join(scene) if scene else "無"


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
            rel_info += f"• {npc_id}：好感度 {好感度}（{tier}），恩怨：{恩怨}，憤怒：{anger}，恐懼：{fear}\n"

    active_companions = {k: v for k, v in companions.items() if v.get('appear_count', 0) >= 3}
    if active_companions:
        rel_info += "\n【玩家身旁已知隨侍】\n"
        for name, data in active_companions.items():
            rel_info += f"• {name}（{data.get('role', '隨侍')}）：{data.get('desc', '無額外描述')}\n"

    return rel_info if rel_info.strip() else "（尚無記錄的 NPC 關係）"


# ============================================================
# 規則格式化
# ============================================================

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

    punishments_info = "【責處規制】"
    for p in punishments:
        punishments_info += f"{p['name']}：{p['description']}；"

    rewards_info = "【恩賞規制】"
    for r in rewards:
        rewards_info += f"{r['name']}：{r['description']}；"

    return f"{ranks_info}\n{court_rules}\n{forbidden}\n{punishments_info}\n{rewards_info}"


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
                'emotion_state': {'anger': 0, 'fear': 0}
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
            'emotion_state': {'anger': 0, 'fear': 0}
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
        if len(h['bot']) > 200:
            bot_preview += "……"
        lines.append(f"玩家：{h['user']}\nGM：{bot_preview}")
    return "\n\n".join(lines)


def build_gemini_history(short_term: list) -> list:
    """將 short_term 轉換為 Gemini Chat API 所需的 history 格式。"""
    history = []
    for h in short_term:
        history.append({"role": "user", "parts": [h["user"]]})
        history.append({"role": "model", "parts": [h["bot"]]})
    return history


def extract_key_info(dialogue_pair: dict) -> str:
    user_msg = dialogue_pair.get('user', '')
    user_msg = re.sub(r'^\[.*?\]\s*|^【.*?】\s*', '', user_msg)[:80].strip()
    bot_msg = dialogue_pair.get('bot', '')[:180].strip()
    return f"[玩家：{user_msg}] → [場景：{bot_msg}]"


def manage_memory(user_id):
    """
    滾動式記憶管理：
    當短期記憶 >= 11 筆時，壓縮最舊的 2 筆為長期記憶條目。
    長期記憶以帶編號列表儲存（最多 15 條）。
    """
    memory = load_player_memory(user_id)
    if not memory:
        return

    short_term = memory.get('short_term', [])
    long_term = memory.get('long_term_summary', '')

    if len(short_term) < 11:
        return

    old_dialogues = short_term[:2]
    memory['short_term'] = short_term[2:]

    new_items = [extract_key_info(d) for d in old_dialogues]

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
    save_player_data(user_id, 'memory', memory)
    print(f"✅ 記憶滾動：已壓縮 2 筆舊對話至長期記憶")


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


async def call_gemini(system: str, user: str, model: str = None,
                      temperature: float = 0.75, max_tokens: int = 600) -> str | None:
    """統一的 Gemini 呼叫函式。回傳文字內容，失敗或被擋時回傳 None。"""
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


# ============================================================
# UI 組件
# ============================================================

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

        # 3. memory.json — 加入 fact_sheet 欄位
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
        relations = {"npcs": {}, "companions": {}}
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

        # 將開場存入短期記憶（user 欄使用自然語句，避免 Gemini 困惑）
        initial_scene = f"{char_desc}\n\n{opening}"
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


# ============================================================
# Bot 設定
# ============================================================

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

    game_rules = format_game_rules()
    gm_system = make_gm_system_instruction(game_rules)

    location = status.get('location', '未知') if status else '未知'
    attributes = status.get('attributes', {}) if status else {}
    # ── 修正3：只保留最近 3 輪 ──
    history_summary = build_history_summary(short_term)
    npc_database = format_npc_data()
    # ── 修正2：注入事實清單 ──
    fact_sheet = load_fact_sheet(interaction.user.id)
    fact_section = f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n已確認事實清單（最高優先級，不得違背）\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{fact_sheet if fact_sheet else '（尚無修正記錄）'}\n" if fact_sheet else ""

    ooc_template = get_script("templates", "ooc_correction")
    full_prompt = ooc_template.format(
        correction=correction,
        last_scene=last_exchange.get('bot', '[無紀錄]')[:200],
        name=profile['name'],
        background=profile['family_description'],
        location=location,
        attributes=attributes,
        npc_database=npc_database,
        history_summary=history_summary,
    ) + fact_section

    try:
        text = await call_gemini(gm_system, full_prompt)
        if not text:
            await interaction.channel.send("⚠️ 修正劇情觸動禁忌，無法生成，請換個修正方向。")
            return

        await interaction.channel.send(
            f"🔄 **劇情修正**\n> 修正意見：{correction}\n\n{text}"
        )

        # ── 修正2：更新事實清單 ──
        update_fact_sheet(interaction.user.id, correction, text[:80])

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
                game_rules = format_game_rules()
                gm_system = make_gm_system_instruction(game_rules)

                long_term = memory.get('long_term_summary', '') if memory else ''
                short_term = memory.get('short_term', []) if memory else []

                location = status.get('location', '未知') if status else '未知'
                attributes = status.get('attributes', {}) if status else {}

                relations = load_player_relations(message.author.id)
                player_relations_str = format_player_relations(relations)

                scene_npcs_str = get_scene_npcs(location)
                scene_npc_list = [n.strip() for n in scene_npcs_str.split('、') if n.strip() and n != '無']
                npc_database = format_npc_data()

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

                # 組裝 action_prompt
                template = get_script("templates", "action_prompt")
                gm_prompt_text = (
                    "【本輪敘事規則】"
                    "直接接續上一幕最後一刻；已登場的人物無需重新出場或介紹，繼續推進劇情；"
                    "禁止重述上一輪已說過的台詞或場景描述。"
                )
                action_prompt = template.format(
                    gm_prompt=gm_prompt_text,
                    npc_database=npc_database,
                    player_relations=player_relations_str,
                    name=profile['name'],
                    location=location,
                    scene_npcs=scene_npcs_str,
                    attributes=attributes,
                    action=cleaned_action,
                    history_summary=history_summary,
                    long_term_summary=long_term,
                    core_settings=""
                )

                # ── 附加強制覆蓋區塊（修正1 + 修正2 + 修正4）──
                overrides = []

                if input_type == 'KILL_CMD':
                    overrides.append(
                        "━━ 殺戮指令強制執行 ━━\n"
                        "玩家已明確下達殺戮指令。目標 NPC 必須在本輪劇情中真實死亡，"
                        "世界狀態須即時更新。此後任何輪次中，該 NPC 均已死亡，不得以任何形式復活。\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )

                if fact_sheet:
                    overrides.append(
                        f"━━ 已確認事實清單（最高優先級）━━\n{fact_sheet}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )

                if emotion_override:
                    overrides.append(emotion_override)

                if overrides:
                    action_prompt += "\n\n" + "\n\n".join(overrides)

                text = await call_gemini(gm_system, action_prompt)
                if not text:
                    await message.reply("⚠️ 此段劇情觸動禁忌，宮中傳訊受阻，請換個方向行動。")
                    return

                await message.reply(text)

                # 追蹤 AI 回應中出現的隨侍人物
                update_companion_tracking(message.author.id, text)

                # 更新短期記憶（只保留最近 10 筆）
                if memory:
                    short_term.append({"user": message.content, "bot": text})
                    short_term = short_term[-10:]
                    memory['short_term'] = short_term
                    save_player_data(message.author.id, 'memory', memory)

                    manage_memory(message.author.id)

            except Exception as e:
                print(f"Error: {e}")
                await message.reply("⚠️ 宮中傳訊受阻，請稍後再試。")

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)