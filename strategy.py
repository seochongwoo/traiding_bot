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


def is_pending_fill_window(dt: datetime) -> bool:
    """장외 대기주문 체결 허용 시간대: 평일 오전장 초반(09:00 ~ 10:00 KST)."""
    dt = dt.astimezone(KST) if dt.tzinfo else dt.replace(tzinfo=KST)
    if not is_session_time(dt):
        return False
    deadline_t = dt.replace(
        hour=C.PENDING_FILL_DEADLINE_HHMM[0],
        minute=C.PENDING_FILL_DEADLINE_HHMM[1],
        second=0,
        microsecond=0
    )
    return dt <= deadline_t


def evaluate_entry(
    score,
    article_type,
    rsi,
    disparity,
    macd_dead_cross,
    market_ok,
    current_price=None,
    open_price=None,
):
    """
    진입 트랙을 판정합니다.
    반환: (track, reasons)  track은 "A"(모멘텀) / "B"(역발상) / None
    """
    if article_type != "catalyst":
        return None, ["시황/무관 기사"]
    min_required_score = min(C.MOMENTUM_SCORE_MIN, C.CONTRARIAN_SCORE_MIN)
    if score < min_required_score:
        return None, [f"점수 미달({score}<{min_required_score})"]
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

    # 트랙 B: 과매도 구간의 강한 호재 + 당일 양봉 반등 확인 필수 (떨어지는 칼날 진입 차단)
    if rsi <= C.CONTRARIAN_RSI_MAX and score >= C.CONTRARIAN_SCORE_MIN:
        if current_price is not None and open_price is not None and open_price > 0:
            if current_price <= open_price:
                return None, a_fail + ["트랙B 음봉 하락중(양봉 반등 미확인)"]
        return "B", []

    return None, a_fail


def compute_tp_sl(price: float, atr: float):
    """ATR 기반 목표/손절 비율을 상·하한(+3.0~4.0% / -1.8~2.5%)으로 제한해 반환합니다."""
    raw_target_pct = (atr / price) * 100 if price and atr else C.TARGET_PCT_MIN
    target_pct = max(C.TARGET_PCT_MIN, min(raw_target_pct, C.TARGET_PCT_MAX))
    stop_pct = max(C.STOP_PCT_MIN, min(target_pct * 0.625, C.STOP_PCT_MAX))
    return round(price * (1 + target_pct / 100)), round(price * (1 - stop_pct / 100))


def gap_check(signal_price: float, open_price: float, fill_price: float = None):
    """
    시그널가 대비 시초가(및 실제 체결가) 갭(%)과 진입 허용 여부를 반환합니다.
    - 갭하락이 MIN_GAP_PCT(-1.0%) 미만이면 시장이 호재를 부정한 것으로 보아 차단
    - 갭상승이 MAX_GAP_UP_PCT(+3.0%) 초과면 고점 추격매수 방지를 위해 차단
    """
    gap_pct = (open_price / signal_price - 1) * 100
    can_enter = C.MIN_GAP_PCT <= gap_pct <= C.MAX_GAP_UP_PCT
    if can_enter and fill_price is not None and fill_price > 0:
        fill_gap_pct = (fill_price / signal_price - 1) * 100
        if not (C.MIN_GAP_PCT <= fill_gap_pct <= C.MAX_GAP_UP_PCT):
            can_enter = False
    return gap_pct, can_enter


def resolve_exit(buy_price, target, stop, highest, bars):
    """
    마지막 점검 이후의 봉(시간순 (open, high, low, close) 목록)을 따라가며 청산 여부를 판정합니다.
    - 시가가 손절가 이하로 갭하락 → 시가 청산
    - 시가가 목표가 이상으로 갭상승 → 시가 청산
    - 같은 봉에서 손절가·목표가 모두 터치 → 보수적으로 손절 우선
    - 봉 종료 후 최고 수익률이 트리거(+2.0%) 이상이면 다음 봉부터 손절가를 본절(+0.3%)로 상향
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


def compute_realized_pnl(buy_price: float, sell_price: float, qty: int) -> int:
    """매수가·청산가·수량 기준 실현 손익(원)을 계산합니다."""
    if qty <= 0 or buy_price <= 0 or sell_price <= 0:
        return 0
    return round((sell_price - buy_price) * qty)


def compute_portfolio_state(positions: list, initial_capital: int = None) -> dict:
    """
    Active_Positions 행 목록으로부터 가상 계좌(초기 원금 2,000만원) 상태를 계산합니다.
    - 매수수량(qty > 0)이 기록된 가상계좌 거래만 합산하므로, 과거 수량 미기재(레거시) 행은 잔고에 영향을 주지 않습니다.
    반환: dict(initial_capital, available_cash, invested_amount, realized_pnl, total_equity, total_return_pct, active_slots)
    """
    if initial_capital is None:
        initial_capital = C.INITIAL_CAPITAL

    realized_pnl = 0
    invested_amount = 0
    active_slots = 0

    for p in positions:
        qty = int(p.get("qty") or 0)
        if qty <= 0:
            continue

        status = p.get("status", "")
        buy_price = float(p.get("buy_price") or 0.0)
        close_price = float(p.get("close_price") or 0.0)

        if status == "청산완료":
            pnl = p.get("pnl_krw")
            if pnl is None or pnl == "":
                pnl = compute_realized_pnl(buy_price, close_price, qty)
            realized_pnl += round(float(pnl))
        elif status == "보유중":
            inv = p.get("invest_amount")
            if not inv:
                inv = round(buy_price * qty)
            invested_amount += round(float(inv))
            active_slots += 1

    total_equity = initial_capital + realized_pnl
    available_cash = max(0, total_equity - invested_amount)
    total_return_pct = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

    return {
        "initial_capital": round(initial_capital),
        "available_cash": round(available_cash),
        "invested_amount": round(invested_amount),
        "realized_pnl": round(realized_pnl),
        "total_equity": round(total_equity),
        "total_return_pct": round(total_return_pct, 2),
        "active_slots": active_slots,
    }


def compute_order_qty(
    buy_price: float,
    available_cash: float,
    active_slots: int = 0,
    slot_budget: float = None,
    max_slots: int = None,
):
    """
    5슬롯 균등 배분(종목당 최대 400만원) 및 가용 예수금 내에서 주문 가능 정수 주식 수(qty)와 매수금액을 반환합니다.
    반환: (qty, invest_amount)
    """
    if slot_budget is None:
        slot_budget = C.SLOT_BUDGET
    if max_slots is None:
        max_slots = C.MAX_POSITION_SLOTS

    if buy_price <= 0 or available_cash <= 0 or active_slots >= max_slots:
        return 0, 0

    budget = min(slot_budget, available_cash)
    qty = int(budget // buy_price)
    if qty <= 0:
        return 0, 0
    invest_amount = round(buy_price * qty)
    return qty, invest_amount
