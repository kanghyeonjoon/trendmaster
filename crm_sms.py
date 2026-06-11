import requests

# Make.com 웹훅 → SOLAPI 문자 발송 시나리오
DEFAULT_WEBHOOK = "https://hook.eu2.make.com/k2jfe47yd2lpv967fga27nflwvlf1ssg"
# 발신번호는 Make 시나리오의 SOLAPI 모듈에 고정되어 있음 (변경은 Make에서)
SENDER_NUMBER = "01080649300"


# 메시지 템플릿 치환 ({고객명}, {회사명} 등)
def render_message(template, row):
    msg = template
    for key in ["고객명", "회사명", "등급", "담당자", "지역"]:
        if key in row:
            msg = msg.replace("{" + key + "}", str(row[key]))
    return msg


# 수신자별로 {to, text} 평탄 JSON을 웹훅에 1건씩 POST (시나리오가 1건=1실행 처리)
def send_sms(webhook_url, targets, template):
    sent, failed = 0, []
    for _, r in targets.iterrows():
        to = str(r["전화번호"]).replace("-", "")
        payload = {"to": to, "text": render_message(template, r)}
        try:
            res = requests.post(webhook_url, json=payload, timeout=30)
            if res.status_code == 200:
                sent += 1
            else:
                failed.append(f"{to} (HTTP {res.status_code})")
        except requests.RequestException as e:
            failed.append(f"{to} ({e})")
    return sent, failed


# SMS/LMS 예상 요금 구분 (한글 2byte 기준, 90byte 초과 시 LMS)
def message_type(text):
    byte_len = len(text.encode("euc-kr", errors="replace"))
    return byte_len, ("SMS (단문)" if byte_len <= 90 else "LMS (장문)")
