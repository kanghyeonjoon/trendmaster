import requests

# Make.com 웹훅 → SOLAPI 문자 발송 시나리오
DEFAULT_WEBHOOK = "https://hook.eu2.make.com/k2jfe47yd2lpv967fga27nflwvlf1ssg"
SENDER_NUMBERS = ["01099168760", "01080649300"]  # SOLAPI에 등록된 발신번호


# 메시지 템플릿 치환 ({고객명}, {회사명} 등)
def render_message(template, row):
    msg = template
    for key in ["고객명", "회사명", "등급", "담당자", "지역"]:
        if key in row:
            msg = msg.replace("{" + key + "}", str(row[key]))
    return msg


# 대상 DataFrame을 웹훅 페이로드로 변환해 발송 요청
def send_sms(webhook_url, sender, targets, template):
    recipients = [
        {"to": str(r["전화번호"]).replace("-", ""), "text": render_message(template, r)}
        for _, r in targets.iterrows()
    ]
    res = requests.post(webhook_url, json={"from": sender, "recipients": recipients}, timeout=30)
    return res, len(recipients)


# SMS/LMS 예상 요금 구분 (한글 2byte 기준, 90byte 초과 시 LMS)
def message_type(text):
    byte_len = len(text.encode("euc-kr", errors="replace"))
    return byte_len, ("SMS (단문)" if byte_len <= 90 else "LMS (장문)")
