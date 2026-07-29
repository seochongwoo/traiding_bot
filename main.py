import time
from datetime import datetime, timedelta
from config import TARGET_KEYWORDS, SIGNAL_THRESHOLD, MAX_NEWS_PER_KEYWORD, KEYWORD_SYNONYMS
from crawler import fetch_news_list, get_news_content
from db import open_worksheet, fetch_existing_urls, append_news_record
from analyzer import analyze_news_sentiment
from notifier import send_discord_signal

def run_trading_bot():
    print("==================================================")
    print(f"Starting Serverless AI Trading Bot at {datetime.utcnow() + timedelta(hours=9)} KST")
    print("==================================================")

    # 1. 구글 스프레드시트 열기
    print("Connecting to Google Sheets...")
    sheet = open_worksheet()
    if not sheet:
        print("Warning: Google Sheets is not connected. The bot will run without database logging.")
        existing_urls = set()
    else:
        print("Successfully connected to Google Sheets.")
        # 기존 처리된 뉴스 URL 수집
        existing_urls = fetch_existing_urls(sheet)
        print(f"Loaded {len(existing_urls)} existing URLs from Sheet.")

    # 2. 키워드별 뉴스 탐색 및 분석 진행
    new_articles_count = 0
    alerts_sent_count = 0

    for keyword in TARGET_KEYWORDS:
        print(f"\nTargeting Keyword: '{keyword}'")
        print(f"Fetching latest {MAX_NEWS_PER_KEYWORD} news items...")
        
        # 최신 검색 리스트 크롤링
        news_items = fetch_news_list(keyword, limit=MAX_NEWS_PER_KEYWORD)
        print(f"Found {len(news_items)} news items for '{keyword}'.")

        for item in news_items:
            # 중복 체크 대상 URL 설정
            # 네이버 뉴스 상세 링크가 있으면 그것을, 없으면 오리지널 링크를 식별자로 사용
            url_identifier = item["naver_news_link"] if item["naver_news_link"] else item["original_link"]
            
            if url_identifier in existing_urls:
                # 이미 처리한 기사인 경우 스킵
                continue
                
            # 제목 키워드 필터링 적용 (노이즈 뉴스 제거로 AI API 호출 및 스프레드시트 낭비 방지)
            synonyms = KEYWORD_SYNONYMS.get(keyword, [keyword])
            has_keyword = any(syn in item["title"] for syn in synonyms)
            if not has_keyword:
                print(f"   -> [필터링 스킵] 제목에 관련 키워드가 없어 스킵합니다: '{item['title']}'")
                continue
                
            print(f"\nProcessing new article: '{item['title']}'")
            print(f"URL: {url_identifier}")
            
            # 본문 내용 가져오기 (네이버 뉴스 링크가 존재하면 본문 파싱, 없으면 검색 스니펫 활용)
            news_content = ""
            if item["naver_news_link"]:
                print("Crawling full article body from Naver News...")
                news_content = get_news_content(item["naver_news_link"])
            
            if not news_content:
                print("Fallback: Using search snippet for analysis.")
                news_content = item["snippet"]

            # AI 분석 (Gemini API)
            print("Requesting Gemini AI analysis...")
            analysis = analyze_news_sentiment(keyword, item["title"], news_content)
            score = analysis["score"]
            summary = analysis["summary"]
            extracted_keywords = analysis["keywords"]
            
            print(f"Analysis result -> Score: {score:+}, Summary: {summary[:60]}...")

            # KST 시간 생성
            kst_now = datetime.utcnow() + timedelta(hours=9)
            datetime_str = kst_now.strftime("%Y-%m-%d %H:%M:%S")

            # 구글 스프레드시트에 저장
            saved_to_db = False
            if sheet:
                saved_to_db = append_news_record(
                    sheet=sheet,
                    datetime_str=datetime_str,
                    keyword=keyword,
                    title=item["title"],
                    url=url_identifier,
                    score=score,
                    summary=summary,
                    keywords=extracted_keywords
                )
                if saved_to_db:
                    print("Recorded to Google Sheets successfully.")
            
            # 중복 방지를 위해 메모리 상의 URL 세트에도 추가
            existing_urls.add(url_identifier)
            new_articles_count += 1

            # 매매 시그널 체크 (임계치 만족 시 Discord 전송)
            if abs(score) >= SIGNAL_THRESHOLD:
                print(f"Signal detected! Score {score:+} crosses threshold {SIGNAL_THRESHOLD}. Sending Discord alert...")
                sent = send_discord_signal(
                    keyword=keyword,
                    title=item["title"],
                    url=url_identifier,
                    score=score,
                    summary=summary,
                    keywords=extracted_keywords
                )
                if sent:
                    alerts_sent_count += 1
            else:
                print(f"No signal triggered. Score {score:+} is within bounds ({SIGNAL_THRESHOLD}).")

            # Gemini API Free Tier 속도 제한(15 RPM) 준수를 위해 4.5초 슬립 적용
            time.sleep(4.5)

    print("\n==================================================")
    print("Execution Finished Summary:")
    print(f"- Total new articles analyzed: {new_articles_count}")
    print(f"- Total Discord alerts sent: {alerts_sent_count}")
    print("==================================================")

if __name__ == "__main__":
    run_trading_bot()
