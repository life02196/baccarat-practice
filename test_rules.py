"""
[為什麼] 讓接手者改完賠率/玩法後，能一鍵驗證沒改壞。涵蓋 26 種玩法賠率與多注結算。
[怎麼做] 直接對 baccarat_rules 的純函式做斷言，不需 pytest：python test_rules.py
[結果]   全部 [PASS] 且結尾 0 failure(s) 即通過。
"""

import baccarat_rules as r


def m(market, o, mode="standard"):
    return r.settle_mult(market, o, mode)


def test_main_bets():
    o = r.make_outcome(9, 7, pc=2, bc=3)          # 閒贏
    assert r.winner_of(o) == "player"
    assert m("player", o) == 1.0
    assert m("banker", o) == -1.0
    assert m("tie", o) == -1.0
    o2 = r.make_outcome(6, 6)                       # 和局
    assert m("player", o2) == 0.0 and m("banker", o2) == 0.0
    assert m("tie", o2) == 8.0


def test_banker_commission_and_nocomm():
    o = r.make_outcome(5, 6, pc=2, bc=2)           # 莊6點2張勝
    assert m("banker", o, "standard") == 0.95
    assert m("banker", o, "nocomm") == 0.5         # 免佣莊6點半賠
    o2 = r.make_outcome(4, 7)                        # 莊非6點勝
    assert m("banker", o2, "nocomm") == 1.0


def test_pairs():
    o = r.make_outcome(4, 4, ppair=True, bpair=True, perfect=True)
    assert m("ppair", o) == 11.0 and m("bpair", o) == 11.0
    assert m("anypair", o) == 5.0
    assert m("perfectpair", o) == 25.0
    assert m("tigerpair", o) == 20.0               # 雙方都對子


def test_big_small_oddeven():
    o = r.make_outcome(9, 7, pc=2, bc=3)           # 共5張
    assert m("big", o) == 0.5 and m("small", o) == -1.0
    assert m("podd", o) == 0.96                      # 閒9單
    assert m("bodd", o) == 0.94                      # 莊7單
    o2 = r.make_outcome(4, 6, pc=2, bc=2)           # 共4張，閒4雙 莊6雙
    assert m("small", o2) == 1.5
    assert m("peven", o2) == 0.9 and m("beven", o2) == 0.94


def test_six_and_tigers():
    o2 = r.make_outcome(5, 6, pc=2, bc=2)          # 莊6點2張
    assert m("super6", o2) == 12.0 and m("tiger6", o2) == 12.0
    assert m("smalltiger", o2) == 22.0 and m("bigtiger", o2) == -1.0
    o3 = r.make_outcome(4, 6, pc=2, bc=3)          # 莊6點3張
    assert m("super6", o3) == 20.0
    assert m("bigtiger", o3) == 50.0 and m("smalltiger", o3) == -1.0


def test_dragon_bonus():
    o = r.make_outcome(0, 7, pc=2, bc=3)           # 莊非例牌贏7點
    assert m("dragon_b", o) == 5.0
    assert m("dragon7", o) == 40.0                  # 莊3張7點勝
    o2 = r.make_outcome(9, 0, pc=2, bc=2)          # 閒例牌9點勝
    assert m("dragon_p", o2) == 1.0                 # 例牌贏1:1
    assert m("pnatural", o2) == 4.0


def test_panda_supertie():
    o = r.make_outcome(8, 6, pc=3, bc=2)           # 閒3張8點勝
    assert m("panda8", o) == 25.0
    for pt, mult in {0: 125, 2: 190, 6: 40, 9: 70}.items():
        ot = r.make_outcome(pt, pt)                 # 和局於各點
        assert m("supertie", ot) == float(mult), (pt, mult)


def test_settle_all_multibet():
    o = r.make_outcome(5, 6, pc=2, bc=2)           # 莊6點2張勝
    bets = [("banker", 1000), ("super6", 100), ("bpair", 200)]
    rows, total = r.settle_all(bets, o)
    assert total == 950 + 1200 - 200               # 莊+950 超6+1200 莊對-200


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
