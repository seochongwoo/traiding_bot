from datetime import datetime, timezone, timedelta
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from strategy import (
    is_session_time, is_pending_fill_window, evaluate_entry, compute_tp_sl,
    gap_check, resolve_exit, in_cooldown, KST
)
from dedup import tokenize, jaccard, find_duplicate


class TestStrategyLogic(unittest.TestCase):

    def test_session_and_pending_fill_window(self):
        # 2026-10-15는 목요일(평일)
        t_open = datetime(2026, 10, 15, 9, 15, tzinfo=KST)
        self.assertTrue(is_session_time(t_open))
        self.assertTrue(is_pending_fill_window(t_open))

        # 오전 10:00 이후는 정규장이지만 대기주문 체결 허용 시간(09:00~10:00) 경과
        t_late_morning = datetime(2026, 10, 15, 10, 13, tzinfo=KST)
        self.assertTrue(is_session_time(t_late_morning))
        self.assertFalse(is_pending_fill_window(t_late_morning))

        t_close_after = datetime(2026, 10, 15, 15, 30, tzinfo=KST)
        self.assertFalse(is_session_time(t_close_after))

        # 2026-10-17은 토요일(주말)
        t_weekend = datetime(2026, 10, 17, 9, 30, tzinfo=KST)
        self.assertFalse(is_session_time(t_weekend))
        self.assertFalse(is_pending_fill_window(t_weekend))

    def test_filter_deadlock_resolved(self):
        track, reasons = evaluate_entry(
            score=7,
            article_type="catalyst",
            rsi=60.0,
            disparity=108.0,
            macd_dead_cross=False,
            market_ok=True
        )
        self.assertEqual(track, "A")
        self.assertEqual(reasons, [])

    def test_contrarian_track_b_requires_strong_score_and_bullish_candle(self):
        # 1) 과매도(RSI=28) + 강한 호재(score=6) + 당일 양봉 반등(현재가 > 시초가) -> 트랙 B 승인
        track, reasons = evaluate_entry(
            score=6,
            article_type="catalyst",
            rsi=28.0,
            disparity=92.0,
            macd_dead_cross=True,
            market_ok=False,
            current_price=300000,
            open_price=295000
        )
        self.assertEqual(track, "B")
        self.assertEqual(reasons, [])

        # 2) 과매도지만 음봉 하락 중(현재가 <= 시초가)이면 떨어지는 칼날 방지를 위해 차단
        track_bear, reasons_bear = evaluate_entry(
            score=6,
            article_type="catalyst",
            rsi=28.0,
            disparity=92.0,
            macd_dead_cross=True,
            market_ok=False,
            current_price=292000,
            open_price=295000
        )
        self.assertIsNone(track_bear)
        self.assertTrue(any("음봉" in r for r in reasons_bear))

        # 3) 약한 호재(score=4)는 트랙 B 진입 차단
        track_weak, _ = evaluate_entry(
            score=4,
            article_type="catalyst",
            rsi=28.0,
            disparity=92.0,
            macd_dead_cross=True,
            market_ok=False,
            current_price=300000,
            open_price=295000
        )
        self.assertIsNone(track_weak)

    def test_market_recap_rejection(self):
        track, reasons = evaluate_entry(
            score=8,
            article_type="market_recap",
            rsi=45.0,
            disparity=100.0,
            macd_dead_cross=False,
            market_ok=True
        )
        self.assertIsNone(track)
        self.assertIn("시황/무관 기사", reasons)

    def test_gap_check_both_directions_and_fill_price(self):
        # 갭상승 +2%: 허용
        gap, can_enter = gap_check(100000, 102000, fill_price=102500)
        self.assertAlmostEqual(gap, 2.0)
        self.assertTrue(can_enter)

        # 시초가는 +0.5%였으나 실제 체결가가 +7.8% 급등한 경우: 차단
        gap, can_enter = gap_check(295500, 297000, fill_price=318500)
        self.assertFalse(can_enter)

        # 시초가 갭하락 -2.4% (마이너스 갭 한도 -1.0% 이탈): 차단
        gap_down, can_enter_down = gap_check(100000, 97600)
        self.assertAlmostEqual(gap_down, -2.4)
        self.assertFalse(can_enter_down)

        # 갭상승 +4%: 차단
        gap_up, can_enter_up = gap_check(100000, 104000)
        self.assertAlmostEqual(gap_up, 4.0)
        self.assertFalse(can_enter_up)

    def test_tp_sl_cap(self):
        # 변동성 급증 시 목표가 +4.0%, 손절가 -2.5% 상한 제한
        target, stop = compute_tp_sl(100000, 10000)
        self.assertEqual(target, 104000) # +4.0%
        self.assertEqual(stop, 97500)    # -2.5%

        # 변동성 축소 시 목표가 +3.0%, 손절가 -1.88%(반올림) 하한 유지
        target_min, stop_min = compute_tp_sl(100000, 1000)
        self.assertEqual(target_min, 103000) # +3.0%
        self.assertEqual(stop_min, 98125)    # -1.875%

    def test_resolve_exit_breakeven_ratchet_at_2pct(self):
        buy = 100000
        target = 104000
        stop = 97500

        # Bar 1: +2.1% 상승 기록 -> 브레이크이븐 트리거 (+2.0% 달성) -> 손절가가 100,300원으로 상향
        bars = [
            (100000, 102100, 99500, 101800),
            (101800, 101900, 100100, 100200) # Bar 2에서 100,100원까지 하락하면 100,300원에 '본절' 청산 발동
        ]
        res = resolve_exit(buy, target, stop, 100000, bars)
        self.assertEqual(res["reason"], "본절")
        self.assertEqual(res["exit_price"], 100300)

    def test_dedup_jaccard(self):
        title1 = "현대차, 브라질 수소 생태계 구축 박차"
        title2 = "현대차그룹 브라질서 수소 생태계 조성 추진"
        recent = [title1]
        dup, sim = find_duplicate(title2, recent, keyword="현대차", threshold=0.4)
        self.assertIsNotNone(dup)
        self.assertGreaterEqual(sim, 0.4)

    def test_cooldown(self):
        now = datetime(2026, 10, 15, 12, 0, tzinfo=KST)
        positions = [
            {
                "symbol": "005930.KS",
                "status": "청산완료",
                "close_date": "2026-10-15 09:30:00"
            }
        ]
        self.assertTrue(in_cooldown(positions, "005930.KS", now))
        self.assertFalse(in_cooldown(positions, "000660.KS", now))


if __name__ == "__main__":
    unittest.main()
