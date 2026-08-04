"""매일 아침 7시(KST) 오늘의 스레드 글을 만들어 메일로 보낸다.

    python threads_daily/main.py            # 생성 + 발송
    python threads_daily/main.py --dry-run  # 생성만 하고 화면에 출력
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import generate as gen
import send_email

KST = ZoneInfo("Asia/Seoul")
MAX_ATTEMPTS = 3
RETRY_DELAYS = [20, 60]  # 초


def generate_with_retry(today):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return gen.generate(today)
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 아침에 알려야 한다
            last_error = exc
            print(f"생성 실패 ({attempt}/{MAX_ATTEMPTS}): {exc!r}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAYS[attempt - 1])
    raise last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="메일을 보내지 않고 생성 결과만 출력한다",
    )
    parser.add_argument(
        "--test-mail",
        action="store_true",
        help="Claude를 호출하지 않고 샘플 메일만 보낸다 (지메일 설정 확인용)",
    )
    args = parser.parse_args()

    today = datetime.now(KST).date()

    if args.test_mail:
        send_email.send(
            subject=f"[{today.strftime('%m/%d')} 스레드] 발송 설정 테스트",
            text_body="이 메일이 도착했다면 지메일 설정이 정상입니다.\n"
            "내일 아침 7시부터 오늘의 스레드가 이 주소로 옵니다.",
        )
        return 0

    print(f"오늘({today.isoformat()}, KST) 글 생성 시작")

    try:
        thread = generate_with_retry(today)
    except Exception as exc:  # noqa: BLE001
        if args.dry_run:
            raise
        send_email.send_failure(today, f"{type(exc).__name__}: {exc}")
        return 1

    if args.dry_run:
        print(json.dumps(thread.model_dump(), ensure_ascii=False, indent=2))
        print("\n" + "=" * 40 + "\n")
        print(send_email.render_text(thread, today))
        return 0

    send_email.send_thread(thread, today)
    gen.save_history(
        {
            "date": today.isoformat(),
            "topic": thread.topic,
            "angle": thread.angle,
            "hook": thread.hook,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
