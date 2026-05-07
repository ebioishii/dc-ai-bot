import json

from game.context import (
    build_model_context,
    compact_memory_window,
    normalize_scene_state,
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
    duplicate_against_recent,
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


def test_duplicate_detection_checks_recent_replies_not_only_previous():
    memory = {
        "short_term": [
            {"user": "a", "bot": "晴蘭沉默地看著你，沒有立刻回答。"},
            {"user": "b", "bot": "宮人低頭整理茶盞，殿內一時安靜。"},
            {"user": "c", "bot": "你把話說出口，晴蘭臉色微白，旁人也都聽見了。"},
        ]
    }

    duplicate = duplicate_against_recent(
        "你把話說出口，晴蘭臉色微白，旁人也都聽見了。",
        memory,
        threshold=0.94,
    )
    fresh = duplicate_against_recent(
        "晴蘭先看向旁邊的宮人，才壓低聲音說此事不能在廊下談。",
        memory,
        threshold=0.94,
    )

    assert duplicate["duplicate"] is True
    assert fresh["duplicate"] is False


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


def test_story_without_choices_rejects_meta_next_step_and_inner_control():
    cases = (
        ("玩家行動完成，局勢略有推進。", "meta"),
        ("接下來，你將如何引導這場對話，是選擇溫和探尋，還是直接施壓？", "choices"),
        ("你決定將此時的局面定格，讓她承受壓力。", "inner"),
    )
    for reply, expected in cases:
        ok, reason = validate_story_output_reason(
            {"reply": reply, "choices": []},
            {"state_update": {}},
            {},
            choices_required=False,
        )
        assert ok is False
        assert expected in reason


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


def test_hint_choices_follow_public_pressure_context():
    choices = plan_strategic_choices(
        {
            "player_intent": "大聲質問晴蘭是不是有人指使她，並說要去慎行司告發",
            "action_type": "pressure",
            "mentioned_npcs": ["晴蘭"],
        },
        {},
        {"status": {}, "scene_npcs": ["晴蘭", "其他宮人"]},
        {"npcs": {"晴蘭": {"alive": True}}},
        {"npcs": [{"name": "晴蘭"}]},
        [{"id": "main", "text": "查清景仁宮局勢", "status": "active", "progress": 0}],
    )
    joined = "\n".join(choice["text"] for choice in choices)

    assert "慎行司" in joined or "主位娘娘" in joined or "管事" in joined
    assert "家常話" not in joined
    assert "給晴蘭留一個能接也能退的台階" not in joined


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


def test_scene_state_tracks_crowd_when_player_addresses_witnesses():
    scene = normalize_scene_state(
        {"location": "景仁宮", "present_npcs": ["晴蘭"]},
        status={"location_name": "景仁宮"},
        scene_npcs=["晴蘭"],
        player_input="讓周圍的人清楚聽見自己的質問，請在場眾人作證",
    )

    assert "晴蘭" in scene["present_npcs"]
    assert "其他宮人" in scene["present_npcs"]


def test_scene_state_keeps_high_rank_audience_as_pending_gate():
    scene = normalize_scene_state(
        {"location": "景仁宮", "present_npcs": ["晴蘭"]},
        status={"location_name": "景仁宮"},
        scene_npcs=["晴蘭"],
        player_input="請求通報陳貴妃，告發晴蘭合謀",
        authoritative_result={
            "state_update": {
                "status_set": {
                    "pending_audience_request": True,
                    "audience_target": "陳貴妃",
                }
            }
        },
    )

    assert scene["phase"] == "audience_request"
    assert scene["pending_audience_request"] is True
    assert scene["audience_target"] == "陳貴妃"
    assert "陳貴妃" not in scene["present_npcs"]
    assert "通報宮人" in scene["present_npcs"]


def test_validation_rejects_auto_granted_high_rank_audience():
    ok, reason = validate_story_output_reason(
        {
            "reply": "陳貴妃緩緩抬眼，聲音平靜地說道：「既然妳有話要稟報，本宮在此聽著。」",
            "choices": [],
        },
        {
            "denied_assumptions": ["high-rank audience is automatically granted"],
            "state_update": {"status_set": {"audience_target": "陳貴妃"}},
        },
        {"scene_state": {"visible_player_action": "請求通報陳貴妃"}, "scene_npcs": ["晴蘭"]},
        choices_required=False,
    )

    assert ok is False
    assert "audience" in reason


def test_validation_rejects_social_turn_that_only_restates_player_dialogue():
    ok, reason = validate_story_output_reason(
        {
            "reply": "你輕聲說道：「今日天氣不錯，倒讓我想起家鄉的風了。」你刻意放緩語速，為彼此留下能接也能退的餘地。",
            "choices": [],
        },
        {
            "relevant_npcs": ["晴蘭"],
            "state_update": {"last_turn_type": "social"},
        },
        {"scene_state": {"visible_player_action": "跟晴蘭寒暄"}, "scene_npcs": ["晴蘭"]},
        choices_required=False,
    )

    assert ok is False
    assert "NPC response" in reason


def test_validation_rejects_story_contradicting_declared_action():
    ok, reason = validate_story_output_reason(
        {
            "reply": "你沒有直接與她們搭話，而是繼續專注於手中的工作。",
            "choices": [],
        },
        {"state_update": {"last_turn_type": "social"}},
        {"scene_state": {"visible_player_action": "跟晴蘭以外的宮人搭話"}, "scene_npcs": ["其他宮人"]},
        choices_required=False,
    )

    assert ok is False
    assert "contradicts" in reason


def test_validation_rejects_repeated_npc_reaction_template():
    ok, reason = validate_story_output_reason(
        {
            "reply": "晴蘭臉色蒼白，眼神閃爍，緊咬下唇，低聲道：「有些事情不是妳想的那樣。」",
            "choices": [],
        },
        {"state_update": {"last_turn_type": "ask"}},
        {"scene_state": {"visible_player_action": "詢問晴蘭"}, "scene_npcs": ["晴蘭"]},
        choices_required=False,
    )

    assert ok is False
    assert "reaction template" in reason


def test_validation_rejects_unjustified_initial_hostility():
    ok, reason = validate_story_output_reason(
        {
            "reply": "晴蘭聞言抬眼看你，神色不悅，語氣也疏離了些：「原來是新來的。」",
            "choices": [],
        },
        {"state_update": {"last_turn_type": "social"}},
        {
            "status": {"turn_count": 1},
            "scene_state": {"visible_player_action": "向晴蘭打招呼，做簡單的自我介紹"},
            "scene_npcs": ["晴蘭"],
            "relations": {"npcs": {"晴蘭": {"好感度": 0, "狀態": "初識", "emotion_state": {"anger": 0}}}},
        },
        choices_required=False,
    )

    assert ok is False
    assert "hostility" in reason


def test_validation_allows_initial_polite_reservation():
    ok, reason = validate_story_output_reason(
        {
            "reply": "晴蘭聞言停下手裡的活，先向旁邊宮人讓了半步，才照規矩回了一禮：「姑娘初來，值房裡多是瑣事，慢慢熟便是。」",
            "choices": [],
        },
        {"state_update": {"last_turn_type": "social"}},
        {
            "status": {"turn_count": 1},
            "scene_state": {"visible_player_action": "向晴蘭打招呼，做簡單的自我介紹"},
            "scene_npcs": ["晴蘭"],
            "relations": {"npcs": {"晴蘭": {"好感度": 0, "狀態": "初識", "emotion_state": {"anger": 0}}}},
        },
        choices_required=False,
    )

    assert ok is True, reason


def test_ooc_extracts_target_action_without_recording_generic_rewrite_as_fact():
    correction = "你沒有描寫劇情，我的行動是「詢問婉貴人：姊姊看著很困擾，是跟襄嬪娘娘有什麼糾紛嗎」，以此重新生成一次"
    last_exchange = {"user": "原本行動", "bot": "錯誤 fallback"}

    assert extract_ooc_target_action(correction, last_exchange) == "詢問婉貴人：姊姊看著很困擾，是跟襄嬪娘娘有什麼糾紛嗎"
    assert should_record_ooc_fact(correction) is False
    assert should_record_ooc_fact("設定：婉貴人此時沒有離開長春宮") is True


def test_ooc_rewrite_rejects_new_arrival_and_repeated_setup():
    assert ooc_rewrite_problem("殿外傳來急促的腳步聲，襄嬪娘娘駕到。") == "rewrite invented a new arrival/interruption/event"
    assert ooc_rewrite_problem("這表明她並非全然屈服，玩家接下來需要決定如何行動。") == "story included meta/system phrasing"
    assert ooc_rewrite_problem(
        "長春宮偏殿窗下香灰尚新，案上只擺著內務府按例送來的器物。",
        previous_valid_reply="長春宮偏殿窗下香灰尚新，案上只擺著內務府按例送來的器物。",
    ) == "rewrite repeated too much previous narration"
