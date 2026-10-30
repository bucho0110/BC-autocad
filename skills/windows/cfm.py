# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CFM 지형에서 횡단 추출 — 횡단선과 지형(삼각망 3D면·등고선·3D 선)의 교점으로 횡단 지반선을 그린다.

횡단선은 ① 도면에 그려 둔 선(중심선과 만나는 곳이 측점), ② 측점 간격마다, ③ 엑셀 측점 목록(편측 거리만큼 좌우).
각 횡단은 중심 지반 점이 배치 기준점에 오도록 세로로 나란히 그리고, 중심 세로선·측점·지반고 문자를 단다.
compute()·build_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import profile as G
from skills.common import settings as S
from skills.common import terrain as T
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CFM"
MODES = ["그려진 횡단선 선택", "측점 간격마다", "엑셀 측점 목록"]
FIELDS = [
    ("방식", "횡단 위치", "choice", MODES[0], MODES),
    ("측점구분", "측점 표기 구분", "choice", "Station", ["Station", "Number"]),
    ("체인", "Number 측점 한 체인 길이 (m)", "real", 20.0, None),
    ("시작거리", "선형 시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("간격", "측점 간격 (m, '측점 간격마다')", "real", 20.0, None),
    ("편측거리", "편측 추출 거리 (m, 간격·엑셀 방식)", "real", 50.0, None),
    ("역방향", "선형 방향 뒤집기", "bool", False, None),
    ("좌우반대", "횡단 좌우 바꾸기 (하천 등)", "bool", False, None),
    ("H축척", "횡단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "횡단 V 축척", "real", 1000.0, None),
    ("배치간격", "횡단 사이 세로 간격 (도면 단위)", "real", 60.0, None),
    ("위에서아래", "측점 순서대로 위 → 아래 배치", "bool", True, None),
    ("거리소수", "작성 거리 소수 자리", "int", 3, None),
    ("높이소수", "작성 높이 소수 자리", "int", 3, None),
    ("측점소수", "+측점 소수 자리 (정수 측점은 소수 없이)", "int", 3, None),
    ("중심선길이", "중심 세로선 길이 (도면 단위)", "real", 10.0, None),
    ("문자높이", "측점·지반고 문자 높이", "real", 2.5, None),
    ("Z0제외", "Z 0 이하 지형 제외", "bool", True, None),
    ("지형레이어", "이 레이어 지형만 (쉼표로 여럿, 비우면 전체)", "str", "", None),
    ("횡단선레이어", "이 레이어 횡단선만 (그려진 횡단선 방식, 비우면 전체)", "str", "", None),
    ("지반선레이어", "지반선 레이어", "str", "횡단_지반선", None),
    ("중심선레이어", "중심 세로선 레이어", "str", "횡단_중심", None),
    ("문자레이어", "측점·지반고 문자 레이어", "str", "횡단_문자", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
LINES_LISP = ('(foreach _e (bc:ss-list _sl) (setq _v (bc:verts _e))'
              ' (write-line (strcat "X" _d (bc:rtos (car (car _v)) 2 10) _d (bc:rtos (cadr (car _v)) 2 10) _d'
              ' (bc:rtos (car (last _v)) 2 10) _d (bc:rtos (cadr (last _v)) 2 10)) _fp))')


def sta_label(d, cfg):
    dec = 0 if abs(d - round(d)) < 1e-9 else int(cfg["측점소수"])
    return C.sta_str(d, cfg["측점구분"], float(cfg["체인"]), dec, prefix="No." if cfg["측점구분"] == "Number" else "")


def _start(cfg):
    return C.station_to_dist(cfg["시작거리"] or "0", cfg["측점구분"], float(cfg["체인"])) or 0.0


def _ends_at(elems, s, half):
    """선형 거리 s에서 직각 횡단선 (왼쪽 끝, 오른쪽 끝)."""
    p, ang = G.point_at(elems, s)
    nx, ny = math.cos(ang + math.pi / 2), math.sin(ang + math.pi / 2)
    return (p[0] + half * nx, p[1] + half * ny), (p[0] - half * nx, p[1] - half * ny)


def section_lines(elems, cfg, drawn=None, stations=None):
    """[(선형 거리, 왼쪽 끝, 오른쪽 끝)]. drawn: 그려진 선 [(a, b)], stations: 측점(문자·숫자) 목록."""
    start, L = _start(cfg), G.total_len(elems)
    out = []
    if cfg["방식"] == MODES[0]:
        for a, b in drawn or []:
            s = G.cross_at(elems, a, b)
            if s is None:
                continue
            p, ang = G.point_at(elems, s)
            # 진행 방향 왼쪽(+)에 있는 끝이 왼쪽 끝
            side = (b[0] - a[0]) * math.cos(ang + math.pi / 2) + (b[1] - a[1]) * math.sin(ang + math.pi / 2)
            out.append((s, b, a) if side > 0 else (s, a, b))
    else:
        half = float(cfg["편측거리"])
        if cfg["방식"] == MODES[1]:
            iv = float(cfg["간격"])
            ss = [0.0]
            if iv > 0:
                k = math.floor(start / iv + 1e-9) + 1
                while k * iv - start < L - 1e-9:
                    ss.append(k * iv - start)
                    k += 1
            ss.append(L)
        else:
            ss = []
            for v in stations or []:
                d = C.station_to_dist(v, cfg["측점구분"], float(cfg["체인"]))
                if d is not None and -1e-9 <= d - start <= L + 1e-9:
                    ss.append(d - start)
        for s in ss:
            out.append((s,) + _ends_at(elems, s, half))
    out.sort(key=lambda t: t[0])
    if cfg["좌우반대"]:
        out = [(s, r, l) for s, l, r in out]
    return out


def compute(elems, edges, lines, cfg, faces=None):
    """→ [{station, dist, ground: [[거리(왼쪽 −), EL]], center_el}] (지형과 두 곳 이상 만난 횡단만)."""
    start = _start(cfg)
    res = []
    for s, lft, rgt in lines:
        p, _a = G.point_at(elems, s)
        dc = math.hypot(p[0] - lft[0], p[1] - lft[1])
        prof = G.ground([(lft, rgt, 0.0)], edges, faces)
        if len(prof) < 2:
            continue
        zc = G.z_at(prof, dc)
        gd = [[float(C.fmt(d - dc, cfg["거리소수"])), float(C.fmt(z, cfg["높이소수"]))] for d, z in prof]
        res.append({"station": sta_label(start + s, cfg), "dist": float(C.fmt(start + s, 4)), "ground": gd,
                    "center_el": None if zc is None else float(C.fmt(zc, cfg["높이소수"]))})
    return res


def build_lisp(secs, base, cfg):
    """횡단 k의 중심 지반 점 = 기준점 + (0, ±k × 배치간격)."""
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    lg, lc, lx = ls(cfg["지반선레이어"]), ls(cfg["중심선레이어"]), ls(cfg["문자레이어"])
    h, cl = float(cfg["문자높이"]), float(cfg["중심선길이"])
    sign = -1.0 if cfg["위에서아래"] else 1.0
    out = ['(bc:ensure-layer "%s" 3) (bc:ensure-layer "%s" 1) (bc:ensure-layer "%s" 7)' % (lg, lc, lx)]
    for k, sec in enumerate(secs):
        bx, by = float(base[0]), float(base[1]) + sign * k * float(cfg["배치간격"])
        zc = sec["center_el"] if sec["center_el"] is not None else sum(z for _d, z in sec["ground"]) / len(sec["ground"])
        pts = [(bx + d * uh, by + (z - zc) * uv) for d, z in sec["ground"]]
        out.append(T.lwpoly_lisp(pts, False, lg))
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (bx, by, bx, by + cl, lc))
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (bx, by + cl + 1.5 * h, ls(sec["station"]), h, lx))
        if sec["center_el"] is not None:
            out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "L" 0.0)'
                       % (bx + 0.5 * h, by + 0.5 * h, ls("EL=" + C.fmt(sec["center_el"], cfg["높이소수"])), h, lx))
    return "".join(out)


