import gspread
from config import GOOGLE_SERVICE_ACCOUNT_INFO, GOOGLE_SPREADSHEET_ID

def get_sheets_client():
    """
    구글 서비스 계정 자격 증명을 바탕으로 gspread 클라이언트를 반환합니다.
    """
    if not GOOGLE_SERVICE_ACCOUNT_INFO:
        print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON env var is missing.")
        return None
        
    try:
        gc = gspread.service_account_from_dict(GOOGLE_SERVICE_ACCOUNT_INFO)
        return gc
    except Exception as e:
        print(f"Exception during Google sheets authentication: {e}")
        return None

def open_worksheet(tab_name: str):
    """
    설정된 GOOGLE_SPREADSHEET_ID와 워크시트 탭 이름을 사용하여 구글 시트 탭을 엽니다.
    해당 탭이 존재하지 않으면 새로 생성하고 기본 헤더를 초기화합니다.
    """
    gc = get_sheets_client()
    if not gc:
        return None
        
    if not GOOGLE_SPREADSHEET_ID:
        print("Warning: GOOGLE_SPREADSHEET_ID env var is missing.")
        return None
        
    try:
        sh = gc.open_by_key(GOOGLE_SPREADSHEET_ID)
        
        # 탭 열기 시도, 없으면 추가
        try:
            sheet = sh.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{tab_name}' not found. Creating a new one...")
            sheet = sh.add_worksheet(title=tab_name, rows="1000", cols="20")
        
        # 비어있으면 헤더 작성
        row1 = sheet.row_values(1)
        if not row1:
            if tab_name == "시트1":
                headers = ["일시", "검색 키워드", "뉴스 제목", "URL", "AI 스코어", "AI 요약", "주요 키워드", "RSI", "이격도", "MACD 상태"]
            elif tab_name == "Active_Positions":
                headers = ["진입일자", "종목코드", "종목명", "매수가", "목표가", "손절가", "상태"]
            else:
                headers = []
                
            if headers:
                sheet.append_row(headers)
            
        return sheet
    except Exception as e:
        print(f"Exception while opening spreadsheet tab '{tab_name}': {e}")
        return None

def fetch_existing_urls(sheet) -> set:
    """
    시트1 탭의 4번째 열(URL)에 기록된 기존 URL 목록을 수집하여 반환합니다.
    """
    if not sheet:
        return set()
        
    try:
        urls = sheet.col_values(4)
        if len(urls) <= 1:
            return set()
        return set(urls[1:])
    except Exception as e:
        print(f"Exception while fetching existing URLs: {e}")
        return set()

def append_news_record(sheet, datetime_str: str, keyword: str, title: str, url: str, score: int, 
                       summary: str, keywords: list, rsi=None, disparity=None, macd_dead_cross=None) -> bool:
    """
    분석 완료된 뉴스 한 건과 보조지표 데이터를 시트1 스프레드시트 탭에 행으로 추가합니다.
    """
    if not sheet:
        return False
        
    try:
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
        
        # 보조지표 포맷팅
        rsi_val = round(rsi, 2) if rsi is not None else ""
        disparity_val = round(disparity, 2) if disparity is not None else ""
        macd_val = "데드크로스(하락)" if macd_dead_cross is True else ("골든크로스(상승)" if macd_dead_cross is False else "")
        
        row = [datetime_str, keyword, title, url, score, summary, keywords_str, rsi_val, disparity_val, macd_val]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"Exception while appending news record to sheet: {e}")
        return False

def fetch_active_positions(sheet) -> list:
    """
    Active_Positions 탭에서 현재 '보유중' 상태인 종목 리스트를 가져옵니다.
    각 항목은 구글 시트 행 번호(row_num, 1-indexed)를 포함하여 반환합니다.
    """
    positions = []
    if not sheet:
        return positions
        
    try:
        all_rows = sheet.get_all_values()
        if len(all_rows) <= 1:
            return positions
            
        headers = all_rows[0]
        # 헤더 아래 데이터 행 순회 (2번째 행부터 데이터 시작)
        for idx, row in enumerate(all_rows[1:], start=2):
            # 행 데이터 패딩 처리
            while len(row) < len(headers):
                row.append("")
                
            status = row[6].strip() if len(row) > 6 else ""
            if status == "보유중":
                positions.append({
                    "row_num": idx,
                    "date": row[0],
                    "symbol": row[1],
                    "name": row[2],
                    "buy_price": float(row[3]) if row[3] else 0.0,
                    "target_price": float(row[4]) if row[4] else 0.0,
                    "stop_loss": float(row[5]) if row[5] else 0.0,
                    "status": status
                })
        return positions
    except Exception as e:
        print(f"Exception while fetching active positions: {e}")
        return positions

def update_position_status(sheet, row_num: int, new_status: str = "청산완료") -> bool:
    """
    구글 시트의 지정 행 번호의 상태 열(7번째 열)을 업데이트합니다.
    """
    if not sheet:
        return False
        
    try:
        sheet.update_cell(row_num, 7, new_status)
        return True
    except Exception as e:
        print(f"Exception while updating position status at row {row_num}: {e}")
        return False

def add_active_position(sheet, date_str: str, symbol: str, name: str, buy_price: float, target_price: float, stop_loss: float, status: str = "보유중") -> bool:
    """
    새로 진입(매수)한 종목 정보를 Active_Positions 탭에 행으로 추가합니다.
    """
    if not sheet:
        return False
        
    try:
        row = [date_str, symbol, name, buy_price, target_price, stop_loss, status]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"Exception while adding active position to sheet: {e}")
        return False

if __name__ == "__main__":
    # 로컬 개발 환경에서 스프레드시트 탭 분리 연동 테스트
    print("Testing spreadsheet multi-tab connection...")
    news_sheet = open_worksheet("시트1")
    pos_sheet = open_worksheet("Active_Positions")
    
    if news_sheet and pos_sheet:
        print("Success! Both 시트1 and Active_Positions tabs are configured.")
        active_pos = fetch_active_positions(pos_sheet)
        print(f"Current active positions count: {len(active_pos)}")
        for pos in active_pos:
            print(pos)
    else:
        print("Failed to open sheets. Please check authorization or spreadsheet ID.")
