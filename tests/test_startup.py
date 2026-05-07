import json
from pathlib import Path

from game.startup import (
    FORBIDDEN_BACKGROUND_TERMS,
    RANDOM_FAMILY_VALUE,
    build_background_prompt,
    build_fallback_background_description,
    build_opening_story_result,
    build_starting_objectives,
    build_starting_relations,
    generate_random_appearance,
    resolve_start_family,
    resolve_start_location,
    sanitize_background_description,
)
from game.npc import get_present_scene_npcs


ROOT = Path(__file__).resolve().parents[1]


def _load_json(name):
    return json.loads((ROOT / "gamedata" / name).read_text(encoding="utf-8"))


def test_random_family_returns_available_family():
    families = _load_json("families.json")["families"]
    family_ids = {family["id"] for family in families}

    for _ in range(20):
        family = resolve_start_family(families, RANDOM_FAMILY_VALUE)
        assert family["id"] in family_ids


def test_family_start_locations_exist():
    families = _load_json("families.json")["families"]
    locations = _load_json("locations.json")["locations"]
    location_ids = {location["id"] for location in locations}

    for family in families:
        start_location = family.get("start_location", {})
        assert start_location.get("location_id") in location_ids
        resolved = resolve_start_location(family, locations)
        assert resolved["id"] == start_location["location_id"]
        assert resolved["name"]
        assert resolved["room"]


def test_locations_have_gameplay_metadata_and_npc_links_are_valid():
    locations = _load_json("locations.json")["locations"]
    npcs = _load_json("npcs.json")["npcs"]
    families = _load_json("families.json")["families"]
    location_ids = {location["id"] for location in locations}

    for location in locations:
        assert location.get("description")
        assert location.get("scene_role")
        assert isinstance(location.get("default_objectives"), list)
        assert isinstance(location.get("event_hooks"), list)
        assert isinstance(location.get("choice_bias"), list)

    assert all(npc.get("location") in location_ids for npc in npcs)
    assert all((family.get("start_location") or {}).get("location_id") in location_ids for family in families)
    for family in families:
        start_id = (family.get("start_location") or {}).get("location_id")
        contacts = family.get("opening_contacts", {})
        local_npcs = [npc for npc in npcs if npc.get("location") == start_id]
        assert local_npcs or contacts.get("host_npc") or contacts.get("peer_npcs")


def test_starting_objectives_follow_location_and_contacts():
    families = _load_json("families.json")["families"]
    locations = _load_json("locations.json")["locations"]
    npcs = _load_json("npcs.json")["npcs"]

    for family in families:
        location = resolve_start_location(family, locations)
        contacts = family.get("opening_contacts", {})
        objectives = build_starting_objectives(location, contacts, npcs)
        objective_text = "\n".join(item["text"] for item in objectives)

        assert objectives
        assert location["name"] in objective_text
        assert "承乾宮" not in objective_text or location["id"] == "cheng_qian_gong"
        assert "陸常在" not in objective_text or contacts.get("host_npc") == "陸常在" or "陸常在" in contacts.get("peer_npcs", [])


def test_starting_relations_only_include_start_scene_and_contacts():
    families = _load_json("families.json")["families"]
    locations = _load_json("locations.json")["locations"]
    npcs = _load_json("npcs.json")["npcs"]

    for family in families:
        location = resolve_start_location(family, locations)
        contacts = family.get("opening_contacts", {})
        relations = build_starting_relations(location, contacts, npcs)
        relation_names = set(relations["npcs"])
        allowed = {
            npc["name"] for npc in npcs
            if npc.get("location") == location["id"]
        }
        allowed.add(contacts.get("host_npc"))
        allowed.update(contacts.get("peer_npcs", []))
        allowed.discard(None)

        assert relations["schemes"] == []
        assert relation_names
        assert relation_names <= allowed
        assert set(relations["hidden_state"]) == relation_names


