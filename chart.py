import yfinance as yf
import pandas as pd
from config import TICKER_MAP

def get_stock_indicators(keyword: str):
    """
    야후 파이낸스를 통해 해당 키워드 종목의 3개월 일봉 데이터를 조회하여
    현재가, RSI(14), ATR(14)을 계산해 반환합니다.
    """
    if keyword not in TICKER_MAP:
        print(f"Warning: '{keyword}' is not in TICKER_MAP. Skipping chart indicator check.")
        return None

    ticker = TICKER_MAP[keyword]
    print(f"Fetching chart data for {keyword} ({ticker}) via yfinance...")

    try:
        # MACD, ATR, RSI 계산을 안정적으로 하기 위해 3개월 데이터를 받습니다.
        df = yf.Ticker(ticker).history(period="3mo")

        if df.empty or len(df) < 26:
            print(f"Warning: Not enough data points fetched for {ticker} (Length: {len(df) if df is not None else 0}).")
            return None

        # 1. 현재가 (마지막 영업일 종가)
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

        indicators = {
            "current_price": current_price,
            "rsi": rsi,
            "atr": atr
        }

        print(f"[{keyword}] Price: {current_price:,.0f} | RSI: {rsi:.2f} | ATR: {atr:.2f}")
        return indicators

    except Exception as e:
        print(f"Exception during indicator calculation for {keyword} ({ticker}): {e}")
        return None

if __name__ == "__main__":
    # 로컬 독립형 모듈 테스트
    print("Testing chart indicators...")
    res = get_stock_indicators("삼성전자")
    print(res)
