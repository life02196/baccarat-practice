"""持續擷取螢幕牌桌區域，辨識閒／莊牌面並計算輸贏。"""

from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import os
import time
import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageGrab, ImageTk

from card_recognizer import annotate_frame, detect_cards
from scoreboard_recognizer import detect_scoreboard

BG, PANEL, FG, DIM = "#0b1220", "#131c2b", "#e6edf5", "#8091a5"
PLAYER, BANKER, TIE, GOLD, NEG = "#4aa3ff", "#ff6b6b", "#54c98a", "#e8c268", "#ff5c6c"
CARD_STABLE_FRAMES = 4
SCORE_STABLE_FRAMES = 3
CLEAR_FRAMES = 3


def _total(cards: list[int]) -> int:
    return sum(rank if rank <= 9 else 0 for rank in cards) % 10


def _labels(cards: list[int]) -> str:
    names = {1: "A", 11: "J", 12: "Q", 13: "K"}
    return " ".join(names.get(rank, str(rank)) for rank in cards) if cards else "－"


def _card_value(rank: int) -> int:
    return rank if rank <= 9 else 0


def is_complete_baccarat_hand(player: list[int], banker: list[int]) -> bool:
    """依標準百家樂補牌表判斷目前牌面是否已經發完，避免提早結算。"""
    if len(player) not in (2, 3) or len(banker) not in (2, 3):
        return False
    player_two = sum(_card_value(rank) for rank in player[:2]) % 10
    banker_two = sum(_card_value(rank) for rank in banker[:2]) % 10
    if player_two in (8, 9) or banker_two in (8, 9):
        return len(player) == 2 and len(banker) == 2
    player_draws = player_two <= 5
    if player_draws:
        if len(player) != 3:
            return False
        third = _card_value(player[2])
        banker_draws = (banker_two <= 2 or
                        (banker_two == 3 and third != 8) or
                        (banker_two == 4 and 2 <= third <= 7) or
                        (banker_two == 5 and 4 <= third <= 7) or
                        (banker_two == 6 and 6 <= third <= 7))
    else:
        if len(player) != 2:
            return False
        banker_draws = banker_two <= 5
    return len(banker) == (3 if banker_draws else 2)