def _flt(types, layers):
    f = '(cons 0 "%s")' % types
    if layers.strip():
        f += ' (cons 8 "%s")' % ls(layers.replace(" ", ""))
    return f


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "지형에서 횡단 추출", size="560x860")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀 측점 목록 방식은 엑셀에서 측점 범위(첫 열)를 먼저 고른 뒤 실행하세요.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=520, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="중심선 → (횡단선) → 지형 선택 → 배치 기준점", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        stations = None
        if cfg["방식"] == MODES[2]:
            try:
                stations = [r[0] for r in X.selection_values() if r and r[0] not in (None, "")]
            except X.ExcelNotReady as e:
                self.error(str(e))
                return
        pick_lines = ''
        if cfg["방식"] == MODES[0]:
            pick_lines = ('(princ "\\n횡단선 선택: ") (setq _sl (ssget (list %s)))'
                          ' (if _sl (setq _skip (append _skip (bc:ss-list _sl)))) %s'
                          % (_flt("LINE,LWPOLYLINE", cfg["횡단선레이어"]), LINES_LISP))
        body = ('(setq _s (entsel "\\n중심선(선형) 선택: ")) (if _s (progn (setq _al (car _s) _skip (list _al)) %s %s'
                ' (princ "\\n지형 객체(3D면·등고선·3D 선) 선택: ") (setq _ss (ssget (list %s))) %s'
                ' (setq _o (getpoint "\\n횡단 배치 기준점(첫 횡단 중심) 지정: "))'
                ' (if _o (progn (setq _o (trans _o 1 0)) (write-line (strcat "O" _d (bc:rtos (car _o) 2 10) _d'
                ' (bc:rtos (cadr _o) 2 10)) _fp)))))'
                % (G.ALIGN_LISP, pick_lines, _flt(G.TERRAIN_TYPES, cfg["지형레이어"]), G.TERRAIN_LISP))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if not rows:
            return
        org = [r.split("\t") for r in rows if r.startswith("O\t")]
        if not org:
            self.status("배치 기준점을 지정하지 않았습니다.")
            return
        elems = G.parse_align(rows)
        if cfg["역방향"]:
            elems = G.reverse_elems(elems)
        drawn = [((float(c[1]), float(c[2])), (float(c[3]), float(c[4])))
                 for c in (r.split("\t") for r in rows) if c[0] == "X"]
        secs = compute(elems, G.parse_edges(rows, cfg["Z0제외"]), section_lines(elems, cfg, drawn, stations), cfg,
                       G.parse_faces(rows, cfg["Z0제외"]))
        if not secs:
            self.error("지형과 만나는 횡단이 없습니다(횡단선이 중심선과 만나는지, 지형에 Z 값이 있는지 확인).")
            return
        code = build_lisp(secs, (float(org[0][1]), float(org[0][2])), cfg)
        if self.in_cad(self.acad.lisp_undo, code, 180) is None:
            return
        self.status("횡단 %d개를 그렸습니다(%s ~ %s)." % (len(secs), secs[0]["station"], secs[-1]["station"]))


def main():
    Window().mainloop()
