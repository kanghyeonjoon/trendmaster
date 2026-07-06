#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
script_align.py — 받아쓰기(words) 사후 교정 2종

① apply_replace_map(words, rmap)
   용어사전 확정 치환. 병원명·브랜드처럼 Whisper가 반복해서 틀리는 표기를
   결정적으로 고친다. 한국어 조사가 붙은 형태("리뷰 의원이")와 두 어절에
   걸친 오인식("리뷰 의원")을 모두 잡고, 병합 시 타임스탬프는
   (첫 단어 start, 끝 단어 end)로 합친다.

② correct(words, script_toks)
   대본 대조 교정. 2단계 앵커 정렬:
   - 1단계: 어절 단위 SequenceMatcher — 연속 anchor_min(기본 3)어절
     exact 일치 구간을 앵커로 잡는다.
   - 2단계: 앵커 '사이' 구간만 어절쌍 유사도(음절 SequenceMatcher,
     autojunk=False 필수 — 한국어 고빈도 음절이 junk 처리되는 함정)로
     단조 정렬해, 유사도 ≥ ratio_min 인 어절만 대본 표기로 치환한다.
   앵커 밖(첫 앵커 이전·마지막 앵커 이후 = 즉흥 발화)은 손대지 않고,
   전체 앵커 커버리지가 낮으면(기본 30% 미만) 전체를 건너뛴다.
   타임스탬프는 절대 바꾸지 않는다.