def test_starting_host_is_not_physically_present_by_default():
    families = _load_json("families.json")["families"]
    rich = next(family for family in families if family["id"] == "rich")
    contacts = rich["opening_contacts"]
    host = contacts["host_npc"]
    peer = contacts["peer_npcs"][0]
    status = {
        "location": rich["start_location"]["location_id"],
        "location_id": rich["start_location"]["location_id"],
        "turn_count": 1,
        "scene_state": {"present_npcs": [host, peer]},
    }
    profile = {"family": "rich"}

    present = get_present_scene_npcs(status["location"], profile=profile, status=status, player_input="先觀察偏殿")

    assert host not in present


def test_starting_scene_only_has_peer_present_by_default():
    families = _load_json("families.json")["families"]
    rich = next(family for family in families if family["id"] == "rich")
    status = {"location": rich["start_location"]["location_id"], "turn_count": 0}
    profile = {"family": rich["id"]}

    present = get_present_scene_npcs(rich["start_location"]["location_id"], profile=profile, status=status)

    assert "陸常在" in present
    assert "李貴妃" not in present


def test_random_appearance_is_non_empty_and_modal_safe():
    families = _load_json("families.json")["families"]

    for family in families:
        for gender in ("女", "男"):
            appearance = generate_random_appearance(gender, family)
            assert appearance.strip()
            assert len(appearance) <= 50


def test_opening_story_has_valid_choices_and_no_major_event_terms():
    families = _load_json("families.json")["families"]
    locations = _load_json("locations.json")["locations"]
    forbidden = ("皇上駕到", "忽然傳召", "突然傳召", "拾到")

    for family in families:
        location = resolve_start_location(family, locations)
        for gender in ("女", "男"):
            profile = {
                "name": "測試",
                "gender": gender,
                "rank": family["rank"],
            }
            story = build_opening_story_result(
                profile,
                family,
                location,
                family.get("opening_contacts", {}),
            )
            choices = story.get("choices")
            assert isinstance(choices, list)
            assert 2 <= len(choices) <= 4
            risks = {choice.get("risk") for choice in choices}
            styles = {choice.get("style") for choice in choices}
            assert "low" in risks
            assert {"medium", "high"} & risks
            assert len(styles) >= 2
            for choice in choices:
                assert choice.get("id")
                assert choice.get("text")
                assert choice.get("effect_hint")
                assert isinstance(choice.get("mechanical_effect"), dict)
            assert not any(term in story["reply"] for term in forbidden)


def test_background_prompt_and_sanitizer_do_not_create_starting_event_contradictions():
    families = _load_json("families.json")["families"]
    locations = _load_json("locations.json")["locations"]
    poor = next(family for family in families if family["id"] == "poor")
    location = resolve_start_location(poor, locations)
    profile = {
        "name": "測試宮女",
        "gender": "女",
        "rank": poor["rank"],
        "appearance": "眉眼清亮，衣衫素淨",
    }

    system, user = build_background_prompt(profile, poor, location)
    prompt_text = system + "\n" + user
    assert "不得寫皇帝已經注意" in prompt_text
    assert "目前位階：宮女" in prompt_text
    assert "起始位置：景仁宮值房" in prompt_text

    unsafe = "測試宮女生於罪臣之家，因緣際會下被皇帝看中，從此命運轉動，走向宮廷深處。"
    sanitized = sanitize_background_description(unsafe, profile, poor, location)

    assert "宮女身份" in sanitized
    assert "景仁宮值房" in sanitized
    assert not any(term in sanitized for term in FORBIDDEN_BACKGROUND_TERMS)
    assert "皇帝" not in poor["description"]


def test_fallback_background_respects_rank_and_location():
    family = {"name": "罪臣之家", "description": "家族因罪沒落", "rank": "宮女"}
    profile = {"name": "林常在", "rank": "宮女", "appearance": "舉止謹慎"}
    location = {"name": "景仁宮", "room": "值房"}

    text = build_fallback_background_description(profile, family, location)

    assert "宮女身份" in text
    assert "景仁宮值房" in text
    assert "常在之身" not in text
    assert "皇帝" not in text
