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
DEFAULT_CHIPS = [100, 500, 1000, 5000]

BG = "#07111f"; PANEL = "#0e1b2b"; RAISED = "#15263a"; EDGE = "#223852"
FG = "#f1f5f9"; DIM = "#8fa3b8"; GOLD = "#f5c76b"
PLAYER = "#42a5ff"; BANKER = "#ff6673"; TIE = "#43d39e"
PURPLE = "#bc8cff"; AMBER = "#f2b968"; ORANGE = "#ff9d66"; TEAL = "#56dcc6"
POS = "#45d483"; NEG = "#ff6673"


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

DATA = os.path.join(base_dir(), "shadow_data.json")
SCREEN_REGIONS = os.path.join(base_dir(), "screen_card_regions.json")

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
    return {"settings": {"start_amount": DEFAULT_START, "mode": "standard", "default_bet": 0,
                         "chip_values": list(DEFAULT_CHIPS), "platform_mode": "auto",
                         "capture_window_title": ""},
            "sessions": [{"start": DEFAULT_START, "mode": "standard", "hands": []}]}


def load_data():
    if not os.path.isfile(DATA):
        return default_data()
    try:
        with open(DATA, encoding="utf-8") as fh:
            d = json.load(fh)
        assert isinstance(d, dict) and "sessions" in d and "settings" in d
        d["settings"].setdefault("chip_values", list(DEFAULT_CHIPS))
        d["settings"].setdefault("platform_mode", "auto")
        d["settings"].setdefault("capture_window_title", "")
        d["settings"]["default_bet"] = 0
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


def session_turnover(sess):
    """Return the total settled stake for one session.

    Older data files may contain hands without a ``bets`` field, so malformed
    or missing bet entries are ignored instead of preventing the app from
    starting.
    """
    total = 0
    for hand in sess.get("hands", []):
        for bet in hand.get("bets", []):
            try:
                amount = int(bet[1])
            except (IndexError, TypeError, ValueError):
                continue
            if amount > 0:
                total += amount
    return total


