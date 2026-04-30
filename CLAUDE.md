# 紫禁城後宮 Discord Bot — 專案說明

## 專案概述
這是一個運行在 Discord 的清宮權謀 RPG Bot，使用 Gemini API 作為 GM（說書人）引擎。
玩家在頻道中輸入行動文字，Bot 推演劇情並回覆古風小說段落。

## 技術棧
- Python 3.11+
- discord.py（slash commands + on_message）
- google-generativeai（Gemini API）
- 資料格式：JSON（無資料庫）

## 目錄結構
```
project/
├── main.py              # 主程式（Bot 邏輯、指令、訊息處理）
├── CLAUDE.md            # 本檔案
├── gamedata/            # 唯讀遊戲設定
│   ├── families.json    # 家世背景與起始加成
│   ├── ranks.json       # 位階體系
│   ├── npcs.json        # NPC 資料（含隱藏動機、情緒）
│   ├── locations.json   # 地點定義
│   ├── rules.json       # 宮廷規矩與禁忌
│   ├── punishments.json # 懲處規制
│   ├── rewards.json     # 恩賞規制
│   └── scripts.json     # System prompt 與 prompt 模板
└── players/             # 執行時自動產生，每位玩家一個子資料夾
    └── {user_id}/
        ├── profile.json    # 基本資料（名諱、家世、位階）
        ├── status.json     # 動態狀態（位置、屬性值、存活）
        ├── memory.json     # 記憶系統（short_term、long_term、fact_sheet）
        ├── inventory.json  # 倉庫
        └── relations.json  # NPC 關係（好感度、情緒值）
```

---

## 核心架構決策（修改前請確認）

### Prompt 組裝優先級
所有 GM 生成都遵循以下順序，**不得打亂**：
1. **System Instruction**（`make_gm_system_instruction()`）— 包含遊戲規則 + 強制約束
2. **Action Prompt 主體**（來自 `scripts.json` 的模板填入）
3. **尾端覆蓋區塊**（殺戮指令 / 事實清單 / 情緒突發）— 必須附加在最後

覆蓋區塊放在尾端是刻意設計，讓模型給予最高注意力，不可移動到前面。

### 記憶系統（memory.json 欄位說明）
| 欄位 | 類型 | 上限 | 說明 |
|---|---|---|---|
| `short_term` | list | 10 筆 | 完整對話紀錄，注入時只取最後 3 筆 |
| `long_term_summary` | string | 15 條目 | 以 ` \| ` 分隔，由 `manage_memory()` 自動壓縮 |
| `fact_sheet` | string | — | `fact_sheet_items` join 後的可讀版本 |
| `fact_sheet_items` | list | 10 條 | `/ooc` 修正後的確認事實，只能 append，不可截斷 |

**注意**：`short_term` 注入上限為 3 筆（`build_history_summary` 中的 `[-3:]`），這是為了避免復讀機效應與 Token 超量，不可調高。

### NPC 情緒系統（relations.json 欄位說明）
情緒值存在 `relations.json` 的每個 NPC 條目下：
```json
{
  "npcs": {
    "皇后": {
      "好感度": 10,
      "恩怨": "初次見面",
      "emotion_state": {
        "anger": 0,
        "fear": 0
      }
    }
  }
}
```
- 侮辱行為（`is_insult`）：anger +25
- 暴力行為（`is_violence`）：anger +40、fear +20
- 超過閾值（`ANGER_THRESHOLD = 70` / `FEAR_THRESHOLD = 70`）時，`build_emotion_override()` 產生強制覆蓋文字注入 prompt 尾端，強迫模型切換至「突發狀況分支」

---

## 函式索引

### 資料讀寫
| 函式 | 說明 |
|---|---|
| `load_player_data(user_id, data_type)` | 通用讀取玩家 JSON |
| `save_player_data(user_id, data_type, data)` | 通用寫入玩家 JSON |
| `load_player_profile/status/memory/inventory/relations` | 各類型快捷讀取 |

### Prompt 組裝
| 函式 | 說明 |
|---|---|
| `make_gm_system_instruction(game_rules)` | 產生 GM system prompt，包含強制規則附加 |
| `format_game_rules()` | 將 JSON 規則格式化為可注入的文字 |
| `format_npc_data()` | 格式化所有 NPC 資料 |
| `get_scene_npcs(location)` | 取得當前場景的 NPC 名單 |
| `build_history_summary(short_term)` | 只取最後 3 筆，每筆 GM 回應截取前 200 字 |
| `format_player_relations(relations)` | 格式化 NPC 關係，含情緒值輸出 |

