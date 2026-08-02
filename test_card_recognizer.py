"""樸克牌辨識器的離線回歸測試，不需要相機或螢幕錄影。"""

import cv2
import numpy as np
import os
from collections import deque
from PIL import Image

from card_recognizer import RANK_LABELS, detect_cards, recognize_rank
from card_recognizer import CardDetection
from screen_card_monitor import (ScreenCardMonitor, _capture_is_black,
                                 choose_capture_window,
                                 is_complete_baccarat_hand)
from baccarat_shadow import Shadow, session_turnover
from scoreboard_recognizer import detect_scoreboard
import baccarat_rules as rules
import baccarat_shadow as shadow_module


def synthetic_card(label: str) -> np.ndarray:
    card = np.full((336, 240, 3), 255, np.uint8)
    cv2.rectangle(card, (0, 0), (239, 335), (205, 205, 205), 2)
    cv2.putText(card, label, (10, 55), cv2.FONT_HERSHEY_COMPLEX, 1.55,
                (0, 0, 0), 2, cv2.LINE_AA)
    return card


def test_all_ranks():
    for expected, label in enumerate(RANK_LABELS, start=1):
        result = recognize_rank(synthetic_card(label))
        assert result is not None, label
        rank, detected, confidence = result
        assert (rank, detected) == (expected, label), (label, result)
        assert confidence >= 0.55, (label, confidence)


def test_multiple_cards_left_to_right():
    frame = np.full((600, 900, 3), (45, 105, 45), np.uint8)
    for index, label in enumerate(("A", "10")):
        x, y = 100 + index * 360, 100
        frame[y:y + 336, x:x + 240] = synthetic_card(label)
    detected = detect_cards(frame)
    assert [card.label for card in detected] == ["A", "10"]


def test_automatic_hand_grouping():
    def detection(rank, x):
        corners = np.array([[x, 100], [x + 80, 100], [x + 80, 212], [x, 212]], np.int32)
        return CardDetection(rank, str(rank), 0.9, corners)
    cards = [detection(1, 100), detection(9, 200), detection(10, 700), detection(7, 800)]
    player, banker = ScreenCardMonitor._split_hands(cards)
    assert player == [1, 9]
    assert banker == [10, 7]


def test_supplied_baccarat_screenshot():
    path = os.path.join(os.path.dirname(__file__), "image.png")
    if not os.path.isfile(path):
        return
    image = cv2.imread(path)
    cards = ScreenCardMonitor._select_table_cards(detect_cards(image, 0.00015))
    player, banker = ScreenCardMonitor._split_hands(cards)
    assert player == [9, 8], player
    assert banker == [9, 6, 3], banker


def test_second_baccarat_screenshot():
    path = os.path.join(os.path.dirname(__file__), "image2.png")
    if not os.path.isfile(path):
        return
    image = cv2.imread(path)
    cards = ScreenCardMonitor._select_table_cards(detect_cards(image, 0.00015))
    player, banker = ScreenCardMonitor._split_hands(cards)
    assert player == [3, 11, 11], player
    assert banker == [6, 9], banker


def test_dreamgaming_baccarat_screenshot():
    path = os.path.join(os.path.dirname(__file__), "image3.png")
    if not os.path.isfile(path):
        return
    image = cv2.imread(path)
    cards = ScreenCardMonitor._select_table_cards(detect_cards(image, 0.00015))
    player, banker = ScreenCardMonitor._split_hands(cards)
    assert player == [12, 2, 6], player
    assert banker == [7, 7], banker


def test_rg_baccarat_screenshot():
    path = os.path.join(os.path.dirname(__file__), "image4.png")
    if not os.path.isfile(path):
        return
    image = cv2.imread(path)
    cards = ScreenCardMonitor._select_table_cards(detect_cards(image, 0.00015))
    player, banker = ScreenCardMonitor._split_hands(cards)
    assert player == [3, 11, 10], player
    assert banker == [13, 12], banker
    score = detect_scoreboard(image)
    assert score is not None and score.finalized
    assert not ScreenCardMonitor._official_result_ready(
        (3, 0), player, banker, True, 1.0, False)
    assert ScreenCardMonitor._official_result_ready(
        (3, 0), player, banker, True, 1.0, True)


