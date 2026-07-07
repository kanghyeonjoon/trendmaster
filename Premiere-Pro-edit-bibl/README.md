# Premiere Auto-Edit

**말하는 영상(롱폼·토크·라이브)을 한 줄 명령으로 러프컷까지.**
무음·추임새(아·어·음·그러니까)·말더듬을 제거하고, 음량을 유튜브 표준(-14 LUFS)으로 맞추고, 컷에 정렬된 자막까지 만들어 **프리미어에서 바로 편집 가능한 시퀀스**로 내보냅니다. 전부 **로컬 실행**(외부 업로드 없음, 윈도우/맥/리눅스).

> **TL;DR (EN):** One command turns a raw talking-head recording into an editable Premiere sequence — silence/filler/stutter removal + loudness leveling + cut-aligned subtitles, all running locally on Apple Silicon. Korean-speech tuned (Whisper).

```bash
./edit.sh "원본영상.mp4" --preset 표준
# → output/ 에 한 번에: _cut.xml (시퀀스) · _cut_audio.wav · 자막 _cut.srt/.vtt/.ass
# → 프리미어에서 파일 > 가져오기 로 .xml + 자막 불러오면 끝
```

---

## 왜?

토크형 롱폼 편집에서 시간을 가장 많이 잡아먹는 건 **무음 제거·추임새 제거·음량 맞추기·자막**입니다. 이 반복 노가다를 자동화해서, **편집자는 B롤·강조·디테일에만 집중**하게 합니다. 원본은 건드리지 않고(비파괴), 결과는 평소처럼 **자유롭게 수정 가능한 일반 시퀀스**로 들어갑니다.

### 실측 (73분 라이브 토크 기준)

| 항목 | 결과 |
|------|------|
| 원본 → 컷 | 73:50 → **67:12** (표준 약 9% 제거 — 자연스러움/어미 보존 우선, 프리셋에 따라 더 공격적) |
| 제거 대상 | 무음 · 추임새 · 어/음 망설임 · 말더듬/중복 · false-start |
| 음량 | -21.6 LUFS → **-14.0 LUFS** (유튜브 표준), 트루피크 정리 |
| 자막 | 단어 단위 전사 → 컷 타임라인 정렬 SRT/VTT/ASS |

---

## 기능

- **무음 제거** — 끝음(작게 흐리는 문장 끝)까지 살리는 민감도 조절
- **숨소리 축소** — 단어 사이 들숨/날숨(노이즈성·말소리보다 작음)을 무음처럼 줄임. 유성음(어/음)은 스펙트럼 평탄도로 구분해 **안 건드림** (기본 ON)
- **추임새는 기본 살림** — `아·어·음·뭐·그러니까` 등은 말맛이라 기본 보존. 타이트하게 빼려면 `공격` 프리셋(추임새·망설임·어/음 음향검출까지 제거)
- **말더듬·중복 제거** — 같은 말 반복 + **비슷한 말 다시하기(false-start)** 유사도 검출
- **재테이크 제거** — NG 내고 문장을 처음부터 다시 읽으면, **앞 시도 + 사이 디렉션 대화("잠시만요", "한 번만 부탁드립니다")까지 통째로** 제거하고 마지막 테이크만 남김. 강조를 위한 의도적 반복은 보존. 제거 내역은 리포트의 "재테이크" 섹션
- **음량 정리** — 압축 + -14 LUFS 노멀라이즈 (+ 옵션: 노이즈/치찰음 제거)
- **자막** — 한 줄 30자 맥락 분할, SRT/VTT/ASS(폰트·외곽선·위치 스타일)
- **프리미어 시퀀스 마커** — 재테이크 잘린 지점·디렉션 의심·컷 촘촘 구간을 타임라인 마커로 삽입. 프리미어에서 `Shift+M`으로 점프하며 바로 검토
- **자연스러움 가드** — 컷이 너무 촘촘한 구간을 자동 경고 (*"자연스러움 > 최대 제거"*)
- **안전망** — 출력 백업, 프레임 무결성 검증, 시각 HTML 리포트
- **프리셋** — `보수 / 표준 / 공격` (코드 수정 없이 `config.json`으로 세부 조절) + **영상 측정 후 프리셋 자동 추천**
- **숏폼 자동 추출** — 하이라이트 in-out → 9:16 세로 클립 (`make_shorts.py`)
- **강조 키워드 자막** — 숫자·핵심어를 색으로 강조한 ASS (`emphasis_subs.py`)
- **AI 편집 에이전트 팀** (Claude Code) — 기획·리서치·컷·자막·검수를 자동 협업

