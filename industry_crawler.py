import requests
import xml.etree.ElementTree as ET
import pandas as pd
import dateutil.parser

# 키워드 + 접미어 조합으로 검색 쿼리를 자동 생성
_PROBLEM_SUFFIXES = [
    "문제점", "어려움", "고민", "단점", "불편", "실패", "위기", "불만", "갈등", "피해",
]
_SOLUTION_SUFFIXES = [
    "해결방법", "해결책", "성공 전략", "노하우", "팁", "개선 방법", "극복", "대응 방법",
]
_CONCERN_SUFFIXES = [
    "힘든점", "문의", "상담", "고충", "현실", "실태",
]

# 제목 분류용 단어
_PROBLEM_WORDS = {
    "문제", "어려움", "실패", "단점", "불만", "이슈", "피해", "위기",
    "논란", "갈등", "하락", "감소", "차단", "제재", "경고", "위험",
    "손실", "분쟁", "정지", "삭제", "침해", "위반", "취소", "불편",
    "고민", "고충", "힘든", "한계", "리스크",
}
_SOLUTION_WORDS = {
    "해결", "방법", "전략", "팁", "개선", "극복", "대응", "성공",
    "성장", "증가", "향상", "최적화", "활용", "노하우", "비결",
    "사례", "공략", "돌파", "회복", "상승", "확대", "방안",
}


def _build_queries(keywords: list[str]) -> list[tuple[str, str]]:
    """키워드 목록에서 (검색쿼리, 유형) 튜플 리스트를 생성한다."""
    queries = []
    for kw in keywords:
        for s in _PROBLEM_SUFFIXES:
            queries.append((f"{kw} {s}", "문제·고민"))
        for s in _SOLUTION_SUFFIXES:
            queries.append((f"{kw} {s}", "해결방법"))
        for s in _CONCERN_SUFFIXES:
            queries.append((f"{kw} {s}", "문제·고민"))
    return queries


def _fetch_google_news(query: str) -> list[dict]:
    """Google News RSS에서 단일 쿼리 결과를 가져온다."""
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    )
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
            items.append({
                "제목": clean_title,
                "링크": link_el.text or "",
                "발행일": pub_date,
            })
        return items
    except Exception:
        return []


def _classify(title: str) -> str:
    """제목 키워드로 문제·고민 / 해결방법 / 복합 / 참고 분류."""
    has_problem = any(w in title for w in _PROBLEM_WORDS)
    has_solution = any(w in title for w in _SOLUTION_WORDS)
    if has_problem and has_solution:
        return "🟡 복합"
    if has_problem:
        return "🔴 문제·고민"
    if has_solution:
        return "🟢 해결방법"
    return "⚪ 참고"


def crawl_by_keywords(keywords: list[str]) -> pd.DataFrame:
    """
    사용자 키워드를 받아 문제·해결 관련 쿼리를 자동 생성하고
    Google News를 크롤링해 분류된 DataFrame을 반환한다.
    """
    queries = _build_queries(keywords)
    rows = []
    seen = set()

    for query, query_type in queries:
        for item in _fetch_google_news(query):
            if item["제목"] in seen:
                continue
            seen.add(item["제목"])
            item["검색쿼리"] = query
            item["쿼리유형"] = query_type
            item["분류"] = _classify(item["제목"])
            rows.append(item)

    if not rows:
        return pd.DataFrame(columns=["분류", "제목", "쿼리유형", "검색쿼리", "발행일", "링크"])

    df = pd.DataFrame(rows)
    order = {"🔴 문제·고민": 0, "🟡 복합": 1, "🟢 해결방법": 2, "⚪ 참고": 3}
    df["_sort"] = df["분류"].map(order).fillna(9)
    df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    return df[["분류", "제목", "쿼리유형", "검색쿼리", "발행일", "링크"]]


def summary_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return df["분류"].value_counts().to_dict()
