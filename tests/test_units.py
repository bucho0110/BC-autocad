# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""AutoCAD 없이 도는 계산 시험(측점·삼각망·DDGP 계획선·CSAR 배치).

실행: <python> -X utf8 tests\\test_units.py   끝에 "FAIL: []"이면 통과.
"""
import os
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.common import coords as C  # noqa: E402
from skills.windows import ddgp, dtin  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


def close(a, b, tol=1e-6):
    return len(a) == len(b) and all(abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol for p, q in zip(a, b))


check("측점 1+250.5", C.station_to_dist("1+250.5") == 1250.5)
check("측점 No.12+5(20)", C.station_to_dist("No.12+5", "Number", 20) == 245.0)
check("측점 문자 No.62+10.5", C.sta_str(1250.5, "Number", 20, 1, prefix="No.") == "No.62+10.5")
P, T = dtin.triangulate([(0, 0, 1), (10, 0, 2), (0, 10, 3), (10, 10, 4), (5, 5, 5)])
check("삼각망 4면", len(T) == 4, T)

sec = {"center": [0, 0, 40], "y_g": 5.0, "el_g": 12.5, "dist": 0, "station": "0+000",
       "ground_pts": [[-150, 6], [-20, 10], [0, 5], [20, 10], [150, 6]]}
cfg = dict(ddgp.DEFAULTS)
head = ["측점", "하상고", "계획고", "하폭", "제방폭", "제내지경사", "제외지경사"]
t = ddgp.parse_table([head, ["0+000", 11.5, 30.5, 15, 4, 2, 2]], cfg)
pts, why = ddgp.side_points(sec, t[0.0], "L", cfg)
check("DDGP 기본", close(pts, [(-15, 4), (-53, 23), (-57, 23), (-87.13114754, 7.93442623)], 1e-6), pts)
head2 = head + ["고수부지고", "고수호안폭", "저수호안경사", "고수부지경사", "제방경사"]
t = ddgp.parse_table([head2, ["0+000", 11.5, 30.5, 40, 4, 2, 2, 15.5, 20, 2, 1, 2]], cfg)
pts, why = ddgp.side_points(sec, t[0.0], "L", cfg)
check("DDGP 고수부지·제방경사", close(pts[:5], [(-12, 4), (-20, 8), (-40, 8.2), (-69.6, 23), (-73.6, 22.92)], 1e-6), pts)
t = ddgp.parse_table([["측점", "하상고"], ["0+000", 11.5]], cfg)
pts, why = ddgp.side_points(sec, t[0.0], "L", cfg)
check("DDGP 값 모자람 보고", pts is None and "계획고" in why, why)

from skills.windows import drre  # noqa: E402
rows = [drre.HEAD, [0, "", "", 2, 3, 0, ""], [20, "BC", 100, 2, 3, 0, 5], [40, "EC", 100, 2, 3, 0, 5], [60, "", "", 0.5, 2, 1, ""]]
r = drre.compute(rows, dict(drre.DEFAULTS))
sg = r["segs"]
check("DRRE 직선 면적 60", abs(sg[0]["area"] - 60) < 1e-9, sg[0])
check("DRRE 곡선 안쪽 연장 19.0·18.4633", abs(sg[1]["L_top"] - 19.0) < 1e-9 and abs(sg[1]["L_bot"] - 18.46334) < 1e-4, sg[1])
check("DRRE 높이 입력(1:0.5) 비탈 2.2361", abs(drre.slope_len(0.5, 2)[0] - 2.236068) < 1e-6)
check("DRRE 밑다짐 면적 10", abs(sg[2]["mat_area"] - 10) < 1e-9, sg[2])
cv = drre.curves_from_segs([((0, 0), (100, 0), 0.41421356), ((100, 0), (200, 0), 0.0)], 1.0)
check("DRRE 곡선 R 70.71(90°)", abs(cv[0][2] - 70.710678) < 1e-4 and cv[0][3] == 1, cv)

try:
    from skills.windows import csar
    order = csar.cell_order(5, 2, 3, "아래→위 열 우선")
    check("CSAR 칸 순서(열 우선 아래→위)", order[:4] == [(0, 0), (0, 1), (0, 2), (1, 0)], order)
    frames = csar.frame_offsets(5, "행", 2, 100.0, 50.0, 10.0)
    check("CSAR 도곽 배치(행 2개씩)", frames == [(0.0, 0.0), (110.0, 0.0), (0.0, -60.0), (110.0, -60.0), (0.0, -120.0)], frames)
except ImportError:
    pass

# 실도면(실제 하천 도면 횡단면도)에서 드러난 것: 괄호 설명 붙은 측점, 단면별 세로 눈금, 긴 LISP 나누기
check("측점 괄호 설명 NO.13+742(풍운교(취입보))", C.station_to_dist("NO.13+742(풍운교(취입보))") == 13742.0)
from skills.common import xsec as XS
from skills.common.lisplib import split_forms
_ents = [{"type": "LWPOLYLINE", "layer": "C", "handle": "1", "points": [(0.0, 10.0, 0.0), (0.0, 12.4, 0.0)], "text": ""},
         {"type": "LWPOLYLINE", "layer": "G", "handle": "2", "points": [(-50.0, 20.0, 0.0), (0.0, 11.2, 0.0), (50.0, 21.0, 0.0)], "text": ""},
         {"type": "TEXT", "layer": "S", "handle": "3", "points": [(5.0, -30.0, 0.0)], "text": "NO.1+100(교량)"},
         {"type": "TEXT", "layer": "E", "handle": "4", "points": [(5.0, -35.0, 0.0)], "text": "EL=30.00"}]
# 왼쪽 눈금: 1m = 2 단위(1/500), 글자는 눈금선보다 0.6 위
_ents += [{"type": "TEXT", "layer": "dt", "handle": "n%d" % v, "points": [(-60.0, 11.2 + (v - 30) * 2 + 0.6, 0.0)], "text": str(v)}
          for v in range(26, 50, 2)]
# 아래 거리 눈금: 1m = 0.5 단위(1/2000), 0은 x=-2, 100m마다 50단위
_ents += [{"type": "TEXT", "layer": "dt", "handle": "h%d" % k, "points": [(-2.0 + k * 50.0, 5.0, 0.0)], "text": str(abs(k) * 100)}
          for k in range(-2, 3)]
_sp = {"ground_layer": "G", "center_layer": "C", "center_len": 2.4, "sta_off": [0.0, -20.0], "el_off": [0.0, -25.0], "tol": 4.0,
       "sta_layer": "S", "el_layer": "E"}
_sec = XS.find(_sp, _ents)[0]
check("단면: 문자 레이어·괄호 측점", _sec["station"] == "NO.1+100(교량)" and _sec["dist"] == 1100.0, _sec)
check("단면: 눈금으로 축척 1/500", _sec["axis"] is not None and abs(_sec["axis"][1] - 2.0) < 1e-9, _sec.get("axis"))
check("단면: EL 35 높이 = 지반 + 10 (V축척 설정 1000 무시)", abs(XS.y_of(_sec, 35.0, 1000.0) - (11.2 + 10.0)) < 1e-9)
check("단면: 거리 눈금으로 가로 축척 1/2000", _sec["haxis"] is not None and abs(XS.uh(_sec, 1000.0) - 0.5) < 1e-9, _sec.get("haxis"))
_b = '(bc:text "a)(" 1)' * 50
check("긴 LISP 식 경계 나누기", len(split_forms(_b, 100)) > 1 and "".join(split_forms(_b, 100)) == _b
      and all(x.startswith("(") and x.endswith(")") for x in split_forms(_b, 100)))

# LISP 함수 이름 중복: 파일이 이름순으로 불려 나중 것이 앞의 것을 덮어쓴다(CR의 bc:bbox가 공통 bc:bbox를 덮어써 CSAR이 깨진 일)
import glob  # noqa: E402
import re  # noqa: E402
_defs = {}
for _f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "lisp", "*.lsp"))):
    for _m in re.finditer(r"^\(defun\s+([^\s(]+)", open(_f, encoding="utf-8-sig").read(), re.M):
        _defs.setdefault(_m.group(1).lower(), []).append(os.path.basename(_f))
_dup = {k: v for k, v in _defs.items() if len(v) > 1}
check("LISP 함수 이름 중복 없음", not _dup, _dup)

# 좌표 소수 표기: 사사오입(보이는 10진 값 기준), 끝 0 유지
_f = [C.fmt(7.125, 2), C.fmt(2.675, 2), C.fmt(100, 4), C.fmt(110.5, 0), C.fmt(-3, 2), C.fmt(1234567.12345, 4)]
check("좌표 소수 사사오입", _f == ["7.13", "2.68", "100.0000", "111", "-3.00", "1234567.1235"], _f)

print("FAIL:", FAIL)
