# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CPL 폴리선 상호 변환 — 고른 폴리선(경량 폴리선·2D 폴리선·3D 폴리선)을 다른 형식으로 바꾼다.

Z 유지: 3D → 2D·경량은 첫 정점 Z를 고도로, 2D·경량 → 3D는 고도를 모든 정점 Z로. 끄면 Z 0.
3D 폴리선은 호(볼록)를 가질 수 없어 호 구간을 각도 간격으로 잘게 나눈다.
변환한 폴리선에 레이어·색을 따로 줄 수 있다. convert_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CPL"
TARGETS = ["폴리선(경량)", "2D 폴리선", "3D 폴리선"]
FIELDS = [
    ("변환", "바꿀 형식", "choice", TARGETS[0], TARGETS),
    ("원본삭제", "변환 후 원본 지우기", "bool", True, None),
    ("Z유지", "원본 Z 유지", "bool", True, None),
    ("호각도", "3D로 바꿀 때 호 나누는 각 (도)", "real", 5.0, None),
    ("특성변경", "변환한 폴리선 레이어·색 바꾸기", "bool", False, None),
    ("레이어", "바꿀 레이어", "str", "변환폴리선", None),
    ("색", "바꿀 색 (ACI, 256 = ByLayer)", "int", 256, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

# P<탭>핸들<탭>종류<탭>닫힘<탭>3D여부 , V<탭>x<탭>y<탭>z<탭>bulge (WCS, LWPOLYLINE은 고도를 z로)
DUMP_LISP = (
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)) _f (cdr (assoc 70 _ed)))'
    ' (write-line (strcat "P" _d (cdr (assoc 5 _ed)) _d _ty _d (if (= 1 (logand 1 _f)) "1" "0") _d'
    '  (if (and (= _ty "POLYLINE") (= 8 (logand 8 _f))) "1" "0")) _fp)'
    ' (cond ((= _ty "LWPOLYLINE") (setq _z (if (assoc 38 _ed) (cdr (assoc 38 _ed)) 0.0) _v nil)'
    '   (foreach _g _ed (cond ((= (car _g) 10) (setq _v (cons (list (trans (list (cadr _g) (caddr _g) _z) _en 0) 0.0) _v)))'
    '                         ((and (= (car _g) 42) _v) (setq _v (cons (list (car (car _v)) (cdr _g)) (cdr _v))))))'
    '   (foreach _p (reverse _v) (write-line (strcat "V" _d (bc:rtos (car (car _p)) 2 10) _d (bc:rtos (cadr (car _p)) 2 10) _d'
    '    (bc:rtos (caddr (car _p)) 2 10) _d (bc:rtos (cadr _p) 2 12)) _fp)))'
    '  ((= _ty "POLYLINE") (setq _x (entnext _en))'
    '   (while (and _x (= (cdr (assoc 0 (entget _x))) "VERTEX"))'
    '    (if (zerop (logand 16 (cdr (assoc 70 (entget _x))))) (progn (setq _p (trans (cdr (assoc 10 (entget _x))) _en 0))'
    '     (write-line (strcat "V" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10) _d (bc:rtos (caddr _p) 2 10) _d'
    '      (bc:rtos (if (assoc 42 (entget _x)) (cdr (assoc 42 (entget _x))) 0.0) 2 12)) _fp)))'
    '    (setq _x (entnext _x))))))')


def parse(rows):
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "P":
            out.append({"handle": c[1], "type": c[2], "closed": c[3] == "1", "is3d": c[4] == "1", "v": []})
        elif c[0] == "V" and out:
            out[-1]["v"].append((float(c[1]), float(c[2]), float(c[3]), float(c[4])))
    return out


def kind_of(p):
    return TARGETS[2] if p["is3d"] else TARGETS[1] if p["type"] == "POLYLINE" else TARGETS[0]


def _densify(v, closed, step):
    """호 구간을 잘게 나눈 정점(볼록 0). z는 구간 앞 정점 z."""
    out = []
    n = len(v)
    for i in range(n if closed else n - 1):
        p, q = v[i], v[(i + 1) % n]
        out.append((p[0], p[1], p[2], 0.0))
        if abs(p[3]) > 1e-12:
            pts = G.polygon([((p[0], p[1]), (q[0], q[1]), p[3])], step)[1:]
            out += [(x, y, p[2], 0.0) for x, y in pts]
    if not closed:
        out.append((v[-1][0], v[-1][1], v[-1][2], 0.0))
    return out


