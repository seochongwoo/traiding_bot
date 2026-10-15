"""
동일 이슈를 다룬 타 언론사 기사(의미 중복)를 제목 단어 집합의 자카드 유사도로 걸러냅니다.
"""
import re

_STOPWORDS = {
    "단독", "속보", "종합", "포토", "영상", "기자", "뉴스", "오늘", "이번", "관련",
    "위해", "대한", "통해", "에서", "으로", "그리고", "the", "and", "사진", "그래픽"
}

_PARTICLES = r"(은|는|이|가|을|를|의|에|에서|서|도|와|과|로|으로|등|된|한|그룹|사|측)$"


def tokenize(title: str, keyword: str = "", synonyms=None) -> set:
    text = re.sub(r"[^0-9A-Za-z가-힣]+", " ", title or "").lower()
    drop_words = {keyword.lower()} | {s.lower() for s in (synonyms or [])}
    
    tokens = set()
    for tok in text.split():
        # 불용 조사 및 꼬리 접미사 제거
        tok = re.sub(_PARTICLES, "", tok) if len(tok) > 2 else tok
        # 키워드 접두사 제거 (예: 현대차그룹 -> 제거)
        for kw in drop_words:
            if kw and tok.startswith(kw):
                tok = tok[len(kw):]
                break
        tok = re.sub(_PARTICLES, "", tok) if len(tok) > 2 else tok
        
        if len(tok) < 2 or tok in _STOPWORDS or tok in drop_words:
            continue
        tokens.add(tok)
    return tokens


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_duplicate(title: str, recent_titles, keyword: str = "", synonyms=None, threshold: float = 0.4):
    """가장 유사한 최근 제목과 유사도를 반환합니다. 임계치 이상이면 (유사제목, 유사도)."""
    target = tokenize(title, keyword, synonyms)
    best, best_score = None, 0.0
    for other in recent_titles:
        other_tokens = tokenize(other, keyword, synonyms)
        s = jaccard(target, other_tokens)
        if s > best_score:
            best, best_score = other, s
    return (best, best_score) if best_score >= threshold else (None, best_score)
