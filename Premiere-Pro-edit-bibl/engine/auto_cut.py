#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_cut.py — 통합 자동 편집 엔진
  무음 제거 + 추임새/망설임/더듬 제거 + 음량 정리 + 자막 을 한 번에.

사용:
  python3 auto_cut.py "<원본영상.mp4>" [--preset 보수|표준|공격]

설정은 engine/config.py(프리셋) + 프로젝트 루트 config.json(사용자)에서 관리.
원본은 건드리지 않음(비파괴). 불러온 시퀀스는 전부 수정 가능.
"""

import sys, os, json, difflib, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 한국어 윈도우 콘솔(cp949)에서도 출력이 크래시하지 않게 — 표시 불가 문자는 ?로.
# (edit.bat이 UTF-8을 강제하지만, python을 직접 실행하는 경우의 안전망)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

import silence_cut as SC
from silence_cut import (probe_media, detect_silence, keep_ranges_from_silence,
                         make_clean_audio, build_fcp7_xml, measure_loudness,
                         compute_gain_db, fmt)
from make_subtitles import (transcribe, build_mapper, regroup, write_srt, srt_time)
import config as CONFIG

CFG = {}   # main()에서 config.load 결과로 채움


def norm(tok):
    return tok.strip(" .,!?…·\"'`~\n\t")


def is_filler(tok):
    t = norm(tok)
    if not t:
        return False
    if t in set(CFG["FILLER_PHRASES"]):
        return True
    sounds = set(CFG["FILLER_SOUND_CHARS"])
    if len(t) == 1 and t in sounds:
        return True
    if len(t) >= 2 and len(set(t)) == 1 and t[0] in sounds:
        return True
    return False


# '좀'이 '조금'의 뜻으로 쓰일 때(좀 더/좀 많이/좀 빨리…) 뒤에 오는 정도 표현
DEGREE_STEMS = ("더", "덜", "많", "적", "크", "작", "빨", "천천", "일찍", "늦",
                "높", "낮", "자주", "오래", "길", "짧", "세게", "약하", "쉽",
                "어렵", "멀", "가까", "느리", "조용", "급")


def keep_filler_in_context(i, sw):
    """문맥상 살려야 할 필러면 True. 지금은 '좀=조금' 케이스."""
    if not CFG.get("CONTEXT_FILLER"):
        return False
    t = norm(sw[i][2])
    if t == "좀" and i + 1 < len(sw):
        nxt = norm(sw[i + 1][2])
        if nxt.startswith(DEGREE_STEMS):     # "좀 더", "좀 많이", "좀 빨리" → 의미 있음
            return True
    return False


def find_repeats(sw):
    """말 더듬기·중복 감지. 반복된 앞 시도를 제거하고 마지막만 남긴다."""
    gap_max = CFG["REPEAT_GAP"]
    pad = CFG["FILLER_PAD"]
    toks = [norm(t) for (_, _, t) in sw]
    n = len(sw)
    removed = [False] * n
    def gap(i):
        return sw[i + 1][0] - sw[i][1]

    i = 0
    while i < n:                                   # A) 같은 단어 연속 반복
        j = i
        while j + 1 < n and toks[j + 1] and toks[j + 1] == toks[i] and gap(j) <= gap_max:
            j += 1
        if j > i:
            for k in range(i, j):
                removed[k] = True
        i = j + 1

    for i in range(n - 1):                          # B) 더듬 조각 "그"→"그게"
        if removed[i] or removed[i + 1]:
            continue
        a, b = toks[i], toks[i + 1]
        if a and b and a != b and len(a) <= 2 and b.startswith(a) and gap(i) <= gap_max:
            removed[i] = True

    for k in (3, 2):                                # C) 여러 단어 통째 반복
        i = 0
        while i + 2 * k <= n:
            if any(removed[i:i + 2 * k]):
                i += 1; continue
            s1, s2 = toks[i:i + k], toks[i + k:i + 2 * k]
            inner = sw[i + k][0] - sw[i + k - 1][1]
            if all(s1) and s1 == s2 and inner <= gap_max:
                for x in range(i, i + k):
                    removed[x] = True
                i += 2 * k
            else:
                i += 1

    # D) false-start: '비슷한 말 다시하기' (정확 일치 아님) → 유사도로 앞 시도 제거
    if CFG.get("FUZZY_REPEAT"):
        ratio_min = CFG.get("FUZZY_RATIO", 0.7)
        for k in (3, 2):
            i = 0
            while i + 2 * k <= n:
                if any(removed[i:i + 2 * k]):
                    i += 1; continue
                a = "".join(toks[i:i + k]); b = "".join(toks[i + k:i + 2 * k])
                inner = sw[i + k][0] - sw[i + k - 1][1]
                if a and b and a != b and len(a) >= 2 and inner <= gap_max \
                        and difflib.SequenceMatcher(None, a, b).ratio() >= ratio_min:
                    for x in range(i, i + k):
                        removed[x] = True
                    i += 2 * k
                else:
                    i += 1

    ranges, rep = [], []
    i = 0
    while i < n:
        if removed[i]:
            j = i
            while j + 1 < n and removed[j + 1]:
                j += 1
            s, e = sw[i][0], sw[j][1]
            ranges.append([max(0.0, s - pad), e + pad])
            rep.append((s, e, " ".join(sw[x][2] for x in range(i, j + 1))))
            i = j + 1
        else:
            i += 1
    return ranges, rep


def find_retakes(sw):
    """전체 재테이크 감지 — 문장을 말하다 틀리고(NG) 잠시 후 처음부터 다시 말한 경우,
    앞 시도(+사이 잡담·디렉션: '잠시만요', '한 번만 부탁드립니다' 등)를 제거하고
    마지막 테이크만 남긴다. find_repeats(2~3어절 즉시 반복)보다 긴 단위를 다룬다.

    판정: 같은 3어절 지점이 시간창 안에 다시 나타나고(앵커), 그 앵커에서부터
          RETAKE_MIN_MATCH 어절 이상을 이어서 다시 말했으면 재테이크.
          (앞 구간 전체와 비교하지 않으므로, 테이크 사이에 디렉션 대화가
           길어도 희석되지 않는다 — 인터뷰형 촬영 대응)
    가드: 재시작 직전 호흡(RETAKE_PAUSE)이 없으면 '강조를 위한 의도적 반복'으로
          보고 건드리지 않는다."""
    min_len   = CFG.get("RETAKE_MIN_TOKENS", 4)     # 두 시도 사이 최소 어절 거리
    max_len   = CFG.get("RETAKE_MAX_TOKENS", 60)    # 최대 어절 거리(잡담 포함 NG 구간)
    window_s  = CFG.get("RETAKE_WINDOW", 60.0)      # 두 시도 시작점 사이 최대 시간
    pause_min = CFG.get("RETAKE_PAUSE", 0.4)
    min_match = CFG.get("RETAKE_MIN_MATCH", 5)      # 앵커부터 이 어절 수 이상 재발화
    sim_min   = CFG.get("RETAKE_TOKEN_SIM", 0.75)   # 어절쌍 인정 유사도(자모)
    pad = CFG["FILLER_PAD"]

    from script_align import _sim as jamo_sim
    toks = [norm(t) for (_, _, t) in sw]
    n = len(sw)
    from collections import defaultdict
    tri = defaultdict(list)
    for i in range(n - 2):
        if toks[i] and toks[i + 1] and toks[i + 2]:
            tri[(toks[i], toks[i + 1], toks[i + 2])].append(i)

    def match_len(i, j):
        """앵커 (i,j)에서 나란히 걸으며 재발화가 몇 어절 이어지는지 (2연속 불일치면 중단)."""
        k = matched = misses = 0
        while i + k < j and j + k < n:
            a, b = toks[i + k], toks[j + k]
            if a == b or jamo_sim(a, b) >= sim_min:
                matched += 1; misses = 0
            else:
                misses += 1
                if misses >= 2:
                    break
            k += 1
        return matched

    candidates = []
    for positions in tri.values():
        for a in range(len(positions) - 1):
            i, j = positions[a], positions[a + 1]   # 연속 등장 쌍 → 다중 테이크는 연쇄 처리
            L = j - i
            if L < min_len or L > max_len:
                continue
            if sw[j][0] - sw[i][0] > window_s:
                continue
            if sw[j][0] - sw[j - 1][1] < pause_min:  # 호흡 없이 이어 말함 → 강조 반복
                continue
            if match_len(i, j) >= min_match:
                candidates.append((i, j))

    removed = [False] * n
    ranges, log = [], []
    for i, j in sorted(candidates):                  # 이른(문장 시작) 앵커 우선
        if any(removed[i:j]):
            continue
        for x in range(i, j):
            removed[x] = True
        s, e = sw[i][0], sw[j - 1][1]
        ranges.append([max(0.0, s - pad), e + pad])
        log.append((s, e, " ".join(sw[x][2] for x in range(i, j))))
    return ranges, log


def merge_ranges(ranges):
    ranges = sorted(ranges)
    out = []
    for a, b in ranges:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(keeps, removes):
    """keeps 구간에서 removes 구간을 빼서 잘게 쪼갠다."""
    removes = merge_ranges(removes)
    min_keep = CFG["MIN_KEEP"]
    out = []
    for a, b in keeps:
        segs = [(a, b)]
        for c, d in removes:
            new = []
            for s, e in segs:
                if d <= s or c >= e:
                    new.append((s, e))
                else:
                    if c > s:
                        new.append((s, min(c, e)))
                    if d < e:
                        new.append((max(d, s), e))
            segs = new
        out.extend(segs)
    return [(s, e) for s, e in out if e - s >= min_keep]


def complement(keeps, total):
    """keeps의 여집합 = 제거된 구간(버린 컷용)."""
    keeps = sorted(keeps)
    out = []
    cur = 0.0
    for a, b in keeps:
        if a > cur:
            out.append((cur, a))
        cur = max(cur, b)
    if cur < total:
        out.append((cur, total))
    return [(a, b) for a, b in out if b - a > 0.02]


def backup_outputs(outdir, base):
    """덮어쓰기 전 이전 결과(가벼운 것만)를 _backup/타임스탬프/ 로 보관. WAV는 제외(용량)."""
    import datetime, shutil
    names = [base + s for s in ["_cut.xml", "_cut.srt", "_cut_report.txt",
                                "_words.json", "_rejected.xml"]]
    existing = [n for n in names if os.path.exists(os.path.join(outdir, n))]
    if not existing:
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(outdir, "_backup", ts)
    os.makedirs(bdir, exist_ok=True)
    for n in existing:
        shutil.copy2(os.path.join(outdir, n), os.path.join(bdir, n))
    return bdir


def verify_keeps(keeps):
    """컷 구간의 길이오류/겹침을 검사. 정상이면 빈 리스트."""
    issues = []
    prev = None
    for idx, (a, b) in enumerate(keeps):
        if b <= a:
            issues.append(f"길이오류 #{idx}: {a:.3f}~{b:.3f}")
        if prev is not None and a < prev - 1e-6:
            issues.append(f"겹침 #{idx}: 이전끝 {prev:.3f} > 시작 {a:.3f}")
        prev = b
    return issues


def find_choppy(keeps, window, max_cuts):
    """컷이 너무 촘촘해 부자연스러울 수 있는 구간을 '출력(컷 후) 타임라인' 기준으로 찾는다.
       자연스러움 > 최대 제거 원칙을 위한 가드. 반환: [(시작, 끝, 컷수), ...]"""
    cps, acc = [], 0.0
    for a, b in keeps[:-1]:
        acc += b - a
        cps.append(acc)          # 출력 타임라인상 컷(점프)이 일어나는 지점
    flagged, i, n = [], 0, len(cps)
    while i < n:
        j = i
        while j < n and cps[j] - cps[i] <= window:
            j += 1
        if j - i >= max_cuts:
            flagged.append([cps[i], cps[j - 1], j - i])
            i = j
        else:
            i += 1
    merged = []
    for s, e, c in flagged:
        if merged and s - merged[-1][1] <= window:
            merged[-1][1] = e; merged[-1][2] += c
        else:
            merged.append([s, e, c])
    return merged


def cut_pos(t, keeps):
    """원본 시각 → 컷(출력) 타임라인 시각. 제거 구간 안이면 그 컷 지점을 반환."""
    acc = 0.0
    for a, b in keeps:
        if t <= a:
            return acc
        if t <= b:
            return acc + (t - a)
        acc += b - a
    return acc


def find_direction_talk(sw, keeps):
    """컷에 살아남은 단어 중 촬영 디렉션 표현('잠시만요', '부탁드립니다' 등)을 찾는다.
    자동 삭제는 위험(본편 멘트와 겹칠 수 있음) → 마커/리포트로 표시만 한다.
    반환: [(원본시각, 원본끝, 주변 문맥 텍스트)] — 3초 안 인접 히트는 묶음."""
    phrases = CFG.get("DIRECTION_PHRASES") or [
        "잠시만요", "잠깐만요", "다시 갈게요", "다시 한번", "다시 한 번",
        "한 번만", "한번만", "부탁드립니다", "부탁드릴게요", "읽을까요",
        "해 주시겠어요", "해주시겠어요", "여기서부터", "여기부터", "괜찮으세요",
        "쉬시고", "컷할게요",
    ]
    def kept(w):
        mid = (w[0] + w[1]) / 2
        return any(a <= mid <= b for a, b in keeps)

    hits = []
    n = len(sw)
    for i, w in enumerate(sw):
        pair = w[2] + (" " + sw[i + 1][2] if i + 1 < n else "")
        if any(p in w[2] or p in pair for p in phrases) and kept(w):
            hits.append(i)
    groups, log = [], []
    for i in hits:
        if groups and sw[i][0] - sw[groups[-1][-1]][1] <= 3.0:
            groups[-1].append(i)
        else:
            groups.append([i])
    for g in groups:
        lo, hi = max(0, g[0] - 2), min(n, g[-1] + 3)   # 앞뒤 문맥 살짝 포함
        log.append((sw[g[0]][0], sw[g[-1]][1],
                    " ".join(sw[x][2] for x in range(lo, hi))))
    return log


def build_stt_prompt():
    """받아쓰기 initial_prompt 조립 — 캐시 지문과 반드시 같은 소스를 쓰도록 단일화."""
    prompt = CFG["VERBATIM_PROMPT"]
    hints = CFG.get("STT_HINTS")
    if hints:   # 병원명·브랜드 등 고유명사를 받아쓰기 힌트로 주입 (config.json STT_HINTS)
        prompt = "고유명사: " + ", ".join(hints) + ". " + prompt
    return prompt


def stt_fingerprint():
    """전사 결과를 좌우하는 설정의 지문. 바뀌면 캐시를 버리고 재전사한다.
    (_cut_audio.wav는 매 실행 재생성이라 파일 지문 대신, wav 내용을 결정하는
    DENOISE/DEESS 설정을 포함한다.)"""
    import hashlib
    payload = {
        "model": CFG["STT_MODEL"],
        "prompt": build_stt_prompt(),
        "condition": True,
        "vad": CFG.get("STT_VAD", True),
        "beam": CFG.get("STT_BEAM", 5),
        "temperature": CFG.get("STT_TEMPERATURE"),
        "denoise": bool(CFG.get("DENOISE")),
        "deess": bool(CFG.get("DEESS")),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False,
                                   sort_keys=True).encode("utf-8")).hexdigest()


def get_transcript(video, audio_src, cache, force=False):
    meta_path = os.path.splitext(cache)[0] + ".meta.json"
    fp = stt_fingerprint()
    if os.path.exists(cache) and not force:
        meta = None
        if os.path.exists(meta_path):
            try:
                meta = json.load(open(meta_path, encoding="utf-8"))
            except Exception:
                meta = None
        if meta is None:
            # 구버전 캐시(메타 없음) — 재사용하되 현재 지문 채택(다음부턴 감지됨)
            print("> 받아쓰기 캐시 사용 (구버전 캐시 — 설정 변경 감지 불가. 재전사하려면 --retranscribe)")
            json.dump({"fingerprint": fp, "adopted": True},
                      open(meta_path, "w", encoding="utf-8"))
            return [tuple(w) for w in json.load(open(cache, encoding="utf-8"))]
        if meta.get("fingerprint") == fp:
            print("> 받아쓰기 캐시 사용 (재전사 생략)")
            return [tuple(w) for w in json.load(open(cache, encoding="utf-8"))]
        print("> 받아쓰기 설정 변경 감지 (모델/힌트/프롬프트 등) → 재전사")
    words = transcribe(audio_src, model=CFG["STT_MODEL"],
                       initial_prompt=build_stt_prompt(), condition=True,
                       vad=CFG.get("STT_VAD", True),
                       beam_size=CFG.get("STT_BEAM", 5),
                       temperature=CFG.get("STT_TEMPERATURE"))
    json.dump(words, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"fingerprint": fp}, open(meta_path, "w", encoding="utf-8"))
    return words


def apply_config_to_modules():
    """무음/음량 파라미터를 silence_cut 모듈에 주입."""
    SC.NOISE_DB = CFG["NOISE_DB"]
    SC.MIN_SILENCE = CFG["MIN_SILENCE"]
    SC.PAD_LEAD = CFG["PAD_LEAD"]
    SC.PAD_TAIL = CFG["PAD_TAIL"]
    SC.MIN_KEEP = CFG["MIN_KEEP"]
    SC.TARGET_LUFS = CFG["TARGET_LUFS"]
    SC.TARGET_PEAK_DB = CFG["TARGET_PEAK_DB"]


def main():
    global CFG
    args = [a for a in sys.argv[1:]]
    preset = "표준"
    if "--preset" in args:
        i = args.index("--preset")
        preset = args[i + 1]
        del args[i:i + 2]
    script_path = None
    if "--script" in args:
        i = args.index("--script")
        script_path = args[i + 1]
        del args[i:i + 2]
    force_stt = "--retranscribe" in args
    if force_stt:
        args.remove("--retranscribe")
    if not args:
        print("사용: python3 auto_cut.py \"<원본영상>\" [--preset 보수|표준|공격]"
              " [--script \"대본.txt\"] [--retranscribe]"); sys.exit(1)
    video = args[0]
    if not os.path.exists(video):
        print("파일 없음:", video); sys.exit(1)
    SC.ensure_tools()   # ffmpeg 없으면 설치 안내 후 종료

    proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CFG = CONFIG.load(preset, project_dir=proj)
    apply_config_to_modules()

    base = os.path.splitext(os.path.basename(video))[0]
    outdir = os.path.join(proj, "output")
    os.makedirs(outdir, exist_ok=True)
    xml_out = os.path.join(outdir, base + "_cut.xml")
    srt_out = os.path.join(outdir, base + "_cut.srt")
    wav_out = os.path.join(outdir, base + "_cut_audio.wav")
    rej_out = os.path.join(outdir, base + "_rejected.xml")
    words_cache = os.path.join(outdir, base + "_words.json")

    if CFG.get("BACKUP_OUTPUTS"):
        bdir = backup_outputs(outdir, base)
        if bdir:
            print(f"> 이전 결과 백업 → _backup/{os.path.basename(bdir)}/")

    src = "config.json" if CFG.get("_config_json") else f"프리셋:{CFG['_preset']}"
    print(f"> 미디어 분석 중...  (설정 {src})")
    info = probe_media(video)
    print(f"   길이 {fmt(info['duration'])} · {info['width']}x{info['height']} · {info['fps']}fps")
    if not info.get("has_audio", True):
        print("\n[오류] 이 영상에는 오디오(소리) 트랙이 없습니다.")
        print("       이 도구는 말소리를 기준으로 편집해서, 소리 없는 영상은 처리할 수 없어요.")
        sys.exit(1)
    if info.get("vfr_suspect"):
        print("   [주의] 가변 프레임레이트(VFR) 영상으로 보입니다 — 뒤로 갈수록 컷/자막이")
        print("          밀릴 수 있어요. 문제가 보이면 아래 명령으로 고정 레이트로 변환 후 다시:")
        print(f"          ffmpeg -i \"{os.path.basename(video)}\" -r {int(round(info['fps']))}"
              f" -c:a copy \"{base}_cfr.mp4\"")

    print("> 무음 감지 중...")
    sil_keeps = keep_ranges_from_silence(detect_silence(video), info["duration"])
    kept_sil = sum(b - a for a, b in sil_keeps)

    print("> 음량 분석 + 오디오 정리 중...")
    loud = measure_loudness(video)
    extra = []
    if CFG.get("DENOISE"):
        extra.append("afftdn")
    if CFG.get("DEESS"):
        extra.append("deesser")
    extra_filters = (",".join(extra) + ",") if extra else ""
    if extra:
        print(f"   오디오 후처리: {', '.join(extra)}")
    ok = make_clean_audio(video, wav_out, info, extra_filters=extra_filters)
    clean_audio = wav_out if ok else None
    if clean_audio:
        after = measure_loudness(wav_out)
        print(f"   음량 {loud['I']}→{after['I']} LUFS / 피크 {loud['TP']}→{after['TP']} dB")
    audio_for_stt = clean_audio or video

    words = get_transcript(video, audio_for_stt, words_cache, force=force_stt)
    print(f"   받아쓴 단어 {len(words)}개")

    # ── 받아쓰기 사후 교정: ① 용어사전 확정 치환 → ② 대본 대조 교정 ──
    import script_align as SA
    replace_log, script_log, script_cov = [], [], None
    rmap = CFG.get("REPLACE_MAP") or {}
    if rmap:
        words, replace_log = SA.apply_replace_map(words, rmap, CFG.get("REPLACE_JOSA"))
        if replace_log:
            print(f"> 용어사전 치환 {len(replace_log)}건")
    spath = script_path or CFG.get("SCRIPT_FILE")
    if spath:
        if not os.path.exists(spath):
            print(f"   [주의] 대본 파일을 찾을 수 없어 대본 교정 건너뜀: {spath}")
        else:
            print("> 대본 대조 교정 중...")
            toks = SA.load_script(spath)
            words, script_log, script_cov = SA.correct(
                words, toks,
                ratio_min=CFG.get("SCRIPT_MATCH_RATIO", 0.8),
                anchor_min=CFG.get("SCRIPT_ANCHOR_MIN", 3),
                gap_max=CFG.get("SCRIPT_GAP_MAX", 30),
                fix_endings=CFG.get("SCRIPT_FIX_ENDINGS", False))
            if script_cov < 0.30:
                print(f"   [주의] 대본 일치율 {script_cov*100:.0f}% — 다른 영상의 대본일 수 있어"
                      " 교정을 건너뜀 (앵커 부족)")
            else:
                print(f"   대본 일치율 {script_cov*100:.0f}% · 표기 교정 {len(script_log)}건"
                      " (즉흥 구간은 건드리지 않음)")
    if replace_log or script_log:
        rep_path = os.path.join(outdir, base + "_script_report.txt")
        SA.write_report(rep_path, replace_log, script_log, script_cov or 0.0)
        print(f"   교정 내역 → {os.path.basename(rep_path)}")

    # ── 제거 구간 계산 ──
    keeps = sil_keeps
    removes = []
    report = {"추임새": [], "망설임": [], "더듬/중복": [], "숨소리": []}
    report["표기 교정"] = ([(t, t, f"{old} → {new}") for t, old, new in replace_log] +
                          [(t, t, f"{old} → {new}") for t, old, new, _r in script_log])
    sw = sorted(words, key=lambda w: w[0])
    fpad = CFG["FILLER_PAD"]

    n_kept_ctx = 0
    if CFG["REMOVE_FILLERS"]:
        for i, (s, e, t) in enumerate(sw):
            if is_filler(t):
                if keep_filler_in_context(i, sw):   # '좀 더' 등 의미 있는 건 살림
                    n_kept_ctx += 1
                    continue
                removes.append([max(0.0, s - fpad), e + fpad])
                report["추임새"].append((s, e, t))

    if CFG["REMOVE_HESITATION"]:
        hmin, hpad = CFG["HESITATION_MIN"], CFG["HESITATION_PAD"]
        for i in range(len(sw) - 1):
            g0, g1 = sw[i][1], sw[i + 1][0]
            if g1 - g0 < hmin:
                continue
            for a, b in sil_keeps:
                lo, hi = max(g0, a) + hpad, min(g1, b) - hpad
                if hi - lo >= hmin:
                    removes.append([lo, hi])
                    report["망설임"].append((lo, hi, "(어/음 등)"))

    if CFG["REMOVE_REPEATS"]:
        rep_ranges, rep_log = find_repeats(sw)
        removes += rep_ranges
        report["더듬/중복"] = rep_log

    if CFG.get("REMOVE_RETAKES", True):
        rt_ranges, rt_log = find_retakes(sw)
        removes += rt_ranges
        report["재테이크"] = rt_log
        if rt_log:
            cut_s = sum(e - s for s, e, _ in rt_log)
            print(f"> 재테이크 {len(rt_log)}곳 감지 — 앞 시도 제거, 마지막 테이크만 남김"
                  f" (약 {fmt(cut_s)} 절약)")

    if CFG.get("ACOUSTIC_FILLER") and clean_audio:
        try:
            import acoustic_filler as AF
            AF.MIN_DUR = CFG.get("ACOUSTIC_MIN_DUR", 0.20)   # 프리셋으로 민감도 조절
            print("> 어/음 음향 검출 중...")
            r_, f_, v_ = AF.analyze(AF.load_audio(clean_audio))
            checked = AF.cross_check(AF.detect(r_, f_, v_), words)
            wstarts = sorted(x[0] for x in sw)
            follow_max = CFG.get("ACOUSTIC_FOLLOW_MAX", 1.0)
            n_ac = n_tail = 0
            for s, e, d, conf, txt in checked:
                if conf != "높음(빈구간)":     # 글자 없는 지속음만 = 가장 안전
                    continue
                # 끝음 보호: 어/음 뒤에 말이 곧 이어지면 컷(=말 중간), 한참 침묵이면 보존(=문장 끝 꼬리)
                idx = bisect.bisect_left(wstarts, e)
                nxt = wstarts[idx] if idx < len(wstarts) else e + 99
                if nxt - e <= follow_max:
                    removes.append([s, e])
                    report["망설임"].append((s, e, "(음향 어/음)"))
                    n_ac += 1
                else:
                    n_tail += 1
            print(f"   음향 어/음 {n_ac}개 추가" + (f" (끝음 꼬리 {n_tail}개 보존)" if n_tail else ""))
        except Exception as ex:
            print(f"   [주의] 음향 검출 건너뜀: {ex}")

    if CFG.get("BREATH_REDUCE") and clean_audio:
        try:
            import breath_reduce as BR
            print("> 숨소리 축소 중...")
            aud, asr = BR.load_audio(clean_audio)
            br = BR.detect_breaths(
                aud, asr, words, sil_keeps,
                min_dur=CFG.get("BREATH_MIN_DUR", 0.15),
                rel_lo=CFG.get("BREATH_REL_LO", -40.0),
                rel_hi=CFG.get("BREATH_REL_HI", -12.0),
                flatness=CFG.get("BREATH_FLATNESS", 0.35),
                frac=CFG.get("BREATH_FRAC", 0.40),
                keep=CFG.get("BREATH_KEEP", 0.12),
                pad=CFG.get("BREATH_PAD", 0.04))
            cut = sum(b - a for a, b in br)
            removes += [list(r) for r in br]
            report["숨소리"] = [(a, b, "(숨소리)") for a, b in br]
            print(f"   숨소리 {len(br)}곳 축소 (약 {fmt(cut)})")
        except Exception as ex:
            print(f"   [주의] 숨소리 축소 건너뜀: {ex}")

    if removes:
        keeps = subtract(sil_keeps, removes)
        kept_now = sum(b - a for a, b in keeps)
        nf, nh, nr, nb = (len(report["추임새"]), len(report["망설임"]),
                          len(report["더듬/중복"]), len(report["숨소리"]))
        ctx = f" (문맥상 '좀' {n_kept_ctx}개 살림)" if n_kept_ctx else ""
        parts = []
        if nf or nh: parts.append(f"추임새 {nf} + 망설임 {nh}")
        if nr: parts.append(f"더듬/중복 {nr}")
        if nb: parts.append(f"숨소리 {nb}")
        print(f"   {' + '.join(parts) or '제거 없음'} 제거{ctx} "
              f"→ 추가로 {fmt(kept_sil - kept_now)} 단축")
        rep_out = os.path.join(outdir, base + "_cut_report.txt")
        with open(rep_out, "w", encoding="utf-8") as f:
            for cat in ("추임새", "망설임", "더듬/중복", "숨소리"):
                f.write(f"━━━ {cat} ({len(report[cat])}개) ━━━\n")
                for s, e, t in report[cat]:
                    f.write(f"  {srt_time(s)}  {t}\n")
                f.write("\n")

    kept = sum(b - a for a, b in keeps)
    removed = info["duration"] - kept
    print(f"\n   총 제거: {fmt(removed)} ({removed/info['duration']*100:.1f}%)  "
          f"| 컷 {len(keeps)}개 | 최종 {fmt(kept)}")

    # ── 검토 지점 수집: 자연스러움 주의(컷 타임라인) + 디렉션 의심(원본→컷 변환) ──
    choppy = find_choppy(keeps, CFG["CHOPPY_WINDOW"], CFG["CHOPPY_MAX"])
    direction_log = find_direction_talk(sw, keeps)
    report["디렉션 의심"] = direction_log
    if direction_log:
        print(f"   디렉션 의심 {len(direction_log)}곳 (자동 삭제 안 함 — 마커/리포트로 표시)")

    markers = []
    if CFG.get("XML_MARKERS", True):
        for s, e, txt in report.get("재테이크", []):
            markers.append((cut_pos(s, keeps), "재테이크 제거됨",
                            f"여기서 NG {fmt(e - s)} 잘림: {txt[:60]}"))
        for s, e, txt in direction_log:
            markers.append((cut_pos(s, keeps), "디렉션 의심",
                            f"확인 필요: {txt[:60]}"))
        for s, e, c in choppy:   # find_choppy는 이미 컷 타임라인 기준
            markers.append((s, f"컷 촘촘({c})", "부자연스러울 수 있음 — 호흡 살릴지 확인"))
        markers.sort()

    # ── XML 생성 ──
    print("> 프리미어 시퀀스(XML) 생성 중...")
    gain = compute_gain_db(loud)
    xml, seq_dur = build_fcp7_xml(video, info, keeps, gain, base + " [러프컷]",
                                  clean_audio=clean_audio,
                                  fade_frames=CFG.get("AUDIO_FADE_FRAMES", 0),
                                  markers=markers)
    open(xml_out, "w", encoding="utf-8").write(xml)
    if markers:
        print(f"   시퀀스 마커 {len(markers)}개 삽입 (프리미어 타임라인에서 바로 점프)")

    # ── 프레임 무결성 검증 ──
    issues = verify_keeps(keeps)
    if issues:
        print(f"   [주의] 검증: 문제 {len(issues)}건 발견")
    else:
        print(f"   검증: 갭/겹침/길이오류 0 (컷 {len(keeps)}개)")

    # ── 자연스러움 가드 (choppy는 마커 수집 단계에서 계산됨) ──
    if choppy:
        print(f"   [주의] 자연스러움 주의: 컷이 촘촘한 구간 {len(choppy)}곳 → 리포트에서 확인 권장")
    rep_path = os.path.join(outdir, base + "_cut_report.txt")
    with open(rep_path, "a", encoding="utf-8") as f:
        f.write(f"━━━ 검증 ━━━\n")
        f.write("  프레임: " + ("정상(갭/겹침 0)\n" if not issues else "; ".join(issues) + "\n"))
        f.write(f"━━━ 자연스러움 주의 (컷 촘촘 = 부자연 위험, {len(choppy)}곳) ━━━\n")
        for s, e, c in choppy:
            f.write(f"  {srt_time(s)}~{srt_time(e)}  {c}컷 (확인 권장)\n")
        f.write("\n")

    # ── 버린 컷 시퀀스 (잘려나간 구간만) ──
    rej_made = False
    if CFG.get("MAKE_REJECTED"):
        rej = complement(keeps, info["duration"])
        if rej:
            rej_xml, _ = build_fcp7_xml(video, info, rej, gain, base + " [버린컷]",
                                        clean_audio=clean_audio)
            open(rej_out, "w", encoding="utf-8").write(rej_xml)
            rej_made = True

    # ── 자막 생성 ──
    print("> 자막(SRT) 생성 중...")
    mapper = build_mapper(keeps)
    sub_words = [w for w in words if not is_filler(w[2])]
    # 자막 줄 길이 — config.json의 SUB_MIN_CHARS/SUB_MAX_CHARS/SUB_KEEP_WHOLE 우선.
    # 지정이 없고 세로 영상(9:16 등)이면 좁은 화면에서 한 줄로 나오게 짧게 잡는다.
    sub_min = CFG.get("SUB_MIN_CHARS")
    sub_max = CFG.get("SUB_MAX_CHARS")
    sub_keep = CFG.get("SUB_KEEP_WHOLE")
    if sub_max is None and info["height"] > info["width"]:
        sub_min, sub_max, sub_keep = 8, 16, 18
        print("   세로 영상 감지 → 자막 한 줄 16자 기준 (config.json SUB_MAX_CHARS 로 조절)")
    lines = regroup(sub_words, mapper, min_c=sub_min, max_c=sub_max, keep_whole=sub_keep)
    write_srt(lines, srt_out)

    # 자막 마감(줄길이 안전망 + CPS) + .vtt/.ass(비블 스타일) 한 번에
    sub_extra = ""
    if CFG.get("POLISH_SUBTITLES"):
        try:
            import subtitle_polish as SP
            SP.FILL_GAPS = CFG.get("SUBTITLE_FILL_GAPS", True)   # 자막 빈칸 제거 여부
            if CFG.get("SUB_MAX_LINE") or sub_keep:              # 줄길이 안전망도 같은 기준으로
                SP.MAX_CHARS_LINE = CFG.get("SUB_MAX_LINE") or sub_keep
            cues = SP.polish(SP.parse_srt(srt_out))
            stem = os.path.splitext(srt_out)[0]
            SP.write_srt(cues, srt_out)
            SP.write_vtt(cues, stem + ".vtt")
            SP.write_ass(cues, stem + ".ass")
            lines = cues
            sub_extra = " (+ .vtt / .ass)"
        except Exception as ex:
            print(f"   [주의] 자막 마감 건너뜀: {ex}")

    print(f"\n완료  (설정 {src})")
    print(f"   시퀀스 : {os.path.basename(xml_out)}")
    print(f"   오디오 : {os.path.basename(wav_out)}")
    print(f"   자막   : {os.path.basename(srt_out)}{sub_extra}  ({len(lines)}줄)")
    if rej_made:
        print(f"   버린컷 : {os.path.basename(rej_out)}  (잘린 부분 검토용)")
    if CFG.get("HTML_REPORT"):
        try:
            import html_report
            summary = {"duration": info["duration"], "kept": kept, "removed": removed,
                       "pct": removed / info["duration"] * 100, "cuts": len(keeps),
                       "preset": CFG["_preset"]}
            hp = html_report.generate(os.path.join(outdir, base + "_report.html"),
                                      base, summary, choppy, report)
            print(f"   리포트 : {os.path.basename(hp)}  (브라우저로 열어 검토)")
        except Exception as ex:
            print(f"   [주의] HTML 리포트 건너뜀: {ex}")
    print(f"\n   프리미어 > 파일 > 가져오기 로 .xml 불러오세요.")
    if len(keeps) > 1:
        print(f"   자연스러움 팁: 타임라인 전체 선택 → Cmd+Shift+D 하면")
        print(f"      모든 컷에 기본 오디오 전환이 적용돼 클릭음 없이 부드러워집니다.")
        rep_path2 = os.path.join(outdir, base + "_cut_report.txt")
        with open(rep_path2, "a", encoding="utf-8") as f:
            f.write("━━━ 다듬기 팁 ━━━\n")
            f.write("  컷 부드럽게: 프리미어 타임라인 전체 선택 → Cmd+Shift+D (모든 컷에 기본 오디오 전환)\n")
            f.write("  자연스러움 주의 구간은 위 목록 참고 — 너무 촘촘하면 일부 컷 되돌려 호흡 살리기\n\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n(중단됨)")
        sys.exit(130)
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            _proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            _outdir = os.path.join(_proj, "output")
            os.makedirs(_outdir, exist_ok=True)
            _logp = os.path.join(_outdir, "_last_error.log")
            open(_logp, "w", encoding="utf-8").write(err)
            print("\n[오류] 처리 중 문제가 발생했습니다.")
            print(f"       상세 로그: {_logp}")
            print("       이 파일 내용을 보여주시면 원인을 빨리 찾을 수 있어요.")
        except Exception:
            print(err)
        sys.exit(1)
