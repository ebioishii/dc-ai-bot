import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from services.gemini_client import BASE_MODEL, call_gemini, call_gemini_json
from game.state import (
    get_script, get_player_folder, save_player_data, load_player_data, player_exists,
    load_player_profile, load_player_status, load_player_memory,
    load_player_inventory, load_player_relations, get_families,
    get_locations, get_npcs, _load_gamedata_bundle, apply_state_update,
    ensure_current_objectives, normalize_inventory_record, normalize_memory_record,
    normalize_player_records, normalize_profile_record, normalize_relations_record,
    normalize_status_record,
)
from game.memory import load_fact_sheet, update_fact_sheet, build_history_summary, update_memory
from game.context import (
    build_model_context, classify_event_size, output_length_policy,
    normalize_scene_state,
)
from game.hints import compact_hints_for_status, format_hint_reply
from game.ooc import (
    build_ooc_rewrite_prompt, extract_ooc_target_action,
    ooc_rewrite_problem, should_record_ooc_fact,
)
from game.performance import elapsed_ms, estimate_tokens, log_reply_performance, now_ms
from game.quality import (
    finalize_story_result, inspect_story_quality, sanitize_player_visible_text,
)
from game.npc import (
    select_relevant_npcs, format_selected_npc_data, get_scene_npcs, get_present_scene_npcs,
    detect_extreme_action, update_npc_emotions, build_emotion_override,
    detect_affection_change, update_npc_affection, update_companion_tracking,
    ensure_hidden_state,
)
from game.formatting import _affection_tier, format_player_relations, format_game_rules, format_story_reply
from game.rules import classify_player_input, resolve_rules
from game.judge import build_judge_prompt, call_judge_ai
from game.story import (
    make_gm_system_instruction, build_story_prompt, call_story_ai,
    fallback_story_result, suppress_choices_when_disabled,
)
from game.validation import validate_story_output_reason
from game.startup import (
    RANDOM_FAMILY_VALUE, build_opening_story_result, format_location_display,
    build_starting_objectives, build_starting_relations,
    generate_random_appearance, resolve_start_family, resolve_start_location,
)

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

