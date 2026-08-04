import time
from datetime import datetime, timedelta
import yfinance as yf
from config import TICKER_MAP
from db import open_worksheet, fetch_active_positions

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

    # 4. 각 기사별 1일/3일/5일 후 수익률 및 최종결과 추적 연산
    for idx, row in enumerate(all_news_rows[1:], start=2):
        while len(row) < len(headers):
            row.append("")

        entry_date_str = row[0]
        keyword = row[1]
        ticker = TICKER_MAP.get(keyword, "")
        entry_yn = row[10].strip()

        # 추적이 필요 없는 행 건너뛰기
        if not ticker:
            continue

        # 1일후(Col 12), 3일후(Col 13), 5일후(Col 14), 최종결과(Col 15) 값 확인
        r1 = row[11].strip()
        r3 = row[12].strip()
        r5 = row[13].strip()
        final_result = row[14].strip()

        needs_update = False
        updates = {}

        try:
            entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Warning: Failed to parse date '{entry_date_str}' at row {idx}. Skipping.")
            continue

        # 1. 1일/3일/5일 후 수익률 계산 (추적할 항목이 하나라도 비어있으면 데이터 로드)
        if entry_yn == "Y" and (not r1 or not r3 or not r5):
            print(f"\n[Row {idx}] Tracking performance for {keyword} ({ticker}) entered at {entry_date_str}...")
            
            # 매수가 매칭 (Active_Positions에서 탐색, 없으면 당일 종가 사용)
            buy_price = 0.0
            # 날짜 일치 여부 확인 (시간 제외 일자 비교)
            entry_date_only = entry_date_str.split(" ")[0]
            for pos in active_positions:
                if pos["name"] == keyword and pos["date"].startswith(entry_date_only):
                    buy_price = pos["buy_price"]
                    break

            # yfinance로 해당 날짜 이후 15일간의 데이터 획득
            try:
                # 시작 날짜는 진입일로 설정
                start_date = entry_dt.strftime("%Y-%m-%d")
                # 주말 및 휴일을 감안해 넉넉하게 15일간 데이터 다운로드
                df = yf.Ticker(ticker).history(start=start_date, period="15d")
                df = df.dropna(subset=['Close'])

                if not df.empty and len(df) > 0:
                    history_closes = df['Close'].tolist()
                    history_dates = df.index.strftime("%Y-%m-%d").tolist()
                    
                    # 진입일에 해당하는 인덱스 찾기
                    entry_idx = -1
                    for i, d_str in enumerate(history_dates):
                        if d_str >= entry_date_only:
                            entry_idx = i
                            break
                    
                    if entry_idx != -1:
                        # 매수가가 시트 매칭되지 않았다면 진입 당일 종가를 기준 매수가로 사용
                        if buy_price == 0.0:
                            buy_price = history_closes[entry_idx]
                        
                        # 1일후 수익률 (i + 1)
                        if not r1 and (entry_idx + 1 < len(history_closes)):
                            c1 = history_closes[entry_idx + 1]
                            ret1 = ((c1 - buy_price) / buy_price) * 100
                            updates[12] = f"{ret1:+.2f}%"
                            print(f"   - 1영업일 후 ({history_dates[entry_idx + 1]}): {c1:,.0f}원 ({ret1:+.2f}%)")
                        
                        # 3일후 수익률 (i + 3)
                        if not r3 and (entry_idx + 3 < len(history_closes)):
                            c3 = history_closes[entry_idx + 3]
                            ret3 = ((c3 - buy_price) / buy_price) * 100
                            updates[13] = f"{ret3:+.2f}%"
                            print(f"   - 3영업일 후 ({history_dates[entry_idx + 3]}): {c3:,.0f}원 ({ret3:+.2f}%)")
                            
                        # 5일후 수익률 (i + 5)
                        if not r5 and (entry_idx + 5 < len(history_closes)):
                            c5 = history_closes[entry_idx + 5]
                            ret5 = ((c5 - buy_price) / buy_price) * 100
                            updates[14] = f"{ret5:+.2f}%"
                            print(f"   - 5영업일 후 ({history_dates[entry_idx + 5]}): {c5:,.0f}원 ({ret5:+.2f}%)")
            except Exception as yf_err:
                print(f"   Warning: Failed to fetch yfinance data for {ticker}: {yf_err}")

        # 2. 최종결과 업데이트
        if entry_yn == "Y":
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
                updates[15] = matched_status
                print(f"   - 최종결과 업데이트: {final_result} -> {matched_status}")
        else:
            # 진입하지 않은 기사
            if final_result != "미진입":
                updates[15] = "미진입"
                print(f"   - 최종결과 업데이트: {final_result} -> 미진입")

        # 5. 변경된 열 데이터 구글 시트에 업데이트
        if updates:
            for col_idx, value in updates.items():
                try:
                    news_sheet.update_cell(idx, col_idx, value)
                    # 구글 API 속도 조절
                    time.sleep(0.5)
                except Exception as cell_err:
                    print(f"Error updating cell at row {idx}, col {col_idx}: {cell_err}")

    print("\n==================================================")
    print("Performance Tracking Batch Completed.")
    print("==================================================")

if __name__ == "__main__":
    run_performance_tracking()
