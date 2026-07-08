# Premiere Pro 자동 편집 프로젝트

## 하네스: 비블 유튜브 영상 편집

**목표:** 원본 영상 1개 → 기획·리서치·컷편집·자막·검수를 전문 에이전트 팀으로 처리해 프리미어 핸드오프까지 자동화.

**트리거:** 비블 영상 편집 전반(기획~자막~쇼츠) 요청 시 `video-edit-pipeline` 스킬을 사용하라. 단일 작업은 전문 스킬 직접 호출 가능 — 컷편집만=`cut-editing`, 자막만=`subtitle-editing`, 리서치만=`content-research`, 기획만=`video-planning`, 검수만=`edit-direction`, 쇼츠만=`shorts-production`. 단순 질문은 직접 응답.

**핵심 엔진:** `engine/auto_cut.py` (= `./edit.sh "영상.mp4" --preset 보수|표준|공격`). 무음·추임새·말더듬 제거 + -14 LUFS 음량정리 + 컷정렬 자막을 한 번에 생성. 설정은 `engine/config.py`(프리셋) + `config.json`(사용자 override). 개선 계획은 `ROADMAP.md`.

**로컬 실행 수칙 (중요):** 사용자는 비개발자다. 환경 문제(GPU 미가속, 패키지 누락, ffmpeg 부재, 구버전 코드)는 **사용자에게 터미널 명령을 시키지 말고 네가 직접 해결**하라:
- 편집 시작 전 `python engine/doctor.py`로 환경 점검. [문제]가 있으면 직접 고친 뒤 진행
- 전사 출력에 "CPU로 전사합니다 (느림)"가 보이고 `nvidia-smi`가 존재하면 → `pip install -r requirements-gpu.txt` 실행 후 재시도
- 작업 시작 전 `git pull`로 최신 코드 확인 (엔진이 계속 개선되고 있음)
- 긴 영상(10분+)의 첫 전사는 GPU로도 수 분 걸림 — 시작 전에 사용자에게 예상 시간을 알려줄 것
- 실패 시 `output/_last_error.log`를 읽고 원인을 직접 진단

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-14 | 초기 구성 (에이전트 5 + 스킬 6) | 전체 | 영상 편집 워크플로우 자동화 |
| 2026-06-14 | 설정 프리셋 + 버린컷/백업/검증 + 자연스러움 가드 | engine, config | 로드맵 Task1·3 |
| 2026-06-14 | 제1원칙 '자연스러움 > 최대 제거' 격상 | edit-director, cut-editing | 비블 피드백 |
| 2026-06-14 | 자막 한줄30자+Pretendard Bold 스타일, 어/음 음향검출, 오디오후처리, 문맥필러+false-start, 전사export, 배치, HTML리포트 | engine 전반 | 로드맵 Task5~10 |
| 2026-06-14 | 에이전트 5팀 전용도구 — analyze_video(프리셋추천)·make_shorts(9:16)·emphasis_subs(강조자막) + 스킬 강화(리텐션·정량검수) | engine, .claude | 에이전트별 디벨롭 |
| 2026-06-14 | 끊김(클릭) 개선(비대칭패딩·미세컷절제·오디오페이드) + 숏폼 PD 에이전트(1분 쇼츠 5개 자동) | engine, .claude | 끊김 피드백 + 쇼츠 자동화 |
| 2026-07-06 | 윈도우 이식 (faster-whisper·경로URL·cp949·GPU 폴백) + 회전/다중스트림/가짜fps 대응 + 세로영상 자막 한줄·자연 줄바꿈 | engine 전반, .bat | 윈도우 실사용 버그 |
| 2026-07-06 | 자막 정확도 4중 방어선 — STT_HINTS·REPLACE_MAP·대본대조교정(script_align, --script)·VAD환청억제 + 캐시 지문화 + 에러가드/doctor + 쇼츠 세로크롭 | engine, config, check.bat | 오타 제로 기획서 1~3차 |
| 2026-07-07 | 프리미어 시퀀스 마커(재테이크/디렉션 의심/컷 촘촘) + 디렉션 표현 감지(표시만) | silence_cut, auto_cut, 리포트 | 타임라인에서 바로 점프 검토 |
| 2026-07-07 | 재테이크 자동 제거(find_retakes) — 3어절 앵커 + 연장매칭으로 NG구간(앞 시도+디렉션 대화) 제거, 마지막 테이크만. 실촬영 17.5분에서 NG 9곳/188초 검증 | auto_cut, config, 리포트 | 인터뷰형 촬영 NG 수작업 제거 부담 |
