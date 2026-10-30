# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""GRP 지형에서 종단 추출 — 선형과 지형(삼각망 3D면·등고선·3D 선)의 교점으로 종단 지반선과 지반고 표를 그린다.

선형은 LINE·LWPOLYLINE(호 포함)·ARC. 지형 선분은 Z 값이 있어야 한다.
선형 시·종점이 지형과 만나지 않는 구간은 비워 둔다(지반고 칸 빈칸).
build()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import profile as G
from skills.common import settings as S
from skills.common import terrain as T
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "GRP"
MARKS = ["측점 간격만", "지형 교차점만", "간격과 교차점 모두"]
FIELDS = [
    ("측점구분", "측점 표기 구분", "choice", "Station", ["Station", "Number"]),
    ("체인", "Number 측점 한 체인 길이 (m)", "real", 20.0, None),
    ("시작거리", "선형 시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("간격", "종단 측점 간격 (m)", "real", 20.0, None),
    ("역방향", "선형 방향 뒤집기", "bool", False, None),
    ("H축척", "종단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "종단 V 축척", "real", 200.0, None),
    ("표기", "세로선·지반고 표기 위치", "choice", MARKS[0], MARKS),
    ("칸높이", "표 한 칸 높이 (도면 단위)", "real", 20.0, None),
    ("제목폭", "표 제목 칸 폭 (도면 단위)", "real", 40.0, None),
    ("문자높이", "표 내용 문자 높이", "real", 2.5, None),
    ("제목높이", "표 제목 문자 높이", "real", 3.0, None),
    ("문자간격", "세로선과 문자 간격", "real", 0.5, None),
    ("지반고소수", "지반고 소수 자리", "int", 2, None),
    ("측점소수", "+측점 소수 자리 (정수 측점은 소수 없이)", "int", 3, None),
    ("Z0제외", "Z 0 이하 지형 제외", "bool", True, None),
    ("제거거리", "정점 줄이기: 앞 점과 거리 이하 (m, 0=안 함)", "real", 0.0, None),
    ("제거높이", "정점 줄이기: 그리고 높이 차 이하 (m)", "real", 0.0, None),
    ("같은높이제거", "앞 점과 같은 높이 정점 빼기", "bool", False, None),
    ("최하단지정", "종단 최하단(기준선) 높이 직접 지정", "bool", False, None),
    ("최하단높이", "최하단 높이 (m)", "real", 0.0, None),
    ("지형레이어", "이 레이어 지형만 (쉼표로 여럿, 비우면 전체)", "str", "", None),
    ("지반선레이어", "지반선 레이어", "str", "종단_지반선", None),
    ("표레이어", "표·세로선 레이어", "str", "종단_표", None),
    ("문자레이어", "문자 레이어", "str", "종단_문자", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def sta_label(d, cfg):
    dec = 0 if abs(d - round(d)) < 1e-9 else int(cfg["측점소수"])
    num = cfg["측점구분"] == "Number"
    return C.sta_str(d, cfg["측점구분"], float(cfg["체인"]), dec, prefix="No." if num else "")


def marks(prof, length, start, cfg):
    """세로선 위치(선형 처음부터 거리) 목록."""
    out = []
    if cfg["표기"] != MARKS[1]:
        iv = float(cfg["간격"])
        out.append(0.0)
        if iv > 0:
            k = math.floor(start / iv + 1e-9) + 1
            while k * iv - start < length - 1e-9:
                out.append(k * iv - start)
                k += 1
        out.append(length)
    if cfg["표기"] != MARKS[0]:
        out += [s for s, _z in prof]
    out.sort()
    res = []
    for s in out:
        if not res or s - res[-1] > 1e-6:
            res.append(s)
    return res


def compute(align_rows, terrain_rows, cfg):
    """덤프 → (선형 요소, 종단 [(거리, z)], 표 행 [[측점, 누가거리, 지반고]], 세로선 거리, 시작거리)."""
    elems = G.parse_align(align_rows)
    if not elems:
        raise ValueError("선형을 읽지 못했습니다(LINE·LWPOLYLINE·ARC).")
    if cfg["역방향"]:
        elems = G.reverse_elems(elems)
    edges = G.parse_edges(terrain_rows, cfg["Z0제외"])
    prof = G.ground(elems, edges, G.parse_faces(terrain_rows, cfg["Z0제외"]))
    if len(prof) < 2:
        raise ValueError("선형과 만나는 지형(Z 값 있는 선·3D면)이 두 곳 미만입니다.")
    prof = G.thin(prof, float(cfg["제거거리"]), float(cfg["제거높이"]), cfg["같은높이제거"])
    length = G.total_len(elems)
    start = C.station_to_dist(cfg["시작거리"] or "0", cfg["측점구분"], float(cfg["체인"])) or 0.0
    ms = marks(prof, length, start, cfg)
    rows = []
    for s in ms:
        z = G.z_at(prof, s)
        rows.append([sta_label(start + s, cfg), C.fmt(start + s, 3), "" if z is None else C.fmt(z, cfg["지반고소수"])])
    return elems, prof, rows, ms, start


def datum_of(prof, cfg):
    if cfg["최하단지정"]:
        return float(cfg["최하단높이"])
    return float(math.floor(min(z for _s, z in prof)) - 1)


def build_lisp(prof, rows, ms, origin, cfg):
    """종단 지반선 + 기준선 + 표. origin = 기준선 왼쪽 끝(시점, 최하단 높이)."""
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    dl = datum_of(prof, cfg)
    ox, oy = float(origin[0]), float(origin[1])
    lg, lt, lx = ls(cfg["지반선레이어"]), ls(cfg["표레이어"]), ls(cfg["문자레이어"])
    rh, tw, h, th, gap = cfg["칸높이"], cfg["제목폭"], cfg["문자높이"], cfg["제목높이"], cfg["문자간격"]
    end_x = ox + ms[-1] * uh

    def X(s):
        return ox + s * uh

    def Y(z):
        return oy + (z - dl) * uv

    def line(x1, y1, x2, y2, lay):
        return '(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (x1, y1, x2, y2, lay)

    def text(x, y, s, hh, just, rot=0.0):
        return '(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" %.10f)' % (x, y, ls(s), hh, lx, just, rot)

    out = ['(bc:ensure-layer "%s" 3) (bc:ensure-layer "%s" 7) (bc:ensure-layer "%s" 7)' % (lg, lt, lx)]
    out.append(T.lwpoly_lisp([(X(s), Y(z)) for s, z in prof], False, lg))
    out.append(line(ox, oy, end_x, oy, lt))
    out.append(text(ox - gap, oy + gap, "DL = %s" % C.fmt(dl, 2), h, "R"))
    titles = ["지반고", "누가거리", "측점"]
    for i in range(4):
        out.append(line(ox - tw, oy - i * rh, end_x, oy - i * rh, lt))
    for x in (ox - tw, ox, end_x):
        out.append(line(x, oy, x, oy - 3 * rh, lt))
    for i, t in enumerate(titles):
        out.append(text(ox - tw / 2, oy - (i + 0.5) * rh, t, th, "MC"))
    for s, (sta, dist, z) in zip(ms, rows):
        x = X(s)
        zz = G.z_at(prof, s)
        out.append(line(x, oy - 3 * rh, x, Y(zz) if zz is not None else oy, lt))
        for i, v in enumerate((z, dist, sta)):
            if v != "":
                out.append(text(x - gap - h / 2, oy - (i + 0.5) * rh, v, h, "MC", math.pi / 2))
    return "".join(out)


def terrain_select(cfg) -> str:
    flt = '(cons 0 "%s")' % G.TERRAIN_TYPES
    if cfg["지형레이어"].strip():
        flt += ' (cons 8 "%s")' % ls(cfg["지형레이어"].replace(" ", ""))
    return flt


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "지형에서 종단 추출", size="560x860")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="선형 선택 → 지형 선택 → 그릴 위치 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(setq _s (entsel "\\n선형 선택: ")) (if _s (progn (setq _al (car _s) _skip (list _al)) %s'
                ' (princ "\\n지형 객체(3D면·등고선·3D 선) 선택: ") (setq _ss (ssget (list %s))) %s'
                ' (setq _o (getpoint "\\n종단 그릴 위치(기준선 왼쪽 끝) 지정: "))'
                ' (if _o (progn (setq _o (trans _o 1 0)) (write-line (strcat "O" _d (bc:rtos (car _o) 2 10) _d'
                ' (bc:rtos (cadr _o) 2 10)) _fp)))))' % (G.ALIGN_LISP, terrain_select(cfg), G.TERRAIN_LISP))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if not rows:
            return
        org = [r.split("\t") for r in rows if r.startswith("O\t")]
        if not org:
            self.status("그릴 위치를 지정하지 않았습니다.")
            return
        try:
            _el, prof, table, ms, _st = compute(rows, rows, cfg)
        except ValueError as e:
            self.error(str(e))
            return
        code = build_lisp(prof, table, ms, (float(org[0][1]), float(org[0][2])), cfg)
        if self.in_cad(self.acad.lisp_undo, code, 180) is None:
            return
        self.status("종단 정점 %d개, 세로선 %d개를 그렸습니다." % (len(prof), len(ms)))


def main():
    Window().mainloop()
