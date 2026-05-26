#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
벤치마킹 트렌드 대시보드
─────────────────────────
경쟁/참고 채널들의 주제·트렌드를 한눈에 분석하는 Streamlit 앱
"""

import json
import os
import re
import platform
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO

import dateutil.parser
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
import requests
import streamlit as st

matplotlib.use("Agg")   # Streamlit 환경용 백엔드

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

try:
    from wordcloud import WordCloud
    HAS_WC = True
except ImportError:
    HAS_WC = False


# ════════════════════════════════════════════════════════════
#  페이지 설정
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="벤치마킹 트렌드 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.dash-header {
    background: linear-gradient(135deg,#1e3a8a,#3b82f6);
    padding:1.2rem 1.8rem; border-radius:12px; color:white; margin-bottom:1.2rem;
}
.dash-header h1 { margin:0; font-size:1.6rem; }
.dash-header p  { margin:.3rem 0 0; opacity:.85; font-size:.85rem; }
div[data-testid="metric-container"] {
    background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:.7rem 1rem;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  상수 & 유틸
# ════════════════════════════════════════════════════════════
CHANNELS_FILE = os.path.join(os.path.dirname(__file__), "benchmark_channels.json")

STOPWORDS_KR = {
    "이","가","을","를","은","는","의","에","에서","로","으로","와","과","도","만",
    "까지","부터","그","저","것","수","때","더","또","및","등","년","월","일","위",
    "한","하는","있는","없는","많은","좋은","다","하다","있다","없다","됩니다","합니다",
    "이런","저런","그런","어떤","이제","정말","너무","매우","아주","바로","같은","대한",
    "위한","통해","대해","관해","이후","이전","이상","이하","최고","최대","최소","최신",
    "완전","진짜","제대로","드디어","결국","마침내","무조건","반드시","꼭","절대",
    "ep","EP","Part","PART","vlog","VLOG","video","VIDEO","|","-","/","·","ㅣ","!","?",
}

DAY_KR = ["월","화","수","목","금","토","일"]
CHANNEL_COLORS = [
    "#3b82f6","#ef4444","#10b981","#f59e0b",
    "#8b5cf6","#ec4899","#06b6d4","#84cc16",
]


def get_font_path() -> str | None:
    sys = platform.system()
    candidates = {
        "Windows": ["C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/NanumGothic.ttf"],
        "Darwin":  ["/System/Library/Fonts/AppleSDGothicNeo.ttc",
                    "/Library/Fonts/NanumGothic.ttf"],
        "Linux":   ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    }
    for path in candidates.get(sys, []):
        if os.path.exists(path):
            return path
    return None


def setup_mpl_font():
    fp = get_font_path()
    if fp:
        try:
            font = fm.FontProperties(fname=fp)
            matplotlib.rcParams["font.family"] = font.get_name()
        except Exception:
            pass
    matplotlib.rcParams["axes.unicode_minus"] = False


setup_mpl_font()


def fmt_num(n) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "-"
    n = int(n)
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n/10_000:.1f}만"
    if n >= 1_000:
        return f"{n/1_000:.1f}천"
    return f"{n:,}"


def extract_keywords(titles: list[str], top_n: int = 40) -> list[tuple[str, int]]:
    """제목 리스트에서 한국어 키워드 빈도 추출"""
    words = []
    for title in titles:
        tokens = re.split(r"[\s\|\-\/\[\]\(\)·「」『』【】〈〉《》\.,!?:;~]+", title)
        for tok in tokens:
            tok = tok.strip().strip("'\"")
            if len(tok) < 2:
                continue
            if tok.lower() in {w.lower() for w in STOPWORDS_KR}:
                continue
            if re.fullmatch(r"[\d\s]+", tok):
                continue
            words.append(tok)
    return Counter(words).most_common(top_n)


# ════════════════════════════════════════════════════════════
#  채널 목록 영속 저장 (JSON)
# ════════════════════════════════════════════════════════════

def load_channels() -> list[dict]:
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_channels(channels: list[dict]):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════
#  데이터 수집
# ════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yt_channel(url: str, days_back: int, max_videos: int) -> pd.DataFrame:
    """yt-dlp로 채널 영상 목록 수집 → DataFrame"""
    if not HAS_YTDLP:
        return pd.DataFrame()

    base = url.rstrip("/")
    ydl_opts = {
        "extract_flat": "in_playlist",
        "playlistend": max_videos,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    info = None
    for try_url in [base + "/videos", base, base + "/streams"]:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(try_url, download=False)
            if result and result.get("entries"):
                info = result
                break
        except Exception:
            continue

    if not info:
        return pd.DataFrame()

    channel_name = info.get("channel") or info.get("uploader") or info.get("title") or url
    cutoff = datetime.now() - timedelta(days=days_back)
    rows = []

    for e in (info.get("entries") or []):
        if not e:
            continue
        ds = e.get("upload_date", "")
        upload_dt = None
        if ds:
            try:
                upload_dt = datetime.strptime(ds, "%Y%m%d")
                if upload_dt < cutoff:
                    continue
            except ValueError:
                pass

        rows.append({
            "channel":      channel_name,
            "title":        e.get("title", ""),
            "view_count":   e.get("view_count") or 0,
            "upload_date":  upload_dt.strftime("%Y-%m-%d") if upload_dt else None,
            "day_of_week":  DAY_KR[upload_dt.weekday()] if upload_dt else None,
            "week":         upload_dt.strftime("%Y-W%U") if upload_dt else None,
            "thumbnail":    e.get("thumbnail", ""),
            "video_url":    f"https://www.youtube.com/watch?v={e.get('id','')}" if e.get("id") else "",
        })

    return pd.DataFrame(rows)


@st.cache_data(ttl=1800, show_spinner=False)
def discover_channels(keyword: str, max_results: int = 30) -> list[dict]:
    """키워드 검색으로 관련 유튜브 채널 자동 발굴"""
    if not HAS_YTDLP:
        return []
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{keyword}", download=False)
        entries = [e for e in (info.get("entries") or []) if e] if info else []
    except Exception:
        return []

    seen_urls = set()
    channels = []
    for e in entries:
        ch_url  = e.get("channel_url") or e.get("uploader_url") or ""
        ch_name = e.get("channel") or e.get("uploader") or ""
        if not ch_url or ch_url in seen_urls:
            continue
        seen_urls.add(ch_url)
        # @핸들 형식으로 정규화
        if "/channel/" in ch_url or "/@" in ch_url:
            pass
        channels.append({
            "name":         ch_name,
            "url":          ch_url,
            "sample_title": e.get("title", ""),
            "view_count":   e.get("view_count") or 0,
        })
    return channels


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(keyword: str, region: str = "KR") -> pd.DataFrame:
    """Google News RSS로 키워드 관련 뉴스 수집"""
    if region == "KR":
        url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    else:
        url = f"https://news.google.com/rss/search?q={keyword}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, timeout=10)
        root = ET.fromstring(resp.content)
        rows = []
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            link  = item.find("link").text or ""
            pub   = item.find("pubDate").text or ""
            try:
                dt = dateutil.parser.parse(pub).strftime("%m/%d %H:%M")
            except Exception:
                dt = pub
            rows.append({"제목": title.split(" - ")[0], "링크": link, "발행일": dt})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


# ════════════════════════════════════════════════════════════
#  시각화 함수
# ════════════════════════════════════════════════════════════

def fig_wordcloud(kw_list: list[tuple[str, int]]) -> plt.Figure | None:
    if not HAS_WC or not kw_list:
        return None
    freq = {w: c for w, c in kw_list}
    fp   = get_font_path()
    wc   = WordCloud(
        font_path=fp,
        width=900, height=420,
        background_color="white",
        colormap="tab10",
        max_words=60,
    ).generate_from_frequencies(freq)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    fig.tight_layout(pad=0)
    return fig


def fig_bar(labels: list, values: list, title: str,
            color: str = "#3b82f6", horizontal: bool = True) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.35) if horizontal else 4))
    if horizontal:
        bars = ax.barh(labels[::-1], values[::-1], color=color, height=0.65)
        ax.bar_label(bars, fmt="%,.0f", padding=4, fontsize=8)
        ax.set_xlabel("횟수")
    else:
        bars = ax.bar(labels, values, color=color, width=0.65)
        ax.bar_label(bars, fmt="%,.0f", padding=2, fontsize=9)
        ax.set_ylabel("횟수")
    ax.set_title(title, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_upload_pattern(df: pd.DataFrame) -> plt.Figure:
    """요일별 업로드 횟수 막대 차트"""
    day_counts = {d: 0 for d in DAY_KR}
    for _, row in df.iterrows():
        if row.get("day_of_week") in day_counts:
            day_counts[row["day_of_week"]] += 1

    fig, ax = plt.subplots(figsize=(8, 3.5))
    colors = ["#ef4444" if d in ("토","일") else "#3b82f6" for d in DAY_KR]
    bars = ax.bar(DAY_KR, [day_counts[d] for d in DAY_KR], color=colors, width=0.6)
    ax.bar_label(bars, padding=2, fontsize=9)
    ax.set_title("요일별 업로드 횟수", pad=10)
    ax.set_ylabel("영상 수")
    ax.spines[["top","right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_channel_compare(channel_dfs: dict[str, pd.DataFrame]) -> plt.Figure:
    """채널별 평균 조회수 비교"""
    names, avgs, totals = [], [], []
    for name, df in channel_dfs.items():
        if df.empty:
            continue
        names.append(name[:12])          # 이름 너무 길면 자르기
        avgs.append(int(df["view_count"].mean()))
        totals.append(len(df))

    if not names:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center")
        return fig

    x = range(len(names))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # 평균 조회수
    colors = [CHANNEL_COLORS[i % len(CHANNEL_COLORS)] for i in range(len(names))]
    bars1 = ax1.bar(x, avgs, color=colors, width=0.6)
    ax1.bar_label(bars1, labels=[fmt_num(v) for v in avgs], padding=3, fontsize=9)
    ax1.set_xticks(list(x)); ax1.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
    ax1.set_title("채널별 평균 조회수"); ax1.set_ylabel("평균 조회수")
    ax1.spines[["top","right"]].set_visible(False)

    # 영상 수
    bars2 = ax2.bar(x, totals, color=colors, width=0.6)
    ax2.bar_label(bars2, fmt="%d", padding=3, fontsize=9)
    ax2.set_xticks(list(x)); ax2.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
    ax2.set_title("채널별 수집 영상 수"); ax2.set_ylabel("영상 수")
    ax2.spines[["top","right"]].set_visible(False)

    fig.tight_layout()
    return fig


def fig_keyword_by_channel(channel_dfs: dict[str, pd.DataFrame], top_kw: list[str]) -> plt.Figure:
    """상위 키워드의 채널별 출현 횟수 누적 막대"""
    kw_top = top_kw[:15]
    channel_names = list(channel_dfs.keys())
    data = {ch: [] for ch in channel_names}

    for ch, df in channel_dfs.items():
        titles = df["title"].tolist() if not df.empty else []
        counts = dict(extract_keywords(titles, top_n=200))
        data[ch] = [counts.get(kw, 0) for kw in kw_top]

    fig, ax = plt.subplots(figsize=(11, 4.5))
    bottom = [0] * len(kw_top)
    for i, ch in enumerate(channel_names):
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        ax.bar(kw_top, data[ch], bottom=bottom, label=ch[:12], color=color, width=0.6)
        bottom = [b + v for b, v in zip(bottom, data[ch])]

    ax.set_title("키워드별 채널 분포 (누적)", pad=10)
    ax.set_ylabel("출현 횟수")
    ax.legend(loc="upper right", fontsize=8)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    ax.spines[["top","right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_weekly_uploads(channel_dfs: dict[str, pd.DataFrame]) -> plt.Figure:
    """채널별 주간 업로드 추이"""
    fig, ax = plt.subplots(figsize=(11, 4))

    for i, (ch, df) in enumerate(channel_dfs.items()):
        if df.empty or "week" not in df.columns:
            continue
        wk = df.groupby("week").size().reset_index(name="count")
        wk = wk.sort_values("week")
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        ax.plot(wk["week"], wk["count"], marker="o", label=ch[:12], color=color, linewidth=2)

    ax.set_title("채널별 주간 업로드 수 추이", pad=10)
    ax.set_ylabel("영상 수")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=8)
    ax.spines[["top","right"]].set_visible(False)
    fig.tight_layout()
    return fig


# ════════════════════════════════════════════════════════════
#  사이드바 — 채널 관리
# ════════════════════════════════════════════════════════════

if "channels"      not in st.session_state: st.session_state.channels      = load_channels()
if "yt_data"       not in st.session_state: st.session_state.yt_data       = {}
if "last_collected" not in st.session_state: st.session_state.last_collected = None
if "discover_res"  not in st.session_state: st.session_state.discover_res  = []

with st.sidebar:

    # ════════════════════════════════════════
    #  🔍 키워드로 채널 자동 발굴
    # ════════════════════════════════════════
    st.markdown("## 🔍 채널 자동 발굴")
    st.caption("키워드를 넣으면 관련 채널을 자동으로 찾아줍니다")

    with st.form("discover_form", clear_on_submit=False):
        disc_keyword = st.text_input("발굴 키워드", placeholder="예: 병원 마케팅")
        disc_btn = st.form_submit_button("🔎 채널 찾기", use_container_width=True)

    if disc_btn and disc_keyword:
        with st.spinner(f"'{disc_keyword}' 관련 채널 탐색 중..."):
            st.session_state.discover_res = discover_channels(disc_keyword, max_results=30)

    if st.session_state.discover_res:
        st.markdown(f"**발굴된 채널 {len(st.session_state.discover_res)}개** — 추가할 채널을 선택하세요")
        existing_urls = {ch["url"] for ch in st.session_state.channels}
        added_any = False
        for i, ch in enumerate(st.session_state.discover_res):
            already = ch["url"] in existing_urls
            ca, cb = st.columns([4, 1])
            ca.markdown(
                f"{'✅' if already else '📺'} **{ch['name'][:18]}**  \n"
                f"`{fmt_num(ch['view_count'])}회` | {ch['sample_title'][:25]}..."
            )
            if not already:
                if cb.button("➕", key=f"disc_{i}", help="벤치마킹 채널로 추가"):
                    st.session_state.channels.append({"name": ch["name"], "url": ch["url"]})
                    save_channels(st.session_state.channels)
                    added_any = True
            else:
                cb.markdown("✔")
        if added_any:
            st.rerun()

    st.divider()

    # ════════════════════════════════════════
    #  📋 등록된 채널 관리
    # ════════════════════════════════════════
    st.markdown("## 📋 벤치마킹 채널 관리")

    with st.form("add_channel", clear_on_submit=True):
        new_name = st.text_input("채널 별칭", placeholder="예: 경쟁사A")
        new_url  = st.text_input("유튜브 채널 URL", placeholder="https://www.youtube.com/@...")
        if st.form_submit_button("➕ 직접 추가", use_container_width=True) and new_url:
            name = new_name.strip() or new_url.split("@")[-1][:15]
            st.session_state.channels.append({"name": name, "url": new_url.strip()})
            save_channels(st.session_state.channels)
            st.success(f"'{name}' 추가됨!")

    if st.session_state.channels:
        st.markdown("**등록된 채널**")
        to_remove = []
        for i, ch in enumerate(st.session_state.channels):
            col_a, col_b = st.columns([4, 1])
            col_a.markdown(f"**{ch['name']}**  \n`{ch['url'][:30]}`")
            if col_b.button("🗑", key=f"del_{i}", help="삭제"):
                to_remove.append(i)
        for i in reversed(to_remove):
            del st.session_state.channels[i]
        if to_remove:
            save_channels(st.session_state.channels)
            st.rerun()
    else:
        st.info("채널을 추가하면 분석이 시작됩니다.")

    st.divider()

    # ════════════════════════════════════════
    #  ⚙️ 수집 설정 + 자동 수집
    # ════════════════════════════════════════
    st.markdown("## ⚙️ 수집 설정")
    days_back  = st.slider("최근 며칠치 수집", 7, 180, 30, 7)
    max_videos = st.slider("채널당 최대 영상 수", 10, 200, 50, 10)

    st.markdown("#### 🔄 자동 수집")
    auto_collect = st.toggle("자동 수집 켜기", value=False, help="설정한 간격마다 자동으로 데이터를 갱신합니다")
    if auto_collect:
        auto_interval = st.selectbox("수집 간격", ["30분", "1시간", "3시간", "6시간", "12시간", "24시간"], index=1)
        interval_map  = {"30분": 30, "1시간": 60, "3시간": 180, "6시간": 360, "12시간": 720, "24시간": 1440}
        interval_min  = interval_map[auto_interval]
        if st.session_state.last_collected:
            elapsed = (datetime.now() - st.session_state.last_collected).total_seconds() / 60
            remaining = max(0, interval_min - elapsed)
            st.caption(f"마지막 수집: {st.session_state.last_collected.strftime('%H:%M')}  \n다음 수집까지: {int(remaining)}분")
        else:
            st.caption("아직 수집 기록 없음")

    st.divider()
    st.markdown("## 📰 뉴스 모니터링 키워드")
    news_kw_raw   = st.text_area("키워드 입력 (줄바꿈으로 구분)", placeholder="병원 마케팅\n유튜브 알고리즘", height=100)
    news_keywords = [k.strip() for k in news_kw_raw.splitlines() if k.strip()]

    st.divider()
    collect_btn = st.button(
        "🚀 데이터 수집 시작",
        type="primary",
        use_container_width=True,
        disabled=len(st.session_state.channels) == 0,
    )


# ════════════════════════════════════════════════════════════
#  데이터 수집 실행 (수동 + 자동)
# ════════════════════════════════════════════════════════════

def run_collect():
    """채널 데이터 수집 공통 함수"""
    if not HAS_YTDLP:
        st.error("yt-dlp가 없습니다. `pip install yt-dlp` 실행 후 재시작하세요.")
        return
    st.session_state.yt_data = {}
    prog  = st.progress(0, text="수집 시작...")
    total = len(st.session_state.channels)
    for i, ch in enumerate(st.session_state.channels):
        prog.progress(i / total, text=f"📡 [{ch['name']}] 수집 중... ({i+1}/{total})")
        st.session_state.yt_data[ch["name"]] = fetch_yt_channel(ch["url"], days_back, max_videos)
    st.session_state.last_collected = datetime.now()
    prog.progress(1.0, text="✅ 수집 완료!")
    import time; time.sleep(0.8); prog.empty()
    total_v = sum(len(d) for d in st.session_state.yt_data.values())
    st.success(f"총 {total_v}개 영상 수집 완료! ({st.session_state.last_collected.strftime('%H:%M')})")

# 수동 수집
if collect_btn and st.session_state.channels:
    run_collect()

# 자동 수집 — 인터벌 초과 시 자동 실행
if (auto_collect
        and st.session_state.channels
        and st.session_state.last_collected is not None):
    elapsed_min = (datetime.now() - st.session_state.last_collected).total_seconds() / 60
    if elapsed_min >= interval_min:
        st.toast(f"🔄 자동 수집 시작 ({auto_interval} 경과)")
        run_collect()

# 자동 수집 ON이면 페이지 자동 새로고침 (30초마다 체크)
if auto_collect and st.session_state.channels:
    import time
    st_autorefresh_placeholder = st.empty()
    # streamlit-autorefresh 없이 meta refresh로 대체
    refresh_sec = min(interval_min * 60, 1800)   # 최대 30분
    st_autorefresh_placeholder.markdown(
        f'<meta http-equiv="refresh" content="{refresh_sec}">',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════════
#  메인 UI
# ════════════════════════════════════════════════════════════

st.markdown("""
<div class="dash-header">
  <h1>📊 벤치마킹 트렌드 대시보드</h1>
  <p>경쟁·참고 채널들의 주제/트렌드를 분석해 콘텐츠 기획 아이디어를 발굴하세요</p>
