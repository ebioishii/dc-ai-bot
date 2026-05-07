import json

from game.context import (
    build_model_context,
    compact_memory_window,
    output_length_policy,
)
from game.formatting import format_story_reply
from game.hints import compact_hints_for_status, format_hint_reply
from game.memory import clean_reply_for_memory
from game.ooc import (
    extract_ooc_target_action,
    ooc_rewrite_problem,
    should_record_ooc_fact,
)
from game.performance import log_reply_performance
from game.quality import (
    chinese_char_count,
    finalize_story_result,
    inspect_story_quality,
    natural_next_step_hint,
    sanitize_player_visible_text,
)
from game.story import fallback_story_result, suppress_choices_when_disabled
from game.validation import validate_story_output_reason
from game.state import normalize_memory_record
from game.rules import plan_strategic_choices
from game.mechanics import evaluate_player_action_costs


def _long_memory(count=30):
    return {
        "short_term": [
            {
                "user": f"第{i}輪原文：我在殿內試探平答應並留意宮人。",
                "bot": f"第{i}輪原文：平答應回應，宮人交換眼色，場面留下可疑線索。"
            }
            for i in range(count)
        ],
        "scene_summary": "",
        "scene_state": {},
        "summary_turns_since_update": 5,
        "fact_sheet": "平答應仍在場。",
    }


def test_long_history_uses_scene_summary_and_recent_turns_only():
    memory, triggered = compact_memory_window(
        _long_memory(),
        status={"location": "長春宮"},
        relations={"npcs": {"平答應": {"好感度": 5, "alive": True}}},
        force=True,
    )
    context = build_model_context(
        memory,
        status={"location": "長春宮"},
        relations={"npcs": {"平答應": {"好感度": 5, "alive": True}}},
        scene_npcs=["平答應"],
        player_input="我低聲安慰她。",
        recent_turns=4,
    )
    payload = json.dumps(context, ensure_ascii=False)

    assert triggered is True
    assert "scene_summary" in context
    assert "scene_state" in context
    assert 3 <= len(context["recent_turns"]) <= 6
    assert len(memory["short_term"]) <= 6
    assert len(memory["scene_summary"]) <= 600
    assert "第0輪原文" not in payload
    assert "第1輪原文" not in payload
    assert "第29輪原文" in payload


def test_normal_interaction_reply_length_and_no_fixed_choices():
    reply = (
        "平答應的指尖仍扣著袖口，聽見你低聲安慰，肩背先是一僵，隨即慢慢垂下。"
        "她沒有立刻回話，只把額角貼近地磚，像是借著你的聲音穩住呼吸。"
        "旁邊一名宮人抬眼看了你一瞬，又很快低頭，這份多出的溫和沒有被完全忽略。"
        "殿內的沉默因此稍稍鬆開，卻也讓你們兩人的舉動落進旁人的餘光，留下後續被問起的可能。"
    )
    story_result = {
        "reply": reply,
        "choices": [
            {"text": "繼續安慰", "effect_hint": "降低她的慌亂"},
            {"text": "觀察宮人", "effect_hint": "留意誰在看"},
            {"text": "退後", "effect_hint": "降低被注意"},
            {"text": "詢問她", "effect_hint": "可能取得線索"},
        ],
    }

    final, _ = finalize_story_result(story_result, length_policy=output_length_policy("normal"))
    text = format_story_reply(final, show_choices=False, natural_hint=natural_next_step_hint(final))

    assert 120 <= chinese_char_count(final["reply"]) <= 250
    assert "【可選行動】" not in text
    assert "1." not in text and "4." not in text
    assert "你心中" not in text and "恐懼" not in text
    assert "平答應" in text
    assert "宮人" in text or "注意" in text


def test_debug_labels_are_removed_from_player_visible_text():
    raw = "劇情修正：上一幕需要改\n修正意見：不要出現\n已使用 OOC\n平答應低聲應了一句。"
    cleaned = sanitize_player_visible_text(raw)

    assert "劇情修正" not in cleaned
    assert "修正意見" not in cleaned
    assert "已使用 OOC" not in cleaned
    assert cleaned == "平答應低聲應了一句。"


def test_duplicate_reply_recommends_single_retry_trigger():
    previous = "平答應低頭不語，殿內宮人交換眼色，氣氛一時凝住。"
    quality = inspect_story_quality(
        "平答應低頭不語，殿內宮人交換眼色，氣氛一時凝住。",
        previous_reply=previous,
        max_chars=250,
    )

    assert quality["duplicate"] is True
    assert quality["retry_recommended"] is True


