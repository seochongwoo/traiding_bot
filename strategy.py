"""
네트워크/시트 의존성이 없는 순수 매매 로직 모음.
main.py에서 호출하며 tests/test_logic.py에서 단위 테스트합니다.
"""
from datetime import datetime, timedelta, timezone
import config as C

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(KST)


def is_session_time(dt: datetime) -> bool:
    """평일 09:00 ~ 15:20(KST)이면 True. 공휴일 여부는 별도로 시세 존재 여부로 판단합니다."""
    dt = dt.astimezone(KST) if dt.tzinfo else dt.replace(tzinfo=KST)
    if dt.weekday() >= 5:
        return False
    open_t = dt.replace(hour=C.MARKET_OPEN_HHMM[0], minute=C.MARKET_OPEN_HHMM[1], second=0, microsecond=0)
    cut_t = dt.replace(hour=C.MARKET_ENTRY_CUTOFF_HHMM[0], minute=C.MARKET_ENTRY_CUTOFF_HHMM[1], second=0, microsecond=0)
    return open_t <= dt <= cut_t


def evaluate_entry(score, article_type, rsi, disparity, macd_dead_cross, market_ok):
    """
    진입 트랙을 판정합니다.
    반환: (track, reasons)  track은 "A"(모멘텀) / "B"(역발상) / None
    """
    if article_type != "catalyst":
        return None, ["시황/무관 기사"]
    if score < C.CONTRARIAN_SCORE_MIN:
        return None, ["점수 미달"]
    if rsi is None or disparity is None:
        return None, ["주가 지표 획득 실패"]

    # 트랙 A: 강한 호재 + 과열 아님 + 상승 추세 + 시장 우호
    a_fail = []
    if score < C.MOMENTUM_SCORE_MIN:
        a_fail.append(f"모멘텀 점수 미달({score})")
    if rsi > C.MOMENTUM_RSI_MAX:
        a_fail.append(f"RSI 과열({rsi:.1f})")
    if disparity >= C.MOMENTUM_DISPARITY_MAX:
        a_fail.append(f"이격도 과열({disparity:.1f}%)")
    if macd_dead_cross:
        a_fail.append("MACD 데드크로스")
    if not market_ok:
        a_fail.append("대세 하락장")
    if not a_fail:
        return "A", []

    # 트랙 B: 과매도 구간의 호재 (거시/MACD 필터 미적용)
    if rsi <= C.CONTRARIAN_RSI_MAX:
        return "B", []

    return None, a_fail


def compute_tp_sl(price: float, atr: float):
    """ATR 기반 목표/손절 비율을 상·하한으로 제한해 반환합니다 (손익비 약 1.67:1)."""
    raw_target_pct = (atr / price) * 100 if price and atr else C.TARGET_PCT_MIN
    target_pct = max(C.TARGET_PCT_MIN, min(raw_target_pct, C.TARGET_PCT_MAX))
    stop_pct = max(C.STOP_PCT_MIN, min(target_pct * 0.6, C.STOP_PCT_MAX))
    return round(price * (1 + target_pct / 100)), round(price * (1 - stop_pct / 100))


def gap_check(signal_price: float, open_price: float):
    """시그널가 대비 시초가 갭(%)과 진입 허용 여부를 반환합니다."""
    gap_pct = (open_price / signal_price - 1) * 100
    return gap_pct, gap_pct <= C.MAX_GAP_UP_PCT


def resolve_exit(buy_price, target, stop, highest, bars):
    """
    마지막 점검 이후의 봉(시간순 (open, high, low, close) 목록)을 따라가며 청산 여부를 판정합니다.
    - 시가가 손절가 이하로 갭하락 → 시가 청산
    - 시가가 목표가 이상으로 갭상승 → 시가 청산
    - 같은 봉에서 손절가·목표가 모두 터치 → 보수적으로 손절 우선
    - 봉 종료 후 최고 수익률이 트리거 이상이면 다음 봉부터 손절가를 본절로 상향
    반환: dict(exit_price, reason or None, stop, highest)
    """
    for o, h, l, c in bars:
        breakeven_armed = stop >= buy_price
        if o <= stop:
            return {"exit_price": o, "reason": "본절" if breakeven_armed else "손절", "stop": stop, "highest": highest}
        if o >= target:
            return {"exit_price": o, "reason": "익절", "stop": stop, "highest": max(highest, h)}
        if l <= stop:
            return {"exit_price": stop, "reason": "본절" if breakeven_armed else "손절", "stop": stop, "highest": max(highest, h)}
        if h >= target:
            return {"exit_price": target, "reason": "익절", "stop": stop, "highest": max(highest, h)}

        highest = max(highest, h)
        if buy_price > 0 and (highest / buy_price - 1) * 100 >= C.BREAKEVEN_TRIGGER_PCT:
            stop = max(stop, round(buy_price * C.BREAKEVEN_STOP_MULT))

    return {"exit_price": None, "reason": None, "stop": stop, "highest": highest}


def in_cooldown(positions, symbol, now: datetime) -> bool:
    """동일 종목이 보유중/진입대기이거나 최근 쿨다운 시간 내 청산됐으면 True."""
    for p in positions:
        if p["symbol"] != symbol:
            continue
        if p["status"] in ("보유중", "진입대기"):
            return True
        if p["status"] == "청산완료" and p.get("close_date"):
            try:
                closed = datetime.strptime(p["close_date"].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            except ValueError:
                continue
            if now - closed < timedelta(hours=C.REENTRY_COOLDOWN_HOURS):
                return True
    return False
