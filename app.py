import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import dateutil.parser
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import platform
import os
import json

# 1. 페이지 설정
st.set_page_config(
    page_title="트렌드마스터 스튜디오",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 히스토리 저장 파일 경로
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

# 사용 모델 (비용 절감 우선)
CLAUDE_MODEL = "claude-sonnet-4-6"

# YouTube Data API
YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# 병원 원장 타겟 소재 키워드 프리셋
HOSPITAL_PRESETS = [
    "병원 경영", "병원 마케팅", "개원", "의료 정책",
    "병원 세무", "병원 노무", "비급여", "환자 응대",
]


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


# ───────────────────────────────────────────────
#  YouTube Data API 연동 (유튜브 트렌드)
# ───────────────────────────────────────────────
def _yt_build_df(items):
    """videos API 응답 items -> DataFrame (조회수 순)."""
    rows = []
    for it in items:
        sn = it.get("snippet", {})
        stt = it.get("statistics", {})
        vid = it.get("id")
        rows.append({
            "제목": sn.get("title", ""),
            "채널": sn.get("channelTitle", ""),
            "조회수": int(stt.get("viewCount", 0)) if stt.get("viewCount") else 0,
            "좋아요": int(stt.get("likeCount", 0)) if stt.get("likeCount") else 0,
            "링크": f"https://www.youtube.com/watch?v={vid}",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("조회수", ascending=False).reset_index(drop=True)
    return df


@st.cache_data(ttl=600)
def yt_search_videos(api_key, query, region="KR", max_results=25):
    """키워드로 영상 검색 후 조회수 통계까지 붙여 반환. (df, error)"""
    if not api_key:
        return None, "YouTube API 키가 필요합니다."
    try:
        # 1) 키워드로 영상 ID 검색 (조회수 순)
        r = requests.get(f"{YT_API_BASE}/search", params={
            "part": "snippet", "q": query, "type": "video",
            "maxResults": max_results, "order": "viewCount",
            "regionCode": region,
            "relevanceLanguage": "ko" if region == "KR" else "en",
            "key": api_key,
        })
        if r.status_code != 200:
            return None, f"검색 실패: {r.status_code} - {r.text[:200]}"
        ids = [it["id"]["videoId"] for it in r.json().get("items", [])
               if it.get("id", {}).get("videoId")]
        if not ids:
            return pd.DataFrame(), None
        # 2) 영상별 조회수/좋아요 통계 가져오기
        r2 = requests.get(f"{YT_API_BASE}/videos", params={
            "part": "snippet,statistics", "id": ",".join(ids), "key": api_key,
        })
        if r2.status_code != 200:
            return None, f"통계 조회 실패: {r2.status_code} - {r2.text[:200]}"
        return _yt_build_df(r2.json().get("items", [])), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=600)
def yt_popular_videos(api_key, region="KR", max_results=25):
    """인기 급상승 영상 반환. (df, error)"""
    if not api_key:
        return None, "YouTube API 키가 필요합니다."
    try:
        r = requests.get(f"{YT_API_BASE}/videos", params={
            "part": "snippet,statistics", "chart": "mostPopular",
            "regionCode": region, "maxResults": max_results, "key": api_key,
        })
        if r.status_code != 200:
            return None, f"불러오기 실패: {r.status_code} - {r.text[:200]}"
        return _yt_build_df(r.json().get("items", [])), None
    except Exception as e:
        return None, str(e)


# ───────────────────────────────────────────────
#  Claude API 연동 (기획안 / 대본 생성)
# ───────────────────────────────────────────────
def get_claude_client(api_key):
    """Anthropic 클라이언트 생성. 키가 없으면 None."""
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except Exception as e:
        st.error(f"Claude 클라이언트 생성 실패: {e}")
        return None


def call_claude(client, system_prompt, user_prompt, max_tokens):
    """Claude 메시지 호출 후 텍스트 반환."""
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return resp.content[0].text


# 공통 페르소나 (병원 원장 타겟)
PERSONA = (
    "당신은 '병원 원장(개원의·병원 경영진)'을 타겟 시청자로 하는 유튜브 채널의 "
    "전문 기획 작가입니다. 시청자는 바쁜 의사이자 경영자이므로, "
    "병원 경영·마케팅·세무/노무·의료 정책 관점에서 실질적으로 도움이 되는 "
    "인사이트를 신뢰감 있는 톤으로 전달합니다. 과장·낚시성 표현은 피합니다."
)


def generate_plan(client, topic, fmt):
    """기획안 생성: 제목 후보, 후킹, 타겟, 구성 개요."""
    fmt_desc = "쇼츠(60초 이내)" if fmt == "쇼츠" else "롱폼(약 10분)"
    user_prompt = f"""아래 소재로 유튜브 영상 기획안을 작성해 주세요.

[소재]
{topic}

[영상 형태]
{fmt_desc}

[출력 형식] 마크다운으로 다음 항목을 작성:
## 🎯 타겟 시청자
(병원 원장 관점에서 이 영상이 왜 필요한지 1~2줄)

## 🔖 제목 후보 (썸네일 카피) 5개
1. ~
(클릭을 부르되 과장 없이)

## 🪝 한 줄 후킹 (영상 시작 3초)
(시청자가 멈추게 만드는 첫 멘트)

## 🧩 구성 개요
({"쇼츠는 3단계로 간결하게" if fmt == "쇼츠" else "인트로 → 본론 2~4꼭지 → 아웃트로 구조로"})
"""
    return call_claude(client, PERSONA, user_prompt, max_tokens=1500)


def generate_script(client, topic, fmt, plan, length_min=10):
    """대본 생성: 형태별 분량/구조 적용."""
    if fmt == "쇼츠":
        spec = (
            "분량은 한국어 150~200자(말하기 45~55초). "
            "강한 후킹(3초 내) → 핵심 정보 1~2개 → 마무리 한 방 구조. "
            "빠르고 임팩트 있게, 군더더기 없이. 화면 자막 포인트도 [자막] 표기로 함께."
        )
        max_tokens = 1500
    else:
        target_chars = int(length_min * 300)  # 분당 약 300자
        spec = (
            f"분량은 약 {length_min}분, 한국어 {target_chars - 200}~{target_chars + 200}자. "
            "인트로(후킹+예고) → 본론 2~4꼭지(각 소제목) → 아웃트로(요약+구독 유도) 구조. "
            "각 꼭지 앞에 [00:00] 형식의 챕터 타임스탬프(대략치)와 소제목을 표기. "
            "병원 원장이 바로 실무에 적용할 수 있는 구체적 내용으로."
        )
        max_tokens = 4000

    user_prompt = f"""아래 소재와 기획안을 바탕으로 실제 촬영용 유튜브 대본(나레이션 멘트)을 작성해 주세요.

[소재]
{topic}

[형태] {fmt}
[작성 규격] {spec}

[참고 기획안]
{plan}

대본만 출력하세요. 멘트는 실제 말하듯 자연스럽게."""
    return call_claude(client, PERSONA, user_prompt, max_tokens=max_tokens)


# ───────────────────────────────────────────────
#  히스토리 저장/불러오기 (로컬 JSON)
# ───────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"히스토리 저장 실패: {e}")


# ───────────────────────────────────────────────
#  세션 상태 초기화
# ───────────────────────────────────────────────
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = ""
if "plan_result" not in st.session_state:
    st.session_state.plan_result = ""
if "script_result" not in st.session_state:
    st.session_state.script_result = ""
if "history" not in st.session_state:
    st.session_state.history = load_history()
if "trend_titles" not in st.session_state:
    st.session_state.trend_titles = []
if "yt_titles" not in st.session_state:
    st.session_state.yt_titles = []
if "yt_df" not in st.session_state:
    st.session_state.yt_df = None


# 5. 메인 화면 구성
st.title("🎬 트렌드마스터 스튜디오")
st.caption("뉴스 트렌드 수집부터 병원 원장 타겟 유튜브 기획·대본 생성까지")
st.markdown("---")

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")

    # Claude API 키
    api_key = st.text_input(
        "Claude API 키",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="기획·대본 생성에 사용됩니다. 입력값은 세션에만 보관됩니다.",
    )
    st.caption(f"모델: `{CLAUDE_MODEL}`")

    # YouTube Data API 키
    yt_api_key = st.text_input(
        "YouTube API 키",
        type="password",
        value=os.environ.get("YOUTUBE_API_KEY", ""),
        help="유튜브 트렌드(인기 영상 분석)에 사용됩니다. 무료로 발급 가능합니다.",
    )

    st.markdown("---")
    st.subheader("🔍 트렌드 검색")
    search_keyword = st.text_input("키워드 검색", placeholder="예: 병원 경영, 개원")

    st.caption("병원 원장 추천 키워드")
    preset_cols = st.columns(2)
    for idx, kw in enumerate(HOSPITAL_PRESETS):
        if preset_cols[idx % 2].button(kw, use_container_width=True, key=f"preset_{kw}"):
            st.session_state.preset_keyword = kw
            st.rerun()

    show_wc = st.toggle("☁️ 워드 클라우드 보기", value=True)

    if st.button('새로고침 🔄', use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# 프리셋 버튼이 눌렸으면 검색어로 사용
if st.session_state.get("preset_keyword") and not search_keyword:
    search_keyword = st.session_state.preset_keyword

# 6. 상위 탭: 뉴스 트렌드 / 유튜브 트렌드 / 기획·대본 / 히스토리
main_tabs = st.tabs(["📰 뉴스 트렌드", "▶️ 유튜브 트렌드", "🎬 기획·대본", "🗂️ 히스토리"])

# ===== 탭 1: 트렌드 =====
with main_tabs[0]:
    if search_keyword:
        st.subheader(f"🔍 '{search_keyword}' 검색 결과")
        df = get_news(None, search_query=search_keyword)
        if show_wc and df is not None:
            draw_wordcloud(df)

        if df is not None:
            st.session_state.trend_titles = df['제목'].tolist()
            st.data_editor(
                df,
                column_config={"링크": st.column_config.LinkColumn("링크", display_text="이동")},
                use_container_width=True, hide_index=True
            )
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("💾 엑셀(CSV)로 저장", csv, "search_news.csv", "text/csv")
        else:
            st.error("뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    else:
        sub_names = ["🔥 종합", "💰 경제", "💻 IT/과학", "💊 건강", "🇺🇸 미국 뉴스(US)"]
        sub_tabs = st.tabs(sub_names)
        codes = ["ALL", "BUSINESS", "TECHNOLOGY", "HEALTH", "ALL_US"]

        for i, tab in enumerate(sub_tabs):
            with tab:
                if i == 4:
                    df = get_news("ALL", region="US")
                else:
                    df = get_news(codes[i], region="KR")

                if df is not None:
                    if i == 0:
                        st.session_state.trend_titles = df['제목'].tolist()
                    if show_wc:
                        with st.expander("☁️ 주요 키워드 시각화 (Word Cloud)", expanded=True):
                            draw_wordcloud(df)

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
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="💾 결과 파일로 저장 (Excel/CSV)",
                        data=csv,
                        file_name=f"news_result_{codes[i]}.csv",
                        mime="text/csv",
                        key=f"dl_{codes[i]}"
                    )

# ===== 탭 2: 유튜브 트렌드 =====
with main_tabs[1]:
    st.subheader("▶️ 유튜브 트렌드 분석")
    if not yt_api_key:
        st.warning("사이드바에 **YouTube API 키**를 입력하면 유튜브 인기 영상을 분석할 수 있어요. (무료 발급)")

    yc1, yc2 = st.columns([3, 1])
    with yc1:
        yt_query = st.text_input(
            "유튜브 키워드 검색",
            placeholder="예: 병원 마케팅, 개원 준비, 비급여",
            key="yt_query",
        )
    with yc2:
        yt_mode = st.radio("모드", ["키워드 검색", "인기 급상승"], key="yt_mode")

    if st.button("🔎 유튜브 분석", type="primary", key="yt_run"):
        if not yt_api_key:
            st.error("사이드바에 YouTube API 키를 먼저 입력해 주세요.")
        else:
            with st.spinner("유튜브 데이터를 가져오는 중..."):
                if yt_mode == "인기 급상승":
                    ydf, yerr = yt_popular_videos(yt_api_key)
                elif not yt_query.strip():
                    ydf, yerr = None, "검색할 키워드를 입력해 주세요."
                else:
                    ydf, yerr = yt_search_videos(yt_api_key, yt_query.strip())
            if yerr:
                st.error(yerr)
            elif ydf is not None and not ydf.empty:
                st.session_state.yt_df = ydf
                st.session_state.yt_titles = ydf["제목"].tolist()
            elif ydf is not None:
                st.info("결과가 없습니다. 다른 키워드로 시도해 보세요.")

    ydf = st.session_state.yt_df
    if ydf is not None and not ydf.empty:
        st.caption(f"인기 영상 {len(ydf)}건 · 조회수 순 정렬")
        if show_wc:
            with st.expander("☁️ 인기 영상 제목 워드클라우드", expanded=False):
                draw_wordcloud(ydf)
        st.data_editor(
            ydf,
            column_config={
                "제목": st.column_config.TextColumn("영상 제목", width="large"),
                "채널": st.column_config.TextColumn("채널", width="medium"),
                "조회수": st.column_config.NumberColumn("조회수", format="%d"),
                "좋아요": st.column_config.NumberColumn("좋아요", format="%d"),
                "링크": st.column_config.LinkColumn("영상", display_text="보기"),
            },
            use_container_width=True, hide_index=True,
        )
        st.caption("💡 마음에 드는 영상 제목을 '🎬 기획·대본' 탭에서 소재로 선택할 수 있어요.")
        csv = ydf.to_csv(index=False).encode("utf-8-sig")
        st.download_button("💾 결과 CSV 저장", csv, "youtube_trend.csv", "text/csv", key="dl_yt")

# ===== 탭 3: 기획·대본 =====
with main_tabs[2]:
    st.subheader("✍️ 소재 선택")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        # 뉴스/유튜브 트렌드에서 수집한 제목 중 고르기
        news_opts = [f"📰 {t}" for t in st.session_state.trend_titles]
        yt_opts = [f"▶️ {t}" for t in st.session_state.yt_titles]
        title_options = ["(직접 입력)"] + news_opts + yt_opts
        picked = st.selectbox("트렌드에서 소재 고르기 (뉴스·유튜브)", title_options)
        if picked != "(직접 입력)":
            picked = picked[2:].strip()  # 앞의 아이콘 제거
        if picked != "(직접 입력)":
            st.session_state.selected_topic = picked
    with col_b:
        st.session_state.selected_topic = st.text_area(
            "소재 (직접 수정 가능)",
            value=st.session_state.selected_topic,
            height=80,
            placeholder="예: 비급여 진료비 공개 의무화, 병원은 어떻게 대응할까",
        )

    st.markdown("---")
    st.subheader("🎛️ 영상 형태")
    c1, c2 = st.columns([1, 2])
    with c1:
        fmt = st.radio("형태 선택", ["쇼츠", "롱폼"], horizontal=True)
    with c2:
        length_min = 10
        if fmt == "롱폼":
            length_min = st.slider("롱폼 분량(분)", min_value=5, max_value=15, value=10)

    topic = st.session_state.selected_topic.strip()
    client = get_claude_client(api_key)

    st.markdown("---")
    btn1, btn2 = st.columns(2)
    with btn1:
        gen_plan = st.button("📝 기획안 생성", use_container_width=True, type="primary")
    with btn2:
        gen_script = st.button("🎬 대본 생성", use_container_width=True)

    if gen_plan or gen_script:
        if not client:
            st.error("사이드바에 Claude API 키를 먼저 입력해 주세요.")
        elif not topic:
            st.error("소재를 입력하거나 트렌드에서 선택해 주세요.")
        else:
            try:
                if gen_plan:
                    with st.spinner("기획안 생성 중..."):
                        st.session_state.plan_result = generate_plan(client, topic, fmt)
                        st.session_state.script_result = ""  # 새 기획이면 대본 초기화
                if gen_script:
                    with st.spinner("대본 생성 중..."):
                        # 기획안이 없으면 즉석에서 만들어 사용
                        plan_for_script = st.session_state.plan_result
                        if not plan_for_script:
                            plan_for_script = generate_plan(client, topic, fmt)
                            st.session_state.plan_result = plan_for_script
                        st.session_state.script_result = generate_script(
                            client, topic, fmt, plan_for_script, length_min
                        )
                        # 히스토리에 저장
                        entry = {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "topic": topic,
                            "format": fmt,
                            "length_min": length_min if fmt == "롱폼" else 1,
                            "plan": st.session_state.plan_result,
                            "script": st.session_state.script_result,
                        }
                        st.session_state.history.insert(0, entry)
                        save_history(st.session_state.history)
            except Exception as e:
                st.error(f"생성 중 오류가 발생했습니다: {e}")

    # 결과 표시
    if st.session_state.plan_result:
        st.markdown("### 📋 기획안")
        st.markdown(st.session_state.plan_result)
        st.download_button(
            "💾 기획안 TXT 저장",
            st.session_state.plan_result.encode("utf-8"),
            "plan.txt", "text/plain", key="dl_plan"
        )

    if st.session_state.script_result:
        st.markdown("### 🎬 대본")
        st.markdown(st.session_state.script_result)
        st.download_button(
            "💾 대본 TXT 저장",
            st.session_state.script_result.encode("utf-8"),
            "script.txt", "text/plain", key="dl_script"
        )

# ===== 탭 4: 히스토리 =====
with main_tabs[3]:
    st.subheader("🗂️ 생성 히스토리")
    if not st.session_state.history:
        st.info("아직 저장된 기획·대본이 없습니다. '기획·대본' 탭에서 대본을 생성하면 자동 저장됩니다.")
    else:
        cols = st.columns([3, 1])
        cols[0].caption(f"총 {len(st.session_state.history)}건")
        if cols[1].button("🗑️ 전체 삭제", use_container_width=True):
            st.session_state.history = []
            save_history([])
            st.rerun()

        for idx, entry in enumerate(st.session_state.history):
            label = f"[{entry['format']}] {entry['topic'][:40]} · {entry['timestamp']}"
            with st.expander(label):
                if entry.get("plan"):
                    st.markdown("**📋 기획안**")
                    st.markdown(entry["plan"])
                if entry.get("script"):
                    st.markdown("**🎬 대본**")
                    st.markdown(entry["script"])
                    st.download_button(
                        "💾 대본 TXT 저장",
                        entry["script"].encode("utf-8"),
                        f"script_{idx}.txt", "text/plain", key=f"dl_hist_{idx}"
                    )
