"""
[為什麼] 戒賭用法：看真實賭場牌桌開牌，用假錢跟著下，不碰真錢。支援一手同時下多注。
         程式不發牌、不讀畫面、不預測；使用者建注單並輸入真實開牌結果，程式一次結算全部。
[怎麼做] tkinter GUI。① 點玩法把「玩法+金額」加入注單（26 種全支援，可多筆）。
         ② 輸入這手結果（閒點/莊點/各幾張/對子）。③ 結算此手 → baccarat_rules 一次算完。
         可自訂起始金額與玩法(標準/免佣)，全程存檔，輸光自動開新局，顯示總共輸了多少。
[結果]   零真錢風險、可多注、跨次啟動保留、輸光重開。
"""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from tkinter import font as tkfont

import baccarat_rules as rules

MIN_BET = 100
DEFAULT_START = 10000

BG = "#0b1220"; PANEL = "#131c2b"; EDGE = "#25344a"
FG = "#e6edf5"; DIM = "#8091a5"; GOLD = "#e8c268"
PLAYER = "#4aa3ff"; BANKER = "#ff6b6b"; TIE = "#54c98a"
PURPLE = "#c39bd3"; AMBER = "#e6b566"; ORANGE = "#ff9f6b"; TEAL = "#5bd6c0"
POS = "#3fb950"; NEG = "#ff5c6c"


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

DATA = os.path.join(base_dir(), "shadow_data.json")

MARKETS = [
    ("player", "閒", PLAYER), ("banker", "莊", BANKER), ("tie", "和", TIE),
    ("ppair", "閒對", PURPLE), ("bpair", "莊對", PURPLE),
    ("anypair", "任意對", PURPLE), ("perfectpair", "完美對", PURPLE),
    ("big", "大", AMBER), ("small", "小", AMBER),
    ("bodd", "莊單", AMBER), ("beven", "莊雙", AMBER),
    ("podd", "閒單", AMBER), ("peven", "閒雙", AMBER),
    ("super6", "超級6", ORANGE), ("tiger6", "老虎6", ORANGE),
    ("smalltiger", "小虎", ORANGE), ("bigtiger", "大虎", ORANGE),
    ("dragon_p", "閒龍寶", TEAL), ("dragon_b", "莊龍寶", TEAL),
    ("pnatural", "閒例牌", TEAL), ("bnatural", "莊例牌", TEAL),
    ("tigerpair", "虎對", ORANGE), ("tigertie", "虎和", ORANGE),
    ("panda8", "熊貓8", ORANGE), ("dragon7", "龍7", ORANGE),
    ("supertie", "超級和", PURPLE),
]
MARKET_ZH = {k: t for k, t, _ in MARKETS}
MARKET_COLOR = {k: c for k, _, c in MARKETS}


def default_data():
    return {"settings": {"start_amount": DEFAULT_START, "mode": "standard", "default_bet": 500},
            "sessions": [{"start": DEFAULT_START, "mode": "standard", "hands": []}]}


def load_data():
    if not os.path.isfile(DATA):
        return default_data()
    try:
        with open(DATA, encoding="utf-8") as fh:
            d = json.load(fh)
        assert isinstance(d, dict) and "sessions" in d and "settings" in d
        if not d["sessions"]:
            d["sessions"] = [{"start": d["settings"]["start_amount"], "mode": d["settings"]["mode"], "hands": []}]
        return d
    except (OSError, json.JSONDecodeError, AssertionError, KeyError):
        return default_data()


