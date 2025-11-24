import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import dateutil.parser
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import platform

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

# 6. 탭 메뉴 구성 (미국 뉴스 추가됨!)
tab_names = ["🔥 종합", "💰 경제", "💻 IT/과학", "💊 건강", "🇺🇸 미국 뉴스(US)"]
tabs = st.tabs(tab_names)
codes = ["ALL", "BUSINESS", "TECHNOLOGY", "HEALTH", "ALL_US"]  # 마지막은 구분용 코드

# 7. 콘텐츠 표시 로직
current_tab_index = 0

# 탭이 선택되었는지 확인하기 위해 각 탭 내부를 순회
# (Streamlit은 탭 클릭 이벤트를 직접 잡기보다, 각 탭 컨텍스트 안에서 그리는 방식입니다)

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
        # 엑셀 다운로드 버튼
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 엑셀(CSV)로 저장", csv, "search_news.csv", "text/csv")

# 검색어가 없을 경우 (탭 보여주기)
else:
    for i, tab in enumerate(tabs):
        with tab:
            # 미국 뉴스는 region을 'US'로 설정
            if i == 4:  # 마지막 탭(미국)
                df = get_news("ALL", region="US")
            else:
                df = get_news(codes[i], region="KR")

            if df is not None:
                # 1. 워드 클라우드 (토글이 켜져 있으면)
                if show_wc:
                    with st.expander("☁️ 주요 키워드 시각화 (Word Cloud)", expanded=True):
                        draw_wordcloud(df)

                # 2. 뉴스 리스트
                st.caption(f"수집된 기사: {len(df)}건")
                st.data_editor(
                    df,
                    column_config={
                        "제목": st.column_config.TextColumn("기사 제목", width="large"),
                        "링크": st.column_config.LinkColumn("원문", display_text="클릭"),
                        "발행일": st.column_config.TextColumn("시간", width="small")
                    },
                    use_container_width=True,
                    hide_index=True
                )

                # 3. 엑셀 다운로드 버튼 (Top 3 중 마지막 기능!)
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="💾 결과 파일로 저장 (Excel/CSV)",
                    data=csv,
                    file_name=f"news_result_{codes[i]}.csv",
                    mime="text/csv"
                )