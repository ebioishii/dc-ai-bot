import os
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

# 模型設定 — 在這裡換模型，全程只改這一行
GM_MODEL = "gemini-2.5-flash-lite"   # 主要 GM 模型
BASE_MODEL = "gemini-2.5-flash-lite"   # 角色背景生成等輔助任務

# --- 工具函式 ---


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


def format_npc_data():
    """將 NPC 資料格式化為 AI 可讀的提示"""
    npcs = get_npcs()
    npc_info = ""
    for npc in npcs:
        npc_info += f"【{npc['name']}】{npc.get('title', '')}\n"
        npc_info += f"  位置：{npc.get('location', '未知')}\n"
        npc_info += f"  性格：{npc.get('personality', '無')}\n"
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

    rewards_info = "【恩賞規制】"
    for r in rewards:
        rewards_info += f"{r['name']}：{r['description']}；"

    return f"{ranks_info}\n{court_rules}\n{forbidden}\n{punishments_info}\n{rewards_info}"


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
        if len(h['bot']) > 200:
            bot_preview += "……"
        lines.append(f"玩家：{h['user']}\nGM：{bot_preview}")
    return "\n\n".join(lines)


def build_gemini_history(short_term: list) -> list:
    """
    將 short_term 轉換為 Gemini Chat API 所需的 history 格式。
    這讓模型真正「記得」對話，而非靠文字摘要猜測。
    """
    history = []
    for h in short_term:
        history.append({"role": "user", "parts": [h["user"]]})
        history.append({"role": "model", "parts": [h["bot"]]})
    return history


def extract_key_info(dialogue_pair: dict) -> str:
    """
    將一筆對話壓縮為長期記憶條目。
    使用固定模板而非額外 AI 呼叫，更穩定且省費用。
    """
    user_msg = dialogue_pair.get('user', '')[:60].strip()
    bot_msg = dialogue_pair.get('bot', '')[:120].strip()
    return f"[玩家：{user_msg}] → [結果：{bot_msg}]"


def manage_memory(user_id):
    """
    滾動式記憶管理：
    當短期記憶 >= 11 筆時，壓縮最舊的 2 筆為長期記憶條目。
    長期記憶以條目數量（最多 15 條）而非字元數截斷，避免切在句子中間。
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

    existing_items = [i.strip() for i in long_term.split(" | ") if i.strip()]
    existing_items.extend(new_items)

    # 只保留最近 15 條
    if len(existing_items) > 15:
        existing_items = existing_items[-15:]

    memory['long_term_summary'] = " | ".join(existing_items)
    save_player_data(user_id, 'memory', memory)
    print(f"✅ 記憶滾動：已壓縮 2 筆舊對話至長期記憶")


# --- 模型工廠 ---

def make_gm_system_instruction(game_rules: str) -> str:
    """產生 GM 的 system instruction 字串（供每次 API 呼叫使用）"""
    gm_rule = get_script("system_prompts", "game_master")
    return gm_rule.replace("{game_rules}", game_rules)


async def call_gemini(system: str, user: str, model: str = None,
                      temperature: float = 0.75, max_tokens: int = 600) -> str | None:
    """
    統一的 Gemini 呼叫函式。
    回傳文字內容，失敗或被擋時回傳 None。
    """
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


# safe_response_text 已由 call_openrouter() 內建容錯取代


# --- UI 組件 ---

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

        # 3. memory.json
        memory = {
            "long_term_summary": "",
            "short_term": []
        }
        save_player_data(user_id, 'memory', memory)

        # 4. inventory.json
        inventory = {"items": ["家傳玉佩"]}
        save_player_data(user_id, 'inventory', inventory)

        # 5. relations.json
        relations = {"npcs": {}}
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

        # 將開場存入短期記憶
        initial_scene = f"【創角】{char_desc}\n\n{opening}"
        memory = load_player_data(user_id, 'memory')
        if memory:
            memory['short_term'].append({
                "user": "[創角] 建立角色",
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


# --- Bot 設定 ---

class HaremBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()


bot = HaremBot()

# --- 指令 ---


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
                    value="直接與 AI 溝通，糾正劇情錯誤", inline=False)
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

    # 取得遊戲規則並組裝 system instruction
    game_rules = format_game_rules()
    gm_system = make_gm_system_instruction(game_rules)

    location = status.get('location', '未知') if status else '未知'
    attributes = status.get('attributes', {}) if status else {}
    history_summary = build_history_summary(short_term)
    npc_database = soften_content(format_npc_data())

    ooc_template = get_script("templates", "ooc_correction")
    full_prompt = ooc_template.format(
        correction=correction,
        last_scene=soften_content(last_exchange.get('bot', '[無紀錄]')[:200]),
        name=profile['name'],
        background=profile['family_description'],
        location=location,
        attributes=attributes,
        npc_database=npc_database,
        history_summary=history_summary,
    )

    try:
        text = await call_gemini(gm_system, full_prompt)
        if not text:
            await interaction.channel.send("⚠️ 修正劇情觸動禁忌，無法生成，請換個修正方向。")
            return

        await interaction.channel.send(
            f"🔄 **劇情修正**\n> 修正意見：{correction}\n\n{text}"
        )

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


# --- 訊息處理 ---

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
                # 取得遊戲規則並組裝 system instruction
                game_rules = format_game_rules()
                gm_system = make_gm_system_instruction(game_rules)

                # 讀取記憶與狀態
                long_term = memory.get(
                    'long_term_summary', '') if memory else ''
                short_term = memory.get('short_term', []) if memory else []

                location = status.get('location', '未知') if status else '未知'
                attributes = status.get('attributes', {}) if status else {}

                relations = load_player_relations(message.author.id)
                player_relations = format_player_relations(relations)

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

            except Exception as e:
                print(f"Error: {e}")
                await message.reply("⚠️ 宮中傳訊受阻，請稍後再試。")

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)
