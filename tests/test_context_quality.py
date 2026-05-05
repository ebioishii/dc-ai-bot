import json

from game.context import (
    build_model_context,
    compact_memory_window,
    output_length_policy,
)
from game.formatting import format_story_reply
from game.performance import log_reply_performance
from game.quality import (
    chinese_char_count,
    finalize_story_result,
    inspect_story_quality,
    natural_next_step_hint,
    sanitize_player_visible_text,
)


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