class StartModal(discord.ui.Modal):
    def __init__(self, gender, family, random_appearance=False):
        title = f"🏮 建立身分：{gender}性"
        if random_appearance:
            title += "・隨機外貌"
        super().__init__(title=f"{title} 🏮")
        self.gender = gender
        self.family = family
        self.random_appearance = random_appearance
        self.p_name = discord.ui.TextInput(
            label='名諱',
            placeholder='請輸入你在宮中的稱呼...',
            min_length=2,
            max_length=10
        )
        self.add_item(self.p_name)
        self.p_appearance = None
        if not random_appearance:
            self.p_appearance = discord.ui.TextInput(
                label='外貌描述',
                placeholder='請簡單描述你的外貌特徵...',
                min_length=5,
                max_length=50,
                style=discord.TextStyle.paragraph
            )
            self.add_item(self.p_appearance)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.p_name.value
        if self.random_appearance:
            appearance = generate_random_appearance(self.gender, self.family)
        else:
            appearance = self.p_appearance.value if self.p_appearance else ""

        bonus = self.family.get("starting_bonus", {})
        user_id = interaction.user.id
        start_location = resolve_start_location(self.family, get_locations())
        npc_data = get_npcs()
        opening_contacts = self.family.get("opening_contacts", {})
        starting_objectives = build_starting_objectives(start_location, opening_contacts, npc_data)

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
        profile = normalize_profile_record(profile)
        save_player_data(user_id, 'profile', profile)

        opening_story = build_opening_story_result(
            profile,
            self.family,
            start_location,
            opening_contacts
        )

        # 2. status.json
        status = {
            "alive": True,
            "location": start_location["id"],
            "location_id": start_location["id"],
            "location_name": start_location["name"],
            "room": start_location.get("room", ""),
            "last_hints": compact_hints_for_status(opening_story.get("choices", [])),
            "current_objectives": starting_objectives,
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
        status = normalize_status_record(status)
        save_player_data(user_id, 'status', status)

        # 3. memory.json — 加入 fact_sheet 欄位
        memory = {
            "long_term_summary": "",
            "short_term": [],
            "fact_sheet": "",
            "fact_sheet_items": [],
            "scene_summary": "",
            "summary_turns_since_update": 0
        }
        memory = normalize_memory_record(memory, status)
        save_player_data(user_id, 'memory', memory)

        # 4. inventory.json
        inventory = {"items": ["家傳玉佩"]}
        inventory = normalize_inventory_record(inventory)
        save_player_data(user_id, 'inventory', inventory)

        # 5. relations.json
        relations = build_starting_relations(start_location, opening_contacts, npc_data)
        relations = normalize_relations_record(relations)
        save_player_data(user_id, 'relations', relations)

        # 顯示創角 Embed
        embed = discord.Embed(title=f"【 {name} 】之入宮檔案", color=0x800000)
        embed.add_field(name="家世", value=self.family["name"], inline=True)
        embed.add_field(name="位階", value=self.family["rank"], inline=True)
        embed.add_field(name="位置", value=format_location_display(status), inline=True)
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

        opening = format_story_reply(opening_story, show_choices=False)
        await interaction.channel.send(content=opening)

        # 將開場存入短期記憶（user 欄使用自然語句，避免 Gemini 困惑）
        initial_scene = f"{char_desc}\n\n{opening}"
        memory = load_player_data(user_id, 'memory')
        if memory:
            memory['short_term'].append({
                "user": "【開場】請描述我初入宮廷時的第一幕場景，從此刻起我正式踏入這座深宮。",
                "bot": initial_scene
            })
            save_player_data(user_id, 'memory', normalize_memory_record(memory, status))


class FamilySelect(discord.ui.Select):
    def __init__(self, families, gender):
        self.families = families
        self.gender = gender
        options = [discord.SelectOption(
            label="🎲 隨機出身",
            description="從目前可選出身中隨機指定一個",
            value=RANDOM_FAMILY_VALUE
        )] + [
            discord.SelectOption(
                label=f["label"],
                description=f["description"][:50],
                value=f["id"]
            ) for f in families
        ]
        super().__init__(placeholder="請選擇你的家世背景...", options=options)

    async def callback(self, interaction: discord.Interaction):
        family_id = self.values[0]
        family = resolve_start_family(self.families, family_id)
        view = AppearanceSelectView(self.gender, family)
        await interaction.response.send_message(
            f"已選定出身：{family['name']}。請選擇外貌設定方式：",
            view=view,
            ephemeral=True
        )


class AppearanceSelectView(discord.ui.View):
    def __init__(self, gender, family):
        super().__init__()
        self.gender = gender
        self.family = family

    @discord.ui.button(label="手動設定外貌", style=discord.ButtonStyle.secondary)
    async def manual_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StartModal(self.gender, self.family, random_appearance=False))

    @discord.ui.button(label="🎲 隨機外貌", style=discord.ButtonStyle.primary)
    async def random_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StartModal(self.gender, self.family, random_appearance=True))


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
        embed.add_field(name="位置", value=format_location_display(status), inline=True)
        embed.add_field(name="生死", value="存活" if status.get(
            'alive', True) else "已故", inline=True)

    if inventory:
        items = inventory.get('items', [])
        embed.add_field(name="倉庫", value="、".join(
            items) if items else "空", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="objectives", description="查看目前短期目標提示")
async def objectives(interaction: discord.Interaction):
    status = load_player_status(interaction.user.id)
    memory = load_player_memory(interaction.user.id) or {}
    if not status:
        await interaction.response.send_message("尚未建立角色，請先使用 /start。", ephemeral=True)
        return
    text = format_hint_reply(status, memory, include_hints=False)
    save_player_data(interaction.user.id, "status", normalize_status_record(status))
    save_player_data(interaction.user.id, "memory", normalize_memory_record(memory, status))
    await interaction.response.send_message(text)


