"""
[為什麼] 使用者想戒賭：保留「參與賭博的刺激」，但完全不下真錢。
         做一個假錢百家樂模擬器——照樣選莊/閒/和、照樣發牌、照樣有輸贏，
         但用真實賠率，讓假錢餘額長期一定往下掉，親眼看清「長期贏不了」。
[怎麼做] 純 Python 實作標準百家樂發牌與補牌規則、真實賠率（莊 0.95、閒 1、和 8）。
         引擎為純函式，GUI 用 tkinter。此檔可獨立跑蒙地卡羅自我驗證賠率。
[結果]   一個零金錢風險的替代品 + 一條往下的餘額曲線，把賭場的數學攤開給你看。
"""

from __future__ import annotations

import random

# ---------- 牌值 ----------

def card_value(rank: int) -> int:
    """A=1，2-9 照數字，10/J/Q/K=0。rank 用 1..13。"""
    return rank if rank <= 9 else 0


def draw_card(rng: random.Random) -> int:
    """回傳 1..13（花色對百家樂點數無影響，省略）。"""
    return rng.randint(1, 13)


def hand_total(cards: list[int]) -> int:
    return sum(card_value(c) for c in cards) % 10


# ---------- 一局發牌（標準補牌規則）----------

def deal_baccarat(rng: random.Random) -> dict:
    """回傳一局結果：玩家/莊家牌、點數、贏家（'player'/'banker'/'tie'）。"""
    p = [draw_card(rng), draw_card(rng)]
    b = [draw_card(rng), draw_card(rng)]

    pt, bt = hand_total(p), hand_total(b)

    # 天生贏家（8 或 9）：雙方都不補
    if pt in (8, 9) or bt in (8, 9):
        return _finish(p, b)

    # 玩家補牌規則
    player_third = None
    if pt <= 5:
        player_third = draw_card(rng)
        p.append(player_third)
    # pt 6 或 7 停牌

    # 莊家補牌規則
    bt = hand_total(b)
    if player_third is None:
        # 玩家沒補：莊家 0-5 補、6-7 停
        if bt <= 5:
            b.append(draw_card(rng))
    else:
        p3 = card_value(player_third)
        draw = False
        if bt <= 2:
            draw = True
        elif bt == 3:
            draw = p3 != 8
        elif bt == 4:
            draw = p3 in (2, 3, 4, 5, 6, 7)
        elif bt == 5:
            draw = p3 in (4, 5, 6, 7)
        elif bt == 6:
            draw = p3 in (6, 7)
        # bt == 7 停牌
        if draw:
            b.append(draw_card(rng))

    return _finish(p, b)


def _finish(p: list[int], b: list[int]) -> dict:
    pt, bt = hand_total(p), hand_total(b)
    if pt > bt:
        winner = "player"
    elif bt > pt:
        winner = "banker"
    else:
        winner = "tie"
    return {"player": p, "banker": b, "player_total": pt, "banker_total": bt, "winner": winner}


# ---------- 賠率結算 ----------

def settle(bet_side: str, amount: float, winner: str) -> float:
    """回傳這局的淨變化（假錢）。
    莊贏賠 0.95（抽 5% 水），閒贏賠 1，和賠 8；押中一方遇和局為和局退還(push)。
    """
    if bet_side == winner:
        if winner == "banker":
            return amount * 0.95
        if winner == "player":
            return amount * 1.0
        if winner == "tie":
            return amount * 8.0
    # 押莊/閒遇到和局 → 退還（不賠不賺）
    if winner == "tie" and bet_side in ("banker", "player"):
        return 0.0
    # 其餘皆輸掉本金
    return -amount


# ---------- 蒙地卡羅自我驗證 ----------

def _monte_carlo(n: int = 500_000) -> None:
    rng = random.Random(42)
    results = {"banker": 0, "player": 0, "tie": 0}
    ev = {"banker": 0.0, "player": 0.0, "tie": 0.0}
    for _ in range(n):
        out = deal_baccarat(rng)
        results[out["winner"]] += 1
        for side in ("banker", "player", "tie"):
            ev[side] += settle(side, 1.0, out["winner"])
    print(f"樣本 {n:,} 局")
    for side in ("banker", "player", "tie"):
        pct = results[side] / n * 100
        print(f"  {side:<7} 出現 {pct:5.2f}%  ｜ 每注1元長期EV = {ev[side]/n:+.4f}")
    print("參考理論值：莊贏 45.86% / 閒贏 44.62% / 和 9.52%")
    print("參考莊家優勢：押莊 -1.06% / 押閒 -1.24% / 押和 -14.4%")


if __name__ == "__main__":
    _monte_carlo()
