from game.schemes import (
    advance_schemes,
    ensure_scheme_state,
    expose_scheme_clues,
    maybe_create_scheme,
    resolve_scheme_by_player_action,
)
from game.npc import extract_companion_candidates, plan_npc_actions
from game.mechanics import evaluate_player_action_costs, update_social_graph_from_turn
from game.rules import resolve_rules
from game.validation import validate_state_update


def _gamedata():
    return {
        "npcs": [
            {
                "name": "皇后",
                "rank": "皇后",
                "base_stats": {"心機": 92, "權謀": 96, "聲望": 80, "智力": 85, "生命": 95},
                "hidden": {"hidden_agenda": "保住后位，打壓得寵新人"},
            },
            {
                "name": "德宣帝",
                "rank": "皇帝",
                "base_stats": {"心機": 85, "權謀": 95, "聲望": 100, "智力": 86, "生命": 120},
            },
        ],
        "ranks": [
            {"name": "皇帝", "level": 1},
            {"name": "皇后", "level": 4},
        ],
        "strategies": [
            {"id": "li_jian_ji", "name": "離間計", "stat_requirement": {"心機": 60, "聲望": 20}},
            {"id": "yin_she_chu_dong", "name": "引蛇出洞", "stat_requirement": {"心機": 55, "智力": 50}},
            {"id": "jie_dao_sha_ren", "name": "借刀殺人", "stat_requirement": {"心機": 70, "權謀": 50}},
            {"id": "tao_ren_xin", "name": "攏絡人心", "stat_requirement": {"財產": 40}},
        ],
    }


def _game_state(intrigue=10, reputation=0, turn=5):
    return {
        "status": {"turn_count": turn, "attributes": {"體力": 100, "權謀": intrigue, "聲望": reputation, "財產": 10}},
        "scene_npcs": ["皇后"],
    }


def _relations():
    return {
        "npcs": {"皇后": {"好感度": -5, "alive": True, "emotion_state": {"anger": 10, "fear": 0}}},
        "companions": {},
        "hidden_state": {"皇后": {"suspicion": 70, "interest": 20, "anger": 20, "trust": -5}},
    }


def test_missing_schemes_are_added_for_old_relations():
    relations = ensure_scheme_state({"npcs": {}, "companions": {}})

    assert relations["schemes"] == []
    assert relations["social_graph"] == {}


def test_companion_candidate_filter_rejects_generic_fragments():
    text = "你命身旁的宮女退下，青蘭侍女上前奉茶，身旁的太監沒有留名。"

    candidates = extract_companion_candidates(text)

    assert "青蘭" in candidates
    assert "你命" not in candidates
    assert "身旁" not in candidates


def test_legacy_birth_seeded_scheme_is_pruned_without_touching_player_file():
    relations = ensure_scheme_state({
        "npcs": {"李貴妃": {"alive": True}},
        "companions": {},
        "schemes": [
            {
                "id": "scheme_0_1",
                "owner": "李貴妃",
                "target": "玩家",
                "strategy_id": "li_jian_ji",
                "goal": "李貴妃想削弱玩家在後宮中的信任與依附",
                "stage": "seeded",
                "progress": 10,
                "risk": 32,
                "clues": [],
                "known_by_player": False,
                "created_turn": 0,
                "last_advanced_turn": 0,
            }
        ],
    })

    assert relations["schemes"] == []


def test_created_scheme_keeps_owner_target_and_goal_when_advanced():
    relations = _relations()
    owner_record = next(iter(relations["npcs"].values()))
    owner_record["contact_count"] = 1
    owner_record["last_interaction_turn"] = 4
    notes = maybe_create_scheme(
        {"risk_level": "high", "social_tone": "probing", "mentioned_npcs": ["皇后"]},
        _game_state(turn=5),
        relations,
        _gamedata(),
    )
    assert notes
    scheme = relations["schemes"][0]
    original = (scheme["owner"], scheme["target"], scheme["goal"])

    advance_schemes({}, _game_state(turn=6), relations, _gamedata())

    assert (scheme["owner"], scheme["target"], scheme["goal"]) == original
    assert scheme["stage"] in {"seeded", "developing", "exposed"}