def test_stability_requires_consecutive_frames():
    history = deque([(8, 9), (3, 11), (3, 11), (3, 11)], maxlen=10)
    assert ScreenCardMonitor._stable(history) == []
    history.append((3, 11))
    assert ScreenCardMonitor._stable(history) == [3, 11]


def test_baccarat_dealing_completion():
    # 錄影中的實例：閒 J+4 必須補牌，K 出現後莊 2+2 對 0 點第三張停牌。
    assert not is_complete_baccarat_hand([11, 4], [2, 2])
    assert is_complete_baccarat_hand([11, 4, 13], [2, 2])
    assert is_complete_baccarat_hand([9, 8], [9, 6, 3])
    assert is_complete_baccarat_hand([3, 11, 11], [6, 9])
    assert is_complete_baccarat_hand([9, 13], [8, 12])  # 任一方例牌即停
    assert not is_complete_baccarat_hand([6, 13], [2, 2])  # 閒停牌後莊 4 點須補
    assert is_complete_baccarat_hand([6, 13], [2, 2, 8])


def test_monitor_emits_each_round_once():
    emitted = []
    class FakeWindow:
        @staticmethod
        def after(_delay, callback): callback()
    class FakeLabel:
        def __init__(self): self.text = "判定：和局"
        def cget(self, _key): return self.text
        def config(self, **kwargs): self.text = kwargs.get("text", self.text)
    monitor = ScreenCardMonitor.__new__(ScreenCardMonitor)
    monitor.current_player = [11, 4, 13]
    monitor.current_banker = [2, 2]
    monitor.round_armed = True; monitor.empty_frames = 0; monitor.last_emitted = None
    monitor.window = FakeWindow(); monitor.winner_result = FakeLabel()
    monitor.official_scores = (4, 4)
    monitor.on_apply = lambda p, b, score, evidence: emitted.append((p, b, score))
    monitor._auto_emit_if_ready(); monitor._auto_emit_if_ready()
    assert len(emitted) == 1
    monitor._mark_empty_frame(); monitor._mark_empty_frame(); monitor._mark_empty_frame()
    monitor._auto_emit_if_ready()
    assert len(emitted) == 2


def test_monitor_official_score_can_settle_without_cards():
    emitted = []
    class FakeLabel:
        def __init__(self): self.text = ""
        def cget(self, _key): return self.text
        def config(self, **kwargs): self.text = kwargs.get("text", self.text)
    monitor = ScreenCardMonitor.__new__(ScreenCardMonitor)
    monitor.current_player = []
    monitor.current_banker = []
    monitor.official_scores = (3, 5)
    monitor.round_armed = True
    monitor.last_emitted = None
    monitor.winner_result = FakeLabel()
    monitor.on_apply = lambda p, b, score, evidence: emitted.append((p, b, score))
    monitor._auto_emit_if_ready()
    assert emitted == [([], [], (3, 5))]
    assert monitor.round_armed is False


def test_rejected_settlement_is_not_retried_every_blank_frame():
    attempts = []
    class FakeLabel:
        def __init__(self): self.text = ""
        def cget(self, _key): return self.text
        def config(self, **kwargs): self.text = kwargs.get("text", self.text)
    monitor = ScreenCardMonitor.__new__(ScreenCardMonitor)
    monitor.current_player = []; monitor.current_banker = []
    monitor.last_verified_player = []; monitor.last_verified_banker = []
    monitor.official_scores = (7, 6); monitor.round_armed = True
    monitor.empty_frames = 0; monitor.last_emitted = None
    monitor.winner_result = FakeLabel()
    monitor.on_apply = lambda p, b, score, evidence: attempts.append(score) or False
    monitor._auto_emit_if_ready()
    for _ in range(6):
        monitor._mark_empty_frame(); monitor._auto_emit_if_ready()
    assert attempts == [(7, 6)]


