# 給接手／貢獻者

歡迎接手。這份說明讓你 10 分鐘內能跑起來、改東西、驗證沒改壞。

## 環境

- Python 3.9+
- 大部分功能只用標準庫。額外套件見 `requirements.txt`：

```bash
pip install -r requirements.txt
```

## 跑起來

```bash
python baccarat_sim.py       # 跑蒙地卡羅，驗證賠率引擎（莊家優勢約 -1.06%）
python baccarat_game.py      # 假錢百家樂（自己發牌）
python baccarat_shadow.py    # 假錢跟牌桌版（多注、全玩法）
python ledger.py             # 記帳 + 戒賭天數
```

## 測試（改完務必跑）

不需要 pytest，直接執行即可：

```bash
python test_rules.py         # 26 種玩法賠率、多注結算
python test_sim.py           # 發牌規則、賠率收斂
```

兩支都印 `[PASS]` 且結尾 `0 failure(s)` 才算通過。

## 程式架構（怎麼分工）

| 層 | 檔案 | 責任 |
|----|------|------|
| 引擎（純邏輯，無 UI） | `baccarat_sim.py` | 發牌、標準補牌規則、基本賠率 |
| 引擎 | `baccarat_rules.py` | 一手結果 → 26 種玩法各自輸贏 |
| 介面（tkinter） | `baccarat_game.py` | 自己發牌的假錢遊戲 |
| 介面 | `baccarat_shadow.py` | 手動輸入牌桌結果的假錢版 |
| 工具 | `ledger.py` / `live_tracker.py` | 記帳、戒賭天數 |
| 展示 | `demo.html` / `baccarat_demo.html` / `make_demo.py` | 功能介紹 |

**改賠率或規則 → 改 `baccarat_rules.py` / `baccarat_sim.py`，然後跑測試。**
UI 只呼叫引擎，不自己算賠率——請維持這個分層。

## 打包 .exe

雙擊 `打包exe.bat`（用獨立 `.buildenv`，不動系統 Python）。產物在 `dist/`。

## 專案界線（重要）

這是**教育／戒賭**用的假錢工具。請維持：

- 不加真錢下注、不連線任何賭場
- 不加螢幕擷取／自動讀牌／自動下注
- 保留「用真實賠率呈現久賭必輸」的初衷

## 送 PR 前

- 跑過 `test_rules.py`、`test_sim.py`
- 新功能附上對應測試
- commit 訊息講清楚改了什麼與為什麼