### 指令解析與情緒系統
| 函式 | 說明 |
|---|---|
| `classify_player_input(text)` | 回傳 `(input_type, cleaned_text)`，類型為 `KILL_CMD` 或 `NARRATIVE` |
| `detect_extreme_action(text)` | 偵測侮辱 / 暴力關鍵字，回傳 `{is_insult, is_violence}` |
| `update_npc_emotions(user_id, npc_list, flags)` | 更新情緒值，回傳更新後的 relations 與觸發閾值的 NPC 清單 |
| `build_emotion_override(triggered_npcs)` | 產生情緒突發的強制覆蓋文字 |

### 事實清單
| 函式 | 說明 |
|---|---|
| `load_fact_sheet(user_id)` | 讀取 `memory.json` 中的 `fact_sheet` 字串 |
| `update_fact_sheet(user_id, correction, result_summary)` | 將 OOC 修正寫入 `fact_sheet_items`，最多保留 10 條 |

### 記憶管理
| 函式 | 說明 |
|---|---|
| `manage_memory(user_id)` | 當 short_term >= 11 筆時，壓縮最舊 2 筆為 long_term 條目 |
| `extract_key_info(dialogue_pair)` | 將一筆對話壓縮為長期記憶條目（固定模板，非 AI） |

---

## Discord 指令對照
| Discord 指令 | 處理函式 | 說明 |
|---|---|---|
| `/start` | `StartModal.on_submit()` | 建立角色、初始化所有 JSON 檔案 |
| `/ooc <修正內容>` | `ooc()` | 修正劇情錯誤、自動更新 fact_sheet |
| `/op <指令>` | `op_cmd()` | GM 強制指令，可無視遊戲規則 |
| `/profile` | `profile()` | 查看角色屬性與倉庫 |
| `/help` | `help_cmd()` | 查看操作指南 |
| 一般訊息 | `on_message()` | 主要遊戲循環 |

---

## 新增功能時的 Checklist

在實作任何新功能前，請逐項確認：

- [ ] 是否影響 prompt 尾端覆蓋區塊的附加順序？
- [ ] 是否需要在 `memory.json` 新增欄位？若是，同步更新 `StartModal.on_submit()` 的初始化區塊。
- [ ] 是否需要在 `relations.json` 新增欄位？若是，同步更新 `update_npc_emotions()` 中的初始化邏輯。
- [ ] 新的 NPC 屬性是否需要在 `format_npc_data()` 或 `format_player_relations()` 中輸出？
- [ ] 新指令是否需要讀取 `fact_sheet`？若是，參考 `ooc()` 的注入方式。
- [ ] 是否改動 `short_term` 的注入筆數上限？（預設 3，不可調高）

---

## 不可更動的設計原則

這些設計有明確原因，修改前必須與開發者確認：

1. **`short_term` 注入上限為 3 筆**：防止復讀機效應與 Token 超量
2. **覆蓋區塊必須附加在 action_prompt 的尾端**：確保模型優先處理強制指令
3. **`fact_sheet_items` 只能 append，不能整體覆蓋**：防止 `/ooc` 修正後舊事實消失導致劇情循環
4. **所有 prompt 長文字模板存在 `scripts.json`**：不在 `main.py` 中硬編碼

---

## 環境變數
```
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
```

---

## 已知限制與待解問題

- [ ] `/op` 指令目前只生成劇情文字，**不會自動回寫 `status.json`**（位階、位置、存活等狀態需手動更新）
- [ ] NPC 情緒值目前跨場景不重置也不衰減，長期遊玩後數值會永久累積
- [ ] `manage_memory()` 的長期記憶壓縮使用固定模板而非 AI 摘要，細節遺失率較高
- [ ] 多人同頻道遊玩時，`on_message` 沒有頻道或角色隔離，不同玩家的訊息會互相觸發
- [ ] `classify_player_input()` 的關鍵字列表為硬編碼，需定期補充新詞彙
- [ ] 情緒系統的觸發關鍵字（`INSULT_KEYWORDS`）目前為簡體 / 繁體混用，需統一
