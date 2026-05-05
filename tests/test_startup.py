import json
from pathlib import Path

from game.startup import (
    RANDOM_FAMILY_VALUE,
    build_opening_story_result,
    generate_random_appearance,
    resolve_start_family,
    resolve_start_location,
)


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
