# 百家樂練習程式

免費、開源的 Windows 百家樂假錢練習工具。程式使用本機螢幕擷取辨識牌面與官方點數，並依照使用者建立的模擬注單自動結算；不會連線下注，也不會操作娛樂城網站。

[下載 Windows 完整版（ZIP）](https://github.com/life02196/baccarat-practice/releases/latest/download/BaccaratPractice-Windows.zip) ｜ [直接下載 EXE](https://github.com/life02196/baccarat-practice/releases/latest/download/BaccaratPractice-Windows.exe) ｜ [所有版本](https://github.com/life02196/baccarat-practice/releases)

## 主要功能

- 自動擷取目前螢幕，不需要相機或額外錄影設備。
- 多螢幕環境可從辨識視窗指定娛樂城視窗；視窗移動到其他螢幕後仍會持續跟隨擷取。
- 支援 MT、DreamGaming（DG）與 RG 牌桌切換及自動偵測。
- 以網站官方點數決定莊、閒、和結果，牌面用於確認對子、張數與補牌資訊。
- 使用多幀證據、牌位記憶及百家樂補牌規則，降低動畫與短暫漏牌造成的未結算。
- 支援莊、閒、和、莊對、閒對、大小、單雙、超級 6、老虎、龍寶、例牌、熊貓 8、龍 7、超級和等畫面上可選玩法。
- 假錢餘額、ALL IN、自訂籌碼、重複上一手、多注、近期輸贏與 Session 總流水。
- 下注後立即保留模擬本金，牌局結束後自動派彩並記錄結果。
- 所有辨識與資料保存都在使用者電腦本機完成。

> 「完美對」需要可靠的花色辨識，目前未開放自動下注選項。影像辨識仍可能受到網站改版、動畫、遮擋、瀏覽器縮放與顯示比例影響，重要結果請自行核對。

## 下載與安裝

1. 前往 [最新版本下載頁](https://github.com/life02196/baccarat-practice/releases/latest)。
2. 建議下載 `BaccaratPractice-Windows.zip`，完整解壓縮後再執行。
3. 雙擊 `百家樂練習程式.exe`。
4. 第一次啟動若 Windows SmartScreen 顯示提示，可先確認下載來源為本儲存庫，再選擇「其他資訊」→「仍要執行」。本程式目前沒有商業數位簽章。

需求：Windows 10／11 64 位元。使用已打包版本不需要安裝 Python。

## 使用方式

1. 先開啟支援的百家樂牌桌，讓牌面與官方點數保持可見。
2. 開啟本程式；辨識視窗會顯示目前找到的牌與點數框。
3. 使用多個螢幕時，可按辨識視窗上方的「擷取視窗」選擇娛樂城所在的瀏覽器視窗。
4. 若自動模式辨識錯網站，按主畫面的「娛樂城」按鈕切換 MT／DreamGaming／RG。
5. 選擇籌碼金額與模擬玩法，建立本手注單。
6. 收牌後程式會依官方點數與多幀牌面證據自動結算。

請勿在發牌途中切換牌桌、網站模式或瀏覽器縮放。牌桌若被其他視窗完全遮住，程式無法辨識。

## 隱私與本機資料

程式不包含上傳畫面、遠端分析或遙測功能。執行後可能在 EXE 所在資料夾建立：

- `shadow_data.json`：假錢帳本與程式設定。
- `screen_card_regions.json`：手動框選的辨識區域。
- `recognition_debug.log`：不含畫面的文字辨識診斷紀錄。

這些檔案已由 `.gitignore` 排除。分享程式時，請分享 Releases 的原始 ZIP，不要分享自己使用後的資料夾。

## 從原始碼執行

需要 Python 3.9 以上版本：

```powershell
python -m venv .buildenv
.\.buildenv\Scripts\python.exe -m pip install -r requirements.txt
.\.buildenv\Scripts\python.exe baccarat_shadow.py
```

重新打包 Windows EXE：

```powershell
.\打包exe.bat
```

## 測試

```powershell
python test_rules.py
python test_sim.py
python test_card_recognizer.py
```

目前包含結算規則、補牌流程、螢幕辨識、DG 多幀證據、對子與各邊注自動結算等回歸測試。

## 專案檔案

| 檔案 | 用途 |
| --- | --- |
| `baccarat_shadow.py` | 主程式、假錢帳本與介面 |
| `screen_card_monitor.py` | 螢幕擷取、多幀辨識與自動結算流程 |
| `card_recognizer.py` | OpenCV 牌面點數辨識 |
| `scoreboard_recognizer.py` | MT／DG／RG 官方點數辨識 |
| `baccarat_rules.py` | 各玩法派彩規則 |
| `test_card_recognizer.py` | 辨識與整合回歸測試 |
| `打包exe.bat` | Windows 一鍵打包腳本 |

## 使用聲明

本專案只提供假錢模擬、程式研究與個人紀錄，不提供真實下注、自動下注、獲利保證或賭博策略。使用者應遵守所在地法律、娛樂城服務條款及螢幕內容相關權利。本專案與 MT、DreamGaming、RG 或其他娛樂城品牌沒有合作、授權或從屬關係。

## 授權

本專案使用 [MIT License](LICENSE)，可免費使用、修改與散布，但軟體依現況提供，不附帶任何保證。
