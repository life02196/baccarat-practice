@echo off
REM 改完程式後，雙擊這個檔就會重新打包「百家樂練習程式」。
REM 用獨立的 .buildenv 環境，不影響 anaconda base。
cd /d "%~dp0"

if not exist ".buildenv\Scripts\python.exe" (
  echo [建立打包環境中...]
  python -m venv .buildenv
  ".buildenv\Scripts\python.exe" -m pip install --disable-pip-version-check pyinstaller -r requirements.txt
)

REM requirements 更新後也同步安裝，確保螢幕牌面辨識套件會被打包。
".buildenv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt

echo [打包 百家樂練習程式...]
".buildenv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name 百家樂練習程式 --distpath dist --workpath build --specpath packaging\specs --hidden-import screen_card_monitor --hidden-import card_recognizer --hidden-import scoreboard_recognizer baccarat_shadow.py

echo.
echo [完成] EXE 在 dist\ 資料夾：
echo    dist\百家樂練習程式.exe
pause
