from __future__ import annotations

import random


RANDOM_FAMILY_VALUE = "__random_family__"

_APPEARANCE_PARTS = {
    "features": ["眉眼清亮", "眼尾微揚", "膚色白淨", "鼻梁秀挺", "唇色淡雅"],
    "temperaments": ["氣度沉靜", "神色溫婉", "姿態端正", "舉止謹慎", "目光澄定"],
    "details": ["衣飾素淨", "髮間只簪一支銀釵", "袖口帶著淡淡熏香", "妝容克制", "步履輕緩"],
}


def resolve_start_family(families: list[dict], family_id: str) -> dict:
    """Return the chosen family, resolving the synthetic random option."""
    if not families:
        raise ValueError("families must not be empty")
    if family_id == RANDOM_FAMILY_VALUE:
        return random.choice(families)
    for family in families:
        if family.get("id") == family_id:
            return family
    raise ValueError(f"unknown family id: {family_id}")


def generate_random_appearance(gender: str, family: dict | None = None) -> str:
    feature = random.choice(_APPEARANCE_PARTS["features"])
    temperament = random.choice(_APPEARANCE_PARTS["temperaments"])
    detail = random.choice(_APPEARANCE_PARTS["details"])
    if gender == "男":
        return f"{feature}，身形清瘦，{temperament}，聲線刻意收斂"
    if (family or {}).get("id") == "poor":
        return f"{feature}，{temperament}，衣衫洗得發白"
    return f"{feature}，{temperament}，{detail}"


def resolve_start_location(family: dict, locations: list[dict]) -> dict:
    start_location = family.get("start_location") or {}
    location_id = start_location.get("location_id")
    for location in locations:
        if location.get("id") == location_id:
            return {
                "id": location["id"],
                "name": location.get("name", location["id"]),
                "room": start_location.get("room", ""),
                "description": location.get("description", ""),
            }
    raise ValueError(f"family {family.get('id')} has invalid start_location: {location_id}")


def build_starting_objectives(location: dict, contacts: dict | None = None, npcs: list[dict] | None = None) -> list[dict]:
    contacts = contacts or {}
    location_id = location.get("id", "")
    location_name = location.get("name") or location_id or "宮中"
    host = str(contacts.get("host_npc") or "").strip()
    peers = [str(name).strip() for name in contacts.get("peer_npcs", []) if str(name).strip()]
    local_npcs = [
        str(npc.get("name")).strip()
        for npc in (npcs or [])
        if isinstance(npc, dict) and npc.get("location") == location_id and str(npc.get("name", "")).strip()
    ]
    names = list(dict.fromkeys(([host] if host else []) + peers + local_npcs))

    objectives = [{
        "id": f"understand_{location_id or 'starting_palace'}",
        "text": f"了解{location_name}內誰掌握話語權",
        "status": "active",
        "progress": 0,
    }]
    if host:
        objectives.append({
            "id": f"judge_{_slug_for_id(host)}",
            "text": f"判斷{host}是願意庇護你，還是想利用你",
            "status": "active",
            "progress": 0,
        })
    if len(names) >= 2:
        others = "、".join(names[1:3])
        objectives.append({
            "id": f"observe_{location_id or 'local'}_factions",
            "text": f"觀察{others}的立場與彼此關係",
            "status": "active",
            "progress": 0,
        })
    return objectives[:3]


def build_starting_relations(location: dict, contacts: dict | None, npcs: list[dict] | None) -> dict:
    contacts = contacts or {}
    location_id = location.get("id", "")
    host = str(contacts.get("host_npc") or "").strip()
    peers = [str(name).strip() for name in contacts.get("peer_npcs", []) if str(name).strip()]
    local_names = [
        str(npc.get("name")).strip()
        for npc in (npcs or [])
        if isinstance(npc, dict) and npc.get("location") == location_id and str(npc.get("name", "")).strip()
    ]
    names = list(dict.fromkeys(([host] if host else []) + peers + local_names))
    npcs_by_name = {npc.get("name"): npc for npc in (npcs or []) if isinstance(npc, dict) and npc.get("name")}
    relations = {"npcs": {}, "companions": {}, "hidden_state": {}, "social_graph": {}, "schemes": []}
    for name in names:
        relations["npcs"][name] = {
            "好感度": 0,
            "狀態": "初識",
            "emotion_state": {"anger": 0, "fear": 0},
            "alive": True,
        }
        relations["hidden_state"][name] = _default_hidden_for_start(name, npcs_by_name.get(name), relations["npcs"][name])
    return relations