def save_data(d):
    try:
        with open(DATA, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def session_balance(sess):
    return sess["start"] + sum(h["change"] for h in sess["hands"])


class Shadow:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.slip = []       # [(market, amount), ...] 本手注單
        self.last_slip = []  # 上一手注單，供「重複上一手」

        root.title("假錢百家樂 — 跟真實牌桌（多注・全玩法）")
        root.configure(bg=BG)
        root.geometry("540x940+20+6")
        root.minsize(520, 860)

        self.f_title = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.f_big = tkfont.Font(family="Consolas", size=23, weight="bold")
        self.f_h = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_mid = tkfont.Font(family="Consolas", size=11, weight="bold")
        self.f_s = tkfont.Font(family="Segoe UI", size=9)
        self.f_xs = tkfont.Font(family="Segoe UI", size=8)

        tk.Label(root, text="假錢百家樂（多注・全玩法）", bg=BG, fg=GOLD, font=self.f_title).pack(pady=(4, 0))

        self.bal_lbl = tk.Label(root, text="0", bg=BG, fg=GOLD, font=self.f_big); self.bal_lbl.pack()
        stat = tk.Frame(root, bg=BG); stat.pack()
        self.hands_lbl = self._stat(stat, "手數", 0)
        self.rate_lbl = self._stat(stat, "勝率", 1)
        self.net_lbl = self._stat(stat, "本局淨", 2)
        self.life_lbl = tk.Label(root, text="", bg=BG, fg=DIM, font=self.f_xs); self.life_lbl.pack(pady=(1, 2))

        setrow = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        setrow.pack(fill="x", padx=8, pady=(1, 3))
        tk.Label(setrow, text="起始", bg=PANEL, fg=DIM, font=self.f_xs).grid(row=0, column=0, padx=(6, 2), pady=3)
        self.start_var = tk.StringVar(value=str(self.data["settings"]["start_amount"]))
        tk.Entry(setrow, textvariable=self.start_var, width=8, justify="center", font=self.f_s,
                 bg=BG, fg=FG, insertbackground=FG, relief="flat").grid(row=0, column=1, ipady=2)
        self.mode_var = tk.StringVar(value=self.data["settings"]["mode"])
        self.mode_btn = tk.Button(setrow, width=14, font=self.f_xs, relief="flat", cursor="hand2",
                                  bg=BG, fg=GOLD, activebackground=EDGE, command=self.toggle_mode)
        self.mode_btn.grid(row=0, column=2, padx=5, ipady=2)
        tk.Button(setrow, text="套用/開新局", font=self.f_xs, relief="flat", cursor="hand2",
                  bg=GOLD, fg=BG, activebackground="#f0d488", command=self.apply_settings).grid(row=0, column=3, padx=5, ipady=2)

        # ① 加注（點玩法 = 用目前金額加入注單）
        tk.Label(root, text="① 點玩法加入注單（可多筆）", bg=BG, fg=FG, font=self.f_h).pack(pady=(2, 1))
        amt_row = tk.Frame(root, bg=BG); amt_row.pack(pady=(0, 2))
        tk.Label(amt_row, text="金額", bg=BG, fg=DIM, font=self.f_xs).pack(side="left", padx=(0, 3))
        self.amt_var = tk.StringVar(value=str(self.data["settings"]["default_bet"]))
        tk.Entry(amt_row, textvariable=self.amt_var, width=8, justify="center", font=self.f_h,
                 bg=PANEL, fg=FG, insertbackground=FG, relief="flat").pack(side="left", ipady=2)
        for chip in (100, 500, 1000):
            tk.Button(amt_row, text=f"+{chip}", font=self.f_xs, relief="flat", cursor="hand2", bg=PANEL, fg=FG,
                      activebackground=EDGE, command=lambda c=chip: self.add_chip(c)).pack(side="left", padx=2, ipady=1)
        tk.Button(amt_row, text="重複上一手", font=self.f_xs, relief="flat", cursor="hand2", bg=PANEL, fg=GOLD,
                  activebackground=EDGE, command=self.repeat_last).pack(side="left", padx=(6, 0), ipady=1)

        mkt = tk.Frame(root, bg=BG); mkt.pack()
        for i, (k, t, c) in enumerate(MARKETS):
            tk.Button(mkt, text=t, width=5, font=self.f_xs, relief="flat", cursor="hand2",
                      bg=PANEL, fg=c, activebackground=c, activeforeground=BG,
                      command=lambda kk=k: self.add_bet(kk)).grid(row=i // 6, column=i % 6, padx=2, pady=2, ipady=2)

        # 注單顯示
        slip_row = tk.Frame(root, bg=BG); slip_row.pack(fill="x", padx=8, pady=(3, 1))
        self.slip_lbl = tk.Label(slip_row, text="注單：空", bg=BG, fg=GOLD, font=self.f_s,
                                 wraplength=420, justify="left", anchor="w")
        self.slip_lbl.pack(side="left", fill="x", expand=True)
        tk.Button(slip_row, text="清空", font=self.f_xs, relief="flat", bg=BG, fg=NEG,
                  activebackground=BG, cursor="hand2", command=self.clear_slip).pack(side="right")

        # 快速結算（只押莊/閒/和・標準玩法時，一鍵搞定）
        qf = tk.Frame(root, bg=BG); qf.pack(pady=(4, 1))
        tk.Label(qf, text="快速結算 ▶", bg=BG, fg=DIM, font=self.f_xs).pack(side="left", padx=(0, 4))
        for k, t, c in (("player", "閒贏", PLAYER), ("banker", "莊贏", BANKER), ("tie", "和局", TIE)):
            tk.Button(qf, text=t, width=6, font=self.f_h, relief="flat", cursor="hand2",
                      bg=c, fg=BG, activebackground=c, activeforeground=BG,
                      command=lambda kk=k: self.quick_settle(kk)).pack(side="left", padx=3, ipady=4)

        # ② 有邊注時：用點牌代替打點數（點你看到的牌，點數/對子/張數自動算）
        tk.Label(root, text="② 有邊注時：點你看到的牌（自動算點數）", bg=BG, fg=FG, font=self.f_h).pack(pady=(4, 1))
        self.p_cards = []; self.b_cards = []; self.target = "player"
        tgt = tk.Frame(root, bg=BG); tgt.pack()
        self.tgt_btns = {}
        for k, t, c in (("player", "輸入:閒", PLAYER), ("banker", "輸入:莊", BANKER)):
            b = tk.Button(tgt, text=t, width=8, font=self.f_s, relief="flat", cursor="hand2",
                          bg=PANEL, fg=c, activebackground=c, activeforeground=BG,
                          command=lambda kk=k: self._set_target(kk))
            b.pack(side="left", padx=4, ipady=3)
            self.tgt_btns[k] = b
        tk.Button(tgt, text="清除牌", width=6, font=self.f_xs, relief="flat", cursor="hand2",
                  bg=PANEL, fg=NEG, activebackground=EDGE, command=self._clear_cards).pack(side="left", padx=(8, 0), ipady=3)

        key = tk.Frame(root, bg=BG); key.pack(pady=(2, 1))
        for i, (rank, lab) in enumerate([(1, "A"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6"), (7, "7"),
                                         (8, "8"), (9, "9"), (10, "10"), (11, "J"), (12, "Q"), (13, "K")]):
            tk.Button(key, text=lab, width=3, font=self.f_s, relief="flat", cursor="hand2",
                      bg=PANEL, fg=FG, activebackground=GOLD, activeforeground=BG,
                      command=lambda r=rank: self._tap_card(r)).grid(row=i // 7, column=i % 7, padx=2, pady=2, ipady=2)

        self.hand_lbl = tk.Label(root, text="閒: -　莊: -", bg=BG, fg=FG, font=self.f_s); self.hand_lbl.pack(pady=(2, 0))
        self.v_perfect = tk.BooleanVar()
        tk.Checkbutton(root, text="完美對(同花同數，選填)", variable=self.v_perfect, bg=BG, fg=DIM, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG, font=self.f_xs).pack()

        tk.Button(root, text="結  算  此  手", font=self.f_h, bg=GOLD, fg=BG, relief="flat",
                  cursor="hand2", activebackground="#f0d488", command=self.settle).pack(fill="x", padx=8, pady=(4, 3), ipady=7)

        self.msg = tk.Label(root, text="① 點玩法加注 → ② 填開牌結果 → 結算此手。", bg=BG, fg=DIM,
                            font=self.f_s, wraplength=500); self.msg.pack(pady=(1, 2))

        self.canvas = tk.Canvas(root, height=64, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        self.canvas.pack(fill="x", padx=8, pady=(1, 3))

        bottom = tk.Frame(root, bg=BG); bottom.pack(pady=(1, 4))
        for t, cmd, col in (("撤銷上一手", self.undo, DIM), ("手動開新局", self.new_session, DIM), ("全部清除", self.wipe_all, NEG)):
            tk.Button(bottom, text=t, font=self.f_xs, relief="flat", bg=BG, fg=DIM,
                      activebackground=BG, activeforeground=col, cursor="hand2", command=cmd).pack(side="left", padx=6)

        self._set_target("player")
        self.update_mode_btn(); self.refresh()

    def _stat(self, parent, label, col):
        f = tk.Frame(parent, bg=BG); f.grid(row=0, column=col, padx=10)
        v = tk.Label(f, text="-", bg=BG, fg=FG, font=self.f_mid); v.pack()
        tk.Label(f, text=label, bg=BG, fg=DIM, font=self.f_xs).pack()
        return v

    def cur_session(self):
        return self.data["sessions"][-1]

    @staticmethod
    def _card_val(r):
        return r if r <= 9 else 0

    @staticmethod
    def _hand_total(cards):
        return sum(Shadow._card_val(c) for c in cards) % 10

    @staticmethod
    def _cards_str(cards):
        lab = {1: "A", 11: "J", 12: "Q", 13: "K"}
        return " ".join(lab.get(c, str(c)) for c in cards) if cards else "-"

    def _set_target(self, who):
        self.target = who
        for k, b in self.tgt_btns.items():
            c = PLAYER if k == "player" else BANKER
            b.config(bg=(c if k == who else PANEL), fg=(BG if k == who else c))

    def _tap_card(self, rank):
        cards = self.p_cards if self.target == "player" else self.b_cards
        if len(cards) >= 3:
            self.msg.config(text="一方最多 3 張", fg=NEG); return
        cards.append(rank)
        # 閒滿2張自動跳到莊，方便連續點
        if self.target == "player" and len(self.p_cards) == 2 and len(self.b_cards) == 0:
            self._set_target("banker")
        self._update_hand()

    def _clear_cards(self):
        self.p_cards = []; self.b_cards = []; self._set_target("player"); self._update_hand()

    def _update_hand(self):
        pt, bt = self._hand_total(self.p_cards), self._hand_total(self.b_cards)
        ps = f"{self._cards_str(self.p_cards)}" + (f" = {pt}點" if self.p_cards else "")
        bs = f"{self._cards_str(self.b_cards)}" + (f" = {bt}點" if self.b_cards else "")
        extra = ""
        if len(self.p_cards) >= 2 and self.p_cards[0] == self.p_cards[1]:
            extra += " [閒對]"
        if len(self.b_cards) >= 2 and self.b_cards[0] == self.b_cards[1]:
            extra += " [莊對]"
        self.hand_lbl.config(text=f"閒: {ps}　莊: {bs}{extra}")

    def add_chip(self, c):
        try:
            cur = int(float(self.amt_var.get() or 0))
        except ValueError:
            cur = 0
        self.amt_var.set(str(cur + c))

    def _amount(self):
        try:
            return max(0, int(float(self.amt_var.get().strip().replace(",", ""))))
        except ValueError:
            return 0

    def add_bet(self, market):
        amt = self._amount()
        if amt <= 0:
            self.msg.config(text="請先輸入金額再點玩法", fg=NEG); return
        for i, (mk, a) in enumerate(self.slip):
            if mk == market:
                self.slip[i] = (mk, a + amt); break
        else:
            self.slip.append((market, amt))
        self._render_slip()
        self.msg.config(text=f"已加入 {MARKET_ZH[market]} {amt:,}", fg=DIM)

    def _render_slip(self):
        if not self.slip:
            self.slip_lbl.config(text="注單：空"); return
        parts = [f"{MARKET_ZH[m]} {a:,}" for m, a in self.slip]
        total = sum(a for _, a in self.slip)
        self.slip_lbl.config(text="注單：" + "｜".join(parts) + f"　（共 {total:,}）")

    def clear_slip(self):
        self.slip = []; self._render_slip(); self.msg.config(text="注單已清空", fg=DIM)

    def _outcome(self):
        pt, bt = self._hand_total(self.p_cards), self._hand_total(self.b_cards)
        pc = len(self.p_cards) if self.p_cards else 2
        bc = len(self.b_cards) if self.b_cards else 2
        ppair = len(self.p_cards) >= 2 and self.p_cards[0] == self.p_cards[1]
        bpair = len(self.b_cards) >= 2 and self.b_cards[0] == self.b_cards[1]
        return rules.make_outcome(pt, bt, pc, bc, ppair, bpair, self.v_perfect.get())

    def settle(self):
        if not self.slip:
            self.msg.config(text="注單是空的，先加注", fg=NEG); return
        self._do_settle(self._outcome())

    MAIN = {"player", "banker", "tie"}

    def quick_settle(self, winner):
        """只押莊/閒/和・標準玩法時，一鍵結算，不用填點數。"""
        if not self.slip:
            self.msg.config(text="注單是空的，先加注", fg=NEG); return
        markets = {m for m, _ in self.slip}
        if not markets <= self.MAIN:
            self.msg.config(text="注單有邊注，請用②填開牌細節再『結算此手』", fg=NEG); return
        if self.cur_session()["mode"] == "nocomm" and "banker" in markets and winner == "banker":
            self.msg.config(text="免佣莊注要知道是否6點，請用②填細節結算", fg=NEG); return
        # 用「只決定贏家」的結果：閒→9:0，莊→0:9，和→0:0
        o = {"player": rules.make_outcome(9, 0), "banker": rules.make_outcome(0, 9),
             "tie": rules.make_outcome(0, 0)}[winner]
        self._do_settle(o)

    def repeat_last(self):
        if not self.last_slip:
            self.msg.config(text="還沒有上一手可重複", fg=DIM); return
        self.slip = [tuple(b) for b in self.last_slip]; self._render_slip()
        total = sum(a for _, a in self.slip)
        self.msg.config(text=f"已載入上一手注單（共 {total:,}），填結果或按快速結算", fg=DIM)

    def _do_settle(self, o):
        sess = self.cur_session(); bal = session_balance(sess)
        staked = sum(a for _, a in self.slip)
        if staked > bal:
            self.msg.config(text=f"注單總額 {staked:,} 超過餘額 {bal:,}", fg=NEG); return
        rows, total = rules.settle_all(self.slip, o, sess["mode"])
        sess["hands"].append({"bets": [list(b) for b in self.slip], "outcome": o, "change": total})
        self.data["settings"]["default_bet"] = self._amount(); save_data(self.data)
        w = {"player": "閒贏", "banker": "莊贏", "tie": "和局"}[rules.winner_of(o)]
        self.last_slip = [tuple(b) for b in self.slip]
        self.slip = []; self._render_slip(); self._reset_outcome()
        if session_balance(sess) < MIN_BET:
            tn = self._total_net()
            self._start_new(self.data["settings"]["start_amount"], sess["mode"])
            self.refresh(msg=f"這局輸光了，已自動開新局。目前總共{'輸' if tn < 0 else '贏'}了 {abs(tn):,}（假）。")
        else:
            sign = "+" if total >= 0 else ""
            self.refresh(msg=f"{w}｜這手結算 {sign}{total:,}（假）。" + ("見好就收。" if total > 0 else "還好是假錢。"))

    def _reset_outcome(self):
        self.v_perfect.set(False)
        self.p_cards = []; self.b_cards = []; self._set_target("player"); self._update_hand()

    def toggle_mode(self):
        self.mode_var.set("nocomm" if self.mode_var.get() == "standard" else "standard"); self.update_mode_btn()

    def update_mode_btn(self):
        self.mode_btn.config(text="標準(莊抽5%)" if self.mode_var.get() == "standard" else "免佣(莊6點半賠)")

    def _mode_zh(self, m):
        return "標準抽水" if m == "standard" else "免佣"

    def apply_settings(self):
        try:
            amt = int(float(self.start_var.get().strip().replace(",", "")))
        except ValueError:
            self.msg.config(text="起始金額請輸入數字", fg=NEG); return
        if amt < MIN_BET:
            self.msg.config(text=f"起始金額至少 {MIN_BET}", fg=NEG); return
        self.data["settings"]["start_amount"] = amt
        self.data["settings"]["mode"] = self.mode_var.get()
        self.slip = []; self._render_slip()
        self._start_new(amt, self.mode_var.get())
        self.refresh(msg=f"新局：起始 {amt:,}，{self._mode_zh(self.mode_var.get())}")

    def _start_new(self, amt, mode):
        self.data["sessions"].append({"start": amt, "mode": mode, "hands": []}); save_data(self.data)

    def undo(self):
        sess = self.cur_session()
        if sess["hands"]:
            sess["hands"].pop(); save_data(self.data); self.refresh(msg="已撤銷上一手")
        elif len(self.data["sessions"]) > 1:
            self.data["sessions"].pop(); save_data(self.data); self.refresh(msg="已回到上一局")
        else:
            self.msg.config(text="沒有可撤銷的紀錄", fg=DIM)

    def new_session(self):
        self.slip = []; self._render_slip()
        self._start_new(self.data["settings"]["start_amount"], self.mode_var.get())
        self.refresh(msg="手動開了新的一局")

    def wipe_all(self):
        self.data = default_data(); save_data(self.data); self.slip = []; self._render_slip()
        self.start_var.set(str(DEFAULT_START)); self.mode_var.set("standard"); self.update_mode_btn()
        self.refresh(msg="全部清除，重新開始。")

    def _total_net(self):
        return sum(h["change"] for s in self.data["sessions"] for h in s["hands"])

    def refresh(self, msg=None):
        sess = self.cur_session(); bal = session_balance(sess)
        hands = len(sess["hands"])
        wins = sum(1 for h in sess["hands"] if h["change"] > 0)
        net = sum(h["change"] for h in sess["hands"])
        rate = (wins / hands * 100) if hands else 0
        self.bal_lbl.config(text=f"{bal:,}", fg=GOLD if bal >= sess["start"] else NEG)
        self.hands_lbl.config(text=str(hands)); self.rate_lbl.config(text=f"{rate:.0f}%")
        self.net_lbl.config(text=f"{net:+,}", fg=POS if net >= 0 else NEG)
        total_hands = sum(len(s["hands"]) for s in self.data["sessions"])
        tn = self._total_net(); sess_no = len(self.data["sessions"])
        money = f"總共輸了 {abs(tn):,}" if tn < 0 else (f"總共贏了 {tn:,}" if tn > 0 else "總共打平")
        self.life_lbl.config(text=f"第 {sess_no} 局 ｜ 玩了 {total_hands} 手 ｜ {money} ｜ {self._mode_zh(sess['mode'])}",
                             fg=NEG if tn < 0 else DIM)
        self.draw(sess)
        if msg:
            self.msg.config(text=msg, fg=(POS if "贏" in msg or "+" in msg else (NEG if "輸" in msg else DIM)))

    def draw(self, sess):
        c = self.canvas; c.delete("all"); c.update_idletasks()
        w = c.winfo_width() or 500; h = c.winfo_height() or 64; pad = 8
        hist = [sess["start"]]; b = sess["start"]
        for hd in sess["hands"]:
            b += hd["change"]; hist.append(b)
        lo, hi = min(hist), max(hist); rng = (hi - lo) or 1
        yof = lambda v: h - pad - (v - lo) / rng * (h - 2 * pad)
        by = yof(sess["start"])
        c.create_line(pad, by, w - pad, by, fill=EDGE, dash=(3, 3))
        c.create_text(pad + 2, by - 8, anchor="w", fill=DIM, text=f"起始 {sess['start']:,}", font=self.f_xs)
        if len(hist) >= 2:
            step = (w - 2 * pad) / (len(hist) - 1); pts = []
            for i, v in enumerate(hist):
                pts += [pad + i * step, yof(v)]
            c.create_line(*pts, fill=(POS if hist[-1] >= sess["start"] else NEG), width=2, smooth=True)


def main():
    root = tk.Tk(); Shadow(root); root.mainloop()


if __name__ == "__main__":
    main()
