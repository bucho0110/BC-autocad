# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""GSE 종단 계획고 찾기 — 종단면도의 계획선(폴리선)에서 원하는 측점들의 계획고를 찾는다.

EL은 높이를 아는 점 하나와 그 EL로, 측점은 계획선 왼쪽 끝 = 시작 거리(또는 측점을 아는 점)로 정한다.
측점은 입력 목록(엑셀 측점 목록 포함) 또는 간격마다. 찾은 값은 표로 돌려주고, 설정하면 종단에 세로선·문자를 쓴다.
x_of()·rows_from_hits()·draw_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.common import vprof as V
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "GSE"
MODES = ["엑셀 측점 목록", "간격마다"]
FIELDS = [
    ("방식", "찾을 측점", "choice", MODES[0], MODES),
    ("측점구분", "측점 표기 구분", "choice", "Station", ["Station", "Number"]),
    ("체인", "Number 측점 한 체인 길이 (m)", "real", 20.0, None),
    ("시작거리", "계획선 왼쪽 끝의 측점 (숫자 또는 0+000)", "str", "0", None),
    ("간격", "간격마다 방식의 간격 (m)", "real", 20.0, None),
    ("H축척", "종단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "종단 V 축척", "real", 200.0, None),
    ("소수", "계획고 소수 자리", "int", 3, None),
    ("측점소수", "+측점 소수 자리", "int", 3, None),
    ("도면표기", "찾은 값 종단에 쓰기", "bool", False, None),
    ("엑셀표기", "엑셀 측점 목록 옆 칸(또는 선택 셀)에 쓰기", "bool", True, None),
    ("머리말", "도면 문자 머리말 (예 FH=)", "str", "FH=", None),
    ("문자높이", "도면 문자 높이", "real", 2.5, None),
    ("선길이", "도면 세로선 길이 (도면 단위)", "real", 10.0, None),
    ("레이어", "도면 표기 레이어", "str", "종단_계획고", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def dists(cfg, stations, length):
    """측점 목록 또는 간격 → 누가거리 목록(계획선 왼쪽 끝 기준 m, 범위 밖 포함)."""
    start = V.start_of(cfg)
    if stations:
        out = []
        for s in stations:
            d = s if isinstance(s, (int, float)) else C.station_to_dist(str(s).strip(), cfg["측점구분"], float(cfg["체인"]))
            if d is None:
                raise ValueError("측점을 읽지 못했습니다: %r" % (s,))
            out.append(float(d) - start)
        return out
    iv = float(cfg["간격"])
    if iv <= 0:
        raise ValueError("간격이 0입니다.")
    out, k = [], int(-(-start // iv))
    while k * iv - start <= length + 1e-9:
        out.append(k * iv - start)
        k += 1
    return out


def hits_lisp(handle_expr, xs, ymin, ymax):
    """계획선과 세로선 x마다 교점(가장 위) → H<탭>k<탭>x<탭>y."""
    return ('(setq _pl %s _k 0) (foreach _x (list %s) (setq _h (bc:hits (list _x %.6f 0.0) (list _x %.6f 0.0) _pl))'
            ' (if _h (progn (setq _h (car (vl-sort _h (function (lambda (a b) (> (cadr a) (cadr b)))))))'
            ' (write-line (strcat "H" _d (itoa _k) _d (bc:rtos (car _h) 2 10) _d (bc:rtos (cadr _h) 2 10)) _fp)))'
            ' (setq _k (1+ _k)))' % (handle_expr, " ".join("%.8f" % x for x in xs), ymin, ymax))


BBOX_LISP = ('(setq _bb (bc:cr-box _pl)) (write-line (strcat "BB" _d (bc:rtos (car (car _bb)) 2 10) _d (bc:rtos (cadr (car _bb)) 2 10)'
             ' _d (bc:rtos (car (cadr _bb)) 2 10) _d (bc:rtos (cadr (cadr _bb)) 2 10)) _fp)')


def rows_from_hits(ds, hits, base_point, base_el, cfg):
    """→ [[측점, 누가거리, 계획고]] (선 밖은 계획고 빈칸), 그리고 표기할 점 [(x, y, 문자)]."""
    uv = 1000.0 / cfg["V축척"]
    start = V.start_of(cfg)
    hm = {int(c[1]): (float(c[2]), float(c[3])) for c in (r.split("\t") for r in hits) if c[0] == "H"}
    rows, marks = [], []
    for k, d in enumerate(ds):
        sta = V.sta_label(start + d, cfg)
        if k in hm:
            z = float(base_el) + (hm[k][1] - float(base_point[1])) / uv
            rows.append([sta, C.fmt(start + d, 3), C.fmt(z, int(cfg["소수"]))])
            marks.append((hm[k][0], hm[k][1], "%s%s" % (cfg["머리말"], C.fmt(z, int(cfg["소수"])))))
        else:
            rows.append([sta, C.fmt(start + d, 3), ""])
    return rows, marks


def draw_lisp(marks, cfg):
    lay = ls(cfg["레이어"])
    h, L = float(cfg["문자높이"]), float(cfg["선길이"])
    out = ['(bc:ensure-layer "%s" 2)' % lay]
    for x, y, s in marks:
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (x, y, x, y + L, lay))
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "BL" %.10f)' % (x - 0.3 * h, y + 0.5 * h, ls(s), h, lay, 1.5707963268))
    return "".join(out)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "종단 계획고 찾기", size="540x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀 측점 목록 방식은 엑셀에서 측점 칸(한 열)을 먼저 고르세요. 결과는 바로 오른쪽 칸에 씁니다.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=500, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="계획선 선택 → EL 아는 점 → EL 입력", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            stations, ws = None, None
            if cfg["방식"] == MODES[0]:
                ws, r0, c0 = X.active_cell()
                stations = [r[0] for r in X.selection_values() if r and r[0] not in (None, "")]
                if not stations:
                    raise ValueError("엑셀에서 측점 칸을 고르세요.")
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        body = ('(setq _s (entsel "\\n계획선(폴리선) 선택: ")) (if _s (progn (setq _pl (car _s)) %s'
                ' (setq _b (getpoint "\\nEL을 아는 점 지정: ")) (if _b (progn (setq _b (trans _b 1 0))'
                ' (setq _z (getreal "\\n그 점의 EL: ")) (if _z (write-line (strcat "B" _d (cdr (assoc 5 (entget _pl))) _d'
                ' (bc:rtos (car _b) 2 10) _d (bc:rtos (cadr _b) 2 10) _d (bc:rtos _z 2 10)) _fp))))))' % BBOX_LISP)
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        b = [r.split("\t") for r in rows or [] if r.startswith("B\t")]
        bb = [r.split("\t") for r in rows or [] if r.startswith("BB\t")]
        if not b or not bb:
            return
        x0, y0, x1, y1 = (float(v) for v in bb[0][1:5])
        uh = 1000.0 / cfg["H축척"]
        try:
            ds = dists(cfg, stations, (x1 - x0) / uh)
        except ValueError as e:
            self.error(str(e))
            return
        bp, bel = (float(b[0][2]), float(b[0][3])), float(b[0][4])
        hits = self.acad.lisp(hits_lisp('(handent "%s")' % b[0][1], [x0 + d * uh for d in ds], y0 - 1, y1 + 1), 60)
        table, marks = rows_from_hits(ds, hits, bp, bel, cfg)
        if cfg["도면표기"] and marks:
            self.in_cad(self.acad.lisp_undo, draw_lisp(marks, cfg), 60)
        if cfg["엑셀표기"]:
            try:
                if ws is not None:
                    X.write_rows(ws, r0, c0 + 1, [[r[2]] for r in table], autofit=False)
                else:
                    ws, r0, c0 = X.active_cell()
                    X.write_rows(ws, r0, c0, [["측점", "누가거리", "계획고"]] + table)
            except X.ExcelNotReady as e:
                self.error(str(e))
        self.status("측점 %d개 중 %d개의 계획고를 찾았습니다." % (len(table), len(marks)))


def main():
    Window().mainloop()
