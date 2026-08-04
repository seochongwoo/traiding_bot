import time
from datetime import datetime, timedelta
from config import (
    TARGET_KEYWORDS, SIGNAL_THRESHOLD, MAX_NEWS_PER_KEYWORD, 
    KEYWORD_SYNONYMS, RSI_BUY_LIMIT, DISPARITY_LIMIT, TICKER_MAP
)
from crawler import fetch_news_list, get_news_content
from db import (
    open_worksheet, fetch_existing_urls, append_news_record,
    fetch_active_positions, update_position_status, add_active_position
)
from analyzer import analyze_news_sentiment
from notifier import send_discord_signal, send_discord_sell_alert
from chart import get_stock_indicators, check_market_trend

def run_trading_bot():
    print("==================================================")
    print(f"Starting Serverless AI Trading Bot at {datetime.utcnow() + timedelta(hours=9)} KST")
    print("==================================================")

    # --------------------------------------------------
    # 🔄 Phase 1: 보유 종목 감시 및 청산 (Sell Logic)
    # --------------------------------------------------
    print("\n==================================================")
    print("🔄 Phase 1: Monitoring & Liquidating Active Positions")
    print("==================================================")
    
    pos_sheet = open_worksheet("Active_Positions")
    if not pos_sheet:
        print("Warning: Active_Positions worksheet is not available. Skipping Phase 1.")
    else:
        active_positions = fetch_active_positions(pos_sheet)
        print(f"Found {len(active_positions)} active positions to monitor.")
        
        for pos in active_positions:
            keyword = pos["name"]
            symbol = pos["symbol"]
            row_num = pos["row_num"]
            buy_price = pos["buy_price"]
            target_price = pos["target_price"]
            stop_loss = pos["stop_loss"]
            
            print(f"\nChecking position: {keyword} ({symbol}) | Entry: {buy_price:,.0f} | Target: {target_price:,.0f} | Stop: {stop_loss:,.0f}")
            
            # 실시간 주가 데이터 획득
            chart_data = get_stock_indicators(keyword)
            if not chart_data:
                print(f"Warning: Failed to fetch chart data for {keyword}. Skipping.")
                continue
                
            current_price = chart_data["current_price"]
            print(f"Current price for {keyword}: {current_price:,.0f}")
            
            # 청산 조건 감시 (목표가 돌파 또는 손절선 이탈)
            is_liquidated = False
            is_profit = False
            
            if current_price >= target_price:
                print(f"🏆 Target hit! current price {current_price:,.0f} >= target {target_price:,.0f}")
                is_liquidated = True
                is_profit = True
            elif current_price <= stop_loss:
                print(f"🚨 Stop loss hit! current price {current_price:,.0f} <= stop loss {stop_loss:,.0f}")
                is_liquidated = True
                is_profit = False
                
            if is_liquidated:
                # 디스코드 채널로 익절/손절 메시지 발송 (#매도-청산-알림)
                sent = send_discord_sell_alert(
                    keyword=keyword,
                    symbol=symbol,
                    buy_price=buy_price,
                    sell_price=current_price,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    is_profit=is_profit
                )
                
                # 구글 스프레드시트 상태를 '청산완료'로 수정
                if sent:
                    updated = update_position_status(pos_sheet, row_num, "청산완료")
                    if updated:
                        print(f"Successfully updated position at row {row_num} to '청산완료'.")
            else:
                print("Holding position. Exit conditions not met.")
                
            # 과부하 방지 1.5초 대기
            time.sleep(1.5)

    # --------------------------------------------------
    # 🔄 Phase 2: 신규 종목 탐색 및 진입 (Buy Logic)
    # --------------------------------------------------
    print("\n==================================================")
    print("🔄 Phase 2: Scanning & Entering New Positions")
    print("==================================================")
    
    # 대세 상승장 필터링: KOSPI와 NASDAQ이 모두 20일선 위에 있어야 매수 탐색 진행
    print("Checking overall market trend index filter...")
    kospi_ok, nasdaq_ok = check_market_trend()
    if not (kospi_ok and nasdaq_ok):
        print(f"🚫 [대세 하락장 차단] KOSPI 20일선 통과: {kospi_ok} | NASDAQ 20일선 통과: {nasdaq_ok}")
        print("Skipping Phase 2 entirely to prevent buying in a downtrend and save API requests.")
        return
        
    print("✅ [시장 상승세 판정] KOSPI와 NASDAQ이 모두 20일선 위에 있습니다. 신규 종목 탐색을 시작합니다.")
    
    # 원래 쓰던 "시트1" 탭에 신규 분석 데이터를 누적합니다.
    news_sheet = open_worksheet("시트1")
    if not news_sheet:
        print("Warning: '시트1' worksheet is not connected. The bot will run without database logging.")
        existing_urls = set()
    else:
        existing_urls = fetch_existing_urls(news_sheet)
        print(f"Loaded {len(existing_urls)} existing URLs from '시트1'.")

    new_articles_count = 0
    alerts_sent_count = 0

    for keyword in TARGET_KEYWORDS:
        print(f"\nTargeting Keyword: '{keyword}'")
        print(f"Fetching latest {MAX_NEWS_PER_KEYWORD} news items...")
        
        # 최신 검색 리스트 크롤링
        news_items = fetch_news_list(keyword, limit=MAX_NEWS_PER_KEYWORD)
        print(f"Found {len(news_items)} news items for '{keyword}'.")

        for item in news_items:
            url_identifier = item["naver_news_link"] if item["naver_news_link"] else item["original_link"]
            
            if url_identifier in existing_urls:
                continue
                
            # 제목 키워드 필터링 적용
            synonyms = KEYWORD_SYNONYMS.get(keyword, [keyword])
            has_keyword = any(syn in item["title"] for syn in synonyms)
            if not has_keyword:
                print(f"   -> [필터링 스킵] 제목에 관련 키워드가 없어 스킵합니다: '{item['title']}'")
                continue
                
            print(f"\nProcessing new article: '{item['title']}'")
            print(f"URL: {url_identifier}")
            
            # 본문 내용 가져오기
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

            # 야후 파이낸스에서 기술적 지표 조회 (RSI, ATR, 이격도, MACD 데드크로스)
            chart_data = get_stock_indicators(keyword)
            rsi = chart_data["rsi"] if chart_data else None
            atr = chart_data["atr"] if chart_data else None
            disparity = chart_data["disparity"] if chart_data else None
            macd_dead_cross = chart_data["macd_dead_cross"] if chart_data else None
            current_price = chart_data["current_price"] if chart_data else None

            # 구글 스프레드시트에 저장 ("시트1" 탭에 보조지표를 포함해 기록)
            saved_to_db = False
            if news_sheet:
                saved_to_db = append_news_record(
                    sheet=news_sheet,
                    datetime_str=datetime_str,
                    keyword=keyword,
                    title=item["title"],
                    url=url_identifier,
                    score=score,
                    summary=summary,
                    keywords=extracted_keywords,
                    rsi=rsi,
                    disparity=disparity,
                    macd_dead_cross=macd_dead_cross
                )
                if saved_to_db:
                    print("Recorded to '시트1' sheet successfully (including chart indicators).")
            
            existing_urls.add(url_identifier)
            new_articles_count += 1

            # 매수 시그널 발생 조건 검사 (AI score >= 8)
            if score >= SIGNAL_THRESHOLD:
                print(f"BUY Signal detected! Score {score:+} >= {SIGNAL_THRESHOLD}.")
                
                if not chart_data:
                    print("Warning: Failed to fetch stock indicators. Skipping position entry.")
                    continue
                    
                # 설거지 방지 및 매수 강도 필터링 적용 (RSI <= 50, 이격도 < 120%, MACD 데드크로스 아닐 것)
                skip_buy = False
                skip_reasons = []
                
                if rsi and rsi > RSI_BUY_LIMIT:
                    skip_buy = True
                    skip_reasons.append(f"RSI 과열 ({rsi:.2f} > {RSI_BUY_LIMIT})")
                if disparity and disparity >= DISPARITY_LIMIT:
                    skip_buy = True
                    skip_reasons.append(f"이격도 과열 ({disparity:.2f}% >= {DISPARITY_LIMIT}%)")
                if macd_dead_cross:
                    skip_buy = True
                    skip_reasons.append("MACD 데드크로스(하락 추세)")
                
                if not skip_buy:
                    # 목표가 및 손절가 계산
                    target_price = current_price + (atr * 3)
                    stop_loss = current_price - (atr * 2)
                    
                    print(f"Filters Passed: Calculated Target: {target_price:,.0f} | Stop Loss: {stop_loss:,.0f}")
                    
                    # 디스코드 채널로 진입 알림 발송 (#일반-알림)
                    sent = send_discord_signal(
                        keyword=keyword,
                        title=item["title"],
                        url=url_identifier,
                        score=score,
                        summary=summary,
                        keywords=extracted_keywords,
                        buy_price=current_price,
                        target_price=target_price,
                        stop_loss=stop_loss,
                        rsi=rsi,
                        atr=atr
                    )
                    
                    # Active_Positions 워크시트에 진입 기록 추가
                    if sent and pos_sheet:
                        symbol = TICKER_MAP.get(keyword, "")
                        added = add_active_position(
                            sheet=pos_sheet,
                            date_str=datetime_str,
                            symbol=symbol,
                            name=keyword,
                            buy_price=current_price,
                            target_price=target_price,
                            stop_loss=stop_loss,
                            status="보유중"
                        )
                        if added:
                            print(f"Successfully recorded new position for {keyword} in Active_Positions.")
                            alerts_sent_count += 1
                else:
                    print(f"BUY Entry Blocked: {', '.join(skip_reasons)}. Skipping position entry.")
            else:
                print(f"No buy signal triggered. Score {score:+} < {SIGNAL_THRESHOLD}.")

            # API 속도 조절 (무료 티어 RPM 안전 준수)
            time.sleep(4.5)

    print("\n==================================================")
    print("Execution Finished Summary:")
    print(f"- Total new articles analyzed: {new_articles_count}")
    print(f"- Total new positions opened: {alerts_sent_count}")
    print("==================================================")

if __name__ == "__main__":
    run_trading_bot()
