# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DMT 구적도 그리기 — 닫힌 경계(폴리선)를 삼각형으로 나눠 번호·밑변·높이 선과 구적표(밑변 × 높이 ÷ 2)를 그린다.

삼각형은 귀 자르기로 나누되 매번 가장 덜 뾰족한(최소각이 큰) 삼각형을 먼저 잘라 예각 삼각형을 줄인다.
밑변 = 가장 긴 변, 높이 = 2 × 면적 ÷ 밑변. 표의 면적은 반올림한 밑변·높이로 계산하고(구적 산출 근거),
마지막 줄에 CAD 면적을 함께 쓴다. 'CAD 면적으로'면 산출 근거 없이 삼각형 실제 면적만.
경계의 호는 잘게 나눈 직선으로 본다. triangulate()·table_rows()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import cadtable as TB
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DMT"
FIELDS = [
    ("축척", "산출 축척 (1000 = m 도면, 1 = mm 도면)", "real", 1000.0, None),
    ("CAD면적", "CAD 면적으로 표 (밑변·높이 없이)", "bool", False, None),
    ("길이소수", "밑변·높이 소수 자리", "int", 2, None),
    ("면적소수", "면적 소수 자리", "int", 2, None),
    ("천단위", "천 단위 구분 기호", "bool", False, None),
    ("높이선", "삼각형마다 높이 선 그리기", "bool", True, None),
    ("번호머리", "번호 머리말", "str", "", None),
    ("문자높이", "번호·표 문자 높이", "real", 2.5, None),
    ("선레이어", "나눔선·높이선 레이어", "str", "구적_선", None),
    ("문자레이어", "번호·표 문자 레이어", "str", "구적_문자", None),
    ("표선레이어", "표 선 레이어", "str", "구적_표", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def _area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _min_angle(a, b, c):
    def ang(p, q, r):
        v1, v2 = (q[0] - p[0], q[1] - p[1]), (r[0] - p[0], r[1] - p[1])
        d = math.hypot(*v1) * math.hypot(*v2)
        return math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / d))) if d > 0 else 0.0
    return min(ang(a, b, c), ang(b, c, a), ang(c, a, b))


def _inside(p, a, b, c):
    d1, d2, d3 = _area2(a, b, p), _area2(b, c, p), _area2(c, a, p)
    return d1 >= -1e-12 and d2 >= -1e-12 and d3 >= -1e-12


