import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_GENERAL, DISCORD_WEBHOOK_SELL

def send_discord_signal(keyword: str, title: str, url: str, score: int, summary: str, keywords: list, 
                        buy_price: float, target_price: float, stop_loss: float, rsi: float, atr: float) -> bool:
    """
    DISCORD_WEBHOOK_GENERAL 채널로 주가 뉴스 분석 시그널 및 매수 진입 카드를 발송합니다.
    """
    if not DISCORD_WEBHOOK_GENERAL:
        print("Warning: DISCORD_WEBHOOK_GENERAL is not configured. Skipping alert.")
        return False

    color = 3066993 # 녹색 계열 (#2ECC71)
    signal_type = "🟢 [AI 뉴스 분석 & 매수 진입 추천]"
    
    keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
    
    payload = {
        "embeds": [
            {
                "title": f"{signal_type} {keyword} (Score: {score:+})",
                "description": f"**[뉴스 읽기]({url})**\n\n**기사 제목**: {title}",
                "color": color,
                "fields": [
                    {
                        "name": "💰 매수 정보 설정",
                        "value": f"💵 **추천 진입가**: `{buy_price:,.0f}원`\n🎯 **목표가(상한)**: `{target_price:,.0f}원`\n🛡️ **손절가(하한)**: `{stop_loss:,.0f}원`",
                        "inline": False
                    },
                    {
                        "name": "📈 보조지표 상태 (설거지 방지 및 필터 통과)",
                        "value": f"⚡ **RSI(14)**: `{rsi:.2f}` (기준: 50 이하)\n📊 **ATR(14)**: `{atr:.2f}` (변동성 범위)",
                        "inline": False
                    },
                    {
                        "name": "💡 AI 3줄 요약",
                        "value": summary,
                        "inline": False
                    },
                    {
                        "name": "🔑 핵심 키워드",
                        "value": keywords_str,
                        "inline": True
                    },
                    {
                        "name": "📊 종목명",
                        "value": keyword,
                        "inline": True
                    }
                ],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {
                    "text": "Serverless AI Trading Bot - Buy Phase"
                }
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_GENERAL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            print(f"[{keyword}] Discord BUY signal alert sent successfully.")
            return True
        else:
            print(f"Error: Failed to send Discord BUY signal. Status code: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Exception while sending Discord BUY notification: {e}")
        return False

def send_discord_sell_alert(keyword: str, symbol: str, buy_price: float, sell_price: float, 
                            target_price: float, stop_loss: float, is_profit: bool) -> bool:
    """
    DISCORD_WEBHOOK_SELL 채널로 포지션 청산(익절/손절) 메시지를 발송합니다.
    """
    if not DISCORD_WEBHOOK_SELL:
        print("Warning: DISCORD_WEBHOOK_SELL is not configured. Skipping alert.")
        return False

    # 익절은 녹색 계열 (#2ECC71), 손절은 적색 계열 (#E74C3C)
    color = 3066993 if is_profit else 15158332
    emoji = "🟢" if is_profit else "🚨"
    title_str = f"{emoji} [포지션 청산 완료] {keyword} ({symbol})"
    reason = "목표가 돌파 (익절 완료)" if is_profit else "손절선 이탈 (손절 완료)"
    
    # 수익률 계산
    return_rate = ((sell_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0.0
    return_rate_str = f"{return_rate:+.2f}%"

    payload = {
        "embeds": [
            {
                "title": title_str,
                "description": f"**{keyword}** 종목의 청산 조건이 발동되어 포지션을 종료합니다.",
                "color": color,
                "fields": [
                    {
                        "name": "📊 청산 요약",
                        "value": f"📈 **수익률**: `{return_rate_str}`\n📢 **청산 사유**: **{reason}**",
                        "inline": False
                    },
                    {
                        "name": "💵 가격 정보",
                        "value": f"📥 **매수가**: `{buy_price:,.0f}원`\n📤 **청산가(현재가)**: `{sell_price:,.0f}원`\n🎯 **목표가**: `{target_price:,.0f}원`\n🛡️ **손절가**: `{stop_loss:,.0f}원`",
                        "inline": False
                    }
                ],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {
                    "text": "Serverless AI Trading Bot - Sell Phase"
                }
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_SELL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            print(f"[{keyword}] Discord SELL alert sent successfully.")
            return True
        else:
            print(f"Error: Failed to send Discord SELL alert. Status code: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Exception while sending Discord SELL notification: {e}")
        return False

if __name__ == "__main__":
    # 간단한 작동 테스트
    import os
    if os.getenv("DISCORD_WEBHOOK_GENERAL"):
        print("Testing BUY alert...")
        send_discord_signal(
            keyword="삼성전자",
            title="삼성전자, 차세대 반도체 공급 계약 발표",
            url="https://n.news.naver.com/mnews/article/001/0000000000",
            score=9,
            summary="- 실적 향상 기대감\n- 신제품 공급 속도 가속화\n- 단기 추세 상승 모멘텀 작용",
            keywords=["반도체", "삼성전자", "공급계약"],
            buy_price=230000,
            target_price=250000,
            stop_loss=210000,
            rsi=43.5,
            atr=8500
        )
    if os.getenv("DISCORD_WEBHOOK_SELL"):
        print("Testing SELL alert...")
        send_discord_sell_alert(
            keyword="삼성전자",
            symbol="005930.KS",
            buy_price=230000,
            sell_price=252000,
            target_price=250000,
            stop_loss=210000,
            is_profit=True
        )