def test_dreamgaming_never_settles_from_cards_alone():
    emitted = []
    monitor = ScreenCardMonitor.__new__(ScreenCardMonitor)
    monitor.current_player = [3, 4]
    monitor.current_banker = [1, 4, 8]
    monitor.official_scores = None
    monitor.round_armed = True
    monitor.last_emitted = None
    monitor.detected_platform = "dreamgaming"
    monitor.platform_mode = "auto"
    monitor.on_apply = lambda p, b, score, evidence: emitted.append((p, b, score))
    monitor._auto_emit_if_ready()
    assert emitted == []
    assert monitor.round_armed is True


def test_old_result_waits_for_blank_transition():
    emitted = []
    class FakeLabel:
        def __init__(self): self.text = ""
        def cget(self, _key): return self.text
        def config(self, **kwargs): self.text = kwargs.get("text", self.text)
    monitor = ScreenCardMonitor.__new__(ScreenCardMonitor)
    monitor.current_player = []
    monitor.current_banker = []
    monitor.official_scores = (7, 8)
    monitor.round_armed = False
    monitor.empty_frames = 0
    monitor.last_emitted = None
    monitor.winner_result = FakeLabel()
    monitor.on_apply = lambda p, b, score, evidence: emitted.append(score)
    monitor._auto_emit_if_ready()
    assert emitted == []
    monitor.official_scores = None
    monitor._mark_empty_frame(); monitor._mark_empty_frame(); monitor._mark_empty_frame()
    monitor.official_scores = (3, 5)
    monitor._auto_emit_if_ready()
    assert emitted == [(3, 5)]


def test_zero_placeholder_requires_visible_cards():
    assert not ScreenCardMonitor._valid_official_score((0, 0), False)
    assert ScreenCardMonitor._valid_official_score((0, 0), True)
    assert ScreenCardMonitor._valid_official_score((0, 7), False)


def test_intermediate_score_waits_for_completed_hand():
    assert not ScreenCardMonitor._official_result_ready(
        (1, 6), [8, 3], [11, 6], True, 20.0)
    assert ScreenCardMonitor._official_result_ready(
        (7, 7), [8, 3, 6], [11, 6, 1], True, 1.0)
    assert not ScreenCardMonitor._official_result_ready(
        (7, 6), [8, 3, 6], [11, 6, 1], True, 20.0)
    assert ScreenCardMonitor._official_result_ready(
        (8, 5), [], [], False, 8.1)
    assert not ScreenCardMonitor._official_result_ready(
        (0, 2), [1, 9], [4, 8, 11], True, 20.0, False, "dreamgaming")
    assert not ScreenCardMonitor._official_result_ready(
        (7, 3), [3, 4], [1, 4, 8], True, 20.0, False, "dreamgaming")


def test_dreamgaming_settles_last_score_when_cards_are_collected():
    promote = ScreenCardMonitor._dreamgaming_collected_result
    assert promote("dreamgaming", False, False, 2, (9, 4), 4.0) == (9, 4)
    assert promote("dreamgaming", True, False, 2, (9, 4), 4.0) is None
    assert promote("dreamgaming", False, True, 4, (9, 4), 4.0) is None
    assert promote("dreamgaming", False, False, 2, (9, 4), 8.1) is None
    assert promote("original", False, False, 2, (9, 4), 4.0) is None


def test_round_candidates_reconstruct_verified_final_hand():
    stats = {
        "player": {(1, 1): (5, 8), (1, 1, 9): (3, 14)},
        "banker": {(4, 6): (6, 9), (4, 6, 1): (3, 15)},
    }
    player, banker = ScreenCardMonitor._best_verified_hands(stats, (1, 1))
    assert player == [1, 1, 9]
    assert banker == [4, 6, 1]
    assert is_complete_baccarat_hand(player, banker)
    pair_stats = {"player": {(3, 3): (4, 10)}, "banker": {(3, 4): (4, 10)}}
    player, banker = ScreenCardMonitor._best_verified_hands(pair_stats, (6, 7))
    assert player[:2] == [3, 3]
    assert banker == [3, 4]