def triangulate(pts):
    """단순 다각형 → 삼각형 [(a, b, c)] (꼭짓점 좌표)."""
    P = [p for i, p in enumerate(pts) if i == 0 or math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1e-9]
    if len(P) > 1 and math.hypot(P[0][0] - P[-1][0], P[0][1] - P[-1][1]) <= 1e-9:
        P.pop()
    if sum(_area2(P[0], P[i], P[i + 1]) for i in range(1, len(P) - 1)) < 0:
        P.reverse()
    idx = list(range(len(P)))
    tris = []
    while len(idx) > 3:
        best = None
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = P[i0], P[i1], P[i2]
            if _area2(a, b, c) <= 1e-12:
                if abs(_area2(a, b, c)) <= 1e-12:  # 일직선 꼭짓점은 버린다
                    best = (float("inf"), k, True)
                    break
                continue
            if any(_inside(P[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            q = _min_angle(a, b, c)
            if best is None or q > best[0]:
                best = (q, k, False)
        if best is None:
            raise ValueError("경계를 삼각형으로 나누지 못했습니다(선이 서로 꼬였는지 확인).")
        _q, k, drop = best
        if not drop:
            tris.append((P[idx[k - 1]], P[idx[k]], P[idx[(k + 1) % len(idx)]]))
        idx.pop(k)
    if len(idx) == 3 and abs(_area2(*(P[i] for i in idx))) > 1e-12:
        tris.append(tuple(P[i] for i in idx))
    return tris


def tri_info(t, k):
    """→ 밑변(m), 높이(m), 면적(㎡), 밑변 두 점, 꼭짓점."""
    sides = [(math.hypot(t[(i + 1) % 3][0] - t[i][0], t[(i + 1) % 3][1] - t[i][1]), i) for i in range(3)]
    L, i = max(sides)
    A_ = abs(_area2(*t)) / 2.0
    return L / k, (2 * A_ / L) / k, A_ / (k * k), (t[i], t[(i + 1) % 3]), t[(i + 2) % 3]


def table_rows(tris, cfg, cad_area):
    k = G.upm(cfg["축척"])
    dl, da, th = int(cfg["길이소수"]), int(cfg["면적소수"]), cfg["천단위"]
    if cfg["CAD면적"]:
        rows = [["번호", "면적(㎡)"]]
    else:
        rows = [["번호", "밑변(m)", "높이(m)", "면적(㎡)"]]
    total = 0.0
    for n, t in enumerate(tris, 1):
        b, h, a, _base, _apex = tri_info(t, k)
        no = "%s%d" % (cfg["번호머리"], n)
        if cfg["CAD면적"]:
            v = round(a, da)
            rows.append([no, G.num_str(v, da, th)])
        else:
            br, hr = round(b, dl), round(h, dl)
            v = round(br * hr / 2.0, da)
            rows.append([no, G.num_str(br, dl, th), G.num_str(hr, dl, th), G.num_str(v, da, th)])
        total += v
    pad = [""] * (len(rows[0]) - 2)
    rows.append(["합계"] + pad + [G.num_str(total, da, th)])
    rows.append(["CAD 면적"] + pad + [G.num_str(cad_area / (k * k), da, th)])
    return rows, total


def draw_lisp(tris, boundary, origin, cfg, rows, start_no=1):
    h = float(cfg["문자높이"])
    ll, lx = ls(cfg["선레이어"]), ls(cfg["문자레이어"])
    edges = set()
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        edges.add((round(a[0], 6), round(a[1], 6), round(b[0], 6), round(b[1], 6)))
        edges.add((round(b[0], 6), round(b[1], 6), round(a[0], 6), round(a[1], 6)))
    out = ['(bc:ensure-layer "%s" 4) (bc:ensure-layer "%s" 7)' % (ll, lx)]
    drawn = set()
    for n, t in enumerate(tris, start_no):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (round(a[0], 6), round(a[1], 6), round(b[0], 6), round(b[1], 6))
            rk = (key[2], key[3], key[0], key[1])
            if key in edges or key in drawn or rk in drawn:
                continue
            drawn.add(key)
            out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (a[0], a[1], b[0], b[1], ll))
        _b, _h, _a, (p, q), apex = tri_info(t, 1.0)
        if cfg["높이선"] and not cfg["CAD면적"]:
            dx, dy = q[0] - p[0], q[1] - p[1]
            u = ((apex[0] - p[0]) * dx + (apex[1] - p[1]) * dy) / (dx * dx + dy * dy)
            f = (p[0] + u * dx, p[1] + u * dy)
            out.append('(setq _hl (bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s"))'
                       ' (if (tblsearch "LTYPE" "HIDDEN") (vla-put-Linetype (vlax-ename->vla-object _hl) "HIDDEN"))'
                       % (apex[0], apex[1], f[0], f[1], ll))
        cx, cy = (t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3
        no = "%s%d" % (cfg["번호머리"], n)
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (cx, cy, ls(no), h, lx))
        out.append('(bc:circle (list %.6f %.6f 0.0) %.6f "%s")' % (cx, cy, max(1.1 * h, 0.4 * h * len(no) + 0.5 * h), lx))
    widths = [8 * h] + [11 * h] * (len(rows[0]) - 1)
    code, _w, _hh = TB.table_lisp(rows, origin, widths, 3 * h, h, cfg["문자레이어"], cfg["표선레이어"])
    out.append(code)
    return "".join(out)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "구적도 그리기", size="500x560")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="닫힌 경계 선택 → 표 넣을 점 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(setq _s (entsel "\\n닫힌 경계(폴리선) 선택: ")) (if _s (progn (setq _ss (ssadd (car _s))) %s'
                ' (setq _p (getpoint "\\n구적표 넣을 점(왼쪽 위) 지정: ")) (if _p (progn (setq _p (trans _p 1 0))'
                ' (write-line (strcat "O" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp)))))' % G.GEO_LISP)
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        org = [r.split("\t") for r in rows or [] if r.startswith("O\t")]
        ents = G.parse(rows or [])
        if not org or not ents:
            return
        e = ents[0]
        if not e["closed"]:
            self.error("닫힌 폴리선을 고르세요.")
            return
        try:
            poly = G.polygon(e["pieces"])
            tris = triangulate(poly)
        except ValueError as ex:
            self.error(str(ex))
            return
        trows, total = table_rows(tris, cfg, e["area"])
        code = draw_lisp(tris, poly, (float(org[0][1]), float(org[0][2])), cfg, trows)
        if self.in_cad(self.acad.lisp_undo, code, 120) is not None:
            self.status("삼각형 %d개, 구적 면적 %s㎡" % (len(tris), G.num_str(total, int(cfg["면적소수"]))))


def main():
    Window().mainloop()
