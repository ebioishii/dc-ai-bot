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

# Project rules for Codex

This is a Discord AI palace-intrigue text game.

## Absolute safety rules
- Never modify .env.
- Never commit .env, tokens, API keys, or secrets.
- Never run git push, git reset --hard, git rebase, or force push unless explicitly requested.
- Preserve existing player JSON data. Add fields only with backward-compatible defaults.

## Architecture
The bot uses a two-AI architecture:

1. Judge AI
- Parses player intent.
- Detects assumptions, social tone, risk, and possible misread.
- Does not write player-facing prose.

2. Rule Engine
- Final authority for game state.
- Resolves summons, inventory, dead NPCs, rank restrictions, world events, objectives, and hidden state deltas.

3. Story Writer AI
- Writes narration only from authoritative_result.
- Must not invent major world events.
- Must not expose hidden_state numbers.
- Must output reply + 2–4 strategic choices.

## Game design requirements
Every turn should provide at least one of:
- new_info
- relation_shift
- risk_change
- objective_update
- event_trigger

Choices must have:
- style
- risk
- reward
- effect_hint
- mechanical_effect

Choices must not be mere paraphrases. They must represent distinct strategies.

NPCs may take active actions:
- test
- pressure
- redirect
- withhold_info
- soft_attack

Story Writer must not write the player's unspoken thoughts or feelings.
Avoid phrases like:
- 你感覺
- 你知道
- 你試圖
unless directly grounded in player input or explicit game_state.

## Validation
Before finishing, run:
python -m py_compile main.py

If modules exist:
python -m compileall game services

Report changed files and test results.