def test_round_features_settle_pairs_without_full_hand_reconstruction():
    stats = {
        "player": {(6, 9): (5, 10), (6, 9, 2): (1, 12)},
        "banker": {(11, 11): (4, 9), (11, 11, 1): (2, 13)},
    }
    evidence = ScreenCardMonitor._round_feature_evidence(stats)
    assert evidence["ppair"] is False
    assert evidence["bpair"] is True
    assert evidence["bc"] == 3


def test_low_confidence_dg_cards_still_form_spatial_hands():
    folder = os.path.join(os.path.dirname(__file__), "diagnostics", "dg_review_v21")
    for name in ("frame_305.jpg", "frame_410.jpg", "frame_647.jpg"):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        cards = detect_cards(cv2.imread(path), min_area_ratio=0.00015)
        selected = ScreenCardMonitor._select_table_cards(cards)
        player, banker = ScreenCardMonitor._split_hands(selected)
        assert 2 <= len(player) <= 3, (name, player, banker)
        assert 2 <= len(banker) <= 3, (name, player, banker)


def test_spatial_group_accepts_dg_ten_at_point_36():
    def card(rank, confidence, x, y=400):
        corners = np.array([[x - 34, y - 49], [x + 34, y - 49],
                            [x + 34, y + 49], [x - 34, y + 49]], np.float32)
        return CardDetection(rank, RANK_LABELS[rank - 1], confidence, corners)

    cards = [card(11, .85, 518), card(11, .56, 636),
             card(1, .86, 779), card(10, .36, 897),
             card(9, .95, 1800, 700)]
    selected = ScreenCardMonitor._select_table_cards(cards)
    player, banker = ScreenCardMonitor._split_hands(selected)
    assert player == [11, 11]
    assert banker == [1, 10]


def test_dg_third_card_row_is_not_split_as_two_hands():
    def card(rank, x, y, confidence=.8):
        corners = np.array([[x - 34, y - 49], [x + 34, y - 49],
                            [x + 34, y + 49], [x - 34, y + 49]], np.float32)
        return CardDetection(rank, RANK_LABELS[rank - 1], confidence, corners)

    cards = [card(4, 518, 411), card(1, 578, 533), card(8, 636, 411),
             card(3, 779, 411), card(7, 839, 533), card(10, 897, 411, .36)]
    selected = ScreenCardMonitor._select_table_cards(cards)
    player, banker = ScreenCardMonitor._split_hands(selected)
    assert player == [4, 8, 1]
    assert banker == [3, 10, 7]


def test_dg_slot_memory_recovers_a_card_seen_in_one_early_frame():
    def card(rank, confidence, x, y=411):
        corners = np.array([[x - 34, y - 49], [x + 34, y - 49],
                            [x + 34, y + 49], [x - 34, y + 49]], np.float32)
        return CardDetection(rank, RANK_LABELS[rank - 1], confidence, corners)

    stats = ScreenCardMonitor._new_dg_slot_stats()
    boxes = ((443, 263, 237, 70), (680, 263, 289, 70))
    ScreenCardMonitor._accumulate_dg_slots(
        stats, [card(10, .286, 518), card(11, .65, 636)], boxes, 1)
    for frame in range(2, 7):
        ScreenCardMonitor._accumulate_dg_slots(
            stats, [card(11, .65, 636), card(5, .78, 779), card(1, .79, 897)],
            boxes, frame)
    evidence = ScreenCardMonitor._dg_slot_evidence(stats, (7, 6))
    assert evidence == {"pc": 2, "ppair": False, "bc": 2, "bpair": False}


