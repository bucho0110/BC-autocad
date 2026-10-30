# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""ETC 엑셀 표 캐드로 — 엑셀에서 고른 범위를 선과 문자로 된 표로 그린다.

엑셀의 열 너비·행 높이·병합·가로 정렬을 따른다. 크기는 '엑셀 글꼴 크기(기준) → 도면 문자 높이' 비율로 바꾼다
(예: 11pt 글자를 높이 3으로 쓰면 1pt = 3/11 도면 단위). 숨긴 행·열은 건너뛴다.
draw_lisp()는 창 없이도 쓴다(MCP skill_run: rows, merges, widths).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import cadtable as TB
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui

CMD = "ETC"
FIELDS = [
    ("문자높이", "도면 문자 높이", "real", 3.0, None),
    ("기준글꼴", "이 엑셀 글꼴 크기(pt)를 위 문자 높이로", "real", 11.0, None),
    ("크기", "칸 크기", "choice", "엑셀 크기대로", ["엑셀 크기대로", "문자 길이에 맞춤"]),
    ("문자레이어", "문자 레이어", "str", "표_문자", None),
    ("선레이어", "선 레이어", "str", "표_선", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
_HALIGN = {-4131: "L", -4152: "R", -4108: "C", 7: "C"}  # xlLeft, xlRight, xlCenter, xlCenterAcrossSelection


def read_excel():
    """선택 범위 → (값 행, 병합, 열 너비 pt, 행 높이 pt, 정렬 {(i, j): L/C/R}). 숨긴 행·열은 뺀다."""
    xl = X.app()
    try:
        rng = xl.Selection
        r0, c0 = rng.Row, rng.Column
        nr, nc = rng.Rows.Count, rng.Columns.Count
        ws = rng.Worksheet
        rows_keep = [i for i in range(nr) if not ws.Rows(r0 + i).Hidden]
        cols_keep = [j for j in range(nc) if not ws.Columns(c0 + j).Hidden]
        vals = rng.Value
        if not isinstance(vals, tuple):
            vals = ((vals,),)
        texts = {}
        for i in rows_keep:
            for j in cols_keep:
                t = ws.Cells(r0 + i, c0 + j).Text
                texts[(i, j)] = str(t) if t is not None else ""
        widths = [float(ws.Columns(c0 + j).Width) for j in cols_keep]
        heights = [float(ws.Rows(r0 + i).Height) for i in rows_keep]
        ri = {i: k for k, i in enumerate(rows_keep)}
        ci = {j: k for k, j in enumerate(cols_keep)}
        merges, aligns, seen = [], {}, set()
        for i in rows_keep:
            for j in cols_keep:
                cell = ws.Cells(r0 + i, c0 + j)
                ha = int(cell.HorizontalAlignment) if cell.HorizontalAlignment is not None else 1
                if ha in _HALIGN:
                    aligns[(ri[i], ci[j])] = _HALIGN[ha]
                if cell.MergeCells:
                    ma = cell.MergeArea
                    key = (ma.Row, ma.Column)
                    if key in seen:
                        continue
                    seen.add(key)
                    a, b = ma.Row - r0, ma.Column - c0
                    c, d = a + ma.Rows.Count - 1, b + ma.Columns.Count - 1
                    rr = [ri[k] for k in range(a, c + 1) if k in ri]
                    cc = [ci[k] for k in range(b, d + 1) if k in ci]
                    if rr and cc and (len(rr) > 1 or len(cc) > 1):
                        merges.append((rr[0], cc[0], rr[-1], cc[-1]))
        rows = [[texts[(i, j)] for j in cols_keep] for i in rows_keep]
    except Exception as e:  # noqa: BLE001
        raise X.ExcelNotReady("엑셀 범위를 읽지 못했습니다: %s" % e)
    return rows, merges, widths, heights, aligns


def draw_lisp(rows, origin, cfg, merges=(), widths_pt=None, heights_pt=None, aligns=None):
    h = float(cfg["문자높이"])
    k = h / max(float(cfg["기준글꼴"]), 1e-6)  # 1pt → 도면 단위
    nc = max(len(r) for r in rows)
    if widths_pt and cfg["크기"] == "엑셀 크기대로":
        widths = [w * k for w in widths_pt]
        heights = [v * k for v in heights_pt] if heights_pt else 2 * h
    else:
        widths = [max(4 * h, max((max(len(s) for s in str(r[j]).split("\n")) if j < len(r) else 0) for r in rows) * 0.9 * h + 2 * h)
                  for j in range(nc)]
        heights = [max(2 * h, (str(max(r, key=lambda v: str(v).count("\n"))).count("\n") + 1) * 1.6 * h + 0.8 * h) for r in rows]

    def al(i, j, v):
        if aligns and (i, j) in aligns:
            return aligns[(i, j)]
        return "R" if X.to_float(v) is not None else "L"
    code, W, H = TB.table_lisp(rows, origin, widths, heights, h, cfg["문자레이어"], cfg["선레이어"], merges, al)
    return code, W, H


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "엑셀 표 캐드로", size="480x360")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="엑셀 선택 범위 → 표 넣을 점(왼쪽 위) 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            rows, merges, widths, heights, aligns = read_excel()
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        pick = self.in_cad(self.acad.lisp, '(setq _o (getpoint "\\n표 넣을 점(왼쪽 위) 지정: ")) (if _o (progn'
                           ' (setq _o (trans _o 1 0)) (write-line (strcat (bc:rtos (car _o) 2 10) _d (bc:rtos (cadr _o) 2 10)) _fp)))',
                           A.PICK_TIMEOUT)
        if not pick:
            return
        code, _w, _h = draw_lisp(rows, [float(v) for v in pick[0].split("\t")], cfg, merges, widths, heights, aligns)
        if self.in_cad(self.acad.lisp_undo, code, 180) is not None:
            self.status("%d행 × %d열 표를 그렸습니다." % (len(rows), len(rows[0]) if rows else 0))


def main():
    Window().mainloop()
