"""以 OpenCV 辨識一般樸克牌牌面，不需網路或外部模型。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

RANK_LABELS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
RANK_VALUES = {label: index + 1 for index, label in enumerate(RANK_LABELS)}
CARD_WIDTH, CARD_HEIGHT = 240, 336


@dataclass(frozen=True)
class CardDetection:
    rank: int
    label: str
    confidence: float
    corners: np.ndarray


def _ordered_corners(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype(np.float32)
    sums, diffs = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(sums)], pts[np.argmin(diffs)],
                     pts[np.argmax(sums)], pts[np.argmax(diffs)]], dtype=np.float32)


def _warp_card(frame: np.ndarray, corners: np.ndarray) -> np.ndarray:
    src = _ordered_corners(corners)
    top = np.linalg.norm(src[1] - src[0]); bottom = np.linalg.norm(src[2] - src[3])
    left = np.linalg.norm(src[3] - src[0]); right = np.linalg.norm(src[2] - src[1])
    landscape = (top + bottom) > (left + right)
    width, height = ((CARD_HEIGHT, CARD_WIDTH) if landscape else (CARD_WIDTH, CARD_HEIGHT))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1],
                    [0, height - 1]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(src, dst)
    card = cv2.warpPerspective(frame, transform, (width, height))
    if landscape:
        card = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE)
    return card


def _normalize_glyph(glyph: np.ndarray, shape: tuple[int, int] = (80, 64)) -> np.ndarray:
    out_h, out_w = shape
    ys, xs = np.where(glyph > 0)
    if not len(xs):
        return np.zeros(shape, np.uint8)
    glyph = glyph[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    scale = min((out_w - 10) / glyph.shape[1], (out_h - 10) / glyph.shape[0])
    size = (max(1, round(glyph.shape[1] * scale)), max(1, round(glyph.shape[0] * scale)))
    resized = cv2.resize(glyph, size, interpolation=cv2.INTER_AREA)
    canvas = np.zeros(shape, np.uint8)
    x, y = (out_w - size[0]) // 2, (out_h - size[1]) // 2
    canvas[y:y + size[1], x:x + size[0]] = resized
    return canvas


def _rank_mask(card: np.ndarray) -> np.ndarray | None:
    """取左上角點數（排除下方花色），正規化成白字黑底。"""
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    # 有些直播網站把點數置中而非印在左上角，因此掃描牌面上半部的完整寬度。
    roi = cv2.GaussianBlur(gray[4:190, 3:CARD_WIDTH - 3], (3, 3), 0)
    _, ink = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    components = []
    for idx in range(1, count):
        x, y, w, h, area = stats[idx]
        if area >= 22 and h >= 9 and y < 135 and x > 0 and y > 0:
            components.append((x, y, w, h, idx))
    if not components:
        return None
    top = min(c[1] for c in components)
    selected = [c for c in components if c[1] <= top + 20]
    glyph = np.zeros_like(ink)
    for *_, idx in selected:
        glyph[labels == idx] = 255
    return _normalize_glyph(glyph)


def _hog(mask: np.ndarray) -> np.ndarray:
    small = cv2.resize(mask, (32, 40), interpolation=cv2.INTER_AREA)
    gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    features = []
    for y in range(0, 40, 8):
        for x in range(0, 32, 8):
            hist, _ = np.histogram(angle[y:y + 8, x:x + 8], bins=9, range=(0, 360),
                                   weights=magnitude[y:y + 8, x:x + 8])
            features.extend(hist)
    vector = np.asarray(features, np.float32)
    return vector / (np.linalg.norm(vector) + 1e-6)


@lru_cache(maxsize=1)
def _templates() -> tuple[np.ndarray, list[str]]:
    samples, labels = [], []
    fonts = (cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX)
    for label in RANK_LABELS:
        for font in fonts:
            for thickness in (1, 2, 3):
                for scale in (1.35, 1.55, 1.8):
                    canvas = np.zeros((100, 100), np.uint8)
                    (w, h), _ = cv2.getTextSize(label, font, scale, thickness)
                    cv2.putText(canvas, label, ((100 - w) // 2, (100 + h) // 2), font, scale,
                                255, thickness, cv2.LINE_AA)
                    samples.append(_hog(_normalize_glyph(canvas)))
                    labels.append(label)
    return np.vstack(samples), labels


def _recognize_upright(card: np.ndarray) -> tuple[int, str, float] | None:
    mask = _rank_mask(card)
    if mask is None:
        return None
    feature = _hog(mask)
    templates, labels = _templates()
    similarities = templates @ feature
    scores = {label: float(similarities[[i for i, value in enumerate(labels) if value == label]].max())
              for label in RANK_LABELS}
    best = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    confidence = max(0.0, min(1.0, 0.65 * scores[best] + 1.05 * (scores[best] - ordered[1])))
    if scores[best] < 0.38:
        return None
    return RANK_VALUES[best], best, confidence


def recognize_rank(card: np.ndarray) -> tuple[int, str, float] | None:
    """辨識直牌或旋轉 180 度的牌，取信心較高的方向。"""
    candidates = [_recognize_upright(card), _recognize_upright(cv2.rotate(card, cv2.ROTATE_180))]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return max(candidates, key=lambda item: item[2]) if candidates else None


def detect_cards(frame: np.ndarray, min_area_ratio: float = 0.012) -> list[CardDetection]:
    """找出畫面中的牌，並依牌中心由左至右排序。"""
    if frame is None or frame.size == 0:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    otsu, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    white = cv2.threshold(blur, max(145, int(otsu)), 255, cv2.THRESH_BINARY)[1]
    # 只補小裂縫；較大的核心會把網站上相鄰的兩張牌黏成一個白框。
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum = frame.shape[0] * frame.shape[1] * min_area_ratio
    found = []
    for contour in contours:
        if cv2.contourArea(contour) < minimum:
            continue
        polygon = cv2.approxPolyDP(contour, 0.025 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        short, long = sorted(cv2.minAreaRect(polygon)[1])
        if short < 25 or not 1.18 <= long / short <= 1.75:
            continue
        corners = polygon.reshape(4, 2)
        result = recognize_rank(_warp_card(frame, corners))
        if result:
            rank, label, confidence = result
            found.append(CardDetection(rank, label, confidence, corners))
    found.sort(key=lambda item: float(item.corners[:, 0].mean()))
    return found


def annotate_frame(frame: np.ndarray, cards: list[CardDetection]) -> np.ndarray:
    output = frame.copy()
    for card in cards:
        corners = _ordered_corners(card.corners).astype(np.int32)
        cv2.polylines(output, [corners], True, (55, 220, 120), 3, cv2.LINE_AA)
        x, y = corners[0]
        cv2.putText(output, f"{card.label}  {card.confidence:.0%}", (max(0, x), max(24, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72, (55, 220, 120), 2, cv2.LINE_AA)
    return output