def test_dg_natural_infers_both_sides_have_two_cards():
    def card(rank, confidence, x, y=411):
        corners = np.array([[x - 34, y - 49], [x + 34, y - 49],
                            [x + 34, y + 49], [x - 34, y + 49]], np.float32)
        return CardDetection(rank, RANK_LABELS[rank - 1], confidence, corners)

    stats = ScreenCardMonitor._new_dg_slot_stats()
    boxes = ((443, 263, 237, 70), (680, 263, 289, 70))
    for frame in range(1, 5):
        ScreenCardMonitor._accumulate_dg_slots(
            stats, [card(5, .76, 636), card(1, .84, 779), card(10, .43, 897)],
            boxes, frame)
    evidence = ScreenCardMonitor._dg_slot_evidence(stats, (5, 8))
    assert evidence["bc"] == 2 and evidence["pc"] == 2
    assert evidence["ppair"] is False and evidence["bpair"] is False


def test_main_bets_push_on_tie():
    outcome = rules.make_outcome(7, 7)
    assert rules.settle_one("player", 1000, outcome) == 0
    assert rules.settle_one("banker", 1000, outcome) == 0
    assert rules.settle_one("tie", 1000, outcome) == 8000


def test_add_bet_resets_amount_to_zero():
    class FakeVar:
        def __init__(self, value): self.value = str(value)
        def get(self): return self.value
        def set(self, value): self.value = str(value)
    class FakeLabel:
        def config(self, **_kwargs): pass
    shadow = Shadow.__new__(Shadow)
    shadow.amt_var = FakeVar(500)
    shadow.slip = []
    shadow.msg = FakeLabel()
    shadow._render_slip = lambda: None
    shadow.cur_session = lambda: {"start": 10000, "hands": []}
    shadow.refresh = lambda: None
    shadow.add_bet("banker")
    assert shadow.slip == [("banker", 500)]
    assert shadow.amt_var.get() == "0"


def test_all_in_uses_uncommitted_balance():
    class FakeVar:
        def __init__(self): self.value = "0"
        def get(self): return self.value
        def set(self, value): self.value = str(value)
    class FakeLabel:
        def config(self, **_kwargs): pass
    shadow = Shadow.__new__(Shadow)
    shadow.amt_var = FakeVar()
    shadow.slip = [("player", 1200)]
    shadow.msg = FakeLabel()
    shadow.cur_session = lambda: {"start": 10000, "hands": [{"change": -1800}]}
    shadow.all_in()
    assert shadow.amt_var.get() == "7000"


def test_available_balance_reserves_bets_until_settlement():
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [("banker", 2500), ("tie", 500)]
    shadow.cur_session = lambda: {"start": 10000, "hands": [{"change": 950}]}
    assert shadow.available_balance() == 7950


def test_top_result_summary_shows_outcome_and_user_result():
    text, color = Shadow._result_summary({"outcome": rules.make_outcome(7, 7), "change": 0})
    assert text == "和局｜本金退回"
    text, color = Shadow._result_summary({"outcome": rules.make_outcome(3, 8), "change": 950})
    assert text == "莊贏｜本手贏 +950"
    text, color = Shadow._result_summary({"outcome": rules.make_outcome(8, 3), "change": -1000})
    assert text == "閒贏｜本手輸 -1,000"
    hand = {"outcome": rules.make_outcome(8, 3), "change": -1200,
            "results": [["banker", 1000, -1000], ["bpair", 200, -200]]}
    text, color = Shadow._result_summary(hand)
    assert text == "閒贏｜押莊 1,000：輸 1,000｜押莊對 200：輸 200｜本手 -1,200"
    assert Shadow._bet_summary([("banker", 1000), ("tie", 500)]) == "押莊 1,000、押和 500"


def test_recent_streak_uses_user_profit_and_loss():
    hands = [{"change": value} for value in (-100, -200, 300, 0, 500)]
    assert Shadow._streak_values(hands) == [
        ("未記錄", "輸"), ("未記錄", "輸"), ("未記錄", "贏"),
        ("未記錄", "和"), ("未記錄", "贏")]
    hands = [
        {"change": -1000, "bets": [["banker", 1000]]},
        {"change": 950, "bets": [["banker", 1000]]},
        {"change": 0, "bets": [["player", 500], ["tie", 100]]},
    ]
    assert Shadow._streak_values(hands) == [
        ("莊", "輸"), ("莊", "贏"), ("閒/和", "和")]


