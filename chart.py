import yfinance as yf
import pandas as pd
from config import TICKER_MAP

def get_stock_indicators(keyword: str):
    """
    야후 파이낸스를 통해 해당 키워드 종목의 3개월 일봉 데이터를 조회하여
    현재가, RSI(14), ATR(14), 이격도(20), MACD 데드크로스 여부를 계산해 반환합니다.
    """
    if keyword not in TICKER_MAP:
        print(f"Warning: '{keyword}' is not in TICKER_MAP. Skipping chart indicator check.")
        return None

    ticker = TICKER_MAP[keyword]
    print(f"Fetching chart data for {keyword} ({ticker}) via yfinance...")

    try:
        # MACD(26), 이격도(20), ATR(14) 계산을 안정적으로 하기 위해 3개월 데이터를 받습니다.
        df = yf.Ticker(ticker).history(period="3mo")

        if df.empty or len(df) < 26:
            print(f"Warning: Not enough data points fetched for {ticker} (Length: {len(df) if df is not None else 0}).")
            return None

        # 1. 실시간 현재가 획득 (fast_info 및 intraday 1m 우선 사용으로 과거 일봉 지연 왜곡 방지)
        t_obj = yf.Ticker(ticker)
        current_price = None
        try:
            fast_price = t_obj.fast_info.last_price
            if fast_price is not None and fast_price > 0:
                current_price = float(fast_price)
        except Exception as e:
            print(f"Warning: fast_info fetch failed for {ticker}: {e}")

        if current_price is None or current_price <= 0:
            try:
                df_1m = t_obj.history(period="1d", interval="1m")
                if not df_1m.empty:
                    current_price = float(df_1m['Close'].iloc[-1])
            except Exception as e:
                print(f"Warning: 1m intraday fetch failed for {ticker}: {e}")

        if current_price is None or current_price <= 0:
            current_price = float(df['Close'].iloc[-1])

        # 2. RSI (14일 기준, 와일더 지수이동평균 방식)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).copy()
        loss = -delta.where(delta < 0, 0).copy()

        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()

        rs = avg_gain / avg_loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1])

        # 3. ATR (14일 기준, 와일더 방식)
        hl = df['High'] - df['Low']
        hc = (df['High'] - df['Close'].shift()).abs()
        lc = (df['Low'] - df['Close'].shift()).abs()
        
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr_series = tr.ewm(alpha=1/14, min_periods=14).mean()
        atr = float(atr_series.iloc[-1])

        # 4. 이격도 (20일 기준)
        sma20 = df['Close'].rolling(window=20).mean()
        latest_sma20 = float(sma20.iloc[-1])
        disparity = float((current_price / latest_sma20) * 100)

        # 5. MACD 및 Signal (12, 26, 9)
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        latest_macd = float(macd.iloc[-1])
        latest_signal = float(signal.iloc[-1])
        macd_dead_cross = bool(latest_macd < latest_signal)

        indicators = {
            "current_price": current_price,
            "rsi": rsi,
            "atr": atr,
            "disparity": disparity,
            "macd_dead_cross": macd_dead_cross
        }

        print(f"[{keyword}] Price: {current_price:,.0f} | RSI: {rsi:.2f} | ATR: {atr:.2f} | Disparity: {disparity:.2f}% | MACD DeadCross: {macd_dead_cross}")
        return indicators

    except Exception as e:
        print(f"Exception during indicator calculation for {keyword} ({ticker}): {e}")
        return None

def check_market_trend():
    """
    코스피(^KS11)와 나스닥(^IXIC)의 현재 지수가 각각 20일선 위에 있는지 검사합니다.
    두 지수가 모두 20일선 위에 있으면 (True, True)를 반환합니다.
    """
    indices = {
        "KOSPI": "^KS11",
        "NASDAQ": "^IXIC"
    }
    
    results = {}
    for name, ticker in indices.items():
        try:
            # 20일선 계산을 위해 2개월 데이터를 받습니다.
            df = yf.Ticker(ticker).history(period="2mo")
            if df.empty:
                print(f"Warning: Empty data for index {name} ({ticker}). Assuming True.")
                results[name] = True
                continue
                
            # NaN 값 제거 (미장 개장 전 또는 휴일 빈 데이터 방지)
            df = df.dropna(subset=['Close'])
            
            if len(df) < 20:
                print(f"Warning: Not enough data points ({len(df)}) for index {name} ({ticker}) after dropping NaNs. Assuming True.")
                results[name] = True
                continue
            
            current_close = float(df['Close'].iloc[-1])
            sma20 = df['Close'].rolling(window=20).mean()
            current_sma20 = float(sma20.iloc[-1])
            
            is_above = current_close > current_sma20
            results[name] = is_above
            print(f"[{name}] Close: {current_close:,.2f} | SMA20: {current_sma20:,.2f} | Above 20MA: {is_above}")
        except Exception as e:
            print(f"Exception during market trend check for {name} ({ticker}): {e}. Assuming True.")
            results[name] = True
            
    return results.get("KOSPI", True), results.get("NASDAQ", True)

def get_intraday_bars(keyword: str, since_dt=None):
    """
    해당 종목의 최근 5분봉 데이터를 조회하여 (open, high, low, close) 튜플 리스트를 시간순으로 반환합니다.
    since_dt가 전달되면 그 시각 이후의 봉만 필터링합니다.
    """
    if keyword not in TICKER_MAP:
        return []
    ticker = TICKER_MAP[keyword]
    try:
        df = yf.Ticker(ticker).history(period="5d", interval="5m")
        if df.empty:
            return []
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
        if since_dt is not None:
            # since_dt tz 처리
            if since_dt.tzinfo is None:
                # KST 가정
                import datetime as dt_mod
                kst = dt_mod.timezone(dt_mod.timedelta(hours=9))
                since_dt = since_dt.replace(tzinfo=kst)
            df = df[df.index > since_dt]
        bars = []
        for _, row in df.iterrows():
            bars.append((float(row['Open']), float(row['High']), float(row['Low']), float(row['Close'])))
        return bars
    except Exception as e:
        print(f"Warning: Failed to fetch intraday bars for {keyword}: {e}")
        return []

def get_today_open(keyword: str):
    """
    해당 종목의 오늘 정규장 시초가(Open)를 조회합니다. 없으면 None 반환.
    """
    if keyword not in TICKER_MAP:
        return None
    ticker = TICKER_MAP[keyword]
    try:
        t = yf.Ticker(ticker)
        # fast_info open이 있을 경우
        try:
            op = getattr(t.fast_info, 'open', None)
            if op and op > 0:
                return float(op)
        except Exception:
            pass
        # 1일봉에서 Open 조회
        df = t.history(period="1d", interval="1m")
        if not df.empty:
            return float(df['Open'].iloc[0])
        df_d = t.history(period="5d")
        if not df_d.empty:
            return float(df_d['Open'].iloc[-1])
        return None
    except Exception as e:
        print(f"Warning: Failed to fetch today open for {keyword}: {e}")
        return None

if __name__ == "__main__":
    # 로컬 독립형 모듈 테스트
    print("Testing chart indicators...")
    res = get_stock_indicators("삼성전자")
    print(res)
    print("\nTesting market trend check...")
    kospi_ok, nasdaq_ok = check_market_trend()
    print(f"KOSPI OK: {kospi_ok} | NASDAQ OK: {nasdaq_ok} | Combined: {kospi_ok and nasdaq_ok}")
    print("\nTesting intraday bars...")
    bars = get_intraday_bars("삼성전자")
    print(f"Fetched {len(bars)} 5m bars. Last bar: {bars[-1] if bars else None}")
