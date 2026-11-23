import time
from datetime import datetime, timedelta
import yfinance as yf
from gspread import Cell
from config import TICKER_MAP, PENDING_MAX_AGE_HOURS
from db import open_worksheet


def run_performance_tracking():
    print("==================================================")
    print(f"Starting Performance Tracking Batch Script at {datetime.utcnow() + timedelta(hours=9)} KST")
    print("==================================================")

    # 1. 시트1 (뉴스 로그) 및 Active_Positions (보유 종목) 열기
    news_sheet = open_worksheet("시트1")
    pos_sheet = open_worksheet("Active_Positions")

    if not news_sheet:
        print("Error: Could not open '시트1' worksheet.")
        return

    # 2. 보유 종목 리스트 로드 (상태 매칭용)
    active_positions = []
    if pos_sheet:
        try:
            all_pos_rows = pos_sheet.get_values()
            if len(all_pos_rows) > 1:
                headers = all_pos_rows[0]
                for idx, row in enumerate(all_pos_rows[1:], start=2):
                    while len(row) < len(headers):
                        row.append("")
                    pos_dt = None
                    try:
                        pos_dt = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                    active_positions.append({
                        "date": row[0].strip(),
                        "dt": pos_dt,
                        "symbol": row[1].strip(),
                        "name": row[2].strip(),
                        "buy_price": float(row[3]) if row[3] else 0.0,
                        "status": row[6].strip(),
                        "reason": row[9].strip(),
                    })
        except Exception as e:
            print(f"Warning: Failed to load active positions for matching: {e}")

    # 3. 뉴스 로그 전체 로드
    try:
        all_news_rows = news_sheet.get_values()
    except Exception as e:
        print(f"Error: Failed to fetch news rows: {e}")
        return

    if len(all_news_rows) <= 1:
        print("No news records to track.")
        return

    headers = all_news_rows[0]
    print(f"Loaded {len(all_news_rows) - 1} news records from '시트1'.")

    # 4. 수익률 미기입 행들의 가장 이른 날짜를 파악해 종목별(최대 5종목) yfinance 일봉을 단 1회씩만 사전 캐싱
    earliest_dt_by_ticker = {}
    for row in all_news_rows[1:]:
        while len(row) < len(headers):
            row.append("")
        keyword = row[1].strip()
        ticker = TICKER_MAP.get(keyword, "")
        if not ticker:
            continue
        buy_price = float(row[10]) if (len(row) > 10 and row[10]) else 0.0
        r1, r3, r5 = row[12].strip(), row[13].strip(), row[14].strip()
        if buy_price > 0 and (not r1 or not r3 or not r5):
            try:
                dt = datetime.strptime(row[0].strip(), "%Y-%m-%d %H:%M:%S")
                if ticker not in earliest_dt_by_ticker or dt < earliest_dt_by_ticker[ticker]:
                    earliest_dt_by_ticker[ticker] = dt
            except Exception:
                continue

    ticker_history_cache = {}
    for ticker, min_dt in earliest_dt_by_ticker.items():
        try:
            start_date = (min_dt - timedelta(days=7)).strftime("%Y-%m-%d")
            print(f"Pre-fetching daily history for {ticker} since {start_date}...")
            df = yf.Ticker(ticker).history(start=start_date, auto_adjust=False)
            df = df.dropna(subset=["Close"])
            if not df.empty:
                ticker_history_cache[ticker] = (
                    df.index.strftime("%Y-%m-%d").tolist(),
                    df["Close"].tolist(),
                )
        except Exception as e:
            print(f"Warning: Failed to pre-fetch history for {ticker}: {e}")

    # 배치 업데이트용 셀 목록 리스트
    cells_to_update = []

    # 5. 각 기사별 1일/3일/5일 후 수익률 및 최종결과 추적 연산
    for idx, row in enumerate(all_news_rows[1:], start=2):
        while len(row) < len(headers):
            row.append("")

        entry_date_str = row[0].strip()
        keyword = row[1].strip()
        ticker = TICKER_MAP.get(keyword, "")
        buy_price = float(row[10]) if (len(row) > 10 and row[10]) else 0.0
        entry_yn = row[11].strip()

        if not ticker:
            continue

        r1 = row[12].strip()
        r3 = row[13].strip()
        r5 = row[14].strip()
        final_result = row[15].strip()

        try:
            entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Warning: Failed to parse date '{entry_date_str}' at row {idx}. Skipping.")
            continue

        # 1. 1일/3일/5일 후 수익률 계산 (사전 캐싱된 일봉 사용)
        if buy_price > 0 and (not r1 or not r3 or not r5) and ticker in ticker_history_cache:
            history_dates, history_closes = ticker_history_cache[ticker]
            entry_date_only = entry_date_str.split(" ")[0]
            entry_idx = -1
            for i in range(len(history_dates) - 1, -1, -1):
                if history_dates[i] <= entry_date_only:
                    entry_idx = i
                    break

            if entry_idx != -1:
                def format_return(ret: float, max_normal: float) -> str:
                    if abs(ret) > max_normal:
                        return f"검증필요({ret:+.2f}%)"
                    return f"{ret:+.2f}%"

                if not r1 and (entry_idx + 1 < len(history_closes)):
                    c1 = history_closes[entry_idx + 1]
                    ret1 = ((c1 - buy_price) / buy_price) * 100
                    cells_to_update.append(Cell(row=idx, col=13, value=format_return(ret1, 30.0)))

                if not r3 and (entry_idx + 3 < len(history_closes)):
                    c3 = history_closes[entry_idx + 3]
                    ret3 = ((c3 - buy_price) / buy_price) * 100
                    cells_to_update.append(Cell(row=idx, col=14, value=format_return(ret3, 60.0)))

                if not r5 and (entry_idx + 5 < len(history_closes)):
                    c5 = history_closes[entry_idx + 5]
                    ret5 = ((c5 - buy_price) / buy_price) * 100
                    cells_to_update.append(Cell(row=idx, col=15, value=format_return(ret5, 80.0)))

        # 2. 최종결과 업데이트 ('Y-A/B' 정규장 진입 및 '대기-A/B' 장외 대기주문 모두 매칭)
        if entry_yn.startswith("Y") or entry_yn.startswith("대기"):
            matched_status = "진행중" if entry_yn.startswith("Y") else "대기중"
            entry_date_only = entry_date_str.split(" ")[0]
            for pos in active_positions:
                if pos["name"] != keyword:
                    continue
                is_time_match = pos["date"].startswith(entry_date_only)
                if not is_time_match and pos["dt"] is not None:
                    diff_hours = (pos["dt"] - entry_dt).total_seconds() / 3600.0
                    is_time_match = (-1.0 <= diff_hours <= PENDING_MAX_AGE_HOURS)
                if is_time_match:
                    if pos["status"] == "보유중":
                        matched_status = "진행중"
                    elif pos["status"] == "진입대기":
                        matched_status = "대기중"
                    elif pos["status"] == "진입취소":
                        matched_status = "진입취소"
                    elif pos["status"] == "청산완료":
                        matched_status = pos["reason"] or "청산완료"
                    break

            if final_result != matched_status:
                cells_to_update.append(Cell(row=idx, col=16, value=matched_status))
                print(f"   - [Row {idx}] 최종결과 업데이트: {final_result} -> {matched_status}")
        else:
            if final_result != "미진입":
                cells_to_update.append(Cell(row=idx, col=16, value="미진입"))

    # 6. 변경된 모든 셀 한 번에 묶어서 배치 업데이트 (API 호출 최소화)
    if cells_to_update:
        print(f"\nSending batch update of {len(cells_to_update)} cells to Google Sheets...")
        try:
            news_sheet.update_cells(cells_to_update)
            print("Successfully updated all cells in one batch call!")
        except Exception as batch_err:
            print(f"Error during batch update: {batch_err}")
    else:
        print("\nNo performance metrics need updating today.")

    print("\n==================================================")
    print("Performance Tracking Batch Completed.")
    print("==================================================")


if __name__ == "__main__":
    run_performance_tracking()