def test_bust_does_not_start_a_new_session():
    class FakeVar:
        def __init__(self): self.value = "100"
        def get(self): return self.value
        def set(self, value): self.value = str(value)
    session = {"start": 100, "mode": "standard", "hands": []}
    shadow = Shadow.__new__(Shadow)
    shadow.data = {"settings": {"default_bet": 0}}
    shadow.slip = [("banker", 100)]
    shadow.amt_var = FakeVar()
    shadow.cur_session = lambda: session
    shadow._render_slip = lambda: None
    shadow._reset_outcome = lambda: None
    messages = []
    shadow.refresh = lambda msg=None: messages.append(msg)
    shadow._start_new = lambda *_args: (_ for _ in ()).throw(AssertionError("started new session"))
    original_save = shadow_module.save_data
    shadow_module.save_data = lambda _data: None
    try:
        shadow._do_settle(rules.make_outcome(9, 0))
    finally:
        shadow_module.save_data = original_save
    assert len(session["hands"]) == 1
    assert "不會自動重開新局" in messages[-1]


def test_shadow_recognition_triggers_settlement():
    settled = []
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [("bpair", 500)]
    shadow.p_cards = []; shadow.b_cards = []
    shadow._set_target = lambda _target: None
    shadow._update_hand = lambda: None
    shadow._do_settle = lambda outcome: settled.append(outcome)
    shadow._apply_screen_cards([9, 8], [9, 6, 3], (7, 8))
    assert len(settled) == 1
    assert settled[0]["pt"] == 7 and settled[0]["bt"] == 8
    assert settled[0]["bpair"] is False


def test_official_score_overrides_card_error_for_main_bet():
    settled = []
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [("banker", 500)]
    shadow.p_cards = []; shadow.b_cards = []
    shadow._set_target = lambda _target: None
    shadow._update_hand = lambda: None
    shadow._do_settle = lambda outcome: settled.append(outcome)
    shadow._apply_screen_cards([8, 9], [8, 8, 10], (3, 5))
    assert len(settled) == 1
    assert rules.winner_of(settled[0]) == "banker"


def test_score_only_side_bet_uses_official_score_without_cards():
    settled = []
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [("podd", 500)]
    shadow.p_cards = []; shadow.b_cards = []
    shadow._set_target = lambda _target: None
    shadow._update_hand = lambda: None
    shadow._do_settle = lambda outcome: settled.append(outcome)
    assert shadow._apply_screen_cards([], [], (3, 8)) is True
    assert len(settled) == 1
    assert settled[0]["pt"] == 3 and settled[0]["bt"] == 8


def test_pair_bet_uses_multiframe_evidence_without_full_cards():
    settled = []
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [("bpair", 500)]
    shadow.p_cards = []; shadow.b_cards = []
    shadow._set_target = lambda _target: None
    shadow._update_hand = lambda: None
    shadow._do_settle = lambda outcome: settled.append(outcome)
    assert shadow._apply_screen_cards([], [], (6, 7), {"bpair": True}) is True
    assert len(settled) == 1
    assert settled[0]["bpair"] is True


