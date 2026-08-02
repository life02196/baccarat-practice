"""
[為什麼] 支援「一手同時下多注」。給定一手的真實結果（閒點/莊點/各幾張/對子），
         自動算出全部 26 種投注玩法各自的輸贏——這是多注結算的核心，必須正確。
[怎麼做] 純函式，不碰 UI。settle_one(market, amount, outcome, mode) 回傳淨變化；
         settle_all 疊加整張注單。賠率完全依使用者提供的娛樂城派彩表。
[結果]   一份可單元測試的結算引擎。net 為正=贏該倍數，0=退還，負=輸掉本金。
"""

from __future__ import annotations

# 超級和：依和局點數的賠率
SUPERTIE = {0: 125, 1: 180, 2: 190, 3: 170, 4: 100, 5: 90, 6: 40, 7: 40, 8: 70, 9: 70}
# 龍寶：非例牌贏，依(贏家點-輸家點)差
DRAGON_MARGIN = {9: 30, 8: 10, 7: 5, 6: 3, 5: 2, 4: 1}


def make_outcome(pt, bt, pc=2, bc=2, ppair=False, bpair=False, perfect=False):
    """一手的結果。pt/bt=閒/莊點數(0-9)，pc/bc=各張數(2或3)，
    ppair/bpair=前兩張是否對子，perfect=是否完美對子(同花同數)。"""
    return {"pt": int(pt), "bt": int(bt), "pc": int(pc), "bc": int(bc),
            "ppair": bool(ppair), "bpair": bool(bpair), "perfect": bool(perfect)}


def winner_of(o):
    if o["pt"] > o["bt"]:
        return "player"
    if o["bt"] > o["pt"]:
        return "banker"
    return "tie"


def settle_mult(market, o, mode):
    """回傳該玩法在此結果下的賠率倍數（net = 下注 * 倍數）。-1=輸，0=退還。"""
    pt, bt, pc, bc = o["pt"], o["bt"], o["pc"], o["bc"]
    w = winner_of(o)
    p_nat = pc == 2 and pt in (8, 9)
    b_nat = bc == 2 and bt in (8, 9)
    total_cards = pc + bc

    if market == "player":
        return 1.0 if w == "player" else (0.0 if w == "tie" else -1.0)
    if market == "banker":
        if w == "banker":
            if mode == "nocomm":
                return 0.5 if bt == 6 else 1.0
            return 0.95
        return 0.0 if w == "tie" else -1.0
    if market == "tie":
        return 8.0 if w == "tie" else -1.0

    if market == "ppair":
        return 11.0 if o["ppair"] else -1.0
    if market == "bpair":
        return 11.0 if o["bpair"] else -1.0
    if market == "anypair":
        return 5.0 if (o["ppair"] or o["bpair"]) else -1.0
    if market == "perfectpair":
        return 25.0 if o["perfect"] else -1.0

    if market == "big":
        return 0.5 if total_cards in (5, 6) else -1.0
    if market == "small":
        return 1.5 if total_cards == 4 else -1.0

    if market == "bodd":
        return 0.94 if bt % 2 == 1 else -1.0
    if market == "beven":
        return 0.94 if bt % 2 == 0 else -1.0
    if market == "podd":
        return 0.96 if pt % 2 == 1 else -1.0
    if market == "peven":
        return 0.9 if pt % 2 == 0 else -1.0

    if market in ("super6", "tiger6"):
        if w == "banker" and bt == 6:
            return 12.0 if bc == 2 else 20.0
        return -1.0
    if market == "smalltiger":
        return 22.0 if (w == "banker" and bt == 6 and bc == 2) else -1.0
    if market == "bigtiger":
        return 50.0 if (w == "banker" and bt == 6 and bc == 3) else -1.0

    if market == "dragon_p":
        return _dragon(w == "player", p_nat, b_nat, w, pt - bt)
    if market == "dragon_b":
        return _dragon(w == "banker", b_nat, p_nat, w, bt - pt)

    if market == "pnatural":
        if p_nat and w == "player":
            return 4.0
        if p_nat and w == "tie":
            return 0.0
        return -1.0
    if market == "bnatural":
        if b_nat and w == "banker":
            return 4.0
        if b_nat and w == "tie":
            return 0.0
        return -1.0

    if market == "panda8":
        return 25.0 if (w == "player" and pc == 3 and pt == 8) else -1.0
    if market == "dragon7":
        return 40.0 if (w == "banker" and bc == 3 and bt == 7) else -1.0

    if market == "tigerpair":
        if o["ppair"] and o["bpair"]:
            return 20.0
        if o["ppair"] or o["bpair"]:
            return 4.0
        return -1.0
    if market == "tigertie":
        return 40.0 if (w == "tie" and pt == 6) else -1.0

    if market == "supertie":
        return float(SUPERTIE[pt]) if w == "tie" else -1.0

    return -1.0


def _dragon(i_won, my_nat, opp_nat, w, margin):
    """龍寶：這方贏→例牌1:1、否則依點差賠；和局→例牌和退還、否則輸。"""
    if i_won:
        if my_nat:
            return 1.0
        return float(DRAGON_MARGIN.get(margin, -1.0)) if margin in DRAGON_MARGIN else -1.0
    if w == "tie":
        return 0.0 if (my_nat and opp_nat) else -1.0
    return -1.0


def settle_one(market, amount, o, mode="standard"):
    return int(round(amount * settle_mult(market, o, mode)))


def settle_all(bets, o, mode="standard"):
    """bets = [(market, amount), ...]，回傳 [(market, amount, change), ...] 與總淨。"""
    rows = []
    total = 0
    for market, amount in bets:
        ch = settle_one(market, amount, o, mode)
        rows.append((market, amount, ch))
        total += ch
    return rows, total
