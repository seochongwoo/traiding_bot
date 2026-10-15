from datetime import datetime, timezone, timedelta
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from strategy import (
    is_session_time, evaluate_entry, compute_tp_sl,
    gap_check, resolve_exit, in_cooldown, KST
)
from dedup import tokenize, jaccard, find_duplicate


class TestStrategyLogic(unittest.TestCase):

    def test_session_time(self):
        # 2026-10-15는 목요일(평일)
        t_open = datetime(2026, 10, 15, 9, 5, tzinfo=KST)
        self.assertTrue(is_session_time(t_open))

        t_close_before = datetime(2026, 10, 15, 15, 19, tzinfo=KST)
        self.assertTrue(is_session_time(t_close_before))

        t_close_after = datetime(2026, 10, 15, 15, 30, tzinfo=KST)
        self.assertFalse(is_session_time(t_close_after))

        t_night = datetime(2026, 10, 15, 22, 48, tzinfo=KST)
        self.assertFalse(is_session_time(t_night))

        t_dawn = datetime(2026, 10, 15, 3, 10, tzinfo=KST)
        self.assertFalse(is_session_time(t_dawn))

        # 2026-10-17은 토요일(주말)
        t_weekend = datetime(2026, 10, 17, 10, 0, tzinfo=KST)
        self.assertFalse(is_session_time(t_weekend))

    def test_filter_deadlock_resolved(self):
        # 감사 리포트의 핵심 문제:
        # 상승장(market_ok=True) + 대형 호재(score=7) + 주가 반등으로 RSI=60인 경우
        # 기존 로직: RSI <= 50 조건 때문에 무조건 차단(Starvation)
        # 신규 로직: 트랙 A (모멘텀) 상한이 RSI 65이므로 정상 진입 승인!
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

    def test_contrarian_track_b(self):
        # 폭락/과매도 구간(RSI=28)에서 호재(score=4) 발생 시
        # 대세 하락장(market_ok=False)이어도 트랙 B(역발상)로 진입!
        track, reasons = evaluate_entry(
            score=4,
            article_type="catalyst",
            rsi=28.0,
            disparity=92.0,
            macd_dead_cross=True,
            market_ok=False
        )
        self.assertEqual(track, "B")
        self.assertEqual(reasons, [])

    def test_market_recap_rejection(self):
        # 과거 단순 시황 중계 기사는 아무리 점수가 높아도 진입 차단
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

    def test_gap_check(self):
        # 갭상승 +2%: 허용
        gap, can_enter = gap_check(100000, 102000)
        self.assertAlmostEqual(gap, 2.0)
        self.assertTrue(can_enter)

        # 갭상승 +4%: 차단
        gap, can_enter = gap_check(100000, 104000)
        self.assertAlmostEqual(gap, 4.0)
        self.assertFalse(can_enter)

    def test_tp_sl_cap(self):
        # 변동성 급증(ATR이 가격의 10%) 시에도 목표가 +5%, 손절가 -3%로 상한 제한
        target, stop = compute_tp_sl(100000, 10000)
        self.assertEqual(target, 105000) # +5%
        self.assertEqual(stop, 97000)    # -3%

        # 변동성 축소(ATR이 가격의 1%) 시에도 목표가 +2.5%, 손절가 -1.5% 하한 유지
        target_min, stop_min = compute_tp_sl(100000, 1000)
        self.assertEqual(target_min, 102500) # +2.5%
        self.assertEqual(stop_min, 98500)    # -1.5%

    def test_resolve_exit_breakeven_ratchet(self):
        buy = 100000
        target = 105000
        stop = 97000

        # Bar 1: +2.8% 상승 기록 -> 브레이크이븐 트리거 (+2.5% 달성) -> 손절가가 100,300원으로 상향되어야 함
        bars = [
            (100000, 102800, 99500, 102500),
            (102500, 102600, 100100, 100200) # Bar 2에서 100,100원까지 하락하면 100,300원에 '본절' 청산 발동
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
                "close_date": "2026-10-15 09:30:00" # 2.5시간 전 청산
            }
        ]
        # 24시간 이내 청산된 종목은 쿨다운 발동
        self.assertTrue(in_cooldown(positions, "005930.KS", now))
        # 미보유 종목은 쿨다운 미발동
        self.assertFalse(in_cooldown(positions, "000660.KS", now))


if __name__ == "__main__":
    unittest.main()
