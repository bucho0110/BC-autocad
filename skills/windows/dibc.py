"""DIBC 선형 이격 거리 조회 — 기준 선형의 측점마다 수직선을 그어 다른 선들과의 거리(좌 +, 우 −)를 잰다.

하폭·제방 간격처럼 측점별 폭을 엑셀로 뽑을 때 쓴다. table()은 창 없이도 쓴다(MCP run_skill).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.windows import dsta

CMD = "DIBC"
FIELDS = [
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("간격", "조회 간격 (m)", "real", 20.0, None),
    ("축척", "축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("시작거리", "선형 시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("000유지", "0+000 형식 유지 (Station)", "bool", True, None),
    ("머리말", "측점 머리말", "str", "", None),
    ("소수", "측점 소수 자리", "int", 0, None),
    ("거리소수", "거리 소수 자리", "int", 3, None),
    ("부호", "좌(+)·우(−) 부호 붙이기", "bool", True, None),
    ("합계", "모든 선 거리 합(폭) 열 추가", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
# dsta.label·plan이 읽는 키를 맞춘다
_DSTA_KEYS = {"km만": False, "플러스0생략": False}


def hit_body(h, rev, dds, others) -> str:
    return ('(setq _al (handent "%s") _ot (mapcar (quote handent) (list %s)))'
            ' (foreach _dd (list %s) (setq _p (bc:curve-pt _al _dd %s) _a (bc:curve-ang _al _dd %s))'
            ' (write-line (strcat "H\\t" (bc:rtos _dd 2 10) (apply (quote strcat) (mapcar (quote (lambda (r) (if r (strcat "\\t" (bc:rtos (car r) 2 10) "\\t" (itoa (cadr r))) "\\t\\t"))) (bc:normal-hit _p _a _ot _al)))) _fp))'
            % (h, " ".join('"%s"' % o for o in others), " ".join("%.10f" % d for d in dds),
               "T" if rev else "nil", "T" if rev else "nil"))


def table(rows, items, n_other, cfg):
    """LISP H 줄 → 표(머리글 포함)."""
    cfg2 = dict(cfg, **_DSTA_KEYS)
    k = dsta.upm(cfg2)
    hits = {}
    for r in rows:
        c = r.split("\t")
        if c[0] == "H":
            hits[round(float(c[1]), 6)] = c[2:]
    head = ["측점", "누가거리"] + ["선%d" % (i + 1) for i in range(n_other)] + (["합계"] if cfg["합계"] else [])
    out = [head]
    for dd, d, _kind in items:
        c = hits.get(round(dd, 6), [])
        vals, tot = [], 0.0
        for i in range(n_other):
            dist = c[2 * i] if 2 * i < len(c) else ""
            side = c[2 * i + 1] if 2 * i + 1 < len(c) else ""
            if dist == "":
                vals.append("")
                continue
            v = float(dist) / k
            tot += v
            if cfg["부호"] and side == "-1":
                v = -v
            vals.append(C.fmt(v, cfg["거리소수"]))
        row = [dsta.label(d, cfg2), C.fmt(d, 4)] + vals
        if cfg["합계"]:
            # 한 선이라도 그 측점 옆에 없으면 폭이 아니므로 비운다(0이나 일부 합으로 쓰면 폭으로 읽힌다)
            row.append(C.fmt(tot, cfg["거리소수"]) if vals and all(v != "" for v in vals) else "")
        out.append(row)
    return out


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "선형 이격 거리 조회", size="560x520")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="기준 선형 → 다른 선들 선택 → 엑셀(선택 셀부터)", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            ws, r0, c0 = X.active_cell()
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        body = ('(setq _a (bc:pick-align "기준 선형 선택"))'
                ' (if _a (progn (write-line (strcat "A\\t" (cdr (assoc 5 (entget (car _a)))) "\\t" (if (cadr _a) "1" "0")'
                ' "\\t" (bc:rtos (bc:curve-len (car _a)) 2 10)) _fp)'
                ' (princ "\\n거리를 잴 다른 선들 선택: ")'
                ' (setq _ss (ssget (list (cons 0 "LINE,LWPOLYLINE,POLYLINE,ARC,SPLINE"))) _i 0)'
                ' (if _ss (while (< _i (sslength _ss)) (if (not (eq (ssname _ss _i) (car _a)))'
                ' (write-line (strcat "O\\t" (cdr (assoc 5 (entget (ssname _ss _i))))) _fp)) (setq _i (1+ _i))))))')
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or []
        a = [x.split("\t") for x in rows if x.startswith("A\t")]
        others = [x.split("\t")[1] for x in rows if x.startswith("O\t")]
        if not a or not others:
            self.status("기준 선형과 다른 선을 모두 골라야 합니다.")
            return
        h, rev, L = a[0][1], a[0][2] == "1", float(a[0][3])
        cfg2 = dict(cfg, **_DSTA_KEYS)
        items = dsta.plan(L, cfg2)
        res = self.in_cad(self.acad.lisp, hit_body(h, rev, [i[0] for i in items], others), 120)
        if res is None:
            return
        out = table(res, items, len(others), cfg)
        X.write_rows(ws, r0, c0, out)
        self.status("측점 %d개 × 선 %d개를 엑셀에 썼습니다." % (len(out) - 1, len(others)))


def main():
    Window().mainloop()
