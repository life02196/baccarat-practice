"""
[為什麼] 戒賭替代品：用假錢玩百家樂，保留選邊、發牌、輸贏的刺激，但不碰真錢。
         用真實賠率，讓餘額曲線長期往下，親眼看清「長期一定輸」。
[怎麼做] tkinter GUI，牌局邏輯 import 自 baccarat_sim（已用蒙地卡羅驗證賠率）。
         選 閒/和/莊 → 下注假錢 → 發牌 → 結算 → 更新餘額與往下的曲線。
[結果]   零金錢風險的賭博體驗 + 一條誠實的下降曲線。
"""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import font as tkfont

import baccarat_sim as eng

START_CHIPS = 10000

BG = "#0b1220"
PANEL = "#131c2b"
EDGE = "#25344a"
FG = "#e6edf5"
DIM = "#8091a5"
GOLD = "#e8c268"
PLAYER_C = "#4aa3ff"     # 閒 藍
BANKER_C = "#ff6b6b"     # 莊 紅
TIE_C = "#54c98a"        # 和 綠
CARD_BG = "#f4f1e8"
CARD_FG = "#1a1a1a"
CARD_RED = "#c0392b"
POS = "#3fb950"
NEG = "#ff5c6c"

SUITS = ["♠", "♥", "♦", "♣"]  # 黑桃紅心方塊梅花
RANKS = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(r: int) -> str:
    return RANKS.get(r, str(r))


