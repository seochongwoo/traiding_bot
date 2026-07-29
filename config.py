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
TARGET_KEYWORDS = ["삼성전자", "SK하이닉스", "테슬라"]
SIGNAL_THRESHOLD = 8
MAX_NEWS_PER_KEYWORD = 5  # 실행당 각 키워드별 탐색할 최신 뉴스 개수