</div>
""", unsafe_allow_html=True)

yt_data: dict[str, pd.DataFrame] = st.session_state.get("yt_data", {})
all_df  = pd.concat(yt_data.values(), ignore_index=True) if yt_data else pd.DataFrame()

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏠 대시보드",
    "🔑 키워드 트렌드",
    "📅 업로드 패턴",
    "📊 채널 비교",
    "📰 뉴스 모니터링",
])


# ════════════════════════════════════════
#  TAB 1 : 대시보드
# ════════════════════════════════════════
with tab1:
    if all_df.empty:
        st.info("👈 왼쪽 사이드바에서 채널을 추가하고 **데이터 수집 시작** 버튼을 눌러주세요.")

        st.markdown("### 💡 이런 분석이 가능해요")
        c1, c2, c3 = st.columns(3)
        c1.markdown("**🔑 키워드 트렌드**\n\n경쟁 채널들이 가장 많이 다루는 주제·키워드를 워드클라우드와 차트로 시각화")
        c2.markdown("**📅 업로드 패턴**\n\n요일별·주간별 업로드 빈도를 분석해 최적 업로드 타이밍 파악")
        c3.markdown("**📊 채널 비교**\n\n채널별 평균 조회수·영상 수·인기 주제를 나란히 비교")
    else:
        # 요약 지표
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("📺 모니터링 채널", f"{len(yt_data)}개")
        m2.metric("🎬 수집 영상 수", f"{len(all_df):,}개")
        m3.metric("👁 전체 평균 조회수", fmt_num(int(all_df["view_count"].mean())))
        m4.metric("🔥 최고 조회수", fmt_num(int(all_df["view_count"].max())))
        top_kw = extract_keywords(all_df["title"].tolist(), top_n=1)
        m5.metric("🔑 최다 키워드", top_kw[0][0] if top_kw else "-")

        st.divider()

        # 채널별 최고 영상
        st.subheader("🏆 채널별 최고 조회수 영상")
        for ch_name, df in yt_data.items():
            if df.empty:
                continue
            best = df.loc[df["view_count"].idxmax()]
            with st.expander(f"**{ch_name}** — {best['title'][:50]}..."):
                col_img, col_info = st.columns([1, 3])
                if best.get("thumbnail"):
                    col_img.image(best["thumbnail"], use_container_width=True)
                col_info.markdown(f"""
