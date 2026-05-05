from __future__ import annotations
import re

from game.state import load_player_memory, save_player_data

def load_fact_sheet(user_id) -> str:
    memory = load_player_memory(user_id)
    if not memory:
        return ""
    return memory.get('fact_sheet', '')


def update_fact_sheet(user_id, correction: str, result_summary: str):
    """
    將 OOC 修正後的事實加入 fact_sheet。
    fact_sheet 以條目形式儲存，最多保留 10 條。
    """
    memory = load_player_memory(user_id)
    if not memory:
        return
    existing = memory.get('fact_sheet_items', [])
    new_entry = f"[修正] {correction[:60]} → [確認事實] {result_summary[:80]}"
    existing.append(new_entry)
    # 只保留最近 10 條修正事實
    memory['fact_sheet_items'] = existing[-10:]
    memory['fact_sheet'] = "\n".join(memory['fact_sheet_items'])
    save_player_data(user_id, 'memory', memory)


def build_history_summary(short_term: list) -> str:
    """
    ── 修正3：精簡上下文 ──
    只保留最近 3 輪對話，GM 回應截取前 200 字，避免復讀機效應。
    """
    if not short_term:
        return "無（初次入宮）"
    # 只取最後 3 輪
    recent = short_term[-3:]
    lines = []
    for h in recent:
        bot_preview = h['bot'][:200].rstrip()
        if len(h['bot']) > 200:
            bot_preview += "……"
        lines.append(f"玩家：{h['user']}\nGM：{bot_preview}")
    return "\n\n".join(lines)


def build_gemini_history(short_term: list) -> list:
    """將 short_term 轉換為 Gemini Chat API 所需的 history 格式。"""
    history = []
    for h in short_term:
        history.append({"role": "user", "parts": [h["user"]]})
        history.append({"role": "model", "parts": [h["bot"]]})
    return history


def extract_key_info(dialogue_pair: dict) -> str:
    user_msg = dialogue_pair.get('user', '')
    user_msg = re.sub(r'^\[.*?\]\s*|^【.*?】\s*', '', user_msg)[:80].strip()
    bot_msg = dialogue_pair.get('bot', '')[:180].strip()
    return f"[玩家：{user_msg}] → [場景：{bot_msg}]"


def manage_memory(user_id):
    """
    滾動式記憶管理：
    當短期記憶 >= 10 筆時，壓縮最舊的 2 筆為長期記憶條目。
    長期記憶以帶編號列表儲存（最多 15 條）。
    """
    memory = load_player_memory(user_id)
    if not memory:
        return

    short_term = memory.get('short_term', [])
    long_term = memory.get('long_term_summary', '')

    if len(short_term) < 10:
        return

    old_dialogues = short_term[:2]
    memory['short_term'] = short_term[2:]

    new_items = [extract_key_info(d) for d in old_dialogues]

    # 相容舊版 pipe-separated 格式與新版帶編號格式
    if ' | ' in long_term and not long_term.strip().startswith('1.'):
        existing_items = [i.strip() for i in long_term.split(' | ') if i.strip()]
    else:
        existing_items = [
            re.sub(r'^\d+\.\s*', '', line).strip()
            for line in long_term.splitlines()
            if line.strip()
        ]
    existing_items.extend(new_items)

    if len(existing_items) > 15:
        existing_items = existing_items[-15:]

    memory['long_term_summary'] = "\n".join(
        f"{i + 1}. {item}" for i, item in enumerate(existing_items)
    )
    save_player_data(user_id, 'memory', memory)
    print(f"✅ 記憶滾動：已壓縮 2 筆舊對話至長期記憶")


def update_memory(user_id, player_input, reply):
    memory = load_player_memory(user_id) or {
        "long_term_summary": "",
        "short_term": [],
        "fact_sheet": "",
        "fact_sheet_items": []
    }
    short_term = memory.get("short_term", [])
    short_term.append({"user": player_input, "bot": reply})
    memory["short_term"] = short_term
    save_player_data(user_id, "memory", memory)
    manage_memory(user_id)
    memory = load_player_memory(user_id)
    if memory and len(memory.get("short_term", [])) > 10:
        memory["short_term"] = memory["short_term"][-10:]
        save_player_data(user_id, "memory", memory)


