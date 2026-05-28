# Calendar Agent - Claude Code MCP 서버 설정 가이드

Claude Code에서 "팀 회의 다음주 화요일 3시에 잡아줘" 한마디로 Google Calendar에 자동 등록됩니다.
추가 Claude API 비용 없음 - Claude Code 구독만으로 동작합니다.

---

## 1단계: Google Cloud 인증 설정 (5분, 무료)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 (또는 기존 프로젝트 사용)
3. **API 및 서비스 > 라이브러리** → "Google Calendar API" 검색 후 활성화
4. **API 및 서비스 > 사용자 인증 정보**
   - "사용자 인증 정보 만들기" → "OAuth 클라이언트 ID"
   - 애플리케이션 유형: **데스크톱 앱**
   - 생성 후 **JSON 다운로드**
5. 다운로드한 파일을 `calendar-agent/credentials.json` 으로 저장

---

## 2단계: 패키지 설치

```bash
cd calendar-agent
pip install -r requirements.txt
```

---

## 3단계: 최초 인증 (1회만)

```bash
python server.py
```

브라우저가 열리면 Google 계정으로 로그인 → 권한 허용
→ `token.json` 자동 생성됨 (이후 자동 갱신)

---

## 4단계: Claude Code에 MCP 서버 등록

`~/.claude/settings.json` 에 추가:

```json
{
  "mcpServers": {
    "calendar": {
      "command": "python",
      "args": ["/절대경로/calendar-agent/server.py"],
      "env": {
        "TIMEZONE": "Asia/Seoul",
        "CALENDAR_ID": "primary"
      }
    }
  }
}
```

> `CALENDAR_ID`: `primary` = 기본 캘린더, 다른 캘린더는 Google Calendar에서 캘린더 ID 확인

---

## 사용 예시

Claude Code에서 그냥 말하면 됩니다:

```
다음주 화요일 오후 3시에 팀 회의 2시간으로 잡아줘
```

```
이번주 일정 보여줘
```

```
내일 오전 10시에 치과 예약 잡아주고 1시간으로 해줘, 장소는 강남역 치과
```

```
방금 잡은 치과 예약 취소해줘
```

---

## 비용 구조

| 항목 | 비용 |
|------|------|
| Claude Code 구독 | 이미 지불 중 |
| Google Calendar API | **무료** (일반 사용량 기준) |
| 추가 Claude API 비용 | **없음** |

---

## 파일 구조

```
calendar-agent/
├── server.py          # MCP 서버 메인
├── requirements.txt   # Python 패키지
├── credentials.json   # Google OAuth (직접 추가 필요, git 제외)
├── token.json         # 자동 생성, git 제외
└── setup_guide.md     # 이 파일
```

> `credentials.json`, `token.json` 은 절대 git에 올리지 마세요.
