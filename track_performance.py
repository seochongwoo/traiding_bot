import time
from datetime import datetime, timedelta
import yfinance as yf
from gspread import Cell
from config import TICKER_MAP
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
            all_pos_rows = pos_sheet.get_all_values()
            if len(all_pos_rows) > 1:
                headers = all_pos_rows[0]
                for idx, row in enumerate(all_pos_rows[1:], start=2):
                    while len(row) < len(headers):
                        row.append("")
                    # 진입일자 | 종목코드 | 종목명 | 매수가 | 목표가 | 손절가 | 상태 | 청산일자 | 청산가 | 청산사유 | 수익률(%)
                    active_positions.append({
                        "date": row[0],
                        "symbol": row[1],
                        "name": row[2],
                        "buy_price": float(row[3]) if row[3] else 0.0,
                        "status": row[6],
                        "reason": row[9]
                    })
        except Exception as e:
            print(f"Warning: Failed to load active positions for matching: {e}")

    # 3. 뉴스 로그 전체 로드
    try:
        all_news_rows = news_sheet.get_all_values()
    except Exception as e:
        print(f"Error: Failed to fetch news rows: {e}")
        return

    if len(all_news_rows) <= 1:
        print("No news records to track.")
        return

    headers = all_news_rows[0]
    print(f"Loaded {len(all_news_rows) - 1} news records from '시트1'.")

    # 배치 업데이트용 셀 목록 리스트
    cells_to_update = []

    # 4. 각 기사별 1일/3일/5일 후 수익률 및 최종결과 추적 연산
    for idx, row in enumerate(all_news_rows[1:], start=2):
        while len(row) < len(headers):
            row.append("")

        entry_date_str = row[0]
        keyword = row[1]
        ticker = TICKER_MAP.get(keyword, "")
        buy_price = float(row[10]) if (len(row) > 10 and row[10]) else 0.0
        entry_yn = row[11].strip()

        # 추적이 필요 없는 행 건너뛰기
        if not ticker:
            continue

        # 1일후(Col 13), 3일후(Col 14), 5일후(Col 15), 최종결과(Col 16) 값 확인
        r1 = row[12].strip()
        r3 = row[13].strip()
        r5 = row[14].strip()
        final_result = row[15].strip()

        try:
            entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Warning: Failed to parse date '{entry_date_str}' at row {idx}. Skipping.")
            continue

        # 1. 1일/3일/5일 후 수익률 계산 (기입할 항목이 하나라도 비어있고 진입가격이 존재할 때)
        if buy_price > 0 and (not r1 or not r3 or not r5):
            print(f"\n[Row {idx}] Tracking performance for {keyword} ({ticker}) | Entry Price: {buy_price:,.0f}원...")
            
            # yfinance로 해당 날짜 이후 15일간의 데이터 획득
            try:
                start_date = entry_dt.strftime("%Y-%m-%d")
                df = yf.Ticker(ticker).history(start=start_date, period="15d")
                df = df.dropna(subset=['Close'])

                if not df.empty and len(df) > 0:
                    history_closes = df['Close'].tolist()
                    history_dates = df.index.strftime("%Y-%m-%d").tolist()
                    
                    entry_date_only = entry_date_str.split(" ")[0]
                    # 진입일에 해당하는 인덱스 찾기
                    entry_idx = -1
                    for i, d_str in enumerate(history_dates):
                        if d_str >= entry_date_only:
                            entry_idx = i
                            break
                    
                    if entry_idx != -1:
                        # 1일후 수익률 (i + 1)
                        if not r1 and (entry_idx + 1 < len(history_closes)):
                            c1 = history_closes[entry_idx + 1]
                            ret1 = ((c1 - buy_price) / buy_price) * 100
                            cells_to_update.append(Cell(row=idx, col=13, value=f"{ret1:+.2f}%"))
                            print(f"   - 1영업일 후 ({history_dates[entry_idx + 1]}): {c1:,.0f}원 ({ret1:+.2f}%)")
                        
                        # 3일후 수익률 (i + 3)
                        if not r3 and (entry_idx + 3 < len(history_closes)):
                            c3 = history_closes[entry_idx + 3]
                            ret3 = ((c3 - buy_price) / buy_price) * 100
                            cells_to_update.append(Cell(row=idx, col=14, value=f"{ret3:+.2f}%"))
                            print(f"   - 3영업일 후 ({history_dates[entry_idx + 3]}): {c3:,.0f}원 ({ret3:+.2f}%)")
                            
                        # 5일후 수익률 (i + 5)
                        if not r5 and (entry_idx + 5 < len(history_closes)):
                            c5 = history_closes[entry_idx + 5]
                            ret5 = ((c5 - buy_price) / buy_price) * 100
                            cells_to_update.append(Cell(row=idx, col=15, value=f"{ret5:+.2f}%"))
                            print(f"   - 5영업일 후 ({history_dates[entry_idx + 5]}): {c5:,.0f}원 ({ret5:+.2f}%)")
            except Exception as yf_err:
                print(f"   Warning: Failed to fetch yfinance data for {ticker}: {yf_err}")

        # 2. 최종결과 업데이트
        if entry_yn.startswith("Y"):
            # Active_Positions 탭과 대조하여 현재 상태 업데이트
            matched_status = "진행중"
            entry_date_only = entry_date_str.split(" ")[0]
            for pos in active_positions:
                if pos["name"] == keyword and pos["date"].startswith(entry_date_only):
                    if pos["status"] == "보유중":
                        matched_status = "진행중"
                    elif pos["status"] == "청산완료":
                        matched_status = pos["reason"] # "익절" 또는 "손절"
                    break
            
            if final_result != matched_status:
                cells_to_update.append(Cell(row=idx, col=16, value=matched_status))
                print(f"   - 최종결과 업데이트: {final_result} -> {matched_status}")
        else:
            # 진입하지 않은 기사
            if final_result != "미진입":
                cells_to_update.append(Cell(row=idx, col=16, value="미진입"))
                print(f"   - 최종결과 업데이트: {final_result} -> 미진입")

    # 5. 변경된 모든 셀 한 번에 묶어서 배치 업데이트 (API 호출 최소화)
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