def test_npc_action_requires_physical_presence_and_uses_profile_basis():
    gamedata = {
        "npcs": [{
            "name": "李貴妃",
            "rank": "貴妃",
            "base_stats": {"心機": 75, "權謀": 70, "聲望": 70},
            "personality": "趨炎附勢，牆頭草，喜歡在背後嚼舌根，喜歡掌握權力",
            "hidden": {"hidden_agenda": "依附皇貴妃，藉此打擊皇后勢力"},
        }],
        "ranks": [{"name": "貴妃", "level": 4}],
    }
    relations = {
        "npcs": {"李貴妃": {"alive": True}},
        "hidden_state": {"李貴妃": {"suspicion": 70, "anger": 0, "trust": 0}},
    }
    judge = {"mentioned_npcs": ["李貴妃"], "social_tone": "probing", "risk_level": "medium"}

    assert plan_npc_actions(judge, {"scene_npcs": []}, relations, gamedata) == []
    actions = plan_npc_actions(judge, {"scene_npcs": ["李貴妃"]}, relations, gamedata)

    assert actions
    assert actions[0]["type"] in {"test", "soft_attack"}
    assert "牆頭草" in actions[0]["personality_basis"]


def test_offscreen_high_rank_npc_cannot_create_birth_scheme():
    gamedata = {
        "npcs": [
            {
                "name": "皇后",
                "rank": "皇后",
                "base_stats": {"心機": 95, "權謀": 95, "聲望": 90},
            },
            {
                "name": "襄嬪",
                "rank": "嬪",
                "base_stats": {"心機": 45, "權謀": 45, "聲望": 40},
            },
        ],
        "ranks": [{"name": "皇后", "level": 1}, {"name": "嬪", "level": 8}],
        "strategies": [{"id": "yin_she_chu_dong", "name": "引蛇出洞", "stat_requirement": {"心機": 60}}],
    }
    relations = {
        "npcs": {"襄嬪": {"好感度": 0, "alive": True, "emotion_state": {"anger": 0, "fear": 0}}},
        "companions": {},
        "hidden_state": {
            "皇后": {"suspicion": 95, "interest": 60, "anger": 0, "trust": 0},
            "襄嬪": {"suspicion": 30, "interest": 10, "anger": 0, "trust": 0},
        },
    }

    notes = maybe_create_scheme(
        {"risk_level": "high", "social_tone": "probing", "mentioned_npcs": []},
        {"status": {"turn_count": 0, "attributes": {"權謀": 10, "聲望": 30}}, "scene_npcs": ["襄嬪"]},
        relations,
        gamedata,
    )

    assert notes == []
    assert relations["schemes"] == []


def test_scene_resident_without_actual_contact_cannot_start_scheme():
    gamedata = {
        "npcs": [{
            "name": "李貴妃",
            "rank": "貴妃",
            "base_stats": {"心機": 90, "權謀": 90, "聲望": 80},
        }],
        "ranks": [{"name": "貴妃", "level": 4}],
        "strategies": [{"id": "li_jian_ji", "stat_requirement": {"心機": 60}}],
    }
    relations = {
        "npcs": {"李貴妃": {"好感度": 0, "alive": True}},
        "hidden_state": {"李貴妃": {"suspicion": 80, "interest": 80, "anger": 20}},
        "schemes": [],
        "companions": {},
        "social_graph": {},
    }

    notes = maybe_create_scheme(
        {"risk_level": "high", "social_tone": "probing", "mentioned_npcs": ["李貴妃"]},
        {"status": {"turn_count": 1, "attributes": {"權謀": 10, "聲望": 5}}, "scene_npcs": ["李貴妃"]},
        relations,
        gamedata,
    )

    assert notes == []
    assert relations["schemes"] == []


