import os
import json
from dotenv import load_dotenv

# 로컬 개발 시 .env 파일 로드
load_dotenv()

# API Keys & Credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")

# 구글 서비스 계정 JSON 파싱
GOOGLE_SERVICE_ACCOUNT_RAW = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SERVICE_ACCOUNT_INFO = None

if GOOGLE_SERVICE_ACCOUNT_RAW:
    try:
        GOOGLE_SERVICE_ACCOUNT_INFO = json.loads(GOOGLE_SERVICE_ACCOUNT_RAW)
    except Exception as e:
        print(f"Warning: Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

# 트레이딩 봇 상세 설정
TARGET_KEYWORDS = ["삼성전자", "SK하이닉스", "LG에너지솔루션", "삼성바이오로직스", "현대차"]
SIGNAL_THRESHOLD = 8
MAX_NEWS_PER_KEYWORD = 5  # 실행당 각 키워드별 탐색할 최신 뉴스 개수

# 키워드 매칭 필터용 동의어 사전 (제목에 이 단어 중 하나라도 포함되어야 AI 분석을 실행함)
KEYWORD_SYNONYMS = {
    "삼성전자": ["삼성전자", "삼성", "삼전"],
    "SK하이닉스": ["SK하이닉스", "하이닉스", "하닉"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG엔솔", "엔솔"],
    "삼성바이오로직스": ["삼성바이오로직스", "삼바", "삼성바이오"],
    "현대차": ["현대차", "현대자동차", "현대"]
}

