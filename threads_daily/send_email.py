"""생성한 글을 Gmail SMTP로 발송한다.

필요한 환경변수:
    GMAIL_USER          보내는 지메일 주소
    GMAIL_APP_PASSWORD  지메일 앱 비밀번호 (계정 비밀번호 아님)
    MAIL_TO             받는 주소. 없으면 GMAIL_USER로 보낸다
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from html import escape

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _blocks(thread) -> list[tuple[str, str]]:
    """(라벨, 본문) 순서대로 정리. 그대로 복사해 올리는 순서와 같다."""
    blocks = [("본문", thread.main)]
    for i, comment in enumerate(thread.comments, 1):
        blocks.append((f"댓글 {i}", comment))
    if thread.cta.strip():
        blocks.append(("마지막 유도", thread.cta))
    return blocks


def render_text(thread, today) -> str:
    lines = [f"{today.strftime('%Y-%m-%d')} 오늘의 스레드", ""]
    for label, body in _blocks(thread):
        lines += [f"[{label}]", body, "", "-" * 32, ""]
    lines += [
        f"주제: {thread.topic}",
        f"각도: {thread.angle}",
        f"어투: {thread.tone}",
        f"메모: {thread.why}",
    ]
    return "\n".join(lines)


def render_html(thread, today) -> str:
    cards = []
    for label, body in _blocks(thread):
        cards.append(
            f'<div class="card">'
            f'<div class="label">{escape(label)}</div>'
            f'<pre>{escape(body)}</pre>'
            f"</div>"
        )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:16px;background:#f4f4f5;
  font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
<div style="max-width:600px;margin:0 auto;">
  <div style="font-size:13px;color:#71717a;margin-bottom:4px;">
    {today.strftime('%Y년 %m월 %d일')} · 오늘의 스레드
  </div>
  <div style="font-size:19px;font-weight:700;color:#18181b;line-height:1.4;margin-bottom:16px;">
    {escape(thread.hook)}
  </div>
  {''.join(cards)}
  <div style="margin-top:16px;padding:14px 16px;background:#fafafa;border-radius:10px;
    font-size:13px;color:#52525b;line-height:1.7;">
    <b>주제</b> {escape(thread.topic)}<br>
    <b>각도</b> {escape(thread.angle)}<br>
    <b>어투</b> {escape(thread.tone)}<br>
    <b>메모</b> {escape(thread.why)}
  </div>
  <div style="margin-top:14px;font-size:12px;color:#a1a1aa;line-height:1.6;">
    트래픽이 가장 잘 나오는 시간대는 오전 7~8시, 저녁 7시~자정입니다.<br>
    본문을 올린 뒤 댓글을 순서대로 이어 다세요.
  </div>
</div>
<style>
  .card{{background:#fff;border-radius:10px;padding:14px 16px;margin-bottom:10px;
    border:1px solid #e4e4e7;}}
  .label{{font-size:11px;font-weight:700;color:#a1a1aa;letter-spacing:.04em;
    margin-bottom:8px;}}
  .card pre{{margin:0;white-space:pre-wrap;word-break:break-word;font-size:15px;
    line-height:1.75;color:#18181b;font-family:inherit;}}
</style>
</body></html>"""


def send(subject: str, text_body: str, html_body: str | None = None) -> None:
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"몽PD 스레드 <{user}>"
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    print(f"발송 완료 → {to}")


def send_thread(thread, today) -> None:
    send(
        subject=f"[{today.strftime('%m/%d')} 오늘의 스레드] {thread.hook[:40]}",
        text_body=render_text(thread, today),
        html_body=render_html(thread, today),
    )


def send_failure(today, error: str) -> None:
    """생성이 실패해도 침묵하지 않는다. 아침에 상황을 알 수 있게 알린다."""
    body = (
        f"{today.strftime('%Y-%m-%d')} 오늘의 스레드 생성에 실패했습니다.\n\n"
        f"{error}\n\n"
        "GitHub Actions 로그를 확인하거나, 워크플로를 수동 실행(Run workflow)해 주세요."
    )
    send(subject=f"[{today.strftime('%m/%d')} 스레드] 생성 실패", text_body=body)
