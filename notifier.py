import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_GENERAL, DISCORD_WEBHOOK_SELL, INITIAL_CAPITAL

def send_discord_signal(
    keyword: str,
    title: str,
    url: str,
    score: int,
    summary: str,
    keywords: list,
    buy_price: float,
    target_price: float,
    stop_loss: float,
    rsi: float,
    atr: float,
    track: str = "A",
    qty: int = 0,
    invest_amount: float = 0.0,
    available_cash: float = None,
    total_equity: float = None,
) -> bool:
    """
    DISCORD_WEBHOOK_GENERAL 채널로 주가 뉴스 분석 시그널 및 매수 진입 카드를 발송합니다.
    """
    if not DISCORD_WEBHOOK_GENERAL:
        print("Warning: DISCORD_WEBHOOK_GENERAL is not configured. Skipping alert.")
        return False

    if track == "B":
        color = 3447003  # 파란색 계열 (#3498DB)
        signal_type = "🔵 [AI 역발상 과매도 매수 진입 - 트랙 B]"
    else:
        color = 3066993  # 녹색 계열 (#2ECC71)
        signal_type = "🟢 [AI 모멘텀 돌파 매수 진입 - 트랙 A]"
    
    keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

    price_info_lines = [
        f"💵 **체결가**: `{buy_price:,.0f}원`",
        f"🎯 **목표가(상한)**: `{target_price:,.0f}원`",
        f"🛡️ **손절가(하한)**: `{stop_loss:,.0f}원`",
    ]
    if qty > 0:
        inv_val = invest_amount if invest_amount > 0 else buy_price * qty
        price_info_lines.append(f"📦 **매수 수량**: `{qty:,}주` (매수금액 `{inv_val:,.0f}원`)")
    if available_cash is not None:
        eq_str = f" / 총자산 `{total_equity:,.0f}원`" if total_equity is not None else ""
        price_info_lines.append(f"🏦 **잔여 예수금**: `{available_cash:,.0f}원`{eq_str}")

    payload = {
        "embeds": [
            {
                "title": f"{signal_type} {keyword} (Score: {score:+})",
                "description": f"**[뉴스 읽기]({url})**\n\n**기사 제목**: {title}",
                "color": color,
                "fields": [
                    {
                        "name": "💰 매수 및 가상계좌 정보",
                        "value": "\n".join(price_info_lines),
                        "inline": False
                    },
                    {
                        "name": "📈 보조지표 상태",
                        "value": f"⚡ **RSI(14)**: `{rsi:.2f}` (트랙 {track})\n📊 **ATR(14)**: `{atr:.2f}`",
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
                    "text": f"Serverless AI Trading Bot - Track {track}"
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

def send_discord_sell_alert(
    keyword: str,
    symbol: str,
    buy_price: float,
    sell_price: float,
    target_price: float,
    stop_loss: float,
    is_profit: bool,
    reason_str: str = "",
    qty: int = 0,
    pnl_krw: float = None,
    available_cash: float = None,
    total_equity: float = None,
) -> bool:
    """
    DISCORD_WEBHOOK_SELL 채널로 포지션 청산(익절/손절/본절) 메시지를 발송합니다.
    """
    if not DISCORD_WEBHOOK_SELL:
        print("Warning: DISCORD_WEBHOOK_SELL is not configured. Skipping alert.")
        return False

    if reason_str == "본절":
        color = 16776960  # 노란색 (#FFFF00)
        emoji = "🟡"
        reason = "본절 스탑 발동 (수수료 보전 청산)"
    elif is_profit:
        color = 3066993   # 녹색 (#2ECC71)
        emoji = "🟢"
        reason = "목표가 돌파 (익절 완료)"
    else:
        color = 15158332  # 적색 (#E74C3C)
        emoji = "🚨"
        reason = "손절선 이탈 (손절 완료)"
        
    title_str = f"{emoji} [포지션 청산 완료] {keyword} ({symbol})"
    
    # 수익률 계산
    return_rate = ((sell_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0.0
    return_rate_str = f"{return_rate:+.2f}%"

    summary_lines = [
        f"📈 **수익률**: `{return_rate_str}`",
        f"📢 **청산 사유**: **{reason}**",
    ]
    if qty > 0 and pnl_krw is not None:
        summary_lines.append(f"💰 **실현 손익**: `{pnl_krw:+,.0f}원` ({qty:,}주)")
    if total_equity is not None:
        acct_ret = ((total_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0
        cash_str = f" (가용 예수금 `{available_cash:,.0f}원`)" if available_cash is not None else ""
        summary_lines.append(f"🏦 **계좌 총자산**: `{total_equity:,.0f}원` (`{acct_ret:+.2f}%`){cash_str}")

    payload = {
        "embeds": [
            {
                "title": title_str,
                "description": f"**{keyword}** 종목의 청산 조건이 발동되어 포지션을 종료합니다.",
                "color": color,
                "fields": [
                    {
                        "name": "📊 청산 및 계좌 요약",
                        "value": "\n".join(summary_lines),
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
            atr=8500,
            qty=17,
            invest_amount=3910000,
            available_cash=16090000,
            total_equity=20000000
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
            is_profit=True,
            qty=17,
            pnl_krw=374000,
            available_cash=20374000,
            total_equity=20374000
        )
