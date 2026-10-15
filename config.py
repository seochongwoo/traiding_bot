import os
import json
from dotenv import load_dotenv

# 로컬 개발 시 .env 파일 로드
load_dotenv()

# API Keys & Credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Discord Webhooks (단일 DISCORD_WEBHOOK_URL 환경변수도 호환)
DISCORD_WEBHOOK_GENERAL = os.getenv("DISCORD_WEBHOOK_GENERAL") or os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_WEBHOOK_SELL = os.getenv("DISCORD_WEBHOOK_SELL") or os.getenv("DISCORD_WEBHOOK_URL")
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
SIGNAL_THRESHOLD = 7
MAX_NEWS_PER_KEYWORD = 5  # 실행당 각 키워드별 탐색할 최신 뉴스 개수

# 키워드 매칭 필터용 동의어 사전 (제목에 이 단어 중 하나라도 포함되어야 AI 분석을 실행함)
KEYWORD_SYNONYMS = {
    "삼성전자": ["삼성전자", "삼성", "삼전"],
    "SK하이닉스": ["SK하이닉스", "하이닉스", "하닉"],
    "LG에너지솔루션": ["LG에너지솔루션", "LG엔솔", "엔솔"],
    "삼성바이오로직스": ["삼성바이오로직스", "삼바", "삼성바이오"],
    "현대차": ["현대차", "현대자동차", "현대"]
}

# 야후 파이낸스 Ticker 매핑 사전
TICKER_MAP = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "현대차": "005380.KS"
}

# 설거지(고점 물림) 방지 필터 설정값
RSI_HIGH_LIMIT = 75
DISPARITY_LIMIT = 120

# 신규 매수 필터 설정값 (구버전 단일 필터 - 현재 진입 로직에서는 사용하지 않음)
RSI_BUY_LIMIT = 50

# 실행 모드 (python main.py --dry-run 시 시트/디스코드 쓰기 생략)
DRY_RUN = os.getenv("DRY_RUN") == "1"

# 정규장 시간 (KST) - 이 시간 밖의 시그널은 '진입대기'로 기록 후 다음 정규장에서 체결 판단
MARKET_OPEN_HHMM = (9, 0)
MARKET_ENTRY_CUTOFF_HHMM = (15, 20)
MAX_GAP_UP_PCT = 3.0          # 시그널가 대비 시초가 갭상승이 이 값 초과면 진입취소

# 트랙 A: 호재 모멘텀 돌파
MOMENTUM_SCORE_MIN = 7
MOMENTUM_RSI_MAX = 65
MOMENTUM_DISPARITY_MAX = 115

# 트랙 B: 과매도 눌림목 역발상 (거시 지수 필터 미적용)
CONTRARIAN_RSI_MAX = 35
CONTRARIAN_SCORE_MIN = 3

# 리스크 관리
TARGET_PCT_MIN, TARGET_PCT_MAX = 2.5, 5.0
STOP_PCT_MIN, STOP_PCT_MAX = 1.5, 3.0
BREAKEVEN_TRIGGER_PCT = 2.5   # 최고 수익률이 이 값 이상이면 손절가를 본절로 상향
BREAKEVEN_STOP_MULT = 1.003   # 본절 + 수수료
REENTRY_COOLDOWN_HOURS = 24

# 중복 기사 제거
DEDUP_JACCARD = 0.4
DEDUP_WINDOW_HOURS = 12


