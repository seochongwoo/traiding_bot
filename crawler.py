import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import quote

# 봇 차단 방지를 위한 브라우저 헤더 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

def parse_news_div(div) -> dict:
    """
    네이버 뉴스 검색 결과의 단일 div 노드에서 제목, 원본 링크, 네이버 뉴스 링크, 스니펫을 구조적으로 추출합니다.
    """
    anchors = div.select("a")
    urls_data = []
    for a in anchors:
        href = a.get("href", "")
        text = a.get_text().strip()
        if href.startswith("http") and not any(x in href for x in ["keep.naver.com"]):
            urls_data.append({"href": href, "text": text})
            
    # 네이버 뉴스 링크 추출
    naver_news_link = ""
    for item in urls_data:
        if "news.naver.com" in item["href"] or "n.news.naver.com" in item["href"]:
            if "media.naver.com" not in item["href"]:
                naver_news_link = item["href"]
                break
                
    # 일반 기사 링크 추출
    original_candidates = []
    for item in urls_data:
        href = item["href"]
        if "news.naver.com" not in href and "naver.com" not in href:
            original_candidates.append(item)
            
    if not original_candidates:
        return None
        
    # 동일한 URL을 가진 요소들끼리 그룹화
    href_groups = {}
    for item in original_candidates:
        href = item["href"]
        if href not in href_groups:
            href_groups[href] = []
        href_groups[href].append(item)
        
    # URL 경로 뎁스(슬래시 수)와 문자열 길이를 바탕으로 기사 원본 상세 URL 판별 (홈페이지 주소 필터링)
    sorted_hrefs = sorted(href_groups.keys(), key=lambda h: (len(h.split('/')), len(h)), reverse=True)
    if not sorted_hrefs:
        return None
        
    article_href = sorted_hrefs[0]
    article_items = href_groups[article_href]
    
    # 제목 추출 (텍스트 길이가 10자 이상인 첫 번째 요소 우선 선택)
    valid_titles = [x["text"] for x in article_items if len(x["text"]) > 10]
    title = valid_titles[0] if valid_titles else article_items[0]["text"]
    
    # 스니펫 추출 (제목과 다르고 길이가 15자 이상인 본문 요약문 조각 선택)
    snippet = ""
    for x in article_items:
        txt = x["text"]
        if txt != title and len(txt) > 15:
            snippet = txt
            break
            
    return {
        "title": title,
        "original_link": article_href,
        "naver_news_link": naver_news_link,
        "snippet": snippet
    }

def fetch_news_list(keyword: str, limit: int = 5) -> list:
    """
    네이버 뉴스 검색결과에서 최신순(sort=1)으로 뉴스 기사 리스트를 가져옵니다.
    """
    encoded_keyword = quote(keyword)
    url = f"https://search.naver.com/search.naver?where=news&query={encoded_keyword}&sm=tab_opt&sort=1"
    
    news_items = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch news list. Status code: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. 현대적인 fds-news-item-list-tab 레이아웃 파싱 시도
        container = soup.select_one(".fds-news-item-list-tab")
        divs = container.find_all("div", recursive=False) if container else []
        
        count = 0
        if divs:
            for div in divs:
                if count >= limit:
                    break
                parsed = parse_news_div(div)
                if parsed:
                    news_items.append({
                        "keyword": keyword,
                        "title": parsed["title"],
                        "original_link": parsed["original_link"],
                        "naver_news_link": parsed["naver_news_link"],
                        "snippet": parsed["snippet"]
                    })
                    count += 1
                    
        # 2. 만약 현대적 레이아웃으로 파싱이 안 되었을 경우 레거시 (li.bx) 레이아웃 폴백 시도
        if not news_items:
            articles = soup.select("li.bx")
            for article in articles:
                if count >= limit:
                    break
                    
                tit_element = article.select_one("a.news_tit")
                if not tit_element:
                    continue
                    
                title = tit_element.get_text().strip()
                original_link = tit_element.get("href", "")
                
                naver_news_link = ""
                info_links = article.select("div.info_group a.info")
                for info in info_links:
                    href = info.get("href", "")
                    if "news.naver.com" in href or "n.news.naver.com" in href:
                        naver_news_link = href
                        break
                
                snippet_element = article.select_one(".api_txt_lines")
                snippet = snippet_element.get_text().strip() if snippet_element else ""
                
                news_items.append({
                    "keyword": keyword,
                    "title": title,
                    "original_link": original_link,
                    "naver_news_link": naver_news_link,
                    "snippet": snippet
                })
                count += 1
                
    except Exception as e:
        print(f"Exception during fetching news list: {e}")
        
    return news_items

def get_news_content(url: str) -> str:
    """
    네이버 뉴스 상세 페이지에서 본문 텍스트(#dic_area)를 크롤링합니다.
    """
    if not url:
        return ""
        
    try:
        # 차단 방지를 위해 시간 지연을 약간 줍니다 (0.5초)
        time.sleep(0.5)
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return ""
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 네이버 뉴스 최신 본문 영역 ID: #dic_area
        body = soup.select_one("#dic_area")
        if body:
            # 기자 정보, 언론사 정보 등 불필요한 공백/태그 제거 및 텍스트 취합
            return body.get_text(strip=True)
            
        # 예전 네이버 뉴스 본문 영역 ID: #articleBodyContents
        body_old = soup.select_one("#articleBodyContents")
        if body_old:
            return body_old.get_text(strip=True)
            
    except Exception as e:
        print(f"Exception during fetching news content from {url}: {e}")
        
    return ""

if __name__ == "__main__":
    # 간단한 작동 테스트
    keyword = "삼성전자"
    print(f"Testing crawler for keyword: '{keyword}'...")
    news = fetch_news_list(keyword, limit=3)
    
    for i, item in enumerate(news, 1):
        print(f"\n[{i}] {item['title']}")
        print(f"    - 원본 링크: {item['original_link']}")
        print(f"    - 네이버 뉴스 링크: {item['naver_news_link']}")
        print(f"    - 스니펫: {item['snippet'][:50]}...")
        
        if item['naver_news_link']:
            content = get_news_content(item['naver_news_link'])
            print(f"    - 상세 본문 수집 성공 (길이: {len(content)} 자)")
        else:
            print("    - 네이버 뉴스 링크 없음")
