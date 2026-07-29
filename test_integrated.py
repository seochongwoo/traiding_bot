import time
import sys
from datetime import datetime, timedelta
from config import TARGET_KEYWORDS, SIGNAL_THRESHOLD
from crawler import fetch_news_list, get_news_content

# Windows 콘솔 인코딩 문제를 해결하기 위해 표준 출력을 UTF-8로 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# --- Mocking DB Module ---
class MockSheet:
    def __init__(self):
        self.records = []
        self.existing_urls = {
            # 여기에 이미 처리된 기사의 가짜 URL을 넣어서 필터링 동작을 테스트할 수 있습니다.
            "https://www.example.com/already-processed-news-url"
        }
        
    def col_values(self, index):
        if index == 4: # URL column
            return ["URL"] + list(self.existing_urls)
        return []

    def append_row(self, row):
        self.records.append(row)
        print(f"   [MOCK-DB] 행 추가 완료: {row[:4]}... [Score: {row[4]}]")
        return True

def mock_open_worksheet():
    print("   [MOCK-DB] 구글 시트 연결 중... (시뮬레이션)")
    return MockSheet()

def mock_fetch_existing_urls(sheet):
    print("   [MOCK-DB] 기존 처리된 뉴스 URL 수집 중...")
    return sheet.existing_urls

def mock_append_news_record(sheet, datetime_str, keyword, title, url, score, summary, keywords):
    return sheet.append_row([datetime_str, keyword, title, url, score, summary, ", ".join(keywords)])

# --- Mocking Analyzer Module ---
def mock_analyze_news_sentiment(keyword, title, content):
    print("   [MOCK-AI] Gemini API 호출 중... (시뮬레이션)")
    # 테스트를 위해 제목에 특정 키워드가 있거나 홀수/짝수 인덱스에 따라 임의의 시그널 점수를 줍니다.
    # 기본은 +9 (호재) 점수로 고정 시뮬레이션
    simulated_score = 9
    if "하락" in title or "우려" in title or "급락" in title:
        simulated_score = -9
    
    return {
        "score": simulated_score,
        "summary": "- [시뮬레이션 요약 1] 본문 수집 데이터가 정상적으로 AI 모델로 전송되었습니다.\n- [시뮬레이션 요약 2] 해당 뉴스는 시장의 강력한 심리적 요인으로 작용할 것입니다.\n- [시뮬레이션 요약 3] 단기 주가 상승 모멘텀이 매우 강력합니다.",
        "keywords": [keyword, "반도체", "호재"]
    }

# --- Mocking Notifier Module ---
def mock_send_discord_signal(keyword, title, url, score, summary, keywords):
    print("   [MOCK-DISCORD] Discord 웹훅 시그널 발송 시뮬레이션:")
    color = "🟢 녹색 (매수)" if score > 0 else "🔴 적색 (매도)"
    print(f"   --------------------------------------------------")
    print(f"   📢 [시그널 발생] {keyword} (점수: {score:+})")
    print(f"   - 색상 테마: {color}")
    print(f"   - 뉴스 제목: {title}")
    print(f"   - 기사 URL: {url}")
    print(f"   - 핵심 키워드: {', '.join(keywords)}")
    print(f"   - AI 요약:\n{summary}")
    print(f"   --------------------------------------------------")
    return True

# --- 통합 파이프라인 시뮬레이터 실행 ---
def run_integrated_simulation():
    print("==================================================")
    print("🚀 서버리스 AI 트레이딩 봇 통합 테스트 (시뮬레이션)")
    print("   실제 API 요청을 보내지 않고 전체 워크플로우를 테스트합니다.")
    print("==================================================")

    # 1. 가짜 구글 시트 연결
    sheet = mock_open_worksheet()
    existing_urls = mock_fetch_existing_urls(sheet)
    print(f"   기존 가짜 DB URL 개수: {len(existing_urls)}")

    new_articles_count = 0
    alerts_sent_count = 0

    # 2. 키워드 탐색 (크롤링만 실제 수행)
    for keyword in TARGET_KEYWORDS[:2]:  # 테스트 속도를 위해 처음 2개 키워드만 탐색
        print(f"\n👉 대상 키워드: '{keyword}'")
        print("   실제 네이버 검색 데이터 크롤링을 시도합니다...")
        
        news_items = fetch_news_list(keyword, limit=2)
        print(f"   -> 실제 네이버 검색 결과 {len(news_items)}건 수집 완료.")

        for item in news_items:
            url_identifier = item["naver_news_link"] if item["naver_news_link"] else item["original_link"]
            
            if url_identifier in existing_urls:
                print(f"   -> [스킵] 이미 처리된 기사 URL: {url_identifier}")
                continue
                
            print(f"\n   [*] 신규 기사 분석 시작: '{item['title']}'")
            
            # 본문 크롤링 시뮬레이션
            news_content = ""
            if item["naver_news_link"]:
                print("   [크롤러] Naver 뉴스 본문 텍스트 수집 중...")
                news_content = get_news_content(item["naver_news_link"])
            
            if not news_content:
                news_content = item["snippet"]
            
            print(f"   -> 수집된 분석 텍스트 크기: {len(news_content)}자")

            # AI 분석 시뮬레이션
            analysis = mock_analyze_news_sentiment(keyword, item["title"], news_content)
            score = analysis["score"]
            summary = analysis["summary"]
            extracted_keywords = analysis["keywords"]

            # 가짜 구글 시트에 기록
            kst_now = datetime.utcnow() + timedelta(hours=9)
            datetime_str = kst_now.strftime("%Y-%m-%d %H:%M:%S")

            mock_append_news_record(
                sheet=sheet,
                datetime_str=datetime_str,
                keyword=keyword,
                title=item["title"],
                url=url_identifier,
                score=score,
                summary=summary,
                keywords=extracted_keywords
            )
            
            existing_urls.add(url_identifier)
            new_articles_count += 1

            # 매매 시그널 임계값 조건 필터링 검증
            if abs(score) >= SIGNAL_THRESHOLD:
                mock_send_discord_signal(
                    keyword=keyword,
                    title=item["title"],
                    url=url_identifier,
                    score=score,
                    summary=summary,
                    keywords=extracted_keywords
                )
                alerts_sent_count += 1

            time.sleep(0.5)

    print("\n==================================================")
    print("🎉 시뮬레이션 통합 테스트 완료 요약:")
    print(f" - 분석 완료한 신규 뉴스 기사 수: {new_articles_count}개")
    print(f" - 조건 부합 및 디스코드 전송 시뮬레이션 횟수: {alerts_sent_count}회")
    print(f" - 시뮬레이션 DB 누적 행 개수: {len(sheet.records)}개")
    print("==================================================")

if __name__ == "__main__":
    run_integrated_simulation()
