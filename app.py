import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import dateutil.parser
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import platform
from industry_crawler import crawl_by_keywords, summary_stats

# 1. 페이지 설정
st.set_page_config(
    page_title="뉴스 트렌드 마스터 Pro",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)


# 2. 한글 폰트 설정 (워드클라우드 깨짐 방지)
def get_font_path():
    os_name = platform.system()
    if os_name == "Windows":
        return "c:/Windows/Fonts/malgun.ttf"  # 윈도우용 맑은고딕
    elif os_name == "Darwin":
        return "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # 맥용
    else:
        return None  # 리눅스 등은 기본 폰트 사용


# 3. 데이터 가져오는 함수 (미국 뉴스 기능 추가!)
@st.cache_data
def get_news(category_code, search_query=None, region="KR"):
    # 지역별 설정 (한국 vs 미국)
    if region == "KR":
        base_url = "https://news.google.com/rss"
        params = "hl=ko&gl=KR&ceid=KR:ko"
    else:  # US
        base_url = "https://news.google.com/rss"
        params = "hl=en-US&gl=US&ceid=US:en"

    # URL 조합
    if search_query:
        url = f"{base_url}/search?q={search_query}&{params}"
    elif category_code == "ALL":
        url = f"{base_url}?{params}"
    else:
        url = f"{base_url}/headlines/section/topic/{category_code}?{params}"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            data = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                link = item.find('link').text
                pubDate = item.find('pubDate').text

                # 제목 정리 (언론사명 분리)
                if region == "KR":
                    clean_title = title.split(' - ')[0]
                else:
                    clean_title = title  # 영어는 그대로 둠

                # 날짜 변환
                try:
                    dt = dateutil.parser.parse(pubDate)
                    formatted_date = dt.strftime("%m/%d %H:%M")
                except:
                    formatted_date = pubDate

                data.append({
                    '제목': clean_title,
                    '링크': link,
                    '발행일': formatted_date
                })
            return pd.DataFrame(data)
        else:
            return None
    except Exception as e:
        return None


# 4. 워드 클라우드 그리는 함수
def draw_wordcloud(df):
    if df is not None and not df.empty:
        text = " ".join(df['제목'])  # 모든 제목을 한 문장으로 합침
        font_path = get_font_path()

        # 워드클라우드 생성 설정
        wc = WordCloud(
            font_path=font_path,
            width=800, height=400,
            background_color="white",
            colormap="Dark2"  # 색상 테마
        ).generate(text)

        # 그림 그리기
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis("off")  # 축 없애기
        st.pyplot(fig)


# 5. 메인 화면 구성
st.title("📰 뉴스 트렌드 마스터 Pro")
st.markdown("---")

