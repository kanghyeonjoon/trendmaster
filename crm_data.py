import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta


# CRM 샘플 데이터 생성 (대시보드/문자발송 페이지 공용)
@st.cache_data
def generate_sample_data(n=300, seed=42):
    rng = np.random.default_rng(seed)
    today = datetime.now()

    regions = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "기타"]
    grades = ["VIP", "Gold", "Silver", "Bronze"]
    channels = ["홈페이지", "전화상담", "지인추천", "광고", "전시회"]
    stages = ["리드", "상담중", "제안", "협상", "계약완료", "이탈"]
    managers = ["김민수", "이서연", "박지훈", "최유진", "정도현"]

    data = {
        "고객명": [f"고객{i+1:03d}" for i in range(n)],
        "회사명": [f"{rng.choice(['한빛', '미래', '대한', '글로벌', '스마트'])}{rng.choice(['상사', '테크', '물산', '산업', '솔루션'])}" for _ in range(n)],
        # 주의: 샘플용 가짜 번호 (010-0000-XXXX). 실제 발송 시 실패합니다.
        "전화번호": [f"010-0000-{i+1:04d}" for i in range(n)],
        "지역": rng.choice(regions, n, p=[0.30, 0.25, 0.08, 0.12, 0.07, 0.06, 0.05, 0.07]),
        "등급": rng.choice(grades, n, p=[0.10, 0.25, 0.35, 0.30]),
        "유입채널": rng.choice(channels, n),
        "영업단계": rng.choice(stages, n, p=[0.25, 0.20, 0.15, 0.10, 0.22, 0.08]),
        "담당자": rng.choice(managers, n),
        "누적매출": (rng.gamma(2, 1500, n)).round(-1).astype(int),  # 만원 단위
        "가입일": [today - timedelta(days=int(d)) for d in rng.uniform(0, 730, n)],
        "최근거래일": [today - timedelta(days=int(d)) for d in rng.uniform(0, 180, n)],
    }
    df = pd.DataFrame(data)
    df["가입일"] = pd.to_datetime(df["가입일"]).dt.date
    df["최근거래일"] = pd.to_datetime(df["최근거래일"]).dt.date
    return df


# 업로드된 데이터가 있으면 그것을, 없으면 샘플을 반환 (페이지 간 공유)
def load_customers():
    if "crm_df" in st.session_state:
        return st.session_state["crm_df"], True
    return generate_sample_data(), False


def save_uploaded(df):
    df["가입일"] = pd.to_datetime(df["가입일"]).dt.date
    df["최근거래일"] = pd.to_datetime(df["최근거래일"]).dt.date
    st.session_state["crm_df"] = df
    return df
