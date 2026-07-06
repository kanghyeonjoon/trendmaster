#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py — 실행 전 환경 점검. 사용: python engine/doctor.py (또는 check.bat)"""

import os, sys, shutil, subprocess

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

OK, BAD, WARN = "[OK]", "[문제]", "[참고]"
problems = 0


def check(label, ok, detail="", fix="", warn_only=False):
    global problems
    tag = OK if ok else (WARN if warn_only else BAD)
    print(f" {tag} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        if fix:
            print(f"        해결: {fix}")
        if not warn_only:
            problems += 1


def main():
    print("Premiere Auto-Edit 환경 점검")
    print("=" * 40)

    # 파이썬
    v = sys.version_info
    check("Python 3.10+", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}",
          "python.org 에서 최신 파이썬 설치")

    # ffmpeg / ffprobe
    ff = shutil.which("ffmpeg")
    check("ffmpeg", bool(ff), ff or "PATH에 없음",
          "윈도우: winget install Gyan.FFmpeg (설치 후 새 명령창)")
    check("ffprobe", bool(shutil.which("ffprobe")), "", "ffmpeg와 함께 설치됨 — 위 해결책과 동일")

    # 파이썬 패키지
    try:
        import numpy
        check("numpy", True, numpy.__version__)
    except ImportError:
        check("numpy", False, "", "pip install -r requirements.txt")
    try:
        import faster_whisper
        check("faster-whisper", True, getattr(faster_whisper, "__version__", ""))
    except ImportError:
        check("faster-whisper", False, "", "pip install -r requirements.txt")

    # GPU
    gpu_n = 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from make_subtitles import _enable_cuda_dlls
        _enable_cuda_dlls()
        import ctranslate2
        gpu_n = ctranslate2.get_cuda_device_count()
    except Exception:
        pass
    if gpu_n > 0:
        check("GPU(CUDA) 가속", True, f"GPU {gpu_n}개 사용 가능")
    else:
        check("GPU(CUDA) 가속", False, "미사용 — CPU로 동작(느림)",
              "NVIDIA GPU가 있다면: pip install -r requirements-gpu.txt", warn_only=True)

    # Whisper 모델 캐시
    hub = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    models = []
    if os.path.isdir(hub):
        models = [d for d in os.listdir(hub) if "faster-whisper" in d]
    check("음성인식 모델 캐시", bool(models),
          ", ".join(m.split("--")[-1] for m in models) if models else "아직 없음 — 첫 실행 때 자동 다운로드(약 3GB)",
          warn_only=True)

    # 디스크 여유
    try:
        free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__))).free / 1e9
        check("디스크 여유 공간 10GB+", free_gb >= 10, f"{free_gb:.0f}GB",
              "여유 공간 확보 권장 (모델 캐시 + 오디오 산출물)", warn_only=free_gb >= 5)
    except Exception:
        pass

    print("=" * 40)
    if problems == 0:
        print("모두 정상 — edit.bat \"영상.mp4\" 로 바로 시작하세요.")
    else:
        print(f"{problems}개 항목을 해결한 뒤 다시 점검하세요.")
    sys.exit(0 if problems == 0 else 1)


if __name__ == "__main__":
    main()