class Shadow:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.slip = []       # [(market, amount), ...] 本手注單
        self.last_slip = []  # 上一手注單，供「重複上一手」
        self.screen_monitor = None
        self.detected_platform = None

        root.title("百家樂練習程式")
        root.configure(bg=BG)
        # Keep the window comfortably above the Windows taskbar. The content
        # remains scrollable, so a shorter default is safer on laptop screens.
        window_height = max(620, min(700, root.winfo_screenheight() - 140))
        root.geometry(f"760x{window_height}+20+20")
        root.minsize(660, 600)

        # 所有內容放入可捲動頁面，避免小螢幕或高 DPI 時底部被裁切。
        self.ui_canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.ui_scroll = tk.Scrollbar(root, orient="vertical", command=self.ui_canvas.yview)
        self.ui_canvas.configure(yscrollcommand=self.ui_scroll.set)
        self.ui_scroll.pack(side="right", fill="y")
        self.ui_canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.ui_canvas, bg=BG)
        self.body_window = self.ui_canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.ui_canvas.configure(scrollregion=self.ui_canvas.bbox("all")))
        self.ui_canvas.bind("<Configure>", lambda e: self.ui_canvas.itemconfigure(self.body_window, width=e.width))
        self.ui_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        root = self.body

        self.f_title = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.f_big = tkfont.Font(family="Consolas", size=27, weight="bold")
        self.f_h = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_mid = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.f_s = tkfont.Font(family="Segoe UI", size=9)
        self.f_xs = tkfont.Font(family="Segoe UI", size=8)

        streak_bar = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        streak_bar.pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(streak_bar, text="近期輸贏", bg=PANEL, fg=DIM,
                 font=self.f_xs).pack(side="left", padx=(14, 9), pady=9)
        self.streak_frame = tk.Frame(streak_bar, bg=PANEL)
        self.streak_frame.pack(side="left", fill="x", expand=True, pady=6)

        result_bar = tk.Frame(root, bg=RAISED, highlightbackground=EDGE, highlightthickness=1)
        result_bar.pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(result_bar, text="本手結果", bg=RAISED, fg=DIM,
                 font=self.f_xs).pack(side="left", padx=(16, 10), pady=10)
        self.result_lbl = tk.Label(result_bar, text="等待下注", bg=RAISED, fg=GOLD,
                                   font=self.f_h, anchor="w", justify="left", wraplength=610)
        self.result_lbl.pack(side="left", fill="x", expand=True, pady=8)

        hero = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        hero.pack(fill="x", padx=14, pady=(8, 8))
        hero.grid_columnconfigure(0, weight=1); hero.grid_columnconfigure(1, weight=1)
        brand = tk.Frame(hero, bg=PANEL); brand.grid(row=0, column=0, sticky="nw", padx=18, pady=(15, 6))
        tk.Label(brand, text="百家樂練習程式", bg=PANEL, fg=FG, font=self.f_title).pack(anchor="w")
        tk.Label(brand, text="自動辨識・假錢練習", bg=PANEL, fg=GOLD, font=self.f_h).pack(anchor="w")
        tk.Label(brand, text="● 螢幕辨識監控中", bg="#10382f", fg=TEAL,
                 font=self.f_xs, padx=9, pady=4).pack(anchor="w", pady=(8, 0))
        balance_box = tk.Frame(hero, bg=RAISED, highlightbackground=EDGE, highlightthickness=1)
        balance_box.grid(row=0, column=1, sticky="nsew", padx=(4, 18), pady=(12, 6))
        tk.Label(balance_box, text="可用餘額", bg=RAISED, fg=DIM, font=self.f_xs).pack(pady=(9, 0))
        self.bal_lbl = tk.Label(balance_box, text="0", bg=RAISED, fg=GOLD, font=self.f_big)
        self.bal_lbl.pack(pady=(0, 8))
        stat = tk.Frame(hero, bg=PANEL); stat.grid(row=1, column=0, columnspan=2, pady=(4, 7))
        self.hands_lbl = self._stat(stat, "手數", 0)
        self.rate_lbl = self._stat(stat, "勝率", 1)
        self.net_lbl = self._stat(stat, "本局淨", 2)
        self.turnover_lbl = self._stat(stat, "Session 流水", 3)
        self.life_lbl = tk.Label(hero, text="", bg=PANEL, fg=DIM, font=self.f_xs)
        self.life_lbl.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        setrow = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        setrow.pack(fill="x", padx=14, pady=(0, 9), ipady=5)
        tk.Label(setrow, text="牌局設定", bg=PANEL, fg=FG, font=self.f_h).grid(row=0, column=0, padx=(12, 8), pady=4)
        tk.Label(setrow, text="起始資金", bg=PANEL, fg=DIM, font=self.f_xs).grid(row=0, column=1, padx=(2, 3))
        self.start_var = tk.StringVar(value=str(self.data["settings"]["start_amount"]))
        tk.Entry(setrow, textvariable=self.start_var, width=8, justify="center", font=self.f_s,
                 bg=RAISED, fg=FG, insertbackground=FG, relief="flat").grid(row=0, column=2, ipady=3)
        self.mode_var = tk.StringVar(value=self.data["settings"]["mode"])
        self.mode_btn = tk.Button(setrow, width=14, font=self.f_xs, relief="flat", cursor="hand2",
                                  bg=RAISED, fg=GOLD, activebackground=EDGE, command=self.toggle_mode)
        self.mode_btn.grid(row=0, column=3, padx=6, ipady=3)
        self.platform_var = tk.StringVar(value=self.data["settings"].get("platform_mode", "auto"))
        self.platform_btn = tk.Button(setrow, width=17, font=self.f_xs, relief="flat", cursor="hand2",
                                      bg=RAISED, fg=TEAL, activebackground=EDGE,
                                      command=self.cycle_platform)
        self.platform_btn.grid(row=0, column=4, padx=(0, 6), ipady=3)
        tk.Button(setrow, text="手動開新局", font=self.f_xs, relief="flat", cursor="hand2",
                  bg=GOLD, fg=BG, activebackground="#f0d488", command=self.apply_settings).grid(
                      row=0, column=5, padx=(2, 10), ipady=3)

        bet_panel = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        bet_panel.pack(fill="x", padx=14, pady=(0, 9))
        bet_head = tk.Frame(bet_panel, bg=PANEL); bet_head.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(bet_head, text="本手下注", bg=PANEL, fg=FG, font=self.f_h).pack(side="left")
        tk.Button(bet_head, text="重複上一手", font=self.f_xs, relief="flat", cursor="hand2",
                  bg=RAISED, fg=GOLD, activebackground=EDGE, command=self.repeat_last).pack(side="right")
        amount_row = tk.Frame(bet_panel, bg=PANEL); amount_row.pack(fill="x", padx=14)
        self.amt_var = tk.StringVar(value="0")
        tk.Entry(amount_row, textvariable=self.amt_var, width=12, justify="right", font=self.f_mid,
                 bg=RAISED, fg=FG, insertbackground=FG, relief="flat").pack(side="left", ipady=7)
        tk.Button(amount_row, text="ALL IN", font=self.f_h, relief="flat", cursor="hand2",
                  bg=BANKER, fg=BG, activebackground="#ff8a8a", command=self.all_in).pack(
                      side="left", padx=(7, 3), ipadx=8, ipady=5)
        tk.Button(amount_row, text="自訂籌碼", font=self.f_xs, relief="flat", cursor="hand2",
                  bg=RAISED, fg=TEAL, activebackground=EDGE, command=self.edit_chips).pack(
                      side="left", padx=3, ipadx=5, ipady=6)
        self.chip_bar = tk.Frame(bet_panel, bg=PANEL); self.chip_bar.pack(fill="x", padx=12, pady=(7, 9))
        self._render_chip_buttons()

        tk.Label(bet_panel, text="主注", bg=PANEL, fg=DIM, font=self.f_xs).pack(anchor="w", padx=14)
        main_mkt = tk.Frame(bet_panel, bg=PANEL); main_mkt.pack(fill="x", padx=11, pady=(4, 8))
        for col, (k, t, c) in enumerate(MARKETS[:3]):
            main_mkt.grid_columnconfigure(col, weight=1)
            tk.Button(main_mkt, text=t, font=self.f_title, relief="flat", cursor="hand2",
                      bg=RAISED, fg=c, activebackground=c, activeforeground=BG,
                      command=lambda kk=k: self.add_bet(kk)).grid(
                          row=0, column=col, sticky="ew", padx=3, ipady=9)

        tk.Label(bet_panel, text="邊注", bg=PANEL, fg=DIM, font=self.f_xs).pack(anchor="w", padx=14)
        mkt = tk.Frame(bet_panel, bg=PANEL); mkt.pack(padx=10, pady=(3, 11))
        auto_markets = [market for market in MARKETS[3:] if market[0] != "perfectpair"]
        for i, (k, t, c) in enumerate(auto_markets):
            tk.Button(mkt, text=t, width=7, font=self.f_xs, relief="flat", cursor="hand2",
                      bg=RAISED, fg=c, activebackground=c, activeforeground=BG,
                      command=lambda kk=k: self.add_bet(kk)).grid(row=i // 6, column=i % 6, padx=3, pady=3, ipady=3)

        # 注單顯示
        slip_row = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        slip_row.pack(fill="x", padx=12, pady=(6, 5), ipady=6)
        self.slip_lbl = tk.Label(slip_row, text="注單：空", bg=BG, fg=GOLD, font=self.f_s,
                                 wraplength=420, justify="left", anchor="w")
        self.slip_lbl.pack(side="left", fill="x", expand=True)
        tk.Button(slip_row, text="清空", font=self.f_xs, relief="flat", bg=BG, fg=NEG,
                  activebackground=BG, cursor="hand2", command=self.clear_slip).pack(side="right")

        # Recognition is fully automatic. Keep only the internal card state
        # required by the settlement callback; no manual card-entry UI.
        self.p_cards = []; self.b_cards = []; self.target = "player"
        self.tgt_btns = {}
        self.hand_lbl = tk.Label(root, text="")
        self.v_perfect = tk.BooleanVar()

        self.msg = tk.Label(root, text="先建立注單；辨識到完整牌局後會自動結算。", bg=PANEL, fg=DIM,
                            font=self.f_s, wraplength=620, padx=12, pady=8,
                            highlightbackground=EDGE, highlightthickness=1)
        self.msg.pack(fill="x", padx=12, pady=(4, 7))

        self.canvas = tk.Canvas(root, height=64, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        self.canvas.pack(fill="x", padx=8, pady=(1, 3))

        bottom = tk.Frame(root, bg=BG); bottom.pack(pady=(1, 4))
        for t, cmd, col in (("撤銷上一手", self.undo, DIM), ("手動開新局", self.new_session, DIM), ("全部清除", self.wipe_all, NEG)):
            tk.Button(bottom, text=t, font=self.f_xs, relief="flat", bg=BG, fg=DIM,
                      activebackground=BG, activeforeground=col, cursor="hand2", command=cmd).pack(side="left", padx=6)
        tk.Frame(root, bg=BG, height=18).pack(fill="x")

        self._set_target("player")
        self.update_mode_btn(); self.update_platform_btn(); self.refresh()
        # 啟動後自動擷取目前螢幕尋找牌面，不需要先按按鈕。
        self.root.after(900, self.open_screen_recognizer)

    def _on_mousewheel(self, event):
        self.ui_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _stat(self, parent, label, col):
        parent_bg = parent.cget("bg")
        f = tk.Frame(parent, bg=parent_bg); f.grid(row=0, column=col, padx=18)
        v = tk.Label(f, text="-", bg=parent_bg, fg=FG, font=self.f_mid); v.pack()
        tk.Label(f, text=label, bg=parent_bg, fg=DIM, font=self.f_xs).pack()
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

    def open_screen_recognizer(self):
        if self.screen_monitor is not None:
            try:
                if self.screen_monitor.window.winfo_exists():
                    self.screen_monitor.window.lift()
                    return
            except tk.TclError:
                pass
        try:
            from screen_card_monitor import ScreenCardMonitor
            self.screen_monitor = ScreenCardMonitor(
                self.root, self._apply_screen_cards, SCREEN_REGIONS,
                platform_mode=self.platform_var.get(),
                on_platform=self._on_platform_detected,
                capture_window_title=self.data["settings"].get("capture_window_title", ""),
                on_capture_window=self._on_capture_window)
        except (ImportError, OSError) as exc:
            self.msg.config(text=f"無法啟動螢幕辨識：{exc}。請安裝 requirements.txt 後重試。", fg=NEG)
            return

    def _apply_screen_cards(self, player_cards, banker_cards, official_scores=None, evidence=None):
        self.p_cards = [int(rank) for rank in player_cards if 1 <= int(rank) <= 13][:3]
        self.b_cards = [int(rank) for rank in banker_cards if 1 <= int(rank) <= 13][:3]
        self._set_target("player")
        self._update_hand()
        pt, bt = self._hand_total(self.p_cards), self._hand_total(self.b_cards)
        winner = "閒贏" if pt > bt else "莊贏" if bt > pt else "和局"
        if self.slip:
            markets = {market for market, _ in self.slip}
            if not official_scores:
                self.msg.config(text="牌面已穩定，正在等待網站官方計分板確認，暫不結算。", fg=AMBER)
                return False
            if official_scores and markets <= self.SCORE_ONLY:
                official_player, official_banker = official_scores
                outcome = rules.make_outcome(official_player, official_banker,
                                             len(self.p_cards), len(self.b_cards))
                self._do_settle(outcome)
                return True
            evidence = dict(evidence or {})
            if len(self.p_cards) in (2, 3):
                evidence.update({"pc": len(self.p_cards),
                                 "ppair": self.p_cards[0] == self.p_cards[1]})
            if len(self.b_cards) in (2, 3):
                evidence.update({"bc": len(self.b_cards),
                                 "bpair": self.b_cards[0] == self.b_cards[1]})
            official_player, official_banker = official_scores
            official_winner = ("player" if official_player > official_banker else
                               "banker" if official_banker > official_player else "tie")
            required = set()
            if markets & {"ppair", "anypair", "tigerpair"}:
                required.add("ppair")
            if markets & {"bpair", "anypair", "tigerpair"}:
                required.add("bpair")
            if markets & {"big", "small"}:
                required.update(("pc", "bc"))
            if (markets & {"super6", "tiger6", "smalltiger", "bigtiger"}
                    and official_winner == "banker" and official_banker == 6):
                required.add("bc")
            if "pnatural" in markets and official_winner in ("player", "tie"):
                required.add("pc")
            if "bnatural" in markets and official_winner in ("banker", "tie"):
                required.add("bc")
            if "panda8" in markets and official_winner == "player" and official_player == 8:
                required.add("pc")
            if "dragon7" in markets and official_winner == "banker" and official_banker == 7:
                required.add("bc")
            if "dragon_p" in markets and official_winner in ("player", "tie"):
                required.add("pc")
                if official_winner == "tie":
                    required.add("bc")
            if "dragon_b" in markets and official_winner in ("banker", "tie"):
                required.add("bc")
                if official_winner == "tie":
                    required.add("pc")
            missing = []
            if "ppair" in required and "ppair" not in evidence: missing.append("閒家前兩張")
            if "bpair" in required and "bpair" not in evidence: missing.append("莊家前兩張")
            if "pc" in required and "pc" not in evidence: missing.append("閒家張數")
            if "bc" in required and "bc" not in evidence: missing.append("莊家張數")
            if "perfectpair" in markets:
                missing.append("花色")
            if official_scores and not missing:
                official_player, official_banker = official_scores
                outcome = rules.make_outcome(
                    official_player, official_banker,
                    evidence.get("pc", 0), evidence.get("bc", 0),
                    evidence.get("ppair", False), evidence.get("bpair", False), False)
                self._do_settle(outcome)
                return True
            if (pt, bt) != tuple(official_scores):
                card_markets = "、".join(MARKET_ZH.get(market, market)
                                         for market in sorted(markets - self.SCORE_ONLY))
                self.msg.config(text=(f"未結算：{card_markets or '此邊注'}需要最終牌張，"
                                      f"目前缺少{'、'.join(missing) or '可信牌面'}；官方比分為 "
                                      f"{official_scores[0]}:{official_scores[1]}。"), fg=NEG)
                return False
            if "perfectpair" in markets:
                self.msg.config(text="完美對目前不支援全自動花色辨識，已停止本手結算。", fg=AMBER)
                return False
            self._do_settle(self._outcome())
            return True
        else:
            self.msg.config(text=f"辨識完成：{winner}（閒 {pt} 點／莊 {bt} 點），但本手沒有注單，因此未結算。", fg=AMBER)
            return True

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

    @staticmethod
    def _chip_label(value):
        if value >= 1_000_000 and value % 1_000_000 == 0:
            return f"+{value // 1_000_000}M"
        if value >= 1000 and value % 1000 == 0:
            return f"+{value // 1000}K"
        return f"+{value:,}"

    def _render_chip_buttons(self):
        for child in self.chip_bar.winfo_children():
            child.destroy()
        values = self.data["settings"].get("chip_values", DEFAULT_CHIPS)
        for value in values:
            tk.Button(self.chip_bar, text=self._chip_label(value), font=self.f_h,
                      relief="flat", cursor="hand2", bg=RAISED, fg=FG,
                      activebackground=GOLD, activeforeground=BG,
                      command=lambda c=value: self.add_chip(c)).pack(
                          side="left", expand=True, fill="x", padx=3, ipady=5)

    def edit_chips(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("自訂籌碼")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        values = self.data["settings"].get("chip_values", DEFAULT_CHIPS)
        variables = [tk.StringVar(value=str(value)) for value in values]
        tk.Label(dialog, text="設定四個常用籌碼", bg=BG, fg=FG,
                 font=self.f_h).pack(padx=22, pady=(17, 5))
        tk.Label(dialog, text="輸入正整數，套用後會自動保存", bg=BG, fg=DIM,
                 font=self.f_xs).pack(pady=(0, 9))
        entries = tk.Frame(dialog, bg=BG); entries.pack(padx=18)
        for index, variable in enumerate(variables):
            tk.Entry(entries, textvariable=variable, width=9, justify="center",
                     bg=RAISED, fg=FG, insertbackground=FG, relief="flat",
                     font=self.f_s).grid(row=0, column=index, padx=3, ipady=5)
        error = tk.Label(dialog, text="", bg=BG, fg=NEG, font=self.f_xs)
        error.pack(pady=(5, 0))

        def save_chips():
            try:
                chips = [int(v.get().strip().replace(",", "")) for v in variables]
            except ValueError:
                error.config(text="籌碼必須是整數")
                return
            if any(value <= 0 for value in chips) or len(set(chips)) != len(chips):
                error.config(text="請輸入四個不同的正整數")
                return
            self.data["settings"]["chip_values"] = chips
            save_data(self.data)
            self._render_chip_buttons()
            self.msg.config(text="自訂籌碼已保存", fg=TEAL)
            dialog.destroy()

        tk.Button(dialog, text="保存籌碼", command=save_chips, bg=GOLD, fg=BG,
                  activebackground="#f0d488", relief="flat", font=self.f_h,
                  cursor="hand2").pack(fill="x", padx=18, pady=(8, 16), ipady=6)
        dialog.grab_set()

    def all_in(self):
        available = self.available_balance()
        self.amt_var.set(str(available))
        if available:
            self.msg.config(text=f"ALL IN 金額已設為 {available:,}，請選擇下注項目", fg=BANKER)
        else:
            self.msg.config(text="目前沒有可再下注的餘額", fg=NEG)

    def _amount(self):
        try:
            return max(0, int(float(self.amt_var.get().strip().replace(",", ""))))
        except ValueError:
            return 0

    def available_balance(self):
        ledger_balance = session_balance(self.cur_session())
        reserved = sum(amount for _, amount in self.slip)
        return max(0, ledger_balance - reserved)

    @staticmethod
    def _bet_summary(bets):
        return "、".join(f"押{MARKET_ZH.get(market, market)} {amount:,}" for market, amount in bets)

    @staticmethod
    def _result_summary(hand):
        winner = rules.winner_of(hand["outcome"])
        winner_text = {"player": "閒贏", "banker": "莊贏", "tie": "和局"}[winner]
        change = hand["change"]
        rows = hand.get("results") or []
        if rows:
            details = []
            for market, amount, result in rows:
                bet = f"押{MARKET_ZH.get(market, market)} {amount:,}"
                if result > 0:
                    details.append(f"{bet}：贏 +{result:,}")
                elif result < 0:
                    details.append(f"{bet}：輸 {abs(result):,}")
                else:
                    details.append(f"{bet}：退回")
            total = f"本手 {change:+,}" if change else "本手 0"
            color = POS if change > 0 else NEG if change < 0 else (TIE if winner == "tie" else GOLD)
            return f"{winner_text}｜" + "｜".join(details) + f"｜{total}", color
        if change > 0:
            return f"{winner_text}｜本手贏 +{change:,}", POS
        if change < 0:
            return f"{winner_text}｜本手輸 {change:,}", NEG
        if winner == "tie":
            return "和局｜本金退回", TIE
        return f"{winner_text}｜本手打平 0", GOLD

    @staticmethod
    def _streak_values(hands, limit=12):
        values = []
        for hand in hands[-limit:]:
            change = hand["change"]
            outcome = "贏" if change > 0 else "輸" if change < 0 else "和"
            labels = [MARKET_ZH.get(market, market) for market, _amount in hand.get("bets", [])]
            if not labels:
                bet_text = "未記錄"
            else:
                bet_text = "/".join(labels[:2]) + ("…" if len(labels) > 2 else "")
            values.append((bet_text, outcome))
        return values

    def _render_streak(self, hands):
        for child in self.streak_frame.winfo_children():
            child.destroy()
        values = self._streak_values(hands)
        if not values:
            tk.Label(self.streak_frame, text="尚無紀錄", bg=PANEL, fg=DIM,
                     font=self.f_s).pack(side="left")
            return
        colors = {"贏": POS, "輸": NEG, "和": RAISED}
        for bet_text, outcome in values:
            width = max(3, min(7, len(bet_text)))
            tk.Label(self.streak_frame, text=f"{bet_text}\n{outcome}",
                     bg=colors[outcome], fg=FG, font=self.f_xs,
                     width=width, padx=2, pady=2).pack(side="left", padx=2)

    def add_bet(self, market):
        amt = self._amount()
        if amt <= 0:
            self.msg.config(text="請先輸入金額再點玩法", fg=NEG); return
        available = self.available_balance()
        if amt > available:
            self.msg.config(text=f"可用餘額只有 {available:,}，無法下注 {amt:,}", fg=NEG)
            return
        for i, (mk, a) in enumerate(self.slip):
            if mk == market:
                self.slip[i] = (mk, a + amt); break
        else:
            self.slip.append((market, amt))
        self.amt_var.set("0")
        self._render_slip()
        self.refresh()
        self.msg.config(text=f"已加入 {MARKET_ZH[market]} {amt:,}", fg=DIM)

    def _render_slip(self):
        if not self.slip:
            self.slip_lbl.config(text="注單：空"); return
        parts = [f"{MARKET_ZH[m]} {a:,}" for m, a in self.slip]
        total = sum(a for _, a in self.slip)
        self.slip_lbl.config(text="注單：" + "｜".join(parts) + f"　（共 {total:,}）")

    def clear_slip(self):
        self.slip = []; self.amt_var.set("0"); self._render_slip(); self.refresh()
        self.msg.config(text="注單已清空，保留金額已退回可用餘額", fg=DIM)

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
    SCORE_ONLY = MAIN | {"bodd", "beven", "podd", "peven", "tigertie", "supertie"}

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
        total = sum(a for _, a in self.last_slip)
        if total > session_balance(self.cur_session()):
            self.msg.config(text=f"上一手共 {total:,}，超過目前餘額", fg=NEG)
            return
        self.slip = [tuple(b) for b in self.last_slip]; self._render_slip(); self.refresh()
        self.msg.config(text=f"已載入上一手注單（共 {total:,}），等待自動辨識結算", fg=DIM)

    def _do_settle(self, o):
        sess = self.cur_session(); bal = session_balance(sess)
        staked = sum(a for _, a in self.slip)
        if staked > bal:
            self.msg.config(text=f"注單總額 {staked:,} 超過餘額 {bal:,}", fg=NEG); return
        rows, total = rules.settle_all(self.slip, o, sess["mode"])
        sess["hands"].append({"bets": [list(b) for b in self.slip],
                              "results": [list(row) for row in rows],
                              "outcome": o, "change": total})
        self.data["settings"]["default_bet"] = 0; save_data(self.data)
        w = {"player": "閒贏", "banker": "莊贏", "tie": "和局"}[rules.winner_of(o)]
        self.last_slip = [tuple(b) for b in self.slip]
        self.slip = []; self.amt_var.set("0"); self._render_slip(); self._reset_outcome()
        if session_balance(sess) < MIN_BET:
            self.refresh(msg="餘額低於最低下注，已停止下注；不會自動重開新局。")
        else:
            sign = "+" if total >= 0 else ""
            self.refresh(msg=f"{w}｜這手結算 {sign}{total:,}（假）。" + ("見好就收。" if total > 0 else "還好是假錢。"))
        # 自動辨識視窗與主畫面共用 Tk 事件迴圈；立即送出待處理的
        # 標籤重繪，避免下一次螢幕擷取前看起來仍是舊餘額。
        root = getattr(self, "root", None)
        if root is not None:
            root.update_idletasks()

    def _reset_outcome(self):
        self.v_perfect.set(False)
        self.p_cards = []; self.b_cards = []; self._set_target("player"); self._update_hand()

    def toggle_mode(self):
        self.mode_var.set("nocomm" if self.mode_var.get() == "standard" else "standard"); self.update_mode_btn()

    PLATFORM_ORDER = ("auto", "original", "dreamgaming", "rg")
    PLATFORM_LABELS = {"auto": "自動", "original": "MT",
                       "dreamgaming": "DreamGaming", "rg": "RG"}

    def cycle_platform(self):
        current = self.platform_var.get()
        index = self.PLATFORM_ORDER.index(current) if current in self.PLATFORM_ORDER else 0
        selected = self.PLATFORM_ORDER[(index + 1) % len(self.PLATFORM_ORDER)]
        self.platform_var.set(selected)
        self.detected_platform = None
        self.data["settings"]["platform_mode"] = selected
        save_data(self.data)
        self.update_platform_btn()
        if self.screen_monitor is not None:
            self.screen_monitor.set_platform(selected)
        self.msg.config(text=f"娛樂城辨識模式已切換為 {self.PLATFORM_LABELS[selected]}", fg=TEAL)

    def _on_platform_detected(self, platform):
        self.detected_platform = platform
        self.update_platform_btn()

    def _on_capture_window(self, title):
        selected = str(title or "")
        self.data["settings"]["capture_window_title"] = selected
        save_data(self.data)
        source = selected or "全部螢幕"
        self.msg.config(text=f"擷取來源已切換為：{source}", fg=TEAL)

    def update_platform_btn(self):
        mode = self.platform_var.get()
        if mode == "auto" and self.detected_platform:
            detected = self.PLATFORM_LABELS.get(self.detected_platform, self.detected_platform)
            text = f"自動｜{detected}"
        else:
            text = f"娛樂城：{self.PLATFORM_LABELS.get(mode, '自動')}"
        self.platform_btn.config(text=text)

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
        self.slip = []; self.amt_var.set("0"); self._render_slip()
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
        self.slip = []; self.amt_var.set("0"); self._render_slip()
        self._start_new(self.data["settings"]["start_amount"], self.mode_var.get())
        self.refresh(msg="手動開了新的一局")

    def wipe_all(self):
        self.data = default_data(); save_data(self.data); self.slip = []; self.amt_var.set("0"); self._render_slip()
        self._render_chip_buttons()
        self.start_var.set(str(DEFAULT_START)); self.mode_var.set("standard")
        self.platform_var.set("auto"); self.detected_platform = None
        self.update_mode_btn(); self.update_platform_btn()
        if self.screen_monitor is not None:
            self.screen_monitor.set_platform("auto")
            self.screen_monitor.use_full_desktop()
        self.refresh(msg="全部清除，重新開始。")

    def _total_net(self):
        return sum(h["change"] for s in self.data["sessions"] for h in s["hands"])

    def refresh(self, msg=None):
        sess = self.cur_session(); ledger_bal = session_balance(sess)
        bal = self.available_balance()
        hands = len(sess["hands"])
        wins = sum(1 for h in sess["hands"] if h["change"] > 0)
        net = sum(h["change"] for h in sess["hands"])
        rate = (wins / hands * 100) if hands else 0
        balance_color = AMBER if self.slip else (GOLD if ledger_bal >= sess["start"] else NEG)
        self.bal_lbl.config(text=f"{bal:,}", fg=balance_color)
        self.hands_lbl.config(text=str(hands)); self.rate_lbl.config(text=f"{rate:.0f}%")
        self.net_lbl.config(text=f"{net:+,}", fg=POS if net >= 0 else NEG)
        self.turnover_lbl.config(text=f"{session_turnover(sess):,}")
        total_hands = sum(len(s["hands"]) for s in self.data["sessions"])
        tn = self._total_net(); sess_no = len(self.data["sessions"])
        money = f"總共輸了 {abs(tn):,}" if tn < 0 else (f"總共贏了 {tn:,}" if tn > 0 else "總共打平")
        self.life_lbl.config(text=f"第 {sess_no} 局 ｜ 玩了 {total_hands} 手 ｜ {money} ｜ {self._mode_zh(sess['mode'])}",
                             fg=NEG if tn < 0 else DIM)
        self._render_streak(sess["hands"])
        if self.slip:
            reserved = sum(amount for _, amount in self.slip)
            bets = self._bet_summary(self.slip)
            self.result_lbl.config(text=f"下注中｜{bets}｜已保留 {reserved:,}", fg=AMBER)
        elif sess["hands"]:
            result_text, result_color = self._result_summary(sess["hands"][-1])
            self.result_lbl.config(text=result_text, fg=result_color)
        else:
            self.result_lbl.config(text="等待下注", fg=GOLD)
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
