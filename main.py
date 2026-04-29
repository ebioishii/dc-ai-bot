import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import google.generativeai as genai

# --- 環境設定 ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-pro')

# --- 工具函式 ---


def get_script(category, key):
    with open('gamedata/scripts.json', 'r', encoding='utf-8') as f:
        return json.load(f)[category][key]


def get_player_folder(user_id):
    """取得玩家資料夾路徑"""
    folder = f'players/{user_id}'
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder


def save_player_data(user_id, data_type, data):
    """儲存玩家特定類型的資料"""
    folder = get_player_folder(user_id)
    with open(f'{folder}/{data_type}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_player_data(user_id, data_type):
    """讀取玩家特定類型的資料"""
    path = f'players/{user_id}/{data_type}.json'
    return json.load(open(path, 'r', encoding='utf-8')) if os.path.exists(path) else None


def player_exists(user_id):
    """檢查玩家是否存在"""
    profile_path = f'players/{user_id}/profile.json'
    return os.path.exists(profile_path)


def load_player_profile(user_id):
    """讀取玩家基本資料"""
    return load_player_data(user_id, 'profile')


def load_player_status(user_id):
    """讀取玩家狀態"""
    return load_player_data(user_id, 'status')


def load_player_memory(user_id):
    """讀取玩家記憶"""
    return load_player_data(user_id, 'memory')


def load_player_inventory(user_id):
    """讀取玩家倉庫"""
    return load_player_data(user_id, 'inventory')


def load_player_relations(user_id):
    """讀取玩家 NPC 關係資料"""
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
    
    npc_info = "【NPC 資料庫】\n"
    for npc in npcs:
        npc_info += f"【{npc['name']}】{npc.get('title', '')}\n"
        npc_info += f"  位置：{npc.get('location', '未知')}\n"
        npc_info += f"  性格：{npc.get('personality', '無')}\n"
        
        # 隱藏 agenda（供 AI 參考但不直接顯示）
        hidden = npc.get('hidden', {})
        if hidden.get('hidden_agenda'):
            agenda = hidden['hidden_agenda'][:80]
            npc_info += f"  潛在意圖：{agenda}...\n"
        
        npc_info += "\n"
    
    return npc_info


def format_player_relations(relations):
    """將玩家與 NPC 的關係格式化"""
    npcs = relations.get('npcs', {}) if relations else {}
    
    if not npcs:
        return "（尚無記錄的 NPC 關係）"
    
    rel_info = "【玩家與 NPC 關係】\n"
    for npc_id, data in npcs.items():
        好感度 = data.get('好感度', 0)
        恩怨 = data.get('恩怨', '無')
        rel_info += f"• {npc_id}：好感度{好感度}，恩怨：{恩怨}\n"
    
    return rel_info

# === 滾動式摘要記憶系統 ===


def extract_key_info(dialogue_pair):
    user_msg = dialogue_pair.get('user', '')
    bot_msg = dialogue_pair.get('bot', '')

    # 強化提取 Prompt，確保位置與 NPC 被紀錄
    extract_prompt = f"""請總結以下對話，用於長期記憶：
玩家行為：{user_msg}
GM回應：{bot_msg}

總結標準：
1. 必須包含：主角目前所在的具體地點。
2. 必須包含：目前正在對話或互動的 NPC。
3. 簡述：發生的重大轉折。
請用 50 字內的一句話總結。"""

    try:
        response = model.generate_content(extract_prompt)
        return response.text.strip()
    except:
        return "（提取失敗）"


def manage_memory(user_id):
    """滾動式記憶管理：當短期記憶 >= 11 筆時，壓縮最舊的 2 筆"""
    memory = load_player_memory(user_id)
    if not memory:
        return

    short_term = memory.get('short_term', [])
    long_term = memory.get('long_term_summary', '')

    if len(short_term) >= 11:
        old_dialogues = short_term[:2]
        remaining = short_term[2:]

        key_infos = []
        for diag in old_dialogues:
            info = extract_key_info(diag)
            key_infos.append(info)

        summary_header = "【過往劇情】"
        new_summary = f"{long_term}\n{summary_header} " + " | ".join(key_infos)
        
        if len(new_summary) > 500:
            new_summary = new_summary[-500:]

        memory['long_term_summary'] = new_summary
        memory['short_term'] = remaining

        save_player_data(user_id, 'memory', memory)
        print(f"✅ 記憶滾動：已壓縮 2 筆舊對話至長期記憶")

# --- AI 規則格式化 ---


def format_game_rules():
    """將所有規則格式化為 AI 可讀的提示"""
    rules_data = get_rules()
    punishments = get_punishments()
    rewards = get_rewards()
    ranks = get_ranks()

    # 格式化位階資訊
    ranks_info = "【後宮位階】皇后>皇貴妃>貴妃>妃>嬪>貴人>常在>答應>宮女\n"
    for rank in ranks[:12]:  # 只取后妃部分
        ranks_info += f"• {rank['name']}：{rank['description']}\n"

    # 格式化宮廷規矩
    court_rules = "【宮廷規矩】\n"
    for rule in rules_data.get('court_rules', []):
        court_rules += f"• {rule}\n"

    # 格式化禁忌
    forbidden = "【禁忌】不可"
    forbidden += "、".join(rules_data.get('forbidden_actions', []))
    forbidden += "。\n"

    # 格式化懲罰
    punishments_info = "【懲罰】"
    for p in punishments:
        punishments_info += f"{p['name']}：{p['description']}；"

    # 格式化獎賞
    rewards_info = "【獎賞】"
    for r in rewards:
        rewards_info += f"{r['name']}：{r['description']}；"

    return f"{ranks_info}\n{court_rules}\n{forbidden}\n{punishments_info}\n{rewards_info}"

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

        # 使用家世的初始屬性
        bonus = self.family.get("starting_bonus", {})
        user_id = interaction.user.id

        # === 建立玩家资料夹 ===
        get_player_folder(user_id)

        # 1. profile.json - 基本资料
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

        # 2. status.json - 角色状态
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

        # 3. memory.json - 記憶資料
        memory = {
            "long_term_summary": "",
            "short_term": []
        }
        save_player_data(user_id, 'memory', memory)

        # 4. inventory.json - 倉庫
        inventory = {
            "items": ["家傳玉佩"]
        }
        save_player_data(user_id, 'inventory', inventory)

        # 5. relations.json - NPC 關係
        relations = {
            "npcs": {}
        }
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

        # 生成角色描述
        try:
            sys_prompt = (
                "你是一位清宮小說家，請根據下列資訊，生成一段150字以內、古風、沉浸感強的角色背景描述，"
                "內容需結合家世、外貌、性別、名諱，並以第三人稱敘述，不要有任何AI或機器人語氣：\n"
                f"名諱：{name}\n性別：{self.gender}\n家世：{self.family['name']}，{self.family['description']}\n外貌：{appearance}"
            )
            response = model.generate_content(sys_prompt)
            char_desc = response.text.strip()
        except Exception as e:
            char_desc = f"（角色描述生成失敗：{e}）"

        await interaction.channel.send(f"**身分背景**\n\n{char_desc}")

        # 使用家世對應的固定開場
        opening = self.family.get("opening")
        await interaction.channel.send(content=opening)
        
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
        # 選擇性別後，顯示家世選單
        view = FamilySelectView(self.families, gender)
        await interaction.response.send_message("請選擇你的家世背景：", view=view, ephemeral=True)


class FamilySelectView(discord.ui.View):
    def __init__(self, families, gender):
        super().__init__()
        self.families = families
        self.gender = gender
        self.add_item(FamilySelect(families, gender))


class GenderView(discord.ui.View):
    def __init__(self, families):
        super().__init__()
        self.families = families
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
        await interaction.response.send_message("「命運之書」已開啟，請先選擇你的身世：", view=GenderView(families), ephemeral=True)


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
        embed.add_field(name="倉庫", value=", ".join(
            items) if items else "空", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ooc", description="直接與 AI 溝通，糾正劇情錯誤")
async def ooc(interaction: discord.Interaction, *, correction: str):
    profile = load_player_profile(interaction.user.id)
    memory = load_player_memory(interaction.user.id)

    if not profile:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return

    # 支援新舊結構
    short_term = memory.get('short_term', []) if memory else []
    if not short_term:
        await interaction.response.send_message("尚無劇情紀錄，無法撤回。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # 移除最後一筆錯誤的歷史紀錄
    last_exchange = short_term.pop()

    # 更新資料結構
    if memory:
        memory['short_term'] = short_term
        save_player_data(interaction.user.id, 'memory', memory)

    # 取得遊戲規則
    game_rules = format_game_rules()
    gm_rule = get_script("system_prompts", "game_master")
    gm_rule = gm_rule.replace("{game_rules}", game_rules)

    # 重建歷史（移除最後一筆）
    long_term = memory.get('long_term_summary', '') if memory else ''
    history_summary = "\n".join([
        f"玩家：{h['user']}\nGM：{h['bot'][:80]}..."
        for h in short_term
    ]) if short_term else "無（初次入宮）"

    # 取得 OOC 修正模板並填充
    ooc_template = get_script("templates", "ooc_correction")
    full_prompt = ooc_template.format(
        correction=correction,
        last_scene="[此段已作廢]",
        game_rules=game_rules,
        name=profile['name'],
        background=profile['family_description'],
        history_summary=history_summary,
        long_term_summary=long_term
    )

    try:
        response = model.generate_content(full_prompt)
        await interaction.channel.send(f"🔄 **劇情修正**\n> 修正意見：{correction}\n\n{response.text}")

        # 儲存新的劇情到歷史紀錄
        short_term.append(
            {"user": f"[OOC修正] {correction}", "bot": response.text})
        short_term = short_term[-10:]

        if memory:
            memory['short_term'] = short_term
            save_player_data(interaction.user.id, 'memory', memory)
    except Exception as e:
        await interaction.channel.send(f"⚠️ 修正失敗：{e}")


@bot.tree.command(name="op", description="GM 指令 - 直接修改遊戲狀態")
async def op_cmd(interaction: discord.Interaction, *, command: str):
    """GM 測試指令：直接對 AI 下命令修改遊戲狀態"""
    profile = load_player_profile(interaction.user.id)
    status = load_player_status(interaction.user.id)
    relations = load_player_relations(interaction.user.id)
    inventory = load_player_inventory(interaction.user.id)
    memory = load_player_memory(interaction.user.id)

    if not profile:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # 取得遊戲規則
    game_rules = format_game_rules()

    # 取得 GM 提示
    gm_rule = get_script("system_prompts", "game_master")
    gm_rule = gm_rule.replace("{game_rules}", game_rules)

    # 重建歷史
    long_term = memory.get('long_term_summary', '') if memory else ''
    short_term = memory.get('short_term', []) if memory else []
    history_summary = "\n".join([
        f"玩家：{h['user']}\nGM：{h['bot'][:80]}..."
        for h in short_term
    ]) if short_term else "無（初次入宮）"

    # 取得 OP 指令模板並填充
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
        long_term_summary=long_term
    )

    try:
        response = model.generate_content(full_prompt)
        await interaction.channel.send(f"⚡ **GM 指令執行**\n> 指令：{command}\n\n{response.text}")

        # 解析 AI 回覆中的狀態變化並更新資料
        # 這裡需要 AI 在回覆中標記需要更新的狀態
        # 簡單版：直接儲存劇情到記憶
        if memory:
            short_term.append(
                {"user": f"[OP] {command}", "bot": response.text})
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
                # 取得遊戲規則
                game_rules = format_game_rules()

                # 取得 GM 提示
                gm_rule = get_script("system_prompts", "game_master")
                gm_rule = gm_rule.replace("{game_rules}", game_rules)

                template = get_script("templates", "action_prompt")

                # === 使用三層記憶結構 ===
                long_term = memory.get(
                    'long_term_summary', '') if memory else ''
                short_term = memory.get('short_term', []) if memory else []
                core = status.get('core', {}) if status else {}

                relations = load_player_relations(message.author.id)
                player_relations = format_player_relations(relations)

                history_summary = "\n".join([
                    f"玩家：{h['user']}\nGM：{h['bot'][:300]}..."
                    for h in short_term
                ]) if short_term else "無（初次入宮）"
                npc_database = format_npc_data()

                full_prompt = template.format(
                    gm_prompt=gm_rule,
                    npc_database=npc_database,
                    player_relations=player_relations,
                    name=profile['name'],
                    background=profile['family_description'],
                    action=message.content,
                    history_summary=history_summary,
                    long_term_summary=long_term,
                    core_settings=core.get('world_view', '')
                )
                response = model.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,  
                        candidate_count=1,
                        max_output_tokens=500,
                    )
                )
                await message.reply(response.text)

                # 更新短期記憶
                if memory:
                    short_term.append(
                        {"user": message.content, "bot": response.text})
                    short_term = short_term[-10:]
                    memory['short_term'] = short_term
                    save_player_data(message.author.id, 'memory', memory)

                    # 觸發滾動管理
                    manage_memory(message.author.id)

            except Exception as e:
                print(f"Error: {e}")

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)