def test_side_bet_only_requires_evidence_that_can_change_its_result():
    class FakeLabel:
        def config(self, **_kwargs): pass

    def apply(market, score, evidence=None):
        settled = []
        shadow = Shadow.__new__(Shadow)
        shadow.slip = [(market, 500)]
        shadow.p_cards = []; shadow.b_cards = []
        shadow.msg = FakeLabel()
        shadow._set_target = lambda _target: None
        shadow._update_hand = lambda: None
        shadow._do_settle = lambda outcome: settled.append(outcome)
        accepted = shadow._apply_screen_cards([], [], score, evidence)
        return accepted, settled

    # These bets are already certain losses from the official score; cards
    # cannot change them and must not leave the hand stuck as "unsettled".
    for market, score in (("super6", (8, 3)), ("panda8", (3, 8)),
                          ("dragon7", (8, 3)), ("dragon_b", (8, 3)),
                          ("pnatural", (3, 8))):
        accepted, settled = apply(market, score)
        assert accepted is True, market
        assert len(settled) == 1, market

    # A winning-condition candidate only needs its own side's card count.
    accepted, settled = apply("panda8", (8, 3), {"pc": 3})
    assert accepted is True and settled[0]["pc"] == 3
    accepted, settled = apply("dragon7", (3, 7), {"bc": 3})
    assert accepted is True and settled[0]["bc"] == 3


def test_all_visible_auto_markets_settle_together_with_full_evidence():
    settled = []
    shadow = Shadow.__new__(Shadow)
    shadow.slip = [(market, 100) for market, _label, _color in shadow_module.MARKETS
                   if market != "perfectpair"]
    shadow.p_cards = []; shadow.b_cards = []
    shadow._set_target = lambda _target: None
    shadow._update_hand = lambda: None
    shadow._do_settle = lambda outcome: settled.append(outcome)
    evidence = {"pc": 3, "bc": 2, "ppair": False, "bpair": True}
    assert shadow._apply_screen_cards([], [], (6, 7), evidence) is True
    assert len(settled) == 1
    assert settled[0] == rules.make_outcome(6, 7, 3, 2, False, True, False)


def test_recorded_dg_rounds_settle_every_visible_market():
    session = os.path.join(os.path.dirname(__file__), "diagnostics",
                           "session_20260803_001212.jsonl")
    if not os.path.isfile(session):
        return
    from analyze_dg_session import analyze

    rounds = analyze(session)
    assert len(rounds) >= 19
    markets = [market for market, _label, _color in shadow_module.MARKETS
               if market != "perfectpair"]
    for round_index, item in enumerate(rounds, 1):
        for market in markets:
            settled = []
            shadow = Shadow.__new__(Shadow)
            shadow.slip = [(market, 100)]
            shadow.p_cards = []; shadow.b_cards = []
            shadow._set_target = lambda _target: None
            shadow._update_hand = lambda: None
            shadow._do_settle = lambda outcome: settled.append(outcome)
            accepted = shadow._apply_screen_cards(
                item["player"], item["banker"], item["official"], item["evidence"])
            assert accepted is True and len(settled) == 1, (round_index, market, item)


def test_official_scoreboard_examples():
    examples = (("image.png", (7, 8), "original"),
                ("image2.png", (3, 5), "original"),
                 ("image3.png", (8, 4), "dreamgaming"),
                 ("image4.png", (3, 0), "rg"),
                 (os.path.join("diagnostics", "dg_review", "frame_173.jpg"),
                  (8, 1), "dreamgaming"),
                 (os.path.join("diagnostics", "_analysis_frame_140.png"), (4, 4), "original"))
    for relative, expected, expected_platform in examples:
        path = os.path.join(os.path.dirname(__file__), relative)
        if not os.path.isfile(path):
            continue
        result = detect_scoreboard(cv2.imread(path))
        assert result is not None, relative
        assert (result.player, result.banker) == expected, (relative, result)
        assert result.platform == expected_platform, (relative, result)
        forced = detect_scoreboard(cv2.imread(path), expected_platform)
        assert forced is not None
        assert (forced.player, forced.banker) == expected


def test_multimonitor_capture_uses_dpi_not_combined_width():
    assert ScreenCardMonitor._capture_coordinate_scale(3360, 1080, 1920, 1080) == 1.0
    assert ScreenCardMonitor._capture_coordinate_scale(2880, 1620, 1920, 1080) == 1.5


