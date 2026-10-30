# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DSTA 선형 측점 표기 — 간격마다 측점 선(눈금)·원·측점 문자. 교차선 위치, 엑셀 측점 목록도.

거리 계산은 파이썬, 점·진행 각도는 LISP(vlax-curve)에서 받아 다시 LISP로 그린다.
plan()·draw_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DSTA"
POS = ["선형방향좌", "선형방향우", "수직좌", "수직좌반대", "수직우", "수직우반대", "수직중간앞", "수직중간뒤"]
FIELDS = [
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("간격", "측점 선 간격 (m)", "real", 20.0, None),
    ("선길이", "측점 선 길이 (도면 단위)", "real", 2.0, None),
    ("축척", "축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("시작거리", "선형 시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("원간격", "측점 원 간격 (m, 0=안 그림, 종점은 항상)", "real", 100.0, None),
    ("원지름", "원 지름 (도면 단위)", "real", 1.0, None),
    ("000유지", "0+000 형식 유지 (Station)", "bool", True, None),
    ("문자", "측점 문자 쓰기", "bool", True, None),
    ("머리말", "측점 문자 머리말 (Number 기본 NO )", "str", "", None),
    ("문자위치", "문자 위치", "choice", "수직좌", POS),
    ("문자간격", "선형~문자 간격 (도면 단위)", "real", 3.0, None),
    ("문자표기간격", "문자 표기 간격 (m)", "real", 100.0, None),
    ("높이", "문자 높이", "real", 2.5, None),
    ("소수", "측점 소수 자리", "int", 0, None),
    ("종점소수", "종점 소수 자리", "int", 2, None),
    ("km만", "1km 단위만 km 숫자 (Station)", "bool", False, None),
    ("플러스0생략", "정체인 뒤 +0 생략 (Number)", "bool", False, None),
    ("선레이어", "측점 선·원 레이어 (비우면 현재)", "str", "", None),
    ("문자레이어", "측점 문자 레이어 (비우면 선 레이어)", "str", "", None),
    ("엑셀", "측점·누가거리·좌표를 엑셀로도", "bool", False, None),
    ("교차소수", "교차선 측점 소수 자리", "int", 3, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def upm(cfg):
    return 1000.0 / float(cfg["축척"] or 1000.0)


def start_dist(cfg):
    v = C.station_to_dist(cfg["시작거리"], cfg["측점구분"], float(cfg["간격"]))
    return v or 0.0


def label(d, cfg, dec=None):
    pre = cfg["머리말"]
    return C.sta_str(d, cfg["측점구분"], float(cfg["간격"]), cfg["소수"] if dec is None else dec, cfg["000유지"],
                     pre, cfg["km만"], cfg["플러스0생략"])


def plan(length_units, cfg):
    """일정 간격 계획: [(도면거리, 누가거리, 종류)] 종류 = 'tick' / 'end'."""
    k = upm(cfg)
    d0 = start_dist(cfg)
    iv = float(cfg["간격"])
    total = length_units / k
    out = [(0.0, d0, "tick")]
    first = math.floor(d0 / iv + 1e-9) * iv + iv
    d = first
    while d < d0 + total - 1e-6:
        out.append(((d - d0) * k, d, "tick"))
        d += iv
    out.append((length_units, d0 + total, "end"))
    return out


def _is_mult(d, step):
    return step > 0 and abs(d / step - round(d / step)) < 1e-6


def draw_lisp(samples, cfg, dec_override=None) -> str:
    """samples: [(도면거리, 누가거리, 종류, x, y, 각도)] → LISP 본문."""
    h = float(cfg["높이"])
    tl = float(cfg["선길이"]) / 2.0
    lay = ls(cfg["선레이어"])
    tlay = ls(cfg["문자레이어"] or cfg["선레이어"])
    g = float(cfg["문자간격"])
    pos = cfg["문자위치"]
    s = []
    for _dd, d, kind, x, y, a in samples:
        n = a + math.pi / 2
        p1 = (x + tl * math.cos(n), y + tl * math.sin(n))
        p2 = (x - tl * math.cos(n), y - tl * math.sin(n))
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (p1[0], p1[1], p2[0], p2[1], lay))
        if kind == "end" or (cfg["원간격"] and _is_mult(d, float(cfg["원간격"]))):
            s.append('(bc:circle (list %.10f %.10f 0.0) %.6f "%s")' % (x, y, float(cfg["원지름"]) / 2.0, lay))
        if not cfg["문자"]:
            continue
        if kind == "tick" and not (cfg["문자표기간격"] and _is_mult(d, float(cfg["문자표기간격"]))) and kind != "cross":
            continue
        dec = dec_override if dec_override is not None else (cfg["종점소수"] if kind == "end" and abs(d - round(d)) > 1e-9 else cfg["소수"])
        txt = ls(label(d, cfg, dec))
        q, rot, just = text_place(x, y, a, g, h, pos)
        s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "%s" %.12f)' % (q[0], q[1], txt, h, tlay, just, rot))
    return "".join(s)


def text_place(x, y, a, g, h, pos):
    L = a + math.pi / 2
    R = a - math.pi / 2
    if pos == "선형방향좌":
        return (x + g * math.cos(L), y + g * math.sin(L)), a, "BC"
    if pos == "선형방향우":
        return (x + g * math.cos(R), y + g * math.sin(R)), a, "TC"
    if pos == "수직좌":
        return (x + g * math.cos(L), y + g * math.sin(L)), L, "ML"
    if pos == "수직좌반대":
        return (x + g * math.cos(L), y + g * math.sin(L)), R, "MR"
    if pos == "수직우":
        return (x + g * math.cos(R), y + g * math.sin(R)), L, "MR"
    if pos == "수직우반대":
        return (x + g * math.cos(R), y + g * math.sin(R)), R, "ML"
    if pos == "수직중간앞":
        return (x - 0.4 * h * math.cos(a), y - 0.4 * h * math.sin(a)), L, "BC"
    return (x + 0.4 * h * math.cos(a), y + 0.4 * h * math.sin(a)), L, "TC"


def sample_body(handle, rev, dds) -> str:
    return '(bc:samples (handent "%s") %s (list %s) _fp)' % (handle, "T" if rev else "nil", " ".join("%.10f" % d for d in dds))


def parse_samples(rows):
    out = {}
    for r in rows:
        c = r.split("\t")
        if c[0] == "S":
            out[round(float(c[1]), 6)] = (float(c[2]), float(c[3]), float(c[4]))
    return out


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "선형 측점 표기", size="600x800")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        for txt, fn in (("간격마다", self.run_interval), ("교차선 위치", self.run_cross), ("엑셀 측점 목록", self.run_excel)):
            tk.Button(bar, text=txt, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat", height=2, width=16).pack(
                side="left", padx=3, expand=True, fill="x")

    def _cfg(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        return cfg

    def _pick_align(self):
        body = ('(setq _a (bc:pick-align "선형(중심선) 선택"))'
                ' (if _a (write-line (strcat "A\\t" (cdr (assoc 5 (entget (car _a)))) "\\t" (if (cadr _a) "1" "0")'
                ' "\\t" (bc:rtos (bc:curve-len (car _a)) 2 10)) _fp))')
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or []
        a = [r.split("\t") for r in rows if r.startswith("A\t")]
        if not a:
            return None
        return a[0][1], a[0][2] == "1", float(a[0][3])

    def _draw(self, h, rev, items, cfg, dec=None):
        rows = self.acad.lisp(sample_body(h, rev, [i[0] for i in items]), 120)
        sm = parse_samples(rows)
        samples = []
        for dd, d, kind in items:
            x, y, a = sm[round(dd, 6)]
            samples.append((dd, d, kind, x, y, a))
        self.acad.lisp_undo(draw_lisp(samples, cfg, dec), 120)
        if cfg["엑셀"]:
            ws, r, c = X.active_cell()
            X.write_rows(ws, r, c, [["측점", "누가거리", "X(토목)", "Y(토목)"]] +
                         [[label(d, dict(cfg, 머리말="")), C.fmt(d, 4), C.fmt(y, 4), C.fmt(x, 4)] for _dd, d, _k, x, y, _a in samples])
        return len(samples)

    def run_interval(self):
        try:
            cfg = self._cfg()
        except ValueError as e:
            self.error(str(e))
            return
        al = self._pick_align()
        if not al:
            return
        h, rev, L = al
        n = self.in_cad(self._draw, h, rev, plan(L, cfg), cfg)
        if n:
            self.status("측점 %d곳을 표기했습니다." % n)

    def run_cross(self):
        try:
            cfg = self._cfg()
        except ValueError as e:
            self.error(str(e))
            return
        al = self._pick_align()
        if not al:
            return
        h, rev, L = al
        body = ('(princ "\\n선형과 교차하는 선 선택: ") (setq _ss (ssget (list (cons 0 "LINE,LWPOLYLINE,POLYLINE,ARC,SPLINE"))))'
                ' (setq _al (handent "%s") _i 0)'
                ' (if _ss (while (< _i (sslength _ss)) (setq _e (ssname _ss _i) _r (vl-catch-all-apply (quote vlax-invoke)'
                ' (list (vlax-ename->vla-object _al) (quote IntersectWith) (vlax-ename->vla-object _e) acExtendNone)))'
                ' (if (and (not (vl-catch-all-error-p _r)) _r) (while _r (write-line (strcat "D\\t" (bc:rtos (bc:curve-d _al (list (car _r) (cadr _r) (caddr _r)) %s) 2 10)) _fp)'
                ' (setq _r (cdddr _r)))) (setq _i (1+ _i))))' % (h, "T" if rev else "nil"))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or []
        k = upm(cfg)
        d0 = start_dist(cfg)
        dds = sorted({round(float(r.split("\t")[1]), 6) for r in rows if r.startswith("D\t")})
        if not dds:
            self.status("교차점이 없습니다.")
            return
        items = [(dd, d0 + dd / k, "cross") for dd in dds]
        n = self.in_cad(self._draw, h, rev, items, cfg, int(cfg["교차소수"]))
        if n:
            self.status("교차점 %d곳에 측점을 표기했습니다." % n)

    def run_excel(self):
        try:
            cfg = self._cfg()
            vals = [r[0] for r in X.selection_values()]
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        dists = [C.station_to_dist(v, cfg["측점구분"], float(cfg["간격"])) for v in vals]
        dists = [d for d in dists if d is not None]
        if not dists:
            self.error("엑셀 선택 범위에서 측점(누가거리)을 읽지 못했습니다.")
            return
        al = self._pick_align()
        if not al:
            return
        h, rev, L = al
        k = upm(cfg)
        d0 = start_dist(cfg)
        items = [((d - d0) * k, d, "cross") for d in dists if -1e-6 <= (d - d0) * k <= L + 1e-6]
        n = self.in_cad(self._draw, h, rev, items, cfg, int(cfg["교차소수"]))
        if n:
            self.status("엑셀 측점 %d곳을 표기했습니다(선형 밖 %d곳 제외)." % (n, len(dists) - len(items)))


def main():
    Window().mainloop()
