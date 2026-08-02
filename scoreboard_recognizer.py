"""辨識直播網站上方藍／紅官方百家樂計分板。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from card_recognizer import _hog, _normalize_glyph


@dataclass(frozen=True)
class ScoreboardResult:
    player: int
    banker: int
    confidence: float
    player_box: tuple[int, int, int, int]
    banker_box: tuple[int, int, int, int]
    finalized: bool = False
    platform: str = "original"


@lru_cache(maxsize=1)
def _digit_templates():
    samples = []
    fonts = (cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX)
    for digit in range(10):
        variants = []
        for font in fonts:
            for scale in (1.2, 1.5, 1.8, 2.1):
                for thickness in (1, 2, 3):
                    canvas = np.zeros((100, 100), np.uint8)
                    text = str(digit)
                    (w, h), _ = cv2.getTextSize(text, font, scale, thickness)
                    cv2.putText(canvas, text, ((100 - w) // 2, (100 + h) // 2), font, scale,
                                255, thickness, cv2.LINE_AA)
                    variants.append(_hog(_normalize_glyph(canvas)))
        samples.append(np.vstack(variants))
    return samples


def _color_boxes(mask: np.ndarray, frame_shape) -> list[tuple[int, int, int, int]]:
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= 100 and 18 <= h <= 110 and w / h >= 1.8 and y < frame_shape[0] * 0.42:
            boxes.append((x, y, w, h))
    return boxes


def _digit_from_bar(frame: np.ndarray, box, side: str):
    x, y, w, h = box
    crop_width = min(80, max(45, round(w * 0.32)))
    crop = frame[y:y + h, x + w - crop_width:x + w] if side == "player" else frame[y:y + h, x:x + crop_width]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, np.array([0, 0, 165]), np.array([179, 125, 255]))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    candidates = []
    for index in range(1, count):
        cx, cy, cw, ch, area = stats[index]
        if ch >= 12 and area >= 25 and cx > 0 and cy > 0 and cx + cw < crop.shape[1] - 1 and cy + ch < crop.shape[0] - 1:
            candidates.append((area, index))
    if not candidates:
        return None
    _, index = max(candidates)
    glyph = np.zeros_like(white); glyph[labels == index] = 255
    return _classify_digit_glyph(glyph)


def _classify_digit_glyph(glyph: np.ndarray, dreamgaming: bool = False):
    feature = _hog(_normalize_glyph(glyph))
    scores = [float((variants @ feature).max()) for variants in _digit_templates()]
    contours, hierarchy = cv2.findContours(glyph, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    holes = sum(1 for item in hierarchy[0] if item[3] >= 0) if hierarchy is not None else 0
    _, _, glyph_w, glyph_h = cv2.boundingRect(glyph)
    # DG 的 1 很窄且沒有內孔；通用 HOG 字型曾把它判成 9。
    # 用實際錄影中的幾何特徵校正，避免直接反轉閒／莊勝負。
    if dreamgaming and holes == 0 and glyph_h and glyph_w / glyph_h <= 0.62:
        scores[1] = max(scores) + 0.12
    # 此網站的 8 與 3 外形接近；兩個內孔可可靠地排除 3。
    if holes >= 2 and int(np.argmax(scores)) == 3 and scores[3] - scores[8] < 0.08:
        scores[8] += 0.12
    digit = int(np.argmax(scores))
    ordered = sorted(scores, reverse=True)
    confidence = min(1.0, max(0.0, scores[digit] + (ordered[0] - ordered[1]) * 0.5))
    return digit, confidence


def _detect_dreamgaming(frame: np.ndarray, red_boxes) -> ScoreboardResult | None:
    """Detect DreamGaming's combined blue/red `PLAYER n VS n BANKER` bar."""
    for x, y, w, h in sorted(red_boxes, key=lambda box: box[2] * box[3], reverse=True):
        if w < 180 or h < 45 or y > frame.shape[0] * 0.25:
            continue
        x0 = max(0, round(x - w * 0.82))
        x1 = min(frame.shape[1], x + w)
        total_width = x1 - x0
        if total_width < 300:
            continue
        crop = frame[y:y + h, x0:x1]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, np.array([0, 0, 165]), np.array([179, 110, 255]))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
        components = []
        for index in range(1, count):
            cx, cy, cw, ch, area = (int(value) for value in stats[index])
            if ch >= 24 and 10 <= cw <= 42 and area >= 100:
                components.append((index, cx, cy, cw, ch, area))
        chosen = []
        for fraction in (0.32, 0.64):
            target = total_width * fraction
            ranked = sorted(components, key=lambda item: abs((item[1] + item[3] / 2) - target))
            if not ranked or abs((ranked[0][1] + ranked[0][3] / 2) - target) > total_width * 0.12:
                chosen = []
                break
            chosen.append(ranked[0])
        if len(chosen) != 2 or chosen[0][0] == chosen[1][0]:
            continue
        digits = []
        for index, *_ in chosen:
            glyph = np.zeros_like(white); glyph[labels == index] = 255
            digits.append(_classify_digit_glyph(glyph, dreamgaming=True))
        player_box = (x0, y, x - x0, h)
        banker_box = (x, y, w, h)
        return ScoreboardResult(digits[0][0], digits[1][0],
                                min(digits[0][1], digits[1][1]),
                                player_box, banker_box, False, "dreamgaming")
    return None