def _default_hidden_for_start(name: str, npc: dict | None, relation: dict | None) -> dict:
    from game.npc import default_hidden_state_for_npc
    return default_hidden_state_for_npc(name, npc, relation)


def _slug_for_id(text: str) -> str:
    result = []
    for char in str(text):
        if char.isascii() and char.isalnum():
            result.append(char.lower())
        elif "\u4e00" <= char <= "\u9fff":
            result.append(f"u{ord(char):x}")
    return "_".join(result)[:80] or "npc"


def format_location_display(status: dict | None) -> str:
    if not isinstance(status, dict):
        return "未知"
    base = status.get("location_name") or status.get("location") or "未知"
    room = status.get("room") or ""
    if room and room not in str(base):
        return f"{base}{room}"
    return str(base)


def build_opening_story_result(profile: dict, family: dict, location: dict, contacts: dict | None = None) -> dict:
    contacts = contacts or family.get("opening_contacts") or {}
    gender = profile.get("gender", "女")
    host = contacts.get("host_npc") or "主位娘娘"
    peers = [str(name) for name in contacts.get("peer_npcs", []) if str(name).strip()]
    peer_text = "、".join(peers) if peers else "同住的小主"
    gender_opening = (family.get("opening_by_gender") or {}).get(gender)
    if not gender_opening:
        gender_opening = (family.get("opening_by_gender") or {}).get("女", "")

    location_name = location.get("name", location.get("id", "宮中"))
    room = location.get("room") or "偏殿"
    name = profile.get("name", "你")
    rank = profile.get("rank", family.get("rank", "小主"))

    reply = (
        f"{gender_opening}\n\n"
        f"{name}被安置在{location_name}{room}。窗下香灰尚新，案上只擺著內務府按例送來的器物，"
        f"一切都像剛被仔細丈量過，不多一分，也不少一分。{peer_text}也在這一宮中安頓，"
        f"彼此位分相近，言行都還帶著初入宮門的試探。{host}身邊的宮人來交代例行請安時辰，"
        f"話說得平穩，只提醒{rank}初來乍到，先熟悉宮規與住處，不必急著出頭。"
    )

    if gender == "男":
        reply += "你身上的女裝沒有錯處，卻仍得時刻留意步幅、聲線與旁人的目光。"

    choices = [
        {
            "id": "choice_1",
            "text": f"先細看{location_name}{room}的陳設、門路與可用人手",
            "style": "observe",
            "risk": "low",
            "reward": "low",
            "effect_hint": "穩健掌握環境線索，降低初入宮門的誤判。",
            "mechanical_effect": {
                "target": "scene",
                "trust_delta": 0,
                "suspicion_delta": -1,
                "anger_delta": 0,
                "intel_gain": 1,
                "reputation_delta": 0,
                "objective_progress_delta": 3,
            },
        },
        {
            "id": "choice_2",
            "text": f"以客氣口吻與{peers[0] if peers else '近旁宮人'}寒暄，試探同住之人的脾性",
            "style": "flatter",
            "risk": "medium",
            "reward": "medium",
            "effect_hint": "可能建立初步交情，也會讓對方記住你的態度。",
            "mechanical_effect": {
                "target": peers[0] if peers else "nearby_servant",
                "trust_delta": 1,
                "suspicion_delta": 1,
                "anger_delta": 0,
                "intel_gain": 1,
                "reputation_delta": 0,
                "objective_progress_delta": 6,
            },
        },
        {
            "id": "choice_3",
            "text": f"委婉向來交代規矩的宮人打聽{host}平日最看重什麼",
            "style": "probe",
            "risk": "high",
            "reward": "high",
            "effect_hint": "若拿捏得當可獲得關鍵情報，失言則容易顯得急切。",
            "mechanical_effect": {
                "target": host,
                "trust_delta": 0,
                "suspicion_delta": 3,
                "anger_delta": 0,
                "intel_gain": 2,
                "reputation_delta": 0,
                "objective_progress_delta": 10,
            },
        },
    ]
    return {"reply": reply, "choices": choices, "state_update": {}}
