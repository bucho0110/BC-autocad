# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CTE 도면 표를 엑셀로 옮기기 — 선과 문자로 된 CAD 표를 엑셀 표로 옮긴다(병합 칸 포함).

표의 가로·세로선 위치로 칸을 나누고, 칸 사이에 선이 없으면 병합으로 본다. 끊긴 선·겹친 선도 된다.
한 칸에 문자가 여러 개면 위 → 아래(줄 바꿈), 왼 → 오른(띄어쓰기)으로 잇는다. 기울어진 선은 무시한다.
parse()·grid()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui

CMD = "CTE"
FIELDS = [
    ("병합", "병합 칸을 엑셀에서도 병합", "bool", True, None),
    ("숫자로", "숫자로 읽히는 값은 숫자로", "bool", True, None),
    ("허용오차", "선 위치 허용오차 (도면 단위, 0 = 자동)", "real", 0.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

DUMP_LISP = (
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)))'
    ' (cond ((member _ty (list "LINE" "LWPOLYLINE" "POLYLINE")) (setq _v (bc:verts _en))'
    '   (if (and (assoc 70 _ed) (= 1 (logand 1 (cdr (assoc 70 _ed))))) (setq _v (append _v (list (car _v)))))'
    '   (while (cdr _v) (write-line (strcat "S" _d (bc:rtos (caar _v) 2 8) _d (bc:rtos (cadar _v) 2 8) _d'
    '    (bc:rtos (caadr _v) 2 8) _d (bc:rtos (cadadr _v) 2 8)) _fp) (setq _v (cdr _v))))'
    '  ((member _ty (list "TEXT" "MTEXT")) (setq _c (bc:obj-center _en))'
    '   (write-line (strcat "T" _d (bc:rtos (car _c) 2 8) _d (bc:rtos (cadr _c) 2 8) _d'
    '    (vl-string-translate "\\t\\n\\r" "   " (bc:text-of _en))) _fp))))')


def parse(rows):
    segs, texts = [], []
    for r in rows:
        c = r.split("\t")
        if c[0] == "S" and len(c) == 5:
            segs.append(tuple(float(v) for v in c[1:]))
        elif c[0] == "T" and len(c) >= 3:
            texts.append((float(c[1]), float(c[2]), c[3].strip() if len(c) > 3 else ""))
    return segs, texts


def _uniq(vals, tol):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def grid(segs, texts, tol=0.0):
    """→ (rows, merges [(r0, c0, r1, c1)]). 가로·세로가 아닌 선은 버린다."""
    hs, vs = [], []
    span = max([abs(s[2] - s[0]) + abs(s[3] - s[1]) for s in segs] or [1.0])
    tol = tol or span * 1e-4
    for x1, y1, x2, y2 in segs:
        if abs(y2 - y1) <= tol and abs(x2 - x1) > tol:
            hs.append(((y1 + y2) / 2, min(x1, x2), max(x1, x2)))
        elif abs(x2 - x1) <= tol and abs(y2 - y1) > tol:
            vs.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
    if not hs or not vs:
        raise ValueError("표의 가로·세로선을 찾지 못했습니다.")
    ys = _uniq([h[0] for h in hs], tol)[::-1]
    xs = _uniq([v[0] for v in vs], tol)
    nr, nc = len(ys) - 1, len(xs) - 1
    if nr < 1 or nc < 1:
        raise ValueError("칸을 만들 수 없습니다(가로선·세로선이 둘 이상씩 있어야 합니다).")

    def covered(lines, pos, a, b):
        return any(abs(L[0] - pos) <= tol and L[1] <= a + tol and L[2] >= b - tol for L in lines)

    parent = {(i, j): (i, j) for i in range(nr) for j in range(nc)}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i in range(nr):
        for j in range(nc):
            if j + 1 < nc and not covered(vs, xs[j + 1], ys[i + 1], ys[i]):
                parent[find((i, j + 1))] = find((i, j))
            if i + 1 < nr and not covered(hs, ys[i + 1], xs[j], xs[j + 1]):
                parent[find((i + 1, j))] = find((i, j))
    groups = {}
    for k in parent:
        groups.setdefault(find(k), []).append(k)
    owner, merges = {}, []
    for cells in groups.values():
        r0, c0 = min(c[0] for c in cells), min(c[1] for c in cells)
        r1, c1 = max(c[0] for c in cells), max(c[1] for c in cells)
        for c in cells:
            owner[c] = (r0, c0)
        if (r0, c0) != (r1, c1):
            merges.append((r0, c0, r1, c1))
    buckets = {}
    for x, y, t in texts:
        if not t or not (xs[0] - tol <= x <= xs[-1] + tol and ys[-1] - tol <= y <= ys[0] + tol):
            continue
        j = max(0, min(nc - 1, sum(1 for v in xs[1:-1] if x > v)))
        i = max(0, min(nr - 1, sum(1 for v in ys[1:-1] if y < v)))
        buckets.setdefault(owner[(i, j)], []).append((x, y, t))
    rows = [[""] * nc for _ in range(nr)]
    for (i, j), items in buckets.items():
        items.sort(key=lambda p: (-p[1], p[0]))
        lines, cur, cy = [], [], None
        hgt = max(1e-9, (ys[i] - ys[i + 1]) * 0.3)
        for x, y, t in items:
            if cy is not None and abs(y - cy) > hgt:
                lines.append(" ".join(cur))
                cur = []
            cur.append(t)
            cy = y
        lines.append(" ".join(cur))
        rows[i][j] = "\n".join(lines)
    return rows, sorted(merges)


def to_excel(rows, merges, cfg):
    ws, r0, c0 = X.active_cell()
    data = [[(X.to_float(v) if cfg["숫자로"] and X.to_float(v) is not None and "\n" not in v else v) for v in r] for r in rows]
    X.write_rows(ws, r0, c0, data)
    if cfg["병합"]:
        xl = X.app()
        xl.DisplayAlerts = False
        try:
            for a, b, c, d in merges:
                rng = ws.Range(ws.Cells(r0 + a, c0 + b), ws.Cells(r0 + c, c0 + d))
                rng.Merge()
                rng.HorizontalAlignment = -4108
                rng.VerticalAlignment = -4108
        finally:
            xl.DisplayAlerts = True


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "도면 표를 엑셀로 옮기기", size="480x330")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀에서 표를 넣을 첫 칸을 고른 뒤 실행하세요.", bg=ui.BG, fg=ui.STATUS,
                 font=ui.FONT).pack(fill="x", padx=10)
        tk.Button(self, text="CAD 표(선·문자) 선택 → 엑셀로", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n표 전체 선택: ") (setq _ss (ssget (list (cons 0 "LINE,LWPOLYLINE,POLYLINE,TEXT,MTEXT")))) %s'
                           % DUMP_LISP, A.PICK_TIMEOUT)
        if not rows:
            return
        try:
            tbl, merges = grid(*parse(rows), float(cfg["허용오차"]))
            to_excel(tbl, merges, cfg)
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        self.status("%d행 × %d열(병합 %d)을 엑셀에 넣었습니다." % (len(tbl), len(tbl[0]), len(merges)))


def main():
    Window().mainloop()
