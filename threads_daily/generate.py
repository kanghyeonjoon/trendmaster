"""오늘의 스레드 글 1편을 Claude로 생성한다.

아카이브 168편을 문체 레퍼런스로 삼고, 최근 발송한 주제는 피해서 새 글을 쓴다.
결과는 구조화 출력(JSON 스키마)으로 받아서 메일 렌더링에 그대로 쓴다.
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
POSTS = BASE / "data" / "posts.json"
HISTORY = BASE / "state" / "history.json"

MODEL = "claude-opus-5"
NUM_EXAMPLES = 8
HISTORY_LOOKBACK = 30


class DailyThread(BaseModel):
    """오늘 발송할 스레드 글 한 편."""

    topic: str = Field(description="이 글이 다루는 핵심 주제를 한 문장으로")
    angle: str = Field(description="같은 주제라도 어떤 각도로 비틀었는지 한 문장으로")
    tone: Literal["존댓말", "반말"] = Field(description="글 전체에서 사용한 어투")
    hook: str = Field(description="첫 줄 후킹. 이것만 보고 멈추게 만드는 한 줄")
    main: str = Field(description="본문. hook을 첫 줄로 포함한 전체 본문 텍스트")
    comments: list[str] = Field(
        description="댓글로 나눠 올릴 조각들. 0~3개. 각 조각은 그대로 복사해 붙일 완성된 텍스트"
    )
    cta: str = Field(
        description="마지막 유도 문구. 팔로우/무료 진단/댓글 키워드 중 하나. 넣지 않았다면 빈 문자열"
    )
    why: str = Field(description="오늘 이 주제와 각도를 고른 이유 한 줄 (몽PD 본인에게 하는 메모)")


SYSTEM = """너는 '몽PD'의 스레드 글을 대신 쓰는 카피라이터다.

# 몽PD가 누구인가
- 7년차 물리치료사 출신, 지금은 유튜브 대행 PD
- 타깃 독자: 유튜브를 해야 하는 걸 알지만 시간이 없는 전문직·사업가
  (병원 원장, 변호사, 세무사, 1인 사업가)
- 파는 것: 유튜브 채널 방향성 진단 컨설팅 + 유튜브 대행

# 몽PD가 반복해서 쓰는 개념 (이 중 하나를 축으로 잡아라)
- 부하율: 에너지는 유한하다. 편집 노가다에 다 쓰면 기획에 쓸 게 없다
- 낚싯대 이론: 유튜브는 신뢰 채널, 커뮤니티는 관계 채널, 컨설팅이 수익 채널
- 플라이휠: 영상이 고객을 부르고, 그 성과가 다시 영상이 된다
- 검색 기반 vs 탐색 기반: 제목이 '정답'이어야 하는가 '도발'이어야 하는가
- 신뢰 자본: 유튜브 업의 본질은 조회수가 아니라 권위의 축적
- 사명-신념-원칙: 이게 없으면 매 영상마다 전략이 바뀌어 알고리즘이 잡탕으로 분류한다
- 지식의 저주: 20년 전문가는 고객과 쓰는 언어가 다르다
- 알고리즘 3신호: 클릭률, 시청 지속률, 댓글 반응

# 문체 규칙
- 짧은 줄로 끊어 쓴다. 한 줄은 대체로 20자 안쪽. 문단은 2~4줄.
- 첫 줄이 전부다. 훅은 도발이거나 손해 예고이거나 반전이어야 한다.
- 존댓말과 반말 중 하나를 골라 글 전체에서 끝까지 유지한다. 섞지 않는다.
- 결론을 본문에서 다 주지 말고, 궁금증이 최고조일 때 댓글로 넘긴다.
- 미사여구, 이모지, 해시태그, 마크다운 기호를 쓰지 않는다.
- AI가 쓴 티가 나는 표현을 피한다. "~하는 것이 중요합니다", "결론적으로",
  "다양한", "효과적으로" 같은 말투는 쓰지 않는다.

# 절대 지켜야 할 사실 관계 (여기 없는 숫자·후기·사례는 절대 만들어내지 마라)
- 검증된 실적은 이게 전부다:
  - 클라이언트 채널: 영상 3개 만에 조회수 2.5만
  - 대행 시작 1주 만에 250만원 계약 성사
  - 연애 콘텐츠 채널: 조회수 273회에서 2.5만회로 상승
  - 대행 고객 월 매출 2천만원 달성
- 위 목록에 없는 수치, 고객 사례, 후기, 인용은 단 하나도 지어내지 않는다.
  숫자가 필요하면 위에서 골라 쓰고, 마땅한 게 없으면 숫자 없이 쓴다.
- "최고", "1등", "유일", "100%", "보장" 같은 표현은 쓰지 않는다 (표시광고법).
- 특정 병원·인물을 실명으로 비방하지 않는다.

# 마지막 유도(CTA)
매 글마다 넣을 필요는 없다. 넣는다면 아래 중 하나만 자연스럽게:
- 팔로우하고 매일 인사이트 받아가라
- 이번 달 무료 진단 컨설팅 남은 자리 (자리 수를 구체적으로 못 박지 말고 '몇 자리' 수준으로)
- 댓글에 특정 키워드를 남기면 디엠을 준다
- 프로필 링크에서 신청

# 네가 만들 결과물
바로 복사해서 스레드에 올릴 수 있는 완성된 글 1편.
main은 본문 전체(첫 줄이 hook), comments는 댓글로 이어 올릴 조각들이다.
설명이나 해설을 붙이지 말고 실제 올릴 텍스트만 담아라."""


def load_examples(seed: int, n: int = NUM_EXAMPLES) -> list[dict]:
    """날짜를 시드로 문체 예시를 뽑는다. 날마다 다른 조합이 들어가도록."""
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


def save_history(entry: dict, keep: int = 200) -> None:
    entries = []
    if HISTORY.exists():
        try:
            entries = json.loads(HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries.append(entry)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(
        json.dumps(entries[-keep:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_user_prompt(today: date, examples: list[dict], history: list[dict]) -> str:
    parts = ["# 몽PD가 실제로 올렸던 글 (문체 레퍼런스)"]
    for i, ex in enumerate(examples, 1):
        parts.append(f"\n--- 예시 {i} ---\n{ex['text']}")

    if history:
        parts.append("\n\n# 최근에 이미 보낸 주제 (겹치지 마라)")
        for h in reversed(history):
            parts.append(f"- [{h.get('date', '?')}] {h.get('topic', '')} / {h.get('angle', '')}")

    parts.append(
        f"\n\n# 오늘 할 일\n오늘은 {today.strftime('%Y년 %m월 %d일')}이다.\n"
        "위 문체를 그대로 살려서 오늘 올릴 스레드 글 1편을 새로 써라.\n"
        "위 예시를 베끼지 말고, 최근 보낸 주제와도 겹치지 않는 새로운 각도를 잡아라.\n"
        "훅 한 줄에 승부를 걸어라."
    )
    return "\n".join(parts)


def generate(today: date | None = None) -> DailyThread:
    today = today or date.today()
    examples = load_examples(seed=today.toordinal())
    history = load_history()

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_user_prompt(today, examples, history)}],
        output_format=DailyThread,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"모델이 생성을 거부했습니다: {response.stop_details}")

    # 기록은 메일 발송까지 성공한 뒤에 남긴다 (main.py 참고).
    # 발송이 실패했는데 주제만 소진되는 걸 막기 위해서다.
    return response.parsed_output


if __name__ == "__main__":
    result = generate()
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
