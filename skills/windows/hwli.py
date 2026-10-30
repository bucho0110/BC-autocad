# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""HWLI 기본설계 값으로 실시설계 측점 값 보간.

기본설계 선형 위의 측점별 값(엑셀: [측점, 값1, 값2, …] — 계획홍수위·제방고 등)을,
실시설계 선형의 측점마다 그 점에서 기본설계 선형에 내린 수선의 발 위치로 선형 보간한다.
결과는 활성 통합문서의 새 시트 'HWLI_결과'에 [실시 측점, 실시 누가거리, 기본 대응 누가거리, 값1, 값2, …].
interpolate()는 창 없이도 쓴다(MCP run_skill).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.windows import dsta

CMD = "HWLI"
FIELDS = [
    ("기본측점구분", "기본설계 측점 구분", "choice", "Station", ["Station", "Number"]),
    ("기본간격", "기본설계 Number 간격 (m)", "real", 200.0, None),
    ("기본시작", "기본설계 선형 시작 거리", "str", "0", None),
    ("측점구분", "실시설계 측점 구분", "choice", "Station", ["Station", "Number"]),
    ("간격", "실시설계 측점 간격 (m)", "real", 20.0, None),
    ("시작거리", "실시설계 선형 시작 거리", "str", "0", None),
    ("축척", "축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("000유지", "0+000 형식 유지", "bool", True, None),
    ("머리말", "실시 측점 머리말", "str", "", None),
    ("소수", "실시 측점 소수 자리", "int", 0, None),
    ("값소수", "보간 값 소수 자리", "int", 3, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def base_table(rows, cfg):
    """엑셀 [측점, 값…] → [(누가거리, [값…])] 거리순, 머리글 행은 건너뜀."""
    out = []
    for r in rows:
        d = C.station_to_dist(r[0], cfg["기본측점구분"], float(cfg["기본간격"]))
        if d is None:
            continue
        out.append((d, [X.to_float(v) for v in r[1:]]))
    out.sort(key=lambda t: t[0])
    return out


def interp(tbl, d):
    """거리 d의 값 목록(양 끝 밖은 끝 값, 빈 값은 None)."""
    if not tbl:
        return []
    if d <= tbl[0][0]:
        return tbl[0][1]
    if d >= tbl[-1][0]:
        return tbl[-1][1]
    for (d1, v1), (d2, v2) in zip(tbl, tbl[1:]):
        if d1 <= d <= d2:
            t = 0.0 if d2 == d1 else (d - d1) / (d2 - d1)
            return [None if (a is None or b is None) else a + (b - a) * t for a, b in zip(v1, v2)]
    return tbl[-1][1]


def interpolate(tbl, pairs, cfg):
    """pairs: [(실시 누가거리, 기본 대응 누가거리)] → 결과 표(머리글 포함)."""
    n = max((len(v) for _d, v in tbl), default=0)
    out = [["실시 측점", "실시 누가거리", "기본 대응 누가거리"] + ["값%d" % (i + 1) for i in range(n)]]
    lab_cfg = dict(cfg, km만=False, 플러스0생략=False)
    for d, bd in pairs:
        vals = interp(tbl, bd)
        out.append([dsta.label(d, lab_cfg), C.fmt(d, 4), C.fmt(bd, 4)] +
                   ["" if v is None else C.fmt(v, cfg["값소수"]) for v in vals])
    return out


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "기본설계 값으로 실시설계 보간", size="580x600")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(body, text="엑셀에서 기본설계 [측점, 값1, 값2…] 범위를 먼저 선택하세요.", bg=ui.PANEL, fg=ui.FG,
                 font=ui.FONT).pack(fill="x", padx=8, pady=4)
        tk.Button(self, text="실행 (기본설계 선형 → 실시설계 선형 선택)", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            tbl = base_table(X.selection_values(), cfg)
            wb = X.app().ActiveWorkbook
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        if len(tbl) < 2:
            self.error("기본설계 측점·값을 두 줄 이상 읽지 못했습니다.")
            return
        k = dsta.upm(cfg)
        b0 = C.station_to_dist(cfg["기본시작"], cfg["기본측점구분"], float(cfg["기본간격"])) or 0.0
        body = ('(setq _b (bc:pick-align "기본설계 선형 선택") _s (bc:pick-align "실시설계 선형 선택"))'
                ' (if (and _b _s) (write-line (strcat "A\\t" (cdr (assoc 5 (entget (car _b)))) "\\t" (if (cadr _b) "1" "0")'
                ' "\\t" (cdr (assoc 5 (entget (car _s)))) "\\t" (if (cadr _s) "1" "0") "\\t" (bc:rtos (bc:curve-len (car _s)) 2 10)) _fp))')
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or []
        a = [x.split("\t") for x in rows if x.startswith("A\t")]
        if not a:
            return
        hb, rb, hs, rs, Ls = a[0][1], a[0][2] == "1", a[0][3], a[0][4] == "1", float(a[0][5])
        items = dsta.plan(Ls, dict(cfg, km만=False, 플러스0생략=False))
        q = ('(setq _bl (handent "%s") _sl (handent "%s"))'
             ' (foreach _dd (list %s) (setq _p (bc:curve-pt _sl _dd %s))'
             ' (write-line (strcat "M\\t" (bc:rtos _dd 2 10) "\\t" (bc:rtos (bc:curve-d _bl _p %s) 2 10)) _fp))'
             % (hb, hs, " ".join("%.10f" % i[0] for i in items), "T" if rs else "nil", "T" if rb else "nil"))
        res = self.in_cad(self.acad.lisp, q, 120)
        if res is None:
            return
        m = {round(float(r.split("\t")[1]), 6): float(r.split("\t")[2]) for r in res if r.startswith("M\t")}
        pairs = [(d, b0 + m[round(dd, 6)] / k) for dd, d, _kind in items if round(dd, 6) in m]
        out = interpolate(tbl, pairs, cfg)
        ws = wb.Worksheets.Add()
        try:
            ws.Name = "HWLI_결과"
        except Exception:
            pass
        X.write_rows(ws, 1, 1, out)
        self.status("실시 측점 %d개를 보간해 시트 '%s'에 썼습니다." % (len(out) - 1, ws.Name))


def main():
    Window().mainloop()
