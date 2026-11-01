# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CCON 표고점으로 등고선 그리기 — Z 값이 있는 점·블록·선 정점·EL 문자(또는 이미 만든 삼각망 3D면)로 주곡선·계곡선을 그린다.

등고선은 고도(Z)를 가진 LWPOLYLINE이다. build()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import terrain as T
from skills.common import ui
from skills.windows import dtin
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CCON"
FIELDS = [
    ("방식", "등고선 바탕", "choice", "점에서 삼각망", ["점에서 삼각망", "3D면(삼각망) 선택"]),
    ("대상점", "점(Point)", "bool", True, None),
    ("대상블록", "블록 삽입점", "bool", True, None),
    ("대상선", "선·폴리선 정점", "bool", True, None),
    ("대상문자", "문자 (삽입점, 숫자를 Z로)", "bool", False, None),
    ("레이어필터", "이 레이어 객체만 (쉼표로 여럿, 비우면 전체)", "str", "", None),
    ("Z0제외", "Z 0 이하 제외", "bool", True, None),
    ("주곡선간격", "주곡선 간격 (m)", "real", 1.0, None),
    ("계곡선간격", "계곡선 간격 (m)", "real", 5.0, None),
    ("주곡선레이어", "주곡선 레이어", "str", "등고선_주곡선", None),
    ("주곡선색", "주곡선 색 (ACI)", "int", 8, None),
    ("계곡선레이어", "계곡선 레이어", "str", "등고선_계곡선", None),
    ("계곡선색", "계곡선 색 (ACI)", "int", 3, None),
    ("외측최소화", "불필요 외측 등고선 최소화 (0=안 함, 1~5)", "real", 0.0, None),
    ("단순화", "등고선 단순화 단계 (0=안 함, 1~5)", "int", 0, None),
    ("특정높이", "이 높이만 그리기 (쉼표로 여럿, 비우면 간격대로)", "str", "", None),
    ("삼각망생성", "삼각망(3D면)도 함께 만들기", "bool", False, None),
    ("삼각망레이어", "삼각망 레이어", "str", "TIN", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
FACE_LISP = ('(if _ss (progn (setq _i 0) (while (< _i (sslength _ss)) (setq _ed (entget (ssname _ss _i)) _i (1+ _i))'
             ' (foreach _g (list 10 11 12 13) (setq _p (cdr (assoc _g _ed)))'
             ' (write-line (strcat "F" _d (itoa _g) _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10) _d'
             ' (bc:rtos (caddr _p) 2 10)) _fp)))))')


def slack_of(level):
    """최소화 단계 1~5 → 바깥 다듬기 여유(중간 변 길이 배수). 클수록 많이 걷는다."""
    lv = max(1.0, min(5.0, float(level)))
    return 8.0 - (lv - 1.0) * 1.5


def select_lisp(cfg) -> str:
    """사람이 고르는 선택 집합 _ss."""
    if cfg["방식"] != "점에서 삼각망":
        return '(princ "\\n삼각망 3D면 선택: ") (setq _ss (ssget (list (cons 0 "3DFACE"))))'
    flt = '(cons 0 "%s")' % T.types_for(cfg)
    if cfg["레이어필터"].strip():
        flt += ' (cons 8 "%s")' % ls(cfg["레이어필터"].replace(" ", ""))
    return '(princ "\\n등고선 만들 객체 선택: ") (setq _ss (ssget (list %s)))' % flt


def dump_lisp(cfg) -> str:
    return FACE_LISP if cfg["방식"] != "점에서 삼각망" else "(bc:dump-ss _ss nil _fp)"


def faces_from_rows(rows):
    """FACE_LISP 결과 → (P, tris). 같은 점은 하나로 묶는다."""
    idx, P, tris, cur = {}, [], [], []
    for r in rows:
        c = r.split("\t")
        if c[0] != "F":
            continue
        p = (float(c[2]), float(c[3]), float(c[4]))
        k = (round(p[0], 6), round(p[1], 6))
        if k not in idx:
            idx[k] = len(P)
            P.append(p)
        cur.append(idx[k])
        if c[1] == "13":
            t = cur[:3]
            if len(set(t)) == 3:
                (ax, ay, _), (bx, by, _), (cx, cy, _) = P[t[0]], P[t[1]], P[t[2]]
                if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
                    t = [t[0], t[2], t[1]]
                tris.append(tuple(t))
            cur = []
    return P, tris


def surface(rows, cfg):
    """덤프 결과 → (P, tris). 점이면 삼각망을 만들고 바깥을 다듬는다."""
    if cfg["방식"] != "점에서 삼각망":
        return faces_from_rows(rows)
    P, tris = dtin.triangulate(T.z_points(C.parse_dump(rows), cfg))
    if cfg["외측최소화"] > 0:
        tris = T.peel(P, tris, slack_of(cfg["외측최소화"]))
    return P, tris


def parse_only(s):
    return [float(v) for v in str(s).replace(" ", "").split(",") if v.strip()]


def build(P, tris, cfg):
    """(LISP 목록, 요약). 목록은 나눠 보낼 묶음들."""
    if not tris:
        raise ValueError("삼각형을 만들 수 없습니다(Z 점이 3개 미만이거나 한 줄 위).")
    zs = [p[2] for p in P]
    only = parse_only(cfg["특정높이"])
    main, index = float(cfg["주곡선간격"]), float(cfg["계곡선간격"])
    lvs = T.levels(min(zs), max(zs), main, only)
    tol = cfg["단순화"] * T.median_edge(P, tris) / 50.0 if cfg["단순화"] > 0 else 0.0
    lm, li = ls(cfg["주곡선레이어"]), ls(cfg["계곡선레이어"])
    parts = ['(bc:ensure-layer "%s" %d) (bc:ensure-layer "%s" %d)' % (lm, cfg["주곡선색"], li, cfg["계곡선색"])]
    n = 0
    for lv in lvs:
        is_index = not only and index > 0 and abs(lv / index - round(lv / index)) < 1e-6
        lay = li if is_index else lm
        for pts, closed in T.contours(P, tris, lv):
            pts = T.simplify(pts, tol, closed)
            if len(pts) >= 2:
                parts.append(T.lwpoly_lisp(pts, closed, lay, lv))
                n += 1
    if cfg["삼각망생성"] and cfg["방식"] == "점에서 삼각망":
        parts.append(dtin.faces_lisp(P, tris, cfg["삼각망레이어"], 8))
    return parts, {"points": len(P), "triangles": len(tris), "levels": len(lvs), "contours": n,
                   "z_range": [round(min(zs), 4), round(max(zs), 4)]}


def chunks(parts, size=200000):
    """LISP 조각을 크기별로 묶는다."""
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > size:
            out.append(cur)
            cur = ""
        cur += p
    if cur:
        out.append(cur)
    return out


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "표고점으로 등고선 그리기", size="560x720")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="도면에서 객체 선택 → 등고선 만들기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        if cfg["방식"] == "점에서 삼각망" and not T.types_for(cfg):
            self.error("대상을 하나 이상 고르세요.")
            return
        rows = self.in_cad(self.acad.lisp, select_lisp(cfg) + dump_lisp(cfg), A.PICK_TIMEOUT)
        if rows is None:
            return
        self.status("등고선 계산 중...")
        try:
            parts, info = build(*surface(rows, cfg), cfg)
        except ValueError as e:
            self.error(str(e))
            return
        if self.in_cad(self._draw_all, parts) is None:
            return
        self.status("등고선 %d개(높이 %d개, %s ~ %s)를 그렸습니다."
                    % (info["contours"], info["levels"], info["z_range"][0], info["z_range"][1]))

    def _draw_all(self, parts):
        with self.acad.undo_group():
            for c in chunks(parts):
                self.acad.lisp(c, 180)
        return True


def main():
    Window().mainloop()