def test_high_intrigue_player_gets_scheme_clue():
    relations = ensure_scheme_state(_relations())
    relations["schemes"].append({
        "id": "scheme_1",
        "owner": "皇后",
        "target": "玩家",
        "strategy_id": "yin_she_chu_dong",
        "goal": "皇后想試探玩家是否藏有野心或把柄",
        "stage": "developing",
        "progress": 35,
        "risk": 20,
        "clues": [],
        "known_by_player": False,
        "created_turn": 3,
        "last_advanced_turn": 4,
    })

    clues = expose_scheme_clues(
        {"action_type": "observe", "player_intent": "觀察殿內眾人的口風"},
        _game_state(intrigue=95),
        relations,
        _gamedata(),
    )

    assert clues
    assert relations["schemes"][0]["clues"]


def test_player_action_can_fail_a_known_scheme():
    relations = ensure_scheme_state(_relations())
    relations["schemes"].append({
        "id": "scheme_1",
        "owner": "皇后",
        "target": "玩家",
        "strategy_id": "li_jian_ji",
        "goal": "皇后想削弱玩家在後宮中的信任與依附",
        "stage": "exposed",
        "progress": 45,
        "risk": 60,
        "clues": ["兩名宮人說起同一件事時，細節竟像被人刻意改過。"],
        "known_by_player": True,
        "created_turn": 3,
        "last_advanced_turn": 4,
    })

    notes = resolve_scheme_by_player_action(
        {"player_intent": "揭穿皇后暗中散布的流言", "mentioned_npcs": ["皇后"]},
        _game_state(intrigue=90),
        relations,
        _gamedata(),
    )

    assert notes
    assert relations["schemes"][0]["stage"] == "failed"


def test_dead_npc_cannot_advance_active_scheme():
    relations = ensure_scheme_state(_relations())
    relations["npcs"]["皇后"]["alive"] = False
    relations["schemes"].append({
        "id": "scheme_1",
        "owner": "皇后",
        "target": "玩家",
        "strategy_id": "li_jian_ji",
        "goal": "皇后想削弱玩家在後宮中的信任與依附",
        "stage": "developing",
        "progress": 45,
        "risk": 10,
        "clues": [],
        "known_by_player": False,
        "created_turn": 3,
        "last_advanced_turn": 4,
    })

    advance_schemes({}, _game_state(turn=6), relations, _gamedata())

    assert relations["schemes"][0]["stage"] == "failed"


def test_story_state_update_cannot_override_schemes():
    assert validate_state_update({"schemes": []}, {"allowed": True}, {}) is False


def test_stamina_blocks_overexertion_against_high_life_npc():
    state = _game_state()
    state["status"]["attributes"]["體力"] = 10
    result = evaluate_player_action_costs(
        {"action_type": "attack", "player_intent": "攻擊德宣帝", "mentioned_npcs": ["德宣帝"]},
        state,
        _relations(),
        _gamedata(),
    )

    assert result["allowed"] is False
    assert any("stamina" in item for item in result["constraints"])


def test_wealth_cost_blocks_bribe_when_poor():
    state = _game_state()
    state["status"]["attributes"]["財產"] = 5
    result = evaluate_player_action_costs(
        {"action_type": "social", "player_intent": "收買皇后身邊的宮人", "mentioned_npcs": ["皇后"]},
        state,
        _relations(),
        _gamedata(),
    )

    assert result["allowed"] is False
    assert any("wealth" in item for item in result["constraints"])


def test_public_accusation_creates_reputation_and_evidence_risk():
    gamedata = {
        "npcs": [{"name": "晴蘭", "rank": "宮女", "base_stats": {"體力": 30}}],
        "ranks": [{"name": "宮女", "level": 9}],
    }
    relations = {
        "npcs": {"晴蘭": {"好感度": 0, "alive": True}},
        "hidden_state": {"晴蘭": {"suspicion": 0, "anger": 0, "trust": 0}},
    }
    result = evaluate_player_action_costs(
        {
            "action_type": "pressure",
            "player_intent": "大聲質問晴蘭是不是有人指使她，讓周圍宮人作證，說要去慎行司告發她合謀",
            "mentioned_npcs": ["晴蘭"],
        },
        {"status": {"attributes": {"體力": 100, "權謀": 30, "聲望": 5, "財產": 0}}, "scene_npcs": ["晴蘭"]},
        relations,
        gamedata,
    )

    assert result["allowed"] is True
    assert result["state_update"]["attributes_delta"]["聲望"] < 0
    assert result["state_update"]["hidden_state_delta"]["晴蘭"]["suspicion"] > 0
    assert any("public_pressure" in item for item in result["constraints"])
    assert any("accusation_requires_evidence" in item for item in result["constraints"])
    assert "accusation is already proven true" in result["denied_assumptions"]