"""

import os, re, unicodedata
from difflib import SequenceMatcher

# 어절 끝에 붙을 수 있는 조사(용어사전 치환용 화이트리스트).
# 임의 접미를 허용하면 "리뷰의원회" 같은 다른 단어까지 오치환하므로 제한한다.
JOSA_DEFAULT = (
    "이 가 을 를 은 는 의 에 에서 으로 로 과 와 랑 이랑 도 만 까지 부터 처럼 보다 "
    "한테 에게 께 요 이요 예요 이에요 입니다 이라 이라고 라고 이라는 라는 이란 란 "
    "이든 든 이나 나 마다 조차 마저 밖에 뿐"
).split()

_PUNCT = "\"'”“‘’(),.…?!~"


def _core(tok):
    """어절에서 앞뒤 문장부호를 뗀 알맹이."""
    return tok.strip().strip(_PUNCT)


def _trail(tok):
    """어절 끝의 문장부호(쉼표 등 — 자막 줄바꿈 근거라 보존)."""
    t = tok.strip()
    i = len(t)
    while i > 0 and t[i - 1] in _PUNCT:
        i -= 1
    return t[i:]


def _sim(a, b):
    """자모 단위 유사도 (autojunk=False 필수).
    음절 그대로 비교하면 '세/셀'처럼 받침 하나 차이도 통째로 불일치로 계산돼
    1음절 오인식(세레늄→셀레늄)이 임계값을 못 넘는다 → NFD로 자모 분해 후 비교."""
    na = unicodedata.normalize("NFD", a)
    nb = unicodedata.normalize("NFD", b)
    return SequenceMatcher(None, na, nb, autojunk=False).ratio()


# ─────────────────────────────────────────────────────────────
# ① 용어사전 확정 치환
# ─────────────────────────────────────────────────────────────

def apply_replace_map(words, rmap, josa=None, max_span=4):
    """words: [(start,end,text)] → (치환된 words, 로그 [(t, old, new)]).
    rmap 예: {"리뷰 의원": "리브힙의원"}  (키의 공백은 무시하고 매칭)"""
    if not rmap:
        return list(words), []
    josa = set(josa) if josa else set(JOSA_DEFAULT)
    # 긴 키 우선 (겹치는 키 방어)
    keys = sorted(rmap.items(), key=lambda kv: -len(kv[0].replace(" ", "")))
    out, log = [], []
    i, n = 0, len(words)
    while i < n:
        hit = None
        for key, rep in keys:
            kc = key.replace(" ", "")
            acc = ""
            for j in range(i, min(n, i + max_span)):
                acc += _core(words[j][2])
                if len(acc) > len(kc) + 4:
                    break
                if acc == kc:
                    hit = (j, rep, "")
                    break
                if acc.startswith(kc):
                    suf = acc[len(kc):]
                    if suf in josa:
                        hit = (j, rep, suf)
                        break
            if hit:
                break
        if hit:
            j, rep, suf = hit
            new_text = rep + suf + _trail(words[j][2])
            out.append((words[i][0], words[j][1], new_text))   # 시각 병합: 첫 start ~ 끝 end
            log.append((words[i][0], " ".join(w[2] for w in words[i:j + 1]), new_text))
            i = j + 1
        else:
            out.append(tuple(words[i]))
            i += 1
    return out, log


# ─────────────────────────────────────────────────────────────
# ② 대본 대조 교정
# ─────────────────────────────────────────────────────────────

def load_script(path):
    """대본 파일 → 어절 토큰 리스트 (빈 줄·공백 정리)."""
    text = open(path, encoding="utf-8").read()
    return [t for t in re.split(r"\s+", text) if _core(t)]


def find_anchors(stt_cores, script_cores, anchor_min=3):
    """연속 anchor_min 어절 이상 exact 일치 블록 → [(i, j, n)] (stt i, script j, 길이 n)."""
    sm = SequenceMatcher(None, stt_cores, script_cores, autojunk=False)
    return [(b.a, b.b, b.size) for b in sm.get_matching_blocks() if b.size >= anchor_min]


def _align_gap(stt_gap, script_gap, ratio_min, fix_endings):
    """앵커 사이 구간 단조 정렬(DP) → [(stt_idx_in_gap, new_core, ratio)].
    stt_gap: [(원본 인덱스, core)], script_gap: [core]"""
    la, lb = len(stt_gap), len(script_gap)
    if la == 0 or lb == 0:
        return []
    # 유사도 행렬 + 단조 정렬 (Needleman-Wunsch, gap 페널티 소량)
    GAP = -0.05
    score = [[0.0] * (lb + 1) for _ in range(la + 1)]
    move = [[0] * (lb + 1) for _ in range(la + 1)]   # 1=대각 2=위(stt스킵) 3=왼쪽(대본스킵)
    for i in range(1, la + 1):
        score[i][0] = score[i - 1][0] + GAP; move[i][0] = 2
    for j in range(1, lb + 1):
        score[0][j] = score[0][j - 1] + GAP; move[0][j] = 3
    sims = {}
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            s = _sim(stt_gap[i - 1][1], script_gap[j - 1])
            sims[(i, j)] = s
            best = (score[i - 1][j - 1] + s, 1)
            up = (score[i - 1][j] + GAP, 2)
            left = (score[i][j - 1] + GAP, 3)
            score[i][j], move[i][j] = max(best, up, left)
    # 역추적 → 대각 이동 중 유사도 임계 통과만 채택
    fixes = []
    i, j = la, lb
    while i > 0 or j > 0:
        m = move[i][j]
        if m == 1:
            a_core = stt_gap[i - 1][1]; b_core = script_gap[j - 1]
            r = sims[(i, j)]
            if a_core != b_core and r >= ratio_min:
                if fix_endings or not _ending_only_diff(a_core, b_core):
                    fixes.append((stt_gap[i - 1][0], b_core, r))
            i, j = i - 1, j - 1
        elif m == 2:
            i -= 1
        else:
            j -= 1
    fixes.reverse()
    return fixes


def _ending_only_diff(a, b):
    """조사/어미 차이만 있는지 — 발화 존중을 위해 기본은 안 고침.
    어미/조사 차이는 어간(앞)이 같고 '끝만' 다르다(공통 접미사 없음).
    오인식은 중간 음절이 다르고 끝(조사)은 다시 일치한다(공통 접미사 있음).
    예) 목적이/목적은·자연스럽게/자연스러운 → 어미 차이(안 고침)
        레이져를/레이저를·콜라건이/콜라겐이 → 중간 오인식(고침)"""
    la, lb = len(a), len(b)
    p = 0
    for x, y in zip(a, b):
        if x != y:
            break
        p += 1
    if p < 2 or p == min(la, lb) == max(la, lb):   # 접두 2음절 미만이거나 완전 동일
        return p >= 2
    s = 0
    while s < min(la, lb) - p and a[la - 1 - s] == b[lb - 1 - s]:
        s += 1
    return s == 0 and (la - p) <= 2 and (lb - p) <= 2


def correct(words, script_toks, ratio_min=0.8, anchor_min=3, gap_max=30,
            min_coverage=0.30, fix_endings=False):
    """대본 대조 교정. → (교정된 words, 로그 [(t, old, new, ratio)], 커버리지 0~1).
    words 길이·타임스탬프 불변. 커버리지가 min_coverage 미만이면 아무것도 안 바꿈."""
    stt_cores = [_core(w[2]) for w in words]
    script_cores = [_core(t) for t in script_toks]
    if not stt_cores or not script_cores:
        return list(words), [], 0.0

    anchors = find_anchors(stt_cores, script_cores, anchor_min)
    covered = sum(n for _, _, n in anchors)
    coverage = covered / len(stt_cores)
    if not anchors or coverage < min_coverage:
        return list(words), [], coverage

    fixes = []   # (words 인덱스, 새 core, ratio)
    for k in range(len(anchors) - 1):
        ai, aj, an = anchors[k]
        bi, bj, _ = anchors[k + 1]
        g0, g1 = ai + an, bi           # stt 갭 [g0, g1)
        h0, h1 = aj + an, bj           # 대본 갭 [h0, h1)
        sg, tg = g1 - g0, h1 - h0
        if sg == 0 or tg == 0:                    # 대본에 없는 즉흥 삽입 → no-touch
            continue
        if sg > gap_max or tg > gap_max:          # 너무 긴 갭은 신뢰 불가
            continue
        if not (0.5 <= sg / tg <= 2.0):           # 길이 불균형 → 다른 내용일 가능성
            continue
        stt_gap = [(g0 + x, stt_cores[g0 + x]) for x in range(sg)]
        script_gap = [script_cores[h0 + x] for x in range(tg)]
        fixes += _align_gap(stt_gap, script_gap, ratio_min, fix_endings)

    out, log = list(words), []
    for idx, new_core, r in fixes:
        s, e, old = out[idx]
        new_text = new_core + _trail(old)          # 쉼표 등 원래 문장부호 보존
        if _core(old) != new_core:
            out[idx] = (s, e, new_text)
            log.append((s, old, new_text, round(r, 3)))
    return out, log, coverage


def write_report(path, replace_log, script_log, coverage):
    """교정 내역 리포트 (비개발자 검수용)."""
    def hms(t):
        m, s = divmod(int(t), 60)
        return f"{m:02d}:{s:02d}"
    with open(path, "w", encoding="utf-8") as f:
        f.write("자막 교정 리포트\n================\n\n")
        f.write(f"[용어사전 치환] {len(replace_log)}건\n")
        for t, old, new in replace_log:
            f.write(f"  {hms(t)}  {old}  →  {new}\n")
        f.write(f"\n[대본 대조 교정] {len(script_log)}건 (대본 일치율 {coverage*100:.0f}%)\n")
        for t, old, new, r in script_log:
            f.write(f"  {hms(t)}  {old}  →  {new}  (유사도 {r})\n")