@bot.tree.command(name="hint", description="查看目前短期目標與建議行動")
async def hint(interaction: discord.Interaction):
    status = load_player_status(interaction.user.id)
    memory = load_player_memory(interaction.user.id) or {}
    if not status:
        await interaction.response.send_message("尚未建立角色，請先使用 /start。", ephemeral=True)
        return
    text = format_hint_reply(status, memory, include_hints=True)
    save_player_data(interaction.user.id, "status", normalize_status_record(status))
    save_player_data(interaction.user.id, "memory", normalize_memory_record(memory, status))
    await interaction.response.send_message(text)


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
        save_player_data(interaction.user.id, 'memory', normalize_memory_record(memory, status))

    location = (status or {}).get("location_name") or (status or {}).get("location") or "未知"
    history_summary = build_history_summary(short_term)
    relations = load_player_relations(interaction.user.id)
    present_npcs = get_present_scene_npcs(location, profile=profile, status=status or {}, player_input=correction)
    selected_npcs = select_relevant_npcs(location, correction, relations, limit=4)
    npc_database = format_selected_npc_data(selected_npcs)
    fact_sheet = load_fact_sheet(interaction.user.id)
    target_action = extract_ooc_target_action(correction, last_exchange)
    previous_valid_reply = str(short_term[-1].get("bot", "")) if short_term else ""
    ooc_system, ooc_prompt = build_ooc_rewrite_prompt(
        correction=correction,
        target_action=target_action,
        invalid_previous_reply=last_exchange.get("bot", ""),
        profile=profile,
        status=status or {},
        present_npcs=present_npcs,
        npc_database=npc_database,
        history_summary=history_summary,
        fact_sheet=fact_sheet,
    )

    try:
        data = await call_gemini_json(ooc_system, ooc_prompt, temperature=0.55, max_tokens=700)
        text = data.get("reply", "") if isinstance(data, dict) else ""
        if not text:
            await interaction.followup.send("修正劇情觸動禁忌，無法生成，請換個修正方向。", ephemeral=True)
            return

        text = sanitize_player_visible_text(text)
        problem = ooc_rewrite_problem(text, previous_valid_reply=previous_valid_reply)
        if problem:
            retry_prompt = (
                ooc_prompt
                + f"\n\nPrevious rewrite failed local check: {problem}. "
                + "Rewrite again. Do not add arrivals, summons, interruptions, new conflicts, or repeat earlier setup. JSON only."
            )
            data = await call_gemini_json(ooc_system, retry_prompt, temperature=0.45, max_tokens=700)
            text = sanitize_player_visible_text(data.get("reply", "") if isinstance(data, dict) else "")
            problem = ooc_rewrite_problem(text, previous_valid_reply=previous_valid_reply)
        if problem:
            text = "你按下方才失準的敘述，重新把注意力放回眼前。長春宮偏殿的陳設與宮人反應仍有可察之處，在場之人也仍按原本的禮數應對；這一幕暫不新增傳喚、闖入或突發變故。"

        story_result, _ = finalize_story_result(
            {"reply": text, "choices": []},
            previous_reply=previous_valid_reply,
            length_policy={"max_chars": 380},
        )
        text = story_result.get("reply", text)
        await interaction.followup.send("已記錄修正，玩家頻道只會顯示修正後劇情。", ephemeral=True)
        await interaction.channel.send(text)

        if should_record_ooc_fact(correction):
            update_fact_sheet(interaction.user.id, correction, text[:80])

        # 儲存修正後的劇情
        short_term.append({"user": target_action, "bot": text})
        short_term = short_term[-10:]
        if memory:
            memory['short_term'] = short_term
            save_player_data(interaction.user.id, 'memory', normalize_memory_record(memory, status))

    except Exception as e:
        await interaction.followup.send(f"修正失敗：{e}", ephemeral=True)


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
        text = await call_gemini(gm_system, full_prompt, use_prompt_cache=True)
        if not text:
            await interaction.followup.send("指令執行被攔截，請調整指令內容後重試。", ephemeral=True)
            return

        text = sanitize_player_visible_text(text)
        await interaction.followup.send("GM 指令已執行，玩家頻道只會顯示結果敘事。", ephemeral=True)
        await interaction.channel.send(text)

        if memory:
            short_term.append({"user": f"GM 調整：{command}", "bot": text})
            short_term = short_term[-10:]
            memory['short_term'] = short_term
            save_player_data(interaction.user.id, 'memory', normalize_memory_record(memory, status))

    except Exception as e:
        await interaction.followup.send(f"指令執行失敗：{e}", ephemeral=True)


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
# 訊息處理（非阻塞 per-channel queue）
# ============================================================

