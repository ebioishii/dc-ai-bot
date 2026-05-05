import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from services.gemini_client import BASE_MODEL, call_gemini
from game.state import (
    get_script, get_player_folder, save_player_data, load_player_data, player_exists,
    load_player_profile, load_player_status, load_player_memory,
    load_player_inventory, load_player_relations, get_families,
    _load_gamedata_bundle, apply_state_update,
)
from game.memory import load_fact_sheet, update_fact_sheet, build_history_summary, update_memory
from game.npc import (
    select_relevant_npcs, format_selected_npc_data, get_scene_npcs,
    detect_extreme_action, update_npc_emotions, build_emotion_override,
    detect_affection_change, update_npc_affection, update_companion_tracking,
    ensure_hidden_state,
)
from game.formatting import _affection_tier, format_player_relations, format_game_rules, format_story_reply
from game.rules import classify_player_input, resolve_rules
from game.judge import build_judge_prompt, call_judge_ai
from game.story import make_gm_system_instruction, build_story_prompt, call_story_ai, fallback_story_result
from game.validation import validate_story_output_reason

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

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
    npc_database = format_selected_npc_data(select_relevant_npcs(location, correction, load_player_relations(interaction.user.id)))
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

            except Exception as e:
                print(f"Error: {e}")
                await message.reply("⚠️ 宮中傳訊受阻，請稍後再試。")

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
