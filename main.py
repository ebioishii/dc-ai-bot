import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import google.generativeai as genai

# --- 環境與 API 設定 ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 使用穩定舊版 SDK
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# --- 工具函式：JSON 管理 ---
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

# --- UI 組件：創角 Modal ---
class StartModal(discord.ui.Modal):
    def __init__(self, gender):
        super().__init__(title=f"🏮 建立身分：{gender}性 🏮")
        self.gender = gender
        
    p_name = discord.ui.TextInput(
        label='名諱', 
        placeholder='請輸入你在宮中的稱呼...', 
        min_length=2, 
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.p_name.value
        
        # 1. AI 生成背景
        try:
            sys_prompt = get_script("system_prompts", "background_gen")
            response = model.generate_content(f"{sys_prompt}\n玩家姓名：{name}, 性別：{self.gender}")
            bg_story = response.text
        except Exception as e:
            bg_story = f"內務府卷宗調閱失敗。({e})"

        # 2. 儲存玩家資料
        player_data = {
            "name": name,
            "gender": self.gender,
            "background": bg_story,
            "attributes": {"體力": 100, "權謀": 10, "聲望": 0},
            "inventory": ["家傳玉佩"],
            "history": [] 
        }
        save_player(interaction.user.id, player_data)

        # 3. 顯示創角 Embed (僅玩家可見)
        embed = discord.Embed(title=f"【 {name} 】之入宮檔案", color=0x800000)
        embed.add_field(name="身分背景", value=bg_story)
        await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            # 取得規則與模板
            gm_rule = get_script("system_prompts", "game_master")
            template = get_script("templates", "action_prompt")
            
            # 將第一章模擬為玩家「踏入宮門」的初始行動
            initial_action = "正式踏入宮門，開始宮廷生活。"
            
            full_prompt = template.format(
                gm_prompt=gm_rule,
                name=name,
                background=bg_story,
                history_summary="故事剛開始，角色初入紫禁城。",
                action=initial_action
            )
            
            # 呼叫 AI (使用與 on_message 相同的規則)
            story_res = model.generate_content(full_prompt)
            await interaction.channel.send(content=story_res.text)
            
        except Exception as e:
            await interaction.channel.send(f"（內務府傳訊有誤：{e}）")

# --- UI 組件：選單與 View (同前) ---
class GenderSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="女"),
            discord.SelectOption(label="男")
        ]
        super().__init__(placeholder="請選擇你的身分...", options=options)

    async def callback(self, interaction: discord.Interaction):
        gender = self.values[0]
        await interaction.response.send_modal(StartModal(gender))

class GenderView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(GenderSelect())

# --- Bot 設定與指令 (同前) ---
class HaremBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = HaremBot()

@bot.tree.command(name="start", description="開始遊戲並建立身分")
async def start(interaction: discord.Interaction):
    if load_player(interaction.user.id):
        await interaction.response.send_message("你已在宮中，不得重新投胎。", ephemeral=True)
    else:
        await interaction.response.send_message("「命運之書」已開啟，請先選擇你的入宮身分：", view=GenderView(), ephemeral=True)

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

@bot.event
async def on_message(message):
    # 1. 排除 Bot 自己的訊息，避免無限循環
    if message.author.bot:
        return

    # 2. 檢查玩家是否有存檔
    data = load_player(message.author.id)
    
    # 3. 如果有存檔，且訊息不是以指令符號 "!" 開頭（如果你有設定的話）
    if data and not message.content.startswith('!'):
        # 這裡可以限制 Bot 只在特定頻道回應，或是私訊回應
        # 若要限制頻道，可以加：if message.channel.id == 你的頻道ID:
        
        async with message.channel.typing():
            try:
                # 1. 取得設定
                gm_rule = get_script("system_prompts", "game_master")
                template = get_script("templates", "action_prompt")

                # 2. 修正後的組合方式：將所有變數填入 template 的大括號中
                full_prompt = template.format(
                    gm_prompt=gm_rule,          # 這裡補上對應 JSON 裡的 {gm_prompt}
                    name=data['name'],
                    background=data['background'],
                    action=message.content
                )
                                
                # 3. 呼叫 Gemini
                response = model.generate_content(full_prompt)
                await message.reply(response.text)
                
                # (選配) 更新玩家的對話歷史，讓 AI 有記憶
                data['history'].append({"user": message.content, "bot": response.text})
                # 只保留最近 5 筆紀錄避免 Token 過長
                data['history'] = data['history'][-5:] 
                save_player(message.author.id, data)
                
            except Exception as e:
                print(f"Error in on_message: {e}")
                # 不要回傳錯誤訊息給玩家，保持沉浸感

    # 4. 重要：必須加上這行，否則 Slash Commands (/start 等) 會失效！
    await bot.process_commands(message)
async def on_ready():
    print(f'✅ {bot.user} 已上線')

bot.run(DISCORD_TOKEN)