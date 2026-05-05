from game.schemes import (
    advance_schemes,
    ensure_scheme_state,
    expose_scheme_clues,
    maybe_create_scheme,
    resolve_scheme_by_player_action,
)
from game.mechanics import evaluate_player_action_costs, update_social_graph_from_turn
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


def test_created_scheme_keeps_owner_target_and_goal_when_advanced():
    relations = _relations()
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