---

## 요구사항

| | |
|---|---|
| OS | **윈도우 · 맥 · 리눅스** — 자막은 faster-whisper(CPU·NVIDIA GPU) |
| 영상 편집 | **Adobe Premiere Pro 25.0+** (FCP7 XML 가져오기) |
| 런타임 | **Python 3.10+**, **ffmpeg** (ffprobe 포함) |
| 자막용 | **faster-whisper** (로컬 음성인식). NVIDIA GPU 있으면 자동 가속 |

> 이 포크는 원본의 애플 실리콘 전용 mlx-whisper를 **faster-whisper**로 교체해 **윈도우/리눅스에서도** 자막까지 전부 동작합니다. (기존 `config.json`의 `mlx-community/whisper-*` 모델 이름은 자동으로 faster-whisper 크기 이름으로 변환됩니다.)

### 설치 — 윈도우

```powershell
# 1) 받기
git clone <이 저장소 URL>
cd Premiere-Pro-edit-bibl

# 2) ffmpeg (둘 중 하나)
winget install Gyan.FFmpeg
# choco install ffmpeg

# 3) 파이썬 의존성
pip install -r requirements.txt

# 4) NVIDIA GPU 가속 (선택 — 전사가 몇 배 빨라짐. 없으면 CPU로 자동 동작)
pip install -r requirements-gpu.txt

# 실행은 edit.bat / batch.bat (아래 사용법 참고)
```

### 설치 — 맥 · 리눅스

```bash
git clone <이 저장소 URL>
cd Premiere-Pro-edit-bibl
brew install ffmpeg              # 맥 / 리눅스는 apt install ffmpeg
pip install -r requirements.txt
chmod +x edit.sh batch.sh
```

---

## 사용법

**윈도우 (`edit.bat` / `batch.bat`):**

```bat
REM 1) 기본 (표준 프리셋)
edit.bat "원본영상.mp4"

REM 2) 프리셋 선택
edit.bat "원본영상.mp4" --preset 보수
edit.bat "원본영상.mp4" --preset 공격

REM 3) 폴더 일괄 처리
batch.bat "촬영본폴더" 표준
```

**맥 · 리눅스 (`edit.sh` / `batch.sh`):**

```bash
# 1) 기본 (표준 프리셋)
./edit.sh "원본영상.mp4"

# 2) 프리셋 선택
./edit.sh "원본영상.mp4" --preset 보수   # 덜 자름 (자연스러움 우선)
./edit.sh "원본영상.mp4" --preset 공격   # 최대한 타이트 (+ 어/음 음향검출)

# 3) 폴더 일괄 처리
./batch.sh "촬영본폴더" 표준
```

**프리미어에서:**
1. `파일 > 가져오기`(윈도우 Ctrl+I / 맥 Cmd+I) → `output/..._cut.xml` 선택 → 생성된 시퀀스 더블클릭
2. 자막은 `output/..._cut.srt`(또는 `.ass`)을 가져와 타임라인에 드래그
3. (선택) 타임라인 전체 선택 → `Ctrl+Shift+D`(맥 Cmd+Shift+D) 로 모든 컷에 오디오 전환 적용

> `_cut_audio.wav`는 XML이 자동으로 끌어옵니다. `_report.html`은 브라우저로 열면 잘린 내용·자연스러움 주의 구간을 타임코드로 확인할 수 있어요.

---

## 자막 오타 잡기 — 4중 방어선

자막 오타는 발생 지점별로 4단계로 잡습니다. 위에서부터 순서대로 세팅하세요.

| 단계 | 방법 | 설정 |
|------|------|------|
| ① 예방 | 받아쓰기에 고유명사 힌트 주입 | `config.json` → `"STT_HINTS": ["리브힙의원"]` |
| ② 확정 치환 | 반복해서 틀리는 표기를 자동으로 바꿈 (조사·두어절 오인식 대응) | `config.json` → `"REPLACE_MAP": {"리뷰 의원": "리브힙의원"}` |
| ③ 대본 대조 | **촬영 대본이 있으면 최강.** 대본과 다른 표기를 자동 교정 (즉흥 구간은 안 건드림) | `edit.bat "영상.mp4" --script "대본.txt"` |
| ④ AI 검수 | Claude Code로 맞춤법·의미 단위까지 다듬기 | 아래 참고 |

