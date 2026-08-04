"""오늘의 작성 브리프를 출력한다.

매일 아침 스레드 글을 쓰기 전에 이걸 먼저 실행한다.
- 오늘 날짜 (한국 시간)
- 문체 레퍼런스로 쓸 아카이브 글 8편 (날마다 다른 조합)
- 최근 30일간 이미 보낸 주제 (겹치지 않게)

    python3 threads_daily/brief.py
"""

from __future__ import annotations

import json
import random
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# `brief.py | head` 처럼 파이프로 잘라 볼 때 역추적이 뜨지 않게 한다
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

BASE = Path(__file__).resolve().parent
POSTS = BASE / "data" / "posts.json"
HISTORY = BASE / "state" / "history.json"

KST = ZoneInfo("Asia/Seoul")
NUM_EXAMPLES = 8
HISTORY_LOOKBACK = 30
POSTS_PER_DAY = 5


def today_kst():
    return datetime.now(KST).date()


def load_examples(seed: int, n: int = NUM_EXAMPLES) -> list[dict]:
    """날짜를 시드로 문체 예시를 뽑는다. 같은 날은 같은 조합, 날이 바뀌면 다른 조합."""
    posts = json.loads(POSTS.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    # 너무 짧은 글은 문체 레퍼런스로 약하다
    pool = [p for p in posts if p["chars"] >= 200]
    return rng.sample(pool, min(n, len(pool)))


def load_history(limit: int = HISTORY_LOOKBACK) -> list[dict]:
    if not HISTORY.exists():
        return []
    try:
        entries = json.loads(HISTORY.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return entries[-limit:]


def main() -> None:
    today = today_kst()
    examples = load_examples(seed=today.toordinal())
    history = load_history()

    print(f"# 오늘 날짜\n{today.strftime('%Y년 %m월 %d일')} (한국 시간)\n")
    print(f"오늘 쓸 글: {POSTS_PER_DAY}편\n")

    print("# 문체 레퍼런스 — 몽PD가 실제로 올렸던 글")
    for i, ex in enumerate(examples, 1):
        print(f"\n--- 예시 {i} ---\n{ex['text']}")

    print("\n\n# 최근에 이미 보낸 주제 (겹치지 마라)")
    if history:
        for h in reversed(history):
            print(f"- [{h.get('date', '?')}] {h.get('topic', '')} / {h.get('angle', '')}")
    else:
        print("(아직 없음 — 첫 발송이다)")

    print("\n\n# 다음 할 일")
    print("threads_daily/WRITING-GUIDE.md 를 읽고 그 규칙대로 5편을 써라.")


if __name__ == "__main__":
    main()
