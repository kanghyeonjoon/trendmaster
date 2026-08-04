"""스레드 아카이브 원문(archive.txt)을 글 단위 JSON으로 파싱한다.

아카이브는 사람이 손으로 관리하는 텍스트 파일이라 구분선이 제각각이다.
(`----`, `-------`, `ㅡㅡㅡㅡ` 등) 그래서 구분선 길이를 따지지 않고
"대시/장음부호만 3개 이상인 줄"을 전부 글 경계로 본다.

사용법:
    python threads_daily/build_corpus.py
"""

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVE = BASE / "data" / "archive.txt"
OUT = BASE / "data" / "posts.json"

# 글과 글 사이 구분선
SEPARATOR = re.compile(r"^[\s]*[-—–ㅡ_]{3,}[\s]*$")

# 댓글로 넘기는 지점. 원문에 (댓글) [댓글] <댓글> [첫 번째 댓글] — 댓글 — (다음) 등이
# 섞여 있고 오타(디음)도 그대로 남아 있어서 함께 잡는다.
COMMENT_BREAK = re.compile(
    r"^[\s]*[\(\[<\-—–]{1,2}\s*"
    r"(?:첫|두|세|네)?\s*(?:번째)?\s*"
    r"(?:댓글|다음|디음)"
    r"\s*[\)\]>\-—–]{1,2}[\s]*$"
)

# 원문 정리용 순번 마커. 예: [5], [1]
INDEX_MARKER = re.compile(r"^[\s]*\[\d+\][\s]*$")

# 팔로우/신청/링크 유도가 들어간 글인지 판별
CTA_HINTS = ("팔로우", "신청", "댓글에", "디엠", "프로필 링크", "리포스트", "상담")

MIN_CHARS = 40
MIN_LINES = 3


def split_posts(raw: str) -> list[str]:
    chunks, current = [], []
    for line in raw.splitlines():
        if SEPARATOR.match(line):
            chunks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    chunks.append("\n".join(current))
    return chunks


def clean(chunk: str) -> str:
    lines = [ln.rstrip() for ln in chunk.splitlines()]
    # 앞뒤 빈 줄과 순번 마커 제거
    while lines and (not lines[0].strip() or INDEX_MARKER.match(lines[0])):
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def analyze(text: str) -> dict:
    lines = text.splitlines()
    breaks = sum(1 for ln in lines if COMMENT_BREAK.match(ln))
    hook = next((ln.strip() for ln in lines if ln.strip()), "")
    return {
        "text": text,
        "hook": hook,
        "chars": len(text),
        "comment_breaks": breaks,
        "has_cta": any(h in text for h in CTA_HINTS),
    }


def main() -> None:
    if not ARCHIVE.exists():
        raise SystemExit(f"아카이브 원문이 없습니다: {ARCHIVE}")

    raw = ARCHIVE.read_text(encoding="utf-8")
    posts = []
    for chunk in split_posts(raw):
        text = clean(chunk)
        if len(text) < MIN_CHARS or len(text.splitlines()) < MIN_LINES:
            continue
        post = analyze(text)
        post["id"] = len(posts)
        posts.append(post)

    OUT.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    with_cta = sum(1 for p in posts if p["has_cta"])
    with_breaks = sum(1 for p in posts if p["comment_breaks"])
    print(f"파싱 완료: {len(posts)}편 → {OUT}")
    print(f"  댓글 분리형: {with_breaks}편 / CTA 포함: {with_cta}편")
    print(f"  평균 길이: {sum(p['chars'] for p in posts) // len(posts)}자")


if __name__ == "__main__":
    main()
