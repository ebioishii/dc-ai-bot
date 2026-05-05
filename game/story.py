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
    compact_authoritative = _compact_authoritative_result(authoritative_result)
    compact_npcs = [_compact_npc(npc) for npc in selected_npcs if isinstance(npc, dict)]
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
            "Do not create, cancel, rename, or redirect NPC schemes. Only reflect scheme_pressure, visible_clues, and scheme_events provided by authoritative_result.",
            "Never reveal scheme ids, hidden goals, numeric progress, numeric risk, or JSON field names in player-facing prose.",
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
        "authoritative_result": compact_authoritative,
        "scheme_context": {
            "visible_clues": authoritative_result.get("visible_clues", []) if isinstance(authoritative_result, dict) else [],
            "scheme_events": authoritative_result.get("scheme_events", []) if isinstance(authoritative_result, dict) else [],
            "scheme_pressure": authoritative_result.get("scheme_pressure", []) if isinstance(authoritative_result, dict) else []
        },
        "selected_lore": selected_lore,
        "selected_npcs": compact_npcs,
        "current_state": sanitized_state,
        "memory_summary": {
            "long_term_summary": (memory or {}).get("long_term_summary", ""),
            "recent_turns": (memory or {}).get("short_term", [])[-3:],
            "fact_sheet": (memory or {}).get("fact_sheet", "")
        }
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


