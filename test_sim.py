"""
[為什麼] 讓接手者確認發牌規則與賠率沒被改壞。
[怎麼做] 跑一批模擬，檢查莊/閒/和出現比例與莊家優勢落在合理範圍。python test_sim.py
[結果]   全部 [PASS] 且結尾 0 failure(s) 即通過。
"""

import random

import baccarat_sim as eng


def test_deal_valid():
    rng = random.Random(1)
    for _ in range(2000):
        out = eng.deal_baccarat(rng)
        assert 0 <= out["player_total"] <= 9
        assert 0 <= out["banker_total"] <= 9
        assert 2 <= len(out["player"]) <= 3
        assert 2 <= len(out["banker"]) <= 3
        assert out["winner"] in ("player", "banker", "tie")


def test_probabilities_converge():
    rng = random.Random(42)
    n = 60000
    c = {"player": 0, "banker": 0, "tie": 0}
    for _ in range(n):
        c[eng.deal_baccarat(rng)["winner"]] += 1
    banker = c["banker"] / n
    player = c["player"] / n
    tie = c["tie"] / n
    # 理論：莊 45.86% / 閒 44.62% / 和 9.52%，給合理容差
    assert 0.44 < banker < 0.475, banker
    assert 0.43 < player < 0.46, player
    assert 0.085 < tie < 0.105, tie


def test_house_edge_negative():
    rng = random.Random(7)
    n = 60000
    ev_b = ev_p = 0.0
    for _ in range(n):
        w = eng.deal_baccarat(rng)["winner"]
        ev_b += eng.settle("banker", 1.0, w)
        ev_p += eng.settle("player", 1.0, w)
    # 押莊/押閒長期都應為負（莊家優勢）
    assert ev_b / n < 0, ev_b / n
    assert ev_p / n < 0, ev_p / n


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as e:
            failures += 1
            print(f"[FAIL] {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{failures} failure(s)")
    raise SystemExit(1 if failures else 0)
