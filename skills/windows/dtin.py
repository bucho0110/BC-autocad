"""DTIN 삼각망 그리기 — Z가 있는 점·블록·선 정점(또는 EL 문자)으로 들로네 삼각망(3D면)을 만든다.

triangulate()는 표준 라이브러리만 쓰는 Bowyer-Watson이다(점 수천 개까지 수 초).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DTIN"
FIELDS = [
    ("대상점", "점(Point)", "bool", True, None),
    ("대상블록", "블록 삽입점", "bool", True, None),
    ("대상선", "선·폴리선 정점", "bool", True, None),
    ("대상문자", "문자 (삽입점, 숫자를 Z로)", "bool", False, None),
    ("Z0제외", "Z=0 점 제외", "bool", True, None),
    ("최대변", "최대 변 길이 (0=제한 없음)", "real", 0.0, None),
    ("레이어", "삼각망 레이어", "str", "TIN", None),
    ("색", "레이어 색 (ACI)", "int", 8, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def triangulate(pts):
    """pts [(x,y,z)] → 삼각형 [(i,j,k)] (반시계). 같은 XY 점은 앞의 것만 쓴다."""
    seen, P = {}, []
    for p in pts:
        k = (round(p[0], 6), round(p[1], 6))
        if k not in seen:
            seen[k] = len(P)
            P.append(p)
    n = len(P)
    if n < 3:
        return P, []
    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    mx, my = min(xs), min(ys)
    d = max(max(xs) - mx, max(ys) - my) or 1.0
    cx, cy = mx + d / 2, my + d / 2
    big = d * 20
    V = [(p[0], p[1]) for p in P] + [(cx - big, cy - big), (cx + big, cy - big), (cx, cy + big)]
    tris = {}

    def circ(a, b, c):
        (ax, ay), (bx, by), (cx_, cy_) = V[a], V[b], V[c]
        dd = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
        if abs(dd) < 1e-20:
            return (0.0, 0.0, float("inf"))
        ux = ((ax * ax + ay * ay) * (by - cy_) + (bx * bx + by * by) * (cy_ - ay) + (cx_ * cx_ + cy_ * cy_) * (ay - by)) / dd
        uy = ((ax * ax + ay * ay) * (cx_ - bx) + (bx * bx + by * by) * (ax - cx_) + (cx_ * cx_ + cy_ * cy_) * (bx - ax)) / dd
        return (ux, uy, (ax - ux) ** 2 + (ay - uy) ** 2)

    def add(a, b, c):
        (ax, ay), (bx, by), (cx_, cy_) = V[a], V[b], V[c]
        if (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax) < 0:
            b, c = c, b
        tris[(a, b, c)] = circ(a, b, c)

    add(n, n + 1, n + 2)
    order = sorted(range(n), key=lambda i: (V[i][0], V[i][1]))
    for i in order:
        x, y = V[i]
        bad = [t for t, (ux, uy, r2) in tris.items() if (x - ux) ** 2 + (y - uy) ** 2 < r2 * (1 + 1e-12)]
        edges = {}
        for t in bad:
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                k = tuple(sorted(e))
                edges[k] = edges.get(k, 0) + 1
            del tris[t]
        for (a, b), cnt in edges.items():
            if cnt == 1:
                add(a, b, i)
    out = [t for t in tris if max(t) < n]
    return P, out


def filter_long(P, tris, maxlen):
    if not maxlen or maxlen <= 0:
        return tris
    def L(a, b):
        return math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1])
    return [t for t in tris if max(L(t[0], t[1]), L(t[1], t[2]), L(t[2], t[0])) <= maxlen]


def faces_lisp(P, tris, layer, color, start=0, count=None) -> str:
    lay = ls(layer)
    s = ['(bc:ensure-layer "%s" %d)' % (lay, int(color))]
    for a, b, c in tris[start:(start + count) if count else None]:
        pa, pb, pc = P[a], P[b], P[c]
        s.append('(entmake (list (quote (0 . "3DFACE")) (cons 8 "%s") (list 10 %.6f %.6f %.6f) (list 11 %.6f %.6f %.6f)'
                 ' (list 12 %.6f %.6f %.6f) (list 13 %.6f %.6f %.6f)))'
                 % (lay, pa[0], pa[1], pa[2], pb[0], pb[1], pb[2], pc[0], pc[1], pc[2], pc[0], pc[1], pc[2]))
    return "".join(s)


def points_from_dump(ents, cfg):
    pts = []
    for e in ents:
        if e["type"] in ("TEXT", "MTEXT"):
            if not cfg["대상문자"]:
                continue
            import re
            # 맨 뒤 숫자. 'EL.(-)1.50'처럼 괄호 부호도 LISP bc:num-in-text와 같게 읽는다
            m = list(re.finditer(r"(\(-\)|-)?(\d+(?:\.\d+)?)", e["text"].replace(",", "")))
            if not m:
                continue
            z = float(m[-1].group(2)) * (-1.0 if m[-1].group(1) else 1.0)
            pts += [(p[0], p[1], z) for p in e["points"]]
        else:
            pts += e["points"]
    if cfg["Z0제외"]:
        pts = [p for p in pts if abs(p[2]) > 1e-9]
    return pts


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "삼각망 그리기", size="520x460")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="도면에서 객체 선택 → 삼각망 만들기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        types = []
        if cfg["대상점"]:
            types.append("POINT")
        if cfg["대상블록"]:
            types.append("INSERT")
        if cfg["대상선"]:
            types.append("LINE,LWPOLYLINE,POLYLINE")
        if cfg["대상문자"]:
            types.append("TEXT,MTEXT")
        if not types:
            self.error("대상을 하나 이상 고르세요.")
            return
        body = ('(princ "\\n삼각망 만들 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) (bc:dump-ss _ss nil _fp)'
                % ",".join(types))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if rows is None:
            return
        pts = points_from_dump(C.parse_dump(rows), cfg)
        self.status("점 %d개로 삼각망 계산 중..." % len(pts))
        P, tris = triangulate(pts)
        tris = filter_long(P, tris, cfg["최대변"])
        if not tris:
            self.error("삼각형을 만들 수 없습니다(점이 3개 미만이거나 한 줄 위).")
            return
        if self.in_cad(self._draw_all, P, tris, cfg) is None:
            return
        self.status("점 %d개, 삼각형 %d개를 만들었습니다(레이어 %s)." % (len(P), len(tris), cfg["레이어"]))

    def _draw_all(self, P, tris, cfg, step=1500):
        """배치를 나눠 그려도 UNDO는 한 번."""
        with self.acad.undo_group():
            for i in range(0, len(tris), step):
                self.acad.lisp(faces_lisp(P, tris, cfg["레이어"], cfg["색"], i, step), 120)
        return True


def main():
    Window().mainloop()
