# 매일 아침 7시 스레드 발송기

매일 오전 7시(KST) 몽PD 문체로 쓴 스레드 글 1편을 이메일로 보낸다.
대행사가 카톡으로 매일 아침 글을 전달해주던 방식을 그대로 자동화한 것이다.

## 어떻게 돌아가나

```
GitHub Actions (매일 22:00 UTC = 07:00 KST)
  └─ main.py
       ├─ generate.py  아카이브 168편을 문체 레퍼런스로 Claude가 새 글 작성
       ├─ send_email.py  본문 / 댓글 1..n / CTA로 나눠 지메일 발송
       └─ state/history.json  발송한 주제를 기록해 다음 날 중복을 피함
```

- **글은 매일 새로 쓴다.** 아카이브를 재활용하지 않는다. 아카이브는 문체·주제·구조를
  학습시키는 레퍼런스로만 쓰이고, 날마다 다른 8편이 예시로 들어간다.
- **중복을 피한다.** 최근 30일치 주제와 각도를 프롬프트에 넣어 같은 얘기를 반복하지 않는다.
- **실패해도 침묵하지 않는다.** 3회 재시도 후에도 실패하면 실패 알림 메일이 온다.

## 설정 (최초 1회)

### 1. GitHub Secrets 등록

저장소 **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com 에서 발급 |
| `GMAIL_USER` | 보내는 지메일 주소 |
| `GMAIL_APP_PASSWORD` | 지메일 **앱 비밀번호** (아래 참고) |
| `MAIL_TO` | 받는 주소. 생략하면 `GMAIL_USER`로 보냄 |

### 2. 지메일 앱 비밀번호 만들기

계정 비밀번호로는 SMTP 로그인이 안 된다. 앱 비밀번호가 따로 필요하다.

1. Google 계정 → 보안 → **2단계 인증**을 켠다 (안 켜져 있으면 앱 비밀번호 메뉴가 안 보인다)
2. https://myaccount.google.com/apppasswords 접속
3. 앱 이름을 아무거나 (예: `트렌드마스터`) 입력하고 생성
4. 나오는 16자리를 공백 없이 `GMAIL_APP_PASSWORD`에 넣는다

### 3. 동작 확인

저장소 **Actions → 매일 아침 스레드 발송 → Run workflow**

- 먼저 `dry_run`을 켜고 실행하면 메일 없이 로그로 결과만 확인할 수 있다
- 그대로 실행하면 지금 바로 한 편이 메일로 온다

## 손으로 돌려보기

```bash
pip install -r threads_daily/requirements.txt
export ANTHROPIC_API_KEY=...
export GMAIL_USER=... GMAIL_APP_PASSWORD=... MAIL_TO=...

python threads_daily/main.py --dry-run    # 생성만, 발송 안 함
python threads_daily/main.py --test-mail  # 샘플 메일만, Claude 호출 안 함
python threads_daily/main.py              # 실제 발송
```

## 글 스타일을 바꾸고 싶을 때

`generate.py`의 `SYSTEM` 프롬프트를 고치면 된다. 주요 구획:

| 구획 | 내용 |
|---|---|
| 몽PD가 누구인가 | 페르소나, 타깃 독자, 파는 것 |
| 반복해서 쓰는 개념 | 부하율, 낚싯대 이론, 검색/탐색 기반 등 8가지 |
| 문체 규칙 | 줄바꿈, 어투, 댓글 분리, 금지 표현 |
| 절대 지켜야 할 사실 관계 | **검증된 실적 목록** |
| 마지막 유도(CTA) | 팔로우 / 무료 진단 / 댓글 키워드 / 프로필 링크 |

### 실적 숫자가 바뀌면 반드시 여기를 고쳐라

`SYSTEM`의 "절대 지켜야 할 사실 관계"에 적힌 숫자가 **모델이 쓸 수 있는 전부**다.
목록에 없는 수치·후기·사례는 지어내지 못하게 막아뒀다. `docs/CONTENT-TODO.md`의
운영 원칙(가짜 숫자 금지, "최고/1등/유일/100%/보장" 금지 — 표시광고법)을 그대로 옮긴 것이니,
새 성과가 생기면 목록에 **추가**하고 낡은 숫자는 지워라.

## 아카이브 갱신

새 글이 쌓이면 `data/archive.txt` 뒤에 이어 붙이고 (글 사이는 `-----` 구분선) 다시 파싱한다.

```bash
python threads_daily/build_corpus.py
```

## 발송 시각 바꾸기

`.github/workflows/daily-thread.yml`의 cron은 **UTC 기준**이다. 한국 시간에서 9를 빼면 된다.

| 원하는 시각 (KST) | cron |
|---|---|
| 오전 7시 | `0 22 * * *` |
| 오전 8시 | `0 23 * * *` |
| 오후 7시 | `0 10 * * *` |

GitHub Actions의 예약 실행은 러너가 붐비면 몇 분에서 십여 분 늦게 시작될 수 있다.
정확히 7시 00분에 도착해야 한다면 cron을 `30 21 * * *`처럼 조금 앞당겨 두면 된다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `main.py` | 오케스트레이션. 재시도, 실패 알림, 기록 저장 |
| `generate.py` | 프롬프트 조립 + Claude 호출 (`claude-opus-5`, 구조화 출력) |
| `send_email.py` | 텍스트/HTML 메일 렌더링 + Gmail SMTP 발송 |
| `build_corpus.py` | `archive.txt` → `posts.json` 파싱 |
| `data/archive.txt` | 스레드 원문 아카이브 (이미 발행된 글) |
| `data/posts.json` | 파싱 결과 168편 |
| `state/history.json` | 발송 기록. 워크플로가 매일 커밋한다 |
