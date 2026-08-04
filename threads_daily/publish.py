"""오늘 쓴 글 5편을 메일 형태로 렌더링하고 발송 기록을 남긴다.

입력은 아래 형식의 JSON 배열이다 (WRITING-GUIDE.md의 '글 하나의 형식' 참고).

    [{"topic": "...", "angle": "...", "tone": "존댓말", "hook": "...",
      "main": "...", "comments": ["...", "..."], "cta": "...", "why": "..."}, ...]

    python3 threads_daily/publish.py today.json --html out.html --text out.txt

지메일 임시보관함에 넣을 제목/HTML/텍스트를 만들어 준다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from html import escape
from pathlib import Path

from brief import HISTORY, today_kst

REQUIRED = ("topic", "angle", "tone", "hook", "main", "why")


# --------------------------------------------------------------------------
# 검증
# --------------------------------------------------------------------------


def validate(raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise SystemExit("입력은 비어 있지 않은 JSON 배열이어야 합니다.")

    posts = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise SystemExit(f"{i}번째 항목이 객체가 아닙니다.")
        missing = [k for k in REQUIRED if not str(item.get(k, "")).strip()]
        if missing:
            raise SystemExit(f"{i}번째 글에 빠진 항목: {', '.join(missing)}")
        if item["tone"] not in ("존댓말", "반말"):
            raise SystemExit(f"{i}번째 글의 tone은 '존댓말' 또는 '반말'이어야 합니다.")

        post = dict(item)
        post["comments"] = [c for c in item.get("comments") or [] if str(c).strip()]
        post["cta"] = str(item.get("cta") or "").strip()
        # 본문 첫 줄과 훅이 어긋나면 복사해 올릴 때 티가 난다
        first_line = post["main"].strip().splitlines()[0].strip()
        if first_line != post["hook"].strip():
            print(
                f"경고: {i}번째 글의 본문 첫 줄이 훅과 다릅니다.\n"
                f"  훅   : {post['hook']}\n  첫 줄: {first_line}",
                file=sys.stderr,
            )
        posts.append(post)
    return posts


# --------------------------------------------------------------------------
# 렌더링
# --------------------------------------------------------------------------


def blocks(post: dict) -> list[tuple[str, str]]:
    """(라벨, 본문) 순서대로. 그대로 복사해 올리는 순서와 같다."""
    out = [("본문", post["main"])]
    for i, comment in enumerate(post["comments"], 1):
        out.append((f"댓글 {i}", comment))
    if post["cta"]:
        out.append(("마지막 유도", post["cta"]))
    return out


def render_text(posts: list[dict], today: date) -> str:
    lines = [f"{today.strftime('%Y-%m-%d')} 오늘의 스레드 {len(posts)}편", ""]
    for n, post in enumerate(posts, 1):
        lines += ["=" * 40, f"{n}번째 글 — {post['topic']}", "=" * 40, ""]
        for label, body in blocks(post):
            lines += [f"[{label}]", body, "", "-" * 32, ""]
        lines += [
            f"각도: {post['angle']}",
            f"어투: {post['tone']}",
            f"메모: {post['why']}",
            "",
            "",
        ]
    return "\n".join(lines)


def _post_html(post: dict, n: int) -> str:
    cards = "".join(
        f'<div class="card"><div class="label">{escape(label)}</div>'
        f"<pre>{escape(body)}</pre></div>"
        for label, body in blocks(post)
    )
    return f"""<div class="post">
  <div class="num">{n}번째 글</div>
  <div class="hook">{escape(post['hook'])}</div>
  {cards}
  <div class="meta">
    <b>주제</b> {escape(post['topic'])}<br>
    <b>각도</b> {escape(post['angle'])}<br>
    <b>어투</b> {escape(post['tone'])}<br>
    <b>메모</b> {escape(post['why'])}
  </div>
</div>"""


def render_html(posts: list[dict], today: date) -> str:
    body = "".join(_post_html(p, n) for n, p in enumerate(posts, 1))
    return f"""<div style="max-width:600px;margin:0 auto;padding:8px;
  font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <div style="font-size:13px;color:#71717a;margin-bottom:14px;">
    {today.strftime('%Y년 %m월 %d일')} · 오늘의 스레드 {len(posts)}편
  </div>
  {body}
  <div style="margin-top:8px;font-size:12px;color:#a1a1aa;line-height:1.6;">
    트래픽이 가장 잘 나오는 시간대는 오전 7~8시, 저녁 7시~자정입니다.<br>
    본문을 올린 뒤 댓글을 순서대로 이어 다세요.
  </div>
<style>
  .post{{margin-bottom:28px;padding-bottom:20px;border-bottom:2px solid #e4e4e7;}}
  .post:last-of-type{{border-bottom:none;}}
  .num{{display:inline-block;font-size:11px;font-weight:700;color:#fff;background:#18181b;
    padding:3px 9px;border-radius:99px;margin-bottom:8px;}}
  .hook{{font-size:18px;font-weight:700;color:#18181b;line-height:1.45;margin-bottom:12px;}}
  .card{{background:#fff;border-radius:10px;padding:14px 16px;margin-bottom:10px;
    border:1px solid #e4e4e7;}}
  .label{{font-size:11px;font-weight:700;color:#a1a1aa;letter-spacing:.04em;margin-bottom:8px;}}
  .card pre{{margin:0;white-space:pre-wrap;word-break:break-word;font-size:15px;
    line-height:1.75;color:#18181b;font-family:inherit;}}
  .meta{{padding:12px 14px;background:#fafafa;border-radius:8px;font-size:13px;
    color:#52525b;line-height:1.7;}}
</style>
</div>"""


def subject(posts: list[dict], today: date) -> str:
    return f"[{today.strftime('%m/%d')} 오늘의 스레드 {len(posts)}편] {posts[0]['hook'][:30]}"


# --------------------------------------------------------------------------
# 기록
# --------------------------------------------------------------------------


def record(posts: list[dict], today: date, keep: int = 200) -> None:
    entries = []
    if HISTORY.exists():
        try:
            entries = json.loads(HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    for post in posts:
        entries.append(
            {
                "date": today.isoformat(),
                "topic": post["topic"],
                "angle": post["angle"],
                "hook": post["hook"],
            }
        )
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(
        json.dumps(entries[-keep:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="글 5편이 담긴 JSON 파일")
    parser.add_argument("--html", help="메일 HTML을 저장할 경로")
    parser.add_argument("--text", help="메일 텍스트본을 저장할 경로")
    parser.add_argument(
        "--no-record", action="store_true", help="history.json에 기록하지 않는다 (연습용)"
    )
    args = parser.parse_args()

    posts = validate(json.loads(Path(args.input).read_text(encoding="utf-8")))
    today = today_kst()

    if args.html:
        Path(args.html).write_text(render_html(posts, today), encoding="utf-8")
    if args.text:
        Path(args.text).write_text(render_text(posts, today), encoding="utf-8")

    if not args.no_record:
        record(posts, today)

    print(f"검증 통과: {len(posts)}편")
    print(f"제목: {subject(posts, today)}")
    if args.html:
        print(f"HTML: {args.html}")
    if args.text:
        print(f"텍스트: {args.text}")
    if not args.no_record:
        print(f"기록 완료: {HISTORY}")


if __name__ == "__main__":
    main()
