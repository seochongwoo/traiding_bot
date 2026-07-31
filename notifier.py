import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL

def send_discord_signal(keyword: str, title: str, url: str, score: int, summary: str, keywords: list, rsi=None, disparity=None, macd_dead_cross=None) -> bool:
    """
    Discord Webhook을 사용하여 주가 영향도 시그널 메시지를 Rich Embed 형태로 전송합니다.
    """
    if not DISCORD_WEBHOOK_URL:
        print("Warning: DISCORD_WEBHOOK_URL is not configured. Skipping alert.")
        return False

    # 호재는 녹색 계열 (#2ECC71), 악재는 적색 계열 (#E74C3C)
    color = 3066993 if score > 0 else 15158332
    signal_type = "🟢 [강한 매수 시그널]" if score > 0 else "🔴 [강한 매도 시그널]"
    
    # 키워드 포맷팅
    keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
    
    # Discord Embed Payload 구성
    payload = {
        "embeds": [
            {
                "title": f"{signal_type} {keyword} (Score: {score:+})",
                "description": f"**[뉴스 읽기]({url})**\n\n**기사 제목**: {title}",
                "color": color,
                "fields": [
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
                        "name": "📊 분석 대상",
                        "value": keyword,
                        "inline": True
                    }
                ],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {
                    "text": "Serverless AI Trading Bot"
                }
            }
        ]
    }

    # 차트 보조지표 필드 동적 추가
    if rsi is not None or disparity is not None or macd_dead_cross is not None:
        rsi_str = f"{rsi:.2f}" if rsi is not None else "N/A"
        disp_str = f"{disparity:.2f}%" if disparity is not None else "N/A"
        macd_str = "🔴 데드크로스(하락 우세)" if macd_dead_cross is True else ("🟢 골든크로스(상승 우세)" if macd_dead_cross is False else "N/A")
        
        indicator_value = f"📈 **RSI(14)**: `{rsi_str}` (경고: $\\ge 75$)\n⚖️ **이격도(20)**: `{disp_str}` (경고: $\\ge 120\\%$)\n📊 **MACD**: {macd_str}"
        payload["embeds"][0]["fields"].append({
            "name": "📊 차트 보조지표 상태 (설거지 방지 통과)",
            "value": indicator_value,
            "inline": False
        })

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            print(f"[{keyword}] Discord signal alert sent successfully.")
            return True
        else:
            print(f"Error: Failed to send Discord signal. Status code: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Exception while sending Discord notification: {e}")
        return False

if __name__ == "__main__":
    # 간단한 작동 테스트
    import os
    if os.getenv("DISCORD_WEBHOOK_URL"):
        print("Testing discord notification...")
        send_discord_signal(
            keyword="삼성전자",
            title="삼성전자, 차세대 HBM 테스트 최종 승인 획득",
            url="https://n.news.naver.com/mnews/article/001/0000000000",
            score=9,
            summary="- 하반기 실적 상승 및 점유율 회복 기대가 커지고 있습니다.\n- 엔비디아향 공급이 드디어 가속화될 전망입니다.\n- 이에 따라 주가 상승 모멘텀이 강화되고 있습니다.",
            keywords=["HBM", "삼성전자", "엔비디아"]
        )
    else:
        print("DISCORD_WEBHOOK_URL is empty. Test skipped.")
