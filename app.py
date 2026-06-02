import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random

st.set_page_config(
    page_title="경희나비솔 CRM",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────── CSS ──────────────────────────────
st.markdown(
    """
<style>
/* KPI metric 폰트 조정 */
[data-testid="stMetricValue"] { font-size: 1.9rem !important; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 0.8rem !important; }

/* 섹션 제목 */
.section-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #1a237e;
    margin: 0 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 2px solid #e8eaf6;
}

/* 관여도 배지 */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
.b-high { background:#FFEBEE; color:#C62828; }
.b-med  { background:#FFF3E0; color:#E65100; }
.b-low  { background:#F5F5F5; color:#616161; border:1px solid #e0e0e0; }
.b-stop { background:#263238; color:white; }
.b-done { background:#E8F5E9; color:#2E7D32; }
.b-target { background:#E3F2FD; color:#1565C0; }

/* 알림 카드 */
.card-urgent {
    background:#FFF5F5; border:1px solid #FFCDD2;
    border-left:4px solid #F44336;
    border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:13px;
}
.card-warn {
    background:#FFFBF0; border:1px solid #FFE082;
    border-left:4px solid #FFC107;
    border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:13px;
}
.card-info {
    background:#F0F7FF; border:1px solid #BBDEFB;
    border-left:4px solid #2196F3;
    border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:13px;
}
.card-ok {
    background:#F1F8E9; border:1px solid #C5E1A5;
    border-left:4px solid #8BC34A;
    border-radius:8px; padding:10px 14px; margin-bottom:6px; font-size:13px;
}

/* 시나리오 박스 */
.scenario-box {
    background:white; border:1px solid #e0e0e0;
    border-radius:10px; padding:14px 18px; margin-bottom:10px;
}
.tag-trigger { font-size:11px; color:#888; margin-top:3px; }
.tag-action  { font-size:11px; color:#1565C0; margin-top:3px; }
</style>
""",
    unsafe_allow_html=True,
)

# ────────────────────────────── SAMPLE DATA ──────────────────────────────
@st.cache_data
def build_data():
    random.seed(42)
    today = datetime.now()

    names = [
        "김민준","이서연","박도윤","최서준","정시우",
        "강하은","조민서","윤지아","장예준","임서현",
        "오준서","한수아","홍이준","신지호","문채원",
        "양현우","백소연","허태양","남지민","류승우",
        "황지수","송현아","전승우","안서진","차민혁",
    ]
    phones = [f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}" for _ in names]

    s_main  = ["요통","경추통","슬관절통","오십견","두통","불면","소화불량","피로","어지럼증","비염"]
    s_other = ["불면","피로","소화불량","두통","냉증","비염","변비","스트레스","안구건조","부종"]
    s_worry = ["치매","중풍","당뇨","고혈압","암","심장질환"]
    s_family= ["고혈압","당뇨","암","치매","심장질환"]

    patients = []
    for i, name in enumerate(names):
        goal    = random.choices(["최소","표준","집중"], weights=[2,8,5])[0]
        worry   = random.sample(s_worry,  random.randint(0, 2))
        other   = random.sample(s_other,  random.randint(0, 4))
        family  = random.sample(s_family, random.randint(0, 2))

        # Factor 1 – 잠재성 점수
        ps = 0
        if goal == "집중": ps += 3
        elif goal == "최소": ps -= 3
        if len(worry)  >= 1: ps += 2
        if len(other)  >= 2: ps += 1
        if len(family) >= 1: ps += 1

        # Factor 2 – 활성도 점수
        acs = random.choices([-10, 0, 1, 3], weights=[1, 3, 4, 4])[0]
        total = ps + acs

        group = (
            "발송중단" if acs == -10 else
            "상" if total >= 4 else
            "중" if total >= 1 else "하"
        )

        visits = random.randint(1, 18)
        comp   = "대상아님"
        if visits >= 3:
            comp = random.choices(["대상아님","대상","참여완료"], weights=[3,2,4])[0]

        reg  = today - timedelta(days=random.randint(14, 400))
        last = today - timedelta(days=random.randint(1, 60))

        patients.append(dict(
            환자명=name,  연락처=phones[i],
            주증상=random.choice(s_main),
            다른증상=", ".join(other)  if other  else "-",
            걱정증상=", ".join(worry)  if worry  else "-",
            가족증상=", ".join(family) if family else "-",
            치료선택=goal,
            잠재성점수=ps, 활성도점수=acs, 최종관여도=total,
            관여도그룹=group, 단골상태=comp,
            방문횟수=visits,
            마지막방문일=last.strftime("%Y-%m-%d"),
            등록일=reg.strftime("%Y-%m-%d"),
        ))

    df_p = pd.DataFrame(patients)

    # ── 진료 기록 ──
    vlist = []
    for _, p in df_p.iterrows():
        base = random.randint(30, 300)
        for v in range(p["방문횟수"]):
            d = today - timedelta(days=base - v * random.randint(5, 20))
            vlist.append(dict(
                환자명=p["환자명"], 주증상=p["주증상"],
                방문일=d.strftime("%Y-%m-%d"),
                상태=random.choices(["완료","예약","노쇼"], weights=[8,2,1])[0],
                관여도그룹=p["관여도그룹"],
            ))
    df_v = (pd.DataFrame(vlist)
            .sort_values("방문일", ascending=False)
            .reset_index(drop=True))

    # ── 처방 기록 ──
    plist = []
    for _, p in df_p.sample(14, random_state=42).iterrows():
        sd    = random.randint(1, 28)
        start = today - timedelta(days=sd)
        d5    = start + timedelta(days=5)
        d12   = start + timedelta(days=12)
        dtype = random.choice(["15일 집중","30일 기초","45일 완성"])
        d5s   = "발송완료" if sd > 6 else ("미발송" if sd >= 5 else "대기중")
        d12s  = "발송완료" if sd > 13 else ("미발송" if sd >= 12 else "대기중")
        plist.append(dict(
            환자명=p["환자명"], 처방유형=dtype,
            복용시작일=start.strftime("%Y-%m-%d"),
            D5예정일=d5.strftime("%Y-%m-%d"),
            D12예정일=d12.strftime("%Y-%m-%d"),
            경과일=sd,
            상태="진행중" if sd <= 14 else "완료",
            D5발송=d5s, D12발송=d12s,
        ))
    df_pr = pd.DataFrame(plist)

    # ── CRM 발송 로그 ──
    stages    = ["초기(주증상)","중기(다른증상)","후기(걱정증상)"]
    reactions = ["긍정회신(+3)","링크클릭(+1)","무반응(0)","부정회신(-10)"]
    llist = []
    for _, p in df_p.iterrows():
        for _ in range(random.randint(0, 5)):
            dt = today - timedelta(days=random.randint(0,90), hours=random.randint(0,23))
            llist.append(dict(
                환자명=p["환자명"], 관여도그룹=p["관여도그룹"],
                발송단계=random.choice(stages),
                콘텐츠=f"{p['주증상']} 관리팁",
                발송일시=dt.strftime("%Y-%m-%d %H:%M"),
                반응=random.choices(reactions, weights=[2,4,8,1])[0],
            ))
    df_l = (pd.DataFrame(llist)
            .sort_values("발송일시", ascending=False)
            .reset_index(drop=True))

    return df_p, df_v, df_pr, df_l


df_patients, df_visits, df_prescriptions, df_logs = build_data()
TODAY = datetime.now()


# ────────────────────────────── HELPERS ──────────────────────────────
GROUP_COLOR = {"상":"#C62828","중":"#E65100","하":"#757575","발송중단":"#263238"}
GROUP_BG    = {"상":"#FFEBEE","중":"#FFF3E0","하":"#FAFAFA","발송중단":"#263238"}
GROUP_EMOJI = {"상":"🔴","중":"🟡","하":"⚪","발송중단":"⛔"}

def badge_html(group: str) -> str:
    cls = {"상":"b-high","중":"b-med","하":"b-low","발송중단":"b-stop"}.get(group,"b-low")
    return f'<span class="badge {cls}">{GROUP_EMOJI.get(group,"")} {group}</span>'

def comp_badge(s: str) -> str:
    cls = {"참여완료":"b-done","대상":"b-target","대상아님":"b-low"}.get(s,"b-low")
    return f'<span class="badge {cls}">{s}</span>'

def reaction_color(r: str) -> str:
    if "긍정" in r:  return "#2E7D32"
    if "링크" in r:  return "#1565C0"
    if "부정" in r:  return "#B71C1C"
    return "#757575"

def reaction_icon(r: str) -> str:
    if "긍정" in r:  return "💬"
    if "링크" in r:  return "👆"
    if "부정" in r:  return "⛔"
    return "➖"


# ────────────────────────────── SIDEBAR ──────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 경희나비솔 한의원")
    st.markdown("**1:1 맞춤 밀착 케어 CRM v2.0**")
    st.divider()

    page = st.radio(
        "nav",
        ["📊 대시보드","👥 환자 관리","📋 진료 기록",
         "💊 처방 관리","📨 CRM 발송 로그","⚙️ 자동화 시나리오"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption(f"📅 {TODAY.strftime('%Y년 %m월 %d일')}")

    d5_cnt = int((
        df_prescriptions["경과일"].between(4,6) &
        (df_prescriptions["D5발송"] == "미발송")
    ).sum())
    d12_cnt = int((
        df_prescriptions["경과일"].between(11,13) &
        (df_prescriptions["D12발송"] == "미발송")
    ).sum())
    flag_cnt = int((df_patients["관여도그룹"] == "발송중단").sum())
    v3_cnt = int(
        ((df_patients["방문횟수"] == 3) & (df_patients["단골상태"] == "대상")).sum()
    )

    if d5_cnt:  st.error(f"⚠️ D+5 알림 {d5_cnt}건 대기중")
    if d12_cnt: st.warning(f"📅 D+12 알림 {d12_cnt}건 대기중")
    if v3_cnt:  st.info(f"🎁 동반자 이벤트 {v3_cnt}건")
    if flag_cnt: st.warning(f"⛔ 발송중단 {flag_cnt}명")


# ═══════════════════════════════════════════════════════════════════
# PAGE 1: DASHBOARD
# ═══════════════════════════════════════════════════════════════════
if page == "📊 대시보드":
    st.markdown('<div class="section-title">📊 CRM 대시보드</div>', unsafe_allow_html=True)
    st.caption("경희나비솔 한의원 · 2-Factor 환자 관여도 기반 자동화 CRM")
    st.divider()

    # ── KPI ──
    g = df_patients["관여도그룹"].value_counts()
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("👥 전체 환자",   len(df_patients))
    c2.metric("🔴 관여도 상",   g.get("상", 0))
    c3.metric("🟡 관여도 중",   g.get("중", 0))
    c4.metric("⚪ 관여도 하",   g.get("하", 0))
    c5.metric("⛔ 발송중단",    g.get("발송중단", 0))
    c6.metric("🎖️ 단골 완료",  int((df_patients["단골상태"] == "참여완료").sum()))

    st.divider()

    # ── Charts ──
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("관여도 그룹 분포")
        gd = df_patients["관여도그룹"].value_counts().reset_index()
        gd.columns = ["그룹","환자수"]
        cmap = {"상":"#EF5350","중":"#FF9800","하":"#BDBDBD","발송중단":"#37474F"}
        fig_pie = px.pie(
            gd, values="환자수", names="그룹", color="그룹",
            color_discrete_map=cmap, hole=0.42,
            category_orders={"그룹":["상","중","하","발송중단"]},
        )
        fig_pie.update_layout(margin=dict(t=10,b=10), height=270, legend_title_text="")
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_r:
        st.subheader("치료 선택 분포")
        td = df_patients["치료선택"].value_counts().reset_index()
        td.columns = ["치료선택","환자수"]
        td["치료선택"] = pd.Categorical(td["치료선택"], ["최소","표준","집중"], ordered=True)
        td = td.sort_values("치료선택")
        fig_bar = px.bar(
            td, x="치료선택", y="환자수", text="환자수", color="치료선택",
            color_discrete_sequence=["#90CAF9","#66BB6A","#EF5350"],
        )
        fig_bar.update_layout(showlegend=False, margin=dict(t=10), height=270, xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_bar, use_container_width=True)

    # ── 관여도 점수 히스토그램 ──
    st.subheader("최종 관여도 점수 분포")
    fig_hist = px.histogram(
        df_patients, x="최종관여도", nbins=14,
        color_discrete_sequence=["#5C6BC0"],
        labels={"최종관여도":"최종 관여도 점수"},
    )
    fig_hist.add_vline(x=4,  line_dash="dot", line_color="#C62828",
                       annotation_text="상 기준(4점)", annotation_position="top right")
    fig_hist.add_vline(x=1,  line_dash="dot", line_color="#E65100",
                       annotation_text="중 기준(1점)", annotation_position="top right")
    fig_hist.update_layout(margin=dict(t=30), height=220, yaxis_title="환자 수")
    st.plotly_chart(fig_hist, use_container_width=True)

    st.divider()

    # ── 오늘의 액션 + 최근 CRM ──
    col_a, col_b = st.columns([1,1])

    with col_a:
        st.subheader("⚡ 오늘의 액션 아이템")

        d5_pend = df_prescriptions[
            df_prescriptions["경과일"].between(4,6) &
            (df_prescriptions["D5발송"] == "미발송")
        ]
        d12_pend = df_prescriptions[
            df_prescriptions["경과일"].between(11,13) &
            (df_prescriptions["D12발송"] == "미발송")
        ]
        v3_ev = df_patients[
            (df_patients["방문횟수"] == 3) & (df_patients["단골상태"] == "대상")
        ]

        for _, r in d5_pend.iterrows():
            st.markdown(
                f'<div class="card-urgent">💊 <b>{r["환자명"]}</b> · '
                f'D+5 경과체크 알림톡 발송 필요 ({r["처방유형"]})</div>',
                unsafe_allow_html=True,
            )
        for _, r in d12_pend.iterrows():
            st.markdown(
                f'<div class="card-warn">📅 <b>{r["환자명"]}</b> · '
                f'D+12 재내원 안내 발송 필요 ({r["처방유형"]})</div>',
                unsafe_allow_html=True,
            )
        for _, r in v3_ev.iterrows():
            st.markdown(
                f'<div class="card-info">🎁 <b>{r["환자명"]}</b> · '
                f'3회차 방문 → 진심 동반자 이벤트 안내 바람</div>',
                unsafe_allow_html=True,
            )
        if len(d5_pend)+len(d12_pend)+len(v3_ev) == 0:
            st.markdown(
                '<div class="card-ok">✅ 오늘의 긴급 액션 아이템 없음</div>',
                unsafe_allow_html=True,
            )

    with col_b:
        st.subheader("📨 최근 CRM 반응 (10건)")
        for _, r in df_logs.head(10).iterrows():
            icon  = reaction_icon(r["반응"])
            color = reaction_color(r["반응"])
            st.markdown(
                f"{icon} **{r['환자명']}** &nbsp;·&nbsp; {r['발송단계']} "
                f"&nbsp;·&nbsp; <span style='color:{color}'>{r['반응']}</span> "
                f"&nbsp;·&nbsp; <small>{r['발송일시'][:10]}</small>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════
# PAGE 2: 환자 관리
# ═══════════════════════════════════════════════════════════════════
elif page == "👥 환자 관리":
    st.markdown('<div class="section-title">👥 환자 관리</div>', unsafe_allow_html=True)
    st.divider()

    # ── 필터 ──
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_group = st.multiselect("관여도 그룹", ["상","중","하","발송중단"],
                                  default=["상","중","하","발송중단"])
    with fc2:
        f_goal  = st.multiselect("치료 선택", ["최소","표준","집중"],
                                  default=["최소","표준","집중"])
    with fc3:
        f_comp  = st.multiselect("단골 상태", ["대상아님","대상","참여완료"],
                                  default=["대상아님","대상","참여완료"])
    with fc4:
        f_name  = st.text_input("환자명 검색", placeholder="이름 입력")

    df_show = df_patients.copy()
    if f_group: df_show = df_show[df_show["관여도그룹"].isin(f_group)]
    if f_goal:  df_show = df_show[df_show["치료선택"].isin(f_goal)]
    if f_comp:  df_show = df_show[df_show["단골상태"].isin(f_comp)]
    if f_name:  df_show = df_show[df_show["환자명"].str.contains(f_name)]

    st.caption(f"검색 결과: {len(df_show)}명")
    st.divider()

    # ── 환자 카드 ──
    for _, row in df_show.iterrows():
        with st.expander(
            f"{GROUP_EMOJI.get(row['관여도그룹'],'')}  {row['환자명']} "
            f"| {row['치료선택']} | 방문 {row['방문횟수']}회 "
            f"| 점수 {row['최종관여도']:+d}"
        ):
            ca, cb, cc = st.columns(3)
            with ca:
                st.markdown(f"**연락처** &nbsp; {row['연락처']}")
                st.markdown(f"**등록일** &nbsp; {row['등록일']}")
                st.markdown(f"**마지막 방문** &nbsp; {row['마지막방문일']}")
            with cb:
                st.markdown(f"**주증상** &nbsp; {row['주증상']}")
                st.markdown(f"**다른증상** &nbsp; {row['다른증상']}")
                st.markdown(f"**걱정증상** &nbsp; {row['걱정증상']}")
                st.markdown(f"**가족증상** &nbsp; {row['가족증상']}")
            with cc:
                st.markdown("**점수 내역**")
                sc1, sc2 = st.columns(2)
                sc1.metric("잠재성 점수", f"{row['잠재성점수']:+d}")
                sc2.metric("활성도 점수", f"{row['활성도점수']:+d}")
                st.metric("최종 관여도", f"{row['최종관여도']:+d}")
                g = row["관여도그룹"]
                st.markdown(badge_html(g) + "&nbsp;&nbsp;" + comp_badge(row["단골상태"]),
                            unsafe_allow_html=True)

    st.divider()
    # ── 요약 테이블 ──
    st.subheader("전체 환자 목록 요약")
    disp = df_show[[
        "환자명","치료선택","주증상","방문횟수",
        "잠재성점수","활성도점수","최종관여도","관여도그룹","단골상태"
    ]].copy()
    disp.insert(0, "번호", range(1, len(disp)+1))
    st.dataframe(disp, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
# PAGE 3: 진료 기록
# ═══════════════════════════════════════════════════════════════════
elif page == "📋 진료 기록":
    st.markdown('<div class="section-title">📋 진료 기록</div>', unsafe_allow_html=True)
    st.divider()

    vc1, vc2, vc3 = st.columns(3)
    with vc1:
        v_patient = st.text_input("환자명 검색")
    with vc2:
        v_status  = st.multiselect("방문 상태", ["완료","예약","노쇼"],
                                    default=["완료","예약","노쇼"])
    with vc3:
        v_group   = st.multiselect("관여도 그룹",
                                    ["상","중","하","발송중단"],
                                    default=["상","중","하","발송중단"])

    dv = df_visits.copy()
    if v_patient: dv = dv[dv["환자명"].str.contains(v_patient)]
    if v_status:  dv = dv[dv["상태"].isin(v_status)]
    if v_group:   dv = dv[dv["관여도그룹"].isin(v_group)]

    st.caption(f"진료 기록: {len(dv)}건")
    st.dataframe(dv, use_container_width=True, hide_index=True)

    st.divider()

    # ── 차트: 방문 상태 & 그룹별 방문 건수 ──
    chart1, chart2 = st.columns(2)
    with chart1:
        st.subheader("방문 상태 분포")
        sd = dv["상태"].value_counts().reset_index()
        sd.columns = ["상태","건수"]
        fig_s = px.pie(sd, values="건수", names="상태",
                       color_discrete_sequence=["#66BB6A","#FFA726","#EF5350"],
                       hole=0.35)
        fig_s.update_layout(margin=dict(t=10,b=10), height=260)
        st.plotly_chart(fig_s, use_container_width=True)

    with chart2:
        st.subheader("그룹별 방문 건수")
        gvd = dv["관여도그룹"].value_counts().reset_index()
        gvd.columns = ["그룹","건수"]
        cmap = {"상":"#EF5350","중":"#FF9800","하":"#BDBDBD","발송중단":"#37474F"}
        fig_gv = px.bar(gvd, x="그룹", y="건수", color="그룹",
                        color_discrete_map=cmap, text="건수")
        fig_gv.update_layout(showlegend=False, margin=dict(t=10), height=260,
                              xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_gv, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# PAGE 4: 처방 관리
# ═══════════════════════════════════════════════════════════════════
elif page == "💊 처방 관리":
    st.markdown('<div class="section-title">💊 처방 관리 (15일 단위 자동화)</div>',
                unsafe_allow_html=True)
    st.divider()

    # ── 알림 배너 ──
    d5_alert = df_prescriptions[
        df_prescriptions["경과일"].between(4,6) &
        (df_prescriptions["D5발송"] == "미발송")
    ]
    d12_alert = df_prescriptions[
        df_prescriptions["경과일"].between(11,13) &
        (df_prescriptions["D12발송"] == "미발송")
    ]

    if not d5_alert.empty:
        st.error(f"⚠️  **D+5 경과체크 미발송 {len(d5_alert)}건** — 즉시 알림톡 발송 필요")
        st.dataframe(d5_alert[["환자명","처방유형","복용시작일","경과일","D5예정일","D5발송"]],
                     use_container_width=True, hide_index=True)
        st.divider()

    if not d12_alert.empty:
        st.warning(f"📅  **D+12 재내원 안내 미발송 {len(d12_alert)}건**")
        st.dataframe(d12_alert[["환자명","처방유형","복용시작일","경과일","D12예정일","D12발송"]],
                     use_container_width=True, hide_index=True)
        st.divider()

    # ── 전체 처방 목록 ──
    st.subheader("전체 처방 목록")

    pr_filter = st.selectbox("처방 상태 필터", ["전체","진행중","완료"])
    dpr = df_prescriptions.copy()
    if pr_filter != "전체":
        dpr = dpr[dpr["상태"] == pr_filter]

    # 색상 강조를 위한 열 추가
    def highlight_d5(row):
        style = [""] * len(row)
        if row["경과일"] in [5] and row["D5발송"] == "미발송":
            idx = row.index.tolist().index("D5발송")
            style[idx] = "background-color: #FFEBEE; color: #C62828; font-weight: bold"
        return style

    st.dataframe(dpr, use_container_width=True, hide_index=True)

    # ── 발송 현황 도넛 차트 ──
    st.divider()
    ch1, ch2 = st.columns(2)
    with ch1:
        st.subheader("D+5 발송 현황")
        d5s = df_prescriptions["D5발송"].value_counts().reset_index()
        d5s.columns = ["상태","건수"]
        fig_d5 = px.pie(d5s, values="건수", names="상태", hole=0.4,
                        color_discrete_sequence=["#66BB6A","#EF5350","#90CAF9"])
        fig_d5.update_layout(margin=dict(t=10,b=10), height=250)
        st.plotly_chart(fig_d5, use_container_width=True)

    with ch2:
        st.subheader("D+12 발송 현황")
        d12s = df_prescriptions["D12발송"].value_counts().reset_index()
        d12s.columns = ["상태","건수"]
        fig_d12 = px.pie(d12s, values="건수", names="상태", hole=0.4,
                         color_discrete_sequence=["#66BB6A","#EF5350","#90CAF9"])
        fig_d12.update_layout(margin=dict(t=10,b=10), height=250)
        st.plotly_chart(fig_d12, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# PAGE 5: CRM 발송 로그
# ═══════════════════════════════════════════════════════════════════
elif page == "📨 CRM 발송 로그":
    st.markdown('<div class="section-title">📨 CRM 발송 로그</div>', unsafe_allow_html=True)
    st.divider()

    # ── KPI ──
    lc1,lc2,lc3,lc4 = st.columns(4)
    lc1.metric("전체 발송", len(df_logs))
    lc2.metric("💬 긍정 회신", int(df_logs["반응"].str.contains("긍정").sum()))
    lc3.metric("👆 링크 클릭", int(df_logs["반응"].str.contains("링크").sum()))
    lc4.metric("⛔ 부정 회신", int(df_logs["반응"].str.contains("부정").sum()))

    st.divider()

    # ── 필터 ──
    lf1, lf2, lf3 = st.columns(3)
    with lf1:
        l_patient = st.text_input("환자명 검색", key="log_p")
    with lf2:
        l_stage = st.multiselect("발송 단계",
            ["초기(주증상)","중기(다른증상)","후기(걱정증상)"],
            default=["초기(주증상)","중기(다른증상)","후기(걱정증상)"])
    with lf3:
        l_react = st.multiselect("반응 필터",
            ["긍정회신(+3)","링크클릭(+1)","무반응(0)","부정회신(-10)"],
            default=["긍정회신(+3)","링크클릭(+1)","무반응(0)","부정회신(-10)"])

    dl = df_logs.copy()
    if l_patient: dl = dl[dl["환자명"].str.contains(l_patient)]
    if l_stage:   dl = dl[dl["발송단계"].isin(l_stage)]
    if l_react:   dl = dl[dl["반응"].isin(l_react)]

    st.caption(f"발송 로그: {len(dl)}건")
    st.dataframe(dl, use_container_width=True, hide_index=True)

    st.divider()

    # ── 차트 ──
    chart_a, chart_b = st.columns(2)
    with chart_a:
        st.subheader("반응 분포")
        rd = df_logs["반응"].value_counts().reset_index()
        rd.columns = ["반응","건수"]
        fig_rd = px.bar(rd, x="반응", y="건수", color="반응", text="건수",
                        color_discrete_sequence=["#66BB6A","#42A5F5","#BDBDBD","#EF5350"])
        fig_rd.update_layout(showlegend=False, margin=dict(t=10), height=260,
                             xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_rd, use_container_width=True)

    with chart_b:
        st.subheader("단계별 발송 건수")
        sd2 = df_logs["발송단계"].value_counts().reset_index()
        sd2.columns = ["단계","건수"]
        fig_sd = px.bar(sd2, x="단계", y="건수", text="건수",
                        color_discrete_sequence=["#7986CB"])
        fig_sd.update_layout(showlegend=False, margin=dict(t=10), height=260,
                             xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_sd, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# PAGE 6: 자동화 시나리오
# ═══════════════════════════════════════════════════════════════════
elif page == "⚙️ 자동화 시나리오":
    st.markdown('<div class="section-title">⚙️ Make.com 자동화 시나리오 (7가지)</div>',
                unsafe_allow_html=True)
    st.caption("관여도 그룹별 차등 발송 로직 · Full / Nurturing / Minimal Sequence")
    st.divider()

    SCENARIOS = [
        {
            "num": "시나리오 1",
            "name": "[초기] 주증상 케어 (AI 아바타 영상)",
            "target": "🔴 상 / 🟡 중 그룹",
            "trigger": "DB 2 방문횟수=1 '완료' 등록 → D+1, 오전 11시",
            "condition": "관여도 그룹 ≠ '하'",
            "action": (
                "① DB 2 주증상 Tag 확인\n"
                "② HeyGen API → 해당 팁 영상 생성\n"
                "③ 알림톡 발송 ([환자명]님, '요통 1분 팁'입니다...)\n"
                "④ DB 4 '초기(주증상)' 로그 기록"
            ),
            "emoji": "🎬",
            "color": "#EF5350",
        },
        {
            "num": "시나리오 2",
            "name": "[15일 처방] 밀착 케어 (D+5, D+12)",
            "target": "15일 처방 결제 환자 전체",
            "trigger": "DB 3 등록 D+1 / 복용시작일+5일 / 복용시작일+12일",
            "condition": "처방 DB 존재",
            "action": (
                "(D+1) AI 아바타 복약지도 영상 발송\n"
                "(D+5) 경과체크 버튼형 알림톡 (좋음/보통/불편함)\n"
                "(D+12) 재내원 안내 알림톡"
            ),
            "emoji": "💊",
            "color": "#FF9800",
        },
        {
            "num": "시나리오 3",
            "name": "[15일 처방] 위기 관리",
            "target": "'불편함' 버튼 클릭 환자",
            "trigger": "D+5 경과체크에서 '불편함' 버튼 클릭 (Webhook)",
            "condition": "-",
            "action": (
                "[즉시] 내부 알림 (Slack/SMS): '⚠️ 긴급: [환자명] 불편함 응답!'\n"
                "[즉시] DB 1 환자 상태 → [위기관리] 업데이트"
            ),
            "emoji": "🚨",
            "color": "#D32F2F",
        },
        {
            "num": "시나리오 4",
            "name": "[중기] 다른증상 케어",
            "target": "🔴 상 / 🟡 중 그룹",
            "trigger": "DB 2 방문횟수=4 또는 5 '완료' 등록 → D+1",
            "condition": "관여도 '상'/'중' + DB 4 중복 없음",
            "action": (
                "① DB 1 다른증상 확인 (예: '소화불량')\n"
                "② 알림톡: '문진표에 적으신 것 기억났습니다...'\n"
                "③ DB 4 '중기(다른증상)' 로그 기록"
            ),
            "emoji": "💬",
            "color": "#7B1FA2",
        },
        {
            "num": "시나리오 5",
            "name": "[후기] 걱정증상 케어 (AI 아바타 영상)",
            "target": "🔴 상 그룹",
            "trigger": "마지막 방문일 +30일 (매일 체크)",
            "condition": "관여도 '상' + DB 4 중복 없음",
            "action": (
                "① DB 1 걱정증상 확인 (예: '치매')\n"
                "② HeyGen API → 걱정증상 팁 영상 생성\n"
                "③ 알림톡: '예전에 치매 걱정하셨던 것 기억났습니다...'\n"
                "④ DB 4 '후기(걱정증상)' 로그 기록"
            ),
            "emoji": "🎬",
            "color": "#1565C0",
        },
        {
            "num": "시나리오 6",
            "name": "[진심 동반자] 이벤트 대상 지정",
            "target": "3회차 내원 환자",
            "trigger": "DB 2 방문횟수=3 '완료' 등록",
            "condition": "-",
            "action": (
                "① DB 1 단골상태 → '대상(3회차)' 업데이트\n"
                "② [즉시] 내부 알림 (데스크): '[환자명]님 3회차, 동반자 이벤트 안내 바람'"
            ),
            "emoji": "🎁",
            "color": "#2E7D32",
        },
        {
            "num": "시나리오 7",
            "name": "[진심 동반자] 설문 완료 처리",
            "target": "이벤트 참여 환자",
            "trigger": "Google Form / Typeform 제출 (Webhook)",
            "condition": "-",
            "action": (
                "① '연락처'로 DB 1 환자 검색\n"
                "② 단골상태 → '참여완료' 업데이트\n"
                "③ (선택) '감사합니다' 알림톡 발송"
            ),
            "emoji": "✅",
            "color": "#00796B",
        },
    ]

    for sc in SCENARIOS:
        with st.expander(f"{sc['emoji']}  **{sc['num']}** — {sc['name']}  |  대상: {sc['target']}"):
            s1, s2 = st.columns([1, 2])
            with s1:
                st.markdown(f"**🎯 트리거**  \n{sc['trigger']}")
                st.markdown(f"**🔀 조건**  \n{sc['condition']}")
            with s2:
                st.markdown("**⚡ 액션**")
                for line in sc["action"].strip().split("\n"):
                    st.markdown(f"&nbsp;&nbsp;{line}")
        st.markdown("")

    st.divider()
    st.subheader("관여도 그룹별 CRM 전략 요약")

    seq_c1, seq_c2, seq_c3, seq_c4 = st.columns(4)
    with seq_c1:
        st.markdown("""
**🔴 관여도 상 (High)**
`Full Sequence`
- 시나리오 1 (초기 AI 영상)
- 시나리오 2 (15일 처방)
- 시나리오 4 (중기 다른증상)
- 시나리오 5 (후기 걱정증상)
- 시나리오 6/7 (동반자 이벤트)
""")
    with seq_c2:
        st.markdown("""
**🟡 관여도 중 (Medium)**
`Nurturing Sequence`
- 시나리오 1 (초기 AI 영상) ✓
- 시나리오 4 (중기 · 정보성) ✓
- 반응에 따라 상 그룹 승격
- 시나리오 5/후기 콘텐츠 ✗
""")
    with seq_c3:
        st.markdown("""
**⚪ 관여도 하 (Low)**
`Minimal Sequence`
- 모든 관계 형성용 콘텐츠 ✗
- 예약 알림 등 기능성만 ✓
- 과잉진료 인상 방지
- 자연 재방문 유도
""")
    with seq_c4:
        st.markdown("""
**⛔ 발송중단 (Flag)**
`CRM 완전 차단`
- 모든 자동화 즉시 중단 ✓
- EMR 'CRM 금지' 플래그
- 악성 후기·스팸 신고 방지
- 환자 의사 존중
""")
