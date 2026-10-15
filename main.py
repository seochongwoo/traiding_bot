import sys
import os
import io
import time
from datetime import datetime, timedelta

# Windows 콘솔 환경(cp949)에서 유니코드/이모지 출력 에러 방지
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# --dry-run 플래그 처리
if "--dry-run" in sys.argv:
    os.environ["DRY_RUN"] = "1"

from config import (
    TARGET_KEYWORDS, MAX_NEWS_PER_KEYWORD, KEYWORD_SYNONYMS, TICKER_MAP, 
    DRY_RUN, DEDUP_WINDOW_HOURS, DEDUP_JACCARD
)
from crawler import fetch_news_list, get_news_content
from db import (
    open_worksheet, fetch_existing_urls, fetch_all_positions, fetch_active_positions,
    batch_update_position, liquidate_position, update_position_highest,
    add_active_position, append_news_records, fetch_recent_titles
)
from analyzer import analyze_news_sentiment
from notifier import send_discord_signal, send_discord_sell_alert
from chart import get_stock_indicators, check_market_trend, get_intraday_bars, get_today_open
from strategy import (
    now_kst, is_session_time, evaluate_entry, compute_tp_sl,
    gap_check, resolve_exit, in_cooldown, KST
)
from dedup import find_duplicate


def run_trading_bot():
    current_kst = now_kst()
    is_session = is_session_time(current_kst)
    current_kst_str = current_kst.strftime("%Y-%m-%d %H:%M:%S")

    print("==================================================")
    print(f"Starting Serverless AI Trading Bot at {current_kst_str} KST")
    print(f"Session Status: {'정규장 운영시간' if is_session else '장외 시간 (신규 진입은 진입대기로 전환)'}")
    if DRY_RUN:
        print("⚡ [DRY RUN MODE] 시트 및 디스코드 쓰기를 건너뜁니다.")
    print("==================================================")

    pos_sheet = open_worksheet("Active_Positions") if not DRY_RUN else None
    all_positions = fetch_all_positions(pos_sheet) if pos_sheet else []

    # --------------------------------------------------
    # ⏳ Phase 0: 장외 진입대기 주문 체결 판단 (Pending Orders)
    # --------------------------------------------------
    if is_session and pos_sheet:
        print("\n==================================================")
        print("⏳ Phase 0: Resolving Pending Orders (진입대기 체결 판단)")
        print("==================================================")
        pending = [p for p in all_positions if p["status"] == "진입대기"]
        print(f"Found {len(pending)} pending orders.")

        for p in pending:
            name = p["name"]
            row_num = p["row_num"]
            sig_price = p["signal_price"] or p["buy_price"]
            print(f"\nEvaluating pending order: {name} (Signal: {sig_price:,.0f}원)")

            # 생성 시각 기준 48시간 이상 경과 시 취소 처리
            try:
                created_dt = datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
                if current_kst - created_dt > timedelta(hours=48):
                    print(f"   -> Expired (> 48h). Cancelling pending order.")
                    batch_update_position(pos_sheet, row_num, {7: "진입취소", 17: "시간초과 만료"})
                    p["status"] = "진입취소"
                    continue
            except Exception:
                pass

            today_open = get_today_open(name)
            chart_data = get_stock_indicators(name)
            if not today_open or not chart_data:
                print(f"   -> Failed to fetch opening/current price for {name}. Keeping pending.")
                continue

            gap_pct, can_enter = gap_check(sig_price, today_open)
            print(f"   -> Today Open: {today_open:,.0f}원 | Gap: {gap_pct:+.2f}% | Can Enter: {can_enter}")

            if can_enter:
                # 갭상승이 +3% 이내: 당일 시초가와 현재가 중 높은 가격으로 안전 체결
                current_price = chart_data["current_price"]
                fill_price = max(today_open, current_price)
                new_target, new_stop = compute_tp_sl(fill_price, chart_data["atr"])
                note_str = f"체결 (시초가 갭 {gap_pct:+.2f}%)"

                batch_update_position(pos_sheet, row_num, {
                    1: current_kst_str,
                    4: round(fill_price),
                    5: round(new_target),
                    6: round(new_stop),
                    7: "보유중",
                    12: round(fill_price),
                    13: 0.0,
                    16: current_kst_str,
                    17: note_str
                })
                p["status"] = "보유중"
                p["buy_price"] = fill_price
                p["target_price"] = new_target
                p["stop_loss"] = new_stop
                p["highest_price"] = fill_price

                print(f"   ✅ [체결 완료] {name} at {fill_price:,.0f}원 | Target: {new_target:,.0f} | Stop: {new_stop:,.0f}")
                send_discord_signal(
                    keyword=name,
                    title=f"[대기주문 정규장 체결] {name}",
                    url="https://finance.naver.com",
                    score=7,
                    summary=f"- 전일 장외 발생 주문이 오늘 시초가({today_open:,.0f}원) 확인 후 정상 체결됨\n- 시초가 갭: {gap_pct:+.2f}%\n- 체결가: {fill_price:,.0f}원",
                    keywords=[name, "대기체결", p["track"]],
                    buy_price=fill_price,
                    target_price=new_target,
                    stop_loss=new_stop,
                    rsi=chart_data["rsi"],
                    atr=chart_data["atr"],
                    track=p["track"]
                )
            else:
                # 갭상승 +3% 초과: 추격매수 금지 원칙에 따라 주문 취소
                cancel_reason = f"진입취소 (갭 {gap_pct:+.2f}%)"
                print(f"   🚫 [체결 취소] Gap +{gap_pct:.2f}% exceeds limit (+3.0%).")
                batch_update_position(pos_sheet, row_num, {
                    7: "진입취소",
                    16: current_kst_str,
                    17: f"시초가 과대 갭상승 ({today_open:,.0f}원 / 시그널 {sig_price:,.0f}원)"
                })
                p["status"] = "진입취소"

    # --------------------------------------------------
    # 🔄 Phase 1: 보유 종목 감시 및 청산 (Sell Logic)
    # --------------------------------------------------
    print("\n==================================================")
    print("🔄 Phase 1: Monitoring & Liquidating Active Positions")
    print("==================================================")
    
    active_positions = [p for p in all_positions if p["status"] == "보유중"]
    print(f"Found {len(active_positions)} active positions to monitor.")

    for pos in active_positions:
        keyword = pos["name"]
        symbol = pos["symbol"]
        row_num = pos["row_num"]
        buy_price = pos["buy_price"]
        target_price = pos["target_price"]
        stop_loss = pos["stop_loss"]
        highest_price = pos["highest_price"]
        
        print(f"\nChecking position: {keyword} ({symbol}) | Entry: {buy_price:,.0f} | Target: {target_price:,.0f} | Stop: {stop_loss:,.0f}")

        # 마지막 점검 시각 파싱
        last_dt = None
        last_str = pos.get("last_checked") or pos.get("date")
        if last_str:
            try:
                last_dt = datetime.strptime(last_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            except Exception:
                pass

        # 장중 5분봉 조회 (점검 주기 사이의 High/Low 터치 감지)
        bars = get_intraday_bars(keyword, since_dt=last_dt)
        chart_data = get_stock_indicators(keyword)
        if not bars and chart_data:
            cp = chart_data["current_price"]
            bars = [(cp, cp, cp, cp)]

        if not bars:
            print(f"Warning: No price bars available for {keyword}. Skipping.")
            continue

        res = resolve_exit(buy_price, target_price, stop_loss, highest_price, bars)
        exit_price = res["exit_price"]
        reason = res["reason"]
        new_highest = res["highest"]
        new_stop = res["stop"]

        # 최고가 및 최고가도달률 갱신
        if new_highest > highest_price or new_highest == 0.0:
            highest_rate = ((new_highest - buy_price) / buy_price) * 100 if buy_price > 0 else 0.0
            print(f"   🏆 New high recorded for {keyword}: {new_highest:,.0f}원 ({highest_rate:+.2f}%)")
            if pos_sheet and not DRY_RUN:
                update_position_highest(pos_sheet, row_num, new_highest, highest_rate, last_checked=current_kst_str)
            pos["highest_price"] = new_highest
            pos["highest_rate"] = highest_rate

        # 본절 스탑(Ratchet) 상향 확인
        if new_stop > stop_loss:
            print(f"   🛡️ Breakeven ratchet triggered: Stop loss raised to {new_stop:,.0f}원")
            if pos_sheet and not DRY_RUN:
                batch_update_position(pos_sheet, row_num, {6: new_stop, 17: "본절 스탑 활성화"})
            pos["stop_loss"] = new_stop

        # 청산 발동 여부
        if exit_price is not None:
            is_profit = (reason == "익절")
            return_rate = ((exit_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0.0
            print(f"   🔔 [청산 발동] {keyword} | Reason: {reason} | Price: {exit_price:,.0f}원 ({return_rate:+.2f}%)")

            if not DRY_RUN:
                send_discord_sell_alert(
                    keyword=keyword,
                    symbol=symbol,
                    buy_price=buy_price,
                    sell_price=exit_price,
                    target_price=target_price,
                    stop_loss=new_stop,
                    is_profit=is_profit,
                    reason_str=reason
                )
                if pos_sheet:
                    liquidate_position(
                        sheet=pos_sheet,
                        row_num=row_num,
                        close_date=current_kst_str,
                        close_price=exit_price,
                        reason=reason,
                        return_rate=return_rate
                    )
            pos["status"] = "청산완료"
            pos["close_date"] = current_kst_str
        else:
            print(f"   Holding position: Exit conditions not met. Current stop: {new_stop:,.0f}원")
            if pos_sheet and not DRY_RUN:
                batch_update_position(pos_sheet, row_num, {16: current_kst_str})

        time.sleep(1.0)

    # --------------------------------------------------
    # 🔄 Phase 2: 신규 종목 탐색 및 진입 (Buy Logic)
    # --------------------------------------------------
    print("\n==================================================")
    print("🔄 Phase 2: Scanning & Entering New Positions")
    print("==================================================")
    
    print("Checking overall market trend index filter...")
    kospi_ok, nasdaq_ok = check_market_trend()
    market_ok = bool(kospi_ok and nasdaq_ok)
    if not market_ok:
        print(f"⚠️ [대세 하락장 상태 감지] KOSPI: {kospi_ok} | NASDAQ: {nasdaq_ok}")
        print("Market is in a downtrend. Track A momentum is blocked, but Track B contrarian remains active.")
    else:
        print("✅ [시장 상승세 판정] KOSPI와 NASDAQ이 모두 20일선 위에 있습니다.")

    news_sheet = open_worksheet("시트1") if not DRY_RUN else None
    existing_urls = fetch_existing_urls(news_sheet) if news_sheet else set()
    print(f"Loaded {len(existing_urls)} existing URLs from '시트1'.")

    new_articles_count = 0
    new_entries_count = 0

    for keyword in TARGET_KEYWORDS:
        symbol = TICKER_MAP.get(keyword, "")
        print(f"\nTargeting Keyword: '{keyword}' ({symbol})")
        
        # 최근 12시간 내 수집된 제목들 로드 (의미 중복 필터용)
        recent_titles = fetch_recent_titles(news_sheet, keyword, hours=DEDUP_WINDOW_HOURS) if news_sheet else []
        news_items = fetch_news_list(keyword, limit=MAX_NEWS_PER_KEYWORD)
        print(f"Found {len(news_items)} news items for '{keyword}'. Recent titles for dedup: {len(recent_titles)}")

        rows_to_append = []

        for item in news_items:
            url_identifier = item["naver_news_link"] if item["naver_news_link"] else item["original_link"]
            title = item["title"]

            if url_identifier in existing_urls:
                continue

            # 제목 키워드 필터링
            synonyms = KEYWORD_SYNONYMS.get(keyword, [keyword])
            has_keyword = any(syn in title for syn in synonyms)
            if not has_keyword:
                print(f"   -> [필터링 스킵] 관련 키워드 없음: '{title}'")
                continue

            # 의미 중복(Semantic Duplicate) 필터링
            dup_title, sim = find_duplicate(title, recent_titles, keyword, synonyms=synonyms, threshold=DEDUP_JACCARD)
            if dup_title:
                print(f"   -> [의미 중복 스킵] 유사도 {sim:.2f}: '{title}' vs '{dup_title}'")
                existing_urls.add(url_identifier)
                continue

            print(f"\nProcessing new article: '{title}'")
            print(f"URL: {url_identifier}")

            # 본문 크롤링
            news_content = ""
            if item["naver_news_link"]:
                news_content = get_news_content(item["naver_news_link"])
            if not news_content:
                news_content = item["snippet"]

            # AI 분석 (Gemini API with retry & article_type)
            analysis = analyze_news_sentiment(keyword, title, news_content)
            score = analysis["score"]
            summary = analysis["summary"]
            extracted_keywords = analysis["keywords"]
            article_type = analysis.get("article_type", "catalyst")

            print(f"Analysis result -> Score: {score:+}, Type: {article_type}, Summary: {summary[:60]}...")

            # 기술적 지표 조회
            chart_data = get_stock_indicators(keyword)
            rsi = chart_data["rsi"] if chart_data else None
            atr = chart_data["atr"] if chart_data else None
            disparity = chart_data["disparity"] if chart_data else None
            macd_dead_cross = chart_data["macd_dead_cross"] if chart_data else None
            current_price = chart_data["current_price"] if chart_data else 0.0

            # 2개 트랙(A: 모멘텀, B: 역발상) 판정
            track, reasons = evaluate_entry(score, article_type, rsi, disparity, macd_dead_cross, market_ok)

            # 중복 보유 및 쿨다운 검증
            if in_cooldown(all_positions, symbol, current_kst):
                reasons.append("이미 보유/대기/쿨다운")
                track = None

            entry_yn = "N"
            if track:
                target_price, stop_loss = compute_tp_sl(current_price, atr)
                
                if is_session:
                    # 정규장: 즉시 체결 및 보유중 등록
                    entry_yn = f"Y-{track}"
                    print(f"🚀 [BUY Entry Triggered - Track {track}] {keyword} at {current_price:,.0f}원 | Target: {target_price:,.0f} | Stop: {stop_loss:,.0f}")
                    
                    if not DRY_RUN:
                        send_discord_signal(
                            keyword=keyword,
                            title=title,
                            url=url_identifier,
                            score=score,
                            summary=summary,
                            keywords=extracted_keywords,
                            buy_price=current_price,
                            target_price=target_price,
                            stop_loss=stop_loss,
                            rsi=rsi,
                            atr=atr,
                            track=track
                        )
                        if pos_sheet:
                            add_active_position(
                                sheet=pos_sheet,
                                date_str=current_kst_str,
                                symbol=symbol,
                                name=keyword,
                                buy_price=current_price,
                                target_price=target_price,
                                stop_loss=stop_loss,
                                status="보유중",
                                signal_price=current_price,
                                track=track,
                                note="정규장 진입"
                            )
                    all_positions.append({"symbol": symbol, "name": keyword, "status": "보유중", "date": current_kst_str})
                    new_entries_count += 1
                else:
                    # 장외 시간: 진입대기로 등록 (전일 종가 즉시 체결 방지)
                    entry_yn = f"대기-{track}"
                    print(f"⏳ [Pending Order Created - Track {track}] {keyword} at Signal {current_price:,.0f}원 (장외 발생)")
                    
                    if pos_sheet and not DRY_RUN:
                        add_active_position(
                            sheet=pos_sheet,
                            date_str=current_kst_str,
                            symbol=symbol,
                            name=keyword,
                            buy_price=0.0,
                            target_price=target_price,
                            stop_loss=stop_loss,
                            status="진입대기",
                            signal_price=current_price,
                            track=track,
                            note="장외 발생"
                        )
                    all_positions.append({"symbol": symbol, "name": keyword, "status": "진입대기", "date": current_kst_str})
                    new_entries_count += 1
            else:
                entry_yn = f"N ({', '.join(reasons)})"
                if score >= 3:
                    print(f"Entry Blocked: {entry_yn}")

            # 시트1 버퍼에 저장할 행 데이터 구성
            keywords_str = ", ".join(extracted_keywords) if isinstance(extracted_keywords, list) else str(extracted_keywords)
            macd_str = "데드크로스(하락)" if macd_dead_cross is True else ("골든크로스(상승)" if macd_dead_cross is False else "")
            
            row_data = [
                current_kst_str, keyword, title, url_identifier, score,
                summary, keywords_str,
                round(rsi, 2) if rsi is not None else "",
                round(disparity, 2) if disparity is not None else "",
                macd_str,
                round(current_price) if current_price else "",
                entry_yn,
                "", "", "", ""
            ]
            rows_to_append.append(row_data)

            existing_urls.add(url_identifier)
            recent_titles.append(title)
            new_articles_count += 1

            time.sleep(4.5)

        # 키워드별 일괄 배치 추가
        if rows_to_append and news_sheet and not DRY_RUN:
            append_news_records(news_sheet, rows_to_append)
            print(f"Recorded {len(rows_to_append)} news articles to '시트1' in one batch.")

    print("\n==================================================")
    print("Execution Finished Summary:")
    print(f"- Total new articles analyzed: {new_articles_count}")
    print(f"- Total new positions/orders: {new_entries_count}")
    print("==================================================")


if __name__ == "__main__":
    run_trading_bot()
