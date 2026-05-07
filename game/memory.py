from __future__ import annotations
import re

from game.context import compact_memory_window
from game.state import load_player_memory, normalize_memory_record, save_player_data

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
    save_player_data(user_id, 'memory', normalize_memory_record(memory))


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
    """相容舊呼叫：改用 scene_summary 壓縮，不再累積完整歷史原文。"""
    memory = load_player_memory(user_id)
    if not memory:
        return

    short_term = memory.get("short_term", [])
    if len(short_term) < 7:
        return

    memory, summarized = compact_memory_window(memory)
    save_player_data(user_id, "memory", normalize_memory_record(memory))
    if summarized:
        print("✅ 記憶滾動：已壓縮舊對話至 scene_summary")


def update_memory(user_id, player_input, reply, status=None, relations=None) -> dict:
    memory = normalize_memory_record(load_player_memory(user_id) or {
        "long_term_summary": "",
        "short_term": [],
        "fact_sheet": "",
        "fact_sheet_items": [],
        "scene_summary": "",
        "summary_turns_since_update": 0
    }, status)
    short_term = memory.get("short_term", [])
    short_term.append({"user": str(player_input or ""), "bot": clean_reply_for_memory(reply)})
    memory["short_term"] = short_term
    memory["summary_turns_since_update"] = int(memory.get("summary_turns_since_update", 0) or 0) + 1
    memory, summarized = compact_memory_window(memory, status=status, relations=relations)
    save_player_data(user_id, "memory", normalize_memory_record(memory, status))
    return {
        "summary_triggered": summarized,
        "recent_turns": len(memory.get("short_term", [])),
        "summary_used": bool(memory.get("scene_summary")),
    }


def clean_reply_for_memory(reply) -> str:
    """Store only durable narration, not Discord UI blocks or rule-engine labels."""
    text = str(reply or "").strip()
    if not text:
        return ""
    split_markers = (
        "\n\n【可選行動】",
        "\n【可選行動】",
        "\n\n【當前目標】",
        "\n【當前目標】",
        "\n\n??貉??",
        "\n??貉??",
    )
    for marker in split_markers:
        index = text.find(marker)
        if index >= 0:
            text = text[:index].strip()
    mechanical_prefixes = (
        "短期目標向前推進了一小步。",
        "短期目標向前推進了一小步。 ",
        "短期目標向前推進了一小步。",
        "你沒有立刻得到明白答案，但殿內的回話順序與侍從動線已經露出一點端倪，足夠支撐下一步判斷。",
        "話落之後，席間的態度有了細微變化。",
    )
    for prefix in mechanical_prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text


