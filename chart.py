import yfinance as yf
import pandas as pd
from config import TICKER_MAP

def get_stock_indicators(keyword):
    """
    야후 파이낸스를 통해 해당 키워드 종목의 3개월 일봉 데이터를 조회하여
    RSI(14), 이격도(20), MACD 데드크로스 여부를 계산해 반환합니다.
    """
    if keyword not in TICKER_MAP:
        print(f"Warning: '{keyword}' is not in TICKER_MAP. Skipping chart indicator check.")
        return None

    ticker = TICKER_MAP[keyword]
    print(f"Fetching chart data for {keyword} ({ticker}) via yfinance...")

    try:
        # MACD(26) 및 이격도(20)를 안정적으로 계산하기 위해 3개월 데이터를 받습니다.
        df = yf.Ticker(ticker).history(period="3mo")

        if df.empty or len(df) < 26:
            print(f"Warning: Not enough data points fetched for {ticker} (Length: {len(df) if df is not None else 0}).")
            return None

        # 1. RSI (14일 기준, 와일더 지수이동평균 방식)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).copy()
        loss = -delta.where(delta < 0, 0).copy()

        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()

        rs = avg_gain / avg_loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1])

        # 2. 이격도 (20일 기준)
        sma20 = df['Close'].rolling(window=20).mean()
        latest_sma20 = float(sma20.iloc[-1])
        current_price = float(df['Close'].iloc[-1])
        disparity = float((current_price / latest_sma20) * 100)

        # 3. MACD 및 Signal (12, 26, 9)
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
            "disparity": disparity,
            "macd_line": latest_macd,
            "macd_signal": latest_signal,
            "macd_dead_cross": macd_dead_cross
        }

        print(f"[{keyword}] Price: {current_price:,.0f} | RSI: {rsi:.2f} | Disparity: {disparity:.2f}% | MACD DeadCross: {macd_dead_cross}")
        return indicators

    except Exception as e:
        print(f"Exception during indicator calculation for {keyword} ({ticker}): {e}")
        return None

if __name__ == "__main__":
    # 로컬 독립형 모듈 테스트
    print("Testing chart indicator calculations...")
    res = get_stock_indicators("삼성전자")
    print(res)