def _detect_rg(frame: np.ndarray, blue_boxes) -> ScoreboardResult | None:
    """Detect RG's compact `PLAYER n VS n BANKER` score panel."""
    for x, y, w, h in sorted(blue_boxes, key=lambda box: box[2] * box[3], reverse=True):
        if not (100 <= w <= 260 and 35 <= h <= 85 and y < frame.shape[0] * 0.2):
            continue
        x1 = min(frame.shape[1], x + round(w * 2.45))
        crop = frame[y:y + h, x:x1]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, np.array([0, 0, 165]), np.array([179, 110, 255]))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
        components = []
        for index in range(1, count):
            cx, cy, cw, ch, area = (int(value) for value in stats[index])
            if ch >= 20 and 8 <= cw <= 38 and area >= 70:
                components.append((index, cx, cy, cw, ch, area))
        chosen = []
        for target in (w * 0.86, w * 1.57):
            ranked = sorted(components, key=lambda item: abs(item[1] + item[3] / 2 - target))
            if not ranked or abs(ranked[0][1] + ranked[0][3] / 2 - target) > w * 0.2:
                chosen = []
                break
            chosen.append(ranked[0])
        if len(chosen) != 2 or chosen[0][0] == chosen[1][0]:
            continue
        digits = []
        for index, *_ in chosen:
            glyph = np.zeros_like(white); glyph[labels == index] = 255
            digits.append(_classify_digit_glyph(glyph))
        finalized = any(80 <= bw <= 250 and 25 <= bh <= 70 and by > y + h
                        and by < frame.shape[0] * 0.45
                        for bx, by, bw, bh in blue_boxes)
        player_box = (x, y, w, h)
        banker_box = (x + w, y, x1 - (x + w), h)
        return ScoreboardResult(digits[0][0], digits[1][0],
                                min(digits[0][1], digits[1][1]),
                                player_box, banker_box, finalized, "rg")
    return None


def detect_scoreboard(frame: np.ndarray, platform: str = "auto") -> ScoreboardResult | None:
    if frame is None or frame.size == 0:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, np.array([85, 90, 75]), np.array([118, 255, 255]))
    red_low = cv2.inRange(hsv, np.array([0, 115, 75]), np.array([12, 255, 255]))
    red_high = cv2.inRange(hsv, np.array([170, 115, 75]), np.array([179, 255, 255]))
    blue_boxes = _color_boxes(blue, frame.shape)
    # 紅色跨 HSV 色相首尾，分開找框可避免合併後黏到大型紅色背景。
    red_boxes = _color_boxes(red_low, frame.shape) + _color_boxes(red_high, frame.shape)
    if platform in ("auto", "original"):
        pairs = []
        for player_box in blue_boxes:
            px, py, pw, ph = player_box
            for banker_box in red_boxes:
                bx, by, bw, bh = banker_box
                vertical_overlap = max(0, min(py + ph, by + bh) - max(py, by))
                gap = abs(bx - (px + pw))
                if vertical_overlap >= min(ph, bh) * 0.45 and gap <= max(45, pw * 0.28) and 0.55 <= bw / pw <= 1.65:
                    score = pw * ph + bw * bh - gap * 40
                    pairs.append((score, player_box, banker_box))
        for _, player_box, banker_box in sorted(pairs, reverse=True):
            player = _digit_from_bar(frame, player_box, "player")
            banker = _digit_from_bar(frame, banker_box, "banker")
            if player and banker:
                return ScoreboardResult(player[0], banker[0], min(player[1], banker[1]),
                                        player_box, banker_box, False, "original")
        if platform == "original":
            return None
    if platform in ("auto", "dreamgaming"):
        result = _detect_dreamgaming(frame, red_boxes)
        if result or platform == "dreamgaming":
            return result
    if platform in ("auto", "rg"):
        return _detect_rg(frame, blue_boxes)
    return None