- ③의 교정 내역은 `output/..._script_report.txt`와 `_report.html`의 "표기 교정" 섹션에서 확인.
- 받아쓰기 설정(모델·힌트)을 바꾸면 자동으로 재전사됩니다. 강제 재전사는 `--retranscribe`.

**④ AI 검수 (Claude Code):**
1. PC에 [Claude Code](https://claude.com/claude-code) 설치
2. 이 폴더에서 Claude Code 열기 → **"자막 교정해줘"**
3. 자막 에디터 에이전트가 `glossary.txt`(용어집)를 기준으로 고유명사·맞춤법·줄 분할을 교정 (타이밍 보존)
4. `glossary.txt`에 병원명·시술명·이름을 채워둘수록 정확해집니다

---

## 튜닝

`engine/config.py`의 프리셋, 또는 프로젝트 루트에 `config.json`(→ `config.json.example` 참고)으로 모든 값을 조절합니다.

| 키 | 의미 |
|----|------|
| `NOISE_DB` | 무음 판정 임계값. 낮출수록 작은 끝음/작은 소리를 살림 |
| `MIN_SILENCE` | 이 길이(초) 이상 조용해야 컷 |
| `FILLER_PHRASES` | 제거할 추임새 단어 목록 |
| `HESITATION_MIN` | 어/음 망설임 빈틈 최소 길이 |
| `TARGET_LUFS` | 목표 라우드니스 (유튜브 -14) |
| `DENOISE` / `DEESS` | 노이즈/치찰음 제거 (기본 OFF) |

---

## 작동 원리

프리미어를 직접 조종(UXP/API)하는 대신, **FCP7 XML(편집 가능한 시퀀스 교환 포맷)을 생성해 가져오기**하는 방식입니다. 그래서:

- **비파괴** — 원본 영상은 안 건드림. 컷은 일반 클립이라 트림·이동·복구 자유
- **안정적** — 프리미어 버전 업데이트에도 안 깨짐
- **빠름** — 분석은 ffmpeg + 로컬 Whisper, 시퀀스 생성은 즉시

```
원본 영상 ─> [파이썬 엔진]
              ├─ 무음 감지(ffmpeg) + 음량 정리(loudnorm)
              ├─ 단어 단위 전사(faster-whisper, verbatim)
              ├─ 추임새/망설임/더듬 제거 구간 계산
              └─ FCP7 XML(컷 시퀀스) + SRT(컷 정렬 자막)
                        │
                        v
            프리미어 '불러오기' ─> 편집 가능한 러프컷 + 자막
```

---

## AI 편집 에이전트 팀 (Claude Code)

[Claude Code](https://claude.com/claude-code)로 이 폴더를 열고 **"이 영상 편집해줘"** 하면, 5개 전문 에이전트가 협업해 기획~검수까지 자동 수행합니다:

| 에이전트 | 역할 |
|---------|------|
| 편집 디렉터 | 방향 설정 · 검수 · 핸드오프 |
| 콘텐츠 리서처 | 핵심 메시지 · 하이라이트 · 삭제구간 · 챕터 · 제목 후보 |
| 영상 기획자 | 인트로 훅 · 흐름 · 강조/B롤 마커 |
| 컷편집가 | 엔진 운용 · 결과 검증 |
| 자막 에디터 | 고유명사 교정 · 가독성 |
| 숏폼 PD | 핵심 기반 1분 쇼츠(9:16) 5개 자동 제작 |

`.claude/agents/`, `.claude/skills/`에 정의돼 있습니다.

---

## [주의] 한계

- 프리미어 프로 **25.0+** 필요 (FCP7 XML 가져오기). 자막은 faster-whisper 사용(NVIDIA GPU 있으면 자동 가속, 없으면 CPU)
- **한국어 발화 최적화** (추임새 목록·Whisper 프롬프트가 한국어 기준 — 다른 언어는 목록 교체 필요)
- 단일 카메라 토크형 기준. 멀티캠/VFR은 미지원
- 어/음 일부는 어떤 Whisper 모델로도 텍스트로 안 잡혀, 음향 검출(옵션)로 보조

---

## 라이선스

[MIT](LICENSE) — 자유롭게 쓰고 고치고 배포하세요. PR 환영합니다.
