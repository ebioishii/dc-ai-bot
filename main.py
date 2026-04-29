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

# --- 訊息處理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_player(message.author.id)
    
    if data and not message.content.startswith('!'):
        async with message.channel.typing():
            try:
                gm_rule = get_script("system_prompts", "game_master")
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