CHANNEL_QUEUES: dict[int, asyncio.Queue] = {}
CHANNEL_WORKERS: dict[int, asyncio.Task] = {}


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith('!'):
        await bot.process_commands(message)
        return

    if load_player_profile(message.author.id):
        try:
            await message.channel.trigger_typing()
        except Exception:
            pass
        queue_player_message(message)
        return

    await bot.process_commands(message)


def queue_player_message(message):
    channel_id = int(message.channel.id)
    queue = CHANNEL_QUEUES.setdefault(channel_id, asyncio.Queue())
    queue.put_nowait(message)
    worker = CHANNEL_WORKERS.get(channel_id)
    if worker is None or worker.done():
        CHANNEL_WORKERS[channel_id] = asyncio.create_task(process_channel_queue(channel_id))


async def process_channel_queue(channel_id: int):
    queue = CHANNEL_QUEUES[channel_id]
    while True:
        try:
            message = await asyncio.wait_for(queue.get(), timeout=30)
        except asyncio.TimeoutError:
            if queue.empty():
                CHANNEL_QUEUES.pop(channel_id, None)
                CHANNEL_WORKERS.pop(channel_id, None)
                return
            continue
        try:
            async with message.channel.typing():
                await handle_player_message(message)
        finally:
            queue.task_done()