def test_high_rank_audience_request_does_not_auto_grant_meeting():
    gamedata = {
        "npcs": [
            {"name": "陳貴妃", "rank": "貴妃", "base_stats": {"權謀": 90}},
            {"name": "晴蘭", "rank": "宮女", "base_stats": {}},
        ],
        "ranks": [{"name": "貴妃", "level": 4}, {"name": "宮女", "level": 9}],
    }
    relations = {
        "npcs": {"陳貴妃": {"alive": True}, "晴蘭": {"alive": True}},
        "hidden_state": {"陳貴妃": {}, "晴蘭": {}},
    }

    result = resolve_rules(
        {
            "action_type": "social",
            "player_intent": "直接向景仁宮的主位娘娘陳貴妃通報，請求會面後向娘娘告發晴蘭合謀",
            "mentioned_npcs": ["陳貴妃", "晴蘭"],
            "mentioned_items": [],
            "assumptions": [],
            "social_tone": "neutral",
            "risk_level": "high",
            "mechanical_tags": [],
        },
        {
            "profile": {"rank": "宮女"},
            "status": {"attributes": {"體力": 100, "權謀": 30, "聲望": 0, "財產": 0}, "turn_count": 1},
            "scene_npcs": ["晴蘭", "其他宮人"],
        },
        {},
        relations,
        {"items": []},
        gamedata,
    )

    assert result["allowed"] is True
    assert "high-rank audience is automatically granted" in result["denied_assumptions"]
    assert any("audience_gate" in item for item in result["constraints"])
    assert result["state_update"]["status_set"]["pending_audience_request"] is True
    assert result["state_update"]["status_set"]["audience_target"] == "陳貴妃"


def test_replacing_palace_furnishing_without_permission_is_rule_risk():
    result = evaluate_player_action_costs(
        {
            "action_type": "other",
            "player_intent": "將枯萎的蘭花丟掉，並擺上新的蘭花",
            "mentioned_npcs": [],
        },
        {"status": {"attributes": {"體力": 100, "權謀": 30, "聲望": 5, "財產": 0}}, "scene_npcs": []},
        {"npcs": {}, "hidden_state": {}},
        {"npcs": [], "ranks": []},
    )

    assert any("palace_property_permission" in item for item in result["constraints"])
    assert "player may freely replace or discard palace property" in result["denied_assumptions"]
    assert result["state_update"]["attributes_delta"]["聲望"] < 0


def test_social_graph_records_attention_and_grudge():
    relations = _relations()
    relations["npcs"]["皇后"]["恩怨"] = "曾遭玩家冒犯或攻擊"
    update_social_graph_from_turn(
        relations,
        {"player_intent": "觀察皇后", "mentioned_npcs": ["皇后"]},
        _game_state(),
        _gamedata(),
    )

    edge = relations["social_graph"]["皇后"]["玩家"]
    assert edge["attention"] > 0
    assert edge["grudge"] > 0


def test_companion_network_helps_expose_scheme():
    relations = ensure_scheme_state(_relations())
    relations["companions"]["青蘭"] = {"role": "隨侍", "desc": "", "appear_count": 20}
    relations["schemes"].append({
        "id": "scheme_1",
        "owner": "皇后",
        "target": "玩家",
        "strategy_id": "yin_she_chu_dong",
        "goal": "皇后想試探玩家是否藏有野心或把柄",
        "stage": "developing",
        "progress": 35,
        "risk": 20,
        "clues": [],
        "known_by_player": False,
        "created_turn": 3,
        "last_advanced_turn": 4,
    })

    clues = expose_scheme_clues(
        {"action_type": "observe", "player_intent": "觀察殿內眾人的口風"},
        _game_state(intrigue=82),
        relations,
        _gamedata(),
    )

    assert clues
