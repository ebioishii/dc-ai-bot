from __future__ import annotations
from game.state import _active_summons, default_state_update
from game.npc import _add_hidden_delta, _add_relation_delta, _hidden_state_for, _npc_by_name, _primary_npc

def plan_world_event(judge_result: dict, game_state: dict, relations: dict | None, gamedata: dict) -> dict:
    status = game_state.get("status", {}) if isinstance(game_state, dict) else {}
    next_turn = int(status.get("turn_count", 0) or 0) + 1
    last_event_turn = int(status.get("last_world_event_turn", 0) or 0)
    if _active_summons(game_state) or next_turn - last_event_turn < 4 or next_turn % 4 != 0:
        return {"type": "none", "description": "", "state_update": {}}

    primary = _primary_npc(
        [str(x) for x in judge_result.get("mentioned_npcs", []) if str(x).strip()],
        game_state,
        gamedata,
        relations
    )
    if primary and _hidden_state_for(relations, primary).get("suspicion", 0) >= 60:
        return {
            "type": "overheard",
            "description": "簾外有宮人腳步略停，像是聽見了殿內隻字片語。",
            "state_update": {
                "status_set": {"last_world_event_turn": next_turn},
                "hidden_state_delta": {primary: {"suspicion": 2}}
            }
        }
    return {
        "type": "interruption",
        "description": "殿外傳來短促通報聲，打斷了原本過於安靜的氣氛。",
        "state_update": {"status_set": {"last_world_event_turn": next_turn}}
    }


