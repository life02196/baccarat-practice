@echo off
REM 改完程式後，雙擊這個檔就會重新打包出新的 exe（兩支都打包）。
REM 用獨立的 .buildenv 環境，不影響 anaconda base。
cd /d "%~dp0"

if not exist ".buildenv\Scripts\python.exe" (
  echo [建立打包環境中...]
  python -m venv .buildenv
  ".buildenv\Scripts\python.exe" -m pip install --disable-pip-version-check pyinstaller
)

echo [打包 假錢百家樂（自己發牌）...]
".buildenv\Scripts\python.exe" -m PyInstaller --onefile --windowed --name BaccaratSim --distpath dist --workpath build --specpath . baccarat_game.py

echo [打包 假錢百家樂（跟真實牌桌）...]
".buildenv\Scripts\python.exe" -m PyInstaller --onefile --windowed --name BaccaratShadow --distpath dist --workpath build --specpath . baccarat_shadow.py

echo.
echo [完成] exe 都在 dist\ 資料夾：
echo    dist\BaccaratSim.exe     （程式自己發牌，練習用）
echo    dist\BaccaratShadow.exe  （你看真實牌桌，跟著下假錢）
pause
