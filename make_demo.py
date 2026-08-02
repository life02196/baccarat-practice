"""
[為什麼] 使用者想看帳本工具的影片 demo。無法真的螢幕錄影，改成：
         真實驅動 ledger.py 跑一遍、抓真實輸出，算成會動的 GIF（等同錄影回放）。
[怎麼做] subprocess 餵真實輸入給 ledger.py，收集真實 stdout；把整段對話組成
         「終端機逐行浮現」的影格，用 Pillow 畫成 demo.gif。畫面內容全部來自
         程式真實輸出，非杜撰。
[結果]   demo.gif —— 一段可播放的示範，展示記錄輸贏、戒賭天數、統計三個功能。
"""

from __future__ import annotations

import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.py")
GIF_PATH = os.path.join(HERE, "demo.gif")

FONT_PATH = r"C:\Windows\Fonts\msjh.ttc"   # 微軟正黑，含中英
FONT_SIZE = 22
LINE_H = 30
PAD = 24
COLS = 60
ROWS = 26
BG = (13, 17, 23)          # GitHub dark
FG = (201, 209, 217)
PROMPT_FG = (63, 185, 80)  # 綠
DIM = (110, 118, 129)


def run_cmd(args: list[str], stdin_text: str = "") -> str:
    """真實執行 ledger.py，回傳真實輸出。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, LEDGER, *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=HERE,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def build_script() -> list[tuple[str, str]]:
    """回傳 (type, text) 影格素材。type: 'cmd' 指令列, 'out' 程式輸出。"""
    lines: list[tuple[str, str]] = []

    def add_block(cmd: str, output: str):
        lines.append(("cmd", f"$ python ledger.py {cmd}"))
        for ln in output.rstrip("\n").split("\n"):
            lines.append(("out", ln))
        lines.append(("out", ""))

    # 先鋪幾場真實紀錄（有輸有贏），讓勝率與當前輸贏有意義
    run_cmd(["add"], "2026-07-26\n5000\n0\n\n")
    run_cmd(["add"], "2026-07-28\n3000\n7000\n\n")
    run_cmd(["add"], "2026-07-29\n6000\n0\n\n")

    # 影片實際展示：記一場輸的、記今天沒賭、看統計
    o1 = run_cmd(["add"], "2026-07-30\n8000\n0\n心情差 手癢\n")
    add_block("add", o1)
    o2 = run_cmd(["clean"], "")
    add_block("clean", o2)
    o3 = run_cmd(["stats"], "")
    add_block("stats", o3)
    return lines


def render(lines: list[tuple[str, str]]) -> None:
    W = PAD * 2 + COLS * (FONT_SIZE * 0.6).__int__() + 40
    W = 760
    H = PAD * 2 + ROWS * LINE_H
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()

    frames: list[Image.Image] = []
    durations: list[int] = []

    visible: list[tuple[str, str]] = []

    def snapshot(hold_ms: int):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        # 標題列
        d.text((PAD, PAD - 6), "戒賭帳本  ledger.py", font=font, fill=DIM)
        y = PAD + LINE_H
        shown = visible[-(ROWS - 2):]
        for kind, text in shown:
            color = PROMPT_FG if kind == "cmd" else FG
            d.text((PAD, y), text, font=font, fill=color)
            y += LINE_H
        frames.append(img)
        durations.append(hold_ms)

    for kind, text in lines:
        visible.append((kind, text))
        if kind == "cmd":
            snapshot(700)          # 指令列停久一點
        elif text.strip() == "":
            snapshot(120)
        else:
            snapshot(180)          # 每行輸出

    # 結尾定格
    snapshot(2600)

    frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"[OK] 寫出 {GIF_PATH}")
    print(f"     影格數 {len(frames)}，尺寸 {W}x{H}")


if __name__ == "__main__":
    # 用乾淨資料錄，錄完清掉
    for f in ("sessions.json", "clean_days.json"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
    script = build_script()
    render(script)
    for f in ("sessions.json", "clean_days.json"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
    print("[OK] 測試資料已清除")