def convert_lisp(polys, cfg):
    """→ (LISP, 바꾼 수). 같은 형식은 건너뛴다."""
    tgt = cfg["변환"]
    out, n = [], 0
    for p in polys:
        if kind_of(p) == tgt or len(p["v"]) < 2:
            continue
        v = p["v"]
        if not cfg["Z유지"]:
            v = [(x, y, 0.0, b) for x, y, _z, b in v]
        props = ('(vl-remove-if-not (function (lambda (g) (member (car g) (list 8 62 6 48 370 420)))) (entget (handent "%s")))'
                 % p["handle"])
        if cfg["특성변경"]:
            props = '(list (cons 8 "%s") (cons 62 %d))' % (ls(cfg["레이어"]), int(cfg["색"]))
        if tgt == TARGETS[0]:
            z = v[0][2]
            body = " ".join("(cons 10 (list %.10f %.10f)) (cons 42 %.12f)" % (x, y, b) for x, y, _z, b in v)
            out.append('(entmake (append (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity")) %s (list (cons 100 "AcDbPolyline")'
                       ' (cons 90 %d) (cons 70 %d) (cons 38 %.10f) %s)))' % (props, len(v), 1 if p["closed"] else 0, z, body))
        elif tgt == TARGETS[1]:
            z = v[0][2]
            out.append('(entmake (append (list (cons 0 "POLYLINE") (cons 100 "AcDbEntity")) %s (list (cons 100 "AcDb2dPolyline")'
                       ' (cons 66 1) (list 10 0.0 0.0 %.10f) (cons 70 %d))))' % (props, z, 1 if p["closed"] else 0))
            for x, y, _z, b in v:
                out.append('(entmake (list (cons 0 "VERTEX") (cons 100 "AcDbEntity") (cons 100 "AcDbVertex") (cons 100 "AcDb2dVertex")'
                           ' (list 10 %.10f %.10f %.10f) (cons 42 %.12f) (cons 70 0)))' % (x, y, z, b))
            out.append('(entmake (list (cons 0 "SEQEND")))')
        else:
            if p["type"] == "LWPOLYLINE" or not p["is3d"]:
                v = [(x, y, v[0][2], b) for x, y, _z, b in v]  # 2D는 고도 하나
            vv = _densify(v, p["closed"], float(cfg["호각도"]))
            out.append('(entmake (append (list (cons 0 "POLYLINE") (cons 100 "AcDbEntity")) %s (list (cons 100 "AcDb3dPolyline")'
                       ' (cons 66 1) (list 10 0.0 0.0 0.0) (cons 70 %d))))' % (props, 8 | (1 if p["closed"] else 0)))
            for x, y, z, _b in vv:
                out.append('(entmake (list (cons 0 "VERTEX") (cons 100 "AcDbEntity") (cons 100 "AcDbVertex") (cons 100 "AcDb3dPolylineVertex")'
                           ' (list 10 %.10f %.10f %.10f) (cons 70 32)))' % (x, y, z))
            out.append('(entmake (list (cons 0 "SEQEND")))')
        if cfg["원본삭제"]:
            out.append('(entdel (handent "%s"))' % p["handle"])
        n += 1
    if cfg["특성변경"]:
        out.insert(0, '(bc:ensure-layer "%s" 7)' % ls(cfg["레이어"]))
    return "".join(out), n


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "폴리선 상호 변환", size="480x420")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="폴리선 선택 → 변환", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n폴리선 선택: ") (setq _ss (ssget (list (cons 0 "LWPOLYLINE,POLYLINE")))) %s'
                           % DUMP_LISP, A.PICK_TIMEOUT)
        if rows is None:
            return
        code, n = convert_lisp(parse(rows), cfg)
        if code and self.in_cad(self.acad.lisp_undo, code, 120) is None:
            return
        self.status("%d개를 %s(으)로 바꿨습니다." % (n, cfg["변환"]))


def main():
    Window().mainloop()
