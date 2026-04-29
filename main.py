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
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# --- 工具函式 ---
def get_script(category, key):
    with open('gamedata/scripts.json', 'r', encoding='utf-8') as f:
        return json.load(f)[category][key]

def save_player(user_id, data):
    if not os.path.exists('players'): os.makedirs('players')
    with open(f'players/{user_id}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_player(user_id):
    path = f'players/{user_id}.json'
    return json.load(open(path, 'r', encoding='utf-8')) if os.path.exists(path) else None


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
        player_data = {
            "name": name,
            "gender": self.gender,
            "family": self.family["id"],
            "appearance": appearance,
            "background": f"{self.family['name']}：{self.family['description']}",
            "attributes": {
                "體力": bonus.get("體力", 100),
                "權謀": bonus.get("權謀", 10),
                "聲望": bonus.get("聲望", 0),
                "財產": bonus.get("財產", 0)
            },
            "inventory": ["家傳玉佩"],
            "history": []
        }
        save_player(interaction.user.id, player_data)

        # 顯示創角 Embed
        embed = discord.Embed(title=f"【 {name} 】之入宮檔案", color=0x800000)
        embed.add_field(name="家世", value=self.family["name"], inline=True)
        embed.add_field(name="位階", value=self.family["rank"], inline=True)
        embed.add_field(name="外貌", value=appearance, inline=False)
        embed.add_field(name="優勢", value="、".join(self.family["advantages"]), inline=False)
        embed.add_field(name="劣勢", value="、".join(self.family["disadvantages"]), inline=False)
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

        await interaction.channel.send(f"**身分背景**\n{char_desc}")

        # 使用家世對應的固定開場
        opening = self.family.get("opening")
        await interaction.channel.send(content=opening)

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
    if load_player(interaction.user.id):
        await interaction.response.send_message("你已在宮中，不得重新投胎。", ephemeral=True)
    else:
        families = get_families()
        await interaction.response.send_message("「命運之書」已開啟，請先選擇你的身世：", view=GenderView(families), ephemeral=True)
        
@bot.tree.command(name="help", description="查看操作指南")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🏮 紫禁城生存手冊", color=0x2b2d31)
    embed.add_field(name="`/start`", value="建立身分與開啟故事", inline=False)
    embed.add_field(name="`/profile`", value="查看屬性與裝備", inline=False)
    embed.add_field(name="`/ooc <修正內容>`", value="直接與 AI 溝通，糾正劇情錯誤", inline=False)
    embed.set_footer(text="直接在頻道中輸入行動，Bot 會推演劇情。")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="profile", description="查看人物表")
async def profile(interaction: discord.Interaction):
    data = load_player(interaction.user.id)
    if not data:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return
    embed = discord.Embed(title=f"角色資訊：{data['name']}", color=0xdaa520)
    attr_text = "\n".join([f"{k}: {v}" for k, v in data['attributes'].items()])
    embed.add_field(name="數值", value=attr_text, inline=True)
    embed.add_field(name="裝備", value=", ".join(data['inventory']), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ooc", description="直接與 AI 溝通，糾正劇情錯誤")
async def ooc(interaction: discord.Interaction, *, correction: str):
    data = load_player(interaction.user.id)
    if not data:
        await interaction.response.send_message("請先使用 /start 建立身分。", ephemeral=True)
        return
    
    if not data.get("history"):
        await interaction.response.send_message("尚無劇情紀錄，無法撤回。", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # 移除最後一筆錯誤的歷史紀錄
    last_exchange = data['history'].pop()
    save_player(interaction.user.id, data)
    
    # 取得遊戲規則
    game_rules = format_game_rules()
    gm_rule = get_script("system_prompts", "game_master")
    gm_rule = gm_rule.replace("{game_rules}", game_rules)
    
    # 重建歷史（移除最後一筆）
    history_summary = "\n".join([
        f"玩家：{h['user']}\nGM：{h['bot'][:80]}..."
        for h in data['history']
    ]) if data['history'] else "無（初次入宮）"
    
    # 取得 OOC 修正模板並填充
    ooc_template = get_script("templates", "ooc_correction")
    full_prompt = ooc_template.format(
        correction=correction,
        last_scene=last_exchange['bot'][:200],
        game_rules=game_rules,
        name=data['name'],
        background=data['background'],
        history_summary=history_summary
    )
    
    try:
        response = model.generate_content(full_prompt)
        # 直接在頻道中公開回覆
        await interaction.channel.send(f"🔄 **劇情修正**\n> 修正意見：{correction}\n\n{response.text}")
        
        # 儲存新的劇情到歷史紀錄
        data['history'].append({"user": f"[OOC修正] {correction}", "bot": response.text})
        data['history'] = data['history'][-5:]
        save_player(interaction.user.id, data)
    except Exception as e:
        await interaction.channel.send(f"⚠️ 修正失敗：{e}")
        
    
# --- 訊息處理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_player(message.author.id)
    
    if data and not message.content.startswith('!'):
        async with message.channel.typing():
            try:
                # 取得遊戲規則
                game_rules = format_game_rules()
                
                # 取得 GM 提示
                gm_rule = get_script("system_prompts", "game_master")
                
                # 將規則注入 GM 提示
                gm_rule = gm_rule.replace("{game_rules}", game_rules)
                
                template = get_script("templates", "action_prompt")
                
                history_summary = "\n".join([
                    f"玩家：{h['user']}\nGM：{h['bot'][:80]}..."
                    for h in data['history']
                ]) if data['history'] else "無（初次入宮）"
                
                full_prompt = template.format(
                    gm_prompt=gm_rule,
                    name=data['name'],
                    background=data['background'],
                    action=message.content,
                    history_summary=history_summary
                )
                
                response = model.generate_content(full_prompt)
                await message.reply(response.text)
                
                data['history'].append({"user": message.content, "bot": response.text})
                data['history'] = data['history'][-5:]
                save_player(message.author.id, data)
                
            except Exception as e:
                print(f"Error: {e}")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)