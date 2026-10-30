# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""JJJ 선 결합 — 고른 선·호·폴리선 중 끝점이 맞닿은 것끼리 이어 폴리선 하나로 만든다(여러 묶음이면 묶음마다).

닫힌 폴리선과 3D 폴리선은 건너뛴다. 높이(Z)가 다른 것끼리는 잇지 않는다. 끝점이 허용오차 안이면 맞닿은 것으로 본다.
새 폴리선의 레이어·색·선종류는 묶음의 첫 객체를 따른다. 처음과 끝이 만나면 닫는다.
chains()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui

CMD = "JJJ"
FIELDS = [
    ("허용오차", "끝점이 맞닿았다고 볼 거리 (도면 단위)", "real", 0.0001, None),
    ("하나도변환", "이을 것이 없는 선·호도 폴리선으로", "bool", False, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
TYPES = "LINE,ARC,LWPOLYLINE"


def _rev(pieces):
    return [(q, p, -b) for p, q, b in reversed(pieces)]


def chains(ents, tol):
    """→ [(핸들 목록, 구간 목록, 닫힘)] — 둘 이상 이은 묶음(또는 하나)."""
    items = [e for e in ents if e["pieces"] and not e["closed"]]
    used = set()

    def near(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol

    def first(pcs):
        return pcs[0][0]

    def last(pcs):
        return pcs[-1][1]

    out = []
    for e in items:
        if e["handle"] in used:
            continue
        used.add(e["handle"])
        hs, pcs = [e["handle"]], list(e["pieces"])
        grown = True
        while grown:
            grown = False
            for f in items:
                if f["handle"] in used or abs(f["elev"] - e["elev"]) > tol:
                    continue
                fp = f["pieces"]
                if near(last(pcs), first(fp)):
                    pcs += fp
                elif near(last(pcs), last(fp)):
                    pcs += _rev(fp)
                elif near(first(pcs), last(fp)):
                    pcs = fp + pcs
                elif near(first(pcs), first(fp)):
                    pcs = _rev(fp) + pcs
                else:
                    continue
                used.add(f["handle"])
                hs.append(f["handle"])
                grown = True
        out.append((hs, pcs, len(pcs) > 1 and near(first(pcs), last(pcs))))
    return out


def chain_lisp(hs, pcs, closed, elev):
    """첫 객체의 레이어·색·선종류로 LWPOLYLINE을 만들고 원본을 지운다."""
    vs = [p for p, _q, _b in pcs] + ([] if closed else [pcs[-1][1]])
    bs = [b for _p, _q, b in pcs] + ([] if closed else [0.0])
    body = " ".join("(cons 10 (list %.10f %.10f)) (cons 42 %.12f)" % (p[0], p[1], b) for p, b in zip(vs, bs))
    keep = "(vl-remove-if-not (function (lambda (g) (member (car g) (list 8 62 6 48 370 420)))) (entget (handent \"%s\")))" % hs[0]
    return ('(entmake (append (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity")) %s'
            ' (list (cons 100 "AcDbPolyline") (cons 90 %d) (cons 70 %d) (cons 38 %.10f) %s)))'
            ' (foreach _h (list %s) (if (handent _h) (entdel (handent _h))))'
            % (keep, len(vs), 1 if closed else 0, elev, body, " ".join('"%s"' % h for h in hs)))


def build(ents, cfg):
    by = {e["handle"]: e for e in ents}
    code, n = [], 0
    for hs, pcs, closed in chains(ents, float(cfg["허용오차"])):
        if len(hs) < 2 and not (cfg["하나도변환"] and by[hs[0]]["type"] in ("LINE", "ARC")):
            continue
        code.append(chain_lisp(hs, pcs, closed, by[hs[0]]["elev"]))
        n += 1
    return "".join(code), n


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "선 결합", size="460x260")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="선·호·폴리선 선택 → 결합", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n결합할 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s'
                           % (TYPES, G.GEO_LISP), A.PICK_TIMEOUT)
        if rows is None:
            return
        code, n = build(G.parse(rows), cfg)
        if code and self.in_cad(self.acad.lisp_undo, code, 120) is None:
            return
        self.status("폴리선 %d개로 결합했습니다." % n)


def main():
    Window().mainloop()