class Game:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.rng = random.Random()
        self.balance = START_CHIPS
        self.hands = 0
        self.my_wins = 0
        self.net = 0
        self.history = [START_CHIPS]
        self.bet_side = "banker"

        root.title("假錢百家樂 — 練習/戒賭用，不下真錢")
        root.configure(bg=BG)
        root.geometry("560x760+60+30")
        root.minsize(520, 720)

        self.f_big = tkfont.Font(family="Consolas", size=34, weight="bold")
        self.f_h = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.f_mid = tkfont.Font(family="Segoe UI", size=11)
        self.f_small = tkfont.Font(family="Segoe UI", size=9)
        self.f_card = tkfont.Font(family="Consolas", size=22, weight="bold")
        self.f_total = tkfont.Font(family="Consolas", size=15, weight="bold")

        # 標題
        tk.Label(root, text="假錢百家樂", bg=BG, fg=GOLD, font=tkfont.Font(
            family="Segoe UI", size=16, weight="bold")).pack(pady=(12, 0))
        tk.Label(root, text="這裡的每一分錢都是假的。真錢你也贏不了——看下面那條線。",
                 bg=BG, fg=DIM, font=self.f_small).pack()

        # 假錢餘額
        tk.Label(root, text="假錢餘額", bg=BG, fg=DIM, font=self.f_small).pack(pady=(10, 0))
        self.bal_lbl = tk.Label(root, text=f"{self.balance:,}", bg=BG, fg=GOLD, font=self.f_big)
        self.bal_lbl.pack()

        # 牌桌
        table = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        table.pack(fill="x", padx=16, pady=10)
        self.player_area = self._hand_area(table, "閒 PLAYER", PLAYER_C, 0)
        self.banker_area = self._hand_area(table, "莊 BANKER", BANKER_C, 1)

        self.result_lbl = tk.Label(root, text="選一邊，下注，發牌", bg=BG, fg=FG, font=self.f_h)
        self.result_lbl.pack(pady=(2, 6))

        # 選邊
        side_row = tk.Frame(root, bg=BG)
        side_row.pack()
        self.side_btns = {}
        for key, text, color in (("player", "押 閒", PLAYER_C),
                                 ("tie", "押 和", TIE_C),
                                 ("banker", "押 莊", BANKER_C)):
            b = tk.Button(side_row, text=text, width=8, font=self.f_h,
                          command=lambda k=key: self.pick(k),
                          relief="flat", cursor="hand2",
                          bg=PANEL, fg=color, activebackground=color, activeforeground="#0b1220")
            b.pack(side="left", padx=6, ipady=8)
            self.side_btns[key] = b

        # 金額
        amt_row = tk.Frame(root, bg=BG)
        amt_row.pack(pady=(10, 4))
        tk.Label(amt_row, text="下注", bg=BG, fg=DIM, font=self.f_small).pack(side="left", padx=(0, 6))
        self.amt_var = tk.StringVar(value="500")
        tk.Entry(amt_row, textvariable=self.amt_var, width=8, justify="center",
                 font=self.f_h, bg=PANEL, fg=FG, insertbackground=FG, relief="flat").pack(side="left", ipady=3)
        for chip in (100, 500, 1000):
            tk.Button(amt_row, text=f"+{chip}", font=self.f_small, relief="flat", cursor="hand2",
                      bg=PANEL, fg=FG, activebackground=EDGE,
                      command=lambda c=chip: self.add_chip(c)).pack(side="left", padx=3, ipady=2)
        tk.Button(amt_row, text="清除", font=self.f_small, relief="flat", cursor="hand2",
                  bg=PANEL, fg=DIM, activebackground=EDGE,
                  command=lambda: self.amt_var.set("0")).pack(side="left", padx=3, ipady=2)

        # 發牌
        self.deal_btn = tk.Button(root, text="發  牌  (Enter)", font=tkfont.Font(
            family="Segoe UI", size=15, weight="bold"),
            bg=GOLD, fg="#231c05", relief="flat", cursor="hand2",
            activebackground="#f0d488", command=self.deal)
        self.deal_btn.pack(fill="x", padx=16, pady=(6, 8), ipady=10)

        # 餘額曲線
        tk.Label(root, text="假錢餘額走勢（看它往哪走）", bg=BG, fg=DIM, font=self.f_small).pack()
        self.canvas = tk.Canvas(root, height=110, bg=PANEL, highlightbackground=EDGE,
                                highlightthickness=1)
        self.canvas.pack(fill="x", padx=16, pady=(2, 8))

        # 統計
        stat = tk.Frame(root, bg=BG)
        stat.pack()
        self.hands_lbl = self._stat(stat, "手數", 0)
        self.rate_lbl = self._stat(stat, "你的勝率", 1)
        self.net_lbl = self._stat(stat, "淨輸贏(假)", 2)

        tk.Button(root, text="重新開始（回到 10,000）", font=self.f_small, relief="flat",
                  bg=BG, fg=DIM, activebackground=BG, activeforeground=FG, cursor="hand2",
                  command=self.reset).pack(pady=(8, 4))

        root.bind("<Return>", lambda e: self.deal())
        root.bind("<KeyPress-1>", lambda e: self.pick("player"))
        root.bind("<KeyPress-2>", lambda e: self.pick("tie"))
        root.bind("<KeyPress-3>", lambda e: self.pick("banker"))

        self.pick("banker")
        self.draw_curve()

    # ---------- UI 建構小工具 ----------
    def _hand_area(self, parent, title, color, col):
        f = tk.Frame(parent, bg=PANEL)
        f.grid(row=0, column=col, padx=18, pady=12, sticky="n")
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        tk.Label(f, text=title, bg=PANEL, fg=color, font=self.f_h).pack()
        cards = tk.Frame(f, bg=PANEL)
        cards.pack(pady=6)
        total = tk.Label(f, text="-", bg=PANEL, fg=FG, font=self.f_total)
        total.pack()
        return {"cards": cards, "total": total}

    def _stat(self, parent, label, col):
        f = tk.Frame(parent, bg=BG)
        f.grid(row=0, column=col, padx=16)
        v = tk.Label(f, text="-", bg=BG, fg=FG, font=self.f_total)
        v.pack()
        tk.Label(f, text=label, bg=BG, fg=DIM, font=self.f_small).pack()
        return v

    # ---------- 操作 ----------
    def pick(self, side):
        self.bet_side = side
        for k, b in self.side_btns.items():
            if k == side:
                col = {"player": PLAYER_C, "tie": TIE_C, "banker": BANKER_C}[k]
                b.config(bg=col, fg="#0b1220")
            else:
                col = {"player": PLAYER_C, "tie": TIE_C, "banker": BANKER_C}[k]
                b.config(bg=PANEL, fg=col)

    def add_chip(self, c):
        try:
            cur = int(float(self.amt_var.get() or 0))
        except ValueError:
            cur = 0
        self.amt_var.set(str(cur + c))

    def _amount(self):
        try:
            v = int(float(self.amt_var.get().strip().replace(",", "")))
            return max(0, v)
        except ValueError:
            return 0

    def _render_cards(self, area, cards):
        for w in area["cards"].winfo_children():
            w.destroy()
        for c in cards:
            suit = self.rng.choice(SUITS)
            red = suit in ("♥", "♦")
            lbl = tk.Label(area["cards"], text=f"{rank_label(c)}\n{suit}",
                           font=self.f_card, width=3, height=2,
                           bg=CARD_BG, fg=CARD_RED if red else CARD_FG,
                           relief="raised", bd=2)
            lbl.pack(side="left", padx=3)

    def deal(self):
        amt = self._amount()
        if amt <= 0:
            self.result_lbl.config(text="請先輸入下注金額", fg=NEG)
            return
        if amt > self.balance:
            self.result_lbl.config(text="假錢不夠了——按「重新開始」", fg=NEG)
            return

        out = eng.deal_baccarat(self.rng)
        self._render_cards(self.player_area, out["player"])
        self._render_cards(self.banker_area, out["banker"])
        self.player_area["total"].config(text=f"{out['player_total']} 點")
        self.banker_area["total"].config(text=f"{out['banker_total']} 點")

        change = eng.settle(self.bet_side, amt, out["winner"])
        self.balance += int(round(change))
        self.net += int(round(change))
        self.hands += 1
        won = (self.bet_side == out["winner"])
        if won:
            self.my_wins += 1

        winner_zh = {"player": "閒 贏", "banker": "莊 贏", "tie": "和 局"}[out["winner"]]
        if change > 0:
            self.result_lbl.config(text=f"{winner_zh}　你 +{int(round(change)):,}（假）", fg=POS)
        elif change < 0:
            self.result_lbl.config(text=f"{winner_zh}　你 {int(round(change)):,}（假）", fg=NEG)
        else:
            self.result_lbl.config(text=f"{winner_zh}　退還本金", fg=DIM)

        self.history.append(self.balance)
        self.refresh()

    def refresh(self):
        self.bal_lbl.config(text=f"{self.balance:,}", fg=GOLD if self.balance >= START_CHIPS else NEG)
        self.hands_lbl.config(text=str(self.hands))
        rate = (self.my_wins / self.hands * 100) if self.hands else 0
        self.rate_lbl.config(text=f"{rate:.0f}%")
        self.net_lbl.config(text=f"{self.net:+,}", fg=POS if self.net >= 0 else NEG)
        self.draw_curve()

    def draw_curve(self):
        c = self.canvas
        c.delete("all")
        c.update_idletasks()
        w = c.winfo_width() or 520
        h = c.winfo_height() or 110
        pad = 8
        data = self.history
        lo, hi = min(data), max(data)
        rng = (hi - lo) or 1

        # 起始線（10000 基準）
        def y_of(v):
            return h - pad - (v - lo) / rng * (h - 2 * pad)

        base_y = y_of(START_CHIPS)
        c.create_line(pad, base_y, w - pad, base_y, fill=EDGE, dash=(3, 3))
        c.create_text(pad + 2, base_y - 8, anchor="w", fill=DIM,
                      text=f"起始 {START_CHIPS:,}", font=self.f_small)

        if len(data) >= 2:
            step = (w - 2 * pad) / (len(data) - 1)
            pts = []
            for i, v in enumerate(data):
                pts.append(pad + i * step)
                pts.append(y_of(v))
            color = POS if data[-1] >= START_CHIPS else NEG
            c.create_line(*pts, fill=color, width=2, smooth=True)

    def reset(self):
        self.balance = START_CHIPS
        self.hands = 0
        self.my_wins = 0
        self.net = 0
        self.history = [START_CHIPS]
        self.player_area["total"].config(text="-")
        self.banker_area["total"].config(text="-")
        for area in (self.player_area, self.banker_area):
            for wdg in area["cards"].winfo_children():
                wdg.destroy()
        self.result_lbl.config(text="重新開始了。這次能撐幾手？", fg=FG)
        self.refresh()


def main():
    root = tk.Tk()
    Game(root)
    root.mainloop()


if __name__ == "__main__":
    main()
