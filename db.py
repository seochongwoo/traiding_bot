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
        # Dictionary 정보를 직접 사용하여 인증
        gc = gspread.service_account_from_dict(GOOGLE_SERVICE_ACCOUNT_INFO)
        return gc
    except Exception as e:
        print(f"Exception during Google sheets authentication: {e}")
        return None

def open_worksheet():
    """
    설정된 GOOGLE_SPREADSHEET_ID를 사용하여 스프레드시트의 첫 번째 워크시트를 엽니다.
    기본 헤더가 구성되어 있지 않다면 헤더를 자동 추가합니다.
    """
    gc = get_sheets_client()
    if not gc:
        return None
        
    if not GOOGLE_SPREADSHEET_ID:
        print("Warning: GOOGLE_SPREADSHEET_ID env var is missing.")
        return None
        
    try:
        sh = gc.open_by_key(GOOGLE_SPREADSHEET_ID)
        sheet = sh.sheet1
        
        # 첫 번째 행을 확인하여 비어있다면 헤더 작성
        row1 = sheet.row_values(1)
        if not row1:
            headers = ["일시", "검색 키워드", "뉴스 제목", "URL", "AI 스코어", "AI 요약", "주요 키워드"]
            sheet.append_row(headers)
            
        return sheet
    except Exception as e:
        print(f"Exception while opening spreadsheet {GOOGLE_SPREADSHEET_ID}: {e}")
        return None

def fetch_existing_urls(sheet) -> set:
    """
    중복 기사 필터링을 위해 구글 스프레드시트의 4번째 열(URL)에 기록된 기존 URL 목록을 반환합니다.
    """
    if not sheet:
        return set()
        
    try:
        # 4번째 열(URL) 값을 전체 로드
        urls = sheet.col_values(4)
        if len(urls) <= 1:
            return set()
        # 헤더를 제외한 URL 세트 반환
        return set(urls[1:])
    except Exception as e:
        print(f"Exception while fetching existing URLs: {e}")
        return set()

def append_news_record(sheet, datetime_str: str, keyword: str, title: str, url: str, score: int, summary: str, keywords: list) -> bool:
    """
    분석 완료된 뉴스 한 건을 구글 스프레드시트에 행으로 추가합니다.
    """
    if not sheet:
        print("Warning: Spreadsheet connection is unavailable. Skipping append.")
        return False
        
    try:
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
        row = [datetime_str, keyword, title, url, score, summary, keywords_str]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"Exception while appending news record to sheet: {e}")
        return False

if __name__ == "__main__":
    # 로컬 개발 환경에서 스프레드시트 연동 테스트
    print("Testing spreadsheet connection...")
    sheet = open_worksheet()
    if sheet:
        print("Spreadsheet opened successfully!")
        urls = fetch_existing_urls(sheet)
        print(f"Fetched {len(urls)} existing news URLs.")
    else:
        print("Failed to open spreadsheet. Check your .env file or share permissions.")
