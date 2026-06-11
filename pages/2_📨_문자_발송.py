import streamlit as st
import pandas as pd
import requests

from crm_data import load_customers
from crm_sms import DEFAULT_WEBHOOK, SENDER_NUMBERS, render_message, send_sms, message_type

# 1. 페이지 설정
st.set_page_config(
    page_title="문자 발송",
    page_icon="📨",
    layout="wide",
    initial_sidebar_state="expanded"
)


# 2. 메인 화면
st.title("📨 문자 발송")
st.caption("CRM 고객을 선택해 Make.com 자동화(SOLAPI)로 문자를 보냅니다.")
st.markdown("---")

df, is_uploaded = load_customers()
if not is_uploaded:
    st.warning("⚠️ 지금은 **샘플 데이터**입니다. 샘플의 전화번호(010-0000-XXXX)는 가짜라서 "
               "실제 발송하면 실패하거나 건당 요금만 차감될 수 있습니다. "
               "실제 고객 CSV를 업로드하거나, 아래 '테스트 발송'으로 내 번호에 먼저 보내보세요.")

if "전화번호" not in df.columns:
    st.error("데이터에 '전화번호' 컬럼이 없습니다. 전화번호가 포함된 CSV를 업로드해주세요.")
    st.stop()

# 사이드바: 발송 설정
with st.sidebar:
    st.header("⚙️ 발송 설정")
    webhook_url = st.text_input("Make 웹훅 URL", value=DEFAULT_WEBHOOK)
    sender = st.selectbox("발신번호", SENDER_NUMBERS)
    st.caption("발신번호는 SOLAPI에 사전 등록된 번호만 사용 가능합니다.")

# 4. 수신 대상 선택
st.subheader("1️⃣ 수신 대상 선택")
c1, c2, c3 = st.columns(3)
sel_grade = c1.multiselect("등급", ["VIP", "Gold", "Silver", "Bronze"])
sel_stage = c2.multiselect("영업단계", sorted(df["영업단계"].unique()))
sel_region = c3.multiselect("지역", sorted(df["지역"].unique()))

targets = df.copy()
if sel_grade:
    targets = targets[targets["등급"].isin(sel_grade)]
if sel_stage:
    targets = targets[targets["영업단계"].isin(sel_stage)]
if sel_region:
    targets = targets[targets["지역"].isin(sel_region)]

picked = st.multiselect(
    "개별 선택 (비워두면 필터된 전체 대상)",
    options=targets["고객명"].tolist(),
)
if picked:
    targets = targets[targets["고객명"].isin(picked)]

st.caption(f"발송 대상: **{len(targets)}명**")

# 5. 메시지 작성
st.subheader("2️⃣ 메시지 작성")
st.caption("플레이스홀더 사용 가능: {고객명} {회사명} {등급} {담당자} {지역}")
template = st.text_area(
    "메시지 내용",
    value="[트렌드마스터] {고객명}님 안녕하세요!\n{등급} 고객님께 드리는 안내입니다.",
    height=120,
)

sample_msg = render_message(template, targets.iloc[0]) if len(targets) else template
byte_len, msg_type = message_type(sample_msg)
st.caption(f"예상 길이: 약 {byte_len} byte → **{msg_type}** 요금 적용")

# 6. 미리보기
st.subheader("3️⃣ 미리보기")
if len(targets):
    preview = targets.head(5).copy()
    preview["발송될 메시지"] = preview.apply(lambda r: render_message(template, r), axis=1)
    st.dataframe(
        preview[["고객명", "전화번호", "발송될 메시지"]],
        use_container_width=True, hide_index=True
    )
    if len(targets) > 5:
        st.caption(f"...외 {len(targets) - 5}명")
else:
    st.info("발송 대상이 없습니다. 필터를 조정해주세요.")

# 7. 발송
st.subheader("4️⃣ 발송")
tab_real, tab_test = st.tabs(["📤 실제 발송", "🧪 테스트 발송 (내 번호로 1건)"])

with tab_real:
    confirm = st.checkbox(f"위 {len(targets)}명에게 실제 문자를 발송하는 것에 동의합니다 (건당 과금)")
    if st.button("🚀 문자 발송하기", type="primary", disabled=not (confirm and len(targets))):
        with st.spinner("발송 요청 중..."):
            res, sent = send_sms(webhook_url, sender, targets, template)
        if res.status_code == 200:
            st.success(f"✅ {sent}건 발송 요청 완료! Make 시나리오 실행 내역에서 결과를 확인하세요.")
        else:
            st.error(f"발송 실패 (HTTP {res.status_code}): {res.text}")

with tab_test:
    test_number = st.text_input("테스트 수신번호 (본인 휴대폰)", placeholder="01012345678")
    if st.button("🧪 테스트 1건 발송", disabled=not test_number):
        test_row = targets.iloc[0] if len(targets) else df.iloc[0]
        recipients = [{"to": test_number.replace("-", ""), "text": render_message(template, test_row)}]
        with st.spinner("발송 요청 중..."):
            res = requests.post(webhook_url, json={"from": sender, "recipients": recipients}, timeout=30)
        if res.status_code == 200:
            st.success("✅ 테스트 발송 요청 완료! 휴대폰을 확인해보세요.")
        else:
            st.error(f"발송 실패 (HTTP {res.status_code}): {res.text}")