# 사이드바 설정
with st.sidebar:
    st.header("🔍 검색 및 설정")
    search_keyword = st.text_input("키워드 검색", placeholder="예: 삼성전자, AI")

    st.markdown("---")
    st.caption("추가 기능")
    # 워드클라우드 토글 버튼
    show_wc = st.toggle("☁️ 워드 클라우드 보기", value=True)

    if st.button('새로고침 🔄', use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 6. 탭 메뉴 구성
tab_names = ["🔥 종합", "💰 경제", "💻 IT/과학", "💊 건강", "🇺🇸 미국 뉴스(US)", "🔎 업종 문제 분석"]
tabs = st.tabs(tab_names)
codes = ["ALL", "BUSINESS", "TECHNOLOGY", "HEALTH", "ALL_US", "INDUSTRY"]  # 마지막은 구분용 코드

# 7. 콘텐츠 표시 로직

# 검색어가 있을 경우
if search_keyword:
    st.subheader(f"🔍 '{search_keyword}' 검색 결과")
    df = get_news(None, search_query=search_keyword)
    if show_wc:
        draw_wordcloud(df)

    if df is not None:
        st.data_editor(
            df,
            column_config={"링크": st.column_config.LinkColumn("링크", display_text="이동")},
            use_container_width=True, hide_index=True
        )
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 엑셀(CSV)로 저장", csv, "search_news.csv", "text/csv")

# 검색어가 없을 경우 (탭 보여주기)
else:
    for i, tab in enumerate(tabs):
        with tab:
            # ── 업종 문제·해결 분석 탭 ────────────────────────────────────
            if codes[i] == "INDUSTRY":
                st.subheader("🔎 업종 문제점 & 해결방법 크롤러")
                st.caption(
                    "업종 키워드를 입력하면 관련 **문제점, 고민, 해결방법**을 자동으로 수집·분류합니다."
                )

                # 키워드 입력
                raw_input = st.text_input(
                    "업종 키워드 입력 (쉼표로 여러 개 가능)",
                    placeholder="예: 유튜브 대행, 영상 편집, 인플루언서 마케팅",
                    key="industry_keyword_input",
                )

                if st.button("🔍 크롤링 시작", key="industry_crawl", use_container_width=True):
                    keywords = [k.strip() for k in raw_input.split(",") if k.strip()]
                    if not keywords:
                        st.warning("키워드를 한 개 이상 입력해 주세요.")
                    else:
                        with st.spinner(f"'{', '.join(keywords)}' 관련 기사 수집 중..."):
                            result_df = crawl_by_keywords(keywords)
                        st.session_state["industry_df"] = result_df
                        st.session_state["industry_keywords"] = keywords

                result_df = st.session_state.get("industry_df")

                if result_df is not None and not result_df.empty:
                    used_kw = st.session_state.get("industry_keywords", [])
                    st.success(f"키워드: **{', '.join(used_kw)}** — 총 {len(result_df)}건 수집")

                    # 요약 지표
                    stats = summary_stats(result_df)
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("🔴 문제·고민", stats.get("🔴 문제·고민", 0))
                    col2.metric("🟡 복합", stats.get("🟡 복합", 0))
                    col3.metric("🟢 해결방법", stats.get("🟢 해결방법", 0))
                    col4.metric("⚪ 참고", stats.get("⚪ 참고", 0))

                    st.markdown("---")

                    # 분류 필터
                    filter_options = ["전체"] + ["🔴 문제·고민", "🟡 복합", "🟢 해결방법", "⚪ 참고"]
                    selected_filter = st.radio(
                        "분류 필터",
                        options=filter_options,
                        horizontal=True,
                        key="industry_filter",
                    )
                    view_df = (
                        result_df
                        if selected_filter == "전체"
                        else result_df[result_df["분류"] == selected_filter]
                    )

                    st.caption(f"표시: {len(view_df)}건 / 전체 {len(result_df)}건")
                    st.data_editor(
                        view_df,
                        column_config={
                            "분류": st.column_config.TextColumn("분류", width="small"),
                            "제목": st.column_config.TextColumn("기사 제목", width="large"),
                            "쿼리유형": st.column_config.TextColumn("유형", width="small"),
                            "검색쿼리": st.column_config.TextColumn("검색쿼리", width="medium"),
                            "발행일": st.column_config.TextColumn("시간", width="small"),
                            "링크": st.column_config.LinkColumn("원문", display_text="클릭"),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

                    if show_wc:
                        with st.expander("☁️ 주요 키워드 시각화 (Word Cloud)", expanded=False):
                            draw_wordcloud(pd.DataFrame({"제목": view_df["제목"].tolist()}))

                    csv = view_df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "💾 결과 저장 (CSV)",
                        csv,
                        "industry_analysis.csv",
                        "text/csv",
                    )
                elif result_df is not None and result_df.empty:
                    st.warning("수집된 기사가 없습니다. 키워드를 바꿔서 다시 시도해 보세요.")
                else:
                    st.info("키워드를 입력하고 크롤링 시작 버튼을 눌러주세요.")

            # ── 일반 뉴스 탭 ──────────────────────────────────────────────
            else:
                if codes[i] == "ALL_US":
                    df = get_news("ALL", region="US")
                else:
                    df = get_news(codes[i], region="KR")

                if df is not None:
                    if show_wc:
                        with st.expander("☁️ 주요 키워드 시각화 (Word Cloud)", expanded=True):
                            draw_wordcloud(df)

                    st.caption(f"수집된 기사: {len(df)}건")
                    st.data_editor(
                        df,
                        column_config={
                            "제목": st.column_config.TextColumn("기사 제목", width="large"),
                            "링크": st.column_config.LinkColumn("원문", display_text="클릭"),
                            "발행일": st.column_config.TextColumn("시간", width="small"),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label="💾 결과 파일로 저장 (Excel/CSV)",
                        data=csv,
                        file_name=f"news_result_{codes[i]}.csv",
                        mime="text/csv",
                    )