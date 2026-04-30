import requests
import xml.etree.ElementTree as ET
import pandas as pd
import dateutil.parser

# 유튜브 대행업 관련 검색 키워드 그룹
SEARCH_KEYWORD_GROUPS = {
    "대행사 운영 문제": [
        "유튜브 대행사 문제",
        "유튜브 마케팅 대행 단점",
        "크리에이터 대행사 갈등",
        "유튜브 채널 운영 어려움",
    ],
    "알고리즘·정책": [
        "유튜브 알고리즘 변화",
        "유튜브 정책 위반",
        "유튜브 저작권 문제",
        "유튜브 수익화 정지",
    ],
    "성장·수익": [
        "유튜브 조회수 하락",
        "유튜브 구독자 감소",
        "유튜브 수익 감소",
        "유튜브 채널 성장 정체",
    ],
    "해결 전략": [
        "유튜브 채널 성장 전략",
        "유튜브 마케팅 성공 사례",
        "유튜브 수익화 방법",
        "유튜브 알고리즘 활용법",
        "유튜브 조회수 높이는 법",
        "유튜브 대행 노하우",
    ],
}

# 제목에서 문제/해결 분류에 쓸 단어 사전
_PROBLEM_WORDS = {
    "문제", "어려움", "실패", "단점", "불만", "이슈", "피해", "위기",
    "논란", "갈등", "하락", "감소", "차단", "제재", "경고", "위험",
    "손실", "분쟁", "정지", "삭제", "침해", "위반", "취소",
}

_SOLUTION_WORDS = {
    "해결", "방법", "전략", "팁", "개선", "극복", "대응", "성공",
    "성장", "증가", "향상", "최적화", "활용", "노하우", "비결",
    "사례", "공략", "돌파", "회복", "상승", "확대",
}


def _fetch_google_news(query: str) -> list[dict]:
    """Google News RSS에서 단일 쿼리 결과를 가져온다."""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            date_el = item.find("pubDate")
            if title_el is None or link_el is None:
                continue
            raw_title = title_el.text or ""
            clean_title = raw_title.split(" - ")[0].strip()
            try:
                dt = dateutil.parser.parse(date_el.text)
                pub_date = dt.strftime("%m/%d %H:%M")
            except Exception:
                pub_date = date_el.text if date_el is not None else ""
            items.append({"제목": clean_title, "링크": link_el.text or "", "발행일": pub_date})
        return items
    except Exception:
        return []


def _classify(title: str) -> str:
    """제목 키워드로 문제점/해결방법/참고 분류."""
    words = set(title)
    # 글자 단위보다 부분 문자열 매칭이 더 정확
    has_problem = any(w in title for w in _PROBLEM_WORDS)
    has_solution = any(w in title for w in _SOLUTION_WORDS)

    if has_problem and not has_solution:
        return "🔴 문제점"
    if has_solution and not has_problem:
        return "🟢 해결방법"
    if has_problem and has_solution:
        return "🟡 복합"
    return "⚪ 참고"


def crawl_industry_news(selected_groups: list[str] | None = None) -> pd.DataFrame:
    """선택한 키워드 그룹에 대해 크롤링 후 분류된 DataFrame을 반환한다."""
    groups = selected_groups or list(SEARCH_KEYWORD_GROUPS.keys())
    rows = []
    seen_titles = set()

    for group in groups:
        keywords = SEARCH_KEYWORD_GROUPS.get(group, [])
        for kw in keywords:
            for item in _fetch_google_news(kw):
                if item["제목"] in seen_titles:
                    continue
                seen_titles.add(item["제목"])
                item["키워드그룹"] = group
                item["검색키워드"] = kw
                item["분류"] = _classify(item["제목"])
                rows.append(item)

    if not rows:
        return pd.DataFrame(columns=["분류", "제목", "키워드그룹", "검색키워드", "발행일", "링크"])

    df = pd.DataFrame(rows)
    # 분류 순서 정렬: 문제점 → 복합 → 해결방법 → 참고
    order = {"🔴 문제점": 0, "🟡 복합": 1, "🟢 해결방법": 2, "⚪ 참고": 3}
    df["_sort"] = df["분류"].map(order).fillna(9)
    df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    return df[["분류", "제목", "키워드그룹", "검색키워드", "발행일", "링크"]]


def summary_stats(df: pd.DataFrame) -> dict:
    """분류별 건수 요약을 반환한다."""
    if df.empty:
        return {}
    return df["분류"].value_counts().to_dict()
