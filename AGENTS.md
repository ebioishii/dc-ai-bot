# AGENTS.md

本專案是 Discord AI 文字遊戲 bot。

## 開發原則
- 不要改動 .env、token、API key。
- 不要刪除 players/ 內的玩家資料結構，除非有 migration。
- 劇情生成不得直接決定世界狀態。
- 程式是最終規則裁判，AI 只負責解析與敘事。
- 所有 Gemini 結構化任務都應要求 JSON 輸出。

## 測試重點
- 執行 python -m py_compile main.py
- 若新增測試，執行 pytest
- 手動檢查 summons、choices、dead NPC、inventory validation

## 重要架構
遊戲流程應為：
player input
-> intent parsing
-> rule resolution
-> story generation
-> validation
-> state update
-> memory update

## AI game architecture rules

This project uses a two-AI architecture:

1. Judge AI:
- Parses player intent.
- Detects assumptions and risks.
- Does not write prose for the player.

2. Story Writer AI:
- Writes narration only from authoritative_result.
- Must not decide major world state.
- Must not reveal hidden_state numbers.
- Must output reply + 2–4 strategic choices.

The Python rule engine is the final authority.
Never allow Story Writer output to directly override game state without validation.

Every player-facing turn must include choices with meaningful mechanical differences.