async def handle_player_message(message):
    total_start = now_ms()
    model_duration_ms = 0
    input_tokens_est = 0
    retry_count = 0
    summary_info = {"summary_triggered": False, "summary_used": False, "recent_turns": 0}

    try:
        if player_exists(message.author.id):
            normalized_records = normalize_player_records(message.author.id)
        else:
            normalized_records = {}
        profile = normalized_records.get("profile") or load_player_profile(message.author.id)
        status = normalized_records.get("status") or load_player_status(message.author.id)
        memory = normalized_records.get("memory") or load_player_memory(message.author.id) or {}
        ensure_current_objectives(status or {}, memory)
        if not profile:
            return

        location = status.get('location', '未知') if status else '未知'
        attributes = status.get('attributes', {}) if status else {}
        relations = load_player_relations(message.author.id)
        player_relations_str = format_player_relations(relations)

        scene_npc_list = get_present_scene_npcs(location, profile=profile, status=status or {}, player_input=message.content)
        fact_sheet = load_fact_sheet(message.author.id)

        resolved_content = message.content
        input_type, cleaned_action = classify_player_input(resolved_content)

        affection_delta = detect_affection_change(message.content)
        if affection_delta != 0 and scene_npc_list:
            explicit_affection_targets = [name for name in scene_npc_list if name and name in message.content]
            for npc_name in explicit_affection_targets:
                update_npc_affection(message.author.id, npc_name, affection_delta)
            relations = load_player_relations(message.author.id)
            player_relations_str = format_player_relations(relations)

        extreme_flags = detect_extreme_action(message.content)
        emotion_override = ""
        if (extreme_flags['is_insult'] or extreme_flags['is_violence']) and scene_npc_list:
            updated_relations, triggered_npcs = update_npc_emotions(
                message.author.id, scene_npc_list, extreme_flags
            )
            relations = updated_relations
            player_relations_str = format_player_relations(relations)
            emotion_override = build_emotion_override(triggered_npcs)

        turn_context = build_model_context(
            memory,
            status=status,
            relations=relations,
            scene_npcs=scene_npc_list,
            player_input=cleaned_action,
            recent_turns=4,
        )
        summary_info["summary_used"] = bool(
            turn_context.get("scene_summary")
            and turn_context["scene_summary"] != "（尚無可用場景摘要）"
        )
        summary_info["recent_turns"] = turn_context.get("recent_turns_count", 0)

        game_state = {
            "profile": profile,
            "status": status or {},
            "location": location,
            "attributes": attributes,
            "scene_npcs": scene_npc_list,
            "relations": relations or {"npcs": {}, "companions": {}},
            "scene_state": turn_context.get("scene_state", {}),
            "scene_summary": turn_context.get("scene_summary", ""),
            "input_type": input_type,
        }
        inventory = load_player_inventory(message.author.id) or {"items": []}
        gamedata = _load_gamedata_bundle()
        relations = ensure_hidden_state(relations, gamedata, game_state, cleaned_action)
        relations = normalize_relations_record(relations)
        save_player_data(message.author.id, "relations", relations)
        game_state["relations"] = relations

        turn_context = build_model_context(
            memory,
            status=status,
            relations=relations,
            scene_npcs=scene_npc_list,
            player_input=cleaned_action,
            recent_turns=4,
        )

        judge_system, judge_prompt = build_judge_prompt(
            cleaned_action,
            game_state,
            memory,
            relations,
            inventory,
            turn_context=turn_context,
        )
        input_tokens_est += estimate_tokens(judge_system) + estimate_tokens(judge_prompt)
        call_start = now_ms()
        judge_result = await call_judge_ai(judge_system, judge_prompt)
        model_duration_ms += elapsed_ms(call_start)

        authoritative_result = resolve_rules(
            judge_result,
            game_state,
            memory,
            relations,
            inventory,
            gamedata
        )

        turn_context = build_model_context(
            memory,
            status=status,
            relations=relations,
            scene_npcs=scene_npc_list,
            player_input=cleaned_action,
            authoritative_result=authoritative_result,
            recent_turns=4,
        )
        game_state["scene_state"] = turn_context.get("scene_state", {})
        event_size = classify_event_size(judge_result, authoritative_result)
        length_policy = output_length_policy(event_size)
        offer_choices = False

        selected_npcs = select_relevant_npcs(location, cleaned_action, relations, limit=4)
        selected_lore = {
            "game_rules": "程式裁決優先；Story Writer 只敘事，不決定世界狀態；不得代寫玩家內心；不得暴露 hidden_state；每輪必須回應 authoritative_result。",
            "fact_sheet": fact_sheet,
            "player_relations": player_relations_str,
            "emotion_override": emotion_override,
            "scene_summary": turn_context.get("scene_summary", ""),
        }
        story_system, story_prompt = build_story_prompt(
            cleaned_action,
            judge_result,
            authoritative_result,
            selected_lore,
            selected_npcs,
            game_state,
            memory,
            turn_context=turn_context,
            output_policy=length_policy,
            offer_choices=offer_choices,
        )

        input_tokens_est += estimate_tokens(story_system) + estimate_tokens(story_prompt)
        call_start = now_ms()
        story_result = await call_story_ai(story_system, story_prompt)
        model_duration_ms += elapsed_ms(call_start)
        story_result = suppress_choices_when_disabled(story_result, offer_choices)

        ok, last_error = validate_story_output_reason(
            story_result,
            authoritative_result,
            game_state,
            choices_required=offer_choices,
        )
        previous_reply = ""
        if isinstance(memory.get("short_term"), list) and memory["short_term"]:
            previous_reply = str(memory["short_term"][-1].get("bot", ""))
        quality = inspect_story_quality(
            story_result.get("reply", ""),
            previous_reply=previous_reply,
            max_chars=length_policy["max_chars"],
            min_chars=length_policy.get("min_chars", 0),
        )

        if (not ok or quality["retry_recommended"]) and retry_count < 1:
            retry_count += 1
            retry_reason = last_error if not ok else "local_quality_check_failed"
            retry_prompt = (
                story_prompt
                + f"\n\nPrevious output failed: {retry_reason}. "
                + "Return corrected JSON only. Keep authoritative_result unchanged. "
                + f"Reply MUST be at least {length_policy.get('min_chars', 220)} Chinese chars and within {length_policy['max_chars']} Chinese chars. "
                + "No debug labels, no player inner thoughts, no repeated wording."
            )
            input_tokens_est += estimate_tokens(retry_prompt)
            call_start = now_ms()
            story_result = await call_story_ai(story_system, retry_prompt)
            model_duration_ms += elapsed_ms(call_start)
            story_result = suppress_choices_when_disabled(story_result, offer_choices)
            ok, last_error = validate_story_output_reason(
                story_result,
                authoritative_result,
                game_state,
                choices_required=offer_choices,
            )

        if not ok:
            print(f"Story validation failed; using fallback: {last_error}")
            story_result = fallback_story_result(authoritative_result)

        story_result, _final_quality = finalize_story_result(
            story_result,
            previous_reply=previous_reply,
            length_policy=length_policy,
        )
        if _final_quality.get("duplicate"):
            story_result, _final_quality = finalize_story_result(
                fallback_story_result(authoritative_result),
                previous_reply=previous_reply,
                length_policy=length_policy,
            )
        text = format_story_reply(story_result, show_choices=False, natural_hint="")
        text = sanitize_player_visible_text(text)
        await message.reply(text)

        authoritative_result["state_update"].setdefault("status_set", {})["last_hints"] = (
            compact_hints_for_status(authoritative_result.get("strategic_choices", []))
        )
        scene_state = normalize_scene_state(
            turn_context.get("scene_state", {}),
            status=status,
            relations=relations,
            scene_npcs=scene_npc_list,
            player_input=cleaned_action,
            authoritative_result=authoritative_result,
        )
        authoritative_result["state_update"].setdefault("status_set", {})["scene_state"] = scene_state
        apply_state_update(message.author.id, authoritative_result["state_update"])

        try:
            update_companion_tracking(message.author.id, story_result.get("reply", ""))
            latest_status = load_player_status(message.author.id)
            latest_relations = load_player_relations(message.author.id)
            summary_info = update_memory(
                message.author.id,
                cleaned_action,
                story_result.get("reply", ""),
                status=latest_status,
                relations=latest_relations,
            )
            normalize_player_records(message.author.id)
        except Exception as post_error:
            print(f"Post-reply maintenance error: {post_error}")

        log_reply_performance({
            "channel_id": message.channel.id,
            "input_tokens_est": input_tokens_est,
            "output_tokens_est": estimate_tokens(text),
            "model_duration_ms": model_duration_ms,
            "total_duration_ms": elapsed_ms(total_start),
            "retry_count": retry_count,
            "summary_used": summary_info.get("summary_used", False),
            "summary_triggered": summary_info.get("summary_triggered", False),
            "recent_turns": summary_info.get("recent_turns", turn_context.get("recent_turns_count", 0)),
            "story_validation_error": last_error if not ok else "",
        })

    except Exception as e:
        print(f"Error: {e}")
        await message.reply("⚠️ 宮中傳訊受阻，請稍後再試。")


@bot.event
async def on_ready():
    print(f'✅ {bot.user} 已上線')

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