class ScreenCardMonitor:
    """先框選兩個牌區，再以週期性螢幕截圖模擬錄影串流。"""

    def __init__(self, parent: tk.Misc, on_apply, config_path: str,
                 platform_mode: str = "auto", on_platform=None):
        self.parent, self.on_apply, self.config_path = parent, on_apply, config_path
        self.platform_mode = platform_mode if platform_mode in (
            "auto", "original", "dreamgaming", "rg") else "auto"
        self.on_platform = on_platform
        self.detected_platform = None
        self.screenshot = ImageGrab.grab(all_screens=True).convert("RGB")
        self.regions: dict[str, tuple[int, int, int, int]] = {}
        self.mode = "player"
        self.drag_start = None
        self.rect_ids: dict[str, int] = {}
        self.running = False
        self.auto_mode = False
        self.job = None
        self.current_player: list[int] = []
        self.current_banker: list[int] = []
        self.last_verified_player: list[int] = []
        self.last_verified_banker: list[int] = []
        self.card_candidate_stats = {"player": {}, "banker": {}}
        self.dg_slot_stats = self._new_dg_slot_stats()
        self.last_dg_boxes = None
        self.last_round_evidence = {}
        self.frame_sequence = 0
        # Do not settle a result that was already visible when the app opened.
        # A between-round blank state arms the next automatic settlement.
        self.round_armed = False
        self.empty_frames = 0
        self.score_absent_frames = 0
        self.last_emitted = None
        self.histories = {"player": deque(maxlen=10), "banker": deque(maxlen=10)}
        self.score_history = deque(maxlen=10)
        self.official_scores = None
        self.score_candidate = None
        self.score_candidate_since = 0.0
        self.last_stable_dg_score = None
        self.last_stable_dg_seen = 0.0
        self.trace_path = os.path.join(os.path.dirname(os.path.abspath(config_path)),
                                       "recognition_debug.log")
        self.last_trace_state = None
        self.preview_visible = True

        self.window = tk.Toplevel(parent)
        self.window.title("百家樂練習程式｜螢幕辨識")
        self.window.configure(bg=BG)
        self.window.attributes("-topmost", True)
        self.window.geometry("1180x780")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        bar = tk.Frame(self.window, bg=PANEL); bar.pack(fill="x")
        self.player_btn = tk.Button(bar, text="1. 框選閒家牌區", command=lambda: self._set_mode("player"),
                                    bg=PLAYER, fg=BG, relief="flat")
        self.player_btn.pack(side="left", padx=(10, 5), pady=7, ipady=3)
        self.banker_btn = tk.Button(bar, text="2. 框選莊家牌區", command=lambda: self._set_mode("banker"),
                                    bg=PANEL, fg=BANKER, relief="flat")
        self.banker_btn.pack(side="left", padx=5, pady=7, ipady=3)
        self.start_btn = tk.Button(bar, text="3. 開始螢幕辨識", command=self.start, state="disabled",
                                   bg=GOLD, fg=BG, relief="flat")
        self.start_btn.pack(side="left", padx=12, pady=7, ipady=3)
        tk.Button(bar, text="重新框選", command=self.reset, bg=PANEL, fg=DIM, relief="flat").pack(
            side="left", padx=5, pady=7, ipady=3)
        self.preview_btn = tk.Button(bar, text="隱藏擷取框", command=self._toggle_preview,
                                     bg=PANEL, fg=TIE, relief="flat")
        self.preview_btn.pack(side="left", padx=5, pady=7, ipady=3)
        self.status = tk.Label(bar, text="在截圖上拖曳框住閒家所有牌會出現的位置", bg=PANEL, fg=GOLD)
        self.status.pack(side="left", padx=12)

        self.canvas = tk.Canvas(self.window, bg="#070b12", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<ButtonPress-1>", self._drag_begin)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        self.bottom = tk.Frame(self.window, bg=PANEL); self.bottom.pack(fill="x")
        self.player_result = tk.Label(self.bottom, text="閒家：尚未設定", bg=PANEL, fg=PLAYER, font=("Segoe UI", 11, "bold"))
        self.player_result.pack(side="left", padx=16, pady=9)
        self.banker_result = tk.Label(self.bottom, text="莊家：尚未設定", bg=PANEL, fg=BANKER, font=("Segoe UI", 11, "bold"))
        self.banker_result.pack(side="left", padx=16, pady=9)
        self.winner_result = tk.Label(self.bottom, text="", bg=PANEL, fg=GOLD, font=("Segoe UI", 12, "bold"))
        self.winner_result.pack(side="left", padx=20, pady=9)
        self.apply_btn = tk.Button(self.bottom, text="手動套用", command=self.apply, state="disabled",
                                   bg=GOLD, fg=BG, relief="flat")
        self.apply_btn.pack(side="right", padx=14, pady=7, ipady=4)

        self.window.update_idletasks()
        self._draw_setup_image()
        self._load_regions()
        # 有既有設定便直接監看；第一次使用則自動搜尋整個桌面。
        # Launch in full-screen automatic discovery even when old manual
        # regions exist; manual regions remain available through setup/reset.
        self.window.after(350, self.start_auto_discovery)

    def _fit(self, image: Image.Image, max_w: int, max_h: int) -> tuple[Image.Image, float]:
        scale = min(max_w / image.width, max_h / image.height, 1.0)
        return image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS), scale

    def _draw_setup_image(self):
        width = max(800, self.canvas.winfo_width() - 4)
        height = max(520, self.canvas.winfo_height() - 4)
        shown, self.scale = self._fit(self.screenshot, width, height)
        self.display_size = shown.size
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, shown.width, shown.height))
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.rect_ids = {}

    def _set_mode(self, mode: str):
        if self.running:
            return
        self.mode = mode
        self.player_btn.config(bg=PLAYER if mode == "player" else PANEL, fg=BG if mode == "player" else PLAYER)
        self.banker_btn.config(bg=BANKER if mode == "banker" else PANEL, fg=BG if mode == "banker" else BANKER)
        name = "閒家" if mode == "player" else "莊家"
        self.status.config(text=f"拖曳框住{name}所有牌會出現的位置", fg=PLAYER if mode == "player" else BANKER)

    def _drag_begin(self, event):
        if self.running:
            return
        self.drag_start = (max(0, event.x), max(0, event.y))
        old = self.rect_ids.get(self.mode)
        if old:
            self.canvas.delete(old)
        color = PLAYER if self.mode == "player" else BANKER
        self.rect_ids[self.mode] = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=color, width=3)

    def _drag_move(self, event):
        if self.drag_start and not self.running:
            self.canvas.coords(self.rect_ids[self.mode], *self.drag_start, event.x, event.y)

    def _drag_end(self, event):
        if not self.drag_start or self.running:
            return
        x0, y0 = self.drag_start; x1, y1 = event.x, event.y
        x0 = min(self.display_size[0], max(0, x0)); x1 = min(self.display_size[0], max(0, x1))
        y0 = min(self.display_size[1], max(0, y0)); y1 = min(self.display_size[1], max(0, y1))
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
        self.drag_start = None
        if x1 - x0 < 80 or y1 - y0 < 80:
            self.status.config(text="框選範圍太小，請重新拖曳", fg=NEG)
            return
        self.regions[self.mode] = tuple(round(value / self.scale) for value in (x0, y0, x1, y1))
        if self.mode == "player":
            self.player_result.config(text="閒家：區域已設定")
            self._set_mode("banker")
        else:
            self.banker_result.config(text="莊家：區域已設定")
        if len(self.regions) == 2:
            self.start_btn.config(state="normal")
            self.status.config(text="兩區設定完成，可開始辨識", fg=GOLD)

    def _save_regions(self):
        width, height = self.screenshot.size
        data = {name: [x0 / width, y0 / height, x1 / width, y1 / height]
                for name, (x0, y0, x1, y1) in self.regions.items()}
        try:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                json.dump({"regions": data}, handle)
        except OSError:
            pass

    def _load_regions(self):
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, encoding="utf-8") as handle:
                data = json.load(handle)["regions"]
            width, height = self.screenshot.size
            for name in ("player", "banker"):
                values = data[name]
                self.regions[name] = tuple(round(v * (width if i % 2 == 0 else height)) for i, v in enumerate(values))
                x0, y0, x1, y1 = self.regions[name]
                color = PLAYER if name == "player" else BANKER
                self.rect_ids[name] = self.canvas.create_rectangle(x0 * self.scale, y0 * self.scale,
                                                                    x1 * self.scale, y1 * self.scale,
                                                                    outline=color, width=3)
            self.player_result.config(text="閒家：已載入上次區域")
            self.banker_result.config(text="莊家：已載入上次區域")
            self.start_btn.config(state="normal")
            self.status.config(text="已載入上次框選，可直接開始或重新框選", fg=GOLD)
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            self.regions = {}

    def reset(self):
        if self.job:
            self.window.after_cancel(self.job); self.job = None
        self.running = False; self.auto_mode = False
        self.window.geometry("1180x780")
        if not self.canvas.winfo_manager():
            self.canvas.pack(fill="both", expand=True, padx=10, pady=10, before=self.bottom)
        self.screenshot = ImageGrab.grab(all_screens=True).convert("RGB")
        self.regions = {}; self.histories = {"player": deque(maxlen=10), "banker": deque(maxlen=10)}
        self.score_history = deque(maxlen=10); self.official_scores = None
        self.last_verified_player = []; self.last_verified_banker = []
        self.card_candidate_stats = {"player": {}, "banker": {}}
        self.dg_slot_stats = self._new_dg_slot_stats()
        self.last_dg_boxes = None
        self.last_round_evidence = {}
        self.frame_sequence = 0
        self.round_armed = False; self.empty_frames = 0; self.score_absent_frames = 0
        self.last_emitted = None; self.last_trace_state = None
        self.score_candidate = None; self.score_candidate_since = 0.0
        self.last_stable_dg_score = None; self.last_stable_dg_seen = 0.0
        self._draw_setup_image(); self._set_mode("player")
        self.player_btn.config(state="normal"); self.banker_btn.config(state="normal")
        self.start_btn.config(state="disabled", text="3. 開始螢幕辨識")
        self.apply_btn.config(state="disabled")
        self.player_result.config(text="閒家：尚未設定"); self.banker_result.config(text="莊家：尚未設定")

    def start(self):
        if len(self.regions) != 2:
            return
        self.running = True; self.auto_mode = False; self._save_regions()
        self.start_btn.config(state="disabled", text="辨識中…")
        self.player_btn.config(state="disabled"); self.banker_btn.config(state="disabled")
        self.status.config(text="正在持續擷取螢幕；開牌完成且結果穩定後即可套用", fg=GOLD)
        self._compact_window()
        self._tick()

    def _compact_window(self):
        """顯示可切換的即時擷取框預覽。"""
        width = 800
        x = max(0, self.window.winfo_screenwidth() - width - 20)
        if self.preview_visible:
            if not self.canvas.winfo_manager():
                self.canvas.pack(fill="both", expand=True, padx=8, pady=6, before=self.bottom)
            self.window.geometry(f"{width}x430+{x}+20")
        else:
            self.canvas.pack_forget()
            self.window.geometry(f"{width}x150+{x}+20")

    def _toggle_preview(self):
        self.preview_visible = not self.preview_visible
        self.preview_btn.config(text="隱藏擷取框" if self.preview_visible else "顯示擷取框")
        if self.running:
            self._compact_window()

    @staticmethod
    def _capture_coordinate_scale(frame_width: int, frame_height: int,
                                  screen_width: int, screen_height: int) -> float:
        """取得 Tk 視窗座標至全螢幕擷取像素的比例，兼容延伸雙螢幕。"""
        if screen_width <= 0 or screen_height <= 0:
            return 1.0
        # 若另一台螢幕向右或向下延伸，只有單一軸的擷取尺寸會變大；
        # 取較小比例可保留真正的 DPI 縮放，避免把延伸桌面誤當縮放率。
        return max(0.5, min(3.0, min(frame_width / screen_width,
                                     frame_height / screen_height)))

    def _mask_own_window(self, frame: np.ndarray):
        """不讓即時預覽中的牌與分數被下一次螢幕擷取重複辨識。"""
        try:
            self.window.update_idletasks()
            screen_w = max(1, self.window.winfo_screenwidth())
            screen_h = max(1, self.window.winfo_screenheight())
            scale = self._capture_coordinate_scale(frame.shape[1], frame.shape[0],
                                                   screen_w, screen_h)
            x0 = max(0, round(self.window.winfo_rootx() * scale))
            y0 = max(0, round(self.window.winfo_rooty() * scale))
            x1 = min(frame.shape[1], round((self.window.winfo_rootx() + self.window.winfo_width()) * scale))
            y1 = min(frame.shape[0], round((self.window.winfo_rooty() + self.window.winfo_height()) * scale))
            if x1 > x0 and y1 > y0:
                frame[y0:y1, x0:x1] = (8, 12, 18)
        except tk.TclError:
            pass

    def start_auto_discovery(self):
        """不需框選，直接掃描完整桌面並依空間位置分成兩手牌。"""
        if self.running:
            return
        self.running = True; self.auto_mode = True
        self.start_btn.config(state="disabled", text="自動搜尋中…")
        self.player_btn.config(state="disabled"); self.banker_btn.config(state="disabled")
        self.status.config(text="正在自動搜尋目前桌面上的牌；若分組不符可按「重新框選」", fg=GOLD)
        self._compact_window()
        self._tick_auto()

    def set_platform(self, platform_mode: str):
        if platform_mode not in ("auto", "original", "dreamgaming", "rg"):
            return
        self.platform_mode = platform_mode
        self.detected_platform = None
        self.histories = {"player": deque(maxlen=10), "banker": deque(maxlen=10)}
        self.score_history = deque(maxlen=10)
        self.current_player = []; self.current_banker = []
        self.last_verified_player = []; self.last_verified_banker = []
        self.card_candidate_stats = {"player": {}, "banker": {}}
        self.dg_slot_stats = self._new_dg_slot_stats()
        self.last_dg_boxes = None
        self.last_round_evidence = {}
        self.frame_sequence = 0
        self.official_scores = None
        self.score_candidate = None; self.score_candidate_since = 0.0
        self.last_stable_dg_score = None; self.last_stable_dg_seen = 0.0
        self.round_armed = False; self.empty_frames = 0
        self.last_emitted = None; self.last_trace_state = None
        if self.on_platform:
            self.on_platform(None)
        self._trace(f"platform mode changed to {platform_mode}")

    @staticmethod
    def _split_hands(cards) -> tuple[list[int], list[int]]:
        """依牌中心最大的水平／垂直間隔，將 4～6 張牌分成兩組。"""
        if not 4 <= len(cards) <= 8:
            return [], []
        # 畫面有額外誤判時，先保留信心最高的六張。
        selected = sorted(cards, key=lambda card: card.confidence, reverse=True)[:6]
        # MT, DG and RG all place Player on the left and Banker on the right.
        # Considering the vertical axis here is unsafe: once third cards appear
        # below the first row, the two rows can look more separated than the two
        # hands and pairs/counts are then attributed to the wrong side.
        best = None
        ordered = sorted(selected, key=lambda card: float(card.corners[:, 0].mean()))
        centers = [float(card.corners[:, 0].mean()) for card in ordered]
        for cut in range(2, len(ordered) - 1):
            if not (2 <= cut <= 3 and 2 <= len(ordered) - cut <= 3):
                continue
            gap = centers[cut] - centers[cut - 1]
            left_spread = max(1.0, centers[cut - 1] - centers[0])
            right_spread = max(1.0, centers[-1] - centers[cut])
            score = gap / (left_spread + right_spread)
            if best is None or score > best[0]:
                best = (score, ordered[:cut], ordered[cut:])
        if best is None or best[0] < 0.28:
            return [], []
        _, first, second = best
        # 一般百家樂畫面為閒家在左（或上）、莊家在右（或下）。
        return ScreenCardMonitor._order_hand(first), ScreenCardMonitor._order_hand(second)

    @staticmethod
    def _select_table_cards(cards):
        """從全畫面白框中選出尺寸一致、彼此鄰近且信心最高的 4～6 張直播牌。"""
        # Different casinos use different face-card fonts. Keep moderately
        # confident cards here; spatial grouping still filters UI false hits.
        # DG 的細字型 8 在真實錄影中約為 0.40；交由尺寸與空間群組
        # 排除 UI 雜訊，避免少一張牌使整手邊注證據消失。
        # DG's thin red 10 glyph regularly scores around 0.36.  It is still a
        # reliable card when it is part of a four-to-six-card table component;
        # the spatial/size checks below reject isolated low-confidence UI hits.
        usable = [card for card in cards if card.confidence >= 0.35]
        components = []
        seen_signatures = set()
        for seed in usable:
            seed_area = max(1.0, float(cv2.contourArea(seed.corners.astype(np.float32))))
            same_size = []
            for card in usable:
                area = max(1.0, float(cv2.contourArea(card.corners.astype(np.float32))))
                if 0.55 <= area / seed_area <= 1.8:
                    same_size.append(card)
            # 以三張牌長邊為鄰近界線建立連通群組。
            remaining = set(range(len(same_size)))
            while remaining:
                group_indices = {remaining.pop()}
                changed = True
                while changed:
                    changed = False
                    for index in list(remaining):
                        center = same_size[index].corners.mean(axis=0)
                        for member in group_indices:
                            other = same_size[member]
                            other_center = other.corners.mean(axis=0)
                            span = max(np.ptp(other.corners[:, 0]), np.ptp(other.corners[:, 1]),
                                       np.ptp(same_size[index].corners[:, 0]), np.ptp(same_size[index].corners[:, 1]))
                            if np.linalg.norm(center - other_center) <= span * 3.0:
                                group_indices.add(index); remaining.remove(index); changed = True; break
                group = [same_size[index] for index in group_indices]
                signature = tuple(sorted((round(float(card.corners[:, 0].mean())),
                                          round(float(card.corners[:, 1].mean()))) for card in group))
                if 4 <= len(group) <= 6 and signature not in seen_signatures:
                    seen_signatures.add(signature); components.append(group)
        if not components:
            return []
        def score(group):
            areas = [max(1.0, float(cv2.contourArea(card.corners.astype(np.float32)))) for card in group]
            return float(np.mean([card.confidence for card in group])) + 0.035 * np.log(float(np.mean(areas)))
        return max(components, key=score)

    @staticmethod
    def _order_hand(cards) -> list[int]:
        """兩張主牌在前；與主牌列分離的第三張排最後，供對子規則正確判斷。"""
        if len(cards) != 3:
            ordered = sorted(cards, key=lambda card: float(card.corners[:, 0].mean()))
            return [card.rank for card in ordered]
        centers = [card.corners.mean(axis=0) for card in cards]
        pairs = [(float(np.linalg.norm(centers[i] - centers[j])), i, j)
                 for i in range(3) for j in range(i + 1, 3)]
        _, first, second = min(pairs)
        main = sorted((cards[first], cards[second]), key=lambda card: float(card.corners[:, 0].mean()))
        third = next(cards[index] for index in range(3) if index not in (first, second))
        return [main[0].rank, main[1].rank, third.rank]

    def _remember_card_candidate(self, side: str, cards: list[int]):
        if len(cards) not in (2, 3):
            return
        key = tuple(cards)
        count, _last = self.card_candidate_stats[side].get(key, (0, 0))
        self.card_candidate_stats[side][key] = (count + 1, self.frame_sequence)

    @staticmethod
    def _new_dg_slot_stats():
        return {side: {0: {}, 1: {}, 2: {}} for side in ("player", "banker")}

    @staticmethod
    def _accumulate_dg_slots(stats, cards, boxes, frame_sequence: int):
        """Accumulate DG cards by their fixed Player/Banker table slots.

        This recovers a card that is visible in only one early frame instead of
        requiring all four cards to be recognized simultaneously.
        """
        if not boxes:
            return
        for side, box in zip(("player", "banker"), boxes):
            x, y, width, height = (float(value) for value in box)
            best_this_frame = {}
            for card in cards:
                if card.confidence < 0.25:
                    continue
                center_x, center_y = (float(value) for value in card.corners.mean(axis=0))
                if not (x <= center_x <= x + width and
                        y + height <= center_y <= y + height * 4.7):
                    continue
                slot = 2 if center_y > y + height * 3.0 else (0 if center_x < x + width / 2 else 1)
                previous = best_this_frame.get(slot)
                if previous is None or card.confidence > previous.confidence:
                    best_this_frame[slot] = card
            for slot, card in best_this_frame.items():
                count, confidence_sum, _last = stats[side][slot].get(card.rank, (0, 0.0, 0))
                stats[side][slot][card.rank] = (
                    count + 1, confidence_sum + float(card.confidence), frame_sequence)

    @staticmethod
    def _dg_slot_evidence(stats, official_score: tuple[int, int]):
        evidence = {}

        def best(side, slot):
            values = stats.get(side, {}).get(slot, {})
            if not values:
                return None
            rank, (count, confidence_sum, last_seen) = max(
                values.items(), key=lambda item: (item[1][0], item[1][1], item[1][2]))
            return rank, count, confidence_sum, last_seen

        for side, prefix, score in (("player", "p", official_score[0]),
                                    ("banker", "b", official_score[1])):
            first, second, third = best(side, 0), best(side, 1), best(side, 2)
            if third and third[1] >= 2:
                evidence[f"{prefix}c"] = 3
            elif first and second and third is None:
                evidence[f"{prefix}c"] = 2
            if first and second:
                if first[0] == second[0] and min(first[1], second[1]) >= 2:
                    evidence[f"{prefix}pair"] = True
                elif first[0] != second[0] and min(first[1], second[1]) >= 2:
                    evidence[f"{prefix}pair"] = False
            # A two-card pair always totals an even number in baccarat.  This
            # safely resolves a low-confidence one-frame slot on odd totals.
            if evidence.get(f"{prefix}c") == 2 and score % 2 == 1:
                evidence[f"{prefix}pair"] = False
        # A two-card 8/9 is a natural: dealing stops immediately for both
        # sides.  Use that rule to recover the other side's missing first slot.
        if evidence.get("pc") == 2 and official_score[0] in (8, 9):
            evidence.setdefault("bc", 2)
        if evidence.get("bc") == 2 and official_score[1] in (8, 9):
            evidence.setdefault("pc", 2)
        if evidence.get("pc") == 2 and official_score[0] % 2 == 1:
            evidence.setdefault("ppair", False)
        if evidence.get("bc") == 2 and official_score[1] % 2 == 1:
            evidence.setdefault("bpair", False)
        return evidence

    @staticmethod
    def _best_verified_hands(stats, official_score: tuple[int, int]):
        """從整局候選牌面選出符合官方點數及補牌規則的最高可信組合。"""
        player_candidates = []
        banker_candidates = []
        for cards, (count, last_seen) in stats.get("player", {}).items():
            if len(cards) in (2, 3) and _total(list(cards)) == official_score[0]:
                player_candidates.append((list(cards), count, last_seen))
        for cards, (count, last_seen) in stats.get("banker", {}).items():
            if len(cards) in (2, 3) and _total(list(cards)) == official_score[1]:
                banker_candidates.append((list(cards), count, last_seen))
        best = None
        for player, player_count, player_seen in player_candidates:
            for banker, banker_count, banker_seen in banker_candidates:
                if not is_complete_baccarat_hand(player, banker):
                    continue
                # 出現次數優先，其次選較接近收牌時看到的組合。
                score = (player_count + banker_count, player_seen + banker_seen)
                if best is None or score > best[0]:
                    best = (score, player, banker)
        return (best[1], best[2]) if best else ([], [])

    @staticmethod
    def _round_feature_evidence(stats):
        """從多幀候選獨立推定對子與張數，不要求牌點 OCR 全部正確。"""
        evidence = {}
        for side, prefix in (("player", "p"), ("banker", "b")):
            candidates = stats.get(side, {})
            true_best = max((count for cards, (count, _seen) in candidates.items()
                             if len(cards) >= 2 and cards[0] == cards[1]), default=0)
            false_best = max((count for cards, (count, _seen) in candidates.items()
                              if len(cards) >= 2 and cards[0] != cards[1]), default=0)
            if true_best >= 2 and true_best >= false_best:
                evidence[f"{prefix}pair"] = True
            elif false_best >= 3 and false_best > true_best:
                evidence[f"{prefix}pair"] = False
            three_best = max((count for cards, (count, _seen) in candidates.items()
                              if len(cards) == 3), default=0)
            two_best = max((count for cards, (count, _seen) in candidates.items()
                            if len(cards) == 2), default=0)
            if three_best >= 2:
                evidence[f"{prefix}c"] = 3
            elif two_best >= 3 and three_best == 0:
                evidence[f"{prefix}c"] = 2
        return evidence

    @staticmethod
    def _stable(history, required: int = CARD_STABLE_FRAMES) -> list[int]:
        """只接受最新連續多幀完全相同，不讓發牌動畫早期結果靠多數決殘留。"""
        if len(history) < required:
            return []
        recent = list(history)[-required:]
        value = recent[-1]
        return list(value) if all(item == value for item in recent) and 2 <= len(value) <= 3 else []

    @staticmethod
    def _consecutive_count(history) -> int:
        if not history:
            return 0
        latest = history[-1]
        count = 0
        for item in reversed(history):
            if item != latest:
                break
            count += 1
        return count

    @staticmethod
    def _valid_official_score(score: tuple[int, int], has_cards: bool) -> bool:
        """Reject the pre-deal 0:0 placeholder without losing real 0:0 ties."""
        return score != (0, 0) or has_cards

    @staticmethod
    def _official_result_ready(score: tuple[int, int], player: list[int],
                               banker: list[int], raw_cards_seen: bool,
                               score_age: float, finalized: bool = False,
                               platform: str = "original") -> bool:
        """Only accept a final score, never a stable intermediate deal score."""
        if finalized:
            return score != (0, 0) or raw_cards_seen
        # DG 只在牌與比分都收走後，使用最後穩定官方比分結算。
        # 不在牌仍顯示時結算，避免同一局被再次暫存或誤用中途比分。
        if platform == "dreamgaming":
            return False
        if player and banker and is_complete_baccarat_hand(player, banker):
            return (_total(player), _total(banker)) == score
        # If cards are visible but the hand is incomplete, the current score is
        # an intermediate value. When card detection completely fails, a long
        # unchanged non-zero score is the conservative fallback.
        if raw_cards_seen:
            return False
        return score != (0, 0) and score_age >= 8.0

    @staticmethod
    def _dreamgaming_collected_result(platform: str, score_visible: bool,
                                      cards_visible: bool, absent_frames: int,
                                      last_score, last_score_age: float):
        """DG 收牌後，以剛消失的最後穩定官方比分作為最終結果。"""
        if (platform == "dreamgaming" and not score_visible and not cards_visible and
                absent_frames >= 2 and last_score and last_score_age <= 8.0):
            return tuple(last_score)
        return None

    def _tick(self):
        if not self.running or not self.window.winfo_exists():
            return
        screen = ImageGrab.grab(all_screens=True).convert("RGB")
        previews = []
        for name in ("player", "banker"):
            crop = screen.crop(self.regions[name])
            frame = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)
            cards = detect_cards(frame, min_area_ratio=0.018)
            ranks = tuple(card.rank for card in cards[:3])
            self.histories[name].append(ranks)
            stable = self._stable(self.histories[name])
            if stable:
                if name == "player": self.current_player = stable
                else: self.current_banker = stable
            elif ranks and ((name == "player" and ranks != tuple(self.current_player)) or
                            (name == "banker" and ranks != tuple(self.current_banker))):
                if name == "player": self.current_player = []
                else: self.current_banker = []
            previews.append(annotate_frame(frame, cards))
        if not any(self.histories[name][-1] for name in ("player", "banker")):
            self._mark_empty_frame()
        else:
            self.empty_frames = 0
        self._render_live(previews)
        if self.current_player and self.current_banker and not is_complete_baccarat_hand(
                self.current_player, self.current_banker):
            self.current_player = []; self.current_banker = []
        self._render_result()
        self._auto_emit_if_ready()
        self.job = self.window.after(180, self._tick)

    def _tick_auto(self):
        if not self.running or not self.auto_mode or not self.window.winfo_exists():
            return
        screen = ImageGrab.grab(all_screens=True).convert("RGB")
        frame = cv2.cvtColor(np.asarray(screen), cv2.COLOR_RGB2BGR)
        self._mask_own_window(frame)
        scoreboard = detect_scoreboard(frame, self.platform_mode)
        if scoreboard and scoreboard.platform != self.detected_platform:
            self.detected_platform = scoreboard.platform
            if self.on_platform:
                self.on_platform(self.detected_platform)
        score_pair = (scoreboard.player, scoreboard.banker) if scoreboard else ()
        platform = scoreboard.platform if scoreboard else (self.detected_platform or self.platform_mode)
        score_finalized = bool(scoreboard and scoreboard.finalized)
        if score_pair != self.score_candidate:
            self.score_candidate = score_pair
            self.score_candidate_since = time.monotonic()
        score_age = time.monotonic() - self.score_candidate_since if score_pair else 0.0
        self.score_history.append(score_pair)
        stable_score = self._stable(self.score_history, required=SCORE_STABLE_FRAMES)
        all_cards = detect_cards(frame, min_area_ratio=0.00015)
        if scoreboard and scoreboard.platform == "dreamgaming":
            self.last_dg_boxes = (scoreboard.player_box, scoreboard.banker_box)
        if platform == "dreamgaming" and self.last_dg_boxes:
            self._accumulate_dg_slots(
                self.dg_slot_stats, all_cards, self.last_dg_boxes, self.frame_sequence)
        cards = self._select_table_cards(all_cards)
        player, banker = self._split_hands(cards)
        self.frame_sequence += 1
        self._remember_card_candidate("player", player)
        self._remember_card_candidate("banker", banker)
        if not player and not banker and not score_pair:
            self._mark_empty_frame()
        else:
            self.empty_frames = 0
        self.histories["player"].append(tuple(player))
        self.histories["banker"].append(tuple(banker))
        stable_player = self._stable(self.histories["player"])
        stable_banker = self._stable(self.histories["banker"])
        if stable_player: self.current_player = stable_player
        elif tuple(player) != tuple(self.current_player): self.current_player = []
        if stable_banker: self.current_banker = stable_banker
        elif tuple(banker) != tuple(self.current_banker): self.current_banker = []
        complete = is_complete_baccarat_hand(self.current_player, self.current_banker)
        if (complete and score_pair and
                (_total(self.current_player), _total(self.current_banker)) == tuple(score_pair)):
            self.last_verified_player = list(self.current_player)
            self.last_verified_banker = list(self.current_banker)
        now = time.monotonic()
        if platform == "dreamgaming" and self.round_armed and stable_score:
            candidate = tuple(stable_score)
            # DG 在發牌前固定顯示 0:0；只有完整牌面也確認為 0:0 時才暫存。
            zero_is_real = (candidate == (0, 0) and complete and
                            (_total(self.current_player), _total(self.current_banker)) == candidate)
            if candidate != (0, 0) or zero_is_real:
                self.last_stable_dg_score = candidate
                self.last_stable_dg_seen = now
        if score_pair:
            self.score_absent_frames = 0
        else:
            self.score_absent_frames += 1
        # DG 的畫面沒有可靠的「final」標記。收牌時牌與比分會一起消失，
        # 因此以最後穩定比分結算，避免把停留較久的中途比分提早當結果。
        dg_collected_score = self._dreamgaming_collected_result(
            platform, bool(score_pair), bool(player or banker), self.score_absent_frames,
            self.last_stable_dg_score,
            now - self.last_stable_dg_seen if self.last_stable_dg_score else float("inf"))
        if stable_score and self._official_result_ready(
                tuple(stable_score), self.current_player, self.current_banker,
                bool(player or banker), score_age, score_finalized,
                platform):
            self.official_scores = tuple(stable_score)
        elif dg_collected_score:
            self.official_scores = tuple(dg_collected_score)
            self.last_round_evidence = self._round_feature_evidence(self.card_candidate_stats)
            for key, value in self._dg_slot_evidence(
                    self.dg_slot_stats, self.official_scores).items():
                self.last_round_evidence.setdefault(key, value)
            verified_player, verified_banker = self._best_verified_hands(
                self.card_candidate_stats, self.official_scores)
            if verified_player and verified_banker:
                self.last_verified_player = verified_player
                self.last_verified_banker = verified_banker
                self.last_round_evidence.update({
                    "pc": len(verified_player), "bc": len(verified_banker),
                    "ppair": verified_player[0] == verified_player[1],
                    "bpair": verified_banker[0] == verified_banker[1],
                })
                self._trace(f"DG verified final cards={verified_player}/{verified_banker}")
            self._trace(f"DG round evidence={self.last_round_evidence}")
            self._trace(f"DG cards collected; promoting last stable score={dg_collected_score}")
        elif score_pair:
            self.official_scores = None
        else:
            if self.score_absent_frames >= CLEAR_FRAMES:
                self.official_scores = None
        trace_state = (score_pair, tuple(player), tuple(banker), self.official_scores,
                       self.round_armed, platform, score_finalized)
        if trace_state != self.last_trace_state:
            self.last_trace_state = trace_state
            self._trace(f"frame score={score_pair or '-'} cards={player}/{banker} "
                        f"stable={self.current_player}/{self.current_banker} "
                        f"official={self.official_scores or '-'} armed={self.round_armed} "
                        f"platform={platform} final={score_finalized} age={score_age:.1f}")
        self._render_auto_preview(frame, all_cards, cards, scoreboard)
        self._render_result()
        self._auto_emit_if_ready()
        if not player or not banker:
            self.status.config(text=f"全螢幕搜尋中：目前找到 {len(cards)} 張牌；需要兩組各 2～3 張", fg=GOLD)
        else:
            progress = min(self._consecutive_count(self.histories["player"]),
                           self._consecutive_count(self.histories["banker"]), CARD_STABLE_FRAMES)
            phase = "牌面完成" if is_complete_baccarat_hand(player, banker) else "依補牌規則等待下一張"
            official = (f"｜官方 {self.official_scores[0]}:{self.official_scores[1]}"
                        if self.official_scores else "｜等待官方分數")
            self.status.config(text=f"牌面：閒 {_labels(player)}／莊 {_labels(banker)}　{phase}　{progress}/8 {official}", fg=TIE)
        self.job = self.window.after(320, self._tick_auto)

    def _render_auto_preview(self, frame: np.ndarray, all_cards, selected_cards, scoreboard):
        """在小視窗顯示實際擷取範圍與本幀辨識結果。"""
        if not self.preview_visible or not self.canvas.winfo_manager():
            return
        annotated = frame.copy()
        selected_ids = {id(card) for card in selected_cards}
        focus_points = []
        for card in all_cards:
            points = np.asarray(card.corners, dtype=np.int32)
            selected = id(card) in selected_ids
            color = (80, 220, 120) if selected else (0, 190, 255)
            cv2.polylines(annotated, [points], True, color, 3 if selected else 1)
            x, y = points[:, 0].min(), points[:, 1].min()
            cv2.putText(annotated, f"{card.label} {card.confidence:.2f}",
                        (int(x), max(18, int(y) - 7)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, color, 2, cv2.LINE_AA)
            if selected:
                focus_points.extend(points.tolist())
        if scoreboard:
            for box, color, label in (
                    (scoreboard.player_box, (255, 150, 50), f"PLAYER {scoreboard.player}"),
                    (scoreboard.banker_box, (70, 80, 255), f"BANKER {scoreboard.banker}")):
                x, y, w, h = box
                cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 3)
                cv2.putText(annotated, label, (x, max(18, y - 7)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
                focus_points.extend(((x, y), (x + w, y + h)))
        if not focus_points:
            fallback = sorted(all_cards, key=lambda card: card.confidence, reverse=True)[:6]
            for card in fallback:
                focus_points.extend(np.asarray(card.corners, dtype=np.int32).tolist())
        if focus_points:
            points = np.asarray(focus_points)
            pad_x = max(80, round(frame.shape[1] * 0.04))
            pad_y = max(55, round(frame.shape[0] * 0.05))
            x0 = max(0, int(points[:, 0].min()) - pad_x)
            y0 = max(0, int(points[:, 1].min()) - pad_y)
            x1 = min(frame.shape[1], int(points[:, 0].max()) + pad_x)
            y1 = min(frame.shape[0], int(points[:, 1].max()) + pad_y)
            shown_frame = annotated[y0:y1, x0:x1]
        else:
            shown_frame = annotated
        image = Image.fromarray(cv2.cvtColor(shown_frame, cv2.COLOR_BGR2RGB))
        width = max(760, self.canvas.winfo_width() - 4)
        height = max(235, self.canvas.winfo_height() - 4)
        shown, _ = self._fit(image, width, height)
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

    def _render_live(self, frames: list[np.ndarray]):
        images = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) for frame in frames]
        target_h = max(image.height for image in images)
        resized = [image.resize((round(image.width * target_h / image.height), target_h)) for image in images]
        combined = Image.new("RGB", (sum(image.width for image in resized) + 8, target_h), "#070b12")
        x = 0
        for image in resized:
            combined.paste(image, (x, 0)); x += image.width + 8
        shown, _ = self._fit(combined, max(800, self.canvas.winfo_width() - 4), max(500, self.canvas.winfo_height() - 4))
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all"); self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

    def _render_result(self):
        p, b = self.current_player, self.current_banker
        emitted_official = (self.last_emitted[1] if isinstance(self.last_emitted, tuple) and
                            len(self.last_emitted) == 2 and self.last_emitted[0] == "official"
                            else None)
        display_official = self.official_scores or emitted_official
        if display_official:
            pt, bt = display_official
            self.player_result.config(text=f"閒家：官方 {pt} 點")
            self.banker_result.config(text=f"莊家：官方 {bt} 點")
            winner, color = (("閒贏", PLAYER) if pt > bt else ("莊贏", BANKER) if bt > pt else ("和局", TIE))
            settled = not self.round_armed and self.last_emitted is not None
            suffix = "｜已自動結算" if settled else ""
            self.winner_result.config(text=f"官方判定：{winner}{suffix}", fg=TIE if settled else color)
            self.apply_btn.config(state="disabled")
        elif p and b:
            self.player_result.config(text=f"閒家：{_labels(p)} = {_total(p)} 點")
            self.banker_result.config(text=f"莊家：{_labels(b)} = {_total(b)} 點")
            pt, bt = _total(p), _total(b)
            winner, color = (("閒贏", PLAYER) if pt > bt else ("莊贏", BANKER) if bt > pt else ("和局", TIE))
            settled = not self.round_armed and self.last_emitted is not None
            suffix = "｜已自動結算" if settled else ""
            platform = self.detected_platform or self.platform_mode
            prefix = "牌面暫估" if platform == "dreamgaming" else "判定"
            self.winner_result.config(text=f"{prefix}：{winner}{suffix}", fg=TIE if settled else color)
            self.apply_btn.config(state="normal")
        else:
            self.player_result.config(text="閒家：等待穩定牌面")
            self.banker_result.config(text="莊家：等待穩定牌面")
            self.winner_result.config(text="等待新牌穩定", fg=GOLD)
            self.apply_btn.config(state="disabled")

    def _mark_empty_frame(self):
        self.empty_frames += 1
        if self.empty_frames >= CLEAR_FRAMES:
            if self.empty_frames == CLEAR_FRAMES:
                self._trace("round armed after blank transition")
                # 只有真正從已結算狀態進入下一局時才清除簽章；若本局
                # 結算被拒絕，不可每幀重送同一結果。
                if not self.round_armed:
                    self.last_emitted = None
                    self.last_verified_player = []
                    self.last_verified_banker = []
                    self.card_candidate_stats = {"player": {}, "banker": {}}
                    self.dg_slot_stats = self._new_dg_slot_stats()
                    self.last_round_evidence = {}
                self.round_armed = True
            self.current_player = []
            self.current_banker = []

    def _auto_emit_if_ready(self):
        if not self.round_armed:
            return

        # Main bets can settle from the site's official score even if card-rank
        # recognition flickers. The callback still rejects edge bets unless the
        # complete recognized cards agree with that official score.
        if self.official_scores:
            signature = ("official", self.official_scores)
        elif ((getattr(self, "detected_platform", None) or
               getattr(self, "platform_mode", "original")) == "dreamgaming"):
            # DG 沒有官方最終標記，牌面辨識即使看似完整也不能單獨派彩。
            return
        elif self.current_player and self.current_banker and is_complete_baccarat_hand(
                self.current_player, self.current_banker):
            signature = (tuple(self.current_player), tuple(self.current_banker), None)
        else:
            return
        if signature == self.last_emitted:
            return
        self.last_emitted = signature
        player = list(self.current_player or getattr(self, "last_verified_player", []))
        banker = list(self.current_banker or getattr(self, "last_verified_banker", []))
        self._trace(f"settlement attempt cards={player}/{banker} official={self.official_scores}")
        accepted = self.on_apply(player, banker, self.official_scores,
                                 dict(getattr(self, "last_round_evidence", {})))
        self._trace(f"settlement callback accepted={accepted}")
        if accepted is not False:
            self.round_armed = False
            self.last_stable_dg_score = None
            self.last_stable_dg_seen = 0.0
            self.last_verified_player = []
            self.last_verified_banker = []
            self.card_candidate_stats = {"player": {}, "banker": {}}
            self.dg_slot_stats = self._new_dg_slot_stats()
            self.last_round_evidence = {}
        elif self.official_scores:
            # 已經對本局作出一次安全拒絕；丟棄舊證據，避免污染下一局。
            self.last_stable_dg_score = None
            self.last_stable_dg_seen = 0.0
            self.last_verified_player = []
            self.last_verified_banker = []
            self.card_candidate_stats = {"player": {}, "banker": {}}
            self.dg_slot_stats = self._new_dg_slot_stats()
            self.last_round_evidence = {}
            current = self.winner_result.cget("text").replace("｜證據不足未結算", "")
            self.winner_result.config(text=current + "｜證據不足未結算", fg=BANKER)

    def _trace(self, message: str):
        path = getattr(self, "trace_path", None)
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as handle:
                timestamp = datetime.now().isoformat(timespec="milliseconds")
                handle.write(f"{timestamp} {message}\n")
        except OSError:
            pass

    def apply(self):
        if self.current_player and self.current_banker:
            self.on_apply(self.current_player, self.current_banker, self.official_scores)
            self.round_armed = False
            self.last_emitted = (tuple(self.current_player), tuple(self.current_banker))

    def close(self):
        self.running = False
        if self.job:
            try: self.window.after_cancel(self.job)
            except tk.TclError: pass
        if self.window.winfo_exists(): self.window.destroy()
