import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from crm_data import load_customers
from crm_sms import DEFAULT_WEBHOOK, SENDER_NUMBER, render_message, send_sms, message_type

# 1. 페이지 설정
st.set_page_config(
    page_title="자동 발송 규칙",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🤖 자동 발송 규칙")
st.caption("조건에 맞는 고객을 자동으로 골라 캠페인 문자를 보냅니다.")
st.markdown("---")

df, is_uploaded = load_customers()
if not is_uploaded:
    st.warning("⚠️ 지금은 **샘플 데이터**입니다. 전화번호가 가짜라서 실제 발송 시 실패하거나 "
               "요금만 차감될 수 있습니다. 실제 고객 CSV 업로드 후 사용하세요.")

if "전화번호" not in df.columns:
    st.error("데이터에 '전화번호' 컬럼이 없습니다. 전화번호가 포함된 CSV를 업로드해주세요.")
    st.stop()

# 사이드바: 발송 설정
with st.sidebar:
    st.header("⚙️ 발송 설정")
    webhook_url = st.text_input("Make 웹훅 URL", value=DEFAULT_WEBHOOK)
    st.text_input("발신번호", value=SENDER_NUMBER, disabled=True)
    st.caption("발신번호는 Make 시나리오에 고정되어 있습니다.")


# 2. 규칙별 공통 UI (대상 미리보기 + 템플릿 + 발송)
def campaign_section(key, targets, default_template):
    st.caption(f"대상 고객: **{len(targets)}명**")

    template = st.text_area("메시지 템플릿", value=default_template, height=120, key=f"tpl_{key}")

    if len(targets):
        sample = render_message(template, targets.iloc[0])
        byte_len, msg_type = message_type(sample)
        st.caption(f"예상 길이: 약 {byte_len} byte → **{msg_type}** 요금 적용")

        with st.expander("👀 대상 및 메시지 미리보기"):
            preview = targets.head(10).copy()
            preview["발송될 메시지"] = preview.apply(lambda r: render_message(template, r), axis=1)
            st.dataframe(
                preview[["고객명", "전화번호", "등급", "발송될 메시지"]],
                use_container_width=True, hide_index=True
            )
            if len(targets) > 10:
                st.caption(f"...외 {len(targets) - 10}명")

        confirm = st.checkbox(f"{len(targets)}명에게 실제 발송하는 것에 동의합니다 (건당 과금)", key=f"ok_{key}")
        if st.button("🚀 캠페인 발송", type="primary", disabled=not confirm, key=f"send_{key}"):
            with st.spinner("발송 요청 중..."):
                sent, failed = send_sms(webhook_url, targets, template)
            if not failed:
                st.success(f"✅ {sent}건 발송 요청 완료!")
            else:
                st.error(f"{sent}건 성공, {len(failed)}건 실패: {', '.join(failed[:5])}")
    else:
        st.info("조건에 맞는 고객이 없습니다.")


# 3. 캠페인 규칙 3종
tab_welcome, tab_remind, tab_vip = st.tabs(["🎉 신규 가입 환영", "⏰ 미거래 리마인드", "💎 VIP 감사"])

today = datetime.now().date()

with tab_welcome:
    st.subheader("🎉 신규 가입 환영 문자")
    days = st.slider("가입 후 경과일 기준", 1, 30, 7, key="d_welcome",
                     help="이 기간 안에 가입한 고객에게 보냅니다.")
    targets = df[pd.to_datetime(df["가입일"]).dt.date >= today - timedelta(days=days)]
    campaign_section(
        "welcome", targets,
        "[트렌드마스터] {고객명}님, 가입을 진심으로 환영합니다!\n"
        "담당자 {담당자}가 정성껏 모시겠습니다. 궁금한 점은 언제든 연락주세요.",
    )

with tab_remind:
    st.subheader("⏰ 미거래 고객 리마인드")
    days = st.slider("마지막 거래 후 경과일 기준", 14, 180, 30, key="d_remind",
                     help="이 기간 이상 거래가 없는 고객에게 보냅니다. (이탈 고객 제외)")
    targets = df[
        (pd.to_datetime(df["최근거래일"]).dt.date <= today - timedelta(days=days))
        & (df["영업단계"] != "이탈")
    ]
    campaign_section(
        "remind", targets,
        "[트렌드마스터] {고객명}님, 오랜만에 인사드립니다.\n"
        "최근 새로운 소식이 많아 안내드리고 싶습니다. 편하신 시간에 연락주시면 감사하겠습니다.",
    )

with tab_vip:
    st.subheader("💎 VIP 고객 감사 문자")
    grades = st.multiselect("대상 등급", ["VIP", "Gold", "Silver", "Bronze"], default=["VIP"], key="g_vip")
    targets = df[df["등급"].isin(grades)] if grades else df.iloc[0:0]
    campaign_section(
        "vip", targets,
        "[트렌드마스터] {고객명}님, 늘 함께해주셔서 감사합니다.\n"
        "{등급} 고객님을 위한 특별 혜택을 준비했습니다. 자세한 내용은 담당자 {담당자}에게 문의해주세요.",
    )