def test_performance_log_contains_duration_and_token_estimates(capsys):
    payload = log_reply_performance({
        "channel_id": "123",
        "input_tokens_est": 1800,
        "output_tokens_est": 350,
        "model_duration_ms": 8200,
        "total_duration_ms": 9300,
        "retry_count": 0,
        "summary_used": True,
        "summary_triggered": False,
        "recent_turns": 4,
    })
    printed = json.loads(capsys.readouterr().out)

    assert payload["model_duration_ms"] == 8200
    assert payload["total_duration_ms"] == 9300
    assert payload["input_tokens_est"] == 1800
    assert printed["recent_turns"] == 4


def test_memory_stores_narration_without_discord_ui_blocks():
    reply = (
        "殿內茶香未散，陸常在的目光在點心上停了一瞬。"
        "\n\n【可選行動】\n1. 觀察\n   ㄴ 效果提示：穩健。"
        "\n\n【當前目標】\n- 了解承乾宮"
    )

    cleaned = clean_reply_for_memory(reply)

    assert cleaned == "殿內茶香未散，陸常在的目光在點心上停了一瞬。"
    assert "【可選行動】" not in cleaned
    assert "【當前目標】" not in cleaned


def test_fallback_story_does_not_expose_mechanical_progress_label():
    result = fallback_story_result({
        "turn_progress": {
            "type": "objective_update",
            "description": "短期目標向前推進了一小步。",
            "state_update": {},
        },
        "strategic_choices": [
            {
                "id": "observe",
                "text": "觀察席間反應",
                "style": "observe",
                "risk": "low",
                "reward": "low",
                "effect_hint": "穩健掌握線索。",
                "mechanical_effect": {"target": "scene", "trust_delta": 0, "suspicion_delta": 0, "anger_delta": 0, "intel_gain": 1, "reputation_delta": 0, "objective_progress_delta": 3},
            },
            {
                "id": "probe",
                "text": "順勢試探一句",
                "style": "probe",
                "risk": "medium",
                "reward": "medium",
                "effect_hint": "可能換得更多情報。",
                "mechanical_effect": {"target": "primary_npc", "trust_delta": 0, "suspicion_delta": 2, "anger_delta": 0, "intel_gain": 2, "reputation_delta": 0, "objective_progress_delta": 8},
            },
        ],
    })

    assert "短期目標向前推進" not in result["reply"]
    assert "顧忌" in result["reply"]


def test_story_choices_are_suppressed_before_no_choice_validation():
    story_result = {
        "reply": "陸常在看了你一眼，語氣比先前平穩。",
        "choices": [{"id": "probe", "text": "追問一句"}],
        "state_update": {},
    }

    cleaned = suppress_choices_when_disabled(story_result, choices_required=False)
    ok, reason = validate_story_output_reason(
        cleaned,
        {"state_update": {}},
        {},
        choices_required=False,
    )

    assert cleaned["choices"] == []
    assert ok is True


def test_story_without_choices_rejects_action_menu_and_unruled_gift():
    ok, reason = validate_story_output_reason(
        {"reply": "殿內一時安靜，宮人垂手退到簾邊。", "choices": [{"id": "observe", "text": "觀察"}]},
        {"state_update": {}},
        {},
        choices_required=False,
    )
    assert ok is False
    assert "choices" in reason

    ok, reason = validate_story_output_reason(
        {"reply": "你可以先觀察。", "choices": []},
        {"state_update": {}},
        {},
        choices_required=False,
    )
    assert ok is False
    assert "choices" in reason

    ok, reason = validate_story_output_reason(
        {"reply": "你沒有立刻得到明白答案，但殿內的回話順序與侍從動線已經露出一點端倪。", "choices": []},
        {"state_update": {}},
        {},
        choices_required=False,
    )
    assert ok is False
    assert "stock" in reason

    ok, reason = validate_story_output_reason(
        {"reply": "李貴妃把玉佩遞給你。", "choices": []},
        {"state_update": {}},
        {},
        choices_required=False,
    )
    assert ok is False
    assert "gift" in reason

    ok, _ = validate_story_output_reason(
        {"reply": "李貴妃把玉佩遞給你。", "choices": []},
        {"state_update": {"inventory_add": ["玉佩"]}},
        {},
        choices_required=False,
    )
    assert ok is True


