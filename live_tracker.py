"""
[為什麼] 使用者在真人百家樂網站（MT/RG 等）自己看牌路、自己下注，
         想用一個獨立的小工具即時記錄每一手的輸贏——不靠娛樂城的介面。
         這是純手動記帳：使用者自己按贏/輸，程式不讀賭場畫面、不預測牌路、不給下注建議。
[怎麼做] tkinter 做一個「釘在最上層」的浮動小視窗，浮在賭場網頁旁邊。
         三顆大按鈕（我贏/我輸/和局）+ 金額框，即時算勝率、當前輸贏、手數、連輸。
         每一手存進 hands.json，可撤銷上一手。鍵盤快速鍵 W/L/T/U。
[結果]   一個即時、誠實的輸贏記錄器。數字擺在眼前，讓人清醒。
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import font as tkfont

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "hands.json")

# 顏色（深色主題，浮在賭場畫面上不刺眼）
BG = "#0d1117"
PANEL = "#161b22"
FG = "#d7dee6"
DIM = "#7c8896"
WIN = "#3fb950"
LOSE = "#ff5c6c"
TIE = "#8b949e"
NET_POS = "#3fb950"
NET_NEG = "#ff5c6c"


def load_hands() -> list[dict]:
    if not os.path.isfile(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_hands(hands: list[dict]) -> None:
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as fh:
            json.dump(hands, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


class Tracker:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.hands = load_hands()

        root.title("百家樂 即時記帳")
        root.configure(bg=BG)
        root.attributes("-topmost", True)   # 釘在最上層
        root.geometry("300x430+40+40")
        root.minsize(280, 400)

        big = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        huge = tkfont.Font(family="Consolas", size=30, weight="bold")
        mid = tkfont.Font(family="Segoe UI", size=11)
        small = tkfont.Font(family="Segoe UI", size=9)
        btn_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        # --- 當前輸贏（最大、最顯眼）---
        tk.Label(root, text="當前輸贏", bg=BG, fg=DIM, font=small).pack(pady=(12, 0))
        self.net_lbl = tk.Label(root, text="0", bg=BG, fg=FG, font=huge)
        self.net_lbl.pack()

        # --- 勝率 / 手數 / 連輸 ---
        stat = tk.Frame(root, bg=BG)
        stat.pack(pady=(4, 10))
        self.rate_lbl = self._stat_cell(stat, "勝率", 0)
        self.count_lbl = self._stat_cell(stat, "手數", 1)
        self.streak_lbl = self._stat_cell(stat, "連輸", 2)

        # --- 金額輸入 ---
        amt_row = tk.Frame(root, bg=BG)
        amt_row.pack(pady=(2, 8))
        tk.Label(amt_row, text="下注金額", bg=BG, fg=DIM, font=small).pack(side="left", padx=(0, 6))
        self.amt_var = tk.StringVar(value="1000")
        self.amt_entry = tk.Entry(
            amt_row, textvariable=self.amt_var, width=8, justify="center",
            font=big, bg=PANEL, fg=FG, insertbackground=FG, relief="flat"
        )
        self.amt_entry.pack(side="left", ipady=4)

        # --- 三顆大按鈕 ---
        self._button(root, "我贏  (W)", WIN, "#06210f", lambda: self.record("win"))
        self._button(root, "我輸  (L)", LOSE, "#2a0a0d", lambda: self.record("lose"))
        self._button(root, "和局  (T)", PANEL, TIE, lambda: self.record("tie"), thin=True)

        # --- 撤銷 ---
        undo = tk.Button(
            root, text="撤銷上一手  (U)", command=self.undo,
            bg=BG, fg=DIM, font=small, relief="flat",
            activebackground=BG, activeforeground=FG, cursor="hand2"
        )
        undo.pack(pady=(4, 2))

        # --- 溫和提醒 ---
        self.note = tk.Label(
            root, text="數字擺在眼前，讓自己清醒。", bg=BG, fg=DIM,
            font=small, wraplength=270
        )
        self.note.pack(side="bottom", pady=(0, 8))

        # 鍵盤快速鍵
        root.bind("<KeyPress-w>", lambda e: self.record("win"))
        root.bind("<KeyPress-W>", lambda e: self.record("win"))
        root.bind("<KeyPress-l>", lambda e: self.record("lose"))
        root.bind("<KeyPress-L>", lambda e: self.record("lose"))
        root.bind("<KeyPress-t>", lambda e: self.record("tie"))
        root.bind("<KeyPress-T>", lambda e: self.record("tie"))
        root.bind("<KeyPress-u>", lambda e: self.undo())
        root.bind("<KeyPress-U>", lambda e: self.undo())

        self.refresh()

    def _stat_cell(self, parent, label, col):
        f = tk.Frame(parent, bg=BG)
        f.grid(row=0, column=col, padx=12)
        val = tk.Label(f, text="-", bg=BG, fg=FG,
                       font=tkfont.Font(family="Consolas", size=15, weight="bold"))
        val.pack()
        tk.Label(f, text=label, bg=BG, fg=DIM,
                 font=tkfont.Font(family="Segoe UI", size=8)).pack()
        return val

    def _button(self, parent, text, bg, fg, cmd, thin=False):
        b = tk.Button(
            parent, text=text, command=cmd, bg=bg, fg=fg,
            font=tkfont.Font(family="Segoe UI", size=13, weight="bold"),
            relief="flat", cursor="hand2", activebackground=bg, activeforeground=fg,
        )
        b.pack(fill="x", padx=18, pady=(3 if thin else 4), ipady=(6 if thin else 12))
        return b

    def _amount(self) -> float:
        raw = self.amt_var.get().strip().replace(",", "").replace("，", "")
        try:
            v = float(raw)
            return v if v >= 0 else 0.0
        except ValueError:
            return 0.0

    def record(self, result: str):
        amt = self._amount()
        if result != "tie" and amt <= 0:
            self._flash_note("請先輸入下注金額", LOSE)
            return
        self.hands.append({"result": result, "amount": amt})
        save_hands(self.hands)
        self.refresh(last=result)

    def undo(self):
        if self.hands:
            self.hands.pop()
            save_hands(self.hands)
            self.refresh(flash="已撤銷上一手")
        else:
            self._flash_note("沒有可撤銷的紀錄", DIM)

    def refresh(self, last: str | None = None, flash: str | None = None):
        net = 0.0
        wins = loses = ties = 0
        streak = cur = 0
        for h in self.hands:
            r, a = h["result"], h.get("amount", 0)
            if r == "win":
                net += a; wins += 1; cur = 0
            elif r == "lose":
                net -= a; loses += 1; cur += 1; streak = max(streak, cur)
            else:
                ties += 1
        decided = wins + loses
        rate = (wins / decided * 100) if decided else 0.0

        self.net_lbl.config(
            text=f"{net:+,.0f}",
            fg=NET_POS if net >= 0 else NET_NEG,
        )
        self.rate_lbl.config(text=f"{rate:.0f}%")
        self.count_lbl.config(text=str(len(self.hands)))
        self.streak_lbl.config(text=str(cur))  # 目前連輸

        if flash:
            self._flash_note(flash, DIM)
        elif last == "win":
            self._flash_note("記下了。贏的時候最危險——見好就收。", WIN)
        elif last == "lose":
            self._flash_note("記下了。輸的錢不會自己回來。", LOSE)
        elif last == "tie":
            self._flash_note("和局，記下了。", TIE)

    def _flash_note(self, text: str, color: str):
        self.note.config(text=text, fg=color)
        self.root.after(2500, lambda: self.note.config(
            text="數字擺在眼前，讓自己清醒。", fg=DIM))


def main():
    root = tk.Tk()
    Tracker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
