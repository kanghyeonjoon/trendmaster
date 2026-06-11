import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from crm_data import load_customers, save_uploaded

# 1. 페이지 설정
st.set_page_config(
    page_title="CRM 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# 2. 메인 화면
st.title("📊 CRM 대시보드")
st.markdown("---")

# 사이드바: 데이터 소스 + 필터
with st.sidebar:
    st.header("⚙️ 데이터 설정")
    uploaded = st.file_uploader("고객 데이터 업로드 (CSV)", type="csv",
                                help="컬럼: 고객명, 회사명, 지역, 등급, 유입채널, 영업단계, 담당자, 누적매출, 가입일, 최근거래일")
    if uploaded:
        df = save_uploaded(pd.read_csv(uploaded))
        st.success(f"업로드 완료: {len(df)}건")
    else:
        df, is_uploaded = load_customers()
        if not is_uploaded:
            st.info("샘플 데이터를 표시 중입니다. CSV를 업로드하면 실제 데이터로 전환됩니다.")

    st.markdown("---")
    st.header("🔍 필터")
    sel_region = st.multiselect("지역", sorted(df["지역"].unique()))
    sel_grade = st.multiselect("등급", ["VIP", "Gold", "Silver", "Bronze"])
    sel_manager = st.multiselect("담당자", sorted(df["담당자"].unique()))

# 필터 적용
filtered = df.copy()
if sel_region:
    filtered = filtered[filtered["지역"].isin(sel_region)]
if sel_grade:
    filtered = filtered[filtered["등급"].isin(sel_grade)]
if sel_manager:
    filtered = filtered[filtered["담당자"].isin(sel_manager)]

# 4. KPI 카드
total_customers = len(filtered)
total_revenue = filtered["누적매출"].sum()
recent_30 = (pd.to_datetime(filtered["가입일"]) >= datetime.now() - timedelta(days=30)).sum()
churned = (filtered["영업단계"] == "이탈").sum()
churn_rate = churned / total_customers * 100 if total_customers else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 전체 고객 수", f"{total_customers:,}명")
col2.metric("💰 누적 매출", f"{total_revenue:,.0f}만원")
col3.metric("🆕 최근 30일 신규", f"{recent_30:,}명")
col4.metric("📉 이탈률", f"{churn_rate:.1f}%", delta=f"-{churned}명", delta_color="inverse")

st.markdown("---")

# 5. 차트 영역 (2단 구성)
left, right = st.columns(2)

with left:
    st.subheader("📈 월별 신규 고객 추이")
    monthly = pd.to_datetime(filtered["가입일"]).dt.to_period("M").value_counts().sort_index()
    monthly_df = pd.DataFrame({"월": monthly.index.astype(str), "신규 고객": monthly.values})
    fig = px.area(monthly_df, x="월", y="신규 고객", markers=True)
    fig.update_layout(margin=dict(t=10, b=10), height=320)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🥇 등급별 고객 분포")
    grade_counts = filtered["등급"].value_counts().reindex(["VIP", "Gold", "Silver", "Bronze"]).dropna()
    fig = px.pie(values=grade_counts.values, names=grade_counts.index, hole=0.45,
                 color=grade_counts.index,
                 color_discrete_map={"VIP": "#FFD700", "Gold": "#FFA500", "Silver": "#C0C0C0", "Bronze": "#CD7F32"})
    fig.update_layout(margin=dict(t=10, b=10), height=320)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("🎯 영업 파이프라인 (퍼널)")
    stage_order = ["리드", "상담중", "제안", "협상", "계약완료"]
    stage_counts = filtered["영업단계"].value_counts().reindex(stage_order).fillna(0)
    fig = go.Figure(go.Funnel(y=stage_order, x=stage_counts.values, textinfo="value+percent initial"))
    fig.update_layout(margin=dict(t=10, b=10), height=320)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🗺️ 지역별 매출")
    region_rev = filtered.groupby("지역")["누적매출"].sum().sort_values(ascending=True)
    fig = px.bar(x=region_rev.values, y=region_rev.index, orientation="h",
                 labels={"x": "매출(만원)", "y": "지역"})
    fig.update_layout(margin=dict(t=10, b=10), height=320)
    st.plotly_chart(fig, use_container_width=True)

# 6. 담당자별 실적
st.markdown("---")
st.subheader("👔 담당자별 실적")
perf = filtered.groupby("담당자").agg(
    고객수=("고객명", "count"),
    총매출=("누적매출", "sum"),
    계약완료=("영업단계", lambda s: (s == "계약완료").sum()),
).reset_index().sort_values("총매출", ascending=False)
perf["평균매출"] = (perf["총매출"] / perf["고객수"]).round(0).astype(int)
st.dataframe(
    perf,
    column_config={
        "총매출": st.column_config.NumberColumn("총매출(만원)", format="%,d"),
        "평균매출": st.column_config.NumberColumn("고객당 평균(만원)", format="%,d"),
        "총매출_bar": None,
    },
    use_container_width=True, hide_index=True
)

# 7. 고객 목록 + 검색 + 다운로드
st.markdown("---")
st.subheader("📋 고객 목록")
search = st.text_input("고객명/회사명 검색", placeholder="예: 고객001, 한빛테크")
table = filtered
if search:
    table = filtered[filtered["고객명"].str.contains(search, na=False) |
                     filtered["회사명"].str.contains(search, na=False)]

st.caption(f"조회된 고객: {len(table)}건")
st.dataframe(
    table.sort_values("누적매출", ascending=False),
    column_config={
        "누적매출": st.column_config.NumberColumn("누적매출(만원)", format="%,d"),
    },
    use_container_width=True, hide_index=True
)

csv = table.to_csv(index=False).encode("utf-8-sig")
st.download_button("💾 엑셀(CSV)로 저장", csv, "crm_customers.csv", "text/csv")