def test_hint_formatter_shows_objectives_and_last_hints():
    status = {
        "location_name": "承乾宮",
        "scene_state": {"location": "承乾宮", "present_npcs": ["陸常在"]},
        "current_objectives": [{"id": "main", "text": "探清承乾宮局勢", "status": "active", "progress": 20}],
        "last_hints": compact_hints_for_status([
            {
                "id": "observe",
                "text": "先觀察殿內眾人的反應",
                "style": "observe",
                "risk": "low",
                "reward": "low",
                "effect_hint": "降低誤判，取得細節",
                "mechanical_effect": {"target": "scene"},
            }
        ]),
    }

    text = format_hint_reply(status, {})

    assert "探清承乾宮局勢" in text
    assert "先觀察殿內眾人的反應" in text
    assert "陸常在" in text


def test_hint_formatter_handles_empty_hints():
    text = format_hint_reply({"current_objectives": []}, {})

    assert "目前沒有建議行動" in text


def test_hint_choices_follow_paper_context():
    choices = plan_strategic_choices(
        {"player_intent": "問陸常在這個紙箋是不是姊姊的東西", "action_type": "ask", "mentioned_npcs": ["陸常在"]},
        {},
        {"status": {}, "scene_npcs": ["陸常在"]},
        {"npcs": {"陸常在": {"alive": True}}},
        {"npcs": [{"name": "陸常在"}]},
        [{"id": "main", "text": "查紙箋", "status": "active", "progress": 0}],
    )
    joined = "\n".join(choice["text"] for choice in choices)

    assert "紙箋" in joined
    assert "點心" not in joined


def test_food_social_action_updates_relation_state():
    result = evaluate_player_action_costs(
        {"player_intent": "請陸常在吃異國點心，自己先吃一塊證明無毒", "action_type": "social", "mentioned_npcs": ["陸常在"]},
        {"scene_npcs": ["陸常在"], "status": {"attributes": {"體力": 90, "權謀": 10, "聲望": 5, "財產": 3000}}},
        {"npcs": {"陸常在": {"好感度": 0, "alive": True}}},
        {"npcs": [{"name": "陸常在"}]},
    )

    assert result["state_update"]["relations_delta"]["陸常在"]["好感度"] > 0
    assert result["state_update"]["hidden_state_delta"]["陸常在"]["trust"] > 0


def test_memory_record_is_summary_only_after_normalization():
    memory = {
        "short_term": [],
        "scene_state": {"location": "wrong"},
        "current_objectives": [{"id": "old", "text": "old", "status": "active", "progress": 1}],
    }
    status = {
        "current_objectives": [
            {"id": "main", "text": "follow the authoritative status objective", "status": "active", "progress": 10}
        ]
    }

    normalized = normalize_memory_record(memory, status)

    assert normalized["_meta"]["role"] == "non_authoritative_ai_memory"
    assert "scene_state" not in normalized
    assert "current_objectives" not in normalized
    assert normalized["objective_summary"] == ["follow the authoritative status objective"]


def test_model_context_prefers_status_scene_state_over_memory_cache():
    context = build_model_context(
        {"scene_state": {"location": "memory-place", "present_npcs": ["Memory NPC"]}, "short_term": []},
        status={"location_name": "status-place", "scene_state": {"location": "status-place", "present_npcs": ["Status NPC"]}},
        relations={"npcs": {"Status NPC": {"emotion_state": {}, "alive": True}}, "hidden_state": {}},
        player_input="look around",
    )

    assert context["scene_state"]["location"] == "status-place"
    assert context["scene_state"]["present_npcs"] == ["Status NPC"]


def test_ooc_extracts_target_action_without_recording_generic_rewrite_as_fact():
    correction = "你沒有描寫劇情，我的行動是「詢問婉貴人：姊姊看著很困擾，是跟襄嬪娘娘有什麼糾紛嗎」，以此重新生成一次"
    last_exchange = {"user": "原本行動", "bot": "錯誤 fallback"}

    assert extract_ooc_target_action(correction, last_exchange) == "詢問婉貴人：姊姊看著很困擾，是跟襄嬪娘娘有什麼糾紛嗎"
    assert should_record_ooc_fact(correction) is False
    assert should_record_ooc_fact("設定：婉貴人此時沒有離開長春宮") is True


def test_ooc_rewrite_rejects_new_arrival_and_repeated_setup():
    assert ooc_rewrite_problem("殿外傳來急促的腳步聲，襄嬪娘娘駕到。") == "rewrite invented a new arrival/interruption/event"
    assert ooc_rewrite_problem(
        "長春宮偏殿窗下香灰尚新，案上只擺著內務府按例送來的器物。",
        previous_valid_reply="長春宮偏殿窗下香灰尚新，案上只擺著內務府按例送來的器物。",
    ) == "rewrite repeated too much previous narration"
