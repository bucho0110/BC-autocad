# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""새 버전 알림 시험(AutoCAD 없이) — 버전 비교, 하루 한 번 확인, 끄기, 인터넷이 안 될 때, 실제 깃허브 태그 읽기.

실행: <python> -X utf8 tests\\test_update.py   끝에 "FAIL: []"이면 통과.
시험 동안 설정 파일 UPDATE.txt를 쓰고, 끝나면 원래 내용으로 되돌린다.
"""
import os
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from skills.common import settings as S  # noqa: E402
from skills.common import update as U  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, info if not cond else "")
    if not cond:
        FAIL.append(name)


p = S.path(U.CMD)
saved = open(p, "rb").read() if os.path.exists(p) else None
real = U._fetch_latest
calls = []
try:
    def fake(v):
        def f():
            calls.append(v)
            if isinstance(v, Exception):
                raise v
            return v
        return f

    major, minor, patch = (int(x) for x in U.VERSION_NUM.split("."))
    up = "%d.%d.%d" % (major, minor + 1, 0)
    T0 = 10 * U.DAY  # 처음 설정은 확인 시각 0 — 하루 넘게 지난 것으로 본다
    U.S.save(U.CMD, dict(U.DEFAULTS))
    U._fetch_latest = fake(up)
    check("새 버전 있으면 알림", U.notice(T0) == "새 버전이 있습니다: BC.%s (현재 BC.%s)." % (up, U.VERSION_NUM),
          U.notice(T0))
    check("하루 안에는 다시 묻지 않음", len(calls) == 1, calls)
    U._fetch_latest = fake(U.VERSION_NUM)
    check("하루 지나면 다시 확인(같은 버전이면 알림 없음)", U.notice(T0 + U.DAY) == "" and len(calls) == 2, calls)
    U._fetch_latest = fake("0.0.1")
    check("더 낮은 버전이면 알림 없음", U.notice(T0 + 2 * U.DAY) == "")
    U._fetch_latest = fake(OSError("인터넷 없음(시험)"))
    check("인터넷이 안 되면 조용히 넘어감", U.notice(T0 + 3 * U.DAY) == "")
    n = len(calls)
    U.notice(T0 + 3 * U.DAY + 10)
    check("실패해도 하루 동안 다시 묻지 않음", len(calls) == n, calls)
    U.S.save(U.CMD, dict(U.DEFAULTS))
    U._fetch_latest = fake(up)
    U.set_enabled(False)
    k = len(calls)
    check("끄면 확인도 알림도 없음", U.notice((T0 + 10 * U.DAY)) == "" and not U.enabled() and len(calls) == k, calls)
    U.set_enabled(True)
    check("다시 켜면 알림", U.enabled() and U.notice((T0 + 10 * U.DAY)) != "")
    check("태그 이름 읽기", U._ver("v0.10.2") == (0, 10, 2) and U._ver("v1.0") is None and U._ver("0.6.1") == (0, 6, 1))
    U._fetch_latest = real
    try:
        latest = real()
        check("실제 깃허브 태그 읽기", U._ver(latest) is not None and U._ver(latest) >= (0, 6, 1), latest)
    except OSError as e:
        print("건너뜀 실제 깃허브 태그 읽기(인터넷 없음):", e)
finally:
    U._fetch_latest = real
    if saved is None:
        os.remove(p) if os.path.exists(p) else None
    else:
        open(p, "wb").write(saved)
print("FAIL:", FAIL)