def test_session_turnover_counts_only_valid_settled_bets():
    session = {
        "hands": [
            {"bets": [["banker", 1000], ["bpair", 200]], "change": 800},
            {"bets": [["player", "500"]], "change": -500},
            {"change": 0},  # 舊版紀錄可能沒有 bets
            {"bets": [["tie"], None, ["banker", -100]], "change": 0},
        ]
    }
    assert session_turnover(session) == 1700


def test_saved_capture_window_requires_an_unambiguous_title():
    windows = [(101, "DG 百家樂 - Chrome"), (202, "MT 百家樂 - Edge")]
    assert choose_capture_window(windows, " DG   百家樂 - Chrome ") == windows[0]
    assert choose_capture_window(windows, "mt 百家樂 - edge") == windows[1]
    assert choose_capture_window(windows, "不存在的視窗") is None
    duplicates = [(1, "Casino"), (2, "CASINO")]
    assert choose_capture_window(duplicates, "casino") is None


def test_capture_black_frame_detection_keeps_dark_interfaces_valid():
    assert _capture_is_black(Image.fromarray(np.zeros((300, 500, 3), np.uint8))) is True
    dark_ui = np.zeros((300, 500, 3), np.uint8)
    dark_ui[20:40, 20:300] = (30, 30, 30)
    dark_ui[100:180, 100:400] = (15, 70, 20)
    assert _capture_is_black(Image.fromarray(dark_ui)) is False


if __name__ == "__main__":
    failures = 0
    for test in (test_all_ranks, test_multiple_cards_left_to_right, test_automatic_hand_grouping,
                 test_supplied_baccarat_screenshot, test_second_baccarat_screenshot,
                 test_dreamgaming_baccarat_screenshot,
                 test_rg_baccarat_screenshot,
                 test_stability_requires_consecutive_frames, test_baccarat_dealing_completion,
                 test_monitor_emits_each_round_once,
                 test_monitor_official_score_can_settle_without_cards,
                 test_rejected_settlement_is_not_retried_every_blank_frame,
                 test_dreamgaming_never_settles_from_cards_alone,
                 test_old_result_waits_for_blank_transition,
                 test_zero_placeholder_requires_visible_cards,
                 test_intermediate_score_waits_for_completed_hand,
                 test_dreamgaming_settles_last_score_when_cards_are_collected,
                 test_round_candidates_reconstruct_verified_final_hand,
                 test_round_features_settle_pairs_without_full_hand_reconstruction,
                 test_low_confidence_dg_cards_still_form_spatial_hands,
                 test_spatial_group_accepts_dg_ten_at_point_36,
                 test_dg_third_card_row_is_not_split_as_two_hands,
                 test_dg_slot_memory_recovers_a_card_seen_in_one_early_frame,
                 test_dg_natural_infers_both_sides_have_two_cards,
                 test_main_bets_push_on_tie,
                 test_add_bet_resets_amount_to_zero,
                 test_all_in_uses_uncommitted_balance,
                 test_available_balance_reserves_bets_until_settlement,
                 test_top_result_summary_shows_outcome_and_user_result,
                 test_recent_streak_uses_user_profit_and_loss,
                 test_bust_does_not_start_a_new_session,
                 test_shadow_recognition_triggers_settlement,
                 test_official_score_overrides_card_error_for_main_bet,
                 test_score_only_side_bet_uses_official_score_without_cards,
                 test_pair_bet_uses_multiframe_evidence_without_full_cards,
                 test_side_bet_only_requires_evidence_that_can_change_its_result,
                 test_all_visible_auto_markets_settle_together_with_full_evidence,
                 test_recorded_dg_rounds_settle_every_visible_market,
                 test_official_scoreboard_examples,
                 test_multimonitor_capture_uses_dpi_not_combined_width,
                 test_session_turnover_counts_only_valid_settled_bets,
                 test_saved_capture_window_requires_an_unambiguous_title,
                 test_capture_black_frame_detection_keeps_dark_interfaces_valid):
        try:
            test(); print(f"[PASS] {test.__name__}")
        except Exception as exc:
            failures += 1; print(f"[FAIL] {test.__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    raise SystemExit(1 if failures else 0)
