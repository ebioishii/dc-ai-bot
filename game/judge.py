from __future__ import annotations
import json

from services.gemini_client import call_gemini_json

JUDGE_AI_MODEL = "gemini-2.5-flash"

def judge_fallback() -> dict:
    return {
        "intent": "unknown",
        "player_intent": "unknown",
        "action_type": "unknown",
        "social_tone": "neutral",
        "risk_level": "medium",
        "possible_misread": "",
        "mentioned_npcs": [],
        "mentioned_items": [],
        "assumptions": [],
        "risk_flags": ["judge_ai_failed"],
        "mechanical_tags": []
    }


async def call_judge_ai(system, user):
    data = await call_gemini_json(
        system,
        user,
        model=JUDGE_AI_MODEL,
        temperature=0.2,
        max_tokens=1000
    )
    if not isinstance(data, dict):
        return judge_fallback()

    fallback = judge_fallback()
    result = {
        "intent": str(data.get("intent") or fallback["intent"])[:300],
        "player_intent": str(data.get("player_intent") or data.get("intent") or fallback["player_intent"])[:300],
        "action_type": str(data.get("action_type") or fallback["action_type"]),
        "social_tone": str(data.get("social_tone") or fallback["social_tone"]),
        "risk_level": str(data.get("risk_level") or fallback["risk_level"]),
        "possible_misread": str(data.get("possible_misread") or "")[:300],
        "mentioned_npcs": data.get("mentioned_npcs") if isinstance(data.get("mentioned_npcs"), list) else [],
        "mentioned_items": data.get("mentioned_items") if isinstance(data.get("mentioned_items"), list) else [],
        "assumptions": data.get("assumptions") if isinstance(data.get("assumptions"), list) else [],
        "risk_flags": data.get("risk_flags") if isinstance(data.get("risk_flags"), list) else [],
        "mechanical_tags": data.get("mechanical_tags") if isinstance(data.get("mechanical_tags"), list) else []
    }
    allowed_types = {"move", "ask", "attack", "wait", "observe", "social", "use_item", "other", "unknown"}
    if result["action_type"] not in allowed_types:
        result["action_type"] = "other"
    allowed_tones = {"humble", "rude", "probing", "evasive", "flattering", "neutral"}
    if result["social_tone"] not in allowed_tones:
        result["social_tone"] = "neutral"
    allowed_risks = {"low", "medium", "high"}
    if result["risk_level"] not in allowed_risks:
        result["risk_level"] = "medium"
    return result


def _json_prompt_payload(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def build_judge_prompt(player_input, game_state, memory, relations, inventory, turn_context: dict | None = None):
    turn_context = turn_context or {}
    judge_system = (
        "You are AI 1: Intent / Judge AI for a Discord text game. "
        "Only understand player input, identify intent, risks, mentions, and assumptions. "
        "Do not write fiction, narration, dialogue, or player-facing story. "
        "Output JSON only."
    )
    judge_user = {
        "task": "Parse player_input into this exact JSON shape.",
        "schema": {
            "intent": "玩家真正想達成的目的",
            "player_intent": "玩家真正想達成的目的，與 intent 相同或更精準",
            "action_type": "move | ask | attack | wait | observe | social | use_item | other",
            "social_tone": "humble | rude | probing | evasive | flattering | neutral",
            "risk_level": "low | medium | high",
            "possible_misread": "NPC 可能如何誤解玩家行動",
            "mentioned_npcs": [],
            "mentioned_items": [],
            "assumptions": [],
            "risk_flags": [],
            "mechanical_tags": []
        },
        "rules": [
            "assumptions are claims from the player that are not guaranteed by current state.",
            "risk_flags should include possible godmoding, impossible item use, dead NPC mention, rank overreach, or state-changing assumptions.",
            "Do not flatter the player. If the wording could be read as rude, provocative, evasive, or overreaching, mark it clearly.",
            "If the player assumes events such as 'betting the emperor passes by', put that claim in assumptions instead of treating it as fact.",
            "mechanical_tags should be short tags such as high_rank_target, provocation, information_probe, item_claim, emperor_assumption, retreat, wait.",
            "Do not decide world state. Do not confirm events."
        ],
        "player_input": player_input,
        "current_state": game_state,
        "scene_state": turn_context.get("scene_state", {}),
        "scene_summary": turn_context.get("scene_summary", (memory or {}).get("scene_summary", "")),
        "recent_turns": turn_context.get("recent_turns", []),
        "fact_sheet": turn_context.get("fact_sheet", (memory or {}).get("fact_sheet", "")),
        "known_relations": relations or {},
        "inventory": inventory or {"items": []}
    }
    return judge_system, _json_prompt_payload(judge_user)