**제목**: {best['title']}
**조회수**: {fmt_num(best['view_count'])}
**게시일**: {best.get('upload_date', '-')}
**링크**: {best.get('video_url', '-')}
""")

        st.divider()

        # 전체 영상 테이블
        st.subheader("📋 전체 수집 영상")
        show_df = all_df[["channel","title","view_count","upload_date","video_url","thumbnail"]].copy()
        show_df["view_count_fmt"] = show_df["view_count"].apply(fmt_num)
        show_df = show_df.sort_values("view_count", ascending=False).reset_index(drop=True)

        st.data_editor(
            show_df[["thumbnail","channel","title","view_count_fmt","upload_date","video_url"]].rename(
                columns={"thumbnail":"썸네일","channel":"채널","title":"제목",
                         "view_count_fmt":"조회수","upload_date":"게시일","video_url":"링크"}),
            column_config={
                "썸네일": st.column_config.ImageColumn("썸네일", width="small"),
                "제목": st.column_config.TextColumn("제목", width="large"),
                "채널": st.column_config.TextColumn("채널", width="medium"),
                "조회수": st.column_config.TextColumn("조회수", width="small"),
                "게시일": st.column_config.TextColumn("게시일", width="small"),
                "링크": st.column_config.LinkColumn("바로가기", display_text="▶ 보기"),
            },
            hide_index=True, use_container_width=True, disabled=True, height=450,
        )

        # 엑셀 다운로드
        buf = BytesIO()
        export = all_df[["channel","title","view_count","upload_date","video_url","thumbnail"]].copy()
        export.columns = ["채널","제목","조회수","게시일","영상URL","썸네일URL"]
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            export.to_excel(w, index=False, sheet_name="벤치마킹")
        buf.seek(0)
        st.download_button(
            "💾 전체 데이터 엑셀 다운로드",
            data=buf.read(),
            file_name=f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ════════════════════════════════════════
#  TAB 2 : 키워드 트렌드
# ════════════════════════════════════════
with tab2:
    if all_df.empty:
        st.info("데이터를 먼저 수집해 주세요.")
    else:
        st.subheader("🔑 전체 채널 키워드 분석")
        all_titles = all_df["title"].tolist()
        top_kw     = extract_keywords(all_titles, top_n=50)

        kw_col, bar_col = st.columns([1, 1], gap="large")

        with kw_col:
            st.markdown("**☁️ 키워드 워드클라우드**")
            if HAS_WC:
                fig = fig_wordcloud(top_kw)
                if fig:
                    st.pyplot(fig, use_container_width=True)
            else:
                st.warning("워드클라우드를 보려면 `pip install wordcloud` 실행 후 재시작하세요.")
                # 텍스트로 대체 표시
                st.write({w: c for w, c in top_kw[:20]})

        with bar_col:
            st.markdown("**📊 상위 20 키워드 빈도**")
            top20 = top_kw[:20]
            if top20:
                fig2 = fig_bar(
                    [w for w, _ in top20],
                    [c for _, c in top20],
                    title="",
                    color="#3b82f6",
                )
                st.pyplot(fig2, use_container_width=True)

        st.divider()

        # 채널별 키워드 분포
        if len(yt_data) > 1:
            st.subheader("📊 상위 키워드의 채널별 분포")
            top_words = [w for w, _ in top_kw[:15]]
            fig3 = fig_keyword_by_channel(yt_data, top_words)
            st.pyplot(fig3, use_container_width=True)

        st.divider()

        # 키워드 테이블 (검색 가능)
        st.subheader("📋 키워드 전체 목록")
        kw_df = pd.DataFrame(top_kw, columns=["키워드", "출현횟수"])
        kw_df["점유율"] = (kw_df["출현횟수"] / kw_df["출현횟수"].sum() * 100).round(1).astype(str) + "%"
        st.dataframe(kw_df, use_container_width=True, hide_index=True, height=350)

        # 💡 아이디어 제안
        st.divider()
        st.subheader("💡 콘텐츠 아이디어 힌트")
        st.markdown("아래 키워드들이 경쟁 채널에서 자주 등장합니다. 내 채널에서 다루지 않은 것이 있다면 기획 소재로 활용해보세요!")
        cols = st.columns(5)
        for i, (word, cnt) in enumerate(top_kw[:20]):
            cols[i % 5].markdown(f"🔹 **{word}** `{cnt}회`")


# ════════════════════════════════════════
#  TAB 3 : 업로드 패턴
# ════════════════════════════════════════
with tab3:
    if all_df.empty:
        st.info("데이터를 먼저 수집해 주세요.")
    else:
        st.subheader("📅 업로드 패턴 분석")

        pat_col1, pat_col2 = st.columns([1, 1], gap="large")

        with pat_col1:
            st.markdown("**요일별 전체 업로드 횟수**")
            fig_pat = fig_upload_pattern(all_df)
            st.pyplot(fig_pat, use_container_width=True)
            st.caption("🔴 = 주말 / 🔵 = 평일")

        with pat_col2:
            st.markdown("**채널별 업로드 요일 분포**")
            day_data = {}
            for ch, df in yt_data.items():
                if not df.empty and "day_of_week" in df.columns:
                    day_data[ch] = df["day_of_week"].value_counts().reindex(DAY_KR, fill_value=0)

            if day_data:
                day_summary = pd.DataFrame(day_data).fillna(0).astype(int)
                st.dataframe(day_summary, use_container_width=True)

        st.divider()

        # 주간 업로드 추이
        st.subheader("📈 채널별 주간 업로드 추이")
        if any("week" in df.columns for df in yt_data.values()):
            fig_wk = fig_weekly_uploads(yt_data)
            st.pyplot(fig_wk, use_container_width=True)

        st.divider()

        # 채널별 업로드 통계
        st.subheader("📊 채널별 업로드 통계")
        stats_rows = []
        for ch, df in yt_data.items():
            if df.empty:
                continue
            stats_rows.append({
                "채널": ch,
                "수집 영상 수": len(df),
                "평균 조회수": fmt_num(int(df["view_count"].mean())),
                "최고 조회수": fmt_num(int(df["view_count"].max())),
                "최다 업로드 요일": df["day_of_week"].mode()[0] if "day_of_week" in df.columns and not df["day_of_week"].isna().all() else "-",
            })
        if stats_rows:
            st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)


# ════════════════════════════════════════
#  TAB 4 : 채널 비교
# ════════════════════════════════════════
with tab4:
    if all_df.empty:
        st.info("데이터를 먼저 수집해 주세요.")
    elif len(yt_data) < 2:
        st.warning("채널 비교는 2개 이상 채널이 필요합니다. 사이드바에서 채널을 추가하세요.")
    else:
        st.subheader("📊 채널 간 성과 비교")

        # 평균 조회수 & 영상 수 비교 차트
        fig_cmp = fig_channel_compare(yt_data)
        st.pyplot(fig_cmp, use_container_width=True)

        st.divider()

        # 채널별 TOP 5 영상
        st.subheader("🏆 채널별 TOP 5 영상")
        ch_tabs = st.tabs(list(yt_data.keys()))
        for i, (ch_name, df) in enumerate(yt_data.items()):
            with ch_tabs[i]:
                if df.empty:
                    st.write("데이터 없음")
                    continue
                top5 = df.nlargest(5, "view_count")[
                    ["thumbnail","title","view_count","upload_date","video_url"]
                ].copy()
                top5["view_count"] = top5["view_count"].apply(fmt_num)
                st.data_editor(
                    top5.rename(columns={
                        "thumbnail":"썸네일","title":"제목","view_count":"조회수",
                        "upload_date":"게시일","video_url":"링크"
                    }),
                    column_config={
                        "썸네일": st.column_config.ImageColumn("썸네일", width="small"),
                        "제목": st.column_config.TextColumn("제목", width="large"),
                        "링크": st.column_config.LinkColumn("바로가기", display_text="▶ 보기"),
                    },
                    hide_index=True, use_container_width=True, disabled=True,
                )

        st.divider()

        # 채널별 독자 키워드 (다른 채널에 없는 것)
        st.subheader("🔍 채널별 독자 키워드 (다른 채널에는 없는 것)")
        all_kw_sets = {}
        for ch, df in yt_data.items():
            if not df.empty:
                all_kw_sets[ch] = set(w for w, _ in extract_keywords(df["title"].tolist(), 30))

        uniq_cols = st.columns(len(all_kw_sets))
        for i, (ch, kw_set) in enumerate(all_kw_sets.items()):
            others = set().union(*[v for k, v in all_kw_sets.items() if k != ch])
            unique = kw_set - others
            with uniq_cols[i]:
                st.markdown(f"**{ch}**")
                for w in sorted(unique)[:10]:
                    st.markdown(f"- {w}")


# ════════════════════════════════════════
#  TAB 5 : 뉴스 모니터링
# ════════════════════════════════════════
with tab5:
    st.subheader("📰 블로그/뉴스 트렌드 모니터링")

    # 자동 키워드: 수집된 영상 상위 키워드 + 사용자 직접 입력
    auto_kw = []
    if not all_df.empty:
        auto_kw = [w for w, _ in extract_keywords(all_df["title"].tolist(), 5)]

    if not news_keywords and not auto_kw:
        st.info("사이드바에서 뉴스 모니터링 키워드를 입력하거나 채널 데이터를 먼저 수집하세요.\n\n채널 데이터가 있으면 상위 키워드가 자동으로 검색됩니다.")
    else:
        search_terms = list(dict.fromkeys(news_keywords + auto_kw))[:8]  # 최대 8개

        if auto_kw and not news_keywords:
            st.info(f"채널 상위 키워드로 자동 검색 중: {', '.join(auto_kw)}")

        for kw in search_terms:
            with st.expander(f"🔍 **{kw}** 관련 뉴스", expanded=(search_terms.index(kw) == 0)):
                with st.spinner(f"'{kw}' 뉴스 불러오는 중..."):
                    news_df = fetch_news(kw)
                if news_df.empty:
                    st.warning("뉴스를 가져오지 못했습니다.")
                else:
                    st.caption(f"최신 {len(news_df)}건")
                    st.data_editor(
                        news_df,
                        column_config={
                            "링크": st.column_config.LinkColumn("링크", display_text="🔗 원문"),
                        },
                        hide_index=True, use_container_width=True, disabled=True, height=250,
                    )
