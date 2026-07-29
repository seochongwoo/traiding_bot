import google.generativeai as genai
import json
from config import GEMINI_API_KEY

def analyze_news_sentiment(keyword: str, title: str, content: str) -> dict:
    """
    Gemini API를 사용하여 뉴스의 단기 주가 영향도 감성 스코어링(-10 ~ +10), 3줄 요약, 키워드 리스트를 JSON 구조로 받아옵니다.
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY is not configured. Skipping LLM analysis.")
        return {"score": 0, "summary": "API 키 미등록으로 분석 생략", "keywords": []}
        
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # 모델 초기화 (속도와 비용이 최적인 gemini-1.5-flash 사용)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        
        # 기사 내용이 없는 경우 타이틀만 보냅니다
        body_content = content if content else "(본문 수집 불가 - 제목으로만 분석)"
        
        prompt = f"""
다음은 주식/코인 투자 관점에서 분석할 뉴스의 제목과 본문 내용입니다.
이 뉴스가 해당 키워드 기업의 단기 주가(향후 1~5일)에 미칠 잠재적 영향을 분석해 주세요.

[분석 대상 핵심어]: {keyword}
[기사 제목]: {title}
[기사 본문]: {body_content}

지침:
1. 단기 주가에 미치는 영향을 -10 (가장 강력한 악재/폭락)에서 +10 (가장 강력한 호재/폭등) 사이의 정수 점수(score)로 평가하세요. 0은 중립입니다.
2. 기사의 핵심 내용과 주가 영향 이유를 명확하게 포함하는 3줄 요약(summary)을 작성하세요. 요약은 읽기 쉽도록 줄바꿈(예: - 로 시작하는 각 리스트 형태로 총 3행)을 넣어 작성하십시오.
3. 관련 주요 키워드(keywords)를 3개에서 5개 사이로 추출하세요.

반드시 다음 JSON 스키마를 만족하는 유효한 JSON 형식으로만 정확히 반환해야 합니다:
{{
  "score": <정수 점수>,
  "summary": "<3줄 요약>",
  "keywords": ["키워드1", "키워드2", ...]
}}
"""
        response = model.generate_content(prompt)
        result = json.loads(response.text.strip())
        
        # 타입 및 범위 안정성 처리
        score = int(result.get("score", 0))
        # 스코어는 -10 ~ +10 제한
        score = max(-10, min(10, score))
        
        return {
            "score": score,
            "summary": result.get("summary", "요약 불가"),
            "keywords": result.get("keywords", [])
        }
        
    except Exception as e:
        print(f"Exception during Gemini analysis: {e}")
        # 오류 발생 시 기본 Fallback 반환
        return {
            "score": 0,
            "summary": f"AI 분석 중 오류 발생: {str(e)[:50]}...",
            "keywords": []
        }

if __name__ == "__main__":
    # 로컬 개발 테스트
    print("Testing Gemini analyzer...")
    res = analyze_news_sentiment(
        keyword="테슬라",
        title="테슬라, 2분기 깜짝 실적 발표... 영업이익 시장 예상치 상회",
        content="테슬라가 오늘 뉴욕 증시 장 마감 후 발표한 2분기 실적에서 매출 255억 달러, 주당 순이익 0.52달러를 기록해 월가의 예상을 크게 상회했습니다. 특히 에너지 저장장치(ESS) 부문의 견고한 성장이 실적을 견인했습니다."
    )
    print(res)
