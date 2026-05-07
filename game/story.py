from __future__ import annotations
from services.gemini_client import GM_MODEL, call_gemini_json
from game.state import get_script, get_strategies
from game.npc import get_npc_stats, hidden_state_cues, format_selected_npc_data
from game.judge import _json_prompt_payload

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
   好感度 30~60（友善）：願意多說半句，但仍守宮規；
   好感度 10~30（中立偏暖）：禮節性應對，不主動交心；
   好感度 -10~10（初識）：正常客氣，不要寫成不悅或敵意；
   好感度 < -10（戒備/敵意）：可能冷淡、試探、刁難或舉報。

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


async def call_story_ai(system, user):
    data = await call_gemini_json(
        system,
        user,
        model=GM_MODEL,
        temperature=0.75,
        max_tokens=1200
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


def suppress_choices_when_disabled(story_result: dict, choices_required: bool) -> dict:
    """Drop JSON choices from Story Writer when the current surface should not show them."""
    if not isinstance(story_result, dict):
        return story_result
    if choices_required:
        return story_result
    cleaned = dict(story_result)
    cleaned["choices"] = []
    return cleaned


def build_story_prompt(
    player_input,
    judge_result,
    authoritative_result,
    selected_lore,
    selected_npcs,
    game_state,
    memory,
    turn_context: dict | None = None,
    output_policy: dict | None = None,
    offer_choices: bool = True,
):
    turn_context = turn_context or {}
    output_policy = output_policy or {"event_size": "normal", "min_chars": 120, "max_chars": 250}
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
    compact_authoritative = _compact_authoritative_result(authoritative_result)
    compact_npcs = [_compact_npc(npc) for npc in selected_npcs if isinstance(npc, dict)]
    story_system = (
        "You are AI 2: Story Writer AI for a Discord text game. "
        "Only write player-facing narration from the authoritative ruling. "
        "You are not the judge. Do not change state, overrule rulings, or treat player assumptions as facts. "
        "Do not reveal hidden_state numbers or full hidden_state objects. Express them only through indirect cues. "
        "Output JSON only."
    )
    story_user = {
        "task": "Write the next player-facing story beat. Include choices only when choices_required is true.",
        "output_schema": {
            "reply": "給玩家看的劇情文字",
            "choices": "[] unless choices_required is true; then provide 2-4 strategic choices with id/text/style/risk/reward/effect_hint/mechanical_effect.",
            "state_update": {}
        },
        "output_policy": {
            "event_size": output_policy.get("event_size", "normal"),
            "reply_length_chinese_chars": f"{output_policy.get('min_chars', 120)}-{output_policy.get('max_chars', 250)}",
            "choices_required": bool(offer_choices),
            "choice_display_rule": "Do not include a 【可選行動】 heading in reply. Put choices only in JSON choices when choices_required is true.",
            "when_no_choices": "End with immersive momentum or a subtle natural opening, not a numbered option list."
        },
        "hard_rules": [
            "You only write story; you do not decide rules.",
            "The first paragraph must directly resolve the player's latest visible action, not replay the previous scene or jump back to an earlier setup.",
            "Do not merely restate the player's action. After at most one short clause of setup, show the NPC response, visible consequence, or concrete clue.",
            "If the player speaks to or asks someone, the reply must include that target's visible response, refusal, silence, or a concrete consequence. Do not stop after paraphrasing the player's words.",
            "Do not mention objective progress, short-term goal progress, percentages, or phrases like '向前推進了一小步' in player-facing prose. Those belong only in /hint.",
            "Avoid stock transition lines. Never write: '你沒有立刻得到明白答案', '回話順序與侍從動線', '話落之後，席間的態度', '簾外腳步聲停住', or '原本平順的話題被迫換了節奏'.",
            "Do not repeat facts or descriptions already present in recent_turns unless the newest player action directly changes them.",
            "Do not reuse the same NPC body-language bundle across turns. Avoid fixed templates such as 臉色蒼白、眼神閃爍、緊咬下唇、不甘與隱忍.",
            "Never write repeated filler refusals like 有些事情不是妳想的那樣, 這裡面牽涉到的, or 真正要緊的名字仍被她避開. If an NPC withholds information, show a concrete visible cost, a partial clue, a named boundary, or a new response angle.",
            "For first contact or relations near neutral/初識, write the NPC as normally polite, cautious, or procedural. Do not make them 不悅、疏離、冷淡, or pulling away unless authoritative_result shows pressure, insult, public accusation, anger, or prior conflict.",
            "Do not overrule authoritative_result.",
            "scene_state.phase is authoritative. If phase is audience_request, write only the request, waiting, gatekeeping, or servant response; the high-rank target has not appeared or spoken unless authoritative_result explicitly says so.",
            "Story Writer must write from authoritative_result.turn_progress and make the consequence visible without exposing numbers.",
            "不得替玩家補充未明說的心理活動、意圖或感受。只能描寫外在行動、環境反應與 NPC 反應。",
            "Do not create, cancel, rename, or redirect NPC schemes. Only reflect scheme_pressure, visible_clues, and scheme_events provided by authoritative_result.",
            "Never reveal scheme ids, hidden goals, numeric progress, numeric risk, or JSON field names in player-facing prose.",
            "Do not add major events that are absent from authoritative_result.confirmed_events, npc_actions, world_event, or state_update.",
            "NPCs may not give, award, hand over, or place an item in the player's possession unless authoritative_result.state_update.inventory_add explicitly contains that item.",
            "Do not turn judge_result.assumptions into happened facts.",
            "If authoritative_result.denied_assumptions includes an event, the reply must say it did not happen or remains unconfirmed.",
            "Do not reveal hidden_state numeric values, labels, or JSON keys in player-facing prose.",
            "Use hidden_state_cues only as indirect body language, pauses, tone, glances, or servant reactions.",
            "You must include all provided npc_actions and world_event if world_event.type is not none.",
            "If world_event.type is none, do not invent interruptions, arrivals, summons, object discoveries, or overheard events.",
            "Do not write the player's private thoughts, fear, intent, or unspoken emotions. Only describe visible posture or consequences.",
            "Avoid writing the player's actions in embellished form unless the player explicitly did them. Do not use phrases like '你不動聲色地', '你定了定神', or '心中'.",
            "If choices_required is false, choices must be [].",
            "If choices_required is false, do not write numbered options, action suggestions, effect hints, or an action menu in reply.",
            "If choices_required is false, never end with a question like what will you do next, how will you guide this, or choose gentle vs direct pressure.",
            "Never write meta analysis such as 'player action completed', 'the situation progressed', 'this shows', or references to the player as a player.",
            "If choices_required is true, choices must be concrete, actionable, and mechanically different.",
            "When authoritative_result.strategic_choices is present, copy those choices exactly unless wording must be shortened; preserve id/style/risk/reward/effect_hint/mechanical_effect.",
            "Each choice must include id, text, style, risk, reward, effect_hint, and mechanical_effect. Use 2-4 choices with at least two styles, one low risk option, and one medium/high risk higher reward option.",
            "state_update is only a suggestion and may be ignored by code.",
            "Only mention NPCs by name if they appear in selected_npcs or are explicitly named in authoritative_result.npc_actions. Never invent, import, or introduce NPC names not present in those sources.",
            "selected_npcs may include palace residents or off-screen power holders for context. Only NPCs in present_npc_names or authoritative_result.npc_actions may speak, enter dialogue, react as physically present, or take action.",
            "permitted_npc_names lists every NPC you may name. Referring to any other person by name is forbidden."
        ],
        "permitted_npc_names": selected_names,
        "present_npc_names": turn_context.get("scene_state", {}).get("present_npcs", []),
        "player_input": player_input,
        "judge_result": judge_result,
        "authoritative_result": compact_authoritative,
        "scheme_context": {
            "visible_clues": authoritative_result.get("visible_clues", []) if isinstance(authoritative_result, dict) else [],
            "scheme_events": authoritative_result.get("scheme_events", []) if isinstance(authoritative_result, dict) else [],
            "scheme_pressure": authoritative_result.get("scheme_pressure", []) if isinstance(authoritative_result, dict) else []
        },
        "selected_lore": selected_lore,
        "selected_npcs": compact_npcs,
        "current_state": sanitized_state,
        "scene_state": turn_context.get("scene_state", {}),
        "scene_summary": turn_context.get("scene_summary", (memory or {}).get("scene_summary", "")),
        "recent_turns": turn_context.get("recent_turns", []),
        "fact_sheet": turn_context.get("fact_sheet", (memory or {}).get("fact_sheet", ""))
    }
    return story_system, _json_prompt_payload(story_user)


def _compact_authoritative_result(authoritative_result: dict | None) -> dict:
    if not isinstance(authoritative_result, dict):
        return {}
    update = authoritative_result.get("state_update", {}) if isinstance(authoritative_result.get("state_update"), dict) else {}
    compact_update = {
        key: value for key, value in update.items()
        if key not in {"schemes", "social_graph"} and value not in ({}, [], None, 0)
    }
    return {
        "allowed": authoritative_result.get("allowed", True),
        "reason": authoritative_result.get("reason", ""),
        "confirmed_events": authoritative_result.get("confirmed_events", []),
        "denied_assumptions": authoritative_result.get("denied_assumptions", []),
        "constraints": authoritative_result.get("constraints", []),
        "npc_actions": authoritative_result.get("npc_actions", []),
        "world_event": authoritative_result.get("world_event", {"type": "none", "description": ""}),
        "turn_progress": authoritative_result.get("turn_progress", {}),
        "strategic_choices": authoritative_result.get("strategic_choices", []),
        "state_update": compact_update,
    }


def _compact_npc(npc: dict) -> dict:
    hidden = npc.get("hidden", {}) if isinstance(npc.get("hidden"), dict) else {}
    return {
        "name": npc.get("name", ""),
        "title": npc.get("title", ""),
        "rank": npc.get("rank", ""),
        "location": npc.get("location", ""),
        "description": str(npc.get("description", ""))[:120],
        "personality": str(npc.get("personality", ""))[:120],
        "base_stats": get_npc_stats(npc),
        "hidden_agenda": str(hidden.get("hidden_agenda", ""))[:120],
    }


def fallback_story_result(authoritative_result: dict) -> dict:
    """Final deterministic backup narration when Story Writer output fails validation."""
    authoritative_result = authoritative_result if isinstance(authoritative_result, dict) else {}
    if authoritative_result.get("allowed") is False:
        reason = str(authoritative_result.get("reason") or "這一步暫時不能照原意推進。").strip()
        reply = f"{reason} 殿內的話音被壓低，旁人只當一切仍按規矩走，留給你的餘地也因此變窄。"
    else:
        progress = authoritative_result.get("turn_progress", {})
        progress_type = progress.get("type") if isinstance(progress, dict) else ""
        npc_actions = authoritative_result.get("npc_actions", [])
        world_event = authoritative_result.get("world_event", {}) if isinstance(authoritative_result.get("world_event"), dict) else {}
        if isinstance(npc_actions, list) and npc_actions:
            actor = str(npc_actions[0].get("npc") or "對方").strip()
            desc = str(npc_actions[0].get("description") or "").strip()
            lead = desc if actor in desc else f"{actor}{desc}" if desc.startswith(("把", "借", "順", "沒有", "收")) else f"{actor}有了反應"
            reply = f"{lead}。她沒有把話說死，卻讓旁人看出這句話不能再照原樣追下去。"
        elif world_event.get("type") and world_event.get("type") != "none":
            desc = str(world_event.get("description") or "").strip()
            reply = desc or "殿中忽有旁人傳話，談話被迫收住。"
        elif progress_type == "new_info":
            reply = "對方避開了最要緊的字眼，卻在停頓處露出破綻：她更在意這件事被誰聽見，而不是事情本身。"
        elif progress_type == "relation_shift":
            reply = "對方的語氣比方才鬆了一分，仍守著規矩，卻不再急著把話題推開。"
        elif progress_type == "risk_change":
            reply = "這一步讓場面安靜了片刻。茶盞被重新擺正，旁人的目光也比先前更有分量，後續行事需要更仔細地拿捏聲量。"
        elif progress_type == "objective_update":
            desc = str(progress.get("description") or "").strip() if isinstance(progress, dict) else ""
            forbidden_progress_words = ("短期目標", "向前推進", "進度", "%")
            if desc and not any(word in desc for word in forbidden_progress_words):
                reply = desc
            else:
                reply = "對方沒有把話說透，卻在停頓裡露出顧忌；這份顧忌本身，已經足夠讓局面往前挪動。"
        else:
            reply = "對方按禮回了一句，沒有多給承諾；可她避開的那一處，正好能留作下一步追問。"

    choices = authoritative_result.get("strategic_choices")
    if isinstance(choices, list) and 2 <= len(choices) <= 4:
        return {"reply": reply, "choices": choices, "state_update": {}}
    return {
        "reply": reply,
        "choices": [
            {
                "id": "observe_low",
                "text": "先收住話頭，觀察席間誰接話、誰避開視線",
                "style": "observe",
                "risk": "low",
                "reward": "low",
                "effect_hint": "穩健累積線索，較不容易引人戒備。",
                "mechanical_effect": {"target": "scene", "trust_delta": 0, "suspicion_delta": -1, "anger_delta": 0, "intel_gain": 1, "reputation_delta": 0, "objective_progress_delta": 3},
            },
            {
                "id": "probe_medium",
                "text": "順著方才的話題輕問一句，試探對方願意透露多少",
                "style": "probe",
                "risk": "medium",
                "reward": "medium",
                "effect_hint": "可能得到更明確情報，也會讓對方記住你的關注點。",
                "mechanical_effect": {"target": "primary_npc", "trust_delta": 0, "suspicion_delta": 2, "anger_delta": 0, "intel_gain": 2, "reputation_delta": 0, "objective_progress_delta": 8},
            },
            {
                "id": "retreat_low",
                "text": "藉整理茶盞暫退半步，把主動權留到下一輪",
                "style": "retreat",
                "risk": "low",
                "reward": "low",
                "effect_hint": "降低當下壓力，但進展較慢。",
                "mechanical_effect": {"target": "self", "trust_delta": 0, "suspicion_delta": -2, "anger_delta": 0, "intel_gain": 0, "reputation_delta": 0, "objective_progress_delta": 1},
            },
        ],
        "state_update": {},
    }
